# 模型适用性与潜在微调清单

本页逐项检查所有启用任务。执行成功、模型与任务相容、精度经过独立验证，是三个不同结论。本轮没有训练、微调或拟合位移偏移。

## B 与 Si：当前结论

| Nucleus | Molecules / atoms | MAE (ppm) | Mean signed error (ppm) | Pearson r | R² |
| --- | ---: | ---: | ---: | ---: | ---: |
| B | 32 / 32 | 8.6845 | +2.3668 | 0.2174 | -0.0068 |
| Si | 32 / 32 | 56.1336 | +56.1336 | 0.2385 | -13.6167 |

本次核对了每个评测结构唯一的 B/Si 原子与标签位置，确认当前数据池标签对齐、checkpoint 参数完整恢复。这样能排除配对错误，但不能证明科学质量。B 预测相关性弱，Si 预测全部偏高；二者都不能宣传为已验证的高精度溶液模型。

当前准备的 B 数据池有 **121** 个规范结构同时出现在 train 与 valid，Si 有 **10** 个。这是准备数据池的重叠，不等于证明与发布模型训练集重叠。所有池记录的溶剂字段均为空。B 的一个训练池标签达到 **3085 ppm**，未来训练前应核查原始来源和单位。按结构、坐标、标签和掩码核对，当前池实际对应 `data_hetero3`，不能再用旧 `data_hetero2` 脚本描述它。

[NMRNet++ 官方归档](https://zenodo.org/records/18232165)与本地下载 checkpoint 包的校验和一致，其中可识别的已训练 checkpoint 只有 H/C。目前 B/Si 使用的是液相 All-nucleus **NMRNet**，不是已核验的 B/Si 专用 NMRNet++ 权重。

## 全部启用任务的检查

| Task | Current interpretation and next step |
| --- | --- |
| [nmr.forward.1H](tasks/nmr-forward-1H.md) | 可作为 H/C 冻结模型基线；误差来自峰匹配，不代表实验原子指认。仍要检查训练重叠和溶剂覆盖。 |
| [nmr.forward.13C](tasks/nmr-forward-13C.md) | 可作为 H/C 冻结模型基线；误差来自峰匹配，不代表实验原子指认。仍要检查训练重叠和溶剂覆盖。 |
| [nmr.forward.19F](tasks/nmr-forward-19F.md) | 当前固相权重没有验证为溶液位移模型。优先解决数据域与参考兼容，不能直接归因于需要微调。 |
| [nmr.forward.31P](tasks/nmr-forward-31P.md) | 当前固相权重没有验证为溶液位移模型。优先解决数据域与参考兼容，不能直接归因于需要微调。 |
| [nmr.forward.11B](tasks/nmr-forward-11B.md) | 仅作诊断：MAE 8.68 ppm，相关系数 0.217。区分能力弱、覆盖未核验；数据修复后可考虑 B 专项适配。 |
| [nmr.forward.29Si](tasks/nmr-forward-29Si.md) | 当前不适合精确溶液位移预测：MAE 56.13 ppm，32 个预测全部偏高。先清理数据并确认相容权重，再考虑微调。 |
| [nmr.retrieval.h.s2m](tasks/nmr-retrieval-h-s2m.md) | 输入输出对应合理，但目前主要是 32 候选的小池检查。先评更大的独立候选库，再判断泛化和微调需求。 |
| [nmr.retrieval.h.m2s](tasks/nmr-retrieval-h-m2s.md) | 输入输出对应合理，但目前主要是 32 候选的小池检查。先评更大的独立候选库，再判断泛化和微调需求。 |
| [nmr.generation.h](tasks/nmr-generation-h.md) | 存在明显数据域差异：专利和 NMRGym 的 32 样本检查均为零精确匹配。先检查独立测试、解析及词表覆盖，再考虑领域微调。 |
| [nmr.retrieval.c.s2m](tasks/nmr-retrieval-c-s2m.md) | 输入输出对应合理，但目前主要是 32 候选的小池检查。先评更大的独立候选库，再判断泛化和微调需求。 |
| [nmr.retrieval.c.m2s](tasks/nmr-retrieval-c-m2s.md) | 输入输出对应合理，但目前主要是 32 候选的小池检查。先评更大的独立候选库，再判断泛化和微调需求。 |
| [nmr.generation.c](tasks/nmr-generation-c.md) | 存在明显数据域差异：专利和 NMRGym 的 32 样本检查均为零精确匹配。先检查独立测试、解析及词表覆盖，再考虑领域微调。 |
| [nmr.retrieval.hc.s2m](tasks/nmr-retrieval-hc-s2m.md) | 输入输出对应合理，但目前主要是 32 候选的小池检查。先评更大的独立候选库，再判断泛化和微调需求。 |
| [nmr.retrieval.hc.m2s](tasks/nmr-retrieval-hc-m2s.md) | 输入输出对应合理，但目前主要是 32 候选的小池检查。先评更大的独立候选库，再判断泛化和微调需求。 |
| [nmr.generation.hc](tasks/nmr-generation-hc.md) | 存在明显数据域差异：专利和 NMRGym 的 32 样本检查均为零精确匹配。先检查独立测试、解析及词表覆盖，再考虑领域微调。 |
| [vibrational.gap.ir](tasks/vibrational-gap-ir.md) | 这是四模态权重的缺通道消融。不能当作独立 IR/Raman 专用模型；需相容权重或另行规划适配。 |
| [vibrational.gap.raman](tasks/vibrational-gap-raman.md) | 这是四模态权重的缺通道消融。不能当作独立 IR/Raman 专用模型；需相容权重或另行规划适配。 |
| [vibrational.gap.ir_raman](tasks/vibrational-gap-ir_raman.md) | 这是四模态权重的缺通道消融。不能当作独立 IR/Raman 专用模型；需相容权重或另行规划适配。 |
| [vibrational.gap.ir_raman_hc](tasks/vibrational-gap-ir_raman_hc.md) | 完整输入和单位已对齐；128 样本 MAE 0.131446 eV，优于均值基线 0.899940 eV。下一步是更大独立评测，无证据要求立即微调。 |
| [vibrational.forward](tasks/vibrational-forward.md) | 使用正确的 Xinyu Hessian/response 路径及成对几何。两例只证明流程执行；先做独立构象集评测。 |
| [vibrational.retrieval](tasks/vibrational-retrieval.md) | 这是四模态权重的缺通道消融。不能当作独立 IR/Raman 专用模型；需相容权重或另行规划适配。 |
| [vibrational.generation](tasks/vibrational-generation.md) | 这是四模态权重的缺通道消融。不能当作独立 IR/Raman 专用模型；需相容权重或另行规划适配。 |
| [nmr.assignment](tasks/nmr-assignment.md) | 作为已知结构的候选指认流程合理，但尚无实验指认准确率。先验证原子标签和对称性，再决定微调。 |
| [nmr.solvent_transfer](tasks/nmr-solvent_transfer.md) | 参考检索基线可执行，但 H 没有优于位移不变基线。仍需溶剂条件模型及独立配对数据。 |
| [spectroscopy.reranking](tasks/spectroscopy-reranking.md) | 这是四模态权重的缺通道消融。不能当作独立 IR/Raman 专用模型；需相容权重或另行规划适配。 |
| [vibrational.retrieval.hc](tasks/vibrational-retrieval-hc.md) | 完整四模态协议适配合理。候选池检索／ITM 不等于开放结构生成；需扩大独立候选库验证。 |
| [vibrational.generation.hc](tasks/vibrational-generation-hc.md) | 已遵循作者生成协议，但同一 64 样本上 ITM 重排使 top-1 从 0.75 降到 0.6875；应先复查这项退化，再考虑重排器适配。 |
| [spectroscopy.reranking.hc](tasks/spectroscopy-reranking-hc.md) | 完整四模态协议适配合理。候选池检索／ITM 不等于开放结构生成；需扩大独立候选库验证。 |
| [ms.forward.glacier](tasks/ms-forward-glacier.md) | 采用作者接口并显式提供采集条件，方法适配合理；31 条评分不足以证明广泛精度。先核查协议与训练重叠，再决定微调。 |
| [ms.forward.iceberg](tasks/ms-forward-iceberg.md) | 采用作者接口并显式提供采集条件，方法适配合理；31 条评分不足以证明广泛精度。先核查协议与训练重叠，再决定微调。 |
| [ms.annotation.magma](tasks/ms-annotation-magma.md) | 这是算法标注，不是可微调神经模型；应改进匹配和验证。 |

## 潜在微调任务清单：按现有证据排序

| Priority | Task family | Prerequisite / reason |
| --- | --- | --- |
| 1 | 29Si / 11B | 先找相容核种专用权重，修复结构泄漏、补回溶剂/参考条件、核验原标签。若没有合适发布权重，再考虑核种专项适配。 |
| 2 | NMR → SMILES (H / C / H+C) | 跨数据集失败明显；验证分子式解析、词表覆盖及独立 scaffold 测试后，可优先做领域适配研究。 |
| 3 | Cross-solvent transfer | 先获得溶剂条件模型和干净、原子对应的配对数据。当前近邻参考基线没有可供微调的神经权重。 |
| 4 | IR/Raman-only gap / generation / retrieval | 若必须支持缺 NMR 输入，应找对应输入训练的权重，或规划缺模态适配；当前分数属于消融。 |
| 5 | Vib2Mol ITM reranker | 先调查同样本 top-1 退化；不得在测试集上拟合校准或重训。后续适配必须使用独立开发集。 |

**暂不能直接下“需要微调”的结论：**F/P 先解决溶液域和参考约定；指认先补实验真值；MS、构象→IR/Raman 先扩大独立评测。MAGMa 是算法。完整输入 gap 现有基线有用。SpectraLLM、分子式预测、谱学 QA 继续暂缓。

[Download B/Si audit](assets/reports/bsi_model_review_20261117.json) · [Official archive inventory](assets/reports/nmrnetpp_release_inventory_20261117.json)

**评测限制：**多个 NMR 视图已确认与 checkpoint 记录的训练数据存在分子重叠，最终生成模型还存在训练文件哈希不一致。现有运行不能证明独立泛化能力。 [Training-history audit / 训练历史审计](training-overlap.md)
