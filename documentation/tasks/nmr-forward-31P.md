# Structure to 31P NMR: alignment audit

Evaluate a compatible frozen model for the selected nucleus without fitting a new reference or calibrating against test labels.

## Current evidence

Current solid-state weights are not validated for solution shifts. Resolve domain/reference compatibility before any fine-tuning decision.

## What goes in

| Field | Meaning |
| --- | --- |
| `smiles / geometry` | A valid molecular graph and a compatible 3D conformer; atom order must be preserved. |
| `nucleus` | 31P; the checkpoint must cover this nucleus. |
| `reference peaks` | Optional measured ppm values for evaluation; not an inference input. |

## What comes out

| Field | Meaning |
| --- | --- |
| `prediction_ppm` | Per-atom chemical shifts in ppm, with atom indices or a peak list. |
| `error / coverage` | Reference-matched errors and coverage; matching does not establish atom assignments. |

## A real recorded example

The first recorded example is shown below, regardless of whether it succeeds. Array previews explicitly state their lengths; download the evidence JSON for complete values. Reference labels are kept separate from model inputs.

```json
{
  "input": {
    "smiles": "COc1ccc(P(=O)(CCCc2ccccc2)OCC)cc1",
    "nucleus": "P",
    "atom_indices": [
      6
    ]
  },
  "output": {
    "prediction_ppm": 246.23046875
  },
  "reference": {
    "ppm": 44.90999984741211
  }
}
```

![nmr.forward.31P actual results](../assets/gallery/nmr-forward-31P.png)

[SVG](../assets/gallery/nmr-forward-31P.svg) · [PNG](../assets/gallery/nmr-forward-31P.png) · [Full input/output JSON](../assets/examples/nmr-forward-31P.json)

## Actual evaluation results

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | recorded model | mae_ppm | 226.449 |
| recorded evaluation | recorded model | rmse_ppm | 237.252 |
| recorded evaluation | recorded model | examples | 32 |

Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.

## Model and method

Earlier cached predictions were paired with an LMDB that had subsequently changed. Their logged targets disagree with current labels, so those earlier scores are invalidated. Frozen re-inference on an exact hashed input repairs the data pairing.

The current solid-state checkpoints still have unverified reference compatibility with solution shifts and large errors after alignment repair. Keep those numbers diagnostic-only; do not add a fitted offset to make the test score smaller.

## Reproduce

[Notebook with executed figures](../notebooks/nmr-forward-31P.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.31P --limit 8 --output results/nmr-forward-31P-new.json
```

## Limits and provenance

A compatible released solution checkpoint or documented reference conversion is required for a valid primary score. No retraining or fitted recalibration is permitted.

- [fp_frozen_fresh_diagnostic_20261115.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/fp_frozen_fresh_diagnostic_20261115.json) — SHA-256 `7a44203bd5826e778a9006edd92dee0ec71e47930c2a980f6082313974c68475`

[Original model / 原模型](https://github.com/Colin-Jay/NMRNet) · [Model review / 模型检查](../model-audit.md)
