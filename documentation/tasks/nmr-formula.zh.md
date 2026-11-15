# 谱图 → 分子式

现有生成器使用给定分子式；不将其计为分子式预测器。

## 模型与协议

本任务需符合输入定义的现成权重、参考数据与适配器。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "h_nmr_ppm": [
    1.2,
    3.65
  ],
  "c_nmr_ppm": [
    18.2,
    58.3
  ],
  "formula_provided": false
}
```

## 输出与指标

缺少必需条件时不产生占位分数。

适配器：`unavailable`。数据域：`experimental`。指标字段：`formula_exact_rate`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.formula --limit 8 --output results/nmr-formula.json
```

## 解释与限制

保持明确的待接入状态；如果必须重新训练才能完成，则按用户要求跳过。

## 已记录结果

```json
[
  {
    "status": "not_evaluated",
    "reason": "现有生成器使用给定分子式；不将其计为分子式预测器。"
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/nmr-formula.ipynb)

## 来源

[原始实现与发布](https://github.com/jiaqingxie/openmolspec-studio-frontend)
