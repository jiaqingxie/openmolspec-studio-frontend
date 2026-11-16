# Spectroscopy QA

Deferred at the user's request.

## Model and protocol

Excluded from default benchmark runs; explicit requests are skipped.

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

Any recorded results below are historical diagnostics only.

Metric fields: `answer_accuracy`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks spectroscopy.qa --limit 8 --output results/spectroscopy-qa.json
```

## Interpretation and limits

No further model downloads, inference or training are planned for this task.

## Recorded results

```json
[
  {
    "task": "spectroscopy.qa",
    "status": "diagnostic_only",
    "model": "local_MolSpect-7B",
    "scope": "explicit_zero_shot_baseline_not_the_official_SpectraLLM_32B_release",
    "metrics": {
      "accuracy": 0.0,
      "examples": 4
    },
    "decoding": {
      "do_sample": false,
      "max_new_tokens": 32,
      "seed": 42
    },
    "formula_provided_to_model": false,
    "source_file": "molspect_zeroshot_formula_qa_20261116.json",
    "sample_limit": 4
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/spectroscopy-qa.ipynb)

## Source

[Original implementation / release](https://github.com/jiaqingxie/openmolspec-studio-frontend)
