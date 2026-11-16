# OpenMolSpec dataset and platform manuscript working outline

Working title: **OpenMolSpec: A Million-Scale Dataset and Platform for Deep Learning in Chemical Spectroscopy**.

This outline follows the 2026-11-17 platform goal. It is a claim/evidence plan, not
a completed submission or a promise of journal acceptance. The earlier Scientific
Data outline remains a historical data-descriptor option.

## Central contribution

Present a versioned spectroscopy resource and reusable software interface linking
data curation, structured tasks, existing model adapters and reproducible analysis.
Distinguish experimental measurements curated from OpenDataLab/WanJuan, calculated
OpenMolSpec observables, and externally maintained benchmarks throughout.

The paper should explain the curation and alignment contribution rather than
treating external measurements or model architectures as newly created by the team.
The API enables access and experimentation; interface count alone is not evidence
of scientific accuracy or generalization.

## Evidence that can be cited now

| Claim | Evidence | Limit |
| --- | --- | --- |
| Curated experimental NMR has million-scale identity coverage | Existing standard-InChI corpus summary: 2,680,271 identities | Full release not recounted here; one identity may have multiple spectra |
| Computed resource has million-scale coverage | Release snapshot: 1,158,074 full InChIKey identities, 1,030,780 strictly aligned | Full artifacts not mounted; snapshots and model-LMDB representations are different counting scopes |
| Seven prepared datasets can be opened through one SDK | Packaged dataset registry, streaming readers, installed-wheel checks | Local files; public dataset release URLs and terms pending |
| Common model classes execute existing weights | SDK frozen-inference reports and actual inference notebooks | Small functional validation, not a new benchmark or SOTA result |
| Multiple spectroscopy tasks share an evaluation interface | 31 active task adapters, with input/output and provenance documentation | Multiple configurations may share a model; some remain diagnostic or algorithmic |
| Users can prepare train/validation data and invoke an existing trainer | Dataset preparation, hash/identity checks and explicit TrainingPlan/fit implementation | New training/save/reload round trip not executed under the current no-training constraint |
| Model-training overlap has been audited for specific NMR files | Full scans and checkpoint fingerprints in `results/nmr_checkpoint_overlap_20261117.json` | Confirmed overlap for several views; final generator training-file discrepancy unresolved; current scores are not independent benchmarks |

## Suggested structure

1. **Motivation and scope.** Explain fragmentation in formats, experimental
   conditions, calculated observables, identity definitions and model interfaces.
2. **Data construction.** Give original sources and versions, extraction,
   normalization, provenance retention, duplicate handling, modality alignment,
   record rejection/quarantine policy and licensing/access.
3. **Data records and distributions.** Separate molecules, spectra, atom shifts,
   conformers and trajectory frames. Report source composition, molecular size,
   elemental coverage, nuclear coverage, missing conditions and split sizes.
4. **Software and task contracts.** Dataset loader, model facades, configuration
   save/load, explicit training, task registry and benchmark receipts. Show a real
   data-to-prediction notebook and a separate training-preflight example.
5. **Technical validation.** Structural/chemical checks, source-metadata checks,
   cross-split and model-training overlap, original-adapter agreement and clean
   package installation. Explain failures as well as successes.
6. **Independent evaluation.** Use fixed eligible held-out data, relevant baselines,
   modality/formula/candidate-pool controls and appropriate uncertainty. This is
   a separate experimental deliverable, not supplied by tiny integration runs.
7. **Usage, availability and limitations.** Publish code/data/checkpoint versions,
   environments, actual download locations, terms and known unsupported domains.

## Figures and tables to assemble

- Data provenance and curation flow, with experimental and calculated branches.
- Dataset scale/distribution panels with explicit counting units and overlap scope.
- Task/input/output matrix grouped by NMR, MS, IR/Raman and multimodal use.
- Actual SDK workflow and prediction/reference examples, including weak cases.
- Independent benchmark comparison once eligible splits are established.
- Tables of dataset cards, model capabilities/checkpoint provenance, and failure
  modes. B/Si and F/P diagnostics must not appear as validated solution predictors.

The existing Gallery supplies scientific assets and underlying JSON; manuscript
panels should be selected for the scientific argument rather than simply counting
all available task images.

## Required work before strong manuscript claims

Confirm redistribution scope and accessible versioned release artifacts. Resolve
or document chemical inconsistencies such as a nucleus absent from its associated
structure. Audit the actual checkpoint-recorded training files and relevant
initialization history before labeling an evaluation independent. Preserve the
difference between molecular overlap and exact spectrum overlap.

The first completed checkpoint audit found 3,281 NMRSpec and 6,794 NMRExp
evaluation identities in the fingerprint-matched alignment training file; the
intermediate generator records the same file. The final generator's train digest
matches `g1_ne`, whereas its log names `g1_all`. This must be resolved before any
claim of independent experimental generalization. The new trainer verifies actual
file bytes; historical weights and data are unchanged.

After explicit authorization, validate training, checkpoint saving and reloading
with a minimal integration run before designing larger scientific experiments.
Any experimental/computed transfer, scaling or fine-tuning claim requires its own
controlled study; none is inferred from the current software release.
