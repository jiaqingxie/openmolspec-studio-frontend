# 结构 → 1H 峰列表

由分子结构预测 1H 化学位移，已有兼容权重时进行冻结推理或已有预测评分。

## 当前结论

可作为 H/C 冻结模型基线；误差来自峰匹配，不代表实验原子指认。仍要检查训练重叠和溶剂覆盖。

## 输入是什么

| Field | Meaning |
| --- | --- |
| `smiles / geometry` | 有效分子结构及相容的三维构象，必须保留原子顺序。 |
| `nucleus` | 1H，权重必须覆盖该核种。 |
| `reference peaks` | 评测时提供实测 ppm 标签；标签不作为模型推理输入。 |

## 输出是什么

| Field | Meaning |
| --- | --- |
| `prediction_ppm` | 逐原子化学位移（ppm）及原子编号，或整理后的峰列表。 |
| `error / coverage` | 与参考谱匹配后的误差及覆盖率；峰匹配不等于实验原子指认。 |

## 真实运行案例

下面展示记录中的第一例，不按结果好坏筛选。长数组预览会标明完整长度；完整数值可下载证据 JSON。参考标签与模型输入分开保留。

```json
{
  "input": {
    "smiles": "C=C(CCCCc1ccccc1)c1ccc(C(C)(C)C)cc1"
  },
  "output": {
    "prediction_ppm": {
      "length": 28,
      "first_values": [
        5.080643653869629,
        5.033477783203125,
        2.49700927734375,
        2.570378065109253
      ]
    },
    "model": "nmrnet"
  },
  "reference": {
    "peaks_ppm": {
      "length": 10,
      "first_values": [
        7.34,
        7.265,
        7.165,
        5.26
      ]
    }
  }
}
```

![nmr.forward.1H actual results](../assets/gallery/nmr-forward-1H.png)

[SVG](../assets/gallery/nmr-forward-1H.svg) · [PNG](../assets/gallery/nmr-forward-1H.png) · [Full input/output JSON](../assets/examples/nmr-forward-1H.json)

## 实际评测结果

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| nmrspec_test | nmrnet | matched_peak_mae_ppm | 0.134143 |
| nmrspec_test | nmrnet | matched_fraction | 0.519243 |
| nmrspec_test | nmrnet | examples | 32 |
| nmrspec_test | nmrnet | scored_examples | 32 |
| nmrspec_test | nmrnetpp | matched_peak_mae_ppm | 0.0769934 |
| nmrspec_test | nmrnetpp | matched_fraction | 0.519243 |
| nmrspec_test | nmrnetpp | examples | 32 |
| nmrspec_test | nmrnetpp | scored_examples | 32 |
| patent_test_10k | nmrnet | matched_peak_mae_ppm | 0.26912 |
| patent_test_10k | nmrnet | matched_fraction | 0.294737 |
| patent_test_10k | nmrnet | examples | 29 |
| patent_test_10k | nmrnet | scored_examples | 29 |
| patent_test_10k | nmrnetpp | matched_peak_mae_ppm | 0.227842 |
| patent_test_10k | nmrnetpp | matched_fraction | 0.294737 |
| patent_test_10k | nmrnetpp | examples | 29 |
| patent_test_10k | nmrnetpp | scored_examples | 29 |
| nmrexp_exp_10k | nmrnet | matched_peak_mae_ppm | 0.0485825 |
| nmrexp_exp_10k | nmrnet | matched_fraction | 0.530831 |
| nmrexp_exp_10k | nmrnet | examples | 32 |
| nmrexp_exp_10k | nmrnet | scored_examples | 32 |
| nmrexp_exp_10k | nmrnetpp | matched_peak_mae_ppm | 0.030637 |
| nmrexp_exp_10k | nmrnetpp | matched_fraction | 0.530831 |
| nmrexp_exp_10k | nmrnetpp | examples | 32 |
| nmrexp_exp_10k | nmrnetpp | scored_examples | 32 |
| nmrgym_test | nmrnet | matched_peak_mae_ppm | 0.196824 |
| nmrgym_test | nmrnet | matched_fraction | 0.529103 |
| nmrgym_test | nmrnet | examples | 32 |
| nmrgym_test | nmrnet | scored_examples | 32 |
| nmrgym_test | nmrnetpp | matched_peak_mae_ppm | 0.198216 |
| nmrgym_test | nmrnetpp | matched_fraction | 0.529103 |
| nmrgym_test | nmrnetpp | examples | 32 |
| nmrgym_test | nmrnetpp | scored_examples | 32 |

样本量和候选池随每次运行记录。图可能展示单个分子，表格是来源实验的实际汇总，不能混为同一统计范围。

## 模型与方法

H/C 读取 NMRNet、NMRNet++ 的预测及对应元数据；未指认实验峰用最小绝对误差匹配，并保留峰数和覆盖率诊断。

位移和误差单位均为 ppm。按分子等权计算匹配峰 MAE/RMSE，必须同时报告匹配比例与峰数误差，因为匹配误差本身不惩罚全部缺失峰或额外峰。

## 复现方式

[Notebook with executed figures](../notebooks/nmr-forward-1H.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.1H --limit 8 --output results/nmr-forward-1H-new.json
```

## 边界与来源

峰匹配误差不是逐原子指认准确率。这里对 H/C 保存的预测评分，不据此外推其他核种的适用性。

- [nmr_documented_examples_20261117_v2.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/nmr_documented_examples_20261117_v2.json) — SHA-256 `669413d6fc0939bdb6826782d41fc13cf12926a672418ecb46303f0b8ba05b99`

[Original model / 原模型](https://github.com/Colin-Jay/NMRNet) · [Model review / 模型检查](../model-audit.md)
