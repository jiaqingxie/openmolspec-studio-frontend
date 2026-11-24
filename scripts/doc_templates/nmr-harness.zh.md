## 已发布的溶液核磁预测器

对于 ¹H、¹¹B、²⁹Si、³¹P 和 ¹⁹F，`root` 可以是解压后包含 `model.json` 的目录，也可以是按核种分子目录的模型库。`python` 指向已安装相应依赖的解释器。结果包含模型校验值、以 ppm 为单位的化学位移和原子编号。运行 ¹³C 五折模型时，将 `root` 指向上游 `nmrnetpp` 目录的上一级，并指定 `backend="nmrnetpp"`。SDK 中名为 `NMRNet` 的类可单独调用原始逐原子基线。

```python
from openmolspec.harness import SpectraHarness

out = SpectraHarness().run(
    "nmr.forward.31P", {"smiles": "CCOP(=O)(OCC)OCC", "solvent": "CDCl3"},
    {"root": "model", "python": "/path/to/solution-nmr/bin/python"},
)
print(out["result"]["records"][0]["prediction_ppm"])
```
