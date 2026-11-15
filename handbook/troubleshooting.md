# 常见问题

## 缺少 checkpoint

前端仓库只含代码。设置 `OPENMOLSPEC_ROOT`（portable）和 `OPENMOLSPEC_BENCH_ROOT`（实验 NMR 工作区），或显式设置 H/C 两个 checkpoint 环境变量。工作台按需加载，各模型缺失不会阻止阅读任务页。

## `KeyError: formula` 或 `modality_mask`

旧的统一评分脚本曾创建缺字段的临时记录。新评测入口接受 `molecular_formula` 别名并从记录存在性补 mask；生成仍要求真实给定分子式。请使用统一入口，不直接运行旧的 `training/unified_metrics.py`。

## `SMILES exceeds target capacity`

原有 byte 分子编码器有长度上限。批量检索会排除超长结构、记录数量，并补取后续合格记录。交互检索请缩小候选结构或改用经过验证的兼容 checkpoint，不截断 SMILES。

## `No such device` 打开 LMDB

一些共享文件系统不支持 mmap。基准入口会自动镜像到 `/tmp`；若磁盘不足，清理不再使用的 `/tmp/openmolspec-bench-lmdb/` 缓存，或提供位于本地盘的数据。

## Gap 误差异常

先核对参考值单位。默认 Vib2Mol 数据保留 Hartree，而模型输出为 eV。自定义数据需 `units.gap` 或 `--gap-unit`。不能直接拿 0.15 Hartree 与 4 eV 相减。

## CUDA 预测 pickle 在 CPU 报反序列化错误

统一正向评分入口使用 CPU Unpickler，把 PyTorch storage 映射到 CPU，不需要重新运行预测或启动训练。仍然只应读取可信的本地预测文件。

## 文档无法访问或 GitHub 同步失败

文档要先推送，再在仓库 Settings → Pages 把 Source 设为 GitHub Actions；主分支推送会触发文档构建与发布。`mkdocs build --strict` 可本地检查。网络或认证失败时，本地代码和文档仍然有效，但不能报告已同步或已发布。

## 小样本得分低或不同任务样本数不同

本次关注流程能否跑通。按核可用性、重复结构和编码容量筛选后，候选集合可能不同。请检查 `sample_ids`、`selection`、`candidate_pool`，不要仅比较百分比。
