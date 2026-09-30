# -*- coding: utf-8 -*-
"""轻量事件总线：模块间解耦（感知/产出/监控互不阻塞）。"""

import logging
import threading
from collections import defaultdict
from typing import Callable

log = logging.getLogger("events")


class EventBus:
    def __init__(self):
        self._lock = threading.RLock()
        self._subs: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable):
        with self._lock:
            self._subs[event].append(handler)

    def publish(self, event: str, **kwargs):
        with self._lock:
            handlers = list(self._subs.get(event, []))
        for handler in handlers:
            try:
                handler(**kwargs)
            except Exception:  # noqa: BLE001
                log.exception("[bus] handler failed for %s", event)


bus = EventBus()
