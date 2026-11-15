# Structure to 13C NMR

Predict chemical shifts for the selected nucleus from a molecular structure, using existing frozen weights where available.

## Model and protocol

For H/C, score existing NMRNet and NMRNet++ predictions with their exact metadata. Unassigned experimental peak sets use minimum-error matching and retain peak-count and coverage diagnostics. B/Si currently lack a verified compatible weight/prediction pair.

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

Shifts and errors are in ppm. Molecule-macro matched-peak MAE/RMSE alone do not penalize every missing/extra peak; publish matched fraction and peak-count error alongside them.

Metric fields: `matched_peak_mae_ppm`, `matched_peak_rmse_ppm`, `peak_count_mae`, `matched_fraction`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.13C --limit 8 --output results/nmr-forward-13C.json
```

## Interpretation and limits

A peak-matching score is not atom-assignment accuracy. Missing compatible B/Si weights cause an explicit skip; this project does not train new heads to fill that gap.

## Recorded results

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

[Open the runnable notebook](../notebooks/nmr-forward-13C.ipynb)

## Source

[Original implementation / release](https://github.com/Colin-Jay/NMRNet)
