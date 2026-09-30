# -*- coding: utf-8 -*-
"""Skills 引擎：data/skills 目录热加载 SKILL.md 技能包。

内置两个技能（满足用户硬性要求）：
  - image-understanding：纯文本 AI 识图（调用 Ollama 视觉模型，结果转文本喂给纯文本模型）
  - markdown-writing：Markdown 编写规范（分课型输出模板）
"""
import logging
from dataclasses import dataclass
from pathlib import Path

from core.config import ROOT

log = logging.getLogger("skills")

SKILLS_DIR = ROOT / "data" / "skills"

BUILTIN_SKILLS = {
    "image-understanding": {
        "name": "image-understanding",
        "description": "纯文本 AI 识图：调用本地视觉模型（qwen2.5-vl/llava/gemma3）理解图片，输出结构化文本描述，供纯文本模型使用。",
        "body": (
            "技能：纯文本 AI 识图\n"
            "1. 收到图片时，调用 Ollama 视觉模型（config.ollama.vision_model）。\n"
            "2. 将图片 base64 传入 /api/generate 的 images 字段。\n"
            "3. 把视觉模型输出整理为结构化文本：内容描述 / OCR 文字 / 布局 / 结论。\n"
            "4. 纯文本模型基于该文本继续推理。"
        ),
    },
    "markdown-writing": {
        "name": "markdown-writing",
        "description": "Markdown 编写规范：所有课堂产出统一使用本规范的标题层级与章节模板。",
        "body": (
            "技能：Markdown 编写\n"
            "1. 一级标题放课程名；二级标题分章节（## 课堂质量 / ## 重难点 / ## 导学案 / ## 变式练习 等）。\n"
            "2. 列表用 - 或 1.；强调用 **加粗**；图表用 ```chart 或 markmap 块。\n"
            "3. 新授课：老师总结+学生总结+导学案+思维导图；讲评课：总结+变式练习；考试自习：分贝报告。"
        ),
    },
}


@dataclass
class Skill:
    name: str
    description: str
    body: str


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._load_builtin()
        self._load_external()

    def _load_builtin(self):
        for key, meta in BUILTIN_SKILLS.items():
            self._skills[key] = Skill(**meta)

    def _load_external(self):
        """热加载 data/skills/<name>/SKILL.md。"""
        if not SKILLS_DIR.exists():
            return
        for md in SKILLS_DIR.glob("*/SKILL.md"):
            try:
                text = md.read_text(encoding="utf-8")
                name = md.parent.name
                desc = ""
                body = text
                for line in text.splitlines():
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
                        body = text.replace(line + "\n", "", 1)
                        break
                self._skills[name] = Skill(name=name, description=desc, body=body)
                log.info("[skills] 加载外部技能: %s", name)
            except Exception as exc:  # noqa: BLE001
                log.warning("[skills] 技能加载失败 %s: %s", md, exc)

    def list_skills(self):
        return list(self._skills.values())

    def get(self, name: str):
        return self._skills.get(name)


skill_registry = SkillRegistry()
