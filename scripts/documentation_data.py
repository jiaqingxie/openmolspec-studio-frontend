"""Data navigation keeps measurement, representation and counting unit explicit."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def pages(en):
    suffix='' if en else '.zh';out={}
    overview='# Data\n\n'+('Explore data by spectroscopy family and by experimental or computed origin. OpenDataLab is the source label for the team-curated patent collection; external resources retain their citations. Record counts, structure identities and geometry frames are different units.\n\n' if en else
                               '按谱型及实验／计算来源选择数据。团队整理的专利库标注来源为 OpenDataLab；其他资源保留引用。谱条目、分子结构身份、构象帧是不同计数单位。\n\n')
    overview+='| '+('Collection | What is available |' if en else '数据类别 | 内容 |')+'\n| --- | --- |\n'
    for path,a,z,desc,desc_zh in [('nmr','NMR','核磁共振','OpenDataLab experimental NMR and external H/C or heteronuclear resources','OpenDataLab 实验 NMR 与外部 H/C、杂核资源'),('ms','MS','质谱','OpenDataLab mass records, MassSpecGym v1.5 and other experimental spectra','OpenDataLab 质量记录、MassSpecGym v1.5 与其他实验谱'),('vibrational','IR / Raman','红外／拉曼','Experimental peak lists and calculated OpenMolSpec, QM9S, QMe14S spectra','实验峰表，以及 OpenMolSpec、QM9S、QMe14S 计算谱'),('multimodal','Multimodal','多谱联合','Co-occurring measurements and explicitly aligned multimodal views','同记录共现测量与明确对齐的多模态视图')]:
        overview+=f'| [{a if en else z}]({path}.md) | {desc if en else desc_zh} |\n'
    overview+='\n[Dataset loading](../api.md) · [Benchmark and custom splits](splits.md) · [Distributions](../datasets.md) · [Corpus comparison](../corpus-comparison.md)\n'
    out[f'data/index{suffix}.md']=overview
    audit=ROOT/'results/opendatalab_all_modalities_20261117.json';raw=json.loads(audit.read_text()) if audit.exists() else None
    external_path=ROOT/'results/external_data_census_20261117.json'
    external=json.loads(external_path.read_text())['datasets'] if external_path.exists() else {}
    if raw:
        counts=raw['counts'];target=sum(counts['entries:'+key] for key in ['NMR','MS','IR','Raman'])
        out[f'data/index{suffix}.md']+=(f'\nThe raw collection contains **{counts["spectral_entries"]:,} characterization entries**, of which **{target:,}** are classified as NMR, MS, IR or Raman. The remainder retains other source labels, including chromatography and other characterization. Task-ready counts depend on the fields and quality tiers on each data card.\n' if en else
            f'\n原始集合包含 **{counts["spectral_entries"]:,} 条表征条目**，其中 **{target:,} 条**归为 NMR、MS、IR 或 Raman；其余保留色谱及其他表征标签。各任务可用数量按数据卡中的字段与质量层级分别报告。\n')
    massbank_path=ROOT/'results/massbank_spectrum_qualification_20261117.json'
    massbank=json.loads(massbank_path.read_text()) if massbank_path.exists() else None
    qme_path=ROOT/'results/qme14s_alignment_20261117.json'
    qme=json.loads(qme_path.read_text()) if qme_path.exists() else None
    qm9_path=ROOT/'results/qm9s_array_qualification_20261118.json'
    qm9=json.loads(qm9_path.read_text()) if qm9_path.exists() else None
    qualified_path=ROOT/'results/opendatalab_structure_qualification_20261117.json'
    qualified=json.loads(qualified_path.read_text()) if qualified_path.exists() else None
    for family,label in [('NMR','nmr'),('MS','ms'),('IR','vibrational'),('multimodal','multimodal')]:
        title={'NMR':'NMR','MS':'MS','IR':'IR / Raman','multimodal':'Multimodal / 多谱联合'}[family]
        text=f'# {title} data\n\n'
        figure={'NMR':'data-nmr-availability','MS':'data-ms-availability','IR':'data-vibrational-availability','multimodal':'data-multimodal-availability'}[family]
        if (ROOT/'documentation/assets/gallery'/f'{figure}.png').exists():
            text+=f'![{title} data availability](../assets/gallery/{figure}.png)\n\n[SVG](../assets/gallery/{figure}.svg) · [PDF](../assets/gallery/{figure}.pdf)\n\n'
        text+='## OpenDataLab\n\n'
        distribution={'NMR':'data-nmr-nuclei','MS':'data-ms-distributions','IR':'data-vibrational-distributions'}.get(family)
        if distribution and (ROOT/'documentation/assets/gallery'/f'{distribution}.png').exists():
            text=text.replace('## OpenDataLab\n\n',f'![{title} chemical distributions](../assets/gallery/{distribution}.png)\n\n[SVG](../assets/gallery/{distribution}.svg) · [PDF](../assets/gallery/{distribution}.pdf)\n\n## OpenDataLab\n\n')
        if raw:
            c=raw['counts'];q=raw['quality']
            if family=='multimodal':
                text+='| Modality combination / 模态组合 | Compound records / 化合物记录 |\n| --- | ---: |\n'
                for name,value in sorted(raw['combinations'].items(),key=lambda x:-x[1]):text+=f'| {name} | {value:,} |\n'
            else:
                for key in (['IR','Raman'] if family=='IR' else [family]):
                    text+=f'- **{key}: {c.get("entries:"+key,0):,}** '+('spectral entries' if en else '条谱条目')+f'; **{c.get("entries_with_structure_text:"+key,0):,}** '+('with structure text.' if en else '条附有结构文本。')+'\n'
                text+='\n'
                selected={key:value for key,value in q.items() if key.startswith(tuple(x+':' for x in (['IR','Raman'] if family=='IR' else [family])))}
                text+='| Availability check / 字段可用性 | Entries or values / 条目或数值 |\n| --- | ---: |\n'+''.join(f'| `{key}` | {value:,} |\n' for key,value in selected.items())+'\n'
            text+=('[Full census](../assets/reports/opendatalab_all_modalities_20261117.json) retains raw spectrum labels and exact classification rules.\n\n' if en else '[完整扫描结果](../assets/reports/opendatalab_all_modalities_20261117.json)保留原谱型标签与准确分类规则。\n\n')
            if qualified and family!='multimodal':
                keys=['ir','raman'] if family=='IR' else [family.lower()]
                text+='### Qualified molecular identities / 结构资格检查\n\n| Modality | Qualified full InChIKeys | Source entries attached to these identities |\n| --- | ---: | ---: |\n'
                for key in keys:
                    text+=f'| {key.upper()} | {qualified["modality_distributions"][key]["unique_identities"]:,} | {qualified["valid_structure_spectral_entries"][key]:,} |\n'
                text+='\n'+('Qualification requires a standard molecular identity and a supported scaffold group; it does not establish spectral extraction accuracy or task eligibility. A molecule can occur in several modalities. [Full qualification and exclusion scope](../assets/reports/opendatalab_structure_qualification_20261117.json).\n\n' if en else
                    '资格检查要求可生成标准分子身份及受支持的骨架分组，不等同于谱提取正确或已满足任务训练要求。同一分子可以出现于多个模态。[完整检查与排除范围](../assets/reports/opendatalab_structure_qualification_20261117.json)。\n\n')
        else:text+=('The complete raw-file census is running. The existing [verified H/C view](../datasets.md) remains available; final raw modality counts will be added after the scan completes.\n\n' if en else '原始全文件分类扫描正在运行。现有[已核验 H/C 视图](../datasets.md)可用；全谱型最终计数将在扫描完成后写入。\n\n')
        if family=='NMR':
            if raw and raw.get('nmr_nucleus_labels'):
                text+='### OpenDataLab nucleus labels / 核种标签\n\n| Nucleus label | Source entries |\n| --- | ---: |\n'+''.join(f'| {key} | {value:,} |\n' for key,value in raw['nmr_nucleus_labels'].items())+'\n'
            text+=('The curated H/C view contains 2,680,271 standard-InChI identities and 238,412 H/C-paired records. It preserves the original prepared train/validation/test roles. Pairing by molecular identity does not ensure matched acquisition conditions.\n\n' if en else
                   '整理后的 H/C 视图包含 2,680,271 个标准 InChI 身份、238,412 条 H/C 配对记录，保留原准备库的 train/val/test。按分子身份配对不自动意味着采集条件一致。\n\n')
            text+='## External experimental data / 外部实验数据\n\n'
            comparison=json.loads((ROOT/'results/corpus_comparison_20261117.json').read_text())
            n=comparison['nmrexp'];counts=n['counts']
            text+=(f'**NMRexp v2 complete local release:** {counts["records"]:,} spectral records / {n["unique_standard_inchikey"]:,} valid standard-InChIKey identities.\n\n' if en else
                   f'**NMRexp v2 本地全库：**{counts["records"]:,} 条谱记录、{n["unique_standard_inchikey"]:,} 个有效标准 InChIKey 身份。\n\n')
            text+='![NMRexp nucleus availability](../assets/gallery/dataset-nmrexp-nuclei.png)\n\n'
            text+='| Resource | Modalities | Citation |\n| --- | --- | --- |\n| NMRexp v2 | ¹H, ¹³C, ¹⁹F, ³¹P, ¹¹B, ²⁹Si | [Dataset](https://zenodo.org/records/17296666) |\n| NMRSpec / NMRTrans | Paired ¹H / ¹³C | [Paper](https://arxiv.org/abs/2602.10158) |\n| NMRGym | Paired ¹H / ¹³C | [Paper](https://arxiv.org/abs/2601.15763) |\n| NMRShiftDB | Assigned shifts and experimental conditions | [Project](https://nmrshiftdb.nmr.uni-koeln.de/) |\n\n'
            local=json.loads((ROOT/'documentation/assets/dataset_audit.json').read_text())['external_local_views']
            text+='### NMRexp local nucleus views / 本地核种视图\n\n| View | Spectral records |\n| --- | ---: |\n'
            for row in local:
                if row['id'].startswith('nmrexp'):text+=f'| `{row["id"]}` | {row["records"]:,} |\n'
            text+='\n'+('These filtered views overlap the complete NMRexp release and are not additional spectra.\n\n' if en else '这些过滤视图与 NMRexp 全库重叠，不应作为额外谱量相加。\n\n')
        elif family=='MS':
            text+=('A molecular-ion m/z record, a list of fragment positions, and a spectrum with numerical intensities support different tasks. Only the last supplies the full reference needed for intensity-spectrum evaluation.\n\n' if en else
                   '单点分子离子 m/z、碎片峰位列表、带数值强度的谱图支持不同任务。完整强度谱评测需要数值强度参考。\n\n')
            text+='## External experimental data / 外部实验数据\n\n- [MassSpecGym v1.5](https://huggingface.co/datasets/roman-bushuiev/MassSpecGym): updated RDKit-standardized molecular structures and benchmark files.\n- [MassBank](https://github.com/MassBank/MassBank-data): experimental spectra with per-record acquisition metadata and provenance.\n\n'
            if 'massspecgym_1_5' in external:
                m=external['massspecgym_1_5'];c=m['counts']
                text+=f'**MassSpecGym v1.5:** {c["spectra"]:,} spectra / {m["unique_connectivities"]:,} molecular connectivities. '
                text+=f'{c["valid_numeric_spectra"]:,} valid numerical peak arrays; {c["finite_collision_energy"]:,} records with finite scalar collision energy.\n\n'
                text+='```python\nfrom openmolspec.dataset import molspectra\ndata = molspectra("massspecgym_1_5", root="/path/to/versioned-tsv")\nprint(data["test"].head(1))\n```\n\n'
            if 'massbank' in external:
                m=external['massbank'];text+=f'**MassBank local snapshot:** {m["counts"]["spectral_records"]:,} records / {m["unique_accessions"]:,} accessions. MS type and acquisition metadata remain attached to each record.\n\n'
                text+='| MS type | Local records |\n| --- | ---: |\n'+''.join(f'| {key} | {value:,} |\n' for key,value in m['ms_types'].items())+'\n'
                if massbank:
                    c=massbank['counts']
                    text+=(f'Complete peak validation found **{c["valid_numeric_spectra"]:,} valid numerical spectra**, including **{c["valid_numeric_ms2_with_valid_structure"]:,} MS2 spectra with a parseable structure**; {c["unique_valid_standard_inchikeys"]:,} unique valid full standard-InChIKeys occur in the snapshot. Declared peak counts agree for every record.\n\n' if en else
                           f'全峰表检查得到 **{c["valid_numeric_spectra"]:,} 条数值有效谱**，其中 **{c["valid_numeric_ms2_with_valid_structure"]:,} 条同时具有有效结构和 MS2 标记**；该快照包含 {c["unique_valid_standard_inchikeys"]:,} 个有效完整标准 InChIKey。所有记录的声明峰数均与实际峰表一致。\n\n')
                    text+='[Numerical qualification and snapshot fingerprint / 数值检查与快照指纹](../assets/reports/massbank_spectrum_qualification_20261117.json)\n\n'
        elif family=='IR':
            text+=('Experimental peak positions and full numerical curves are separate representations. Do not treat a broadened peak list as an experimental intensity trace.\n\n' if en else '实验峰位与完整数值曲线是不同表示，不能把展宽后的峰列表当作原始实验强度曲线。\n\n')
            text+='## Computed data / 计算数据\n\n| Dataset | Local form | Citation |\n| --- | --- | --- |\n| OpenMolSpec computed observables | IR/Raman, H/C and molecular properties; geometry/reference metadata retained | [Project](https://github.com/X1nyuLu/openSpec-alpha) |\n| QM9S | Calculated IR/Raman and molecular properties | [Paper](https://www.nature.com/articles/s43588-023-00550-y) |\n| QMe14S | Calculated spectra across 14 elements; local processed arrays have 186,102 rows per channel | [Paper](https://arxiv.org/abs/2501.18876) |\n\n'
            if 'qm9s' in external:
                q=external['qm9s'];text+=f'**QM9S local view:** {q["mapping_ids"]:,} mapped records, {q["unique_canonical_isomeric_smiles"]:,} canonical isomeric structures, {q["csv_files"]:,} corresponding CSV files. These are local-view counts, distinct from the original publication total.\n\n'
            if qm9:
                c=qm9['channels']['ir'];n=c['counts']['finite_nonconstant_rows']
                text+=(f'Complete numerical scans of both QM9S bulk CSVs found **{n:,} finite, nonconstant curves per channel**, with {c["spectral_points"]:,} points over {c["axis_min_cm1"]:g}–{c["axis_max_cm1"]:g} cm⁻¹. Bulk row indices are **not yet verified against molecular mapping IDs**; this count establishes curve quality, not molecule–spectrum pairing. [Numerical report](../assets/reports/qm9s_array_qualification_20261118.json).\n\n' if en else
                    f'QM9S 两个完整 CSV 数值扫描均得到 **{n:,} 条有限、非常数曲线**，每条 {c["spectral_points"]:,} 点，覆盖 {c["axis_min_cm1"]:g}–{c["axis_max_cm1"]:g} cm⁻¹。批量 CSV 行号**尚未与分子映射 ID 核实**；这里确认曲线质量，不能据此宣称分子—谱配对已验证。[数值检查报告](../assets/reports/qm9s_array_qualification_20261118.json)。\n\n')
            if 'qme14s' in external:
                q=external['qme14s']['channels']['ir'];text+=f'**QMe14S processed arrays:** {q["records"]:,} rows × {q["shape"][1]:,} samples per channel, {q["axis_min"]:g}–{q["axis_max"]:g} cm⁻¹. '
                text+=f'Each channel contains {q["constant_rows"]:,} constant rows; {q["records"]-q["constant_rows"]:,} are nonconstant.\n\n'
                if qme:
                    c=qme['counts']
                    text+=(f'The complete raw-file check found **{c["unique_standard_inchikeys"]:,} standard-InChIKey identities** across the {c["rows"]:,} rows. IR/Raman structure-text disagreements: {c["ir_raman_structure_text_disagreements"]}. Both arrays agree with the filename-index mapping under the report’s explicit interpolation grid and 0.2% relative maximum-error tolerance. This checks numerical consistency; the original processing code is not attested.\n\n' if en else
                           f'全部原文件检查得到 **{c["unique_standard_inchikeys"]:,} 个标准 InChIKey 身份**，对应 {c["rows"]:,} 行；IR/Raman 结构文本不一致数为 {c["ir_raman_structure_text_disagreements"]}。两通道数组均通过“文件名编号对应数组行”的数值一致性检查，使用报告声明的插值网格及 0.2% 相对最大误差容差。该检查验证数值对应关系，不代表已核查原始处理代码。\n\n')
                    text+='[Complete structure/array alignment report / 完整结构与数组核对](../assets/reports/qme14s_alignment_20261117.json)\n\n'
        else:
            text+=('Co-occurrence means the source compound record contains these modalities. It does not establish same-instrument, same-solvent or same-conformer acquisition. Preserve source document, compound locator and conditions when building aligned tasks. Computed multimodal records likewise retain their geometry and NMR reference definitions.\n\n' if en else
                   '共现统计表示同一原始化合物记录列有这些模态，不自动证明它们在相同仪器、溶剂或构象下采集。构建对齐任务时，应保留来源文档、化合物位置及采集条件；计算多谱记录也保留构象与 NMR 参考定义。\n\n')
            if qme and qme.get('paired_array_quality'):
                n=qme['paired_array_quality']['both_finite_nonconstant_rows']
                text+='## Computed paired IR / Raman\n\n'
                text+=(f'QMe14S has **{n:,} aligned rows with finite, nonconstant values in both channels**, after the complete filename/array consistency check. These computed pairs are reported separately from experimental co-occurrence; their source is [QMe14S](https://arxiv.org/abs/2501.18876). [Pair-quality counts](../assets/reports/qme14s_alignment_20261117.json).\n\n' if en else
                       f'QMe14S 完成全量文件／数组对应检查后，有 **{n:,} 行同时具备有限、非常数的 IR 与 Raman 曲线**。这些计算配对与实验共现分开统计，来源为 [QMe14S](https://arxiv.org/abs/2501.18876)。[配对质量统计](../assets/reports/qme14s_alignment_20261117.json)。\n\n')
        text+='[Data index](index.md) · [Loading API](../api.md) · [Splits](splits.md) · [Theory](../theory/index.md)\n'
        if external:text+='\n[External complete-file census / 外部数据扫描](../assets/reports/external_data_census_20261117.json)\n'
        out[f'data/{label}{suffix}.md']=text
    out[f'data/splits{suffix}.md']=('# Benchmark and custom splits\n\n' if en else '# 统一基准与自定义划分\n\n')+('Registered benchmark views retain their source split roles. Use those fixed identities for comparable benchmark scores. To create a separate user dataset, explicitly export a new random or scaffold split; source data and published benchmark files remain intact.\n\n' if en else
        '注册的 benchmark 视图保留来源划分；可比评分使用固定测试身份。需要用户自定义划分时，显式导出新的随机或骨架版本，并保留来源与原始划分信息。\n\n')+'''```python
from openmolspec.dataset import molspectra
from openmolspec.split import split_records

data = molspectra('opendatalab_nmr', root='/path/to/data')
fixed = data.get_split()
# Export a NEW user dataset from your chosen input pool:
manifest = split_records(fixed['train'], 'my-scaffold-dataset',
    method='scaffold', seed=2026, ratios=(.8, .1, .1),
    source='OpenDataLab', domain='experimental')
# method='random' uses molecular-connectivity groups.
print(manifest['files'])
```

'''+('Scaffold splitting round-trips standard InChI before extracting achiral Bemis–Murcko scaffolds; acyclic molecules fall back to connectivity identities. Random splitting also groups identical connectivity, keeping repeated spectra and stereoisomers together. Stable SHA-256 assignment is independent of row order and modality. Ratios are expected proportions; large groups can produce unequal final row counts. Each export records the seed, grouping policy, RDKit version, original roles and file hashes. Empty splits are possible for small or highly homogeneous pools; inspect the manifest before training.\n' if en else
      '骨架划分先按标准 InChI 还原，再提取不含手性的 Bemis–Murcko 骨架；无环分子按连接关系分组。随机划分同样按连接关系分组，使重复谱和立体异构体保留在同一集合。SHA-256 分配不受行顺序与模态影响。比例是期望值，较大的分组会影响最终行数。导出清单记录 seed、分组策略、RDKit 版本、原始角色和文件哈希。小规模或同质数据池可能产生空集合，训练前应检查清单。\n')
    if qualified:
        report_link='../assets/reports/opendatalab_structure_qualification_20261117.json'
        overview=f'\n## '+('Standard molecular identities' if en else '标准分子身份')+'\n\n'
        overview+=(f'The complete structure/scaffold qualification retains **{qualified["unique_valid_identities"]:,} full standard-InChIKey identities**; **{qualified["benchmark_identities"]:,}** have at least one NMR, MS, IR or Raman entry and receive a fixed v1 benchmark role. These are identity counts, distinct from measurements and the curated H/C view.\n\n' if en else
            f'完整结构／骨架资格检查保留 **{qualified["unique_valid_identities"]:,} 个完整标准 InChIKey 身份**；其中 **{qualified["benchmark_identities"]:,} 个**至少具有一条 NMR、MS、IR 或 Raman 记录，进入固定 v1 分组。这里统计分子身份，与测量条目数及整理后的 H/C 视图分开。\n\n')
        overview+='![OpenDataLab molecular distributions](../assets/gallery/data-opendatalab-chemistry.png)\n\n[SVG](../assets/gallery/data-opendatalab-chemistry.svg) · [PDF](../assets/gallery/data-opendatalab-chemistry.pdf)\n\n'
        overview+=f'[Qualification and exclusions / 检查与排除范围]({report_link})\n'
        out[f'data/index{suffix}.md']+=overview
        split='\n## '+('Fixed OpenMolSpec v1 partition' if en else '固定 OpenMolSpec v1 分组')+'\n\n'
        split+=('This new identity partition spans the qualified OpenDataLab NMR/MS/IR/Raman collection. Every occurrence of a molecular connectivity and every supported scaffold stays in one role across modalities. It does not overwrite the existing curated H/C benchmark or external source folds.\n\n' if en else
            '新身份分组覆盖通过资格检查且具有 NMR／MS／IR／Raman 条目的 OpenDataLab 集合。相同连接关系与受支持骨架的分子在各模态保留同一角色；原整理 H/C benchmark 及外部来源划分单独保留。\n\n')
        ambiguity=qualified['benchmark_scaffold_ambiguities']
        split+=(f'The availability counts include {ambiguity["identities"]:,} identities from {ambiguity["connectivities"]:,} connectivity groups that yielded multiple normalized scaffolds; {ambiguity["target_modality_identities"]:,} of these identities have target-modality entries. All these forms are excluded from the fixed benchmark. Custom scaffold exports reject conflicting connectivity roles atomically; use grouped random splitting or resolve the structural forms.\n\n' if en else
            f'可用性统计中的 {ambiguity["connectivities"]:,} 个连接关系组产生了多个标准骨架，涉及 {ambiguity["identities"]:,} 个身份，其中 {ambiguity["target_modality_identities"]:,} 个有目标模态条目；这些身份不进入固定 benchmark。自定义骨架导出遇到相同连接关系的角色冲突时整体拒绝写出，可选择按连接关系随机分组或先处理结构形式。\n\n')
        split+='| Role | Molecular identities | Attached source compound records |\n| --- | ---: | ---: |\n'
        for role,row in qualified['fixed_scaffold_split'].items():split+=f'| {role} | {row["identities"]:,} | {row["source_records"]:,} |\n'
        split+='\n![Fixed identity partition](../assets/gallery/data-opendatalab-splits.png)\n\n'
        release='https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/v1.0/'
        split+=f'[Manifest with SHA-256]({release}manifest.json) · [Train]({release}train.csv.gz) · [Validation]({release}val.csv.gz) · [Test]({release}test.csv.gz)\n\n'
        split+=('Downloads contain identity membership, scaffold-group hashes and source entry counts. They contain no spectral arrays; task-specific numerical fields, acquisition conditions and eligibility must be checked against source records. The manifest attests zero cross-split scaffold or connectivity groups.\n' if en else
            '下载文件包含身份归属、骨架分组哈希和来源条目数，不包含谱数组；具体任务还需在原记录中检查数值字段、采集条件与资格。清单验证骨架和连接关系均无跨集合分组。\n')
        out[f'data/splits{suffix}.md']+=split
        multi='\n## '+('Identity-level modality union' if en else '身份级模态并集')+'\n\n'
        multi+=('These counts merge all occurrences of the same full standard InChIKey. They describe molecular coverage, separate from the source-record co-occurrence table above.\n\n' if en else
            '以下按完整标准 InChIKey 合并所有来源出现位置，用于描述分子覆盖范围，与前文的单条来源记录共现分开。\n\n')
        multi+='| Molecular modality union | Qualified identities |\n| --- | ---: |\n'
        for mask,count in sorted(qualified['identity_modality_masks'].items(),key=lambda item:-item[1]):
            label=' + '.join(name for bit,name in enumerate(['NMR','MS','IR','Raman']) if int(mask)&(1<<bit)) or 'No target modality'
            multi+=f'| {label} | {count:,} |\n'
        multi+=f'\n[Complete structure qualification]({report_link})\n'
        out[f'data/multimodal{suffix}.md']+=multi
    return out
