# IR / Raman → SMILES

使用 Xinyu 保存的 Vib2Mol 模型完成结构检索、SMILES 生成或候选重排。完整输入为 IR+Raman+H/C；仅 IR/Raman 的路径作为缺核消融。

## 当前结论

这是四模态权重的缺通道消融。不能当作独立 IR/Raman 专用模型；需相容权重或另行规划适配。

## 输入是什么

| Field | Meaning |
| --- | --- |
| `IR / Raman` | 每个可见通道 1024 个强度点，按 400→4000 cm⁻¹ 排列，并采用 checkpoint 的归一化。 |
| `missing channels` | 此路径省略四模态权重的部分通道，属于消融，不是独立训练的专用模型。 |

## 输出是什么

| Field | Meaning |
| --- | --- |
| `SMILES candidates` | 解码后有效、规范化且去重的结构；完整输入路径使用 beam 10 和 ITM 重排。 |
| `top-k` | 分别报告生成与重排后的 top-k；不提供分子式。 |

## 真实运行案例

下面展示记录中的第一例，不按结果好坏筛选。长数组预览会标明完整长度；完整数值可下载证据 JSON。参考标签与模型输入分开保留。

```json
{
  "reference": "CCCCc1cc2ccccc2c(OCCN(C)C)n1",
  "raw_top_1": "N1=NN2N=NN=C2N1",
  "canonical_top_1": "n1nc2[nH]nnn2n1",
  "input": {
    "ir": {
      "length": 1024,
      "first_values": [
        0.012721044011414051,
        0.012162876315414906,
        0.011645566672086716,
        0.010846862569451332
      ]
    },
    "raman": {
      "length": 1024,
      "first_values": [
        0.026861174032092094,
        0.022829052060842514,
        0.02229130268096924,
        0.0217174980789423
      ]
    }
  }
}
```

![vibrational.generation actual results](../assets/gallery/vibrational-generation.png)

[SVG](../assets/gallery/vibrational-generation.svg) · [PNG](../assets/gallery/vibrational-generation.png) · [Full input/output JSON](../assets/examples/vibrational-generation.json)

## 实际评测结果

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded sample | recorded model | valid_rate | 1 |
| recorded sample | recorded model | exact_rate | 0 |
| recorded sample | recorded model | examples | 4 |

样本量和候选池随每次运行记录。图可能展示单个分子，表格是来源实验的实际汇总，不能混为同一统计范围。

## 模型与方法

复用原实现的 encode_spectra、canonical/unique_candidates 与 rerank_candidates。生成默认 beam=10、最大长度 300；先移除无效和重复规范结构，再对前 10 个候选用 ITM 正类概率重排。不提供分子式，也不使用近邻缓存回放。

检索报告双向 Recall@1/5/10、MRR 和候选池大小。生成同时报告原始 beam 的有效率、规范去重后的 top-1/3/5/10 及重排后的 top-k；重排始终使用明确的候选列表。

## 复现方式

[Notebook with executed figures](../notebooks/vibrational-generation.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks vibrational.generation --limit 8 --output results/vibrational-generation-new.json
```

## 边界与来源

生成与重排 checkpoint 的 H/C 参考和归一化缓冲必须一致。小候选池可能让检索分数偏高，必须公布样本 ID、种子和来源组成。

- [smoke_vib2mol_20261115.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/smoke_vib2mol_20261115.json) — SHA-256 `2d847121c398071c68040623482a51118d1e20932779247b2eb72e071b8a8ae4`

[Original model / 原模型](https://github.com/X1nyuLu/openSpec-alpha) · [Model review / 模型检查](../model-audit.md)
