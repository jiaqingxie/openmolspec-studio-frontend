# 数据与输入格式

## 工作区结构

```text
OpenMolSpec/
  data/align_eval/
    nmrspec_test/test.jsonl
    patent_test_10k/test.jsonl
    nmrexp_exp_10k/test.jsonl
    nmrgym_test/test.jsonl
  runs/
    f90bd7f743574d18a7f72ae72ce95e59/best.pt  # H/C alignment
    bebaecf2bca248f1a47eaa01f403002a/best.pt  # H/C generation
  studio/                                  # 本前端仓库的本地检出，可放在其他位置
```

评测时可用 `--alignment-checkpoint` 和 `--generation-checkpoint` 指定其他已有权重。推理会检查权重内 `training_stage` 并严格加载结构一致的参数。

## H/C JSONL

每行一个参考分子：

```json
{"smiles":"CCO","formula":"C2H6O","h_nmr":[{"type":"1H NMR","chemical_shift":"1.20 (t, J=7.0 Hz, 3H), 3.65 (q, J=7.0 Hz, 2H)","solvent":"CDCl3","frequency":"400 MHz"}],"c_nmr":[{"type":"13C NMR","chemical_shift":"18.2, 58.3"}],"modality_mask":[1,1]}
```

峰位置使用 ppm。`modality_mask` 依次表示 H、C，允许 `[1,0]`、`[0,1]`、`[1,1]`；可见核必须有记录。旧字段 `molecular_formula` 作为 `formula` 的别名。缺失 mask 时按实际记录推断。生成需要显式分子式；检索不把分子式编码成输入。缺失分子式不会从参考结构偷偷推导。

读取时规范化异构 SMILES、合并相同规范结构，按文件顺序选择前 N 个符合谱型的结构。检索的 byte 编码器有目标长度上限：超过容量的候选会计入 `exceeds_model_capacity` 并继续取后续记录，不截断结构。

## 数据域与划分

实验 NMR 应保留来源、核、溶剂、频率及可用的原子指认。计算 IR/Raman 保留计算方法及单位。实验 NMR 与计算 NMR 需要分开统计。

本次流程验证直接使用已有四个测试 JSONL，记录其哈希，不重新宣称已完成全部数据的实验性审核或训练集泄漏审核。发布严格 benchmark 前，需按 InChIKey 和 scaffold 审核与权重训练集的重叠，特别是 NMRExp、WanJuan、NMRShiftDB 之间及不同 ¹¹B 来源之间的重叠。

## 正向预测文件

默认读取 `--models-root`（默认工作区同级 `models/`）下：

```text
nmrnet/results/<dataset>_H/<fold>/*.out.pkl
nmrnetpp/results/<dataset>_H/<fold>/*.out.pkl
nmrnetpp/data_ours/<dataset>_H/valid.lmdb
```

C 核将 `_H` 换为 `_C`。`matid` 与对应 LMDB 的键排序一致；`select_atom` 定义每分子的有效原子，输出按这些有效原子展开。评分检查数量与 shape，再对各 fold 的相同原子做平均。只读取可信的本地 pickle 文件。

## Gap 标签

默认便携包的 Vib2Mol LMDB 中 `gap` 是 Hartree，评测显式乘 `27.211386245988` 转 eV。带 `units.gap` 的记录优先按元数据处理。自定义 `--gap-lmdb` 必须有该单位字段或显式提供 `--gap-unit hartree` / `--gap-unit eV`。输出预测和 MAE/RMSE 均为 eV。

若共享文件系统不支持 LMDB mmap，评测自动将该文件镜像到 `/tmp/openmolspec-bench-lmdb/`，结果的哈希仍对应原始文件。

## ¹⁹F / ³¹P 跨域诊断

读取 `models/nmrnet/results_solid/F/` / `P/` 下已有预测，对应 `models/nmrnetpp/pool_F/valid.lmdb` / `pool_P/valid.lmdb` 的标签。每条记录必须只有一个被指认的目标核原子，预测与标签 shape 必须一致。报告逐原子 ppm MAE/RMSE。

这些结果的模型来自固相域，测试标签来自已有 NMRExp/WanJuan 实验溶液池。输出显式标注 `model_domain=solid_state` 与 `evaluation_domain=experimental_solution`，作为跨域流程诊断；不能当作同域模型精度或经过独立 scaffold 划分审计的正式测试结果。¹¹B / ²⁹Si 目前只有数据，没有本入口已验证的权重预测对。
