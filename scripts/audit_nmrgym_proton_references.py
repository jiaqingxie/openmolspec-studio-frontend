"""Trace the 14 extreme NMRGym test references to nucleus-labelled records and rescore frozen predictions."""

import argparse
from collections import Counter
import csv
import gzip
import json
from pathlib import Path
import pickle
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import Chem
from evaluate_nmrgym_proton import scores
from openmolspec_bench.data import sha256

SDF_SHA = "0e86688360e23c88ccf0eb82a1251315fa57ec6f5b376dc8886f3311793a0afe"
OFFICIAL_SHA = "04504b08800baf5fab57836e51b9314cc600eff237da6222c4567eec03379ac3"
SDF_URL = (
    "https://sourceforge.net/projects/nmrshiftdb2/files/data/nmrshiftdb2withsignals.sd/"
)
PAPERS = {
    "PKGDAHNXKNOKIH": {
        "id": "PMC5654143 · compound 1",
        "url": "https://doi.org/10.1186/s12885-017-3667-9",
        "groups": [6.80, 7.22, 7.46, 6.51, 3.20, 1.26, 4.99, 3.90],
        "carbon": [
            123.9,
            138.1,
            132.3,
            140.1,
            139.6,
            119.7,
            133.4,
            129.7,
            158.5,
            143.2,
            32.9,
            27.6,
            179.8,
            62.4,
            58.7,
        ],
        "note": "氢栏的 15 个值与同一行碳栏、原论文化合物 1 的 ¹³C 峰表逐值相同。原论文另列 8 组氢信号。",
    },
    "ANLVCISSEPMBQL": {
        "id": "PMC6017869 · compound 19",
        "url": "https://doi.org/10.3390/molecules23030693",
        "groups": [[1.35, 2.35], 5.50, 6.91, 7.03, 7.31, 7.68, 8.62],
        "carbon": [
            24.03,
            25.73,
            50.23,
            51.43,
            120.1,
            121.7,
            122.1,
            128.9,
            132.7,
            138.3,
            138.9,
            140.5,
            141.2,
            147.6,
            149.2,
            150.7,
            160.0,
            162.0,
        ],
        "note": "1.35–2.35 是一组 10H 多重峰。后四个数是原论文的 ¹³C 位移，原文还列出 5.50 至 8.62 ppm 的六组氢信号。",
    },
    "IDLLXOURUDOUML": {
        "id": "PMC5854701 · compound 9r",
        "url": "https://doi.org/10.1038/s41598-018-22875-9",
        "groups": [
            10.79,
            [7.62, 7.73],
            7.58,
            [7.42, 7.55],
            [7.14, 7.25],
            [6.86, 7.04],
            [6.50, 6.72],
            5.47,
            [3.87, 4.04],
            2.92,
            2.42,
            [2.14, 2.39],
            [1.84, 2.03],
            1.62,
        ],
        "couplings_hz": [5.0, 2.9, 53.6, 11.2, 31.7, 11.8],
        "note": "原文有 14 组氢信号。NMRGym 将峰区间两端分别计数，也将原文标为 J 的 6 个数值按 ppm 收入。53.6 和 31.7 的单位都是 Hz。",
    },
}
METRICS = (
    "matched_peak_mae_ppm",
    "cosine",
    "count_penalized_error_ppm",
    "matched_fraction",
    "matched_peak_r2",
)


def source_records(sdf, wanted):
    records = {}
    for block in sdf.read_bytes().split(b"$$$$"):
        m = re.search(rb">\s*<INChI key>\s*([A-Z]{14})-", block)
        if not m or (key := m[1].decode()) not in wanted:
            continue
        if key in records:
            raise ValueError(f"Multiple source structures for {key}")
        props = dict(
            re.findall(
                r">\s*<([^>]+)>\n([^\n]+)", block.decode("latin1").replace("\r", "")
            )
        )
        records[key] = props
    return records


def values(entry):
    return [float(token.split(";")[0]) for token in entry.split("|") if token.strip()]


def review(row, db):
    key = row["connectivity"]
    h, c = row["official_h_ppm"], row["official_c_ppm"]
    extreme = [n for n in h if abs(n) > 50]
    if key in PAPERS:
        p = PAPERS[key]
        groups = p["groups"]
        if "couplings_hz" in p:
            # The raw lists include all range endpoints and each J value.
            tokens = [v for g in groups for v in (g if isinstance(g, list) else [g])]
            assert Counter(h) == Counter(tokens + p["couplings_hz"])
            kind = "coupling_hz_in_shift_field"
        else:
            assert not (Counter(extreme) - Counter(p["carbon"]))
            if key == "PKGDAHNXKNOKIH":
                assert Counter(h) == Counter(c) == Counter(p["carbon"])
            kind = "carbon_exact"
        return dict(
            kind=kind,
            note=p["note"],
            source=p["id"],
            url=p["url"],
            proton_groups_ppm=groups,
            source_carbon_ppm=p.get("carbon"),
            source_couplings_hz=p.get("couplings_hz"),
        )
    props = db[key]
    carbons = values(props["Spectrum 13C 0"])
    hfields = [n for n in props if n.startswith("Spectrum 1H ")]
    assert len(hfields) <= 1
    groups = values(props[hfields[0]]) if hfields else None
    kind = "carbon_exact"
    if groups is None:
        assert not (Counter(h + c) - Counter(carbons))
        note = "同连通结构的碳谱同时覆盖氢栏和碳栏所有数值，含重复次数。匹配的数据库记录仅给出碳谱，氢谱留缺。"
    elif key == "HAXFWIACAGNFHA":
        assert Counter(h) == Counter(groups + [149.0])
        kind = "extra_unsupported_proton"
        note = "数据库氢谱完整覆盖另外四个值，额外的 149.0 ppm 缺乏氢谱支持。碳谱中有 149.52 ppm，149.0 的确切来历未证实。"
    else:
        assert not (Counter(extreme) - Counter(carbons)) and not (
            set(extreme) & set(groups)
        )
        added = sorted((Counter(groups) - Counter(h)).elements())
        note = f"异常值在同连通结构的 ¹³C 谱中精确出现。数据库氢谱比原氢栏多出 {', '.join(map(str, added))} ppm 的条目，重复位移按原记录计数。"
    mid = props["nmrshiftdb2 ID"]
    return dict(
        kind=kind,
        note=note,
        source="nmrshiftdb2 " + mid,
        url="https://nmrshiftdb.nmr.uni-koeln.de/molecule/" + mid,
        source_inchikey=props["INChI key"],
        # Bibliographic leads recorded against these structures in the historical
        # nmrshiftdb SPECTRUM table. Neither is used to impute proton shifts.
        cited_paper={
            "2333": "https://doi.org/10.1016/S0031-9422(01)00334-X",
            "5339": "https://doi.org/10.1016/S0031-9422(01)00061-9",
        }.get(mid),
        source_carbon_field="Spectrum 13C 0",
        source_carbon_ppm=carbons,
        source_proton_field=hfields[0] if hfields else None,
        proton_groups_ppm=groups,
    )


def measure(rows):
    out = {"molecules": len(rows)}
    refs = [r["reference"] for r in rows]
    for label in ("v2", "clean"):
        m, _ = scores([r[label] for r in rows], refs)
        out[label] = {k: m[k] for k in METRICS}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--official",
        type=Path,
        default=ROOT / "../../data/benchmarks/NMRGym_test_balanced_dedup.pkl",
    )
    p.add_argument(
        "--sdf", type=Path, default=ROOT / ".runtime/forward-tuning/nmrshiftdb2.sd"
    )
    p.add_argument(
        "--replays", type=Path, default=ROOT / "../runs/nmrgym-specialist/1H-clean-v3"
    )
    p.add_argument(
        "--out", type=Path, default=ROOT / "results/nmrgym_proton_reference_audit"
    )
    a = p.parse_args()
    if sha256(a.official) != OFFICIAL_SHA or sha256(a.sdf) != SDF_SHA:
        raise ValueError("Unexpected source edition")
    benchmark = json.loads((ROOT / "results/nmrgym_proton_clean.json").read_text())
    panels = {}
    wanted = {}
    for label, info in benchmark["test"].items():
        f = a.replays / (label + ".jsonl.gz")
        if sha256(f) != info["replay_sha256"]:
            raise ValueError("Unexpected test replay")
        with gzip.open(f, "rt") as stream:
            panels[label] = list(map(json.loads, stream))
        for r in panels[label]:
            if max(map(abs, r["reference"])) > 50:
                assert r["smiles"] not in wanted
                wanted[r["smiles"]] = (label, r)
    db = source_records(a.sdf, {r["connectivity"] for _, r in wanted.values()})
    report = dict(
        official_test_sha256=OFFICIAL_SHA,
        sdf_sha256=SDF_SHA,
        sdf_source=SDF_URL,
        bank_source="https://huggingface.co/datasets/sweetssweets/NMRBank",
        test_policy="Post-hoc sensitivity using frozen predictions. The official benchmark uses the original labels. Selection: one or more reference proton shifts with |ppm| > 50. No prediction-based selection.",
        source_matching="Identical official SMILES and reference multiset. Database search by first InChIKey block. Some database records specify stereo omitted by NMRGym. Cross-check is not an unambiguous accession mapping from NMRGym, which has no such field.",
        normalization="One group per reported multiplet, with each range kept in proton_groups_ppm and its midpoint used for point-based sensitivity scores. No expansion by integration. Preserve repeated entries in database spectra.",
        audit=[],
        panels={},
    )
    reviewed = {}
    with a.official.open("rb") as stream:
        official = pickle.load(stream)
    for idx, o in enumerate(official):
        if o["smiles"] not in wanted:
            continue
        label, r = wanted[o["smiles"]]
        key = r["connectivity"]
        assert key not in reviewed and Counter(o["h_shift"]) == Counter(r["reference"])
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(o["smiles"])).split("-")[0] == key
        item = dict(
            official_index_zero_based=idx,
            panel=label,
            connectivity=key,
            smiles=o["smiles"],
            official_h_ppm=o["h_shift"],
            official_c_ppm=o["c_shift"],
        )
        item.update(review(item, db))
        groups = item["proton_groups_ppm"]
        item["sensitivity_reference_ppm"] = (
            [float(np.mean(g)) for g in groups] if groups else None
        )
        report["audit"].append(item)
        reviewed[key] = item
    assert len(wanted) == len(reviewed) == 14
    for label, rs in panels.items():
        other = []
        eligible = []
        revised = []
        for r in rs:
            q = reviewed.get(r["connectivity"])
            if q is None:
                other.append(r)
            if q is None or q["sensitivity_reference_ppm"] is not None:
                eligible.append(r)
                revised.append(
                    {
                        **r,
                        "reference": q["sensitivity_reference_ppm"]
                        if q
                        else r["reference"],
                    }
                )
        original = measure(rs)
        for model in ("v2", "clean"):
            for k in METRICS:
                np.testing.assert_allclose(
                    original[model][k],
                    benchmark["test"][label][model][k],
                    rtol=0,
                    atol=1e-9,
                )
        report["panels"][label] = dict(
            official=original,
            without_flagged=measure(other),
            same_eligible_original_labels=measure(eligible),
            same_eligible_reviewed_labels=measure(revised),
            restored=len(revised) - len(other),
            missing_proton_reference=len(rs) - len(revised),
        )
    a.out.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    with a.out.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "官方行号（从0计）",
                "测试组",
                "连通结构 InChIKey",
                "核查结果",
                "原始氢栏 ppm",
                "原始碳栏 ppm",
                "来源氢峰（多重峰区间保留）ppm",
                "来源",
                "来源链接",
                "数据库所引论文",
                "SMILES",
            ]
        )
        for row in report["audit"]:
            groups = row["proton_groups_ppm"]
            group_text = (
                ", ".join(
                    "–".join(map(str, g)) if isinstance(g, list) else str(g)
                    for g in groups
                )
                if groups
                else "匹配记录仅有碳谱"
            )
            writer.writerow(
                [
                    row["official_index_zero_based"],
                    row["panel"],
                    row["connectivity"],
                    row["note"],
                    ", ".join(map(str, row["official_h_ppm"])),
                    ", ".join(map(str, row["official_c_ppm"])),
                    group_text,
                    row["source"],
                    row["url"],
                    row.get("cited_paper"),
                    row["smiles"],
                ]
            )


if __name__ == "__main__":
    main()
