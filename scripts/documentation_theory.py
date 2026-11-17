"""Bilingual spectroscopy theory, numerical inversion and teaching navigation."""


def pages(en):
    suffix='' if en else '.zh';out={}
    out[f'theory/index{suffix}.md']=(r'''# Spectroscopy theory

Spectra connect physical observables to molecular structure, dynamics and acquisition conditions. These chapters explain the quantities behind OpenMolSpec task inputs, outputs and losses.

| Topic | Concepts | Executable tutorial |
| --- | --- | --- |
| [NMR](nmr.md) | Chemical shifts, spin coupling, FID, Fourier transform, relaxation | [FID → spectrum](../notebooks/theory-nmr-fourier.ipynb) |
| [Mass spectrometry](ms.md) | Ion mass, adducts, isotopes, fragmentation, resolving power | [Isotope envelope](../notebooks/theory-ms-isotopes.ipynb) |
| [IR and Raman](vibrational.md) | Normal modes, selection rules, line shapes and units | [Spectral broadening](../notebooks/theory-vibrational-broadening.ipynb) |
| [NMR inversion](../inversion/index.md) | Relaxation/diffusion kernels, ill-conditioning, nonnegative regularization | [Relaxation distribution](../notebooks/theory-nmr-inversion.ipynb) |

All four tutorials execute numerical simulations with declared parameters. Experimental and computed dataset examples live under [Data](../data/index.md).
''' if en else r'''# 谱学理论

谱学把可测信号与分子结构、动力学和采集条件联系起来。本栏解释 OpenMolSpec 任务输入、输出与损失函数背后的物理量，并提供可修改参数的数值模拟。

| 专题 | 核心内容 | 可执行教程 |
| --- | --- | --- |
| [核磁共振 NMR](nmr.md) | 化学位移、自旋耦合、FID、傅里叶变换与弛豫 | [FID → 频谱](../notebooks/theory-nmr-fourier.ipynb) |
| [质谱 MS](ms.md) | 离子质量、加合物、同位素、碎裂与分辨率 | [同位素包络](../notebooks/theory-ms-isotopes.ipynb) |
| [IR 与 Raman](vibrational.md) | 简正模式、选择定则、谱线展宽与单位 | [谱线展宽](../notebooks/theory-vibrational-broadening.ipynb) |
| [NMR 反演](../inversion/index.md) | 弛豫／扩散核、病态问题与非负正则化 | [弛豫分布恢复](../notebooks/theory-nmr-inversion.ipynb) |

四项教程均实际执行带明确参数的数值模拟。实验与计算数据案例见 [Data](../data/index.md)。
''')
    out[f'theory/nmr{suffix}.md']=(r'''# Nuclear magnetic resonance

## Chemical shifts and molecular environments

A nucleus in a magnetic field experiences an effective field modified by electronic shielding. Chemical shift uses a reference frequency:

$$\delta = 10^6(\nu-\nu_\mathrm{ref})/\nu_\mathrm{ref}.$$

The unit is ppm. A frequency separation in Hz depends on the spectrometer frequency; ppm and Hz must therefore remain distinct. Solvent, temperature, concentration, exchange and referencing can alter the observed shift. Two identical structures need not produce identical experimental peak lists under different conditions.

## Coupling and peak lists

In the weak-coupling limit, scalar coupling splits resonances; a first-order $n+1$ pattern applies only for the relevant set of equivalent spin-½ neighbours. Strong coupling, magnetic inequivalence, exchange and overlap can invalidate this rule. Peak integration relates to populations under suitable acquisition and relaxation conditions. A reported multiplet centre, a picked line and an atomwise shift are different objects.

OpenMolSpec preserves shift prose and, when available, multiplicity, integration, coupling constants, solvent and frequency. H/C forward prediction returns atomwise shifts. Matching an unassigned experimental peak set to those predictions yields candidate assignments; symmetry and experimental correlation spectra determine how these should be interpreted.

## Time-domain signal and Fourier transform

A simple complex free induction decay can be written

$$s(t)=\sum_k A_k\exp(-t/T_{2,k}^{*})\exp[i(2\pi\nu_k t+\phi_k)].$$

The Fourier transform maps frequency components into a spectrum. Acquisition duration controls nominal frequency resolution, sampling controls bandwidth, and the Nyquist limit constrains unaliased offsets. Apodization changes line width and noise; zero filling interpolates the display without adding acquired information. Phase and baseline processing affect peak picking and intensity interpretation.

The [Fourier tutorial](../notebooks/theory-nmr-fourier.ipynb) constructs a complex FID from three known frequencies, transforms it and checks the recovered dominant frequency. It uses Hz offsets rather than pretending to have a calibrated ppm reference.

## Relaxation and inverse problems

Longitudinal recovery is characterized by $T_1$; transverse decay by $T_2$. Effective $T_2^*$ also includes field inhomogeneity. A distribution of environments can generate a sum of decays, motivating [regularized inversion](../inversion/index.md). Pulse-sequence kernels and time units must match the experiment.

## Further reading

- [NMRInversions.jl theory](https://aris-mav.github.io/NMRInversions.jl/stable/theory/), for relaxation and diffusion inversion.
- [MLatom documentation](https://xacs.xmu.edu.cn/docs/mlatom/), for molecular simulations and computational spectroscopy workflows.
''' if en else r'''# 核磁共振 NMR

## 化学位移与分子环境

电子屏蔽改变原子核感受到的有效磁场。化学位移以参考频率定义：

$$\delta = 10^6(\nu-\nu_\mathrm{ref})/\nu_\mathrm{ref}.$$

单位是 ppm；以 Hz 表示的频差取决于仪器频率，因此 ppm 和 Hz 不能直接互换。溶剂、温度、浓度、交换过程和参考标准均可能改变观测位移。同一结构在不同实验条件下可以具有不同峰表。

## 耦合、积分与峰表

弱耦合近似下，标量耦合导致共振裂分；常见的 $n+1$ 规则只适用于相关的一组等价自旋 ½ 邻核。强耦合、磁不等价、交换和峰重叠都可能使简单规则失效。适当采集与弛豫条件下，积分可反映核数或相对含量。多重峰中心、单条裂分线、逐原子化学位移是不同的数据对象。

OpenMolSpec 保留位移原文，以及可获得的裂分、积分、耦合常数、溶剂和仪器频率。H/C 正向模型输出逐原子位移。将未指认实验峰与预测位移匹配，可以提出候选指认；需要结合对称性与实验相关谱解释。

## 时域信号与傅里叶变换

简单复数自由感应衰减可以表示为：

$$s(t)=\sum_k A_k\exp(-t/T_{2,k}^{*})\exp[i(2\pi\nu_k t+\phi_k)].$$

傅里叶变换把频率成分转为频谱。采集时长决定名义频率分辨率，采样间隔决定带宽，Nyquist 条件限定无混叠频率范围。加窗会改变线宽和噪声；补零增加显示采样点，但不增加原始采集信息。相位和基线处理也影响峰提取与强度解释。

[傅里叶教程](../notebooks/theory-nmr-fourier.ipynb)用三个已知频率生成复数 FID，执行变换，并检查恢复的主频。示例使用 Hz 偏移；没有实验参考频率时，不把它包装成已校准的 ppm 谱。

## 弛豫与逆问题

$T_1$ 描述纵向恢复，$T_2$ 描述横向衰减，$T_2^*$ 还包含磁场不均匀等影响。多环境体系可能表现为多指数衰减，因此可以通过[正则化反演](../inversion/index.md)估计分布。核函数、脉冲序列和时间单位必须对应。

## 延伸阅读

- [NMRInversions.jl theory](https://aris-mav.github.io/NMRInversions.jl/stable/theory/)：弛豫与扩散反演。
- [MLatom 文档](https://xacs.xmu.edu.cn/docs/mlatom/)：分子模拟和计算谱学流程。
''')
    out[f'theory/ms{suffix}.md']=(r'''# Mass spectrometry

## Molecular mass, ions and adducts

A mass spectrometer measures ions. The observed coordinate is mass-to-charge ratio, $m/z$, rather than neutral molecular mass. Protonation, deprotonation, sodium adduction, charge state and electron mass conventions affect the mapping from a molecular formula to an ion. Exact monoisotopic mass, nominal mass and average molecular weight serve different purposes.

An isolated reported m/z can help constrain molecular identity. It does not contain the fragment intensities needed to train or evaluate an MS/MS spectrum predictor. [Data](../data/index.md) distinguishes these record forms.

## Isotope patterns and resolving power

Natural isotope abundances produce a distribution of ion masses. In a carbon-only illustration, the number of ¹³C atoms follows a binomial distribution. Real envelopes also depend on hydrogen, nitrogen, oxygen, sulfur, halogens and the ion composition. Resolving power is commonly expressed as $R=m/\Delta m$, with the width convention specified, often FWHM.

The [isotope tutorial](../notebooks/theory-ms-isotopes.ipynb) normalizes a carbon-only probability distribution and shows two resolving powers. It is a teaching simulation of an isotope envelope, not an experimental fragmentation spectrum.

## Tandem mass spectrometry

MS/MS selects a precursor and records product ions after activation. Fragmentation depends on molecular graph, charge localization, adduct, collision energy, instrument and acquisition mode. Relative intensities can change substantially across conditions. Numerical energy values from different instrument conventions are not automatically equivalent.

GLACIER and ICEBERG in OpenMolSpec require explicit acquisition inputs. MAGMa proposes mass-compatible fragments on a specified graph. A fragment mass match supports a candidate explanation; multiple pathways or isomers may remain possible.

## Comparing spectra

For vectors $x$ and $y$, cosine similarity is $(x\cdot y)/(\|x\|\|y\|)$. Peak tolerance or bin width, normalization, precursor removal, filtering and unassigned-peak handling all affect the result. Report these choices and the spectrum identities with every comparison. Evaluation should also respect molecule, acquisition and source partitions.

## Sources

- [MassSpecGym](https://huggingface.co/datasets/roman-bushuiev/MassSpecGym): versioned experimental MS/MS and benchmark definitions.
- [ms-pred](https://github.com/coleygroup/ms-pred): GLACIER/ICEBERG implementations and model training procedures.
''' if en else r'''# 质谱 MS

## 分子质量、离子与加合物

质谱仪测量离子，横坐标是质荷比 $m/z$。质子化、去质子化、钠加合、不同电荷态和电子质量约定，都会影响分子式到离子质量的换算。精确单同位素质量、名义质量和平均分子量具有不同含义。

专利中单独报告的一个 m/z 可以帮助确认产物，但没有完整碎片强度信息。[Data](../data/index.md)会区分单点质量记录、碎片峰位与完整数值强度谱。

## 同位素包络与分辨率

天然同位素丰度形成不同离子质量的概率分布。仅考虑碳的教学模型中，¹³C 数目服从二项分布；真实同位素包络还受其他元素及离子组成影响。分辨率常记为 $R=m/\Delta m$，需要说明峰宽定义，例如半峰全宽 FWHM。

[同位素教程](../notebooks/theory-ms-isotopes.ipynb)计算归一化的碳同位素概率并比较两种分辨率。它模拟同位素包络，不代表实验 MS/MS 碎裂谱。

## 串联质谱

MS/MS 先选择前体离子，再记录活化后的产物离子。碎裂受分子图、荷电位置、加合物、碰撞能量、仪器和采集模式影响。相同结构在不同条件下的相对强度可以明显变化；不同仪器给出的能量数值不能直接视为同一物理条件。

OpenMolSpec 中的 GLACIER、ICEBERG 需要明确采集条件。MAGMa 在指定分子图上提出质量相容的候选碎片；质量匹配可以支持候选解释，但不唯一确定实际碎裂路径。

## 谱图比较

向量 $x,y$ 的余弦相似度为 $(x\cdot y)/(\|x\|\|y\|)$。峰匹配容差或分箱宽度、归一化、前体峰移除、过滤及未指认峰处理都会影响分数。每次比较应同时记录这些选择和谱图身份，并控制分子、采集条件和来源划分。

## 来源

- [MassSpecGym](https://huggingface.co/datasets/roman-bushuiev/MassSpecGym)：实验 MS/MS 与版本化基准。
- [ms-pred](https://github.com/coleygroup/ms-pred)：GLACIER／ICEBERG 实现与训练流程。
''')
    out[f'theory/vibrational{suffix}.md']=(r'''# Infrared and Raman spectroscopy

## Normal modes from the Hessian

Near an equilibrium geometry, the harmonic approximation expands the energy to second order in nuclear displacements. The Hessian contains the second derivatives. Diagonalizing the mass-weighted Hessian gives normal-mode eigenvalues and eigenvectors; positive eigenvalues give squared angular frequencies. Translation and rotation are excluded when constructing vibrational modes. Imaginary frequencies indicate negative curvature and require interpretation before treating a geometry as a minimum.

A nonlinear molecule has $3N-6$ vibrational modes; an isolated linear molecule has $3N-5$. Frequencies depend on geometry, electronic-structure method, masses and harmonic/anharmonic treatment. A different conformer can produce a different spectrum.

## Complementary selection rules

IR activity depends on the change in electric dipole moment along a normal coordinate. Raman activity depends on derivatives of the polarizability tensor. These are complementary observables: an intense IR mode can be weak in Raman. Experimental Raman intensities additionally depend on excitation frequency, temperature, polarization and collection geometry. Stored Raman activity is not automatically the same as measured intensity.

## From discrete modes to line shapes

A plotted spectrum is commonly formed by broadening mode frequencies:

$$I(\tilde\nu)=\sum_k A_k L(\tilde\nu-\tilde\nu_k).$$

The line shape $L$ can be Gaussian or Lorentzian. Gaussian width $\sigma$ and FWHM satisfy $\mathrm{FWHM}=2\sqrt{2\ln2}\,\sigma$. Axis limits, line width, frequency scaling and intensity normalization should accompany a calculated spectrum. Broadening does not recover missing experimental physics.

The [broadening tutorial](../notebooks/theory-vibrational-broadening.ipynb) uses five declared modes and checks that the area under a normalized Gaussian sum equals the total supplied activity. IR and Raman use the same frequencies and different activity vectors.

## Experimental versus computed spectra

Absorbance and transmittance are related logarithmically under their respective measurement conventions. Sparse reported IR peak positions do not provide a full intensity curve. Gas, liquid and solid environments can change positions and widths. Frequency resampling must use explicit units and a defined axis; do not interpolate a peak list and claim it is a measured spectrum.

For conformer-to-spectrum evaluation, use the coordinates associated with the reference. For multimodal learning, define whether NMR and vibrational observables belong to the same conformer, molecular identity or condition and preserve their references.

## Sources

- [MLatom](https://xacs.xmu.edu.cn/docs/mlatom/): computational spectroscopy workflows.
- [QM9S](https://www.nature.com/articles/s43588-023-00550-y): calculated spectra and molecular response properties.
- [QMe14S](https://arxiv.org/abs/2501.18876): calculated spectra spanning a broader element set.
''' if en else r'''# 红外 IR 与拉曼 Raman

## Hessian 与简正模式

在平衡构象附近，谐振近似把势能按核位移展开到二阶。Hessian 是能量二阶导数矩阵；对质量加权 Hessian 对角化，可得到简正模式及对应的角频率平方。构建振动模式时需要处理平移与转动自由度。虚频对应负曲率，不能直接把含显著虚频的构象当作稳定极小值。

非线性分子有 $3N-6$ 个振动模式，孤立线性分子有 $3N-5$ 个。振动频率与构象、电子结构方法、同位素质量及谐性／非谐性处理有关；不同构象可以具有不同谱图。

## 互补的选择定则

IR 活性与偶极矩沿简正坐标的变化有关；Raman 活性与极化率张量导数有关。因此两个通道提供互补信息，一个 IR 强峰可能对应弱 Raman 信号。实验 Raman 强度还取决于激发频率、温度、偏振与采集几何，数据文件中的 Raman activity 不能自动等同于实测强度。

## 离散模式到连续谱形

计算谱常通过展宽离散模式得到：

$$I(\tilde\nu)=\sum_k A_k L(\tilde\nu-\tilde\nu_k).$$

$L$ 可选 Gaussian 或 Lorentzian。Gaussian 的标准差与半峰全宽满足 $\mathrm{FWHM}=2\sqrt{2\ln2}\,\sigma$。谱轴、线宽、频率缩放与强度归一化均应明确；展宽本身不会补回缺失的环境或非谐性效应。

[展宽教程](../notebooks/theory-vibrational-broadening.ipynb)使用五个明确给出的模式，并验证归一化 Gaussian 谱的积分等于输入总活性。IR 与 Raman 使用相同模式频率、不同活性向量。

## 实验谱与计算谱

吸光度与透射率按相应测量约定呈对数关系。稀疏 IR 峰位列表不包含完整强度曲线。气相、液相和固相环境会改变峰位置及线宽。重采样必须明确单位与谱轴，也不能把峰表插值后描述成原始实测谱。

构象到谱图的评测应使用参考谱对应的坐标。多谱联合学习需要明确：不同模态是对应同一构象、同一分子身份，还是相同实验条件，并保留参考信息。

## 来源

- [MLatom](https://xacs.xmu.edu.cn/docs/mlatom/)：计算谱学流程。
- [QM9S](https://www.nature.com/articles/s43588-023-00550-y)：计算谱和分子响应性质。
- [QMe14S](https://arxiv.org/abs/2501.18876)：更广元素覆盖的计算谱数据。
''')
    out[f'inversion/index{suffix}.md']=(r'''# Inversion

NMR inversion estimates relaxation-time or diffusion-coefficient distributions from time-domain measurements. This section integrates the mathematical concepts described in [NMRInversions.jl](https://aris-mav.github.io/NMRInversions.jl/stable/theory/) into the OpenMolSpec workflow. The upstream Julia package offers additional algorithms and 2D functionality; the Python API below implements nonnegative quadratic regularization for 1D data.

## Choose the kernel

| Experiment | Kernel | Input unit requirement |
| --- | --- | --- |
| CPMG / T₂ decay | $\exp(-t/T_2)$ | time and T₂ in the same unit |
| Saturation recovery | $1-\exp(-t/T_1)$ | time and T₁ in the same unit |
| Inversion recovery | $1-2\exp(-t/T_1)$ | time and T₁ in the same unit; signed signal |
| Diffusion | $\exp(-bD)$ | bD dimensionless |

For a distribution on a chosen grid, measurements satisfy $g\approx Kf+\epsilon$. Here $f$ contains discrete bin amplitudes. A density per unit T or per unit log T requires the appropriate quadrature convention and must be identified separately.

## Why regularization is needed

Nearby exponential components produce similar signals. The kernel is ill-conditioned: a tiny perturbation can change the recovered distribution substantially. A small reconstruction residual therefore does not prove a unique distribution or resolve closely spaced physical components.

The implemented objective is

$$\min_{f\ge0}\|W(Kf-g)\|_2^2+\alpha\|Lf\|_2^2.$$

$W$ optionally weights observations by inverse noise standard deviation. $L$ is the identity or a second-difference operator on an equally spaced log grid. Increasing $\alpha$ increases regularization; excessive values can merge components. Alpha values depend on kernel, scaling, grid and weighting and should not be compared across conventions without care.

## Python interface

```python
import numpy as np
from openmolspec.inversion import invert

time = np.linspace(0, 1.5, 100)  # seconds
signal = .35*np.exp(-time/.05) + .65*np.exp(-time/.35)
grid = np.geomspace(.005, 2, 100)  # seconds
result = invert(time, signal, grid, experiment='T2',
                alpha=.01, penalty='curvature')
print(result.diagnostics)
weights = result.weights
reconstruction = result.fitted_signal
```

`samples`, `signal` and `grid` must be finite vectors; sampling coordinates and grid must increase strictly, and grid values must be positive. The caller performs phase/baseline correction and chooses physical units and an appropriate kernel. The result includes nonnegative weights, reconstruction, residuals, alpha and convergence diagnostics.

## Parameter selection and alternatives

Inspect reconstruction, residual structure, distribution stability and sensitivity to alpha/grid. GCV, L-curves and discrepancy criteria are alternative selection strategies. The current Python API accepts alpha explicitly. Sparse L1 regularization and multi-exponential nonlinear fitting make different assumptions; consult the upstream package for its available solvers and automatic selection procedures.

Run the [simulated inversion tutorial](../notebooks/theory-nmr-inversion.ipynb) to see known components, noisy observations and reconstructed distributions. For [the upstream Python/Julia integration](https://aris-mav.github.io/NMRInversions.jl/stable/python/), follow its installation instructions and API rather than treating OpenMolSpec as an identical implementation.
''' if en else r'''# Inversion：NMR 数值反演

NMR 反演从时域测量恢复弛豫时间或扩散系数分布。本栏把 [NMRInversions.jl 的理论](https://aris-mav.github.io/NMRInversions.jl/stable/theory/)纳入 OpenMolSpec 流程。上游 Julia 包还提供其他求解算法与二维功能；下方 Python 接口实现一维数据的非负二次正则化反演。

## 选择核函数

| 实验 | 核函数 | 单位要求 |
| --- | --- | --- |
| CPMG／T₂ 衰减 | $\exp(-t/T_2)$ | 时间与 T₂ 单位一致 |
| 饱和恢复 | $1-\exp(-t/T_1)$ | 时间与 T₁ 单位一致 |
| 反转恢复 | $1-2\exp(-t/T_1)$ | 时间与 T₁ 单位一致，保留信号正负号 |
| 扩散 | $\exp(-bD)$ | bD 为无量纲量 |

离散化后，观测满足 $g\approx Kf+\epsilon$。这里的 $f$ 表示离散格点幅度；若解释为每单位 T 或每单位 log T 的概率密度，还需要明确积分权重和归一化约定。

## 为什么需要正则化

相近指数成分产生的时域信号很相似，核矩阵因此病态：微小噪声可能显著改变恢复分布。重建残差很小，不代表分布唯一，也不代表分辨出了相近的物理组分。

当前求解目标为：

$$\min_{f\ge0}\|W(Kf-g)\|_2^2+\alpha\|Lf\|_2^2.$$

$W$ 可用噪声标准差的倒数加权；$L$ 可以是单位矩阵，或等间距对数格点上的二阶差分。增大 $\alpha$ 会增强正则化，过大则可能合并真实组分。参数含义依赖核、数据缩放、格点和权重，不能跨约定直接比较数值。

## Python 接口

```python
import numpy as np
from openmolspec.inversion import invert

time = np.linspace(0, 1.5, 100)  # 秒
signal = .35*np.exp(-time/.05) + .65*np.exp(-time/.35)
grid = np.geomspace(.005, 2, 100)  # 秒
result = invert(time, signal, grid, experiment='T2',
                alpha=.01, penalty='curvature')
print(result.diagnostics)
weights = result.weights
reconstruction = result.fitted_signal
```

输入向量须为有限数值，采样坐标与格点严格递增，格点大于零。相位／基线处理、物理单位与实验核由调用者明确。输出包括非负幅度、重建信号、残差、alpha 与收敛信息。

## 参数选择与其他方法

应同时检查重建、残差结构、分布稳定性，以及 alpha／格点的敏感性。GCV、L 曲线和偏差准则可用于参数选择；当前 Python 接口显式接收 alpha。L1 稀疏正则化和多指数非线性拟合使用不同假设，可参考上游包的求解器与自动参数选择。

[反演模拟教程](../notebooks/theory-nmr-inversion.ipynb)展示已知组分、带噪观测与恢复分布。需要上游完整功能时，可按其 [Python／Julia 集成说明](https://aris-mav.github.io/NMRInversions.jl/stable/python/)安装和调用。
''')
    return out
