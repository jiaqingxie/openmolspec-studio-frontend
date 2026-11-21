"""Compare assigned and NMRNet peak predictors on identical molecules across independent corpora."""

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import Chem, RDLogger
from openmolspec.assigned_shifts import AssignedShiftPredictor
from openmolspec_bench.data import normalize_record, readonly_lmdb, sha256
from openmolspec_bench.metrics import peak_metrics
from openmolspec_bench.runner import read_prediction_folds
from spec2struct_fork.structured import parse_nmr_record, SHIFT, SHIFT_PRESENT

DATASETS = ("patent_test_10k", "nmrspec_test", "nmrexp_exp_10k", "nmrgym_test")


def merged(values, gap):
    if gap == 0:
        return sorted(values)
    clusters = []
    for v in sorted(values):
        if not clusters or v - clusters[-1][0] > gap:
            clusters.append([])
        clusters[-1].append(v)
    return [np.mean(grp) for grp in clusters]


def score(pred, ref, penalty):
    from scipy.optimize import linear_sum_assignment

    val = peak_metrics(pred, ref)
    costs = []
    for p, y in zip(pred, ref):
        distance = np.abs(np.subtract.outer(np.asarray(p), np.asarray(y)))
        i, j = linear_sum_assignment(distance)
        costs.append(
            float(
                (
                    np.minimum(distance[i, j], 2 * penalty).sum()
                    + penalty * abs(len(y) - len(p))
                )
                / max(len(p), len(y), 1)
            )
        )
    val["count_penalized_error_ppm"] = float(np.mean(costs))
    return val


def reference(a, name):
    smi_ref = {}
    symbol = a.nucleus[-1].lower()
    with (a.external / name / "test.jsonl").open() as f:
        for line in f:
            row = normalize_record(json.loads(line))
            peaks = [
                v[SHIFT]
                for rec in row[symbol + "_nmr"]
                for v in parse_nmr_record(rec, symbol)
                if v[SHIFT_PRESENT]
            ]
            if peaks:
                smi_ref.setdefault(row["smiles"], peaks)
    return smi_ref


def frozen(a, name):
    symbol = a.nucleus[-1]
    fn = a.models / "nmrnetpp/data_ours" / (name + "_" + symbol) / "valid.lmdb"
    env = readonly_lmdb(fn)
    with env.begin() as tx:
        smiles = [pickle.loads(b)["smiles"] for _, b in tx.cursor()]
    env.close()
    output = {}
    for backend in ["nmrnet", "nmrnetpp"]:
        files = sorted(
            (a.models / backend / "results" / (name + "_" + symbol)).glob("*/*.out.pkl")
        )
        if not files:
            continue
        folds = read_prediction_folds(files)
        pred = {}
        for i in sorted(set.intersection(*(set(f) for f in folds))):
            smi = Chem.MolToSmiles(Chem.MolFromSmiles(smiles[i]))
            pred.setdefault(
                smi, np.mean(np.stack([f[i] for f in folds]), axis=0).tolist()
            )
        output[backend] = pred
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("external", "models", "model", "report"):
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--nucleus", choices=["1H", "13C"], required=True)
    a = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    model = AssignedShiftPredictor(a.model)
    assert model.nucleus == a.nucleus
    penalty = 1.0 if a.nucleus == "1H" else 10.0
    gaps = (0.0, 0.03, 0.07, 0.12) if a.nucleus == "1H" else (0.0, 0.15, 0.4, 0.8)
    by_set = {}
    reserved = set()
    for name in DATASETS:
        refs = reference(a, name)
        old = frozen(a, name)
        ids = sorted(set(refs).intersection(*(set(v) for v in old.values())))
        keys = {s: Chem.MolToInchiKey(Chem.MolFromSmiles(s)).split("-")[0] for s in ids}
        ids = [s for s in ids if keys[s] not in reserved]
        if name == DATASETS[0]:
            reserved.update(keys.values())
        raw = {s: [v["shift_ppm"] for v in model.predict(s)] for s in ids}
        ids = [s for s in ids if raw[s]]
        if not ids:
            raise ValueError(f"No matched predictor outputs for {name}")
        y = [refs[s] for s in ids]
        baseline = {k: score([v[s] for s in ids], y, penalty) for k, v in old.items()}
        if name == DATASETS[0]:
            grid = {
                g: score([merged(raw[s], g) for s in ids], y, penalty) for g in gaps
            }
            gap = min(grid, key=lambda g: grid[g]["count_penalized_error_ppm"])
            choice = min(
                {**baseline, "assigned": grid[gap]},
                key=lambda k: ({**baseline, "assigned": grid[gap]})[k][
                    "count_penalized_error_ppm"
                ],
            )
        baseline["assigned"] = score([merged(raw[s], gap) for s in ids], y, penalty)
        by_set[name] = dict(
            paired_molecules=len(ids),
            predictors=baseline,
            selected=baseline[choice],
            eligible_refs=len(refs),
        )
        print(
            name,
            len(ids),
            {k: round(v["count_penalized_error_ppm"], 4) for k, v in baseline.items()},
            flush=True,
        )
    report = dict(
        nucleus=a.nucleus,
        selection_corpus=DATASETS[0],
        evaluation_corpora=DATASETS[1:],
        selection_metric="penalized minimum-cost matching per molecule",
        unmatched_cost_ppm=penalty,
        merge_gap_ppm=gap,
        selected_predictor=choice,
        grid=grid,
        datasets=by_set,
        model_sha256=sha256(a.model / "model.json"),
    )
    a.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
