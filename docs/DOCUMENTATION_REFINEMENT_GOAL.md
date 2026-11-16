# Documentation and model review — 2026-11-17

This is phase 1 of the [current OpenMolSpec dataset and platform goal](OPENMOLSPEC_PLATFORM_GOAL.md), updated on 2026-11-17. The broader goal adds a public dataset/model API and user-facing training workflows; it retains every documentation deliverable below. OpenDataLab-curated spectra are experimental measurements from external sources, as clarified by the user, and are presented separately from OpenMolSpec computed data.

Phase-1 scope:

1. Group tasks into NMR, MS, IR/Raman and multimodal families. Explain the scientific question, required inputs, units, outputs and interpretation for every active task.
2. Replace schema-only demonstrations with traceable real input/output records, executed analysis cells, figures and result tables. Add a Photo Gallery with downloadable scientific figures and their source data.
3. Expand the Quick Start into a reproducible path from checkout through a first example, model inference and result interpretation.
4. Describe dataset contents, record counts, molecule counts, source composition, modality availability and split distributions. Separate OpenMolSpec computed data, our curated derivatives, and external datasets. Do not sum overlapping views or equate spectra, conformers and molecules.
5. Recheck model/task compatibility and scientific evidence, especially B/Si. Produce a prioritized list of potential future fine-tuning tasks, distinguishing missing weights, protocol problems and insufficient validation from actual model limitations.
6. Validate bilingual sources, executed notebooks, figures, links and builds; push the release branch, publish RTD and verify hosted content.

No training, fine-tuning or fitted reference calibration is authorized. SpectraLLM, formula prediction and spectroscopy QA remain deferred. Historical measurements and experimental references retain their provenance; illustrative or fabricated predictions must not be presented as results.

Work order: evidence/data audit → figures and notebooks → task pages and navigation → Quick Start and dataset/model-review pages → browser/CI checks → publication.
