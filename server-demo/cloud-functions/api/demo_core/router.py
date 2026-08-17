"""框架无关的 API 层：接收拆解好的请求，返回 (status, payload)。

不依赖 http.server，也不依赖任何 Web 框架，所以同一份代码跑在两个地方：
  - 本地：dev_server.py（开发时用）
  - 线上：cloud-functions/api/[[default]].py（生产姿势）

端点刻意和 SDK 方法一一对应，让浏览器 Network 面板里看到的调用顺序就是
SDK 的调用顺序。特别是**不把四步合并成一个接口** —— 合并之后前端只剩一个
进度条，最该讲的东西全被藏起来了。

HTTP 响应的 data 用 camelCase，与 Node 版完全一致，前端因此可以在两个仓库
之间逐字节复用。时间线里的 SDK 入参/返回值则保留 Python 原样的 snake_case。
"""

from __future__ import annotations

from typing import Any, Mapping

from .client import DEMO_PREFIX, MissingTokenError, create_client, resolve_region
from .errors import http_status_for, serialize_error
from .scenarios import SCENARIOS
from .trace import Trace

RUNTIME_LABEL = "python"


class RouteNotFoundError(Exception):
    pass


class BadRequestError(Exception):
    pass


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word.capitalize() for word in rest)


def camelize(value: Any) -> Any:
    """把 SDK 返回的 snake_case dict 转成 HTTP 层的 camelCase。

    这一层转换是 Python 侧独有的：SDK 公开字段是 snake_case，而 JSON API 和
    共享前端约定用 camelCase。转换点收在这里，不散落到各处。
    """
    if isinstance(value, dict):
        return {_camel(str(key)): camelize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [camelize(item) for item in value]
    return value


def dispatch(
    method: str,
    segments: list[str],
    query: Mapping[str, str],
    body: Mapping[str, Any] | None,
    env: Mapping[str, str | None],
) -> tuple[int, dict[str, Any]]:
    trace = Trace()
    region_configured = bool(resolve_region(env))
    try:
        data = _route(method.upper(), segments, query, body, env, trace)
        trace.observe_region(region_configured)
        return 200, {"ok": True, "data": data, "trace": trace.items}
    except BaseException as error:  # noqa: BLE001 - 统一翻译成 HTTP 响应
        # trace 照样返回：失败时的调用记录比成功时更有价值。
        trace.observe_region(region_configured)
        return _status_for(error), {
            "ok": False,
            "error": serialize_error(error),
            "trace": trace.items,
        }


def _status_for(error: BaseException) -> int:
    if isinstance(error, MissingTokenError):
        return 503
    if isinstance(error, RouteNotFoundError):
        return 404
    if isinstance(error, BadRequestError):
        return 400
    return http_status_for(error)


def _route(
    method: str,
    segments: list[str],
    query: Mapping[str, str],
    body: Mapping[str, Any] | None,
    env: Mapping[str, str | None],
    trace: Trace,
) -> Any:
    if not segments or segments[0] != "api":
        raise RouteNotFoundError(f"没有这个端点：{method} /{'/'.join(segments)}")

    resource = segments[1] if len(segments) > 1 else ""
    first = segments[2] if len(segments) > 2 else ""
    second = segments[3] if len(segments) > 3 else ""

    if resource == "config" and method == "GET":
        return {
            "runtime": RUNTIME_LABEL,
            "hasToken": bool(env.get("MAKERS_API_TOKEN")),
            "region": resolve_region(env),
        }

    if resource == "projects":
        if not first and method == "GET":
            return _list_projects(env, trace)
        if not first and method == "POST":
            return _create_project(_require_body(body), env, trace)
        if first and method == "GET":
            return _get_project(first, env, trace)
        if first and method == "DELETE":
            return _delete_project(first, env, trace)

    if resource == "deployments":
        if not first and method == "POST":
            return _deploy(_require_body(body), env, trace)
        if first and not second and method == "GET":
            return _get_deployment(_require_query(query, "projectId"), first, env, trace)
        if first and second == "log" and method == "GET":
            return _get_log(_require_query(query, "projectId"), first, env, trace)

    if resource == "scenarios" and first and method == "POST":
        return _run_scenario(first, body or {}, env, trace)

    raise RouteNotFoundError(f"没有这个端点：{method} /{'/'.join(segments)}")


def _require_body(body: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if body is None:
        raise BadRequestError("请求体必须是 JSON 对象")
    return body


def _require_query(query: Mapping[str, str], key: str) -> str:
    value = query.get(key)
    if not value:
        raise BadRequestError(f"缺少查询参数 {key}")
    return value


def _require_string(source: Mapping[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise BadRequestError(f"缺少字段 {key}")
    return value


# ── Projects ──────────────────────────────────────────────────────


def _create_project(body: Mapping[str, Any], env: Mapping[str, str | None], trace: Trace) -> Any:
    name = _require_string(body, "name")
    client = create_client(env, trace)
    created = trace.record(
        "client.projects.create",
        {"name": name},
        lambda: client.projects.create(name=name),
    )
    trace.note("create 只返回 project_id。名称、状态、域名都要再调 projects.get 才拿得到。")
    return camelize(created)


def _list_projects(env: Mapping[str, str | None], trace: Trace) -> Any:
    client = create_client(env, trace)
    # 只翻第一页。演示项目不会多，真实场景请用 list_all() 自动翻页。
    page = trace.record(
        "client.projects.list",
        {"page_size": 100},
        lambda: client.projects.list(page_size=100),
    )
    items = [
        {
            "projectId": item.get("project_id"),
            "name": item.get("name"),
            "createdOn": item.get("created_on"),
            "presetDomain": item.get("preset_domain"),
        }
        for item in page.get("items", [])
        if str(item.get("name", "")).startswith(DEMO_PREFIX)
    ]
    return {"items": items}


def _get_project(project_id: str, env: Mapping[str, str | None], trace: Trace) -> Any:
    client = create_client(env, trace)
    project = trace.record(
        "client.projects.get",
        {"project_id": project_id},
        lambda: client.projects.get(project_id=project_id),
    )
    trace.note(
        "preset_domain 在项目上。Production 的正式地址不在部署结果里 —— "
        "这是 SDK 最反直觉的一点，也是为什么部署完还要多查一次。"
    )
    return {"project": camelize(project)}


def _delete_project(project_id: str, env: Mapping[str, str | None], trace: Trace) -> Any:
    client = create_client(env, trace)
    trace.record(
        "client.projects.delete",
        {"project_id": project_id},
        lambda: client.projects.delete(project_id=project_id),
    )
    return {}


# ── Deployments ───────────────────────────────────────────────────


def _deploy(body: Mapping[str, Any], env: Mapping[str, str | None], trace: Trace) -> Any:
    project_id = _require_string(body, "projectId")
    html = _require_string(body, "html")
    target = "Preview" if body.get("env") == "Preview" else "Production"
    client = create_client(env, trace)

    deployment = trace.record(
        "client.deployments.deploy",
        {
            "project_id": project_id,
            "artifact": {"files": {"index.html": f"<{len(html)} 字节>"}},
            "env": target,
            "wait": False,
        },
        lambda: client.deployments.deploy(
            project_id=project_id,
            # 内联文件由 SDK 打成 Zip，服务端不需要有任何构建产物落盘。
            artifact={"files": {"index.html": html}},
            env=target,
            # 关键：Serverless 里绝不能用 wait=True。函数有执行时长上限，
            # 而 wait 默认等 900 秒，必然超时。立刻返回 deployment_id，
            # 让前端轮询 GET /api/deployments/:id。
            wait=False,
        ),
    )
    trace.note(
        "wait=False 时只返回 deployment_id / project_id / env 三个字段。"
        "没有状态，也没有地址。接下来的轮询由前端驱动。"
    )
    return camelize(deployment)


def _get_deployment(
    project_id: str, deployment_id: str, env: Mapping[str, str | None], trace: Trace
) -> Any:
    client = create_client(env, trace)
    deployment = trace.record(
        "client.deployments.get",
        {"project_id": project_id, "deployment_id": deployment_id},
        lambda: client.deployments.get(project_id=project_id, deployment_id=deployment_id),
    )
    return {"status": deployment.get("status"), "deployment": camelize(deployment)}


def _get_log(
    project_id: str, deployment_id: str, env: Mapping[str, str | None], trace: Trace
) -> Any:
    client = create_client(env, trace)
    log = trace.record(
        "client.deployments.get_log",
        {"project_id": project_id, "deployment_id": deployment_id},
        lambda: client.deployments.get_log(project_id=project_id, deployment_id=deployment_id),
    )
    return camelize(log)


# ── 场景 ──────────────────────────────────────────────────────────


def _run_scenario(
    name: str, body: Mapping[str, Any], env: Mapping[str, str | None], trace: Trace
) -> Any:
    scenario = SCENARIOS.get(name)
    if scenario is None:
        raise BadRequestError(f"未知场景：{name}")

    import time

    payload = {
        "name": body.get("name") or f"{DEMO_PREFIX}{int(time.time() * 1000)}",
        "html": body.get("html") or "<h1>hello</h1>",
    }
    scenario(payload, env, trace)
    # 场景的意义就是抛异常。走到这里说明后端行为变了，值得当成失败暴露出来。
    raise RuntimeError("场景执行完毕却没有抛出预期的异常，后端行为可能已变化。")
