# Task catalog

| ID | Task | Adapter |
| --- | --- | --- |
| `nmr.forward.1H` | [Structure to 1H NMR](nmr-forward-1H.md) | `nmrnet_predictions` |
| `nmr.forward.13C` | [Structure to 13C NMR](nmr-forward-13C.md) | `nmrnet_predictions` |
| `nmr.forward.19F` | [Structure to 19F NMR: alignment audit](nmr-forward-19F.md) | `nmrnet_hetero_predictions` |
| `nmr.forward.31P` | [Structure to 31P NMR: alignment audit](nmr-forward-31P.md) | `nmrnet_hetero_predictions` |
| `nmr.forward.11B` | [Structure to 11B NMR: frozen diagnostic](nmr-forward-11B.md) | `nmrnet_bsi_diagnostic` |
| `nmr.forward.29Si` | [Structure to 29Si NMR: frozen diagnostic](nmr-forward-29Si.md) | `nmrnet_bsi_diagnostic` |
| `nmr.retrieval.h.s2m` | [NMR retrieval: H, s2m](nmr-retrieval-h-s2m.md) | `spec2struct_alignment` |
| `nmr.retrieval.h.m2s` | [NMR retrieval: H, m2s](nmr-retrieval-h-m2s.md) | `spec2struct_alignment` |
| `nmr.generation.h` | [NMR-to-SMILES generation: H](nmr-generation-h.md) | `spec2struct_generation` |
| `nmr.retrieval.c.s2m` | [NMR retrieval: C, s2m](nmr-retrieval-c-s2m.md) | `spec2struct_alignment` |
| `nmr.retrieval.c.m2s` | [NMR retrieval: C, m2s](nmr-retrieval-c-m2s.md) | `spec2struct_alignment` |
| `nmr.generation.c` | [NMR-to-SMILES generation: C](nmr-generation-c.md) | `spec2struct_generation` |
| `nmr.retrieval.hc.s2m` | [NMR retrieval: HC, s2m](nmr-retrieval-hc-s2m.md) | `spec2struct_alignment` |
| `nmr.retrieval.hc.m2s` | [NMR retrieval: HC, m2s](nmr-retrieval-hc-m2s.md) | `spec2struct_alignment` |
| `nmr.generation.hc` | [NMR-to-SMILES generation: HC](nmr-generation-hc.md) | `spec2struct_generation` |
| `vibrational.gap.ir` | [HOMO–LUMO gap prediction: IR](vibrational-gap-ir.md) | `studio_gap` |
| `vibrational.gap.raman` | [HOMO–LUMO gap prediction: RAMAN](vibrational-gap-raman.md) | `studio_gap` |
| `vibrational.gap.ir_raman` | [HOMO–LUMO gap prediction: IR_RAMAN](vibrational-gap-ir_raman.md) | `studio_gap` |
| `vibrational.gap.ir_raman_hc` | [HOMO–LUMO gap prediction: IR + Raman + H/C](vibrational-gap-ir_raman_hc.md) | `studio_gap` |
| `vibrational.forward` | [Conformer to IR and Raman](vibrational-forward.md) | `studio_vibrational_forward` |
| `vibrational.retrieval` | [Vib2Mol bidirectional retrieval with IR/Raman only](vibrational-retrieval.md) | `vib2mol_retrieval` |
| `vibrational.generation` | [Vib2Mol generation with IR/Raman only](vibrational-generation.md) | `vib2mol_generation` |
| `nmr.assignment` | [H/C peak-to-atom assignment](nmr-assignment.md) | `nmrnet_atom_assignment` |
| `nmr.solvent_transfer` | [H/C cross-solvent transfer: experimental-reference baseline](nmr-solvent_transfer.md) | `nmr_solvent_reference` |
| `nmr.formula` | [Molecular formula prediction](nmr-formula.md) | `unavailable` |
| `spectroscopy.qa` | [Spectroscopy QA](spectroscopy-qa.md) | `unavailable` |
| `spectroscopy.reranking` | [Vib2Mol candidate reranking with IR/Raman only](spectroscopy-reranking.md) | `vib2mol_reranking` |
| `vibrational.retrieval.hc` | [Vib2Mol bidirectional retrieval with H/C](vibrational-retrieval-hc.md) | `vib2mol_retrieval` |
| `vibrational.generation.hc` | [Vib2Mol generation with H/C](vibrational-generation-hc.md) | `vib2mol_generation` |
| `spectroscopy.reranking.hc` | [Vib2Mol candidate reranking with H/C](spectroscopy-reranking-hc.md) | `vib2mol_reranking` |
| `ms.forward.glacier` | [Molecule to MS/MS with GLACIER](ms-forward-glacier.md) | `ms_pretrained_glacier` |
| `ms.forward.iceberg` | [Molecule to MS/MS with ICEBERG](ms-forward-iceberg.md) | `ms_pretrained_iceberg` |
| `ms.annotation.magma` | [MS/MS peak annotation with MAGMa](ms-annotation-magma.md) | `magma_algorithm` |
| `multispectral.spectrallm.generation` | [SpectraLLM structure generation](multispectral-spectrallm-generation.md) | `unavailable` |
