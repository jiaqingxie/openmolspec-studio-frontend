## Released solution carbon model

The predictor averages the atomic shifts from five NMRNet++ checkpoints and reports one peak per symmetry-equivalent carbon group in the input SMILES. Distinct carbon environments retain separate peaks even if their predicted shifts are close. A validation set of 108 patent structures selected this setting from 60 combinations of fold count, experimental-model weight and peak grouping.

| Independent evaluation | Unique structures | Five folds, one peak per carbon atom | Five folds, one peak per symmetry group |
| --- | ---: | ---: | ---: |
| NMRSpec | 1,000 | 2.31 | 1.22 |
| NMRExp | 748 | 2.45 | 1.14 |
| NMRGym | 980 | 3.20 | 2.77 |

Values are molecule-averaged peak-list errors in ppm. Minimum-cost matching caps paired errors at 20 ppm and charges 10 ppm for each extra or missing peak. Averaging across the three held-out sets, the paired 95% interval for the change was −0.95 to −0.87 ppm. Molecular connectivities are disjoint across development and evaluation sets. Overlap with upstream NMRNet++ pretraining is unverified.

[Use the carbon predictor](https://jiaqingxie.github.io/openmolspec.github.io/#tool-13c) · [Fold comparisons](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/forward_carbon_folds.json) · [Author checkpoints](https://zenodo.org/records/18232165) · [Download the carbon SDK and model profile](https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/peak-nmr-v2/openmolspec-13C.zip)

Run the selected predictor with the NMRNet++ source and five author checkpoints installed under the model root.

```python
from openmolspec.harness import SpectraHarness

prediction = SpectraHarness().run(
    "nmr.forward.13C", {"smiles": "CC(C)O"},
    {"root": "models", "backend": "nmrnetpp", "python": "/path/to/nmr-env/bin/python"},
)
print(prediction["result"]["records"][0]["peaks"])
```
