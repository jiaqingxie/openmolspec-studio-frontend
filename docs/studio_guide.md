# OpenMolSpec Studio

OpenMolSpec Studio 是面向当前仓库数据与模型的精简 Streamlit 前端。它参考
`git@github.com:X1nyuLu/ramancloud-alpha.git` 的分子输入与谱图交互，但只保留四个工作流：

- 三维构象 → IR / Raman / ¹H NMR / ¹³C NMR；
- 理论 IR / Raman / 计算 H/C NMR → 分子结构检索；
- 理论 IR / Raman / 可选计算 H/C NMR → HOMO–LUMO gap；
- 理论光谱 → Vib2Mol 分子结构候选。

本应用只面向 OpenMolSpec **理论计算光谱域**。IR/Raman 来自量化频率计算标签及其固定
展宽流程，H/C NMR 是 TMS 参考的计算化学位移；不使用实验光谱训练结果或将实验谱与
理论谱混合。数据记录中的 `source_dataset` 表示分子身份来源，不表示页面读取了该来源的
实验谱图。

## 运行

默认从仓库根目录发现数据和模型。也可以显式指定其他位置：

```bash
export OPENMOLSPEC_ROOT=/path/to/openmolspec-repository
python -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

页面启动后会自动发现 checkpoint、test set LMDB 和 Vib2Mol 评估缓存。默认自动选择设备：
CUDA 可用时使用 `cuda:0` 并预加载全部模型；CUDA 不可用时自动回退到 CPU，预加载
Hi、Hij、dedipole、depolar、NMR 和 gap，并对 Vib2Mol 检索与生成使用缓存路径。
Streamlit 的资源缓存会在后续页面切换和 rerun 时复用这些实例，不会重复加载。

如需指定其他 GPU：

```bash
OPENMOLSPEC_DEVICE=cuda:1 .venv/bin/streamlit run app.py
```

也可以显式使用 CPU：

```bash
OPENMOLSPEC_DEVICE=cpu .venv/bin/streamlit run app.py
```

## 输入格式

理论 IR / Raman 文件可以是一列强度，也可以是两列 `wavenumber, intensity`。两列文件需要覆盖
400–4000 cm⁻¹ 中至少两个点。应用会排序、去重、线性插值为 1024 点，并按单条谱图、
单模态执行 min–max 归一化，与 OpenMolSpec benchmark 保持一致。

¹H / ¹³C NMR 输入为 ppm 峰位列表，可用逗号、空格或换行分隔。分子结构支持 Ketcher
二维绘制、SMILES 和 XYZ；绘制结果会转换为 SMILES，再由 RDKit 生成并优化三维构象。
页面通过 3Dmol.js 展示模型实际读取的构象，可使用鼠标旋转和缩放。

## 当前推理路径

| 工作流 | 本地实现 |
|---|---|
| 构象 → 谱图 | 四个 1M EquiformerV3 分别预测 Hi、Hij、dedipole、depolar，经理论重建得到 IR/Raman；H/C NMR 使用 1M 原子级 checkpoint |
| 谱图 → gap | 直接加载 1M Shared Spectroscopy Transformer checkpoint |
| 谱图 → 检索 | CUDA 上使用 Vib2Mol learned embeddings；显式 CPU 调试时回退到 test set 谱库余弦基线 |
| 谱图 → 生成 | CUDA 上直接 beam search/rerank；显式 CPU 调试时使用 test set 锚点的已验证缓存 |

理论 IR/Raman 重建先将 Hi/Hij 装配为完整 Cartesian Hessian，质量加权并几何移除平移与
转动自由度，求解正则模；随后把预测的 `∂μ/∂R` 和 `∂α/∂R` 投影到各振动模，得到 IR 与
Raman activity。最终沿用 OpenMolSpec 的 `0.965` 频率缩放、400–4000 cm⁻¹ / 1024 点网格、
IR 20 cm⁻¹ 与 Raman 12 cm⁻¹ Lorentz 展宽，以及 298 K、532 nm Raman 强度约定。输出按
OpenMolSpec benchmark 的 per-record/per-modality min–max 规则归一化。该流程是 1M 理论模型
的代理推理，不会在网页请求期间启动 Gaussian。

检索的 CPU 回退同样使用 NMR：¹H 与 ¹³C 分别采用适合其化学位移尺度的双向高斯峰集合
匹配，再与可用的 IR/Raman 余弦相似度取平均。CUDA 上的 Vib2Mol 路径则直接将四种模态
送入共享编码器。

生成页默认展示 8 个结构可能性。直接推理会扩大 beam 池后规范化、去重并重排；缓存回退会
汇总多个相近理论谱锚点的已验证候选，同时明确标注来源，不会把缓存结果标为对任意上传谱图的直接生成。
可用 `OPENMOLSPEC_VIB2MOL_DIRECT=0|1` 显式关闭或强制直接 Vib2Mol 推理；默认根据
`OPENMOLSPEC_DEVICE` 选择直接推理或缓存回退。
