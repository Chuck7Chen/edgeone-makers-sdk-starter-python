# EdgeOne Makers SDK Starter (Python)

[English](README.md) | 中文

用最少的步骤跑通 EdgeOne Makers SDK：创建项目、部署页面、拿到访问地址。示例不需要你本地有任何构建产物。

需要 TypeScript 版本请看 [edgeone-makers-sdk-starter](https://github.com/Chuck7Chen/edgeone-makers-sdk-starter)。

对应 contract 版本 `0.1.21`。

## 前置条件

- Python 3.10+
- 一个 Makers API token

## 60 秒上手

```sh
# 1. 装 SDK（只需一次）
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 2. 配置 token
cp .env.example .env
# 编辑 .env，填入 MAKERS_API_TOKEN

# 3. 跑
./.venv/bin/python quickstart/quickstart.py
```

### 预期输出

```text
[1/3] 创建项目 hello-1755144000000
      project_id = pages-xxxxxxxx
[2/3] 打包上传并部署
      (首次查询) -> Process
      Process -> Success
[3/3] 读取访问地址

完成 → https://hello-1755144000000.edgeone.app
```

打开最后那个地址就能看到部署好的页面。

## 三个容易踩的坑

这三点都和直觉相反，建议先看完再写自己的代码。

### 1. 部署成功后拿不到网址

`deployments.deploy()` 的返回值里**没有正式域名**。不等待时它只有 `deployment_id`、`project_id`、`env` 三个字段；即使 `wait=True`，也只有 Preview 部署才会有 `preview_url`。

Production 的正式地址挂在**项目**上，要再查一次：

```python
project = client.projects.get(project_id=project_id)
print(f"https://{project['preset_domain']}")
```

`preset_domain` 是可选字段，刚创建的项目可能还没分配，需要判空。

### 2. `source` 目前只能填 `cli`

`source` 是构造 Client 的必填参数，但当前合同**只覆盖 `cli`**。其他取值尚未确认，不应依赖。

### 3. Preview 部署要求项目已有 Production 部署

`deploy(env="Preview")` 会先做预检查，如果项目还没有任何 Production 部署，直接抛 `ValidationError`。新项目请先发一次 Production 部署。

## 常见错误

SDK 的所有失败都抛 `MakersError` 的子类，异常上带 `code`、`request_id`、`http_status` 三个字段便于排查。

| 异常 | 典型原因 | 怎么办 |
|------|---------|--------|
| `AuthError` | token 无效或过期 | 重新签发 token；确认没填错 region |
| `ValidationError` | 参数不合法；Preview 缺前置部署；制品路径非法 | 读 message，它会指出具体字段 |
| `ConflictError` | 项目名在同一账号下已存在 | 换个名字，或用 `projects.list(name=...)` 查已有项目 |
| `NotFoundError` | project_id / deployment_id 不存在 | 确认 ID；注意删除后不可恢复 |
| `RateLimitError` | 触发管理 API 限流 | SDK 已对查询类自动重试，写操作需自己退避后重试 |
| `UploadError` | 制品上传到 COS 失败 | 检查制品大小与网络 |
| `DeploymentTimeoutError` | 等待超时（默认 15 分钟） | **部署仍在线上继续**，用 `deployments.get` 继续查状态 |

网络层失败（DNS、连接被拒）同样抛 `MakersError`，但 `code` / `request_id` / `http_status` 全是 `None`——后端根本没应答。这三个字段只在有值时才值得打印。

## Serverless 场景注意

如果你打算在云函数里调用 SDK，有两条现在就该知道：

- **不要用 `wait=True`**。云函数有执行时长上限，而 `wait` 默认等 15 分钟。正确做法是 `deploy(wait=False)` 立刻拿到 `deployment_id`，再由前端轮询另一个查状态的函数。
- **显式传 `region`**。留空时 SDK 会自动探测（先试 china 再试 global），且缓存只在单个 Client 实例内有效。云函数每次冷启动都是新实例，等于每次都多付一次探测请求。

这两条都在 [`server-demo/`](server-demo/README.md) 里有可运行的示范。

## 调用观察台（server-demo）

带 UI 的服务端接入示例，把每次 SDK 调用的入参、返回值和耗时实时显示出来，
还能一键触发 `ConflictError` / `ValidationError` / `NotFoundError` 看真实报错。

```sh
.venv/bin/python server-demo/dev_server.py   # 打开 http://localhost:8787
```

它也可以直接部署到 EdgeOne Makers：仓库根的 `edgeone.json` 已经把静态目录指向
`server-demo/public`，`cloud-functions/` 放在仓库根是因为 EdgeOne 只扫描这一个位置。
唯一要手动做的是在控制台配置 `MAKERS_API_TOKEN`。

详见 [`server-demo/README.md`](server-demo/README.md)。

## SDK 依赖

本 Starter 直接依赖已发布的 PyPI 包 `makers-sdk`，当前版本 `0.1.0b1`，公开 import
为 `makers_sdk`，源码位于
[QT-7274/edgeone-makers-sdk-dev](https://github.com/QT-7274/edgeone-makers-sdk-dev)。

该包仍处于预发布阶段，beta 之间可能有破坏性变更，所以 `requirements.txt` 锁的是精确
版本。注意 `>=0.1.0` 这类写法匹配不到 `0.1.0b1`——PEP 440 下预发布版排在正式版之前。

## 后续内容

本仓库目前包含 L0 快速开始与 L2 服务端接入。规划中的内容：

- `recipes/` — 部署目录、部署 Zip、环境变量、分页、自己轮询、错误处理、Preview 部署
