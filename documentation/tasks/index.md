# Tasks by spectroscopy family

Choose the kind of evidence you have: NMR peaks, MS/MS peaks, a molecular geometry, or several spectral modalities together. Each task page explains the question, input fields, output fields and a real recorded example.

## [NMR](nmr.md)

| Task / 任务 | Spectroscopy / 谱型 | Definition / 定义 |
| --- | --- | --- |
| `nmr.forward.1H` | 1H | [Structure to 1H NMR](nmr-forward-1H.md) |
| `nmr.forward.13C` | 13C | [Structure to 13C NMR](nmr-forward-13C.md) |
| `nmr.forward.19F` | 19F | [Structure to 19F NMR: alignment audit](nmr-forward-19F.md) |
| `nmr.forward.31P` | 31P | [Structure to 31P NMR: alignment audit](nmr-forward-31P.md) |
| `nmr.forward.11B` | 11B | [Structure to 11B NMR: frozen diagnostic](nmr-forward-11B.md) |
| `nmr.forward.29Si` | 29Si | [Structure to 29Si NMR: frozen diagnostic](nmr-forward-29Si.md) |
| `nmr.retrieval.h.s2m` | 1H | [NMR retrieval: H, s2m](nmr-retrieval-h-s2m.md) |
| `nmr.retrieval.h.m2s` | 1H | [NMR retrieval: H, m2s](nmr-retrieval-h-m2s.md) |
| `nmr.generation.h` | 1H | [NMR-to-SMILES generation: H](nmr-generation-h.md) |
| `nmr.retrieval.c.s2m` | 13C | [NMR retrieval: C, s2m](nmr-retrieval-c-s2m.md) |
| `nmr.retrieval.c.m2s` | 13C | [NMR retrieval: C, m2s](nmr-retrieval-c-m2s.md) |
| `nmr.generation.c` | 13C | [NMR-to-SMILES generation: C](nmr-generation-c.md) |
| `nmr.retrieval.hc.s2m` | 1H, 13C | [NMR retrieval: HC, s2m](nmr-retrieval-hc-s2m.md) |
| `nmr.retrieval.hc.m2s` | 1H, 13C | [NMR retrieval: HC, m2s](nmr-retrieval-hc-m2s.md) |
| `nmr.generation.hc` | 1H, 13C | [NMR-to-SMILES generation: HC](nmr-generation-hc.md) |
| `nmr.assignment` | 1H, 13C | [H/C peak-to-atom assignment](nmr-assignment.md) |
| `nmr.solvent_transfer` | 1H, 13C | [H/C cross-solvent transfer: experimental-reference baseline](nmr-solvent_transfer.md) |

## [Mass spectrometry](ms.md)

| Task / 任务 | Spectroscopy / 谱型 | Definition / 定义 |
| --- | --- | --- |
| `ms.forward.glacier` | MS/MS | [Molecule to MS/MS with GLACIER](ms-forward-glacier.md) |
| `ms.forward.iceberg` | MS/MS | [Molecule to MS/MS with ICEBERG](ms-forward-iceberg.md) |
| `ms.annotation.magma` | MS/MS | [MS/MS peak annotation with MAGMa](ms-annotation-magma.md) |

## [IR / Raman](vibrational.md)

| Task / 任务 | Spectroscopy / 谱型 | Definition / 定义 |
| --- | --- | --- |
| `vibrational.gap.ir` | IR | [HOMO–LUMO gap prediction: IR](vibrational-gap-ir.md) |
| `vibrational.gap.raman` | RAMAN | [HOMO–LUMO gap prediction: RAMAN](vibrational-gap-raman.md) |
| `vibrational.gap.ir_raman` | IR, RAMAN | [HOMO–LUMO gap prediction: IR_RAMAN](vibrational-gap-ir_raman.md) |
| `vibrational.forward` | IR, Raman | [Conformer to IR and Raman](vibrational-forward.md) |
| `vibrational.retrieval` | IR, Raman | [Vib2Mol bidirectional retrieval with IR/Raman only](vibrational-retrieval.md) |
| `vibrational.generation` | IR, Raman | [Vib2Mol generation with IR/Raman only](vibrational-generation.md) |
| `spectroscopy.reranking` | IR, Raman | [Vib2Mol candidate reranking with IR/Raman only](spectroscopy-reranking.md) |

## [Multimodal spectroscopy](multimodal.md)

| Task / 任务 | Spectroscopy / 谱型 | Definition / 定义 |
| --- | --- | --- |
| `vibrational.gap.ir_raman_hc` | IR, Raman, 1H, 13C | [HOMO–LUMO gap prediction: IR + Raman + H/C](vibrational-gap-ir_raman_hc.md) |
| `vibrational.retrieval.hc` | IR, Raman, 1H, 13C | [Vib2Mol bidirectional retrieval with H/C](vibrational-retrieval-hc.md) |
| `vibrational.generation.hc` | IR, Raman, 1H, 13C | [Vib2Mol generation with H/C](vibrational-generation-hc.md) |
| `spectroscopy.reranking.hc` | IR, Raman, 1H, 13C | [Vib2Mol candidate reranking with H/C](spectroscopy-reranking-hc.md) |

## [Deferred tasks](deferred.md)

| Task / 任务 | Spectroscopy / 谱型 | Definition / 定义 |
| --- | --- | --- |
| `nmr.formula` | 1H, 13C | [Molecular formula prediction](nmr-formula.md) |
| `spectroscopy.qa` | NMR, IR, Raman | [Spectroscopy QA](spectroscopy-qa.md) |
| `multispectral.spectrallm.generation` | IR, Raman, NMR, MS/MS | [SpectraLLM structure generation](multispectral-spectrallm-generation.md) |
