# Python SDK — OpenMolSpec v1.0

The package provides dataset loading, model facades, training preparation and benchmark entry points. The base installation has no third-party dependencies. In this release, frozen inference has real execution evidence; the training launcher has completed one encoder step and one generator step, including checkpoint save, configuration reload and identical repeated inference on tiny train/validation examples. This checks software integration, not learning performance.

## Install

The [versioned release](https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/tag/v1.0) provides the wheel and checksum. For data loading and model interfaces, install it directly into your environment:

```bash
python -m pip install "https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/v1.0/openmolspec-1.0.0-py3-none-any.whl"
```

For the notebooks, source code and optional dependencies, clone the repository:

```bash
git clone --branch release/openmolspec-v1 https://github.com/jiaqingxie/openmolspec-studio-frontend.git
cd openmolspec-studio-frontend
python3 -m venv .venv
.venv/bin/python -m pip install .
# Optional local data formats and analysis:
.venv/bin/python -m pip install '.[data,analysis]'
# Optional packaged NMR Transformer training dependencies:
# .venv/bin/python -m pip install '.[train]'
```

The package is distributed through GitHub Releases. NMRNet, Vib2Mol and MS models use their author environments, selected with `python=`. Only OpenMolSpec modules are exposed to that interpreter; its torch/numpy versions are preserved. Original production-processing commands now require `pip install ".[production]"`.

## Dataset loading, provenance and splits

```python
from openmolspec.dataset import molspectra, list_datasets

print([card['name'] for card in list_datasets()])
data = molspectra('opendatalab_nmr', root='/path/to/hc_nmr_inchi_v1')
splits = data.get_split()       # existing train / val / test files
rows = splits['test'].head(3)   # streaming; does not load the full corpus
hc = splits['test'].select(modalities=['1H', '13C'], limit=32)
print(data.summary())
# data.verify()                # hash complete files against the audited version
```

| Registered name | Format | Domain / origin |
| --- | --- | --- |
| `opendatalab_nmr` | `train.jsonl`, `val.jsonl`, `test.jsonl` | Team-curated external experimental NMR |
| `nmrspec_test`, `patent_test_10k`, `nmrexp_exp_10k`, `nmrgym_test` | `test.jsonl` | Prepared experimental evaluation views |
| `openspec_test` | `openspec_test.lmdb` | OpenMolSpec calculated observables |
| `massspecgym_test` | `MassSpecGym_test_full.csv` | External experimental MS/MS |
| `massspecgym_1_5` | Versioned `MassSpecGym.tsv`, filtered by its native fold | External experimental MS/MS; v1.5 |

Pass a directory or, for a single-file test view, the file itself. Legacy LMDB requires explicit `trusted=True` because it contains Python pickles. Record fields are preserved; `_openmolspec` adds dataset, domain, split, source-file locator and available modalities. Missing acquisition conditions are not fabricated. Card counts describe audited versions, not arbitrary local files; `verify()` rejects changed files. Full dataset downloads are not silently performed. Verified public release URLs and redistribution scope remain pending; see [data sources and counts](datasets.md).

`audit_splits(data.get_split())` recomputes structural identities with RDKit and a disk-backed index. Default connectivity grouping keeps stereoisomers together. Results apply only to the supplied views; checking a small subset does not establish full-corpus or pretrained-model independence.

## NMRNet: actual frozen inference

```python
from openmolspec.model import NMRNet

model = NMRNet.from_pretrained(
    '/path/to/models', nucleus='13C', python='/path/to/nmr-env/bin/python'
)
result = model.predict([row['smiles'] for row in rows])
print(result['records'])       # atom_indices + prediction_ppm
print(result['provenance']['checkpoint_sha256'])
model.save_config('nmrnet-config.json')
restored = NMRNet.from_config('nmrnet-config.json')
```

The model root contains original `nmrnet/nmrnet-orig` source and `nmrnet/weights/finetune/liquid` assets. This adapter runs liquid H/C fold 0 on CPU with the original scaler. Atom indices follow zero-based RDKit AddHs(input SMILES), and the generated geometry is recorded. Training overlap and solvent effects remain unverified. B/Si/F/P are not exposed as validated NMRNet variants. [Original assets](https://zenodo.org/records/19142375).

To run the [SDK inference notebook](notebooks/sdk-inference.ipynb), install `requirements-docs-examples.txt` and the package, then configure:

```bash
export OPENMOLSPEC_MODELS_ROOT=/path/to/models
export OPENMOLSPEC_NMR_PYTHON=/path/to/nmr-env/bin/python
```

That notebook actually calls `model.predict`, prints checkpoint identity, compares real experimental peaks and renders a figure. Peak matching is not experimental atom-assignment accuracy.

## Model interfaces

| Class | Input → output | SDK training |
| --- | --- | --- |
| `NMRNet` | SMILES → H/C atom shifts; `assign` adds measured peaks | No |
| `NMRTransformer(stage='align')` | NMR query + explicit candidates → ranking | Existing alignment trainer |
| `NMRTransformer(stage='generate')` | NMR + known formula → SMILES | Existing generator; alignment checkpoint required |
| `GapModel` | IR/Raman/H/C → gap in eV | No |
| `Vib2Mol` | IR/Raman/H/C → SMILES; `retrieve(..., rerank=True)` uses ITM on supplied candidates | No |
| `MSPredictor(model='glacier' or 'iceberg')` | Structure + adduct, collision energy, instrument → MS/MS | No |

Vibrational inputs are `ir`, `raman` (1024 values each), `nmr_h`, `nmr_c` (ppm arrays), with checkpoint-compatible reference and normalization. Missing channels are rejected unless `allow_missing_modalities=True`, which marks the run as an ablation. NMR retrieval excludes formula input; generation requires it. All model facades support configuration save/load: this saves paths and settings, not copies of weights.

## Prepare and train your own NMR data

```python
from openmolspec.dataset import MolecularSpectra
from openmolspec.training import prepare_nmr_training
from openmolspec.model import NMRTransformer

custom = MolecularSpectra.from_jsonl(
    splits={'train': 'train.jsonl', 'val': 'val.jsonl'},
    name='my_experiment', domain='experimental',
)
prepared = prepare_nmr_training(custom['train'], custom['val'], 'prepared-nmr')
model = NMRTransformer(stage='align', device='cpu')
plan = model.training_plan(prepared, run_dir='runs/my-alignment', epochs=10, batch_size=32)
print(plan.describe())
print(plan.validate())
# result = model.fit(plan)     # launches training; use a new run directory
```

Records require `smiles`, `formula`, `h_nmr`, `c_nmr` and optional `[has_H, has_C]` masks. Preparation checks formulas, nuclei and train/validation connectivity overlap. `select` preserves split roles; an existing test view cannot be supplied as training data. Training rechecks file hashes and overlap before launching and creates a new log, plan and best-checkpoint hash. Generation training additionally requires `alignment_checkpoint=`. Pretrained initialization restores weights, not optimizer/scheduler state.

The [executed preflight notebook](notebooks/sdk-training-preflight.ipynb) uses two real records from each original OpenDataLab train/validation split. It runs data preparation and validation, **not training**. A separate actual training run has now verified both stages. The [training integration report](assets/reports/sdk_training_roundtrip_20261117.json) records two training and two validation records, one optimizer step per stage, checkpoint hashes and save/reload inference equality. These records retain their original split roles; no test examples are used. No learning-performance claim is made. One source inconsistency encountered during example selection was a hydrogen-free `BrOBr` structure with a ¹H record; training preparation now rejects absent-nucleus records, while raw loaders retain them for inspection.

## Task discovery and benchmark execution

```python
from openmolspec.task import list_tasks
from openmolspec.benchmark import Benchmark

print(list_tasks(group='nmr'))
bench = Benchmark(workspace='/path/to/OpenMolSpec', python='/path/to/runtime/bin/python')
report = bench.run('nmr.retrieval.hc.s2m', datasets=['nmrspec_test'],
                   limit=32, output='results/my-benchmark.json')
```

The 31 active adapters remain accessible; deferred tasks are excluded. A completed adapter does not establish model accuracy or independent validation. Interpret scores with the [model audit](model-audit.md) and [evaluation protocols](protocols.md).


A full chemistry check of the four local evaluation JSONLs inspected 39,183 records. Five records in the 10,000-record patent view had a recorded nucleus absent from the structure (five H flags; two of those also C flags). The other three views had no flags under these checks. This is not an audit of every raw spectrum or of the full 2.68-million-identity corpus. [Download audit](assets/reports/sdk_nmr_input_audit_20261117.json).


To reproduce the software integration check from this repository:

```bash
python scripts/verify_sdk_training.py \
  --python /path/to/nmr-env/bin/python \
  --work runs/sdk-training-check \
  --output results/sdk-training-check.json
```
