# Vib2Mol candidate reranking with H/C

Use Xinyu's saved Vib2Mol models for spectral structure elucidation. The complete input is IR + Raman + H/C; the IR/Raman-only route is a missing-NMR ablation.

## Model and protocol

Reuse the authors' encode_spectra, canonical/unique_candidates and rerank_candidates utilities. Generation defaults to beam 10 and maximum length 300, removes invalid/duplicate canonical structures, and reranks up to 10 candidates by ITM positive-class probability. No molecular formula is supplied and no nearest-neighbor cache is used.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "ir": "1024 min-max-normalized intensities",
  "raman": "1024 min-max-normalized intensities",
  "wavenumber_cm1": [
    400,
    4000
  ],
  "nmr_h_shifts_ppm": [
    1.2,
    3.65
  ],
  "nmr_c_shifts_ppm": [
    18.2,
    58.3
  ],
  "nmr_reference_id": "must match checkpoint",
  "formula": "not supplied to Vib2Mol"
}
```

## Outputs and metrics

Retrieval reports both directions with the candidate-pool size and deterministic tie policy. Generation reports canonical top-1/3/5/10, validity across raw beams and reranked top-k separately. Reranking uses an explicit candidate list.

Metric fields: `top_1_hit_rate`, `mrr`. Domain: `computed`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks spectroscopy.reranking.hc --limit 8 --output results/spectroscopy-reranking-hc.json
```

## Interpretation and limits

Checkpoint pairs must share their H/C reference and normalization buffers. Small candidate pools can inflate retrieval numbers; publish the sample IDs, seed and source composition with every score.

## Recorded results

```json
[
  {
    "task": "spectroscopy.reranking.hc",
    "dataset_name": null,
    "status": "passed",
    "metrics": {
      "recall_at_1": 1.0,
      "recall_at_5": 1.0,
      "recall_at_10": 1.0,
      "mrr": 1.0,
      "queries": 64,
      "candidate_pool": 64,
      "unique_candidates": 64,
      "tie_policy": "stable_candidate_order",
      "top_1_hit_rate": 1.0
    },
    "given_nmr": true,
    "source_counts": {
      "ZINCV2": 28,
      "SDBS": 2,
      "PCQM4MV2": 11,
      "WILEYIR": 1,
      "ZINCV1": 7,
      "RXN": 5,
      "NISTIR": 1,
      "QM9": 9
    },
    "selection": {
      "read": 20390,
      "duplicate_structure": 3662,
      "eligible_distinct_structures": 16728,
      "selected": 64
    },
    "sampling": "reservoir",
    "seed": 42,
    "source_file": "vib2mol_xinyu_random64_20261116.json",
    "sample_limit": 64
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/spectroscopy-reranking-hc.ipynb)

## Source

[Original implementation / release](https://github.com/X1nyuLu/openSpec-alpha)
