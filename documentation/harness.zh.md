# Spectra Harness

Spectra Harness 把 Python、命令行和 MCP 的任务注册、输入检查、模型调用及运行记录统一起来。可替换的谱型插件参考 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的组织方式。

| 插件 | 直接调用 |
| --- | --- |
| NMR Spectra Harness | H/C 正向预测、峰指认、谱到结构检索、已知分子式条件下的生成 |
| MS Spectra Harness | 明确采集条件的 GLACIER、ICEBERG 预测 |
| Vibrational Spectra Harness | Gap 预测，以及 Vib2Mol 检索、生成、候选重排 |

完整任务目录还包含基准和算法适配器。`catalog()` 列出直接 Harness 能力，其他入口见[任务页](tasks/index.md)。

## Python 调用

```python
from openmolspec.harness import SpectraHarness

harness = SpectraHarness()
print(harness.catalog())
inputs = {'smiles': 'CCO'}
settings = {'root': '/path/to/models', 'python': '/path/to/nmr-env/bin/python'}
print(harness.validate('nmr.forward.13C', inputs, settings))
report = harness.run('nmr.forward.13C', inputs, settings, repeats=2)
print(report['completed'], report['repeat_predictions_equal'])
prediction = report['result']
```

每次调用保存耗时、成功／失败和响应／预测哈希。完整响应可能包含变化的临时文件溯源信息，因此另行报告预测一致性。准确率需要参考标签与相应评测协议。

## 命令行

请求 JSON 包含 `task`、`inputs`、`model_config` 和可选 `repeats`：

```bash
python -m openmolspec.harness catalog
python -m openmolspec.harness validate --request request.json
python -m openmolspec.harness run --request request.json --output new-result.json
```

## MCP 接入

安装可选 `mcp` 依赖，在客户端中配置本地环境的 Python：

```json
{
  "mcpServers": {
    "openmolspec": {
      "command": "/path/to/environment/bin/python",
      "args": ["-m", "openmolspec.mcp"]
    }
  }
}
```

服务使用 stdio，提供 `spectra_tasks`、`spectra_datasets`、`spectra_validate`、`spectra_predict`。MCP 用 `model_settings` 传入模型与运行环境配置。输入不满足条件时，检查入口返回原因，随后才启动模型。后端环境需要具备相应依赖和权重。

仓库提供 [Spectra Harness skill](https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/skills/spectra-harness)。训练通过显式 SDK 计划执行，接收独立 train/val 并创建新的输出目录，详见[模型与训练](model-audit.md)。

## 实际执行记录

[Repeated NMR/MS/vibrational calls](assets/reports/spectra_harness_stability_20261117.json) · [MCP protocol](assets/reports/spectra_mcp_protocol_20261117.json) · [MCP real NMR inference](assets/reports/spectra_mcp_real_call_20261117.json)
