"""Complete task and training-configuration benchmark catalogue."""
import json
from pathlib import Path
from documentation_content import GROUPS,group,results_table
from documentation_evidence import load_evidence
from manual_profiles import profile
from manual_data import table
from manual_citations import markdown as references

ROOT=Path(__file__).resolve().parents[1]


def pages(tasks,en):
    t=lambda a,b:a if en else b;suffix='' if en else '.zh';out={}
    configs=json.loads((ROOT/'documentation/assets/benchmarks/catalog.json').read_text())['configured_experiments']
    text='# '+t('Benchmarks','基准评测')+'\n\n'
    text+=t('OpenMolSpec defines benchmark tasks for NMR, MS, vibrational and multimodal spectroscopy. This catalogue includes every active task, its saved evaluation results and the configured training experiments.\n\n','OpenMolSpec 为 NMR、质谱、振动光谱与多谱联合定义了基准任务。本目录列出全部活跃任务、保存的评测结果，以及训练实验配置。\n\n')
    text+='## '+t('Task benchmarks','任务基准')+'\n\n'
    rows=[]
    for family,label,zh in GROUPS:
        active=[task for task in tasks if task.enabled and group(task)==family]
        if not active:continue
        rows.append((f'[{label if en else zh}](benchmarks/{family}.md)',len(active),t('Definitions, inputs, metrics and recorded results.','任务定义、输入、指标与运行结果。')))
        child='# '+(label if en else zh)+' benchmarks\n\n'
        child+=t('The sections below give each task definition and the results from its recorded evaluation runs. Open the task guide for model calls and full input/output examples.\n\n','下面按任务列出定义及保存的评测结果。模型调用和完整输入输出示例见相应任务指南。\n\n')
        for task in active:
            title,purpose,method,metrics,_,_=profile(task,en);bundle=load_evidence(task.id);slug=task.id.replace('.','-')
            child+=f'## {title}\n\n`{task.id}`\n\n{purpose}\n\n{metrics}\n\n'
            child+=f'[Task guide](../tasks/{slug}.md) · [Tutorial](../notebooks/{slug}.ipynb) · [Predictions](../assets/examples/{slug}.json)\n\n'
            for index,run in enumerate(bundle['runs'],1):
                settings={k:run[k] for k in ['dataset','counts','sampling','seed','given_formula','given_nmr','beam_size'] if k in run and run[k] is not None}
                child+=(t('Run settings: ','运行设置：')+'; '.join(f'`{key}={json.dumps(value,ensure_ascii=False)}`' for key,value in settings.items())).rstrip()+'\n\n'
                child+=results_table({'runs':[run]},en)+'\n'
        out[f'benchmarks/{family}{suffix}.md']=child+references(['openmolspec','nmrnet','nmrtrans'] if family=='nmr' else ['massspecgym'] if family=='ms' else ['openmolspec','qme14s','qm9s'],en)
    text+=table([t('Family','类别'),t('Tasks','任务数'),t('Contents','内容')],rows)
    text+='## '+t('Training benchmark configurations','训练基准配置')+'\n\n'
    text+=t('The [production benchmark results](benchmarks/production.md) report the saved 200k/1M experiments for Hessians, H/C shifts, response tensors, molecular properties and structure generation.\n\n','[生产基准结果](benchmarks/production.md)列出保存的 200k／1M 实验，包括 Hessian、H/C 位移、响应张量、分子性质与结构生成。\n\n')
    text+=t('The configuration catalogue contains 53 YAML experiments. They specify the input channels, targets, architecture, dataset version, random seed and optimizer budget. [All configurations](benchmarks/training.md).\n\n','配置目录包含 53 个 YAML 实验，记录输入通道、目标、架构、数据版本、随机种子和优化器预算。[查看全部配置](benchmarks/training.md)。\n\n')
    text+=table([t('Benchmark family','基准类别'),t('Input → output','输入 → 输出'),t('Model','模型')],[
        ('structure2property',t('3D structure → energy, HOMO, LUMO, gap, dipole and ZPVE','三维结构 → 能量、HOMO、LUMO、能隙、偶极矩和零点振动能'),'Equiformer-v3'),
        ('structure2spectrum',t('3D structure → IR/Raman arrays','三维结构 → IR/Raman 数组'),'Equiformer-v3'),
        ('structure2observables',t('3D structure → scalar and tensor observables','三维结构 → 标量与张量可观测量'),'Equiformer-v3'),
        ('structure2nmr',t('3D structure → atomwise H/C shifts','三维结构 → 逐原子 H/C 化学位移'),'Equiformer-v3'),
        ('structure2hessian',t('3D structure → Hessian tensor blocks','三维结构 → Hessian 张量块'),'Equiformer-v3'),
        ('structure2response',t('3D structure → dipole/polarizability derivatives','三维结构 → 偶极矩／极化率导数'),'Equiformer-v3'),
        ('spectrum2structure',t('Spectra → molecular structure','光谱 → 分子结构'),'Vib2Mol'),
        ('spectrum2property',t('Spectra → quantum-chemical property','光谱 → 量子化学性质'),'Vib2Conf / shared spectroscopy Transformer'),
        ('spectrum2conformer',t('Spectra → three-dimensional conformer; protocol definition','光谱 → 三维构象；协议定义'),'Vib2Conf')])
    text+='## '+t('Metrics','评测指标')+'\n\n'
    text+=t('Regression tasks report MAE and RMSE in the target unit. Retrieval reports Recall@k and mean reciprocal rank for the selected candidate pool. Structure generation reports canonical top-k accuracy and valid-SMILES rate. Spectral prediction compares numerical intensities using cosine and entropy similarity.\n\n','回归任务以目标单位报告 MAE 与 RMSE；检索报告给定候选池上的 Recall@k 和平均倒数排名；结构生成报告规范化结构 top-k 准确率及有效 SMILES 比例；谱预测使用余弦和熵相似度比较数值强度。\n\n')
    text+=r'$$\mathrm{MAE}=\frac1N\sum_{i=1}^{N}|\hat y_i-y_i|,\qquad \mathrm{RMSE}=\sqrt{\frac1N\sum_{i=1}^{N}(\hat y_i-y_i)^2}.$$'+'\n\n'
    text+=r'$$\mathrm{Recall@}k=\frac1N\sum_i\mathbf{1}[r_i\leq k],\qquad \mathrm{MRR}=\frac1N\sum_i\frac1{r_i}.$$'+'\n\n'
    text+='## '+t('Run a benchmark','运行评测')+'\n\n'
    text+='```bash\npython -m openmolspec_bench list\npython -m openmolspec_bench run --workspace /path/to/OpenMolSpec \\\n  --tasks nmr.retrieval.hc.s2m nmr.generation.hc \\\n  --alignment-checkpoint /path/to/alignment.pt \\\n  --generation-checkpoint /path/to/generation.pt \\\n  --limit 64 --sampling reservoir --seed 42 --output results/nmr.json\n```\n\n'
    text+=t('Choose the required model assets using the task guide. The result JSON records predictions, target values, dataset settings, metrics and model fingerprints.\n\n','按任务指南指定所需模型文件。结果 JSON 保存预测、目标值、数据设置、指标与模型指纹。\n\n')
    text+='## '+t('Additional task definitions','其他任务定义')+'\n\n'
    text+=t('Molecular formula prediction, spectroscopy QA and SpectraLLM generation are listed in the task registry as deferred.\n','分子式预测、谱学 QA 与 SpectraLLM 生成在任务注册表中列为暂缓任务。\n')
    out[f'benchmarks{suffix}.md']=text+references(['openmolspec','nmrnet','nmrtrans','nmrgym','massspecgym','qme14s','qm9s'],en)

    text='# '+t('Training benchmark configurations','训练基准配置')+'\n\n'
    text+=t('Download the [benchmark source archive](../assets/benchmarks/openmolspec-benchmark-source.zip), unpack it and work from the extracted directory. The archive includes the launcher, model adapters, data-preparation modules and all 53 configurations. [SHA-256 manifest](../assets/benchmarks/benchmark-source-manifest.json).\n\n','下载[基准训练源码包](../assets/benchmarks/openmolspec-benchmark-source.zip)，解压后进入目录。源码包包含启动器、模型适配器、数据准备模块和全部 53 份配置。[SHA-256 清单](../assets/benchmarks/benchmark-source-manifest.json)。\n\n')
    text+='```bash\nunzip openmolspec-benchmark-source.zip\ncd openmolspec-benchmarks\npython -m benchmarks --help\npython -m benchmarks run \\\n  --config benchmarks/configs/structure2property/equiformer_v3.yaml --dry-run\n```\n\n'
    text+=t('Download a YAML file to inspect the exact targets, architecture and training budget. Configurations are grouped by task family. The production training workflow reads them with `python -m benchmarks run --config <file>`.\n\n','下载 YAML 文件可查看准确的训练目标、架构和预算。配置按任务类别组织，生产训练流程使用 `python -m benchmarks run --config <file>` 读取。\n\n')
    for family in sorted({row['family'] for row in configs}):
        text+=f'## {family}\n\n'
        rows=[]
        for row in configs:
            if row['family']!=family:continue
            budget=row['training'];steps=budget.get('max_steps');epochs=budget.get('epochs');schedule=f'{steps:,} steps' if steps else f'{epochs} epochs' if epochs else 'configuration'
            rows.append((f'[{row["config"].split("/")[-1]}](../assets/benchmarks/configs/{row["config"]})',row['modality'],', '.join(row['targets']),row['release'],schedule))
        text+=table(['Configuration','Input','Targets','Data release','Budget'],rows)
    out[f'benchmarks/training{suffix}.md']=text+references(['openmolspec','qme14s','qm9s'],en)
    report_path=ROOT/'docs/figures/openmolspec_benchmark_overview.json'
    report=json.loads(report_path.read_text())
    import hashlib
    out['assets/benchmarks/production-results.json']=json.dumps({'source':'docs/figures/openmolspec_benchmark_overview.json','source_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),'metrics':report},indent=2)+'\n'
    text='# '+t('Production benchmark results','生产基准结果')+'\n\n'
    text+=t('These tables reproduce the saved production benchmark overview. The training-size labels identify the 200k and one-million-molecule configurations. [Download the numerical report](../assets/benchmarks/production-results.json) with its source checksum.\n\n','下表读取保存的生产基准汇总。训练规模标签对应 200k 与一百万分子配置。[下载数值报告](../assets/benchmarks/production-results.json)及来源校验和。\n\n')
    text+='## '+t('Structure to H/C chemical shifts','结构到 H/C 化学位移')+'\n\n'
    text+=table(['Training size','¹H MAE (ppm)','¹H RMSE (ppm)','¹³C MAE (ppm)','¹³C RMSE (ppm)'],[(size,*[f'{row[key]:.6g}' for key in ['MAE_H','RMSE_H','MAE_C','RMSE_C']]) for size,row in report['structure2nmr'].items()])
    first=next(iter(report['structure2nmr'].values()))
    text+=t('Scored target atoms: ','计分目标原子：')+f'¹H {first["count_H"]:,}; ¹³C {first["count_C"]:,}.\n\n'
    text+='## '+t('Hessian to vibrational frequencies','Hessian 到振动频率')+'\n\n'
    text+=table(['Model / reference','Frequency MAE (cm⁻¹)'],[(name,f'{value:.6g}') for name,value in report['hessian_frequency_mae_cm1'].items()])
    text+='## '+t('Structure to response tensors','结构到响应张量')+'\n\n'
    rows=[]
    for size,targets in report['structure2response'].items():
        for target,row in targets.items():
            rows.append((size,target,row['unit'],f'{row["test"]["MAE_"+target]:.6g}',f'{row["test"]["RMSE_"+target]:.6g}',f'{row["test_records"]:,}'))
    text+=table(['Training size','Target','Unit','Test MAE','Test RMSE','Test records'],rows)
    text+='## '+t('Spectra to molecular properties','光谱到分子性质')+'\n\n'
    properties=report['spectrum2property_mae']
    text+=table(['Property','Unit','200k MAE','1M MAE'],[(name,unit,f'{a:.6g}',f'{b:.6g}') for name,unit,a,b in zip(properties['properties'],properties['units'],properties['200k'],properties['1000k'])])
    text+='## '+t('Spectra to molecular structures','光谱到分子结构')+'\n\n'
    generation=report['vib2mol_generation']
    text+=table(['Training size / channels',*[f'Top-{k}' for k in generation['ranks']]],[(name,*[f'{value:.2%}' for value in values]) for name,values in generation.items() if name!='ranks'])
    text+=t('`full` uses IR, Raman and H/C NMR. `ir` and `ir_raman` identify the corresponding input-channel experiments. [Training configurations and source](training.md).\n','`full` 使用 IR、Raman 与 H/C NMR；`ir` 和 `ir_raman` 分别标识相应的输入通道实验。[训练配置与源码](training.md)。\n')
    out[f'benchmarks/production{suffix}.md']=text+references(['openmolspec','openspec','qme14s','qm9s'],en)
    for name,title in [('protocols',t('Evaluation protocols','评测协议')),('publication',t('Documentation and releases','文档与发布'))]:
        out[f'{name}{suffix}.md']='---\norphan: true\n---\n\n# '+title+'\n\n'+t('See [Benchmarks](benchmarks.md) for task protocols and results, [Data](data/index.md) for the datasets, and [Quick start](quickstart.md) for installation.\n','任务协议与结果见[基准评测](benchmarks.md)，数据说明见[数据](data/index.md)，安装步骤见[快速开始](quickstart.md)。\n')
    return out
