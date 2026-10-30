# Min–max training datasets and clean restart

Each IR and Raman spectrum independently uses `(x-min)/(max-min)` across
the full 1024-point 400–4000 cm^-1 grid. No percentile clipping is applied.
Absolute intensity is removed; peak heights relative to baseline are preserved.
Train/eval/test use identical per-record rules, without fitting split statistics.
Constant spectra become zeros and are counted. Invalid spectra fail the export
without dropping records. Spectra are converted to float32 before computing
min/max; arithmetic and normalized storage are float32 throughout. Raw inputs
and property labels are unchanged. If conversion collapses a tiny signal on a
large baseline to a constant, the existing zero-spectrum policy applies.

Raw LMDBs remain read-only. New roots preserve keys, split membership, SMILES,
scalar labels and units. Per-record bounds are in `spectrum_normalization`.
`normalization.json` contains the method, source record hashes, counts and
completion state. Split parquet files are copied unchanged; source summaries
are preserved as `source_summary.json`.

## Export

```bash
python -m benchmarks.data.normalize_spectra \
  --data-dir benchmark_data/spectrum_properties_ks200k \
  --format vib2conf \
  --output benchmark_data/spectrum_properties_ks200k_minmax

python -m benchmarks.data.normalize_spectra \
  --data-dir benchmark_data/release_v1 \
  --format vib2mol \
  --output benchmark_data/release_v1_minmax
```

Export streams records with progress bars. LMDB map size is automatic (four
times source size, at least 1 GiB), not a RAM allocation. Normalized spectra are
stored as float32 regardless of source dtype. Existing output directories, overlapping
paths and already-normalized inputs are refused. Failed partial output remains
marked failed. Only train once normalization.json reports completed.

## Fresh training

Canonical spectral-task YAMLs now point to _minmax roots and use -minmax
experiment variants. Obsolete robust-minmax copies and the generic multi-target
vib2conf.yaml were removed. Hessian and other task configs are unchanged.
Four-card Matching now uses batch 64 per GPU (global 256) instead of the
OOM-prone 256. Other loss/learning-rate settings are unchanged.

```bash
python -m benchmarks run \
  --config benchmarks/configs/spectrum2property/dipole_total_ks200k.yaml --debug

CUDA_VISIBLE_DEVICES=0,1 OMP_NUM_THREADS=1 python -m benchmarks run \
  --config benchmarks/configs/spectrum2structure/vib2mol_smoke_ddp2.yaml

# Formal training after smoke passes; do not resume raw-spectrum checkpoints.
python -m benchmarks run \
  --config benchmarks/configs/spectrum2property/dipole_total_ks200k.yaml

CUDA_VISIBLE_DEVICES=0,1,2,3 OMP_NUM_THREADS=1 python -m benchmarks run \
  --config benchmarks/configs/spectrum2structure/vib2mol.yaml
```

Historical spectrum2property and spectrum2structure run directories were moved
out of runs/ into artifacts/retired-spectrum-runs-20260911/ for recoverable
retirement, including logs, checkpoints and TensorBoard events. Hessian runs,
other task runs and original LMDBs were not changed. This does not reclaim disk
space; the archive can be restored if needed.

Tests: `python -m unittest discover -s tests -p test_spectrum_normalization.py -v`.

## Export performance

The optimized exporter defaults to `--batch-size 256 --commit-interval 8192`
and sequential-read readahead (`--no-readahead` disables it). Batch size is
export records, unrelated to model training batch size. Conversion is vectorized
and LMDB uses ordered bulk inserts; source checksums and durable commits remain
enabled. No worker processes or unsafe asynchronous durability options are used.
Memory is bounded by the batch and current transaction, not dataset size.
Each split reports read/transform/hash/write-commit timings in normalization.json.
The cursor/hash definition and normalized values are unchanged from the scalar
implementation; regression tests cover partial batches and commit boundaries.

A 2048-record synthetic, in-memory conversion check measured approximately
0.129 s scalar versus 0.091 s batched (1.43x). This excludes disk IO and is not
an estimate of end-to-end speedup on shared storage. Commit frequency drops
16-fold relative to the original 512-record normalization transactions.

Earlier builders were audited separately: `prepare._write_lmdb` already commits
every 10,000 records, so it does not share that frequent-commit issue. Its
serialization and insertion remain scalar. `prepare.py` parallelizes RDKit
identity creation but not all export work. Spectrum-property/Hessian/response
payload builders are sequential, loading fields per shard to avoid repeated
small compressed reads; each split can revisit the same shards. Those are
different potential bottlenecks, not evidence that they need rebuilding.
Hessian construction code and existing artifacts were not changed.

Running processes continue using their already-loaded code. Do not launch a
second exporter against the same output, and do not rename/delete a directory
while it is being written. An interrupted output is not resumable: use a new
root (then update the training data path) or inspect/retire the partial output
after the original process has stopped.
