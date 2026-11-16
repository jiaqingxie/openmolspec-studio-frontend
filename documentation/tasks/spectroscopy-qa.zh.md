# 谱学问答 / 推理

按用户要求暂不推进。

## 模型与协议

已从默认评测任务中排除，显式调用也会跳过。

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

下方已有结果仅作历史诊断归档。

适配器：`unavailable`。数据域：`experimental`。指标字段：`answer_accuracy`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks spectroscopy.qa --limit 8 --output results/spectroscopy-qa.json
```

## 解释与限制

该任务不再下载模型、运行推理或训练。

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

[原始实现与发布](https://github.com/jiaqingxie/openmolspec-studio-frontend)
