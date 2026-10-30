# OpenSpec Scientific Data Data Descriptor 行文框架

本文档用于准备 OpenSpec 的 Scientific Data `Data Descriptor` 投稿稿件。它是写作模板，不是 Scientific Data 的官方模板；正式投稿前应以期刊最新投稿指南为准。

## 1. Manuscript overview

### Recommended article type

`Data Descriptor`

### Recommended manuscript length

Scientific Data 对 Data Descriptor 正文没有严格总字数限制。建议 OpenSpec 初稿控制在约 5,000–8,000 个英文词，重点保证 Methods、Data Records 和 Technical Validation 足够详细。

建议分配如下：

| Section | Suggested length |
|---|---:|
| Abstract | 150–170 words |
| Background & Summary | 800–1,200 words |
| Methods | 1,800–3,000 words |
| Data Records | 800–1,500 words |
| Data Overview | 300–600 words |
| Technical Validation | 1,200–2,000 words |
| Usage Notes | 300–700 words |

以上是写作规划，不是期刊硬性字数限制。

### Official format reminders

- Title 不超过 110 个字符，包括空格；
- Abstract 建议不超过 170 词；
- 图建议不超过 8 张；
- 表建议不超过 10 张；
- 单个图注不超过 350 词；
- 正文主章节没有严格总字数限制；
- Supplementary Information 应只放确实无法放入正文的补充内容。

## 2. Proposed title

标题应客观描述数据内容，不使用 `novel`、`first`、`AI-ready`、`open` 等宣传性词语，也尽量避免自定义缩写。

### Candidate titles

> A large-scale multimodal molecular dataset of vibrational spectra, NMR spectra and quantum-chemical properties

> A multimodal molecular dataset linking three-dimensional structures, vibrational spectra and quantum-chemical properties

> A large-scale molecular dataset integrating structures, vibrational spectra and quantum-chemical properties

最终标题需要根据实际发布的数据类型、样本规模和数据来源确定。

## 3. Abstract

### Writing purpose

用 120–170 词回答四个问题：

1. 为什么需要这个数据集？
2. 数据从哪里来、如何生成？
3. 数据包含哪些模态和字段？
4. 其他研究者可以如何复用？

不要把摘要写成模型论文摘要，不要重点描述某个模型的性能提升，也不要提出未经验证的“最大”“最全面”等结论。

### Draft template

> Molecular spectroscopy provides information about chemical composition and structure, but existing public resources often focus on a single spectral modality or do not provide aligned three-dimensional structures and quantum-chemical properties. Here, we introduce OpenSpec, a large-scale multimodal molecular dataset linking molecular structures with vibrational spectra, NMR-related information and quantum-chemical properties. The dataset is compiled from [source datasets] and processed using [Gaussian calculation and parsing workflow]. Each record contains [main data fields], together with provenance metadata, quality-control flags and predefined data splits. The released data and processing code support spectrum-to-structure prediction, structure-to-spectrum generation, multimodal representation learning and molecular property prediction. OpenSpec is distributed through [repository] under [license], with a persistent identifier at [DOI].

正式版本必须替换所有方括号内容，并确保数据规模与实际发布版本一致。

## 4. Background & Summary

### Recommended length

800–1,200 words。

### Section objective

介绍数据集建立的背景、现有数据资源的不足和 OpenSpec 的复用价值。该部分应说明“为什么需要这个数据集”，但不应写成结果讨论或模型性能论文。

### Recommended structure

#### 4.1 Molecular spectroscopy and structure–property learning

介绍 IR、Raman、NMR 与分子结构、电子性质之间的关系，说明光谱数据在分子识别、结构解析、性质预测和生成式建模中的作用。

#### 4.2 Limitations of existing resources

围绕以下问题组织文献综述：

- 不同数据集通常只包含单一光谱类型；
- 光谱、三维坐标和量子化学性质缺少统一 ID 对齐；
- 数据格式、单位和光谱处理参数不统一；
- 缺少大规模、机器可读、带 provenance 的数据资源；
- 数据划分和结构泄漏问题可能影响 benchmark 的可信度。

这里应引用所有直接相关的数据集和已有光谱数据论文。

#### 4.3 Motivation and reuse value of OpenSpec

说明 OpenSpec 的目标和预期用途：

- spectrum-to-structure；
- structure-to-spectrum；
- 多模态分子预训练；
- 光谱检索和相似性搜索；
- 分子性质预测；
- scaling-law benchmark；
- 量子化学数据质量分析。

避免使用没有数据支持的主观表述，例如“革命性”“最先进”或“绝对最大”。

#### 4.4 Dataset overview

用一段话概述：

- 数据来源；
- 预计样本数量；
- 光谱和性质类型；
- 数据发布格式；
- 代码和 DOI 地址。

最终数量必须以正式发布版本为准，不应沿用项目早期目标数字。

## 5. Methods

### Recommended length

1,800–3,000 words。Methods 是 Data Descriptor 的核心章节，应写到读者能够根据描述复现数据处理流程。

### 5.1 Input datasets

逐一说明每个输入数据集：

| Dataset | Version | Original citation | Used data | License/redistribution |
|---|---|---|---|---|
| NIST IR | `[version]` | `[citation]` | `[fields]` | `[status]` |
| PAH | `[version]` | `[citation]` | `[fields]` | `[status]` |
| PCQM4MV2 | `[version]` | `[citation]` | `[fields]` | `[status]` |
| QM9 | `[version]` | `[citation]` | `[fields]` | `[status]` |
| RXN | `[version]` | `[citation]` | `[fields]` | `[status]` |
| Wiley IR | `[version]` | `[citation]` | `[fields]` | `[status]` |
| Wiley Raman | `[version]` | `[citation]` | `[fields]` | `[status]` |
| ZINC | `[version]` | `[citation]` | `[fields]` | `[status]` |

需要写明：

- 数据的精确版本或下载日期；
- 原始数据的获取地址；
- 使用了哪些字段；
- 输入记录数量；
- 筛选后记录数量；
- 是否进行 Gaussian 重新计算；
- 是否允许原始文件和派生文件再分发。

如果某个来源不能公开原始 Gaussian 文件，应在此处说明，并明确 OpenSpec 公开的是哪些派生数据。

### 5.2 Quantum-chemical calculations

说明 Gaussian 计算设置：

- Gaussian 版本；
- exchange-correlation functional；
- basis set；
- 电荷和自旋多重度；
- 几何优化设置；
- 频率计算设置；
- 是否检查虚频；
- Raman 计算设置；
- NMR shielding 计算设置；
- 温度和其他环境参数。

不要只写“按照标准 Gaussian 流程计算”，必须提供足以复现计算的设置。

### 5.3 Gaussian log-file parsing

描述从 `.log` 文件中提取的数据：

- 原子元素和原子序数；
- 三维坐标；
- archive section；
- Hessian；
- energy、ZPVE、U、H、G；
- dipole 和 polarizability；
- HOMO、LUMO 和 gap；
- vibrational frequencies；
- IR intensities；
- Raman activities；
- NMR isotropic shielding、anisotropy 和 tensor。

说明 parser 如何处理：

- 缺失字段；
- 可选字段；
- 格式不完整的日志；
- 数值解析失败；
- 重复记录；
- 解析失败日志的记录和报告。

解析异常不得静默丢弃。所有失败记录应进入 processing report。

### 5.4 Structure representation

说明：

- SMILES 的来源和标准化方式；
- 是否生成 canonical SMILES；
- 是否计算 InChIKey；
- 原子序数的数据类型；
- 坐标单位和数据类型；
- 分子 ID 和来源 ID 的命名规则；
- 同一分子多构象是否保留。

建议使用全局唯一 ID，例如：

```text
NISTIR-123
PAH-123
PCQM4MV2-123
WILEYIR-123
```

同时保存 `source_dataset` 和 `source_id`，不要只保存一个无法追溯来源的整数 ID。

### 5.5 Vibrational spectrum processing

需要明确写出所有光谱处理参数：

```text
frequency range       400–4000 cm⁻¹
number of grid points 1024
IR broadening         [sigma]
Raman broadening      [sigma]
Raman wavelength      532 nm, if retained
temperature           298 K, if retained
frequency scaling     0.965, if retained
line shape            Lorentzian
```

需要给出 Raman intensity 的计算公式，并说明每个量的单位、数据类型和数值范围。Raman 强度必须保持 `float64`，除非后续验证证明降精度不会改变数据。

如果 IR 和 Raman 使用不同的展宽参数、频率修正或强度计算流程，应在论文中明确区分。

### 5.6 NMR processing

说明：

- shielding 和 chemical shift 的定义；
- reference correction；
- isotropic shielding 和 anisotropy 单位；
- tensor 的元素排列顺序；
- NMR 光谱坐标范围；
- 展宽函数及 sigma；
- 原子级 NMR 数据如何与分子结构对齐；
- 缺少 NMR 的样本如何标记。

当前代码中 NMR 解析和光谱生成逻辑仍需进一步规范，正式写作前必须固定定义和单位。

### 5.7 Filtering and deduplication

说明样本筛选规则：

- 是否删除无法解析的 Gaussian 文件；
- 是否删除缺少 SMILES 的记录；
- 是否删除虚频结构；
- 是否删除异常原子或异常坐标；
- 是否保留同一分子的不同构象；
- 是否进行 exact duplicate 去重；
- 是否进行 canonical SMILES 或 InChIKey 去重；
- 是否进行跨来源数据去重。

必须报告每一步筛选前后的样本数量。

### 5.8 Data splits

建议至少提供：

- random split；
- molecule-level split；
- scaffold split；
- source-aware split。

需要说明划分比例、随机种子、去重顺序和划分文件格式。测试集中不应出现训练集中的同一分子或不合理近邻结构。

## 6. Data Records

### Recommended length

800–1,500 words。

这一节专门说明公开数据包的实际内容，不进行大规模科学分析。

### 6.1 Repository and version

写明：

- 数据仓库名称；
- DOI；
- 数据版本；
- 发布日期；
- 许可证；
- 代码仓库和 release；
- 数据是否包含原始 Gaussian 文件。

模板：

> The OpenSpec dataset is available from [repository] under accession [DOI]. Version [version] contains [number] records and is distributed under [license]. The release includes [file list]. The source code used for parsing and validation is available at [GitHub URL], release [tag].

### 6.2 Folder structure

建议描述：

```text
openspec-v1.0/
├── metadata/
├── structures/
├── spectra/
├── properties/
├── splits/
├── examples/
└── checksums.sha256
```

### 6.3 File formats

建议发布：

- Parquet：定长表格字段和 metadata；
- HDF5/NPZ：光谱、坐标、Hessian 等数组；
- JSON/JSONL：索引、数据字典和质量报告；
- pickle：仅作为 Python 兼容附加格式。

说明每种格式的读取方式、数组 shape、dtype、单位和缺失值表示。

### 6.4 Data dictionary

论文中应提供字段表。建议至少包含：

| Field | Type | Shape | Unit | Description |
|---|---|---|---|---|
| `sample_id` | string | scalar | — | Global sample identifier |
| `source_dataset` | string | scalar | — | Source dataset |
| `smiles` | string | scalar | — | Canonical or standardized SMILES |
| `atomic_numbers` | int32 | `N` | — | Atomic numbers |
| `coordinates` | float32 | `N×3` | Å | Cartesian coordinates |
| `freq` | float64 | variable | cm⁻¹ | Vibrational frequencies |
| `ir` | float64 | 1024 | documented | Broadened IR spectrum |
| `raman` | float64 | 1024 | documented | Broadened Raman spectrum |
| `nmr_shifts` | float64 | variable | documented | NMR values |
| `hessian` | float32/float64 | `3N×3N` | documented | Hessian matrix |
| `energy` | float64 | scalar | documented | Electronic energy |
| `gap` | float64 | scalar | documented | LUMO–HOMO gap |
| `quality_flags` | JSON/string | variable | — | Validation results |

## 7. Data Overview

### Recommended length

300–600 words，建议只使用 1–2 张图或表。

### Recommended content

- 各来源数据集的样本数；
- 各种光谱模态的覆盖率；
- 独立分子数和构象数；
- 元素、原子数和分子量分布；
- 缺失字段比例；
- 数据版本的总大小。

不要把这一节扩展为模型实验或新的科学结论。Data Descriptor 的重点是描述和支持数据复用。

## 8. Technical Validation

### Recommended length

1,200–2,000 words。

### 8.1 Parser validation

从每个来源随机抽取样本，将原始 Gaussian log 中的数值与 parser 输出逐项对照。

报告：

- 抽样数量；
- 字段匹配率；
- 数值误差；
- 解析失败率；
- 失败原因分类。

### 8.2 Structural consistency

检查：

- 原子数是否等于坐标数；
- 原子序数是否与 SMILES 元素组成一致；
- 坐标是否存在 NaN/Inf；
- Hessian 是否为 `3N×3N`；
- tensor shape 是否正确；
- 分子 ID 是否唯一。

### 8.3 Spectral consistency

检查：

- frequency 与 intensity 数量一致；
- IR/Raman 光谱长度一致；
- 光谱是否存在 NaN/Inf；
- 光谱值是否出现异常大值；
- 负频率如何处理；
- 展宽前后峰位置是否合理；
- Raman 强度计算是否保持 float64。

### 8.4 Property validation

检查能量、ZPVE、偶极矩、极化率、HOMO/LUMO、Hessian 和 NMR tensor 的字段完整性、shape、单位和数值范围。

### 8.5 Duplicate and leakage analysis

报告：

- exact duplicate 数量；
- canonical SMILES duplicate 数量；
- 跨来源重叠数量；
- scaffold 重叠情况；
- train/test 结构泄漏情况；
- 不同构象的划分策略。

### 8.6 Reproducibility validation

使用公开代码、固定依赖和 demo 输入重新执行处理流程，验证结果与发布文件一致。建议保存：

- parser version；
- Git commit；
- Python 和依赖版本；
- command line；
- random seed；
- SHA-256 checksums。

### 8.7 Validation 统计结果（当前发布版本，数字来自 `reports/publication/summary.json`）

> 复现命令：`python -m openmolspec.quality.stats --output reports/publication`
> （依赖缓存约 5 分钟；首次运行需加载 `artifacts/processed/openspec.pickle`、`artifacts/processed/openspec_nmr.pickle`
> 和 12 个轨迹 pickle，约 40 分钟）。

| 指标 | 数值 |
|---|---|
| 频率计算成功率 | 1,249,283 / 1,320,451 = 94.6% |
| Raman 光谱覆盖率（频率成功记录中） | 100% |
| NMR 计算成功率 | 1,105,022 / 1,320,451 = 83.7% |
| 三模态（IR+Raman+NMR）记录 | 1,101,461 |
| 几何优化收敛率（全库，11 来源平均） | 96.1%（各来源 91.9%–99.6%） |
| 含虚频的记录占比 | 3.09%（38,621 条；1 个虚频 32,918、2 个 4,647、≥3 个 1,056） |
| 唯一 InChIKey（发布记录） | 1,093,654 |
| 多构象分子数（同一 InChIKey ≥2 条记录） | 62,280（WILEYIR 最多，最大 89 构象） |
| 异常值标记记录数（10×MAD 或 [0.1%, 99.9%] 外） | 147,803（能量/力/频率/NMR shift 任一字段） |
| 热化学量缺失（U/H/G=NaN，解析器缺陷，见下） | 137,196 条（QM9 133,434 + ZINCV1 3,761 + ZINCV2 1） |

各来源明细表：`reports/publication/source_success_anomaly.csv`
（freq/Raman/NMR 成功率、收敛率、虚频率、异常率、QC 通过率汇总）。

已出版级图（`reports/publication/figures/`，300 dpi PNG）：

- `fig_convergence_by_source.png` — 各来源优化收敛/部分/失败堆叠条形
- `fig_modality_success_by_source.png` — 各来源频率/Raman/NMR/三模态成功率
- `fig_imaginary_frequency_distribution.png` — 虚频数量分布 + 最小频率分布
- `fig_outlier_detection.png` — 每原子能量、最终力、最小频率、NMR 极值分布
- `fig_conformer_distribution.png` — 构象数分布
- `fig_molecular_distributions.png` — 元素覆盖、分子量、重原子数、原子数分布
- `fig_source_rates_heatmap.png` — 各来源成功率/异常率热图

#### 解析器缺陷记录（正文需披露）

QM9（100%）与部分 ZINCV1 的 Gaussian log 在 archive 段不输出
`ETot/HTot/GTot`，导致旧解析器丢失 U/H/G（存为 NaN，影响 137,196 条记录
的 QC 判定）。log 正文的 "Sum of electronic and thermal Energies/Enthalpies/
Free Energies" 行包含完整值；`src/openmolspec/parsing/gaussian.py` 已修复（文本行 fallback，
`tests/test_parser_thermal.py` 覆盖）。发布数据的回填重生成待定，详见
`docs/validation_findings.md`。

## 9. Usage Notes

### Recommended length

300–700 words。

提供最小可运行示例，说明如何：

1. 下载数据；
2. 读取一个结构记录；
3. 读取 IR/Raman/NMR 光谱；
4. 读取量子化学性质；
5. 使用预定义 split；
6. 处理缺失字段和质量标记。

建议在代码仓库中同时提供 `examples/load_sample.py`。

### 9.1 Benchmark 任务（Application，GPU 集群执行）

正式任务共用冻结发布版本的 scaffold-disjoint aligned 分割，分子身份与
scaffold 均不跨越 train/eval/test，测试集跨模型一致。
数据准备：`python -m benchmarks.data.prepare --split-file builds/openmolspec-20260830/release-v1/splits/align_split.parquet --output benchmark_data/release_v1 --workers 32`。

| 任务 | 输入 | 目标 | 模型 | 指标 | 入口 |
|---|---|---|---|---|---|
| 结构→属性 | 3D 结构 | energy, gap, homo, lumo, dipole_total, zpve | EquiformerV3 | MAE / RMSE / R² | `benchmarks/models/equiformer_v3/train.py` |
| 结构→光谱 | 3D 结构 | IR / Raman（1024 点） | EquiformerV3 | MAE / cosine / Pearson | 同上 |
| 光谱→结构 | IR / Raman | kekule SMILES | Vib2Mol | top-1 / top-10 recall | `benchmarks/scripts/run_vib2mol.sh` |
| 光谱→构象 | IR / Raman | 3D 构象 | Vib2Conf | Recall@1/3/5 | `benchmarks/scripts/run_vib2conf.sh` |
| 光谱→属性 | IR / Raman | 量子性质 | Vib2Conf 谱编码器+回归头 | MAE / RMSE / R² | `benchmarks/models/vib2conf/props_head.py` |

模型上游代码分别 pin 于 `benchmarks/models/<name>/upstream/`（vib2mol
`207a86e`、vib2conf `7038837`、equiformer_v3 `a7300c5`）。完整运行说明见
`docs/plans/benchmark_runbook.md`；结果模板 `reports/benchmark/results_template.csv`。

> 说明：Vib2Conf 上游的 `--grad-props`（光谱→属性）在 pin commit 中只做
> 参数校验、未接入训练；本仓库在 `props_head.py` 中实现了该契约（复用其
> SpectralEncoding + SpectralEncoder + AttentionalPooling 结构）。

## 10. Data Availability

该声明需要简洁但完整，重复 Data Records 的核心信息。

### Template

> The OpenSpec dataset is available at [repository] under accession [DOI], version [version]. The release contains [specific files and data types] and is distributed under [license]. Source datasets are acknowledged and cited in the Data Records and References sections. Where redistribution of original Gaussian log files is restricted, OpenSpec provides the corresponding derived data, provenance metadata and source-file hashes.

正式版本必须替换所有方括号内容，并确认许可证与数据仓库页面一致。

## 11. Code Availability

### Template

> The code used to parse Gaussian log files, generate processed spectra and perform quality control is available at [GitHub URL], release [tag] or commit [hash]. The repository contains the processing scripts, schema, validation utilities and example commands. The computational environment is documented in [environment file].

需要附上：

- GitHub URL；
- release/tag 或 commit；
- Python 版本；
- RDKit、NumPy、pandas 等依赖版本；
- 数据生成命令；
- 小规模测试命令；
- parser 和 schema 版本。

## 12. Figures and tables

### Recommended figures

#### Figure 1. Data production workflow

展示：

```text
source datasets
    ↓
Gaussian calculations/log files
    ↓
ID and SMILES matching
    ↓
log parsing
    ↓
spectrum/property processing
    ↓
quality control and deduplication
    ↓
public release and benchmark splits
```

#### Figure 2. Dataset composition

展示各来源数据集、光谱类型和量化性质覆盖率。

#### Figure 3. Representative multimodal record

同一分子同时展示：

- 2D molecular graph；
- 3D coordinates；
- IR spectrum；
- Raman spectrum；
- NMR spectrum；
- selected quantum-chemical properties。

#### Figure 4. Technical validation

展示 parser 对照、缺失率、重复率、异常值和数据划分泄漏检查。

### Recommended tables

- Table 1：数据来源、版本、样本数和许可证；
- Table 2：数据字段、数据类型、shape 和单位；
- Table 3：质量控制规则及通过率；
- Table 4：数据划分和结构泄漏统计。

## 13. Supplementary Information

只放正文无法容纳但有助于复现的材料，例如：

- 完整 Gaussian 输入参数；
- 额外 parser 正则表达式说明；
- 详细单位转换公式；
- 额外的质量控制表；
- 大型但规模适中的字段说明；
- 额外读取示例。

不要把大规模数据表放入 Supplementary Information。大型数据应放入数据仓库，并在论文中通过 DOI 和文件名引用。

## 14. Author statements

### Author Contributions

按 CRediT 或类似方式说明：

- Conceptualization；
- Data curation；
- Methodology；
- Software；
- Validation；
- Writing – original draft；
- Writing – review and editing；
- Supervision；
- Project administration。

### Competing Interests

如果没有竞争利益，可以使用期刊允许的标准表述：

> The authors declare no competing interests.

### Funding

列出基金名称、项目编号和资助机构。没有资助时按期刊要求说明。

### Ethics statement

该项目主要使用计算化学和公开分子数据，通常不涉及人或动物实验；正式投稿时仍应根据数据来源和期刊表格要求确认是否需要声明。

## 15. Final writing checklist

### Scientific content

- [ ] 标题客观且不超过 110 个字符；
- [ ] 摘要不超过 170 词；
- [ ] Background & Summary 说明数据需求和复用价值；
- [ ] Methods 足以复现数据处理；
- [ ] Data Records 定义全部文件和字段；
- [ ] Technical Validation 给出定量质量证据；
- [ ] 不将 Data Descriptor 写成普通模型性能论文；
- [ ] 所有统计数字与正式数据版本一致。

### Data and code

- [ ] 数据可供审稿人匿名访问；
- [ ] 正式数据仓库具有 DOI；
- [ ] 数据许可证已确认；
- [ ] 输入数据集全部引用；
- [ ] 代码 release 和数据版本互相对应；
- [ ] schema、metadata 和 checksums 已发布；
- [ ] 提供 demo 和读取示例；
- [ ] 已完成去重、质量控制和数据泄漏检查。

## 16. Official references

- [Scientific Data submission guidelines](https://www.nature.com/sdata/publish/submission-guidelines)
- [Scientific Data aims and scope](https://www.nature.com/sdata/aims-and-scope)
- [Scientific Data data policies](https://www.nature.com/sdata/policies/data-policies)
- [Scientific Data repository guidance](https://www.nature.com/sdata/policies/repositories)
- [Scientific Data guide for referees](https://www.nature.com/sdata/policies/for-referees)
