# 当前执行规划：200k / 1M 与 H/C NMR

更新日期：2026-09-14。本文件优先于历史的五档 scaling 与谱图构建说明。

## 阶段与范围

1. 清理已停止的 spectrum→property 实验：将 runs 中该 family 的日志、
   TensorBoard、checkpoint 和配置快照迁到 artifacts 的可恢复归档。
   其他任务（尤其 Hessian、response、Vib2Mol）的历史数据/实验不删除或覆盖。
2. 为 200k 和 1M 重建谱→属性 LMDB，包含 IR、Raman、H/C 计算位移及四种属性。
3. 完成 IR+Raman+¹³C+¹H 的 200k/1M 共享 Transformer 基线，单属性单模型。
4. 1M 结束后再讨论 IR、Raman、1H、13C 的模态消融，当前不启动消融。
   模型已经使用 H/C 位移，详见[共享编码器说明](shared_spectroscopy.md)。
5. Vib2Mol 也接入 H/C，但保留原有六层 encoder，不采用 2+4 pooling。
   新数据另存至 `release_v1_ks{200,1000}k_hc_nmr_minmax`，见 [Vib2Mol 说明](vib2mol_hc_nmr.md)。

只将 200k/1M 作为新的主实验；Hessian 等任务历史配置保留以便追溯，不继续扩展中间档。
正式谱→属性目标现为 dipole magnitude、isotropic polarizability、HOMO–LUMO gap。
Polarizability anisotropy 配置已归档，不再训练；下文四属性构建与核验数字是历史数据事实，
已有字段继续保留，无需重建 LMDB，也不删除已有实验结果。
谱→属性和 Vib2Mol 的 400k/600k/800k YAML 已移到 docs/archives/benchmark-configs/。
不要删除冻结 payload、原始 Gaussian 日志、分子去重结果、scaffold/KS 划分或 TMS 参考。

## 固定训练预算

| 任务 | 每次训练 optimizer steps | 验证间隔 | batch / GPU 数 | 学习率 |
|---|---:|---:|---|---|
| spectrum→property | 312,500 | 2,500 | 128 / 1 | 5e-5 |
| Vib2Mol matching | 312,500 | 2,500 | 64 / 4（global 256） | 1e-4 |
| Vib2Mol generation | 312,500 | 2,500 | 64 / 4（global 256） | 1e-4 |

在同一任务内固定模型、global batch、seed=624、按 optimizer step 更新的 cosine
调度；不要以 epoch 数或早停改变总预算。不同任务的相同步数不代表相同 FLOPs。
Vib2Mol 两阶段独立计数，合计 625,000 updates。

每档使用完全相同的验证 10,390 / 测试 20,390；200k 是 1M 的嵌套 KS 子集。
所有新实验从头开始，timestamp+hash 自动命名，不加载已归档 checkpoint。
属性使用训练集统计量标准化，SmoothL1(beta=1)，MAE/RMSE 还原为 D、Å³、eV。

## NMR 语义与来源

读取冻结 `payload/nmr` 中的 `atomic_numbers` 和 `nmr_isotropic`，
只按同一 `align_sample_id` 配对，不改用同 InChIKey 的其他构象或计算记录。
不使用旧的 `nmr_shifts`（实际为 shielding 副本）或旧的 0–12 展宽谱。

TMS 日志：`artifacts/calculations/tms_reference/tms_reference.log`。
SHA-256：`d6273f14fda3cb5e2c0b2fe8d0100dabcb2ca29bddf3eccf632c82ed4e2e1bce`。
脚本重新读取日志并校验优化完成、45 个正频率、17 个屏蔽值和正常结束，
不是使用无法追溯的手写 reference 常数。

- H: sigma_ref = 31.706375 ppm；C: sigma_ref = 191.483675 ppm。
- delta = sigma_ref - sigma（常用近似）；转换以 float64 运算，输出 float32。
- 几何：B3LYP/6-311+G(d,p)，D3BJ，ultrafine，nosymm。
- NMR：OPBE/6-311+G(2d,p)，保留生产模板的 IOP(3/76=0770002300,
  3/77=1000010000,3/78=1000010000)，气相。
- 本次核对 11 个来源各一份日志，NMR route 匹配。未逐条核实所有历史日志的方法；
  方法一致性仍需在发布 QC 中完整审计。

新增字段：

| 字段 | 含义 |
|---|---|
| nmr_h_shifts_ppm / nmr_c_shifts_ppm | 独立、升序、变长的逐原子计算位移集合 |
| nmr_h_present / nmr_c_present | 该核种是否存在；真实无核种保持空数组，不伪造零峰 |
| nmr_reference_id / nmr_shift_unit | 参考版本标识和 ppm 单位 |
| nmr_sample_id | 配对来源，仅用于审计，不输入模型 |
| nmr_representation / nmr_quality_flags | 表示约定、空核种标记 |

不输出原子编号/指认，不为模型添加化学式或结构标签；不裁剪负值/极端值，
不对位移逐分子 min–max，不假设等价原子已平均，不伪造积分、J 耦合或多重峰。
这不是完整实验 NMR 谱，也未包含溶剂或构象系综校准。

IR/Raman 保留来源 LMDB 中的 float32 min–max 数组及归一化元数据。
四种属性及其物理单位逐值保留，不重复换算。原始 Raman 计算仍保持 float64。

## 构建与验证

生产模块：`benchmarks.data.prepare_multimodal_properties`。
一次遍历 NMR 分片，同时产生 200k 和 1M；每 8192 条提交 LMDB 事务。
拒绝覆盖，缺失记录/非法字段直接失败而非静默丢弃。summary state=completed
才允许使用；构建失败的目录保留以便诊断，不应当作训练数据。

```bash
python -m benchmarks.data.prepare_multimodal_properties
```

默认源是已验证的 `benchmark_data/spectrum_properties_ks1000k_minmax`。
若旧数据已迁移到可恢复归档，重新构建时用 `--source <归档中该目录>`，
并指定新的 `--output-root`，从 inventory.json 查找归档位置。
`--limit-per-split 8 --output-root reports/benchmark/hc_nmr_build_smoke` 可用于小样本检查。

输出：

- benchmark_data/spectrum_properties_ks200k_hc_nmr_minmax/
- benchmark_data/spectrum_properties_ks1000k_hc_nmr_minmax/

每个目录包含 vib2conf/{train,eval,test}.lmdb、benchmark_split.parquet、
nmr_reference.json、summary.json（计数、位移范围、核种缺失数、来源等）。
当前 LmdbPropsDataset 读取 IR/Raman、H/C 位移与指定属性，collate 生成变长
NMR padding mask。H/C 分别用训练集 median/IQR 归一化；验证/测试不参与拟合。
数据已完成，无需因更换模型重新构建 LMDB。

## 启动

以下先示范 dipole；polar_iso、gap 用同目录对应单属性 YAML。

```bash
python -m benchmarks run --config benchmarks/configs/spectrum2property/dipole_total_ks200k.yaml --debug
python -m benchmarks run --config benchmarks/configs/spectrum2property/dipole_total_ks200k.yaml
python -m benchmarks run --config benchmarks/configs/spectrum2property/dipole_total_ks1000k.yaml
```

## 可恢复清理

```bash
python benchmarks/scripts/retire_spectrum_properties.py
python benchmarks/scripts/retire_spectrum_properties.py --apply
```

默认 dry-run；必须先停掉所有 VPS 上相关任务。脚本只迁移已明确限定的
spectrum2property 目录，不根据遗留 status=running 文件擅自取消进程。
`--include-data` 仅在两个新数据集完成后允许归档旧五档谱→属性数据（包括旧 cache）。
归档位于 artifacts/retired-spectrum2property-<UTC>/，inventory.json
逐项记录原路径与新路径。恢复时确认原路径不存在再迁回；移动不释放磁盘空间。

## 本次执行结果

- 两档构建完成，共用一次完整 NMR 遍历，总耗时约 223 秒，excluded=0。
- 200k: train=200,000 / eval=10,390 / test=20,390。
- 1M: train=1,000,000 / eval=10,390 / test=20,390。
- 全量 LMDB key 与官方索引一致，训练集嵌套、验证/测试集一致，sample ID 无跨集交集。
- 384 次记录抽查的 IR/Raman 与四种属性逐值保持不变；255 个不同样本的
  H/C 位移从原始 payload 独立重新计算，与新字段逐值一致；当前训练 loader/collate 通过。
- 相关 22 项单元测试通过；尚未启动 GPU 训练。

旧 20 个 property runs（5 个 family 目录）和 3 个相关报告目录归档到：
`artifacts/retired-spectrum2property-20260914T081038477392Z/`。
旧五档 raw/minmax 数据共 10 个目录归档到：
`artifacts/retired-spectrum2property-20260914T081539155250Z/`。
其中可复现重建的源为后者下的 `benchmark_data/spectrum_properties_ks1000k_minmax`。

重要：构建成功不等于 NMR 物理质量已全部通过。1M 训练集有 442 条无 H、52 条无 C，
200k 分别为 109、12；两档共同验证/测试集各有 2 条无 H，均无缺 C 记录。
这些条目保持空数组/存在标记，不为满足全核种条件改动既有划分。
1M 训练集 H 位移范围约 [-109.16, 57.65] ppm，C 约 [-950.54, 1260.68] ppm。
极端值原样保留，未直接判定为失败；仍需核查电子态、计算收敛、方法一致性和
解析完整性。当前模型消费这些字段，median/IQR 不裁剪异常值，也不能替代物理 QC。

后续发布前还需迁移生产 NMR schema：明确区分 shielding 与 referenced chemical shift，
停止将旧 `nmr_shifts`/混合核种展宽谱作为正确的位移谱。不要原地篡改当前冻结发布包。
