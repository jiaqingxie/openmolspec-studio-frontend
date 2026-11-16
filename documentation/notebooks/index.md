# Executed notebooks

Each active task notebook shows actual input/output data, a run table, executable analysis and a result figure. These notebooks analyze saved inference; they are not placeholders for hypothetical results.

[SDK: actual NMR inference](sdk-inference.ipynb) · [SDK: training preflight](sdk-training-preflight.ipynb)

[Dataset distributions / 数据分布](datasets-overview.ipynb)

## NMR

- [Structure to 1H NMR](nmr-forward-1H.ipynb)
- [Structure to 13C NMR](nmr-forward-13C.ipynb)
- [Structure to 19F NMR: alignment audit](nmr-forward-19F.ipynb)
- [Structure to 31P NMR: alignment audit](nmr-forward-31P.ipynb)
- [Structure to 11B NMR: frozen diagnostic](nmr-forward-11B.ipynb)
- [Structure to 29Si NMR: frozen diagnostic](nmr-forward-29Si.ipynb)
- [NMR retrieval: H, s2m](nmr-retrieval-h-s2m.ipynb)
- [NMR retrieval: H, m2s](nmr-retrieval-h-m2s.ipynb)
- [NMR-to-SMILES generation: H](nmr-generation-h.ipynb)
- [NMR retrieval: C, s2m](nmr-retrieval-c-s2m.ipynb)
- [NMR retrieval: C, m2s](nmr-retrieval-c-m2s.ipynb)
- [NMR-to-SMILES generation: C](nmr-generation-c.ipynb)
- [NMR retrieval: HC, s2m](nmr-retrieval-hc-s2m.ipynb)
- [NMR retrieval: HC, m2s](nmr-retrieval-hc-m2s.ipynb)
- [NMR-to-SMILES generation: HC](nmr-generation-hc.ipynb)
- [H/C peak-to-atom assignment](nmr-assignment.ipynb)
- [H/C cross-solvent transfer: experimental-reference baseline](nmr-solvent_transfer.ipynb)

## Mass spectrometry

- [Molecule to MS/MS with GLACIER](ms-forward-glacier.ipynb)
- [Molecule to MS/MS with ICEBERG](ms-forward-iceberg.ipynb)
- [MS/MS peak annotation with MAGMa](ms-annotation-magma.ipynb)

## IR / Raman

- [HOMO–LUMO gap prediction: IR](vibrational-gap-ir.ipynb)
- [HOMO–LUMO gap prediction: RAMAN](vibrational-gap-raman.ipynb)
- [HOMO–LUMO gap prediction: IR_RAMAN](vibrational-gap-ir_raman.ipynb)
- [Conformer to IR and Raman](vibrational-forward.ipynb)
- [Vib2Mol bidirectional retrieval with IR/Raman only](vibrational-retrieval.ipynb)
- [Vib2Mol generation with IR/Raman only](vibrational-generation.ipynb)
- [Vib2Mol candidate reranking with IR/Raman only](spectroscopy-reranking.ipynb)

## Multimodal spectroscopy

- [HOMO–LUMO gap prediction: IR + Raman + H/C](vibrational-gap-ir_raman_hc.ipynb)
- [Vib2Mol bidirectional retrieval with H/C](vibrational-retrieval-hc.ipynb)
- [Vib2Mol generation with H/C](vibrational-generation-hc.ipynb)
- [Vib2Mol candidate reranking with H/C](spectroscopy-reranking-hc.ipynb)

## Deferred tasks

- [Molecular formula prediction](nmr-formula.ipynb)
- [Spectroscopy QA](spectroscopy-qa.ipynb)
- [SpectraLLM structure generation](multispectral-spectrallm-generation.ipynb)
