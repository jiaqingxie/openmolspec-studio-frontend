# 文档维护与发布

本手册使用 MkDocs Material，通过 GitHub Actions 构建，再由 GitHub Pages 托管。Markdown 源文件在 `handbook/`，导航在 `mkdocs.yml`，不会混入旧核心文档中的训练操作。

## 本地预览

```bash
python -m pip install -r requirements-docs.txt
python scripts/render_task_catalog.py
python -m mkdocs serve
```

发布前检查：

```bash
python scripts/render_task_catalog.py --check
python -m mkdocs build --strict
python -m unittest discover -s tests -p test_benchmark_v1.py -v
```

任务定义位于 `openmolspec_bench/catalog.py`，由命令行和前端直接读取。手册任务表由脚本生成；CI 检查手册与目录一致。

## GitHub Pages

1. 将审阅通过的分支推送到 GitHub 并合入 `main`。
2. 仓库 Settings → Pages → Build and deployment → Source 选择 **GitHub Actions**。
3. 查看 Documentation workflow 的 build 与 deploy 结果。

PR 只构建文档，不部署。合入 `main` 后 workflow 使用 `pages: write` 和 `id-token: write` 上传并发布。只有 workflow 成功和实际 Pages 状态确认后，才能宣称上线。

参考 [GitHub 自定义 Pages workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) 和 [MkDocs 部署说明](https://www.mkdocs.org/user-guide/deploying-your-docs/)。
