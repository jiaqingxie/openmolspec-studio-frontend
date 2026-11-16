# OpenMolSpec Studio v1.0

谱学任务、已有模型推理和可复现评测的统一工作台。支持实验 H/C NMR 候选检索与 SMILES 生成，并保留计算 IR/Raman、谱图到性质和 Vib2Mol 工作流。

中英文完整手册已上线：[English](https://openmolspec-10.readthedocs.io/en/latest/) · [简体中文](https://openmolspec-10.readthedocs.io/en/latest/zh/index.html)。共 150 个 HTML 页面、68 个已执行的 notebook 预览及下载，每个任务附输入示例。源文件位于 [documentation/](documentation/index.md)；旧 [handbook/](handbook/index.md) 保留历史记录。

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

统一目录保留 34 个任务配置，其中 31 项继续推进、3 项按用户要求停用（SpectraLLM、分子式预测、谱学 QA）。31 个活跃任务均有运行入口；F/P 正式评分仍受适用域门槛限制，B/Si 只报诊断，跨溶剂目前为实验参考检索基线。覆盖 H/C NMR、Xinyu 四模态 Vib2Mol、gap、构象到 IR/Raman、GLACIER/ICEBERG 和 MAGMa。接口存在不代表精度已验证。结果记录数据与权重 SHA-256、样本、候选池和状态。流程入口只进行推理或已有预测评分。

详情见[任务目录](handbook/tasks.md)、[数据格式](handbook/data.md)、[评测口径](handbook/benchmark.md)、[Studio 操作](handbook/studio.md)及[结果](handbook/results.md)。旧核心项目说明仍位于 [docs/openmolspec_core.md](docs/openmolspec_core.md)。

## 构建使用手册

```bash
python -m pip install -r requirements-docs.txt
python scripts/render_task_catalog.py --check
python scripts/build_readthedocs.py --output site --strict
```

Read the Docs 使用 `.readthedocs.yaml` 构建 `release/openmolspec-v1` 分支；GitHub Actions 负责严格文档构建检查。前端 Full documentation 默认跳转至已上线的手册，可通过 `OPENMOLSPEC_DOCS_URL` 覆盖地址。发布证据见 [RTD 核验记录](results/readthedocs_publication_20261116.json)。

前端导航为 Tool、Dataset Download、Prediction (Online)、Full documentation。在线 MS 推理可通过 `OPENMOLSPEC_MS_PYTHON` 指定包含作者依赖的 Python。模型与数据路径配置见 [快速开始](documentation/quickstart.zh.md)。

最新证据见 [评测协议](documentation/protocols.zh.md) 和各任务页。旧 F/P 分数因输入与标签错配作废；新推理已对齐，但固态权重的溶液位移参考未核实，不能宣称修复了预测精度。

在线 Vib2Mol 生成使用 beam=10、有效规范化候选去重和 ITM 重排，与本轮 Xinyu 协议评测一致。生成与重排模型的 H/C 归一化不一致或重排失败时明确报错；缺少模态时页面提示离线四模态准确率不适用。

当前模型来源和接入条件见 [后续模型核查](docs/ACTIVE_MODEL_FOLLOWUP.md)。

原子指认使用冻结 NMRNet H/C 权重，可在 Prediction (Online) 中直接运行。跨溶剂页面明确标注参考检索基线；源数据准备和部署变量见 [接入与发布说明](docs/REMAINING_TASKS_DELIVERY.md)。
