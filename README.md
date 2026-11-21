# OpenMolSpec

项目网页：[OpenMolSpec v1.0](https://jiaqingxie.github.io/openmolspec.github.io/)。提供 Introduction、在线 Tool、实验 Dataset 预览和 Documentation 跳转。Agent Harness 接入模型 API，通过真实 MCP 工具完成能力发现、输入校验和模型调用，提供可展开的调用记录、实际运行回放与过程截图。网站构建见 [website/README.md](website/README.md)，推理服务部署见 [online_api/README.md](online_api/README.md)。

面向化学谱学的数据集与深度学习平台。v1.0 通过 Python 包 `openmolspec` 提供数据加载、模型调用、训练准备、自主训练与评测。NMRTransformer 已完成编码器和生成器的微型真实训练、保存、重载与重复推理检查；模型效果按各任务的实际评测范围报告。用法见 [Python SDK](documentation/api.zh.md)，功能入口见 [文档目录](documentation/index.zh.md)。

OpenDataLab / WanJuan 清洗所得数据是团队整理的外部实验谱，与 OpenMolSpec 计算谱及接入的外部基准分别报告。当前工作台支持实验 H/C NMR 候选检索与 SMILES 生成，并保留计算 IR/Raman、谱图到性质和 Vib2Mol 工作流。

随网站发布的完整手册：[English](https://jiaqingxie.github.io/openmolspec.github.io/docs/index.html) · [简体中文](https://jiaqingxie.github.io/openmolspec.github.io/docs/zh/index.html)。[Read the Docs](https://openmolspec.readthedocs.io/en/latest/) 独立构建。采用 Sphinx 和经典 `sphinx_rtd_theme`，提供左侧层级目录、全文搜索、上下篇导航和语言切换。包含 84 个经 Jupyter 内核执行的教程预览及下载；项目网页保留 43 张真实结果与数据分布图。源文件位于 [documentation/](documentation/index.md)；旧 [handbook/](handbook/index.md) 保留历史记录。

## 安装与启动

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[production,models]" -r requirements.txt
export OPENMOLSPEC_ARIAL_FONT=/path/to/installed/Arial.ttf
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

统一目录保留 35 个任务配置，其中 32 项继续推进、3 项按用户要求停用（SpectraLLM、分子式预测、谱学 QA）。32 个活跃任务均有运行入口；³¹P 和 ¹⁹F 使用现有实验数据训练的溶液位移模型，B/Si 只报诊断，跨溶剂目前为实验参考检索基线。覆盖 H/C NMR、TransPeakNet HSQC、Xinyu 四模态 Vib2Mol、gap、构象到 IR/Raman、GLACIER/ICEBERG 和 MAGMa。接口存在不代表精度已验证。结果记录数据与权重 SHA-256、样本、候选池和状态。流程入口只进行推理或已有预测评分。

详情见[任务目录](handbook/tasks.md)、[数据格式](handbook/data.md)、[评测口径](handbook/benchmark.md)、[Studio 操作](handbook/studio.md)及[结果](handbook/results.md)。旧核心项目说明仍位于 [docs/openmolspec_core.md](docs/openmolspec_core.md)。

³¹P 与 ¹⁹F 的 CPU 预测器接收 SMILES 和可选溶剂。当前选出的 ³¹P 模型在 4,248 种留出分子上的观测 MAE 为 4.32 ppm，分子等权 MAE 为 5.60 ppm。[在线预测 ³¹P](https://jiaqingxie.github.io/openmolspec.github.io/#tool-31p) · [同划分模型比较](documentation/tasks/nmr-forward-31P.zh.md)。¹⁹F 的 GNN 与树模型组合在 14,330 种留出结构上的观测 MAE 为 5.92 ppm，分子等权 MAE 为 5.62 ppm。[¹⁹F 模型卡](documentation/tasks/nmr-forward-19F.zh.md)。权重位置、模型调研、按骨架和谱源拆分的误差、历史标签复核及复现命令见[实验报告](docs/SOLUTION_NMR_RESEARCH.zh.md)。

## 构建使用手册

文档构建使用 Python 3.11 或更新版本。MyST-NB 仅渲染已保存的 notebook 输出，构建时不执行模型代码。

```bash
python -m pip install -r requirements-docs.txt
python scripts/render_task_catalog.py --check
python scripts/build_readthedocs.py --output site --strict
```

Read the Docs 使用 `.readthedocs.yaml` 构建 `release/openmolspec-v1` 分支；GitHub Actions 负责严格文档构建检查。前端 Full documentation 默认跳转至已上线的手册，可通过 `OPENMOLSPEC_DOCS_URL` 覆盖地址。发布证据见 [RTD 核验记录](results/readthedocs_publication_20261116.json)。

本地工作台导航包括 Tool、Prediction (Online)、Data、Tasks、Tutorials、Theory、Inversion 与 Documentation。在线 MS 推理可通过 `OPENMOLSPEC_MS_PYTHON` 指定包含作者依赖的 Python。模型与数据路径配置见 [快速开始](documentation/quickstart.zh.md)。

最新证据见 [评测协议](documentation/protocols.zh.md) 和各任务页。旧 F/P 分数因输入与标签错配作废；新推理已对齐，但固态权重的溶液位移参考未核实，不能宣称修复了预测精度。

在线 Vib2Mol 生成使用 beam=10、有效规范化候选去重和 ITM 重排，与本轮 Xinyu 协议评测一致。生成与重排模型的 H/C 归一化不一致或重排失败时明确报错；缺少模态时页面提示离线四模态准确率不适用。

当前模型来源和接入条件见 [后续模型核查](docs/ACTIVE_MODEL_FOLLOWUP.md)。

二维 HSQC 可用 TransPeakNet 从 SMILES 和溶剂预测交叉峰。用冻结权重重算作者笔记本的 511 行溶剂记录，¹³C / ¹H MAE 为 2.024874 / 0.165062 ppm。对公开的 479 张谱等权平均，结果为 2.027531 / 0.165891 ppm。网页的峰匹配规则另行评测，7,926 个不同观测峰中有 5,141 个命中专家给出的碳位点，未匹配峰计入分母。[中文任务指南](documentation/tasks/nmr-hsqc-transpeaknet.zh.md) · [完整预测](results/transpeaknet_hsqc_479.json)

原子指认使用冻结 NMRNet H/C 权重，可在 Prediction (Online) 中直接运行。跨溶剂页面明确标注参考检索基线；源数据准备和部署变量见 [接入与发布说明](docs/REMAINING_TASKS_DELIVERY.md)。

### simpleNMR 归属样例

作者的 2-乙基-1-茚酮工作簿含一维氢谱、碳谱、纯位移氢谱及 HSQC、COSY、HMBC。脚本从工作簿重算碳信号的候选原子，最后与作者保存的演示表按信号编号核对。逐碳位移、候选原子和 HSQC 峰见[样例结果](results/simplenmr_indanone.json)。[作者仓库](https://github.com/EricHughesABC/simpleNMR/tree/685b819a54fb49ccba63290cd1b493a00ae33ebd)

在单独的 Python 3.10 环境中运行。脚本使用 Java 11 或更高版本。Linux 下使用平台的 classpath 分隔符调用作者的 NMRShiftDB 预测器，并在临时目录中读写工作文件。

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/EricHughesABC/simpleNMR.git
git -C simpleNMR fetch --depth 1 origin 685b819a54fb49ccba63290cd1b493a00ae33ebd
git -C simpleNMR checkout 685b819a54fb49ccba63290cd1b493a00ae33ebd
git -C simpleNMR sparse-checkout set csTables exampleProblems/2-ethyl-1-indanone
python -m pip install 'numpy==1.26.4' 'pandas==1.5.3' 'rdkit==2024.9.6' 'nmrglue==0.11' 'PyQt5==5.15.11' 'openpyxl==3.1.5' scipy networkx PyYAML pillow
python scripts/reproduce_simplenmr.py --source simpleNMR --output results/indanone-local.json
```
