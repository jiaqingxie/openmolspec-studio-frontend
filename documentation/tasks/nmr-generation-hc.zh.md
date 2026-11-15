# 谱图 → SMILES · HC

用已有生成模型从实验 H/C NMR 预测 SMILES 候选。

## 模型与协议

该模型需要显式给定分子式。按原推理代码的有效性、分子式一致性和模型分数排序 beam，取 top-1 评分。不会从目标 SMILES 偷偷推导缺失的输入分子式。

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

报告有效 SMILES 比率、规范异构 SMILES exact match、分子式一致率，同时保存 beam size、模态 mask 和样本。JSONL 的 smiles 仅是评测答案，不是生成输入。

适配器：`spec2struct_generation`。数据域：`experimental`。指标字段：`valid_rate`、`exact_rate`、`formula_match_rate`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.generation.hc --limit 8 --output results/nmr-generation-hc.json
```

## 解释与限制

给定分子式的结构生成与分子式预测、无分子式生成是不同任务。跨数据集 exact match 低或为零时保留真实结果，不替换成缓存答案。

## 已记录结果

```json
[
  {
    "task": "nmr.generation.hc",
    "dataset_name": "nmrspec_test",
    "status": "passed",
    "metrics": {
      "modality": "available",
      "examples": 32,
      "skipped_missing_modality": 0,
      "valid": 32,
      "formula_match": 29,
      "exact": 4,
      "valid_rate": 1.0,
      "formula_match_rate": 0.90625,
      "exact_rate": 0.125
    },
    "beam_size": 5,
    "selection": {
      "read": 32,
      "missing_modality": 0,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "sampling": "first_distinct_canonical_structures_in_file_order",
    "source_file": "smoke_nmr_20261115_v2.json",
    "sample_limit": 32
  },
  {
    "task": "nmr.generation.hc",
    "dataset_name": "patent_test_10k",
    "status": "passed",
    "metrics": {
      "modality": "available",
      "examples": 32,
      "skipped_missing_modality": 0,
      "valid": 24,
      "formula_match": 1,
      "exact": 0,
      "valid_rate": 0.75,
      "formula_match_rate": 0.03125,
      "exact_rate": 0.0
    },
    "beam_size": 5,
    "selection": {
      "read": 173,
      "missing_modality": 141,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "sampling": "first_distinct_canonical_structures_in_file_order",
    "source_file": "smoke_nmr_20261115_v2.json",
    "sample_limit": 32
  },
  {
    "task": "nmr.generation.hc",
    "dataset_name": "nmrexp_exp_10k",
    "status": "passed",
    "metrics": {
      "modality": "available",
      "examples": 32,
      "skipped_missing_modality": 0,
      "valid": 32,
      "formula_match": 29,
      "exact": 22,
      "valid_rate": 1.0,
      "formula_match_rate": 0.90625,
      "exact_rate": 0.6875
    },
    "beam_size": 5,
    "selection": {
      "read": 50,
      "missing_modality": 18,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "sampling": "first_distinct_canonical_structures_in_file_order",
    "source_file": "smoke_nmr_20261115_v2.json",
    "sample_limit": 32
  },
  {
    "task": "nmr.generation.hc",
    "dataset_name": "nmrgym_test",
    "status": "passed",
    "metrics": {
      "modality": "available",
      "examples": 32,
      "skipped_missing_modality": 0,
      "valid": 25,
      "formula_match": 15,
      "exact": 0,
      "valid_rate": 0.78125,
      "formula_match_rate": 0.46875,
      "exact_rate": 0.0
    },
    "beam_size": 5,
    "selection": {
      "read": 32,
      "missing_modality": 0,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "sampling": "first_distinct_canonical_structures_in_file_order",
    "source_file": "smoke_nmr_20261115_v2.json",
    "sample_limit": 32
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-generation-hc.ipynb)

## 来源

[原始实现与发布](https://github.com/jiaqingxie/openmolspec-studio-frontend)
