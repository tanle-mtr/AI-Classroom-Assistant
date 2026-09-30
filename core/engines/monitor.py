# -*- coding: utf-8 -*-
"""监控引擎：上课自动录制（摄像头 mp4 + 麦克风 wav，共享模式），下课切片保存；
14 天滚动清理；关机/手动全量导出。"""
import logging
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from core.config import config, ROOT
from core.events import bus

log = logging.getLogger("monitor")

MONITOR_DIR = ROOT / (config.get("output.monitoring_dir") or "data/monitoring")
EXPORT_DIR = ROOT / "data" / "exports"


class MonitorEngine:
    def __init__(self):
        self._active = False
        self._writer = None
        self._stop = threading.Event()
        self._retention_days = config.get("monitoring.retention_days", 14)
        bus.subscribe("lesson.started", self._on_start)
        bus.subscribe("lesson.ended", self._on_end)

    def _on_start(self, lesson=None, **_):
        if not config.get("monitoring.enabled", True):
            return
        self._stop.clear()
        self._active = True
        threading.Thread(target=self._record, args=(lesson,), daemon=True).start()

    def _on_end(self, lesson=None, **_):
        self._stop.set()
        self._active = False
        log.info("[monitor] 下课，监控切片保存")

    def _record(self, lesson):
        """录制线程：摄像头帧写 mp4 + 麦克风采样写 wav（共享模式）。"""
        try:
            import cv2
            name = lesson.name or "未命名课程"
            ts = datetime.now().strftime("%H%M")
            date = datetime.now().strftime("%Y-%m-%d")
            out = MONITOR_DIR / date
            out.mkdir(parents=True, exist_ok=True)
            base = out / f"{name}_{ts}"

            # 麦克风（WASAPI 共享）
            import sounddevice as sd
            import numpy as np
            wav_path = Path(str(base) + ".wav")
            samplerate = 16000
            frames = []
            mic_stream = sd.InputStream(samplerate=samplerate, channels=1,
                                        dtype="float32", exclusive=False)
            mic_stream.start()

            # 摄像头（共享打开）
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
            mp4_path = Path(str(base) + ".mp4")
            writer = None
            fps = 10
            last = time.time()

            while not self._stop.is_set():
                # 音频
                try:
                    data, _ = mic_stream.read(1600)
                    frames.append(data)
                except Exception:  # noqa: BLE001
                    pass
                # 视频
                ok, frame = cap.read()
                if ok and time.time() - last > 1.0 / fps:
                    if writer is None:
                        h, w = frame.shape[:2]
                        writer = cv2.VideoWriter(str(mp4_path), cv2.VideoWriter_fourcc(*"mp4v"),
                                                 fps, (w, h))
                    writer.write(frame)
                    last = time.time()
                time.sleep(0.05)

            mic_stream.stop()
            cap.release()
            if writer:
                writer.release()
            if frames:
                audio = np.concatenate(frames) if frames else np.zeros(1, dtype="float32")
                import wave
                with wave.open(str(wav_path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(samplerate)
                    wf.writeframes((audio * 32767).astype(np.int16).tobytes())
            log.info("[monitor] 录制保存: %s", base)
        except Exception as exc:  # noqa: BLE001
            log.warning("监控录制失败: %s", exc)

    def cleanup(self) -> int:
        """14 天滚动清理。"""
        cutoff = datetime.now() - timedelta(days=self._retention_days)
        removed = 0
        for date_dir in MONITOR_DIR.glob("*"):
            if date_dir.is_dir():
                try:
                    d = datetime.strptime(date_dir.name, "%Y-%m-%d")
                    if d < cutoff:
                        shutil.rmtree(date_dir, ignore_errors=True)
                        removed += 1
                except ValueError:
                    continue
        if removed:
            log.info("[monitor] 清理过期监控 %s 天目录", removed)
        return removed

    def export(self) -> list:
        """全量导出：监控+总结+座位表 → data/exports（分类）。"""
        files = []
        for src_name in ("monitoring", "summaries", "roster"):
            src = ROOT / "data" / src_name
            dst = EXPORT_DIR / src_name
            if src.exists():
                shutil.copytree(src, dst, dirs_exist_ok=True)
                files.extend(str(p) for p in dst.rglob("*"))
        log.info("[monitor] 导出完成 %s 个文件", len(files))
        return files


monitor = MonitorEngine()


def _cleanup_daily():
    """每 6 小时滚动清理（daemon 线程）。"""
    def loop():
        while True:
            time.sleep(6 * 3600)
            monitor.cleanup()
    threading.Thread(target=loop, daemon=True).start()
