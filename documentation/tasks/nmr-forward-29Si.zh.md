# 结构 → 29Si 峰列表

由分子结构预测 29Si 化学位移，已有兼容权重时进行冻结推理或已有预测评分。

## 模型与协议

H/C 读取 NMRNet、NMRNet++ 的预测及对应元数据；未指认实验峰用最小绝对误差匹配，并保留峰数和覆盖率诊断。B/Si 暂无已验证的兼容权重/预测对。

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

位移和误差单位均为 ppm。按分子等权计算匹配峰 MAE/RMSE，必须同时报告匹配比例与峰数误差，因为匹配误差本身不惩罚全部缺失峰或额外峰。

适配器：`unavailable`。数据域：`experimental`。指标字段：`matched_peak_mae_ppm`、`matched_peak_rmse_ppm`、`peak_count_mae`、`matched_fraction`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.forward.29Si --limit 8 --output results/nmr-forward-29Si.json
```

## 解释与限制

峰匹配误差不是逐原子指认准确率。缺少 B/Si 兼容权重时明确跳过，不为补任务重新训练模型头。

## 已记录结果

```json
[
  {
    "status": "not_evaluated",
    "reason": "保留六核任务定义；尚未验证可用于此实验域的 checkpoint 和预测文件。"
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-forward-29Si.ipynb)

## 来源

[原始实现与发布](https://github.com/Colin-Jay/NMRNet)
