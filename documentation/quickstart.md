# Quick start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e . -r requirements.txt
export OPENMOLSPEC_BENCH_ROOT=/path/to/OpenMolSpec
export OPENMOLSPEC_ROOT=/path/to/openmolspec-studio-portable
.venv/bin/streamlit run app.py
```

The frontend exposes Tool, Dataset Download, Prediction (Online), and Full documentation. Weights and complete datasets are stored separately from Git.

```bash
python -m openmolspec_bench list
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec --tasks vibrational.gap.ir_raman_hc --limit 32 --output results/my_run.json
```

```bash
export OPENMOLSPEC_NMR_PYTHON=/path/to/nmr-runtime/bin/python
export OPENMOLSPEC_MODELS_ROOT=/path/to/models
export OPENMOLSPEC_SOLVENT_REFERENCE=/path/to/solvent_reference_library.json
```
