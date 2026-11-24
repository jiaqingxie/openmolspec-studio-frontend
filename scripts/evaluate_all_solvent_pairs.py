"""Compare solvent transfer for every measured pair with an independent same-solvent-pair reference."""

from argparse import ArgumentParser
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
from openmolspec_bench.solvent_transfer import ReferenceTransfer
from openmolspec_bench.solvent_fit import fit, predict
from openmolspec_bench.data import sha256


def main():
    p = ArgumentParser(description=__doc__)
    p.add_argument("--library", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    library = json.loads(a.library.read_text())
    ref = ReferenceTransfer(library)
    out = dict(
        library_sha256=sha256(a.library),
        protocol="All observed ordered-by-solvent atom pairs with another connectivity in the same nucleus/solvent pair. Entire connectivity excluded from ridge fit and reference search. Pair-weighted and molecule-weighted MAE in ppm.",
        eligible={},
        records=[],
        skipped=[],
    )
    for n in ("1H", "13C"):
        rows = [r for r in library["pairs"] if r["nucleus"] == n]
        by_key = defaultdict(list)
        for r in rows:
            by_key[r["smiles"]].append(r)
        solvents = sorted(
            {r[k + "_solvent"] for r in rows for k in ("source", "target")}
        )
        by_pair = defaultdict(set)
        for r in rows:
            by_pair[r["source_solvent"], r["target_solvent"]].add(r["smiles"])
        # Each independent structure contributes one median shift change per solvent pair.
        grouped = defaultdict(lambda: defaultdict(list))
        for row in rows:
            pair = (row["source_solvent"], row["target_solvent"])
            grouped[pair][row["smiles"]].append(
                row["target"]["shift_ppm"] - row["source"]["shift_ppm"]
            )
        middle = {
            pair: {key: float(np.median(delta)) for key, delta in molecules.items()}
            for pair, molecules in grouped.items()
        }
        errors = []
        per_key = []
        for key, targets in sorted(by_key.items()):
            training = [r for r in rows if r["smiles"] != key]
            model = {
                "solvents": {n: solvents},
                "coefficients": {n: fit(training, solvents)},
            }
            local = []
            for r in targets:
                src, tgt = r["source_solvent"], r["target_solvent"]
                metadata = dict(
                    nucleus=n,
                    connectivity=key,
                    molecule_id=r["molecule_id"],
                    atom_id=r["atom_id"],
                    source=src,
                    target=tgt,
                )
                if len(by_pair[src, tgt]) < 2:
                    out["skipped"].append(metadata)
                    continue
                x = r["source"]["shift_ppm"]
                truth = r["target"]["shift_ppm"]
                baseline = ref.predict(key, n, src, tgt, x)["predicted_target_ppm"]
                fitted = predict(model, n, src, tgt, x)["predicted_target_ppm"]
                robust = x + float(
                    np.median([d for k, d in middle[src, tgt].items() if k != key])
                )
                local.append(np.abs(np.array([fitted, baseline, x, robust]) - truth))
                out["records"].append(
                    dict(
                        **metadata,
                        source_ppm=x,
                        truth_ppm=truth,
                        ridge=fitted,
                        reference=baseline,
                        median=robust,
                    )
                )
            if local:
                errors.extend(local)
                per_key.append(np.mean(local, axis=0))
        labels = ["ridge", "reference", "unchanged", "median"]
        out["eligible"][n] = dict(
            rows=len(errors),
            molecules=len(per_key),
            all_rows=len(rows),
            all_molecules=len(by_key),
            pair_weighted_mae=dict(zip(labels, np.mean(errors, axis=0))),
            molecule_weighted_mae=dict(zip(labels, np.mean(per_key, axis=0))),
        )
    a.output.write_text(json.dumps(out, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
