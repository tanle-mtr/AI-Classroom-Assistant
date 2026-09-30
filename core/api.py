# -*- coding: utf-8 -*-
"""FastAPI 路由：核心对外接口（Web 控制台 + C# 桥 + 托盘共用）。"""

import json
import logging
import threading
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from core.config import config, ROOT, DATA_DIR
from core.state import state, LESSON_TYPES

# 导入即注册事件订阅（感知/分贝记录/ASR/产出/监控 随课程事件启停）
import core.engines.perception  # noqa: F401
import core.engines.db_logger  # noqa: F401
import core.engines.asr  # noqa: F401
import core.engines.summarizer  # noqa: F401
import core.engines.monitor  # noqa: F401
import core.engines.remote  # noqa: F401
from core.engines.perception import manager as perception_manager
from core.engines.monitor import monitor as monitor_engine
from core.engines import remote as remote_engine

log = logging.getLogger("api")
app = FastAPI(title="AI 课堂助手核心", docs_url=None, redoc_url=None)

# ---------------- 后台缓存（根治 v1 卡顿：网络请求绝不进请求线程） ----------------

_public_ip_cache: dict = {"ip": "", "ts": 0.0}
_models_cache: dict = {"models": [], "ts": 0.0}
_lock = threading.Lock()


def refresh_public_ip(force: bool = False):
    """后台线程更新公网 IP（ipify 免费接口）。"""
    import time
    now = time.time()
    with _lock:
        if not force and now - _public_ip_cache["ts"] < 300:
            return
    try:
        # 优先 ipify；中国网络不可达时换 3322（国内稳定）
        for url in ("https://api.ipify.org?format=json", "https://myip.ipip.net/"):
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    text = resp.read().decode("utf-8", errors="ignore")
                import re
                found = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
                if found:
                    with _lock:
                        _public_ip_cache.update(ip=found.group(1), ts=time.time())
                        config.set("remote.public_ip", found.group(1))
                        config.save()
                    return
            except Exception:  # noqa: BLE001
                continue
        log.warning("公网 IP 获取失败：所有接口不可达")
    except Exception as exc:  # noqa: BLE001
        log.warning("公网 IP 获取失败: %s", exc)


def refresh_models(force: bool = False):
    """后台线程探测 Ollama 已安装模型（启动时/手动刷新）。"""
    import time
    now = time.time()
    with _lock:
        if not force and now - _models_cache["ts"] < 60:
            return
    base = config.get("ollama.base_url") or "http://127.0.0.1:11434"
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
        with _lock:
            _models_cache.update(models=names, ts=time.time())
            config.set("ollama.available_models", names)
            if names:
                if config.get("ollama.model") not in names:
                    config.set("ollama.model", names[0])
                if config.get("ollama.vision_model") not in names:
                    # 优先选带视觉能力的模型
                    vis = next((n for n in names if any(k in n.lower() for k in
                              ("gemma3", "llava", "qwen2.5-vl", "minicpm", "vision"))), names[0])
                    config.set("ollama.vision_model", vis)
                config.save()
    except Exception as exc:  # noqa: BLE001
        log.warning("Ollama 模型探测失败: %s", exc)


def _start_background_refresh():
    threading.Thread(target=refresh_models, daemon=True).start()
    threading.Thread(target=refresh_public_ip, daemon=True).start()


# ---------------- 课程事件（ClassIsland 桥推送） ----------------

@app.post("/api/events/lesson")
async def on_lesson_event(payload: dict):
    event = payload.get("event")
    lesson = payload.get("lesson") or {}
    if event == "started":
        state.on_lesson_started(lesson)
    elif event == "ended":
        state.on_lesson_ended(lesson)
    else:
        return JSONResponse({"ok": False, "error": f"未知事件: {event}"}, status_code=400)
    return {"ok": True}


# ---------------- 状态与配置 ----------------

@app.get("/api/state")
async def get_state():
    snap = state.snapshot()
    snap["server"] = {
        "port": config.get("server.port"),
        "public_ip": _public_ip_cache["ip"],
        "ollama_models": _models_cache["models"],
        "ollama_model": config.get("ollama.model") or "",
        "ollama_vision": config.get("ollama.vision_model") or "",
        "monitoring": config.get("monitoring.enabled"),
    }
    return snap


@app.get("/api/config")
async def get_config():
    return config.data()


@app.post("/api/config")
async def set_config(payload: dict):
    for key, value in payload.items():
        config.set(key, value)
    config.save()
    if key == "remote.public_ip":
        threading.Thread(target=refresh_public_ip, kwargs={"force": True}, daemon=True).start()
    return {"ok": True}


@app.get("/api/perception")
async def get_perception():
    """当前感知状态（麦克风/摄像头/屏幕是否激活 + 实时数据）。"""
    return {
        "active": perception_manager.active,
        "mic_db": round(perception_manager.mic.average_db(), 1)
                   if perception_manager.mic else None,
        "screen_active": perception_manager.screen.active_ratio
                           if perception_manager.screen else None,
        "face_count": perception_manager.cam.last_face_count
                       if perception_manager.cam else None,
        "baseline": perception_manager.cam.baseline
                      if perception_manager.cam else None,
    }


@app.post("/api/models/refresh")
async def refresh_models_api():
    threading.Thread(target=refresh_models, kwargs={"force": True}, daemon=True).start()
    return {"ok": True}


@app.get("/api/lesson_types")
async def lesson_types():
    return {"types": list(LESSON_TYPES)}


# ---------------- 总结文件 ----------------

@app.get("/api/summaries")
async def list_summaries():
    out_dir = ROOT / (config.get("output.dir") or "data/summaries")
    files = []
    if out_dir.exists():
        for p in sorted(out_dir.rglob("*.md"), reverse=True):
            files.append({
                "path": str(p.relative_to(ROOT)).replace("\\", "/"),
                "name": p.name,
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            })
    return {"files": files}


@app.get("/api/summary")
async def get_summary(path: str):
    target = (ROOT / path).resolve()
    if not str(target).startswith(str(ROOT.resolve())) or not target.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    return FileResponse(target, media_type="text/markdown")


# ---------------- 课件上传（按科目自动分类，无口令） ----------------

@app.post("/api/courseware")
async def upload_courseware(subject: str = Form("未分类"), file: UploadFile = File(...)):
    subject = (subject or "未分类").strip()
    config.ensure_subject(subject)
    sub_dir = ROOT / config.get("output.courseware_dir") / subject
    sub_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    target = sub_dir / safe_name
    data = await file.read()
    target.write_bytes(data)
    return {"ok": True, "path": str(target.relative_to(ROOT)).replace("\\", "/")}


# ---------------- 座位表 ----------------

@app.post("/api/roster")
async def upload_roster(file: UploadFile = File(...)):
    from core.engines.roster import save_roster_image
    return await save_roster_image(file)


@app.get("/api/roster")
async def get_roster():
    from core.engines.roster import _load_roster, ROSTER_JSON
    roster = _load_roster()
    return {"exists": ROSTER_JSON.exists(), "seats": roster.get("seats", []),
            "updated": roster.get("updated", ""),
            "face_samples": sum(1 for p in (ROSTER_JSON.parent / "faces").glob("*/*")
                                if p.is_file()) if (ROSTER_JSON.parent / "faces").exists() else 0}


@app.post("/api/roster/detect")
async def detect_roster(file: UploadFile = File(...)):
    """上传当前摄像头画面，检测换座（真实场景由感知引擎定时调用）。"""
    from core.engines.roster import detect_seating
    tmp = ROOT / "data" / "roster" / "last_frame.jpg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(await file.read())
    result = detect_seating(tmp)
    return result


@app.post("/api/roster/apply")
async def apply_roster(payload: dict):
    from core.engines.roster import apply_move
    return apply_move(payload.get("confirmed", {}))


@app.get("/api/roster/export")
async def export_roster():
    from core.engines.roster import export_roster
    out = export_roster()
    if out is None:
        return JSONResponse({"error": "座位表为空"}, status_code=404)
    return FileResponse(out, media_type="text/markdown",
                        filename=out.name)


# ---------------- 监控与导出 ----------------

@app.post("/api/monitor/export")
async def export_monitoring():
    """全量导出（关机前/手动）：监控+总结+座位表 → data/exports。"""
    files = monitor_engine.export()
    return {"ok": True, "count": len(files)}


@app.post("/api/monitor/cleanup")
async def cleanup_monitoring():
    removed = monitor_engine.cleanup()
    return {"ok": True, "removed": removed}


@app.get("/api/monitor/status")
async def monitor_status():
    return {
        "recording": monitor_engine._active,
        "retention_days": config.get("monitoring.retention_days", 14),
        "enabled": config.get("monitoring.enabled", True),
    }


# ---------------- 远程访问（Cloudflare 隧道 + OpenList） ----------------

@app.get("/api/remote/status")
async def remote_status():
    return remote_engine.status()


@app.post("/api/remote/start")
async def remote_start(payload: dict | None = None):
    """启动远程：cf 隧道（token 在 config/remote/tunnel_token）+ OpenList。"""
    if payload and payload.get("tunnel_token"):
        config.set("remote.tunnel_token", payload["tunnel_token"])
        config.save()
    openlist_ok = remote_engine.start_openlist()
    tunnel_ok = remote_engine.start_tunnel()
    return {"ok": True, "openlist": openlist_ok, "tunnel": tunnel_ok,
            **remote_engine.status()}


@app.post("/api/remote/stop")
async def remote_stop():
    remote_engine.stop_remote()
    return {"ok": True}


# ---------------- 静态 Web 控制台 ----------------

_DIST = ROOT / "webui" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="webui")
else:
    @app.get("/")
async def index_stub():
        return JSONResponse({"ok": True, "msg": "webui 尚未构建（npm run build 后访问）",
                             "api": "/api/state"})


def create_app():
    _start_background_refresh()
    monitor_engine.cleanup()          # 启动即滚动清理过期监控
    from core.engines.monitor import _cleanup_daily
    _cleanup_daily()                  # 每 6 小时再清理一次
    return app
