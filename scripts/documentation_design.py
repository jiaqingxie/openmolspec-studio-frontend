"""Home page and figure captions for the OpenMolSpec user manual."""
from html import escape


def viewer_html(en,prefix=''):
    title='Interactive molecular example' if en else '交互式分子示例'
    explanation=('Explore the molecular structure in 3D alongside the dataset orbital energies and the gap predicted from IR, Raman and H/C NMR spectra.' if en else
        '在三维中查看分子结构，配合数据集中的参考轨道能量，以及由 IR、Raman 和 H/C NMR 光谱预测的能隙。')
    return f'''\n### {title}

{explanation}

<div class="oms-conformer-demo" data-oms-viewer data-oms-assets="{prefix}assets/viewer/" data-oms-language="{'en' if en else 'zh'}">
<label>{'Molecule' if en else '分子'} <select class="oms-conformer-select" aria-label="{'Select molecule' if en else '选择分子'}"></select></label>
<div class="oms-conformer-canvas" role="img" aria-label="{'Interactive molecular conformer' if en else '交互式分子构象'}"></div>
<p class="oms-conformer-result" aria-live="polite">{'Loading coordinates…' if en else '正在加载坐标…'}</p>
</div>

'''


def homepage(en):
    text='# OpenMolSpec\n\n'
    text+='Chemical spectroscopy and deep learning\n\n'
    text+=('OpenMolSpec is a Python library for working with molecular spectra. Load experimental and computed datasets, predict spectra and molecular properties, identify structures, and train models with your own data. It supports NMR, mass spectrometry, infrared and Raman spectroscopy.\n\n' if en else
           'OpenMolSpec 是面向分子谱学的 Python 工具包。你可以加载实验与计算数据集，预测谱图和分子性质，通过谱图解析结构，也可以用自己的数据训练模型。支持 NMR、质谱、红外与拉曼光谱。\n\n')
    text+='## '+('Getting started' if en else '开始使用')+'\n\n'
    text+=('Follow the [Quick start](quickstart.md) to install OpenMolSpec and work through data loading, prediction and training. The [tutorials](notebooks/index.md) explain each step with code, outputs and figures.\n\n' if en else
           '从[快速开始](quickstart.md)安装 OpenMolSpec，依次学习数据加载、模型预测和训练。[教程](notebooks/index.md)配有逐步说明、代码、输出和图。\n\n')
    text+='```python\nfrom openmolspec.dataset import molspectra\nfrom openmolspec.model import NMRNet\n\ndata = molspectra("opendatalab_nmr", root="data/nmr")\nmolecule = data["test"].head(1)[0]\n\nmodel = NMRNet.from_pretrained("models", nucleus="13C",\n    python="/path/to/nmr-env/bin/python")\nprediction = model.predict(molecule["smiles"])\nprint(prediction["records"])\n```\n\n'
    text+='## Examples\n\n'
    text+=('Explore spectrum prediction, structure elucidation and property prediction in the following examples.\n\n' if en else '下面的例子展示如何预测谱图、解析分子结构，以及预测分子性质。\n\n')
    for title,zh,slug,desc,desc_zh in [
        ('Structure elucidation from NMR','从 NMR 解析结构','nmr-generation-hc','The top-ranked structure matches the reference molecule in this H/C NMR example.','输入氢谱、碳谱和分子式，首选候选结构与参考分子一致。'),
        ('Predicting tandem mass spectra','预测串联质谱','ms-forward-glacier','Compare GLACIER predictions with 14 measured peaks: cosine similarity 0.869 and entropy similarity 0.796.','GLACIER 预测与 14 个实测峰对比：余弦相似度 0.869，熵相似度 0.796。'),
        ('IR and Raman from a molecular geometry','由分子构象预测红外与拉曼谱','vibrational-forward','Use the openSpec model to predict vibrational spectra from atomic coordinates.','使用 openSpec 模型，从原子坐标预测振动光谱。'),
        ('HOMO–LUMO gap prediction','预测 HOMO–LUMO 能隙','vibrational-gap-ir_raman_hc','Combine IR, Raman and NMR spectra to predict the molecular energy gap.','结合 IR、Raman 和 NMR，预测分子的 HOMO–LUMO 能隙。')]:
        text+=f'### [{title if en else zh}](notebooks/{slug}.ipynb)\n\n{desc if en else desc_zh}\n\n'
        text+=f'[![{title}](assets/gallery/{slug}.png)](notebooks/{slug}.ipynb)\n\n'
    text+=viewer_html(en)
    text+='## '+('Documentation' if en else '使用手册')+'\n\n'
    for path,a,z,desc,desc_zh in [
        ('data/index.md','Data','数据','Datasets, experimental details, distributions and splits.','数据集、实验信息、数据分布与划分。'),
        ('tasks/index.md','Tasks','任务','Task definitions, inputs, outputs and model usage.','任务定义、输入输出与模型使用。'),
        ('notebooks/index.md','Tutorials','教程','Step-by-step examples for prediction, training and spectroscopy.','预测、训练与谱学理论的分步教程。'),
        ('api-reference/index.md','API reference','API 参考','Classes, functions, arguments, return values and examples.','类、函数、参数、返回值和调用示例。'),
        ('benchmarks.md','Benchmarks','基准评测','Benchmark datasets, protocols, metrics and results.','基准数据、评测流程、指标与结果。'),
        ('harness.md','Agent Harness','Agent Harness','Use spectroscopy tools from Python, the command line or an agent.','通过 Python、命令行或 Agent 调用谱学工具。')]:
        text+=f'- [{a if en else z}]({path}): {desc if en else desc_zh}\n'
    return text


def caption(task,evidence,en):
    notes={
        'hsqc':('Observed and predicted HSQC cross-peaks for butanenitrile in CDCl₃.','丁腈在 CDCl₃ 中的实测和预测 HSQC 交叉峰。'),
        'parity':('Predicted and reference values.','预测值与参考值。'),
        'vibrational':('IR and Raman spectra for the displayed molecular geometry.','所示分子构象的 IR 与 Raman 光谱。'),
        'molecules':('Reference structure and generated candidates.','参考结构与生成候选。'),
        'ranking':('Molecular candidates ranked by spectral similarity.','按谱相似度排序的分子候选。'),
        'nmr_peaks':('Measured and predicted chemical shifts in ppm.','实测与预测化学位移，单位为 ppm。'),
        'ms':('Measured and predicted MS/MS spectra.','实测与预测 MS/MS 谱。'),
        'assignment':('Peak assignments on the molecular structure.','分子结构上的峰指认。'),
        'solvent':('Chemical shift transfer between solvents.','溶剂间的化学位移迁移。'),
        'magma':('Fragments assigned to the measured MS/MS peaks.','实测 MS/MS 峰对应的碎片结构。')}
    return escape(notes[evidence['plot']['kind']][0 if en else 1])
