# 峰 → 原子指认

给定结构，将谱峰指认到对应原子；需保留原子编号及对称等价关系。

## 模型与协议

候选方案是已有 NMRNet 逐原子位移加匹配，或 TransPeakNet 发布的 H/C HSQC 权重及匹配代码。

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

需用核实过的实验指认参考计算准确率。仅有未指认峰列表，不能得出原子指认准确率。

适配器：`unavailable`。数据域：`experimental`。指标字段：`assignment_accuracy`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.assignment --limit 8 --output results/nmr-assignment.json
```

## 解释与限制

模型方向已找到，兼容权重和原子参考尚未验证接入；不宣称已完成六核指认。

## 已记录结果

```json
[
  {
    "status": "not_evaluated",
    "reason": "候选为已有逐原子 NMRNet 加匹配，或 TransPeakNet H/C HSQC；需核验原子编号、等价位点和实验指认参考。"
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-assignment.ipynb)

## 来源

[原始实现与发布](https://github.com/siriusxiao62/2dNMR)
