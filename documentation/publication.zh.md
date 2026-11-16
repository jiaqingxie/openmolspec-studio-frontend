# 发布状态

仓库提供 `.readthedocs.yaml`。安装 `requirements-docs.txt` 后用 `python scripts/build_readthedocs.py --output site --strict` 构建。本地、CI 和 Read the Docs 使用同一构建脚本，已生成并验证 150 个 HTML 页面、68 个 notebook 预览、语言切换与下载链接。目前尚无已确认上线的 Read the Docs URL；只有项目导入和托管构建成功后才会发布实际网址。

部署后在前端设置 `OPENMOLSPEC_DOCS_URL`。当前环境的网络代理无法解析，GitHub 推送、依赖下载和 Read the Docs 账户访问仍受外部条件限制。
