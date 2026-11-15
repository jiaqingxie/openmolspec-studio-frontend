# 结构 → 19F 峰列表

检查已有 19F 预测与实验参考的配对、位移参考和适用域，不拟合新的校正参数。

## 模型与协议

旧预测对应的 LMDB 后来发生变化，保存的 target 与当前标签不一致，旧 MAE 已撤回。冻结权重对带哈希的同一份输入重新推理，可以修复样本配对。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "smiles": "CCO",
  "formula": "C2H6O",
  "h_nmr": [
    {
      "type": "1H NMR",
      "chemical_shift": "1.20 (t, 3H), 3.65 (q, 2H)"
    }
  ],
  "c_nmr": [
    {
      "type": "13C NMR",
      "chemical_shift": "18.2, 58.3"
    }
  ],
  "modality_mask": [
    1,
    1
  ]
}
```

## 输出与指标

配对修复后的固相 checkpoint 在实验溶液数据上误差仍很大，且位移参考兼容性未确认，仅保留为诊断，不作为正式溶液模型成绩。

适配器：`nmrnet_hetero_predictions`。数据域：`experimental`。指标字段：`mae_ppm`、`rmse_ppm`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.19F --limit 8 --output results/nmr-forward-19F.json
```

## 解释与限制

需要兼容的现成溶液 checkpoint，或作者明确提供的参考转换。不得对测试标签拟合一个偏移来降低误差，也不启动重新训练。

## 已记录结果

```json
[
  {
    "task": "nmr.forward.19F",
    "dataset_name": null,
    "status": "skipped",
    "reason": "F/P prediction-label alignment is verified, but the available solid-state checkpoint has no verified solution-shift reference. A compatible released checkpoint or documented reference conversion is required; no training or fitted calibration is performed. Use --allow-cross-domain-diagnostic only for a labeled diagnostic report.",
    "source_file": "fp_primary_score_gate_20261116.json",
    "sample_limit": 32
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-forward-19F.ipynb)

## 来源

[原始实现与发布](https://github.com/Colin-Jay/NMRNet)
