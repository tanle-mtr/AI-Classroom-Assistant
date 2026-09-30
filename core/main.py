# -*- coding: utf-8 -*-
"""AI 课堂助手 —— Python 核心入口。

启动：python main.py [--port 18760]  （或 python -m core.main）
无窗口打包：PyInstaller --noconsole（逻辑写日志文件，不依赖 stdout）
"""

import argparse
import logging
import os
import socket
import sys
from pathlib import Path

# 保证以脚本方式运行（python main.py / pythonw main.py）时包导入可用
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "core.log", encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("main")


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    from core.config import config

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=config.get("server.port", 18760))
    args, _ = parser.parse_known_args()

    # 端口占用则顺延（v1 教训：僵尸进程占端口时自动避让）
    port = args.port
    while port_in_use(port) and port < args.port + 20:
        log.warning("端口 %s 被占用，尝试 %s", port, port + 1)
        port += 1
    config.set("server.port", port)
    config.save()

    from core.api import create_app
    import uvicorn

    app = create_app()
    log.info("核心启动: http://127.0.0.1:%s", port)
    try:
        # log_config=None：沿用上方 basicConfig（文件+stderr），避免 dictConfig 冲突
        uvicorn.run(app, host=config.get("server.host", "127.0.0.1"),
                    port=port, log_config=None, log_level="warning")
    except Exception as exc:  # noqa: BLE001
        log.exception("uvicorn 启动失败: %s", exc)


if __name__ == "__main__":
    main()
