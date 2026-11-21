"""Select a TransPeakNet correction on silver data, then audit the expert gold archive."""

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import Chem
import torch
from openmolspec_bench.transpeaknet import (
    SOLVENT_CLASS,
    load_model,
    predict_sites,
    correction_keys,
    calibrated_prediction,
)
from openmolspec_bench.data import sha256
from openmolspec.dataset import molspectra

STRENGTHS = (0, 0.15, 0.35, 0.6, 0.85, 1.0)


def observations(smiles, sol, ids, preds, targets):
    m = Chem.MolFromSmiles(smiles)
    for site, raw, ref in zip(ids, preds, targets):
        hydrogens = m.GetAtomWithIdx(site).GetTotalNumHs()
        groups = correction_keys(raw[0], sum(raw[1:]) / 2, sol, hydrogens)
        yield groups, np.asarray(raw), np.asarray(ref)


def calibration(groups, tables, depth):
    for k in reversed(groups[: depth + 1]):
        if k in tables:
            return tables[k]
    return np.zeros(3)


def select(a, gold):
    val = []
    res = defaultdict(list)
    train_ids = set()
    val_ids = set()
    with gzip.open(a.cache, "rt") as f:
        for line in f:
            k, smi, _, sol, idx, raw, target = json.loads(line)
            if k in gold:
                continue
            fold = (
                int(hashlib.sha256(("hsqc-cal-v1:" + k).encode()).hexdigest()[:8], 16)
                % 5
            )
            if fold == 0:
                val_ids.add(k)
                val.append((k, smi, sol, idx, raw, target))
                continue
            train_ids.add(k)
            for groups, p, y in observations(smi, sol, idx, raw, target):
                for group in groups:
                    res[group].append(y - p)
    assert train_ids.isdisjoint(val_ids)
    tables = {k: np.median(v, axis=0) for k, v in res.items() if len(v) >= 30}
    del res
    score = np.zeros((4, len(STRENGTHS), 2))
    by_id = defaultdict(list)
    for key, smi, sol, idx, raw, target in val:
        local = np.zeros_like(score)
        for groups, p, y in observations(smi, sol, idx, raw, target):
            for depth in range(4):
                delta = calibration(groups, tables, depth)
                error = np.abs(p + np.array(STRENGTHS)[:, None] * delta - y)
                local[depth, :, 0] += error[:, 0]
                local[depth, :, 1] += error[:, 1:].mean(axis=1)
        by_id[key].append(local / len(raw))
    score = np.mean([np.mean(v, axis=0) for v in by_id.values()], axis=0)
    settings = [
        np.unravel_index(score[:, :, i].argmin(), score.shape[:2]) for i in range(2)
    ]
    conf = dict(
        depths=[int(d) for d, _ in settings],
        strengths=[STRENGTHS[t] for _, t in settings],
        tables={k: v.tolist() for k, v in tables.items()},
    )
    report = dict(
        selection_metric="validation molecule-weighted carbon and proton MAE, ppm",
        baseline_validation=score[0, 0].tolist(),
        selected_validation=[
            float(score[d, t, i]) for i, (d, t) in enumerate(settings)
        ],
        silver_train_identities=len(train_ids),
        silver_validation_identities=len(val_ids),
        silver_archive_sha256=sha256(a.cache),
        frozen_base_training_overlap="silver split may include structures seen in author training; gold identities excluded from all calibration",
        settings={k: v for k, v in conf.items() if k != "tables"},
    )
    return conf, report, train_ids | val_ids


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("cache", "source", "config", "report"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    torch.set_num_threads(1)
    archive = a.source / "data_annotation/HSQC_Annotation_TestData.zip"
    data = molspectra("transpeaknet_hsqc_test", root=archive)
    data.verify()
    expert_records = list(data["test"])
    gold = {
        Chem.MolToInchiKey(Chem.MolFromSmiles(r["smiles"])).split("-")[0]
        for r in expert_records
    }
    conf, report, silver = select(a, gold)
    a.config.write_text(json.dumps(conf, separators=(",", ":")) + "\n")
    a.report.write_text(json.dumps(report, indent=2) + "\n")
    print("Frozen", report, flush=True)
    source = a.source
    metadata = defaultdict(set)
    with (source / "data_csv/2dnmr/all_files_testdata_solvent_mw.csv").open() as f:
        for row in csv.DictReader(f):
            metadata[row["File_name"]].add(int(row["solvent_class"]))
    model = load_model(source)
    names = {code: name for name, code in SOLVENT_CLASS.items()}
    rows = []
    for r in expert_records:
        smi = r["smiles"]
        key = Chem.MolToInchiKey(Chem.MolFromSmiles(smi)).split("-")[0]
        if key in silver:
            raise ValueError("Gold structure present in silver fit or validation")
        solvents = metadata[r["source_id"]]
        sol = next(iter(solvents)) if len(solvents) == 1 else SOLVENT_CLASS["unknown"]
        mol = Chem.AddHs(Chem.MolFromSmiles(smi))
        ids, c, h = predict_sites(model, mol, names[sol])
        annotations = {v["carbon_atom_index"]: v for v in r["hsqc_assignments"]}
        raw = np.column_stack([c, h])
        target = np.array(
            [
                [annotations[i]["carbon_ppm"]] + (annotations[i]["proton_ppm"] * 2)[:2]
                for i in ids
            ]
        )
        _, cal_c, cal_h = calibrated_prediction((ids, c, h), mol, names[sol], conf)
        adjusted = np.column_stack([cal_c, cal_h])
        rows.append(
            [
                [float(err[:, 0].mean()), float(err[:, 1:].mean())]
                for err in (abs(raw - target), abs(adjusted - target))
            ]
        )
    arr = np.array(rows)
    rng = np.random.default_rng(2583)
    draws = rng.integers(len(rows), size=(5000, len(rows)))
    delta = arr[:, 1] - arr[:, 0]
    bounds = np.percentile(delta[draws].mean(axis=1), [2.5, 97.5], axis=0)
    report.update(
        paired_difference_ci95={name: bounds[:, i].tolist() for i, name in enumerate(("carbon_mae_ppm", "proton_mae_ppm"))},
        gold_spectra=len(rows),
        gold_sha256=sha256(archive),
        config_sha256=sha256(a.config),
        baseline_expert_test=arr[:, 0].mean(axis=0).tolist(),
        selected_expert_test=arr[:, 1].mean(axis=0).tolist(),
    )
    a.report.write_text(json.dumps(report, indent=2) + "\n")
    print(
        "Expert",
        report["baseline_expert_test"],
        report["selected_expert_test"],
        flush=True,
    )


if __name__ == "__main__":
    main()
