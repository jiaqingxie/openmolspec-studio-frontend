# 发布状态

[English](https://openmolspec-10.readthedocs.io/en/latest/) · [简体中文](https://openmolspec-10.readthedocs.io/en/latest/zh/index.html)

Read the Docs 使用根目录 `.readthedocs.yaml` 构建 `release/openmolspec-v1` 分支，采用 Sphinx 与经典 RTD 主题。站点包括分类任务、真实结果图册、数据分布、模型与训练说明及 82 份教程（含暂停任务说明和数据分布 notebook）。发布构建不执行模型代码。

```bash
python scripts/build_bilingual_docs.py --check
python scripts/build_readthedocs.py --output site --strict
python scripts/publish_readthedocs.py --apply --project openmolspec-10 --wait 600
```

先推送对应 Git 提交，再发布。发布脚本检查远端精确提交与完成的 RTD 构建，公开页面另行验证。
