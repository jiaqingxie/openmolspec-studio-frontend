# molspec

molspec 是基于 OpenMolSpec 计算能力的分子与谱学对话产品，采用 **Next.js + FastAPI + 独立化学计算服务 + MCP**。
前端以对话为入口，Agent 根据问题选择计算工具；支持 SMILES、Ketcher 分子编辑、交互式三维结构、理论谱图附件和结果展示。
原有谱学模型、RDKit 构象处理、谱图解析和理论重建逻辑继续由 Python 计算服务执行。

在输入框下方点击 **画分子**，可绘制结构或载入 SMILES，然后选择 **插入 SMILES**（保留原有问题）或
**添加为附件**。输入区和历史消息中的附件均可点击打开，分子可切换 2D/3D，谱图可缩放查看。
在附件预览中编辑会创建新分子，保留已经发送的结构与坐标。四个常用提问只填入可编辑草稿，发送后由 Agent 选择工具。
导入光谱时声明横轴格式、单位和数据来源。预览会显示原始数据、处理步骤及模型适用性。模型输入须覆盖
400–4000 cm⁻¹，单列输入须明确确认采用 1024 点模型网格。

## 本地启动

需要 PostgreSQL 和 Node.js **24.14.1 或更新版本**。安装脚本优先复用项目的 Python 3.11–3.12 虚拟环境；
没有兼容解释器时，通过 uv 创建 Python 3.12 环境。不会向系统 Python 安装项目依赖。

```bash
./setup.sh
test -f .env || cp .env.example .env
docker run --name molspec-postgres -d \
  -e POSTGRES_USER=molspec -e POSTGRES_PASSWORD=local-development-password \
  -e POSTGRES_DB=molspec -p 127.0.0.1:5432:5432 -v molspec-pgdata:/var/lib/postgresql/data postgres:17
docker exec molspec-postgres pg_isready -U molspec -d molspec
# 在 .env 设置 OPENMOLSPEC_DATABASE_URL。其他端口请同步修改 DSN。
OPENMOLSPEC_MOCK_SSO=1 ./start.sh
```

- [工作台](http://127.0.0.1:3000)
- [公开 MCP 指南](http://127.0.0.1:3000/integrations/mcp)
- 对外 MCP Streamable HTTP 使用 `http://127.0.0.1:3000/api/mcp`。用侧栏账户菜单创建 MolSpec 访问令牌。

启动器管理三个独立进程，检查占用端口、等待服务健康，并在任一进程退出时收尾。
按 Ctrl+C 或运行 `./stop.sh` 停止；只停止本启动器记录的进程。日志保存在 `.openmolspec/logs/`。
可用 `./start.sh --web-port 3001 --api-port 8100 --chemistry-port 8101` 指定端口。

生产模式先在 `web/` 运行 `npm run build`，再运行 `./start.sh --production`。

## 配置模型和科学资产

`.env` 中的配置只进入 Python 服务，浏览器只读取连接与能力状态。

| 配置 | 用途 |
| --- | --- |
| `OPENAI_BASE_URL` | OpenAI 兼容服务根地址，包含 `/v1`（若服务使用该前缀） |
| `OPENAI_API_KEY` | 服务端密钥；不要求鉴权的本地服务可以留空 |
| `OPENMOLSPEC_LLM_MODEL` | 支持 Chat Completions 流式工具调用的模型名称 |
| `OPENMOLSPEC_ROOT` | 完整 OpenMolSpec 资产目录，包含原有 `runs/`、`benchmark_data/` 和模型实现 |
| `OPENMOLSPEC_MAX_OUTPUT_TOKENS` | 单次模型请求的输出上限，默认 4096 |
| `OPENMOLSPEC_RUN_TOKEN_LIMIT` | 每次分析的累计 token 上限，默认 64000，累计值依赖供应商报告 |
| `OPENMOLSPEC_CALCULATION_WAIT_SECONDS` | 后端等待计算的时间预算，默认 1800 秒 |
| `OPENMOLSPEC_DEVICE` | `auto`、`cpu`、`cuda:0` 等；默认 CUDA 可用时选择 CUDA，否则 CPU |

分子编辑在浏览器内运行。登录后可以保存结构和谱图附件，也可以独立使用化学计算和 MCP 工具。网页 Agent 回复需要配置 LLM。
没有 checkpoint 或测试数据时，工具返回明确的能力错误，不生成占位预测或虚构 Agent 回答。

所有模型输出均属于 **OpenMolSpec 理论计算光谱域**。CPU 上的 Vib2Mol 路径可能使用
理论测试集检索基线或已验证生成缓存；直接推理、缓存和检索来源会保留在结果中。
输入格式和模型约定见 [谱学说明](docs/studio_guide.md)。

## 服务与数据边界

```text
web/                     Next.js 界面；/api 同源代理到应用 API
services/api/             会话、附件、持久化 SSE、OpenAI 兼容 Agent、MCP 客户端
services/chemistry/       独立化学服务、串行计算 Worker、持久化任务、HTTP/MCP 工具
openmolspec_ui/           复用的分子处理、解析、模型推理与理论谱重建
.openmolspec/             原始上传文件、启动器记录和日志（不入 Git）
PostgreSQL                molspec_app 与 molspec_chemistry schema
```

普通界面操作经应用 API 调用化学 HTTP 接口；自然语言任务由 Agent 经 MCP 调用同一套处理函数。
应用 API 不导入 RDKit/PyTorch，不加载科学模型。计算任务保存提交时的分子坐标和谱图快照，
后续编辑不会改变已提交的输入。

聊天请求启动独立 Agent task，并持久化消息与事件。关闭或刷新页面不会停止该 task；前端可以
用 run ID 重放 SSE。Pydantic AI 保存工具调用及返回的结构化历史。应用服务从已保存的计算等待点恢复，
模型流在重启时若无可恢复检查点则标记中断。化学服务恢复排队任务，标记重启时正在执行的计算为失败。
停止回复和取消计算是独立操作。计算排队时可取消，运行中取消请求返回 `409 job_running`。

两个服务启动时会在全新的 PostgreSQL 库里创建带版本的 schema。旧 SQLite 文件保留原样。
API 与化学 Worker 各运行一个进程。容器部署和原生配置见 [部署文档](docs/web_deployment.md)。

## 账户和免费 Credits

本地启动器默认使用开发环境。显式设置 `OPENMOLSPEC_MOCK_SSO=1` 后，侧栏提供两种固定模拟身份。
访客可以阅读指南和绘制分子，登录后可以使用聊天、上传、计算及令牌管理。真实公司 SSO 暂未接入，
生产模式在发现模拟登录配置时会拒绝启动。

每天北京时间 00:00 刷新免费额度，默认 20 Credits，可通过 `OPENMOLSPEC_FREE_CREDITS` 调整。
余额不累积。网页和外部 MCP 共用余额，每次实际开始的谱学计算消耗 1 Credit，
计入提交当天的额度。执行前取消或模型不可用会释放预留。
工具发现、分子检查、任务状态查询和网页对话的语言模型用量免费。

完整 HTTP、SSE 和 MCP 数据格式见 [接口约定](docs/api-contract.md)。

## MCP 工具

化学服务提供 `get_capabilities`、`inspect_molecule`、`predict_spectra`、
`retrieve_candidates`、`predict_gap`、`generate_candidates`、`get_calculation` 和 `inspect_spectrum`。
预测的 IR 和 Raman 会各自保存为谱图 ID，可在计算结果里加入下一轮对话。
Agent 使用保存的 molecule/spectrum/job ID；工具返回有限摘要、单位和来源，完整数组通过计算 API 获取。

可用官方 MCP Python SDK 连接真实服务：

```python
import asyncio
import os
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    headers = {"Authorization": f"Bearer {os.environ['MOLSPEC_TOKEN']}"}
    async with httpx.AsyncClient(headers=headers) as client:
        async with streamable_http_client("http://127.0.0.1:3000/api/mcp", http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print(await session.list_tools())
                print(await session.call_tool("inspect_molecule", {"smiles": "CCO"}))

asyncio.run(main())
```

## 验证

```bash
# Set this to a disposable PostgreSQL database with permission to create test databases.
export OPENMOLSPEC_TEST_DATABASE_URL='postgresql://molspec:local-development-password@127.0.0.1:5432/postgres'
.venv/bin/python -m pytest tests/services tests/test_chemistry.py tests/test_spectra.py tests/test_config.py tests/test_inference.py tests/test_theoretical.py -q
cd web
npm test
npm run typecheck
npm run build
```

服务测试包含真实 HTTP/MCP 调用、原有 RDKit 与测试 LMDB 检索、持久化/恢复、
断开 SSE 后继续执行，以及本地测试模型服务驱动的 Agent → MCP → 化学服务整链路。
真实 LLM 和完整 checkpoint 推理另需配置上述密钥和资产。配置真实供应商后，可运行以下评测，报告包含各用例结果、耗时、工具记录及供应商用量。

```bash
.venv/bin/python scripts/evaluate_agent.py --mock-identity researcher --output molspec-evaluation.json
```

账户和 PostgreSQL 的验收见 [账户验收记录](docs/account_validation.md)。已有科学资产清单见 [Agent 验收记录](docs/agent_product_validation.md)。
仓库保留的部分上游 benchmark 测试依赖未随包提供的 `benchmarks` 源码；直接运行整个旧测试目录
会遇到该模块缺失的收集错误，迁移相关测试不依赖它。

原 Streamlit 入口 `app.py` 作为旧实现参考保留，默认启动方式已经切换为新的 Web 架构。
