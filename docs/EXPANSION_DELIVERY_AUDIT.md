# Pretrained expansion delivery audit

This is an evidence inventory, not a declaration of completed delivery. No training, fine-tuning or fitted label calibration was performed in this expansion. Model weights and complete datasets remain external to this repository.

| Requirement | Evidence in this repository | Current assessment |
| --- | --- | --- |
| Repair structure → 19F/31P | `results/fp_alignment_audit_20261115.json`, `results/fp_frozen_fresh_diagnostic_20261115.json`, `results/fp_primary_score_gate_20261116.json` | Input/target mismatch repaired by fresh frozen inference. Available solid-state weights lack a verified solution-shift reference. Formal solution accuracy remains unestablished; primary scores are skipped. |
| Follow Xinyu's Vib2Mol protocol | `results/vib2mol_xinyu_random64_20261116.json`, `openmolspec_bench/runner.py`, `openmolspec_ui/inference.py` | Four-modal normalization, beam=10, canonical valid deduplication and ITM reranking implemented. Random 64-sample offline run complete. Online protocol regression tests pass; one real online sample completed direct beam=10 generation and ITM reranking, returning one valid unique candidate. See `results/online_vib2mol_protocol_20261116.json`; this is execution evidence, not an accuracy benchmark. |
| Audit HOMO–LUMO gap | `results/gap_protocol_random128_20261116.json` | Complete-input frozen inference MAE 0.131446 eV on 128 random distinct structures; fixed training-mean baseline 0.899940 eV. Missing-channel results separately reported. |
| Add vibrational forward task | `results/vibrational_forward_paired_logs_20261116.json` | Two paired original-geometry examples run; not a held-out accuracy benchmark. |
| Remaining B/Si forward tasks | `results/bsi_frozen_diagnostic_20261116.json` | Liquid All-nucleus NMRNet frozen inference completed: 32 distinct molecules each, B MAE 8.684532 ppm / Si 56.133585 ppm. All parameters loaded and labels aligned. Diagnostic only: nucleus-specific training coverage and experimental assignment provenance unverified; primary adapter remains skipped. |
| Atom assignment | `results/assignment_carbon32_20261116.json` | Direct frozen H/C NMRNet plus symmetry-aware site matching implemented. Carbon run: 32 molecules, 488 matches, coverage 0.939238, residual 0.899131 ppm. Experimental assignment accuracy remains unmeasured. |
| Solvent transfer | `results/solvent_transfer_reference32_20261116.json` | Reference-retrieval baseline completed on 32 molecules / 296 atom pairs, with query connectivity excluded. H/C MAE 0.137628/1.094286 ppm. Dedicated neural model still missing; baseline not consistently better than unchanged shifts. |
| Formula prediction and spectroscopy QA | `openmolspec_bench/molspect.py` | Local complete MolSpect-7B zero-shot experiment completed: four distinct molecules, QA 0/4 and formula exact match 0/4. See `results/molspect_zeroshot_formula_qa_20261116.json`. These are diagnostic scores under an unverified checkpoint/prompt pairing, not official-model reproduction or a validated primary task interface. |
| MAGMa annotation | `results/magma_real_test_verified_20261115.json` | Original algorithm on two distinct molecules; 1534 fragment index checks, zero errors. Index basis is engine_smiles. Algorithm candidates do not establish experimental mechanisms. |
| GLACIER/ICEBERG on our molecules | `results/ms_glacier_32_molecules_20261116.json`, `results/ms_iceberg_32_molecules_20261116.json` | Direct frozen author inference; each run scores 31 distinct molecules and skips one missing-condition record. Full observed spectra used, so scoring differs from author protocols that filter unmatched peaks. Training overlap not independently established. |
| Official SpectraLLM pretrained test | `documentation/tasks/multispectral-spectrallm-generation.md` | Complete official 32B weights are unavailable locally; older 7B adapter's specified base is missing. Local MolSpect experiment is separately identified. |
| Detailed English/Chinese task documentation | `documentation/tasks/`, `scripts/build_bilingual_docs.py` | 34 task definitions, paired language pages, examples and recorded result provenance. Source consistency and links checked. |
| Notebook demonstrations | `documentation/notebooks/`, `results/doc_notebook_execution.json` | 68 notebook files contain executed plain-Python demonstration outputs. IPC restrictions prevent Jupyter kernel validation. These demonstrations display recorded inference results; they do not rerun models. |
| Read the Docs hosting | `.readthedocs.yaml`, `mkdocs.yml`, `requirements-docs.txt` | Configuration prepared. Custom HTML builder replaces the publication dependency on MkDocs plugins: 150 HTML pages, 68 previews, language switches and downloads validated locally. Hosted build/live URL remain unverified because network/account access is unavailable. |
| Frontend navigation | `openmolspec_ui/portal.py`, `app.py` | Tool, Dataset Download, Prediction (Online), Full documentation routes implemented and AppTest checked. External documentation jump needs a verified OPENMOLSPEC_DOCS_URL after publication. |
| Dataset Download | `openmolspec_ui/portal.py`, `documentation/datasets.md` | Original distribution links and downloadable input templates/catalog provided. Public OpenMolSpec full-dataset URL remains unavailable; optional OPENMOLSPEC_DATASET_URL is not presented as a published release. |
| GitHub push | Local commits `c5e68d2`, `38120c3` | Push to origin/release/openmolspec-v1 attempted and failed because proxy DNS does not resolve. No remote publication claimed. |

## Scope revision — 2026-11-16

SpectraLLM, formula prediction and spectroscopy QA are deferred by the user. Their archived evidence above is historical and they are no longer delivery blockers. The catalog retains 34 definitions, with 31 enabled. B/Si, atom assignment, solvent transfer, website and Read the Docs remain active. See [model source audit](ACTIVE_MODEL_FOLLOWUP.md) for concrete candidate models and provenance.

## Verification scope

- 12 benchmark checks and 6 MS adapter checks passed for evaluation mechanics.
- 3 online-generation regression checks cover rank failure propagation, normalization mismatch and candidate/score alignment; 2 configuration checks passed.
- Streamlit AppTest verified the four navigation routes and MS form; the later generation-page check verifies the 1–10 candidate range.
- Bilingual generator consistency and 82 Markdown pages' local navigation/link checks passed.
- Notebook evidence records the execution engine, source hashes and evaluation index hash. Passing notebook cells does not prove MkDocs or Read the Docs rendering.
- Offline checks do not prove remote publication, dataset independence, full-benchmark accuracy or scientific validity outside the stated model/input domains.

## External requirements still missing

Network/DNS recovery is required for dependencies, official model downloads and GitHub push. Read the Docs needs an accessible project/account connection and a successful hosted build before a real URL can be reported. Compatible F/P references, validated B/Si training coverage, experimental atom-assignment ground truth and specialized neural solvent checkpoints remain scientific/model requirements. The executable assignment and reference-transfer baseline do not fill these accuracy requirements; no missing weights will be synthesized by training.

## Scope-revision checks

The 12 benchmark checks passed again. All three deferred tasks were directly verified to skip before model/data access. The 68 notebook demonstrations were re-executed and their hashes verified against the new B/Si evidence index. Catalog and bilingual-source consistency, local Markdown links and whitespace checks passed. These checks do not establish hosted publication.

Latest functional delivery and reproducible commands: [REMAINING_TASKS_DELIVERY.md](REMAINING_TASKS_DELIVERY.md). B/Si, assignment and reference-transfer shared CLI checks passed; real Streamlit button tests for both new pages passed.
