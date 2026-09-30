# -*- coding: utf-8 -*-
"""配置管理：读写项目根 config.json，提供默认值合并。"""
import json
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"
DATA_DIR = ROOT / "data"

DEFAULT_CONFIG = {
    "server": {"host": "127.0.0.1", "port": 18760},
    "ollama": {
        "base_url": "http://127.0.0.1:11434",
        "model": "",               # 文本/总结模型，启动时自动探测 ollama 已装模型
        "vision_model": "",        # 视觉模型（识图）
        "available_models": [],
    },
    "classisland": {"enabled": True, "bridge_port": 18761},
    "classinfo": {"grade": "", "region": "", "subjects": []},   # 首次打开询问
    "perception": {
        "mic_enabled": True,
        "cam_enabled": True,
        "screen_enabled": True,
        "shared_mode": True,       # 共享不独占麦克风/摄像头
        "sample_seconds": 2,       # 每次感知采样时长
    },
    "asr": {
        "enabled": False,          # 本地转写默认关（2核机器吃力）
        "model": "tiny",
    },
    "tardiness": {
        "screen_active_minutes": 2,   # 下课事件后屏幕仍活跃 N 分钟
        "require_students_seated": True,  # 摄像头见多数学生未离座
    },
    "monitoring": {
        "enabled": True,
        "retention_days": 14,
        "auto_export_on_shutdown": True,
    },
    "roster": {"file": "", "auto_detect": True},
    "remote": {
        "cloudflared": False,
        "tunnel_token": "",
        "openlist": False,
        "public_ip": "",
    },
    "output": {
        "dir": "data/summaries",
        "courseware_dir": "data/courseware",
        "monitoring_dir": "data/monitoring",
    },
    "subjects": ["语文", "数学", "英语", "物理", "化学", "生物",
                 "政治", "历史", "地理", "信息技术", "体育", "美术", "音乐"],
}


class Config:
    """线程安全的配置读写。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._data = dict(DEFAULT_CONFIG)
        self._load()

    def _load(self):
        if CONFIG_FILE.exists():
            try:
                saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self._deep_merge(self._data, saved)
            except Exception as exc:  # noqa: BLE001
                print(f"[config] 读取配置失败，使用默认值: {exc}")

    @staticmethod
    def _deep_merge(base, patch):
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                Config._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key, default=None):
        with self._lock:
            node = self._data
            for part in key.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return node

    def set(self, key, value):
        with self._lock:
            node = self._data
            parts = key.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value

    def data(self):
        with self._lock:
            return json.loads(json.dumps(self._data))

    def save(self):
        with self._lock:
            CONFIG_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8")

    def ensure_subject(self, name):
        """课件上传：按科目分类，没有的科目自动创建。"""
        name = (name or "").strip()
        if not name:
            return
        with self._lock:
            if name not in self._data.get("subjects", []):
                self._data.setdefault("subjects", []).append(name)
                self.save()


config = Config()
