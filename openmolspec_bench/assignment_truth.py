"""Evaluate the deployed 1D assignment against experimental atom-index labels."""

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import shutil

from rdkit import Chem
from .assignment import assign_peaks, predict_atoms
from .data import sha256


def score(row, predictions, symbol):
    key, _, smiles, _, solvent, sites = row
    mol = Chem.MolFromSmiles(smiles)
    ranks = Chem.CanonicalRankAtoms(mol, breakTies=False, includeChirality=True)
    observed = defaultdict(set)
    for atom, shifts in sites:
        for ppm in shifts:
            observed[ppm].add(ranks[atom])
    peaks = sorted(observed)
    matched = correct = 0
    if predictions is not None:
        result = assign_peaks(
            smiles, symbol, predictions, peaks, 0.5 if symbol == "H" else 5
        )
        explicit = Chem.AddHs(mol)
        matched = len(result["assignments"])
        for hit in result["assignments"]:
            indices = hit["atom_indices"]
            if symbol == "H":
                indices = [
                    explicit.GetAtomWithIdx(i).GetNeighbors()[0].GetIdx()
                    for i in indices
                ]
            allowed = observed[peaks[hit["peak_index"]]]
            correct += any(ranks[i] in allowed for i in indices)
    return dict(
        connectivity=key,
        smiles=smiles,
        solvent_id=solvent,
        peaks=len(peaks),
        assigned=matched,
        correct=correct,
        inference_available=predictions is not None,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--limit",
        type=int,
        default=256,
        help="Distinct test connectivities per nucleus",
    )
    parser.add_argument("--exclude-connectivities", type=Path,
                        help="JSON list of excluded test connectivity keys")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.dataset, "rt") as stream:
        rows = [r for r in map(json.loads, stream) if r[1] == "test"]
    exclusions = set(json.loads(args.exclude_connectivities.read_text())) if args.exclude_connectivities else set()
    rows = [r for r in rows if r[0] not in exclusions]
    report = dict(
        dataset_sha256=sha256(args.dataset),
        split="test",
        model="NMRNet liquid fold 0",
        selection="first N SHA256(assignment-v1 + connectivity) per nucleus",
        scoring="Unique measured ppm; any labelled symmetry-equivalent heavy site. H uses the attached heavy atom. Unmatched peaks and geometry failures count as incorrect.",
        upstream_checkpoint_training_overlap="unknown",
        exclusion_list_sha256=sha256(args.exclude_connectivities) if args.exclude_connectivities else None,
        nuclei={},
    )
    for symbol, nucleus in [("H", "1H"), ("C", "13C")]:
        selected = [r for r in rows if r[3] == nucleus]
        keys = sorted(
            {r[0] for r in selected},
            key=lambda k: hashlib.sha256(("assignment-v1" + k).encode()).digest(),
        )[: args.limit]
        keep = set(keys)
        selected = [r for r in selected if r[0] in keep]
        smiles = sorted({r[2] for r in selected})
        predictions = {}

        def infer(batch):
            digest = hashlib.sha256(json.dumps(batch).encode()).hexdigest()
            cache = args.cache / f"{symbol}-{digest}.json"
            if cache.exists():
                predictions.update(json.loads(cache.read_text()))
                return
            try:
                with tempfile.TemporaryDirectory(dir=args.cache) as tmp:
                    try:
                        values, _ = predict_atoms(
                            batch, symbol, args.models_root, Path(tmp) / "run"
                        )
                    except RuntimeError:
                        log = Path(tmp) / "run" / "inference.log"
                        if log.is_file():
                            shutil.copyfile(log, args.cache / (digest + ".error.log"))
                        raise
                    found = {
                        s: list(map(float, values[i])) for i, s in enumerate(batch)
                    }
            except ValueError as exc:
                if not str(exc).startswith(
                    ("Unsupported atom", "3D conformer generation failed")
                ):
                    raise
                if len(batch) > 1:
                    middle = len(batch) // 2
                    infer(batch[:middle])
                    infer(batch[middle:])
                    return
                found = {batch[0]: None}
            temp = cache.with_suffix(".tmp")
            temp.write_text(json.dumps(found, allow_nan=False))
            temp.replace(cache)
            predictions.update(found)

        for start in range(0, len(smiles), 48):
            infer(smiles[start : start + 48])
            print(nucleus, len(predictions), "of", len(smiles), flush=True)
        records = [score(r, predictions[r[2]], symbol) for r in selected]
        n, m, c = (
            sum(r[field] for r in records) for field in ("peaks", "assigned", "correct")
        )
        by_key = defaultdict(lambda: [0, 0])
        for r in records:
            by_key[r["connectivity"]][0] += r["correct"]
            by_key[r["connectivity"]][1] += r["peaks"]
        report["nuclei"][nucleus] = dict(
            connectivities=len(keys),
            spectra=len(records),
            peaks=n,
            assigned=m,
            correct=c,
            accuracy=c / n if n else None,
            coverage=m / n if n else None,
            precision_among_assigned=c / m if m else None,
            molecule_macro_accuracy=sum(cor / tot for cor, tot in by_key.values())
            / len(by_key) if by_key else None,
            inference_failures=sum(not r["inference_available"] for r in records),
            records=records,
        )
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
