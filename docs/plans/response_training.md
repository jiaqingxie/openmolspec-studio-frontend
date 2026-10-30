# Direct IR/Raman response training

The `structure2response` task trains `dedipole` and `depolar` independently
using the shared Cartesian tensor loss, DDP, checkpoint and TensorBoard lifecycle.
The 200k presets use r5, depth 4, C128, lmax=4/mmax=2, 312,500 optimizer steps and global
batch 128 (64 per GPU, two GPUs), matching the Hessian starting recipe.

Labels come from the frozen frequency payload, using exactly the existing
200k KS split. Missing or invalid labels fail export instead of dropping IDs.
The payload parser has already converted dipole derivatives to Debye/Angstrom
and polarizability derivatives to Bohr^3/Angstrom; export applies no additional
conversion, scalar centering, mass weighting or frequency scaling.
Axes are `(atom, coordinate, dipole)` and
`(atom, coordinate, polarization, polarization)` respectively. The last two
depolar axes are symmetric. Full Cartesian component MAE/RMSE are reported;
these are response errors, not IR/Raman spectral errors.

The response node heads use SO(3) features and CartesianTensor bases (`ij`,
`ijk=ikj`). Depolar uses two spherical channels to represent both l=1 copies
in its 18-dimensional symmetric Cartesian tensor space, plus l=2 and l=3.
It requires lmax >= 3. The implementation shares the direct tensor backbone
with Hessian training and does not import Harmony.

## Export and smoke test

From the repository root, export both labels once:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
python -m benchmarks.data.prepare_response \
  --split-file builds/openmolspec-20260830/release-v1/splits/scaling/align_ks_200k.parquet \
  --output benchmark_data/release_v1_ks200k_response_r5 \
  --cutoff 5.0
```

Expected counts: 200,000 train, 10,390 eval, 20,390 test. Existing LMDBs are
never overwritten. To test export alone, use a different output directory and
append `--limit-per-split 4`; point a temporary YAML at that directory for
training on the exported subset. Do not use a subset export as formal data.

After full export, run one debug epoch for each target (512 train and 128
validation/test samples, no retained checkpoints or TensorBoard events):

```bash
CUDA_VISIBLE_DEVICES=0,1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
python -m benchmarks run \
  --config benchmarks/configs/structure2response/dedipole_ks200k_r5.yaml --debug

CUDA_VISIBLE_DEVICES=0,1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
python -m benchmarks run \
  --config benchmarks/configs/structure2response/depolar_ks200k_r5.yaml --debug
```

## Full training

Remove `--debug` from each command above to train for 312,500 optimizer steps. Each run
selects its checkpoint by validation MAE, restores it, then reports test
MAE/RMSE automatically. No additional torchrun wrapper is needed.

Outputs live under
`runs/openmolspec-v1-ks200k/structure2response/equiformer-v3/<target>-direct-r5/seed-624/<timestamp>/`:

- `train.log`
- `artifacts/equiformer_v3_structure2response_best.pt`
- `artifacts/results_structure2response.json`
- `artifacts/tensorboard/`

This implements response training and component evaluation. A joint
Hi/Hij/dedipole/depolar spectrum renderer is a separate next step.

## Response performance repair (2026-09-16)

Response forwards previously reconstructed `CartesianTensor`, invoking e3nn
reduced-tensor-product code generation on every batch, including evaluation.
Following Harmony, tensor layouts and change-of-basis buffers are now prepared
once at initialization. Tensor axes, units, loss, learned parameters and the
step-based schedule are unchanged; existing model state dictionaries remain
compatible. The existing response LMDBs do not need rebuilding.

The shared tensor trainer now uses persistent workers when workers > 0 and
pinned memory for CUDA with non-blocking transfers. Persistent validation/test
workers remain alive as well, so monitor host RAM when running multiple jobs.
New best checkpoints include optimizer/scheduler states; this is not an
automatic or exact-resume implementation. Old checkpoints lack those states.
Restart in a new timestamped run for the corrected experiment; existing runs
are not deleted. Removing repeated code generation fixes a confirmed overhead,
but sustained GPU throughput must still be checked on the training VPS.

## Validation performed

The 200k split plus held-out sets contains 230,780 records; both derivative
fields have present flags for every record. The exporter also checks shapes,
finite values and polarizability symmetry when reading values. A real-payload
smoke export of four records per split completed, followed by separate
one-epoch CPU/Gloo two-rank runs for both targets using a small depth-1/C16/
lmax-3 backbone. Both runs completed train/validation/test, saved and restored
checkpoints, and produced exactly one TensorBoard event file each.
All 94 repository unit tests passed, including response rotation covariance,
gradient propagation, tensor symmetry, label preservation and CLI parsing.
This validates the implementation, not convergence or GPU memory requirements
of the full 200k presets.
