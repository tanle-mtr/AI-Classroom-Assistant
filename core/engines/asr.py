# -*- coding: utf-8 -*-
"""本地语音转写（faster-whisper，默认关闭，2 核机器慎开）。"""
import logging
import threading

from core.config import config
from core.events import bus

log = logging.getLogger("asr")


class AsrEngine:
    def __init__(self):
        self._enabled = config.get("asr.enabled", False)
        self._model = None
        bus.subscribe("lesson.ended", self._on_end)

    def _on_end(self, lesson=None, **_):
        if not self._enabled:
            return
        try:
            from faster_whisper import WhisperModel
            if self._model is None:
                self._model = WhisperModel(config.get("asr.model", "tiny"),
                                           device="cpu", compute_type="int8")
            import os
            rec = None
            # 转写最近一段课程录音（monitoring 目录下该课切片 wav）
            for p in sorted((config.get("output.monitoring_dir") or "data/monitoring").rglob("*.wav")):
                rec = p
            if rec:
                segments, _ = self._model.transcribe(str(rec))
                text = "\n".join(s.text for s in segments)
                log.info("[asr] 转写完成（%s 字）：%s", len(text), text[:80])
        except Exception as exc:  # noqa: BLE001
            log.warning("ASR 转写失败: %s", exc)


asr_engine = AsrEngine()
