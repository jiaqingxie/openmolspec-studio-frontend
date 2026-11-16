# Documentation and platform-goal update — 2026-11-17

This delivery completes the local documentation implementation for phase 1 of
[the updated platform goal](OPENMOLSPEC_PLATFORM_GOAL.md). It does not claim that
the planned public dataset/model classes, training API or full independent
benchmark have been implemented.

## Reader-facing changes

- 31 active tasks grouped into NMR, MS, IR/Raman and multimodal spectroscopy;
  three user-deferred tasks remain separately marked.
- Task pages explain required inputs, units, actual outputs, measured results,
  source hashes, model applicability and rerun commands.
- Photo Gallery contains 31 result figures and four dataset distribution figures,
  with PNG/SVG images and downloadable underlying data.
- 70 bilingual notebooks run actual analysis cells in Jupyter: 62 active-task
  notebooks, two dataset notebooks and six deferred-status notebooks. They
  analyze saved real inference and census results; they do not rerun the models.
- Quick Start covers a first reproducible figure without model downloads,
  notebook execution, original model runtimes and result interpretation.
- Dataset pages separate OpenDataLab / WanJuan experimental measurements curated
  by the team, computed OpenMolSpec data and external benchmark sources.

## Evidence and scientific limits

Fresh frozen inference recorded real examples for 44 NMR task/dataset combinations
and four vibrational ranking tasks. Earlier actual MS, atom-assignment,
cross-solvent, gap, vibrational-generation and conformer/spectrum results are
retained with source hashes. No model training or fitted calibration was run.

The data audit scanned all four local NMR evaluation files and the complete
OpenMolSpec test LMDB. Parent experimental-corpus counts and full computed-release
counts retain their original summary/snapshot scope; they were not independently
recounted from the full release in this update. OpenDataLab experimental provenance
was clarified by the project owner. Provider versions, redistribution scope and
cross-corpus overlap remain release tasks.

B/Si diagnostics remain unsuitable as validated production accuracy claims.
The 32-molecule B/Si MAEs are approximately 8.68 / 56.13 ppm. Current validation
pools match `data_hetero3`; their prepared train/validation structure intersections
are 121 for B and 10 for Si. This is not proof of overlap with the frozen model's
training data. Missing solvent/reference information and suspicious original
labels need investigation before adaptation. The inspected official NMRNet++
checkpoint archive does not establish availability of B/Si-specific weights.

The model-review page covers all active tasks and orders potential future
fine-tuning work by evidence and prerequisites. F/P reference-domain checks,
experimental assignment ground truth and larger independent MS/vibrational
evaluations remain necessary.

## Validation

- Jupyter execution: 70 notebooks, 132 rich outputs; per-notebook file hashes in
  `results/doc_notebook_execution.json`.
- Strict Sphinx build: 166 content pages, 170 HTML pages including search/index;
  both languages, links, anchors, notebook source/evaluation/evidence hashes pass.
- Browser: all 31 task-gallery images load, dataset provenance/count text appears,
  translated task navigation and English/Chinese search work, a notebook figure
  renders, downloaded notebook matches the source, mobile menu works, no JS errors.
- Four documentation-build tests, seven publication tests, twelve benchmark tests
  and the new generation-recording regression test pass. Recording preserves
  scores/order and excludes masked modalities from saved generation inputs.
- Repository generator checks and `git diff --check` pass.

The release branch remains `release/openmolspec-v1`. Remote publication is a
separate check after pushing this change; it must identify the exact built commit
and compare hosted pages/downloads/assets with the local build before completion
is reported.
