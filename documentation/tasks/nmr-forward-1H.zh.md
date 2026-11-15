# 结构 → 1H 峰列表

由分子结构预测 1H 化学位移，已有兼容权重时进行冻结推理或已有预测评分。

## 模型与协议

H/C 读取 NMRNet、NMRNet++ 的预测及对应元数据；未指认实验峰用最小绝对误差匹配，并保留峰数和覆盖率诊断。B/Si 暂无已验证的兼容权重/预测对。

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

位移和误差单位均为 ppm。按分子等权计算匹配峰 MAE/RMSE，必须同时报告匹配比例与峰数误差，因为匹配误差本身不惩罚全部缺失峰或额外峰。

适配器：`nmrnet_predictions`。数据域：`experimental`。指标字段：`matched_peak_mae_ppm`、`matched_peak_rmse_ppm`、`peak_count_mae`、`matched_fraction`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.1H --limit 8 --output results/nmr-forward-1H.json
```

## 解释与限制

峰匹配误差不是逐原子指认准确率。缺少 B/Si 兼容权重时明确跳过，不为补任务重新训练模型头。

## 已记录结果

```json
[
  {
    "task": "nmr.forward.1H",
    "dataset_name": "nmrspec_test",
    "status": "passed",
    "selection": {
      "read": 32,
      "missing_modality": 0,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "source_file": "smoke_forward_20261115_v3.json",
    "sample_limit": 32,
    "models": [
      {
        "model": "nmrnet",
        "metrics": {
          "matched_peak_mae_ppm": 0.13414263433412102,
          "matched_peak_rmse_ppm": 0.23681643380742615,
          "peak_count_mae": 10.21875,
          "matched_fraction": 0.5192430632770222,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      },
      {
        "model": "nmrnetpp",
        "metrics": {
          "matched_peak_mae_ppm": 0.07699339577171921,
          "matched_peak_rmse_ppm": 0.1638748144986357,
          "peak_count_mae": 10.21875,
          "matched_fraction": 0.5192430632770222,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      }
    ]
  },
  {
    "task": "nmr.forward.1H",
    "dataset_name": "patent_test_10k",
    "status": "passed",
    "selection": {
      "read": 32,
      "missing_modality": 0,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "source_file": "smoke_forward_20261115_v3.json",
    "sample_limit": 32,
    "models": [
      {
        "model": "nmrnet",
        "metrics": {
          "matched_peak_mae_ppm": 0.2691200683990773,
          "matched_peak_rmse_ppm": 0.5308687779393774,
          "peak_count_mae": 24.75862068965517,
          "matched_fraction": 0.2947374416128153,
          "examples": 29,
          "scored_examples": 29,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      },
      {
        "model": "nmrnetpp",
        "metrics": {
          "matched_peak_mae_ppm": 0.22784231065252586,
          "matched_peak_rmse_ppm": 0.4845488263627234,
          "peak_count_mae": 24.75862068965517,
          "matched_fraction": 0.2947374416128153,
          "examples": 29,
          "scored_examples": 29,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      }
    ]
  },
  {
    "task": "nmr.forward.1H",
    "dataset_name": "nmrexp_exp_10k",
    "status": "passed",
    "selection": {
      "read": 32,
      "missing_modality": 0,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "source_file": "smoke_forward_20261115_v3.json",
    "sample_limit": 32,
    "models": [
      {
        "model": "nmrnet",
        "metrics": {
          "matched_peak_mae_ppm": 0.04858252130873491,
          "matched_peak_rmse_ppm": 0.07973883212249766,
          "peak_count_mae": 8.09375,
          "matched_fraction": 0.5308309470320394,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      },
      {
        "model": "nmrnetpp",
        "metrics": {
          "matched_peak_mae_ppm": 0.03063703681651138,
          "matched_peak_rmse_ppm": 0.06262486667216845,
          "peak_count_mae": 8.09375,
          "matched_fraction": 0.5308309470320394,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      }
    ]
  },
  {
    "task": "nmr.forward.1H",
    "dataset_name": "nmrgym_test",
    "status": "passed",
    "selection": {
      "read": 32,
      "missing_modality": 0,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "source_file": "smoke_forward_20261115_v3.json",
    "sample_limit": 32,
    "models": [
      {
        "model": "nmrnet",
        "metrics": {
          "matched_peak_mae_ppm": 0.1968244606377943,
          "matched_peak_rmse_ppm": 0.39348758699328934,
          "peak_count_mae": 15.84375,
          "matched_fraction": 0.5291027660402658,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      },
      {
        "model": "nmrnetpp",
        "metrics": {
          "matched_peak_mae_ppm": 0.19821629074817518,
          "matched_peak_rmse_ppm": 0.40631559148803237,
          "peak_count_mae": 15.84375,
          "matched_fraction": 0.5291027660402658,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      }
    ]
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-forward-1H.ipynb)

## 来源

[原始实现与发布](https://github.com/Colin-Jay/NMRNet)
