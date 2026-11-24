"""Generate paired English/Chinese task pages and runnable notebook demonstrations."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openmolspec_bench.catalog import TASKS

DOCS = ROOT / "documentation"


def example(task):
    if task.id == "nmr.assignment":
        return {"smiles": "CCO", "nucleus": "13C", "peaks_ppm": [18.2, 58.3], "tolerance_ppm": 5.0}
    if task.id == "nmr.solvent_transfer":
        return {"smiles": "CCO", "nucleus": "1H", "source_solvent": "CDCl3", "target_solvent": "DMSO-d6", "source_peaks_ppm": [1.2, 3.65]}
    if task.id == "nmr.formula":
        return {"h_nmr_ppm": [1.2, 3.65], "c_nmr_ppm": [18.2, 58.3], "formula_provided": False}
    if task.id == "spectroscopy.qa":
        return {"question": "How many distinct 13C shifts are listed?", "13C_shift_ppm": [18.2, 58.3]}
    if task.id.startswith("multispectral."):
        return {"ir": "1024 intensities on the documented axis", "raman": "1024 intensities on the same axis",
                "h_nmr_ppm": [1.2, 3.65], "c_nmr_ppm": [18.2, 58.3], "prompt_format": "must follow the released model's preprocessing"}
    if task.id.startswith("ms."):
        return {"spec_id": "example-input-only", "smiles": "CCO", "adduct": "[M+H]+",
                "collision_energy": 20, "instrument": "Orbitrap", "precursor_mz": 47.0491,
                "peaks": [[31.0178, 1.0], [47.0491, 0.4]]}
    if task.id == "vibrational.forward":
        return {"geometry": "Exact source Gaussian coordinates in Angstrom", "reference": "IR and Raman from the same Gaussian log",
                "example_logs": ["tests/fixtures/NISTIR-11730.log", "tests/fixtures/QM9-dsgdb9nsd_000001.log"]}
    if task.id.startswith(("vibrational.", "spectroscopy.reranking")):
        return {"ir": "1024 min-max-normalized intensities", "raman": "1024 min-max-normalized intensities",
                "wavenumber_cm1": [400, 4000], "nmr_h_shifts_ppm": [1.2, 3.65], "nmr_c_shifts_ppm": [18.2, 58.3],
                "nmr_reference_id": "must match checkpoint", "formula": "not supplied to Vib2Mol"}
    return {"smiles": "CCO", "formula": "C2H6O", "h_nmr": [{"type": "1H NMR", "chemical_shift": "1.20 (t, 3H), 3.65 (q, 2H)"}],
            "c_nmr": [{"type": "13C NMR", "chemical_shift": "18.2, 58.3"}], "modality_mask": [1, 1]}


def profile(task):
    id_ = task.id
    if not task.enabled:
        title = {"nmr.formula": "Molecular formula prediction", "spectroscopy.qa": "Spectroscopy QA",
                 "multispectral.spectrallm.generation": "SpectraLLM structure generation"}[id_]
        return (title, "Deferred at the user's request.", "Excluded from default benchmark runs; explicit requests are skipped.",
                "Any recorded results below are historical diagnostics only.", "No further model downloads, inference or training are planned for this task.",
                "https://github.com/jiaqingxie/openmolspec-studio-frontend")
    if id_ == "nmr.assignment":
        return ("H/C peak-to-atom assignment", "Propose atom assignments for measured peaks and a known structure.",
                "Run the released liquid NMRNet H/C fold-0 checkpoint directly on a seeded 3D conformer. Require complete checkpoint restoration, preserve RDKit AddHs(input SMILES) atom indices, group topological symmetry sites, and use minimum-cost matching with explicit unmatched peaks and sites. Default tolerances are 0.5 ppm for H and 5 ppm for C.",
                "Report matched fraction, residual MAE and candidate atom indices. The 32-molecule carbon run matched 488 peaks; an additional online hydrogen request completed. assignment_accuracy is null because independent atom-assignment labels were not supplied.",
                "Residual error is not assignment accuracy. Topological symmetry is not proof of magnetic equivalence. Solvent and conformer ensembles are not modeled; H/C only. See the source JSON for input geometry, checkpoint hash and sample identities.",
                "https://github.com/Colin-Jay/NMRNet")
    if id_ == "nmr.solvent_transfer":
        return ("H/C cross-solvent transfer: experimental-reference baseline", "Estimate target-solvent shifts from a measured source-solvent spectrum using paired experimental references.",
                "Use reviewed, one-dimensional H/C NMRShiftDB records; exclude calculated-condition entries, unknown/mixed solvents and conflicting repeated atom shifts. Pair the same database atom across solvents. Retrieve the nearest other molecular connectivity by Morgan Tanimoto, then the nearest source shift, and add that reference atom's measured solvent difference. No parameters are fitted. All records sharing the query connectivity, including stereoisomers, are excluded.",
                "Report H and C errors separately and compare with leaving the source shift unchanged. The completed run covers 32 distinct molecules and 296 paired atoms. Predictions expose reference molecules, atom/spectrum IDs and similarity.",
                "This is a retrieval baseline, not a pretrained neural solvent model. It does not consistently improve both nuclei over unchanged shifts. The reference library is small, and temperature/concentration/reference conventions are not independently harmonized. Neural solvent checkpoints remain unavailable.",
                "https://nmrshiftdb.nmr.uni-koeln.de/")
    if id_.startswith("ms.forward."):
        model = id_.split(".")[-1].upper()
        return (f"Molecule to MS/MS with {model}",
                "Predict an MS/MS peak list from a molecular structure under an explicitly supplied adduct, collision energy and instrument. The model parameters remain frozen.",
                "The adapter loads the authors' released checkpoint and calls their predict_mol interface. Our held-out CSV provides observed peaks; acquisition metadata must match its spectrum ID, molecule and adduct. Duplicate molecules are excluded by default.",
                "Mass is in Da/m/z. Scores use 150000 max-pooled bins over 0–1500 Da, the top 100 predicted bins, cosine similarity and entropy similarity against all observed peaks. Missing acquisition conditions are skipped without imputation. This is not identical to a benchmark that discards unassigned observed peaks.",
                "Pretrained MassSpecGym weights may overlap a differently constructed split. Training overlap and complete instrument/adduct support metadata have not been independently established.",
                "https://github.com/coleygroup/ms-pred")
    if id_ == "ms.annotation.magma":
        return ("MS/MS peak annotation with MAGMa", "Enumerate candidate molecular fragments and match their masses to observed MS/MS peaks. This is an algorithmic task and uses no trained parameters.",
                "The adapter retains MAGMa v8's original canonicalization and 10 ppm default tolerance. Every exported fragment is checked against engine_smiles, the actual graph used by the engine, rather than assuming the input SMILES has the same atom order.",
                "Report matched-peak fraction, annotated-spectrum count and checked-fragment count. A matched fragment is an algorithmic explanation, not an experimentally confirmed unique fragmentation mechanism.",
                "Hydrogen shifts, graph depth and canonicalization have specific engine semantics. Do not reinterpret graph depth as an experimentally measured reaction sequence.",
                "https://github.com/Dsadd4/MassSpecGym-MAGMA-annotation")
    if id_.startswith("vibrational.gap."):
        full = id_.endswith("ir_raman_hc")
        return ("HOMO–LUMO gap prediction: " + ("IR + Raman + H/C" if full else id_.split(".")[-1].upper()),
                "Predict the molecular HOMO–LUMO gap in eV from spectral inputs, using the existing shared spectroscopy Transformer.",
                "The checkpoint was trained for ir-raman-nmr inputs. Complete-input evaluation supplies both IR/Raman and H/C peaks. Other variants deliberately omit channels and are ablations of the same four-modality checkpoint, not separately trained unimodal models.",
                "The bundled Vib2Mol LMDB stores gap in Hartree; convert it once to eV using 27.211386245988. The prediction is unnormalized with the checkpoint's stored target mean/std. H/C normalization and reference must agree with the checkpoint. Report MAE/RMSE and the fixed training-mean baseline on exactly the same records.",
                "A small first-record sample may be biased by source order. Use seeded reservoir sampling for broader checks; missing-channel scores must remain separate from complete-input scores.",
                "https://github.com/X1nyuLu/openSpec-alpha")
    if id_.startswith("vibrational.") or id_.startswith("spectroscopy.reranking"):
        if id_ == "vibrational.forward":
            return ("Conformer to IR and Raman", "Predict vibrational spectra from a fixed molecular geometry with Xinyu openSpec's Equiformer-v3 Hessian and response checkpoints.",
                    "Use exactly the coordinates associated with the reference Gaussian spectra. The adapter checks that XYZ loading preserves those coordinates, predicts Hessian/response tensors, and reconstructs broadened normalized IR/Raman spectra.",
                    "Compare normalized predicted and reference spectra on the common 1024-point, 400–4000 cm⁻¹ axis. Report channel-wise cosine similarity and intensity MAE.",
                    "The default two real Gaussian examples establish paired execution only. Their held-out status is not audited. An independently generated RDKit conformer must not be substituted and presented as the original reference geometry.",
                    "https://github.com/X1nyuLu/openSpec-alpha")
        kind = "generation" if "generation" in id_ else "candidate reranking" if "reranking" in id_ else "bidirectional retrieval"
        return ("Vib2Mol " + kind + (" with H/C" if id_.endswith(".hc") else " with IR/Raman only"),
                "Use Xinyu's saved Vib2Mol models for spectral structure elucidation. The complete input is IR + Raman + H/C; the IR/Raman-only route is a missing-NMR ablation.",
                "Reuse the authors' encode_spectra, canonical/unique_candidates and rerank_candidates utilities. Generation defaults to beam 10 and maximum length 300, removes invalid/duplicate canonical structures, and displays the decoder order with an ITM matching probability for each candidate. No molecular formula is supplied and no nearest-neighbor cache is used.",
                "Retrieval reports both directions with the candidate-pool size and deterministic tie policy. Generation reports canonical top-1/3/5/10, validity across raw beams and reranked top-k separately. Reranking uses an explicit candidate list.",
                "Checkpoint pairs must share their H/C reference and normalization buffers. Small candidate pools can inflate retrieval numbers; publish the sample IDs, seed and source composition with every score.",
                "https://github.com/X1nyuLu/openSpec-alpha")
    if id_.startswith("nmr.retrieval."):
        view, direction = id_.split(".")[2:]
        return (f"NMR retrieval: {view.upper()}, {direction}", "Rank candidate structures from NMR spectra, or rank candidate spectra from a molecular structure, with the existing dual encoder.",
                "H-only, C-only and H+C are explicit visibility masks. The spectral encoder does not receive the molecular formula. Canonical isomeric identities define positive matches; the selected dataset supplies the candidate pool.",
                "Report Recall@1/5/10 and MRR with candidate counts. Byte-encoded candidate SMILES that exceed checkpoint capacity are excluded and counted rather than silently truncated.",
                "Scores from 16, 32 and full-dataset candidate pools are not directly comparable. Existing dataset provenance and train/test overlap still require independent audit before an accuracy claim.",
                "https://github.com/jiaqingxie/openmolspec-studio-frontend")
    if id_.startswith("nmr.generation."):
        return ("NMR-to-SMILES generation: " + id_.split(".")[-1].upper(), "Generate candidate molecular structures from experimental H/C NMR with the existing generation checkpoint.",
                "The existing model requires an explicitly supplied molecular formula. Beam candidates are ranked by validity, formula agreement and model score, following the checkpoint's inference code. No formula is derived secretly from the target structure.",
                "Report valid SMILES rate, canonical exact-match rate and formula-match rate, with the beam size, modality mask and selected records.",
                "Formula-conditioned generation must be distinguished from formula prediction and from generation without a supplied formula. Low or zero cross-dataset exact match is retained, not replaced by cached answers.",
                "https://github.com/jiaqingxie/openmolspec-studio-frontend")
    if id_.startswith("nmr.forward."):
        nucleus = id_.split(".")[-1]
        if nucleus in ("19F", "31P"):
            return (f"Structure to {nucleus} NMR: alignment audit", "Evaluate a compatible frozen model for the selected nucleus without fitting a new reference or calibrating against test labels.",
                    "Earlier cached predictions were paired with an LMDB that had subsequently changed. Their logged targets disagree with current labels, so those earlier scores are invalidated. Frozen re-inference on an exact hashed input repairs the data pairing.",
                    "The current solid-state checkpoints still have unverified reference compatibility with solution shifts and large errors after alignment repair. Keep those numbers diagnostic-only; do not add a fitted offset to make the test score smaller.",
                    "A compatible released solution checkpoint or documented reference conversion is required for a valid primary score. No retraining or fitted recalibration is permitted.",
                    "https://github.com/Colin-Jay/NMRNet")
        if nucleus in ("11B", "29Si"):
            return (f"Structure to {nucleus} NMR: frozen diagnostic", "Run the released liquid All-nucleus NMRNet checkpoint on existing atom-indexed validation records.",
                    "Completed 32 distinct molecules per nucleus using the saved scaler and full checkpoint restoration. Sample IDs and atom labels were checked against the exact inference inputs. See results/bsi_frozen_diagnostic_20261116.json and scripts/run_frozen_bsi_diagnostic.py.",
                    "Diagnostic atom-level MAE/RMSE in ppm; these are not peak-matching scores or validated held-out benchmark results.",
                    "Nucleus-specific training coverage, training overlap and experimental assignment provenance are unverified. The model has no solvent input. Primary scoring remains disabled; NMRNet++ B/Si-specific weights are still being sought. No fitting was performed.",
                    "https://github.com/Colin-Jay/NMRNet")
        return (f"Structure to {nucleus} NMR", "Predict chemical shifts for the selected nucleus from a molecular structure, using existing frozen weights where available.",
                "For H/C, score existing NMRNet and NMRNet++ predictions with their exact metadata. Unassigned experimental peak sets use minimum-error matching and retain peak-count and coverage diagnostics.",
                "Shifts and errors are in ppm. Molecule-macro matched-peak MAE/RMSE alone do not penalize every missing/extra peak; publish matched fraction and peak-count error alongside them.",
                "A peak-matching score is not atom-assignment accuracy. These H/C results score saved predictions; they do not establish validity for other nuclei.",
                "https://github.com/Colin-Jay/NMRNet")
    missing = {
        "nmr.assignment": ("Peak-to-atom assignment", "Map observed peaks to atoms in a known structure.", "Candidate approaches are frozen atomwise NMRNet plus matching, or released TransPeakNet H/C HSQC weights and matching code. Requires reference atom indices on the exact graph, symmetry handling and verified experimental assignments. Unassigned H/C peak lists do not provide assignment ground truth."),
        "nmr.solvent_transfer": ("Cross-solvent chemical-shift transfer", "Predict a spectrum under a target solvent from the same molecule in a source solvent.", "Candidate solvent-conditioned models include NMRNet++ and TransPeakNet. Their relevant weights and paired experimental records must be obtained and verified. Solvent-conditioned forward prediction alone does not validate cross-solvent transfer. A new fitted correction would violate the no-training constraint."),
        "nmr.formula": ("Molecular-formula prediction from spectra", "Predict a molecular formula without providing it as an input.", "The current NMR generator consumes a known formula and therefore cannot establish formula-prediction accuracy. A compatible released model is required."),
        "spectroscopy.qa": ("Spectroscopy question answering", "Answer a question grounded in supplied spectral evidence.", "Requires a reference-answer dataset and compatible frozen QA weights. Generic structure-generation outputs are not substituted for QA answers."),
        "multispectral.spectrallm.generation": ("Multispectral structure generation with SpectraLLM", "Predict a structure jointly from one or more spectral modalities using released SpectraLLM weights.", "The official current release is a 32B model. The locally found older 7B adapter refers to a missing base checkpoint and cannot be attached to an arbitrary model. Download the released model or provide its matching base; do not retrain."),
    }
    title, purpose, requirement = missing[id_]
    if id_ in ("nmr.formula", "spectroscopy.qa"):
        return (title, purpose, requirement + " A separate local MolSpect-7B zero-shot probe uses real H/C records and the stored chat template, with no supplied formula or structure and a 32-new-token greedy limit.",
                "Completed diagnostic reports show exact formula accuracy or explicit 13C-entry-count answer accuracy; incomplete runs are excluded.",
                "The local checkpoint release/stage and prompt compatibility are unverified. This probe is neither an official MolSpectLLM reproduction nor a SpectraLLM32B benchmark, and does not enable the primary task adapter. No training is performed.",
                "https://github.com/Eurekashen/SpecMol")
    return title, purpose, requirement, "No validated score is emitted while required assets or adapters are missing.", "This task remains explicit in the catalog and is skipped rather than trained to completion.", "https://github.com/siriusxiao62/2dNMR" if id_ in ("nmr.assignment", "nmr.solvent_transfer") else "https://github.com/OPilgrim/SpectraLLM"


def profile_zh(task):
    id_ = task.id
    if not task.enabled:
        return ("按用户要求暂不推进。", "已从默认评测任务中排除，显式调用也会跳过。",
                "下方已有结果仅作历史诊断归档。", "该任务不再下载模型、运行推理或训练。")
    if id_ in ("nmr.formula", "spectroscopy.qa"):
        return ("分别检查无给定分子式的预测，以及基于谱图证据的问答；正式适配器仍缺已验证的兼容权重。",
                "另设本地 MolSpect-7B 零样本探测：输入真实 H/C 谱及问题，使用权重自带聊天模板，不提供分子式或 SMILES，贪心解码最多 32 个新 token。",
                "只读取已完成的诊断报告，分别报告分子式 exact accuracy 或明确列出的 13C 位移条目计数正确率。未完成运行不汇总成绩。",
                "本地权重对应的发布版本、训练阶段和提示兼容性未核实；该探测不等于官方 MolSpectLLM 或 SpectraLLM32B 复现，也不会将正式任务标记为可用。全程不训练。")
    if id_.startswith("ms.forward."):
        return ("给定分子结构、加合物、碰撞能和仪器，预测 MS/MS 的 m/z–强度峰列表。",
                "直接加载作者发布的冻结 checkpoint，调用 predict_mol。用我们测试 CSV 中的实测谱评分，并按谱图 ID、规范分子结构和加合物核对采集元数据。默认每个分子只取一条谱，避免多碰撞能重复分子主导平均值。",
                "m/z 单位为 Da。用 0–1500 Da、150000 个 bin，bin 内 max pooling，保留预测强度最高的 100 个 bin，计算与全部实测峰的余弦相似度和熵相似度。缺少碰撞能或仪器时不补造条件，明确跳过。",
                "该口径保留全部实测峰，不等同于只保留可指认峰的 benchmark。预训练使用 MassSpecGym，当前自建划分与权重训练集重叠尚未独立核验；旧权重的仪器/加合物训练覆盖元数据也不完整。")
    if id_ == "ms.annotation.magma":
        return ("从已知分子枚举候选碎片，用质量误差匹配实测 MS/MS 谱峰，无需模型训练。",
                "保留 MAGMa v8 原来的规范化和默认 10 ppm 容差。片段原子编号按引擎实际使用的 engine_smiles 解释，逐片检查原子元素计数、原子范围和键连接；不能直接套到输入 SMILES 的原子顺序。",
                "报告匹配谱峰比例、成功标注谱图数及检查的碎片数。候选片段和根到片段路径是算法解释，不能当作实验确认的唯一碎裂机制。",
                "氢迁移、图深度、断键数等字段沿用原算法语义。默认规范化会改变原子顺序，必须保留 engine_smiles；不擅自改动枚举和匹配算法。")
    if id_.startswith("vibrational.gap."):
        return ("由谱图预测 HOMO–LUMO gap，使用已有共享谱学 Transformer，输出 eV。",
                "该 checkpoint 的训练模态是 IR+Raman+H/C。完整输入配置提供四种谱；IR-only、Raman-only 和 IR+Raman 是同一模型的缺通道消融，不是独立训练的单谱模型。",
                "原 Vib2Mol LMDB 的 gap 为 Hartree，仅乘一次 27.211386245988 转 eV。模型输出按 checkpoint 保存的均值和标准差反归一化，H/C 使用权重内的中心、尺度与参考 ID。报告 MAE/RMSE，并在相同样本上报告训练均值常量基线。",
                "按文件顺序的首批样本可能来源偏倚，较广的检查使用固定种子的 reservoir 抽样。缺通道与完整输入的成绩必须分开解释。")
    if id_ == "vibrational.forward":
        return ("从固定分子构象预测 IR/Raman，复用 Xinyu openSpec 项目的 Equiformer-v3 Hessian 和 response 权重。",
                "坐标与参考谱必须来自同一 Gaussian 日志；检查 XYZ 加载后坐标不变，预测 Hessian/响应导数，再经振动模和展宽重建谱图。",
                "预测与参考均使用 400–4000 cm⁻¹ 的 1024 点轴和 min-max 强度归一化，分别报告 IR/Raman 的余弦相似度及强度 MAE。",
                "默认两个真实 Gaussian 日志仅用于配对运行检查，未审计其独立测试身份。不能用新生成的 RDKit 构象代替原参考几何后宣称是严格配对精度。")
    if id_.startswith("vibrational.") or id_.startswith("spectroscopy.reranking"):
        return ("使用 Xinyu 保存的 Vib2Mol 模型完成结构检索、SMILES 生成或候选重排。完整输入为 IR+Raman+H/C；仅 IR/Raman 的路径作为缺核消融。",
                "复用原实现的 encode_spectra、canonical/unique_candidates 与 rerank_candidates。生成默认 beam=10、最大长度 300；先移除无效和重复规范结构，默认保留有效候选的解码顺序，另附 ITM 匹配概率，支持按该概率重排。不提供分子式，也不使用近邻缓存回放。",
                "检索报告双向 Recall@1/5/10、MRR 和候选池大小。生成同时报告原始 beam 的有效率、规范去重后的 top-1/3/5/10 及重排后的 top-k；重排始终使用明确的候选列表。",
                "生成与重排 checkpoint 的 H/C 参考和归一化缓冲必须一致。小候选池可能让检索分数偏高，必须公布样本 ID、种子和来源组成。")
    if id_.startswith("nmr.retrieval."):
        return ("用已有双编码器，从 NMR 谱检索候选分子，或由分子检索候选谱。",
                "H-only、C-only、H+C 使用明确的可见性 mask，谱编码器不接收分子式。规范异构 SMILES 用于判定对应关系，所选测试分子构成本次候选池。",
                "报告 Recall@1/5/10、MRR、查询数和候选数。byte 分子编码器遇到超长 SMILES 时排除并计数，补取后续合格记录，不截断分子结构。",
                "16、32 和全库候选的成绩不能直接比较。数据来源和训练/测试重叠仍需单独审计。JSONL 中的 smiles 是评测目标或候选身份，不作为谱编码器的输入。")
    if id_.startswith("nmr.generation."):
        return ("用已有生成模型从实验 H/C NMR 预测 SMILES 候选。",
                "该模型需要显式给定分子式。按原推理代码的有效性、分子式一致性和模型分数排序 beam，取 top-1 评分。不会从目标 SMILES 偷偷推导缺失的输入分子式。",
                "报告有效 SMILES 比率、规范异构 SMILES exact match、分子式一致率，同时保存 beam size、模态 mask 和样本。JSONL 的 smiles 仅是评测答案，不是生成输入。",
                "给定分子式的结构生成与分子式预测、无分子式生成是不同任务。跨数据集 exact match 低或为零时保留真实结果，不替换成缓存答案。")
    if id_.startswith("nmr.forward."):
        nucleus = id_.split(".")[-1]
        if nucleus in ("19F", "31P"):
            return (f"检查已有 {nucleus} 预测与实验参考的配对、位移参考和适用域，不拟合新的校正参数。",
                    "旧预测对应的 LMDB 后来发生变化，保存的 target 与当前标签不一致，旧 MAE 已撤回。冻结权重对带哈希的同一份输入重新推理，可以修复样本配对。",
                    "配对修复后的固相 checkpoint 在实验溶液数据上误差仍很大，且位移参考兼容性未确认，仅保留为诊断，不作为正式溶液模型成绩。",
                    "需要兼容的现成溶液 checkpoint，或作者明确提供的参考转换。不得对测试标签拟合一个偏移来降低误差，也不启动重新训练。")
        if nucleus in ("11B", "29Si"):
            return (f"用已训练的液相 All-nucleus NMRNet 对 {nucleus} 验证数据做冻结推理。",
                    "B、Si 各完成 32 个不同分子，复用保存的 scaler，检查完整加载全部权重，并通过样本 ID 核对原子标签。证据为 results/bsi_frozen_diagnostic_20261116.json；复现脚本为 scripts/run_frozen_bsi_diagnostic.py。",
                    "报告逐原子 MAE/RMSE，单位 ppm；这是诊断值，不是峰匹配分数或已验证的独立测试成绩。",
                    "各核训练覆盖、训练重叠及实验原子指认来源尚未核实，且该模型不输入溶剂。正式评分仍停用；继续核查 NMRNet++ 的 B/Si 专用权重，不拟合任何校正。")
        return (f"由分子结构预测 {nucleus} 化学位移，已有兼容权重时进行冻结推理或已有预测评分。",
                "H/C 读取 NMRNet、NMRNet++ 的预测及对应元数据；未指认实验峰用最小绝对误差匹配，并保留峰数和覆盖率诊断。",
                "位移和误差单位均为 ppm。按分子等权计算匹配峰 MAE/RMSE，必须同时报告匹配比例与峰数误差，因为匹配误差本身不惩罚全部缺失峰或额外峰。",
                "峰匹配误差不是逐原子指认准确率。这里对 H/C 保存的预测评分，不据此外推其他核种的适用性。")
    if id_ == "nmr.assignment":
        return ("给定结构和实测 H/C 峰，预测逐原子位移并输出候选指认。",
                "直接加载液相 NMRNet H/C fold-0 权重，固定种子生成构象；完整恢复权重，保存 RDKit AddHs(input SMILES) 的 0 起始原子编号。按拓扑对称性合并位点，再做带未匹配项的最小代价匹配。H/C 默认容差分别为 0.5/5 ppm。",
                "32 个碳谱分子已完成，匹配 488 个峰；另有真实在线氢谱请求。报告覆盖率、残差、原子编号及歧义候选；缺少独立实验指认答案时 assignment_accuracy 为 null。",
                "匹配残差不等于指认准确率；拓扑对称不保证磁等价。模型不输入溶剂，未做构象系综平均，目前仅覆盖 H/C。")
    if id_ == "nmr.solvent_transfer":
        return ("用跨溶剂实验参考估计目标位移；当前提供无训练的参考检索基线。",
                "从 NMRShiftDB 审核通过的 H/C 一维数据中排除计算记录、混合/未知溶剂及重复测量冲突，按同一数据库原子配对。先按 Morgan 相似度选其他分子，再选最接近的源位移，加入该参考原子的实测溶剂差。排除查询分子及相同连接关系的所有立体异构体，不拟合参数。",
                "已跑 32 个不同分子、296 个原子位移对；按 H/C 分别报告 MAE，并与源位移不变的基线比较。输出参考分子、原子/谱图 ID 和相似度。",
                "这不是神经网络溶剂模型，对两种核尚无稳定收益。参考库较小，温度、浓度及位移参考尚未统一核验；专用神经网络权重仍待取得。")
    return (task.note, "本任务需符合输入定义的现成权重、参考数据与适配器。", "缺少必需条件时不产生占位分数。", "保持明确的待接入状态；如果必须重新训练才能完成，则按用户要求跳过。")


def observations():
    preferred = ["smoke_nmr_20261115_v2.json", "smoke_forward_20261115_v3.json", "fp_alignment_audit_20261115.json",
                 "fp_primary_score_gate_20261116.json",
                 "gap_protocol_audit_20261115.json", "gap_protocol_random128_20261116.json", "vib2mol_xinyu_protocol_20261115.json",
                 "vib2mol_xinyu_random64_20261116.json", "vibrational_forward_paired_logs_20261116.json",
                 "ms_glacier_32_molecules_20261116.json", "ms_iceberg_32_molecules_20261116.json", "magma_real_test_verified_20261115.json",
                 "assignment_carbon32_20261116.json", "solvent_transfer_reference32_20261116.json"]
    result = {}
    for name in preferred:
        path = ROOT / "results" / name
        if not path.is_file():
            continue
        payload = json.loads(path.read_text())
        if not (payload.get("completed_at") or payload.get("completed")):
            continue
        for row in payload.get("results", [payload] if "task" in payload else []):
            id_ = row.get("task")
            if not id_:
                continue
            brief = {key: row[key] for key in ("task", "dataset_name", "status", "metrics", "counts", "reason", "examples", "given_nmr", "beam_size", "reranked_metrics", "source_counts", "selection", "sampling", "seed", "training_mean_baseline", "unique_molecules", "model_kind", "purpose", "limitations") if key in row}
            brief["source_file"] = name
            brief["sample_limit"] = payload.get("limit", len(payload.get("records", [])))
            if "models" in row:
                brief["models"] = [{"model": model["model"], "metrics": model["metrics"]} for model in row["models"]]
            if id_.startswith(("nmr.retrieval", "nmr.generation", "nmr.forward.1H", "nmr.forward.13C")):
                result.setdefault(id_, []).append(brief)
            else:
                result[id_] = [brief]
    name = "molspect_zeroshot_formula_qa_20261116.json"
    path = ROOT / "results" / name
    if path.is_file():
        payload = json.loads(path.read_text())
        if payload.get("completed") is True:
            for task in ("nmr.formula", "spectroscopy.qa"):
                metrics = payload["metrics"][task]
                rows = [row for row in payload["records"] if row["task"] == task]
                if not rows or len(rows) != metrics["examples"] or metrics["accuracy"] != sum(row["correct"] for row in rows) / len(rows):
                    raise ValueError("MolSpect completed report metrics disagree with records")
                result[task] = [{"task": task, "status": "diagnostic_only", "model": payload["model"],
                                 "scope": payload["scope"], "metrics": metrics, "decoding": payload["decoding"],
                                 "formula_provided_to_model": payload["formula_provided_to_model"],
                                 "source_file": name, "sample_limit": len(rows)}]
    name = "bsi_frozen_diagnostic_20261116.json"
    path = ROOT / "results" / name
    if path.is_file():
        payload = json.loads(path.read_text())
        if payload.get("completed") is True:
            for symbol, row in payload["nuclei"].items():
                task = "nmr.forward." + {"B": "11B", "Si": "29Si"}[symbol]
                result[task] = [{"task": task, "status": "diagnostic_only",
                                 "model": "NMRNet liquid All-nucleus fold 0",
                                 "metrics": {k: row[k] for k in ("mae_ppm", "rmse_ppm")},
                                 "molecules": row["molecules"], "atoms": row["atoms"],
                                 "primary_score_eligible": False, "limitations": payload["limitations"],
                                 "label_alignment_verified": row["label_alignment_verified"],
                                 "source_file": name, "sample_limit": row["molecules"]}]
    return result


def build():
    from documentation_pages import build_pages
    from build_api_reference import build as build_api
    from manual_profiles import profile as user_profile,profile_zh as user_profile_zh
    pages=build_pages(TASKS, user_profile, user_profile_zh)
    pages.update(build_api())
    from manual_benchmarks import pages as benchmark_pages
    from manual_sdk import pages as sdk_pages
    for en in [True,False]:
        pages.update(benchmark_pages(TASKS,en))
        pages.update(sdk_pages(en))
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failures = []
    for name, content in build().items():
        path = DOCS / name
        if args.check:
            if not path.is_file():
                failures.append(name)
            elif name.endswith(".ipynb"):
                stored, expected = json.loads(path.read_text()), json.loads(content)
                for cell, reference in zip(stored["cells"], expected["cells"]):
                    source = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
                    if source != "".join(reference["source"]):
                        failures.append(name)
                        break
                if len(stored["cells"]) != len(expected["cells"]):
                    failures.append(name)
            elif path.read_text() != content:
                failures.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith('.ipynb'):
                from documentation_notebooks import write_notebook
                write_notebook(path,json.loads(content))
            else:path.write_text(content)
    if failures:
        raise SystemExit("Regenerate bilingual documentation: " + ", ".join(failures))
    print(f"Bilingual task docs prepared for {len(TASKS)} tasks")


if __name__ == "__main__":
    main()
