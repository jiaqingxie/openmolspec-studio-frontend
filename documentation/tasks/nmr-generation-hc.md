# NMR-to-SMILES generation: HC

Generate candidate molecular structures from experimental H/C NMR with the existing generation checkpoint.

## Current evidence

Strong dataset dependence: zero exact matches on the 32-example patent and NMRGym checks. Prioritize a clean external test and parsing/token coverage audit; then consider domain fine-tuning.

## What goes in

| Field | Meaning |
| --- | --- |
| `h_nmr / c_nmr` | HC records: shift positions (ppm), multiplicity/integration/J where recorded; obey the modality mask. |
| `formula` | A known molecular formula is required by this checkpoint. |
| `beam_size` | Number of decoded candidates; 5 in the documented experiment. |

## What comes out

| Field | Meaning |
| --- | --- |
| `candidates` | Generated SMILES, canonical structures, validity, formula match and model score. |
| `exact_match` | Compare the selected candidate with a held reference structure; valid SMILES alone is not success. |

## A real recorded example

The first recorded example is shown below, regardless of whether it succeeds. Array previews explicitly state their lengths; download the evidence JSON for complete values. Reference labels are kept separate from model inputs.

```json
{
  "input": {
    "formula": "C22H28",
    "h_nmr": [
      {
        "type": "1H NMR",
        "chemical_shift": "7.34 (s, 4H), 7.265 (m, 2H), 7.165 (m, 3H), 5.26 (d, J=1.6 Hz, 1H), 5.01 (t, J=1.4 Hz, 1H), 2.61 (t, J=7.8 Hz, 2H), 2.53 (t, J=7.6 Hz, 2H), 1.665 (m, 2H), 1.52 (d, J=7.7 Hz, 2H), 1.33 (s, 9H)"
      }
    ],
    "c_nmr": [
      {
        "type": "13C NMR",
        "chemical_shift": "150.22, 148.03, 142.68, 138.28, 128.36, 128.22, 125.68, 125.58, 125.12, 111.51, 35.72, 35.03, 34.46, 31.32, 31.11, 27.93"
      }
    ],
    "modality_mask": [
      1,
      1
    ]
  },
  "reference_smiles": "C=C(CCCCc1ccccc1)c1ccc(C(C)(C)C)cc1",
  "candidates": {
    "length": 5,
    "first_values": [
      {
        "smiles": "C=C(CCCCc1ccc(C(C)(C)C)cc1)c1ccccc1",
        "canonical_smiles": "C=C(CCCCc1ccc(C(C)(C)C)cc1)c1ccccc1",
        "score": -1.4133434984593123,
        "valid": true,
        "formula_match": true
      },
      {
        "smiles": "C=C(CCCCc1ccccc1)c1ccc(C(C)(C)C)cc1",
        "canonical_smiles": "C=C(CCCCc1ccccc1)c1ccc(C(C)(C)C)cc1",
        "score": -1.5937606929851142,
        "valid": true,
        "formula_match": true
      },
      {
        "smiles": "C=C(CCCc1ccc(C(C)(C)C)cc1)Cc1ccccc1",
        "canonical_smiles": "C=C(CCCc1ccc(C(C)(C)C)cc1)Cc1ccccc1",
        "score": -3.3677357960558183,
        "valid": true,
        "formula_match": true
      },
      {
        "smiles": "C=C(CCCCc1ccccc1)CCCc1ccccc1",
        "canonical_smiles": "C=C(CCCCc1ccccc1)CCCc1ccccc1",
        "score": -2.710929739130215,
        "valid": true,
        "formula_match": false
      }
    ]
  },
  "exact_match": false
}
```

![nmr.generation.hc actual results](../assets/gallery/nmr-generation-hc.png)

[SVG](../assets/gallery/nmr-generation-hc.svg) · [PNG](../assets/gallery/nmr-generation-hc.png) · [Full input/output JSON](../assets/examples/nmr-generation-hc.json)

## Actual evaluation results

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| nmrspec_test | recorded model | examples | 32 |
| nmrspec_test | recorded model | valid_rate | 1 |
| nmrspec_test | recorded model | formula_match_rate | 0.90625 |
| nmrspec_test | recorded model | exact_rate | 0.125 |
| patent_test_10k | recorded model | examples | 32 |
| patent_test_10k | recorded model | valid_rate | 0.75 |
| patent_test_10k | recorded model | formula_match_rate | 0.03125 |
| patent_test_10k | recorded model | exact_rate | 0 |
| nmrexp_exp_10k | recorded model | examples | 32 |
| nmrexp_exp_10k | recorded model | valid_rate | 1 |
| nmrexp_exp_10k | recorded model | formula_match_rate | 0.90625 |
| nmrexp_exp_10k | recorded model | exact_rate | 0.6875 |
| nmrgym_test | recorded model | examples | 32 |
| nmrgym_test | recorded model | valid_rate | 0.78125 |
| nmrgym_test | recorded model | formula_match_rate | 0.46875 |
| nmrgym_test | recorded model | exact_rate | 0 |

Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.

## Model and method

The existing model requires an explicitly supplied molecular formula. Beam candidates are ranked by validity, formula agreement and model score, following the checkpoint's inference code. No formula is derived secretly from the target structure.

Report valid SMILES rate, canonical exact-match rate and formula-match rate, with the beam size, modality mask and selected records.

## Reproduce

[Notebook with executed figures](../notebooks/nmr-generation-hc.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.generation.hc --limit 8 --output results/nmr-generation-hc-new.json
```

## Limits and provenance

Formula-conditioned generation must be distinguished from formula prediction and from generation without a supplied formula. Low or zero cross-dataset exact match is retained, not replaced by cached answers.

- [nmr_documented_examples_20261117_v2.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/nmr_documented_examples_20261117_v2.json) — SHA-256 `669413d6fc0939bdb6826782d41fc13cf12926a672418ecb46303f0b8ba05b99`

[Original model / 原模型](https://github.com/jiaqingxie/openmolspec-studio-frontend) · [Model review / 模型检查](../model-audit.md)
