# `openmolspec` package

This is the unified Python package for turning Gaussian logs and source labels
into OpenMolSpec records, validating them, constructing splits and assembling
releases. The public SDK adds `dataset.py`, `model.py`, `task.py`, `benchmark.py` and
`training.py`. Heavy model runtimes are loaded lazily through `_worker.py`;
existing upstream implementations remain separate. See the Python SDK guide
in `documentation/api.md` for the alpha API and its validation limits.

The dependency direction is intentionally layered:

```text
core ─┬→ parsing ─┐
      ├→ io ──────┴→ workflows
      ├→ quality ───→ datasets
      └→ release
```

`analysis`, `maintenance` and `legacy` are leaf command packages: production
modules never import from them.

- `core/`: schema, constants, processing reports and progress;
- `io/`: manifest-backed input and task loading;
- `parsing/`: Gaussian and optimization-trajectory parsers;
- `workflows/`: manifest, frequency, NMR and trajectory production;
- `quality/`: record QC, identity analysis and publication statistics;
- `datasets/`: scaffold-aware dataset splitting;
- `release/`: catalog, export, release gates and freezing;
- `analysis/`: statistics, publication figures and trajectory visualization;
- `maintenance/`: dataset-specific recovery and diagnostic commands;
- `legacy/`: compatibility CLIs and historical helpers.

## Production workflows

| Module | Responsibility |
|---|---|
| `workflows/manifest.py` | Orchestrate the incremental frequency/NMR manifest |
| `workflows/manifest_scan.py` | Scan source trees, normalize identities and write audit records |
| `workflows/frequency.py` | Parse structures, properties, IR and Raman data |
| `workflows/nmr.py` | Parse NMR shielding data and generate NMR spectra |
| `workflows/trajectories.py` | Extract per-step geometries, energies, forces and convergence diagnostics |

Analysis scripts are indexed in `analysis/README.md`. Dataset-specific tools,
including the ZINC v2 NMR reparser, are indexed in `maintenance/README.md`.

The shared Gaussian archive/property/spectrum implementation lives in
`src/openmolspec/parsing/gaussian.py`. Former file-map and raw-directory CLIs
are retained under `legacy/` and are not part of the canonical workflow.

## Legacy entry point

`legacy/extract_properties_backup.py` is retained for comparison and
backward compatibility. It is not the canonical OpenSpec v1 production path.

## Recommended workflow

For new production runs, prefer the repository-level staged entry point:

```bash
python -m openmolspec --config configs/default.yaml --stage all
```

Use `--stage manifest`, `--stage freq`, `--stage nmr`, `--stage validate`, `--stage dedup`
or `--stage split` to run one stage. The legacy scripts below remain available
for compatibility.

```text
workflows/manifest_scan.py
        ↓
openspec_manifest.parquet
        ↓
python -m openmolspec --stage freq / --stage nmr
        ↓
parsed dataset + processing report
```

Manifest cache shards live under `paths.manifest_cache_dir`. Subsequent runs
reuse unchanged source logs and process only additions, modifications and
deletions. The staged pipeline reads `openspec_manifest.parquet` directly, so the legacy
SMILES/file JSON maps can be disabled with
`runtime.write_compatibility_json: false`. Keep
`runtime.manifest_min_file_age_seconds` nonzero while Gaussian jobs may still
be writing output files.

Do not place generated pickles, reports or source Gaussian logs in this
directory. Keep generated data under a configured output directory.

## Optimization trajectories

Extract the optimization trajectory from a frequency calculation directory:

```bash
python -m openmolspec.workflows.trajectories \
  --log-path /path/to/freq_logs \
  --save-path artifacts/processed/openspec_opt_trajectories.pickle \
  --report-path reports/opt_trajectories.json \
  --workers 8
```

The output is one row per optimization frame. It includes atomic numbers,
coordinates, electronic energy, SCF cycle count, Gaussian forces, force and
displacement convergence values, final-step status, and final-frequency
metadata. Forces use the convention `F = -dE/dR` and are stored in Hartree/Bohr;
coordinates are in Angstrom and energies are in Hartree.

To process all frequency datasets, write one pickle per dataset to avoid
holding the complete multi-dataset trajectory collection in memory:

```bash
python -m openmolspec.workflows.trajectories \
  --freq-root /inspire/hdd/project/chemicalreaction/luxinyu-240207020178/hpc/mols/freq \
  --output-dir trajectory_outputs \
  --report-dir reports/opt_trajectories \
  --workers 8
```

Use `--datasets pcqm4mv2 zinc_v2` to restrict the batch. The expected input
layout is `<freq-root>/<dataset>/<dataset>_log`. The all-dataset mode also
includes `sdbs` and `peptide`; their output IDs use the `SDBS-` and `PEPTIDE-`
prefixes. Optimization trajectories do not require a SMILES label.
