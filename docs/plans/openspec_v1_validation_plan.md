# OpenSpec v1.0 Validation & Release — Codex Execution Plan

## 0. Role and objective

You are working on the OpenSpec repository.

The dataset currently contains approximately **1.1 million unique molecules**, each associated with an optimized molecular geometry and available quantum-chemical properties / spectra.

Your task is to turn the existing data-generation repository into a **reproducible, auditable validation and public-release pipeline** suitable for a Scientific Data Data Descriptor.

Do not fabricate scientific results.\
Do not silently discard failed records.\
Do not change scientific definitions without explicitly documenting the change.

Before editing code, inspect the repository and existing scripts, especially:

```text
src/openmolspec/legacy/extract_spectra.py
src/openmolspec/legacy/extract_properties.py
src/openmolspec/legacy/extract_nmr.py
src/openmolspec/workflows/manifest_scan.py
```

Preserve backward compatibility where practical.

---

# Phase 1 — Repository audit

First inspect the complete repository.

Produce:

```text
docs/repository_audit.md
```

The audit must list:

1. all data-generation scripts;
2. all fields currently emitted;
3. units currently used;
4. spectrum processing parameters;
5. Gaussian parsing logic;
6. exception handling;
7. hard-coded paths;
8. duplicated parsing logic;
9. current ID construction;
10. current output formats;
11. places using `except: pass` or equivalent silent failure;
12. fields whose definitions are inconsistent between scripts.

Do not modify scientific behavior during this phase.

At the end, provide a short proposed refactor plan.

---

# Phase 2 — Freeze OpenSpec v1 schema

Create one authoritative schema definition.

Preferred layout:

```text
src/openmolspec/
    schema.py
    constants.py
configs/
    openspec_v1.yaml
```

The v1 schema should support at least:

```text
sample_id
source_dataset
source_id

smiles
canonical_smiles
inchikey

atomic_numbers
coordinates

energy
zpve
U0
U
H
G

dipole
polarizability
homo
lumo
gap
hessian

frequencies
ir_intensities
ir_spectrum

raman_activities
raman_spectrum

nmr_isotropic
nmr_anisotropy
nmr_tensor
nmr_shifts

source_file_hash
parser_version
processing_version
quality_flags
missing_fields
```

Every numerical field must have:

```text
dtype
shape
unit
missing-value policy
description
```

Store all spectrum/calculation metadata explicitly, including where applicable:

```text
Gaussian version
functional
basis set
charge
multiplicity

frequency range
frequency grid size
frequency scaling factor

IR broadening
IR line shape

Raman broadening
Raman line shape
Raman temperature
Raman excitation wavelength

NMR reference definition
```

Scientific constants and processing parameters must not remain duplicated across scripts.

---

# Phase 3 — Fix parser reliability

Refactor Gaussian parsing so that all parsers share common low-level parsing utilities where possible.

Requirements:

## 3.1 No silent failures

Remove patterns equivalent to:

```python
try:
    ...
except:
    pass
```

All failures must produce structured records.

Use an error taxonomy such as:

```text
FILE_NOT_FOUND
LOG_INCOMPLETE
SCF_FAILED
OPT_NOT_CONVERGED
GEOMETRY_PARSE_FAILED
ENERGY_PARSE_FAILED
FREQUENCY_PARSE_FAILED
IR_PARSE_FAILED
RAMAN_PARSE_FAILED
NMR_PARSE_FAILED
HESSIAN_PARSE_FAILED
SMILES_MISSING
ATOM_COUNT_MISMATCH
INVALID_NUMERIC_VALUE
UNKNOWN_ERROR
```

## 3.2 Structured processing report

Every processing run must generate:

```text
processing_report.parquet
processing_summary.json
```

At minimum:

```text
sample_id
source_dataset
source_id
status
error_type
error_message
missing_fields
quality_flags
source_file_hash
parser_version
```

A missing optional field must not automatically delete the entire molecule.

## 3.3 Unit tests

Create parser tests using small representative Gaussian logs.

Cover:

```text
successful log
failed optimization
missing optional section
malformed numerical value
missing NMR
missing Raman
negative frequencies
partial/truncated log
```

---

# Phase 4 — Internal Technical Validation

Implement:

```text
src/openmolspec/quality/validation.py
```

and CLI:

```bash
python -m openmolspec.quality.validation \
    --dataset <path> \
    --output reports/internal_qc
```

Perform the following checks.

## 4.1 Structural validation

For every molecule check:

```text
len(atomic_numbers) == coordinates.shape[0]
coordinates.shape == (N, 3)

no NaN
no Inf

valid atomic numbers
unique sample_id
valid source metadata
```

Where possible verify molecular formula / element composition against canonical SMILES.

Check:

```text
hessian.shape == (3N, 3N)
```

when Hessian is present.

## 4.2 Optimization validation

Record:

```text
optimization converged
number of optimization steps
presence of imaginary frequencies
number of imaginary frequencies
minimum frequency
```

Do not automatically remove imaginary-frequency structures unless existing project policy explicitly requires it.

Instead label them.

## 4.3 Spectrum validation

Check:

```text
frequency/intensity length consistency

fixed-grid spectrum shape
expected frequency range

NaN
Inf
negative or impossible values
extreme outliers

IR consistency
Raman consistency
NMR consistency
```

## 4.4 Property validation

Generate distributions and outlier statistics for:

```text
energy
zpve
dipole
polarizability
HOMO
LUMO
gap
thermochemical properties
```

Use robust statistics:

```text
count
missing rate
mean
std
median
MAD
1%
5%
25%
50%
75%
95%
99%
min
max
```

Do not automatically remove statistical outliers.

Flag them.

## 4.5 Attrition accounting

Produce a machine-readable accounting table:

```text
raw_input
parsed
optimization_converged
schema_valid
QC_pass
deduplicated
final_release
```

Include exact removal/flagging counts by reason.

Output:

```text
reports/internal_qc/
    summary.json
    attrition.csv
    error_breakdown.csv
    missingness.csv
    property_statistics.csv
    spectrum_statistics.csv
    figures/
```

---

# Phase 5 — Deduplication and molecular identity

Implement:

```text
src/openmolspec/quality/dedup.py
```

Generate at least:

```text
exact-record duplicates
canonical-SMILES duplicates
InChIKey duplicates
cross-source overlaps
```

Explicitly document treatment of:

```text
stereoisomers
tautomers
salts
fragments
charges
isotopes
different conformers
```

Do not silently collapse chemically distinct records.

Generate:

```text
dedup_report.parquet
dedup_summary.json
```

The final statement "`1.1 million unique molecules`" must be reproducible from this pipeline.

---

# Phase 6 — Dataset splits and leakage analysis

Implement:

```text
src/openmolspec/datasets/
```

Generate:

```text
random split
molecule-level split
scaffold split
source-aware split
```

Every split must include:

```text
random seed
split algorithm
dataset version
creation timestamp
molecule counts
```

Check leakage using:

```text
canonical SMILES
InChIKey
Bemis–Murcko scaffold
```

Produce:

```text
reports/leakage/
    molecule_overlap.csv
    scaffold_overlap.csv
    source_overlap.csv
    summary.json
```

The final benchmark test set must remain **fixed** for all subsequent scaling experiments.

---

# Phase 7 — QM9S / QMe14S external computational validation

Create a standalone validation module:

```text
src/openmolspec/quality/external_computational.py
```

Do not hard-code external dataset locations.

CLI example:

```bash
python -m openmolspec.quality.external_computational \
    --openspec <path> \
    --reference <qm9s-or-qme14s-path> \
    --reference-name QM9S \
    --output reports/qm9s
```

Perform two analyses.

## 7.1 Matched chemical-space comparison

Compare chemically matched subsets based on variables such as:

```text
element composition
heavy atom count
molecular weight
ring count
functional groups
formal charge
```

Compare distributions of:

```text
geometry descriptors
dipole
polarizability
HOMO
LUMO
gap
vibrational frequencies
IR quantities
Raman quantities
```

Calculate where appropriate:

```text
Wasserstein distance
KS statistic
standardized mean difference
quantile differences
```

Generate publication-quality Q–Q/distribution plots.

## 7.2 Exact molecule overlap

Where identical molecules exist between OpenSpec and the reference dataset, perform molecule-level comparisons.

Report:

```text
N overlap
MAE
RMSE
median absolute error
R²
Pearson r
Spearman rho
```

Generate parity plots.

Explicitly preserve information about different DFT levels of theory.

Do not interpret method-dependent offsets as parser errors automatically.

---

# Phase 8 — Experimental spectroscopy validation

Implement:

```text
src/openmolspec/quality/experimental.py
```

The code must support a user-supplied experimental mapping:

```text
sample_id
experimental_spectrum_path
spectral_type
experimental_metadata
```

Support at least IR first.

Raman/NMR may be added through the same API.

Use **stratified/random sampling**, not manually selected examples.

Recommended strata:

```text
molecular size
element composition
functional group
ring/non-ring
spectral complexity
```

## IR metrics

Implement:

### Peak-position metrics

```text
peak MAE in cm^-1
median absolute error
error quantiles
```

Support configurable matching tolerances:

```text
±20 cm^-1
±30 cm^-1
±50 cm^-1
```

Report:

```text
peak precision
peak recall
peak F1
```

### Whole-spectrum metrics

After common preprocessing:

```text
cosine similarity
Pearson correlation
spectral angle
Wasserstein distance
```

All preprocessing must be recorded:

```text
spectral range
grid
normalization
broadening
baseline handling
```

Generate representative:

```text
high-agreement
median-agreement
low-agreement
```

examples algorithmically, not manually.

---

# Phase 9 — Scaling-law benchmark

This phase demonstrates **dataset utility**, not dataset correctness.

Create:

```text
benchmarks/scaling/
```

The benchmark must support Vib2Mol and Harmony only if their code/dependencies are available.

Do not rewrite those models unnecessarily.

Create a shared training-data interface.

Use nested training subsets such as:

```text
10k
30k
100k
300k
1M
```

Important:

```text
10k ⊂ 30k ⊂ 100k ⊂ 300k ⊂ 1M
```

Use the exact same validation/test set for all runs.

Fix:

```text
split
random seed
model architecture
optimizer
evaluation protocol
```

Record:

```text
training molecule count
training steps
GPU hours
parameters
final metrics
best validation metrics
test metrics
```

Do not claim a formal power law unless the fit supports it.

Optionally fit:

```text
L(N) = A * N^(-alpha) + L_inf
```

but always show raw points.

Required output:

```text
reports/scaling/
    runs.parquet
    fitted_curves.json
    figures/
```

Primary scientific question:

```text
Does performance continue improving beyond the ~100k-molecule regime?
```

---

# Phase 10 — Optional optimization trajectory extraction

Do this only after the core validation pipeline is stable.

Create:

```text
src/openmolspec/trajectory/
```

For each optimization trajectory extract, where available:

```text
sample_id
step_index
n_steps

atomic_numbers
coordinates

energy
forces

max_force
rms_force
max_displacement
rms_displacement

is_final
is_converged
```

Force convention must be explicit:

```text
F = -dE/dR
```

Store unit explicitly.

Do not assume independent lists of geometries, energies and forces can simply be zipped.

Associate quantities at the **optimization-cycle level**.

Produce both:

```text
OpenSpec-Trajectory-Full
OpenSpec-Trajectory-Sampled
```

The sampled version may retain representative optimization steps.

Do not mix this trajectory dataset into OpenSpec-Core.

---

# Phase 11 — Release builder

Implement:

```text
src/openmolspec/release/
```

Command:

```bash
python -m openmolspec.release.build \
    --config configs/openspec_v1.yaml \
    --output releases/openspec-v1.0
```

Target structure:

```text
openspec-v1.0/

├── metadata/
│   ├── dataset_card.json
│   ├── schema.json
│   ├── source_metadata.csv
│   ├── processing_summary.json
│   └── processing_report.parquet
│
├── structures/
│   └── structures.parquet
│
├── spectra/
│   ├── ir_spectra.h5
│   ├── raman_spectra.h5
│   └── nmr_spectra.h5
│
├── properties/
│   └── quantum_properties.parquet
│
├── splits/
│   ├── random_split.json
│   ├── molecule_split.json
│   ├── scaffold_split.json
│   └── source_split.json
│
├── validation/
│   ├── internal/
│   ├── external_computational/
│   ├── experimental/
│   └── scaling/
│
├── examples/
│   ├── load_sample.py
│   └── reproduce_demo.py
│
├── checksums.sha256
└── LICENSE
```

Pickle may remain as an optional compatibility format.

It must not be the only public format.

---

# Phase 12 — Reproducibility

Create a minimal reproducibility workflow.

Include:

```text
environment.yml or pyproject.toml
locked dependencies where practical
parser version
Git commit
dataset version
random seeds
CLI commands
```

Provide a small demo dataset allowing:

```bash
python examples/reproduce_demo.py
```

The command should run:

```text
Gaussian parsing
schema conversion
QC
spectrum generation
final serialization
checksum verification
```

without requiring the full 1.1M dataset.

---

# Automated tests

Add tests covering:

```text
schema validation
unit conversion
Gaussian parser
spectrum generation
NMR parsing
deduplication
split leakage
hash generation
release packaging
QC aggregation
```

A scientific calculation should have deterministic regression tests where possible.

Run the full test suite before considering a phase complete.

---

# Working rules

Work phase by phase.

For each phase:

1. inspect existing implementation;
2. state what will change;
3. make the smallest coherent implementation;
4. add tests;
5. run tests;
6. report modified files;
7. report unresolved scientific assumptions.

Do not proceed by replacing the whole repository with a new framework.

Prefer incremental refactoring.

Do not modify scientific constants merely to make tests pass.

Never fabricate missing metadata.

If a scientific definition is ambiguous, expose it as configuration and clearly mark the unresolved decision.

---

# Definition of Done for OpenSpec v1.0

The project is release-ready only when all of the following are reproducible:

- [ ] Exact count of input records
- [ ] Exact count of final molecules
- [ ] Definition of molecular uniqueness
- [ ] Parser success/failure statistics
- [ ] Optimization convergence statistics
- [ ] Missing-field statistics
- [ ] Internal structural QC
- [ ] Internal spectral QC
- [ ] Internal property QC
- [ ] Duplicate analysis
- [ ] Cross-source overlap analysis
- [ ] Leakage-free benchmark splits
- [ ] QM9S/QMe14S external comparison
- [ ] Experimental spectroscopy validation
- [ ] Reproducibility demo
- [ ] Machine-readable schema
- [ ] Processing report
- [ ] Dataset version
- [ ] Parser version
- [ ] SHA-256 checksums
- [ ] Source/license metadata
- [ ] Public non-pickle data formats

Scaling-law experiments are recommended but are not a blocker for core data correctness.

Optimization trajectories are an optional OpenSpec extension and are not a blocker for OpenSpec-Core v1.0.

---

# Start now

Begin with **Phase 1 only**.

Inspect the repository, produce:

```text
docs/repository_audit.md
```

and report:

```text
A. current architecture
B. scientific-definition inconsistencies
C. reliability risks
D. proposed file-level changes for Phase 2
E. questions that genuinely cannot be resolved from the repository
```

Do not implement later phases until the Phase 1 audit is complete.
