# MS/MS 峰 → MAGMa 候选碎片标注

从已知分子枚举候选碎片，用质量误差匹配实测 MS/MS 谱峰，无需模型训练。

## 当前结论

这是算法标注，不是可微调神经模型；应改进匹配和验证。

## 输入是什么

| Field | Meaning |
| --- | --- |
| `smiles / peaks` | 已知结构、实测 MS/MS 峰 [m/z, 相对强度] 及加合物。 |
| `ppm_tolerance` | 质量误差容限，默认 10 ppm；不是 NMR 化学位移容限。 |

## 输出是什么

| Field | Meaning |
| --- | --- |
| `peak_annotations` | 候选碎片、分子式、质量误差及 engine_smiles 上的原子/键编号。 |
| `interpretation` | 算法给出的候选解释，不是已实验确认的唯一裂解机制。 |

## 真实运行案例

下面展示记录中的第一例，不按结果好坏筛选。长数组预览会标明完整长度；完整数值可下载证据 JSON。参考标签与模型输入分开保留。

```json
{
  "input": {
    "smiles": "C1=CC=C(C(=C1)C2=CC=C(C=C2)C(=O)O)C3=NNN=N3",
    "adduct": "[M+H]+",
    "observed_peaks": {
      "length": 40,
      "first_values": [
        [
          86.0158,
          0.14814814814814814
        ],
        [
          87.0237,
          0.16016016016016016
        ],
        [
          97.0082,
          0.06906906906906907
        ],
        [
          98.0159,
          1.0
        ]
      ]
    }
  },
  "sample_id": "MassSpecGymID0046618",
  "output": {
    "engine_smiles": "O=C(O)c1ccc(-c2ccccc2-c2nn[nH]n2)cc1",
    "peak_annotations": {
      "length": 40,
      "first_values": [
        {
          "peak_id": 7,
          "mz": 86.0158,
          "intensity": 0.14814814814814814,
          "matched": true,
          "matched_fragment": {
            "fragment_id": 16256,
            "atom_indices": {
              "length": 7,
              "first_values": [
                7,
                8,
                9,
                10
              ]
            },
            "bond_indices_cut": [
              6,
              13,
              21
            ],
            "bond_atom_pairs_cut": [
              [
                6,
                7
              ],
              [
                13,
                14
              ],
              [
                17,
                13
              ]
            ],
            "formula": "C7H4",
            "matched_mass": 85.007825032,
            "ppm_diff": 8.21707883641277,
            "score": 5.0,
            "h_shift": -3,
            "tree_depth": 3,
            "parent_fragment_ids": [
              130944,
              245632,
              802815
            ],
            "lineage_root_to_fragment": [
              1048575,
              262016,
              245632,
              16256
            ]
          }
        },
        {
          "peak_id": 8,
          "mz": 87.0237,
          "intensity": 0.16016016016016016,
          "matched": true,
          "matched_fragment": {
            "fragment_id": 786554,
            "atom_indices": {
              "length": 7,
              "first_values": [
                1,
                3,
                4,
                5
              ]
            },
            "bond_indices_cut": [
              0,
              1,
              6
            ],
            "bond_atom_pairs_cut": [
              [
                0,
                1
              ],
              [
                1,
                2
              ],
              [
                6,
                7
              ]
            ],
            "formula": "C7H4",
            "matched_mass": 86.015650064,
            "ppm_diff": 8.992363592338872,
            "score": 5.0,
            "h_shift": -2,
            "tree_depth": 3,
            "parent_fragment_ids": [
              786555,
              786558,
              1048570
            ],
            "lineage_root_to_fragment": [
              1048575,
              1048574,
              1048570,
              786554
            ]
          }
        },
        {
          "peak_id": 10,
          "mz": 97.0082,
          "intensity": 0.06906906906906907,
          "matched": true,
          "matched_fragment": {
            "fragment_id": 8160,
            "atom_indices": {
              "length": 8,
              "first_values": [
                5,
                6,
                7,
                8
              ]
            },
            "bond_indices_cut": [
              4,
              12,
              17
            ],
            "bond_atom_pairs_cut": [
              [
                4,
                5
              ],
              [
                12,
                13
              ],
              [
                6,
                18
              ]
            ],
            "formula": "C8H5",
            "matched_mass": 96.0,
            "ppm_diff": 9.620291666697275,
            "score": 6.0,
            "h_shift": -5,
            "tree_depth": 3,
            "parent_fragment_ids": [
              262112,
              532479,
              794607
            ],
            "lineage_root_to_fragment": [
              1048575,
              1048559,
              794607,
              8160
            ]
          }
        },
        {
          "peak_id": 11,
          "mz": 98.0159,
          "intensity": 1.0,
          "matched": true,
          "matched_fragment": {
            "fragment_id": 786936,
            "atom_indices": {
              "length": 8,
              "first_values": [
                3,
                4,
                5,
                6
              ]
            },
            "bond_indices_cut": [
              2,
              8,
              20
            ],
            "bond_atom_pairs_cut": [
              [
                1,
                3
              ],
              [
                8,
                9
              ],
              [
                12,
                7
              ]
            ],
            "formula": "C8H5",
            "matched_mass": 97.007825032,
            "ppm_diff": 8.23145967595748,
            "score": 6.0,
            "h_shift": -4,
            "tree_depth": 3,
            "parent_fragment_ids": [
              786943,
              790520,
              1048056
            ],
            "lineage_root_to_fragment": [
              1048575,
              1048568,
              1048056,
              786936
            ]
          }
        }
      ]
    }
  }
}
```

![ms.annotation.magma actual results](../assets/gallery/ms-annotation-magma.png)

[SVG](../assets/gallery/ms-annotation-magma.svg) · [PNG](../assets/gallery/ms-annotation-magma.png) · [Full input/output JSON](../assets/examples/ms-annotation-magma.json)

## 实际评测结果

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | recorded model | matched_peak_fraction | 0.568182 |
| recorded evaluation | recorded model | checked_fragments | 1534 |

样本量和候选池随每次运行记录。图可能展示单个分子，表格是来源实验的实际汇总，不能混为同一统计范围。

## 模型与方法

保留 MAGMa v8 原来的规范化和默认 10 ppm 容差。片段原子编号按引擎实际使用的 engine_smiles 解释，逐片检查原子元素计数、原子范围和键连接；不能直接套到输入 SMILES 的原子顺序。

报告匹配谱峰比例、成功标注谱图数及检查的碎片数。候选片段和根到片段路径是算法解释，不能当作实验确认的唯一碎裂机制。

## 复现方式

[Notebook with executed figures](../notebooks/ms-annotation-magma.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks ms.annotation.magma --limit 8 --output results/ms-annotation-magma-new.json
```

## 边界与来源

氢迁移、图深度、断键数等字段沿用原算法语义。默认规范化会改变原子顺序，必须保留 engine_smiles；不擅自改动枚举和匹配算法。

- [magma_real_test_verified_20261115.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/magma_real_test_verified_20261115.json) — SHA-256 `e65563b00863389105f5eae392d493167d693ac4ca38b9f1abfbd40942d1946b`

[Original model / 原模型](https://github.com/Dsadd4/MassSpecGym-MAGMA-annotation) · [Model review / 模型检查](../model-audit.md)
