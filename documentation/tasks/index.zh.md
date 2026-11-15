# 任务目录

| ID | 任务 | 适配器 |
| --- | --- | --- |
| `nmr.forward.1H` | [结构 → 1H 峰列表](nmr-forward-1H.md) | `nmrnet_predictions` |
| `nmr.forward.13C` | [结构 → 13C 峰列表](nmr-forward-13C.md) | `nmrnet_predictions` |
| `nmr.forward.19F` | [结构 → 19F 峰列表](nmr-forward-19F.md) | `nmrnet_hetero_predictions` |
| `nmr.forward.31P` | [结构 → 31P 峰列表](nmr-forward-31P.md) | `nmrnet_hetero_predictions` |
| `nmr.forward.11B` | [结构 → 11B 峰列表](nmr-forward-11B.md) | `unavailable` |
| `nmr.forward.29Si` | [结构 → 29Si 峰列表](nmr-forward-29Si.md) | `unavailable` |
| `nmr.retrieval.h.s2m` | [谱图 → 结构检索 · H](nmr-retrieval-h-s2m.md) | `spec2struct_alignment` |
| `nmr.retrieval.h.m2s` | [结构 → 谱图检索 · H](nmr-retrieval-h-m2s.md) | `spec2struct_alignment` |
| `nmr.generation.h` | [谱图 → SMILES · H](nmr-generation-h.md) | `spec2struct_generation` |
| `nmr.retrieval.c.s2m` | [谱图 → 结构检索 · C](nmr-retrieval-c-s2m.md) | `spec2struct_alignment` |
| `nmr.retrieval.c.m2s` | [结构 → 谱图检索 · C](nmr-retrieval-c-m2s.md) | `spec2struct_alignment` |
| `nmr.generation.c` | [谱图 → SMILES · C](nmr-generation-c.md) | `spec2struct_generation` |
| `nmr.retrieval.hc.s2m` | [谱图 → 结构检索 · HC](nmr-retrieval-hc-s2m.md) | `spec2struct_alignment` |
| `nmr.retrieval.hc.m2s` | [结构 → 谱图检索 · HC](nmr-retrieval-hc-m2s.md) | `spec2struct_alignment` |
| `nmr.generation.hc` | [谱图 → SMILES · HC](nmr-generation-hc.md) | `spec2struct_generation` |
| `vibrational.gap.ir` | [IR → HOMO–LUMO gap](vibrational-gap-ir.md) | `studio_gap` |
| `vibrational.gap.raman` | [RAMAN → HOMO–LUMO gap](vibrational-gap-raman.md) | `studio_gap` |
| `vibrational.gap.ir_raman` | [IR_RAMAN → HOMO–LUMO gap](vibrational-gap-ir_raman.md) | `studio_gap` |
| `vibrational.gap.ir_raman_hc` | [IR + Raman + H/C NMR → HOMO–LUMO gap](vibrational-gap-ir_raman_hc.md) | `studio_gap` |
| `vibrational.forward` | [构象 → IR / Raman](vibrational-forward.md) | `studio_vibrational_forward` |
| `vibrational.retrieval` | [IR / Raman → 结构检索](vibrational-retrieval.md) | `vib2mol_retrieval` |
| `vibrational.generation` | [IR / Raman → SMILES](vibrational-generation.md) | `vib2mol_generation` |
| `nmr.assignment` | [峰 → 原子指认](nmr-assignment.md) | `unavailable` |
| `nmr.solvent_transfer` | [跨溶剂化学位移迁移](nmr-solvent_transfer.md) | `unavailable` |
| `nmr.formula` | [谱图 → 分子式](nmr-formula.md) | `unavailable` |
| `spectroscopy.qa` | [谱学问答 / 推理](spectroscopy-qa.md) | `unavailable` |
| `spectroscopy.reranking` | [谱图 + 候选结构 → 重排](spectroscopy-reranking.md) | `vib2mol_reranking` |
| `vibrational.retrieval.hc` | [IR + Raman + H/C → 结构检索](vibrational-retrieval-hc.md) | `vib2mol_retrieval` |
| `vibrational.generation.hc` | [IR + Raman + H/C → SMILES（Xinyu 协议）](vibrational-generation-hc.md) | `vib2mol_generation` |
| `spectroscopy.reranking.hc` | [IR + Raman + H/C + 候选 → ITM 重排](spectroscopy-reranking-hc.md) | `vib2mol_reranking` |
| `ms.forward.glacier` | [分子 → MS/MS（GLACIER）](ms-forward-glacier.md) | `ms_pretrained_glacier` |
| `ms.forward.iceberg` | [分子 → MS/MS（ICEBERG）](ms-forward-iceberg.md) | `ms_pretrained_iceberg` |
| `ms.annotation.magma` | [MS/MS 峰 → MAGMa 候选碎片标注](ms-annotation-magma.md) | `magma_algorithm` |
| `multispectral.spectrallm.generation` | [多谱 → 结构（SpectraLLM）](multispectral-spectrallm-generation.md) | `unavailable` |
