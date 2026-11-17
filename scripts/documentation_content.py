"""Reader-facing bilingual documentation shared by task pages and notebooks."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GROUPS=[('nmr','NMR','核磁共振 NMR'),('ms','Mass spectrometry','质谱 MS'),
        ('vibrational','IR / Raman','红外 / 拉曼 IR / Raman'),('multimodal','Multimodal spectroscopy','多谱联合'),
        ('deferred','Deferred tasks','暂不推进')]


def group(task):
    if not task.enabled:return 'deferred'
    if task.id.startswith('nmr.'):return 'nmr'
    if task.id.startswith('ms.'):return 'ms'
    if task.id.endswith(('.hc','_hc')):return 'multimodal'
    return 'vibrational'


def io_contract(task,en):
    id_=task.id
    if id_.startswith('nmr.forward.'):
        nucleus=id_.split('.')[-1]
        fields=[('smiles / geometry','A valid molecular graph and a compatible 3D conformer; atom order must be preserved.','有效分子结构及相容的三维构象，必须保留原子顺序。'),
                ('nucleus',f'{nucleus}; the checkpoint must cover this nucleus.',f'{nucleus}，权重必须覆盖该核种。'),
                ('reference peaks','Optional measured ppm values for evaluation; not an inference input.','评测时提供实测 ppm 标签；标签不作为模型推理输入。')]
        outputs=[('prediction_ppm','Per-atom chemical shifts in ppm, with atom indices or a peak list.','逐原子化学位移（ppm）及原子编号，或整理后的峰列表。'),
                 ('error / coverage','Reference-matched errors and coverage; matching does not establish atom assignments.','与参考谱匹配后的误差及覆盖率；峰匹配不等于实验原子指认。')]
    elif id_=='nmr.assignment':
        fields=[('smiles','Known molecular structure; the task does not identify an unknown molecule.','已知分子结构；本任务不负责猜测未知分子。'),('nucleus / peaks_ppm','1H or 13C and the measured 1D peak positions in ppm.','1H 或 13C，以及实测一维峰位置（ppm）。'),('tolerance_ppm','Maximum allowed peak/site residual: default H 0.5, C 5 ppm.','峰与预测位点的最大允许残差，默认 H 0.5、C 5 ppm。')]
        outputs=[('assignments','Peak index → candidate atom indices, predicted ppm, residual and alternatives.','峰编号 → 候选原子编号、预测位移、残差与备选位点。'),('unmatched','Unassigned peaks and sites remain explicit. Experimental assignment accuracy is unavailable.','保留未匹配峰和位点。当前没有实验指认准确率。')]
    elif id_=='nmr.solvent_transfer':
        fields=[('structure / nucleus','Molecular connectivity and 1H or 13C.','分子连接结构及 1H 或 13C 核种。'),('solvents','Explicit source and target solvents that have paired references.','显式指定源溶剂与目标溶剂，且参考库包含对应配对。'),('source_ppm','Measured source-solvent shifts in ppm.','源溶剂下的实测位移（ppm）。')]
        outputs=[('target_ppm / delta_ppm','Estimated target shift and solvent difference from an independent reference.','从独立参考记录估计目标位移及跨溶剂差值。'),('reference','Reference identity, spectra/atom IDs, Tanimoto similarity and exclusions.','参考分子、谱图/原子 ID、Tanimoto 相似度及排除规则。')]
    elif id_.startswith('nmr.retrieval.'):
        view,direction=id_.split('.')[2:]
        fields=[('query',f'{view.upper()} peak records for s2m; molecular structure for m2s. Direction here: {direction}.',f's2m 使用 {view.upper()} 峰记录查询结构；m2s 使用结构查询谱。当前方向：{direction}。'),('candidate_pool','Explicit candidate structures or spectra; ranking is restricted to this pool.','明确提供候选结构或谱库；结果仅在这个候选池内排序。'),('formula','Not supplied to the spectral encoder.','谱编码器不接收分子式。')]
        outputs=[('ranked_candidates','Candidate identity, rank and embedding similarity score.','候选 ID、排名与嵌入相似度分数。'),('recall / MRR','Report candidate-pool size with every metric; 32-way retrieval is not full-library retrieval.','每个指标都应同时给出候选池大小；32 候选检索不代表全库检索。')]
    elif id_.startswith('nmr.generation.'):
        view=id_.split('.')[-1].upper()
        fields=[('h_nmr / c_nmr',f'{view} records: shift positions (ppm), multiplicity/integration/J where recorded; obey the modality mask.',f'{view} 谱记录：位移（ppm）及原记录中的多重性、积分、J 值；按模态掩码选择输入。'),('formula','A known molecular formula is required by this checkpoint.','此 checkpoint 必须显式提供已知分子式。'),('beam_size','Number of decoded candidates; 5 in the documented experiment.','解码候选数；本页实验使用 5。')]
        outputs=[('candidates','Generated SMILES, canonical structures, validity, formula match and model score.','生成 SMILES、规范结构、有效性、分子式一致性及模型分数。'),('exact_match','Compare the selected candidate with a held reference structure; valid SMILES alone is not success.','将选中候选与参考结构比较；SMILES 有效并不代表结构正确。')]
    elif id_.startswith('ms.forward.'):
        fields=[('smiles / adduct','Molecular structure and ion/adduct, e.g. the actual [M+H]+ or [M+Na]+ in the record.','分子结构与记录中的离子/加合物类型，例如 [M+H]+ 或 [M+Na]+。'),('collision_energy / instrument','Recorded acquisition settings supported by the released model; do not invent missing values.','发布模型支持的实际碰撞能与仪器条件；不能补造缺失值。'),('precursor_mz','Recorded precursor m/z; input conventions follow the author interface.','记录中的前体 m/z；按作者接口解释输入条件。')]
        outputs=[('predicted_peaks','Pairs of m/z and relative intensity; figures retain the top 100 predicted peaks.','m/z 与相对强度对；图中显示预测强度最高的 100 个峰。'),('similarity','Cosine/entropy similarity to all observed reference peaks, with skipped records counted.','与全部实测参考峰比较的余弦/熵相似度，同时统计跳过记录。')]
    elif id_=='ms.annotation.magma':
        fields=[('smiles / peaks','Known structure, measured MS/MS peaks [m/z, relative intensity], and adduct.','已知结构、实测 MS/MS 峰 [m/z, 相对强度] 及加合物。'),('ppm_tolerance','Mass tolerance, default 10 ppm; not an NMR chemical-shift tolerance.','质量误差容限，默认 10 ppm；不是 NMR 化学位移容限。')]
        outputs=[('peak_annotations','Candidate fragments, formulas, mass errors and atom/bond indices on engine_smiles.','候选碎片、分子式、质量误差及 engine_smiles 上的原子/键编号。'),('interpretation','Algorithmic candidate explanations; neither learned predictions nor unique confirmed mechanisms.','算法给出的候选解释，不是已实验确认的唯一裂解机制。')]
    elif id_=='vibrational.forward':
        fields=[('geometry','Element symbols and N×3 Cartesian coordinates in Å, taken from the same Gaussian log as the reference.','元素列表及 N×3 笛卡尔坐标（Å），与参考谱取自同一份 Gaussian 日志。'),('checkpoints','Xinyu openSpec Equiformer-v3 Hessian Hi/Hij and dipole/polarizability derivative weights.','Xinyu openSpec 的 Equiformer-v3 Hessian Hi/Hij 及偶极矩/极化率导数权重。')]
        outputs=[('IR / Raman','Two normalized intensity arrays on 1024 points spanning 400–4000 cm⁻¹.','400–4000 cm⁻¹、1024 点共同网格上的两条归一化强度数组。'),('spectral error','Channel-wise cosine similarity and intensity MAE against paired computed reference spectra.','与成对计算参考谱比较的分通道余弦相似度及强度 MAE。')]
    else:
        complete=id_.endswith(('.hc','_hc'))
        fields=[('IR / Raman','1024 intensity samples per visible channel, ordered 400→4000 cm⁻¹, using the checkpoint normalization.','每个可见通道 1024 个强度点，按 400→4000 cm⁻¹ 排列，并采用 checkpoint 的归一化。')]
        if complete:fields.append(('1H / 13C','Per-atom shift arrays in ppm with the checkpoint-compatible reference ID and normalization.','逐原子位移数组（ppm），参考 ID 和归一化必须与 checkpoint 一致。'))
        else:fields.append(('missing channels','This uses a four-modal checkpoint with channels omitted; it is an ablation, not a separately trained model.','此路径省略四模态权重的部分通道，属于消融，不是独立训练的专用模型。'))
        if '.gap.' in id_:outputs=[('gap_ev','One predicted HOMO–LUMO gap in eV; source Hartree labels are converted once.','一个 HOMO–LUMO gap 预测值（eV）；原始 Hartree 标签仅转换一次。'),('MAE / baseline','Error against reference and the frozen training-mean constant on the same records.','与参考值的误差，以及相同样本上固定训练均值基线的误差。')]
        elif '.generation' in id_:outputs=[('SMILES candidates','Decoded valid, canonical unique candidates; full-input route uses beam 10 and ITM reranking.','解码后有效、规范化且去重的结构；完整输入路径使用 beam 10 和 ITM 重排。'),('top-k','Generation and reranking scores are separate. No molecular formula is supplied.','分别报告生成与重排后的 top-k；不提供分子式。')]
        else:
            fields.append(('candidate structures','An explicit candidate library; scores cannot identify molecules outside it.','明确提供候选结构库；模型只能在此库中排序。'))
            outputs=[('ranking','Candidate identities with similarity or ITM positive-class scores.','候选结构 ID，以及相似度或 ITM 正类分数。'),('recall / MRR','Ranking metrics plus candidate-pool size and source composition.','排序指标、候选池大小及样本来源构成。')]
    def table(rows):return '| Field | Meaning |\n| --- | --- |\n'+'\n'.join(f'| `{k}` | {a if en else z} |' for k,a,z in rows)+'\n'
    return table(fields),table(outputs)


def metric_rows(bundle):
    allowed={'mae_ppm','rmse_ppm','matched_peak_mae_ppm','matched_fraction','matched_peak_fraction_macro','matched_residual_mae_ppm','assignment_accuracy',
             'mae_ev','rmse_ev','recall_at_1','mrr','candidate_pool','exact_rate','valid_rate','formula_match_rate','exact_canonical_top1','exact_canonical_top5',
             'valid_smiles_fraction','cosine_similarity','entropy_similarity','ir_cosine_similarity','raman_cosine_similarity','matched_peak_fraction',
             'unchanged_shift_mae_ppm','molecules','atoms','examples','queries','scored_examples','checked_fragments'}
    rows=[]
    for run in bundle['runs']:
        groups=[(m['model'],m['metrics']) for m in run.get('models',[])] or [('recorded model',run['metrics'])]
        for model,metrics in groups:
            if metrics and all(isinstance(v,dict) for v in metrics.values()):groups2=list(metrics.items())
            else:groups2=[(model,metrics)]
            for label,m in groups2:
                for key,value in m.items():
                    if key in allowed and not isinstance(value,(dict,list)):
                        rows.append((str(run.get('dataset') or 'recorded sample'),label,key,'not measured' if value is None else f'{value:.6g}' if isinstance(value,float) else str(value)))
        for label,key in [('ITM reranked','reranked_metrics'),('Training-mean baseline','training_mean_baseline')]:
            for metric,value in run.get(key,{}).items():
                if metric in allowed:rows.append((str(run.get('dataset') or 'recorded sample'),label,metric,f'{value:.6g}' if isinstance(value,float) else str(value)))
    return rows


def results_table(bundle,en):
    lines=['| Dataset / scope | Model / variant | Metric | Value |','| --- | --- | --- | ---: |']
    lines+=['| '+' | '.join(row)+' |' for row in metric_rows(bundle)]
    return '\n'.join(lines)+'\n'


def quickstart(en):
    if en:
        text='''# Quick start

Start with a real saved example, then run a model when its external weights and data are available. The repository contains documentation evidence; large model checkpoints and complete datasets are separate.

## 1. Get the documented release

Use Python 3.11 or newer for the documentation environment. The public documentation follows the release branch below; the newer frontend on `main` has a different application layout.

```bash
git clone --branch release/openmolspec-v1 https://github.com/jiaqingxie/openmolspec-studio-frontend.git
cd openmolspec-studio-frontend
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r requirements-docs-examples.txt
```

## 2. Reproduce the first figure without model downloads

This command reads the actual 128-sample frozen gap predictions, recomputes MAE/RMSE and draws the reference/prediction figure. It does not rerun the model.
'''
    else:
        text='''# 快速开始

先从一份真实运行结果开始，再按需配置权重并执行模型。仓库已经保存文档所需的实际输入输出；大模型权重和完整数据集独立存放。

## 1. 获取文档对应的发布分支

文档环境使用 Python 3.11 或更新版本。线上手册对应下面的 release 分支；`main` 上较新的前端具有不同应用结构。

```bash
git clone --branch release/openmolspec-v1 https://github.com/jiaqingxie/openmolspec-studio-frontend.git
cd openmolspec-studio-frontend
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r requirements-docs-examples.txt
```

## 2. 不下载模型，先复现第一张真实结果图

下面的命令读取 128 个样本的真实冻结推理预测，重新计算 MAE/RMSE 并绘制预测与参考对照图。这一步是结果分析，不是重新运行模型。
'''
    text+='''
```bash
.venv-docs/bin/python -m pip install -e .
# Set this to an Arial TTF file installed or licensed on your machine:
export OPENMOLSPEC_ARIAL_FONT=/path/to/Arial.ttf
.venv-docs/bin/python - <<'PY'
import sys
sys.path.insert(0, 'scripts')
from documentation_evidence import load_evidence, recompute, render
task = 'vibrational.gap.ir_raman_hc'
evidence = load_evidence(task)
print(recompute(evidence))
render(task, evidence).savefig('my-first-result.png', dpi=180)
PY
```

'''
    text+=('Expected recomputed MAE is approximately **0.131446 eV**. Open `my-first-result.png`, then compare the [real-results gallery](gallery.md) and [complete-input gap task](tasks/vibrational-gap-ir_raman_hc.md).\n\n## 3. Run the notebook cells\n\n' if en else '重新计算得到的 MAE 约为 **0.131446 eV**。打开 `my-first-result.png`，再查看[真实结果图册](gallery.md)和[完整输入 gap 任务](tasks/vibrational-gap-ir_raman_hc.md)。\n\n## 3. 逐格运行 notebook\n\n')
    text+='```bash\n.venv-docs/bin/jupyter lab documentation/notebooks/vibrational-gap-ir_raman_hc.ipynb\n```\n\n'
    text+=('Select the Python kernel from `.venv-docs`, then Run All. Cells show the actual input, actual output, recomputed diagnostics and a figure. Full arrays are stored in `documentation/assets/examples/`; abbreviated previews state their array length. Source result filenames and SHA-256 hashes accompany each notebook.\n\n## 4. Prepare frozen-model inference\n\n' if en else '选择 `.venv-docs` 的 Python kernel 后运行全部单元格。依次显示真实输入、真实输出、重算指标和图。完整数组在 `documentation/assets/examples/`；页面中的缩略预览会标明数组长度。每份 notebook 都列出来源结果文件与 SHA-256。\n\n## 4. 配置冻结模型推理\n\n')
    text+=('Model runtimes are separate from the lightweight documentation environment. Install the original model dependencies in their own environments. See [dataset sources](datasets.md) and [model suitability](model-audit.md) before choosing a task. The expected workspace is:\n\n' if en else '模型运行环境与轻量文档环境分开。按模型作者的依赖建立独立环境；选择任务前先看[数据来源](datasets.md)和[模型适用性](model-audit.md)。工作区组织如下：\n\n')
    text+='''```text
workspace/
  OpenMolSpec/
    studio/                     # this checkout
    data/align_eval/<dataset>/test.jsonl
    runs/<run-id>/best.pt        # existing NMR encoder/generator
  models/                       # NMRNet / NMRNet++ released assets
  openmolspec-studio-portable/   # Xinyu models, normalization, test LMDB
```

```bash
python -m openmolspec_bench list
python -m openmolspec_bench run \
  --workspace /path/to/workspace/OpenMolSpec \
  --portable-root /path/to/workspace/openmolspec-studio-portable \
  --tasks vibrational.gap.ir_raman_hc \
  --limit 32 --sampling reservoir --seed 42 --device cpu \
  --output results/my-gap-run.json
```

'''
    text+=('Run this command with a Python interpreter containing the original model dependencies. The complete-input task needs IR, Raman and both H/C channels with the checkpoint reference. Each output path must be new. `--limit` controls example count; it does not train or change the model.\n\nFor NMR assignment, explicitly select the dataset, model root and NMR runtime:\n\n' if en else '使用已装好原模型依赖的 Python 执行上面的命令。完整输入任务需要 IR、Raman、H/C 及相容参考。输出文件必须是新路径。`--limit` 只控制样本数，不会训练或改变模型。\n\n运行 NMR 指认时，还要明确数据集、模型目录和 NMR 专用 Python：\n\n')
    text+='''```bash
python -m openmolspec_bench run \
  --workspace /path/to/workspace/OpenMolSpec \
  --models-root /path/to/workspace/models \
  --nmr-python /path/to/nmr-runtime/bin/python \
  --tasks nmr.assignment --datasets nmrspec_test \
  --assignment-nucleus 13C --limit 2 \
  --output results/my-assignment-run.json
```

'''
    text+=('## 5. Read the result correctly\n\n- `status=passed` means the adapter completed; scientific suitability is assessed separately.\n- `metrics` contains actual scores; `sample_ids`, hashes and conditions define what was evaluated.\n- `skipped` means required assets, conditions or a valid reference are missing. Read `reason`; no score should be invented.\n- F/P formal solution scores remain blocked; B/Si results are diagnostic. Cross-solvent transfer is a reference-retrieval baseline.\n- A small candidate pool, unknown training overlap or absent assignment labels limits the claim you can make.\n\n## 6. Build the bilingual website\n\n' if en else '## 5. 正确解读结果\n\n- `status=passed` 只代表接口执行成功；科学适用性需要单独判断。\n- `metrics` 保存实际指标；`sample_ids`、哈希和条件说明究竟评了什么。\n- `skipped` 代表缺少资产、条件或合法参考；请查看 `reason`，不能补造分数。\n- F/P 溶液正式评分仍被拦截，B/Si 仅作诊断，跨溶剂迁移当前是参考检索基线。\n- 小候选池、未核查训练重叠、缺实验指认标签，都会限制可作出的结论。\n\n## 6. 构建中英文文档\n\n')
    text+='''```bash
.venv-docs/bin/python scripts/build_bilingual_docs.py --check
.venv-docs/bin/python scripts/build_readthedocs.py --output site --strict
.venv-docs/bin/python -m http.server 8000 --directory site
```

'''
    text+=('Open `http://localhost:8000/`; use the language switch for Chinese. Documentation builds render saved notebook outputs and never launch model inference.\n' if en else '打开 `http://localhost:8000/`，使用语言按钮切换中英文。文档构建仅渲染已保存的 notebook 输出，不启动模型推理。\n')
    return text


def datasets_page(en):
    d=json.loads((ROOT/'documentation/assets/dataset_audit.json').read_text())
    text=('# Datasets: contents, scale and provenance\n\n' if en else '# 数据集：内容、规模与来源\n\n')
    text+=('OpenMolSpec brings together experimental spectra curated from OpenDataLab / WanJuan, calculated spectra produced by the team, and externally maintained benchmarks. The OpenDataLab-derived corpus is experimental, as confirmed by the project owner; curation does not imply that our team performed the original measurements. A locally prepared file is not automatically a dataset created by us. Counts below use explicit units and verification scopes.\n\n' if en else 'OpenMolSpec 包括从 OpenDataLab / WanJuan 清洗整理的实验谱、团队构建的计算谱，以及接入的外部基准。项目负责人已明确 OpenDataLab 这条数据主线来自实验测量；团队贡献是清洗整理，不是原始测量。本地整理的文件不会自动变成“我们自建的数据”。下列数字均标明计数单位和核验范围。\n\n')
    text+=('## 1. OpenMolSpec calculated data\n\nThe documented frozen-candidate release contains **1,158,074 full molecules** deduplicated by full InChIKey, **1,030,780 aligned molecules** with IR/Raman/NMR, and **32,333,251 optimization trajectory frames** with energies/forces. Frames are not additional molecules. These are release-snapshot figures from the project data description; the full release files are not mounted in this workspace and were not independently recounted here.\n\n' if en else '## 1. OpenMolSpec 自建计算数据\n\n项目冻结候选版本记录：按完整 InChIKey 去重的 **1,158,074 个 full 分子**，同时具有 IR/Raman/NMR 的 **1,030,780 个 align 分子**，以及带能量/力的 **32,333,251 个优化轨迹帧**。轨迹帧不能另算成分子。以上是项目数据说明中的版本快照；当前工作区未挂载完整 release 文件，因此本次没有把这些总量重新全盘计数。\n\n')
    text+='| Aligned split | Molecules in release snapshot |\n| --- | ---: |\n| Train | 1,000,000 |\n| Validation | 10,390 |\n| Test | 20,390 |\n\n'
    r=next(r for r in d['datasets'] if r['id']=='openspec_test')
    text+=(f'The local test LMDB **was fully scanned**: {r["records"]:,} records and {r["unique_canonical_isomeric_smiles"]:,} distinct RDKit canonical isomeric SMILES. The stored-model representation and identity definition differ from the release InChIKey counts; these two numbers must not be substituted for each other. There are 20,388 H+C records and two C-only records. All 20,390 contain IR and Raman arrays.\n\n' if en else f'本次**完整扫描**了本地测试 LMDB：实际有 **{r["records"]:,} 条记录**、**{r["unique_canonical_isomeric_smiles"]:,} 个不同的 RDKit 规范异构 SMILES**。模型文件中的表示及身份口径与 release 的 InChIKey 口径不同，二者不能互换。20,388 条同时具有 H/C，另有 2 条仅含 C；20,390 条都包含 IR 与 Raman 数组。\n\n')
    text+='![OpenMolSpec test distribution](assets/gallery/dataset-openspec-test.png)\n\n'
    text+=('The source labels (QM9, ZINC, SDBS, etc.) identify the original molecular libraries. IR/Raman/NMR observables in this LMDB are calculated; a source label does not turn them into experimental spectra.\n\n| Field | Shape / unit / meaning |\n| --- | --- |\n| `sample_id`, `source_dataset`, `inchikey` | Record identity, molecular-library origin, stored structural identifier |\n| `ir`, `raman` | 1024 normalized values per channel; 400–4000 cm⁻¹ |\n| `nmr_h_shifts_ppm`, `nmr_c_shifts_ppm` | Variable-length per-atom ppm arrays; unassigned, no J splitting |\n| `nmr_reference_id` | Reference convention required to match the checkpoint |\n| `gap`, `homo`, `lumo`, `energy` | Stored quantum-chemical quantities; gap in Hartree, converted once to eV for evaluation |\n\n' if en else 'QM9、ZINC、SDBS 等 source 标签表示原始分子库来源。这份 LMDB 的 IR/Raman/NMR 观测量是计算得到的，不能因为来源叫 SDBS 或 NISTIR 就称为实测谱。\n\n| 字段 | 形状 / 单位 / 含义 |\n| --- | --- |\n| `sample_id`、`source_dataset`、`inchikey` | 记录 ID、原分子库来源、保存的结构标识 |\n| `ir`、`raman` | 每通道 1024 个归一化值；400–4000 cm⁻¹ |\n| `nmr_h_shifts_ppm`、`nmr_c_shifts_ppm` | 变长逐原子 ppm 数组；未指认，不含 J 裂分 |\n| `nmr_reference_id` | 必须与 checkpoint 一致的参考约定 |\n| `gap`、`homo`、`lumo`、`energy` | 保存的量化性质；gap 原单位 Hartree，评测时仅转换一次为 eV |\n\n')
    text+=('## 2. Team-curated experimental NMR from OpenDataLab / WanJuan\n\nThis experimental corpus is curated from OpenDataLab / WanJuan patent measurements. Original measurements and citations remain attributable to their sources. The public provider version and redistribution scope still require release-level verification. The standard-InChI view has **2,680,271 identities**: 2,174,218 train, 250,984 validation and 255,069 test. It preserves **2,722,790 H records** and **252,158 C records**; one molecule can have several measurements. Counts come from the existing complete-corpus verification report, whose digest is included in this audit.\n\n' if en else '## 2. OpenDataLab / WanJuan：团队整理的实验 NMR\n\n这条实验数据主线来自 OpenDataLab / WanJuan 专利测量，团队负责清洗和整理，原始测量及引用仍归属其来源。正式发布还需核实提供方版本和可再分发范围。standard-InChI 视图有 **2,680,271 个结构身份**：训练 2,174,218、验证 250,984、测试 255,069。保留 **2,722,790 条 H 记录**和 **252,158 条 C 记录**，一个分子可能有多条测量。这些数字来自已有的全库核验报告，报告哈希也保存在本次审计中。\n\n')
    text+='![Patent corpus split and modality distribution](assets/gallery/dataset-patent-corpus.png)\n\n'
    text+=('The view groups by standard InChI, selects a representative SMILES, retains the most informative H/C records separately, and assigns scaffold-based splits. Its 10,000-record evaluation subset is part of the parent corpus and must not be added to that total.\n\n## 3. Prepared evaluation views of external NMR\n\nEvery file below was fully scanned in this update. Each row has `smiles`, `formula`, `h_nmr`, `c_nmr` and a `[has_H, has_C]` mask. H/C records retain peak text; available fields can include shifts, multiplicity, integration, couplings and acquisition frequency. Missing conditions are not fabricated.\n\n' if en else '这个视图按 standard InChI 分组，选择代表 SMILES，分别保留信息较充分的 H/C 记录，再按 scaffold 划分。用于评测的 10,000 条专利子集属于父数据，不能再加到总量里。\n\n## 3. 从外部 NMR 整理的评测视图\n\n下列文件在本次更新中均已完整扫描。每行包含 `smiles`、`formula`、`h_nmr`、`c_nmr` 和 `[has_H, has_C]` 掩码。H/C 保留峰文本，原记录有时还含多重性、积分、J 值和频率；缺失条件不会补造。\n\n')
    text+='| Local view | Original source | Records | Unique canonical structures | H only | C only | H+C |\n| --- | --- | ---: | ---: | ---: | ---: | ---: |\n'
    for r in d['datasets'][:4]:
        m=r['modality_records'];text+=f'| `{r["id"]}` | {r["source"]} | {r["records"]:,} | {r["unique_canonical_isomeric_smiles"]:,} | {m.get("H only",0):,} | {m.get("C only",0):,} | {m.get("H+C",0):,} |\n'
    text+='\n![NMR evaluation data](assets/gallery/dataset-nmr-views.png)\n\n'
    text+=('The directory name `nmrexp_exp_10k` is a target-size label: it actually contains **9,183** records after filtering. NMRSpec here is the NMRTrans test benchmark. NMRGym and NMRExp remain external sources even after conversion to our interface.\n\n## 4. External full/local filtered sources\n\n' if en else '目录名 `nmrexp_exp_10k` 只是目标规模，过滤后实际是 **9,183 条**。这里的 NMRSpec 是 NMRTrans 测试 benchmark。NMRGym 和 NMRExp 即使转成统一接口，仍属于外部来源。\n\n## 4. 外部原始／本地过滤数据\n\n')
    text+='| External local view | Count | Counting unit / method |\n| --- | ---: | --- |\n'
    for r in d['external_local_views']:
        text+=f'| `{r["id"]}` | {r.get("records",r.get("spectra")):,} | '+('Parquet spectral rows (metadata)' if 'records' in r else 'CSV spectra (complete scan)')+' |\n'
    ms=next(r for r in d['external_local_views'] if r['id']=='MassSpecGym_test_full')
    text+=f'\nMassSpecGym test: **{ms["spectra"]:,} spectra / {ms["distinct_smiles_strings"]:,} distinct stored SMILES strings**.\n\n'
    text+='![External NMRExp nuclei](assets/gallery/dataset-nmrexp-nuclei.png)\n\n'
    text+=('MassSpecGym is an external dataset. Our GLACIER/ICEBERG evaluation selected 32 distinct molecules and scored 31 spectra per model, skipping one missing-condition record. Those 31 are a small evaluated subset, not the dataset size.\n\n## Access and reproducibility\n\n' if en else 'MassSpecGym 是外部数据。本项目 GLACIER/ICEBERG 实验选择 32 个不同分子，每个模型评分 31 条谱，因条件缺失跳过 1 条。31 只是实际评测子集大小，不是全数据量。\n\n## 获取与复现\n\n')
    text+='- [MassSpecGym original distribution](https://huggingface.co/datasets/roman-bushuiev/MassSpecGym)\n- [NMRNet data / weights](https://zenodo.org/records/19142375)\n- [NMRNet++ data / weights](https://zenodo.org/records/18232165)\n- [This audit: counts, histograms, schemas, file hashes and real examples](assets/dataset_audit.json)\n\n'
    text+=('A verified public full OpenMolSpec release URL is not available here yet. The downloadable audit and task examples are available now; they do not replace full data distribution. Public redistribution must follow the original sources. Our computed release snapshot, curated patent view and external evaluation subsets overlap conceptually and must not be summed into a single "total molecules" number.\n' if en else '这里尚无经过验证的 OpenMolSpec 完整公开数据下载地址。当前可下载审计统计和任务真实示例，但它们不等于完整数据发布。数据分发应遵循原始来源要求。计算数据版本、专利整理视图和外部评测子集有不同口径及父子关系，不能简单相加成一个“总分子数”。\n')
    return text


def assessment(task,en):
    id_=task.id
    if not task.enabled:return ('Deferred; no new work.' if en else '已暂停，本轮不推进。')
    if id_.endswith('29Si'):return ('Unsuitable as an accurate solution predictor: 56.13 ppm MAE, all 32 predictions biased high. Clean data and obtain compatible weights before considering fine-tuning.' if en else '当前不适合精确溶液位移预测：MAE 56.13 ppm，32 个预测全部偏高。先清理数据并确认相容权重，再考虑微调。')
    if id_.endswith('11B'):return ('Diagnostic only: 8.68 ppm MAE, correlation 0.217. Weak discrimination and unaudited coverage; nucleus-specific adaptation is a candidate after data repair.' if en else '仅作诊断：MAE 8.68 ppm，相关系数 0.217。区分能力弱、覆盖未核验；数据修复后可考虑 B 专项适配。')
    if id_.endswith(('19F','31P')):return ('Current solid-state weights are not validated for solution shifts. Resolve domain/reference compatibility before any fine-tuning decision.' if en else '当前固相权重没有验证为溶液位移模型。优先解决数据域与参考兼容，不能直接归因于需要微调。')
    if id_=='nmr.solvent_transfer':return ('Executable reference baseline; H does not improve on unchanged shifts. A solvent-conditioned model and independent paired data are still needed.' if en else '参考检索基线可执行，但 H 没有优于位移不变基线。仍需溶剂条件模型及独立配对数据。')
    if id_=='nmr.assignment':return ('Reasonable candidate pipeline for a known structure; no experimental assignment accuracy yet. Validate atom labels and symmetry before proposing fine-tuning.' if en else '作为已知结构的候选指认流程合理，但尚无实验指认准确率。先验证原子标签和对称性，再决定微调。')
    if id_.startswith('nmr.generation.'):return ('Strong dataset dependence: zero exact matches on the 32-example patent and NMRGym checks. Prioritize a clean external test and parsing/token coverage audit; then consider domain fine-tuning.' if en else '存在明显数据域差异：专利和 NMRGym 的 32 样本检查均为零精确匹配。先检查独立测试、解析及词表覆盖，再考虑领域微调。')
    if id_.startswith('nmr.retrieval.'):return ('Input/output pairing is appropriate; the 32-candidate smoke pool is small. Validate a larger independent library before judging generalization or fine-tuning.' if en else '输入输出对应合理，但目前主要是 32 候选的小池检查。先评更大的独立候选库，再判断泛化和微调需求。')
    if id_.startswith('nmr.forward.'):return ('Reasonable H/C frozen-model baseline; reported errors use peak matching, not experimental atom assignments. Verify data overlap and solvent coverage.' if en else '可作为 H/C 冻结模型基线；误差来自峰匹配，不代表实验原子指认。仍要检查训练重叠和溶剂覆盖。')
    if id_.startswith('ms.forward.'):return ('Appropriate author model interface and explicit conditions; 31 scored spectra are insufficient for a broad accuracy claim. Protocol/overlap audit precedes fine-tuning.' if en else '采用作者接口并显式提供采集条件，方法适配合理；31 条评分不足以证明广泛精度。先核查协议与训练重叠，再决定微调。')
    if id_=='ms.annotation.magma':return ('Algorithmic annotation, not a trainable neural model. Improve matching and validation rather than propose fine-tuning.' if en else '这是算法标注，不是可微调神经模型；应改进匹配和验证。')
    if id_=='vibrational.forward':return ('Correct Xinyu Hessian/response route and paired geometry. Two examples demonstrate execution only; evaluate a held-out geometry set before adaptation.' if en else '使用正确的 Xinyu Hessian/response 路径及成对几何。两例只证明流程执行；先做独立构象集评测。')
    if not id_.endswith(('.hc','_hc')):return ('Missing-channel ablation of a four-modal checkpoint. Poor scores do not validate a stand-alone IR/Raman model; use compatible unimodal weights or plan separate adaptation.' if en else '这是四模态权重的缺通道消融。不能当作独立 IR/Raman 专用模型；需相容权重或另行规划适配。')
    if '.gap.' in id_:return ('Complete inputs and units are aligned; 0.131446 eV MAE beats the 0.899940 eV mean baseline on 128 samples. Broader independent evaluation is the next step, not immediate fine-tuning.' if en else '完整输入和单位已对齐；128 样本 MAE 0.131446 eV，优于均值基线 0.899940 eV。下一步是更大独立评测，无证据要求立即微调。')
    if '.generation' in id_:return ('Author generation protocol is implemented. ITM reranking lowers top-1 from 0.75 to 0.6875 on the same 64 examples; validate this regression before adapting the ranker.' if en else '已遵循作者生成协议，但同一 64 样本上 ITM 重排使 top-1 从 0.75 降到 0.6875；应先复查这项退化，再考虑重排器适配。')
    return ('Complete four-modal protocol is appropriate. Candidate-pool retrieval and explicit-pool ITM are not open-world generation; validate larger held-out pools.' if en else '完整四模态协议适配合理。候选池检索／ITM 不等于开放结构生成；需扩大独立候选库验证。')


def model_audit_page(tasks,en):
    title='Model suitability and potential fine-tuning' if en else '模型适用性与潜在微调清单'
    text='# '+title+'\n\n'
    text+=('This review covers every enabled task. Successful execution, reasonable task/model pairing, and independently validated accuracy are separate findings. No training, fine-tuning or fitted offset was performed.\n\n## B and Si: current verdict\n\n' if en else '本页逐项检查所有启用任务。执行成功、模型与任务相容、精度经过独立验证，是三个不同结论。本轮没有训练、微调或拟合位移偏移。\n\n## B 与 Si：当前结论\n\n')
    text+='| Nucleus | Molecules / atoms | MAE (ppm) | Mean signed error (ppm) | Pearson r | R² |\n| --- | ---: | ---: | ---: | ---: | ---: |\n'
    audit=json.loads((ROOT/'results/bsi_model_review_20261117.json').read_text())
    for n,r in audit['nuclei'].items():text+=f'| {n} | 32 / 32 | {r["mae_ppm"]:.4f} | {r["mean_signed_error_ppm"]:+.4f} | {r["correlation"]:.4f} | {r["r_squared"]:.4f} |\n'
    text+=('\nThe sole B/Si atom in each evaluated structure matches the saved label index; current pool labels and all checkpoint parameters were checked. That fixes alignment, not scientific quality. B predictions have weak correlation; Si predictions are all too high. Neither is presented as a validated accurate solution predictor.\n\n' if en else '\n本次核对了每个评测结构唯一的 B/Si 原子与标签位置，确认当前数据池标签对齐、checkpoint 参数完整恢复。这样能排除配对错误，但不能证明科学质量。B 预测相关性弱，Si 预测全部偏高；二者都不能宣传为已验证的高精度溶液模型。\n\n')
    text+=('The current prepared B pool has **121** canonical structures shared between train and validation; Si has **10**. These are overlaps in the prepared data pool, not proof of overlap with the released model’s training set. All pool rows have blank solvent fields. A B training-pool label reaches **3085 ppm**, requiring raw-source/unit review before any future training. The pool contents match `data_hetero3` by structure, coordinates, labels and masks; old `data_hetero2` preparation scripts do not describe the current pool.\n\n' if en else '当前准备的 B 数据池有 **121** 个规范结构同时出现在 train 与 valid，Si 有 **10** 个。这是准备数据池的重叠，不等于证明与发布模型训练集重叠。所有池记录的溶剂字段均为空。B 的一个训练池标签达到 **3085 ppm**，未来训练前应核查原始来源和单位。按结构、坐标、标签和掩码核对，当前池实际对应 `data_hetero3`，不能再用旧 `data_hetero2` 脚本描述它。\n\n')
    text+=('The [official NMRNet++ archive](https://zenodo.org/records/18232165) matches the downloaded checkpoint archive checksum; its identifiable trained checkpoints are H/C only. The B/Si diagnostic uses liquid All-nucleus **NMRNet**, not verified B/Si-specific NMRNet++ weights.\n\n' if en else '[NMRNet++ 官方归档](https://zenodo.org/records/18232165)与本地下载 checkpoint 包的校验和一致，其中可识别的已训练 checkpoint 只有 H/C。目前 B/Si 使用的是液相 All-nucleus **NMRNet**，不是已核验的 B/Si 专用 NMRNet++ 权重。\n\n')
    text+=('## Every active task\n\n' if en else '## 全部启用任务的检查\n\n')
    text+='| Task | Current interpretation and next step |\n| --- | --- |\n'
    for t in tasks:
        if t.enabled:text+=f'| [{t.id}](tasks/{t.id.replace(".","-")}.md) | {assessment(t,en)} |\n'
    text+=('\n## Potential future fine-tuning — ordered by evidence\n\n' if en else '\n## 潜在微调任务清单：按现有证据排序\n\n')
    rows=[('1','29Si / 11B','Compatible nucleus-specific weights first; repair structure leakage, recover solvent/reference metadata and verify raw labels. If no suitable released weights exist, nucleus-specific adaptation is justified.','先找相容核种专用权重，修复结构泄漏、补回溶剂/参考条件、核验原标签。若没有合适发布权重，再考虑核种专项适配。'),
          ('2','NMR → SMILES (H / C / H+C)','Strong cross-dataset failures justify an adaptation study after formula parsing, tokenizer coverage and independent scaffold tests are verified.','跨数据集失败明显；验证分子式解析、词表覆盖及独立 scaffold 测试后，可优先做领域适配研究。'),
          ('3','Cross-solvent transfer','First obtain a solvent-conditioned model and clean paired, atom-mapped data. Current nearest-reference baseline is not a neural checkpoint that can be fine-tuned.','先获得溶剂条件模型和干净、原子对应的配对数据。当前近邻参考基线没有可供微调的神经权重。'),
          ('4','IR/Raman-only gap / generation / retrieval','If missing-NMR use is a product requirement, acquire a checkpoint trained for that input or plan missing-modality adaptation. Current results are ablations.','若必须支持缺 NMR 输入，应找对应输入训练的权重，或规划缺模态适配；当前分数属于消融。'),
          ('5','Vib2Mol ITM reranker','Investigate the observed same-sample top-1 regression; calibrating or retraining on the test set is prohibited. Use a separate development set for any later adaptation.','先调查同样本 top-1 退化；不得在测试集上拟合校准或重训。后续适配必须使用独立开发集。')]
    text+='| Priority | Task family | Prerequisite / reason |\n| --- | --- | --- |\n'
    for p,t,a,z in rows:text+=f'| {p} | {t} | {a if en else z} |\n'
    text+=('\n**Not yet a fine-tuning conclusion:** F/P need compatible solution/reference definitions first; assignment needs experimental ground truth; MS and conformer→IR/Raman need larger independent evaluations. MAGMa is an algorithm. Full-input gap has a useful current baseline. SpectraLLM, formula prediction and QA remain deferred.\n' if en else '\n**暂不能直接下“需要微调”的结论：**F/P 先解决溶液域和参考约定；指认先补实验真值；MS、构象→IR/Raman 先扩大独立评测。MAGMa 是算法。完整输入 gap 现有基线有用。SpectraLLM、分子式预测、谱学 QA 继续暂缓。\n')
    text+='\n[Download B/Si audit](assets/reports/bsi_model_review_20261117.json) · [Official archive inventory](assets/reports/nmrnetpp_release_inventory_20261117.json)\n'
    return text
