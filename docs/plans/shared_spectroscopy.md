# Shared spectroscopy Transformer

更新：2026-09-14。本文件的 2+4 pooling 仅用于 spectrum→property。
Vib2Mol 的 H/C 接入保留其原有六层 encoder，见 [Vib2Mol 说明](vib2mol_hc_nmr.md)；Hessian 不改动。

**Modality-specific embeddings + one shared Transformer encoder.**

## 输入与编码

| 模态 | 嵌入 | 位置与缺失处理 |
|---|---|---|
| IR + Raman | 两通道堆叠 → 1×1 channel fusion → stride=8 patch convolution | 共轴 400–4000 cm⁻¹、1024 点；patch 中心波数的 Fourier positional embedding |
| ¹³C | 每个 ppm 值一个 token，独立 C MLP + C type embedding | 不加序列位置；全缺失时 NO_C |
| ¹H | 每个 ppm 值一个 token，独立 H MLP + H type embedding | 不加序列位置；全缺失时 NO_H |

默认 128 个振动 token，拼接 `[T_vib; T_C; T_H]` 后进入共享的
2 层 TransformerEncoder。NMR padding 和有真实峰时的缺失占位 token 均被 mask；
无核种用空数组表示，不伪造零 ppm 峰。峰顺序不携带信息，重复位移仍保留。
有效峰缺少标签不是“无该核种”，数据加载会报错。

随后用 128 个可学习 query + 1 个 CLS，通过 4 层 attentional pooling。
每层依次执行 cross-attention（读取同一混合 memory，应用 padding mask）、
query self-attention、FFN。最后取 query CLS 输出接单属性回归头。
这对应 upstream Vib2Conf 的 2+4 结构，不是一次平均池化后再接四层 encoder。
128 个输入 Vib token 和 128 个 pooling query 是不同参数；query 无物理波数位置。

默认 d_model=512、8 heads、encoder_layers=2、pooling_layers=4、nlayers=6、
pooling_queries=128、FFN=4×d_model、dropout=0.1。
可在 YAML 的 `model.parameters` 修改参数；encoder_layers + pooling_layers 必须等于 nlayers。
没有独立的 NMR encoder，也没有先分别编码再 late fusion。

## 两类归一化

- IR/Raman：沿用已经完成的逐谱普通 min–max，float32，不重写 LMDB。
- H/C：分别按训练集所有对应核种的位移计算 `(δ − median) / IQR`。
  不逐分子归一化、不做分位数裁剪。IQR 为零或无该核种时 scale=1；无核种中心=0。
- 回归目标：沿用训练集均值/标准差和 SmoothL1(beta=1)。MAE/RMSE 反标准化
  后报告，单位为 dipole D、polarizability Å³、gap eV。

首次正式训练会缓存 H/C 统计量到数据集 `vib2conf/.cache/nmr_median_iqr.json`，
其他属性实验复用。缓存校验训练 LMDB 路径、大小、修改时间、参考文件摘要与策略。
200k/1M 各自拟合；验证/测试不参与。checkpoint 保存模型配置元数据以及
归一化 buffer，推理恢复时不需重新拟合。不要加载旧架构 checkpoint。

Debug 只在训练小子集拟合，不写归一化缓存、checkpoint 或 TensorBoard。
Robust scaling 不等于异常值清洗；极端 NMR 位移仍需要后续 QC。

## 当前实验

三种属性（dipole magnitude、isotropic polarizability、HOMO–LUMO gap）
× KS200k/1M 共六个正式 YAML，默认 `modality: ir-raman-nmr`。
Polarizability anisotropy 不再作为正式训练目标，其配置移入
`docs/archives/benchmark-configs/spectrum2property/`。已有 LMDB 字段、解析能力与实验结果保留，
不需要重建数据；三项目标均使用全部四种输入模态，并非一谱对应一属性。
同任务对齐 312,500 optimizer steps、每 2,500 steps 验证；先完成 1M 再做模态消融。
现有训练适配路径/注册名仍为 `vib2conf`，但模型是本仓库的共享 Transformer，
不再调用 upstream Vib2Conf 编码器。新 run variant 含 `shared-pooling-v2`，
checkpoint 架构标识为 `shared_spectroscopy_pooling_v2`；与先前纯六层 CLS 版本不兼容。

```bash
python -m benchmarks run \
  --config benchmarks/configs/spectrum2property/dipole_total_ks200k.yaml \
  --debug
```

去掉 `--debug` 正式训练；1M 改用 `dipole_total_ks1000k.yaml`。
其他目标为 `polar_iso`、`gap` 同名配置。
模型已经通过 NMR 排列不变性、padding 隔离、缺失核种、梯度与 checkpoint
恢复测试，并完成真实 LMDB 小样本 CPU 训练/验证/测试。尚未验证 GPU 显存和吞吐；
新结构下 batch_size=128 需要先试训确认，不能沿用旧模型的性能结论。

## 1M 模态递增实验

正式消融只比较下列有序输入，不做所有模态的组合爆炸：

1. IR；
2. IR + Raman；
3. IR + Raman + ¹H/¹³C NMR。

三种情况分别由 `build_ir_property_model`、
`build_ir_raman_property_model`、`build_ir_raman_nmr_property_model` 构建，
但共享完全相同的 Transformer 容量、1M scaffold split、seed、batch size 和
312,500-step 调度。非 NMR 工厂拒绝 NMR 统计量，全模态工厂缺少训练集 H/C
median/IQR 时直接报错。每个属性的文件名后缀分别是
`_ir_ks1000k.yaml`、`_ir_raman_ks1000k.yaml` 和 `_ks1000k.yaml`。
