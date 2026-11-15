# 结构 → 谱图检索 · H

用已有双编码器，从 NMR 谱检索候选分子，或由分子检索候选谱。

## 模型与协议

H-only、C-only、H+C 使用明确的可见性 mask，谱编码器不接收分子式。规范异构 SMILES 用于判定对应关系，所选测试分子构成本次候选池。

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

报告 Recall@1/5/10、MRR、查询数和候选数。byte 分子编码器遇到超长 SMILES 时排除并计数，补取后续合格记录，不截断分子结构。

适配器：`spec2struct_alignment`。数据域：`experimental`。指标字段：`recall_at_1`、`recall_at_5`、`recall_at_10`、`mrr`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.retrieval.h.m2s --limit 8 --output results/nmr-retrieval-h-m2s.json
```

## 解释与限制

16、32 和全库候选的成绩不能直接比较。数据来源和训练/测试重叠仍需单独审计。JSONL 中的 smiles 是评测目标或候选身份，不作为谱编码器的输入。

## 已记录结果

```json
[
  {
    "task": "nmr.retrieval.h.m2s",
    "dataset_name": "nmrspec_test",
    "status": "passed",
    "metrics": {
      "recall_at_1": 1.0,
      "recall_at_5": 1.0,
      "recall_at_10": 1.0,
      "mrr": 1.0,
      "queries": 32,
      "candidate_pool": 32,
      "unique_candidates": 32,
      "tie_policy": "stable_candidate_order"
    },
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
    "task": "nmr.retrieval.h.m2s",
    "dataset_name": "patent_test_10k",
    "status": "passed",
    "metrics": {
      "recall_at_1": 0.625,
      "recall_at_5": 0.9375,
      "recall_at_10": 0.96875,
      "mrr": 0.7752976190476191,
      "queries": 32,
      "candidate_pool": 32,
      "unique_candidates": 32,
      "tie_policy": "stable_candidate_order"
    },
    "selection": {
      "read": 33,
      "missing_modality": 0,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 1
    },
    "sampling": "first_distinct_canonical_structures_in_file_order",
    "source_file": "smoke_nmr_20261115_v2.json",
    "sample_limit": 32
  },
  {
    "task": "nmr.retrieval.h.m2s",
    "dataset_name": "nmrexp_exp_10k",
    "status": "passed",
    "metrics": {
      "recall_at_1": 0.84375,
      "recall_at_5": 0.96875,
      "recall_at_10": 1.0,
      "mrr": 0.8877604166666666,
      "queries": 32,
      "candidate_pool": 32,
      "unique_candidates": 32,
      "tie_policy": "stable_candidate_order"
    },
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
    "task": "nmr.retrieval.h.m2s",
    "dataset_name": "nmrgym_test",
    "status": "passed",
    "metrics": {
      "recall_at_1": 0.65625,
      "recall_at_5": 0.90625,
      "recall_at_10": 0.90625,
      "mrr": 0.7492974473443224,
      "queries": 32,
      "candidate_pool": 32,
      "unique_candidates": 32,
      "tie_policy": "stable_candidate_order"
    },
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

[打开可运行 notebook](../notebooks/nmr-retrieval-h-m2s.ipynb)

## 来源

[原始实现与发布](https://github.com/jiaqingxie/openmolspec-studio-frontend)
