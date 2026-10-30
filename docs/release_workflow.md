# OpenMolSpec release workflow

The release builder turns the generated Gaussian-derived artifacts into a
versioned data product. It does not delete failed records or mutate source
pickles.

## Release contract

- Molecular identity is the full InChIKey. Stereoisomers and represented
  protonation states remain distinct.
- `catalog/full.parquet` contains one row per molecular identity and allows
  missing modalities.
- `catalog/align.parquet` is a subset of `full` for which frequency, IR,
  Raman and NMR all parsed successfully for the same `sample_id`.
- `catalog/records.parquet` retains every source record, including duplicates,
  conformers, parsing failures and quality flags.
- The official scaffold-disjoint split contains exactly 1,000,000 aligned
  training molecules, 10,390 validation molecules and 20,390 test molecules.
  Full InChIKeys and Bemis-Murcko scaffolds do not cross partitions.
- `full` and `align` use exactly the same validation/test molecules. Full-only
  molecules that share a held-out scaffold are marked `excluded`, while the
  remaining partial-modality molecules enlarge only `full` training.
- Record-level origin is stored as `source_dataset`/`source_id` in
  `catalog/records.parquet`. Molecule and split tables include
  `source_datasets`, modality-specific sources and `representative_source`.
- Each payload family's `index.parquet` joins `sample_id` to `source_dataset`,
  `source_id` and `molecule_id`; array shard rows remain linked by `record_id`,
  `shard` and `row_in_shard`.
- Numerical arrays are released as resumable HDF5 shards. Scalar metadata and
  indices use Parquet. Raman arrays are always stored as float64.

## Commands

Build the lightweight catalogs, leakage-safe splits and release gates first:

```bash
python -m openmolspec.release.build \
  --config configs/openmolspec_v1_release.yaml \
  --stage catalog

python -m openmolspec.release.build \
  --config configs/openmolspec_v1_release.yaml \
  --stage split

python -m openmolspec.release.build \
  --config configs/openmolspec_v1_release.yaml \
  --stage validate
```

Export large payloads independently. Completed shards are detected and reused,
so an interrupted export can be resumed with the same command:

```bash
python -m openmolspec.release.build --config configs/openmolspec_v1_release.yaml --stage export --only frequency
python -m openmolspec.release.build --config configs/openmolspec_v1_release.yaml --stage export --only nmr
python -m openmolspec.release.build --config configs/openmolspec_v1_release.yaml --stage export --only trajectory
```

Rebuild the compact global index and aggregate payload summary without reading
the source pickles:

```bash
python -m openmolspec.release.build --config configs/openmolspec_v1_release.yaml --stage index
```

Run publication validation with versioned inputs and cache:

```bash
python -m openmolspec.quality.stats \
  --pickle artifacts/processed/openspec.pickle \
  --nmr-pickle builds/openmolspec-20260830/openspec_nmr.pickle \
  --manifest builds/openmolspec-20260830/datasets/openspec_manifest.parquet \
  --trajectory-dir trajectory_outputs \
  --descriptors reports/analysis/chemical_descriptors.parquet \
  --opt-reports reports/opt_trajectories \
  --dedup-summary reports/dedup/dedup_summary.json \
  --source-statistics reports/analysis/source_statistics.parquet \
  --record-qc reports/internal_qc/record_qc.parquet \
  --cache-dir builds/openmolspec-20260830/release-v1/cache/validation-v2 \
  --output builds/openmolspec-20260830/release-v1/validation/publication \
  --workers 32
```

Freeze only after catalogs, splits, validation and all desired payload shards
are complete. This computes SHA-256 checksums for input and release files and
writes source/config checksums plus the environment/schema lock. A dirty Git
state is recorded exactly through `source_checksums.parquet`, but the public
release should still be associated with a clean commit and immutable Git tag:

```bash
python -m openmolspec.release.build \
  --config configs/openmolspec_v1_release.yaml \
  --stage freeze \
  --hash-workers 2
```

After `release-lock.json` is created, do not edit that release directory. Any
change to data, processing, schema or splits requires a new release ID.

For a fresh machine, all stages can be run in order with `--stage all`, but the
separate commands are preferred for this approximately 130 GB source build.
