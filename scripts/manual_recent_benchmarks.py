"""Render the November retrieval, NMRGym and SpecMol reports in both locales."""

import hashlib
import json
from pathlib import Path

from manual_data import table

ROOT = Path(__file__).resolve().parents[1]


def report(name):
    path = ROOT / 'results' / name
    data = path.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def render(en):
    def t(english, chinese):
        return english if en else chinese

    def attachment(name, value):
        assets['assets/benchmarks/' + name] = json.dumps(value, ensure_ascii=False, indent=2) + '\n'

    assets = {}
    variants = [
        ('ir', t('IR only, masked model', 'IR 单谱，屏蔽其余通道')),
        ('raman', t('Raman only, masked model', 'Raman 单谱，屏蔽其余通道')),
        ('author', t('IR + Raman, VB-Mols', 'IR + Raman，VB-Mols')),
        ('adapted', t('IR + Raman, estimated H/C', 'IR + Raman，估计 H/C')),
        ('four', t('IR + Raman + supplied ¹H + ¹³C', 'IR + Raman + 给定 ¹H + ¹³C')),
    ]
    library = {'variants': {}}
    ranks = []
    for name, label in variants:
        filename = f'vib_library4096_{name}.json'
        data, digest = report(filename)
        if not data['complete']:
            raise ValueError(f'Incomplete release result: {filename}')
        for key in ('pool', 'query_targets', 'seed', 'shortlist', 'given_formula', 'candidate_identity'):
            if key in library and library[key] != data[key]:
                raise ValueError(f'Mismatched {key} in {filename}')
            library[key] = data[key]
        counts = [data[key] for key in ('embedding_rank', 'shortlist_itm_rank', 'exhaustive_itm_rank')]
        ranks.append([label] + [f"{row['top1_hits']} / {row['queries']}" for row in counts]
                     + [f"{counts[-1]['top5_hits']} / {counts[-1]['queries']}"])
        library['variants'][name] = {'source': filename, 'source_sha256': digest,
                                     **{k: v for k, v in data.items() if k not in library and k != 'complete'}}
    filename = 'vib_4096_matched_summary.json'
    reference, digest = report(filename)
    library['independent_reference'] = {'source': filename, 'source_sha256': digest,
                                        'channels': reference['independent_reference']}
    attachment('matched-library-4096.json', library)
    lib = '## ' + t('Retrieval and reranking in a 4,096-structure library', '4,096 个候选结构的检索与重排') + '\n\n'
    lib += t('Each of 128 queries has its target in the same bank. Embedding search and matching-head reranking of the top 32 use all queries. Exhaustive reranking scores all 4,096 candidates for the first 32 queries. Targets use canonical SMILES with stereochemistry removed. The model receives no molecular formula.',
             '128 个查询共用同一候选库，每个真结构都在库中。嵌入检索和前 32 名匹配头重排覆盖全部查询；全库重排对前 32 个查询分别给全部 4,096 个候选打分。目标按忽略立体化学的规范 SMILES 比对，模型输入不含分子式。') + '\n\n'
    lib += table([t('Input / model', '输入与模型'), t('Embedding Top-1', '嵌入 Top-1'),
                  t('Shortlist Top-1', '前 32 重排 Top-1'), t('Exhaustive Top-1', '全库重排 Top-1'),
                  t('Exhaustive Top-5', '全库重排 Top-5')], ranks)
    lib += t('An independent method compares query spectra with a theoretical spectral library. Its first-pass Top-1 counts on the 128 queries were ',
             '另一条检索路径将查询谱与独立理论参考谱库比较。128 个查询上，第一轮检索的 Top-1 命中数为 ') + ', '.join(
        f"{label} {reference['independent_reference'][mode]['reference_rank']['top1_hits']}/128"
        for mode, label in [('ir','IR'),('raman','Raman'),('ir_raman','IR + Raman'),('ir_raman_hc',t('four spectra','四谱'))]
    ) + t('. The neural library supplies candidate SMILES only.', '。上表神经模型的候选库仅提供 SMILES。') + '\n\n'
    lib += t('[Download candidates, individual ranks and model fingerprints]', '[下载候选结构、逐查询排名与模型指纹]') + '({assets}matched-library-4096.json)\n\n'

    gym, digest = report('nmrgym_nmrtrans_comparison.json')
    gym['test_protocol']['source'] = 'data/align_eval/nmrgym_test/test.jsonl'
    attachment('nmrgym-nmrtrans.json', {'source_sha256': digest, **gym})
    protocol = json.loads((ROOT/'documentation/assets/benchmarks/adaptation-protocols.json').read_text())
    n = gym['test_protocol']['n']
    inverse = '## ' + t('NMRGym spectrum-to-structure evaluation', 'NMRGym 谱到结构评测') + '\n\n'
    inverse += t(f'The 24 November comparison fixes {n:,} test records and scores exact isomeric canonical SMILES. Each model receives only its selected channels. The +formula condition additionally supplies the reference molecular formula. Greedy and beam-10 decoding have separate scores.',
                 f'11 月 24 日的对照固定 {n:,} 条测试记录，按保留立体化学的规范 SMILES 统计精确命中。每个模型仅接收所选谱种；+formula 条件额外提供参考分子式。贪心解码与 beam-10 分开计分。') + '\n\n'
    rows = []
    for condition in gym['conditions']:
        for view in condition['views']:
            selected = view['validation_selected_greedy_exact']
            rates = view['test_exact_rates']
            rows.append([
                condition['initialization'], '+' if condition['given_formula'] else '−',
                {'h':'¹H', 'c':'¹³C', 'hc':'¹H + ¹³C'}[view['view']], f"{condition['max_epochs']:,}",
                '—' if selected is None else f'{selected:.3%}', f"{view['evaluated_test_records']:,} / {n:,}",
                t('Pending', '待评测') if rates is None else ', '.join(f'{k} {v:.2%}' for k, v in rates.items()),
            ])
    inverse += table([t('Initialization', '初始化'), t('Formula', '分子式'), t('Input', '谱种'),
                      t('Epoch budget','轮数上限'), t('Validation greedy exact', '验证集贪心精确率'),
                      t('Test records scored','测试计分条数'), t('Test exact','测试精确率')], rows)
    inverse += t('Four accepted training submissions cover the dedicated NMRGym split and a pooled NMRSpec / NMRExp / patent split, each with and without molecular formula. The configurations start from generic T5-small with randomly initialized spectral encoders, four GPUs per submission and separate H, C and H+C runs. The epoch budget is the configured maximum.',
                 '四组训练提交覆盖 NMRGym 单库和 NMRSpec、NMRExp、专利三库合并数据，两类数据各有提供分子式和不提供分子式的条件。配置使用通用 T5-small 初始化，谱编码器随机初始化，每组申请四卡，分别运行 H、C、H+C。轮数列为配置上限。') + '\n\n'
    inverse += t('[Download the split and scores]', '[下载测试协议与成绩]') + '({assets}nmrgym-nmrtrans.json) · ' + t('[Training configurations and submission records]', '[训练配置与提交记录]') + '({assets}adaptation-protocols.json)\n\n'

    qa, digest = report('specmol_qa32.json')
    if not qa['complete']:
        raise ValueError('Incomplete SpecMol record')
    correct = sum(r['correct'] for r in qa['records'])
    valid = sum(r['predicted'] in ('A','B','C','D') for r in qa['records'])
    total = len(qa['records'])
    if correct/total != qa['metrics']['exact_rate'] or valid/total != qa['metrics']['format_valid_rate']:
        raise ValueError('SpecMol response metrics disagree with predictions')
    scores = {'source_sha256':digest,'task':qa['task'],'device':qa['device'],'metrics':qa['metrics'],
              'dataset_sha256':qa['source_sha256'],'index_sha256':qa['provenance']['index_sha256'],'records':qa['records']}
    attachment('specmol-qa-responses.json', scores)
    language = '## ' + t('SpecMol spectroscopy QA', 'SpecMol 谱学问答') + '\n\n'
    language += t(f'The released SpecMol-7B model answered {total} four-choice questions counting entries in NMRSpec ¹H or ¹³C peak lists on GPU. Scoring the full decoded answer gave **{correct}/{total} correct ({correct/total:.1%})** and **{valid}/{total} valid choices ({valid/total:.1%})**.',
                  f'发布版 SpecMol-7B 在 GPU 上回答了 {total} 道 NMRSpec 四选一题，任务是数出 ¹H 或 ¹³C 峰表中的条目。完整生成回答中，**{correct}/{total} 题答对（{correct/total:.1%}）**，**{valid}/{total} 个回答可解析为有效选项（{valid/total:.1%}）**。') + '\n\n'
    train = protocol['qa']['splits']['train']['n']
    val = protocol['qa']['splits']['val']['n']
    vib = protocol['vib']['counts']
    language += t(f'The separate four-GPU LoRA submission uses {train:,} training and {val:,} validation questions split by connectivity. The 24 November snapshot contains the base-model result above. The adapted-model held-out result is pending.',
                  f'另有四卡 LoRA 微调提交，按分子连通性划分 {train:,} 条训练题与 {val:,} 条验证题。11 月 24 日快照收录了上述基础模型结果，微调模型留出集成绩待回收。') + '\n\n'
    language += t('[Download all questions and decoded choices]', '[下载全部问题、生成回答与标准选项]') + '({assets}specmol-qa-responses.json)\n\n'
    vib_fit = t(f'A separate two-GPU IR + Raman adaptation submission uses connectivity-disjoint splits of {vib["train"]:,} training, {vib["val"]:,} validation and {vib["test"]} test structures. The 24 November snapshot contains its split manifest and submission receipt. Its fitted checkpoint scores are pending.',
                f'独立的 IR + Raman 双卡微调提交按连通结构划分 {vib["train"]:,} 个训练、{vib["val"]:,} 个验证和 {vib["test"]} 个测试结构。11 月 24 日快照收录了数据划分与任务提交回执，微调权重的评测结果待回收。') + '\n\n'
    return assets, lib, inverse, language, vib_fit


def heldout_sections(en):
    def t(english, chinese):
        return english if en else chinese

    records = {}
    def source(filename):
        data, digest = report(filename + '.json')
        records[filename] = {'source_sha256': digest}
        return data

    sections = {}
    assignment = 'assignment_all_heldout_sites'
    data = source(assignment)
    sites = {n: {k:v for k,v in m.items() if k != 'records'} for n,m in data['nuclei'].items()}
    records[assignment].update(scoring=data['scoring'], split=data['split'], nuclei=sites)
    sections['assignment'] = '## ' + t('Experimental atom assignments', '实验位点指认') + '\n\n' + t(
        'The fitted atom-site model was evaluated on every held-out connectivity, including unmatched experimental peaks in the accuracy denominator. Hungarian matching used tolerances of 0.5 ppm for H and 5 ppm for C. Symmetry-equivalent labelled sites count as correct.',
        '拟合的位点模型评测覆盖全部留出连通结构。匈牙利匹配采用 H 0.5 ppm、C 5 ppm 容差；正确率分母包含未匹配实验峰，匹配至对称等价标注位点也计为正确。') + '\n\n' + table(
        [t('Nucleus','核种'),t('Connectivities','连通结构'),t('Spectra','谱图'),t('Correct / labelled peaks','正确峰 / 标注峰'),t('Accuracy','正确率')],
        [[n,f"{s['connectivities']:,}",f"{s['spectra']:,}",f"{s['correct']:,} / {s['peaks']:,}",f"{s['accuracy']:.1%}"] for n,s in sites.items()])
    filename = 'solvent_all_supported_pairs'
    data = source(filename)
    records[filename].update(protocol=data['protocol'], eligible=data['eligible'])
    sections['solvent'] = '## ' + t('Cross-solvent shifts', '跨溶剂位移') + '\n\n' + t(
        'Each prediction excludes the query connectivity from fitting the ridge correction and searching reference spectra. The table weights each eligible atom–solvent pair equally.',
        '预测时从岭回归拟合与参考谱检索中剔除查询分子的全部连通结构记录。表中每个符合条件的原子与溶剂组合权重相同。') + '\n\n' + table(
        [t('Nucleus','核种'),t('Molecules','分子数'),t('Pairs','配对数'),t('Keep shift / ppm MAE','沿用源位移 / ppm MAE'),t('Reference / ppm MAE','参考谱 / ppm MAE'),t('Ridge / ppm MAE','岭回归 / ppm MAE')],
        [[n,v['molecules'],f"{v['rows']:,}",*[f"{v['pair_weighted_mae'][k]:.3f}" for k in ('unchanged','reference','ridge')]] for n,v in data['eligible'].items()])
    filename = 'nmr_cross_source_library_scale'
    data = source(filename)
    records[filename].update(results=data['results'],protocol=data['protocol'])
    sections['nmr_retrieval'] = '## ' + t('NMR retrieval across sources', '跨来源 NMR 检索') + '\n\n' + t(
        'Top-1 recall on 512 fixed queries from each source with 2,048 candidates. Known aligner training and validation structures are excluded. Each cell gives spectra-to-molecule / molecule-to-spectra recall.',
        '每个来源采用 512 个固定查询、2,048 个候选，排除已知对齐模型训练与验证结构。每格为谱到分子 / 分子到谱的 Top-1 召回率。') + '\n\n' + table(
        [t('Source','来源'),'¹H','¹³C','¹H + ¹³C'],
        [[name,*[' / '.join(f"{modes[v][direction]['2048']['r1']:.1%}" for direction in ('s2m','m2s')) for v in ('h','c','hc')]] for name,modes in data['results'].items()])
    filename = 'mechfrag_fragment_annotations'
    data = source(filename)
    frag = {k:data[k] for k in ('ppm','peaks','matched_fraction','magma_matched_fraction_same_peaks','checkpoint_sha256','interpretation')}
    records[filename].update(**frag, spectra=len(data['records']), missing_conditions=len(data['skipped']))
    sections['ms'] = '## ' + t('MS/MS fragment mass coverage', 'MS/MS 碎片质量覆盖率') + '\n\n' + t(
        f"On the same {frag['peaks']:,} observed peaks from {len(data['records'])} MassSpecGym spectra, MechFrag-MS matched {frag['matched_fraction']:.2%} and MAGMa matched {frag['magma_matched_fraction_same_peaks']:.2%} within {frag['ppm']} ppm. {len(data['skipped'])} additional spectra lacked acquisition conditions. Scoring fragment atom identities would require experimental labels.",
        f"在 {len(data['records'])} 张 MassSpecGym 谱图的同一批 {frag['peaks']:,} 个实测峰上，采用 {frag['ppm']} ppm 容差，MechFrag-MS 的质量匹配率为 {frag['matched_fraction']:.2%}，MAGMa 为 {frag['magma_matched_fraction_same_peaks']:.2%}。另有 {len(data['skipped'])} 张谱缺采集条件。碎片原子身份的准确率需要独立实验标注。") + '\n\n'
    filename = 'gap_four_channel_1024'
    data = source(filename)['results'][0]
    four = data['metrics']
    records[filename].update(metrics=four,training_mean_baseline=data['training_mean_baseline'],dataset_sha256=data['dataset']['sha256'])
    filename = 'gap_vibrational_heldout'
    partial = source(filename)
    base = partial['models']['ir']['test']['mean_baseline_mae_ev']
    mae = [partial['models'][k]['test']['mae_ev'] for k in ('ir','raman','ir_raman')]
    records[filename].update(counts=partial['counts'],test_mae_ev=dict(zip(('ir','raman','ir_raman'),mae)),mean_baseline_mae_ev=base)
    sections['gap'] = '## ' + t('HOMO–LUMO gap', 'HOMO–LUMO 能隙') + '\n\n' + t(
        f"With IR, Raman and H/C available, the model reached {four['mae_ev']:.3f} eV MAE and {four['rmse_ev']:.3f} eV RMSE on {four['examples']:,} molecules. In a separate connectivity-disjoint panel of {partial['counts']['test']:,}, models fitted for IR, Raman and IR + Raman reached {mae[0]:.3f}, {mae[1]:.3f} and {mae[2]:.3f} eV MAE. The corresponding training-mean baseline was {base:.3f} eV.",
        f"同时提供 IR、Raman、H/C 时，{four['examples']:,} 个分子的 MAE 为 {four['mae_ev']:.3f} eV，RMSE 为 {four['rmse_ev']:.3f} eV。另一组按连通结构留出的 {partial['counts']['test']:,} 个分子上，针对 IR、Raman、IR + Raman 单独拟合的模型 MAE 分别为 {mae[0]:.3f}、{mae[1]:.3f}、{mae[2]:.3f} eV，训练均值基线为 {base:.3f} eV。") + '\n\n'
    filename = 'vib_generation_rerank_replay64'
    old = source(filename); records[filename].update(totals=old['totals'],queries=old['queries'])
    filename = 'vib_generation_hc_heldout24'
    fresh = source(filename); records[filename].update(counts=fresh['counts'],queries=len(fresh['records']),selection=fresh['selection'])
    sections['generation'] = '## ' + t('Ranking generated structures', '生成结构排序') + '\n\n' + t(
        'On the original 64 four-spectrum queries, the default order of distinct valid beam candidates recovered 48 top-1 targets. Sorting by the matching head recovered 44. In a separately selected panel of 24, both orders recovered 14 top-1 and 19 top-3 targets.',
        '在原有的 64 个四谱查询上，按去重后有效 beam 候选的默认顺序，第一名命中 48 个目标；匹配头打分排序后为 44 个。另选 24 个查询后，两种顺序的第一名均命中 14 个，前三名均命中 19 个。') + '\n\n'
    filename = 'external_nmr_interfaces'
    ext = source(filename); records[filename]['interfaces'] = ext
    sections['interfaces'] = '## ' + t('External NMR interfaces', '外部 NMR 工具接口') + '\n\n' + t(
        'UltraNMR passed its upstream formula and peak-encoding example. NMRAgent exercised its planner and verifier through a local fixture with dry-run chemistry tools. ChefNMR loaded its sampling configuration and transformed 238 Real-SpecTeach inputs. These checks cover input preparation and interfaces. Model inference and accuracy remain unevaluated for all three.',
        'UltraNMR 已核验上游示例的分子式与峰编码；NMRAgent 用本地固定响应检验了规划器、验证器与化学工具的空跑流程；ChefNMR 已加载采样配置并转换 238 条 Real-SpecTeach 输入。三者目前核验到数据准备与接口层，模型推理和准确率尚待评测。') + '\n\n'
    link = t('[Download the metrics and source fingerprints]', '[下载指标与原始报告指纹]') + '({assets}heldout-tasks.json)\n\n'
    return {'assets/benchmarks/heldout-tasks.json':json.dumps(records,indent=2,ensure_ascii=False)+'\n'}, sections, link
