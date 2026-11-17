"""Publish reproducible corpus comparison and filtered retrieval results."""
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'documentation/assets'
SOURCES={
    'nmrexp':'https://zenodo.org/records/17296666',
    'nmrspec':'https://arxiv.org/html/2602.10158v1',
    'nmrtrans':'https://github.com/little1d/NMRTrans',
    'nmrgym':'https://arxiv.org/abs/2601.15763',
    'multimodal':'https://rxn4chemistry.github.io/multimodal-spectroscopic-dataset/',
}


def corpus_page(en):
    r=json.loads((ROOT/'results/corpus_comparison_20261117.json').read_text());assert r['completed']
    p,n,o=r['patent'],r['nmrexp'],r['overlap'];pc,nc=p['counts'],n['counts']
    page='# '+('Experimental data: coverage and overlap' if en else '实验数据：覆盖范围与重叠')+'\n\n'
    page+=('A count of spectra is not a count of unique molecules. We scanned the complete local patent train/validation/test files and the NMRexp v2 `1004` parquet, using a common standard-InChIKey identity. The comparison below separates records, spectral entries and molecular identities.\n\n' if en else
           '谱记录数不等于独立分子数。我们完整扫描了专利库 train/val/test 和 NMRexp v2 的 `1004` parquet，以 standard-InChIKey 统一结构身份，分别统计分子记录、谱条目和去重身份。\n\n')
    page+='## '+('Compared resources' if en else '与哪些资源比较')+'\n\n'
    page+=('| Resource | Data origin | Reported scale and unit | Main distinction |\n| --- | --- | --- | --- |\n' if en else
           '| 资源 | 数据来源 | 规模及单位 | 主要区别 |\n| --- | --- | --- | --- |\n')
    page+=(f'| OpenMolSpec patent view | Experimental, team-curated external patent records | {pc["records"]:,} molecular records; {pc["h_records"]+pc["c_records"]:,} H/C entries | H-rich corpus; {pc["H+C"]:,} records contain both H/C |\n' if en else
           f'| OpenMolSpec 专利视图 | 团队整理的外部专利实验数据 | {pc["records"]:,} 条分子记录，{pc["h_records"]+pc["c_records"]:,} 条 H/C 谱条目 | 以 H 为主，{pc["H+C"]:,} 条分子记录同时有 H/C |\n')
    page+=(f'| [NMRexp v2]({SOURCES["nmrexp"]}) | Experimental journal supporting information, 2010–2024 | {nc["records"]:,} spectral records in our full-file scan | H, C, F, P, B and Si; solvent and frequency metadata |\n' if en else
           f'| [NMRexp v2]({SOURCES["nmrexp"]}) | 2010–2024 年期刊补充材料中的实验谱 | 全文件扫描 {nc["records"]:,} 条谱记录 | H、C、F、P、B、Si 六核种及溶剂、频率元数据 |\n')
    page+=(f'| [NMRSpec / NMRTrans]({SOURCES["nmrspec"]}) | Experimental literature NMR | Paper benchmark: 239,997 molecular samples | Paired H/C structure generation; [current code]({SOURCES["nmrtrans"]}) reports a separate 21,298-record release test split |\n' if en else
           f'| [NMRSpec / NMRTrans]({SOURCES["nmrspec"]}) | 文献实验 NMR | 论文基准为 239,997 个分子样本 | 配对 H/C 结构生成；[当前代码]({SOURCES["nmrtrans"]})另报告发布版测试集 21,298 条，不能混为同一版本 |\n')
    page+=(f'| [NMRGym]({SOURCES["nmrgym"]}) | Curated experimental NMR benchmark | Paper: 269,999 unique molecules | Paired H/C, scaffold split and multiple downstream tasks |\n' if en else
           f'| [NMRGym]({SOURCES["nmrgym"]}) | 整理后的实验 NMR 基准 | 论文报告 269,999 个独立分子 | 配对 H/C、骨架划分及多项下游任务 |\n')
    page+=(f'| [Multimodal Spectroscopic Dataset]({SOURCES["multimodal"]}) | Simulated spectra of patent-derived structures | Project overview: about 790k molecules | NMR, HSQC, IR and MS; simulated observables |\n\n' if en else
           f'| [Multimodal Spectroscopic Dataset]({SOURCES["multimodal"]}) | 专利分子结构的模拟谱 | 项目页约 79 万分子 | NMR、HSQC、IR 和 MS，谱为模拟值 |\n\n')
    page+=('External counts are attributed to the cited versions, not independently recounted except NMRexp. The NMRSpec paper and current model release use different counts; we do not substitute one for the other. Sources inspected 2026-11-17.\n\n' if en else
           '外部规模按引用版本标注，除 NMRexp 外没有在此独立重数全库。NMRSpec 论文与当前模型发布版的计数不同，不能互换。来源核对日期：2026-11-17。\n\n')
    page+='## '+('Full-file molecular overlap' if en else '全文件分子身份交集')+'\n\n'
    page+='![Full corpus identity comparison](assets/gallery/corpus-comparison.png)\n\n[SVG](assets/gallery/corpus-comparison.svg) · [Data](assets/reports/corpus_comparison_20261117.json)\n\n'
    page+='| '+('Identity count | Value |' if en else '身份计数 | 数值 |')+'\n| --- | ---: |\n'
    for a,z,value in [('Patent unique identities','专利库去重身份',p['unique_standard_inchikey']),('NMRexp unique identities','NMRexp 去重身份',n['unique_standard_inchikey']),('Shared','两库共有',o['intersection']),('Patent only relative to this NMRexp version','专利库中未出现在该 NMRexp 版本',o['patent_only']),('NMRexp only relative to this patent view','NMRexp 中未出现在该专利视图',o['nmrexp_only']),('Union','两库身份并集',o['union'])]:
        page+=f'| {a if en else z} | {value:,} |\n'
    page+='\n'+(f'{o["intersection"]/p["unique_standard_inchikey"]:.2%} of patent identities and {o["intersection"]/n["unique_standard_inchikey"]:.2%} of NMRexp identities are shared. An identity absent from this NMRexp version is not automatically a new experimental measurement or absent from every other database.\n\n' if en else
        f'交集占专利库身份的 {o["intersection"]/p["unique_standard_inchikey"]:.2%}，占 NMRexp 身份的 {o["intersection"]/n["unique_standard_inchikey"]:.2%}。未出现在这一版 NMRexp 的身份，不等于新实验测量，也不等于其他所有数据库都没有。\n\n')
    page+='## '+('Metadata and paired-data checks' if en else '元数据与配对检查')+'\n\n'
    page+='| '+('Check | Patent view | NMRexp |' if en else '检查项 | 专利视图 | NMRexp |')+'\n| --- | ---: | ---: |\n'
    page+=f'| H/C spectral entries / 谱条目 | {pc["h_records"]+pc["c_records"]:,} | {nc.get("nucleus:1H",0)+nc.get("nucleus:13C",0):,} |\n'
    page+=f'| Identities with both H/C / 同时有 H/C 的身份 | {p["unique_identities_by_modality"]["H+C"]:,} | {n["unique_identities_by_modality"]["H+C"]:,} |\n'
    page+=f'| Structured solvent present / 结构化溶剂字段非空 | {pc["spectral_records_with_structured_solvent"]:,} / {pc["h_records"]+pc["c_records"]:,} | {nc["solvent_present"]:,} / {nc["records"]:,} |\n'
    page+=f'| Frequency present / 频率字段非空 | {pc["spectral_records_with_frequency"]:,} / {pc["h_records"]+pc["c_records"]:,} | {nc["frequency_present"]:,} / {nc["records"]:,} |\n\n'
    page+=(f'{pc["h_c_from_different_patents"]:,} paired patent records have different H and C patent-provenance identifiers. Likewise, aggregating NMRexp entries by identity does not prove matched acquisition conditions. A paired-input benchmark needs solvent, source and acquisition controls beyond molecular identity. Nonempty metadata is not proof of correct extraction.\n\n' if en else
        f'专利配对记录中，{pc["h_c_from_different_patents"]:,} 条的 H 与 C 来源专利标识不同。同样，按身份聚合 NMRexp 记录不能证明采集条件一致。配对输入基准还需要控制溶剂、来源和采集条件；字段非空也不代表提取正确。\n\n')
    providers={key.split(':',1)[1]:v for key,v in pc.items() if key.startswith('provider:')}
    page+=('Stored source labels: ' if en else '原文件保留的来源标签：')+', '.join(f'{key} ({value:,})' for key,value in providers.items())+'.\n\n'
    page+='## '+('Contribution and remaining evidence' if en else '贡献定位与仍需补充的证据')+'\n\n'
    page+=('The defensible contribution is the curated experimental collection together with a consistent access, task and training interface. The current H/C-paired subset is much smaller than the total patent identity count; scale alone does not establish superiority over paired H/C benchmarks. Demonstrating learning value requires fixed source-aware evaluation, training-scale curves, external transfer and multiple seeds. [Current experiments](learning-evidence.md) report what has actually run.\n\n' if en else
           '当前可支撑的贡献是整理后的实验数据，以及一致的数据访问、任务和训练接口。H/C 配对子集远小于专利库总身份数，不能仅凭总量声称优于配对 H/C 基准。学习价值需要固定来源控制的评测、训练规模曲线、外部迁移和多随机种子支撑。[当前实验](learning-evidence.md)列出已经实际跑过的内容。\n\n')
    page+=('The scan uses stored patent InChI and RDKit-generated NMRexp identities. It does not rederive every patent identity, assess manual extraction accuracy or establish redistribution rights. The local NMRexp file also matches the official v2 MD5. Full SHA-256 file fingerprints, RDKit version and validity flags are in the downloadable report. [Version evidence](assets/reports/corpus_comparison_sources.json).\n' if en else
           '扫描采用专利库保存的 InChI，以及 RDKit 从 NMRexp SMILES 生成的身份；没有逐条重建专利身份、人工评估提取精度或确认再分发权限。本地 NMRexp 文件的 MD5 也与官方 v2 一致。完整 SHA-256 文件指纹、RDKit 版本和有效性标记见可下载报告。[版本核对记录](assets/reports/corpus_comparison_sources.json)。\n')
    return page


def learning_page(en):
    report=ROOT/'results/nmr_filtered_retrieval_20261117.json'
    page='# '+('Learning evidence and controlled evaluations' if en else '学习证据与对照评测')+'\n\n'
    page+=('Software execution, frozen-model evaluation and gains from new training are separate questions. This page records their current evidence.\n\n' if en else
           '软件能运行、冻结模型有效、增加训练数据带来提升，是三个不同问题。这里分别列出当前证据。\n\n')
    page+='## '+('Actual training integration check' if en else '实际训练链路检查')+'\n\n'
    page+=('Both NMRTransformer stages completed one optimizer update on two real training records, with two validation records and no test examples. Checkpoint saving, configuration reload and repeated inference agreed. This is a successful software integration check, not a learning curve or a meaningful model accuracy result. [Report](assets/reports/sdk_training_roundtrip_20261117.json) · [Training API](api.md).\n\n' if en else
           'NMRTransformer 两个阶段均使用两个真实训练记录、两个验证记录，各完成一次优化器更新，没有使用测试样本。Checkpoint 保存、配置重载及重复推理一致性检查通过。这是成功的软件链路验证，不是学习曲线或模型精度结论。[报告](assets/reports/sdk_training_roundtrip_20261117.json) · [训练 API](api.md)。\n\n')
    page+='## '+('Retrieval with train/validation identity exclusion' if en else '排除训练／验证身份后的检索')+'\n\n'
    if report.exists():
        r=json.loads(report.read_text());assert r['completed']
        page+=(f'The frozen alignment checkpoint is evaluated on {r["protocol"]["candidate_pool"]} H/C-complete molecules per source. Both fingerprint-matched alignment train and validation files are excluded at InChIKey connectivity level, grouping stereoisomers. Seed 42 selects the pool; the same molecules and candidate identities are used for H, C and H+C ablations. No molecular formula is supplied. The checkpoint uses byte encoding with a 512-token source budget; longer NMR text is truncated by its original encoder.\n\n' if en else
               f'每个来源选取 {r["protocol"]["candidate_pool"]} 个 H/C 完整分子评估冻结编码器。按 InChIKey 连接关系排除与哈希匹配的编码器 train/val 文件重叠的身份，包括立体异构体。固定种子 42 选择候选池，H、C、H+C 消融使用完全相同的分子与候选身份，不提供分子式。该权重使用 byte 编码和 512-token 输入预算，超长 NMR 文本按原编码器规则截断。\n\n')
        page+='![Filtered retrieval modality comparison](assets/gallery/filtered-retrieval.png)\n\n[SVG](assets/gallery/filtered-retrieval.svg) · [Full report](assets/reports/nmr_filtered_retrieval_20261117.json)\n\n'
        page+='| Source | H R@1 | C R@1 | H+C R@1 | H+C R@5 | H+C R@10 |\n| --- | ---: | ---: | ---: | ---: | ---: |\n'
        for name,row in r['datasets'].items():
            v=row['views'];m=v['hc']['s2m']
            page+=f'| `{name}` | {v["h"]["s2m"]["recall_at_1"]:.1%} | {v["c"]["s2m"]["recall_at_1"]:.1%} | {m["recall_at_1"]:.1%} | {m["recall_at_5"]:.1%} | {m["recall_at_10"]:.1%} |\n'
        page+='\n'+('Table: spectrum-to-molecule retrieval. The report also includes the reverse direction, per-query ranks, shuffled-pair controls and 2,000-bootstrap intervals conditional on the fixed candidate pool. These controls do not establish unknown pretraining-history, scaffold or source-document independence. Related molecules remain possible. Missing-channel results are ablations of the same checkpoint, not separate trained models.\n\n' if en else
                   '表格为谱到分子检索。完整报告还包括反向检索、逐查询排名、随机打乱配对的对照，以及基于固定候选池的 2,000 次 bootstrap 区间。这些控制不能证明未知预训练历史、骨架或来源文档独立；仍可能存在相关分子。缺通道结果是同一 checkpoint 的消融，不是独立训练的模型。\n\n')
    else:
        page+=('The evaluation is in progress; no score is published before completion.\n\n' if en else '该评测尚在运行，完成前不发布分数。\n\n')
    page+=('The [token-budget audit](assets/reports/nmr_filtered_token_budget_20261117.json) found no truncated candidate SMILES. Some spectral texts exceed the checkpoint source budget; those original preprocessing limits remain in the scores.\n\n' if en else
           '[输入预算审计](assets/reports/nmr_filtered_token_budget_20261117.json)确认没有候选 SMILES 超长；部分谱文本超过该权重的输入预算，评分保留原模型预处理限制。\n\n')
    page+='```bash\npython scripts/evaluate_filtered_nmr.py \\\n  --workspace /path/to/OpenMolSpec \\\n  --work runs/filtered-retrieval \\\n  --output results/filtered-retrieval.json --limit 512\n```\n\n'
    page+='## '+('Experiments still required for the paper' if en else '论文仍需要的实验')+'\n\n'
    page+=('| Experiment | Status |\n| --- | --- |\n| Matched-compute data-scale curves across several seeds | Not completed; requires a suitable training queue |\n| New training with and without the patent corpus | Not completed |\n| External transfer with source/document/scaffold controls | Not completed |\n| Manual source-grounded extraction and atom-assignment quality checks | Not completed |\n\n' if en else
           '| 实验 | 状态 |\n| --- | --- |\n| 统一计算预算、多随机种子的数据规模曲线 | 未完成，需要合适的训练队列 |\n| 加入／不加入专利数据的新训练对照 | 未完成 |\n| 控制来源文档和骨架的外部迁移评测 | 未完成 |\n| 对照原文的人工提取质量与原子指认核验 | 未完成 |\n\n')
    page+='[Data comparison](corpus-comparison.md) · [Training-history audit](training-overlap.md) · [Model review](model-audit.md)\n'
    return page


def render():
    import numpy as np
    import matplotlib.pyplot as plt
    from documentation_figures import canvas, count_bars, panel, footer, BLUE, TEAL, GREY, ORANGE, clean, short_count
    from matplotlib.ticker import FuncFormatter
    for name in ('corpus_comparison_20261117','nmr_filtered_retrieval_20261117'):
        path=ROOT/'results'/f'{name}.json'
        if path.exists():shutil.copyfile(path,ASSETS/'reports'/path.name)
    report=ROOT/'results/corpus_comparison_20261117.json'
    if report.exists():
        r=json.loads(report.read_text());o=r['overlap']
        fig,axes=canvas('Experimental NMR: shared and distinct molecular coverage','Data · complete local-file census',
            'Patent train / validation / test and NMRexp v2 · full standard-InChIKey identity')
        axes[0].set_position([.185,.205,.31,.53])
        count_bars(axes[0],['Patent only','Shared','NMRexp only'],[o['patent_only'],o['intersection'],o['nmrexp_only']],[BLUE,TEAL,GREY])
        axes[0].set_xlabel('Unique molecular identities');panel(axes[0],'a','Identity partition')
        rows=[r['patent']['unique_identities_by_modality'],r['nmrexp']['unique_identities_by_modality']]
        x=np.arange(2)
        axes[1].bar(x-.18,[q['H'] for q in rows],.35,color=BLUE,label='Has H')
        axes[1].bar(x+.18,[q['H+C'] for q in rows],.35,color=TEAL,label='Has H + C')
        axes[1].set_xticks(x,['Patent','NMRexp']);axes[1].set_ylabel('Unique identities');axes[1].yaxis.set_major_formatter(FuncFormatter(short_count));clean(axes[1]);axes[1].legend();panel(axes[1],'b','Coverage of paired modalities')
        footer(fig,'Modality bars overlap and must not be added. A molecule absent from one collection is not proof of a novel measurement.','Census · not a learning benchmark')
        for ext in ('png','svg'):fig.savefig(ASSETS/'gallery'/f'corpus-comparison.{ext}',dpi=180,metadata={'Date':None} if ext=='svg' else None)
        plt.close(fig)
    report=ROOT/'results/nmr_filtered_retrieval_20261117.json'
    if report.exists():
        r=json.loads(report.read_text());fig,axes=canvas('NMR retrieval after excluding known training identities','Frozen model · controlled input ablation',
            f'{r["protocol"]["candidate_pool"]} candidates per dataset · identical H/C-complete molecules across input settings',height=6.5)
        names=list(r['datasets']);labels=['NMRSpec','Patent','NMRexp','NMRGym'];pos=np.arange(len(names))
        for ax,direction,letter,title in zip(axes,['s2m','m2s'],['a','b'],['Spectrum → molecule','Molecule → spectrum']):
            for offset,view,label,color in [(-.24,'h','H',GREY),(0,'c','C',BLUE),(.24,'hc','H+C',TEAL)]:
                scores=[r['datasets'][name]['views'][view][direction]['recall_at_1'] for name in names]
                ax.bar(pos+offset,np.array(scores)*100,width=.22,color=color,label=label)
                intervals=np.array([r['datasets'][name]['views'][view][direction]['recall_at_1_bootstrap_95ci'] for name in names])
                ax.errorbar(pos+offset,np.array(scores)*100,yerr=np.stack([np.array(scores)-intervals[:,0],intervals[:,1]-scores])*100,
                            fmt='none',ecolor='#526174',elinewidth=.8,capsize=2)
            ax.axhline(100/r['protocol']['candidate_pool'],color=ORANGE,lw=1.3,ls='--',label='Random expectation')
            ax.set_xticks(pos,labels);ax.set(ylabel='Recall@1 (%)',ylim=(0,100));clean(ax);panel(ax,letter,title)
        handles,labels=axes[1].get_legend_handles_labels()
        fig.legend(handles,labels,ncol=4,loc='lower center',bbox_to_anchor=(.51,.117),fontsize=10)
        footer(fig,'Whiskers: 95% bootstrap intervals, conditional on the fixed pool. Known train/val connectivity excluded; pretraining, scaffolds and source independence unaudited.')
        for ext in ('png','svg'):fig.savefig(ASSETS/'gallery'/f'filtered-retrieval.{ext}',dpi=180,metadata={'Date':None} if ext=='svg' else None)
        plt.close(fig)


if __name__=='__main__':render()
