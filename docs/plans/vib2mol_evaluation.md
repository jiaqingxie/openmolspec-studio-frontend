# ks200k Vib2Mol evaluation

Use the validation-selected matching and generation checkpoints, not test-selected
weights. Both encoders receive IR, Raman and unassigned H/C NMR. No formula
constraint is added. One GPU is sufficient; this evaluation is not DDP.

Generation uses incremental decoder KV caching adapted from `../vib2mol-v1`:
self-attention K/V grow by one token, cross-attention K/V are projected once,
and beam parent selection reorders every layer's cache. The adapter changes no
parameters, token IDs, training path, or checkpoint keys. Tests compare every
incremental logit plus greedy/beam sequences and scores against the uncached
path. Plain IR/Raman Vib2Mol and the H/C model both use the cached path.
The legacy plain beam loop could emit `max_length + 1` tokens; the reference
cached loop also corrects that boundary, while the H/C cached and uncached
paths are exactly equivalent under their already-correct length boundary.

From the repository root:

```bash
VIB_RUN=runs/openmolspec-v1-ks200k/spectrum2structure/vib2mol/ir-raman-hc-generation-v1/seed-624/2026-09-14-09-23-b1913a/artifacts/vib2mol
MATCH_CKPT="$VIB_RUN/checkpoints/openspec/ir-raman-kekule_smiles/vib2mol/2026-09-14-09-23-a25dba/best_recall.pth"
GEN_CKPT="$VIB_RUN/checkpoints/openspec/ir-raman-kekule_smiles/vib2mol/2026-09-14-23-29-9e2cae/best_acc.pth"
```

Retrieval over the complete 20,390-record test candidate pool, followed by ITM
reranking of the top 50 candidates per spectrum:

```bash
CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 python -m benchmarks.models.vib2mol.workflow retrieval-eval \
  --data-dir benchmark_data/release_v1_ks200k_hc_nmr_minmax \
  --modality ir-raman-nmr --checkpoint "$MATCH_CKPT" \
  --rerank --rank-checkpoint "$MATCH_CKPT" --topk 50 \
  --batch-size 32 --rerank-batch-size 32 --device cuda:0
```

Generation with beam size 10 and ITM reranking:

```bash
CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 python -m benchmarks.models.vib2mol.workflow generation-eval \
  --data-dir benchmark_data/release_v1_ks200k_hc_nmr_minmax \
  --modality ir-raman-nmr --checkpoint "$GEN_CKPT" \
  --rerank --rank-checkpoint "$MATCH_CKPT" --topk 10 \
  --beam-size 10 --batch-size 8 --rerank-batch-size 32 --max-length 300 --device cuda:0
```

Each command creates a new timestamped workspace under `runs/vib2mol/` and
writes `test_metrics.json`, `workflow_summary.json`, and per-query JSONL
predictions. Use `--debug --debug-train-samples 2 --debug-eval-samples 2
--debug-test-samples 2` for a temporary two-record smoke test, not a benchmark.

Retrieval reports Recall@1/3/5/10 by paired record index, retaining the exact
LMDB dataset order for both encodings and candidates. Reverse retrieval is
not reranked. Generation reports canonical molecule top-k before and after
reranking; invalid candidates are removed and canonical duplicates collapsed
in beam order. Validity is computed on raw beams before filtering. Candidates
beyond `--topk` retain their original order. Ground truth comes directly from
LMDB rather than decoded target tokens. Reranking uses ITM positive probability,
not the positive logit or a sum with cosine similarity.

## Tokenizer audit (2026-09-16)

The pinned vocabulary has 181 entries and a 300-token limit. Full audit:

| Split | Records | Unknown tokens | Round-trip mismatches | Over 300 tokens | Maximum tokens |
|---|---:|---:|---:|---:|---:|
| Train | 200,000 | 0 | 0 | 0 | 236 |
| Validation | 10,390 | 0 | 0 | 0 | 142 |
| Test | 20,390 | 0 | 0 | 0 | 120 |

`C13` encodes as `C`, `1`, `3`: ring closure labels, not carbon-13.
`C%13` denotes ring label 13, while `[13CH4]` represents an isotope-bearing
atom. All three are round-trip safe. An isolated `C13` is only a fragment,
not a complete ring-closed molecule.

The tokenizer silently drops `@`, `/`, and `\\` stereo markers. The current
dataset contains none because `benchmarks/data/prepare.py` exports Kekule
SMILES with `isomericSmiles=False`. Thus these experiments do **not** measure
stereochemical reconstruction (nor guarantee isotope identity retained by
that export). This audit validates tokenization of exported targets, not
identity preservation from the original molecular records. Changing the
vocabulary or target identity policy would require a versioned dataset and
compatible retraining; neither has been changed here.

Reproduce the audit:

```bash
TOKENIZERS_PARALLELISM=false python -m benchmarks.models.vib2mol.audit_tokenizer \
  --data-dir benchmark_data/release_v1_ks200k_hc_nmr_minmax \
  --output reports/benchmark/vib2mol_ks200k/tokenizer_audit.json
```
