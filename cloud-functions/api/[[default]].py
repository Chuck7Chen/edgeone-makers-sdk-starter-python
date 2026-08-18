"""Adapter B：EdgeOne Cloud Functions 入口。

catch-all 路由，`/api/*` 的所有请求都落到这里，再交给共享的 dispatch。
整个适配层就下面这几十行 —— 业务逻辑一行都不在这里。

为什么是 Cloud Functions 而不是 Edge Functions：
Edge Functions 跑在 V8 边缘运行时，只有 Web API，禁止 Node 内置模块和第三方包。
Makers SDK 是 Python 包，必须要完整的 Python 运行时，也就是 Cloud Functions。

本地 dev_server.py 复用的就是下面这个 handler 类 —— Python 侧两种形态是
同一个 BaseHTTPRequestHandler 子类，连 adapter 都不用写第二份。
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 让 demo_core 无论被谁加载都能 import 到（本地直跑 / 平台构建产物）。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_core.router import dispatch  # noqa: E402


def _env() -> dict[str, str | None]:
    # token 从环境变量读，永远不下发给浏览器。
    return {
        "MAKERS_API_TOKEN": os.environ.get("MAKERS_API_TOKEN"),
        "MAKERS_REGION": os.environ.get("MAKERS_REGION"),
    }


class handler(BaseHTTPRequestHandler):
    # Cloud Functions 与本地 http.server 共用这一个类。
    # self.path 是未剥离前缀的完整路径，两种形态下行为一致。

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        segments = [part for part in parsed.path.split("/") if part]
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}

        body = None
        length = int(self.headers.get("Content-Length") or 0)
        if length > 0:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                body = None
            if not isinstance(body, dict):
                body = None

        status, payload = dispatch(method, segments, query, body, _env())
        self._send_json(status, payload)

    def _send_json(self, status: int, payload: object) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: object) -> None:
        # 默认实现往 stderr 打日志，本地开发时噪音太大。
        pass
