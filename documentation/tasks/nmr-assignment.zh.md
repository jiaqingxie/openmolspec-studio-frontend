# H/C 峰 → 原子指认

给定结构和实测 H/C 峰，预测逐原子位移并输出候选指认。

## 模型与协议

直接加载液相 NMRNet H/C fold-0 权重，固定种子生成构象；完整恢复权重，保存 RDKit AddHs(input SMILES) 的 0 起始原子编号。按拓扑对称性合并位点，再做带未匹配项的最小代价匹配。H/C 默认容差分别为 0.5/5 ppm。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "smiles": "CCO",
  "nucleus": "13C",
  "peaks_ppm": [
    18.2,
    58.3
  ],
  "tolerance_ppm": 5.0
}
```

## 输出与指标

32 个碳谱分子已完成，匹配 488 个峰；另有真实在线氢谱请求。报告覆盖率、残差、原子编号及歧义候选；缺少独立实验指认答案时 assignment_accuracy 为 null。

适配器：`nmrnet_atom_assignment`。数据域：`experimental`。指标字段：`matched_peak_fraction_macro`、`matched_residual_mae_ppm`、`assignment_accuracy`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.assignment --limit 8 --output results/nmr-assignment.json
```

## 解释与限制

匹配残差不等于指认准确率；拓扑对称不保证磁等价。模型不输入溶剂，未做构象系综平均，目前仅覆盖 H/C。

## 已记录结果

```json
[
  {
    "task": "nmr.assignment",
    "status": "passed",
    "metrics": {
      "molecules": 32,
      "matched_peaks": 488,
      "matched_peak_fraction_macro": 0.9392376720501721,
      "matched_residual_mae_ppm": 0.8991307922920895,
      "assignment_accuracy": null
    },
    "selection": {
      "read": 32,
      "missing_modality": 0,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "purpose": "real_peak_assignment_execution_not_atom_accuracy_benchmark",
    "limitations": [
      "No experimental atom assignment ground truth supplied.",
      "Symmetry is topological; conformer/solvent effects can change observed equivalence.",
      "Residual and coverage are diagnostics, not assignment accuracy.",
      "Training overlap unverified; frozen model is not solvent-conditioned."
    ],
    "source_file": "assignment_carbon32_20261116.json",
    "sample_limit": 32
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-assignment.ipynb)

## 来源

[原始实现与发布](https://github.com/Colin-Jay/NMRNet)
