"""Library retrieval via independent reference spectra and molecular fingerprint similarity."""

import argparse
from pathlib import Path
from functools import lru_cache
import json
import pickle

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from scipy.ndimage import gaussian_filter1d
from .data import readonly_lmdb, sha256
from openmolspec_ui.config import discover_assets


@lru_cache(maxsize=60000)
def identity(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None or not mol.GetNumAtoms():
        raise ValueError("Invalid molecular structure")
    return Chem.MolToSmiles(mol, isomericSmiles=False), Chem.MolToInchiKey(mol).split(
        "-"
    )[0]


def vectorize(row):
    channels = []
    for name in ("ir", "raman"):
        x = np.maximum(np.asarray(row[name], dtype=np.float32), 0)
        channels.append(np.sqrt(x))
    for name, low, high, width in [
        ("nmr_h_shifts_ppm", -5, 20, 0.1),
        ("nmr_c_shifts_ppm", -30, 260, 1.0),
    ]:
        bins = round((high - low) / width)
        x = np.histogram(row[name], bins=bins, range=(low, high))[0].astype(np.float32)
        channels.append(gaussian_filter1d(x, 1))
    return [x / max(float(np.linalg.norm(x)), 1.0e-12) for x in channels]


def ranking(order, target):
    return int(np.flatnonzero(order == target)[0]) + 1


def reference_spectra(path, pool, train):
    banned = {identity(s)[1] for s in pool}
    seen = set()
    refs = []
    spectra = []
    refkey = None
    with readonly_lmdb(path) as env, env.begin() as txn:
        for _, blob in txn.cursor():
            r = pickle.loads(blob)
            smi, key = identity(r["kekule_smiles"])
            if key in seen or key in banned or key not in train:
                continue
            # H/C bins are shared across samples only when they use the same chemical-shift reference.
            if refkey is None:
                refkey = r["nmr_reference_id"]
            if r["nmr_reference_id"] != refkey:
                raise ValueError("Reference profiles differ")
            seen.add(key)
            refs.append(smi)
            spectra.append(vectorize(r))
    if len(refs) < 8:
        raise ValueError("Incompatible reference library or query panel")
    return refs, spectra, refkey


def fingerprint_lookup(pool, refs):
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)

    def fp(s):
        return generator.GetFingerprint(Chem.MolFromSmiles(s))

    bank = [fp(s) for s in pool]

    @lru_cache(maxsize=512)
    def similarities(ref_idx):
        return np.asarray(
            DataStructs.BulkTanimotoSimilarity(fp(refs[int(ref_idx)]), bank),
            dtype=np.float32,
        )

    return similarities


def candidate_orders(scores, similarities):
    nearest = np.argsort(-scores, kind="stable")[:8]
    t = np.stack([similarities(int(i)) for i in nearest])
    single = np.argsort(-t[0], kind="stable")
    fused = t.mean(axis=0)
    full = np.argsort(-fused, kind="stable")
    top32 = single[:32]
    shortlist = np.concatenate(
        [top32[np.argsort(-fused[top32], kind="stable")], single[32:]]
    )
    return single, shortlist, full, t[0], fused


def retrieve_reference(
    inputs, candidates, portable, *, top_k=10, rerank=False, shortlist=False
):
    """Rank a SMILES bank using independent theoretical reference spectra.

    Inputs accept IR alone, Raman alone, their pair, or their pair with both H/C
    lists. Four-channel inference requires the chemical shift reference ID.
    Shortlist reranking returns up to 32 ITM-free, fingerprint-consensus results.
    """
    from importlib.resources import files

    channels = [
        k for k in ("ir", "raman", "nmr_h", "nmr_c") if inputs.get(k) is not None
    ]
    if channels not in (
        ["ir"],
        ["raman"],
        ["ir", "raman"],
        ["ir", "raman", "nmr_h", "nmr_c"],
    ):
        raise ValueError("Expected IR, Raman, IR + Raman, or all four channels")
    if (
        type(top_k) is not int
        or top_k < 1
        or (shortlist and (not rerank or top_k > 32))
    ):
        raise ValueError("Invalid top_k or shortlist ranking")
    if isinstance(candidates, str):
        raise ValueError("Supply a list of SMILES candidates")
    pool = list(dict.fromkeys(identity(s)[0] for s in candidates))
    if len(pool) < 2:
        raise ValueError("Supply at least two distinct candidate structures")
    row = {}
    for name, field, default in (
        ("ir", "ir", np.zeros(1024)),
        ("raman", "raman", np.zeros(1024)),
        ("nmr_h", "nmr_h_shifts_ppm", []),
        ("nmr_c", "nmr_c_shifts_ppm", []),
    ):
        row[field] = np.asarray(
            inputs[name] if name in channels else default, dtype=np.float32
        )
        if name in channels and (
            row[field].ndim != 1
            or not len(row[field])
            or not np.isfinite(row[field]).all()
            or name in ("ir", "raman")
            and len(row[field]) != 1024
        ):
            raise ValueError("Invalid channel: " + name)
    fit = json.loads(
        files("openmolspec")
        .joinpath("assets", "vib_shift_fit_connectivities.json")
        .read_text()
    )
    refs, spectra, refkey = reference_spectra(
        discover_assets(portable).spectrum_lmdb, pool, set(fit["train"])
    )
    if "nmr_h" in channels and inputs.get("nmr_reference_id") != refkey:
        raise ValueError("Supply the reference library's nmr_reference_id for H/C")
    features = vectorize(row)
    names = ("ir", "raman", "nmr_h", "nmr_c")
    scores = sum(
        np.stack([r[i] for r in spectra]) @ features[i]
        for i, name in enumerate(names)
        if name in channels
    ) / len(channels)
    first, short, full, nearest_score, consensus_score = candidate_orders(
        scores, fingerprint_lookup(pool, refs)
    )
    order = short if shortlist else full if rerank else first
    values = consensus_score if rerank else nearest_score
    return dict(
        reference_connectivities=len(refs),
        candidate_pool=len(pool),
        channels=channels,
        ranking="top32_consensus"
        if shortlist
        else "full_consensus"
        if rerank
        else "nearest_reference",
        candidates=[
            {"smiles": pool[i], "score": float(values[i])} for i in order[:top_k]
        ],
    )


def evaluate(portable, fit_index, pool_size, n_queries, seed, selected_channel=None):
    """Score nearest-reference retrieval and both reranking strategies on a held-out panel."""
    from .expanded_vib import choose

    if not 2 <= pool_size or not 1 <= n_queries <= pool_size:
        raise ValueError("Expected at least two candidates and one query")
    path = discover_assets(Path(portable)).spectrum_lmdb
    fit = json.loads(fit_index.read_text())
    train = set(fit["train"])
    queries, pool, rows, _ = choose(
        path, pool_size, n_queries, seed, train | set(fit["val"])
    )
    refs, spectra, refkey = reference_spectra(path, pool, train)
    if any(r["nmr_reference_id"] != refkey for r in rows):
        raise ValueError("Incompatible query chemical shift reference")
    qx = [vectorize(r) for r in rows]
    sim = [np.stack(q) @ np.stack(r).T for q, r in zip(zip(*qx), zip(*spectra))]
    del spectra
    similarities = fingerprint_lookup(pool, refs)
    ids = {s: i for i, s in enumerate(pool)}
    report = dict(
        protocol="Fixed spectral-neighbor reference baseline: each supplied channel has equal weight after unit normalization. Candidate scores use Morgan radius 2 Tanimoto to the closest reference; reranking averages Tanimoto over the top 8 references with equal weights. All reference connectivities are in the pre-existing fitting partition and disjoint from every candidate. Only SMILES are supplied for the candidate bank. No parameters fitted for this baseline.",
        dataset_sha256=sha256(path),
        fit_index_sha256=sha256(fit_index),
        seed=seed,
        reference_connectivities=len(refs),
        pool_size=len(pool),
        pool=pool,
        query_targets=queries,
        shortlist=32,
        channels={},
    )
    for label, indices in [
        ("ir", [0]),
        ("raman", [1]),
        ("ir_raman", [0, 1]),
        ("ir_raman_hc", [0, 1, 2, 3]),
    ]:
        if selected_channel is not None and label != selected_channel:
            continue
        similarity = sum(sim[i] for i in indices) / len(indices)
        records = []
        for s, scores in zip(queries, similarity):
            single, shortlist, full, _, _ = candidate_orders(scores, similarities)
            records.append(
                dict(
                    target=s,
                    reference_rank=ranking(single, ids[s]),
                    shortlist_rank=ranking(shortlist, ids[s]),
                    full_rank=ranking(full, ids[s]),
                )
            )
        metrics = {}
        for field in ("reference_rank", "shortlist_rank", "full_rank"):
            ranks = np.asarray([r[field] for r in records])
            metrics[field] = dict(
                top1_hits=int((ranks == 1).sum()),
                top5_hits=int((ranks <= 5).sum()),
                mrr=float(np.mean(1 / ranks)),
                queries=len(ranks),
            )
        report["channels"][label] = dict(metrics=metrics, records=records)
        print(label, metrics, flush=True)
    report["complete"] = True
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    from importlib.resources import files

    p.add_argument(
        "--fit-index",
        type=Path,
        default=files("openmolspec").joinpath(
            "assets", "vib_shift_fit_connectivities.json"
        ),
    )
    for name in ("portable", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--pool", type=int, default=4096)
    p.add_argument("--queries", type=int, default=128)
    p.add_argument("--seed", type=int, default=1123)
    a = p.parse_args()
    report = evaluate(a.portable, a.fit_index, a.pool, a.queries, a.seed)
    tmp = a.output.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2) + "\n")
    tmp.replace(a.output)


if __name__ == "__main__":
    main()
