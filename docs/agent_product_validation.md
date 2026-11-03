# molspec Agent 验收记录

2026-11-03，本地工作区使用 Next.js 生产构建、FastAPI、独立化学服务和私有 MCP。97 项相关 Python 测试通过。此前的 32 项前端测试、TypeScript 类型检查和 Next.js 生产构建已通过。

| 项目 | 本轮证据 |
| --- | --- |
| 对话 SDK | 固定 pydantic-ai-slim 2.64.0 和 openai 3.42.1。依赖检查通过。使用 SDK 的流式输出和 DeferredToolRequests 保存计算等待点 |
| 乙醇结构检查 | Tensoris 的 deepseek-v4.1-flash-1017 经 Pydantic AI 实际调用 inspect_molecule，本地 MCP 与 RDKit 返回 C₂H₆O、46.069 g/mol。协议 fixture 另行覆盖下一轮的成对调用历史 |
| 输入与预设 | 浏览器验证四个常用提问、预测预设填草稿、无效 SMILES 报错、CCO 附件、上传元数据和能力面板 |
| 部分谱图 | 浏览器上传 800–1500 cm⁻¹ 三点测试输入，保留该范围并标记仅供预览。HTTP/MCP 测试覆盖域、单位、无效行、重复和非有限值 |
| 连续计算 | 受控预测 fixture 通过实际 HTTP/MCP 写入 IR/Raman 引用，下一轮 SDK 调用读取 IR 摘要并用相同 ID 运行既有余弦检索。缓存候选逻辑也在参考 fixture 上运行 |
| 任务生命周期 | 服务测试覆盖 SSE 断线和重放、排队计算恢复、运行中计算中断、应用恢复等待后接续 Agent、停止回复保留计算引用、HTTP/MCP 请求去重 |
| 真实供应商评测 | 13 个用例中实际执行 8 个，8 个通过自动判定。用例耗时合计 72.976 秒，供应商报告 26,863 输入 token 和 7,511 输出 token，共 16 次模型请求。5 个正向科学计算用例因资产缺失阻塞 |
| 真实供应商续问与重放 | 在同一乙醇对话中，Tensoris 复用上一轮的分子 ID 并调用 get_capabilities。客户端在首个 SSE 事件后断开，从该事件 ID 续读成功。重复提交相同 request_id 返回原 run ID，会话只增加一轮。耗时 6.045 秒，3,999 输入 token 和 521 输出 token。记录在 tensoris-followup-replay.json |

评测用例位于 [molspec.json](../tests/evals/molspec.json)。正向谱图用例复用前一用例的真实预测结果。负向用例使用明确的测试输入。报告记录执行用例的耗时、工具、用量和自动检查结果，供人工抽查回答与科学解释。

```bash
.venv/bin/python scripts/evaluate_agent.py --output molspec-evaluation.json
```

复核补充了 JSON 字符串形式工具参数的 SSE 回归测试。复用评测现在要求同一次成功计算的调用参数和返回输入引用均匹配原谱图 ID。

## 无工具 Agent 补验

按本轮验收范围，在临时数据库和空工具注册表的隔离实例中使用真实 Tensoris 模型。化学服务地址指向未使用的本地端口，验证过程不建立 MCP 会话。

- 真实流式回复在首个 SSE 事件后断开。从该事件续读收到完整答复，重复提交同一请求 ID 返回同一运行和消息。合计 1.764 秒，供应商报告 217 输入 token 和 113 输出 token。
- 重启隔离 API 后，模型从持久化历史正确回忆上一轮给出的验收代号。耗时 1.403 秒，供应商报告 235 输入 token 和 36 输出 token。
- 收到真实输出增量后停止回复，事件流返回 `run_cancelled`，会话清除活跃运行。该取消请求没有完整的供应商用量。
- 16 项非 MCP 后端回归、32 项前端测试及 TypeScript 类型检查通过。

详细证据位于 `artifacts/agent-product/tensoris-agent-only.json`。本次验收范围为纯对话与会话生命周期。科学计算的真实验收仍待下列资产。

## 外部资源

| 能力 | 当前缺口 |
| --- | --- |
| 对话 | Tensoris OpenAI 兼容接口已配置并验证。密钥保存在本地服务端环境配置中 |
| 预测 IR/Raman/NMR | Hessian Hi/Hij、偶极响应、极化率响应、H/C NMR 权重，四个张量训练目录的 `resolved_config.yaml`，上游 Equiformer Hessian/NMR 与 Hessian physics 实现及相应运行依赖 |
| 检索 | OpenMolSpec 理论测试集 LMDB。余弦基线可直接使用；直接 Vib2Mol 排序另需 retrieval checkpoint、NMR normalizer 与上游模型及 tokenizer |
| 结构推测 | 缓存路径需要理论 LMDB 和 `generation_predictions.jsonl`。直接 Vib2Mol 路径需要生成权重、NMR normalizer、适配器、评估模块、上游实现与本地 tokenizer |
| 能隙 | Vib2Conf gap checkpoint 和上游 `benchmarks/models/vib2conf/model.py` 及其运行依赖 |

当前配置根目录中的 11 项 `MANIFEST.json` 资产路径均缺失。已有资产可通过服务端 `OPENMOLSPEC_ROOT` 指向完整目录。状态面板检查资源存在性，真实模型加载和结果正确性须以运行验收为准。

本地证据保存在 `artifacts/agent-product/`。服务测试中的模型回复与预测数据均为 fixture。真实供应商的逐项结果见该目录下的 `real-model-evaluation.json`。
