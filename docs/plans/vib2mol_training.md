# Vib2Mol retrieval and generation smoke workflow

## Active scope (2026-09-14)

Use `vib2mol_ks200k.yaml` and `vib2mol_ks1000k.yaml` for the current size study.
The 400k/600k/800k configs are archived under `docs/archives/benchmark-configs/`.
Keep the existing IR+Raman Vib2Mol data and runs unchanged. The active baseline
now uses IR+Raman+H/C shifts; defer modality ablations until the 1M baseline completes.
See [H/C model and data](vib2mol_hc_nmr.md) and [current roadmap](benchmark_200k_1m_nmr.md).

## Fixed-step production training

The current `benchmarks/configs/spectrum2structure/vib2mol.yaml` uses:

```yaml
training:
  max_steps: 312500
  generation_max_steps: 312500
  eval_every_steps: 2500
  batch_size: 64
  generation_batch_size: 64
  learning_rate: 1.0e-4
  generation_learning_rate: 1.0e-4
  gpus: 4
```

Batch sizes are **per GPU**: matching global batch 256; generation global batch
256. Each stage starts its own optimizer, scheduler and step counter. Each batch
causes one optimizer update (no accumulation); DDP does not multiply the counter.
The pipeline therefore budgets 625,000 total optimizer updates across two stages.
On the 1M training set this is approximately 80 matching and 80 generation
traversals. Unlike equal steps, this does not match the global batch or compute
cost of the property benchmark (global batch 128).

Cosine LR is updated after every optimizer step, from the configured LR towards
zero over that stage's budget, without warmup. This matches the step scheduling
convention of the current property/Hessian trainers; LR magnitude remains
task-specific. Old `warmup_epochs`, `min_lr` and epoch scheduling from the pinned
upstream do not control step mode. Validation runs every 2,500 updates and at the
final update even when the budget is not divisible by the interval. Generation
token accuracy is computed at every validation, not every five epochs. Early
stopping is disabled in fixed-budget mode; validation still selects the best
model. Dataset samplers are reshuffled with `set_epoch` on every traversal.

Each stage writes `best_recall.pth` or `best_acc.pth` and
`training_summary.json` within its checkpoint directory. The summary includes
actual/best steps, selection score, interval and scheduler unit. Weights remain
state dictionaries with H/C normalization buffers and reference metadata; these
are not compatible with pre-NMR checkpoints or optimizer-resume snapshots.
The generation stage initializes from the best matching weights. TensorBoard's
training/validation and LR x-axes are optimizer steps. Generation accuracy remains
token accuracy, not molecular exact-match accuracy.

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
python -m benchmarks run \
  --config benchmarks/configs/spectrum2structure/vib2mol.yaml
```

For a two-GPU step-mode check, run
`benchmarks/configs/spectrum2structure/vib2mol_batch_probe_ddp2.yaml` instead.
All shipped smoke/probe presets also use steps. Debug caps each stage at one
traversal of its small training subset (or the requested budget if smaller),
always validates the final step and removes temporary artifacts on normal exit.
Legacy epoch CLI/YAML is retained for old experiments, but epochs and steps must
not be mixed. This change does not resume or alter already-running experiments.

The remaining epoch-based descriptions below document the legacy workflow.

The pipeline has two stages: `matching` trains retrieval/alignment; `spt`
trains the SMILES generator initialized from the validation-best matching
checkpoint. Retrieval/alignment losses and generation losses remain those of
the pinned upstream model, not the scalar property's SmoothL1 loss.

## Dependencies and data

The existing `benchmark_data/release_v1/vib2mol` contains 1,000,000 train,
10,390 validation and 20,390 test records. `demo_10k` does not currently have
a Vib2Mol export. Check the real dataset without changing links:

```bash
python -m benchmarks.models.vib2mol.workflow check-data --data-dir benchmark_data/release_v1
```

Checks inspect up to 32 records per split, not a full scientific QC audit.
The current execution environment lacks transformers; install the version
pinned in the upstream requirements if it is also missing on your training VPS:

```bash
python -m pip install 'transformers==4.44.2'
```

Do not reinstall the whole upstream requirements file over the working
Equiformer PyTorch environment: it pins different PyTorch/CUDA package versions.

## Two-stage smoke run

```bash
python -m benchmarks run --config benchmarks/configs/spectrum2structure/vib2mol_smoke.yaml
```

This YAML enables debug explicitly: train128 / validation64 / test64, one GPU,
matching batch16 for one epoch, then generation batch8 for one epoch. Debug
copies a deterministic prefix of each existing split to temporary LMDBs;
original datasets are not modified. Temporary checkpoints are needed for the
stage handoff but are removed together with logs and temporary datasets when
the debug run exits, including on failure. The test subset is only staged;
training uses train/validation, not a beam-search test evaluation.

To change the subset sizes edit `debug.*_samples`. To keep artifacts, create
a separate nondebug config; disabling debug on this smoke config trains on
the entire configured dataset, not the tiny prefix.

## Formal stages and evaluation

The existing `vib2mol.yaml` is a nondebug full pipeline. Each run now owns
an isolated `artifacts/vib2mol` workspace containing upstream checkpoints,
logs, TensorBoard `runs/` and `workflow_summary.json`. No shared upstream
dataset symlink is changed. The summary records exact stage checkpoint paths.
Stage handoff chooses the latest validation-improvement `*_recall*.pth`,
not the final unscored `epoch*.pth`; generation similarly reports its
validation-improvement `*_acc*.pth`. Upstream scheduling is still epoch-based.

YAML `model.stage` supports `matching`, `generation-train`, and `pipeline`.
For standalone generation set `model.base_checkpoint` to the matching path;
the adapter forwards it explicitly. For separate test evaluation:

```bash
python -m benchmarks.models.vib2mol.workflow retrieval-eval \
  --data-dir benchmark_data/release_v1 --checkpoint /absolute/path/to/matching.pth
python -m benchmarks.models.vib2mol.workflow generation-eval \
  --data-dir /path/to/current/export --checkpoint /absolute/path/to/generation.pth
```

Current release_v1 Vib2Mol records lack `formula`. Training without formula
works, but the upstream generation evaluation collator loads formula even when
formula conditioning is disabled. Export using the current
`benchmarks.data.prepare --formats vib2mol` before generation evaluation; the
adapter refuses missing/empty formulas rather than failing mid-evaluation.

Single-GPU and two-GPU smoke configurations are available. Debug validates
plumbing, not retrieval quality or generated-SMILES test accuracy.

## Global contrastive negatives

The maintained launcher replaces the upstream contrastive-loss method.
During DDP training it gathers normalized molecule and spectrum embeddings
with autograd support, computes local-anchor/global-key cross entropy in both
directions, and offsets positive labels by the preceding ranks' batch sizes.
Unequal local batch sizes are padded for communication and weighted so DDP
averaging matches a single global-batch objective. This is not detached gather.
ITM also uses local-anchor/global-candidate logits during DDP training. The
maintained `matching.py` exchanges molecular token embeddings, masks and
spectral hidden states; feature gathering preserves gradients back to the
owning rank. SMILES lengths and uneven local batches are padded for exchange.
The paired positive is excluded using its global index before softmax, then
one negative molecule and one negative spectrum are sampled per local pair.
Thus the matching classifier still evaluates one positive and two negatives
per sample, not every cross-card combination. Replicated validation stays local.
Only the paired row is masked; semantically equivalent molecules would need
additional identity-aware masking if non-unique training data were introduced.

Validation keeps local loss computation because upstream currently replicates
the complete validation set on each rank. Rank zero's validation metric drives
checkpoint selection and early stopping; its stopping state is broadcast to
every rank before deciding whether to leave the epoch loop.
The two-process regression test compares both loss and parameter gradients
against the single-process global-batch reference, including uneven 2+3 batches:

```bash
OMP_NUM_THREADS=1 python -m unittest discover -s tests -p test_vib2mol_contrastive.py -v
OMP_NUM_THREADS=1 python -m unittest discover -s tests -p test_vib2mol_matching.py -v
```

## DDP lifecycle

The maintained `lifecycle.py` adapter also replaces the matching/generation
training loops without editing ignored upstream files. Only rank zero prints
the best validation score (previously other ranks printed an uninitialized
`-inf`). Generation accuracy is evaluated every five epochs upstream, so only
those epochs update accuracy-based early stopping. Non-finite validation scores
are errors, not silently replaced. Loss logging detaches tensors, and the
launcher destroys the process group in `finally`, including on failure.

Two-process CPU tests cover synchronized plateau stopping, skipped accuracy
epochs and invalid scores; rerun the GPU smoke after updating:

```bash
OMP_NUM_THREADS=1 python -m unittest discover -s tests -p test_vib2mol_lifecycle.py -v
CUDA_VISIBLE_DEVICES=0,1 OMP_NUM_THREADS=1 python -m benchmarks run \
  --config benchmarks/configs/spectrum2structure/vib2mol_smoke_ddp2.yaml
```
