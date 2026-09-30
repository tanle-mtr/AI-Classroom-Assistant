# -*- coding: utf-8 -*-
"""感知管理器：麦克风（WASAPI 共享）/ 摄像头（MediaFoundation 共享）/ 屏幕差分活跃度。

不独占设备：共享模式采集，其他进程可同时使用麦克风/摄像头。
"""
import logging
import threading
import time
from dataclasses import dataclass, field

from core.config import config
from core.events import bus

log = logging.getLogger("perception")


@dataclass
class MicProbe:
    """WASAPI 共享模式分贝采样（每 1 秒取一次）。"""
    enabled: bool = True
    db_buffer: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def start(self):
        if not self.enabled:
            return
        self._stop.clear()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        import sounddevice as sd
        import numpy as np
        try:
            with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                                blocksize=1600, exclusive=False) as stream:
                while not self._stop.is_set():
                    data, _ = stream.read(1600)
                    rms = float(np.sqrt(np.mean(data ** 2)))
                    db = 20 * np.log10(rms + 1e-6)
                    with self._lock:
                        self.db_buffer.append(round(float(db), 1))
                        self.db_buffer = self.db_buffer[-1800:]
        except Exception as exc:  # noqa: BLE001
            log.warning("麦克风采样失败（可能被独占或无声卡）: %s", exc)

    def average_db(self):
        with self._lock:
            if not self.db_buffer:
                return None
            return sum(self.db_buffer) / len(self.db_buffer)

    def minute_series(self):
        """每分钟平均分贝（考试/自习报告用折线数据）。"""
        with self._lock:
            if not self.db_buffer:
                return []
            n = len(self.db_buffer) // 60
            series = []
            for i in range(n):
                seg = self.db_buffer[i * 60:(i + 1) * 60]
                series.append(round(sum(seg) / len(seg), 1))
            return series


@dataclass
class ScreenProbe:
    enabled: bool = True
    active_ratio: float = 0.0
    _last: object = None
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def start(self):
        if not self.enabled:
            return
        self._stop.clear()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        from PIL import ImageGrab
        import numpy as np
        try:
            while not self._stop.is_set():
                img = ImageGrab.grab()
                small = np.asarray(img.resize((160, 90), ImageGrab.Image.LANCZOS))[:, :, :3]
                if self._last is not None:
                    diff = np.mean(np.abs(small.astype(int) - self._last.astype(int)))
                    self.active_ratio = min(1.0, diff / 12.0)
                self._last = small
                time.sleep(1.0)
        except Exception as exc:  # noqa: BLE001
            log.warning("屏幕采样失败: %s", exc)


@dataclass
class CamProbe:
    enabled: bool = True
    baseline: int = 0          # 就座人数基线（首次上课建立）
    last_face_count: int = 0
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def start(self):
        if not self.enabled:
            return
        self._stop.clear()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        import cv2
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # 共享打开，不独占
            if not cap.isOpened():
                cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(2)
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
                self.last_face_count = len(faces)
                if self.baseline == 0 and len(faces) > 0:
                    self.baseline = len(faces)
                time.sleep(3)
            cap.release()
        except Exception as exc:  # noqa: BLE001
            log.warning("摄像头采样失败（无摄像头或已被占用）: %s", exc)


class PerceptionManager:
    def __init__(self):
        self.mic = MicProbe(enabled=config.get("perception.mic_enabled", True))
        self.screen = ScreenProbe(enabled=config.get("perception.screen_enabled", True))
        self.cam = CamProbe(enabled=config.get("perception.cam_enabled", True))
        self.active = False
        bus.subscribe("lesson.started", self._on_start)
        bus.subscribe("lesson.ended", self._on_end)

    def _on_start(self, lesson=None, **_):
        self.active = True
        self.mic.start()
        self.screen.start()
        self.cam.start()
        log.info("[perception] 上课感知启动（共享模式，不独占设备）")

    def _on_end(self, lesson=None, **_):
        self.active = False
        self.mic.stop()
        self.screen.stop()
        self.cam.stop()
        log.info("[perception] 感知停止")


manager = PerceptionManager()
