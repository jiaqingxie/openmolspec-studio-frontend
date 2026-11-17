# OpenMolSpec project website

Public URL: https://jiaqingxie.github.io/openmolspec.github.io/

The project portal uses static HTML, CSS and JavaScript. It includes the full
bilingual Sphinx manual at `docs/` and displays figures generated from recorded
model runs and complete-file data audits.

Build from the release repository after regenerating documentation figures:

```bash
python scripts/build_readthedocs.py --output .runtime/manual-site-v1 --strict
python scripts/build_project_site.py --output .runtime/github-pages-v1 --manual .runtime/manual-site-v1
python -m http.server 8769 --directory .runtime
```

Preview `http://localhost:8769/github-pages-v1/`. Publish the generated directory
to the `main` branch of `jiaqingxie/openmolspec.github.io`; GitHub Pages serves its
repository root. Keep `.nojekyll`. Relative asset paths support the project URL.

Counts and figure links are generated from the versioned evidence reports.
Model inference and training use the Python package and documented runtimes.
