"""Print one line per outstanding inverse-spectroscopy work item for a terminal."""

from pathlib import Path
import fcntl
import json
import statistics

studio = Path(__file__).resolve().parents[1]
results = studio / "results"
runtime = studio / ".runtime/nonforward"
nmr = studio.parent / "runs/nmrtrans-inverse-v1"


def load(p):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def packing(source):
    folder = nmr / "data" / source
    if (folder / "manifest.json").is_file():
        return False
    try:
        with (folder / "prepare.lock").open() as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except FileNotFoundError:
        pass
    return False


for name, sources in (
    ("NMRGym", ["nmrgym"]),
    ("其他三库", ["nmrspec", "nmrexp", "patent"]),
):
    scheduler = load(nmr / "scheduler.json")
    submission = load(
        nmr / "submissions" / ("gym.json" if len(sources) == 1 else "other.json")
    )
    prepared = sum((nmr / "data" / s / "manifest.json").is_file() for s in sources)
    preflights = sum(
        (nmr / source / view / "preflight.json").is_file()
        for source in sources for view in ("hc", "h", "c")
    )
    finished = sum(
        (nmr / source / view / "complete.json").exists()
        for source in sources
        for view in ("hc", "h", "c")
    )
    active = [
        p
        for source in sources
        for p in (nmr / source).glob("*/timing.jsonl")
        if not (p.parent / "complete.json").exists()
    ]
    if active:
        timing = max(active, key=lambda p: p.stat().st_mtime)
        events = []
        for line in timing.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        starts = {}
        for event in events:
            if event["event"] == "epoch_start":
                starts[event["epoch"]] = event["time"]
        intervals = [
            starts[i] - starts[i - 1] for i in sorted(starts) if i - 1 in starts
        ]
        epoch = max(starts, default=0)
        status = f"{timing.parent.parent.name}/{timing.parent.name} epoch {epoch + 1}"
        if intervals:
            status += f"，到上限约 {statistics.median(intervals[-5:]) * (100 - epoch) / 3600:.1f} h"
    elif finished == 3 * len(sources):
        status = f"已完成 {finished}/{3 * len(sources)} 个模型"
    elif submission.get("state") == "accepted":
        job = submission.get("resource_name") or submission["name"]
        status = f"调度已接受 {job}，已完成 {finished}/{3 * len(sources)} 个模型"
    elif submission.get("state") == "unreachable":
        status = "无法连接调度器，未取得作业 ID"
    elif submission.get("state") == "unconfirmed":
        status = "未取得调度器的创建回执"
    elif submission.get("state", scheduler.get("state")) == "rejected":
        log = Path(submission.get("log") or "")
        status = "提交被拒，未入队"
        if log.is_file() and "has no right to operate[use] the resource[quotagroups]" in log.read_text():
            status = "提交身份无 GPU 组权限，未入队"
    else:
        status = "等待调度确认"
    preparing = [s for s in sources if packing(s)]
    packing_note = "，打包中 " + "/".join(preparing) if preparing else ""
    print(
        f"NMRTrans v1 {name} (H/C/H+C)  {status}，数据包 {prepared}/{len(sources)}{packing_note}，CPU 验证 {preflights}/{3 * len(sources)}"
    )

assigned = load(results / "assignment_all_heldout_sites.json").get("nuclei", {})
for tag in ["1H", "13C"]:
    m = assigned.get(tag)
    print(
        f"{tag} 原子指认  "
        + (
            f"{m['correct']}/{m['peaks']} = {m['accuracy']:.1%}"
            if m
            else "真值评测，等待结果"
        )
    )

d = load(results / "gap_vibrational_heldout.json")
if d:
    vals = [v["test"]["mae_ev"] for v in d["models"].values()]
    print("缺通道能隙 IR/Raman/双谱  " + " / ".join(f"{x:.3f}" for x in vals) + " eV")

retrieval = load(results / "nmr_cross_source_library_scale.json").get("results", {})
for source, modes in retrieval.items():
    values = [modes[view]["s2m"]["2048"]["r1"] for view in ("h", "c", "hc")]
    print(f"NMR 检索 {source}，2048 候选，H/C/H+C Top-1  " + " / ".join(f"{value:.1%}" for value in values))

gap = load(results / "gap_four_channel_1024.json")
if gap:
    row, = gap["results"]
    print(f"四谱能隙  {row['metrics']['examples']} 个样本，MAE {row['metrics']['mae_ev']:.3f} eV")

for channels, label in [("双谱", "adapted"), ("四谱", "four")]:
    d = load(results / f"vib_shortlist4096_{label}.json")
    if d.get("complete"):
        before, after = d["embedding_rank"], d["shortlist_itm_rank"]
        print(f"{channels} 4096 候选  检索 Top-1 {before['top1_hits']}/{before['queries']}，前 32 重排 {after['top1_hits']}/{after['queries']}")

refs = load(results / "vib_reference_library4096.json")
for channel, item in refs.get("channels", {}).items():
    metrics = item["metrics"]
    print(f"{channel} 参考谱 4096 候选  检索 / 前 32 / 全库重排 Top-1 "
          + " / ".join(str(metrics[rank]["top1_hits"]) for rank in ("reference_rank","shortlist_rank","full_rank"))
          + f"（{metrics['reference_rank']['queries']} 查询）")

for label, file, score in [
    ("Xinyu 双谱+分子式 VB-Mols", "vib_generation_native_vbmols", "beam"),
    ("Xinyu 双谱+分子式 OpenMolSpec", "vib_generation_native_dual_formula", "beam"),
    ("双谱生成适配，无分子式", "vib_generation_dual_adapted24", "canonical_beam_order"),
    (
        "双谱解码器微调，无分子式",
        "vib_generation_dual_tuned_decoder24",
        "canonical_beam_order",
    ),
    ("四谱生成重排，新测试", "vib_generation_hc_heldout24", "canonical_beam_order"),
]:
    d = load(results / (file + ".json"))
    status = (
        (
            f"Top-1 {d['counts'][score]['top1']}/{len(d['records'])}"
            + ("" if d["complete"] else "（部分）")
        )
        if d
        else "等待结果"
    )
    if not d and file == "vib_generation_dual_tuned_decoder24":
        log = runtime / "gen-train-head.log"
        if load(results / "vib_decoder_fit.json"):
            status = "已拟合，等待结构命中评测"
        elif log.is_file():
            for line in reversed(log.read_text().splitlines()):
                if line.startswith("teacher-forced spectra "):
                    count, total = line.split()[-2:]
                    status = f"正在提取解码特征 {count}/{total}"
                    break
    print(label + "  " + status)
decision = load(results / "vib_dual_model_selection.json")
if decision:
    selected = decision["selected"]
    confirmation = decision.get("confirmation", {})
    if confirmation:
        print(
            "双谱生成独立复核  原模型 "
            + str(confirmation["frozen"]["top1"])
            + "/24，开发集优胜模型 "
            + str(confirmation[selected]["top1"])
            + f"/24，前五名 {confirmation[selected]['top5']}/24"
        )
    elif not decision.get("complete"):
        print("双谱生成独立复核  已选定模型，正在比较")
r = load(results / "vib_generation_rerank_replay64.json")
if r:
    print("四谱重排回放  ITM 44/64；beam 顺序 48/64")
for nucleus, entry in load(results / "solvent_all_supported_pairs.json").get("eligible", {}).items():
    mae = entry["pair_weighted_mae"]
    print(f"{nucleus} 跨溶剂  {entry['rows']} 对，原位移 / 检索 / 拟合 MAE "
          f"{mae['unchanged']:.3f} / {mae['reference']:.3f} / {mae['ridge']:.3f} ppm")
fragments = load(results / "mechfrag_fragment_annotations.json")
if fragments:
    print(f"碎片  {len(fragments['records'])} 张谱 / {fragments['peaks']} 峰，MechFrag-MS {fragments['matched_fraction']:.1%}，MAGMa {fragments['magma_matched_fraction_same_peaks']:.1%}")
for name, file in [("SpecMol 问答","specmol_qa32.json"),("SpectraLLM 解码","spectrallm_qm9s32.json")]:
    record = load(results / file)
    if record.get('complete'):
        print(f"{name}  n={record['metrics']['examples']}，准确率 {record['metrics']['exact_rate']:.1%}")
    else:
        print(f"{name}  正式成绩待回收，调度状态见 runs/task-evaluation/status.sh")
b = load(runtime / "nmr-handoff-check.json")
m = load(results / "nmr_retrieval_to_generation_http.json")
print(
    "NMR 检索转生成  "
    + "，".join(
        [s for ok, s in ((b, "网页交互已验证"), (m, "本地 HTTP 实机已验证")) if ok]
    )
    if b or m
    else "NMR 检索转生成  待验证"
)
