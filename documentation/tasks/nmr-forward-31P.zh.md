# 结构 → 31P 峰列表

检查已有 31P 预测与实验参考的配对、位移参考和适用域，不拟合新的校正参数。

## 当前结论

当前固相权重没有验证为溶液位移模型。优先解决数据域与参考兼容，不能直接归因于需要微调。

## 输入是什么

| Field | Meaning |
| --- | --- |
| `smiles / geometry` | 有效分子结构及相容的三维构象，必须保留原子顺序。 |
| `nucleus` | 31P，权重必须覆盖该核种。 |
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
    "smiles": "COc1ccc(P(=O)(CCCc2ccccc2)OCC)cc1",
    "nucleus": "P",
    "atom_indices": [
      6
    ]
  },
  "output": {
    "prediction_ppm": 246.23046875
  },
  "reference": {
    "ppm": 44.90999984741211
  }
}
```

![nmr.forward.31P actual results](../assets/gallery/nmr-forward-31P.png)

[SVG](../assets/gallery/nmr-forward-31P.svg) · [PNG](../assets/gallery/nmr-forward-31P.png) · [Full input/output JSON](../assets/examples/nmr-forward-31P.json)

## 实际评测结果

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | recorded model | mae_ppm | 226.449 |
| recorded evaluation | recorded model | rmse_ppm | 237.252 |
| recorded evaluation | recorded model | examples | 32 |

样本量和候选池随每次运行记录。图可能展示单个分子，表格是来源实验的实际汇总，不能混为同一统计范围。

## 模型与方法

旧预测对应的 LMDB 后来发生变化，保存的 target 与当前标签不一致，旧 MAE 已撤回。冻结权重对带哈希的同一份输入重新推理，可以修复样本配对。

配对修复后的固相 checkpoint 在实验溶液数据上误差仍很大，且位移参考兼容性未确认，仅保留为诊断，不作为正式溶液模型成绩。

## 复现方式

[Notebook with executed figures](../notebooks/nmr-forward-31P.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.31P --limit 8 --output results/nmr-forward-31P-new.json
```

## 边界与来源

需要兼容的现成溶液 checkpoint，或作者明确提供的参考转换。不得对测试标签拟合一个偏移来降低误差，也不启动重新训练。

- [fp_frozen_fresh_diagnostic_20261115.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/fp_frozen_fresh_diagnostic_20261115.json) — SHA-256 `7a44203bd5826e778a9006edd92dee0ec71e47930c2a980f6082313974c68475`

[Original model / 原模型](https://github.com/Colin-Jay/NMRNet) · [Model review / 模型检查](../model-audit.md)
