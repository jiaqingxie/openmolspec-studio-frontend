# IR / Raman → SMILES

使用 Xinyu 保存的 Vib2Mol 模型完成结构检索、SMILES 生成或候选重排。完整输入为 IR+Raman+H/C；仅 IR/Raman 的路径作为缺核消融。

## 模型与协议

复用原实现的 encode_spectra、canonical/unique_candidates 与 rerank_candidates。生成默认 beam=10、最大长度 300；先移除无效和重复规范结构，再对前 10 个候选用 ITM 正类概率重排。不提供分子式，也不使用近邻缓存回放。

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

检索报告双向 Recall@1/5/10、MRR 和候选池大小。生成同时报告原始 beam 的有效率、规范去重后的 top-1/3/5/10 及重排后的 top-k；重排始终使用明确的候选列表。

适配器：`vib2mol_generation`。数据域：`computed`。指标字段：`exact_rate`、`valid_rate`。

## 运行推理或评分

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks vibrational.generation --limit 8 --output results/vibrational-generation.json
```

## 解释与限制

生成与重排 checkpoint 的 H/C 参考和归一化缓冲必须一致。小候选池可能让检索分数偏高，必须公布样本 ID、种子和来源组成。

## 已记录结果

```json
[
  {
    "status": "not_evaluated",
    "reason": "直接运行已有 Vib2Mol beam 解码，不使用缓存或近邻回放；原始 beam top-1，不进行分子式重排。"
  }
]
```

## Notebook

[打开可运行 notebook](../notebooks/vibrational-generation.ipynb)

## 来源

[原始实现与发布](https://github.com/X1nyuLu/openSpec-alpha)
