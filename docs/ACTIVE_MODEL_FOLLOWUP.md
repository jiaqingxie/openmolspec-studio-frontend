# Active scope and model sources — 2026-11-16

The user deferred SpectraLLM, formula prediction and spectroscopy QA. These three
catalog entries are disabled, excluded from `--tasks all`, and skipped even when
explicitly selected. Their old diagnostic results are retained as history.
There are 31 active definitions, all with execution adapters. F/P formal scores remain gated; B/Si are diagnostic-only; solvent transfer is an experimental-reference retrieval baseline. No training or fitted calibration is allowed. The current delivery evidence superseding the initial audit below is in [REMAINING_TASKS_DELIVERY.md](REMAINING_TASKS_DELIVERY.md).

## Website and documentation

The Streamlit frontend and bilingual Read the Docs sources/configuration exist.
The new shared builder generated and validated 150 HTML pages, including 68 notebook previews. Read the Docs and CI now use this tested custom HTML build; public hosting is not verified. A fresh DNS check on 2026-11-16 failed
for GitHub, Read the Docs and the configured proxy. No public URL is claimed.

## Conformer → IR/Raman provenance

The forward models are the Equiformer-v3 Hessian (`hi`, `hij`) and response
(`dedipole`, `depolar`) models from Xinyu's openSpec project. Local project
instructions reference `luxinyu-240207020178/openSpec` in
`docs/openmolspec_core.md`. Exact run paths and checkpoint hashes are recorded in
`results/vibrational_forward_paired_logs_20261116.json`.
Two paired Gaussian-log geometries have completed inference. This confirms the
pipeline on these examples, not a held-out benchmark. Vib2Mol is the separate
inverse spectrum-to-structure model.

## B and Si

The [official NMRNet++ repository](https://github.com/YongqiJin/NMRNetplusplus)
lists F/P/B/Si and solvent-aware H/C workflows and links its weights to
[Zenodo](https://zenodo.org/records/18232165). Its `run_heteroatoms.sh` starts
training, so it must not be used here. The locally downloaded `checkpoints.zip`
contains H/C checkpoints but no identifiable B/Si or solvent-specific checkpoint.
The official remote archive inventory is not yet accessible.

A different local candidate is the released NMRNet **liquid All-nucleus** model:
`nmrnet/weights/finetune/liquid/All_mol_pre_all_h_220816_global_0_kener_gauss_atomdes_0_unimol_large_atom_regloss_mae_lr_1e-4_bs_8_0.06_50`.
Checkpoint metadata says `selected_atom=All`, `num_classes=1`, and the original
training data path ends in `nmrshiftdb2/2024/All`. Its dictionary includes B and Si.
These facts establish a candidate inference interface; they do **not** establish
that both nuclei had sufficient labeled training data.

The first run completed successfully: B MAE **8.684532 ppm**, Si MAE
**56.133585 ppm**, each on 32 distinct molecules / 32 labeled atoms. All checkpoint
parameters loaded, with no missing or unexpected keys. Labels were aligned and
metrics independently recomputed. The large Si error means this candidate is not
a validated usable Si predictor. Evidence: `results/bsi_frozen_diagnostic_20261116.json`.

`scripts/run_frozen_bsi_diagnostic.py` selects up to 32 distinct molecules per
nucleus from the local validation pools, reuses the saved scaler, requires every
instantiated model parameter to load from the checkpoint, and verifies predictions
against the exact atom labels via inference sample IDs. It never fits the scaler
or model. Results remain diagnostic-only until training coverage, evaluation
overlap and experimental label provenance are verified.

## Peak → atom assignment

There are relevant existing models. A known structure can be passed to an
atomwise shift predictor and the predictions matched to observed peaks, with
atom numbering and symmetry-equivalent sites explicitly retained. A peak-set
error alone is not assignment accuracy.

[TransPeakNet](https://github.com/siriusxiao62/2dNMR) provides pretrained checkpoint
files, H/C matching code, an evaluation notebook and an expert-annotated HSQC
test set. It is a concrete H/C/2D candidate, not evidence of six-nucleus coverage.
Local frozen NMRNet H/C models now power the implemented 1D assignment interface. A 32-molecule carbon run and real H/C online requests completed. Independent experimental atom-assignment accuracy is still unverified. TransPeakNet code/weights were not found in the local model
directory; download is blocked by network access.

## Cross-solvent shifts

This requires a solvent-aware model and paired measurements of the same molecule
in source and target solvents. NMRNet++ offers a solvent-aware H/C configuration;
TransPeakNet predicts solvent-conditioned H/C HSQC spectra. Neither README alone
establishes a validated measured-spectrum-to-measured-spectrum transfer adapter.

[MagNET](https://github.com/ekwan/MagNET) is an additional released H/C candidate:
its explicit-solvent model supports chloroform, benzene, methanol and water, but
requires solvent-containing MD geometries. Its standard `predict_shifts` example
uses AIMNet2-optimized geometry and chloroform correction. It does not support
B/Si-containing inputs. Code/weights were not found locally.

For an atom-mapped paired benchmark, a possible protocol to evaluate is
`delta_target = delta_source + f(structure, target_solvent) - f(structure, source_solvent)`.
This is a proposed fixed inference protocol, not a reported result or a fitted
correction. Model-specific geometry requirements and paired data must be met
before enabling it.

The cross-solvent reference baseline is now implemented and evaluated on 32 distinct molecules; it does not replace the missing neural checkpoints. See the delivery document for the exact method, errors, unchanged-shift comparison and reference exclusion rules.
