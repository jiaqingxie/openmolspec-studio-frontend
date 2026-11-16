# 发布状态

文档已发布到 [Read the Docs](https://openmolspec-10.readthedocs.io/en/latest/)，可直接打开[中文版](https://openmolspec-10.readthedocs.io/en/latest/zh/index.html)。站点包含 150 个内容页面，其中包括 68 个已执行的 notebook 预览及下载；每页提供语言切换。首次验证成功的托管构建为 [35915674](https://app.readthedocs.org/projects/openmolspec-10/builds/35915674/)，对应发布提交 `5e8ce72655105f4a6cd61859c9c98c0574d36955`。

Read the Docs 使用仓库根目录 `.readthedocs.yaml` 构建 `release/openmolspec-v1` 分支。安装 `requirements-docs.txt` 后，本地、CI 和托管构建共用 `python scripts/build_readthedocs.py --output site --strict`。前端 Full documentation 默认跳转至实际文档地址，也可通过 `OPENMOLSPEC_DOCS_URL` 覆盖。推送对应提交后，可用 `python scripts/publish_readthedocs.py --apply --project openmolspec-10 --wait 600` 触发发布更新。

站点使用 Sphinx 与经典 `sphinx_rtd_theme`，提供左侧层级目录、全文搜索、面包屑和上下篇导航。英文和中文拥有独立搜索索引。MyST-NB 仅渲染已保存的 notebook 输出，文档构建始终禁用代码执行。
