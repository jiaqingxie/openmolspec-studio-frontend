"""Reconstruct QM9S spectra from native response tensors at the paired optimized geometry."""

import argparse
import csv
import hashlib
import json
import pickle
import sys
from pathlib import Path
import numpy as np
from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from openmolspec_bench.data import readonly_lmdb
from openmolspec_ui.theoretical import harmonic_modes, mode_activities
from scipy.constants import h, c, k as boltzmann


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("qm9s", "reserved", "output"):
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--size", type=int, default=640)
    a = p.parse_args()
    gold = {}
    env = readonly_lmdb(a.reserved)
    with env.begin() as txn:
        for key, blob in txn.cursor():
            r = pickle.loads(blob)
            if r.get("source_dataset") == "QM9":
                gold[r["inchikey"].split("-")[0]] = r["sample_id"]
    env.close()
    matches = {}
    with (a.qm9s / "mapping.txt").open() as f:
        for line in f:
            idx, smiles = line.rstrip().split(maxsplit=1)
            m = Chem.MolFromSmiles(smiles)
            if m is None:
                continue
            key = Chem.MolToInchiKey(m).split("-")[0]
            if key in gold:
                matches.setdefault(key, (int(idx), smiles))
    chosen = sorted(
        matches,
        key=lambda k: hashlib.sha256(("qm9s-forward-v1:" + k).encode()).digest(),
    )[: a.size]
    book = {}
    for k in chosen:
        idx, smiles = matches[k]
        file = a.qm9s / "qm9s_csv" / f"{idx:06}.csv"
        with file.open() as f:
            raw = list(csv.reader(f))[1:]
        native = raw[0]
        if (
            int(float(native[1])) != idx
            or Chem.MolToInchiKey(Chem.MolFromSmiles(native[3])).split("-")[0] != k
        ):
            raise ValueError(f"QM9S native ID mismatch at {idx}")
        n = int(float(native[4]))
        geom = np.array([r[1:5] for r in raw[10 : 10 + n]], float)
        if np.any(geom[:, 0].astype(int) != geom[:, 0]):
            raise ValueError("Invalid atomic number")
        hessian = np.array([r[1 : 1 + 3 * n] for r in raw[-3 * n :]], float)
        if hessian.shape != (3 * n, 3 * n) or not np.allclose(
            hessian, hessian.T, atol=0.005
        ):
            raise ValueError("Invalid QM9S Hessian")
        masses = np.array(
            [
                Chem.GetPeriodicTable().GetMostCommonIsotopeMass(int(z))
                for z in geom[:, 0]
            ]
        )
        modes = harmonic_modes(hessian, geom[:, 1:], masses)
        # QM9S stores derivatives as [atom, displacement axis, response component].
        # DetaNet uses xx, xy, yy, xz, yz, zz for the six polarizability components.
        dipole = np.array([r[1:10] for r in raw[10 + n : 10 + 2 * n]], float).reshape(
            n, 3, 3
        )
        polar = np.array(
            [r[1:19] for r in raw[10 + 2 * n : 10 + 3 * n]], float
        ).reshape(n, 3, 6)
        polar = polar[:, :, [0, 1, 3, 1, 2, 4, 3, 4, 5]].reshape(n, 3, 3, 3)
        ir, raman = mode_activities(modes.cartesian_modes, dipole, polar)
        freq = modes.frequencies_cm1 * 0.965
        valid = freq > 1
        freq, ir, raman = freq[valid], ir[valid], raman[valid]
        # Compare the two sets of response tensors with a fixed optical convention.
        grid = np.arange(500.0, 4001.0)
        line_shape = 1 / (1 + ((grid[:, None] - freq[None, :]) / 10.0) ** 2)
        population = 1 - np.exp(-h * c * 100 * freq / (boltzmann * 298.0))
        raman = raman * (1e7 / 532 - freq) ** 4 / freq / population
        rec = dict(
            key=k,
            id=idx,
            original_qm9=int(float(native[2])),
            openspec=gold[k],
            smiles=smiles,
            geom=geom.tolist(),
            ir=(line_shape @ ir).astype("f"),
            raman=(line_shape @ raman).astype("f"),
        )
        book[idx] = rec
    rows = list(book.values())
    print(
        "Matched native geometry, Hessian and response tensors", len(rows), flush=True
    )
    temporary = a.output.with_suffix(".partial")
    with temporary.open("wb") as f:
        pickle.dump(rows, f)
    temporary.replace(a.output)


if __name__ == "__main__":
    main()
