# -*- coding: utf-8 -*-
"""产出引擎：下课按课型路由生成 md 文档（老师/学生总结、导学案、思维导图、变式练习、分贝报告）。

路由（用户需求定稿）：
  - 新授课：老师总结 + 学生总结 + 导学案 + 思维导图
  - 讲评课：老师总结 + 学生总结 + 变式练习（不生成思维导图）
  - 考试/自习：仅老师总结（分贝折线 + 平均分贝）
  - 电影/无学习内容/电脑多数时间未开机：不产出任何文件（监控录像除外）
"""
import logging
import re
import threading
import time
from pathlib import Path
from datetime import datetime

from core.config import config, ROOT
from core.events import bus
from core.engines.skills import skill_registry

log = logging.getLogger("summarizer")

NO_OUTPUT_KEYWORDS = ("电影", "观影", "视频", "无内容", "自习讨论")


def _safe(name: str) -> str:
    """文件名消毒：中文保留、非法字符替换（v1 中文路径 bug 教训）。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", str(name)).strip()
    return name[:40] or "未命名"


def _ollama_generate(prompt: str, model: str | None = None, images: list | None = None):
    """调用 Ollama /api/generate（超时 180s）。"""
    import urllib.request
    import json as _json
    base = config.get("ollama.base_url") or "http://127.0.0.1:11434"
    body = {"model": model or config.get("ollama.model") or "qwen2.5:7b",
            "prompt": prompt, "stream": False}
    if images:
        body["images"] = images
    req = urllib.request.Request(
        f"{base}/api/generate", data=_json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = _json.loads(resp.read().decode("utf-8"))
    return data.get("response", "")


def _write_md(rel_dir: str, filename: str, content: str) -> Path:
    out = ROOT / rel_dir
    out.mkdir(parents=True, exist_ok=True)
    target = out / filename
    target.write_text(content, encoding="utf-8")
    return target


def _summary_context(lesson) -> str:
    """汇总本节感知上下文：课程信息 + 分贝序列 + 屏幕/摄像头统计。"""
    from core.engines.perception import manager
    lines = [
        f"课程：{lesson.name}（{lesson.subject} / {lesson.lesson_type}）",
        f"时长：{int((lesson.end_time - lesson.start_time) // 60)} 分钟",
    ]
    db_series = manager.mic.minute_series() if manager.mic else []
    if db_series:
        lines.append("每分钟平均分贝：" + ", ".join(f"{d:.1f}" for d in db_series))
    if manager.screen:
        lines.append(f"屏幕活跃度：{manager.screen.active_ratio:.2f}")
    if manager.cam:
        lines.append(f"摄像头就座基线：{manager.cam.baseline} 人")
    return "\n".join(lines)


def _generate(lesson, system_prompt: str, task: str, images=None) -> str:
    ctx = _summary_context(lesson)
    skill_docs = "\n\n".join(
        f"### {s.name}\n{s.body}" for s in skill_registry.list_skills())
    prompt = (
        f"{system_prompt}\n\n——内置技能——\n{skill_docs}\n\n——课堂感知数据——\n{ctx}\n\n——任务——\n{task}"
    )
    return _ollama_generate(prompt, images=images)


class SummarizerEngine:
    def __init__(self):
        bus.subscribe("lesson.ended", self._on_ended)

    def _on_ended(self, lesson=None, **_):
        threading.Thread(target=self._produce, args=(lesson,), daemon=True).start()

    def _produce(self, lesson):
        try:
            name = lesson.name or "未命名课程"
            if any(k in name for k in NO_OUTPUT_KEYWORDS):
                log.info("[summarizer] 无学习内容课程，跳过产出（监控继续）")
                bus.publish("lesson.done")
                return
            from core.engines.perception import manager
            # 电脑多数时间未开机：屏幕活跃度极低时跳过
            if manager.screen and manager.screen.active_ratio < 0.02:
                log.info("[summarizer] 屏幕几乎无活跃，视为电脑未开机，跳过产出")
                bus.publish("lesson.done")
                return

            date = datetime.now().strftime("%Y-%m-%d")
            subject = _safe(lesson.subject or "未分类")
            course = _safe(name)
            ltype = lesson.lesson_type or "新授课"
            out_base = Path(config.get("output.dir") or "data/summaries") / date / subject

            if ltype in ("考试", "自习"):
                self._exam_report(lesson, out_base, course)
            elif ltype == "讲评课":
                self._review_lesson(lesson, out_base, course)
            else:
                self._normal_lesson(lesson, out_base, course)
        except Exception as exc:  # noqa: BLE001
            log.exception("总结生成失败: %s", exc)
        finally:
            bus.publish("lesson.done")

    def _normal_lesson(self, lesson, out_base: Path, course: str):
        """新授课：老师总结 + 学生总结 + 导学案 + 思维导图。"""
        teacher = _generate(
            lesson,
            "你是资深教研员。请客观评估本节课堂质量，指出哪部分值得细讲、哪部分可讲短，并给出防拖堂建议。",
            "生成老师的课堂总结（Markdown）：## 课堂质量 / ## 建议细讲 / ## 建议精简 / ## 防拖堂建议。")
        _write_md(str(out_base), f"{course}_老师课堂总结.md", f"# {lesson.name} · 老师课堂总结\n\n{teacher}")

        student = _generate(
            lesson,
            "你是优秀学生助手。用学生视角总结本节课程，突出重难点。",
            "生成学生课堂总结（Markdown）：## 本节总结 / ## 重难点 / ## 易错点 / ## 复习建议。")
        _write_md(str(out_base), f"{course}_学生总结.md", f"# {lesson.name} · 学生总结\n\n{student}")

        guide = _generate(
            lesson,
            "你是教研组长。设计一份导学案帮助老师备课与授课。",
            "生成导学案（Markdown）：## 学习目标 / ## 重难点 / ## 教学流程 / ## 课堂练习 / ## 作业布置。")
        _write_md(str(out_base), f"{course}_导学案.md", f"# {lesson.name} · 导学案\n\n{guide}")

        mindmap = _generate(
            lesson,
            "你是知识图谱专家。将本节知识点整理为 Markmap 思维导图。",
            "生成思维导图（Markdown 内嵌 Markmap 格式，用 ---\nmarkmap\n 包裹，输出纯文本思维导图，不要解释）。")
        _write_md(str(out_base), f"{course}_思维导图.md", f"# {lesson.name} · 思维导图\n\n{mindmap}")

        log.info("[summarizer] 新授课产出 4 文件: %s", course)

    def _review_lesson(self, lesson, out_base: Path, course: str):
        """讲评课：老师总结 + 学生总结 + 变式练习（不生成思维导图）。"""
        teacher = _generate(
            lesson,
            "你是资深教研员。这是讲评课（评奖之前作业/试卷）。评估讲评质量，指出可细讲/可精简部分。",
            "生成老师课堂总结（Markdown）：## 课堂质量 / ## 建议细讲 / ## 建议精简 / ## 防拖堂建议。")
        _write_md(str(out_base), f"{course}_老师课堂总结.md", f"# {lesson.name} · 老师课堂总结（讲评课）\n\n{teacher}")

        student = _generate(
            lesson,
            "你是优秀学生助手。讲评课上老师评讲了作业/试卷，总结本节要点与易错点。",
            "生成学生总结（Markdown）：## 本节总结 / ## 重难点 / ## 易错点 / ## 复习建议。")
        _write_md(str(out_base), f"{course}_学生总结.md", f"# {lesson.name} · 学生总结（讲评课）\n\n{student}")

        practice = _generate(
            lesson,
            "你是命题老师。根据本节讲评的作业/试卷内容，出 5 道类似变式练习题。",
            "生成变式练习（Markdown）：## 变式练习（5 题，含答案解析）")
        _write_md(str(out_base), f"{course}_变式练习.md", f"# {lesson.name} · 变式练习（讲评课）\n\n{practice}")

        log.info("[summarizer] 讲评课产出 3 文件: %s", course)

    def _exam_report(self, lesson, out_base: Path, course: str):
        """考试/自习：仅老师总结（分贝折线 + 平均分贝）。"""
        from core.engines.perception import manager
        series = manager.mic.minute_series() if manager.mic else []
        avg = (sum(series) / len(series)) if series else None
        lines = [f"# {lesson.name} · 纪律报告（考试/自习）\n"]
        if series:
            lines.append("```chart\n{type: 'line', title: '每分钟平均分贝', data: "
                         + str(series) + "}\n```\n")
            lines.append(f"平均分贝：**{avg:.1f}** dB\n")
        else:
            lines.append("（本节课未采集到分贝数据）\n")
        lines.append("\n> 说明：考试/自习课只生成老师的纪律报告，不生成学生材料。")
        _write_md(str(out_base), f"{course}_纪律报告.md", "\n".join(lines))
        log.info("[summarizer] 考试/自习产出纪律报告: %s", course)


summarizer = SummarizerEngine()
