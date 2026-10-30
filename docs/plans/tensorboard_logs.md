# TensorBoard 日志入口

2026-09-14 整理后的本地入口：

```bash
tensorboard --logdir reports/tensorboard-current --port 6006
```

入口使用相对目录软链接，按任务 / variant / 数据规模 / seed / run 时间戳分组。
训练仍写入原来的 run 目录，软链接实时读取，不复制或移动正在写入的事件文件。
不要用仓库根目录作为 logdir，否则历史归档和 upstream 示例也会被扫描。

## 保留范围

- 200k：H/C NMR 三属性模型、Vib2Mol、Hi、Hij、dedipole、depolar。
- 1M：已使用 312,500-step 调度的 Hi、Hij。
- 共 10 个实验。当前失败或停滞实验也保留，便于诊断；保留不代表运行健康。
- Vib2Mol 链接覆盖该实验的内部 runs 目录，后续 generation 阶段日志也可被发现。

## 移出的过渡日志

以下 3 份事件文件已移动到 `artifacts/retired-tensorboard-20260914/`，
保留原相对路径，可按原路径恢复：

- depolar：`2026-09-09-11-09-800a07`（旧 epoch 调度）。
- dedipole：`2026-09-09-11-10-5cd585`（旧 epoch 调度）。
- Hessian smoke：`2026-09-11-03-02-6fa283`。

没有删除 checkpoint、训练文本日志或实验配置。此前 `artifacts/retired-*`
中的历史日志保持归档；upstream 自带示例不修改，也不纳入当前入口。
入口与归档均已被现有 `reports/`、`artifacts/` ignore 规则排除。

## 后续实验

这是本次已有实验的索引，不会自动收录新的外层 run。新实验启动后，可添加目录链接：

```bash
ln -s /absolute/path/to/new/run/artifacts/tensorboard \
  reports/tensorboard-current/new-experiment-name
```

Vib2Mol 的链接目标改为该 run 的 `artifacts/vib2mol/runs`。
同一次实验原目录内的新事件文件可自动被发现，无需重新链接。
