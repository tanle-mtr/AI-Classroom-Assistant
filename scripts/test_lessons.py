# -*- coding: utf-8 -*-
"""端到端测试：模拟各课型课程事件，验证产出路由。

用法：python test_lessons.py [base_url]
"""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18760"


def post(path, payload):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def lesson(name, subject, ltype, seconds=2):
    post("/api/events/lesson", {"event": "started", "lesson": {
        "name": name, "subject": subject, "lesson_type": ltype}})
    print(f"上课: {name} ({subject}/{ltype})")
    time.sleep(seconds)
    post("/api/events/lesson", {"event": "ended"})
    print("下课")
    time.sleep(seconds * 2)   # 等待后台产出


if __name__ == "__main__":
    cases = [
        ("数学第三章 函数", "数学", "新授课"),
        ("期中试卷讲评", "数学", "讲评课"),
        ("期末模拟考试", "数学", "考试"),
        ("电影赏析课", "语文", "其他"),
    ]
    for c in cases:
        lesson(*c)
    # 列出产出
    with urllib.request.urlopen(f"{BASE}/api/summaries", timeout=10) as resp:
        files = json.loads(resp.read().decode("utf-8"))["files"]
    print("\n=== 产出文件 ===")
    for f in files:
        print(f["path"])
    print(f"\n共 {len(files)} 个文件")
