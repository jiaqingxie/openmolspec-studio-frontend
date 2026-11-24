## 当前上线的液相碳谱模型

模型先对五个 NMRNet++ 检查点的逐碳原子预测取平均，再对分子中拓扑对称的碳原子取平均，每组输出一个峰和对应原子编号。两个结构环境不同但预测位移相近的碳仍然分别输出。我们在 108 个专利验证分子上比较了 60 种折数、实验数据模型权重及峰合并设置。

| 独立评测集 | 分子数 | 每个碳原子一个峰 | 每组对称碳一个峰 |
| --- | ---: | ---: | ---: |
| NMRSpec | 1,000 | 2.31 | 1.22 |
| NMRExp | 748 | 2.45 | 1.14 |
| NMRGym | 980 | 3.20 | 2.77 |

表中单位为 ppm，按分子等权。预测峰与实测峰以最小误差匹配，匹配误差上限为 20 ppm，每多报或漏报一个峰计 10 ppm。三个测试集合并后，新旧误差差值的配对 95% 区间为 −0.95 至 −0.87 ppm。验证集和三个测试集之间按分子连通结构去重。上游预训练集与这些测试结构的重叠情况尚未核实。

[在线预测碳谱](https://jiaqingxie.github.io/openmolspec.github.io/#tool-13c) · [选型结果](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/forward_carbon_folds.json) · [原作者发布的权重](https://zenodo.org/records/18232165) · [下载 SDK 与碳谱模型配置](https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/peak-nmr-v2/openmolspec-13C.zip)

在模型目录下安装 NMRNet++ 源码及五折权重后，可以在 SDK 中运行。

```python
from openmolspec.harness import SpectraHarness

prediction = SpectraHarness().run(
    "nmr.forward.13C", {"smiles": "CC(C)O"},
    {"root": "models", "backend": "nmrnetpp", "python": "/path/to/nmr-env/bin/python"},
)
print(prediction["result"]["records"][0]["peaks"])
```
