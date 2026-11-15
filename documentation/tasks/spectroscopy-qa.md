# Spectroscopy question answering

Answer a question grounded in supplied spectral evidence.

## Model and protocol

Requires a reference-answer dataset and compatible frozen QA weights. Generic structure-generation outputs are not substituted for QA answers.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "question": "How many distinct 13C shifts are listed?",
  "13C_shift_ppm": [
    18.2,
    58.3
  ]
}
```

## Outputs and metrics

No validated score is emitted while required assets or adapters are missing.

Metric fields: `answer_accuracy`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks spectroscopy.qa --limit 8 --output results/spectroscopy-qa.json
```

## Interpretation and limits

This task remains explicit in the catalog and is skipped rather than trained to completion.

## Recorded results

```json
[
  {
    "status": "not_evaluated",
    "reason": "需要有参考答案的题集和固定模型接口。"
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/spectroscopy-qa.ipynb)

## Source

[Original implementation / release](https://github.com/jiaqingxie/openmolspec-studio-frontend)
