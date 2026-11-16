# Runnable interfaces and publication status — 2026-11-16

The requested functional pass now includes H/C atom assignment, a clearly labeled
H/C solvent-transfer reference baseline, B/Si diagnostic CLI adapters, and a fully
built bilingual HTML documentation site. SpectraLLM, formula prediction and QA
remain disabled. There was no model training or fitted calibration.

## Atom assignment

`openmolspec_bench.assignment` invokes the authors' liquid NMRNet H/C checkpoints
and saved scalers directly. It checks complete parameter restoration, preserves
the RDKit AddHs(input SMILES) atom order, groups topological symmetry sites and
uses minimum-cost peak matching with explicit unmatched peaks/sites. Geometry is
generated with seed 42 and MMFF optimized when supported. This optimizes geometry,
not model parameters. Default matching tolerances are 0.5 ppm for H and 5 ppm for C.

- `results/assignment_carbon32_20261116.json`: 32 distinct real molecules, 488
  matched carbon peaks, molecule-macro coverage **0.939238**, matched residual MAE
  **0.899131 ppm**. These diagnostics do not measure atom assignment accuracy.
- `results/assignment_online_h_20261116.json`: a direct hydrogen request completed.
- `results/new_prediction_pages_apptest_20261116.json`: real webpage button tests
  completed for both assignment and solvent transfer, with no exceptions.

Output indices are zero-based; exported atom-map numbers are index + 1. No
independent experimental atom-assignment labels are supplied, so accuracy remains
`null`. The model does not condition on solvent or average a conformer ensemble.

Configure the frontend:

```bash
export OPENMOLSPEC_NMR_PYTHON=/path/to/nmr-runtime/bin/python
export OPENMOLSPEC_MODELS_ROOT=/path/to/models
```

Open **Prediction (Online) → NMR 峰 → 原子指认**. The JSON request schema is:

```json
{"smiles":"CCO","nucleus":"13C","peaks_ppm":[18.2,58.3],"tolerance_ppm":5.0}
```

```bash
python -m openmolspec_bench.assignment --models-root /path/to/models --request request.json --output new-assignment.json
```

## Solvent transfer baseline

This is **experimental-reference retrieval, not a neural solvent model**. The
specialized NMRNet++/TransPeakNet weights remain unavailable. A local boron model
repository was also audited: its solvent-aware source exists but its trained
weights and saved feature scaler are absent.

The running baseline uses the existing NMRShiftDB 1.3.6 SQL archive. The extraction
imports only whitelisted chemical fields, without executing SQL from the archive.
It selects reviewed 1D H/C spectra and excludes calculated-condition records,
unknown/mixed solvents and conflicting repeated shifts. Pairing uses the same
database atom ID, not guessed atom order. The prepared reference library contains
**1,869 paired atom records from 53 molecular connectivities**.

For each query, all reference molecules with the same connectivity (including
stereoisomers) are excluded. A fixed Morgan radius-2, 2048-bit Tanimoto search
selects the nearest other molecule; source-shift distance selects the reference
atom. Its measured solvent difference is added to the supplied source shift.
The method fits no parameters and returns the reference molecule, atom IDs,
spectrum IDs and similarity. There is no fitted correction against test labels.

`results/solvent_transfer_reference32_20261116.json` records a seeded, 32-distinct-
molecule run with **296 atom pairs**; three candidate pairs were skipped for lack
of an independent reference:

| Nucleus | Molecules | Atom pairs | Transfer MAE (ppm) | Unchanged-source MAE (ppm) |
| --- | ---: | ---: | ---: | ---: |
| 1H | 19 | 156 | 0.137628 | 0.135385 |
| 13C | 13 | 140 | 1.094286 | 1.163714 |

The baseline does not consistently improve both nuclei. Temperature,
concentration and original reference conventions are not independently
harmonized. Similarity is not a calibrated probability. This is a runnable first
baseline, not evidence that the requested neural solvent model has been delivered.

Prepare the library from an existing archive (no downloads or training):

```bash
python scripts/prepare_solvent_reference.py --source /path/to/nmrshiftdb-data-1_3_6.sql.gz --output extracted.json
python -m openmolspec_bench.solvent_transfer --prepare extracted.json --output solvent_reference_library.json
export OPENMOLSPEC_SOLVENT_REFERENCE=/path/to/solvent_reference_library.json
python -m openmolspec_bench.solvent_transfer --evaluate --library solvent_reference_library.json --limit 32 --output new-transfer-evaluation.json
```

Open **Prediction (Online) → 跨溶剂化学位移** for a new request. Reference data and
weights stay outside Git and must be available to the deployed model runtime.

## B/Si CLI wiring

Both tasks now invoke the frozen diagnostic script from the shared runner; one
run is reused for the two nuclei within a single invocation. Results retain
`primary_score_eligible=false` and `score_scope=diagnostic_only`. No claim is made
that the poor Si accuracy or nucleus-specific training coverage was repaired.
`results/remaining_interfaces_smoke_20261116.json` records successful execution
of B, Si, assignment and solvent-transfer interfaces.

## Read the Docs build

The previous local workflow could check sources but could not render HTML because
the MkDocs/plugin dependencies were unavailable. The publication workflow now uses
one deterministic Mistune-based builder in local execution, CI and Read the Docs:

```bash
python -m pip install -r requirements-docs.txt
python scripts/render_task_catalog.py --check
python scripts/build_bilingual_docs.py --check
python scripts/build_readthedocs.py --output site --strict
```

The build produces **150 HTML pages**, including 68 executed notebook previews,
English/Chinese page switches, raw notebook downloads and task search. It verifies
internal links, fragments and notebook source/evaluation hashes; stale notebook
outputs fail the build. No model is imported and no Jupyter kernel is started.
The optional previous MkDocs renderer remains in `requirements-docs-mkdocs.txt`.

`.readthedocs.yaml` uses the platform's supported
[custom HTML build commands](https://docs.readthedocs.com/platform/stable/build-customization.html)
and writes to `$READTHEDOCS_OUTPUT/html`. A real hosted build has not been verified:
the current environment cannot resolve GitHub, Read the Docs or its configured
proxy; there is no connected RTD account/session or supplied project/build URL.
No public deployment is claimed. After a hosted build succeeds, set the real
`OPENMOLSPEC_DOCS_URL` on the frontend.

## Validation

24 focused checks passed (12 benchmark, 5 assignment, 5 solvent-reference and 2 HTML-build checks). Both new Streamlit pages completed real button-triggered computations. Four remaining CLI interfaces completed a bounded integration run. All 68 notebook demonstrations were re-executed; source consistency, 82 Markdown pages and the full 150-page HTML build passed.
