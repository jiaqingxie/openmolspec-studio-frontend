# IR/Raman → four scalar properties

> Superseded preparation/scaling plan: use [200k/1M with H/C NMR](benchmark_200k_1m_nmr.md).
> The active property YAMLs now use `_hc_nmr_minmax` datasets. 400k/600k/800k
> configs have moved to `docs/archives/benchmark-configs/`. The older commands
> below are retained for provenance, not the current execution plan.

Each experiment trains one Vib2Conf spectral encoder and one regression head.
No geometry, molecular formula, SMILES or other property labels enter the model.
The default input is paired IR + Raman (400–4000 cm⁻¹, 1024 points per spectrum).
For ablations set `task.modality` to `ir` or `raman` and change the experiment
variant accordingly. All three modes use the same prepared molecules.

| Property | YAML target | Label / metric unit |
|---|---|---|
| Dipole magnitude | dipole_total | Debye |
| Isotropic polarizability | polar_iso | Å³ |
| Polarizability anisotropy | polar_anisotropy | Å³ |
| HOMO–LUMO gap | gap | eV |

The dipole magnitude is the parsed Gaussian `Tot`; gap is LUMO minus HOMO,
not an optical gap. The static polarizability tensor gives
`polar_iso = trace(alpha)/3` and
`polar_anisotropy = sqrt(3/2 * sum((alpha - polar_iso I)**2))`.
For a symmetric tensor both are rotation invariant. Anisotropy is the square
root, not its square. Archive six-component order is xx,xy,yy,xz,yz,zz.
Only the benchmark copy is converted: polar scalars are multiplied by
`0.529177210903³` and the gap by `27.211386245988`. Dipole stays in Debye (D).
Every LMDB record carries unit metadata; incompatible/untagged old LMDBs are
rejected with a rebuild instruction, preventing silent unit mixing. Training
results also record target units. MAE/RMSE use these units; R² is dimensionless.

## Prepare once

```bash
python -m benchmarks.data.prepare_spectrum_properties \
  --split-file builds/openmolspec-20260830/release-v1/splits/scaling/align_ks_200k.parquet \
  --output benchmark_data/spectrum_properties_ks200k
```

Reads frozen frequency HDF5 shards, without loading the full pickle or building
radius graphs. Keeps only records with finite spectra and all four labels,
so comparisons share one cohort. It does not change scaffold assignments.
`benchmark_split.parquet` retains source_dataset and inchikey;
`excluded.parquet` records rejected IDs and reasons; `summary.json` records
actual sizes and units. Counts can be below the nominal split sizes. A finite
label check is not a full scientific QC audit. Existing LMDB files are never
overwritten. Old prepared LMDBs need rebuilding to contain polar targets.

## Run

```bash
python -m benchmarks run --config benchmarks/configs/spectrum2property/dipole_total_ks200k.yaml --debug
python -m benchmarks run --config benchmarks/configs/spectrum2property/dipole_total_ks200k.yaml
python -m benchmarks run --config benchmarks/configs/spectrum2property/polar_iso_ks200k.yaml
python -m benchmarks run --config benchmarks/configs/spectrum2property/polar_anisotropy_ks200k.yaml
python -m benchmarks run --config benchmarks/configs/spectrum2property/gap_ks200k.yaml
```

Run sequentially on one GPU; this adapter does not yet implement DDP. Initial
configs use AdamW, LR 5e-5, cosine scheduling per optimizer step, 312,500 steps,
validation every 2,500 steps, batch size 128. This matches the Hessian update
budget, validation cadence and global batch (64 per GPU × 2 GPUs). At KS200k,
drop-last gives 1,562 batches per traversal, so this is about 200.064 epochs
and 40 million sample presentations. The learning-rate magnitude remains
task-specific; equal steps do not imply equal FLOPs or wall time.
For scaling, change the official KS split, preparation
output, YAML data root and release identifier; keep step budget and batch size
fixed. The four tasks have separate checkpoints and timestamp+hash run paths.

Targets are standardized using training labels only (cached outside debug).
The loss is SmoothL1 (`training.loss: smooth_l1`, `loss_beta: 1.0`) on the
standardized residual r: `0.5*r²/beta` for `|r| < beta`, otherwise
`|r| - 0.5*beta`. With beta=1 this is the Huber loss with threshold 1.
Thus the transition is one training standard deviation in physical units,
not 1 D / Å³ / eV. Each property's full training set, including the final
partial batch, fits the normalizer; validation and test never fit it.
No clipping or log transform is applied. Old partial-batch normalizer caches
are invalidated by a preprocessing tag.
MAE, RMSE and R² use restored physical units; test is evaluated on the best
validation checkpoint. TensorBoard logs scalar metrics under each run's artifacts.
The preparation output retains released intensities (Raman float64). Current
training YAMLs use a separate `_minmax` dataset produced by
`benchmarks.data.normalize_spectra`: ordinary per-record, per-modality min–max
normalization, computed and stored in float32 by the current exporter. Original
LMDBs are not modified. Previously built float64 normalized copies remain valid
because the model loader casts spectra to float32.
Debug uses small subsets and no persistent run artifacts via the YAML runner.

## Dipole scaling: 200K to 1M

The existing official KS subsets are nested; all sizes share exactly 10,390
validation and 20,390 test sample IDs. The 1M setting uses `align_split.parquet`,
not a nonexistent `align_ks_1000k.parquet`. Reuse the completed 200K baseline.
New presets are `dipole_total_ks{400,600,800,1000}k.yaml` in
`benchmarks/configs/spectrum2property/`.

Build additional datasets from the repository root (CPU; no training is started):

```bash
set -euo pipefail
for size in 400 600 800 1000; do
  split_file="builds/openmolspec-20260830/release-v1/splits/scaling/align_ks_${size}k.parquet"
  if [ "$size" = 1000 ]; then
    split_file="builds/openmolspec-20260830/release-v1/splits/align_split.parquet"
  fi
  python -m benchmarks.data.prepare_spectrum_properties \
    --split-file "$split_file" \
    --output "benchmark_data/spectrum_properties_ks${size}k"
  python -m benchmarks.data.normalize_spectra \
    --data-dir "benchmark_data/spectrum_properties_ks${size}k" \
    --format vib2conf \
    --output "benchmark_data/spectrum_properties_ks${size}k_minmax"
done
```

Both commands refuse to overwrite existing datasets; inspect incomplete outputs
before retrying. Inspect each `summary.json` and `normalization.json`: actual
counts can decrease if invalid records are rejected. Compare accepted sample IDs
in `benchmark_split.parquet` across sizes before reporting a scaling benchmark.
Files are under `<output>/vib2conf/{train,eval,test}.lmdb`.
Each prepared dataset contains all four property labels, so it can also serve
the gap and polarizability experiments without another data export.

Train sequentially on one GPU:

```bash
for size in 400 600 800 1000; do
  CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 python -m benchmarks run \
    --config "benchmarks/configs/spectrum2property/dipole_total_ks${size}k.yaml" || break
done
```

All presets keep the 200K model and optimizer settings, batch size 128 and
312,500 updates (40M sample presentations). Approximate dataset traversals are
200, 100, 66.7, 50 and 40 respectively. This is fixed-update scaling, not
training each size to convergence. Target mean/std are fitted separately using
each training subset only. Compare MAE in D; z-score training losses have
different scales when the subset statistics differ.

## Training-label range audit (KS200k)

Run `python -m benchmarks.data.profile_property_targets` to reproduce the
training-only audit. Results go to `reports/benchmark/spectrum_property_ranges_ks200k/`.
All 200,000 training candidates have finite labels; this audit does not reload
spectra or replace preparation QC. Statistics below use the requested benchmark units.

| Target | Min | Median | P99 | Max | Mean ± std |
|---|---:|---:|---:|---:|---:|
| Dipole (D) | 0 | 3.404 | 10.023 | 41.407 | 3.665 ± 2.127 |
| Isotropic polarizability (Å³) | 1.080 | 21.846 | 44.464 | 175.106 | 21.733 ± 6.685 |
| Anisotropy (Å³) | 0.000783 | 9.068 | 31.723 | 314.602 | 10.210 ± 6.349 |
| Gap (eV) | 0.296 | 5.689 | 7.475 | 10.691 | 5.632 ± 0.921 |

Recommendation: retain z-score scaling for all four tasks and use SmoothL1
to reduce sensitivity to the long tails. Values outside mean ±5 std account
for 0.486%, 0.309%, 0.304%, and 0.017%, respectively; those are not automatically
invalid labels. Log transforms may be tested on validation later, particularly
for anisotropy, but change emphasis toward relative error. Do not choose
transforms or thresholds using test performance. Refit training statistics for
each scaling subset instead of hardcoding this table.
