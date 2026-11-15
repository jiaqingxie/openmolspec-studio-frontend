# 分子 → MS/MS（ICEBERG）

给定分子结构、加合物、碰撞能和仪器，预测 MS/MS 的 m/z–强度峰列表。

## 模型与协议

直接加载作者发布的冻结 checkpoint，调用 predict_mol。用我们测试 CSV 中的实测谱评分，并按谱图 ID、规范分子结构和加合物核对采集元数据。默认每个分子只取一条谱，避免多碰撞能重复分子主导平均值。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "spec_id": "example-input-only",
  "smiles": "CCO",
  "adduct": "[M+H]+",
  "collision_energy": 20,
  "instrument": "Orbitrap",
  "precursor_mz": 47.0491,
  "peaks": [
    [
      31.0178,
      1.0
    ],
    [
      47.0491,
      0.4
    ]
  ]
}
```

## 输出与指标

m/z 单位为 Da。用 0–1500 Da、150000 个 bin，bin 内 max pooling，保留预测强度最高的 100 个 bin，计算与全部实测峰的余弦相似度和熵相似度。缺少碰撞能或仪器时不补造条件，明确跳过。

适配器：`ms_pretrained_iceberg`。数据域：`experimental`。指标字段：`cosine_similarity`、`entropy_similarity`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks ms.forward.iceberg --limit 8 --output results/ms-forward-iceberg.json
```

## 解释与限制

该口径保留全部实测峰，不等同于只保留可指认峰的 benchmark。预训练使用 MassSpecGym，当前自建划分与权重训练集重叠尚未独立核验；旧权重的仪器/加合物训练覆盖元数据也不完整。

## 已记录结果

```json
[
  {
    "task": "ms.forward.iceberg",
    "metrics": {
      "cosine_similarity": 0.4624995623966228,
      "entropy_similarity": 0.3698472199736009
    },
    "counts": {
      "passed": 31,
      "skipped": 1
    },
    "selection": {
      "split_rows_examined": 1444,
      "exceeds_heavy_atom_limit": 473,
      "duplicate_molecule": 939,
      "missing_acquisition_metadata": 0
    },
    "sampling": "first_real_test_records_with_at_most_40_heavy_atoms",
    "unique_molecules": 32,
    "source_file": "ms_iceberg_32_molecules_20261116.json",
    "sample_limit": 32
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/ms-forward-iceberg.ipynb)

## 来源

[原始实现与发布](https://github.com/coleygroup/ms-pred)
