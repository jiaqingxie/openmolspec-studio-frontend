# 安装与首次运行

需要 Python 3.10 或更新版本。推荐使用独立虚拟环境。

```bash
git clone https://github.com/jiaqingxie/openmolspec-studio-frontend.git
cd openmolspec-studio-frontend
python3 -m venv .venv
.venv/bin/python -m pip install -e . -r requirements.txt
```

仓库包含前端和推理代码。模型 checkpoint、原始数据、LMDB 和训练输出需要单独提供，不随 Git 同步。只读任务目录无需模型和 PyTorch：

```bash
.venv/bin/python -m openmolspec_bench list
.venv/bin/python -m openmolspec_bench list --json
```

## 启动工作台

```bash
export OPENMOLSPEC_ROOT=/path/to/openmolspec-studio-portable
export OPENMOLSPEC_BENCH_ROOT=/path/to/OpenMolSpec
export OPENMOLSPEC_DEVICE=cpu
.venv/bin/streamlit run app.py
```

浏览器打开命令打印的本地地址。默认进入任务与评测页，模型按实际操作加载。无权重时也能阅读目录与已有评测结果。

## 首次模型评测

`--workspace` 指向含 `data/align_eval/` 和 `runs/` 的 OpenMolSpec 数据工作区。

```bash
.venv/bin/python -m openmolspec_bench run \
  --workspace /path/to/OpenMolSpec \
  --tasks nmr.retrieval.hc.s2m nmr.generation.hc \
  --datasets nmrspec_test --limit 32 --device cpu \
  --output results/my_first_run.json
```

已有同名输出时命令拒绝覆盖，请换新文件名。CPU 上小样本可用于检查流程，GPU 用 `--device cuda:0`。没有 CUDA 时显式指定 GPU 会报错。

模型位置与数据格式见[数据与输入格式](data.md)。完整指标解释见[基准评测](benchmark.md)。
