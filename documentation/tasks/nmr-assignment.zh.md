# 峰 → 原子指认

需要保留原子编号的实验参考值和匹配模型。

## 模型与协议

本任务需符合输入定义的现成权重、参考数据与适配器。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "smiles": "CCO",
  "nucleus": "13C",
  "observed_peaks_ppm": [
    18.2,
    58.3
  ],
  "atom_index_basis": "RDKit molecule reconstructed from the exact input SMILES"
}
```

## 输出与指标

缺少必需条件时不产生占位分数。

适配器：`unavailable`。数据域：`experimental`。指标字段：`assignment_accuracy`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.assignment --limit 8 --output results/nmr-assignment.json
```

## 解释与限制

保持明确的待接入状态；如果必须重新训练才能完成，则按用户要求跳过。

## 已记录结果

```json
[
  {
    "status": "not_evaluated",
    "reason": "需要保留原子编号的实验参考值和匹配模型。"
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-assignment.ipynb)

## 来源

[原始实现与发布](https://github.com/jiaqingxie/openmolspec-studio-frontend)
