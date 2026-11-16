# 快速开始

新的数据加载、模型类和训练准备入口见 [Python SDK 指南](api.md)。

先从一份真实运行结果开始，再按需配置权重并执行模型。仓库已经保存文档所需的实际输入输出；大模型权重和完整数据集独立存放。

## 1. 获取文档对应的发布分支

文档环境使用 Python 3.11 或更新版本。线上手册对应下面的 release 分支；`main` 上较新的前端具有不同应用结构。

```bash
git clone --branch release/openmolspec-v1 https://github.com/jiaqingxie/openmolspec-studio-frontend.git
cd openmolspec-studio-frontend
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r requirements-docs-examples.txt
```

## 2. 不下载模型，先复现第一张真实结果图

下面的命令读取 128 个样本的真实冻结推理预测，重新计算 MAE/RMSE 并绘制预测与参考对照图。这一步是结果分析，不是重新运行模型。

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

重新计算得到的 MAE 约为 **0.131446 eV**。打开 `my-first-result.png`，再查看[真实结果图册](gallery.md)和[完整输入 gap 任务](tasks/vibrational-gap-ir_raman_hc.md)。

## 3. 逐格运行 notebook

```bash
.venv-docs/bin/jupyter lab documentation/notebooks/vibrational-gap-ir_raman_hc.ipynb
```

选择 `.venv-docs` 的 Python kernel 后运行全部单元格。依次显示真实输入、真实输出、重算指标和图。完整数组在 `documentation/assets/examples/`；页面中的缩略预览会标明数组长度。每份 notebook 都列出来源结果文件与 SHA-256。

## 4. 配置冻结模型推理

模型运行环境与轻量文档环境分开。按模型作者的依赖建立独立环境；选择任务前先看[数据来源](datasets.md)和[模型适用性](model-audit.md)。工作区组织如下：

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

使用已装好原模型依赖的 Python 执行上面的命令。完整输入任务需要 IR、Raman、H/C 及相容参考。输出文件必须是新路径。`--limit` 只控制样本数，不会训练或改变模型。

运行 NMR 指认时，还要明确数据集、模型目录和 NMR 专用 Python：

```bash
python -m openmolspec_bench run   --workspace /path/to/workspace/OpenMolSpec   --models-root /path/to/workspace/models   --nmr-python /path/to/nmr-runtime/bin/python   --tasks nmr.assignment --datasets nmrspec_test   --assignment-nucleus 13C --limit 2   --output results/my-assignment-run.json
```

## 5. 正确解读结果

- `status=passed` 只代表接口执行成功；科学适用性需要单独判断。
- `metrics` 保存实际指标；`sample_ids`、哈希和条件说明究竟评了什么。
- `skipped` 代表缺少资产、条件或合法参考；请查看 `reason`，不能补造分数。
- F/P 溶液正式评分仍被拦截，B/Si 仅作诊断，跨溶剂迁移当前是参考检索基线。
- 小候选池、未核查训练重叠、缺实验指认标签，都会限制可作出的结论。

## 6. 构建中英文文档

```bash
.venv-docs/bin/python scripts/build_bilingual_docs.py --check
.venv-docs/bin/python scripts/build_readthedocs.py --output site --strict
.venv-docs/bin/python -m http.server 8000 --directory site
```

打开 `http://localhost:8000/`，使用语言按钮切换中英文。文档构建仅渲染已保存的 notebook 输出，不启动模型推理。
