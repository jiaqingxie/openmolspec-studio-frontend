# 评测协议

所有公开结果图来自实际记录。证据 JSON 保留来源报告哈希。执行成功与科学有效性分开判断；小候选池、准备数据的 split 标签、峰匹配误差，不能宣传成独立泛化或实验原子指认准确率。

完整 IR/Raman/H/C 输入与缺通道消融分别报告。Gap 从 Hartree 到 eV 仅转换一次。MS 在明确采集条件下与全部实测峰比较。冻结模型图没有拟合校准。另有独立的 SDK 训练接口检查：每个原始划分取两个记录，编码器与生成器各训练一步并验证保存重载；这不是性能基准。

[Dataset definitions](datasets.md) · [Model-by-model audit](model-audit.md)

**评测限制：**多个 NMR 视图已确认与 checkpoint 记录的训练数据存在分子重叠，最终生成模型还存在训练文件哈希不一致。现有运行不能证明独立泛化能力。 [Training-history audit / 训练历史审计](training-overlap.md)
