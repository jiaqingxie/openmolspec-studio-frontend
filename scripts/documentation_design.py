"""Reader-facing navigation and captions for the bilingual documentation."""
from html import escape


def homepage(en):
    title='Datasets, models and reproducible spectroscopy' if en else '数据集、模型与可复现的化学谱学'
    intro=('Load molecular spectra, predict observables, retrieve or generate structures, and train NMR models through a common Python interface.' if en else
           '通过统一 Python 接口加载分子谱学数据、预测谱图、检索或生成结构，并训练 NMR 模型。')
    text=f'# OpenMolSpec\n\n<div class="oms-eyebrow">Chemical spectroscopy · Open research platform</div>\n\n'
    text+=f'<p class="oms-lead"><strong>{title}</strong><br>{intro}</p>\n\n'
    text+='<div class="oms-stat-grid">\n'
    for value,english,chinese in [('7','dataset registry entries','个数据注册入口'),('31','active task configurations','个启用任务配置'),('74','executed bilingual notebooks','份已执行中英文 notebook')]:
        text+=f'<div class="oms-stat"><strong>{value}</strong><span>{english if en else chinese}</span></div>\n'
    text+='</div>\n\n'
    paths=[('datasets.html','Use the data','使用数据','Understand sources, distributions, split roles and loading APIs.','了解来源、分布、训练与测试划分，以及数据加载方法。'),
           ('tasks/index.html','Choose a task','选择任务','Start from your input: a structure, NMR peaks, MS/MS, IR or Raman.','从手头的结构、NMR 峰、MS/MS、IR 或 Raman 出发。'),
           ('api.html','Predict and train','预测与训练','Use model classes, inspect real examples and prepare training data.','调用模型类、检查真实案例，并准备自己的训练数据。')]
    text+='<div class="oms-paths">\n'+''.join(f'<a class="oms-path" href="{url}"><strong>{a if en else z} →</strong><span>{ae if en else ze}</span></a>\n' for url,a,z,ae,ze in paths)+'</div>\n\n'
    text+='## '+('See an actual result' if en else '先看一份实际结果')+'\n\n'
    text+=('The geometry-to-spectrum example uses Xinyu’s openSpec models and the exact coordinates of its Gaussian reference. The two curves show the recorded prediction and calculation. This figure shows one of two examples; it establishes a working inference path, not a large independent benchmark.\n\n' if en else
           '构象到谱图示例调用 Xinyu 的 openSpec 模型，输入坐标与 Gaussian 参考完全对应。两条曲线分别是实际预测与参考计算。图中展示两个案例中的一例，说明推理路径已跑通；完整精度仍需更大规模的独立评测。\n\n')
    text+='[![IR and Raman: recorded prediction and reference](assets/gallery/vibrational-forward.png)](tasks/vibrational-forward.md)\n\n'
    text+=('[Explore all result figures](gallery.md) · [Open this task](tasks/vibrational-forward.md) · [Read the executed notebook](notebooks/vibrational-forward.ipynb)\n\n' if en else
           '[浏览全部结果图](gallery.md) · [任务输入与输出](tasks/vibrational-forward.md) · [查看已执行 notebook](notebooks/vibrational-forward.ipynb)\n\n')
    text+='## '+('Start with the Python package' if en else '从 Python 包开始')+'\n\n'
    text+=('Install the versioned wheel using the [SDK guide](api.md), then inspect the dataset registry. Loading full data and running model weights require the assets described there.\n\n' if en else
           '先按 [SDK 指南](api.md) 安装带版本号的 wheel，再查看数据注册表。完整数据和模型权重的准备方法也在该页列出。\n\n')
    text+='```python\nfrom openmolspec.dataset import list_datasets\n\nfor card in list_datasets():\n    print(card["name"])\n```\n\n'
    text+='[Quick Start](quickstart.md) · [Python SDK](api.md) · [Executed notebooks](notebooks/index.md)\n\n'
    text+='## '+('What the data represent' if en else '这里的数据分别是什么')+'\n\n'
    text+=('| Collection | Meaning | Where to inspect |\n| --- | --- | --- |\n'
           '| Team-curated experimental NMR | Patent-derived measurements; 2,680,271 stored standard-InChI identities in the current prepared corpus. Curation does not mean we measured these spectra. | [Sources and counts](datasets.md) |\n'
           '| Computed observables | Calculated IR/Raman and associated molecular properties. Molecular records and geometry frames are counted separately. | [Distributions](datasets.md) |\n'
           '| External benchmarks | NMRSpec, NMRexp, NMRGym and MS resources retain their own provenance and attribution. | [Data comparison](corpus-comparison.md) |\n\n' if en else
           '| 数据类别 | 含义 | 查看详情 |\n| --- | --- | --- |\n'
           '| 团队整理的实验 NMR | 从专利整理的实验测量；当前准备库含 2,680,271 个存储的标准 InChI 身份。整理数据不代表实验由我们测量。 | [来源与计数](datasets.md) |\n'
           '| 计算谱与性质 | 计算得到的 IR/Raman 及分子性质，分子记录和构象帧分别计数。 | [数据分布](datasets.md) |\n'
           '| 外部基准 | NMRSpec、NMRexp、NMRGym、MS 等资源保留各自来源和贡献者。 | [数据比较](corpus-comparison.md) |\n\n')
    text+=('Dataset counts use different units and can overlap. The registry is an access layer, not seven newly measured datasets.\n\n' if en else
           '不同资源的计数单位不同，也可能包含相同分子。注册入口提供统一访问，不代表七个新测量的数据集。\n\n')
    text+='## '+('Assess a model before using it' if en else '使用前判断模型是否适合')+'\n\n'
    text+=('H/C NMR, MS/MS and vibrational examples contain actual outputs. B/Si and F/P are diagnostic; cross-solvent transfer is currently an experimental-reference baseline. The training API has completed an encoder/generator train–save–reload integration check on tiny examples; large-scale learning claims require separate experiments.\n\n' if en else
           'H/C NMR、MS/MS 与振动谱案例均展示真实输出。B/Si 和 F/P 当前只作诊断，跨溶剂迁移当前为实验参考检索基线。训练接口已完成编码器与生成器的微型训练、保存、重载检查；大规模学习效果需要另外的实验支撑。\n\n')
    text+='[Model suitability](model-audit.md) · [Evaluation protocols](protocols.md) · [Training overlap](training-overlap.md) · [Publication status](publication.md)\n'
    return text


def caption(task, evidence, en):
    kind=evidence['plot']['kind']
    notes={
        'parity':('Every recorded pair is shown; inspect the scale and error distribution.','展示全部记录的配对点，注意坐标范围与误差分布。'),
        'vibrational':('Exact input geometry; Gaussian reference and model prediction on a common axis.','使用完全相同的输入构象，在同一波数轴比较 Gaussian 参考与模型预测。'),
        'molecules':('First recorded case. The graph comparison states whether the actual top-1 result matches.','记录中的第一例；结构比较明确标出实际 top-1 是否与参考一致。'),
        'ranking':('A small candidate-library example; green marks the reference.','小候选库检索示例；绿色标出参考候选。'),
        'nmr_peaks':('Structure input and experimental/predicted peak positions. Stick height is not intensity.','输入分子结构与实验／预测峰位置；棒高不代表强度。'),
        'ms':('Observed spectrum above, prediction below; acquisition conditions are retained.','上方为实测谱，下方为预测谱，保留采集条件。'),
        'assignment':('Atom indices use the input graph. Matching residual is not assignment accuracy.','原子索引对应输入图；匹配残差不等于实验指认准确率。'),
        'solvent':('Comparison with unchanged shifts, separated by nucleus. Lower error is better.','按核种分别比较参考迁移和保持原位移不变；误差越低越好。'),
        'magma':('Algorithmic fragment matching for observed peaks, with unmatched peaks retained.','对实测峰进行算法碎片匹配，同时保留未匹配峰。'),
    }
    note=notes[kind][0 if en else 1]
    return escape(note)
