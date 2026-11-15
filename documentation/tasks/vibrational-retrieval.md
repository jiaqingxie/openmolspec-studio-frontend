# Vib2Mol bidirectional retrieval with IR/Raman only

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

Metric fields: `recall_at_1`, `recall_at_5`, `recall_at_10`, `mrr`. Domain: `computed`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks vibrational.retrieval --limit 8 --output results/vibrational-retrieval.json
```

## Interpretation and limits

Checkpoint pairs must share their H/C reference and normalization buffers. Small candidate pools can inflate retrieval numbers; publish the sample IDs, seed and source composition with every score.

## Recorded results

```json
[
  {
    "status": "not_evaluated",
    "reason": "已有 Vib2Mol checkpoint 直接编码本次选中样本；提供 IR+Raman，不提供 H/C。"
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/vibrational-retrieval.ipynb)

## Source

[Original implementation / release](https://github.com/X1nyuLu/openSpec-alpha)
