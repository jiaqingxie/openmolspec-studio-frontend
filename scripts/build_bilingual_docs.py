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
        return {"smiles": "CCO", "nucleus": "13C", "observed_peaks_ppm": [18.2, 58.3],
                "atom_index_basis": "RDKit molecule reconstructed from the exact input SMILES"}
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
            return ("Conformer to IR and Raman", "Predict vibrational spectra from a fixed molecular geometry with existing Hessian and response models.",
                    "Use exactly the coordinates associated with the reference Gaussian spectra. The adapter checks that XYZ loading preserves those coordinates, predicts Hessian/response tensors, and reconstructs broadened normalized IR/Raman spectra.",
                    "Compare normalized predicted and reference spectra on the common 1024-point, 400–4000 cm⁻¹ axis. Report channel-wise cosine similarity and intensity MAE.",
                    "The default two real Gaussian examples establish paired execution only. Their held-out status is not audited. An independently generated RDKit conformer must not be substituted and presented as the original reference geometry.",
                    "https://github.com/X1nyuLu/openSpec-alpha")
        kind = "generation" if "generation" in id_ else "candidate reranking" if "reranking" in id_ else "bidirectional retrieval"
        return ("Vib2Mol " + kind + (" with H/C" if id_.endswith(".hc") else " with IR/Raman only"),
                "Use Xinyu's saved Vib2Mol models for spectral structure elucidation. The complete input is IR + Raman + H/C; the IR/Raman-only route is a missing-NMR ablation.",
                "Reuse the authors' encode_spectra, canonical/unique_candidates and rerank_candidates utilities. Generation defaults to beam 10 and maximum length 300, removes invalid/duplicate canonical structures, and reranks up to 10 candidates by ITM positive-class probability. No molecular formula is supplied and no nearest-neighbor cache is used.",
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
        return (f"Structure to {nucleus} NMR", "Predict chemical shifts for the selected nucleus from a molecular structure, using existing frozen weights where available.",
                "For H/C, score existing NMRNet and NMRNet++ predictions with their exact metadata. Unassigned experimental peak sets use minimum-error matching and retain peak-count and coverage diagnostics. B/Si currently lack a verified compatible weight/prediction pair.",
                "Shifts and errors are in ppm. Molecule-macro matched-peak MAE/RMSE alone do not penalize every missing/extra peak; publish matched fraction and peak-count error alongside them.",
                "A peak-matching score is not atom-assignment accuracy. Missing compatible B/Si weights cause an explicit skip; this project does not train new heads to fill that gap.",
                "https://github.com/Colin-Jay/NMRNet")
    missing = {
        "nmr.assignment": ("Peak-to-atom assignment", "Map observed peaks to atoms in a known structure.", "Requires reference atom indices on the exact graph and a compatible pretrained assignment/prediction model. Unassigned H/C peak lists do not provide assignment ground truth."),
        "nmr.solvent_transfer": ("Cross-solvent chemical-shift transfer", "Predict a spectrum under a target solvent from the same molecule in a source solvent.", "Requires paired experimental records and an existing solvent-conditioned model. A new fitted solvent correction would violate the no-training constraint."),
        "nmr.formula": ("Molecular-formula prediction from spectra", "Predict a molecular formula without providing it as an input.", "The current NMR generator consumes a known formula and therefore cannot establish formula-prediction accuracy. A compatible released model is required."),
        "spectroscopy.qa": ("Spectroscopy question answering", "Answer a question grounded in supplied spectral evidence.", "Requires a reference-answer dataset and compatible frozen QA weights. Generic structure-generation outputs are not substituted for QA answers."),
        "multispectral.spectrallm.generation": ("Multispectral structure generation with SpectraLLM", "Predict a structure jointly from one or more spectral modalities using released SpectraLLM weights.", "The official current release is a 32B model. The locally found older 7B adapter refers to a missing base checkpoint and cannot be attached to an arbitrary model. Download the released model or provide its matching base; do not retrain."),
    }
    title, purpose, requirement = missing[id_]
    return title, purpose, requirement, "No validated score is emitted while required assets or adapters are missing.", "This task remains explicit in the catalog and is skipped rather than trained to completion.", "https://github.com/OPilgrim/SpectraLLM" if "spectrallm" in id_ else "https://github.com/jiaqingxie/openmolspec-studio-frontend"


def profile_zh(task):
    id_ = task.id
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
        return ("从固定分子构象预测 IR/Raman，复用已有 Hessian 和 response 模型。",
                "坐标与参考谱必须来自同一 Gaussian 日志；检查 XYZ 加载后坐标不变，预测 Hessian/响应导数，再经振动模和展宽重建谱图。",
                "预测与参考均使用 400–4000 cm⁻¹ 的 1024 点轴和 min-max 强度归一化，分别报告 IR/Raman 的余弦相似度及强度 MAE。",
                "默认两个真实 Gaussian 日志仅用于配对运行检查，未审计其独立测试身份。不能用新生成的 RDKit 构象代替原参考几何后宣称是严格配对精度。")
    if id_.startswith("vibrational.") or id_.startswith("spectroscopy.reranking"):
        return ("使用 Xinyu 保存的 Vib2Mol 模型完成结构检索、SMILES 生成或候选重排。完整输入为 IR+Raman+H/C；仅 IR/Raman 的路径作为缺核消融。",
                "复用原实现的 encode_spectra、canonical/unique_candidates 与 rerank_candidates。生成默认 beam=10、最大长度 300；先移除无效和重复规范结构，再对前 10 个候选用 ITM 正类概率重排。不提供分子式，也不使用近邻缓存回放。",
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
        return (f"由分子结构预测 {nucleus} 化学位移，已有兼容权重时进行冻结推理或已有预测评分。",
                "H/C 读取 NMRNet、NMRNet++ 的预测及对应元数据；未指认实验峰用最小绝对误差匹配，并保留峰数和覆盖率诊断。B/Si 暂无已验证的兼容权重/预测对。",
                "位移和误差单位均为 ppm。按分子等权计算匹配峰 MAE/RMSE，必须同时报告匹配比例与峰数误差，因为匹配误差本身不惩罚全部缺失峰或额外峰。",
                "峰匹配误差不是逐原子指认准确率。缺少 B/Si 兼容权重时明确跳过，不为补任务重新训练模型头。")
    return (task.note, "本任务需符合输入定义的现成权重、参考数据与适配器。", "缺少必需条件时不产生占位分数。", "保持明确的待接入状态；如果必须重新训练才能完成，则按用户要求跳过。")


def observations():
    preferred = ["smoke_nmr_20261115_v2.json", "smoke_forward_20261115_v3.json", "fp_alignment_audit_20261115.json",
                 "fp_primary_score_gate_20261116.json",
                 "gap_protocol_audit_20261115.json", "gap_protocol_random128_20261116.json", "vib2mol_xinyu_protocol_20261115.json",
                 "vib2mol_xinyu_random64_20261116.json", "vibrational_forward_paired_logs_20261116.json",
                 "ms_glacier_32_molecules_20261116.json", "ms_iceberg_32_molecules_20261116.json", "magma_real_test_verified_20261115.json"]
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
            brief = {key: row[key] for key in ("task", "dataset_name", "status", "metrics", "counts", "reason", "examples", "given_nmr", "beam_size", "reranked_metrics", "source_counts", "selection", "sampling", "seed", "training_mean_baseline", "unique_molecules") if key in row}
            brief["source_file"] = name
            brief["sample_limit"] = payload.get("limit", len(payload.get("records", [])))
            if "models" in row:
                brief["models"] = [{"model": model["model"], "metrics": model["metrics"]} for model in row["models"]]
            if id_.startswith(("nmr.retrieval", "nmr.generation", "nmr.forward.1H", "nmr.forward.13C")):
                result.setdefault(id_, []).append(brief)
            else:
                result[id_] = [brief]
    return result


def notebook(task, language):
    en = language == "en"
    title, purpose, method, metrics, limits, source = profile(task)
    content = [
        {"cell_type": "markdown", "metadata": {}, "source": [f"# {title if en else task.title}\n\n", purpose if en else task.note or "已有模型推理与任务接口示例。", "\n\n", "This notebook displays recorded real evaluation results. Model inference is opt-in and never trains parameters." if en else "本 notebook 展示已记录的真实评测结果。模型推理需显式开启，始终不进行训练。"]},
        {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": ["import json, os, sys, subprocess, tempfile\nfrom pathlib import Path\n", "root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'openmolspec_bench').is_dir()), None)\n", "if root is None:\n    raise RuntimeError('Run this notebook from the cloned OpenMolSpec frontend repository')\n", f"task_id = {task.id!r}\n", f"example_input = {example(task)!r}\n", "print(json.dumps(example_input, indent=2, ensure_ascii=False))"]},
        {"cell_type": "markdown", "metadata": {}, "source": ["## Recorded evaluation\n\nResults retain their sample size, conditions and source file; an execution pass does not imply accuracy." if en else "## 已记录的评测\n\n保留样本量、输入条件和来源文件；流程执行成功不等于精度达标。"]},
        {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": ["index = json.loads((root / 'documentation/assets/evaluation_index.json').read_text())\n", "recorded = index.get(task_id, [])\n", "print(json.dumps(recorded or {'status': 'not_evaluated', 'reason': 'Required compatible assets or adapter unavailable'}, indent=2, ensure_ascii=False))"]},
        {"cell_type": "markdown", "metadata": {}, "source": ["## Optional frozen inference\n\nSet `OPENMOLSPEC_RUN_NOTEBOOK_INFERENCE=1` and configure the workspace and model runtime. Missing weights cause a skip/error, never training." if en else "## 可选：冻结权重推理\n\n设置 `OPENMOLSPEC_RUN_NOTEBOOK_INFERENCE=1` 并配置工作区和模型环境。缺少权重时跳过或报错，不会启动训练。"]},
        {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": ["if os.environ.get('OPENMOLSPEC_RUN_NOTEBOOK_INFERENCE') == '1':\n", "    runtime = os.environ.get('OPENMOLSPEC_PYTHON', sys.executable)\n", "    workspace = os.environ.get('OPENMOLSPEC_BENCH_ROOT', str(root.parent))\n", "    with tempfile.TemporaryDirectory(prefix='openmolspec-notebook-') as directory:\n", "        command = [runtime, '-m', 'openmolspec_bench', 'run', '--workspace', workspace, '--tasks', task_id, '--limit', '2', '--output', str(Path(directory) / 'result.json')]\n", "        subprocess.run(command, cwd=root, check=True)\n", "        print((Path(directory) / 'result.json').read_text())\n", "else:\n    print('Model execution disabled; recorded evaluation displayed above. No training performed.')"]},
    ]
    for index, cell in enumerate(content):
        cell["id"] = hashlib.sha256(f"{task.id}:{language}:{index}".encode()).hexdigest()[:12]
    return {"cells": content, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


def build():
    files = {}
    data = observations()
    files["assets/evaluation_index.json"] = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    for language in ("en", "zh"):
        en, suffix = language == "en", "" if language == "en" else ".zh"
        home = "# OpenMolSpec v1.0\n\n" + ("Frozen-model spectroscopy tasks, reproducible evaluation and online prediction. No training is performed. Use the language selector to switch between English and Chinese.\n\n" if en else "整合已有谱学模型、可复现评测与在线推理，不进行训练。通过语言选择器切换英文和中文。\n\n")
        home += ("- [Tasks](tasks/index.md)\n- [Notebook gallery](notebooks/index.md)\n- [Quick start](quickstart.md)\n- [Evaluation protocol](protocols.md)\n- [Dataset download](datasets.md)\n- [Publication status](publication.md)\n" if en else "- [任务目录](tasks/index.md)\n- [Notebook 展示](notebooks/index.md)\n- [快速开始](quickstart.md)\n- [评测协议](protocols.md)\n- [数据下载](datasets.md)\n- [发布状态](publication.md)\n")
        files[f"index{suffix}.md"] = home
        quick = "# " + ("Quick start" if en else "快速开始") + "\n\n```bash\npython3 -m venv .venv\n.venv/bin/python -m pip install -e . -r requirements.txt\nexport OPENMOLSPEC_BENCH_ROOT=/path/to/OpenMolSpec\nexport OPENMOLSPEC_ROOT=/path/to/openmolspec-studio-portable\n.venv/bin/streamlit run app.py\n```\n\n"
        quick += ("The frontend exposes Tool, Dataset Download, Prediction (Online), and Full documentation. Weights and complete datasets are stored separately from Git.\n\n" if en else "前端提供 Tool、Dataset Download、Prediction (Online)、Full documentation 四个栏目。权重与完整数据独立于 Git 存放。\n\n")
        quick += "```bash\npython -m openmolspec_bench list\npython -m openmolspec_bench run --workspace /path/to/OpenMolSpec --tasks vibrational.gap.ir_raman_hc --limit 32 --output results/my_run.json\n```\n"
        files[f"quickstart{suffix}.md"] = quick
        protocol = "# " + ("Evaluation protocols" if en else "评测协议") + "\n\n"
        protocol += ("Every run records input/checkpoint hashes, sample IDs, modality conditions, candidate pools and execution states. F/P cached results whose logged targets disagree with current input labels are invalidated. Correct pairing is necessary but does not establish solid-to-solution reference compatibility.\n\n" if en else "每次运行记录输入/权重哈希、样本 ID、模态条件、候选池和运行状态。F/P 缓存预测若保存的标签与当前输入不一致，则撤回旧评分。配对修复也不能证明固相到溶液的位移参考兼容。\n\n")
        protocol += ("The gap and Xinyu Vib2Mol checkpoints expect IR+Raman+H/C. Missing-channel variants are ablations, reported separately. Gap targets are converted from Hartree to eV once; stored H/C and target normalization is reused. Vib2Mol generation uses canonical unique valid beams and ITM positive-class reranking.\n\n" if en else "Gap 和 Xinyu 的 Vib2Mol checkpoint 使用 IR+Raman+H/C。缺核输入属于消融，分开报告。Gap 标签仅从 Hartree 转换一次为 eV，复用 checkpoint 的 H/C 和目标归一化。Vib2Mol 生成采用规范化、有效去重后的 beam，再按 ITM 正类概率重排。\n\n")
        protocol += ("MS scores use real held-out CSV spectra and matched acquisition metadata. Missing collision energy/instrument is skipped without imputation. Small samples and unverified training overlap do not establish full-benchmark accuracy.\n" if en else "MS 使用真实测试 CSV 及匹配的采集元数据。缺碰撞能或仪器时直接跳过，不补造条件。小样本及未完成训练集重叠审计的分数不能作为完整 benchmark 精度。\n")
        files[f"protocols{suffix}.md"] = protocol
        datasets = "# " + ("Dataset download" if en else "数据下载") + "\n\n"
        datasets += ("Use the original download/distribution pages and retain their licenses, sample identities, splits and units. Complete datasets and weights are not bundled in this repository.\n\n" if en else "通过原始分发页面下载数据，保留许可、样本 ID、划分和单位。本仓库不打包完整数据或模型权重。\n\n")
        datasets += "- [MassSpecGym](https://huggingface.co/datasets/roman-bushuiev/MassSpecGym)\n- [NMRNet data and weights](https://zenodo.org/records/19142375)\n- [GLACIER / ICEBERG pretrained assets](https://github.com/coleygroup/ms-pred)\n- [SpectraLLM released models](https://github.com/OPilgrim/SpectraLLM)\n\n"
        datasets += ("Our prepared test CSV, NMR JSONL, and portable Gaussian/LMDB assets are configured by local paths. Public OpenMolSpec dataset export URLs must be verified before being added here.\n" if en else "我们已准备的测试 CSV、NMR JSONL、Gaussian/LMDB 资产通过本地路径配置。OpenMolSpec 数据导出下载地址需实际验证后再添加。\n")
        files[f"datasets{suffix}.md"] = datasets
        publication = "# " + ("Publication status" if en else "发布状态") + "\n\n"
        publication += ("Read the Docs configuration is provided in `.readthedocs.yaml`. Build with `pip install -r requirements-docs.txt` and `mkdocs build --strict`. The repository has no confirmed live Read the Docs URL yet. A project import and successful hosted build are required before a URL is advertised as published.\n\n" if en else "仓库提供 `.readthedocs.yaml`。安装 `requirements-docs.txt` 后用 `mkdocs build --strict` 构建。目前尚无已确认上线的 Read the Docs URL；只有项目导入和托管构建成功后才会发布实际网址。\n\n")
        publication += ("Configure `OPENMOLSPEC_DOCS_URL` on the frontend after deployment. The current environment's network proxy does not resolve, so GitHub push, dependency download and Read the Docs account access remain externally blocked.\n" if en else "部署后在前端设置 `OPENMOLSPEC_DOCS_URL`。当前环境的网络代理无法解析，GitHub 推送、依赖下载和 Read the Docs 账户访问仍受外部条件限制。\n")
        files[f"publication{suffix}.md"] = publication
        task_index = "# " + ("Task catalog" if en else "任务目录") + "\n\n| ID | " + ("Task | Adapter" if en else "任务 | 适配器") + " |\n| --- | --- | --- |\n"
        notebook_index = "# " + ("Notebook gallery" if en else "Notebook 展示") + "\n\n" + ("Notebooks display recorded evaluation evidence and include opt-in inference commands. They never train models.\n\n" if en else "Notebook 展示已记录的评测证据，并提供可选推理命令，不进行训练。\n\n")
        for task in TASKS:
            slug = task.id.replace(".", "-")
            title, purpose, method, metrics, limits, source = profile(task)
            heading = title if en else task.title
            task_index += f"| `{task.id}` | [{heading}]({slug}.md) | `{task.backend}` |\n"
            notebook_index += f"- [{heading}]({slug}.ipynb)\n"
            if en:
                page = f"# {title}\n\n{purpose}\n\n## Model and protocol\n\n{method}\n\n## Inputs and example\n\nThe example below illustrates the schema; it is not a measured spectrum or an accuracy result.\n\n```json\n{json.dumps(example(task), indent=2)}\n```\n\n## Outputs and metrics\n\n{metrics}\n\nMetric fields: `{'`, `'.join(task.metrics)}`. Domain: `{task.domain}`.\n\n## Run the existing model\n\n"
            else:
                zh_purpose, zh_method, zh_metrics, zh_limits = profile_zh(task)
                page = f"# {heading}\n\n{zh_purpose}\n\n## 模型与协议\n\n{zh_method}\n\n## 输入与示例\n\n以下仅展示输入格式，不是实测谱或精度结果。\n\n```json\n{json.dumps(example(task), indent=2, ensure_ascii=False)}\n```\n\n## 输出与指标\n\n{zh_metrics}\n\n适配器：`{task.backend}`。数据域：`{task.domain}`。指标字段：`{'`、`'.join(task.metrics)}`。\n\n## 运行推理或评分\n\n"
            page += f"```bash\npython -m openmolspec_bench run --workspace /path/to/OpenMolSpec \\\n  --tasks {task.id} --limit 8 --output results/{slug}.json\n```\n\n"
            if en:
                page += f"## Interpretation and limits\n\n{limits}\n\n## Recorded results\n\n"
            else:
                page += f"## 解释与限制\n\n{zh_limits}\n\n## 已记录结果\n\n"
            page += "```json\n" + json.dumps(data.get(task.id, [{"status": "not_evaluated", "reason": task.note}]), indent=2, ensure_ascii=False) + "\n```\n\n"
            page += f"## Notebook\n\n[{'Open the runnable notebook' if en else '打开可运行 notebook'}](../notebooks/{slug}.ipynb)\n\n## {'Source' if en else '来源'}\n\n[{'Original implementation / release' if en else '原始实现与发布'}]({source})\n"
            files[f"tasks/{slug}{suffix}.md"] = page
            files[f"notebooks/{slug}{suffix}.ipynb"] = json.dumps(notebook(task, language), ensure_ascii=False, indent=2) + "\n"
        files[f"tasks/index{suffix}.md"] = task_index
        files[f"notebooks/index{suffix}.md"] = notebook_index
    return files


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
            path.write_text(content)
    if failures:
        raise SystemExit("Regenerate bilingual documentation: " + ", ".join(failures))
    print(f"Bilingual task docs prepared for {len(TASKS)} tasks")


if __name__ == "__main__":
    main()
