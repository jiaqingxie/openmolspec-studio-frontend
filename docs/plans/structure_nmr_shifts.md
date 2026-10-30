# 构象 → 原子级 H/C 化学位移

本阶段新增数据构建器 `python -m benchmarks.data.prepare_nmr_shifts`，
不改变现有训练任务，不修改原始 LMDB、冻结 payload 或 Gaussian 日志。
训练已接入独立的 `structure2nmr` 任务：共享 EqV3 backbone，H/C 各一个原子级
标量 head，不使用分子级 pooling，也不复用排序后的谱图 NMR 列表。

## 标签与构象配对

谱图模型的 H/C 位移是排序后的无归属列表，不能直接作为原子标签。
冻结 NMR payload 保存了原子顺序和 shielding，但没有保存坐标。
因此本构建器：

1. 按原有 align sample ID 关联 NMR payload 和 manifest。
2. 读取 manifest 指定的 NMR 日志，核对 SHA-256。
3. 要求单一、完整、连续编号的 shielding block。通常要求正常结束；仅接受两种明确的收尾失败：
   已 Leave Link 601 后进入 l9999 并发生 Erroneous write 或明确由 l9999 报 Error termination
   （且没有进入后续计算链接）；或已 Leave Link 1002，
   紧接 Internal input file was deleted! 和 Error termination via Lnk1e，并在此结束。
   两种情况均必须已输出完整有限的逐原子 3×3 tensor、有 SCF 完成和 GIAO 标记，
   且没有提前报错。此类记录仍核对冻结标签和哈希，
   标记 `normal_termination=False`，并写入 `recovered_records.parquet` 供审核。
   汇总字段 `recovered_abnormal_termination_counts` 记录各 split 恢复的记录数。
   对混写日志，仅当所有早期错误都在所用 orientation 之前、后段正常结束，
   且唯一末尾 archive 的原子顺序、电荷/多重度、距离矩阵和保手性刚体拟合均匹配
   （坐标容差 5e-5 Å），才允许恢复后段；仍要求完整 SCF/GIAO/tensor 和最终链接证据。
   此类记录保守标记为异常恢复，不把整个混写日志标作正常。
   若 orientation 缺失或原子编号与 shielding 不匹配，可使用同一日志的唯一终末
   SP/NMR archive 坐标；要求最终正常结束、完整有限的逐原子张量、原子序列一致、
   Link 1002→601→9999 收尾完整，archive 的 HF 有限且 RMSD ≤ 1e-7。
   此路径独立读取 archive 电荷/多重度，并标记
   `nmr_geometry_source="NMR terminal SP archive"`；仍核对冻结标签和原始哈希。
   另接受一种严格限定的外部截断：完整逐原子 shielding tensor 和 SCF/GIAO
   证据已经输出并正常 `Leave Link 1002`，其后只进入一次 Link 601，文件恰好终止于
   `Calculating spin-rotation constants.`。该路径不接受任意 EOF、额外链接、错误行或
   不完整 tensor，并仍逐原子核对冻结 payload 与源文件哈希。
   另有两类仅限已观测签名的收尾恢复：其一是在正常 `Leave Link 1002` 后，唯一后续
   Link 601 因 `FileIO operation on non-existent file` 或
   `RdWrB1 read garbage pointers` 明确异常退出；其二是正常 `Leave Link 601` 后进入
   最终 l9999，随后文件截断或在该链接内报错，且没有进入任何后续链接。前者只接受
   这两个已知 I/O 签名，不接受任意 Link 601 错误；后者仅涉及 Gaussian 最终归档/
   终止记录。两者仍要求完整 SCF/GIAO、全原子有限 3×3 tensor、冻结 payload 数值
   一致及源文件哈希一致，并分别写入可审计的 `nmr_completion` 状态。
4. 读取该 block 前最近一次 Input/Standard orientation，核对原子编号、元素顺序。
5. 与冻结 NMR payload 的原子序列、shielding 数值核对（绝对容差 1e-6 ppm）。
6. 使用该 NMR 计算自身的坐标，无需将它强行配到 frequency 坐标或另一个构象。

**不按 SMILES 重新排列，不按位移排序，不平均等价原子，不跨记录补标签。**

`--collect-errors` 会扫描全部输入后统一报告错误；只要还有错误，构建仍标记为失败，
不会发布缩小后的 split。它不同于会允许排除记录的 `--skip-invalid`。

构建成功后可逐条验收输出（只用于本地可信的 LMDB，内部使用 pickle）：

```bash
python -m benchmarks.data.verify_nmr_shifts --output benchmark_data/release_v1_ks200k_nmr_shifts_r5_v6
```

验收通过后写入 `verification.json`，覆盖全部图的 split 身份、H/C 标签 mask、
有限性、邻接边范围、统计量和恢复审计清单。

### 2026-09-14：200k 全量构建与验收

已完成 `benchmark_data/release_v1_ks200k_nmr_shifts_r5_v6`，并逐条读回全部 LMDB 验收。
`summary.json` 为 `completed`，`verification.json` 为 `verified`。

| 划分 | 分子记录 | H 标签 | C 标签 |
| --- | ---: | ---: | ---: |
| train | 200,000 | 2,990,043 | 2,045,949 |
| eval | 10,390 | 142,928 | 109,145 |
| test | 20,390 | 294,607 | 227,786 |

排除记录为 0，原始 scaffold split 不变。12 条训练记录经证据核对恢复并保留审计；
5 条训练记录不含 H/C，图仍保留，监督 mask 全 false，实际有监督训练分子为 199,995。
这是数据结构与提取一致性验收，不等同于完整物理 QC；未裁剪原始极端位移值。
本次未构建 1M 版本，也未启动结构→NMR 模型训练。
这保证坐标和 shielding 来自同一计算；并不宣称已证明 NMR 坐标与 frequency
最终构象完全相同。源计算方法尚未逐日志审核，参考计算已校验。

### 2026-09-17：1M 全量构建与验收

`benchmark_data/release_v1_ks1000k_nmr_shifts_r5` 已由完整 align split 干净重建，
`summary.json` 为 `completed`，独立逐条读回后的 `verification.json` 为 `verified`。

| 划分 | 分子记录 | H 标签 | C 标签 | 无 H/C 监督记录 |
| --- | ---: | ---: | ---: | ---: |
| train | 1,000,000 | 14,839,163 | 10,253,539 | 22 |
| eval | 10,390 | 142,928 | 109,145 | 0 |
| test | 20,390 | 294,607 | 227,786 | 0 |

排除记录为 0，原始 scaffold split 不变；实际有监督训练分子为 999,978。
51 条训练记录属于上述证据约束下的异常收尾恢复，均保存在
`recovered_records.parquet` 并通过冻结 payload、源哈希和逐条 LMDB 验收。
训练集 H/C population 统计分别为 `3.077777 ± 2.295987 ppm` 和
`81.107820 ± 53.378339 ppm`。

参考仍是 `tms-d6273f14fda3cb5e`：

- H：sigma_ref = 31.706375 ppm。
- C：sigma_ref = 191.483675 ppm。
- delta = sigma_ref - sigma；计算参考位移，非实验校准位移。

## PyG Data / LMDB 格式

| 字段 | 形状 / 含义 |
|---|---|
| `pos` | `[N,3]`，float32，Å |
| `atomic_numbers` | `[N]`，所有元素，包括显式 H |
| `edge_index` | `[2,E]`，双向 radius graph，默认 5 Å |
| `nmr_shift` | `[N,1]`，float32，ppm，未标准化 |
| `nmr_mask` | `[N]`，只有 H/C 为 True |
| `nmr_h_mask` / `nmr_c_mask` | `[N]`，分核种监督/统计 |
| `atom_id` | `[N]`，分子内部 0-based Gaussian 顺序，批处理不偏移 |
| `charge` / `multiplicity` | 来自该 NMR 日志 |
| `sample_id` / `inchikey` / `source_dataset` | 可追溯身份与来源 |
| `nmr_reference_id` / `nmr_log_path` / `nmr_file_hash` | 标签与构象来源 |

非 H/C 的 target 填零只是占位，**绝不能参与监督或归一化统计**。
没有 H 或没有 C 的分子可以保留，缺失核种 mask 全 False。
没有任何 H/C 的记录同样保留，`has_nmr_target=False`、所有监督 mask 为 False。
summary 分别报告 `no_hc_target_counts` 和 `supervised_counts`，保留 split 数量不代表
所有分子都有本任务的监督目标。允许单原子图没有边，原子级训练器支持此情形。

## 构建命令

在 repo 根目录执行。需要原始 HPC 日志路径可访问，默认 32 个 I/O 线程、
有界预取；冻结 HDF5 字段每 shard 读取一次，LMDB 每 4096 条提交。
**默认严格模式**：不匹配、文件缺失、未能验证完整结果的异常结束等会停止，并写出失败报告，
不静默改变验证/测试集。输出目录必须不存在，禁止覆盖源数据。

200k：

```bash
OMP_NUM_THREADS=1 python -m benchmarks.data.prepare_nmr_shifts \
  --split-file builds/openmolspec-20260830/release-v1/splits/scaling/align_ks_200k.parquet \
  --output benchmark_data/release_v1_ks200k_nmr_shifts_r5 \
  --workers 32
```

1M：

```bash
OMP_NUM_THREADS=1 python -m benchmarks.data.prepare_nmr_shifts \
  --split-file builds/openmolspec-20260830/release-v1/splits/align_split.parquet \
  --output benchmark_data/release_v1_ks1000k_nmr_shifts_r5 \
  --workers 32
```

正式目标分别为 200,000 / 1,000,000 个训练分子，验证 10,390，测试 20,390。
完整通过严格校验后才能确认实际可用数量；不能将其它任务的成功计数当作本任务的构建结果。
如确实需要过滤坏记录，可显式使用 `--skip-invalid`，但这可能改变数量及共同 heldout，
必须审阅 `excluded_records.parquet` 后再决定是否训练。

输出包括 `equiformer_v3/{train,eval,test}.lmdb`、`benchmark_split.parquet`、
`nmr_reference.json`、`excluded_records.parquet`、`summary.json`。
只有 `summary.state == completed` 的输出可供后续训练使用。

## 训练实现与命令

配置：`benchmarks/configs/structure2nmr/hc_ks200k_r5.yaml` 和
`benchmarks/configs/structure2nmr/hc_ks1000k_r5.yaml`，保持相同模型、global batch
和 step 调度。200k 与 1M 原子级数据均已完成构建和验收，无需重新构建。
模型输入仅为元素、坐标和已存邻接边；
电荷/多重度目前仅保留为元数据，未编码进模型。

```bash
# 两卡 debug：短程试训，结束后不保留日志、checkpoint 或 TensorBoard
CUDA_VISIBLE_DEVICES=0,1 OMP_NUM_THREADS=1 python -m benchmarks run \
  --config benchmarks/configs/structure2nmr/hc_ks200k_r5.yaml --debug

# 正式训练：自动生成时间戳+哈希目录
CUDA_VISIBLE_DEVICES=0,1 OMP_NUM_THREADS=1 python -m benchmarks run \
  --config benchmarks/configs/structure2nmr/hc_ks200k_r5.yaml
```

4 层、lmax=4、mmax=2、5 Å；每卡 batch=64，两卡 global batch=128。
312,500 optimizer steps，学习率 3e-4→0，逐 step cosine 调度；每 2,500 steps 验证。
H/C 分别使用 summary 中训练集 population mean/std，不扫描验证/测试集拟合统计量。
每个核种计算标准化后的 SmoothL1（beta=1），再对有标签的核种等权平均；
DDP 先汇总有效原子数，修正梯度平均，使每个核种内按全局有效原子等权。
最佳 checkpoint 按 `mean(MAE_H/std_H, MAE_C/std_C)` 选取。
`MAE_H`、`RMSE_H`、`MAE_C`、`RMSE_C` 均为 **ppm**，`count_H/C` 为有效原子数。

checkpoint 保存训练归一化参数、参考物、split 哈希及模型配置；恢复时核对一致性。
产物位于自动 run 目录的 `artifacts/equiformer_v3_structure2nmr_best.pt`、
`artifacts/results_structure2nmr.json`，并沿用公共 TensorBoard 记录器。
空 H/C mask 保持图连接的零 loss；全批次无边时使用与真实图断开的辅助图适配
上游空边限制，其输出被丢弃，不给真实原子添加虚假邻接关系。

已通过真实数据缩小模型的两进程 CPU/Gloo debug 测试，包含不等长 heldout 分片；
未在当前环境进行 CUDA/NCCL 或正式规模显存验证。

## 训练约定

- 等变结构 backbone，逐原子标量输出，不做分子 sum/mean pooling。
- H/C 的归一化参数分开，仅使用对应训练子集；summary 提供 population mean/std。
- 建议 H/C 分别计算 normalized loss 再合并，避免 C 的数值尺度或 H 的原子数主导。
- 无 H/C 分子不贡献 loss、MAE 或归一化统计。全空监督 batch 不得对空数组求 mean；
  DDP 下必须统一处理（例如图连接的零 loss 并正确归约有效原子数），不能单 rank 跳过 backward。
- 验证/测试分别报告 `MAE_H` 与 `MAE_C`（ppm），在反标准化后计算。
- 所有构象应继承其分子的 split，不允许帧级随机拆分。
- 数据内的其它标签和身份字段仅用于追溯；模型输入只选择结构、元素以及明确约定的电荷/自旋信息。

测试：`python -m unittest discover -s tests -p test_structure_nmr_data.py -v`。

2026-09-14 已完成 128 train + 128 eval + 128 test 的真实数据检查，
位于 `reports/benchmark/structure_nmr_validation/`，未剔除记录。
该目录是抽样验证，不是完整 200k/1M 数据集。
