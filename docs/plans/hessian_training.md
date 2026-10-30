# Direct Hessian training

## Step-aligned scaling runs

Current Hessian and response presets use `training.max_steps: 312500` and
`training.eval_every_steps: 2500` instead of `epochs`. AdamW starts at 3e-4;
cosine scheduling advances after every optimizer update, with no warmup and
eta_min=0. Each update uses the learning rate before that scheduler step.
All scales therefore have 125 validation opportunities, including the final
step. Training batches are full-sized (incomplete epoch tails are dropped),
and samplers reshuffle each traversal. With two GPUs and batch_size=64, the
global batch is 128 and the budget is 40 million sample presentations.

TensorBoard training and validation use global_step as the horizontal axis.
Learning rate is logged every 100 updates (also first and last); train loss
is averaged over the validation interval across ranks. Final test metrics
appear as single scalar points under test/<metric> at the best checkpoint step.
Existing event files are not rewritten. Debug caps the step budget at one
pass through the debug subset and retains no training artifacts. Checkpoints
remain best-model snapshots, not full optimizer-resume states. Historical
epoch-based configurations remain readable for reproducibility.

## Joint held-out physical evaluation

`python -m benchmarks.evaluate_hessian` loads two standalone best checkpoints
using each run's frozen `resolved_config.yaml`, not the current training YAML.
It evaluates only the prepared test split, verifies IDs/geometry/Hessian labels
against the original release, and uses full untruncated reference Hessians.

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m benchmarks.evaluate_hessian \
  --hi-run runs/openmolspec-v1-ks200k/structure2hessian/equiformer-v3/hi-direct-r8/seed-624/2026-09-07-12-04-74449d \
  --hij-run runs/openmolspec-v1-ks200k/structure2hessian/equiformer-v3/hij-direct-r8/seed-624/2026-09-07-12-04-dfc2f7 \
  --data-dir benchmark_data/release_v1_ks200k_hessian_r8 \
  --output reports/benchmark/joint_hessian_r8_test \
  --device cuda:0
```

For a smoke run use `--limit 10` and a different output directory. Output paths
must not exist. Inference is single-GPU, one molecule at a time; float64 physical
diagnostics run on CPU. No DDP or retraining is needed. `--payload` can relocate
the full frequency HDF5 directory when the original machine path is unavailable.

Outputs: `per_molecule.parquet`, `frequencies.parquet`, `summary.json`.
Three cases are reported: full reference, cutoff reference, assembled prediction.
Raw and symmetrized matrix errors are separate. Symmetry, translation and rotation
residuals are measured before correction; rigid mass-weighted residual is measured
after symmetrization. Rotation nullity is only expected at stationary geometries,
so compare against the reference, not an unconditional pass/fail threshold.
Signed frequencies use an SVD rigid-subspace projection (5 rigid modes for linear
molecules, 6 for nonlinear), following Harmony's physical_validation/hessian_utils.py.
No PSD clipping, acoustic sum rule repair or empirical frequency scaling is applied.
Imaginary counts use frequency < -20 cm^-1 by default; configurable via
`--imaginary-threshold`. Excess counts are count differences, not mode matching.
Frequency errors compare sorted internal modes, not overlap-matched normal modes.
Standard ASE elemental masses are used (not isotope-specific Gaussian masses).
Summary averages weight molecules equally and differ from training's component-
weighted MAE. These diagnostics do not evaluate rotation covariance of model
predictions or IR/Raman intensities; those require additional inference/derivatives.

This task follows Harmony's `models/equiformerV3.py` Hi/Hij heads and
`pred_spectrum.py::assemble_cartesian_hessian` (reference checkout HEAD
`a3c9d47`, inspected 2026-09-05). OpenMolSpec uses its pinned EquiformerV3
backbone and an owned edge-output adapter; training does not import Harmony.

- `Hi`: symmetric 3×3 diagonal blocks, one per atom, equivariant FFN head.
- `Hij`: general 3×3 off-diagonal blocks, one per directed radius edge.
  The edge head projects messages before summing over destination nodes,
  matching Harmony's `return_edge_message=True` branch.
- Graphs include all directed pairs at distance strictly less than 5 Å,
  without self edges or a neighbor-count cap, sorted by destination.
  Stored edge order is used for both labels and message passing.
- Cartesian SmoothL1 loss, mean over block components, independent Hi/Hij
  experiments. Unlike Harmony's default irreps loss, this explicitly uses
  its supported Cartesian loss route. No energy derivatives are computed.
- Gaussian archive coordinates and Hessians retain their common atom order
  and frame. Export converts Hartree/Bohr² to eV/Å² (factor ~97.1736243).
  There is no mass weighting, frequency scaling, or scalar mean subtraction.
- Hessian YAML presets use lmax=4/mmax=2, C128/depth4, 200 epochs,
  batch size 64 per GPU on two GPUs (global batch 128).
  This is a starting configuration, not a reproduction of published scores.

## Prepare the 200k experiment

### Single-node DDP

Hessian training supports `training.gpus: 2` (or another local GPU count).
`python -m benchmarks run` launches `torch.distributed.run` automatically;
do not wrap the outer benchmark command in torchrun. For example:

```bash
CUDA_VISIBLE_DEVICES=0,1 python -m benchmarks run \
  --config benchmarks/configs/structure2hessian/Hi_ks200k_r5_ddp2.yaml
```

Append `--debug` for an ephemeral multi-process smoke run. Debug retains the
Hessian GPU count, disables DataLoader workers, and does not retain artifacts.
Batch size and workers are **per rank**: batch 64 on two GPUs means global batch
128. CUDA ranks use LOCAL_RANK/NCCL; CPU smoke tests use Gloo. Data needs no rebuild.
The automatic launcher supports one node, not multi-node scheduling.

Following Harmony's DDP initialization and epoch sampler pattern, training
shuffles DistributedSampler each epoch. It drops at most world_size-1 samples
per epoch instead of padding duplicates. Validation/test use non-padding
partitions, reducing absolute/squared error sums and component counts globally.
Training loss is weighted by the global number of tensor components per step.
Only rank zero prints progress and writes checkpoints/results; checkpoints store
the unwrapped model for single-GPU compatibility. Other Equiformer task families
remain single-GPU. Existing checkpoints are best-model weights, not full optimizer
resume states: switching a running experiment to DDP does not resume its optimizer.

### Export

Run once from the repository root. The existing dipole LMDB contains no
Hessian, so this creates a separate dataset from release frequency shards.

```bash
python -m benchmarks.data.prepare_hessian \
  --split-file builds/openmolspec-20260830/release-v1/splits/scaling/align_ks_200k.parquet \
  --output benchmark_data/release_v1_ks200k_hessian
```

The exporter retains the official split IDs and source/InChIKey metadata.
Expected counts follow that split (200,000 train, 10,390 eval, 20,390 test).
It fails on missing or invalid labels instead of silently changing the split.
`benchmark_split.parquet`, `summary.json`, and `hessian_coverage.parquet`
record provenance and the Frobenius norm fraction excluded by the cutoff.
Files are read one shard at a time; memory use is bounded by a shard plus
the split index. LMDB map size defaults internally to 200 GiB of address
space; actual disk usage grows with records, not the map limit.
Existing LMDB outputs are not overwritten. A failed export must use a fresh
output directory or have its incomplete outputs inspected before removal.

## Train

First run a debug experiment on the prepared data (one epoch, no retained
run artifacts):

```bash
python -m benchmarks run \
  --config benchmarks/configs/structure2hessian/Hi_ks200k.yaml --debug
python -m benchmarks run \
  --config benchmarks/configs/structure2hessian/Hij_ks200k.yaml --debug
```

Then launch the two experiments sequentially on the same GPU:

```bash
python -m benchmarks run \
  --config benchmarks/configs/structure2hessian/Hi_ks200k.yaml
python -m benchmarks run \
  --config benchmarks/configs/structure2hessian/Hij_ks200k.yaml
```

Run directories use automatic timestamp + random suffix names. Checkpoints
and test/validation MAE and RMSE are written under each run. Metrics are in
eV/Å² and averaged over tensor components, not averaged equally per molecule.
The tensor task does not fit the scalar target normalizer.

For an export smoke test, use a separate output with `--limit-per-split 4`;
this intentionally changes counts and must not be used as a formal dataset.

## Interpretation

To assemble a Hessian, assign `H[dst, :, src, :] = Hij`, insert `Hi` on the
diagonal, reshape to `(3N, 3N)`, then take `(H + H.T) / 2` as Harmony does.
Do not symmetrize individual Hij blocks. Missing long-range blocks are zero:
this is a radius-truncated Hessian predictor, not an all-pairs dense model.
`hessian_coverage.parquet` measures this approximation separately from model
error. It does not impose positive semidefiniteness or translation sum rules.
The current training commands report block errors; frequency/stability
evaluation of a pair of checkpoints is a separate downstream calculation.
