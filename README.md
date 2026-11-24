# OpenMolSpec

项目网页：[OpenMolSpec v1.0](https://jiaqingxie.github.io/openmolspec.github.io/)。可直接打开[中文版](https://jiaqingxie.github.io/openmolspec.github.io/?lang=zh)。工作台列出各任务的输入与输出，数据探索支持按 SMILES 查实验谱、调用预测、对照计算谱与实测峰。首页使用同一份蔗糖样品的氢谱、碳谱及 HSQC；智能体工作流图与三个真实案例可直接回放。网站构建见 [website/README.md](website/README.md)，推理服务部署见 [online_api/README.md](online_api/README.md)。

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

任务目录包含 37 个活跃配置，覆盖单谱与多谱检索、库内重排、位点指认、跨溶剂位移、能隙、碎片候选标注、SpecMol 问答和 SpectraLLM 结构生成。可通过 Python、命令行和 MCP 调用已配置的模型。独立的分子式预测已停用。各项实测规模和适用范围见[评测结果](handbook/results.md)，工具调用见[Harness 图和示例](documentation/harness/mcp.zh.md)。

详情见[任务目录](handbook/tasks.md)、[数据格式](handbook/data.md)、[评测口径](handbook/benchmark.md)、[Studio 操作](handbook/studio.md)及[结果](handbook/results.md)。旧核心项目说明仍位于 [docs/openmolspec_core.md](docs/openmolspec_core.md)。

³¹P 与 ¹⁹F 的 CPU 预测器接收 SMILES 和可选溶剂。当前选出的 ³¹P 模型在 4,248 种留出分子上的观测 MAE 为 4.27 ppm，分子等权 MAE 为 5.54 ppm。[在线预测 ³¹P](https://jiaqingxie.github.io/openmolspec.github.io/#tool-31p) · [同划分模型比较](documentation/tasks/nmr-forward-31P.zh.md)。¹⁹F 的 GNN 与树模型组合在 14,330 种留出结构上的观测 MAE 为 5.92 ppm，分子等权 MAE 为 5.62 ppm。[¹⁹F 模型卡](documentation/tasks/nmr-forward-19F.zh.md)。权重位置、模型调研、按骨架和谱源拆分的误差、历史标签复核及复现命令见[实验报告](docs/SOLUTION_NMR_RESEARCH.zh.md)。

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

二维 HSQC 从 SMILES 和溶剂预测交叉峰，使用 TransPeakNet 作者权重和 OpenMolSpec 位移校准。2DNMRGym 官方 eval 的 479 张谱中，双轴命中率为 51.1%，碳指认正确率为 66.4%。万卷 21 份局部峰表的 95 个已报告峰中命中 35 个。TransPeakNet 专家档案和 2DNMRGym 共用这 479 张谱，按一个基准计数。[两组基准、逐谱预测与复现命令](results/hsqc_benchmarks/README.md) · [模型与原作者权重复现](documentation/tasks/nmr-hsqc-transpeaknet.zh.md)

正向预测涵盖六种一维核、二维 HSQC、IR / Raman 和两个 MS/MS 后端。各项完整测试集规模、参考类型、指标与脚本入口见[正向预测汇总](documentation/benchmarks.zh.md)与[论文结果整理](docs/manuscript/forward_prediction_results.md)。 [同一万卷分子的 ¹H、³¹P 和 HSQC 脚本](scripts/example_forward_wanjuan.py) · [实测与预测对照图](docs/figures/forward_wanjuan_example.pdf)

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
