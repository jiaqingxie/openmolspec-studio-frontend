# Cross-solvent chemical-shift transfer

Predict a spectrum under a target solvent from the same molecule in a source solvent.

## Model and protocol

Candidate solvent-conditioned models include NMRNet++ and TransPeakNet. Their relevant weights and paired experimental records must be obtained and verified. Solvent-conditioned forward prediction alone does not validate cross-solvent transfer. A new fitted correction would violate the no-training constraint.

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
    "reason": "候选为带溶剂条件的 NMRNet++/TransPeakNet；需取得对应权重及同一分子的跨溶剂配对记录后验证。"
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/nmr-solvent_transfer.ipynb)

## Source

[Original implementation / release](https://github.com/siriusxiao62/2dNMR)
