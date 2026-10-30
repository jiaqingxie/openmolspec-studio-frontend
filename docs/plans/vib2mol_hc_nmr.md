# Vib2Mol: IR/Raman + H/C NMR

## Model

The original Vib2Mol six-layer spectral encoder, molecular encoder/decoder and
projection dimension are retained (d_model=768, d_proj=256 by default).
**There is no 2+4 pooling and no added encoder.**

IR and Raman remain float32 min–max spectra on the shared 400–4000 cm⁻¹ axis.
Channel fusion precedes patchification (patch=8, 128 Vib tokens), with physical
wavenumber Fourier positional embeddings. H/C use separate median/IQR scaling
and independent Linear→SiLU→Linear embeddings, with no sequence positions.
The input sequence is CLS + Vib + C + H, with explicit NO_C/NO_H for empty sets.
Repeated per-atom shifts remain repeated tokens; no assignments or atom indices
are given to the model. This is computed, unassigned NMR, not an experimental
peak list with coupling/integral/equivalence-group labels.

All encoder layers and downstream cross-attention receive validity masks.
Matching retains global contrastive negatives and global ITM hard negatives;
differentiable exchanges now pad both molecular and spectral token lengths
across ranks and exchange the corresponding masks. Padding cannot become a peak.
Generation consumes the same mixed spectral memory for MLM, causal training,
greedy inference and beam search.

Maintained code lives in `benchmarks/models/vib2mol/{nmr_embedding,nmr_data,multimodal}.py`;
the pinned, ignored upstream tree is not modified. The launcher selects explicit
`build_ir_vib2mol`, `build_ir_raman_vib2mol`, or
`build_ir_raman_nmr_vib2mol` factories; `--hc-nmr` remains the full-modality
compatibility marker. The internal upstream task name stays
`ir-raman-kekule_smiles`, while the public modality is `ir-raman-nmr`.

The controlled modality ladder additionally exposes `ir-raman-hnmr` through
`build_ir_raman_hnmr_vib2mol`. It reads the same aligned 1M LMDB and the same
train-split NMR normalization artifact, but emits only ragged ¹H tokens. ¹³C
shifts are not collated, tokenized, or passed to the shared encoder. Its formal
configuration is
`benchmarks/configs/spectrum2structure/vib2mol_ir_raman_hnmr_ks1000k.yaml`.

## Data

Two new exports preserve the source SMILES/spectra, joining the completed
property H/C export by exact sample ID, split and InChIKey. Every record's spectra
must match the property export bit-for-bit. Original LMDBs are not overwritten.

| Root under benchmark_data | Train | Validation | Test |
|---|---:|---:|---:|
| release_v1_ks200k_hc_nmr_minmax | 200,000 | 10,390 | 20,390 |
| release_v1_ks1000k_hc_nmr_minmax | 1,000,000 | 10,390 | 20,390 |

Each root contains `vib2mol/openspec_{train,eval,test}.lmdb`, split index,
TMS reference and build summary. Only `state=completed` is usable.
The builder refuses existing outputs (use a new output path to reproduce):

```bash
python -m benchmarks.data.prepare_multimodal_vib2mol \
  --properties benchmark_data/spectrum_properties_ks200k_hc_nmr_minmax \
  --output benchmark_data/release_v1_ks200k_hc_nmr_minmax

python -m benchmarks.data.prepare_multimodal_vib2mol \
  --properties benchmark_data/spectrum_properties_ks1000k_hc_nmr_minmax \
  --output benchmark_data/release_v1_ks1000k_hc_nmr_minmax
```

Each training size fits H/C median/IQR from its own training split only. Formal
runs cache statistics at `vib2mol/.cache/nmr_median_iqr.json`; the work directory
also records `nmr_normalizer.json`. Debug fits the temporary training subset and
does not persist artifacts/cache. Checkpoints include scaler buffers, architecture
and NMR reference ID. Old pre-NMR checkpoints are rejected, even when upstream
requests non-strict loading. Evaluation restores the checkpoint's statistics.

## Training

Both sizes retain 312,500 optimizer steps **per stage**, step-wise cosine LR,
matching batch=64/GPU and generation batch=64/GPU. Matching was reduced from 128
after a four-GPU run exhausted rank 1 GPU memory. The addition of NMR increases
sequence length: recheck GPU memory; the old batch-size sweet spot is not guaranteed.

```bash
CUDA_VISIBLE_DEVICES=0,1 OMP_NUM_THREADS=1 \
python -m benchmarks run \
  --config benchmarks/configs/spectrum2structure/vib2mol_smoke_ddp2.yaml

CUDA_VISIBLE_DEVICES=0,1,2,3 OMP_NUM_THREADS=1 \
python -m benchmarks run \
  --config benchmarks/configs/spectrum2structure/vib2mol_ks200k.yaml

CUDA_VISIBLE_DEVICES=0,1,2,3 OMP_NUM_THREADS=1 \
python -m benchmarks run \
  --config benchmarks/configs/spectrum2structure/vib2mol_ks1000k.yaml
```

Validation generation accuracy is token accuracy, not molecular exact match.
Standalone `workflow retrieval-eval` / `generation-eval` with `--modality ir-raman-nmr`
use `evaluate_multimodal.py`, reporting test-pool recall or canonical-SMILES beam
exact matches/validity. H/C `--rerank --rank-checkpoint <matching checkpoint>`
now supports spectrum-to-molecule retrieval and generated-beam reordering.
It uses positive-class ITM softmax probabilities with the full IR/Raman/H/C
memory and masks; normalization/reference mismatches between checkpoints fail.
Reverse molecule-to-spectrum retrieval is reported without reranking.
Do not call the legacy upstream inference scripts directly for H/C checkpoints.

See [ks200k evaluation and tokenizer audit](vib2mol_evaluation.md) for commands
and the non-stereochemical target limitation.

NMR normalization is not QC: negative/extreme calculated shifts are retained.
No GPU benchmark has been run as part of this migration.

The 1M modality-increment configs are `vib2mol_ir_ks1000k.yaml`,
`vib2mol_ir_raman_ks1000k.yaml`, and `vib2mol_ks1000k.yaml`. They use the same
1M/10,390/20,390 scaffold splits, seed, per-GPU batch size, four-GPU global
batch and 312,500 steps per stage; only the enabled spectroscopy inputs differ.
