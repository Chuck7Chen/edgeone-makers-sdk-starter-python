"""Adapter A：本地开发服务器。

只做两件事：把 /api/* 交给 Cloud Functions 那个 handler 类，其余路径当静态文件伺服。

Python 侧这两种形态共用同一个 BaseHTTPRequestHandler 子类 —— Cloud Functions
的 Handler 模式用的就是标准库这个基类，所以线上线下真的是同一份代码，
不需要写第二个适配层。

运行：
    .venv/bin/python server-demo/dev_server.py
"""

from __future__ import annotations

import importlib.util
import mimetypes
import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLIC_DIR = HERE / "public"
# cloud-functions/ 必须在仓库根：EdgeOne 只扫描项目根目录下的这一个位置。
FUNCTIONS_DIR = HERE.parent / "cloud-functions" / "api"
PORT = int(os.environ.get("PORT", "8787"))


def load_env_file() -> None:
    """把仓库根目录的 .env 读进环境变量。

    只是 Starter 的便利函数，与 SDK 行为无关；生产环境请用平台自己的
    环境变量注入机制（Cloud Functions 里是 Makers 环境变量）。
    """
    env_path = HERE.parent / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_api_handler() -> type:
    """加载 cloud-functions/api/[[default]].py 里的 handler 类。

    文件名带方括号是 EdgeOne 的 catch-all 路由约定，不是合法的模块名，
    所以只能按路径加载。
    """
    entry = FUNCTIONS_DIR / "[[default]].py"
    spec = importlib.util.spec_from_file_location("cloud_functions_entry", entry)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {entry}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.handler


ApiHandler = load_api_handler()


class DevHandler(ApiHandler):  # type: ignore[misc, valid-type]
    """/api/* 走继承来的 API 逻辑，其余路径伺服 public/ 下的静态文件。"""

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            super().do_GET()
        else:
            self._serve_static()

    def _serve_static(self) -> None:
        relative = "index.html" if self.path in ("", "/") else self.path.lstrip("/").split("?")[0]
        target = (PUBLIC_DIR / relative).resolve()

        # 目录穿越防护：解析后必须还在 public/ 里面。
        if not target.is_relative_to(PUBLIC_DIR.resolve()) or not target.is_file():
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type.endswith("javascript"):
            content_type += "; charset=utf-8"

        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)


def main() -> int:
    load_env_file()

    print("\n  EdgeOne Makers SDK 调用观察台\n")
    print(f"  → http://localhost:{PORT}\n")
    has_token = bool(os.environ.get("MAKERS_API_TOKEN"))
    print(f"  token   {'已配置' if has_token else '缺失（复制 .env.example 为 .env 并填入）'}")
    print(f"  region  {os.environ.get('MAKERS_REGION') or '未设置，SDK 会自动探测'}\n")

    server = ThreadingHTTPServer(("", PORT), DevHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
