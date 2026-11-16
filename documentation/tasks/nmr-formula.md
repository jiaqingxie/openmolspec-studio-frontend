# Molecular formula prediction

Deferred at the user's request.

## Model and protocol

Excluded from default benchmark runs; explicit requests are skipped.

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

Any recorded results below are historical diagnostics only.

Metric fields: `formula_exact_rate`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.formula --limit 8 --output results/nmr-formula.json
```

## Interpretation and limits

No further model downloads, inference or training are planned for this task.

## Recorded results

```json
[
  {
    "task": "nmr.formula",
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

[Open the runnable notebook](../notebooks/nmr-formula.ipynb)

## Source

[Original implementation / release](https://github.com/jiaqingxie/openmolspec-studio-frontend)
