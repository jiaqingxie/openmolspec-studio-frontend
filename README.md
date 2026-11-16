# OpenMolSpec Studio v1.0

谱学任务、已有模型推理和可复现评测的统一工作台。支持实验 H/C NMR 候选检索与 SMILES 生成，并保留计算 IR/Raman、谱图到性质和 Vib2Mol 工作流。

中英文完整手册源文件位于 [documentation/](documentation/index.md)，每个任务附输入示例和 notebook。Read the Docs 发布配置已准备；实际构建和公开网址尚未验证。旧 [handbook/](handbook/index.md) 保留历史记录。

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

统一目录保留 34 个任务配置，其中 31 项继续推进、3 项按用户要求停用（SpectraLLM、分子式预测、谱学 QA）。活跃任务中 27 项已有执行或评分接口（含禁止正式评分的 F/P），B/Si、原子指认及跨溶剂迁移四项仍待验证接入。覆盖 H/C NMR、Xinyu 四模态 Vib2Mol、gap、构象到 IR/Raman、GLACIER/ICEBERG 和 MAGMa。接口存在不代表精度已验证。结果记录数据与权重 SHA-256、样本、候选池和状态。流程入口只进行推理或已有预测评分。

详情见[任务目录](handbook/tasks.md)、[数据格式](handbook/data.md)、[评测口径](handbook/benchmark.md)、[Studio 操作](handbook/studio.md)及[结果](handbook/results.md)。旧核心项目说明仍位于 [docs/openmolspec_core.md](docs/openmolspec_core.md)。

## 构建使用手册

```bash
python -m pip install -r requirements-docs.txt
python scripts/render_task_catalog.py --check
python -m mkdocs build --strict
```

Read the Docs 导入本仓库并使用 `.readthedocs.yaml` 构建；GitHub Actions 负责严格文档构建检查。确认真实上线地址后设置 `OPENMOLSPEC_DOCS_URL`，前端 Full documentation 会跳转到该地址。未配置时展示本地文档与发布状态。

前端导航为 Tool、Dataset Download、Prediction (Online)、Full documentation。在线 MS 推理可通过 `OPENMOLSPEC_MS_PYTHON` 指定包含作者依赖的 Python。模型与数据路径配置见 [快速开始](documentation/quickstart.zh.md)。

最新证据见 [评测协议](documentation/protocols.zh.md) 和各任务页。旧 F/P 分数因输入与标签错配作废；新推理已对齐，但固态权重的溶液位移参考未核实，不能宣称修复了预测精度。

在线 Vib2Mol 生成使用 beam=10、有效规范化候选去重和 ITM 重排，与本轮 Xinyu 协议评测一致。生成与重排模型的 H/C 归一化不一致或重排失败时明确报错；缺少模态时页面提示离线四模态准确率不适用。

当前模型来源和接入条件见 [后续模型核查](docs/ACTIVE_MODEL_FOLLOWUP.md)。
