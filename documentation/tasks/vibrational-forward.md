# Conformer to IR and Raman

Predict vibrational spectra from a fixed molecular geometry with Xinyu openSpec's Equiformer-v3 Hessian and response checkpoints.

## Current evidence

Correct Xinyu Hessian/response route and paired geometry. Two examples demonstrate execution only; evaluate a held-out geometry set before adaptation.

## What goes in

| Field | Meaning |
| --- | --- |
| `geometry` | Element symbols and N×3 Cartesian coordinates in Å, taken from the same Gaussian log as the reference. |
| `checkpoints` | Xinyu openSpec Equiformer-v3 Hessian Hi/Hij and dipole/polarizability derivative weights. |

## What comes out

| Field | Meaning |
| --- | --- |
| `IR / Raman` | Two normalized intensity arrays on 1024 points spanning 400–4000 cm⁻¹. |
| `spectral error` | Channel-wise cosine similarity and intensity MAE against paired computed reference spectra. |

## A real recorded example

The first recorded example is shown below, regardless of whether it succeeds. Array previews explicitly state their lengths; download the evidence JSON for complete values. Reference labels are kept separate from model inputs.

![vibrational.forward actual results](../assets/gallery/vibrational-forward.png)

[SVG](../assets/gallery/vibrational-forward.svg) · [PNG](../assets/gallery/vibrational-forward.png) · [Full input/output JSON](../assets/examples/vibrational-forward.json)

<details><summary>Inspect the actual input and output fields</summary>

```json
{
  "sample_id": "NISTIR-11730",
  "input": {
    "gaussian_log": "NISTIR-11730.log",
    "sha256": "894857d2c85d7106e5613540c593ff5a2ca3e2c90bed289575d38227086c2df1",
    "atoms": 13
  },
  "output": {
    "wavenumber_cm1": {
      "length": 1024,
      "first_values": [
        400.0,
        403.5190734863281,
        407.0381164550781,
        410.55718994140625
      ]
    },
    "predicted_ir": {
      "length": 1024,
      "first_values": [
        0.01742994412779808,
        0.013713346794247627,
        0.011153731495141983,
        0.009342214092612267
      ]
    },
    "predicted_raman": {
      "length": 1024,
      "first_values": [
        0.009821882471442223,
        0.007297216448932886,
        0.005653610453009605,
        0.004528572782874107
      ]
    }
  },
  "reference": {
    "reference_ir": {
      "length": 1024,
      "first_values": [
        0.01633988507091999,
        0.013211564160883427,
        0.011014701798558235,
        0.009432419203221798
      ]
    },
    "reference_raman": {
      "length": 1024,
      "first_values": [
        0.007780710235238075,
        0.005948643200099468,
        0.004715456161648035,
        0.0038486106786876917
      ]
    }
  },
  "metrics": {
    "ir_cosine_similarity": 0.9578531980514526,
    "ir_mae": 0.009397805668413639,
    "raman_cosine_similarity": 0.9989054203033447,
    "raman_mae": 0.0008200838346965611
  }
}
```

</details>

## Actual evaluation results

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded sample | recorded model | ir_cosine_similarity | 0.977503 |
| recorded sample | recorded model | raman_cosine_similarity | 0.990194 |

Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.

## Model and method

Use exactly the coordinates associated with the reference Gaussian spectra. The adapter checks that XYZ loading preserves those coordinates, predicts Hessian/response tensors, and reconstructs broadened normalized IR/Raman spectra.

Compare normalized predicted and reference spectra on the common 1024-point, 400–4000 cm⁻¹ axis. Report channel-wise cosine similarity and intensity MAE.

## Reproduce

[Notebook with executed figures](../notebooks/vibrational-forward.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks vibrational.forward --limit 8 --output results/vibrational-forward-new.json
```

## Limits and provenance

The default two real Gaussian examples establish paired execution only. Their held-out status is not audited. An independently generated RDKit conformer must not be substituted and presented as the original reference geometry.

<details><summary>Source reports and SHA-256 fingerprints</summary>

- [vibrational_forward_paired_logs_20261116.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/vibrational_forward_paired_logs_20261116.json) — SHA-256 `3e35b2c5b0c5b83715f49397e9d3ab5a744429ec90bff2551a96ea0d1641e087`

</details>


[Original model / 原模型](https://github.com/X1nyuLu/openSpec-alpha) · [Model review / 模型检查](../model-audit.md)
