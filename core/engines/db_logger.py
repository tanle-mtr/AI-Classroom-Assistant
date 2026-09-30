# -*- coding: utf-8 -*-
"""分贝日志引擎：每分钟记录一次平均分贝到 data/logs/db_minutes.jsonl（考试/自习报告用）。"""
import json
import logging
import threading
import time
from pathlib import Path

from core.config import ROOT
from core.events import bus

log = logging.getLogger("db_logger")
DB_FILE = ROOT / "data" / "logs" / "db_minutes.jsonl"


class DbLogger:
    def __init__(self):
        self._stop = threading.Event()
        self._started = False
        bus.subscribe("lesson.started", self._on_start)
        bus.subscribe("lesson.ended", self._on_end)

    def _on_start(self, lesson=None, **_):
        if self._started:
            return
        self._started = True
        self._stop.clear()
        threading.Thread(target=self._loop, daemon=True).start()

    def _on_end(self, lesson=None, **_):
        self._stop.set()
        self._started = False

    def _loop(self):
        from core.engines.perception import manager
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            while not self._stop.is_set():
                db = manager.mic.average_db()
                if db is not None:
                    record = {"ts": time.time(), "db": db}
                    with DB_FILE.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                time.sleep(60)
        except Exception as exc:  # noqa: BLE001
            log.warning("分贝日志写入失败: %s", exc)


db_logger = DbLogger()
