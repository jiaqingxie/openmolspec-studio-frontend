# Studio 操作

## 任务与评测

默认页面展示统一任务目录。可按任务类型筛选，查看接入的评测适配器和待接入原因。下方选择 `results/*.json` 结果文件，查看运行状态并下载完整记录。页面浏览不需要加载模型。

## 实验 NMR → 结构

输入 ¹H、¹³C 或两者的 ppm 峰列表，可清空一种核以使用单核模式。

- **候选结构检索**：每行一个 SMILES，点击检索。模型编码候选并按与谱图的余弦相似度排序，显示候选池大小。
- **SMILES 生成**：提供已知分子式并选择 beam size，点击生成。候选按有效性、分子式一致性和模型分数排序。

下载的 JSON 是该次真实模型操作的结果。¹⁹F、³¹P、¹¹B、²⁹Si 暂无本前端已验证的推理适配器，目录中保留任务定义和接入状态。

H/C 模型默认从 `OPENMOLSPEC_BENCH_ROOT/runs/` 发现，或分别设置 `OPENMOLSPEC_ALIGN_CHECKPOINT`、`OPENMOLSPEC_GENERATE_CHECKPOINT`。`OPENMOLSPEC_DEVICE` 为 `auto`、`cpu` 或 `cuda:0` 等。

## 原有计算域工作流

设置 `OPENMOLSPEC_ROOT` 到 portable 资产目录后，可以继续使用：

1. 构象 → IR/Raman/H/C NMR：输入 SMILES（RDKit 构象）或 XYZ，计算模型预测谱图。
2. 谱图 → 结构检索：上传 IR/Raman 谱，可补 H/C 峰。直接 Vib2Mol 与数据库谱相似度 fallback 必须按返回的 backend 区分。
3. 谱图 → HOMO–LUMO gap：上传 IR/Raman，可补 H/C，输出 eV。
4. 谱图 → 结构生成：按环境使用 Vib2Mol 直接推理或测试集缓存路径。

CPU 缓存回放的命中属于已有测试集结果，不能作为任意新输入的实时生成证据。计算域 H/C NMR 输出也不计入实验 NMR benchmark。

振动谱 CSV/TXT 采用波数 cm⁻¹ 和强度两列；工作台重采样到 400–4000 cm⁻¹、1024 点并归一化。使用页面提供的模板可以减少格式错误。
