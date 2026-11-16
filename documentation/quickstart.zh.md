# 快速开始

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e . -r requirements.txt
export OPENMOLSPEC_BENCH_ROOT=/path/to/OpenMolSpec
export OPENMOLSPEC_ROOT=/path/to/openmolspec-studio-portable
.venv/bin/streamlit run app.py
```

前端提供 Tool、Dataset Download、Prediction (Online)、Full documentation 四个栏目。权重与完整数据独立于 Git 存放。

```bash
python -m openmolspec_bench list
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec --tasks vibrational.gap.ir_raman_hc --limit 32 --output results/my_run.json
```

```bash
export OPENMOLSPEC_NMR_PYTHON=/path/to/nmr-runtime/bin/python
export OPENMOLSPEC_MODELS_ROOT=/path/to/models
export OPENMOLSPEC_SOLVENT_REFERENCE=/path/to/solvent_reference_library.json
```
