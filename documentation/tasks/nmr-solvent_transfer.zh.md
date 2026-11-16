# H/C 跨溶剂位移 · 参考检索基线

用跨溶剂实验参考估计目标位移；当前提供无训练的参考检索基线。

## 当前结论

参考检索基线可执行，但 H 没有优于位移不变基线。仍需溶剂条件模型及独立配对数据。

## 输入是什么

| Field | Meaning |
| --- | --- |
| `structure / nucleus` | 分子连接结构及 1H 或 13C 核种。 |
| `solvents` | 显式指定源溶剂与目标溶剂，且参考库包含对应配对。 |
| `source_ppm` | 源溶剂下的实测位移（ppm）。 |

## 输出是什么

| Field | Meaning |
| --- | --- |
| `target_ppm / delta_ppm` | 从独立参考记录估计目标位移及跨溶剂差值。 |
| `reference` | 参考分子、谱图/原子 ID、Tanimoto 相似度及排除规则。 |

## 真实运行案例

下面展示记录中的第一例，不按结果好坏筛选。长数组预览会标明完整长度；完整数值可下载证据 JSON。参考标签与模型输入分开保留。

```json
{
  "input": {
    "nucleus": "1H",
    "source_ppm": 1.45,
    "source_solvent": "CD3OD",
    "target_solvent": "acetone-d6",
    "query_connectivity": "C1CCCCC1"
  },
  "output": {
    "source_ppm": 1.45,
    "predicted_target_ppm": 1.3799999999999997,
    "predicted_delta_ppm": -0.07000000000000028,
    "source_solvent": "CD3OD",
    "target_solvent": "acetone-d6",
    "nucleus": "1H",
    "query_connectivity": "C1CCCCC1",
    "reference": {
      "identity": "C1COCCO1",
      "molecule_id": "10016061",
      "atom_id": "10093018",
      "source_ppm": 3.66,
      "target_ppm": 3.59,
      "source_spectrum_ids": [
        "20197666"
      ],
      "target_spectrum_ids": [
        "20197080"
      ]
    },
    "tanimoto_similarity": 0.125,
    "same_connectivity_excluded": true,
    "method": "nearest_paired_experimental_reference_delta",
    "model_kind": "retrieval_baseline_not_neural_model",
    "query_molecule_id": "10811",
    "query_atom_id": "10046537",
    "target_reference_ppm": 1.43,
    "source_spectrum_ids": [
      "20197663"
    ],
    "target_spectrum_ids": [
      "20197659"
    ]
  }
}
```

![nmr.solvent_transfer actual results](../assets/gallery/nmr-solvent_transfer.png)

[SVG](../assets/gallery/nmr-solvent_transfer.svg) · [PNG](../assets/gallery/nmr-solvent_transfer.png) · [Full input/output JSON](../assets/examples/nmr-solvent_transfer.json)

## 实际评测结果

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | 13C | atoms | 140 |
| recorded evaluation | 13C | molecules | 13 |
| recorded evaluation | 13C | mae_ppm | 1.09429 |
| recorded evaluation | 13C | unchanged_shift_mae_ppm | 1.16371 |
| recorded evaluation | 13C | rmse_ppm | 1.90935 |
| recorded evaluation | 1H | atoms | 156 |
| recorded evaluation | 1H | molecules | 19 |
| recorded evaluation | 1H | mae_ppm | 0.137628 |
| recorded evaluation | 1H | unchanged_shift_mae_ppm | 0.135385 |
| recorded evaluation | 1H | rmse_ppm | 0.376179 |

样本量和候选池随每次运行记录。图可能展示单个分子，表格是来源实验的实际汇总，不能混为同一统计范围。

## 模型与方法

从 NMRShiftDB 审核通过的 H/C 一维数据中排除计算记录、混合/未知溶剂及重复测量冲突，按同一数据库原子配对。先按 Morgan 相似度选其他分子，再选最接近的源位移，加入该参考原子的实测溶剂差。排除查询分子及相同连接关系的所有立体异构体，不拟合参数。

已跑 32 个不同分子、296 个原子位移对；按 H/C 分别报告 MAE，并与源位移不变的基线比较。输出参考分子、原子/谱图 ID 和相似度。

## 复现方式

[Notebook with executed figures](../notebooks/nmr-solvent_transfer.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.solvent_transfer --limit 8 --output results/nmr-solvent_transfer-new.json
```

## 边界与来源

这不是神经网络溶剂模型，对两种核尚无稳定收益。参考库较小，温度、浓度及位移参考尚未统一核验；专用神经网络权重仍待取得。

- [solvent_transfer_reference32_20261116.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/solvent_transfer_reference32_20261116.json) — SHA-256 `7532dc2b785a93aa51323934bb748b768f1bfc7c820809bc2065d0840afc543f`

[Original model / 原模型](https://nmrshiftdb.nmr.uni-koeln.de/) · [Model review / 模型检查](../model-audit.md)
