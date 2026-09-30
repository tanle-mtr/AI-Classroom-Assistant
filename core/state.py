# -*- coding: utf-8 -*-
"""课程状态机：由 ClassIsland 桥推送的课程事件驱动。

状态流：IDLE -> IN_LESSON（上课）-> PROCESSING（下课产出中）-> IDLE
课型路由（用户需求定稿）：
  - 新授课：老师总结 + 学生总结 + 导学案 + 思维导图
  - 讲评课：老师总结 + 学生总结 + 变式练习（不生成思维导图）
  - 考试/自习：仅老师总结（每分钟分贝折线 + 平均分贝）
  - 电影/无学习内容 / 电脑多数时间未开机：不产出任何文件（监控录像除外）
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.events import bus

log = logging.getLogger("state")

LESSON_TYPES = ("新授课", "讲评课", "考试", "自习", "其他")


class Phase(Enum):
    IDLE = "idle"
    IN_LESSON = "in_lesson"
    PROCESSING = "processing"


@dataclass
class Lesson:
    lesson_id: str = ""
    name: str = ""                 # 课程名（从 ClassIsland 读取）
    subject: str = ""              # 科目（自动推断/映射）
    lesson_type: str = "新授课"     # 新授课/讲评课/考试/自习/其他
    start_time: float = 0.0
    end_time: float = 0.0
    meta: dict = field(default_factory=dict)


class CourseState:
    def __init__(self):
        self.phase = Phase.IDLE
        self.current: Lesson | None = None
        self._today_lessons: list[Lesson] = []

    # ---- 查询 ----
    def snapshot(self) -> dict:
        now = time.time()
        lesson = None
        if self.current:
            lesson = {
                "lesson_id": self.current.lesson_id,
                "name": self.current.name,
                "subject": self.current.subject,
                "lesson_type": self.current.lesson_type,
                "started_at": datetime.fromtimestamp(self.current.start_time).strftime("%H:%M:%S"),
                "elapsed_min": round((now - self.current.start_time) / 60, 1),
            }
        return {
            "phase": self.phase.value,
            "current": lesson,
            "today_lessons": [
                {
                    "name": l.name,
                    "subject": l.subject,
                    "lesson_type": l.lesson_type,
                    "start": datetime.fromtimestamp(l.start_time).strftime("%H:%M"),
                    "end": datetime.fromtimestamp(l.end_time).strftime("%H:%M"),
                }
                for l in self._today_lessons
            ],
        }

    # ---- 事件入口（由 IPC 桥经 API 调用） ----
    def on_lesson_started(self, lesson: dict):
        now = time.time()
        item = Lesson(
            lesson_id=str(lesson.get("lesson_id") or int(now)),
            name=lesson.get("name") or lesson.get("subject") or "未命名课程",
            subject=lesson.get("subject") or "",
            lesson_type=lesson.get("lesson_type") or "新授课",
            start_time=now,
            meta=lesson.get("meta") or {},
        )
        if not item.subject:
            item.subject = self._guess_subject(item.name)
        self.current = item
        self.phase = Phase.IN_LESSON
        log.info("[state] 上课: %s (%s/%s)", item.name, item.subject, item.lesson_type)
        bus.publish("lesson.started", lesson=item)

    def on_lesson_ended(self, lesson: dict | None = None):
        if self.phase != Phase.IN_LESSON or not self.current:
            log.warning("[state] 收到下课事件但当前无进行中的课，忽略")
            return
        item = self.current
        item.end_time = time.time()
        self._today_lessons.append(item)
        self.phase = Phase.PROCESSING
        log.info("[state] 下课: %s", item.name)
        bus.publish("lesson.ended", lesson=item)
        # 产出完成后回到空闲（由产出引擎发布 lesson.done）
        bus.subscribe("lesson.done", self._on_done)

    def _on_done(self, **_):
        self.phase = Phase.IDLE
        self.current = None

    @staticmethod
    def _guess_subject(name: str) -> str:
        from core.config import config
        subs = config.get("subjects") or []
        for s in subs:
            if s and s in name:
                return s
        return name or "未分类"


state = CourseState()
