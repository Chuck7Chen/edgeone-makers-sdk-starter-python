"""Client 工厂。

两个 Serverless 相关的决定写在这里：
  - 显式传 region：每次冷启动都是新实例，自动探测的缓存不跨实例共享。
    留空的话最坏每次冷启动都要多发两个探测请求。
  - 注入 logger：把 SDK 内部事件汇进时间线（见 trace.py）。
"""

from __future__ import annotations

from typing import Any, Mapping

from makers_sdk import Client

from .trace import Trace

# 演示项目统一前缀，前端的清理列表靠它筛选。
DEMO_PREFIX = "sdk-demo-"


class MissingTokenError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "后端没有读到 MAKERS_API_TOKEN。把 .env.example 复制成 .env 填入 token 后重启服务。"
        )


def resolve_region(env: Mapping[str, str | None]) -> str | None:
    region = env.get("MAKERS_REGION")
    return region if region in ("china", "global") else None


def create_client(env: Mapping[str, str | None], trace: Trace, **overrides: Any) -> Client:
    token = env.get("MAKERS_API_TOKEN")
    if not token:
        raise MissingTokenError()

    options: dict[str, Any] = {
        "token": token,
        # 目前唯一确认可用的取值。契约把其他取值标为「未确认」，不要臆造。
        "source": "cli",
        "region": resolve_region(env),
        "logger": trace.logger,
    }
    options.update(overrides)

    client = Client(**options)
    trace.client = client
    return client
