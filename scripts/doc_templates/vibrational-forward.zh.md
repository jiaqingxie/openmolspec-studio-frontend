## QM9S 参考条件

在 337 种验证分子上分别为 IR 和拉曼选择强度计算方式、频率修正系数与展宽。下表在另 303 种分子上评测，每个分子的权重相同。全部 640 种分子来自 OpenMolSpec 为评测留出的 QM9 结构。参考谱由 QM9S 同一优化构型的 Hessian 与响应导数计算。

| 通道 | 原模型 → 入选模型的余弦相似度 | 余弦提升的配对 95% 区间 | 原模型 → 入选模型的强度 MAE |
| --- | ---: | ---: | ---: |
| IR | 0.9621 → 0.9835 | [+0.0192, +0.0236] | 0.0100 → 0.0067 |
| 拉曼 | 0.9125 → 0.9850 | [+0.0682, +0.0764] | 0.0198 → 0.0070 |

IR 采用逐振动模式强度，频率系数为 0.9975，高斯展宽 σ 为 2 cm⁻¹。 拉曼 采用逐振动模式强度，频率系数为 0.9975，高斯展宽 σ 为 2 cm⁻¹。

QM9S 模式适用于仅含 H/C/N/O/F 且至多有 9 个重原子的分子。每个通道输出 500–4,000 cm⁻¹ 区间的 997 个归一化强度。计算参考谱采用 0.965 谐振频率系数和 10 cm⁻¹ 洛伦兹半高半宽，拉曼条件为 532 nm、298 K。基准使用原始优化坐标，网页会从 SMILES 生成坐标。网页也提供原始 openSpec 的 1,024 点模式。

[在线预测](https://jiaqingxie.github.io/openmolspec.github.io/#tool-ir-raman) · [下载配对评测集与 SDK](https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/vibrational-forward-v2/openmolspec-qm9s.zip)

解压后安装包内的 wheel、NumPy 和 SciPy，并在解压目录运行以下命令。安装原始模型运行环境和权重后，可加 `--qm9s-fresh --portable-root /path/to/openmolspec-studio-portable`，从存档的坐标重新运行四个网络。

```bash
python -m openmolspec_bench run --tasks vibrational.forward --qm9s-bundle benchmark --limit 10000 --output qm9s-result.json
```

压缩包收录 Zou 等人发布的 QM9S 的转换子集，包括优化构型、重建的参考谱及 OpenMolSpec 输出。[QM9S 数据集](https://figshare.com/articles/dataset/QM9S_dataset/24235333) · [原论文](https://doi.org/10.1038/s43588-023-00550-y) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
