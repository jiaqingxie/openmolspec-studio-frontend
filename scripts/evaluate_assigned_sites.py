"""Measure assignment of observed peaks to experimental atom labels on the complete held-out split."""

import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path

from openmolspec.assigned_shifts import AssignedShiftPredictor
from openmolspec.solution_shifts import solvent_id
from openmolspec_bench.assignment_truth import score
from openmolspec_bench.data import sha256


SOLVENT_LABELS = (
    "unknown",
    "CDCl3",
    "DMSO-d6",
    "D2O",
    "CD3OD",
    "C6D6",
    "acetone-d6",
    "CD3CN",
    "THF-d8",
    "CD2Cl2",
    "toluene-d8",
    "other",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "root", "training_reports", "output"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    assert list(map(solvent_id, SOLVENT_LABELS)) == list(range(12))
    digest = sha256(args.dataset)
    groups = defaultdict(set)
    test = defaultdict(list)
    with gzip.open(args.dataset, "rt") as stream:
        for row in map(json.loads, stream):
            groups[row[1]].add(row[0])
            if row[1] == "test":
                test[row[3]].append(row)
    if (
        groups["test"] & (groups["train"] | groups["val"])
        or groups["train"] & groups["val"]
    ):
        raise ValueError("Connectivity overlap between splits")
    result = dict(
        dataset_sha256=digest,
        scoring="All annotated peaks including unmatched; chirality-aware equivalent heavy sites; 0.5 ppm H and 5 ppm C; fixed Hungarian assignment.",
        split="all test connectivities disjoint from training and validation",
        nuclei={},
    )
    for nucleus, symbol in [("1H", "H"), ("13C", "C")]:
        root = args.root / (nucleus + "-assigned")
        model = AssignedShiftPredictor(root)
        report = json.loads(
            (
                args.training_reports / ("forward_selection_" + nucleus + ".json")
            ).read_text()
        )
        if (
            report["source"]["output_sha256"] != digest
            or report["config"]["tree_sha256"] != model.config["tree_sha256"]
            or report["config"]["lookup_sha256"] != model.config["lookup_sha256"]
        ):
            raise ValueError("Checkpoint or data differs from the training report")
        records = []
        for row in test[nucleus]:
            try:
                values = model.assignment_predictions(row[2], SOLVENT_LABELS[row[4]])
            except ValueError as e:
                if str(e) != "A hydrogen lacks a supported attached heavy-atom site":
                    raise
                values = None
            records.append(score(row, values, symbol))
        peaks, assigned, correct = (
            sum(r[k] for r in records) for k in ("peaks", "assigned", "correct")
        )
        result["nuclei"][nucleus] = dict(
            connectivities=len({r["connectivity"] for r in records}),
            spectra=len(records),
            peaks=peaks,
            assigned=assigned,
            correct=correct,
            accuracy=correct / peaks,
            coverage=assigned / peaks,
            failures=sum(not r["inference_available"] for r in records),
            weights=model.config,
            records=records,
        )
        dest = args.output.with_suffix(".tmp")
        dest.write_text(json.dumps(result, allow_nan=False) + "\n")
        dest.replace(args.output)
        print(nucleus, correct, peaks, flush=True)


if __name__ == "__main__":
    main()
