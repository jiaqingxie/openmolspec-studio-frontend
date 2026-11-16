# 多谱 → 结构（SpectraLLM）

按用户要求暂不推进。

## 模型与协议

已从默认评测任务中排除，显式调用也会跳过。

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

下方已有结果仅作历史诊断归档。

适配器：`unavailable`。数据域：`mixed`。指标字段：`exact_rate`、`valid_rate`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks multispectral.spectrallm.generation --limit 8 --output results/multispectral-spectrallm-generation.json
```

## 解释与限制

该任务不再下载模型、运行推理或训练。

## 已记录结果

```json
[
  {
    "status": "not_evaluated",
    "reason": "用户已明确暂不推进；历史结果仅作归档，不再运行。"
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/multispectral-spectrallm-generation.ipynb)

## 来源

[原始实现与发布](https://github.com/jiaqingxie/openmolspec-studio-frontend)
