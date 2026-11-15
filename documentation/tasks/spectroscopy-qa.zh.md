# 谱学问答 / 推理

分别检查无给定分子式的预测，以及基于谱图证据的问答；正式适配器仍缺已验证的兼容权重。

## 模型与协议

另设本地 MolSpect-7B 零样本探测：输入真实 H/C 谱及问题，使用权重自带聊天模板，不提供分子式或 SMILES，贪心解码最多 32 个新 token。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "question": "How many distinct 13C shifts are listed?",
  "13C_shift_ppm": [
    18.2,
    58.3
  ]
}
```

## 输出与指标

只读取已完成的诊断报告，分别报告分子式 exact accuracy 或明确列出的 13C 位移条目计数正确率。未完成运行不汇总成绩。

适配器：`unavailable`。数据域：`experimental`。指标字段：`answer_accuracy`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks spectroscopy.qa --limit 8 --output results/spectroscopy-qa.json
```

## 解释与限制

本地权重对应的发布版本、训练阶段和提示兼容性未核实；该探测不等于官方 MolSpectLLM 或 SpectraLLM32B 复现，也不会将正式任务标记为可用。全程不训练。

## 已记录结果

```json
[
  {
    "task": "spectroscopy.qa",
    "status": "diagnostic_only",
    "model": "local_MolSpect-7B",
    "scope": "explicit_zero_shot_baseline_not_the_official_SpectraLLM_32B_release",
    "metrics": {
      "accuracy": 0.0,
      "examples": 4
    },
    "decoding": {
      "do_sample": false,
      "max_new_tokens": 32,
      "seed": 42
    },
    "formula_provided_to_model": false,
    "source_file": "molspect_zeroshot_formula_qa_20261116.json",
    "sample_limit": 4
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/spectroscopy-qa.ipynb)

## 来源

[原始实现与发布](https://github.com/Eurekashen/SpecMol)
