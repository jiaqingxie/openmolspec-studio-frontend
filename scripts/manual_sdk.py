"""Practical SDK, FAQ and bibliography pages."""
import json
from pathlib import Path
from manual_citations import REFERENCES,markdown as references
from manual_data import table

ROOT=Path(__file__).resolve().parents[1]


def pages(en):
    t=lambda a,b:a if en else b;suffix='' if en else '.zh';out={}
    text='# Python SDK\n\n'
    text+=t('OpenMolSpec provides streaming datasets, spectroscopy model classes, training plans and benchmark runners. This guide explains how these interfaces fit together. Follow [Quick start](quickstart.md) for installation and your first prediction.\n\n','OpenMolSpec 提供流式数据集、谱学模型类、训练计划和评测入口。本节介绍这些接口如何配合使用。安装与首次预测步骤见[快速开始](quickstart.md)。\n\n')
    text+='## '+t('Dataset objects','数据集对象')+'\n\n'
    text+='```python\nfrom openmolspec.dataset import molspectra, list_datasets\n\nprint([card["name"] for card in list_datasets()])\ndata = molspectra("opendatalab_nmr", root="data/nmr")\nsplits = data.get_split()\nrows = splits["test"].head(3)\npaired = splits["train"].select(modalities=["1H", "13C"], limit=100)\nprint(data.summary())\nprint(data.verify())\n```\n\n'
    text+=t('`MolecularSpectra` groups the named splits. Each `SpectraSplit` reads records as you iterate, keeping memory usage bounded. `select` combines channel filters and a row limit; `head` reads a small list. `verify` checks the complete local files against the dataset version.\n\n','`MolecularSpectra` 按名称组织划分；`SpectraSplit` 在迭代时逐条读取，避免把全库载入内存。`select` 组合通道筛选与行数上限，`head` 返回少量记录；`verify` 核对完整本地文件与数据版本。\n\n')
    cards=json.loads((ROOT/'src/openmolspec/assets/datasets.json').read_text())
    descriptions={
        'transpeaknet_hsqc_test':t('Author HSQC test ZIP with 479 experimental spectra and expert carbon assignments.','作者发布的 HSQC 测试 ZIP，含 479 张实验谱及专家碳原子指认。'),
        'opendatalab_nmr':t('Cleaned experimental H/C NMR.','清洗后的实验 H/C NMR。'),
        'opendatalab_nmr_prepared':t('Original prepared H/C files.','原始准备版 H/C 文件。'),
        'nmrspec_test':'NMRSpec / NMRTrans', 'nmrgym_test':'NMRGym',
        'nmrexp_exp_10k':t('Prepared NMRexp evaluation view.','整理后的 NMRexp 评测视图。'),
        'patent_test_10k':t('OpenDataLab H/C evaluation subset.','OpenDataLab H/C 评测子集。'),
        'openspec_test':t('Computed multimodal spectra and properties.','计算多谱及分子性质。'),
        'massspecgym_test':t('Prepared MS/MS evaluation CSV.','整理后的 MS/MS 评测 CSV。'),
        'massspecgym_1_5':t('MassSpecGym v1.5 TSV with source folds.','保留原划分的 MassSpecGym v1.5 TSV。')}
    text+=table([t('Registered name','注册名称'),'Format',t('Description','说明')],[(f'`{card["name"]}`',f'`{card["format"]}`',descriptions.get(card['name'],t('Cleaned experimental ','清洗后的实验 ')+card['name'].removeprefix('opendatalab_').upper())) for card in cards])
    text+=t('Download the [TransPeakNet test ZIP](https://github.com/siriusxiao62/2dNMR/tree/main/data_annotation) from the authors. The reader preserves the original SMILES order and exposes the measured `hsqc_peaks` as [¹³C ppm, ¹H ppm] pairs and `hsqc_assignments` as per-carbon annotations. The full training and validation spectra are available on request from the authors.\n\n','从作者仓库下载 [TransPeakNet 测试 ZIP](https://github.com/siriusxiao62/2dNMR/tree/main/data_annotation)。读取器保留原始 SMILES 顺序，`hsqc_peaks` 是 [¹³C ppm, ¹H ppm] 坐标对，`hsqc_assignments` 是按碳原子整理的指认。完整训练谱和验证谱需向作者申请。\n\n')
    text+='```python\nhsqc = molspectra("transpeaknet_hsqc_test", root="HSQC_Annotation_TestData.zip")\nprint(hsqc.verify())\nrecord = hsqc["test"].select(modalities=["HSQC"]).head(1)[0]\nprint(record["smiles"], record["hsqc_peaks"])\n```\n\n'
    text+=t('Each record retains its source fields. `_openmolspec` adds the dataset, domain, split, file locator and detected channels. The [Data guide](data/index.md) describes numerical fields, units, acquisition conditions and cleaned counts.\n\n','每条记录保留来源字段，`_openmolspec` 补充数据集、数据域、划分、文件位置与通道。数值字段、单位、采集条件及清洗后数量见[数据指南](data/index.md)。\n\n')
    text+='## '+t('Import your own measurements','导入自己的测量')+'\n\n'
    text+='```python\nfrom openmolspec.dataset import MolecularSpectra\n\ncustom = MolecularSpectra.from_jsonl(\n    splits={"train": "my-train.jsonl", "val": "my-val.jsonl"},\n    name="my_measurements", domain="experimental")\nprint(custom["train"].head(1))\n```\n\n'
    text+=t('Use the H/C JSONL schema for `format="nmr_jsonl"`. For heteronuclear shifts, optical peak lists or general spectral dictionaries, choose `format="jsonl"`. The reader recognizes `nucleus` with `peaks_ppm`, `modality` with `wavenumber_cm1`, and numerical mass-spectral `peaks`.\n\n','H/C JSONL 使用 `format="nmr_jsonl"`；杂核位移、光学峰表或一般谱字典使用 `format="jsonl"`。读取器识别 `nucleus` 与 `peaks_ppm`、`modality` 与 `wavenumber_cm1`，以及数值质谱 `peaks`。\n\n')
    text+='## '+t('Model interfaces','模型接口')+'\n\n'
    text+=table(['Class',t('Input → output','输入 → 输出'),t('Training route','训练方式')],[
        ('`NMRNet`','SMILES → ¹H/¹³C shifts; structure + peaks → assignments','[NMRNet](tasks/nmr-forward-13C.md)'),
        ('`NMRTransformer(stage="align")`',t('NMR + candidates → ranking','NMR + 候选结构 → 排名'),'`training_plan`, `fit`'),
        ('`NMRTransformer(stage="generate")`',t('NMR + formula → molecular structures','NMR + 分子式 → 分子结构'),'`training_plan`, `fit`'),
        ('`GapModel`','IR + Raman + H/C → gap (eV)','[openSpec](tasks/vibrational-gap-ir_raman_hc.md)'),
        ('`Vib2Mol`',t('Spectra → structures or candidate ranking','光谱 → 分子结构或候选排序'),'[openSpec](tasks/vibrational-generation-hc.md)'),
        ('`MSPredictor`',t('Molecule + acquisition conditions → MS/MS','分子 + 采集条件 → MS/MS'),'[ms-pred](tasks/ms-forward-glacier.md)')])
    text+=t('Select each model’s dependencies through `python=`. This lets a lightweight OpenMolSpec client call the environment containing the author model implementation and its weights.\n\n','通过 `python=` 指定各模型的依赖环境，使 OpenMolSpec 客户端可以调用安装了作者实现及权重的解释器。\n\n')
    text+='### NMRNet\n\n'
    text+='```python\nfrom openmolspec.model import NMRNet\n\nmodel = NMRNet.from_pretrained(\n    "models", nucleus="13C", python="/path/to/nmr-env/bin/python")\nprediction = model.predict("CCO")\nprint(prediction["records"][0]["atom_indices"])\nprint(prediction["records"][0]["prediction_ppm"])\nassignments = model.assign("CCO", [18.2, 58.3], tolerance_ppm=5.0)\n```\n\n'
    text+=t('The model directory contains `nmrnet/nmrnet-orig` and `nmrnet/weights`. The liquid-state fold-0 adapter predicts H/C shifts on CPU. Atom indices use the zero-based RDKit graph after adding hydrogens. The assignment output links measured peak indices to predicted atom sites and includes residuals and alternative matches.\n\n','模型目录包含 `nmrnet/nmrnet-orig` 与 `nmrnet/weights`。液相 fold-0 接口在 CPU 上预测 H/C 位移。原子编号采用 RDKit 加氢后的 0 起始顺序。指认结果把实测峰编号关联到预测原子位点，并提供残差与备选匹配。\n\n')
    text+='### NMRTransformer\n\n'
    text+='```python\nfrom openmolspec.model import NMRTransformer\n\nquery = data["test"].head(1)[0]\naligner = NMRTransformer.from_pretrained(\n    "alignment.pt", stage="align", python="/path/to/nmr-env/bin/python")\nranking = aligner.retrieve(query, ["CCO", "CCCO", "COC"], top_k=3)\ngenerator = NMRTransformer.from_pretrained(\n    "generation.pt", stage="generate",\n    python="/path/to/nmr-env/bin/python")\ncandidates = generator.predict(query, beam_size=5)\n```\n\n'
    text+=t('Retrieval ranks the supplied molecular candidates from their spectral/molecular embeddings. Generation uses the NMR channels and the known `formula` in the query. Returned candidates include SMILES, validity, formula agreement and model scores.\n\n','检索利用谱与分子嵌入为给定候选排序；生成使用查询中的 NMR 通道和已知 `formula`。返回候选包括 SMILES、有效性、分子式一致性与模型分数。\n\n')
    text+='### '+t('Vibrational and property models','振动谱与性质模型')+'\n\n'
    text+='```python\nimport json\nfrom pathlib import Path\nfrom openmolspec.model import GapModel, Vib2Mol\n\ninputs = json.loads(Path(\n    "documentation/assets/harness/vibrational-request.json").read_text())["inputs"]\ngap_model = GapModel(root="openspec-models", python="/path/to/openspec-env/bin/python")\ngap = gap_model.predict(inputs)\nstructure_model = Vib2Mol(root="openspec-models", python="/path/to/openspec-env/bin/python")\nstructures = structure_model.predict(inputs)\n```\n\n'
    text+=t('IR and Raman inputs each contain 1,024 normalized intensities on the 400–4,000 cm⁻¹ grid. `nmr_h` and `nmr_c` contain ppm shifts using the checkpoint reference. `GapModel` returns energy gaps in eV. `Vib2Mol` generates molecular candidates; its `retrieve` method ranks a supplied candidate library.\n\n','IR 和 Raman 各包含 400–4,000 cm⁻¹ 网格上的 1,024 点归一化强度。`nmr_h` 与 `nmr_c` 保存采用权重参考标准的 ppm 位移。`GapModel` 返回 eV 能隙；`Vib2Mol` 生成分子候选，`retrieve` 则为给定候选库排序。\n\n')
    text+='### '+t('Mass-spectrum prediction','质谱预测')+'\n\n'
    text+='```python\nfrom openmolspec.model import MSPredictor\n\nms = MSPredictor(model="glacier", source="ms-pred",\n    weights="glacier-weights", python="/path/to/ms-env/bin/python")\nprediction = ms.predict(smiles="CCO", adduct="[M+H]+",\n    collision_energy=20.0, instrument="Orbitrap")\nprint(prediction)\n```\n\n'
    text+=t('Supply the molecular structure, adduct, collision energy and instrument used for the desired spectrum. Choose `model="iceberg"` for the ICEBERG adapter. See the task guides for model assets and spectral comparison settings.\n\n','提供目标谱对应的分子结构、加合物、碰撞能与仪器。ICEBERG 接口使用 `model="iceberg"`。模型文件与谱比较设置见任务指南。\n\n')
    text+='## '+t('Training and checkpoint reuse','训练与权重复用')+'\n\n'
    text+='```python\nfrom openmolspec.training import prepare_nmr_training\n\nprepared = prepare_nmr_training(custom["train"], custom["val"], "prepared-nmr")\nmodel = NMRTransformer(stage="align", device="cpu")\nplan = model.training_plan(\n    prepared, run_dir="runs/my-encoder", epochs=10, batch_size=32)\nprint(plan.describe())\nprint(plan.validate())\ntrained = model.fit(plan)\nmodel.save_config("trained-model.json")\nrestored = NMRTransformer.from_config("trained-model.json")\n```\n\n'
    text+=t('Preparation validates the molecular formula, nucleus labels and train/validation identity separation. `fit` launches the configured training stage and selects the best validation checkpoint. For a generator, use `stage="generate"` and supply its alignment checkpoint. The [training tutorial](notebooks/sdk-training-preflight.ipynb) explains every preparation step and inspects saved training/checkpoint results.\n\n','准备阶段检查分子式、核种与训练／验证身份分离。`fit` 启动指定阶段训练，并选择最佳验证 checkpoint。生成器使用 `stage="generate"` 并指定对齐权重。[训练教程](notebooks/sdk-training-preflight.ipynb)解释准备步骤，并检查保存的训练与权重结果。\n\n')
    text+='## '+t('Evaluation and numerical inversion','评测与数值反演')+'\n\n'
    text+='```python\nfrom openmolspec.task import list_tasks\nfrom openmolspec.benchmark import Benchmark\n\nprint(list_tasks(group="nmr"))\nbenchmark = Benchmark(workspace="/path/to/OpenMolSpec",\n    python="/path/to/nmr-env/bin/python", alignment_checkpoint="alignment.pt", nmr_python="/path/to/nmr-env/bin/python")\nreport = benchmark.run("nmr.retrieval.hc.s2m", datasets=["nmrspec_test"],\n    limit=64, output="results/my-retrieval.json")\n```\n\n'
    text+=t('Use [Benchmarks](benchmarks.md) for task metrics and experiment configurations. The inversion module provides nonnegative regularized recovery of relaxation and diffusion distributions; see [NMR inversion](inversion/index.md). The complete [API reference](api-reference/index.md) includes signatures, parameters and return values.\n','任务指标与实验配置见[基准评测](benchmarks.md)。反演模块提供弛豫、扩散分布的非负正则化恢复，见 [NMR 反演](inversion/index.md)。完整 [API 参考](api-reference/index.md)列出签名、参数与返回值。\n')
    out[f'api{suffix}.md']=text+references(['openmolspec','nmrnet','nmrtrans','openspec','glacier','iceberg','inversions'],en)

    text='# '+t('Common workflows','常用流程')+'\n\n'
    for title,title_zh,body,body_zh in [
        ('Choose your input','选择输入','Use molecular structures for spectrum prediction, structures plus peaks for assignment, spectra for retrieval/generation, and time-domain traces for numerical inversion. [Tasks](tasks/index.md).','结构用于谱预测，结构与峰用于指认，谱用于检索或生成，时域信号用于数值反演。见[任务](tasks/index.md)。'),
        ('Read a peak list','读取峰表','NMR uses ppm positions; MS uses m/z–intensity pairs; IR and Raman use cm⁻¹ positions with intensities where supplied. To produce dense optical inputs, save the grid and broadening parameters with the array.','NMR 使用 ppm 位置，MS 使用 m/z–强度对，IR/Raman 使用 cm⁻¹ 位置及可用强度。构建密集光谱时，将网格和展宽参数与数组一起保存。'),
        ('Select model environments','选择模型环境','Pass the interpreter containing the model dependencies through `python=`. Set the checkpoint or model-root path on the corresponding model class. [SDK](api.md).','通过 `python=` 指定安装了模型依赖的解释器，在模型类中指定 checkpoint 或模型根目录。见 [SDK](api.md)。'),
        ('Train with your own data','训练自己的数据','Import named train/validation files with `MolecularSpectra.from_jsonl`, prepare them with `prepare_nmr_training`, create a training plan and call `model.fit(plan)`.','使用 `MolecularSpectra.from_jsonl` 导入训练／验证文件，再通过 `prepare_nmr_training` 准备数据，创建训练计划并调用 `model.fit(plan)`。'),
        ('Create dataset splits','创建数据划分','Use `split_records` with grouped random or scaffold assignment. Inspect the manifest for split counts, group policy and file hashes. [Splits](data/splits.md).','使用 `split_records` 按连接关系随机分组或按骨架划分，再从 manifest 查看数量、分组策略和文件哈希。见[划分](data/splits.md)。'),
        ('Map predictions to atoms','把预测映射到原子','NMRNet uses zero-based RDKit AddHs atom indices. MAGMa returns indices on its `engine_smiles` graph. Keep the returned graph with the indices when drawing annotations.','NMRNet 使用 RDKit AddHs 后的 0 起始原子编号，MAGMa 使用 `engine_smiles` 图上的编号。绘制指认时同时保留返回的图和编号。'),
        ('Run a tutorial','运行教程','Clone the release branch and install `requirements-docs-examples.txt`. Scientific plots use Arial; set `OPENMOLSPEC_ARIAL_FONT` to the TTF file on your machine. Configure model paths for the SDK inference notebook.','克隆 release 分支并安装 `requirements-docs-examples.txt`。科学绘图使用 Arial，可通过 `OPENMOLSPEC_ARIAL_FONT` 指定本机 TTF；SDK 推理教程另外配置模型路径。'),
        ('Connect an agent','连接 Agent','Use Spectra Harness from Python, JSON CLI requests or MCP. Discover tasks, validate the request, execute it, then read `result`. [Agent Harness](harness.md).','通过 Python、JSON 命令行请求或 MCP 使用 Spectra Harness。先发现任务、验证请求，再执行并读取 `result`。见 [Agent Harness](harness.md)。')]:
        text+='## '+(title if en else title_zh)+'\n\n'+(body if en else body_zh)+'\n\n'
    out[f'faq{suffix}.md']=text.rstrip()+'\n'
    text='# '+t('Citations','引用来源')+'\n\n'
    text+=t('Cite OpenMolSpec for the software workflow and the original resources used in your analysis. Dataset and task pages also include their references at the bottom.\n\n','使用软件流程时引用 OpenMolSpec，并引用分析中使用的原始资源。数据集和任务页面底部也列出相应参考文献。\n\n')
    text+=references(REFERENCES.keys(),en)
    out[f'citations{suffix}.md']=text
    return out
