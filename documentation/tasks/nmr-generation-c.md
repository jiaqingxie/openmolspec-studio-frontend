# NMR-to-SMILES generation: C

Generate candidate molecular structures from experimental H/C NMR with the existing generation checkpoint.

## Model and protocol

The existing model requires an explicitly supplied molecular formula. Beam candidates are ranked by validity, formula agreement and model score, following the checkpoint's inference code. No formula is derived secretly from the target structure.

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

Report valid SMILES rate, canonical exact-match rate and formula-match rate, with the beam size, modality mask and selected records.

Metric fields: `valid_rate`, `exact_rate`, `formula_match_rate`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.generation.c --limit 8 --output results/nmr-generation-c.json
```

## Interpretation and limits

Formula-conditioned generation must be distinguished from formula prediction and from generation without a supplied formula. Low or zero cross-dataset exact match is retained, not replaced by cached answers.

## Recorded results

```json
[
  {
    "task": "nmr.generation.c",
    "dataset_name": "nmrspec_test",
    "status": "passed",
    "metrics": {
      "modality": "available",
      "examples": 32,
      "skipped_missing_modality": 0,
      "valid": 31,
      "formula_match": 23,
      "exact": 3,
      "valid_rate": 0.96875,
      "formula_match_rate": 0.71875,
      "exact_rate": 0.09375
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
    "task": "nmr.generation.c",
    "dataset_name": "patent_test_10k",
    "status": "passed",
    "metrics": {
      "modality": "available",
      "examples": 32,
      "skipped_missing_modality": 0,
      "valid": 28,
      "formula_match": 3,
      "exact": 0,
      "valid_rate": 0.875,
      "formula_match_rate": 0.09375,
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
    "task": "nmr.generation.c",
    "dataset_name": "nmrexp_exp_10k",
    "status": "passed",
    "metrics": {
      "modality": "available",
      "examples": 32,
      "skipped_missing_modality": 0,
      "valid": 32,
      "formula_match": 30,
      "exact": 19,
      "valid_rate": 1.0,
      "formula_match_rate": 0.9375,
      "exact_rate": 0.59375
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
    "task": "nmr.generation.c",
    "dataset_name": "nmrgym_test",
    "status": "passed",
    "metrics": {
      "modality": "available",
      "examples": 32,
      "skipped_missing_modality": 0,
      "valid": 30,
      "formula_match": 16,
      "exact": 0,
      "valid_rate": 0.9375,
      "formula_match_rate": 0.5,
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

[Open the runnable notebook](../notebooks/nmr-generation-c.ipynb)

## Source

[Original implementation / release](https://github.com/jiaqingxie/openmolspec-studio-frontend)
