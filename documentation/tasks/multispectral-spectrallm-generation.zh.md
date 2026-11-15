# 多谱 → 结构（SpectraLLM）

官方新权重为 32B；当前本地仅有旧 7B adapter 且其指定基座缺失。需下载完整官方权重或提供匹配基座，不进行训练。

## 模型与协议

本任务需符合输入定义的现成权重、参考数据与适配器。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "ir": "1024 intensities on the documented axis",
  "raman": "1024 intensities on the same axis",
  "h_nmr_ppm": [
    1.2,
    3.65
  ],
  "c_nmr_ppm": [
    18.2,
    58.3
  ],
  "prompt_format": "must follow the released model's preprocessing"
}
```

## 输出与指标

缺少必需条件时不产生占位分数。

适配器：`unavailable`。数据域：`mixed`。指标字段：`exact_rate`、`valid_rate`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks multispectral.spectrallm.generation --limit 8 --output results/multispectral-spectrallm-generation.json
```

## 解释与限制

保持明确的待接入状态；如果必须重新训练才能完成，则按用户要求跳过。

## 已记录结果

```json
[
  {
    "status": "not_evaluated",
    "reason": "官方新权重为 32B；当前本地仅有旧 7B adapter 且其指定基座缺失。需下载完整官方权重或提供匹配基座，不进行训练。"
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/multispectral-spectrallm-generation.ipynb)

## 来源

[原始实现与发布](https://github.com/OPilgrim/SpectraLLM)
