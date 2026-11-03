# Web 服务部署

## 原生开发环境

先准备一个全新的 PostgreSQL 数据库，再按 [README](../README.md) 安装并启动。
`./start.sh` 从 `.env` 读取 `OPENMOLSPEC_DATABASE_URL`，启动三个独立进程。
在原生模式下，API 与化学服务始终绑定回环地址，前端发布同源 `/api/*`。
启动器等待各服务健康。原始上传和日志位于 `.openmolspec/`。

`OPENMOLSPEC_ENV` 可取 `development`、`test` 或 `production`。独立运行和
Compose 和 `./start.sh --production` 默认使用 `production`，原生开发启动器默认使用 `development`。
`OPENMOLSPEC_MOCK_SSO=1` 只允许开发和隔离测试。真实公司 SSO 需要另行接入，
入口可使用 `Accounts.login_verified_identity()` 接收身份提供方已验证的主体。

## 独立服务

为两个 Python 进程配置同一 `OPENMOLSPEC_DATABASE_URL` 和随机
`OPENMOLSPEC_INTERNAL_KEY`。可用 `openssl rand -hex 32` 生成共享密钥。
按顺序在两个终端启动。应用服务使用 `requirements-services.txt`、`services/api/`
和 `services/credits.py`。化学服务另外需要科学依赖和模型资产。

```bash
.venv/bin/python -m uvicorn services.chemistry.app:app --host 127.0.0.1 --port 8001 --env-file .env
.venv/bin/python -m uvicorn services.api.app:app --host 127.0.0.1 --port 8000 --env-file .env
```

前端设置 `OPENMOLSPEC_API_URL` 指向应用服务，应用设置
`OPENMOLSPEC_CHEMISTRY_URL` 指向化学服务。原生默认分别是
`http://127.0.0.1:8000` 和 `http://127.0.0.1:8001`。
`OPENMOLSPEC_MCP_LOCAL_URL` 与 `OPENMOLSPEC_MCP_CLOUD_URL` 决定指南展示的地址。
网关路径是 `/api/mcp`。部署到独立域名时，通过 `OPENMOLSPEC_ALLOWED_ORIGINS`
提供额外允许的网页来源。私有化学服务需要额外 Host 时使用
`OPENMOLSPEC_MCP_ALLOWED_HOSTS`。公网账号会话使用 HTTPS。

## Docker Compose

按 `.env.example` 设置数据库密码、`OPENMOLSPEC_COMPOSE_DATABASE_URL` 和内部密钥。
在本地测试模拟账号时显式设置 `OPENMOLSPEC_ENV=development` 和
`OPENMOLSPEC_MOCK_SSO=1`。

```bash
docker compose up --build
docker compose ps
```

Compose 等待 PostgreSQL 健康后启动后端。只有 Web 端口发布到主机回环地址。
PostgreSQL 使用 `postgres-data` 持久卷，原始附件保存到 API 的 `.openmolspec` 挂载。
模型资产以只读方式挂载，化学容器默认 CPU。

## 状态与恢复

两个服务在同一数据库使用各自的版本化 schema。应用服务拥有账户、会话、消息、
Agent run、SSE、附件引用和额度账本。化学服务拥有分子、谱图、计算快照和任务。
任务与对应额度预留或结算在同一 PostgreSQL 事务中提交。重启时保留排队任务和预留。
已开始计算的任务计费，执行前中断的任务释放预留。原有 SQLite 文件保留原样。

API 与化学服务各运行一个 Uvicorn worker。数据库持久化和恢复仍由单进程调度器驱动。
