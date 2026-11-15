# Two-stage NMR → SMILES baseline

This spectrum-to-structure baseline reads `data/raw/WanJuan_MolSpectra_v1_0_3.jsonl`.
It takes a molecular formula and any available ¹H/¹³C NMR records, including
H-only and C-only cases, and generates canonical isomeric SMILES with a
Transformer. There is no MS input. New alignment runs use structured NMR
tokens. New runs tokenize molecular SMILES with the local Vib2Mol BPE vocabulary.
The completed 12,265,389-example extraction and 2,680,271-InChI deduplicated
training view are documented in
[DATASET_CARD.md](DATASET_CARD.md).

The workflow follows the local OpenMolSpec/Vib2Mol `matching → generation`
handoff. The source parser converts experimental NMR prose into one token per
chemical shift and independent model weights. Alignment combines symmetric
contrastive learning with hard-negative spectrum–molecule matching; generation
remains autoregressive.

## Setup and data preparation

From the repository root, with Python 3.10+:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'torch==2.4.1+cpu' \
  --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r spec2struct/requirements.txt
.venv/bin/python -m spec2struct.data \
  --input data/raw/WanJuan_MolSpectra_v1_0_3.jsonl \
  --output-dir model_data/hc_demo \
  --max-examples 20000
.venv/bin/python -m spec2struct.verify --data-dir model_data/hc_demo
```

Omit `--max-examples` for a full streaming pass. Choose a new output directory
for each run; preparation refuses to replace prior splits. Each compound needs
a parseable SMILES and nonempty ¹H or ¹³C shift text. All matching H/C records
are retained in `h_nmr` and `c_nmr` lists with type, shift, and available
frequency/solvent/source-line fields. `modality_mask` is `[has_H, has_C]`.
RDKit canonicalizes the SMILES,
calculates its molecular formula, and obtains a Bemis–Murcko scaffold. A stable
hash assigns each scaffold to train/validation/test at 80/10/10. Acyclic
structures are grouped by canonical SMILES, so actual record ratios can differ.
`summary.json` records counts, H-only/C-only/H+C totals, and the split method.
`verify` scans each split, checks masks and scaffold assignment, spot-checks
SMILES/formula consistency, and records SHA-256 digests in `verification.json`.
The formula is derived from the training target because it
is an explicitly supplied model input; users must supply it at inference.
On a GPU host, install a CUDA-compatible PyTorch build in `.venv` instead of
the CPU wheel shown above.

If the GPU host supports CUDA 12.8, a newer build can be installed from the
[PyTorch CUDA wheel index](https://download.pytorch.org/whl/cu128/torch/).
Large wheels may exhaust a small `/tmp`; use the project filesystem for pip's
temporary files and skip its cache:

```bash
mkdir -p .tmp/pip
TMPDIR="$(pwd)/.tmp/pip" .venv/bin/python -m pip install --no-cache-dir \
  --upgrade 'torch==2.9.1+cu128' \
  --extra-index-url https://download.pytorch.org/whl/cu128
.venv/bin/python -c 'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())'
```

Run this on a GPU node after confirming the repository and `model_data/` are
mounted there. The CUDA build must match the node's GPU and driver.

## Stage 1: align spectra and molecules

The spectrum encoder reads visible H/C peak tokens **without the formula**. The
paired SMILES uses the local Vib2Mol BPE vocabulary, a learned molecular CLS
token, and a separate molecular encoder. Global bidirectional InfoNCE uses a
learned contrastive scale. A cross-modal matching head classifies each true pair
and two hard negatives sampled from the global contrastive scores. The local
tokenizer adds six stereo/patent symbols absent from the reference vocabulary
so the existing isomeric SMILES targets remain reversible. Validation
spectrum-to-molecule recall@1 chooses
`align/best.pt`. Both directions of recall are reported. A deterministic
validation reservoir bounds the retrieval evaluation cost.
New alignment runs default to a 512-dimensional model with eight attention
heads, six spectrum/molecule encoder layers, six decoder layers, a 2048-unit
feedforward layer, and a 256-dimensional contrastive projection. Override these
with `--hidden-size`, `--heads`, `--encoder-layers`, `--decoder-layers`,
`--feedforward-size`, and `--projection-size` as needed.

Each peak token has separate features for nucleus, shift, range width,
multiplicity, integration, up to three coupling constants, spectrometer
frequency, solvent, and DEPT subtype where available. Missing values have
presence flags or unknown categories. A record with no parseable shift keeps
one missing-shift token. Formula elements and counts become separate tokens in
generation. The default source limit is 128 tokens; `--max-source-tokens`
changes it. H/C masks remove hidden peaks before encoding.

```bash
.venv/bin/python -m spec2struct.train align \
  --data-dir model_data/hc_nmr_inchi_v1 --run-dir runs/hc_nmr_v1/align \
  --epochs 2 --max-train-batches 100 --max-val-examples 1024
```

For full-data multi-GPU alignment, launch one process per GPU with `torchrun`:

```bash
OMP_NUM_THREADS=4 .venv/bin/torchrun --standalone --nproc-per-node=4 \
  -m spec2struct.train align \
  --data-dir model_data/hc_nmr_inchi_v1 \
  --run-dir runs/hc_nmr_inchi_align_ddp \
  --epochs 10 --batch-size 8 --learning-rate 1e-4 \
  --max-val-examples 1024 --log-every 100 --device cuda
```

`--batch-size` is per GPU (global batch and contrastive negative pool are
`4 × 8 = 32` in this example). Change `--nproc-per-node` to the GPU count and
use a CUDA-enabled PyTorch build in `.venv`.
`align` defaults to `--input-representation structured`. Use
`--input-representation byte` only to reproduce the earlier text baseline;
its source limit remains 512 bytes. Representation and source limit are saved
in the checkpoint and inherited automatically by `generate`, `evaluate`, and
`predict`. Existing byte-model checkpoints still load as byte models. Running
jobs keep the representation they loaded at launch; start a new alignment run
to train the structured encoder.
`--run-dir` is an optional parent directory. Every launch creates a UUID
subdirectory beneath it; without the option, the parent is `runs/align` or
`runs/generate`. Rank 0 prints a `run_directory_created` event containing the
actual `run_dir` and shares that path with all DDP ranks. Reusing a parent for
multiple experiments cannot overwrite earlier checkpoints.
DDP shards training rows across ranks, gathers embeddings for global in-batch
negatives, exchanges token features for the matching head, and writes validation
results and checkpoints from rank 0. Generation also shards training and
validation rows; `--batch-size` is per GPU, and its cross-entropy is weighted by
the global number of non-padding SMILES tokens. Its auxiliary alignment loss
continues training the molecular encoder, projections, and ITM head. Both stages step a
cosine learning rate scheduler after every optimizer update, reaching zero on
the last planned step. Each rank scans the training JSONL to select its rows,
so storage bandwidth matters.
Both stages print JSON progress events and append them to `progress.jsonl` in
their run directory. Batch 1, every `--log-every` batches, and the final batch
are reported; alignment logs global DDP loss and examples seen. Training and
validation boundaries, checkpoint saves, and epoch results are also recorded.
`--tqdm auto` (default) shows a progress bar only on an interactive terminal;
use `--tqdm always` to force it or `--tqdm never` to suppress it. In a Pod log,
the JSON lines remain readable without a progress bar. Monitor them with:

```bash
tail -f runs/hc_nmr_inchi_align_ddp/UUID_FROM_LOG/progress.jsonl
```

The new logging code applies to newly started processes; an already running
training process keeps its loaded code and writes only at epoch boundaries.

## Full test-set retrieval

Use the alignment checkpoint to search every test spectrum against every test
molecule (255,069 candidates in `hc_nmr_inchi_v1`). Encoding and ranking run in
batches, so the full similarity matrix is never held in memory. This command
requires a GPU node and reports both retrieval directions and their full-pool
loss. It writes a JSON result without replacing an existing file:

```bash
OMP_NUM_THREADS=8 .venv/bin/python -m spec2struct.evaluate_alignment_full \
  --data-dir model_data/hc_nmr_inchi_v1 \
  --checkpoint runs/hc_nmr_inchi_align_itm_bpe_cosine/4c6f42c4b61f465b86bc2b47f449096c/best.pt \
  --split test --device cuda:0 --encode-batch-size 128 \
  --query-batch-size 256 \
  --output runs/hc_nmr_inchi_align_itm_bpe_cosine/4c6f42c4b61f465b86bc2b47f449096c/full_test.json
```

The earlier `evaluate_alignment(..., max_examples=8192)` result used a fixed
reservoir of 8,192 test examples. Its Recall@1 is therefore measured against a
smaller candidate pool and should not be compared directly to this full-pool
result.

To measure the benefit of a supplied exact molecular formula, rerun the same
command with `--formula-filter` and a fresh `--output` path such as
`full_test_formula.json`. The evaluator reports both unconstrained Recall@1
and Recall@1 after limiting candidates to the query's formula, plus the gain
in percentage points and formula-pool sizes. This uses the test row's formula
as a known input; it does not predict the formula or apply the ITM classifier.

## TensorBoard for completed runs

Training writes `history.json` and `progress.jsonl`, not TensorBoard events.
Export any completed run once, then open the scalar charts locally or through
your editor's port forwarding:

```bash
.venv/bin/python -m pip install tensorboard
.venv/bin/python -m spec2struct.export_tensorboard \
  runs/hc_nmr_inchi_align_full_20260924 \
  runs/hc_nmr_inchi_align_full_20260924_bs1024 \
  runs/hc_nmr_inchi_align_structured_512/d9f5ec1bb200414f8651e7ec5540e4c9
.venv/bin/tensorboard --logdir runs/tensorboard --port 6006
```

Open `http://localhost:6006`. The export includes epoch training/validation
loss, both retrieval recall@1 directions, learning rate, and logged training window loss
against global steps. It refuses to overwrite an existing export directory;
choose a new `--output-dir` when re-exporting.

## Stage 2: generate SMILES

Generation loads the **best alignment checkpoint**, compares the recorded
training and validation SHA-256 digests, and reuses the aligned spectrum encoder. Formula and
visible H/C tokens condition an autoregressive Transformer decoder. Every
parameter remains trainable: token cross-entropy trains generation, while a
formula-free NMR-to-molecule alignment/ITM loss trains the molecular branch.
The default joint objective is generation loss plus `0.1 ×` alignment loss;
adjust it with the positive `--alignment-loss-weight` option. The two stages use
separate optimizers and checkpoint directories. Generation validation loss
chooses `best.pt`.
Targets are RDKit canonical isomeric SMILES (for example, aromatic `c1ccccc1`),
encoded with the local Vib2Mol BPE vocabulary. They are not converted to Kekulé
SMILES.

```bash
.venv/bin/python -m spec2struct.train generate \
  --data-dir model_data/hc_nmr_inchi_v1 --run-dir runs/hc_nmr_v1/generate \
  --alignment-checkpoint runs/hc_nmr_v1/align/ALIGN_UUID/best.pt \
  --epochs 2 --max-train-batches 100 --max-val-batches 20
OMP_NUM_THREADS=8 .venv/bin/torchrun --standalone --nproc-per-node=8 \
  -m spec2struct.train generate \
  --data-dir model_data/hc_nmr_inchi_v1 \
  --alignment-checkpoint runs/hc_nmr_inchi_align_itm_bpe_cosine/4c6f42c4b61f465b86bc2b47f449096c/best.pt \
  --run-dir runs/hc_nmr_inchi_generate_ddp \
  --epochs 30 --batch-size 64 --learning-rate 5e-5 \
  --alignment-loss-weight 0.1 \
  --log-every 100 --tqdm always --device cuda
.venv/bin/python -m spec2struct.train evaluate \
  --data-dir model_data/hc_nmr_inchi_v1 \
  --checkpoint runs/hc_nmr_v1/generate/GENERATE_UUID/best.pt \
  --split test --modality hc --max-examples 100 --beam-size 5
.venv/bin/python -m spec2struct.train predict \
  --checkpoint runs/hc_nmr_v1/generate/GENERATE_UUID/best.pt --formula C2H6O \
  --h1 '1.2 (t, 3H), 3.7 (q, 2H), 2.4 (br, 1H)' \
  --c13 '58.3, 18.5'
```

For full-test generation quality, launch one evaluator per GPU. Each rank scans
the same test file but decodes a distinct set of examples; results are reduced
to one JSON report. Beam search batches active candidates and spectra to reduce
decoder calls. Generation now uses KV caching by default: each decoder layer
stores self-attention keys/values for the generated prefix and projects the
encoder memory keys/values once per spectrum. Beam expansion and pruning
reorder the cached histories. Each step computes only the newest token.
Existing checkpoints and CLI commands work without retraining; training still
uses the full-sequence decoder. For numerical comparisons in Python, pass
`use_kv_cache=False` to `beam_search` or `beam_search_batch`.
`--batch-size` is spectra per GPU, and rank 0 reports progress to
stderr. The evaluation metric definitions and candidate ranking are unchanged.

```bash
OMP_NUM_THREADS=4 .venv/bin/torchrun --standalone --nproc-per-node=8 \
  -m spec2struct.train evaluate \
  --data-dir model_data/hc_nmr_inchi_v1 \
  --checkpoint runs/hc_nmr_inchi_generate_ddp/b815d60597044b83a12fc7061d576dd0/best.pt \
  --split test --modality available --max-examples 255069 \
  --beam-size 5 --batch-size 16 --log-every 100 --device cuda
```

Training randomly hides H or C in dual-modality records (`--drop-h-prob` and
`--drop-c-prob`, both 0.2 by default); it never hides the only present modality.
When a compound has several selected records, training rotates their order
across epochs so later records can enter the model input limit. The original
`hc_nmr_v1` files retain every recognized nonempty H/C record; the InChI view
selects the most informative H and C source rows for each molecule.
The mask removes hidden modality tokens before encoding. At evaluation,
`--modality available|h|c|hc` selects the desired input condition. At inference,
repeat `--h1` or `--c13` for multiple records, or provide only one modality.
Old one-stage checkpoints cannot initialize either stage or inference.

Replace `ALIGN_UUID` and `GENERATE_UUID` with the UUIDs printed by their runs.
For a full run, remove the batch limits.
Each stage saves `best.pt`, `last.pt`, and `history.json`.
Evaluation reports canonical exact match, RDKit validity, and formula match.
Beam candidates are ranked with formula-matching structures first.
`predict` reports `best: null` when its beam contains no valid structure with
the requested formula. This generative baseline should be measured on
the held-out test split before use. Training uses the packages in `.venv`.

## Data caveats

The NMR field contains prose, multiplet labels and coupling constants, not a
standardized peak list. The original `hc_nmr_v1` JSONL retains every recognized
record, while
the structured encoder shares a 128-token default budget between formula,
H and C. New BPE runs limit SMILES to 300 tokens; older byte checkpoints retain
their 160-byte target limit. The parser recognizes common peak notation and range
shifts, but unusual prose can lose details.
Some records omit assignments or use inconsistent notation. The InChI training
view merges SMILES with the same standard InChI and reassigns each resulting
molecule to one scaffold-based split. Structures without a standard InChI are
listed separately in `inchi_failures.jsonl`.
