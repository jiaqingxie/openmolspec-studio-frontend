# NMR retrieval: HC, m2s

Rank candidate structures from NMR spectra, or rank candidate spectra from a molecular structure, with the existing dual encoder.

## Model and protocol

H-only, C-only and H+C are explicit visibility masks. The spectral encoder does not receive the molecular formula. Canonical isomeric identities define positive matches; the selected dataset supplies the candidate pool.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

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

## Outputs and metrics

Report Recall@1/5/10 and MRR with candidate counts. Byte-encoded candidate SMILES that exceed checkpoint capacity are excluded and counted rather than silently truncated.

Metric fields: `recall_at_1`, `recall_at_5`, `recall_at_10`, `mrr`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.retrieval.hc.m2s --limit 8 --output results/nmr-retrieval-hc-m2s.json
```

## Interpretation and limits

Scores from 16, 32 and full-dataset candidate pools are not directly comparable. Existing dataset provenance and train/test overlap still require independent audit before an accuracy claim.

## Recorded results

```json
[
  {
    "task": "nmr.retrieval.hc.m2s",
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
    "task": "nmr.retrieval.hc.m2s",
    "dataset_name": "patent_test_10k",
    "status": "passed",
    "metrics": {
      "recall_at_1": 0.625,
      "recall_at_5": 0.90625,
      "recall_at_10": 0.90625,
      "mrr": 0.7388174019607843,
      "queries": 32,
      "candidate_pool": 32,
      "unique_candidates": 32,
      "tie_policy": "stable_candidate_order"
    },
    "selection": {
      "read": 173,
      "missing_modality": 140,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 1
    },
    "sampling": "first_distinct_canonical_structures_in_file_order",
    "source_file": "smoke_nmr_20261115_v2.json",
    "sample_limit": 32
  },
  {
    "task": "nmr.retrieval.hc.m2s",
    "dataset_name": "nmrexp_exp_10k",
    "status": "passed",
    "metrics": {
      "recall_at_1": 0.875,
      "recall_at_5": 1.0,
      "recall_at_10": 1.0,
      "mrr": 0.9244791666666666,
      "queries": 32,
      "candidate_pool": 32,
      "unique_candidates": 32,
      "tie_policy": "stable_candidate_order"
    },
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
    "task": "nmr.retrieval.hc.m2s",
    "dataset_name": "nmrgym_test",
    "status": "passed",
    "metrics": {
      "recall_at_1": 0.84375,
      "recall_at_5": 0.96875,
      "recall_at_10": 0.96875,
      "mrr": 0.8972537878787878,
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

[Open the runnable notebook](../notebooks/nmr-retrieval-hc-m2s.ipynb)

## Source

[Original implementation / release](https://github.com/jiaqingxie/openmolspec-studio-frontend)
