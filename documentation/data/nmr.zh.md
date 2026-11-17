# NMR data

![NMR data availability](../assets/gallery/data-nmr-availability.png)

[SVG](../assets/gallery/data-nmr-availability.svg) · [PDF](../assets/gallery/data-nmr-availability.pdf)

![NMR chemical distributions](../assets/gallery/data-nmr-nuclei.png)

[SVG](../assets/gallery/data-nmr-nuclei.svg) · [PDF](../assets/gallery/data-nmr-nuclei.pdf)

## OpenDataLab

- **NMR: 18,588,070** 条谱条目; **13,732,773** 条附有结构文本。

| Availability check / 字段可用性 | Entries or values / 条目或数值 |
| --- | ---: |
| `NMR:nonempty_shift_text` | 18,511,179 |
| `NMR:shift_text_contains_number` | 18,499,239 |
| `NMR:solvent_present` | 18,167,918 |
| `NMR:positive_frequency` | 17,349,294 |

[完整扫描结果](../assets/reports/opendatalab_all_modalities_20261117.json)保留原谱型标签与准确分类规则。

### Qualified molecular identities / 结构资格检查

| Modality | Qualified full InChIKeys | Source entries attached to these identities |
| --- | ---: | ---: |
| NMR | 2,707,528 | 13,716,645 |

资格检查要求可生成标准分子身份及受支持的骨架分组，不等同于谱提取正确或已满足任务训练要求。同一分子可以出现于多个模态。[完整检查与排除范围](../assets/reports/opendatalab_structure_qualification_20261117.json)。

### OpenDataLab nucleus labels / 核种标签

| Nucleus label | Source entries |
| --- | ---: |
| 1H | 16,572,405 |
| 13C | 1,456,877 |
| 19F | 360,167 |
| 31P | 161,534 |
| 11B | 9,154 |
| 29Si | 6,571 |
| Other / multiple nuclei | 9,253 |
| Unspecified | 12,109 |

整理后的 H/C 视图包含 2,680,271 个标准 InChI 身份、238,412 条 H/C 配对记录，保留原准备库的 train/val/test。按分子身份配对不自动意味着采集条件一致。

## External experimental data / 外部实验数据

**NMRexp v2 本地全库：**3,372,987 条谱记录、1,499,173 个有效标准 InChIKey 身份。

![NMRexp nucleus availability](../assets/gallery/dataset-nmrexp-nuclei.png)

| Resource | Modalities | Citation |
| --- | --- | --- |
| NMRexp v2 | ¹H, ¹³C, ¹⁹F, ³¹P, ¹¹B, ²⁹Si | [Dataset](https://zenodo.org/records/17296666) |
| NMRSpec / NMRTrans | Paired ¹H / ¹³C | [Paper](https://arxiv.org/abs/2602.10158) |
| NMRGym | Paired ¹H / ¹³C | [Paper](https://arxiv.org/abs/2601.15763) |
| NMRShiftDB | Assigned shifts and experimental conditions | [Project](https://nmrshiftdb.nmr.uni-koeln.de/) |

### NMRexp local nucleus views / 本地核种视图

| View | Spectral records |
| --- | ---: |
| `nmrexp_11B_usable` | 16,871 |
| `nmrexp_13C_usable` | 1,439,344 |
| `nmrexp_19F_usable` | 195,077 |
| `nmrexp_1H_usable` | 1,651,821 |
| `nmrexp_29Si_usable` | 2,385 |
| `nmrexp_31P_usable` | 32,890 |

这些过滤视图与 NMRexp 全库重叠，不应作为额外谱量相加。

[Data index](index.md) · [Loading API](../api.md) · [Splits](splits.md) · [Theory](../theory/index.md)

[External complete-file census / 外部数据扫描](../assets/reports/external_data_census_20261117.json)
