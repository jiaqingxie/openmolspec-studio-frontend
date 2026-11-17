# NMR-to-SMILES generation: C

Generate candidate molecular structures from experimental H/C NMR with the existing generation checkpoint.

**Evaluation limitation:** molecular overlap with checkpoint-recorded training data is confirmed for several NMR views. The final generator also has a training-file fingerprint discrepancy. These runs do not establish independent generalization.  [Training-history audit / 训练历史审计](../training-overlap.md)

## Current evidence

Strong dataset dependence: zero exact matches on the 32-example patent and NMRGym checks. Prioritize a clean external test and parsing/token coverage audit; then consider domain fine-tuning.

## What goes in

| Field | Meaning |
| --- | --- |
| `h_nmr / c_nmr` | C records: shift positions (ppm), multiplicity/integration/J where recorded; obey the modality mask. |
| `formula` | A known molecular formula is required by this checkpoint. |
| `beam_size` | Number of decoded candidates; 5 in the documented experiment. |

## What comes out

| Field | Meaning |
| --- | --- |
| `candidates` | Generated SMILES, canonical structures, validity, formula match and model score. |
| `exact_match` | Compare the selected candidate with a held reference structure; valid SMILES alone is not success. |

## A real recorded example

The first recorded example is shown below, regardless of whether it succeeds. Array previews explicitly state their lengths; download the evidence JSON for complete values. Reference labels are kept separate from model inputs.

![nmr.generation.c actual results](../assets/gallery/nmr-generation-c.png)

[SVG](../assets/gallery/nmr-generation-c.svg) · [PNG](../assets/gallery/nmr-generation-c.png) · [Full input/output JSON](../assets/examples/nmr-generation-c.json)

<details><summary>Inspect the actual input and output fields</summary>

```json
{
  "input": {
    "formula": "C22H28",
    "h_nmr": [],
    "c_nmr": [
      {
        "type": "13C NMR",
        "chemical_shift": "150.22, 148.03, 142.68, 138.28, 128.36, 128.22, 125.68, 125.58, 125.12, 111.51, 35.72, 35.03, 34.46, 31.32, 31.11, 27.93"
      }
    ],
    "modality_mask": [
      0,
      1
    ]
  },
  "reference_smiles": "C=C(CCCCc1ccccc1)c1ccc(C(C)(C)C)cc1",
  "candidates": {
    "length": 5,
    "first_values": [
      {
        "smiles": "C=C(CCc1ccc(C(C)(C)C)cc1)CCc1ccccc1",
        "canonical_smiles": "C=C(CCc1ccccc1)CCc1ccc(C(C)(C)C)cc1",
        "score": -2.8281531435108036,
        "valid": true,
        "formula_match": true
      },
      {
        "smiles": "C=C(c1ccc(C(C)(C)C)cc1)c1ccc(C(C)(C)C)cc1",
        "canonical_smiles": "C=C(c1ccc(C(C)(C)C)cc1)c1ccc(C(C)(C)C)cc1",
        "score": -3.3919860787640914,
        "valid": true,
        "formula_match": true
      },
      {
        "smiles": "C=C(CCc1ccccc1)c1ccc(C(C)(C)C)cc1CC",
        "canonical_smiles": "C=C(CCc1ccccc1)c1ccc(C(C)(C)C)cc1CC",
        "score": -3.731960778021964,
        "valid": true,
        "formula_match": true
      },
      {
        "smiles": "C=C(CCCc1ccccc1)c1ccc(C(C)(C)C)cc1",
        "canonical_smiles": "C=C(CCCc1ccccc1)c1ccc(C(C)(C)C)cc1",
        "score": -3.0991712021525473,
        "valid": true,
        "formula_match": false
      }
    ]
  },
  "exact_match": false
}
```

</details>

## Actual evaluation results

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| nmrspec_test | recorded model | examples | 32 |
| nmrspec_test | recorded model | valid_rate | 0.96875 |
| nmrspec_test | recorded model | formula_match_rate | 0.71875 |
| nmrspec_test | recorded model | exact_rate | 0.09375 |
| patent_test_10k | recorded model | examples | 32 |
| patent_test_10k | recorded model | valid_rate | 0.875 |
| patent_test_10k | recorded model | formula_match_rate | 0.09375 |
| patent_test_10k | recorded model | exact_rate | 0 |
| nmrexp_exp_10k | recorded model | examples | 32 |
| nmrexp_exp_10k | recorded model | valid_rate | 1 |
| nmrexp_exp_10k | recorded model | formula_match_rate | 0.9375 |
| nmrexp_exp_10k | recorded model | exact_rate | 0.59375 |
| nmrgym_test | recorded model | examples | 32 |
| nmrgym_test | recorded model | valid_rate | 0.9375 |
| nmrgym_test | recorded model | formula_match_rate | 0.5 |
| nmrgym_test | recorded model | exact_rate | 0 |

Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.

## Model and method

The existing model requires an explicitly supplied molecular formula. Beam candidates are ranked by validity, formula agreement and model score, following the checkpoint's inference code. No formula is derived secretly from the target structure.

Report valid SMILES rate, canonical exact-match rate and formula-match rate, with the beam size, modality mask and selected records.

## Reproduce

[Notebook with executed figures](../notebooks/nmr-generation-c.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.generation.c --limit 8 --output results/nmr-generation-c-new.json
```

## Limits and provenance

Formula-conditioned generation must be distinguished from formula prediction and from generation without a supplied formula. Low or zero cross-dataset exact match is retained, not replaced by cached answers.

<details><summary>Source reports and SHA-256 fingerprints</summary>

- [nmr_documented_examples_20261117_v2.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/nmr_documented_examples_20261117_v2.json) — SHA-256 `669413d6fc0939bdb6826782d41fc13cf12926a672418ecb46303f0b8ba05b99`

</details>


[Original model / 原模型](https://github.com/jiaqingxie/openmolspec-studio-frontend) · [Model review / 模型检查](../model-audit.md)
