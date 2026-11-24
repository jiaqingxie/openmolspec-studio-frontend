"""Task descriptions written for users of the spectroscopy library."""


def profile(task,en=True):
    name=task.id;source='https://github.com/jiaqingxie/openmolspec-studio-frontend'
    if not task.enabled:
        return task.title,('Additional spectroscopy task.' if en else '其他谱学任务。'),'','','',source
    if name == 'spectroscopy.qa':
        return ('Spectral question answering with SpecMol' if en else 'SpecMol 谱学问答',
                'Ask a question about a supplied spectrum.' if en else '针对输入谱图文本提问。',
                'The released SpecMol-7B chat model receives the question and spectrum as text.' if en else '将问题与谱图文本交给发布的 SpecMol-7B 聊天模型。',
                'Score the complete choice and report response format validity. The separately labeled pilot scores only the first token.' if en else '统计完整回答的选项正确率和格式有效率，首个 token 的诊断单列。','','https://github.com/Eurekashen/SpecMol')
    if name == 'multispectral.spectrallm.generation':
        return ('Structure generation with SpectraLLM' if en else 'SpectraLLM 多谱结构生成',
                'Generate a structure from a multispectral text prompt.' if en else '根据多谱文本生成分子结构。',
                'The released 32B model reads the author system message and spectrum prompt. The reference SMILES is used only during scoring.' if en else '32B 权重读取作者提供的系统消息与谱图问题，参考 SMILES 仅用于评分。',
                'Report valid output format and canonical SMILES exact match.' if en else '统计格式有效率及规范 SMILES 完全匹配率。','','https://github.com/OPilgrim/SpectraLLM')
    if name == 'ms.annotation.mechfrag':
        return ('MS/MS fragment candidates with MechFrag-MS' if en else 'MechFrag-MS 碎片候选指认',
                'Find atom-indexed fragments consistent with observed product ion masses.' if en else '寻找质量与实测子离子一致的候选碎片及原子编号。',
                'The locked policy proposes fragment ions for the known molecule and acquisition conditions.' if en else '锁定的策略模型根据分子结构与采集条件提出碎片离子。',
                'Report observed-peak mass coverage at 10 ppm. Experimental atom masks would be needed to measure structural accuracy.' if en else '报告 10 ppm 窗口内实测峰的质量匹配覆盖率，结构正确率需要实验碎片原子标注。','','')
    if name in ('vibrational.retrieval.ir','vibrational.retrieval.raman'):
        channel='IR' if name.endswith('.ir') else 'Raman'
        return (f'{channel} spectrum-to-structure retrieval' if en else f'{channel} 单谱到结构检索',
                'Rank a SMILES library using one vibrational spectrum.' if en else '用一条振动谱在 SMILES 候选库中检索结构。',
                'Retrieve independent reference spectra and rank candidate fingerprint similarity. The native four-channel model is also evaluated with the other channels masked.' if en else '检索独立的参考谱，再按参考分子与候选的指纹相似度排序。同时对原四谱模型进行了通道屏蔽消融。',
                'Report query count, library size, Top-1/5 hits and mean reciprocal rank.' if en else '报告查询数、库规模、Top-1/5 命中数与平均倒数排名。','','')
    if name.startswith('nmr.forward.'):
        isotope=name.rsplit('.',1)[-1]
        title=f'{isotope} chemical shift prediction' if en else f'{isotope} 化学位移预测'
        purpose=(f'Predict the {isotope} chemical shifts of a molecule from its structure. Use the atom indices to display predictions on the molecular graph or compare them with measured peaks.' if en else
                 f'根据分子结构预测 {isotope} 化学位移。利用返回的原子编号，可以把预测值标到分子结构上，也可以与实测峰比较。')
        method=('NMRNet encodes the molecular geometry and predicts chemical shifts at the selected atoms. The adapter prepares a conformer, loads the nucleus-specific weights and applies the checkpoint scaler.' if en else
                'NMRNet 编码分子构象，并预测所选原子的化学位移。接口负责准备构象、加载相应核种的权重，并应用模型的位移缩放参数。')
        if isotope in ['19F','31P']:
            method=('Use the solid-state NMRNet checkpoint to generate atomwise F/P predictions for the prepared molecular geometries. The benchmark scores the saved predictions against the exact paired LMDB references. Supply the frozen-inference directory and select the cross-domain comparison option.' if en else
                '使用固态 NMRNet 权重，为准备好的分子构象生成逐原子 F/P 预测。基准将保存的预测与严格配对的 LMDB 标签计分；调用时指定冻结推理目录，并选择跨数据域比较选项。')
        metrics='MAE and RMSE are reported in ppm.' if en else 'MAE 和 RMSE 的单位均为 ppm。'
        return title,purpose,method,metrics,'','https://github.com/Colin-Jay/NMRNet'
    if name=='nmr.hsqc.transpeaknet':
        return ('HSQC cross-peak prediction' if en else 'HSQC 交叉峰预测',
                'Predict C–H cross-peaks from a known structure and solvent.' if en else '根据已知分子结构与溶剂预测碳氢交叉峰。',
                'Load the released TransPeakNet weights and encode the original SMILES with explicit hydrogens. The benchmark pairs each predicted carbon and its two ordered proton outputs with the expert row for the same carbon index.' if en else
                '加载 TransPeakNet 作者权重，按输入 SMILES 的顺序补氢建图。对每个碳位点，按原子编号将模型的碳输出和两个有序氢输出与专家标注配对。',
                'The full ZIP gives one vote to each of 479 spectra. The author notebook gives one vote to each of 511 metadata rows covering 472 spectra. The full-ZIP run uses the unknown class for 38 conflicting and seven missing solvent labels.' if en else
                '全量评测对 479 张谱等权平均。作者笔记本对溶剂表中的 511 行等权平均，覆盖 472 张谱。全量评测将 38 张有多种溶剂类别和 7 张缺溶剂记录的谱设为 unknown。',
                '', 'https://github.com/siriusxiao62/2dNMR/tree/2e93db82a9d627ac01109474e9b6e594065e3d56')
    if name=='nmr.assignment':
        return ('Peak-to-atom assignment' if en else '峰到原子的指认',
                'Assign measured NMR peaks to atoms in a known molecular structure.' if en else '将实测 NMR 峰与已知分子结构中的原子对应起来。',
                'NMRNet first predicts atomwise shifts. Symmetry-related sites are grouped, then a minimum-cost matching step pairs the measured peaks with the predicted sites. The output includes atom indices, predicted shifts, residuals and alternative assignments.' if en else
                '先用 NMRNet 预测逐原子化学位移，再合并对称相关位点，通过最小代价匹配把实测峰与预测位点对应。输出包含原子编号、预测位移、匹配残差和备选指认。',
                'Evaluate correct experimental peak-to-site assignments, counting unmatched peaks as incorrect. The assigned-site backend accepts symmetry-equivalent sites.' if en else '用实验峰到位点的真值计算正确率，未指认峰计错。自有位点模型接受对称等价位点。','','https://github.com/Colin-Jay/NMRNet')
    if name=='nmr.solvent_transfer':
        return ('Cross-solvent chemical shift transfer' if en else '跨溶剂化学位移迁移',
                'Estimate a spectrum in a target solvent from measurements in a source solvent.' if en else '从源溶剂下的实测位移估计目标溶剂中的谱。',
                'Carbon defaults to the fitted ridge correction. For hydrogen, the experimental-reference model retrieves a similar molecular environment with paired measurements in both solvents. It adds the reference solvent difference to the query shift and returns the reference molecule and atom IDs alongside the estimate.' if en else
                '碳默认使用拟合的岭回归校正，氢默认使用实验参考模型。参考模型检索具有两种溶剂配对测量的相似分子环境，把参考中的溶剂位移差加到查询位移上，同时返回参考分子和原子编号。',
                'Evaluate H and C shifts separately using MAE in ppm.' if en else '分别使用 ppm 单位的 MAE 评估 H 与 C 位移。','','https://nmrshiftdb.nmr.uni-koeln.de/')
    if name.startswith(('nmr.retrieval.','nmr.generation.')):
        view=name.split('.')[2];channels={'h':'¹H','c':'¹³C','hc':'¹H + ¹³C'}[view]
        if '.generation.' in name:
            return (f'Structure elucidation from {channels} NMR' if en else f'从 {channels} NMR 解析结构',
                    'Generate candidate molecular structures from NMR peak lists and a molecular formula.' if en else '根据 NMR 峰表和分子式生成候选结构。',
                    'The NMRTransformer spectral encoder represents the peak lists, and the molecular decoder generates SMILES with beam search. Candidates include their molecular formula agreement and decoding scores.' if en else
                    'NMRTransformer 的谱编码器将峰表转为表征，分子解码器通过 beam search 生成 SMILES。每个候选附有分子式一致性和解码分数。',
                    'Canonical top-k accuracy and valid-SMILES rate summarize generation.' if en else '用规范化结构的 top-k 准确率与有效 SMILES 比例汇总生成结果。','',source)
        direction='Spectrum-to-structure' if name.endswith('.s2m') else 'Structure-to-spectrum'
        title=f'{direction} retrieval: {channels}' if en else f'{"谱到结构" if name.endswith(".s2m") else "结构到谱"}检索：{channels}'
        return title,('Rank the candidates that best match the query molecule or spectrum.' if en else '为查询分子或谱图寻找最匹配的候选。'),('The dual encoder maps molecular structures and NMR peak lists into a shared embedding space. Candidates are ranked by embedding similarity.' if en else '双编码器将分子结构与 NMR 峰表映射到同一表征空间，并按嵌入相似度排序。'),('Report Recall@1/5/10 and mean reciprocal rank together with the candidate count.' if en else '报告 Recall@1/5/10、平均倒数排名及候选数。'),'',source
    if name.startswith('ms.forward.'):
        model=name.rsplit('.',1)[-1].upper()
        return (f'MS/MS prediction with {model}' if en else f'使用 {model} 预测 MS/MS',
                'Predict the fragment masses and intensities of a molecule under specified acquisition conditions.' if en else '在指定采集条件下预测分子的碎片质量和强度。',
                f'{model} takes the molecular structure, adduct, collision energy and instrument. Its fragment and intensity components produce a numerical MS/MS peak list.' if en else f'{model} 接收分子结构、加合物、碰撞能和仪器类型，通过碎片与强度预测模块生成 MS/MS 峰表。',
                'Compare the predicted and measured spectra using cosine and entropy similarity.' if en else '使用余弦相似度与熵相似度比较预测谱和实测谱。','','https://github.com/coleygroup/ms-pred')
    if name=='ms.annotation.magma':
        return ('MS/MS fragment annotation' if en else 'MS/MS 碎片指认',
                'Find molecular fragments that explain the measured MS/MS peaks.' if en else '为实测 MS/MS 峰寻找对应的分子碎片。',
                'MAGMa enumerates fragments of the molecular graph and matches their masses to the measured peaks. Each annotation contains its fragment formula, mass error and atom/bond indices.' if en else 'MAGMa 枚举分子图的碎片，并与实测峰的质量进行匹配。每条指认包含碎片分子式、质量误差及原子／键编号。',
                'Report matched-peak coverage and mass errors in ppm.' if en else '报告峰匹配覆盖率及 ppm 单位的质量误差。','','https://github.com/Dsadd4/MassSpecGym-MAGMA-annotation')
    source='https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/documentation/assets/benchmarks'
    if name=='vibrational.forward':
        return ('IR and Raman from a molecular geometry' if en else '从分子构象预测 IR 与 Raman',
                'Predict infrared and Raman spectra from atomic coordinates using the openSpec model.' if en else '使用 openSpec 模型，从原子坐标预测红外与拉曼光谱。',
                'The geometry model predicts the Hessian and dipole/polarizability response tensors. Normal-mode analysis converts these tensors into frequencies and activities, which are broadened onto the spectral grid.' if en else '构象模型预测 Hessian、偶极矩与极化率响应张量；通过简正模式分析得到频率与活性，再展宽为连续光谱。',
                'Compare IR and Raman separately using cosine similarity and intensity MAE.' if en else '分别使用余弦相似度和强度 MAE 比较 IR 与 Raman。','',source)
    complete=name.endswith(('.hc','_hc'));channels='IR + Raman + NMR' if complete else 'IR + Raman'
    if '.gap.' in name:
        channels={'ir':'IR','raman':'Raman','ir_raman':'IR + Raman','ir_raman_hc':'IR + Raman + NMR'}[name.rsplit('.',1)[-1]]
        return (f'HOMO–LUMO gap from {channels}' if en else f'由 {channels} 预测 HOMO–LUMO 能隙',
                'Estimate the molecular HOMO–LUMO energy gap from spectra.' if en else '根据谱图估计分子的 HOMO–LUMO 能隙。',
                ('The openSpec spectral Transformer encodes the selected channels and its regression head predicts the energy gap. The prediction is returned in eV.' if en else 'openSpec 谱 Transformer 编码所选通道，由回归头预测能隙，输出单位为 eV。') if complete else ('A ridge regressor fits pooled vibrational intensities and similarities to reference spectra. The model for the observed channels predicts the energy gap in eV.' if en else '岭回归模型使用合并频段后的振动谱强度及与参考谱的相似度。软件根据输入通道选择模型，输出单位为 eV。'),
                'Report MAE and RMSE in eV.' if en else '报告以 eV 为单位的 MAE 与 RMSE。','',source)
    generation='.generation' in name;rerank='reranking' in name
    title=('Structure generation' if generation else 'Candidate reranking' if rerank else 'Structure retrieval')+': '+channels
    zh=('结构生成' if generation else '候选重排' if rerank else '结构检索')+'：'+channels
    purpose=('Generate structures from molecular spectra.' if generation else 'Rank molecular structures by agreement with the input spectra.') if en else ('从分子谱图生成结构。' if generation else '按候选结构与输入谱图的一致性进行排序。')
    method=('The openSpec model encodes the spectral channels with Vib2Mol. Generation uses beam search and molecular matching scores; retrieval compares embeddings, and candidate reranking uses the matching head.' if en else 'openSpec 模型通过 Vib2Mol 编码谱通道。生成使用 beam search 和分子匹配分数；检索比较嵌入，候选重排使用匹配头。')
    metrics=('Report top-k accuracy for generation, and Recall@k/MRR for ranking.' if en else '生成报告 top-k 准确率，排序报告 Recall@k 与 MRR。')
    return title if en else zh,purpose,method,metrics,'',source


def profile_zh(task):
    _,purpose,method,metrics,notes,_=profile(task,False)
    return purpose,method,metrics,notes
