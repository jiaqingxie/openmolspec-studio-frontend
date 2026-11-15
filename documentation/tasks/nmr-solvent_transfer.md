# Cross-solvent chemical-shift transfer

Predict a spectrum under a target solvent from the same molecule in a source solvent.

## Model and protocol

Requires paired experimental records and an existing solvent-conditioned model. A new fitted solvent correction would violate the no-training constraint.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "smiles": "CCO",
  "nucleus": "1H",
  "source_solvent": "CDCl3",
  "target_solvent": "DMSO-d6",
  "source_peaks_ppm": [
    1.2,
    3.65
  ]
}
```

## Outputs and metrics

No validated score is emitted while required assets or adapters are missing.

Metric fields: `mae_ppm`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.solvent_transfer --limit 8 --output results/nmr-solvent_transfer.json
```

## Interpretation and limits

This task remains explicit in the catalog and is skipped rather than trained to completion.

## Recorded results

```json
[
  {
    "status": "not_evaluated",
    "reason": "需要同一分子跨溶剂配对记录及已有可用模型。"
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/nmr-solvent_transfer.ipynb)

## Source

[Original implementation / release](https://github.com/jiaqingxie/openmolspec-studio-frontend)
