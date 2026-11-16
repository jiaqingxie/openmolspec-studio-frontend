# 构象 → IR / Raman

从固定分子构象预测 IR/Raman，复用 Xinyu openSpec 项目的 Equiformer-v3 Hessian 和 response 权重。

## 模型与协议

坐标与参考谱必须来自同一 Gaussian 日志；检查 XYZ 加载后坐标不变，预测 Hessian/响应导数，再经振动模和展宽重建谱图。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "geometry": "Exact source Gaussian coordinates in Angstrom",
  "reference": "IR and Raman from the same Gaussian log",
  "example_logs": [
    "tests/fixtures/NISTIR-11730.log",
    "tests/fixtures/QM9-dsgdb9nsd_000001.log"
  ]
}
```

## 输出与指标

预测与参考均使用 400–4000 cm⁻¹ 的 1024 点轴和 min-max 强度归一化，分别报告 IR/Raman 的余弦相似度及强度 MAE。

适配器：`studio_vibrational_forward`。数据域：`computed`。指标字段：`ir_cosine_similarity`、`raman_cosine_similarity`、`ir_mae`、`raman_mae`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks vibrational.forward --limit 8 --output results/vibrational-forward.json
```

## 解释与限制

默认两个真实 Gaussian 日志仅用于配对运行检查，未审计其独立测试身份。不能用新生成的 RDKit 构象代替原参考几何后宣称是严格配对精度。

## 已记录结果

```json
[
  {
    "task": "vibrational.forward",
    "dataset_name": null,
    "status": "passed",
    "metrics": {
      "ir_cosine_similarity": 0.9775025844573975,
      "ir_mae": 0.005194379133172333,
      "raman_cosine_similarity": 0.9901942908763885,
      "raman_mae": 0.0016446748340968043
    },
    "examples": 2,
    "source_file": "vibrational_forward_paired_logs_20261116.json",
    "sample_limit": 2
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/vibrational-forward.ipynb)

## 来源

[原始实现与发布](https://github.com/X1nyuLu/openSpec-alpha)
