# Molecular-formula prediction from spectra

Predict a molecular formula without providing it as an input.

## Model and protocol

The current NMR generator consumes a known formula and therefore cannot establish formula-prediction accuracy. A compatible released model is required.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "h_nmr_ppm": [
    1.2,
    3.65
  ],
  "c_nmr_ppm": [
    18.2,
    58.3
  ],
  "formula_provided": false
}
```

## Outputs and metrics

No validated score is emitted while required assets or adapters are missing.

Metric fields: `formula_exact_rate`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.formula --limit 8 --output results/nmr-formula.json
```

## Interpretation and limits

This task remains explicit in the catalog and is skipped rather than trained to completion.

## Recorded results

```json
[
  {
    "status": "not_evaluated",
    "reason": "现有生成器使用给定分子式；不将其计为分子式预测器。"
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/nmr-formula.ipynb)

## Source

[Original implementation / release](https://github.com/jiaqingxie/openmolspec-studio-frontend)
