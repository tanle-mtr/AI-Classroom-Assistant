# -*- coding: utf-8 -*-
"""远程访问引擎：OpenList 文件浏览 + Cloudflare 隧道（cloudflared，免 VPS）。

工具自动下载到 tools/（GitHub 直链，网络受限时提示手动放入）。
"""
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.request import urlretrieve

from core.config import config, ROOT

log = logging.getLogger("remote")

TOOLS_DIR = ROOT / "tools"
OPENLIST_ZIP = TOOLS_DIR / "openlist.zip"
OPENLIST_DIR = TOOLS_DIR / "openlist"
OPENLIST_EXE = OPENLIST_DIR / "openlist.exe"
CLOUDFLARED_EXE = TOOLS_DIR / "cloudflared.exe"

OPENLIST_URL = "https://github.com/OpenListTeam/OpenList/releases/download/v4.2.6/openlist-windows-amd64-lite.zip"
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

_openlist_proc = None
_tunnel_proc = None


def _ensure_tools():
    """后台线程自动下载（存在即用）。"""
    def download(url, target):
        if target.exists() and target.stat().st_size > 100_000:
            return True
        try:
            TOOLS_DIR.mkdir(parents=True, exist_ok=True)
            urlretrieve(url, str(target))
            return target.exists() and target.stat().st_size > 100_000
        except Exception as exc:  # noqa: BLE001
            log.warning("工具下载失败（网络受限可手动放入 tools/）: %s", exc)
            return False

    def run():
        ok = download(OPENLIST_URL, OPENLIST_ZIP)
        if ok and not OPENLIST_EXE.exists():
            import zipfile
            try:
                with zipfile.ZipFile(OPENLIST_ZIP) as z:
                    z.extractall(OPENLIST_DIR)
            except Exception as exc:  # noqa: BLE001
                log.warning("OpenList 解压失败: %s", exc)
        download(CLOUDFLARED_URL, CLOUDFLARED_EXE)

    threading.Thread(target=run, daemon=True).start()


_ensure_tools()  # 模块导入即启动后台下载


def start_openlist() -> bool:
    """启动 OpenList 挂载导出目录（端口 5244）。"""
    global _openlist_proc
    if _openlist_proc and _openlist_proc.poll() is None:
        return True
    if not OPENLIST_EXE.exists():
        log.warning("OpenList 未就绪（tools/openlist/openlist.exe 缺失）")
        return False
    export_dir = ROOT / "data" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    _openlist_proc = subprocess.Popen(
        [str(OPENLIST_EXE), "--dir", str(export_dir), "--port", "5244"],
        creationflags=subprocess.CREATE_NO_WINDOW)
    log.info("[remote] OpenList 启动 :5244")
    return True


def start_tunnel() -> bool:
    """启动 Cloudflare 隧道（token 模式，免登录）。"""
    global _tunnel_proc
    if _tunnel_proc and _tunnel_proc.poll() is None:
        return True
    token = config.get("remote.tunnel_token", "")
    if not token:
        log.warning("[remote] 未配置 Cloudflare 隧道 token（设置页填入后自动启动）")
        return False
    if not CLOUDFLARED_EXE.exists():
        log.warning("cloudflared 未就绪（tools/cloudflared.exe 缺失）")
        return False
    _tunnel_proc = subprocess.Popen(
        [str(CLOUDFLARED_EXE), "tunnel", "--no-autoupdate", "run", "--token", token],
        creationflags=subprocess.CREATE_NO_WINDOW)
    log.info("[remote] Cloudflare 隧道启动")
    return True


def stop_remote():
    global _openlist_proc, _tunnel_proc
    for proc in (_openlist_proc, _tunnel_proc):
        if proc and proc.poll() is None:
            proc.terminate()
    _openlist_proc = _tunnel_proc = None


def status() -> dict:
    return {
        "openlist": bool(_openlist_proc and _openlist_proc.poll() is None),
        "openlist_url": "http://127.0.0.1:5244" if (_openlist_proc and _openlist_proc.poll() is None) else "",
        "tunnel": bool(_tunnel_proc and _tunnel_proc.poll() is None),
        "public_ip": config.get("remote.public_ip", ""),
        "tools_ready": {
            "cloudflared": CLOUDFLARED_EXE.exists(),
            "openlist": OPENLIST_EXE.exists(),
        },
    }
