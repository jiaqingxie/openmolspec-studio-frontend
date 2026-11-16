# Vib2Mol generation with IR/Raman only

Use Xinyu's saved Vib2Mol models for spectral structure elucidation. The complete input is IR + Raman + H/C; the IR/Raman-only route is a missing-NMR ablation.

## Current evidence

Missing-channel ablation of a four-modal checkpoint. Poor scores do not validate a stand-alone IR/Raman model; use compatible unimodal weights or plan separate adaptation.

## What goes in

| Field | Meaning |
| --- | --- |
| `IR / Raman` | 1024 intensity samples per visible channel, ordered 400→4000 cm⁻¹, using the checkpoint normalization. |
| `missing channels` | This uses a four-modal checkpoint with channels omitted; it is an ablation, not a separately trained model. |

## What comes out

| Field | Meaning |
| --- | --- |
| `SMILES candidates` | Decoded valid, canonical unique candidates; full-input route uses beam 10 and ITM reranking. |
| `top-k` | Generation and reranking scores are separate. No molecular formula is supplied. |

## A real recorded example

The first recorded example is shown below, regardless of whether it succeeds. Array previews explicitly state their lengths; download the evidence JSON for complete values. Reference labels are kept separate from model inputs.

```json
{
  "reference": "CCCCc1cc2ccccc2c(OCCN(C)C)n1",
  "raw_top_1": "N1=NN2N=NN=C2N1",
  "canonical_top_1": "n1nc2[nH]nnn2n1",
  "input": {
    "ir": {
      "length": 1024,
      "first_values": [
        0.012721044011414051,
        0.012162876315414906,
        0.011645566672086716,
        0.010846862569451332
      ]
    },
    "raman": {
      "length": 1024,
      "first_values": [
        0.026861174032092094,
        0.022829052060842514,
        0.02229130268096924,
        0.0217174980789423
      ]
    }
  }
}
```

![vibrational.generation actual results](../assets/gallery/vibrational-generation.png)

[SVG](../assets/gallery/vibrational-generation.svg) · [PNG](../assets/gallery/vibrational-generation.png) · [Full input/output JSON](../assets/examples/vibrational-generation.json)

## Actual evaluation results

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded sample | recorded model | valid_rate | 1 |
| recorded sample | recorded model | exact_rate | 0 |
| recorded sample | recorded model | examples | 4 |

Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.

## Model and method

Reuse the authors' encode_spectra, canonical/unique_candidates and rerank_candidates utilities. Generation defaults to beam 10 and maximum length 300, removes invalid/duplicate canonical structures, and reranks up to 10 candidates by ITM positive-class probability. No molecular formula is supplied and no nearest-neighbor cache is used.

Retrieval reports both directions with the candidate-pool size and deterministic tie policy. Generation reports canonical top-1/3/5/10, validity across raw beams and reranked top-k separately. Reranking uses an explicit candidate list.

## Reproduce

[Notebook with executed figures](../notebooks/vibrational-generation.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks vibrational.generation --limit 8 --output results/vibrational-generation-new.json
```

## Limits and provenance

Checkpoint pairs must share their H/C reference and normalization buffers. Small candidate pools can inflate retrieval numbers; publish the sample IDs, seed and source composition with every score.

- [smoke_vib2mol_20261115.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/smoke_vib2mol_20261115.json) — SHA-256 `2d847121c398071c68040623482a51118d1e20932779247b2eb72e071b8a8ae4`

[Original model / 原模型](https://github.com/X1nyuLu/openSpec-alpha) · [Model review / 模型检查](../model-audit.md)
