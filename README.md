# OpenMolSpec Studio v1.0

谱学任务、已有模型推理和可复现评测的统一工作台。支持实验 H/C NMR 候选检索与 SMILES 生成，并保留计算 IR/Raman、谱图到性质和 Vib2Mol 工作流。

完整手册位于 [handbook/](handbook/index.md)。[GitHub Pages 手册](https://jiaqingxie.github.io/openmolspec-studio-frontend/) 在 Documentation workflow 成功部署后生效。

## 安装与启动

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e . -r requirements.txt
export OPENMOLSPEC_ROOT=/path/to/openmolspec-studio-portable
export OPENMOLSPEC_BENCH_ROOT=/path/to/OpenMolSpec
export OPENMOLSPEC_DEVICE=cpu
.venv/bin/streamlit run app.py
```

默认打开任务与评测页；使用某个模型时才加载对应权重。模型 checkpoint、数据和训练输出独立存放，不包含在本代码仓库中。

## 任务与评测

```bash
python -m openmolspec_bench list
python -m openmolspec_bench run \
  --workspace /path/to/OpenMolSpec \
  --tasks nmr.retrieval.hc.s2m nmr.generation.hc \
  --datasets nmrspec_test --limit 32 --device cpu \
  --output results/my_smoke.json
```

统一目录包含 26 个任务定义、19 个已有评测适配器，覆盖六核 NMR 任务定义、H/C 双向检索与生成、F/P 跨域评分、IR/Raman gap 和 Vib2Mol 检索/生成/重排。待接入任务显式标记。结果记录数据与权重 SHA-256、样本、候选池和状态。流程入口只进行推理或已有预测评分。

详情见[任务目录](handbook/tasks.md)、[数据格式](handbook/data.md)、[评测口径](handbook/benchmark.md)、[Studio 操作](handbook/studio.md)及[结果](handbook/results.md)。旧核心项目说明仍位于 [docs/openmolspec_core.md](docs/openmolspec_core.md)。

## 构建使用手册

```bash
python -m pip install -r requirements-docs.txt
python scripts/render_task_catalog.py --check
python -m mkdocs build --strict
```

GitHub 仓库 Settings → Pages 的 Source 设为 GitHub Actions。PR 构建文档，主分支更新发布文档。
