"""Reader-facing guides for cleaned spectroscopy datasets."""
import json
from pathlib import Path
from manual_citations import markdown as references

ROOT=Path(__file__).resolve().parents[1]


def notebook(en):
    """Explain and replot the complete cleaned experimental data summaries."""
    import hashlib
    t=lambda a,b:a if en else b;cells=[]
    def md(text):cells.append({'cell_type':'markdown','metadata':{},'source':[text]})
    def code(text):cells.append({'cell_type':'code','metadata':{},'source':[text],'execution_count':None,'outputs':[]})
    md('# '+t('Exploring the spectroscopy datasets','探索谱学数据集')+'\n\n'+t('This tutorial explores the cleaned experimental collection: how many molecules and spectra it contains, which nuclei are available, where the peak positions lie and how the data are split for learning. The plots use the full cleaned-data histograms.','本教程探索清洗后的实验数据集：有多少分子与谱图、有哪些核种、峰位置如何分布，以及如何划分训练数据。图中的分布来自完整清洗数据的直方图。'))
    md('## '+t('Read the dataset summary','读取数据摘要')+'\n\n'+t('The summary contains H/C molecular counts and separate spectral counts for each experimental view. Read these fields before choosing a dataset for your task.','摘要保存 H/C 分子数量，以及各实验视图的谱数量。选择任务所需数据集之前，先查看这些字段。'))
    code("import json, sys, io\nfrom pathlib import Path\nfrom IPython.display import display, SVG\nroot = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'openmolspec_bench').is_dir())\nsys.path.insert(0, str(root / 'scripts'))\nsummary = json.loads((root / 'documentation/assets/cleaned-data-summary.json').read_text())\nprint('H/C molecules:', summary['nmr']['molecular_identities'])\nprint('H spectra:', summary['nmr']['counts']['h_spectra'])\nprint('C spectra:', summary['nmr']['counts']['c_spectra'])\nfor modality, view in summary['experimental']['views'].items():\n    print(modality, view['spectra'], 'spectra;', view['molecules'], 'molecules')")
    md('## '+t('Molecular size and chemical shifts','分子大小与化学位移')+'\n\n'+t('Heavy-atom count and molecular weight describe the chemical space available for training. The NMR panels show the positions of parsed H/C peaks in ppm. Tail bins collect values outside the displayed central range, so all cleaned records contribute to the plots.','重原子数与分子量描述训练数据覆盖的化学空间。NMR 面板展示解析后的 H/C 峰位置，单位为 ppm。尾部格汇总显示区间之外的值，因此图中保留了全部清洗记录。'))
    code("from build_manual_examples import distributions\nimport matplotlib.pyplot as plt\nfigures = distributions()\ndef show(name):\n    stream = io.StringIO()\n    figures[name].savefig(stream, format='svg', metadata={'Date': None})\n    display(SVG(stream.getvalue()))\nshow('data-cleaned-nmr')\nshow('data-cleaned-nmr-shifts')")
    md('## '+t('Spectral coverage and peak distributions','谱型覆盖与峰分布')+'\n\n'+t('The nucleus-count panel uses a logarithmic axis to display both abundant and less common nuclei. MS panels describe molecular size and m/z peak positions; IR/Raman panels use wavenumber in cm⁻¹. These representations help choose channel masks, input grids and sampling policies.','核种数量图使用对数轴，以便同时展示高丰度和较少的核种。MS 面板展示分子大小与 m/z 峰位置，IR/Raman 面板使用 cm⁻¹ 波数。这些分布可用于选择通道掩码、输入网格和抽样策略。'))
    code("for name in ['data-cleaned-experimental', 'data-cleaned-ms', 'data-cleaned-vibrational']:\n    show(name)\nfor figure in figures.values():\n    plt.close(figure)")
    md('## '+t('Training, validation and test files','训练、验证和测试文件')+'\n\n'+t('The cleaned H/C collection retains named train/validation/test files. The summary records their molecular counts and checks standard-identity intersections. Use the training set for fitting and the validation set for choosing model settings.','清洗后的 H/C 集合保留训练、验证和测试文件。摘要记录各文件的分子数量和标准身份交集。使用训练集拟合，在验证集选择模型设置。'))
    code("for role, view in summary['nmr']['files'].items():\n    print(role, view['records'], 'molecules')\nprint('Cross-split identity intersections:', summary['nmr']['split_identity_overlaps'])")
    md('[Data guide](../data/index.md) · [Dataset API](../api-reference/module-datasets.md) · [Create a split](../data/splits.md)')
    for i,cell in enumerate(cells):cell['id']=hashlib.sha256(f'cleaned-data:{en}:{i}'.encode()).hexdigest()[:12]
    return {'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},'openmolspec_evidence_files':['documentation/assets/cleaned-data-summary.json','scripts/build_manual_examples.py','scripts/documentation_figures.py','src/openmolspec/plotting.py']},'nbformat':4,'nbformat_minor':5}


def table(headers,rows):
    return '| '+' | '.join(headers)+' |\n|'+'|'.join(' --- ' for _ in headers)+'|\n'+''.join('| '+' | '.join(str(v) for v in row)+' |\n' for row in rows)+'\n'


def pages(en):
    suffix='' if en else '.zh';out={};t=lambda a,b:a if en else b
    summary=json.loads((ROOT/'documentation/assets/cleaned-data-summary.json').read_text())
    nmr=summary['nmr'];experimental=summary['experimental'];views=experimental['views']
    descriptions={
        'IR':t('Experimental infrared peak positions and molecular structures.','实验红外峰位置及对应分子结构。'),
        'Raman':t('Experimental Raman peak positions and molecular structures.','实验拉曼峰位置及对应分子结构。'),
        'MS':t('Numerical m/z–intensity peak lists and molecular structures.','数值化 m/z–强度峰表及对应分子结构。'),
        '11B':t('Boron chemical shifts and boron-containing structures.','硼化学位移及含硼分子结构。'),
        '19F':t('Fluorine chemical shifts and fluorinated structures.','氟化学位移及含氟分子结构。'),
        '29Si':t('Silicon chemical shifts and silicon-containing structures.','硅化学位移及含硅分子结构。'),
        '31P':t('Phosphorus chemical shifts and phosphorus-containing structures.','磷化学位移及含磷分子结构。')}
    text='# '+t('Data','数据')+'\n\n'
    text+=t('Use the dataset interface to load experimental measurements and calculated spectra. This guide describes the cleaned data, their fields, experimental conditions and train/validation/test files.\n\n','通过统一的数据接口加载实验测量与计算光谱。本节介绍清洗后可用的数据、字段、实验条件，以及训练、验证和测试文件。\n\n')
    text+='## '+t('OpenMolSpec experimental collection','OpenMolSpec 实验数据集')+'\n\n'
    rows=[('[H/C NMR](nmr.md)',t('Experimental NMR','实验 NMR'),t('Proton/carbon shifts, structures, formulas, spectral text and acquisition metadata.','氢碳化学位移、结构、分子式、谱文本与采集信息。'),f'{nmr["molecular_identities"]:,} '+t('molecules','个分子'))]
    for modality in ['11B','19F','29Si','31P','MS','IR','Raman']:
        v=views[modality];guide='nmr' if modality in ['11B','19F','29Si','31P'] else 'ms' if modality=='MS' else 'vibrational'
        rows.append((f'[{modality}]({guide}.md)',t('Experimental','实验'),descriptions[modality],f'{v["spectra"]:,} '+t('spectra','条谱')+f'; {v["molecules"]:,} '+t('molecules','个分子')))
    text+=table([t('Dataset','数据集'),t('Category','分类'),t('Description','内容描述'),t('Cleaned usable data','清洗后可用数量')],rows)
    text+=t('The collection is curated from OpenDataLab / WanJuan MolSpectra v1.0.3. H/C records are grouped by standard molecular identity. The other views retain unique numerical spectra and their source conditions.\n\n','本数据集由 OpenDataLab / WanJuan MolSpectra v1.0.3 清洗整理。H/C 按标准分子身份组织，其他视图保留去重后的数值谱及实验条件。\n\n')
    text+='![Cleaned experimental spectroscopy coverage](../assets/gallery/data-cleaned-experimental.png)\n\n'
    text+='![Cleaned molecular distributions](../assets/gallery/data-cleaned-nmr.png)\n\n'
    text+=t('Molecular size and weight for all 2,678,511 cleaned H/C records. The last bin includes larger molecules. [SVG](../assets/gallery/data-cleaned-nmr.svg) · [PDF](../assets/gallery/data-cleaned-nmr.pdf)\n\n','全部 2,678,511 条清洗后 H/C 记录的分子大小与分子量分布；最右侧一格包含更大的分子。[SVG](../assets/gallery/data-cleaned-nmr.svg) · [PDF](../assets/gallery/data-cleaned-nmr.pdf)\n\n')
    text+='## '+t('External experimental resources','外部实验资源')+'\n\n'
    text+=table([t('Dataset / view','数据集／视图'),t('Category','分类'),t('Description','内容描述'),t('Usable records','可用条目')],[
        ('NMRexp v2','NMR',t('Per-nucleus experimental NMR Parquet views; see the nucleus table.','按核种整理的实验 NMR Parquet 视图，数量见核种表。'),'[NMR](nmr.md)'),
        ('NMRSpec / NMRTrans','NMR',t('H/C spectra and target structures for retrieval and structure generation.','用于谱结构检索、结构生成的 H/C 谱与目标结构。'),'10,000'),
        ('NMRGym','NMR',t('Experimental NMR molecular structure elucidation test view.','实验 NMR 分子结构解析测试视图。'),'10,000'),
        ('MassSpecGym v1.5','MS/MS',t('Numerical tandem spectra with molecular and acquisition fields for forward prediction.','具有结构和采集字段、可用于前向预测的数值串联质谱。'),'119,029'),
        ('MassBank','MS/MS',t('Numerical MS2 spectra with valid molecular structures.','含有效分子结构的数值 MS2 谱。'),'120,512')])
    text+='## '+t('Computed spectra','计算光谱')+'\n\n'
    text+=table([t('Dataset / view','数据集／视图'),t('Category','分类'),t('Description','内容描述'),t('Usable records','可用条目')],[
        ('OpenMolSpec / openSpec test','IR / Raman / NMR',t('Paired spectra, structures and quantum-chemical properties for multimodal learning.','配对光谱、分子结构和量子化学性质，用于多模态学习。'),'20,390'),
        ('QMe14S','IR / Raman',t('Finite, nonconstant paired IR and Raman arrays across 14 elements.','覆盖 14 种元素、两通道均为有限且非常数值的 IR/Raman 配对数组。'),'184,252')])
    text+='## '+t('Load a dataset','加载数据')+'\n\n'
    text+='```python\nfrom openmolspec.dataset import molspectra\n\ndata = molspectra("opendatalab_nmr", root="data/nmr")\nrecord = data["test"].head(1)[0]\nprint(record["smiles"])\nprint(record["h_peaks_ppm"])\npaired = data["train"].select(modalities=["1H", "13C"])\n```\n\n'
    text+=t('Place the cleaned `train.jsonl`, `val.jsonl` and `test.jsonl` files in `data/nmr`. The [NMR guide](nmr.md) explains every field and the [split guide](splits.md) explains how to construct your own dataset. [Download counts and distributions](../assets/cleaned-data-summary.json).\n','将清洗后的 `train.jsonl`、`val.jsonl`、`test.jsonl` 放在 `data/nmr` 目录。[NMR 数据指南](nmr.md)解释字段，[划分指南](splits.md)说明如何构建自己的数据集。[下载计数与分布](../assets/cleaned-data-summary.json)。\n')
    out[f'data/index{suffix}.md']=text+references(['opendatalab','nmrexp','nmrtrans','nmrgym','massspecgym','massbank','qme14s','openmolspec'],en)

    text='# '+t('NMR data','NMR 数据')+'\n\n'
    text+=t('NMR records connect molecular structures to chemical shifts. The cleaned collection covers proton, carbon, boron, fluorine, silicon and phosphorus. Chemical shifts use ppm; acquisition frequencies use MHz.\n\n','NMR 记录将分子结构与化学位移连接起来。清洗后的数据覆盖氢、碳、硼、氟、硅和磷；化学位移单位为 ppm，采集频率单位为 MHz。\n\n')
    text+='## '+t('Cleaned H/C collection','清洗后的 H/C 集合')+'\n\n'
    text+=table([t('Quantity','项目'),t('Count','数量')],[(t('Molecular identities','分子身份'),f'{nmr["molecular_identities"]:,}'),('¹H spectra',f'{nmr["counts"]["h_spectra"]:,}'),('¹³C spectra',f'{nmr["counts"]["c_spectra"]:,}'),('¹H peaks',f'{nmr["counts"]["h_peaks"]:,}'),('¹³C peaks',f'{nmr["counts"]["c_peaks"]:,}'),(t('Molecules with both H and C','同时有 H/C 的分子'),'238,226')])
    text+=t('Cleaning validates the molecular structure, checks that the measured nucleus occurs in the molecule, parses numerical shifts and normalizes the molecular formula. Each retained molecule has at least one usable H or C spectrum. Molecular identity and the prepared split role are retained.\n\n','清洗包括验证结构、检查分子中存在对应核种、解析数值化学位移，以及规范分子式。保留的每个分子至少具有一条可用的氢谱或碳谱，并保留分子身份和原有划分角色。\n\n')
    text+=table([t('Field','字段'),t('Type / unit','类型／单位'),t('Meaning','含义')],[
        ('`smiles`, `inchi`, `standard_inchikey`','string',t('Molecular structure and standard identity.','分子结构与标准身份。')),
        ('`formula`','string',t('Molecular formula normalized from the structure.','由结构规范化的分子式。')),
        ('`h_peaks_ppm`, `c_peaks_ppm`','list[float] / ppm',t('Parsed proton and carbon peak positions.','解析后的氢谱与碳谱峰位置。')),
        ('`h_nmr`, `c_nmr`','list[dict]',t('Spectrum text, nucleus, frequency and source-line metadata.','谱文本、核种、频率和来源行信息。')),
        ('`modality_mask`','[has_H, has_C]',t('Which NMR channels are available.','可用的 NMR 通道。')),
        ('`h_provenance`, `c_provenance`','dict',t('Acquisition/source information for each nucleus.','各核种对应的采集与来源信息。')),
        ('`patent_id`, `year`, `source`','string',t('Original document, publication year and source collection.','原文献、发表年份与来源库。'))])
    text+=t('Use the numerical arrays for learning and plotting. Keep the spectral text when studying multiplicity, integration or coupling constants. Select solvent and frequency conditions from the nucleus-specific source record when building a condition-dependent model.\n\n','训练和绘图使用数值数组；研究多重性、积分或耦合常数时保留谱文本。构建条件相关模型时，从对应核种的原记录中选择溶剂和频率。\n\n')
    text+='![Proton and carbon chemical-shift distributions](../assets/gallery/data-cleaned-nmr-shifts.png)\n\n'
    text+='## '+t('Heteronuclear views','杂核视图')+'\n\n'
    text+=table([t('Nucleus','核种'),t('Spectra','谱数'),t('Molecules','分子数')],[(m,f'{views[m]["spectra"]:,}',f'{views[m]["molecules"]:,}') for m in ['11B','19F','29Si','31P']])
    text+=t('Each record contains `smiles`, `standard_inchikey`, `nucleus`, `peaks_ppm`, `chemical_shift`, `solvent`, `frequency` and the source document. Peak intervals are represented by their center.\n\n','每条记录包含 `smiles`、`standard_inchikey`、`nucleus`、`peaks_ppm`、`chemical_shift`、`solvent`、`frequency` 与来源文献。区间峰用中心位置表示。\n\n')
    text+='```python\nfrom openmolspec.dataset import molspectra\n\nboron = molspectra("opendatalab_11b", root="data/experimental")\nrecord = boron["test"].select(modalities="11B").head(1)[0]\nprint(record["smiles"], record["peaks_ppm"])\n```\n\n'
    text+='## NMRexp\n\n'
    text+=t('NMRexp provides experimental shifts extracted from the chemical literature in per-nucleus Parquet files. The filtered local views contain the following spectral records.\n\n','NMRexp 提供从化学文献提取的实验化学位移，按核种保存在 Parquet 文件中。筛选后的本地视图包含以下谱记录。\n\n')
    text+=table([t('Nucleus','核种'),t('Spectral records','谱记录')],[(m,f'{n:,}') for m,n in [('1H',1651821),('13C',1439344),('19F',195077),('31P',32890),('11B',16871),('29Si',2385)]])
    text+=t('NMRSpec and NMRGym provide complementary test sets for spectral retrieval and structure elucidation. Load their prepared H/C JSONL views with `molspectra("nmrspec_test", root=...)` and `molspectra("nmrgym_test", root=...)`.\n','NMRSpec 和 NMRGym 提供谱结构检索及结构解析测试集。整理后的 H/C JSONL 视图分别用 `molspectra("nmrspec_test", root=...)` 与 `molspectra("nmrgym_test", root=...)` 加载。\n')
    out[f'data/nmr{suffix}.md']=text+references(['opendatalab','nmrexp','nmrtrans','nmrgym'],en)

    text='# '+t('Mass spectrometry data','质谱数据')+'\n\n'
    text+=t('Mass spectra store m/z positions and intensities. MS/MS prediction additionally uses the ion/adduct, collision energy, instrument and precursor mass to define the acquisition conditions.\n\n','质谱数据保存 m/z 位置与强度。MS/MS 预测还使用离子／加合物、碰撞能、仪器及前体质量来定义采集条件。\n\n')
    text+='## OpenDataLab\n\n'+descriptions['MS']+f' {views["MS"]["spectra"]:,} '+t('spectra across','条谱，覆盖')+f' {views["MS"]["molecules"]:,} '+t('molecules.','个分子。')+'\n\n'
    text+=t('Cleaning retains spectra with at least two finite positive m/z values, finite nonnegative intensities and a positive intensity sum. Exact duplicates with the same molecular identity and source conditions are removed.\n\n','清洗保留至少两个有限正 m/z、强度有限非负且强度总和为正的谱；相同分子身份、谱值及实验条件的重复谱会被去除。\n\n')
    text+='![Cleaned MS molecular size and peak positions](../assets/gallery/data-cleaned-ms.png)\n\n'
    text+='```python\nfrom openmolspec.dataset import molspectra\n\ndata = molspectra("opendatalab_ms", root="data/experimental")\nrecord = data["test"].head(1)[0]\nprint(record["smiles"])\nprint(record["peaks"][:5])  # [[m/z, intensity], ...]\n```\n\n'
    text+='## MassSpecGym\n\n'
    text+=t('The v1.5 forward-prediction view contains 119,029 spectra with the acquisition fields required by the simulation task. The dataset reader preserves `spec_id`, `smiles`, `peaks`, `adduct`, `collision_energy`, `instrument` and `precursor_mz`. Use `molspectra("massspecgym_1_5", root=...)` for the TSV source, or import a prepared CSV with `SpectraSplit(format="massspecgym_csv", ...)`.\n\n','v1.5 前向预测视图包含 119,029 条具有模拟任务所需采集字段的谱。读取器保留 `spec_id`、`smiles`、`peaks`、`adduct`、`collision_energy`、`instrument` 和 `precursor_mz`。TSV 源文件用 `molspectra("massspecgym_1_5", root=...)` 加载；整理好的 CSV 使用 `SpectraSplit(format="massspecgym_csv", ...)` 导入。\n\n')
    text+='## MassBank\n\n'+t('The numerical MS2 view contains 120,512 spectra with valid molecular structures. Retain the spectrum accession, ion mode, instrument, collision conditions and source license alongside the peak array.\n','数值 MS2 视图包含 120,512 条具有有效结构的谱。使用峰数组时同时保留谱编号、离子模式、仪器、碰撞条件与来源许可信息。\n')
    out[f'data/ms{suffix}.md']=text+references(['opendatalab','massspecgym','massbank'],en)

    text='# '+t('IR and Raman data','IR 与 Raman 数据')+'\n\n'
    text+=t('Experimental views store measured peak positions. Computed views provide dense spectra and associated quantum-chemical properties for spectrum prediction, retrieval and molecular structure generation.\n\n','实验视图保存测得的峰位置；计算视图提供密集光谱及相关量子化学性质，用于谱预测、检索与分子结构生成。\n\n')
    text+='## '+t('Experimental spectra','实验光谱')+'\n\n'
    text+=table([t('Modality','模态'),t('Spectra','谱数'),t('Molecules','分子数')],[(m,f'{views[m]["spectra"]:,}',f'{views[m]["molecules"]:,}') for m in ['IR','Raman']])
    text+=t('Records contain `wavenumber_cm1`, the molecular structure, source spectrum label and acquisition metadata. `intensities` is included when measured intensities are available. Each spectrum has at least two finite positive peak positions. To construct a dense input, choose a wavenumber grid and broadening width and save those parameters with the array.\n\n','记录包含 `wavenumber_cm1`、分子结构、原谱型标签和采集信息；有实测强度时同时保存 `intensities`。每条谱至少有两个有限正峰位置。构建密集输入时，应选择波数网格和展宽宽度，并将参数与数组一起保存。\n\n')
    text+='![Experimental IR and Raman peak positions](../assets/gallery/data-cleaned-vibrational.png)\n\n'
    text+='```python\nfrom openmolspec.dataset import molspectra\n\ndata = molspectra("opendatalab_ir", root="data/experimental")\nspectrum = data["train"].head(1)[0]\nprint(spectrum["wavenumber_cm1"])\n```\n\n'
    text+='## '+t('OpenMolSpec computed test view','OpenMolSpec 计算测试视图')+'\n\n'
    text+=t('The openSpec test view contains 20,390 records. Each record provides IR and Raman arrays with 1,024 intensities on a 400–4,000 cm⁻¹ axis, a molecular structure and property targets. H/C shifts retain the checkpoint reference identifier. The HOMO–LUMO gap is stored in Hartree in the LMDB; multiply once by 27.211386245988 to obtain eV. `GapModel.predict` returns eV.\n\n','openSpec 测试视图包含 20,390 条记录。每条提供 400–4,000 cm⁻¹ 网格上的 1,024 点 IR 与 Raman 强度、分子结构和性质目标。H/C 位移保留权重对应的参考标识。LMDB 中能隙单位为 Hartree，乘一次 27.211386245988 得到 eV；`GapModel.predict` 返回 eV。\n\n')
    text+='```python\nfrom openmolspec.dataset import molspectra\n\ndata = molspectra("openspec_test", root="data/openspec_test.lmdb", trusted=True)\nrecord = data["test"].head(1)[0]\nprint(len(record["ir"]), len(record["raman"]))  # 1024 1024\n```\n\n'
    text+='## QMe14S\n\n'+t('The aligned view contains 184,252 pairs with finite, nonconstant IR and Raman values in both channels. The original resource covers 14 elements and provides response information for studying structure–spectrum relationships. The numerical arrays are aligned with the molecular filenames.\n','对齐视图包含 184,252 对 IR/Raman，两通道均为有限且非常数值。原资源覆盖 14 种元素，并提供研究结构与光谱关系所需的响应信息。数值数组已与分子文件名对应。\n')
    out[f'data/vibrational{suffix}.md']=text+references(['opendatalab','qme14s','qm9s','openmolspec'],en)

    text='# '+t('Multimodal data','多模态数据')+'\n\n'
    text+=t('A multimodal record groups the spectral channels used together by a model. Select the required channels before preparing a training batch. The H/C experimental view contains 238,226 molecules with both proton and carbon NMR; the computed openSpec view combines IR, Raman and H/C shifts.\n\n','多模态记录将模型联合使用的光谱通道组织在一起。准备训练批次前先选择所需通道。实验 H/C 视图包含 238,226 个同时具有氢谱和碳谱的分子；计算 openSpec 视图联合 IR、Raman 与 H/C 位移。\n\n')
    text+='```python\npaired = data["train"].select(modalities=["1H", "13C"], limit=100)\nfor record in paired:\n    print(record["smiles"], record["modality_mask"])\n```\n\n'
    text+=t('For experimental cross-modal joins, use the standard molecular identity and retain the source document and acquisition conditions. For geometry-to-spectrum learning, use the coordinates associated with the reference calculation. For NMR models, keep the nucleus and chemical-shift reference in the input metadata.\n','实验跨模态关联使用标准分子身份，同时保留来源文献和采集条件。构象到光谱的学习使用参考计算对应的坐标；NMR 模型输入元数据保留核种和化学位移参考。\n')
    out[f'data/multimodal{suffix}.md']=text+references(['opendatalab','openmolspec','qme14s'],en)

    text='# '+t('Dataset splits','数据集划分')+'\n\n'
    text+=t('The cleaned H/C files retain the prepared train, validation and test roles. Their standard molecular identities do not overlap across files.\n\n','清洗后的 H/C 文件保留原有训练、验证和测试角色，各文件之间的标准分子身份没有交集。\n\n')
    text+=table(['Split',t('Molecules','分子数')],[(role,f'{v["records"]:,}') for role,v in nmr['files'].items()])
    text+=t('Other experimental views use the fixed OpenMolSpec v1 scaffold partition. The table gives usable spectra in each file.\n\n','其他实验视图采用固定 OpenMolSpec v1 骨架划分。下表统计各文件中的可用谱。\n\n')
    text+=table([t('View','视图'),'Train','Validation','Test'],[(m,*[f'{v["splits"][r]:,}' for r in ['train','val','test']]) for m,v in views.items()])
    text+='## '+t('Create your own split','创建自己的划分')+'\n\n'
    text+='```python\nfrom openmolspec.split import split_records\n\nmanifest = split_records(\n    data["train"], "my-scaffold-dataset", method="scaffold",\n    seed=2026, ratios=(.8, .1, .1),\n    source="OpenDataLab", domain="experimental")\nprint(manifest["files"])\n```\n\n'
    text+=t('Use `method="scaffold"` to group by normalized Bemis–Murcko scaffold, or `method="random"` to group by molecular connectivity. The export records the seed, grouping policy, original roles and file hashes. Inspect the saved manifest to see the resulting split sizes.\n\n','`method="scaffold"` 按规范化 Bemis–Murcko 骨架分组，`method="random"` 按分子连接关系分组。导出记录随机种子、分组策略、原始角色及文件哈希；划分后的数量见保存的 manifest。\n\n')
    release='https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/v1.0/'
    text+=t('Fixed molecular-membership files: ','固定分子成员文件：')+' · '.join(f'[{label}]({release}{name})' for label,name in [('Manifest','manifest.json'),('Train','train.csv.gz'),('Validation','val.csv.gz'),('Test','test.csv.gz')])+'\n'
    out[f'data/splits{suffix}.md']=text+references(['openmolspec','opendatalab'],en)
    out[f'datasets{suffix}.md']='---\norphan: true\n---\n\n# '+t('Datasets','数据集')+'\n\n'+t('Dataset descriptions, counts and distributions are in [Data](data/index.md).\n','数据集描述、数量与分布已合并到[数据](data/index.md)。\n')
    comparison=json.loads((ROOT/'documentation/assets/cleaned-corpus-comparison.json').read_text())
    text='# '+t('Experimental corpus comparison','实验数据集比较')+'\n\n'
    text+=t('Compare molecular coverage using a full standard InChIKey for every structure. The OpenDataLab side uses the cleaned H/C collection; NMRexp uses the valid standard molecular identities in its v2 release.\n\n','使用完整标准 InChIKey 比较分子覆盖范围。OpenDataLab 一侧采用清洗后的 H/C 集合，NMRexp 一侧采用 v2 版本中的有效标准分子身份。\n\n')
    text+=table([t('Quantity','项目'),t('Molecular identities','分子身份数')],[(a if en else z,f'{comparison[key]:,}') for key,a,z in [
        ('opendatalab_cleaned','Cleaned OpenDataLab H/C collection','清洗后的 OpenDataLab H/C 集合'),
        ('nmrexp_valid_identities','NMRexp v2','NMRexp v2'),('shared','Shared identities','两库共有'),
        ('opendatalab_only','OpenDataLab identities absent from NMRexp v2','未出现在 NMRexp v2 中的 OpenDataLab 身份'),
        ('nmrexp_only','NMRexp identities absent from this H/C collection','未出现在该 H/C 集合中的 NMRexp 身份'),('union','Combined unique identities','合并后的去重身份')]])
    text+=t('Use these identity groups when selecting external evaluation data. The [split guide](splits.md) describes the fixed partitions and custom scaffold exports. [Download comparison counts](../assets/cleaned-corpus-comparison.json).\n','选择外部评测数据时可依据这些身份分组。[划分指南](splits.md)介绍固定划分及自定义骨架导出。[下载比较计数](../assets/cleaned-corpus-comparison.json)。\n')
    out[f'data/comparison{suffix}.md']=text+references(['opendatalab','nmrexp','nmrtrans','nmrgym'],en)
    out[f'corpus-comparison{suffix}.md']='---\norphan: true\n---\n\n# '+t('Corpus comparison','数据集比较')+'\n\n[Data comparison](data/comparison.md)\n'
    return out
