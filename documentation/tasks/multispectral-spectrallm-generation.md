# SpectraLLM structure generation

Deferred at the user's request.

## Model and protocol

Excluded from default benchmark runs; explicit requests are skipped.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "ir": "1024 intensities on the documented axis",
  "raman": "1024 intensities on the same axis",
  "h_nmr_ppm": [
    1.2,
    3.65
  ],
  "c_nmr_ppm": [
    18.2,
    58.3
  ],
  "prompt_format": "must follow the released model's preprocessing"
}
```

## Outputs and metrics

Any recorded results below are historical diagnostics only.

Metric fields: `exact_rate`, `valid_rate`. Domain: `mixed`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks multispectral.spectrallm.generation --limit 8 --output results/multispectral-spectrallm-generation.json
```

## Interpretation and limits

No further model downloads, inference or training are planned for this task.

## Recorded results

```json
[
  {
    "status": "not_evaluated",
    "reason": "用户已明确暂不推进；历史结果仅作归档，不再运行。"
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/multispectral-spectrallm-generation.ipynb)

## Source

[Original implementation / release](https://github.com/jiaqingxie/openmolspec-studio-frontend)
