# 结构 → 11B 峰列表

用已训练的液相 All-nucleus NMRNet 对 11B 验证数据做冻结推理。

## 模型与协议

B、Si 各完成 32 个不同分子，复用保存的 scaler，检查完整加载全部权重，并通过样本 ID 核对原子标签。证据为 results/bsi_frozen_diagnostic_20261116.json；复现脚本为 scripts/run_frozen_bsi_diagnostic.py。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "smiles": "CCO",
  "formula": "C2H6O",
  "h_nmr": [
    {
      "type": "1H NMR",
      "chemical_shift": "1.20 (t, 3H), 3.65 (q, 2H)"
    }
  ],
  "c_nmr": [
    {
      "type": "13C NMR",
      "chemical_shift": "18.2, 58.3"
    }
  ],
  "modality_mask": [
    1,
    1
  ]
}
```

## 输出与指标

报告逐原子 MAE/RMSE，单位 ppm；这是诊断值，不是峰匹配分数或已验证的独立测试成绩。

适配器：`unavailable`。数据域：`experimental`。指标字段：`matched_peak_mae_ppm`、`matched_peak_rmse_ppm`、`peak_count_mae`、`matched_fraction`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.11B --limit 8 --output results/nmr-forward-11B.json
```

上方正式接口会跳过未验证评分。复现 B/Si 冻结诊断时，使用全新的输出目录：

```bash
python scripts/run_frozen_bsi_diagnostic.py --models-root /path/to/models --output /path/to/new-bsi-run --limit 32
```

## 解释与限制

各核训练覆盖、训练重叠及实验原子指认来源尚未核实，且该模型不输入溶剂。正式评分仍停用；继续核查 NMRNet++ 的 B/Si 专用权重，不拟合任何校正。

## 已记录结果

```json
[
  {
    "task": "nmr.forward.11B",
    "status": "diagnostic_only",
    "model": "NMRNet liquid All-nucleus fold 0",
    "metrics": {
      "mae_ppm": 8.684532299637794,
      "rmse_ppm": 12.436461034675611
    },
    "molecules": 32,
    "atoms": 32,
    "primary_score_eligible": false,
    "limitations": [
      "Nucleus-specific training coverage is unverified.",
      "Training overlap with evaluation records is unaudited.",
      "This model does not condition on solvent.",
      "Atom labels originate from the local prepared pool; experimental assignment provenance is unverified."
    ],
    "label_alignment_verified": true,
    "source_file": "bsi_frozen_diagnostic_20261116.json",
    "sample_limit": 32
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-forward-11B.ipynb)

## 来源

[原始实现与发布](https://github.com/Colin-Jay/NMRNet)
