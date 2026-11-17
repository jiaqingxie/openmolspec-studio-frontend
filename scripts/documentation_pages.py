"""Generate bilingual reader pages and real-result analysis notebooks."""
import hashlib
import json
from pathlib import Path

from documentation_content import GROUPS, group, io_contract, results_table, quickstart, datasets_page, model_audit_page, assessment
from documentation_evidence import compact, load_evidence
def overlap_notice(*args, **kwargs): return ""
from documentation_models import training_section, model_index
from documentation_data import pages as data_pages
from documentation_theory import pages as theory_pages
from documentation_design import homepage, caption
from documentation_research import corpus_page, learning_page

ROOT=Path(__file__).resolve().parents[1]


def notebook(task,language):
    en=language=='en';id_=task.id;slug=id_.replace('.','-')
    cells=[]
    def markdown(text):cells.append({'cell_type':'markdown','metadata':{},'source':[text]})
    def code(text):cells.append({'cell_type':'code','metadata':{},'source':[text],'execution_count':None,'outputs':[]})
    markdown(f'# {id_}\n\n'+('Actual saved frozen-model results, rechecked and visualized by executed cells. The cells below do not rerun the model. Source files and hashes identify the original inference. No hypothetical predictions are used.' if en else '下面的单元格读取真实冻结模型运行结果，重新核算并绘图；它们不等于再次运行模型。来源文件和哈希可追溯到原始推理，不使用假想预测。'))
    code('import json, sys, io\nfrom pathlib import Path\nfrom IPython.display import display, Markdown, SVG\n'
         "root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'openmolspec_bench').is_dir()), None)\n"
         "if root is None:\n    raise RuntimeError('Run from the cloned release repository; see Quick Start')\n"
         "sys.path.insert(0, str(root / 'scripts'))\n"
         "from documentation_evidence import load_evidence, compact, recompute, render\n"
         "from documentation_content import results_table\n"
         f'evidence = load_evidence({id_!r})\n'
         "print(json.dumps({'task': evidence['task'], 'status': evidence['status'], 'source_sha256': evidence['source_hashes']}, indent=2, ensure_ascii=False))")
    if task.enabled:
        markdown('## '+('Actual input and output' if en else '实际输入与输出')+'\n\n'+('First recorded example; arrays over eight entries show length and a preview. Full values are in the downloadable evidence JSON.' if en else '使用记录中的第一例。超过八项的数组会显示长度和缩略值，完整数值保存在可下载证据 JSON 中。'))
        code("example = evidence['examples'][0]\nprint(json.dumps(compact(example), indent=2, ensure_ascii=False))")
        markdown('## '+('Recorded run table and recomputed diagnostics' if en else '实际运行指标与重新核算'))
        code(f'display(Markdown(results_table(evidence, {en!r})))\nprint(json.dumps(recompute(evidence), indent=2, ensure_ascii=False))')
        markdown('## '+('Prediction / reference figure' if en else '预测／参考对照图')+'\n\n'+assessment(task,en))
        code(f"figure = render({id_!r}, evidence)\nimage = io.StringIO()\nfigure.savefig(image, format='svg', metadata={{'Date': None}})\ndisplay(SVG(image.getvalue()))\nimport matplotlib.pyplot as plt\nplt.close(figure)")
        markdown(('## Rerun the model\n\nUse the task page and Quick Start to configure the original model runtime, checkpoint and dataset. The analysis environment alone is sufficient for all cells above.' if en else '## 重新执行模型\n\n按任务页面与 Quick Start 配置原模型运行环境、checkpoint 和数据。上面的分析单元格只需要文档示例环境。')+f'\n\n[Task](../tasks/{slug}.md) · [Quick Start](../quickstart.md)\n')
    else:markdown('Task deferred by the user. No model inference or new scientific score is presented.' if en else '用户已暂停此任务，本轮不运行模型，也不展示新的科学评分。')
    for i,c in enumerate(cells):c['id']=hashlib.sha256(f'{id_}:{language}:{i}'.encode()).hexdigest()[:12]
    return {'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},
                                    'openmolspec_evidence_files':[f'documentation/assets/examples/{slug}.json','scripts/documentation_evidence.py','scripts/documentation_figures.py','src/openmolspec/plotting.py','scripts/documentation_content.py']},'nbformat':4,'nbformat_minor':5}


def dataset_notebook(en):
    cells=[{'cell_type':'markdown','metadata':{},'source':['# '+('Dataset census and distributions' if en else '数据集计数与分布')+'\n\n'+('Replot audited full-file histograms; release-snapshot and parent-corpus counts retain their separate provenance.' if en else '从已核验的全文件统计重新绘图；release 快照和父数据量保留各自来源，不混合相加。')]},
           {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':["import sys, json, io\nfrom pathlib import Path\nfrom IPython.display import display, SVG\nroot = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'openmolspec_bench').is_dir())\nsys.path.insert(0, str(root / 'scripts'))\nfrom documentation_evidence import render_datasets\naudit = json.loads((root / 'documentation/assets/dataset_audit.json').read_text())\nfor row in audit['datasets']:\n    assert sum(row['modality_records'].values()) == row['records']\n    print(row['id'], row['records'], row['unique_canonical_isomeric_smiles'], row['modality_records'])\n"]},
           {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':["import matplotlib.pyplot as plt\nfor name, figure in render_datasets(save=False).items():\n    image = io.StringIO()\n    figure.savefig(image, format='svg', metadata={'Date': None})\n    display(SVG(image.getvalue()))\n    plt.close(figure)\n"]}]
    for i,c in enumerate(cells):c['id']=hashlib.sha256(f'datasets:{en}:{i}'.encode()).hexdigest()[:12]
    return {'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},
                                    'openmolspec_evidence_files':['documentation/assets/dataset_audit.json','scripts/documentation_evidence.py','scripts/documentation_figures.py','src/openmolspec/plotting.py']},'nbformat':4,'nbformat_minor':5}


def build_pages(tasks,profile,profile_zh):
    files={};bundles={t.id:load_evidence(t.id) for t in tasks}
    files['assets/evaluation_index.json']=json.dumps({k:v['runs'] for k,v in bundles.items()},ensure_ascii=False,indent=2)+'\n'
    for en in (True,False):
        suffix='' if en else '.zh';language='en' if en else 'zh'
        home=homepage(en)
        files[f'index{suffix}.md']=home
        files[f'quickstart{suffix}.md']=quickstart(en).replace('\n\n', '\n\n'+('For the new dataset/model classes and training preflight, start with the [Python SDK guide](api.md).\n\n' if en else '新的数据加载、模型类和训练准备入口见 [Python SDK 指南](api.md)。\n\n'), 1)
        files[f'datasets{suffix}.md']=datasets_page(en)
        files[f'datasets{suffix}.md']+='\n'+overlap_notice(en)
        files[f'model-audit{suffix}.md']=model_index(tasks,en)
        files[f'model-audit{suffix}.md']+='\n'+overlap_notice(en)
        files.update(data_pages(en))
        files.update(theory_pages(en))
        if (ROOT/'results/corpus_comparison_20261117.json').exists():
            files[f'corpus-comparison{suffix}.md']=corpus_page(en)
        files[f'learning-evidence{suffix}.md']='---\norphan: true\n---\n\n# Benchmarks\n\n[Benchmark guide / 统一评测指南](benchmarks.md)\n'
        files[f'notebooks/datasets-overview{suffix}.ipynb']=json.dumps(dataset_notebook(en),ensure_ascii=False,indent=2)+'\n'
        task_index='# '+('Tasks by spectroscopy family' if en else '按谱型浏览任务')+'\n\n'
        task_index+=('Choose the kind of evidence you have: NMR peaks, MS/MS peaks, a molecular geometry, or several spectral modalities together. Each task page explains the question, input fields, output fields and a real recorded example.\n\n' if en else '先按手头的信息选择：NMR 峰、MS/MS 峰、分子构象，或多种谱联合。每个任务页面说明解决什么问题、输入字段、输出字段，并展示真实运行案例。\n\n')
        notebook_index='# '+('Tutorials' if en else 'Tutorials 教程')+'\n\n'+('Each active task notebook shows actual input/output data, a run table, executable analysis and a result figure. These notebooks analyze saved inference; they are not placeholders for hypothetical results.\n\n' if en else '每个启用任务的 notebook 都有真实输入输出、运行指标、可执行分析和结果图。它们分析已保存的推理，不是列出“可能得到什么”的占位示例。\n\n')
        notebook_index+='[SDK: actual NMR inference](sdk-inference.ipynb) · [SDK: training preflight](sdk-training-preflight.ipynb)\n\n'
        notebook_index+=f'[Dataset distributions / 数据分布](datasets-overview.ipynb)\n\n'
        notebook_index+='## Theory simulations / 理论模拟\n\n'
        for name,title in [('nmr-fourier','NMR FID and Fourier transform'),('nmr-inversion','NMR relaxation inversion'),('vibrational-broadening','IR and Raman broadening'),('ms-isotopes','MS isotope envelopes')]:
            notebook_index+=f'- [{title}](theory-{name}.ipynb)\n'
        notebook_index+='\n'
        gallery='# Photo Gallery — '+('real results' if en else '真实结果')+'\n\n'
        gallery+=('Every image is generated from saved model outputs or audited dataset counts. Click a figure to open the task, its real example and interpretation. Blue/orange curves are identified in each panel; failed predictions and weak baselines are retained. Figures are generated with Matplotlib and RDKit.\n\n' if en else '每张图来自保存的模型输出或核验后的数据统计。点击图片进入对应任务、真实样本与解释。各图注明曲线含义，保留错误预测和较弱基线。图由 Matplotlib 与 RDKit 生成。\n\n')
        gallery+='<nav class="oms-gallery-nav" aria-label="Gallery categories">'+''.join(f'<a href="#gallery-{k}">{a if en else z}</a>' for k,a,z in GROUPS if k!='deferred')+'</nav>\n\n'
        for key,label,label_zh in GROUPS:
            members=[t for t in tasks if group(t)==key];heading=label if en else label_zh
            task_index+=f'## [{heading}]({key}.md)\n\n'
            task_index+='| Task / 任务 | Spectroscopy / 谱型 | Definition / 定义 |\n| --- | --- | --- |\n'
            for item in members:
                task_index+=f'| `{item.id}` | {", ".join(item.modalities)} | [{profile(item)[0] if en else item.title}]({item.id.replace(".","-")}.md) |\n'
            task_index+='\n'
            category=f'# {heading}\n\n'
            category+=('Task pages contain actual examples and measured results. A diagnostic status is not a validated production accuracy claim.\n\n' if en else '任务页面包含真实示例与实际评分。标为诊断的任务不代表已验证的正式精度。\n\n')
            category+='| Task / input → output | Task ID |\n| --- | --- |\n'
            notebook_index+=f'## {heading}\n\n'
            if key!='deferred':gallery+=f'<div id="gallery-{key}"></div>\n\n## {heading}\n\n<div class="oms-gallery-grid">\n'
            for task in members:
                slug=task.id.replace('.','-');title=profile(task)[0] if en else task.title
                category+=f'| [{title}]({slug}.md) | `{task.id}` |\n'
                notebook_index+=f'- [{title}]({slug}.ipynb)\n'
                if task.enabled:
                    gallery+=f'<figure><a href="tasks/{slug}.html"><img src="assets/gallery/{slug}.png" alt="{task.id}: actual model results" loading="lazy" width="2176" height="1088"></a><figcaption><strong><a href="tasks/{slug}.html">{title}</a></strong><span class="oms-caption-note">{caption(task,bundles[task.id],en)}</span><span class="oms-downloads"><a href="notebooks/{slug}.html">Notebook</a> · <a href="assets/gallery/{slug}.svg">SVG</a> · <a href="assets/gallery/{slug}.png">PNG</a> · <a href="assets/examples/{slug}.json">Data / 数据</a></span></figcaption></figure>\n'
            if key!='deferred':gallery+='</div>\n\n'
            notebook_index+='\n'
            files[f'tasks/{key}{suffix}.md']=category
        gallery+='[Corpus comparison](corpus-comparison.md) · [Controlled learning evaluations](learning-evidence.md)\n\n'
        gallery+='## '+('Dataset distributions' if en else '数据分布')+'\n\n'
        for slug in ('dataset-openspec-test','dataset-patent-corpus','dataset-nmr-views','dataset-nmrexp-nuclei'):
            gallery+=f'[![{slug}](assets/gallery/{slug}.png)](datasets.md)\n\n[SVG](assets/gallery/{slug}.svg) · [Data](assets/dataset_audit.json)\n\n'
        files[f'gallery{suffix}.md']=gallery
        files[f'tasks/index{suffix}.md']=task_index
        files[f'notebooks/index{suffix}.md']=notebook_index
        for task in tasks:
            slug=task.id.replace('.','-');b=bundles[task.id]
            title,purpose,method,metrics,limits,source=profile(task)
            if not en:purpose,method,metrics,limits=profile_zh(task);title=task.title
            page=f'# {title}\n\n{purpose}\n\n'
            if task.id.startswith(('nmr.retrieval.', 'nmr.generation.')):
                page+=overlap_notice(en, '../')
            if not task.enabled:
                page+=('Deferred at the user’s request. No new model result is claimed.\n' if en else '按用户要求暂不推进，本轮不展示新的模型结果。\n')
            else:
                page+='## '+('Example and evaluation' if en else '示例与评测')+f'\n\n{assessment(task,en)}\n\n'
                inputs,outputs=io_contract(task,en)
                page+='## '+('What goes in' if en else '输入是什么')+'\n\n'+inputs+'\n'
                page+='## '+('What comes out' if en else '输出是什么')+'\n\n'+outputs+'\n'
                page+='## '+('A real recorded example' if en else '真实运行案例')+'\n\n'
                page+=('The first recorded example is shown below, regardless of whether it succeeds. Array previews explicitly state their lengths; download the evidence JSON for complete values. Reference labels are kept separate from model inputs.\n\n' if en else '下面展示记录中的第一例，不按结果好坏筛选。长数组预览会标明完整长度；完整数值可下载证据 JSON。参考标签与模型输入分开保留。\n\n')
                page+=f'![{task.id} actual results](../assets/gallery/{slug}.png)\n\n[SVG](../assets/gallery/{slug}.svg) · [PNG](../assets/gallery/{slug}.png) · [Full input/output JSON](../assets/examples/{slug}.json)\n\n'
                page+='<details><summary>'+('Inspect the actual input and output fields' if en else '展开查看实际输入与输出字段')+'</summary>\n\n'
                page+='```json\n'+json.dumps(compact(b['examples'][0],4),ensure_ascii=False,indent=2)+'\n```\n\n</details>\n\n'
                page+='## '+('Actual evaluation results' if en else '实际评测结果')+'\n\n'+results_table(b,en)+'\n'
                page+=('Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.\n\n' if en else '样本量和候选池随每次运行记录。图可能展示单个分子，表格是来源实验的实际汇总，不能混为同一统计范围。\n\n')
                page+='## '+('Model and method' if en else '模型与方法')+f'\n\n{method}\n\n{metrics}\n\n'
                page+='## '+('Reproduce' if en else '复现方式')+'\n\n'
                page+=f'[Notebook with executed figures](../notebooks/{slug}.ipynb) · [Quick Start](../quickstart.md)\n\n'
                page+=f'```bash\npython -m openmolspec_bench run --workspace /path/to/OpenMolSpec \\\n  --tasks {task.id} --limit 8 --output results/{slug}-new.json\n```\n\n'
                page+=training_section(task,en)+'\n'
                page+='## '+('Data requirements and references' if en else '数据要求与引用')+f'\n\n{limits}\n\n'
                page+='<details><summary>'+('Source reports and SHA-256 fingerprints' if en else '来源报告与 SHA-256 指纹')+'</summary>\n\n'
                for name,digest in b['source_hashes'].items():page+=f'- [{name}](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/{name}) — SHA-256 `{digest}`\n'
                page+='\n</details>\n\n'
                page+=f'\n[Original model / 原模型]({source}) · [Model review / 模型检查](../model-audit.md)\n'
            files[f'tasks/{slug}{suffix}.md']=page
            files[f'notebooks/{slug}{suffix}.ipynb']=json.dumps(notebook(task,language),ensure_ascii=False,indent=2)+'\n'
        # Retain protocol/publication details; these pages are maintained below.
        files[f'protocols{suffix}.md']=('# Evaluation protocols\n\n' if en else '# 评测协议\n\n')+('All published figures use actual recorded results. Each evidence JSON carries source report hashes. Execution success is separate from scientific validity. Small candidate-pool results, prepared-data split labels and matched-peak errors must not be described as independent generalization or atom-assignment accuracy.\n\nComplete IR/Raman/H/C input and missing-channel ablations are reported separately. Gap units are converted once from Hartree to eV. MS scores compare with all observed peaks under explicit acquisition conditions. The frozen-model figures contain no fitted calibration. A separate two-record-per-split SDK training integration check completed one encoder and one generator step with save/reload verification; it is not a performance benchmark.\n\n' if en else '所有公开结果图来自实际记录。证据 JSON 保留来源报告哈希。执行成功与科学有效性分开判断；小候选池、准备数据的 split 标签、峰匹配误差，不能宣传成独立泛化或实验原子指认准确率。\n\n完整 IR/Raman/H/C 输入与缺通道消融分别报告。Gap 从 Hartree 到 eV 仅转换一次。MS 在明确采集条件下与全部实测峰比较。冻结模型图没有拟合校准。另有独立的 SDK 训练接口检查：每个原始划分取两个记录，编码器与生成器各训练一步并验证保存重载；这不是性能基准。\n\n')+'[Dataset definitions](datasets.md) · [Model-by-model audit](model-audit.md)\n'
        files[f'publication{suffix}.md']=('# Publication status\n\n' if en else '# 发布状态\n\n')+('[English](https://openmolspec-10.readthedocs.io/en/latest/) · [简体中文](https://openmolspec-10.readthedocs.io/en/latest/zh/index.html)\n\n')+('Read the Docs builds `release/openmolspec-v1` with the root `.readthedocs.yaml`, Sphinx and the classic RTD theme. The site includes categorized tasks, a real-results gallery, dataset distributions, model review and 82 tutorials, including SDK inference, training preparation and theory simulations. Notebook publication never executes model code.\n\n' if en else 'Read the Docs 使用根目录 `.readthedocs.yaml` 构建 `release/openmolspec-v1` 分支，采用 Sphinx 与经典 RTD 主题。站点包括分类任务、真实结果图册、数据分布、模型与训练说明及 82 份教程（含暂停任务说明和数据分布 notebook）。发布构建不执行模型代码。\n\n')+'```bash\npython scripts/build_bilingual_docs.py --check\npython scripts/build_readthedocs.py --output site --strict\npython scripts/publish_readthedocs.py --apply --project openmolspec-10 --wait 600\n```\n\n'+('Publish only after pushing the corresponding Git commit. The publication script verifies the exact remote commit and finished RTD build; public pages are checked separately.\n' if en else '先推送对应 Git 提交，再发布。发布脚本检查远端精确提交与完成的 RTD 构建，公开页面另行验证。\n')
    for suffix,en in [('',True),('.zh',False)]:
        files[f'protocols{suffix}.md']+='\n'+overlap_notice(en)
    return {name:(content.rstrip()+'\n' if name.endswith('.md') else content) for name,content in files.items()}
