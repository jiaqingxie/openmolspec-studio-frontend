"""Build paired 13C/1H references for WanJuan and the official 2DNMRGym evaluation."""

import argparse
from collections import Counter, defaultdict
import csv
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from rdkit import Chem, RDLogger
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


def matched_count(x, y, tolerances):
    allowed = (np.abs(x[:, None, :] - y[None, :, :]) <= tolerances).all(axis=2)
    matches = maximum_bipartite_matching(csr_matrix(allowed), perm_type="column")
    return int((matches >= 0).sum())


def write_rows(path, rows):
    with (
        path.open("wb") as out,
        gzip.GzipFile(filename="", fileobj=out, mode="wb", mtime=0) as z,
    ):
        for row in rows:
            z.write(
                (
                    json.dumps(
                        row, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                    )
                    + "\n"
                ).encode()
            )


@lru_cache(maxsize=120000)
def identity(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None or mol.GetNumAtoms() == 0:
        return ""
    return Chem.MolToInchiKey(mol).split("-")[0]


def reference_pairs(assignments):
    return sorted({(a["carbon_ppm"], h) for a in assignments for h in a["proton_ppm"]})


def source_pools(source, calibration):
    pools = {}
    paths = {
        "author_2d_trainval": [
            source
            / "data_csv/2dnmr/nmr_smile_solventclass_filtered4_3dgnn_trainval.csv"
        ],
        "author_1d_pretraining_inventory": sorted(
            (source / "data_csv/1dnmr").glob("*.csv")
        ),
    }
    for label, files in paths.items():
        column = "SMILES" if label == "author_2d_trainval" else "smiles"
        keys = set()
        for path in files:
            with path.open() as handle:
                keys.update(identity(r[column]) for r in csv.DictReader(handle))
        keys.discard("")
        pools[label] = keys
    with gzip.open(calibration, "rt") as f:
        pools["local_calibration_train_or_validation"] = {
            json.loads(line)[0] for line in f
        }
    return pools


def wanjuan(path, review, digest):
    audit, candidates = [], []
    located = defaultdict(set)
    multi_lists = defaultdict(set)
    actual = hashlib.sha256()
    # Parse each source document once while verifying the snapshot.
    with path.open("rb") as f:
        for doc_line, raw in enumerate(f, 1):
            actual.update(raw)
            lower = raw.lower()
            if b"hsqc" not in lower and b"heteronuclear single quantum" not in lower:
                continue
            doc = json.loads(raw)
            patent = doc["meta_info"]["folder_id"]
            for i, comp in enumerate(doc.get("compounds", [])):
                for j, spec in enumerate(comp.get("spectra", [])):
                    kind = spec.get("spectrum_type", "").lower()
                    if (
                        "hsqc" not in kind
                        and "heteronuclear single quantum" not in kind
                    ):
                        continue
                    source_id = f"{patent}:{i}:{j}@{doc_line}"
                    event = dict(
                        id=source_id, spectrum_type=kind, line=spec.get("source_line")
                    )
                    audit.append(event)
                    smiles = comp.get("smiles_std") or comp.get("smiles")
                    shift = str(spec.get("chemical_shift") or "").strip()
                    if not smiles or not shift:
                        event["status"] = "missing_structure_or_shift_text"
                        continue
                    if shift not in review or "15n" in kind or "29si" in kind:
                        event["status"] = "no_reviewed_unambiguous_CH_peak_list"
                        continue
                    mol = Chem.MolFromSmiles(smiles)
                    if (
                        mol is None
                        or len(Chem.GetMolFrags(mol)) != 1
                        or any(a.GetAtomicNum() == 0 for a in mol.GetAtoms())
                    ):
                        event["status"] = (
                            "invalid_disconnected_or_unspecified_structure"
                        )
                        continue
                    solvent_text = spec.get("solvent") or ""
                    solvent = {
                        "CDCl3": "CDCl3",
                        "CHCl3": "CDCl3",
                        "D2O": "D2O",
                        "C6D6": "C6D6",
                        "DMSO-d6": "DMSO-d6",
                    }.get(solvent_text, "unknown")
                    pairs = tuple(
                        sorted(set(map(tuple, review[shift]["peaks_c_h_ppm"])))
                    )
                    key = identity(smiles)
                    location = (patent, event["line"], pairs)
                    located[location].add(key)
                    if len(pairs) >= 3:
                        multi_lists[pairs].add(key)
                    event["review_example"] = review[shift]["example_source"]
                    candidates.append(
                        (location, pairs, smiles, solvent, solvent_text, event)
                    )
    if actual.hexdigest() != digest:
        raise ValueError("Unexpected WanJuan source snapshot")
    records = {}
    for location, pairs, smiles, solvent, raw_solvent, event in candidates:
        if len(located[location]) > 1 or len(multi_lists.get(pairs, ())) > 1:
            event["status"] = "conflicting_structure_attribution"
            continue
        sig = (Chem.MolToSmiles(Chem.MolFromSmiles(smiles)), solvent, pairs)
        if sig in records:
            event["status"] = "duplicate"
        else:
            event["status"] = "included"
            records[sig] = dict(
                id=event["id"],
                smiles=smiles,
                solvent=solvent,
                raw_solvent=raw_solvent,
                peaks_c_h_ppm=pairs,
                scope="reported_correlations_only",
                source_ids=[],
            )
        records[sig]["source_ids"].append(event["id"])
        event["benchmark_id"] = records[sig]["id"]
    return list(records.values()), audit


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("wanjuan", "gym", "source", "calibration-cache", "out"):
        p.add_argument("--" + flag, required=True, type=Path)
    p.add_argument(
        "--review",
        type=Path,
        default=ROOT / "results/hsqc_benchmarks/wanjuan_review.json",
    )
    args = p.parse_args()
    from openmolspec.dataset import molspectra
    from openmolspec_bench.data import sha256
    from openmolspec_bench.transpeaknet import SOLVENT_CLASS, graph

    RDLogger.DisableLog("rdApp.*")
    args.out.mkdir(exist_ok=True, parents=True)
    archive = args.source / "data_annotation/HSQC_Annotation_TestData.zip"
    raw_digest = json.loads(
        (ROOT / "results/opendatalab_all_modalities_20261117.json").read_text()
    )["source_sha256"]
    expected = {
        "wanjuan": (args.wanjuan, raw_digest),
        "gym_official_eval": (
            args.gym,
            "75cf2132353b34d862ef311522aa64b8451e9070ce4723596d94347ec40e0c4c",
        ),
        "transpeaknet_expert": (
            archive,
            "614be38c96f4bd1b8faad55a13c80423fe39136258bf234c4b0956d38fda0368",
        ),
        "calibration_cache": (
            args.calibration_cache,
            "0ab682f5ba9042be93d3375a767d7d1e24377e4bdd156cd5d3a9b66a5dfa5b61",
        ),
    }
    for name, (path, digest) in expected.items():
        if name != "wanjuan" and sha256(path) != digest:
            raise ValueError(f"Source version differs for {path}")
    pool = source_pools(args.source, args.calibration_cache)
    records, audit = wanjuan(
        args.wanjuan, json.loads(args.review.read_text()), raw_digest
    )
    panels = {"wanjuan": records, "2dnmrgym": []}
    write_rows(args.out / "wanjuan_audit.jsonl.gz", audit)
    names = {v: k for k, v in SOLVENT_CLASS.items()}
    experts = {
        r["source_id"]: r
        for r in molspectra("transpeaknet_hsqc_test", root=archive)["test"]
    }
    # The final selector drops expert identities again after reading the silver cache.
    calibration_ids = pool["local_calibration_train_or_validation"]
    calibration_ids.difference_update(identity(r["smiles"]) for r in experts.values())
    selection = json.loads((ROOT / "results/forward_selection_hsqc.json").read_text())
    if (
        len(calibration_ids)
        != selection["silver_train_identities"]
        + selection["silver_validation_identities"]
    ):
        raise ValueError("Fitting-pool identities differ from the calibration receipt")
    metadata = defaultdict(set)
    with (args.source / "data_csv/2dnmr/all_files_testdata_solvent_mw.csv").open() as f:
        for r in csv.DictReader(f):
            metadata[r["File_name"]].add(int(r["solvent_class"]))
    common = Counter()
    with args.gym.open() as f:
        for gym in map(json.loads, f):
            sid = gym["filename"] + ".csv"
            expert = experts[sid]
            smiles = expert["smiles"]
            molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
            sol = names[gym["graph_data"]["solvent_class"]]
            reconstructed = graph(molecule, sol)
            if not all(
                np.array_equal(reconstructed[k].numpy(), gym["graph_data"][k])
                for k in ("x", "edge_index", "edge_attr")
            ):
                raise ValueError(f"Graph or atom order mismatch for {sid}")
            indices = [
                a.GetIdx()
                for a in molecule.GetAtoms()
                if a.GetAtomicNum() == 6
                and any(n.GetAtomicNum() == 1 for n in a.GetNeighbors())
            ]
            # Official 2DNMRGym coordinates are stored in 1/200 (C) and 1/10 (H) ppm.
            labels = []
            for i, c, h in zip(indices, gym["c_peaks"], gym["h_peaks"], strict=True):
                if len(c) != 1 or len(h) != 2:
                    raise ValueError(f"Unrecognized HSQC label shape for {sid}")
                labels.append(
                    dict(
                        carbon_atom_index=i,
                        carbon_ppm=c[0] * 200,
                        proton_ppm=list(dict.fromkeys(v * 10 for v in h)),
                    )
                )
            panels["2dnmrgym"].append(
                dict(
                    id=sid,
                    smiles=smiles,
                    solvent=sol,
                    assignments=labels,
                    peaks_c_h_ppm=reference_pairs(labels),
                    scope="source_peak_list",
                )
            )
            exp_by_site = {
                v["carbon_atom_index"]: v for v in expert["hsqc_assignments"]
            }

            def same_site(v):
                e = exp_by_site[v["carbon_atom_index"]]
                return abs(e["carbon_ppm"] - v["carbon_ppm"]) <= 0.001 and np.allclose(
                    np.sort((e["proton_ppm"] * 2)[:2]),
                    np.sort((v["proton_ppm"] * 2)[:2]),
                    atol=0.001,
                    rtol=0,
                )

            common["same_source_id_and_structure"] += 1
            common["same_site_labels_within_0.001_ppm"] += all(
                same_site(v) for v in labels
            )
            classes = metadata[sid]
            exp_sol = names[next(iter(classes))] if len(classes) == 1 else "unknown"
            common["same_solvent_input"] += sol == exp_sol
            gym_peaks = np.asarray(panels["2dnmrgym"][-1]["peaks_c_h_ppm"])
            expert_peaks = np.asarray(reference_pairs(expert["hsqc_assignments"]))
            common["same_unassigned_peak_set_within_0.001_ppm"] += (
                len(gym_peaks)
                == len(expert_peaks)
                == matched_count(gym_peaks, expert_peaks, [0.001, 0.001])
            )
    if {r["id"] for r in panels["2dnmrgym"]} != set(experts) or len(
        panels["2dnmrgym"]
    ) != len(experts):
        raise ValueError("The two official release views are not aligned")
    ids = {}
    for label, rows in panels.items():
        for r in rows:
            key = identity(r["smiles"])
            if not key:
                raise ValueError(r["id"])
            r["connectivity"] = key
            r["listed_in"] = [name for name, keys in pool.items() if key in keys]
        ids[label] = {r["connectivity"] for r in rows}
    meta = dict(
        sources={k: v[1] for k, v in expected.items()},
        wanjuan_review_sha256=sha256(args.review),
        gym_revision="a586d2de73a783ea5636ffd8c1df0363a5bd6df0",
        transpeaknet_revision="2e93db82a9d627ac01109474e9b6e594065e3d56",
        wanjuan_audit=dict(Counter(r["status"] for r in audit)),
        official_views=dict(common),
        pool_unique_connectivities={k: len(v) for k, v in pool.items()},
        pairwise_shared_connectivities={},
        panels={},
    )
    for label, rows in panels.items():
        out = args.out / (label + ".jsonl.gz")
        write_rows(out, rows)
        meta["panels"][label] = dict(
            spectra=len(rows),
            unique_connectivities=len(ids[label]),
            reference_sha256=sha256(out),
            spectra_listed_in={n: sum(n in r["listed_in"] for r in rows) for n in pool},
        )
        for other in panels:
            if other > label:
                meta["pairwise_shared_connectivities"][f"{label}/{other}"] = len(
                    ids[label] & ids[other]
                )
    (args.out / "sources.json").write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
