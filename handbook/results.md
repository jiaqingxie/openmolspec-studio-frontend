# 历史评测结果（已被后续审计部分替代）

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
