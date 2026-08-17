"""调用观察层：把「SDK 做了什么」变成前端能渲染的结构化事件。

三个数据来源：
  1. record()       包住每次 SDK 方法调用，拿到方法名、入参、返回值、耗时
  2. logger         注入 Client，拿到 SDK 主动上报的内部事件
  3. client.region  读公开属性，反推自动探测的结果

关于第 2 条要知道它的边界：v0.1.0 的 SDK 只在一个地方调 logger（error 级，
制品上传失败）。**区域探测和重试退避不产生任何日志**，所以「为什么第一次调用
特别慢」这件事光靠 logger 是看不出来的，只能用第 3 条从 client.region 反推。

注意：trace 是这个 demo 自己加的观察层，不是 SDK 的一部分。真实业务代码里
直接调 SDK 方法即可。

时间线里的入参/返回值刻意保留 SDK 原样的 snake_case，而 HTTP 响应的 data 用
camelCase —— 前端因此可以在两个仓库间逐字节复用，同时用户又能看到 Python 侧
真实的调用长相。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping, TypeVar

from .errors import serialize_error

T = TypeVar("T")


class _Logger:
    """SDK 的 Logger 协议：debug / info / warn / error，签名为 (message, context)。"""

    def __init__(self, trace: "Trace") -> None:
        self._trace = trace

    def debug(self, message: str, context: Mapping[str, Any] | None = None) -> None:
        self._trace.log("debug", message, context)

    def info(self, message: str, context: Mapping[str, Any] | None = None) -> None:
        self._trace.log("info", message, context)

    def warn(self, message: str, context: Mapping[str, Any] | None = None) -> None:
        self._trace.log("warn", message, context)

    def error(self, message: str, context: Mapping[str, Any] | None = None) -> None:
        self._trace.log("error", message, context)


class Trace:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        # create_client 会把创建出来的 Client 登记在这里，用于事后读 region。
        self.client: Any = None
        self.logger = _Logger(self)

    def log(self, level: str, message: str, context: Mapping[str, Any] | None = None) -> None:
        item: dict[str, Any] = {"kind": "log", "level": level, "message": message}
        if context:
            item["context"] = dict(context)
        self.items.append(item)

    def note(self, text: str) -> None:
        """给上一条调用挂一句教学注解，前端渲染成黄色批注。"""
        self.items.append({"kind": "note", "text": text})

    def record(self, method: str, request: Any, run: Callable[[], T]) -> T:
        started_at = time.monotonic()
        try:
            response = run()
        except BaseException as error:
            self.items.append(
                {
                    "kind": "call",
                    "method": method,
                    "request": request,
                    "error": serialize_error(error),
                    "durationMs": round((time.monotonic() - started_at) * 1000),
                }
            )
            raise
        self.items.append(
            {
                "kind": "call",
                "method": method,
                "request": request,
                "response": response,
                "durationMs": round((time.monotonic() - started_at) * 1000),
            }
        )
        return response

    def observe_region(self, configured: bool) -> None:
        """请求收尾时读一次 client.region。

        没显式配 region 时，SDK 会在第一次业务调用前先探测（最坏 china 失败 →
        global 成功 → 真正的请求，三个 HTTP 往返）。这个过程不打日志，只能从
        属性反推结果。Serverless 每次冷启动都是新实例，缓存不跨实例，
        所以生产环境应该显式传 region 把这一步省掉。
        """
        if configured or self.client is None:
            return
        detected = getattr(self.client, "region", None)
        if not detected:
            return
        self.log(
            "info",
            f"region 未显式配置，SDK 自动探测到 {detected}",
            {"建议": "生产环境显式传 region，省掉冷启动时的探测往返"},
        )
