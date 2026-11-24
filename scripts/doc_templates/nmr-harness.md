## Released solution-shift predictors

For ¹H, ¹¹B, ²⁹Si, ³¹P and ¹⁹F, set `root` to the extracted model directory containing `model.json`, or to a registry containing a subdirectory for each nucleus. Set `python` to the environment with the model dependencies. The response includes the checkpoint digest, ppm values and atom indices. With the ¹³C five-fold model, set `root` to the parent of the upstream `nmrnetpp` directory and select `backend="nmrnetpp"`. The named `NMRNet` SDK class retains the atomwise author baseline.

```python
from openmolspec.harness import SpectraHarness

out = SpectraHarness().run(
    "nmr.forward.31P", {"smiles": "CCOP(=O)(OCC)OCC", "solvent": "CDCl3"},
    {"root": "model", "python": "/path/to/solution-nmr/bin/python"},
)
print(out["result"]["records"][0]["prediction_ppm"])
```
