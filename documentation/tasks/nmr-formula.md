# Molecular-formula prediction from spectra

Predict a molecular formula without providing it as an input.

## Model and protocol

The current NMR generator consumes a known formula and therefore cannot establish formula-prediction accuracy. A compatible released model is required. A separate local MolSpect-7B zero-shot probe uses real H/C records and the stored chat template, with no supplied formula or structure and a 32-new-token greedy limit.

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

Completed diagnostic reports show exact formula accuracy or explicit 13C-entry-count answer accuracy; incomplete runs are excluded.

Metric fields: `formula_exact_rate`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.formula --limit 8 --output results/nmr-formula.json
```

## Interpretation and limits

The local checkpoint release/stage and prompt compatibility are unverified. This probe is neither an official MolSpectLLM reproduction nor a SpectraLLM32B benchmark, and does not enable the primary task adapter. No training is performed.

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

[Original implementation / release](https://github.com/Eurekashen/SpecMol)
