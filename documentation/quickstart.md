# Quick start

For the new dataset/model classes and training preflight, start with the [Python SDK guide](api.md).

Start with a real saved example, then run a model when its external weights and data are available. The repository contains documentation evidence; large model checkpoints and complete datasets are separate.

## 1. Get the documented release

Use Python 3.11 or newer for the documentation environment. The public documentation follows the release branch below; the newer frontend on `main` has a different application layout.

```bash
git clone --branch release/openmolspec-v1 https://github.com/jiaqingxie/openmolspec-studio-frontend.git
cd openmolspec-studio-frontend
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r requirements-docs-examples.txt
```

## 2. Reproduce the first figure without model downloads

This command reads the actual 128-sample frozen gap predictions, recomputes MAE/RMSE and draws the reference/prediction figure. It does not rerun the model.

```bash
.venv-docs/bin/python - <<'PY'
import sys
sys.path.insert(0, 'scripts')
from documentation_evidence import load_evidence, recompute, render
task = 'vibrational.gap.ir_raman_hc'
evidence = load_evidence(task)
print(recompute(evidence))
render(task, evidence).savefig('my-first-result.png', dpi=180)
PY
```

Expected recomputed MAE is approximately **0.131446 eV**. Open `my-first-result.png`, then compare the [real-results gallery](gallery.md) and [complete-input gap task](tasks/vibrational-gap-ir_raman_hc.md).

## 3. Run the notebook cells

```bash
.venv-docs/bin/jupyter lab documentation/notebooks/vibrational-gap-ir_raman_hc.ipynb
```

Select the Python kernel from `.venv-docs`, then Run All. Cells show the actual input, actual output, recomputed diagnostics and a figure. Full arrays are stored in `documentation/assets/examples/`; abbreviated previews state their array length. Source result filenames and SHA-256 hashes accompany each notebook.

## 4. Prepare frozen-model inference

Model runtimes are separate from the lightweight documentation environment. Install the original model dependencies in their own environments. See [dataset sources](datasets.md) and [model suitability](model-audit.md) before choosing a task. The expected workspace is:

```text
workspace/
  OpenMolSpec/
    studio/                     # this checkout
    data/align_eval/<dataset>/test.jsonl
    runs/<run-id>/best.pt        # existing NMR encoder/generator
  models/                       # NMRNet / NMRNet++ released assets
  openmolspec-studio-portable/   # Xinyu models, normalization, test LMDB
```

```bash
python -m openmolspec_bench list
python -m openmolspec_bench run   --workspace /path/to/workspace/OpenMolSpec   --portable-root /path/to/workspace/openmolspec-studio-portable   --tasks vibrational.gap.ir_raman_hc   --limit 32 --sampling reservoir --seed 42 --device cpu   --output results/my-gap-run.json
```

Run this command with a Python interpreter containing the original model dependencies. The complete-input task needs IR, Raman and both H/C channels with the checkpoint reference. Each output path must be new. `--limit` controls example count; it does not train or change the model.

For NMR assignment, explicitly select the dataset, model root and NMR runtime:

```bash
python -m openmolspec_bench run   --workspace /path/to/workspace/OpenMolSpec   --models-root /path/to/workspace/models   --nmr-python /path/to/nmr-runtime/bin/python   --tasks nmr.assignment --datasets nmrspec_test   --assignment-nucleus 13C --limit 2   --output results/my-assignment-run.json
```

## 5. Read the result correctly

- `status=passed` means the adapter completed; scientific suitability is assessed separately.
- `metrics` contains actual scores; `sample_ids`, hashes and conditions define what was evaluated.
- `skipped` means required assets, conditions or a valid reference are missing. Read `reason`; no score should be invented.
- F/P formal solution scores remain blocked; B/Si results are diagnostic. Cross-solvent transfer is a reference-retrieval baseline.
- A small candidate pool, unknown training overlap or absent assignment labels limits the claim you can make.

## 6. Build the bilingual website

```bash
.venv-docs/bin/python scripts/build_bilingual_docs.py --check
.venv-docs/bin/python scripts/build_readthedocs.py --output site --strict
.venv-docs/bin/python -m http.server 8000 --directory site
```

Open `http://localhost:8000/`; use the language switch for Chinese. Documentation builds render saved notebook outputs and never launch model inference.
