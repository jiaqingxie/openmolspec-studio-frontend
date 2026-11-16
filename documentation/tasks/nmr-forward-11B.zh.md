# 结构 → 11B 峰列表

用已训练的液相 All-nucleus NMRNet 对 11B 验证数据做冻结推理。

## 当前结论

仅作诊断：MAE 8.68 ppm，相关系数 0.217。区分能力弱、覆盖未核验；数据修复后可考虑 B 专项适配。

## 输入是什么

| Field | Meaning |
| --- | --- |
| `smiles / geometry` | 有效分子结构及相容的三维构象，必须保留原子顺序。 |
| `nucleus` | 11B，权重必须覆盖该核种。 |
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
    "smiles": "Cc1cnc([B-]23OC(=O)C[C+]2CC(=O)O3)o1",
    "atom_indices": [
      5
    ]
  },
  "output": {
    "prediction_ppm": [
      26.116743087768555
    ]
  },
  "reference": {
    "ppm": [
      7.5
    ]
  }
}
```

![nmr.forward.11B actual results](../assets/gallery/nmr-forward-11B.png)

[SVG](../assets/gallery/nmr-forward-11B.svg) · [PNG](../assets/gallery/nmr-forward-11B.png) · [Full input/output JSON](../assets/examples/nmr-forward-11B.json)

## 实际评测结果

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | recorded model | mae_ppm | 8.68453 |
| recorded evaluation | recorded model | rmse_ppm | 12.4365 |
| recorded evaluation | recorded model | molecules | 32 |
| recorded evaluation | recorded model | atoms | 32 |

样本量和候选池随每次运行记录。图可能展示单个分子，表格是来源实验的实际汇总，不能混为同一统计范围。

## 模型与方法

B、Si 各完成 32 个不同分子，复用保存的 scaler，检查完整加载全部权重，并通过样本 ID 核对原子标签。证据为 results/bsi_frozen_diagnostic_20261116.json；复现脚本为 scripts/run_frozen_bsi_diagnostic.py。

报告逐原子 MAE/RMSE，单位 ppm；这是诊断值，不是峰匹配分数或已验证的独立测试成绩。

## 复现方式

[Notebook with executed figures](../notebooks/nmr-forward-11B.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.11B --limit 8 --output results/nmr-forward-11B-new.json
```

## 边界与来源

各核训练覆盖、训练重叠及实验原子指认来源尚未核实，且该模型不输入溶剂。正式评分仍停用；继续核查 NMRNet++ 的 B/Si 专用权重，不拟合任何校正。

- [bsi_frozen_diagnostic_20261116.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/bsi_frozen_diagnostic_20261116.json) — SHA-256 `0f7c1f6c9eae12e644753581f785d76b1824f8311d5fccc7ae4afb98d19c65e6`

[Original model / 原模型](https://github.com/Colin-Jay/NMRNet) · [Model review / 模型检查](../model-audit.md)
