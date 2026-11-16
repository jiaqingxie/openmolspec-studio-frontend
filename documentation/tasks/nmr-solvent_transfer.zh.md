# 跨溶剂化学位移迁移

预测同一分子从源溶剂到目标溶剂的化学位移变化。

## 模型与协议

候选为带溶剂输入的 NMRNet++、TransPeakNet；需取得对应冻结权重以及同一分子的跨溶剂配对记录。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "smiles": "CCO",
  "nucleus": "1H",
  "source_solvent": "CDCl3",
  "target_solvent": "DMSO-d6",
  "source_peaks_ppm": [
    1.2,
    3.65
  ]
}
```

## 输出与指标

按核分别报告目标位移及位移变化误差，核对原子映射、溶剂和实验条件。

适配器：`unavailable`。数据域：`experimental`。指标字段：`mae_ppm`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.solvent_transfer --limit 8 --output results/nmr-solvent_transfer.json
```

## 解释与限制

溶剂条件正向预测不自动等于经过验证的跨溶剂迁移；目前未接入，且不通过拟合测试标签做溶剂校正。

## 已记录结果

```json
[
  {
    "status": "not_evaluated",
    "reason": "候选为带溶剂条件的 NMRNet++/TransPeakNet；需取得对应权重及同一分子的跨溶剂配对记录后验证。"
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-solvent_transfer.ipynb)

## 来源

[原始实现与发布](https://github.com/siriusxiao62/2dNMR)
