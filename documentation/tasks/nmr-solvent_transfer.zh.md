# H/C 跨溶剂位移 · 参考检索基线

用跨溶剂实验参考估计目标位移；当前提供无训练的参考检索基线。

## 模型与协议

从 NMRShiftDB 审核通过的 H/C 一维数据中排除计算记录、混合/未知溶剂及重复测量冲突，按同一数据库原子配对。先按 Morgan 相似度选其他分子，再选最接近的源位移，加入该参考原子的实测溶剂差。排除查询分子及相同连接关系的所有立体异构体，不拟合参数。

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

已跑 32 个不同分子、296 个原子位移对；按 H/C 分别报告 MAE，并与源位移不变的基线比较。输出参考分子、原子/谱图 ID 和相似度。

适配器：`nmr_solvent_reference`。数据域：`experimental`。指标字段：`mae_ppm`、`unchanged_shift_mae_ppm`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.solvent_transfer --limit 8 --output results/nmr-solvent_transfer.json
```

## 解释与限制

这不是神经网络溶剂模型，对两种核尚无稳定收益。参考库较小，温度、浓度及位移参考尚未统一核验；专用神经网络权重仍待取得。

## 已记录结果

```json
[
  {
    "task": "nmr.solvent_transfer",
    "status": "passed",
    "metrics": {
      "13C": {
        "atoms": 140,
        "molecules": 13,
        "mae_ppm": 1.0942857142857159,
        "unchanged_shift_mae_ppm": 1.1637142857142861,
        "rmse_ppm": 1.9093510490665238
      },
      "1H": {
        "atoms": 156,
        "molecules": 19,
        "mae_ppm": 0.13762820512820512,
        "unchanged_shift_mae_ppm": 0.13538461538461527,
        "rmse_ppm": 0.3761793421174233
      }
    },
    "counts": {
      "distinct_molecules": 32,
      "paired_atoms": 296,
      "skipped_pairs": 3
    },
    "seed": 42,
    "model_kind": "retrieval_baseline_not_neural_model",
    "purpose": "leave_one_connectivity_out_reference_baseline",
    "limitations": [
      "Existing neural solvent model is not installed; this is a reference-retrieval baseline.",
      "No parameter fitting or test-label calibration. Query connectivity and stereoisomers excluded.",
      "Temperature, concentration and original experimental referencing are not independently harmonized.",
      "Low-similarity references can be inaccurate; a successful run does not establish useful accuracy."
    ],
    "source_file": "solvent_transfer_reference32_20261116.json",
    "sample_limit": 32
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-solvent_transfer.ipynb)

## 来源

[原始实现与发布](https://nmrshiftdb.nmr.uni-koeln.de/)
