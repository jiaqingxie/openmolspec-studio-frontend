# MS data

![MS data availability](../assets/gallery/data-ms-availability.png)

[SVG](../assets/gallery/data-ms-availability.svg) · [PDF](../assets/gallery/data-ms-availability.pdf)

![MS chemical distributions](../assets/gallery/data-ms-distributions.png)

[SVG](../assets/gallery/data-ms-distributions.svg) · [PDF](../assets/gallery/data-ms-distributions.pdf)

## OpenDataLab

- **MS: 13,257,689** spectral entries; **10,356,478** with structure text.

| Availability check / 字段可用性 | Entries or values / 条目或数值 |
| --- | ---: |
| `MS:unstructured_or_missing` | 13,226,620 |
| `MS:positive_measured_mz` | 13,233,024 |
| `MS:at_least_two_numeric_peaks` | 29,480 |
| `MS:at_least_six_numeric_peaks` | 14,354 |
| `MS:fragment_text_present` | 1,367 |
| `MS:explicit_collision_energy` | 2 |
| `MS:numeric_positions_only` | 12,263 |
| `MS:numeric_position_intensity_pairs` | 17,742 |
| `MS:mixed_or_text_peaks` | 1,064 |

[Full census](../assets/reports/opendatalab_all_modalities_20261117.json) retains raw spectrum labels and exact classification rules.

### Qualified molecular identities / 结构资格检查

| Modality | Qualified full InChIKeys | Source entries attached to these identities |
| --- | ---: | ---: |
| MS | 2,167,510 | 10,347,217 |

Qualification requires a standard molecular identity and a supported scaffold group; it does not establish spectral extraction accuracy or task eligibility. A molecule can occur in several modalities. [Full qualification and exclusion scope](../assets/reports/opendatalab_structure_qualification_20261117.json).

A molecular-ion m/z record, a list of fragment positions, and a spectrum with numerical intensities support different tasks. Only the last supplies the full reference needed for intensity-spectrum evaluation.

## External experimental data / 外部实验数据

- [MassSpecGym v1.5](https://huggingface.co/datasets/roman-bushuiev/MassSpecGym): updated RDKit-standardized molecular structures and benchmark files.
- [MassBank](https://github.com/MassBank/MassBank-data): experimental spectra with per-record acquisition metadata and provenance.

**MassSpecGym v1.5:** 231,104 spectra / 28,923 molecular connectivities. 231,104 valid numerical peak arrays; 121,746 records with finite scalar collision energy.

```python
from openmolspec.dataset import molspectra
data = molspectra("massspecgym_1_5", root="/path/to/versioned-tsv")
print(data["test"].head(1))
```

**MassBank local snapshot:** 142,978 records / 142,978 accessions. MS type and acquisition metadata remain attached to each record.

| MS type | Local records |
| --- | ---: |
| MS2 | 120,949 |
| MS | 21,011 |
| MSn | 19 |
| MS3 | 929 |
| MS4 | 70 |

Complete peak validation found **142,978 valid numerical spectra**, including **120,512 MS2 spectra with a parseable structure**; 20,375 unique valid full standard-InChIKeys occur in the snapshot. Declared peak counts agree for every record.

[Numerical qualification and snapshot fingerprint / 数值检查与快照指纹](../assets/reports/massbank_spectrum_qualification_20261117.json)

[Data index](index.md) · [Loading API](../api.md) · [Splits](splits.md) · [Theory](../theory/index.md)

[External complete-file census / 外部数据扫描](../assets/reports/external_data_census_20261117.json)
