"""Compare 13C NMRNet++ folds and learned site shifts on paired, structure-disjoint corpora."""

import argparse
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import Chem, RDLogger
from openmolspec.assigned_shifts import AssignedShiftPredictor, combine_sites
from openmolspec.peak_learning import PeakLearningPredictor
from openmolspec_bench.data import readonly_lmdb, sha256
from openmolspec_bench.runner import read_prediction_folds
from openmolspec_bench.peak_evaluation import matching_errors
from openmolspec_bench.metrics import peak_metrics
from compare_assigned_hc import DATASETS, reference


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("models", "external", "assigned", "weak", "selected", "report"):
        p.add_argument("--" + n, type=Path, required=True)
    a = p.parse_args()
    a.nucleus = "13C"
    RDLogger.DisableLog("rdApp.*")
    selector = json.loads(a.selected.read_text())
    weight = selector["model"]["peak_learning_weight"]
    base = AssignedShiftPredictor(a.assigned)
    weak = PeakLearningPredictor(a.weak)
    candidates = [
        (n, w, g)
        for n in (1, 3, 5)
        for w in (0.0, 0.15, 0.3, 0.5)
        for g in (-1.0, 0.0, 0.2, 0.5, 0.8)
    ]
    default = (5, 0.0, -1.0)
    # Negative merge gap preserves every atomic prediction, including equivalent carbon atoms.
    report = dict(
        nucleus="13C",
        selection_dataset=DATASETS[0],
        audit_datasets=list(DATASETS[1:]),
        experimental_site_weight=weight,
        source_sha256=sha256(a.selected),
        penalty_ppm=10.0,
        datasets={},
    )
    occupied = set()
    delta = []
    for dataset in DATASETS:
        refs = reference(a, dataset)
        metadata = a.models / "nmrnetpp/data_ours" / (dataset + "_C") / "valid.lmdb"
        root = a.models / "nmrnetpp/results" / (dataset + "_C")
        fd = sorted(root.glob("cv_seed_42_fold_*/*.out.pkl"))
        if len(fd) != 5:
            raise ValueError("All five model folds are required")
        folds = read_prediction_folds(fd)
        with readonly_lmdb(metadata) as env:
            with env.begin() as t:
                rows = [pickle.loads(b) for _, b in t.cursor()]
        measured = []
        spectrum = []
        for i in sorted(set.intersection(*(set(f) for f in folds))):
            orig = rows[i]["smiles"]
            mol = Chem.MolFromSmiles(orig)
            smi = Chem.MolToSmiles(mol)
            key = Chem.MolToInchiKey(mol).split("-")[0]
            if key in occupied or smi not in refs:
                continue
            carbons = [at.GetIdx() for at in mol.GetAtoms() if at.GetAtomicNum() == 6]
            raw = np.stack([f[i] for f in folds])
            if raw.shape != (5, len(carbons)):
                raise ValueError("Recorded folds are not atom-aligned")
            indices = {idx: j for j, idx in enumerate(carbons)}
            observed = combine_sites(base.predict(orig), weak.predict(orig), weight)
            custom = np.array([s["shift_ppm"] for s in observed])
            grouped = [
                np.asarray([indices[idx] for idx in s["atom_indices"]])
                for s in observed
            ]
            if sorted(j for grp in grouped for j in grp) != list(range(len(carbons))):
                raise ValueError("Incomplete carbon site coverage")
            expanded = np.zeros(len(carbons))
            for shift, grp in zip(custom, grouped):
                expanded[grp] = shift
            # Reuse each fixed fold average for every validation setting.
            atom = {n: raw[:n].mean(axis=0) for n in (1, 3, 5)}
            sites = {
                n: np.array([atom[n][group].mean() for group in grouped]) for n in atom
            }
            spectrum.append((atom, sites, custom, expanded))
            measured.append(refs[smi])
            occupied.add(key)

        def scores(setting):
            n, w, g = setting
            pred = []
            for atom, sites, custom, expanded in spectrum:
                if g < 0:
                    pred.append((1 - w) * atom[n] + w * expanded)
                    continue
                values = np.sort((1 - w) * sites[n] + w * custom)
                groups = []
                for v in values:
                    if not groups or g == 0 or v - groups[-1][0] > g:
                        groups.append([])
                    groups[-1].append(v)
                pred.append(np.array([sum(grp) / len(grp) for grp in groups]))
            return matching_errors(pred, measured, 10), pred

        if dataset == DATASETS[0]:
            ranked = sorted(
                (scores(setting)[0].mean(), setting) for setting in candidates
            )
            pick = ranked[0][1]
            report.update(
                selected_setting=pick,
                validation_grid=[dict(setting=st, error=float(v)) for v, st in ranked],
            )
            a.report.write_text(json.dumps(report, indent=2) + "\n")
        e0, p0 = scores(default)
        e1, p1 = scores(pick)
        report["datasets"][dataset] = dict(
            molecules=len(measured),
            raw=dict(
                **peak_metrics(p0, measured), count_penalized_error_ppm=float(e0.mean())
            ),
            candidate=dict(
                **peak_metrics(p1, measured), count_penalized_error_ppm=float(e1.mean())
            ),
        )
        if dataset != DATASETS[0]:
            delta.append(e1 - e0)
        print(
            dataset,
            len(measured),
            round(e0.mean(), 4),
            round(e1.mean(), 4),
            pick,
            flush=True,
        )
    d = np.concatenate(delta)
    rng = np.random.default_rng(4273)
    ci = np.percentile(rng.choice(d, (2000, len(d))).mean(axis=1), [2.5, 97.5]).tolist()
    report.update(
        heldout_difference_ci95=ci,
        deploy_setting=(
            pick if ci[1] < 0 and sum(x.mean() < 0 for x in delta) >= 2 else default
        ),
    )
    a.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
