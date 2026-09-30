# -*- coding: utf-8 -*-
"""座位表引擎：图片上传识图建表 + 上课摄像头换座检测。"""
import base64
import json
import logging
import re
import threading
import time
from pathlib import Path
from datetime import datetime

from core.config import ROOT
from core.events import bus

log = logging.getLogger("roster")

ROSTER_DIR = ROOT / "data" / "roster"
ROSTER_JSON = ROSTER_DIR / "roster.json"
FACES_DIR = ROSTER_DIR / "faces"
LAST_FRAME = ROSTER_DIR / "last_frame.jpg"

DEFAULT_ROSTER = {"seats": [], "updated": "", "columns": 0, "rows": 0}


def _load_roster() -> dict:
    if ROSTER_JSON.exists():
        try:
            return json.loads(ROSTER_JSON.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("座位表读取失败: %s", exc)
    return dict(DEFAULT_ROSTER)


def _save_roster(data: dict):
    ROSTER_JSON.parent.mkdir(parents=True, exist_ok=True)
    ROSTER_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _vision_describe(image_path: Path) -> str:
    """调用视觉模型描述图片（识图 skill 的核心实现）。"""
    import urllib.request
    from core.config import config
    base = config.get("ollama.base_url") or "http://127.0.0.1:11434"
    model = config.get("ollama.vision_model") or config.get("ollama.model") or "gemma3:4b"
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    body = {"model": model, "prompt": "请识别这张教室座位表图片：输出每行每列的姓名，JSON 数组格式。",
            "images": [b64], "stream": False}
    req = urllib.request.Request(
        f"{base}/api/generate", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("response", "")


def _parse_seats(text: str) -> list:
    """从视觉模型输出中提取座位数组。"""
    match = re.search(r"\[\s*\[.*?\]\s*\]", text, re.S)
    if not match:
        return []
    try:
        arr = json.loads(match.group(0))
        seats = []
        for r_i, row in enumerate(arr):
            for c_i, name in enumerate(row):
                if name:
                    seats.append({"row": r_i + 1, "col": c_i + 1, "name": str(name).strip()})
        return seats
    except Exception as exc:  # noqa: BLE001
        log.warning("座位解析失败: %s", exc)
        return []


async def save_roster_image(file) -> dict:
    """API：上传座位表图片 → 识图建表。"""
    ROSTER_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "roster.png").suffix or ".png"
    img = ROSTER_DIR / f"roster_image{ext}"
    img.write_bytes(await file.read())
    text = _vision_describe(img)
    seats = _parse_seats(text)
    roster = {"seats": seats, "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
              "columns": max((s["col"] for s in seats), default=0),
              "rows": max((s["row"] for s in seats), default=0)}
    _save_roster(roster)
    log.info("[roster] 座位表已更新：%s 人", len(seats))
    return {"ok": True, "count": len(seats), "raw": text[:200]}


def detect_seating(frame_path: Path) -> dict:
    """换座检测：对比当前画面与 roster 座位布局。"""
    roster = _load_roster()
    if not roster.get("seats"):
        return {"moved": False, "reason": "无座位表基线"}
    text = _vision_describe(frame_path)
    current = _parse_seats(text)
    if not current:
        return {"moved": False, "reason": "当前画面无法识别"}
    # 简单对比：姓名集合差异
    old = {s["name"] for s in roster["seats"]}
    now = {s["name"] for s in current}
    missing = old - now
    if missing:
        return {"moved": True, "suggested": list(missing)[:5],
                "reason": "检测到座位变化，建议更新座位表"}
    return {"moved": False}


def apply_move(confirmed: dict) -> dict:
    """确认换座：更新座位表。"""
    roster = _load_roster()
    moves = confirmed.get("moves") or []
    for mv in moves:
        name = mv.get("name", "")
        row, col = int(mv.get("row", 0)), int(mv.get("col", 0))
        if not name or row <= 0 or col <= 0:
            continue
        for seat in roster["seats"]:
            if seat["name"] == name:
                seat["row"], seat["col"] = row, col
    roster["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_roster(roster)
    return {"ok": True, "count": len(roster["seats"])}


def export_roster() -> Path | None:
    """导出座位表为 Markdown 表格。"""
    roster = _load_roster()
    if not roster.get("seats"):
        return None
    out = ROSTER_DIR / "座位表.md"
    lines = ["# 班级座位表\n", f"更新于：{roster.get('updated', '')}\n"]
    lines.append("| 行 | 列 | 姓名 |\n|---|----|----|")
    for s in sorted(roster["seats"], key=lambda x: (x["row"], x["col"])):
        lines.append(f"| {s['row']} | {s['col']} | {s['name']} |")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
