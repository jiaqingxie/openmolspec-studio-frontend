# Hessian r5 data scaling

Run commands from the repository root. The series is 200k, 400k, 600k,
800k and 1M training molecules. Reuse the current 200k runs after they finish.
The existing KS subsets are nested within the full 1M aligned training split;
all five sizes share 10,390 validation and 20,390 test molecules.
The `ks1000k` configuration name denotes the full aligned training pool,
not a separately generated KS split file.

All presets retain seed 624, radius 5 Angstrom, depth 4, C128,
lmax=4/mmax=2, Cartesian SmoothL1, AdamW learning rate 3e-4,
weight decay 1e-4 and cosine decay over each run's configured epochs. Batch size is 64 per GPU
on two GPUs (global batch 128). Train Hi and Hij independently.
Epochs are adjusted to approximately match the optimizer-update budget of
200k at 200 epochs. With two ranks and batch 64 per rank, each epoch has
`ceil(train_size / 128)` updates (the final partial batch is retained).

| Training size | Epochs | Optimizer updates |
|---|---:|---:|
| 200k | 200 | 312,600 |
| 400k | 100 | 312,500 |
| 600k | 67 | 314,096 |
| 800k | 50 | 312,500 |
| 1M | 40 | 312,520 |

The 600k budget is about 0.48% larger because epochs must be integers.
Cosine decay reaches zero at the end of each configured run. This is an
approximately fixed-update comparison, not an exact GPU-hour budget:
molecular sizes and graph costs can vary. Record wall time and GPU-hours
as well as validation and test metrics. Existing processes retain their
startup configuration; these YAML edits apply to newly launched runs.

## Export the additional datasets

Each export contains both Hi and Hij labels and serves both training runs.
Run once; the exporter refuses to overwrite existing LMDBs. A failed export
needs an inspected/cleaned directory or a fresh output path (also update its
training YAML). No new KS selection is needed.

```bash
set -euo pipefail
for size in 400 600 800 1000; do
  split_file="builds/openmolspec-20260830/release-v1/splits/scaling/align_ks_${size}k.parquet"
  if [ "$size" = 1000 ]; then
    split_file="builds/openmolspec-20260830/release-v1/splits/align_split.parquet"
  fi
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m benchmarks.data.prepare_hessian \
    --payload builds/openmolspec-20260830/release-v1/payload/frequency \
    --split-file "$split_file" \
    --output "benchmark_data/release_v1_ks${size}k_hessian_r5" \
    --cutoff 5.0
done
```

## Inspect and launch

Inspect all commands without training (also works before exporting data):

```bash
set -euo pipefail
for size in 400 600 800 1000; do
  for target in Hi Hij; do
    python -m benchmarks run \
      --config "benchmarks/configs/structure2hessian/${target}_ks${size}k_r5.yaml" \
      --dry-run
  done
done
```

After the r5 200k evaluation, launch the following in a persistent shell or
inside a scheduler allocation with two GPUs. This runs eight jobs sequentially
on the same GPU pair; the launcher handles torchrun internally. Adjust visible
GPU IDs to the allocation. Install TensorBoard in a fresh training environment
with `python -m pip install -e '.[training]'` in addition to model dependencies.

```bash
set -euo pipefail
export CUDA_VISIBLE_DEVICES=0,1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
for size in 400 600 800 1000; do
  for target in Hi Hij; do
    python -m benchmarks run \
      --config "benchmarks/configs/structure2hessian/${target}_ks${size}k_r5.yaml"
  done
done
```

For a single job, for example:

```bash
CUDA_VISIBLE_DEVICES=0,1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
python -m benchmarks run \
  --config benchmarks/configs/structure2hessian/Hi_ks400k_r5.yaml
```

The launcher creates a fresh timestamped run each time; rerunning this loop
does not resume or skip finished training. If interrupted, start with the
remaining sizes/targets. Checkpoints contain best model weights, not full
optimizer resume state.

TensorBoard and text logs are stored under:

```text
runs/openmolspec-v1-ks<SIZE>k/structure2hessian/equiformer-v3/
  <hi|hij>-direct-r5/seed-624/<timestamp>/train.log
  <hi|hij>-direct-r5/seed-624/<timestamp>/artifacts/tensorboard/
```

```bash
tensorboard --logdir runs --port 6006
```

## Full Hessian and frequency evaluation

For each size, set the completed Hi/Hij run directories explicitly so that
evaluation uses the intended pair of best checkpoints. The following template
fails early until those paths are supplied. Choose a new report directory
if this evaluation has already been run.

```bash
size=400
: "${HI_RUN:?Set HI_RUN to the completed Hi run directory}"
: "${HIJ_RUN:?Set HIJ_RUN to the completed Hij run directory}"
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m benchmarks.evaluate_hessian \
  --hi-run "$HI_RUN" \
  --hij-run "$HIJ_RUN" \
  --data-dir "benchmark_data/release_v1_ks${size}k_hessian_r5" \
  --output "reports/benchmark/joint_hessian_ks${size}k_r5_test" \
  --device cuda:0
```

Use size=200, 600, 800 or 1000 with the corresponding checkpoint pair.
Report full-matrix MAE, frequency MAE, low-frequency bias, imaginary-mode
counts and the cutoff-reference baseline using the same aggregation as the
existing r8 evaluation. Select checkpoints on validation, not test metrics.
