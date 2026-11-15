# Spectroscopy question answering

Answer a question grounded in supplied spectral evidence.

## Model and protocol

Requires a reference-answer dataset and compatible frozen QA weights. Generic structure-generation outputs are not substituted for QA answers. A separate local MolSpect-7B zero-shot probe uses real H/C records and the stored chat template, with no supplied formula or structure and a 32-new-token greedy limit.

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

Completed diagnostic reports show exact formula accuracy or explicit 13C-entry-count answer accuracy; incomplete runs are excluded.

Metric fields: `answer_accuracy`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks spectroscopy.qa --limit 8 --output results/spectroscopy-qa.json
```

## Interpretation and limits

The local checkpoint release/stage and prompt compatibility are unverified. This probe is neither an official MolSpectLLM reproduction nor a SpectraLLM32B benchmark, and does not enable the primary task adapter. No training is performed.

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

[Original implementation / release](https://github.com/Eurekashen/SpecMol)
