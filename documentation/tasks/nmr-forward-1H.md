# Structure to 1H NMR

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
  --tasks nmr.forward.1H --limit 8 --output results/nmr-forward-1H.json
```

## Interpretation and limits

A peak-matching score is not atom-assignment accuracy. Missing compatible B/Si weights cause an explicit skip; this project does not train new heads to fill that gap.

## Recorded results

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

[Open the runnable notebook](../notebooks/nmr-forward-1H.ipynb)

## Source

[Original implementation / release](https://github.com/Colin-Jay/NMRNet)
