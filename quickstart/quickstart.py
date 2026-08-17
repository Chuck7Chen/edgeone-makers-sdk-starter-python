"""EdgeOne Makers SDK 快速开始。

建项目 → 部署 → 等待完成 → 打印访问地址，全程不需要本地有任何构建产物。
运行方式见仓库根目录的 README。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from makers_sdk import Client, DeploymentTimeoutError, MakersError

PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>Hello EdgeOne</title>
  </head>
  <body>
    <h1>Hello EdgeOne Makers</h1>
    <p>这个页面由 SDK 的 quickstart 部署。</p>
  </body>
</html>
"""


def load_env_file() -> None:
    """把仓库根目录的 .env 读进环境变量。

    只是 Starter 的便利函数，与 SDK 行为无关；生产环境请用平台自己的
    环境变量注入机制。
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    load_env_file()

    token = os.environ.get("MAKERS_API_TOKEN")
    if not token:
        print(
            "缺少 MAKERS_API_TOKEN。先把 .env.example 复制为 .env 并填入 token。",
            file=sys.stderr,
        )
        return 1

    # region 留空时 SDK 会自动探测（先试 china 再试 global），每个 Client 实例
    # 探测一次。生产环境建议显式指定，省掉这次探测请求。
    configured_region = os.environ.get("MAKERS_REGION")
    region = configured_region if configured_region in ("china", "global") else None

    client = Client(
        token=token,
        # 当前合同只覆盖 cli；其他取值尚未确认，不应依赖。
        source="cli",
        region=region,
    )

    # 项目名在同一账号下唯一，带上时间戳，否则第二次运行会直接撞名称冲突。
    project_name = f"hello-{int(time.time() * 1000)}"

    try:
        print(f"[1/3] 创建项目 {project_name}")
        # create 只返回 project_id，名称、状态、域名等字段要用 projects.get 另外查。
        created = client.projects.create(name=project_name)
        project_id = created["project_id"]
        print(f"      project_id = {project_id}")

        print("[2/3] 打包上传并部署")
        deployment = client.deployments.deploy(
            project_id=project_id,
            # 内联文件由 SDK 打成 Zip，所以本地不需要有 dist 目录。
            # 换成 {"directory": "./dist"} 就是部署真实构建产物。
            artifact={"files": {"index.html": PAGE_HTML}},
            # wait=True 会轮询到终态。不传则立即返回，此时只有 deployment_id、
            # project_id 和 env 三个字段，没有状态也没有地址。
            wait=True,
            status_change=lambda event: print(
                f"      {event.get('previous_status') or '(首次查询)'}"
                f" -> {event['deployment'].get('status')}"
            ),
        )

        # wait 只在「等不下去」时抛异常。部署自身失败是正常返回的，要自己判断状态。
        if deployment.get("status") != "Success":
            log = client.deployments.get_log(
                project_id=project_id,
                deployment_id=deployment["deployment_id"],
            )
            print(
                f"\n部署结束但未成功（{deployment.get('status')}）。"
                f"构建日志：{log['log_url']}",
                file=sys.stderr,
            )
            return 1

        print("[3/3] 读取访问地址")
        # 关键点：Production 的正式域名不在部署结果里，而挂在项目上。
        # 部署结果的 preview_url 只对 Preview 部署有值。
        project = client.projects.get(project_id=project_id)
        preset_domain = project.get("preset_domain")
        if preset_domain:
            print(f"\n完成 → https://{preset_domain}")
        else:
            print("\n部署成功，但项目尚未分配默认域名，稍后再查一次 projects.get 即可。")
        return 0

    except DeploymentTimeoutError:
        # 等待超时不会取消线上部署，它还在继续跑。
        print("等待超时。部署仍在进行，可用 deployments.get 继续查状态。", file=sys.stderr)
        return 1
    except MakersError as error:
        print(f"SDK 报错（{type(error).__name__}）：{error}", file=sys.stderr)
        # 网络层失败时这三个字段都是 None，只在后端真的回了东西时才打印。
        details = {
            "code": error.code,
            "request_id": error.request_id,
            "http_status": error.http_status,
        }
        shown = [f"{key}={value}" for key, value in details.items() if value is not None]
        if shown:
            print(" ".join(shown), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
