# OpenMolSpec Benchmark Runbook（GPU 集群执行）

本文档说明如何在 GPU 集群上复现 OpenSpec 的 5 个 Application 基准。当前数据
仍在生成，因此先以固定、可复现的 demo 子集打通工作流；数据冻结后再用同一套
接口生成正式 benchmark。

## 0. 当前阶段：先跑 demo

```bash
python -m benchmarks check
python -m benchmarks prepare-demo \
    --sample-size 10000 --output benchmark_data/demo_10k --workers 32
python -m benchmarks run \
    --config benchmarks/configs/structure2property/dipole.yaml \
    --debug --dry-run
```

`prepare-demo` 使用 InChIKey 分组后的稳定哈希抽样，并显式跳过尚未冻结的 QC；
同一个 seed 不受原始行顺序影响。建议先各跑 1–2 epoch，验证显存、吞吐、loss
下降和 checkpoint 写出，再扩大到 100k 或全量。

## 1. 环境

- Python 3.10+，PyTorch 2.x + CUDA；`pip install -r requirements.txt`
  （vib2mol / vib2conf 各有一份；EquiformerV3 见其 `experimental/docs/env_setup.md`）。
- 需要 `lmdb`、`rdkit`、`torch_geometric`（含 `torch_cluster`、`torch_scatter` 扩展，
  PyG 按 torch/CUDA 版本安装）。
- 建议每个任务固定 seed：`--seed 624`（与上游一致）。

## 2. 正式数据（冻结后）

```bash
# 在本机或集群执行一次（约 30–60 分钟，输出 ~25 GB）
python -m benchmarks.data.prepare \
    --split-file builds/openmolspec-20260830/release-v1/splits/align_split.parquet \
    --output benchmark_data/release_v1 --workers 32
```

产物（`benchmark_data/`）：`benchmark_split.parquet`（sample_id → split）、
三个任务的 LMDB、`summary.json`（含 train/test 分子重叠 = 0 的泄漏检查）。

### 固定分割

- 算法：直接复用冻结发布版本的 scaffold-disjoint `align_split.parquet`；
  benchmark 不再自行重划正式数据。
- 默认严格导出冻结 `align_split.parquet` 中的记录；可选 `--record-qc` 会进一步
  过滤并改变样本数，必须作为独立 benchmark 变体记录。
- 所有任务共用同一 test 集，结果可直接横向比较。

## 3. 任务与命令

训练代码按 `experiment launcher → trainer → engine → model` 分层：launcher
解析 YAML 并管理独立运行目录；trainer 构建数据、模型和优化器，并管理 epoch、
scheduler 与最优 checkpoint；engine 只处理逐 batch 的 forward、loss 和评估
指标。实现集中在 `benchmarks/trainers/`、`benchmarks/engines/` 和
`benchmarks/models/`；上游源码与适配器并置在各模型的 `upstream/` 中。

推荐从版本化 YAML 启动，先检查展开后的命令，再正式运行：

```bash
python -m benchmarks run \
  --config benchmarks/configs/structure2observables/equiformer_v3.yaml \
  --dry-run

python -m benchmarks run \
  --config benchmarks/configs/structure2observables/equiformer_v3.yaml
```

YAML 中 `task.targets` 明确列出真正训练的输出头。每次运行会独立保存解析后配置、
环境、完整命令、训练日志、状态和模型产物；同一非空 run 目录不会被覆盖。下面的
直接命令仍保留用于调试底层 adapter。

运行目录自动使用本地时间戳加六位 UUID 随机十六进制后缀，例如
`2026-09-05-14-30-a1b2c3`，与 Harmony 一致，无需传入 `--run-id`。

### 2.1 结构→属性（EquiformerV3）

```bash
bash benchmarks/scripts/run_equiformer_v3.sh
# 或单任务：
python -m benchmarks.models.equiformer_v3.train \
    --task structure2property \
    --data-dir benchmark_data/equiformer_v3 \
    --output reports/benchmark \
    --epochs 50 --batch-size 32 --lr 3e-4 --device cuda:0
```

- 目标：energy, gap, homo, lumo, dipole_total, zpve（训练集均值/标准差归一化，
  报告为原始量纲）。
- 模型：`EquiformerV3_OC`（pin commit `a7300c5`，`use_pbc=False`）+ 池化标量
  嵌入上的回归头。
- 输出：`reports/benchmark/results_structure2property.{csv,json}` + 最优权重。

### 2.2 结构→光谱（EquiformerV3）

```bash
python -m benchmarks.models.equiformer_v3.train \
    --task structure2spectrum \
    --data-dir benchmark_data/equiformer_v3 \
    --output reports/benchmark \
    --epochs 50 --batch-size 32 --lr 3e-4 --device cuda:0
```

- 目标：IR / Raman 1024 点光谱；损失 = MSE + 0.5×(1 − cosine)。
- 指标：MAE、cosine similarity、Pearson r（逐记录）。

### 2.3 光谱→结构（Vib2Mol，检索与 SMILES 生成）

```bash
python -m benchmarks.models.vib2mol.workflow check-data \
  --data-dir benchmark_data/release_v1
```

Vib2Mol 是两阶段模型，先训练 matching 编码器，再以 matching 权重初始化 SPT
生成模型。adapter 会自动创建上游固定数据路径所需的软链接；不会一次启动三个
模态任务，也不会用通配符模糊选择 checkpoint。

```bash
# Stage 1: spectrum/SMILES matching（4 卡 DDP）
python -m benchmarks.models.vib2mol.workflow matching \
  --data-dir benchmark_data/release_v1 \
  --modality ir-raman \
  --epochs 100 --batch-size 256 --lr 1e-4 \
  --gpus 4 --device cuda

# Stage 2: autoregressive SMILES generation（填入上一命令返回的绝对路径）
python -m benchmarks.models.vib2mol.workflow generation-train \
  --data-dir benchmark_data/release_v1 \
  --modality ir-raman \
  --base-checkpoint /absolute/path/to/matching/epoch99.pth \
  --epochs 100 --batch-size 32 --lr 1e-4 \
  --gpus 4 --device cuda \
  --smiles-augment
```

单卡 demo 可以用一条 pipeline 命令串联两阶段：

```bash
python -m benchmarks run \
  --config benchmarks/configs/spectrum2structure/vib2mol.yaml
```

评估命令：

```bash
# matching 检索
python -m benchmarks.models.vib2mol.workflow retrieval-eval \
  --data-dir benchmark_data/release_v1 --modality ir-raman \
  --checkpoint /absolute/path/to/matching.pth --device cuda:0

# SPT 真正生成 SMILES
python -m benchmarks.models.vib2mol.workflow generation-eval \
  --data-dir benchmark_data/release_v1 --modality ir-raman \
  --checkpoint /absolute/path/to/spt.pth \
  --beam-size 10 --device cuda:0
```

`--use-formula` 可训练/评估分子式条件模型；任务名会自动变为上游要求的
`ir-raman-kekule_smiles-formula`。当前导出器会写 `formula`。上游 generation
evaluator 即使不启用分子式条件也会读取该列，所以旧版 Vib2Mol LMDB 需重导出：

```bash
python -m benchmarks.data.prepare \
  --pickle artifacts/processed/openspec.pickle \
  --manifest datasets/openspec_manifest.parquet \
  --split-file builds/openmolspec-20260830/release-v1/splits/align_split.parquet \
  --output benchmark_data/release_v1 --formats vib2mol \
  --workers 32 --overwrite
```

### 2.4 光谱→结构（构象判别）（Vib2Conf）

```bash
bash benchmarks/scripts/run_vib2conf.sh
```

前置：

```bash
mkdir -p benchmarks/models/vib2conf/upstream/datasets
ln -sfn "$(pwd)/benchmark_data/vib2conf" benchmarks/models/vib2conf/upstream/datasets/openspec_vc
```

任务（`--ds openspec_vc`）：`raman`、`ir`、`ir-raman`，模型
`vib2conf_equiformer_moe_balance0001`。测试集指标：`eval.py` → Recall@1/3/5。

### 2.5 光谱→属性（Vib2Conf 谱编码器 + 回归头）

Vib2Conf 上游的 `--grad-props` 在 pin commit 中只做参数校验、未接入训练；
本仓库在 `benchmarks/models/vib2conf/props_head.py` 中实现了该契约
（复用其 SpectralEncoding + SpectralEncoder + AttentionalPooling 结构，
配置同 `vib2conf_equiformer_base_pool4`，加每个性质一个回归头）。

```bash
python -m benchmarks.models.vib2conf.props_head \
    --data-dir benchmark_data/vib2conf \
    --output reports/benchmark \
    --epochs 100 --batch-size 128 --lr 5e-5 --device cuda:0
```

- 输入 IR+Raman（可 `--no-concat-spectrum` 单模态），目标同上 6 个性质。
- 输出：`reports/benchmark/results_spectrum2property_vib2conf.{csv,json}`。

## 4. 结果回填

GPU 跑完后，把各任务指标汇总到：

```
reports/benchmark/results_template.csv   # 模板见下
```

| task | model | modality | metric | value | seed | data_version | notes |
|---|---|---|---|---|---|---|---|
| structure2property | EquiformerV3 | 3D | MAE_energy / R2_gap / ... |  | 624 | openspec-v1.0 | |
| structure2spectrum | EquiformerV3 | 3D | MAE_ir / cosine_raman |  | 624 | openspec-v1.0 | |
| spectrum2structure | Vib2Mol | ir | top1 / top10 |  | 624 | openspec-v1.0 | |
| spectrum2conformer | Vib2Conf | raman | recall@1 / @3 / @5 |  | 624 | openspec-v1.0 | |
| spectrum2property | Vib2Conf+head | ir+raman | MAE_energy / R2_gap |  | 624 | openspec-v1.0 | |

`data_version` 使用 `benchmark_data/summary.json` 中的记录数 + seed 标记，
保证与发布版本一一对应。

## 5. 预计资源

- EquiformerV3（6 层、128 通道，~25M 参数）：1×A100 约 0.5–1.0 s/step，
  50 epoch × ~25k step ≈ 1–2 天；可用 `--backbone-override` 调整规模。
- Vib2Mol / Vib2Conf：上游默认配置，4×GPU 约 1–2 天/任务。
- 当前已验证数据导出器和训练 CLI 可加载；GPU 训练时长需在目标集群实测，不能
  将 CLI/导出测试等同于模型训练成功。

## 6. 复现性清单

- [ ] `python -m benchmarks.data.prepare --split-file <release>/splits/align_split.parquet --workers 32`
- [ ] 固定 GPU 驱动 / CUDA / PyTorch 版本并记录
- [ ] 三个 vendored 仓库 commit 已 pin（vib2mol `207a86e`、vib2conf `7038837`、
      equiformer_v3 `a7300c5`）
- [ ] 每个任务记录 seed、训练步数、GPU 时数、参数量、最优权重路径
- [ ] 结果回填 `reports/benchmark/results_template.csv`
