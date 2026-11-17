# OpenMolSpec

<div class="oms-eyebrow">Chemical spectroscopy · Open research platform</div>

<p class="oms-lead"><strong>数据集、模型与可复现的化学谱学</strong><br>通过统一 Python 接口加载分子谱学数据、预测谱图、检索或生成结构，并训练 NMR 模型。</p>

<div class="oms-stat-grid">
<div class="oms-stat"><strong>8</strong><span>个数据注册入口</span></div>
<div class="oms-stat"><strong>31</strong><span>个启用任务配置</span></div>
<div class="oms-stat"><strong>82</strong><span>份已执行中英文 notebook</span></div>
</div>

<div class="oms-paths">
<a class="oms-path" href="data/index.html"><strong>使用数据 →</strong><span>了解来源、分布、训练与测试划分，以及数据加载方法。</span></a>
<a class="oms-path" href="tasks/index.html"><strong>选择任务 →</strong><span>从手头的结构、NMR 峰、MS/MS、IR 或 Raman 出发。</span></a>
<a class="oms-path" href="api.html"><strong>预测与训练 →</strong><span>调用模型类、检查真实案例，并准备自己的训练数据。</span></a>
</div>

## 先看一份实际结果

构象到谱图示例调用 Xinyu 的 openSpec 模型，输入坐标与 Gaussian 参考完全对应。两条曲线分别是实际预测与参考计算。图中展示两个案例中的一例，说明推理路径已跑通；完整精度仍需更大规模的独立评测。

[![IR and Raman: recorded prediction and reference](assets/gallery/vibrational-forward.png)](tasks/vibrational-forward.md)

[浏览全部结果图](gallery.md) · [任务输入与输出](tasks/vibrational-forward.md) · [查看教程](notebooks/vibrational-forward.ipynb)

## 从 Python 包开始

先按 [SDK 指南](api.md) 安装带版本号的 wheel，再查看数据注册表。完整数据和模型权重的准备方法也在该页列出。

```python
from openmolspec.dataset import list_datasets

for card in list_datasets():
    print(card["name"])
```

[Quick Start](quickstart.md) · [Python SDK](api.md) · [Tutorials](notebooks/index.md)

## 这里的数据分别是什么

| 数据类别 | 含义 | 查看详情 |
| --- | --- | --- |
| 团队整理的实验 NMR | 从专利整理的实验测量；当前准备库含 2,680,271 个存储的标准 InChI 身份。整理数据不代表实验由我们测量。 | [来源与计数](datasets.md) |
| 计算谱与性质 | 计算得到的 IR/Raman 及分子性质，分子记录和构象帧分别计数。 | [数据分布](datasets.md) |
| 外部基准 | NMRSpec、NMRexp、NMRGym、MS 等资源保留各自来源和贡献者。 | [数据比较](corpus-comparison.md) |

不同资源的计数单位不同，也可能包含相同分子。注册入口提供统一访问，不代表八个新测量的数据集。

## 使用前判断模型是否适合

H/C NMR、MS/MS 与振动谱案例均展示真实输出。B/Si 和 F/P 当前只作诊断，跨溶剂迁移当前为实验参考检索基线。训练接口已完成编码器与生成器的微型训练、保存、重载检查；大规模学习效果需要另外的实验支撑。

[Model suitability](model-audit.md) · [Evaluation protocols](protocols.md) · [Publication status](publication.md)

[Data](data/index.md) · [Theory](theory/index.md) · [Inversion](inversion/index.md) · [Spectra Harness](harness.md)
