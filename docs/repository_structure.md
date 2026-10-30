# Repository structure

The repository separates reusable library code, executable scripts, generated
artifacts and publication documentation. The complete source layout is below.

## Unified data package

```text
src/openmolspec/
├── __main__.py
├── cli.py
├── core/
│   ├── constants.py
│   ├── schema.py
│   ├── processing.py
│   └── progress.py
├── io/
│   └── tasks.py
├── parsing/
│   ├── gaussian.py
│   └── trajectory.py
├── workflows/
│   ├── manifest.py
│   ├── manifest_scan.py
│   ├── frequency.py
│   ├── nmr.py
│   └── trajectories.py
├── quality/
│   ├── validation.py
│   ├── dedup.py
│   └── stats.py
├── datasets/
│   └── splits.py
├── analysis/
│   ├── analyze_dataset_comparison.py
│   ├── plot_align_chemical_distribution.py
│   ├── plot_dataset_statistics.py
│   ├── plot_element_coverage.py
│   ├── plot_openmolspec_overview.py
│   └── visualize_opt_trajectory.py
├── maintenance/
│   └── parse_zinc_v2_nmr.py
├── legacy/
│   ├── extract_spectra.py
│   ├── extract_properties.py
│   ├── extract_nmr.py
│   ├── extract_properties_backup.py
│   └── function.py
├── release/
│   ├── common.py
│   ├── catalog.py
│   ├── splits.py
│   ├── validation.py
│   ├── export.py
│   ├── freeze.py
│   └── build.py
```

Production users should normally call `python -m openmolspec`; direct
extraction modules exist for focused runs and historical interfaces.

## Application benchmarks

```text
benchmarks/
├── __main__.py           # python -m benchmarks
├── cli.py                # check/prepare-demo/commands/train orchestration
├── data/                 # split selection and LMDB exporters
├── engines/              # batch losses, metrics and target normalization
├── trainers/             # YAML launcher, epoch/checkpoint lifecycle and assembly
├── models/               # registry, model/dataset adapters and upstream source
│   ├── equiformer_v3/    # adapter files + ignored upstream/
│   ├── vib2conf/         # adapter files + ignored upstream/
│   └── vib2mol/          # workflow adapter + ignored upstream/
└── scripts/              # cluster launch and upstream setup scripts
```

## Configuration, tests and documentation

```text
configs/             versioned production and release configurations
tests/               unit/regression tests and small Gaussian fixtures
docs/manuscript/     Scientific Data manuscript material
docs/plans/          execution and benchmark plans
docs/figures/        publication-ready figures and compact figure metadata
notebooks/           exploratory analysis only
pyproject.toml        package metadata and the `openmolspec` CLI entry point
```

## Generated and local-only artifacts

```text
builds/              versioned release builds and frozen candidates
datasets/            generated manifests and compatibility maps
reports/             QC, analysis, retry lists and processing reports
trajectory_outputs/  per-source optimization trajectory pickles
supplementary/        local auxiliary inputs
benchmarks/models/*/upstream/ pinned external model repositories
benchmark_data/       generated demo-model inputs and outputs
artifacts/processed/  large generated pickle/PT datasets moved from repository root
artifacts/figures/    local exploratory figures
```

These paths and large `*.pickle`, `*.pkl`, `*.h5` and `*.pt` files are ignored
by Git. They must not be added to source-control commits. The canonical small
Gaussian fixture is kept under `tests/fixtures/` through an explicit ignore
exception.

## Naming rules

- `extract_*.py`: source-data extraction commands;
- `plot_*.py` and `analyze_*.py`: analysis-only commands;
- `src/openmolspec/*`: importable data implementation, never large generated data;
- `benchmarks/*`: model adapters, data preparation and training workflows;
- `tests/test_*.py`: regression tests;
- `reports/`: reproducible but local generated outputs.
