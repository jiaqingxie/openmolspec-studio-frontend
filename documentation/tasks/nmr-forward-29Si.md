# Structure to 29Si NMR

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
  --tasks nmr.forward.29Si --limit 8 --output results/nmr-forward-29Si.json
```

## Interpretation and limits

A peak-matching score is not atom-assignment accuracy. Missing compatible B/Si weights cause an explicit skip; this project does not train new heads to fill that gap.

## Recorded results

```json
[
  {
    "status": "not_evaluated",
    "reason": "保留六核任务定义；尚未验证可用于此实验域的 checkpoint 和预测文件。"
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/nmr-forward-29Si.ipynb)

## Source

[Original implementation / release](https://github.com/Colin-Jay/NMRNet)
