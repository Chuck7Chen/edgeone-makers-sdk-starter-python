"""错误场景：把 SDK 几个反直觉的地方做成可点击的演示。

这些场景**故意**抛异常。没人会为了看一眼报错去改示例代码，所以把它们做成
按钮 —— 这是 UI 相对命令行示例最大的增量。

每个场景跑完都会抛出异常，由 router.py 统一翻译成 HTTP 状态码。
场景 id 与 Node 版 scenarios.ts 一一对应。
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .client import create_client
from .trace import Trace

Scenario = Callable[[Mapping[str, Any], Mapping[str, "str | None"], Trace], None]


def _conflict(payload: Mapping[str, Any], env: Mapping[str, str | None], trace: Trace) -> None:
    """项目名重复 → ConflictError（HTTP 409）。"""
    client = create_client(env, trace)
    name = payload["name"]

    trace.record(
        "client.projects.create",
        {"name": name},
        lambda: client.projects.create(name=name),
    )
    trace.note(
        "第一次创建成功。项目名在同一账号下唯一，这是新用户最容易踩的第一个坑："
        "quickstart 用时间戳做名字就是为了绕开它。"
    )

    trace.record(
        "client.projects.create",
        {"name": name},
        lambda: client.projects.create(name=name),
    )


def _preview_precheck(
    payload: Mapping[str, Any], env: Mapping[str, str | None], trace: Trace
) -> None:
    """新项目直接发 Preview 部署 → ValidationError（HTTP 400）。"""
    client = create_client(env, trace)
    name = payload["name"]

    created = trace.record(
        "client.projects.create",
        {"name": name},
        lambda: client.projects.create(name=name),
    )
    trace.note("这是一个全新项目，还没有任何 Production 部署。")

    project_id = created["project_id"]
    trace.record(
        "client.deployments.deploy",
        {
            "project_id": project_id,
            "artifact": {"files": {"index.html": "…"}},
            "env": "Preview",
            "wait": False,
        },
        lambda: client.deployments.deploy(
            project_id=project_id,
            artifact={"files": {"index.html": payload["html"]}},
            env="Preview",
            wait=False,
        ),
    )


def _not_found(payload: Mapping[str, Any], env: Mapping[str, str | None], trace: Trace) -> None:
    """对不存在的项目发部署 → NotFoundError（HTTP 404）。不产生任何项目。"""
    client = create_client(env, trace)
    project_id = "makers-does-not-exist-000"
    trace.note("拿一个不存在的 projectId 发部署，看 SDK 怎么把后端的错误码翻译成类型化异常。")

    trace.record(
        "client.deployments.deploy",
        {
            "project_id": project_id,
            "artifact": {"files": {"index.html": "…"}},
            "wait": False,
        },
        lambda: client.deployments.deploy(
            project_id=project_id,
            artifact={"files": {"index.html": payload["html"]}},
            wait=False,
        ),
    )


SCENARIOS: dict[str, Scenario] = {
    "conflict": _conflict,
    "preview-precheck": _preview_precheck,
    "not-found": _not_found,
}
