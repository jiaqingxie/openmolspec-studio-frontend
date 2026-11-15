# 结构 → 13C 峰列表

由分子结构预测 13C 化学位移，已有兼容权重时进行冻结推理或已有预测评分。

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
  --tasks nmr.forward.13C --limit 8 --output results/nmr-forward-13C.json
```

## 解释与限制

峰匹配误差不是逐原子指认准确率。缺少 B/Si 兼容权重时明确跳过，不为补任务重新训练模型头。

## 已记录结果

```json
[
  {
    "task": "nmr.forward.13C",
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
          "matched_peak_mae_ppm": 1.166839493503614,
          "matched_peak_rmse_ppm": 2.3898515362116135,
          "peak_count_mae": 2.65625,
          "matched_fraction": 0.8683153839313926,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      },
      {
        "model": "nmrnetpp",
        "metrics": {
          "matched_peak_mae_ppm": 0.8163807039222384,
          "matched_peak_rmse_ppm": 2.0137184870551987,
          "peak_count_mae": 2.65625,
          "matched_fraction": 0.8683153839313926,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      }
    ]
  },
  {
    "task": "nmr.forward.13C",
    "dataset_name": "patent_test_10k",
    "status": "passed",
    "selection": {
      "read": 173,
      "missing_modality": 141,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "source_file": "smoke_forward_20261115_v3.json",
    "sample_limit": 32,
    "models": [
      {
        "model": "nmrnet",
        "metrics": {
          "matched_peak_mae_ppm": 8.041924852126245,
          "matched_peak_rmse_ppm": 24.297510376653264,
          "peak_count_mae": 18.193548387096776,
          "matched_fraction": 0.43315070786510484,
          "examples": 31,
          "scored_examples": 31,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      },
      {
        "model": "nmrnetpp",
        "metrics": {
          "matched_peak_mae_ppm": 7.5615217252266795,
          "matched_peak_rmse_ppm": 22.917821121262513,
          "peak_count_mae": 18.193548387096776,
          "matched_fraction": 0.43315070786510484,
          "examples": 31,
          "scored_examples": 31,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      }
    ]
  },
  {
    "task": "nmr.forward.13C",
    "dataset_name": "nmrexp_exp_10k",
    "status": "passed",
    "selection": {
      "read": 50,
      "missing_modality": 18,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "source_file": "smoke_forward_20261115_v3.json",
    "sample_limit": 32,
    "models": [
      {
        "model": "nmrnet",
        "metrics": {
          "matched_peak_mae_ppm": 1.3063837598230228,
          "matched_peak_rmse_ppm": 7.498559532565537,
          "peak_count_mae": 3.90625,
          "matched_fraction": 0.7535539713423682,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      },
      {
        "model": "nmrnetpp",
        "metrics": {
          "matched_peak_mae_ppm": 1.2925194849511477,
          "matched_peak_rmse_ppm": 8.097448280861592,
          "peak_count_mae": 3.90625,
          "matched_fraction": 0.7535539713423682,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      }
    ]
  },
  {
    "task": "nmr.forward.13C",
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
          "matched_peak_mae_ppm": 2.2765265164740645,
          "matched_peak_rmse_ppm": 3.99253565138379,
          "peak_count_mae": 2.625,
          "matched_fraction": 0.9080126647199663,
          "examples": 32,
          "scored_examples": 32,
          "aggregation": "equal_weight_per_molecule",
          "assignment": "minimum_absolute_error_without_atom_labels"
        }
      },
      {
        "model": "nmrnetpp",
        "metrics": {
          "matched_peak_mae_ppm": 2.4534173733134828,
          "matched_peak_rmse_ppm": 4.157696167382544,
          "peak_count_mae": 2.625,
          "matched_fraction": 0.9080126647199663,
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

[打开可运行 notebook](../notebooks/nmr-forward-13C.ipynb)

## 来源

[原始实现与发布](https://github.com/Colin-Jay/NMRNet)
