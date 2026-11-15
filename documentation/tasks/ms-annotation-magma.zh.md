# MS/MS 峰 → MAGMa 候选碎片标注

从已知分子枚举候选碎片，用质量误差匹配实测 MS/MS 谱峰，无需模型训练。

## 模型与协议

保留 MAGMa v8 原来的规范化和默认 10 ppm 容差。片段原子编号按引擎实际使用的 engine_smiles 解释，逐片检查原子元素计数、原子范围和键连接；不能直接套到输入 SMILES 的原子顺序。

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

报告匹配谱峰比例、成功标注谱图数及检查的碎片数。候选片段和根到片段路径是算法解释，不能当作实验确认的唯一碎裂机制。

适配器：`magma_algorithm`。数据域：`experimental`。指标字段：`matched_peak_fraction`、`checked_fragments`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks ms.annotation.magma --limit 8 --output results/ms-annotation-magma.json
```

## 解释与限制

氢迁移、图深度、断键数等字段沿用原算法语义。默认规范化会改变原子顺序，必须保留 engine_smiles；不擅自改动枚举和匹配算法。

## 已记录结果

```json
[
  {
    "task": "ms.annotation.magma",
    "metrics": {
      "matched_peak_fraction": 0.5681818181818182,
      "annotated_spectra": 2,
      "checked_fragments": 1534
    },
    "counts": {
      "passed": 2
    },
    "selection": {
      "split_rows_examined": 2040,
      "exceeds_heavy_atom_limit": 2005,
      "duplicate_molecule": 33,
      "missing_acquisition_metadata": 0
    },
    "source_file": "magma_real_test_verified_20261115.json",
    "sample_limit": 2
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/ms-annotation-magma.ipynb)

## 来源

[原始实现与发布](https://github.com/Dsadd4/MassSpecGym-MAGMA-annotation)
