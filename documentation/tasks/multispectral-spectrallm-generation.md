# Multispectral structure generation with SpectraLLM

Predict a structure jointly from one or more spectral modalities using released SpectraLLM weights.

## Model and protocol

The official current release is a 32B model. The locally found older 7B adapter refers to a missing base checkpoint and cannot be attached to an arbitrary model. Download the released model or provide its matching base; do not retrain.

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

No validated score is emitted while required assets or adapters are missing.

Metric fields: `exact_rate`, `valid_rate`. Domain: `mixed`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks multispectral.spectrallm.generation --limit 8 --output results/multispectral-spectrallm-generation.json
```

## Interpretation and limits

This task remains explicit in the catalog and is skipped rather than trained to completion.

## Recorded results

```json
[
  {
    "status": "not_evaluated",
    "reason": "官方新权重为 32B；当前本地仅有旧 7B adapter 且其指定基座缺失。需下载完整官方权重或提供匹配基座，不进行训练。"
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/multispectral-spectrallm-generation.ipynb)

## Source

[Original implementation / release](https://github.com/OPilgrim/SpectraLLM)
