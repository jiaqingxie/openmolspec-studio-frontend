"""One task catalog shared by the command line, Studio, and documentation."""

from dataclasses import asdict, dataclass


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


TASKS = []
for nucleus in ("1H", "13C", "19F", "31P", "11B", "29Si"):
    TASKS.append(Task(
        f"nmr.forward.{nucleus}", f"结构 → {nucleus} 峰列表", "forward", (nucleus,),
        "experimental", ("nmrnet_predictions" if nucleus in ("1H", "13C") else
                         "nmrnet_hetero_predictions" if nucleus in ("19F", "31P") else "unavailable"),
        (("mae_ppm", "rmse_ppm") if nucleus in ("19F", "31P") else
         ("matched_peak_mae_ppm", "matched_peak_rmse_ppm", "peak_count_mae", "matched_fraction")),
        "对已有 NMRNet/NMRNet++ 推理文件评分；无逐原子指认时使用最小代价峰匹配。"
        if nucleus in ("1H", "13C") else
        "已有 NMRNet 固相权重在实验溶液单核数据上的预测评分，明确作为跨域诊断结果。"
        if nucleus in ("19F", "31P") else "保留六核任务定义；尚未验证可用于此实验域的 checkpoint 和预测文件。"))
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
for id_, title, modalities, backend, metrics, note in (
    ("vibrational.forward", "构象 → IR / Raman", ("IR", "Raman"), "unavailable", ("spectral_cosine", "spectral_mae"),
     "Studio 已有 Hessian / response 推理入口；本统一基准尚未接入有配对参考值的评测数据。"),
    ("vibrational.retrieval", "IR / Raman → 结构检索", ("IR", "Raman"), "vib2mol_retrieval", ("recall_at_1", "recall_at_5", "recall_at_10", "mrr"),
     "已有 Vib2Mol checkpoint 直接编码本次选中样本；提供 IR+Raman，不提供 H/C。"),
    ("vibrational.generation", "IR / Raman → SMILES", ("IR", "Raman"), "vib2mol_generation", ("exact_rate", "valid_rate"),
     "直接运行已有 Vib2Mol beam 解码，不使用缓存或近邻回放；原始 beam top-1，不进行分子式重排。"),
    ("nmr.assignment", "峰 → 原子指认", ("1H", "13C", "19F", "31P", "11B", "29Si"), "unavailable", ("assignment_accuracy",),
     "需要保留原子编号的实验参考值和匹配模型。"),
    ("nmr.solvent_transfer", "跨溶剂化学位移迁移", ("1H", "13C", "19F", "31P", "11B", "29Si"), "unavailable", ("mae_ppm",),
     "需要同一分子跨溶剂配对记录及已有可用模型。"),
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

BY_ID = {task.id: task for task in TASKS}


def records():
    return [asdict(task) for task in TASKS]
