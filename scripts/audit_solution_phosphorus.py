"""Stratify the 31P single-environment test by the phosphorus bonds encoded in each SMILES."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np
from rdkit import Chem

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from openmolspec.solution_shifts import analyte


def phosphorus_group(smiles):
    mol, _ = analyte(smiles, "31P")
    atom = next(a for a in mol.GetAtoms() if a.GetAtomicNum() == 15)
    partners = {
        b.GetOtherAtom(atom).GetSymbol()
        for b in atom.GetBonds()
        if b.GetBondType() == Chem.BondType.DOUBLE
    }
    if "O" in partners:
        return "P=O"
    if "S" in partners:
        return "P=S"
    if atom.GetFormalCharge() > 0:
        return "positive P"
    if atom.GetDegree() == 3 and atom.GetFormalCharge() == 0:
        if all(a.GetAtomicNum() == 6 for a in atom.GetNeighbors()):
            return "neutral P, three carbon neighbours"
        return "neutral P, three neighbours including a heteroatom"
    return "other P environments"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benchmark", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    run = next(
        r
        for r in json.loads(args.benchmark.read_text())["results"]
        if r["task"] == "nmr.forward.31P"
        and r["dataset_name"] == "experimental_solution_31P_test"
    )
    groups = defaultdict(lambda: defaultdict(list))
    for row in run["predictions"]:
        group = phosphorus_group(row["smiles"])
        groups[group][row["connectivity"]].append(
            abs(row["prediction_ppm"] - row["reference_ppm"])
        )
    counts = {}
    for group, identities in sorted(groups.items()):
        error = [v for series in identities.values() for v in series]
        counts[group] = dict(
            identities=len(identities),
            observations=len(error),
            mae_ppm=float(np.mean(error)),
            median_absolute_ppm=float(np.median(error)),
            molecule_macro_mae_ppm=float(
                np.mean([np.mean(v) for v in identities.values()])
            ),
        )
    args.output.write_text(
        json.dumps(
            {"reference_sha256": run["dataset"]["sha256"], "groups": counts}, indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
