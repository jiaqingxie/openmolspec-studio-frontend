# OpenMolSpec 任务评测

## 任务扩展评测（2026-11-23）

| 任务 | 样本和实测结果 |
| --- | --- |
| 单谱检索 | 每个来源 512 个固定查询，从同库 512 个候选逐步增加跨库干扰物至 2,048 个。在此规模上，NMRSpec、Patent、NMRExp、NMRGym 的 ¹H 谱→结构 Top-1 依次为 95.12%、74.61%、90.82%、15.82%，¹³C 为 49.80%、30.08%、47.07%、28.91%。[双向分库结果](../results/nmr_cross_source_library_scale.json) |
| IR + Raman 检索与重排 | 4,096 个结构候选、128 次查询，仅给振动谱，从双谱估计 H/C。在相同输入和候选上，Top-1 从 41/128 降到前 32 名重排后的 39/128，Top-5 从 90 降到 69。独立参考谱方法在同一批查询上的分数见下行。[双谱逐查询神经分数](../results/vib_shortlist4096_adapted.json) · [作者原版 128 候选对照](../results/vib_author_pilot128.json) |
| IR + Raman + ¹H + ¹³C 检索与重排 | 相同的 4,096 个候选和 128 次查询，提供全部四谱。Top-1 从检索的 118/128 升至前 32 名重排后的 120/128，Top-5 均为 128/128。此前在 1,024 候选和 64 个查询上分别为 63/64 和 64/64。[四谱逐查询神经分数](../results/vib_shortlist4096_four.json) · [1,024 候选](../results/vib_library1024_comparison.json) |
| 4,096 候选的参考谱检索 | 128 次查询。8,878 种参考分子与整批候选连通性互斥。IR、Raman、双谱、四谱以最近参考分子排序，Top-1 依次为 27、28、31、34 次；以八近邻对前 32 名重排为 23、26、38、41 次；对全部 4,096 个候选重排为 21、21、33、37 次。候选只提供 SMILES。[全库逐查询结果](../results/vib_reference_library4096.json) |
| 能隙 | 四谱在 1,024 个结构上 MAE 为 0.135 eV，训练均值基线为 0.804 eV。缺通道模型另按连通性留出 3,381 个样本，IR、Raman、双谱 MAE 分别为 0.382、0.318、0.288 eV，同批均值基线 0.749 eV。[四谱](../results/gap_four_channel_1024.json) · [缺通道](../results/gap_vibrational_heldout.json) |
| 一维原子指认 | 自有位点模型在全部训练和验证连通性之外评分，未指认峰计错。¹H 正确 6,633/12,543 个峰（1,720 种分子），¹³C 正确 18,193/31,018 个峰（3,142 种分子）。H 按相连重原子计分，对称等价位点可接受。冻结 NMRNet 在原 256 种分子/核的结果为 64.16% 和 82.73%，上游暴露范围不同。保守排除与公开液相库有相同重元素计数的结构后，仅余 25 和 12 种，且多数超出模型可推理范围。[自有模型](../results/assignment_all_heldout_sites.json) · [公开库排重审计](../results/assignment_exposure_audit.json) · [冻结模型子集](../results/assignment_liquid_archive_disjoint.json) |
| 跨溶剂位移 | 同一批 46 个分子、442 个原子配对，逐分子留出。¹³C 拟合校正与参考检索的 MAE 分别为 0.809 和 1.144 ppm，¹H 分别为 0.215 和 0.151 ppm。改用全部可比较的配对，¹H 共 1,453 对、20 种分子，按配对等权的 MAE 为原位移 0.144、参考检索 0.193、拟合 0.258 ppm；按分子等权则为原位移 0.375、参考检索 0.318、拟合 0.368 ppm。¹³C 共 283 对、26 种分子。[全部配对](../results/solvent_all_supported_pairs.json) · [原面板逐原子结果](../results/solvent_transfer_fitted.json) |
| MS/MS 碎片候选 | 使用 MechFrag-MS 的 balanced_neutral_context 锁定权重，模型 SHA-256 前缀为 4efd945c。55 张有采集条件的实测谱，1,741 个峰，10 ppm 内 MechFrag-MS、MAGMa 命中率分别为 62.26%、58.13%。另 9 张缺少条件。该指标衡量质量匹配覆盖率，碎片结构真值仍缺。[同峰对照](../results/mechfrag_fragment_annotations.json) |
| SpectraLLM | 已注册官方 32B 权重的多谱文本到 SMILES 接口。首个 GPU 作业在访问权重服务器时连接超时，未执行解码。已暂停权重续传和作业重提，本轮不纳入结果表。 |
| SpecMol 问答 | 使用发布的 7B 合并权重，GPU 完整解码 32 道 H/C 峰数及 ppm 区间四选一题，29/32 格式合规，4/32 选对。按碳总数、氢总数、碳区间、氢区间分组，依次答对 1/8、1/8、2/8、0/8。[完整回答](../results/specmol_qa32.json) |

神经匹配头也对固定面板的前两个查询逐一打分，共分别比较 2 × 4,096 个谱–结构组合。四谱的正确结构均排第 1，双谱分别排第 6 和第 1。大库中 128 个查询的前 32 名重排，四谱纠正 5 个首位同时失去 3 个，双谱纠正 12 个同时失去 14 个。现已完成 32 个相同查询的 GPU 逐候选评测。每次查询对 4,096 个候选打分，四谱直接检索与全库重排均为 31/32，双谱从 11/32 降至 8/32。IR 单谱、Raman 单谱和作者原版双谱模型的全库神经重排均为 0/32。[四谱](../results/vib_library4096_four.json) · [适配双谱](../results/vib_library4096_adapted.json) · [原版双谱](../results/vib_library4096_author.json)。[配对与全库试跑明细](../results/vib_4096_matched_summary.json)

### NMRGym 专项解谱

同一组 10,000 条测试记录含 168,456 个氢位移和 213,570 个碳位移条目。旧转换器要求氢峰带括号，导致旧 NMRTrans 测试包的 10,000 条氢峰表均为空。当前评测从原始 JSONL 重建输入。每种模型仅使用表中谱种。给定分子式组额外读取参考分子式。所有组合按同一批分子的异构规范 SMILES 计算贪心生成和 beam-10 的结构命中率。[六种条件及测试进度](../results/nmrgym_nmrtrans_comparison.json)

| NMRGym 专项模型 | ¹H 验证集贪心命中率 | ¹³C 验证集贪心命中率 | ¹H+¹³C 验证集贪心命中率 | 共同测试集 |
| --- | ---: | ---: | ---: | --- |
| 通用 T5-small 起训，无分子式 | 待训练 | 待训练 | 待训练 | 训练结束后同协议评测 |
| 通用 T5-small 起训，给定分子式 | 待训练 | 待训练 | 待训练 | 训练结束后同协议评测 |
| 已发布 NMRTrans 权重微调，无分子式，最多 100 轮 | 0.166% | 0.186% | 0.497% | 已提交 GPU 评测 |

NMRGym 单库训练与 NMRSpec、NMRExp、Patent 三库合训分别包含六个正式实验。各自从通用 T5-small 初始化解码器，随机初始化所需的谱编码器。有、无分子式的模型对同一谱种共用训练和验证分子、随机种子 42、学习率 0.0001 和全局有效批量 4,096。每个模型最多训练 10,000 轮，每 20 轮验证一次，以验证集贪心结构命中率选择模型。微调对照单独报告。[NMRTrans 官方训练配置](https://github.com/little1d/NMRTrans/blob/main/configs/experiment_c_h.yaml)

SpecMol-7B 已提交四卡 LoRA 微调，训练 8,192 道、验证 512 道 NMRSpec 峰表计数与区间计数题，按分子连接关系隔离训练、验证和测试。用验证损失选权重，固定 32 道和扩展 256 道测试题按完整回答计分。

Xinyu 的 Vib2Mol 双谱检索和双谱生成分别从作者发布的权重微调，仅输入 IR、Raman。训练用的是发布包中 `openspec_test.lmdb` 的内部再划分，11,632 种分子连接结构用于训练，1,558 种用于验证。固定 128 个检索查询和 24 个生成目标均与拟合数据按分子连接关系隔离。结果归入内部适配实验，单列于官方数据划分的结果之外。

MCP 已通过 stdio 实际运行碳的跨溶剂位移与 MechFrag-MS，HTTP 另实测 H/C 溶剂路径及实验峰指认。UltraNMR 的输入编码与上游例题一致，NMRAgent 用本地固定响应走通 planner/verifier，ChefNMR 官方预处理器读入 Real-SpecTeach 的 238 条双谱。三个外部项目的结构生成分数待评估。[MCP 记录](../results/harness_mcp_mechfrag.json) · [HTTP 指认](../results/harness_assigned_http.json) · [外部模型核对](../results/external_nmr_interfaces.json)

各项检索分数取决于候选库、输入通道和查询来源。计算振动谱、实验 NMR 和实测 MS/MS 分别报告。语言模型的软件训练检查见[训练接口](../documentation/benchmarks/training.zh.md)，Agent 工具调用见[Harness 图](../documentation/assets/harness/mcp-workflow.svg)。


> 本页保留旧运行记录，不能作为当前能力总表。旧 F/P 预测与输入标签错配，以下两项分数已作废；新审计见 `results/fp_primary_score_gate_20261116.json`。最新四模态 Vib2Mol、gap、振动正向与 MS 结果见 [中英文任务文档](../documentation/tasks/index.zh.md)。

运行完成：`2026-11-15T10:08:12.353774+00:00`。用途：流程小样本验证。

共 59 个任务/数据集组合：52 通过，0 失败，7 跳过。

样本上限 16，设备 `cpu`，beam size 以各生成任务记录为准。权重保持已有状态，没有训练。

[下载完整结果 JSON](assets/v1_pipeline_20261115.json)，包含数据/权重哈希、样本 ID、选择规则、候选池和每项运行状态。

这些结果检验代码与资产能否配合运行。小候选池、给定分子式、跨域输入等条件必须与分数一起解读；本次未重新审核数据来源及训练集泄漏。

## H/C 检索与生成

检索 R@1 使用本次选中的候选池，生成 exact 为给定分子式并重排后的 top-1。

| 数据集 | H+C 谱→结构 R@1 | H+C 结构→谱 R@1 | H+C 生成 exact | 生成有效率 |
| --- | --- | --- | --- | --- |
| nmrspec_test | 1.0000 | 1.0000 | 0.1250 | 1.0000 |
| patent_test_10k | 0.8125 | 0.6875 | 0.0000 | 0.8750 |
| nmrexp_exp_10k | 0.8125 | 0.7500 | 0.7500 | 1.0000 |
| nmrgym_test | 0.8125 | 0.8125 | 0.0000 | 0.7500 |

## 已有正向预测评分

| 任务 | 数据集 | 模型 | MAE (ppm) | 评分分子数 | 匹配覆盖率 |
| --- | --- | --- | --- | --- | --- |
| nmr.forward.1H | nmrspec_test | nmrnet | 0.1312 | 16 | 0.4802 |
| nmr.forward.1H | nmrspec_test | nmrnetpp | 0.0775 | 16 | 0.4802 |
| nmr.forward.1H | patent_test_10k | nmrnet | 0.2894 | 13 | 0.3243 |
| nmr.forward.1H | patent_test_10k | nmrnetpp | 0.2297 | 13 | 0.3243 |
| nmr.forward.1H | nmrexp_exp_10k | nmrnet | 0.0751 | 16 | 0.5262 |
| nmr.forward.1H | nmrexp_exp_10k | nmrnetpp | 0.0411 | 16 | 0.5262 |
| nmr.forward.1H | nmrgym_test | nmrnet | 0.1938 | 16 | 0.5582 |
| nmr.forward.1H | nmrgym_test | nmrnetpp | 0.1861 | 16 | 0.5582 |
| nmr.forward.13C | nmrspec_test | nmrnet | 1.2599 | 16 | 0.8661 |
| nmr.forward.13C | nmrspec_test | nmrnetpp | 0.9092 | 16 | 0.8661 |
| nmr.forward.13C | patent_test_10k | nmrnet | 7.6736 | 16 | 0.4695 |
| nmr.forward.13C | patent_test_10k | nmrnetpp | 6.5046 | 16 | 0.4695 |
| nmr.forward.13C | nmrexp_exp_10k | nmrnet | 1.3243 | 16 | 0.7411 |
| nmr.forward.13C | nmrexp_exp_10k | nmrnetpp | 1.6554 | 16 | 0.7411 |
| nmr.forward.13C | nmrgym_test | nmrnet | 1.7850 | 16 | 0.8912 |
| nmr.forward.13C | nmrgym_test | nmrnetpp | 1.9565 | 16 | 0.8912 |

H/C 使用未指认峰的最小误差匹配，同时记录峰数误差和覆盖率，不作为逐原子指认精度。

## 其他已运行任务

| 任务 | 条件 | 指标 |
| --- | --- | --- |
| nmr.forward.19F | 旧输入错配 | 分数作废 |
| nmr.forward.31P | 旧输入错配 | 分数作废 |
| vibrational.gap.ir | 计算 IR/Raman，未提供 H/C | mae_ev=1.3193; rmse_ev=1.6003 |
| vibrational.gap.raman | 计算 IR/Raman，未提供 H/C | mae_ev=2.7287; rmse_ev=2.7861 |
| vibrational.gap.ir_raman | 计算 IR/Raman，未提供 H/C | mae_ev=1.1394; rmse_ev=1.2454 |
| vibrational.retrieval | 计算 IR/Raman，未提供 H/C | recall_at_1=0.0625; mrr=0.2952 |
| vibrational.generation | 计算 IR/Raman，未提供 H/C | valid_rate=1.0000; exact_rate=0.0000 |
| spectroscopy.reranking | 计算 IR/Raman，未提供 H/C | recall_at_1=0.1250; mrr=0.3015; top_1_hit_rate=0.1250 |

F/P 的旧评分无效；冻结重跑虽已验证标签对齐，但固态到溶液的参考约定仍未确认，默认跳过正式评分。Vib2Mol 生成使用原始 beam top-1，不使用测试集缓存。Gap 参考值先按元数据转换成 eV。

## 跳过项

以下条目没有生成占位分数：

- `nmr.forward.11B`（skipped）：保留六核任务定义；尚未验证可用于此实验域的 checkpoint 和预测文件。
- `nmr.forward.29Si`（skipped）：保留六核任务定义；尚未验证可用于此实验域的 checkpoint 和预测文件。
- `vibrational.forward`（skipped）：Studio 已有 Hessian / response 推理入口；本统一基准尚未接入有配对参考值的评测数据。
- `nmr.assignment`（skipped）：需要保留原子编号的实验参考值和匹配模型。
- `nmr.solvent_transfer`（skipped）：需要同一分子跨溶剂配对记录及已有可用模型。
- `nmr.formula`（skipped）：现有生成器使用给定分子式；不将其计为分子式预测器。
- `spectroscopy.qa`（skipped）：需要有参考答案的题集和固定模型接口。

## 本地验证与发布状态

指标、输入规范化和预测解包的 12 项检查通过。Streamlit AppTest 验证了无模型资产时的默认页和 NMR 页面，H/C 交互检索与生成服务也实际运行通过。

手册采用 MkDocs Material，已配置 GitHub Actions 构建和 Pages 发布。当前环境无法解析网络代理域名，因此严格 MkDocs 依赖安装、GitHub 推送和远端 Pages 部署尚未验证；本页不代表站点已上线。
