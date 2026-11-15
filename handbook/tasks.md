# 任务目录

此表由 `openmolspec_bench/catalog.py` 自动生成，与命令行和 Studio 使用同一份定义。

已接入表示存在评测适配器，仍需对应权重与数据；待接入不会产生占位分数。

| ID | 任务 | 谱型 | 数据域 | 适配器 | 指标 |
| --- | --- | --- | --- | --- | --- |
| `nmr.forward.1H` | 结构 → 1H 峰列表 | 1H | experimental | nmrnet_predictions | matched_peak_mae_ppm, matched_peak_rmse_ppm, peak_count_mae, matched_fraction |
| `nmr.forward.13C` | 结构 → 13C 峰列表 | 13C | experimental | nmrnet_predictions | matched_peak_mae_ppm, matched_peak_rmse_ppm, peak_count_mae, matched_fraction |
| `nmr.forward.19F` | 结构 → 19F 峰列表 | 19F | experimental | nmrnet_hetero_predictions | mae_ppm, rmse_ppm |
| `nmr.forward.31P` | 结构 → 31P 峰列表 | 31P | experimental | nmrnet_hetero_predictions | mae_ppm, rmse_ppm |
| `nmr.forward.11B` | 结构 → 11B 峰列表 | 11B | experimental | 待接入 | matched_peak_mae_ppm, matched_peak_rmse_ppm, peak_count_mae, matched_fraction |
| `nmr.forward.29Si` | 结构 → 29Si 峰列表 | 29Si | experimental | 待接入 | matched_peak_mae_ppm, matched_peak_rmse_ppm, peak_count_mae, matched_fraction |
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
| `vibrational.forward` | 构象 → IR / Raman | IR, Raman | computed | 待接入 | spectral_cosine, spectral_mae |
| `vibrational.retrieval` | IR / Raman → 结构检索 | IR, Raman | computed | vib2mol_retrieval | recall_at_1, recall_at_5, recall_at_10, mrr |
| `vibrational.generation` | IR / Raman → SMILES | IR, Raman | computed | vib2mol_generation | exact_rate, valid_rate |
| `nmr.assignment` | 峰 → 原子指认 | 1H, 13C, 19F, 31P, 11B, 29Si | experimental | 待接入 | assignment_accuracy |
| `nmr.solvent_transfer` | 跨溶剂化学位移迁移 | 1H, 13C, 19F, 31P, 11B, 29Si | experimental | 待接入 | mae_ppm |
| `nmr.formula` | 谱图 → 分子式 | 1H, 13C | experimental | 待接入 | formula_exact_rate |
| `spectroscopy.qa` | 谱学问答 / 推理 | NMR, IR, Raman | experimental | 待接入 | answer_accuracy |
| `spectroscopy.reranking` | 谱图 + 候选结构 → 重排 | IR, Raman | computed | vib2mol_reranking | top_1_hit_rate, mrr |

## 任务说明

- **nmr.forward.1H**：对已有 NMRNet/NMRNet++ 推理文件评分；无逐原子指认时使用最小代价峰匹配。

- **nmr.forward.13C**：对已有 NMRNet/NMRNet++ 推理文件评分；无逐原子指认时使用最小代价峰匹配。

- **nmr.forward.19F**：已有 NMRNet 固相权重在实验溶液单核数据上的预测评分，明确作为跨域诊断结果。

- **nmr.forward.31P**：已有 NMRNet 固相权重在实验溶液单核数据上的预测评分，明确作为跨域诊断结果。

- **nmr.forward.11B**：保留六核任务定义；尚未验证可用于此实验域的 checkpoint 和预测文件。

- **nmr.forward.29Si**：保留六核任务定义；尚未验证可用于此实验域的 checkpoint 和预测文件。

- **nmr.generation.h**：显式提供分子式；模型按分子式重排 beam，需与无分子式结果分开比较。

- **nmr.generation.c**：显式提供分子式；模型按分子式重排 beam，需与无分子式结果分开比较。

- **nmr.generation.hc**：显式提供分子式；模型按分子式重排 beam，需与无分子式结果分开比较。

- **vibrational.forward**：Studio 已有 Hessian / response 推理入口；本统一基准尚未接入有配对参考值的评测数据。

- **vibrational.retrieval**：已有 Vib2Mol checkpoint 直接编码本次选中样本；提供 IR+Raman，不提供 H/C。

- **vibrational.generation**：直接运行已有 Vib2Mol beam 解码，不使用缓存或近邻回放；原始 beam top-1，不进行分子式重排。

- **nmr.assignment**：需要保留原子编号的实验参考值和匹配模型。

- **nmr.solvent_transfer**：需要同一分子跨溶剂配对记录及已有可用模型。

- **nmr.formula**：现有生成器使用给定分子式；不将其计为分子式预测器。

- **spectroscopy.qa**：需要有参考答案的题集和固定模型接口。

- **spectroscopy.reranking**：Vib2Mol ITM 正类概率重排显式候选池；候选池由本次选中的不同参考结构构成。
