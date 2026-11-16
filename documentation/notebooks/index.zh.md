# 已执行 notebook

每个启用任务的 notebook 都有真实输入输出、运行指标、可执行分析和结果图。它们分析已保存的推理，不是列出“可能得到什么”的占位示例。

[Dataset distributions / 数据分布](datasets-overview.ipynb)

## 核磁共振 NMR

- [结构 → 1H 峰列表](nmr-forward-1H.ipynb)
- [结构 → 13C 峰列表](nmr-forward-13C.ipynb)
- [结构 → 19F 峰列表](nmr-forward-19F.ipynb)
- [结构 → 31P 峰列表](nmr-forward-31P.ipynb)
- [结构 → 11B 峰列表](nmr-forward-11B.ipynb)
- [结构 → 29Si 峰列表](nmr-forward-29Si.ipynb)
- [谱图 → 结构检索 · H](nmr-retrieval-h-s2m.ipynb)
- [结构 → 谱图检索 · H](nmr-retrieval-h-m2s.ipynb)
- [谱图 → SMILES · H](nmr-generation-h.ipynb)
- [谱图 → 结构检索 · C](nmr-retrieval-c-s2m.ipynb)
- [结构 → 谱图检索 · C](nmr-retrieval-c-m2s.ipynb)
- [谱图 → SMILES · C](nmr-generation-c.ipynb)
- [谱图 → 结构检索 · HC](nmr-retrieval-hc-s2m.ipynb)
- [结构 → 谱图检索 · HC](nmr-retrieval-hc-m2s.ipynb)
- [谱图 → SMILES · HC](nmr-generation-hc.ipynb)
- [H/C 峰 → 原子指认](nmr-assignment.ipynb)
- [H/C 跨溶剂位移 · 参考检索基线](nmr-solvent_transfer.ipynb)

## 质谱 MS

- [分子 → MS/MS（GLACIER）](ms-forward-glacier.ipynb)
- [分子 → MS/MS（ICEBERG）](ms-forward-iceberg.ipynb)
- [MS/MS 峰 → MAGMa 候选碎片标注](ms-annotation-magma.ipynb)

## 红外 / 拉曼 IR / Raman

- [IR → HOMO–LUMO gap](vibrational-gap-ir.ipynb)
- [RAMAN → HOMO–LUMO gap](vibrational-gap-raman.ipynb)
- [IR_RAMAN → HOMO–LUMO gap](vibrational-gap-ir_raman.ipynb)
- [构象 → IR / Raman](vibrational-forward.ipynb)
- [IR / Raman → 结构检索](vibrational-retrieval.ipynb)
- [IR / Raman → SMILES](vibrational-generation.ipynb)
- [谱图 + 候选结构 → 重排](spectroscopy-reranking.ipynb)

## 多谱联合

- [IR + Raman + H/C NMR → HOMO–LUMO gap](vibrational-gap-ir_raman_hc.ipynb)
- [IR + Raman + H/C → 结构检索](vibrational-retrieval-hc.ipynb)
- [IR + Raman + H/C → SMILES（Xinyu 协议）](vibrational-generation-hc.ipynb)
- [IR + Raman + H/C + 候选 → ITM 重排](spectroscopy-reranking-hc.ipynb)

## 暂不推进

- [谱图 → 分子式](nmr-formula.ipynb)
- [谱学问答 / 推理](spectroscopy-qa.ipynb)
- [多谱 → 结构（SpectraLLM）](multispectral-spectrallm-generation.ipynb)
