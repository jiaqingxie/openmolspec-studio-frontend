# 基准评测

## 运行所有已定义任务

```bash
python -m openmolspec_bench run \
  --workspace /path/to/OpenMolSpec \
  --portable-root /path/to/openmolspec-studio-portable \
  --models-root /path/to/models \
  --tasks all --limit 32 --device cpu --threads 2 \
  --output results/all_smoke.json
```

`all` 会逐项报告待接入任务，不以占位分数代表通过。未找到必需资产为 `skipped`；数据错误、导入错误和模型运行错误为 `failed`，且命令最终返回非零退出码。每个任务完成后原子更新结果文件，因此中断前完成的结果仍可检查。只有包含 `completed_at` 的文件代表整个命令已结束。

## 单项评测

```bash
python -m openmolspec_bench run \
  --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.1H nmr.forward.13C \
  --datasets nmrspec_test --limit 32 \
  --output results/forward.json

python -m openmolspec_bench run \
  --workspace /path/to/OpenMolSpec \
  --portable-root /path/to/openmolspec-studio-portable \
  --tasks vibrational.gap.ir vibrational.gap.raman vibrational.gap.ir_raman \
  --limit 8 --output results/gap.json
```

## 指标

| 任务 | 指标与口径 |
| --- | --- |
| H/C 双向检索 | Recall@1/5/10、MRR；每个查询在本次选中的全部候选中排序，输出候选数量，分数相同按候选原始顺序排序 |
| H/C 生成 | 有效 SMILES 比率、规范异构 SMILES exact match、分子式一致率；提供分子式，按现有模型逻辑重排 beam 后取 top-1 |
| 正向 NMR 峰列表 | 最小绝对误差匹配后的 ppm MAE/RMSE，同时报告峰数误差、匹配覆盖率、评分分子数与参考覆盖数 |
| 光谱 → gap | MAE、RMSE，单位 eV；IR-only、Raman-only、IR+Raman 分别运行，未给 NMR |
| IR+Raman 检索 | 直接 Vib2Mol 编码，报告双向 Recall@1/5/10 与 MRR，候选为本次选中结构；不提供 H/C |
| IR+Raman 生成 | 直接 Vib2Mol beam 解码的原始 top-1，报告有效率与 exact match；不使用给定分子式或缓存回放 |
| 候选重排 | 用已有 Vib2Mol ITM 正类概率重排显式候选池，报告 top-1 和 MRR |

峰匹配误差按分子等权平均；没有逐原子标签时，这不是逐原子预测精度。匹配仅包含两边共有数量的峰，所以额外峰和缺失峰必须结合 `peak_count_mae` 与 `matched_fraction` 解读。

32 个候选的小样本检索分数不能直接与 1,000 / 10,000 / 全库候选的结果比较。`--limit` 变更后必须重新报告候选池及所选样本。流程验证结果也不能证明训练集去重或跨数据集泛化。

Vib2Mol 可以独立验证：

```bash
python -m openmolspec_bench run \
  --workspace /path/to/OpenMolSpec \
  --portable-root /path/to/openmolspec-studio-portable \
  --tasks vibrational.retrieval vibrational.generation spectroscopy.reranking \
  --limit 4 --beam-size 3 --output results/vib2mol.json
```

该入口只运行指定 checkpoint，不会自动切换成谱相似度检索或缓存生成。小样本使用 IR+Raman，不提供 H/C，属于已有多模态模型的缺核输入验证。

## 结果文件

JSON 保存任务 ID、数据域、数据文件和权重的 SHA-256、选择规则与排除数量、样本 ID、设备、PyTorch/Python 版本、耗时和状态。正向 NMR 保存的是已有预测的评分，明确标记 `score_existing_predictions`。本次不进行训练或更新权重。
