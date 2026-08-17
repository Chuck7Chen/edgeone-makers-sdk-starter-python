# server-demo · 调用观察台

L2 服务端接入示例。一个带 UI 的小应用，把 SDK 的每次调用、入参、返回值和耗时
实时显示出来。

它要解决的不是「怎么部署一个页面」——`quickstart/` 四十行就够了。它要解决的是
**SDK 那些从返回值上看不出来的行为**：`create` 只给一个 ID、`deploy` 不等待时
只有三个字段、Production 的域名根本不在部署结果里。这些写在注释里容易被划过去，
做成实时滚动的调用记录就很难忽略。

## 跑起来

```sh
# 1. 装依赖（仓库根目录）
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 填 token
cp .env.example .env   # 编辑填入 MAKERS_API_TOKEN

# 3. 启动
.venv/bin/python server-demo/dev_server.py
```

打开 http://localhost:8787 。改端口用 `PORT=9000 .venv/bin/python server-demo/dev_server.py`。

## 界面里有什么

**左侧场景选择器**把 SDK 反直觉的地方做成了可点击的：

| 场景 | 演示什么 | 有副作用吗 |
|------|---------|-----------|
| 正常部署 | 建项目 → 部署 → 轮询 → 取域名，四步都看得见 | 建一个真项目 |
| 重名项目 | `ConflictError` → HTTP 409 | 建一个真项目 |
| Preview 无 Production | `ValidationError` → HTTP 400，SDK 本地预检直接拦下 | 建一个真项目 |
| 项目不存在 | `NotFoundError` → HTTP 404 | 无 |

**右侧调用时间线**是重点。每条记录可展开，显示传给 SDK 的入参和 SDK 返回的原始
结构（保留 Python 的 `snake_case`）。连续的 `deployments.get` 会折叠成一行并显示
状态迁移链。

**左下角项目清理列表**：每跑一次正常流程就在账号里建一个真项目，名字统一带
`sdk-demo-` 前缀，可以在这里直接删掉。

## 结构

```text
server-demo/
├── public/index.html                前端，无框架无构建，单文件
├── dev_server.py                    Adapter A：本地 http.server
└── cloud-functions/                 Adapter B：EdgeOne Cloud Functions 部署单元
    ├── requirements.txt
    └── api/
        ├── [[default]].py           catch-all 入口，handler 类
        └── demo_core/               框架无关的实现，两个 adapter 共用
            ├── router.py            路由与端点
            ├── client.py            Client 工厂
            ├── trace.py             调用观察层
            ├── scenarios.py         错误场景
            └── errors.py            异常 → HTTP 状态码
```

Python 侧有个便宜可占：EdgeOne Cloud Functions 的 Handler 模式用的就是标准库的
`BaseHTTPRequestHandler`，和本地 `http.server` 同一个基类。所以
`api/[[default]].py` 里那个 `handler` 类**线上线下是同一份代码**，
`dev_server.py` 直接继承它再加一个静态文件分支就完事了，不需要写第二个适配层。

`public/index.html` 与 Node starter 仓库里的那一份**逐字节相同**。同一个页面，
换个后端进程照样跑——这是「两语言 SDK 语义一致」最直接的证明。

## 端点

刻意和 SDK 方法一一对应，浏览器 Network 面板里的调用顺序就是 SDK 的调用顺序。

| 端点 | SDK 调用 |
|------|---------|
| `GET /api/config` | — |
| `POST /api/projects` | `projects.create` |
| `GET /api/projects` | `projects.list` |
| `GET /api/projects/:id` | `projects.get` |
| `DELETE /api/projects/:id` | `projects.delete` |
| `POST /api/deployments` | `deployments.deploy(wait=False)` |
| `GET /api/deployments/:id` | `deployments.get` |
| `GET /api/deployments/:id/log` | `deployments.get_log` |
| `POST /api/scenarios/:name` | 见上表 |

响应统一是 `{ ok, data | error, trace }`。**`trace` 是这个 demo 加的观察层，
不是 SDK 的一部分**，真实业务代码里直接调 SDK 方法即可。

**命名边界**：SDK 公开字段是 `snake_case`，而 HTTP API 和共享前端约定用
`camelCase`。转换收在 `router.py` 的 `camelize()` 一处，不散落到各个端点。
时间线里显示的入参/返回值是转换前的原样，所以你能同时看到两种命名。

## 三个刻意的设计决定

**不把四步合并成一个接口。** 后端完全可以用 `deploy(wait=True)` 一次搞定，
但那样前端就只剩一个转圈的进度条，最该讲的东西全被藏起来了。

**不在 Serverless 里用 `wait`。** 云函数有执行时长上限，而 `wait` 默认等 900 秒，
必然超时。正确做法是 `deploy(wait=False)` 立刻拿到 `deployment_id`，由前端
轮询另一个端点。这是把 SDK 用进 Serverless 的唯一正确方式。

**Token 只在后端。** 页面从头到尾拿不到 `MAKERS_API_TOKEN`。这也是为什么这个
demo 不能做成纯静态页——必须有个后端替浏览器持有凭证。

## 关于可观测性的边界

时间线里的 SDK 内部事件有两个来源，值得说清楚各自的边界：

**注入的 `logger`** 覆盖面比想象中窄。v0.1.0 的 SDK 只在一处调 logger（error 级，
制品上传失败）。**区域探测和重试退避不产生任何日志。**

**`client.region`** 是公开属性，能反推出自动探测的结果。时间线里那条
「region 未显式配置，SDK 自动探测到 china」就是这么来的，不是 SDK 主动上报的。

所以「为什么第一次调用特别慢」这件事，目前只能靠读 `client.region` 反推，
看不到探测过程本身。

## 部署到 Cloud Functions

`cloud-functions/` 是按 EdgeOne 的约定组织的，可以直接部署——**但要等 SDK 发布**。

平台构建时按 `cloud-functions/requirements.txt` 从 PyPI 装依赖，而 `makers-sdk`
目前还没发布。包发布后即可部署，代码不用改。本地 `dev_server.py` 不受影响，
它用的是仓库根 `.venv` 里的可编辑安装。

另外要注意 **Edge Functions 跑不了这个 SDK**。EdgeOne 有两种函数形态：

| | Edge Functions | Cloud Functions |
|---|---|---|
| 目录 | `edge-functions/` | `cloud-functions/` |
| 运行时 | V8 边缘运行时，仅 Web API，只能写 JS | 完整 Python / Node.js |
| 第三方包 | 不支持 | 支持 |

Makers SDK 是 Python 包，必须用 Cloud Functions。

部署时还需要：在 Makers 控制台配置 `MAKERS_API_TOKEN` 环境变量，并把静态资源
输出目录指向 `server-demo/public`。