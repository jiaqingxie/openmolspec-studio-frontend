# Structure to 29Si NMR: frozen diagnostic

Run the released liquid All-nucleus NMRNet checkpoint on existing atom-indexed validation records.

## Model and protocol

Completed 32 distinct molecules per nucleus using the saved scaler and full checkpoint restoration. Sample IDs and atom labels were checked against the exact inference inputs. See results/bsi_frozen_diagnostic_20261116.json and scripts/run_frozen_bsi_diagnostic.py.

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

Diagnostic atom-level MAE/RMSE in ppm; these are not peak-matching scores or validated held-out benchmark results.

Metric fields: `matched_peak_mae_ppm`, `matched_peak_rmse_ppm`, `peak_count_mae`, `matched_fraction`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.29Si --limit 8 --output results/nmr-forward-29Si.json
```

The primary command above skips unverified scoring. To reproduce both frozen diagnostics in a fresh directory:

```bash
python scripts/run_frozen_bsi_diagnostic.py --models-root /path/to/models --output /path/to/new-bsi-run --limit 32
```

## Interpretation and limits

Nucleus-specific training coverage, training overlap and experimental assignment provenance are unverified. The model has no solvent input. Primary scoring remains disabled; NMRNet++ B/Si-specific weights are still being sought. No fitting was performed.

## Recorded results

```json
[
  {
    "task": "nmr.forward.29Si",
    "status": "diagnostic_only",
    "model": "NMRNet liquid All-nucleus fold 0",
    "metrics": {
      "mae_ppm": 56.13358532078564,
      "rmse_ppm": 58.105817484466186
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

[Open the runnable notebook](../notebooks/nmr-forward-29Si.ipynb)

## Source

[Original implementation / release](https://github.com/Colin-Jay/NMRNet)
