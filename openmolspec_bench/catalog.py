"""One task catalog shared by the command line, Studio, and documentation."""

from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    family: str
    modalities: tuple[str, ...]
    domain: str
    backend: str
    metrics: tuple[str, ...]
    note: str = ""
    enabled: bool = True


TASKS = []
for nucleus in ("1H", "13C", "19F", "31P", "11B", "29Si"):
    TASKS.append(Task(
        f"nmr.forward.{nucleus}", f"结构 → {nucleus} 峰列表", "forward", (nucleus,),
        "experimental", ("nmrnet_predictions" if nucleus in ("1H", "13C") else "solution_chemical_shift"),
        (("mae_ppm", "molecule_macro_mae_ppm", "rmse_ppm") if nucleus in ("19F", "31P", "11B", "29Si") else
         ("count_penalized_error_ppm", "matched_peak_mae_ppm", "matched_peak_rmse_ppm", "peak_count_mae", "matched_fraction")),
        "用训练后的氢谱模型或五折 NMRNet++ 碳谱预测与实测峰列表配对，对漏峰和多报峰计入惩罚；同时提供原始逐原子基线。"
        if nucleus in ("1H", "13C") else
        "使用实验溶液谱训练的模型预测化学位移，以按分子连通性留出的实测单环境谱评分。可显式选择旧模型进行冻结诊断。"))
for view, modalities in (("h", ("1H",)), ("c", ("13C",)), ("hc", ("1H", "13C"))):
    for direction in ("s2m", "m2s"):
        TASKS.append(Task(f"nmr.retrieval.{view}.{direction}",
                          f"{'谱图 → 结构' if direction == 's2m' else '结构 → 谱图'}检索 · {view.upper()}",
                          "retrieval", modalities, "experimental", "spec2struct_alignment",
                          ("recall_at_1", "recall_at_5", "recall_at_10", "mrr")))
    TASKS.append(Task(f"nmr.generation.{view}", f"谱图 → SMILES · {view.upper()}", "generation",
                      modalities, "experimental", "spec2struct_generation",
                      ("valid_rate", "exact_rate", "formula_match_rate"),
                      "显式提供分子式；模型按分子式重排 beam，需与无分子式结果分开比较。"))
for view in ("ir", "raman", "ir_raman"):
    modalities = tuple(view.upper().split("_"))
    TASKS.append(Task(f"vibrational.gap.{view}", f"{view.upper()} → HOMO–LUMO gap", "property",
                      modalities, "computed", "studio_gap", ("mae_ev", "rmse_ev")))
TASKS.append(Task("vibrational.gap.ir_raman_hc", "IR + Raman + H/C NMR → HOMO–LUMO gap", "property",
                  ("IR", "Raman", "1H", "13C"), "computed", "studio_gap", ("mae_ev", "rmse_ev"),
                  "按 checkpoint 的 ir-raman-nmr 完整输入运行；同时报告训练均值常量基线。"))
for id_, title, modalities, backend, metrics, note in (
    ("vibrational.forward", "构象 → IR / Raman", ("IR", "Raman"), "studio_vibrational_forward", ("ir_cosine_similarity", "raman_cosine_similarity", "ir_mae", "raman_mae"),
     "在相同的核坐标上预测 IR 和 Raman。安装 QM9S 验证包后默认使用预留结构；也支持指定 Gaussian 日志复核原始 openSpec 协议。"),
    ("vibrational.retrieval", "IR / Raman → 结构检索", ("IR", "Raman"), "vib2mol_retrieval", ("recall_at_1", "recall_at_5", "recall_at_10", "mrr"),
     "已有 Vib2Mol checkpoint 直接编码本次选中样本；提供 IR+Raman，不提供 H/C。"),
    ("vibrational.generation", "IR / Raman → SMILES", ("IR", "Raman"), "vib2mol_generation", ("exact_rate", "valid_rate"),
     "直接运行已有 Vib2Mol beam 解码，不使用缓存或近邻回放；原始 beam top-1，不进行分子式重排。"),
    ("nmr.assignment", "H/C 峰 → 原子指认", ("1H", "13C"), "nmrnet_atom_assignment", ("matched_peak_fraction_macro", "matched_residual_mae_ppm", "assignment_accuracy"),
     "直接运行冻结 NMRNet H/C 权重，加对称位点合并与带容差的全局匹配。原子编号随输出保存；缺实验指认参考时准确率为 null。"),
    ("nmr.solvent_transfer", "H/C 跨溶剂位移 · 参考检索基线", ("1H", "13C"), "nmr_solvent_reference", ("mae_ppm", "unchanged_shift_mae_ppm"),
     "无训练的实测参考检索迁移，排除查询分子及同连接关系的立体异构体；已跑 32 分子。不是神经网络模型，专用权重仍待接入。"),
    ("nmr.formula", "谱图 → 分子式", ("1H", "13C"), "unavailable", ("formula_exact_rate",),
     "现有生成器使用给定分子式；不将其计为分子式预测器。"),
    ("spectroscopy.qa", "谱学问答 / 推理", ("NMR", "IR", "Raman"), "unavailable", ("answer_accuracy",),
     "需要有参考答案的题集和固定模型接口。"),
    ("spectroscopy.reranking", "谱图 + 候选结构 → 重排", ("IR", "Raman"), "vib2mol_reranking", ("top_1_hit_rate", "mrr"),
     "Vib2Mol ITM 正类概率重排显式候选池；候选池由本次选中的不同参考结构构成。"),
):
    TASKS.append(Task(id_, title, id_.split(".")[-1], modalities,
                      "computed" if id_.startswith("vibrational") or backend.startswith("vib2mol_") else "experimental",
                      backend, metrics, note))

for id_, title, backend, metrics in (
    ("vibrational.retrieval.hc", "IR + Raman + H/C → 结构检索", "vib2mol_retrieval", ("recall_at_1", "recall_at_5", "recall_at_10", "mrr")),
    ("vibrational.generation.hc", "IR + Raman + H/C → SMILES（Xinyu 协议）", "vib2mol_generation", ("exact_canonical_top1", "exact_canonical_top5", "valid_smiles_fraction")),
    ("spectroscopy.reranking.hc", "IR + Raman + H/C + 候选 → ITM 重排", "vib2mol_reranking", ("top_1_hit_rate", "mrr")),
):
    TASKS.append(Task(id_, title, "generation" if "generation" in id_ else "retrieval" if "retrieval" in id_ else "reranking",
                      ("IR", "Raman", "1H", "13C"), "computed", backend, metrics,
                      "使用 Xinyu 保存的四模态 checkpoint、H/C 参考与归一化；生成按原评测脚本去重和 ITM 重排。"))

TASKS.append(Task("nmr.hsqc.transpeaknet", "结构与溶剂 → HSQC 交叉峰", "forward", ("HSQC",),
                  "experimental", "transpeaknet", ("carbon_mae_ppm", "proton_mae_ppm"),
                  "使用作者二维谱权重，按专家标注的原子编号计算每张谱的碳、氢位移误差。"))

for model in ("glacier", "iceberg"):
    TASKS.append(Task(f"ms.forward.{model}", f"分子 → MS/MS（{model.upper()}）", "forward", ("MS/MS",),
                      "experimental", f"ms_pretrained_{model}", ("cosine_similarity", "entropy_similarity"),
                      "直接调用作者的冻结 checkpoint；使用我们测试 CSV 的实测谱并核对分子、加合物和采集条件。"))
TASKS.append(Task("ms.annotation.magma", "MS/MS 峰 → MAGMa 候选碎片标注", "annotation", ("MS/MS",),
                  "experimental", "magma_algorithm", ("matched_peak_fraction", "checked_fragments"),
                  "原算法，无训练；原子索引以 engine_smiles 为准并逐碎片验证，标注不等于实验确认的机制。"))
TASKS.append(Task("multispectral.spectrallm.generation", "多谱 → 结构（SpectraLLM）", "generation",
                  ("IR", "Raman", "NMR", "MS/MS"), "mixed", "unavailable", ("exact_rate", "valid_rate"),
                  "官方新权重为 32B；当前本地仅有旧 7B adapter 且其指定基座缺失。需下载完整官方权重或提供匹配基座，不进行训练。"))

DEFERRED_BY_USER = {"nmr.formula", "spectroscopy.qa", "multispectral.spectrallm.generation"}
TASKS = [replace(task, enabled=False, note="用户已明确暂不推进；历史结果仅作归档，不再运行。")
         if task.id in DEFERRED_BY_USER else task for task in TASKS]
BY_ID = {task.id: task for task in TASKS}


def records():
    return [asdict(task) for task in TASKS]
