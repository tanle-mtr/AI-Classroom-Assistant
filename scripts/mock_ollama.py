# -*- coding: utf-8 -*-
"""Mock Ollama：模拟 /api/tags 与 /api/generate，便于无 Ollama 环境端到端调试。

用法：python mock_ollama.py   （监听 11434）
真实接入时删除/不启动即可。
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 11434
MODELS = ["qwen2.5:7b", "gemma3:4b"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/tags"):
            self._send({"models": [{"name": m, "model": m} for m in MODELS]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = {}
        if self.path.startswith("/api/generate"):
            model = body.get("model", "unknown")
            prompt = body.get("prompt", "")
            images = body.get("images")
            resp = (
                f"（mock 响应 · 模型 {model} · 是否带图 {'是' if images else '否'}）\n\n"
                f"## 本节内容\n这是模拟生成的课堂总结。真实部署时由 Ollama 的 {model} "
                f"根据课堂感知数据生成。\n\n"
                f"**收到提示词摘要**：{prompt[:120]}……"
            )
            self._send({"model": model, "response": resp, "done": True})
        else:
            self._send({"error": "not found"}, 404)


if __name__ == "__main__":
    print(f"Mock Ollama 监听 http://127.0.0.1:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
