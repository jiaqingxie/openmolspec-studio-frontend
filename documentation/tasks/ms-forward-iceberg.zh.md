# 分子 → MS/MS（ICEBERG）

给定分子结构、加合物、碰撞能和仪器，预测 MS/MS 的 m/z–强度峰列表。

## 当前结论

采用作者接口并显式提供采集条件，方法适配合理；31 条评分不足以证明广泛精度。先核查协议与训练重叠，再决定微调。

## 输入是什么

| Field | Meaning |
| --- | --- |
| `smiles / adduct` | 分子结构与记录中的离子/加合物类型，例如 [M+H]+ 或 [M+Na]+。 |
| `collision_energy / instrument` | 发布模型支持的实际碰撞能与仪器条件；不能补造缺失值。 |
| `precursor_mz` | 记录中的前体 m/z；按作者接口解释输入条件。 |

## 输出是什么

| Field | Meaning |
| --- | --- |
| `predicted_peaks` | m/z 与相对强度对；图中显示预测强度最高的 100 个峰。 |
| `similarity` | 与全部实测参考峰比较的余弦/熵相似度，同时统计跳过记录。 |

## 真实运行案例

下面展示记录中的第一例，不按结果好坏筛选。长数组预览会标明完整长度；完整数值可下载证据 JSON。参考标签与模型输入分开保留。

![ms.forward.iceberg actual results](../assets/gallery/ms-forward-iceberg.png)

[SVG](../assets/gallery/ms-forward-iceberg.svg) · [PNG](../assets/gallery/ms-forward-iceberg.png) · [Full input/output JSON](../assets/examples/ms-forward-iceberg.json)

<details><summary>展开查看实际输入与输出字段</summary>

```json
{
  "input": {
    "smiles": "C/C1=C\\[C@@H](C)C/C=C/[C@H]2[C@@H]3O[C@]3(C)[C@@H](C)[C@H]3[C@H](Cc4c[nH]c5ccccc45)NC(=O)[C@]32C(=O)/C=C/C(=O)[C@@H]1O",
    "adduct": "[M+Na]+",
    "collision_energy": "35.0",
    "instrument": "Orbitrap",
    "precursor_mz": 551.2511
  },
  "sample_id": "MassSpecGymID0000403",
  "output": {
    "predicted_peaks_top100": {
      "length": 100,
      "first_values": [
        [
          93.06987621515076,
          0.0043686628341674805
        ],
        [
          129.0573002311496,
          0.004620126914232969
        ],
        [
          130.065125248125,
          0.07967650890350342
        ],
        [
          131.07295026510042,
          0.011109611950814724
        ]
      ]
    }
  },
  "reference": {
    "observed_peaks": {
      "length": 12,
      "first_values": [
        [
          160.0366,
          0.03803803803803804
        ],
        [
          240.0992,
          0.03803803803803804
        ],
        [
          287.1152,
          0.04704704704704705
        ],
        [
          289.0945,
          0.042042042042042045
        ]
      ]
    }
  },
  "metrics": {
    "cosine_similarity": 0.9412847417548776,
    "entropy_similarity": 0.6221104979157452,
    "predicted_nonzero_bins": 100,
    "reference_nonzero_bins": 12
  }
}
```

</details>

## 实际评测结果

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | recorded model | cosine_similarity | 0.4625 |
| recorded evaluation | recorded model | entropy_similarity | 0.369847 |

样本量和候选池随每次运行记录。图可能展示单个分子，表格是来源实验的实际汇总，不能混为同一统计范围。

## 模型与方法

直接加载作者发布的冻结 checkpoint，调用 predict_mol。用我们测试 CSV 中的实测谱评分，并按谱图 ID、规范分子结构和加合物核对采集元数据。默认每个分子只取一条谱，避免多碰撞能重复分子主导平均值。

m/z 单位为 Da。用 0–1500 Da、150000 个 bin，bin 内 max pooling，保留预测强度最高的 100 个 bin，计算与全部实测峰的余弦相似度和熵相似度。缺少碰撞能或仪器时不补造条件，明确跳过。

## 复现方式

[Notebook with executed figures](../notebooks/ms-forward-iceberg.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks ms.forward.iceberg --limit 8 --output results/ms-forward-iceberg-new.json
```

## 边界与来源

该口径保留全部实测峰，不等同于只保留可指认峰的 benchmark。预训练使用 MassSpecGym，当前自建划分与权重训练集重叠尚未独立核验；旧权重的仪器/加合物训练覆盖元数据也不完整。

<details><summary>来源报告与 SHA-256 指纹</summary>

- [ms_iceberg_32_molecules_20261116.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/ms_iceberg_32_molecules_20261116.json) — SHA-256 `7b403aa40d8478ff3ff8ee93ed6bec4151493d88eb0d2521f037542889c443ee`

</details>


[Original model / 原模型](https://github.com/coleygroup/ms-pred) · [Model review / 模型检查](../model-audit.md)
