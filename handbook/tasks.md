# 任务目录

此表由 `openmolspec_bench/catalog.py` 自动生成，与命令行和 Studio 使用同一份定义。

已接入表示存在评测适配器，仍需对应权重与数据；待接入不会产生占位分数。

| ID | 任务 | 谱型 | 数据域 | 适配器 | 指标 |
| --- | --- | --- | --- | --- | --- |
| `nmr.forward.1H` | 结构 → 1H 峰列表 | 1H | experimental | nmrnet_predictions | matched_peak_mae_ppm, matched_peak_rmse_ppm, peak_count_mae, matched_fraction |
| `nmr.forward.13C` | 结构 → 13C 峰列表 | 13C | experimental | nmrnet_predictions | matched_peak_mae_ppm, matched_peak_rmse_ppm, peak_count_mae, matched_fraction |
| `nmr.forward.19F` | 结构 → 19F 峰列表 | 19F | experimental | nmrnet_hetero_predictions | mae_ppm, rmse_ppm |
| `nmr.forward.31P` | 结构 → 31P 峰列表 | 31P | experimental | nmrnet_hetero_predictions | mae_ppm, rmse_ppm |
| `nmr.forward.11B` | 结构 → 11B 峰列表 | 11B | experimental | nmrnet_bsi_diagnostic | mae_ppm, rmse_ppm |
| `nmr.forward.29Si` | 结构 → 29Si 峰列表 | 29Si | experimental | nmrnet_bsi_diagnostic | mae_ppm, rmse_ppm |
| `nmr.retrieval.h.s2m` | 谱图 → 结构检索 · H | 1H | experimental | spec2struct_alignment | recall_at_1, recall_at_5, recall_at_10, mrr |
| `nmr.retrieval.h.m2s` | 结构 → 谱图检索 · H | 1H | experimental | spec2struct_alignment | recall_at_1, recall_at_5, recall_at_10, mrr |
| `nmr.generation.h` | 谱图 → SMILES · H | 1H | experimental | spec2struct_generation | valid_rate, exact_rate, formula_match_rate |
| `nmr.retrieval.c.s2m` | 谱图 → 结构检索 · C | 13C | experimental | spec2struct_alignment | recall_at_1, recall_at_5, recall_at_10, mrr |
| `nmr.retrieval.c.m2s` | 结构 → 谱图检索 · C | 13C | experimental | spec2struct_alignment | recall_at_1, recall_at_5, recall_at_10, mrr |
| `nmr.generation.c` | 谱图 → SMILES · C | 13C | experimental | spec2struct_generation | valid_rate, exact_rate, formula_match_rate |
| `nmr.retrieval.hc.s2m` | 谱图 → 结构检索 · HC | 1H, 13C | experimental | spec2struct_alignment | recall_at_1, recall_at_5, recall_at_10, mrr |
| `nmr.retrieval.hc.m2s` | 结构 → 谱图检索 · HC | 1H, 13C | experimental | spec2struct_alignment | recall_at_1, recall_at_5, recall_at_10, mrr |
| `nmr.generation.hc` | 谱图 → SMILES · HC | 1H, 13C | experimental | spec2struct_generation | valid_rate, exact_rate, formula_match_rate |
| `vibrational.gap.ir` | IR → HOMO–LUMO gap | IR | computed | studio_gap | mae_ev, rmse_ev |
| `vibrational.gap.raman` | RAMAN → HOMO–LUMO gap | RAMAN | computed | studio_gap | mae_ev, rmse_ev |
| `vibrational.gap.ir_raman` | IR_RAMAN → HOMO–LUMO gap | IR, RAMAN | computed | studio_gap | mae_ev, rmse_ev |
| `vibrational.gap.ir_raman_hc` | IR + Raman + H/C NMR → HOMO–LUMO gap | IR, Raman, 1H, 13C | computed | studio_gap | mae_ev, rmse_ev |
| `vibrational.forward` | 构象 → IR / Raman | IR, Raman | computed | studio_vibrational_forward | ir_cosine_similarity, raman_cosine_similarity, ir_mae, raman_mae |
| `vibrational.retrieval` | IR / Raman → 结构检索 | IR, Raman | computed | vib2mol_retrieval | recall_at_1, recall_at_5, recall_at_10, mrr |
| `vibrational.generation` | IR / Raman → SMILES | IR, Raman | computed | vib2mol_generation | exact_rate, valid_rate |
| `nmr.assignment` | H/C 峰 → 原子指认 | 1H, 13C | experimental | nmrnet_atom_assignment | matched_peak_fraction_macro, matched_residual_mae_ppm, assignment_accuracy |
| `nmr.solvent_transfer` | H/C 跨溶剂位移 · 参考检索基线 | 1H, 13C | experimental | nmr_solvent_reference | mae_ppm, unchanged_shift_mae_ppm |
| `nmr.formula` | 谱图 → 分子式 | 1H, 13C | experimental | 待接入 | formula_exact_rate |
| `spectroscopy.qa` | 谱学问答 / 推理 | NMR, IR, Raman | experimental | 待接入 | answer_accuracy |
| `spectroscopy.reranking` | 谱图 + 候选结构 → 重排 | IR, Raman | computed | vib2mol_reranking | top_1_hit_rate, mrr |
| `vibrational.retrieval.hc` | IR + Raman + H/C → 结构检索 | IR, Raman, 1H, 13C | computed | vib2mol_retrieval | recall_at_1, recall_at_5, recall_at_10, mrr |
| `vibrational.generation.hc` | IR + Raman + H/C → SMILES（Xinyu 协议） | IR, Raman, 1H, 13C | computed | vib2mol_generation | exact_canonical_top1, exact_canonical_top5, valid_smiles_fraction |
| `spectroscopy.reranking.hc` | IR + Raman + H/C + 候选 → ITM 重排 | IR, Raman, 1H, 13C | computed | vib2mol_reranking | top_1_hit_rate, mrr |
| `ms.forward.glacier` | 分子 → MS/MS（GLACIER） | MS/MS | experimental | ms_pretrained_glacier | cosine_similarity, entropy_similarity |
| `ms.forward.iceberg` | 分子 → MS/MS（ICEBERG） | MS/MS | experimental | ms_pretrained_iceberg | cosine_similarity, entropy_similarity |
| `ms.annotation.magma` | MS/MS 峰 → MAGMa 候选碎片标注 | MS/MS | experimental | magma_algorithm | matched_peak_fraction, checked_fragments |
| `multispectral.spectrallm.generation` | 多谱 → 结构（SpectraLLM） | IR, Raman, NMR, MS/MS | mixed | 待接入 | exact_rate, valid_rate |

## 任务说明

- **nmr.forward.1H**：对已有 NMRNet/NMRNet++ 推理文件评分；无逐原子指认时使用最小代价峰匹配。

- **nmr.forward.13C**：对已有 NMRNet/NMRNet++ 推理文件评分；无逐原子指认时使用最小代价峰匹配。

- **nmr.forward.19F**：已拦截旧输入错配；冻结重跑后固相权重的溶液位移参考仍未确认，默认跳过正式评分，仅显式允许跨域诊断。

- **nmr.forward.31P**：已拦截旧输入错配；冻结重跑后固相权重的溶液位移参考仍未确认，默认跳过正式评分，仅显式允许跨域诊断。

- **nmr.forward.11B**：已用液相 All-nucleus NMRNet 各完成 32 分子冻结诊断；B/Si 训练覆盖与实验标签来源未验证，正式评分仍跳过。

- **nmr.forward.29Si**：已用液相 All-nucleus NMRNet 各完成 32 分子冻结诊断；B/Si 训练覆盖与实验标签来源未验证，正式评分仍跳过。

- **nmr.generation.h**：显式提供分子式；模型按分子式重排 beam，需与无分子式结果分开比较。

- **nmr.generation.c**：显式提供分子式；模型按分子式重排 beam，需与无分子式结果分开比较。

- **nmr.generation.hc**：显式提供分子式；模型按分子式重排 beam，需与无分子式结果分开比较。

- **vibrational.gap.ir_raman_hc**：按 checkpoint 的 ir-raman-nmr 完整输入运行；同时报告训练均值常量基线。

- **vibrational.forward**：已有 Hessian/response 模型在原始 Gaussian 日志的同一几何上预测；默认两个真实日志示例，仅作配对流程检查。

- **vibrational.retrieval**：已有 Vib2Mol checkpoint 直接编码本次选中样本；提供 IR+Raman，不提供 H/C。

- **vibrational.generation**：直接运行已有 Vib2Mol beam 解码，不使用缓存或近邻回放；原始 beam top-1，不进行分子式重排。

- **nmr.assignment**：直接运行冻结 NMRNet H/C 权重，加对称位点合并与带容差的全局匹配。原子编号随输出保存；缺实验指认参考时准确率为 null。

- **nmr.solvent_transfer**：无训练的实测参考检索迁移，排除查询分子及同连接关系的立体异构体；已跑 32 分子。不是神经网络模型，专用权重仍待接入。

- **nmr.formula**：用户已明确暂不推进；历史结果仅作归档，不再运行。

- **spectroscopy.qa**：用户已明确暂不推进；历史结果仅作归档，不再运行。

- **spectroscopy.reranking**：Vib2Mol ITM 正类概率重排显式候选池；候选池由本次选中的不同参考结构构成。

- **vibrational.retrieval.hc**：使用 Xinyu 保存的四模态 checkpoint、H/C 参考与归一化；生成按原评测脚本去重和 ITM 重排。

- **vibrational.generation.hc**：使用 Xinyu 保存的四模态 checkpoint、H/C 参考与归一化；生成按原评测脚本去重和 ITM 重排。

- **spectroscopy.reranking.hc**：使用 Xinyu 保存的四模态 checkpoint、H/C 参考与归一化；生成按原评测脚本去重和 ITM 重排。

- **ms.forward.glacier**：直接调用作者的冻结 checkpoint；使用我们测试 CSV 的实测谱并核对分子、加合物和采集条件。

- **ms.forward.iceberg**：直接调用作者的冻结 checkpoint；使用我们测试 CSV 的实测谱并核对分子、加合物和采集条件。

- **ms.annotation.magma**：原算法，无训练；原子索引以 engine_smiles 为准并逐碎片验证，标注不等于实验确认的机制。

- **multispectral.spectrallm.generation**：用户已明确暂不推进；历史结果仅作归档，不再运行。
