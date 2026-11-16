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

The publication workflow uses Sphinx 8.2.3, the classic `sphinx_rtd_theme` 3.1.0,
and MyST-NB 1.4.0 in local execution, CI and Read the Docs. The earlier lightweight
custom HTML renderer was used for the first publication and has been replaced.
Build with Python 3.11 or newer:

```bash
python -m pip install -r requirements-docs.txt
python scripts/render_task_catalog.py --check
python scripts/build_bilingual_docs.py --check
python scripts/build_readthedocs.py --output site --strict
```

The build produces **150 content pages plus four search/index pages**, including
68 executed notebook previews, English/Chinese page switches, raw notebook
downloads, localized full-text search and hierarchical navigation. It verifies
internal links, fragments and notebook source/evaluation hashes; stale notebook
outputs fail the build. No model is imported and no Jupyter kernel is started.
MyST-NB execution is disabled; notebook metadata cannot opt into execution during
publication. The optional previous MkDocs renderer remains in `requirements-docs-mkdocs.txt`.

`.readthedocs.yaml` uses the platform's supported
[custom HTML build commands](https://docs.readthedocs.com/platform/stable/build-customization.html)
and writes to `$READTHEDOCS_OUTPUT/html`. The documentation is now published:

- [English](https://openmolspec-10.readthedocs.io/en/latest/)
- [简体中文](https://openmolspec-10.readthedocs.io/en/latest/zh/index.html)
- [First verified hosted build 35915674](https://app.readthedocs.org/projects/openmolspec-10/builds/35915674/)

The existing account project `openmolspec-10` was reused. Its previous builds
failed with `config:path:default-not-found`. The published release branch now
contains the root `.readthedocs.yaml`; RTD's default branch is
`release/openmolspec-v1`, with that explicit configuration path.
`results/readthedocs_publication_20261116.json` verifies commit
`5e8ce72655105f4a6cd61859c9c98c0574d36955`, all 150 public HTML page bodies,
all 68 notebook download hashes, and the manifest/evaluation/CSS assets.
GitHub Documentation and Benchmark integration checks also passed for that commit.

The initial command environment denied socket creation. After network access was
enabled, the server's configured HTTP proxy successfully reached GitHub and RTD;
direct HTTPS connections timed out. Publication uses the working proxy. The
public documentation CDN rejected Python's default User-Agent with Cloudflare
1010; verification with a browser User-Agent returned the actual published pages.
No credentials are sent when checking public pages.

`scripts/publish_readthedocs.py` now prepares the authenticated import workflow.
It uses only Python's standard library, supports `--direct` to bypass HTTP proxies, and
accepts an RTD token through `READTHEDOCS_TOKEN` or a hidden interactive prompt.
No credentials are embedded in the script or saved to disk. It checks the remote
release branch matches the expected commit before any RTD changes, reuses an
account project for this repository when present, sets the release branch and
configuration path, triggers `latest`, and optionally watches its build.
Credentials are restricted to the official RTD API; redirects are refused.

Run these commands from this checkout in a terminal with network access:

```bash
git push origin release/openmolspec-v1
python3 scripts/publish_readthedocs.py --apply --wait 600
```

Without `--apply`, the script only prints its plan. A standalone copy can use
`--expected-commit <full Git SHA>` instead of discovering the local checkout's
HEAD. A queued build is not reported as verified: verification requires a
successful finished build at that exact commit. Public page reachability was
checked separately as recorded above. Automatic GitHub-to-RTD rebuilds are not
yet independently verified; the authenticated script can trigger them explicitly.

The release frontend now links to the verified RTD URL by default, with an
optional `OPENMOLSPEC_DOCS_URL` override. Remote `main` has independently moved to
a Next.js/FastAPI frontend; bringing the expanded prediction pages/navigation into
that frontend remains separate work. Publishing this documentation branch does
not establish that the newer web frontend has been deployed with these changes.

## Validation

24 focused checks passed (12 benchmark, 5 assignment, 5 solvent-reference and 2 HTML-build checks), followed by 7 publication workflow checks. Both new Streamlit pages completed real button-triggered computations. Four remaining CLI interfaces completed a bounded integration run. All 68 notebook demonstrations were re-executed; source consistency, 82 Markdown pages and the full 150-page HTML build passed. The hosted publication audit verified 221 public resources.
