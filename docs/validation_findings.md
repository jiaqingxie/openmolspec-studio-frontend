# OpenSpec Validation Findings

记录 Validation 分析中发现的数据质量与解析问题，用于 Scientific Data 的
Technical Validation 章节。所有结论均基于当前发布集合（`artifacts/processed/openspec.pickle`，
1,249,283 条频率成功记录）。

## 1. QM9 / ZINCV1 的热化学性质（U/H/G）缺失 —— 解析器缺陷

**状态：代码已修复，数据未重新生成（等待决策）。**

### 现象

- 内部 QC 中 `NONFINITE_U/H/G` 共 137,196 条记录：
  - QM9：133,434 条（100%）
  - ZINCV1：3,761 条（6.6%）
  - ZINCV2：1 条
- 这些记录在 `artifacts/processed/openspec.pickle` 中 U/H/G = NaN，导致 `qc_pass` 从
  1,249,283 降到 1,112,081。

### 根因（已用源 log 验证）

1. 这些来源的 Gaussian log **没有**在 archive 段输出 `ETot/HTot/GTot`
   标签（archive 只含 `HF\ZeroPoint\Thermal`）；抽样 20/20 条 QM9 log
   全部如此，ZINCV1 部分如此。
2. 但 log 正文打印了完整热化学量（QM9 抽样 20/20 全部存在）：
   ```
   Sum of electronic and thermal Energies=      -40.488438   # U
   Sum of electronic and thermal Enthalpies=    -40.487493   # H
   Sum of electronic and thermal Free Energies= -40.510970   # G
   ```
3. 旧版解析器只从 archive 的 `ETot/HTot/GTot` 提取 U/H/G → QM9 全部
   丢字段；`pd.DataFrame` 列对齐时填 NaN。
4. 对比：NISTIR 等来源的 log archive **有** `ETot/HTot/GTot`，U/H/G 正常。

### 修复

`src/openmolspec/parsing/gaussian.py` 的 `_parse_archive_properties` 增加文本行 fallback：
archive 标签缺失时读取 "Sum of electronic and thermal ..." 行。测试见
`tests/test_parser_thermal.py`（用真实 QM9 log 作 fixture，3 个断言全过）。

### 对发布数据的影响（待决策）

- 重新解析受影响记录（约 137k 条 log）并回填 `artifacts/processed/openspec.pickle` 后，
  `qc_pass` 预计升至 ~1,249,232（剩余真异常仅 51 条：7 条频率/光谱
  非法、5 条 Hessian shape、3 条 ZPVE、1 条 polar 等）。
- 已生成 pickle 的 U/H/G 仍是 NaN；重新生成约需 1–2 小时（仅重解析
  受影响记录）。

## 2. 其余异常记录（真异常，51 条）

| 错误类型 | 条数 |
|---|---|
| INVALID_FREQUENCIES / NONFINITE_FREQ / INVALID_IR/RAMAN_SPECTRUM_SHAPE | 7 |
| INVALID_HESSIAN_SHAPE | 5 |
| NONFINITE_ZPVE | 3 |
| NONFINITE_POLAR | 1 |
| 合计（去重后） | ~51 |

这些是真实的解析/数据异常，不在发布集合中。

## 3. 复现命令

```bash
# 重新生成全部 validation 报告（复用缓存，约 5 分钟）
python -m openmolspec.quality.stats --output reports/publication
```
