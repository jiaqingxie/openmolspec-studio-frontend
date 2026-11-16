# 谱图 → SMILES · HC

用已有生成模型从实验 H/C NMR 预测 SMILES 候选。

## 当前结论

存在明显数据域差异：专利和 NMRGym 的 32 样本检查均为零精确匹配。先检查独立测试、解析及词表覆盖，再考虑领域微调。

## 输入是什么

| Field | Meaning |
| --- | --- |
| `h_nmr / c_nmr` | HC 谱记录：位移（ppm）及原记录中的多重性、积分、J 值；按模态掩码选择输入。 |
| `formula` | 此 checkpoint 必须显式提供已知分子式。 |
| `beam_size` | 解码候选数；本页实验使用 5。 |

## 输出是什么

| Field | Meaning |
| --- | --- |
| `candidates` | 生成 SMILES、规范结构、有效性、分子式一致性及模型分数。 |
| `exact_match` | 将选中候选与参考结构比较；SMILES 有效并不代表结构正确。 |

## 真实运行案例

下面展示记录中的第一例，不按结果好坏筛选。长数组预览会标明完整长度；完整数值可下载证据 JSON。参考标签与模型输入分开保留。

```json
{
  "input": {
    "formula": "C22H28",
    "h_nmr": [
      {
        "type": "1H NMR",
        "chemical_shift": "7.34 (s, 4H), 7.265 (m, 2H), 7.165 (m, 3H), 5.26 (d, J=1.6 Hz, 1H), 5.01 (t, J=1.4 Hz, 1H), 2.61 (t, J=7.8 Hz, 2H), 2.53 (t, J=7.6 Hz, 2H), 1.665 (m, 2H), 1.52 (d, J=7.7 Hz, 2H), 1.33 (s, 9H)"
      }
    ],
    "c_nmr": [
      {
        "type": "13C NMR",
        "chemical_shift": "150.22, 148.03, 142.68, 138.28, 128.36, 128.22, 125.68, 125.58, 125.12, 111.51, 35.72, 35.03, 34.46, 31.32, 31.11, 27.93"
      }
    ],
    "modality_mask": [
      1,
      1
    ]
  },
  "reference_smiles": "C=C(CCCCc1ccccc1)c1ccc(C(C)(C)C)cc1",
  "candidates": {
    "length": 5,
    "first_values": [
      {
        "smiles": "C=C(CCCCc1ccc(C(C)(C)C)cc1)c1ccccc1",
        "canonical_smiles": "C=C(CCCCc1ccc(C(C)(C)C)cc1)c1ccccc1",
        "score": -1.4133434984593123,
        "valid": true,
        "formula_match": true
      },
      {
        "smiles": "C=C(CCCCc1ccccc1)c1ccc(C(C)(C)C)cc1",
        "canonical_smiles": "C=C(CCCCc1ccccc1)c1ccc(C(C)(C)C)cc1",
        "score": -1.5937606929851142,
        "valid": true,
        "formula_match": true
      },
      {
        "smiles": "C=C(CCCc1ccc(C(C)(C)C)cc1)Cc1ccccc1",
        "canonical_smiles": "C=C(CCCc1ccc(C(C)(C)C)cc1)Cc1ccccc1",
        "score": -3.3677357960558183,
        "valid": true,
        "formula_match": true
      },
      {
        "smiles": "C=C(CCCCc1ccccc1)CCCc1ccccc1",
        "canonical_smiles": "C=C(CCCCc1ccccc1)CCCc1ccccc1",
        "score": -2.710929739130215,
        "valid": true,
        "formula_match": false
      }
    ]
  },
  "exact_match": false
}
```

![nmr.generation.hc actual results](../assets/gallery/nmr-generation-hc.png)

[SVG](../assets/gallery/nmr-generation-hc.svg) · [PNG](../assets/gallery/nmr-generation-hc.png) · [Full input/output JSON](../assets/examples/nmr-generation-hc.json)

## 实际评测结果

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| nmrspec_test | recorded model | examples | 32 |
| nmrspec_test | recorded model | valid_rate | 1 |
| nmrspec_test | recorded model | formula_match_rate | 0.90625 |
| nmrspec_test | recorded model | exact_rate | 0.125 |
| patent_test_10k | recorded model | examples | 32 |
| patent_test_10k | recorded model | valid_rate | 0.75 |
| patent_test_10k | recorded model | formula_match_rate | 0.03125 |
| patent_test_10k | recorded model | exact_rate | 0 |
| nmrexp_exp_10k | recorded model | examples | 32 |
| nmrexp_exp_10k | recorded model | valid_rate | 1 |
| nmrexp_exp_10k | recorded model | formula_match_rate | 0.90625 |
| nmrexp_exp_10k | recorded model | exact_rate | 0.6875 |
| nmrgym_test | recorded model | examples | 32 |
| nmrgym_test | recorded model | valid_rate | 0.78125 |
| nmrgym_test | recorded model | formula_match_rate | 0.46875 |
| nmrgym_test | recorded model | exact_rate | 0 |

样本量和候选池随每次运行记录。图可能展示单个分子，表格是来源实验的实际汇总，不能混为同一统计范围。

## 模型与方法

该模型需要显式给定分子式。按原推理代码的有效性、分子式一致性和模型分数排序 beam，取 top-1 评分。不会从目标 SMILES 偷偷推导缺失的输入分子式。

报告有效 SMILES 比率、规范异构 SMILES exact match、分子式一致率，同时保存 beam size、模态 mask 和样本。JSONL 的 smiles 仅是评测答案，不是生成输入。

## 复现方式

[Notebook with executed figures](../notebooks/nmr-generation-hc.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.generation.hc --limit 8 --output results/nmr-generation-hc-new.json
```

## 边界与来源

给定分子式的结构生成与分子式预测、无分子式生成是不同任务。跨数据集 exact match 低或为零时保留真实结果，不替换成缓存答案。

- [nmr_documented_examples_20261117_v2.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/nmr_documented_examples_20261117_v2.json) — SHA-256 `669413d6fc0939bdb6826782d41fc13cf12926a672418ecb46303f0b8ba05b99`

[Original model / 原模型](https://github.com/jiaqingxie/openmolspec-studio-frontend) · [Model review / 模型检查](../model-audit.md)
