# IR + Raman + H/C NMR → HOMO–LUMO gap

由谱图预测 HOMO–LUMO gap，使用已有共享谱学 Transformer，输出 eV。

## 模型与协议

该 checkpoint 的训练模态是 IR+Raman+H/C。完整输入配置提供四种谱；IR-only、Raman-only 和 IR+Raman 是同一模型的缺通道消融，不是独立训练的单谱模型。

## 输入与示例

以下仅展示输入格式，不是实测谱或精度结果。

```json
{
  "ir": "1024 min-max-normalized intensities",
  "raman": "1024 min-max-normalized intensities",
  "wavenumber_cm1": [
    400,
    4000
  ],
  "nmr_h_shifts_ppm": [
    1.2,
    3.65
  ],
  "nmr_c_shifts_ppm": [
    18.2,
    58.3
  ],
  "nmr_reference_id": "must match checkpoint",
  "formula": "not supplied to Vib2Mol"
}
```

## 输出与指标

原 Vib2Mol LMDB 的 gap 为 Hartree，仅乘一次 27.211386245988 转 eV。模型输出按 checkpoint 保存的均值和标准差反归一化，H/C 使用权重内的中心、尺度与参考 ID。报告 MAE/RMSE，并在相同样本上报告训练均值常量基线。

适配器：`studio_gap`。数据域：`computed`。指标字段：`mae_ev`、`rmse_ev`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks vibrational.gap.ir_raman_hc --limit 8 --output results/vibrational-gap-ir_raman_hc.json
```

## 解释与限制

按文件顺序的首批样本可能来源偏倚，较广的检查使用固定种子的 reservoir 抽样。缺通道与完整输入的成绩必须分开解释。

## 已记录结果

```json
[
  {
    "task": "vibrational.gap.ir_raman_hc",
    "dataset_name": null,
    "status": "passed",
    "metrics": {
      "mae_ev": 0.1314457535089349,
      "rmse_ev": 0.20596364382966384,
      "examples": 128
    },
    "given_nmr": true,
    "source_counts": {
      "ZINCV2": 58,
      "SDBS": 4,
      "PCQM4MV2": 20,
      "WILEYIR": 9,
      "ZINCV1": 12,
      "RXN": 6,
      "QM9": 18,
      "WILEYRAMAN": 1
    },
    "selection": {
      "read": 20390,
      "duplicate_structure": 3662,
      "eligible_distinct_structures": 16728,
      "selected": 128
    },
    "sampling": "reservoir",
    "seed": 42,
    "training_mean_baseline": {
      "constant_ev": 5.645122750946045,
      "mae_ev": 0.8999401965027582,
      "rmse_ev": 1.0696170714220543,
      "examples": 128
    },
    "source_file": "gap_protocol_random128_20261116.json",
    "sample_limit": 128
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/vibrational-gap-ir_raman_hc.ipynb)

## 来源

[原始实现与发布](https://github.com/X1nyuLu/openSpec-alpha)
