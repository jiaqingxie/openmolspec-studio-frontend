# OpenSpec repository audit

**Audit scope:** repository state inspected on 2026-08-12.

**Purpose:** record the current data-generation implementation before changing scientific behavior. This audit corresponds to Phase 1 of `OpenSpec v1.0 Validation & Release — Codex Execution Plan.md`.

**Maintenance note:** the audit describes the pre-refactor state. The shared
Gaussian parser refactor was completed afterwards in `src/openmolspec/parsing/gaussian.py`; the
three frequency/property scripts now contain compatibility wrappers and CLI
orchestration rather than their former duplicate parser implementations.

## 1. Repository inventory

### Data-generation scripts

| File | Role | Output |
|---|---|---|
| `src/openmolspec/workflows/manifest_scan.py` | Combines source label JSON files and Gaussian log paths into global maps | `datasets/openspec_smiles.json`, `datasets/openspec_freq_files.json` |
| `src/openmolspec/legacy/extract_spectra.py` | Parses Gaussian logs, structures, quantum-chemical properties, IR and Raman data | Pandas DataFrame pickle |
| `src/openmolspec/legacy/extract_properties.py` | Parses Gaussian logs, structures and quantum-chemical properties; also computes IR/Raman arrays | Pandas DataFrame pickle |
| `src/openmolspec/legacy/extract_nmr.py` | Parses NMR shielding information and provides NMR spectrum broadening | Pandas DataFrame pickle |
| `src/openmolspec/legacy/extract_properties_backup.py` | Older/backup parser with a similar Gaussian parser and tensor reconstruction path | Pandas DataFrame pickle |
| `src/openmolspec/legacy/function.py` | Legacy structure, coordinate and graph-feature helpers; not part of the current extraction CLI | No dataset output by itself |

The repository also contains exploratory notebooks under `notebooks/`. These are not production pipelines.

### Current repository-level inputs and artifacts

- `datasets/` and `supplementary/` are expected to contain large external inputs and are gitignored.
- `NISTIR-11730.log` is a local Gaussian log example.
- `*.pickle`, `*.pkl` and `*.pt` are generated or auxiliary artifacts and are not suitable as the only public release format.
- `README.md` documents the project at a high level; the release plan and manuscript outline document the intended validation/release work.

## 2. Current emitted fields

### `extract_spectra.py` and `extract_properties.py`

The two current parsers can emit the following keys when the corresponding sections are present:

| Field | Current representation | Notes |
|---|---|---|
| `filename` | string | Input log path; machine-specific path may be persisted |
| `smiles` | string or `None` | Looked up from the supplied SMILES map |
| `atom` | NumPy `int32` array | Atomic numbers |
| `coordinate` | NumPy `float32` array | Flattened Cartesian coordinates in the current parser |
| `energy` | NumPy array/scalar | Archive `HF` value |
| `zpve` | NumPy array/scalar | Archive `ZeroPoint` value |
| `U0` | NumPy array/scalar | Computed as `energy + zpve` when both exist |
| `U` | NumPy array/scalar | Archive `ETot` value |
| `H` | NumPy array/scalar | Archive `HTot` value |
| `G` | NumPy array/scalar | Archive `GTot` value |
| `dipole` | NumPy array | Archive `Dipole` value |
| `dipole_deriv` | array, reshaped to `(N, 3, 3)` | Current code applies `* 4.8032` |
| `polar` | array, usually reshaped to `(3, 3)` | Archive polarizability components are reconstructed as a symmetric matrix |
| `polar_deriv` | array, reshaped to `(N, 3, 3, 3)` | Current code applies `* 1.8897` |
| `hessian` | symmetric array, intended shape `(3N, 3N)` | Reconstructed from lower-triangular archive values |
| `dipole_total` | Python float | Parsed from log text |
| `isotropic_polar` | parsed in regex definitions but not retained in current implementation | Requires audit/fix decision |
| `homo` | Python float | Parsed from the last matching alpha occupied eigenvalue line |
| `lumo` | Python float | Parsed from the last matching alpha virtual eigenvalue line |
| `gap` | Python float | Computed as `lumo - homo` |
| `quadrupole` | array, reconstructed to `(3, 3)` | Regex assumes the section exists |
| `octapole` | array, reconstructed to `(3, 3, 3)` | Regex assumes a specific component order |
| `freq` | NumPy array | Vibrational frequencies; `extract_spectra.py` multiplies by `0.965`, while `extract_properties.py` does not |
| `ir` | NumPy array of length 1024 | Lorentzian-broadened IR spectrum |
| `raman` | NumPy array of length 1024 | Raman spectrum calculated from broadened Raman activity |

The parsers do not currently emit explicit fields for `sample_id`, `source_dataset`, `source_id`, `canonical_smiles`, `inchikey`, source-file hash, parser version, processing version, quality flags or missing-field lists.

### `extract_nmr.py`

The NMR parser can emit:

| Field | Current representation | Notes |
|---|---|---|
| `filename` | string | Input log path |
| `atom` | NumPy array | Atomic numbers inferred from element labels |
| `isotropic` | NumPy array | Values parsed from Gaussian shielding output |
| `anisotropy` | NumPy array | Values parsed from Gaussian shielding output |
| `shielding_tensor` | flattened NumPy array | Nine tensor components per atom, if parsed |
| `smiles` | string | Looked up through module-global `label_dict` |

`get_nmr_spectrum()` creates a 1024-point spectrum over `0–12` with a default broadening sigma of `0.05`, but the current CLI does not explicitly add the generated spectrum to each parsed record.

## 3. Units and numerical conventions currently present

The scripts define the following constants:

```text
CM_HZ = 2.99792458e10
A_M   = 1e-10
KB    = 1.380649e-23
HP    = 6.62606896e-34
C     = 299792458
```

The code and comments indicate or imply:

- vibrational frequencies are represented in `cm^-1`;
- coordinates are read from Gaussian archive coordinates and stored as `float32`; the expected coordinate unit is Å, but this is not recorded in output metadata;
- Raman intensity conversion uses SI constants, a temperature default of `298 K`, and excitation wavelength default `532 nm`;
- `dipole_deriv` is multiplied by `4.8032`;
- `polar_deriv` is multiplied by `1.8897`;
- energy, thermochemical quantities, dipole, polarizability, Hessian and NMR values have no explicit unit metadata in the output;
- `extract_nmr.py` uses lower-case duplicate constants with slightly different spelling and numeric formatting (`cm_hz`, `A_m`, `Kb`, `hp`, `c`).

The output therefore does not yet provide a reliable machine-readable unit contract. Units and conversion factors must be frozen in the v1 schema before public release.

## 4. Spectrum processing parameters

### IR and Raman in `extract_spectra.py`

- Frequency correction: `freq = freq * 0.965` before broadening.
- Fixed grid: `np.linspace(400, 4000, 1024)`.
- Line shape: Lorentzian, implemented by `Lorenz_broadening`.
- Default Lorentzian sigma in the helper: `12`.
- Raman intensity conversion: temperature `298 K`, excitation wavelength `532 nm`.
- Raman calculations intentionally use `float64` according to the function docstring.

### IR and Raman in `extract_properties.py`

- No `0.965` frequency correction is applied in `_log2spectrum()`.
- Fixed grid: `np.linspace(400, 4000, 1024)`.
- `get_ir_spectrum()` default sigma: `20`.
- `get_raman_spectrum()` default sigma: `12` for broadened activity.
- `_log2spectrum()` directly calls `Lorenz_broadening` with its helper default sigma `12` for both IR and Raman activity, so the named `get_ir_spectrum()` helper is not the actual path used there.
- Raman temperature and excitation wavelength defaults are `298 K` and `532 nm`.

### NMR in `extract_nmr.py`

- Fixed grid: `np.linspace(0, 12, 1024)`.
- Default NMR sigma: `0.05` in `get_nmr_spectrum()`.
- The unit and direction of the NMR axis are not explicitly documented in the output.

These differences are scientific-definition inconsistencies, not merely code style differences. They must be resolved or exposed as explicit configuration before combining outputs from the two parser paths.

## 5. Gaussian parsing logic

The primary parsers follow this flow:

1. Read the complete log file as text with UTF-8 and `errors='ignore'`.
2. Split on `----------------------------------------------------------------------` and take the last section as an archive-like block.
3. Remove formatting and split archive fields using `\\`.
4. Map archive fields to `job`, `input`, `notation`, `coordinates`, `properties`, `hessian` and `force`.
5. Parse archive coordinates into atomic numbers and Cartesian coordinates using RDKit element parsing.
6. Parse archive properties using tags including `HF`, `ZeroPoint`, `Dipole`, `DipoleDeriv`, `Polar`, `PolarDeriv`, `ETot`, `HTot` and `GTot`.
7. Parse text-based properties using regular expressions for dipole total, isotropic polarizability, HOMO/LUMO, quadrupole and octapole.
8. Parse frequency, IR intensity and Raman activity lines from the Gaussian log.
9. Broaden spectra and reconstruct tensors.
10. Convert selected values to NumPy arrays and return a dictionary if an atom field was produced.

The archive parser assumes a particular Gaussian archive layout and field order. There is no explicit Gaussian version, calculation method, basis set, charge or multiplicity extraction in the current emitted record.

## 6. Exception handling and silent failure

The following patterns currently suppress or weaken failure reporting:

### Primary spectra/properties parser

`extract_spectra.py` and `extract_properties.py` wrap most of `LogParser.__init__()` in:

```python
except Exception as e:
    pass
```

An invalid or incomplete file can therefore return a partial dictionary or an empty dictionary without a structured error record. The multiprocessing wrapper only retains records for which an `atom` field is present.

### Backup properties parser

`src/openmolspec/legacy/extract_properties_backup.py` also catches parser exceptions in the constructor and returns the current properties dictionary. Its multiprocessing wrapper catches all processing exceptions and returns `None`.

### NMR parser

`extract_nmr.py` prints an exception in the constructor but does not attach an error type or error message to the output. The wrapper also prints and returns `None` on failure.

### Specific failure risks

- `re.findall(patterns['quadrupole'], self.text, re.S)[-1]` raises `IndexError` when no quadrupole match exists.
- Missing archive fields can raise `KeyError`.
- Tensor shape assumptions can raise `ValueError`.
- Missing or malformed numeric values can raise conversion errors.
- File paths and label lookups can fail without being represented in a processing report.

The current pipeline has no `processing_report.parquet`, `processing_summary.json`, error taxonomy, missing-field report or attrition accounting.

## 7. Hard-coded paths and runtime assumptions

### `extract_labels.py`

```python
root_dir = '/inspire/hdd/project/chemicalreaction/luxinyu-240207020178/hpc/mols/freq'
```

The source dataset names and output paths are also hard-coded. The script writes directly to absolute paths under the current project directory.

The code constructs `log_path` with `root_dir` and later calls `os.path.join(root_dir, log_path)`, which can duplicate the root prefix. This needs to be verified and fixed before regenerating label maps.

### Other scripts

- `extract_spectra.py` defaults to `datasets/openspec_freq_files.json`, `datasets/openspec_smiles.json` and `artifacts/processed/openspec.pickle`.
- `extract_properties.py` defaults to the same input maps and `./test.pickle`.
- `extract_nmr.py` defaults its three CLI arguments to empty strings and depends on a module-global `label_dict` initialized only in the `__main__` path.
- `src/openmolspec/legacy/function.py` imports `mol_from_np_2`, which is not present in this repository, and also assumes optional packages including PyTorch Geometric, ASE and Open Babel.
- Multiprocessing uses `mp.cpu_count()` directly, with no CLI control over worker count.

## 8. Duplicated parsing logic

`extract_spectra.py`, `extract_properties.py` and `src/openmolspec/legacy/extract_properties_backup.py` contain substantially duplicated implementations of:

- physical constants;
- Raman intensity conversion;
- Lorentzian broadening;
- Gaussian archive parsing;
- coordinate parsing;
- archive property parsing;
- text-property regular expressions;
- frequency/IR/Raman extraction;
- tensor reconstruction;
- multiprocessing output handling.

The duplication has already resulted in inconsistent behavior, especially frequency scaling and IR broadening. A future refactor should extract shared low-level parsing and numerical utilities while preserving a compatibility wrapper for existing commands.

## 9. Current ID construction

`extract_labels.py` intends to add source prefixes for selected datasets:

```text
NISTIR-
PAH-
PCQM4MV2-
RXN-
WILEYIR-
WILEYRAMAN-
```

The code does not add explicit prefixes for `qm9`, `zinc_v1` or `zinc_v2`. It also iterates over log filenames after stripping `.log`, while the label map may have already been rewritten with a prefix. This creates a likely mismatch between `valid_ids` and `label_dict`.

The current emitted records do not retain separate `source_dataset` and `source_id` fields. A reproducible v1 identity model should preserve both, alongside a global `sample_id`, canonical SMILES and preferably InChIKey.

## 10. Current output formats

### Label maps

JSON maps:

```text
sample ID → SMILES
sample ID → Gaussian log path
```

The current path map may contain machine-specific absolute paths, which are not portable release metadata.

### Parsed data

All current extraction CLIs serialize a Pandas `DataFrame` with `DataFrame.to_pickle()`.

This is convenient for local Python use but is not sufficient as the only public format because it is Python/pandas-version dependent and does not expose a formal schema, units or missing-value policy. The release plan should add portable formats such as Parquet and HDF5/NPZ, with pickle retained only as an optional compatibility artifact.

## 11. Field-definition inconsistencies

The following inconsistencies must be resolved before freezing v1:

| Topic | Current inconsistency or ambiguity |
|---|---|
| Frequency scaling | `extract_spectra.py` applies `0.965`; `extract_properties.py` does not |
| IR broadening | Helper default is `12`; `get_ir_spectrum()` declares `20`; actual primary path uses helper default `12` |
| Raman activity/intensity | Different helper paths exist; actual processing path must be specified |
| Coordinate shape | Parser initially stores flattened coordinates; schema expects `(N, 3)` |
| Coordinate units | Expected to be Å but not stored in metadata |
| Tensor units | Conversion factors are applied but their units and provenance are not emitted |
| Energy units | No unit metadata is emitted |
| NMR naming | Parser emits `isotropic`, `anisotropy`, `shielding_tensor`; target schema proposes `nmr_isotropic`, `nmr_anisotropy`, `nmr_tensor`, `nmr_shifts` |
| NMR spectrum | Helper exists, but generated NMR spectrum is not clearly included in CLI output |
| SMILES identity | Only `smiles` is emitted; canonicalization and InChIKey are absent |
| Provenance | No source dataset, source ID, file hash or parser version |
| Quality metadata | No quality flags or missing-field list |
| Gaussian metadata | Functional, basis set, charge, multiplicity and convergence are not emitted |
| Optional fields | Missing optional sections can abort a whole record rather than be represented as missing |

## 12. Proposed incremental refactor plan

This audit deliberately does not change scientific behavior. The next phases should proceed in this order:

### Step 1 — Freeze the current behavior in documentation and fixtures

- Preserve the current scripts as compatibility entry points.
- Add a small representative Gaussian fixture set.
- Record current output keys, shapes and processing parameters.
- Decide which current behavior is the v1 scientific definition and which behavior is legacy.

### Step 2 — Add authoritative constants and schema

- Create `src/openmolspec/core/constants.py` for shared physical constants and processing parameters.
- Create `src/openmolspec/core/schema.py` and `configs/openspec_v1.yaml` for fields, dtype, shape, unit and missing-value policy.
- Do not silently alter existing values; expose differences as explicit configuration until resolved.

### Step 3 — Introduce structured parser results

- Replace silent exceptions with structured success/failure results.
- Add the planned error taxonomy.
- Preserve optional-field omissions and record them in `missing_fields`.
- Generate `processing_report.parquet` and `processing_summary.json`.

### Step 4 — Add internal QC

- Implement structural, optimization, spectral and property checks.
- Produce attrition accounting and distribution statistics.
- Flag outliers rather than deleting them automatically.

### Step 5 — Add identity, deduplication and splits

- Define `sample_id`, source identity and molecular uniqueness.
- Produce exact, canonical-SMILES, InChIKey and cross-source overlap reports.
- Generate fixed, leakage-checked splits.

### Step 6 — Build portable release artifacts

- Convert parsed data into documented Parquet/HDF5/NPZ/JSON artifacts.
- Add metadata, checksums, examples and a release builder.
- Keep pickle only as an optional compatibility format.

### Step 7 — Add external/experimental validation and benchmarks

- Implement QM9S/QMe14S comparison only after internal schema and QC are stable.
- Add experimental spectroscopy validation through a user-supplied mapping.
- Run scaling-law experiments after the correctness pipeline is reproducible.

## 13. Audit conclusion

The repository contains the essential extraction prototype and can parse at least one local Gaussian example, but it is not yet an auditable release pipeline. The lowest-risk next implementation step is the v1 schema/configuration phase after this audit, preceded by a small fixture and regression test if the current behavior needs to be frozen. No scientific constants or parser behavior were changed as part of this audit.
