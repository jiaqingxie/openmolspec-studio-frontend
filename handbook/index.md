# OpenMolSpec v1.0

OpenMolSpec 把结构、谱图和分子性质的任务放进同一个工作台，使用已经保存的模型权重进行推理和评分。当前发布工作集中在任务整合、运行验证、前端和使用文档。

- [安装与首次运行](quickstart.md)：启动 Studio 或独立运行评测。
- [任务目录](tasks.md)：查看六核 NMR、IR、Raman 的任务与适配器覆盖。
- [Studio 操作](studio.md)：输入实验 H/C NMR、检索候选和生成结构。
- [基准评测](benchmark.md)：复现小样本运行，理解各指标和候选池。
- [评测结果](results.md)：查看实际运行的状态和限制。

NMR 实验域包含 ¹H、¹³C、¹⁹F、³¹P、¹¹B、²⁹Si 的任务定义。当前交互推理模型支持 H/C，另有 ¹⁹F/³¹P 已有预测的跨域诊断评分；¹¹B/²⁹Si 保留待接入状态。IR/Raman 支持计算谱。旧 Studio 中的计算 H/C NMR 作为计算域工作流单独保留，不作为实验 NMR 基准。

任务目录里有入口不代表该任务已完成评测；请结合结果文件里的 `passed`、`failed`、`skipped` 和具体原因判断。
