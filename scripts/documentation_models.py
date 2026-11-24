"""Task-specific model use, objectives and adaptation instructions."""


def training_section(task,en):
    id_=task.id
    if not task.enabled:return ''
    title='## Call and adapt this model' if en else '## 调用模型与微调'
    if id_ == 'nmr.hsqc.transpeaknet':
        intro = ('From the OpenMolSpec source checkout, install the HSQC dependencies and get the frozen author release.' if en else
                 '在 OpenMolSpec 源码目录中安装 HSQC 依赖，并下载作者发布的代码、权重和测试集。')
        commands = """python -m pip install -e '.[hsqc]'
git clone https://github.com/siriusxiao62/2dNMR.git
git -C 2dNMR checkout 2e93db82a9d627ac01109474e9b6e594065e3d56
python -m openmolspec_bench run --tasks nmr.hsqc.transpeaknet --transpeaknet-source 2dNMR --limit 479 --output results/hsqc-local.json"""
        return title + '\n\n' + intro + '\n\n```bash\n' + commands + '\n```\n'
    if id_.startswith(('nmr.retrieval.','nmr.generation.')):
        generate='.generation.' in id_;stage='generate' if generate else 'align'
        code=f"from openmolspec.model import NMRTransformer\nmodel = NMRTransformer.from_pretrained(\n    '/path/to/checkpoint.pt', stage='{stage}',\n    python='/path/to/nmr-env/bin/python')\n"
        code+=("result = model.predict(query, beam_size=5)\n" if generate else "result = model.retrieve(query, candidate_smiles, top_k=10)\n") if not id_.endswith('.m2s') else f"from openmolspec.benchmark import Benchmark\nbenchmark = Benchmark(workspace='/path/to/workspace',\n    python='/path/to/sdk-env/bin/python',\n    alignment_checkpoint='/path/to/checkpoint.pt',\n    nmr_python='/path/to/nmr-env/bin/python')\nresult = benchmark.run('{id_}', output='m2s-results.json', limit=32)\n"
        code+="plan = model.training_plan(\n    'prepared-nmr', run_dir='runs/my-model', epochs=10, batch_size=32"
        if generate:code+=",\n    alignment_checkpoint='/path/to/alignment.pt'"
        code+=")\nprint(plan.validate())\n# trained = model.fit(plan)\n"
        text=('Prepare disjoint train/validation records with `prepare_nmr_training`; supply an alignment checkpoint for the generator. Use H/C masks to define available inputs and choose model selection criteria on validation data. Pretrained initialization restores model weights. [Data preparation](../api.md) provides the complete workflow.' if en else
              '先用 `prepare_nmr_training` 准备相互独立的 train/val；生成阶段需要对齐 checkpoint。用 H/C 掩码定义输入通道，在验证集选择模型。已有权重可用于初始化。[数据准备与训练指南](../api.md)给出完整流程。')
        loss=(r'$$L_{\rm LM}=-\frac{1}{N_{\rm token}}\sum_t\log p_\theta(y_t\mid y_{<t},x,F).$$' if generate else
              r'$$L_{\rm align}=\tfrac12[\mathrm{CE}(SM^\top/\tau,I)+\mathrm{CE}(MS^\top/\tau,I)]+\lambda_{\rm ITM}L_{\rm match}.$$')
        detail=('Generation uses token cross-entropy; an optional joint alignment term follows its configured weight. Alignment uses normalized spectral/molecular representations with symmetric contrastive cross-entropy; ITM configuration adds positive/negative matching. The actual checkpoint/training configuration determines the objective.' if en else
                '生成使用 token 交叉熵，可按配置加入联合对齐项。对齐使用归一化谱学／分子表征的双向对比交叉熵；ITM 配置增加正负配对分类项。具体目标与权重以训练配置为准。')
        return f'{title}\n\n```python\n{code}```\n\n{text}\n\n'+('### Training objective' if en else '### 训练目标')+f'\n\n{loss}\n\n{detail}\n'
    if id_.startswith('nmr.forward.') or id_=='nmr.assignment':
        isotope=id_.rsplit('.',1)[-1] if id_.startswith('nmr.forward.') else '13C'
        if isotope in ('1H','13C'):
            code=f"from openmolspec.model import NMRNet\nmodel = NMRNet.from_pretrained('/path/to/models', nucleus='{isotope}',\n    python='/path/to/nmr-env/bin/python')\n"
            code+="result = model.assign(smiles, measured_peaks_ppm)\n" if id_=='nmr.assignment' else "result = model.predict(smiles)\n"
        else:
            extra_asset=",\n    fp_inference_root='/path/to/frozen-fp'" if isotope in ('19F','31P') else ''
            extra_option=', allow_cross_domain_diagnostic=True' if isotope in ('19F','31P') else ''
            code=f"from openmolspec.benchmark import Benchmark\nbenchmark = Benchmark(workspace='/path/to/workspace',\n    python='/path/to/sdk-env/bin/python',\n    models_root='/path/to/models',\n    nmr_python='/path/to/nmr-env/bin/python'{extra_asset})\nresult = benchmark.run('{id_}', output='{isotope}-results.json', limit=32{extra_option})\n"
        text=('For fine-tuning, use the [NMRNet author training implementation](https://github.com/Colin-Jay/NMRNet), preparing atom-labelled structures/coordinates, target masks and train/validation LMDBs for the selected nucleus. Its `atom_regloss_mae` and `atom_regloss_mse` criteria operate on supervised target atoms. Retain the scaler/reference convention and select the checkpoint on validation data. This author training route is separate from the SDK inference facade.' if en else
              '微调使用 [NMRNet 作者训练实现](https://github.com/Colin-Jay/NMRNet)：准备对应核种的逐原子标签、结构／坐标、目标掩码及 train/val LMDB。实现提供 `atom_regloss_mae` 与 `atom_regloss_mse`，在有标签的原子上计算目标。保留 scaler 和参考标准，在验证集选择 checkpoint。该训练流程通过作者实现运行。')
        loss=r'$$L_{\rm MAE}=\frac{1}{N_{\rm labelled}}\sum_{i\in\mathcal M}|\hat\delta_i-\delta_i|,\qquad L_{\rm MSE}=\frac{1}{N_{\rm labelled}}\sum_{i\in\mathcal M}(\hat\delta_i-\delta_i)^2.$$'
        if id_=='nmr.assignment':text+=(' Peak matching then minimizes a separate assignment cost under the stated tolerances; it does not create atom-labelled training truth.' if en else ' 峰指认再按容差最小化匹配代价；匹配本身不会产生实验逐原子真值。')
        return f'{title}\n\n```python\n{code}```\n\n{text}\n\n{loss}\n'
    if id_.startswith('ms.forward.'):
        model=id_.rsplit('.',1)[-1]
        code=f"from openmolspec.model import MSPredictor\nmodel = MSPredictor(model='{model}', source='/path/to/ms-pred',\n    weights='/path/to/weights', python='/path/to/ms-env/bin/python')\nresult = model.predict(smiles=smiles, adduct='[M+H]+',\n    collision_energy=20., instrument='Orbitrap')\n"
        text=('Fine-tune using the [author training modules](https://github.com/coleygroup/ms-pred). Build molecule-disjoint splits with structures, acquisition conditions, measured peak intensities and the fragment targets required by the chosen architecture. ICEBERG exposes `ms_pred.iceberg.train_gen` and `ms_pred.iceberg.train_inten`; GLACIER exposes `ms_pred.glacier.train_joint` and contrastive joint training. Inspect each entry’s `--help` and the released configuration before launching.' if en else
              '微调使用 [作者训练模块](https://github.com/coleygroup/ms-pred)。准备分子独立的 train/val，包含结构、采集条件、实测峰强度及所选架构需要的碎片目标。ICEBERG 对应 `ms_pred.iceberg.train_gen`、`ms_pred.iceberg.train_inten`；GLACIER 提供 `ms_pred.glacier.train_joint` 及联合对比训练。启动前对照发布配置和各模块的 `--help`。')
        text+=(' ICEBERG fragment generation uses binary cross-entropy over valid atom decisions; its intensity module supports cosine or entropy objectives. GLACIER joint/contrastive losses depend on its configuration; preserve the selected variant when reporting fine-tuning.' if en else
               ' ICEBERG 碎片生成对有效原子决策使用二元交叉熵，强度模块支持余弦或熵目标。GLACIER 联合／对比损失随配置变化，报告微调时须注明具体变体。')
        loss=r'$$L_{\rm cosine}=1-\frac{\hat s\cdot s}{\|\hat s\|\|s\|}.$$'
        if model=='glacier':
            loss+='\n\n'+r'$$L_{\rm joint}=w_I[mL_{I,\rm MAGMa}+(1-m)L_{I,\rm end-to-end}]+w_FmL_{\rm fragment}.$$'
            text+=(' Here m is the scheduled MAGMa weight, w_I and w_F are configured loss weights, and fragment supervision combines matched atom-membership and fragment-cardinality cross-entropy. The contrastive variant additionally uses its configured decoy objective.' if en else
                   ' 其中 m 为调度的 MAGMa 权重，w_I、w_F 为配置权重；碎片监督结合匹配后的原子归属与碎片基数交叉熵。对比训练变体另使用其配置的 decoy 目标。')
        return f'{title}\n\n```python\n{code}```\n\n{text}\n\n{loss}\n'
    if id_.startswith(('vibrational.','spectroscopy.reranking')):
        forward=id_=='vibrational.forward';gap='.gap.' in id_;generate='.generation' in id_
        if forward:
            code="from openmolspec.benchmark import Benchmark\nbenchmark = Benchmark(workspace='/path/to/workspace',\n    python='/path/to/vibrational-env/bin/python',\n    portable_root='/path/to/portable-models')\nresult = benchmark.run('vibrational.forward',\n    output='geometry-to-spectrum-results.json', limit=2)\n"
            text=('Adapt the [openSpec training implementation](https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/documentation/assets/benchmarks) with reference geometries, Hessians and response tensors using the same atom ordering, units and mode conventions. Tensor/property losses train the forward model; spectral similarity is a downstream evaluation, not automatically its training loss.' if en else
                  '按 [openSpec 训练实现](https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/documentation/assets/benchmarks)准备参考构象、Hessian 与响应张量，保持原子顺序、单位和模式约定。正向模型训练使用张量／性质目标；下游谱相似度不自动等于其训练 loss。')
        else:
            cls='GapModel' if gap else 'Vib2Mol';code=f"from openmolspec.model import {cls}\nmodel = {cls}(root='/path/to/portable-models',\n    python='/path/to/vibrational-env/bin/python')\n"
            missing=not id_.endswith(('.hc','_hc'))
            if id_ == 'vibrational.generation':
                code += "result = model.predict(inputs)\n"
            else:
                code+=(f"result = model.predict(inputs, allow_missing_modalities={missing})\n" if gap or generate else f"result = model.retrieve(inputs, candidate_smiles,\n    rerank={'True' if 'reranking' in id_ else 'False'}, allow_missing_modalities={missing})\n")
            text=('Use the [openSpec/Vib2Mol author training workflow](https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/documentation/assets/benchmarks) for adaptation. Export aligned spectral/structure LMDBs, retain H/C references and normalization, and keep train/validation groups disjoint. Retrieval combines symmetric contrastive cross-entropy with matching cross-entropy; generation adds autoregressive molecular-token cross-entropy. Property regression uses the target transform and regression criterion from its training configuration. SDK classes expose inference; these training workflows run in the author implementation.' if en else
                  '通过 [openSpec／Vib2Mol 作者训练流程](https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/documentation/assets/benchmarks)进行适配。准备谱—结构对齐的 LMDB，保留 H/C 参考和归一化，确保 train/val 分组独立。检索采用双向对比交叉熵与配对分类交叉熵；生成使用分子 token 自回归交叉熵。性质回归按其训练配置保留目标变换和回归准则。SDK 提供推理，相关训练通过作者实现执行。')
        loss=r'$$L_{\rm retrieval}=L_{\rm contrastive}+L_{\rm matching},\qquad L_{\rm generation}=-\sum_t\log p(y_t\mid y_{<t},s).$$'
        if gap or forward:
            loss=r'$$\ell_\beta(r)=\begin{cases}r^2/(2\beta),&|r|<\beta,\\ |r|-\beta/2,&|r|\ge\beta.\end{cases}$$'
            if gap:
                loss+='\n\n'+r'$$L_{\rm gap}=\frac1N\sum_i\ell_\beta\left(\hat z_i-\frac{y_i-\mu_{\rm train}}{\sigma_{\rm train}}\right).$$'
                text+=(' The current Vib2Conf property engine uses mean SmoothL1 loss on training-normalized targets; its configurable beta is positive and defaults to 1. Retain the training mean/std for validation and inference.' if en else
                       ' 当前 Vib2Conf 性质引擎对训练集标准化目标使用平均 SmoothL1；beta 为正数，默认 1。验证与推理使用相同的训练均值和标准差。')
            else:
                loss+='\n\n'+r'$$L_{\rm tensor}=\sum_{q\in\{H_i,H_{ij},\partial\mu,\partial\alpha\}}\frac1{N_q}\sum_j\ell_1(\hat T_{qj}-T_{qj}).$$'
                text+=(' Each released direct model trains its selected tensor head; the Hessian/response engine averages Cartesian SmoothL1 terms by the global number of tensor components. Separate checkpoints and target units are retained when reconstructing normal modes.' if en else
                       ' 各 direct 模型训练其选定的张量头；Hessian／响应引擎按全局张量分量数平均 Cartesian SmoothL1。重建简正模式时保留各目标的独立 checkpoint 与单位。')
        return f'{title}\n\n```python\n{code}```\n\n{text}\n\n{loss}\n'
    settings="solvent_library='/path/to/solvent-library.json'" if id_=='nmr.solvent_transfer' else "magma_source='/path/to/MAGMA-source',\n    ms_input_csv='/path/to/measured-ms.csv',\n    ms_metadata_tsv='/path/to/acquisition-metadata.tsv'"
    code=f"from openmolspec.benchmark import Benchmark\nbenchmark = Benchmark(workspace='/path/to/workspace',\n    python='/path/to/task-env/bin/python',\n    {settings})\nresult = benchmark.run('{id_}', output='new-algorithm-results.json', limit=32)\n"
    return f'{title}\n\n```python\n{code}```\n\n'+('This task is an algorithmic workflow. Adapt its reference library or matching rules; there are no neural parameters or training loss. The task’s matching objective and provenance are described above.' if en else
                               '此任务是算法流程，可调整参考库或匹配规则；没有神经网络参数和训练 loss。具体匹配目标与数据来源见上文。')+'\n'


def model_index(tasks,en):
    text='# '+('Models and training' if en else '模型与训练')+'\n\n'
    text+=('Choose a task to see its model, exact inputs/outputs, direct call, training route and objective. The Python SDK and author training implementations share the documented data conventions.\n\n' if en else
           '选择任务即可查看对应模型、准确输入输出、调用方式、训练路径与目标函数。Python SDK 与作者训练实现使用文档中列出的数据约定。\n\n')
    text+='| Task | Spectroscopy | Guide |\n| --- | --- | --- |\n'
    for task in tasks:
        if task.enabled:text+=f'| `{task.id}` | {", ".join(task.modalities)} | [{task.title}](tasks/{task.id.replace(".","-")}.md) |\n'
    text+='\n[Python SDK](api.md) · [Data splits](data/splits.md) · [Tutorials](notebooks/index.md) · [Spectra Harness](harness.md)\n'
    return text
