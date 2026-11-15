# Conformer to IR and Raman

Predict vibrational spectra from a fixed molecular geometry with existing Hessian and response models.

## Model and protocol

Use exactly the coordinates associated with the reference Gaussian spectra. The adapter checks that XYZ loading preserves those coordinates, predicts Hessian/response tensors, and reconstructs broadened normalized IR/Raman spectra.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "geometry": "Exact source Gaussian coordinates in Angstrom",
  "reference": "IR and Raman from the same Gaussian log",
  "example_logs": [
    "tests/fixtures/NISTIR-11730.log",
    "tests/fixtures/QM9-dsgdb9nsd_000001.log"
  ]
}
```

## Outputs and metrics

Compare normalized predicted and reference spectra on the common 1024-point, 400–4000 cm⁻¹ axis. Report channel-wise cosine similarity and intensity MAE.

Metric fields: `ir_cosine_similarity`, `raman_cosine_similarity`, `ir_mae`, `raman_mae`. Domain: `computed`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks vibrational.forward --limit 8 --output results/vibrational-forward.json
```

## Interpretation and limits

The default two real Gaussian examples establish paired execution only. Their held-out status is not audited. An independently generated RDKit conformer must not be substituted and presented as the original reference geometry.

## Recorded results

```json
[
  {
    "task": "vibrational.forward",
    "dataset_name": null,
    "status": "passed",
    "metrics": {
      "ir_cosine_similarity": 0.9775025844573975,
      "ir_mae": 0.005194379133172333,
      "raman_cosine_similarity": 0.9901942908763885,
      "raman_mae": 0.0016446748340968043
    },
    "examples": 2,
    "source_file": "vibrational_forward_paired_logs_20261116.json",
    "sample_limit": 2
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/vibrational-forward.ipynb)

## Source

[Original implementation / release](https://github.com/X1nyuLu/openSpec-alpha)
