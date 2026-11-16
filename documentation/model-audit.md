# Model suitability and potential fine-tuning

This review covers every enabled task. Successful execution, reasonable task/model pairing, and independently validated accuracy are separate findings. No training, fine-tuning or fitted offset was performed.

## B and Si: current verdict

| Nucleus | Molecules / atoms | MAE (ppm) | Mean signed error (ppm) | Pearson r | R² |
| --- | ---: | ---: | ---: | ---: | ---: |
| B | 32 / 32 | 8.6845 | +2.3668 | 0.2174 | -0.0068 |
| Si | 32 / 32 | 56.1336 | +56.1336 | 0.2385 | -13.6167 |

The sole B/Si atom in each evaluated structure matches the saved label index; current pool labels and all checkpoint parameters were checked. That fixes alignment, not scientific quality. B predictions have weak correlation; Si predictions are all too high. Neither is presented as a validated accurate solution predictor.

The current prepared B pool has **121** canonical structures shared between train and validation; Si has **10**. These are overlaps in the prepared data pool, not proof of overlap with the released model’s training set. All pool rows have blank solvent fields. A B training-pool label reaches **3085 ppm**, requiring raw-source/unit review before any future training. The pool contents match `data_hetero3` by structure, coordinates, labels and masks; old `data_hetero2` preparation scripts do not describe the current pool.

The [official NMRNet++ archive](https://zenodo.org/records/18232165) matches the downloaded checkpoint archive checksum; its identifiable trained checkpoints are H/C only. The B/Si diagnostic uses liquid All-nucleus **NMRNet**, not verified B/Si-specific NMRNet++ weights.

## Every active task

| Task | Current interpretation and next step |
| --- | --- |
| [nmr.forward.1H](tasks/nmr-forward-1H.md) | Reasonable H/C frozen-model baseline; reported errors use peak matching, not experimental atom assignments. Verify data overlap and solvent coverage. |
| [nmr.forward.13C](tasks/nmr-forward-13C.md) | Reasonable H/C frozen-model baseline; reported errors use peak matching, not experimental atom assignments. Verify data overlap and solvent coverage. |
| [nmr.forward.19F](tasks/nmr-forward-19F.md) | Current solid-state weights are not validated for solution shifts. Resolve domain/reference compatibility before any fine-tuning decision. |
| [nmr.forward.31P](tasks/nmr-forward-31P.md) | Current solid-state weights are not validated for solution shifts. Resolve domain/reference compatibility before any fine-tuning decision. |
| [nmr.forward.11B](tasks/nmr-forward-11B.md) | Diagnostic only: 8.68 ppm MAE, correlation 0.217. Weak discrimination and unaudited coverage; nucleus-specific adaptation is a candidate after data repair. |
| [nmr.forward.29Si](tasks/nmr-forward-29Si.md) | Unsuitable as an accurate solution predictor: 56.13 ppm MAE, all 32 predictions biased high. Clean data and obtain compatible weights before considering fine-tuning. |
| [nmr.retrieval.h.s2m](tasks/nmr-retrieval-h-s2m.md) | Input/output pairing is appropriate; the 32-candidate smoke pool is small. Validate a larger independent library before judging generalization or fine-tuning. |
| [nmr.retrieval.h.m2s](tasks/nmr-retrieval-h-m2s.md) | Input/output pairing is appropriate; the 32-candidate smoke pool is small. Validate a larger independent library before judging generalization or fine-tuning. |
| [nmr.generation.h](tasks/nmr-generation-h.md) | Strong dataset dependence: zero exact matches on the 32-example patent and NMRGym checks. Prioritize a clean external test and parsing/token coverage audit; then consider domain fine-tuning. |
| [nmr.retrieval.c.s2m](tasks/nmr-retrieval-c-s2m.md) | Input/output pairing is appropriate; the 32-candidate smoke pool is small. Validate a larger independent library before judging generalization or fine-tuning. |
| [nmr.retrieval.c.m2s](tasks/nmr-retrieval-c-m2s.md) | Input/output pairing is appropriate; the 32-candidate smoke pool is small. Validate a larger independent library before judging generalization or fine-tuning. |
| [nmr.generation.c](tasks/nmr-generation-c.md) | Strong dataset dependence: zero exact matches on the 32-example patent and NMRGym checks. Prioritize a clean external test and parsing/token coverage audit; then consider domain fine-tuning. |
| [nmr.retrieval.hc.s2m](tasks/nmr-retrieval-hc-s2m.md) | Input/output pairing is appropriate; the 32-candidate smoke pool is small. Validate a larger independent library before judging generalization or fine-tuning. |
| [nmr.retrieval.hc.m2s](tasks/nmr-retrieval-hc-m2s.md) | Input/output pairing is appropriate; the 32-candidate smoke pool is small. Validate a larger independent library before judging generalization or fine-tuning. |
| [nmr.generation.hc](tasks/nmr-generation-hc.md) | Strong dataset dependence: zero exact matches on the 32-example patent and NMRGym checks. Prioritize a clean external test and parsing/token coverage audit; then consider domain fine-tuning. |
| [vibrational.gap.ir](tasks/vibrational-gap-ir.md) | Missing-channel ablation of a four-modal checkpoint. Poor scores do not validate a stand-alone IR/Raman model; use compatible unimodal weights or plan separate adaptation. |
| [vibrational.gap.raman](tasks/vibrational-gap-raman.md) | Missing-channel ablation of a four-modal checkpoint. Poor scores do not validate a stand-alone IR/Raman model; use compatible unimodal weights or plan separate adaptation. |
| [vibrational.gap.ir_raman](tasks/vibrational-gap-ir_raman.md) | Missing-channel ablation of a four-modal checkpoint. Poor scores do not validate a stand-alone IR/Raman model; use compatible unimodal weights or plan separate adaptation. |
| [vibrational.gap.ir_raman_hc](tasks/vibrational-gap-ir_raman_hc.md) | Complete inputs and units are aligned; 0.131446 eV MAE beats the 0.899940 eV mean baseline on 128 samples. Broader independent evaluation is the next step, not immediate fine-tuning. |
| [vibrational.forward](tasks/vibrational-forward.md) | Correct Xinyu Hessian/response route and paired geometry. Two examples demonstrate execution only; evaluate a held-out geometry set before adaptation. |
| [vibrational.retrieval](tasks/vibrational-retrieval.md) | Missing-channel ablation of a four-modal checkpoint. Poor scores do not validate a stand-alone IR/Raman model; use compatible unimodal weights or plan separate adaptation. |
| [vibrational.generation](tasks/vibrational-generation.md) | Missing-channel ablation of a four-modal checkpoint. Poor scores do not validate a stand-alone IR/Raman model; use compatible unimodal weights or plan separate adaptation. |
| [nmr.assignment](tasks/nmr-assignment.md) | Reasonable candidate pipeline for a known structure; no experimental assignment accuracy yet. Validate atom labels and symmetry before proposing fine-tuning. |
| [nmr.solvent_transfer](tasks/nmr-solvent_transfer.md) | Executable reference baseline; H does not improve on unchanged shifts. A solvent-conditioned model and independent paired data are still needed. |
| [spectroscopy.reranking](tasks/spectroscopy-reranking.md) | Missing-channel ablation of a four-modal checkpoint. Poor scores do not validate a stand-alone IR/Raman model; use compatible unimodal weights or plan separate adaptation. |
| [vibrational.retrieval.hc](tasks/vibrational-retrieval-hc.md) | Complete four-modal protocol is appropriate. Candidate-pool retrieval and explicit-pool ITM are not open-world generation; validate larger held-out pools. |
| [vibrational.generation.hc](tasks/vibrational-generation-hc.md) | Author generation protocol is implemented. ITM reranking lowers top-1 from 0.75 to 0.6875 on the same 64 examples; validate this regression before adapting the ranker. |
| [spectroscopy.reranking.hc](tasks/spectroscopy-reranking-hc.md) | Complete four-modal protocol is appropriate. Candidate-pool retrieval and explicit-pool ITM are not open-world generation; validate larger held-out pools. |
| [ms.forward.glacier](tasks/ms-forward-glacier.md) | Appropriate author model interface and explicit conditions; 31 scored spectra are insufficient for a broad accuracy claim. Protocol/overlap audit precedes fine-tuning. |
| [ms.forward.iceberg](tasks/ms-forward-iceberg.md) | Appropriate author model interface and explicit conditions; 31 scored spectra are insufficient for a broad accuracy claim. Protocol/overlap audit precedes fine-tuning. |
| [ms.annotation.magma](tasks/ms-annotation-magma.md) | Algorithmic annotation, not a trainable neural model. Improve matching and validation rather than propose fine-tuning. |

## Potential future fine-tuning — ordered by evidence

| Priority | Task family | Prerequisite / reason |
| --- | --- | --- |
| 1 | 29Si / 11B | Compatible nucleus-specific weights first; repair structure leakage, recover solvent/reference metadata and verify raw labels. If no suitable released weights exist, nucleus-specific adaptation is justified. |
| 2 | NMR → SMILES (H / C / H+C) | Strong cross-dataset failures justify an adaptation study after formula parsing, tokenizer coverage and independent scaffold tests are verified. |
| 3 | Cross-solvent transfer | First obtain a solvent-conditioned model and clean paired, atom-mapped data. Current nearest-reference baseline is not a neural checkpoint that can be fine-tuned. |
| 4 | IR/Raman-only gap / generation / retrieval | If missing-NMR use is a product requirement, acquire a checkpoint trained for that input or plan missing-modality adaptation. Current results are ablations. |
| 5 | Vib2Mol ITM reranker | Investigate the observed same-sample top-1 regression; calibrating or retraining on the test set is prohibited. Use a separate development set for any later adaptation. |

**Not yet a fine-tuning conclusion:** F/P need compatible solution/reference definitions first; assignment needs experimental ground truth; MS and conformer→IR/Raman need larger independent evaluations. MAGMa is an algorithm. Full-input gap has a useful current baseline. SpectraLLM, formula prediction and QA remain deferred.

[Download B/Si audit](assets/reports/bsi_model_review_20261117.json) · [Official archive inventory](assets/reports/nmrnetpp_release_inventory_20261117.json)

**Evaluation limitation:** molecular overlap with checkpoint-recorded training data is confirmed for several NMR views. The final generator also has a training-file fingerprint discrepancy. These runs do not establish independent generalization.  [Training-history audit / 训练历史审计](training-overlap.md)
