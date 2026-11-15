# Structure to 31P NMR: alignment audit

Evaluate a compatible frozen model for the selected nucleus without fitting a new reference or calibrating against test labels.

## Model and protocol

Earlier cached predictions were paired with an LMDB that had subsequently changed. Their logged targets disagree with current labels, so those earlier scores are invalidated. Frozen re-inference on an exact hashed input repairs the data pairing.

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

The current solid-state checkpoints still have unverified reference compatibility with solution shifts and large errors after alignment repair. Keep those numbers diagnostic-only; do not add a fitted offset to make the test score smaller.

Metric fields: `mae_ppm`, `rmse_ppm`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.31P --limit 8 --output results/nmr-forward-31P.json
```

## Interpretation and limits

A compatible released solution checkpoint or documented reference conversion is required for a valid primary score. No retraining or fitted recalibration is permitted.

## Recorded results

```json
[
  {
    "task": "nmr.forward.31P",
    "dataset_name": null,
    "status": "skipped",
    "reason": "F/P prediction-label alignment is verified, but the available solid-state checkpoint has no verified solution-shift reference. A compatible released checkpoint or documented reference conversion is required; no training or fitted calibration is performed. Use --allow-cross-domain-diagnostic only for a labeled diagnostic report.",
    "source_file": "fp_primary_score_gate_20261116.json",
    "sample_limit": 32
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/nmr-forward-31P.ipynb)

## Source

[Original implementation / release](https://github.com/Colin-Jay/NMRNet)
