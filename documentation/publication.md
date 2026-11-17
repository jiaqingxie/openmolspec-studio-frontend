# Publication status

[English](https://openmolspec-10.readthedocs.io/en/latest/) · [简体中文](https://openmolspec-10.readthedocs.io/en/latest/zh/index.html)

Read the Docs builds `release/openmolspec-v1` with the root `.readthedocs.yaml`, Sphinx and the classic RTD theme. The site includes categorized tasks, a real-results gallery, dataset distributions, model review and 82 tutorials, including SDK inference, training preparation and theory simulations. Notebook publication never executes model code.

```bash
python scripts/build_bilingual_docs.py --check
python scripts/build_readthedocs.py --output site --strict
python scripts/publish_readthedocs.py --apply --project openmolspec-10 --wait 600
```

Publish only after pushing the corresponding Git commit. The publication script verifies the exact remote commit and finished RTD build; public pages are checked separately.
