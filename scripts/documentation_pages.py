"""Generate bilingual reader pages and real-result analysis notebooks."""
import hashlib
import json
from pathlib import Path

from documentation_content import GROUPS, group, io_contract, results_table, quickstart, datasets_page, model_audit_page, assessment
from documentation_evidence import compact, load_evidence
def overlap_notice(*args, **kwargs): return ""
from documentation_models import training_section, model_index
from manual_data import pages as data_pages
from documentation_theory import pages as theory_pages
from manual_harness import pages as harness_pages
from documentation_design import homepage, caption, viewer_html
from manual_quickstart import quickstart
from manual_citations import markdown as reference_list
from documentation_research import corpus_page, learning_page

ROOT=Path(__file__).resolve().parents[1]


def solution_task_page(nucleus, en):
    if nucleus == '31P' and (ROOT/'results/phosphorus_gnn_selection.json').is_file():
        from phosphorus_model_card import model_card
        return model_card(en)
    report = json.loads((ROOT / 'results' / f'solution_shifts_{nucleus}.json').read_text())
    single = report['metrics']['test_single']
    unseen = report['metrics']['test_single_unseen_scaffold']
    sample = 'CCOP(=O)(OCC)OCC' if nucleus == '31P' else 'Fc1ccccc1'
    slug = f'nmr-forward-{nucleus}'
    if en:
        title = f'{nucleus} solution chemical shifts from SMILES'
        intro = 'Predict shifts in ppm from a molecular structure and optional NMR solvent. Each environment includes its zero-based input atom indices. Symmetry-equivalent atoms share one predicted peak.'
        accuracy = (f"The held-out single-environment test contains {single['observations']:,} observations across {single['identities']:,} connectivities. "
                    f"MAE is {single['mae_ppm']:.2f} ppm and median absolute error is {single['median_absolute_ppm']:.2f} ppm. "
                    f"MAE is {unseen['mae_ppm']:.2f} ppm on the subset with nonempty scaffolds absent from training.")
        limitation = 'Training uses experimental records with one observed signal and one graph-equivalence class. On multisite spectra, validation compares sorted peak lists when the observed count matches. Chemical shifts do not determine coupling constants, line shapes or intensities.'
        archive = 'The archived solid-state diagnostic is available in the original notebook.'
    else:
        title = f'从 SMILES 预测 {nucleus} 溶液化学位移'
        intro = '输入分子结构和可选的核磁溶剂，输出各化学环境的预测位移（ppm）以及输入 SMILES 中从零开始的原子编号。对称等价的原子共享一个预测峰。'
        accuracy = (f"单一环境测试集含 {single['identities']:,} 种留出分子和 {single['observations']:,} 条观测。"
                    f"MAE 为 {single['mae_ppm']:.2f} ppm，中位绝对误差为 {single['median_absolute_ppm']:.2f} ppm。"
                    f"训练中未出现的非空骨架子集 MAE 为 {unseen['mae_ppm']:.2f} ppm。")
        limitation = '训练使用只含一个观测峰且只有一类图对称位点的实验记录。多环境分子的评测仅在峰数匹配时比较排序后的峰列表。输出覆盖峰位置，逐峰归属、耦合常数、强度和线形仍需额外证据。'
        archive = '原固态权重的历史诊断保存在旧版笔记本中。'
    return (f'# {title}\n\n{intro}\n\n{accuracy}\n\n{limitation}\n\n'
            f'```python\nfrom openmolspec.model import SolutionShiftPredictor\n\n'
            f'model = SolutionShiftPredictor("/path/to/OpenMolSpec/runs/solution-shifts-v1/{nucleus}")\n'
            f'print(model.predict("{sample}", solvent="CDCl3")["environments"])\n```\n\n'
            f'```bash\npython -m pip install -e ".[solution-nmr]"\n'
            f'python -m openmolspec_bench run --workspace /path/to/OpenMolSpec --tasks nmr.forward.{nucleus} '
            f'--limit 100000 --output results/{slug}-test.json\n```\n\n'
            f'{archive} [Notebook](../notebooks/{slug}.ipynb)\n')


def reference_keys(task):
    name=task.id
    if name=='nmr.hsqc.transpeaknet':return ['transpeaknet']
    if name.startswith('nmr.forward.') or name=='nmr.assignment':return ['nmrnet','opendatalab']
    if name=='nmr.solvent_transfer':return ['nmrshiftdb']
    if name.startswith('nmr.'):return ['nmrtrans','nmrgym','opendatalab']
    if name=='ms.annotation.magma':return ['magma','massspecgym']
    if name.startswith('ms.'):return ['glacier' if name.endswith('glacier') else 'iceberg','massspecgym']
    return ['openspec','openmolspec','qme14s','qm9s']


def notebook(task,language):
    en=language=='en';id_=task.id;slug=id_.replace('.','-')
    from manual_profiles import profile
    title,purpose,method,metrics,_,_=profile(task,en)
    runtime_options=' --fp-inference-root /path/to/frozen-fp --allow-cross-domain-diagnostic' if id_ in ['nmr.forward.19F','nmr.forward.31P'] else ''
    if id_ == 'nmr.hsqc.transpeaknet':runtime_options = ' --transpeaknet-source /path/to/2dNMR'
    cells=[]
    def markdown(text):cells.append({'cell_type':'markdown','metadata':{},'source':[text]})
    def code(text):cells.append({'cell_type':'code','metadata':{},'source':[text],'execution_count':None,'outputs':[]})
    markdown(f'# {title}\n\n{purpose}\n\n{method}\n\n'+('This tutorial loads the saved predictions, explains the input/output fields and evaluates the results. Use the final command to run the model on a new dataset.' if en else '本教程读取保存的预测，解释输入输出字段，并评估结果。最后给出在新数据集上运行模型的命令。'))
    code('import json, sys, io\nfrom pathlib import Path\nfrom IPython.display import display, Markdown, SVG\n'
         "root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'openmolspec_bench').is_dir()), None)\n"
         "if root is None:\n    raise RuntimeError('Run from the cloned release repository; see Quick Start')\n"
         "sys.path.insert(0, str(root / 'scripts'))\n"
         "from documentation_evidence import load_evidence, compact, recompute, render\n"
         "from documentation_content import results_table\n"
         f'evidence = load_evidence({id_!r})\n'
         "print('Task:', evidence['task'])\nprint('Examples:', len(evidence['examples']))")
    if task.enabled:
        inputs,outputs=io_contract(task,en)
        markdown('## '+('Inputs and outputs' if en else '输入与输出')+'\n\n'+inputs+'\n'+outputs+'\n'+('Inspect the example records below. Long arrays show their length and first values; the downloadable JSON contains the complete arrays.' if en else '查看下面的示例记录。长数组显示长度与前几个数值，下载 JSON 可获取完整数组。'))
        code("for example in evidence['examples'][:3]:\n    print(json.dumps(compact(example), indent=2, ensure_ascii=False))")
        markdown('## '+('Evaluate the predictions' if en else '评估预测')+f'\n\n{metrics}\n\n'+('The table gives the dataset and metric for each run. The following calculation recomputes summary values from the plotted predictions.' if en else '表格给出每次运行的数据集与指标。后续代码从绘图使用的预测值重新计算汇总结果。'))
        code(f'display(Markdown(results_table(evidence, {en!r})))\nprint(json.dumps(recompute(evidence), indent=2, ensure_ascii=False))')
        markdown('## '+('Visualize the result' if en else '查看结果图')+'\n\n'+caption(task,evidence=load_evidence(task.id),en=en)+'\n\n'+('Compare the prediction with the reference and inspect the returned structures or peak positions. The plot is generated directly from the records loaded above.' if en else '比较预测与参考，查看返回的结构或峰位置。图由上方读取的记录直接生成。'))
        count=min(3,len(load_evidence(id_)['examples'])) if id_ in ['nmr.generation.hc','ms.forward.glacier','ms.forward.iceberg'] else 1
        code(f"import matplotlib.pyplot as plt\nfor example_index in range({count}):\n    figure = render({id_!r}, evidence, example_index=example_index)\n    image = io.StringIO()\n    figure.savefig(image, format='svg', metadata={{'Date': None}})\n    display(SVG(image.getvalue()))\n    plt.close(figure)")
        markdown(('## Run the model\n\nConfigure the runtime and weights following the task guide. Select this task in the benchmark runner to evaluate your dataset.' if en else '## 运行模型\n\n按任务指南配置环境和权重，在 benchmark runner 中选择本任务，即可评估自己的数据集。')+f'\n\n```bash\npython -m openmolspec_bench run --workspace /path/to/OpenMolSpec \\\n  --tasks {id_}{runtime_options} --limit 8 --output results/{slug}.json\n```\n\n[Task](../tasks/{slug}.md) · [Quick start](../quickstart.md)\n')
        markdown(reference_list(reference_keys(task),en))
    else:markdown('Task deferred by the user. No model inference or new scientific score is presented.' if en else '用户已暂停此任务，本轮不运行模型，也不展示新的科学评分。')
    for i,c in enumerate(cells):c['id']=hashlib.sha256(f'{id_}:{language}:{i}'.encode()).hexdigest()[:12]
    return {'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},
                                    'openmolspec_evidence_files':[f'documentation/assets/examples/{slug}.json','scripts/documentation_evidence.py','scripts/documentation_figures.py','src/openmolspec/plotting.py','scripts/documentation_content.py']},'nbformat':4,'nbformat_minor':5}


def dataset_notebook(en):
    from manual_data import notebook
    return notebook(en)


def build_pages(tasks,profile,profile_zh):
    files={};bundles={t.id:load_evidence(t.id) for t in tasks}
    files['assets/evaluation_index.json']=json.dumps({k:v['runs'] for k,v in bundles.items()},ensure_ascii=False,indent=2)+'\n'
    for en in (True,False):
        suffix='' if en else '.zh';language='en' if en else 'zh'
        home=homepage(en)
        files[f'index{suffix}.md']=home
        files[f'quickstart{suffix}.md']=quickstart(en)
        files[f'datasets{suffix}.md']=datasets_page(en)
        files[f'datasets{suffix}.md']+='\n'+overlap_notice(en)
        files[f'model-audit{suffix}.md']=model_index(tasks,en)
        files[f'model-audit{suffix}.md']+='\n'+overlap_notice(en)
        files.update(data_pages(en))
        for name,body in theory_pages(en).items():
            keys=['inversions','nmrnet'] if 'nmr' in name or 'inversion' in name else ['massspecgym','glacier','iceberg'] if '/ms' in name else ['qm9s','qme14s','openspec']
            files[name]=body+reference_list(keys,en) if name.endswith('.md') else body
        for name,body in harness_pages(en).items():
            files[name]=body+reference_list(['deepseek_harness','nmrnet','glacier','iceberg','openspec'],en) if name.endswith('.md') else body
        if (ROOT/'results/corpus_comparison_20261117.json').exists():
            files[f'corpus-comparison{suffix}.md']='---\norphan: true\n---\n\n# Data comparison\n\n[Data comparison](data/comparison.md)\n'
        files[f'learning-evidence{suffix}.md']='---\norphan: true\n---\n\n# Benchmarks\n\n[Benchmark guide / 统一评测指南](benchmarks.md)\n'
        files[f'notebooks/datasets-overview{suffix}.ipynb']=json.dumps(dataset_notebook(en),ensure_ascii=False,indent=2)+'\n'
        task_index='# '+('Tasks by spectroscopy family' if en else '按谱型浏览任务')+'\n\n'
        task_index+=('Choose the kind of evidence you have: NMR peaks, MS/MS peaks, a molecular geometry, or several spectral modalities together. Each task page explains the question, input fields, output fields and a real recorded example.\n\n' if en else '先按手头的信息选择：NMR 峰、MS/MS 峰、分子构象，或多种谱联合。每个任务页面说明解决什么问题、输入字段、输出字段，并展示真实运行案例。\n\n')
        notebook_index='# '+('Tutorials' if en else '教程')+'\n\n'+('Follow the tutorials to learn how to load spectra, call models, interpret their outputs and evaluate predictions. Each task includes explanatory text, code, saved results and figures.\n\n' if en else '通过教程学习如何加载谱图、调用模型、理解输出并评估预测。每个任务都配有说明、代码、运行结果和图。\n\n')
        notebook_index+='[SDK: actual NMR inference](sdk-inference.ipynb) · [SDK: training preflight](sdk-training-preflight.ipynb)\n\n'
        notebook_index+=f'[Dataset distributions / 数据分布](datasets-overview.ipynb)\n\n'
        notebook_index+='## Theory simulations / 理论模拟\n\n'
        for name,title in [('nmr-fourier','NMR FID and Fourier transform'),('nmr-inversion','NMR relaxation inversion'),('vibrational-broadening','IR and Raman broadening'),('ms-isotopes','MS isotope envelopes')]:
            notebook_index+=f'- [{title}](theory-{name}.ipynb)\n'
        notebook_index+='\n'
        gallery='# '+('Gallery' if en else '图集')+'\n\n'
        gallery+=('Browse model predictions, candidate structures and cleaned-data distributions. Open a task to inspect its inputs, outputs and tutorial.\n\n' if en else '浏览模型预测、候选结构与清洗后的数据分布。打开任务即可查看输入、输出和教程。\n\n')
        gallery+='<nav class="oms-gallery-nav" aria-label="Gallery categories">'+''.join(f'<a href="#gallery-{k}">{a if en else z}</a>' for k,a,z in GROUPS if k!='deferred')+'</nav>\n\n'
        for key,label,label_zh in GROUPS:
            members=[t for t in tasks if group(t)==key];heading=label if en else label_zh
            task_index+=f'## [{heading}]({key}.md)\n\n'
            task_index+='| Task / 任务 | Spectroscopy / 谱型 | Definition / 定义 |\n| --- | --- | --- |\n'
            for item in members:
                task_index+=f'| `{item.id}` | {", ".join(item.modalities)} | [{profile(item,en)[0]}]({item.id.replace(".","-")}.md) |\n'
            task_index+='\n'
            category=f'# {heading}\n\n'
            category+=('Choose a task to see its purpose, inputs, outputs, model call and examples.\n\n' if en else '选择任务，查看用途、输入输出、模型调用与示例。\n\n')
            category+='| Task / input → output | Task ID |\n| --- | --- |\n'
            notebook_index+=f'## {heading}\n\n'
            if key!='deferred':gallery+=f'<div id="gallery-{key}"></div>\n\n## {heading}\n\n<div class="oms-gallery-grid">\n'
            for task in members:
                slug=task.id.replace('.','-');title=profile(task,en)[0]
                category+=f'| [{title}]({slug}.md) | `{task.id}` |\n'
                notebook_index+=f'- [{title}]({slug}.ipynb)\n'
                if task.enabled:
                    gallery+=f'<figure><a href="tasks/{slug}.html"><img src="assets/gallery/{slug}.png" alt="{task.id}: actual model results" loading="lazy" width="2176" height="1088"></a><figcaption><strong><a href="tasks/{slug}.html">{title}</a></strong><span class="oms-caption-note">{caption(task,bundles[task.id],en)}</span><span class="oms-downloads"><a href="notebooks/{slug}.html">Notebook</a> · <a href="assets/gallery/{slug}.svg">SVG</a> · <a href="assets/gallery/{slug}.png">PNG</a> · <a href="assets/examples/{slug}.json">Data / 数据</a></span></figcaption></figure>\n'
            if key!='deferred':gallery+='</div>\n\n'
            notebook_index+='\n'
            files[f'tasks/{key}{suffix}.md']=category
        gallery+='[Corpus comparison](corpus-comparison.md) · [Controlled learning evaluations](learning-evidence.md)\n\n'
        gallery+='## '+('Dataset distributions' if en else '数据分布')+'\n\n'
        for slug in ('data-cleaned-nmr','data-cleaned-nmr-shifts','data-cleaned-experimental','data-cleaned-ms','data-cleaned-vibrational'):
            gallery+=f'[![{slug}](assets/gallery/{slug}.png)](data/index.md)\n\n[SVG](assets/gallery/{slug}.svg) · [Data](assets/cleaned-data-summary.json)\n\n'
        files[f'gallery{suffix}.md']=gallery
        files[f'tasks/index{suffix}.md']=task_index
        files[f'notebooks/index{suffix}.md']=notebook_index
        for task in tasks:
            slug=task.id.replace('.','-');b=bundles[task.id]
            title,purpose,method,metrics,limits,source=profile(task)
            if not en:
                from manual_profiles import profile as localized_profile
                title,purpose,method,metrics,limits,source=localized_profile(task,False)
            page=f'# {title}\n\n{purpose}\n\n'
            if task.id.startswith(('nmr.retrieval.', 'nmr.generation.')):
                page+=overlap_notice(en, '../')
            if not task.enabled:
                page+=('Deferred at the user’s request. No new model result is claimed.\n' if en else '按用户要求暂不推进，本轮不展示新的模型结果。\n')
            else:
                inputs,outputs=io_contract(task,en)
                page+='## '+('What goes in' if en else '输入是什么')+'\n\n'+inputs+'\n'
                page+='## '+('What comes out' if en else '输出是什么')+'\n\n'+outputs+'\n'
                page+='## '+('A real recorded example' if en else '真实运行案例')+'\n\n'
                page+=('Inspect the input, prediction and reference for the example below. Download the JSON for the complete numerical arrays and additional examples.\n\n' if en else '下面展示示例的输入、预测与参考。下载 JSON 可获取完整数值数组及更多示例。\n\n')
                page+=f'![{task.id} actual results](../assets/gallery/{slug}.png)\n\n[SVG](../assets/gallery/{slug}.svg) · [PNG](../assets/gallery/{slug}.png) · [Full input/output JSON](../assets/examples/{slug}.json)\n\n'
                if task.id in ['nmr.generation.hc','ms.forward.glacier','ms.forward.iceberg']:
                    for index in range(1,min(3,len(b['examples']))):
                        page+=f'### '+('Example' if en else '示例')+f' {index+1}\n\n'
                        page+=f'![{task.id} example {index+1}](../assets/gallery/{slug}-example-{index+1}.png)\n\n'
                page+='<details><summary>'+('Inspect the actual input and output fields' if en else '展开查看实际输入与输出字段')+'</summary>\n\n'
                page+='```json\n'+json.dumps(compact(b['examples'][0],4),ensure_ascii=False,indent=2)+'\n```\n\n</details>\n\n'
                page+='## '+('Actual evaluation results' if en else '实际评测结果')+'\n\n'+results_table(b,en)+'\n'
                page+='## '+('Model and method' if en else '模型与方法')+f'\n\n{method}\n\n{metrics}\n\n'
                if task.id=='vibrational.gap.ir_raman_hc':page+=viewer_html(en,'../')
                page+='## '+('Reproduce' if en else '复现方式')+'\n\n'
                page+=f'[Notebook with executed figures](../notebooks/{slug}.ipynb) · [Quick Start](../quickstart.md)\n\n'
                extra=' --fp-inference-root /path/to/frozen-fp --allow-cross-domain-diagnostic' if task.id in ['nmr.forward.19F','nmr.forward.31P'] else ''
                if task.id == 'nmr.hsqc.transpeaknet':extra = ' --transpeaknet-source /path/to/2dNMR'
                page+=f'```bash\npython -m openmolspec_bench run --workspace /path/to/OpenMolSpec \\\n  --tasks {task.id}{extra} --limit 8 --output results/{slug}-new.json\n```\n\n'
                page+=training_section(task,en)+'\n'
                if task.id.startswith('nmr.forward.'):
                    nucleus=task.id.rsplit('.',1)[-1]
                    domain='solid-state' if nucleus in ['19F','31P'] else 'liquid'
                    checkpoint='All-nucleus fold 0' if nucleus in ['11B','29Si'] else nucleus+' checkpoint' if nucleus in ['19F','31P'] else nucleus+' fold 0'
                    page+='\n| '+('Model setting | Value |' if en else '模型设置 | 值 |')+'\n| --- | --- |\n'
                    page+=f'| Checkpoint | NMRNet {checkpoint} |\n| Training domain | {domain} |\n| Shift unit | ppm |\n\n'
                page+='<details><summary>'+('Source reports and SHA-256 fingerprints' if en else '来源报告与 SHA-256 指纹')+'</summary>\n\n'
                for name,digest in b['source_hashes'].items():page+=f'- [{name}](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/{name}) — SHA-256 `{digest}`\n'
                page+='\n</details>\n\n'
                page+=f'\n[Model implementation / 模型实现]({source}) · [Model review / 模型检查](../model-audit.md)\n'
                page+=reference_list(reference_keys(task),en)
            if task.id in ('nmr.forward.19F', 'nmr.forward.31P'):
                page = solution_task_page(task.modalities[0], en)
            files[f'tasks/{slug}{suffix}.md']=page
            files[f'notebooks/{slug}{suffix}.ipynb']=json.dumps(notebook(task,language),ensure_ascii=False,indent=2)+'\n'
        # Retain protocol/publication details; these pages are maintained below.
        files[f'protocols{suffix}.md']=('# Evaluation protocols\n\n' if en else '# 评测协议\n\n')+('All published figures use actual recorded results. Each evidence JSON carries source report hashes. Execution success is separate from scientific validity. Small candidate-pool results, prepared-data split labels and matched-peak errors must not be described as independent generalization or atom-assignment accuracy.\n\nComplete IR/Raman/H/C input and missing-channel ablations are reported separately. Gap units are converted once from Hartree to eV. MS scores compare with all observed peaks under explicit acquisition conditions. The frozen-model figures contain no fitted calibration. A separate two-record-per-split SDK training integration check completed one encoder and one generator step with save/reload verification; it is not a performance benchmark.\n\n' if en else '所有公开结果图来自实际记录。证据 JSON 保留来源报告哈希。执行成功与科学有效性分开判断；小候选池、准备数据的 split 标签、峰匹配误差，不能宣传成独立泛化或实验原子指认准确率。\n\n完整 IR/Raman/H/C 输入与缺通道消融分别报告。Gap 从 Hartree 到 eV 仅转换一次。MS 在明确采集条件下与全部实测峰比较。冻结模型图没有拟合校准。另有独立的 SDK 训练接口检查：每个原始划分取两个记录，编码器与生成器各训练一步并验证保存重载；这不是性能基准。\n\n')+'[Dataset definitions](datasets.md) · [Model-by-model audit](model-audit.md)\n'
        files[f'publication{suffix}.md']=('# Publication status\n\n' if en else '# 发布状态\n\n')+('[English](https://openmolspec.readthedocs.io/en/latest/) · [简体中文](https://openmolspec.readthedocs.io/en/latest/zh/index.html)\n\n')+('Read the Docs builds `release/openmolspec-v1` with the root `.readthedocs.yaml`, Sphinx and the classic RTD theme. The site includes categorized tasks, a real-results gallery, dataset distributions, model review and 82 tutorials, including SDK inference, training preparation and theory simulations. Notebook publication never executes model code.\n\n' if en else 'Read the Docs 使用根目录 `.readthedocs.yaml` 构建 `release/openmolspec-v1` 分支，采用 Sphinx 与经典 RTD 主题。站点包括分类任务、真实结果图册、数据分布、模型与训练说明及 82 份教程（含暂停任务说明和数据分布 notebook）。发布构建不执行模型代码。\n\n')+'```bash\npython scripts/build_bilingual_docs.py --check\npython scripts/build_readthedocs.py --output site --strict\npython scripts/publish_readthedocs.py --apply --project openmolspec --wait 600\n```\n\n'+('Publish only after pushing the corresponding Git commit. The publication script verifies the exact remote commit and finished RTD build; public pages are checked separately.\n' if en else '先推送对应 Git 提交，再发布。发布脚本检查远端精确提交与完成的 RTD 构建，公开页面另行验证。\n')
    for suffix,en in [('',True),('.zh',False)]:
        files[f'protocols{suffix}.md']+='\n'+overlap_notice(en)
    return {name:(content.rstrip()+'\n' if name.endswith('.md') else content) for name,content in files.items()}
