"""Bounded real-data MAGMa annotation with verified engine-graph atom indices."""

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

from .data import sha256
from .ms import select_ms_records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parent = Path(__file__).resolve().parents[3]
    parser.add_argument("--source", type=Path, default=parent / "MassSpecGym-MAGMA-annotation")
    parser.add_argument("--input-csv", type=Path, default=parent / "MassSpecGym-MAGMA-annotation/data/MassSpecGym_test_full.csv")
    parser.add_argument("--metadata-tsv", type=Path, default=parent / "MassSpecGym-MAGMA-annotation/data/MassSpecGym1.5.tsv")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--max-heavy-atoms", type=int, default=20)
    parser.add_argument("--ppm", type=float, default=10.)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows, selection = select_ms_records(args.input_csv, args.metadata_tsv, args.limit, args.max_heavy_atoms)
    sys.path.insert(0, str(args.source))
    from fragments.magma.op.Magma4MassSpecGYm import process_csv_row

    check_path = args.source / "scripts/verify_index_alignment.py"
    spec = importlib.util.spec_from_file_location("openmolspec_magma_index_check", check_path)
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    report = {"task": "ms.annotation.magma", "training_performed": False, "algorithm": "MAGMa v8, original canonicalization",
              "dataset": {"path": str(args.input_csv), "sha256": sha256(args.input_csv)},
              "selection": selection, "ppm_tolerance": args.ppm,
              "source": {"path": str(args.source), "entry_sha256": sha256(args.source / "fragments/magma/op/Magma4MassSpecGYm.py")},
              "atom_index_basis": "engine_smiles", "interpretation": "algorithmic_candidate_annotations_not_experimentally_confirmed_mechanisms",
              "records": []}
    for row in rows:
        print(json.dumps({"event": "annotating", "spec_id": row["spec_id"]}), flush=True)
        native = {"spec_id": row["spec_id"], "smiles": row["smiles"], "prec_type": row["adduct"],
                  "peaks": repr([tuple(value) for value in row["reference_peaks"]])}
        result = process_csv_row(native, ppm_threshold=args.ppm, build_annotation=True,
                                 skip_canonicalization=False, output_file="in_memory_annotation")
        annotation_json = result.pop("annotation_json", None)
        result = {key: (value.item() if hasattr(value, "item") else value) for key, value in result.items()}
        if result.get("success") and annotation_json:
            annotation = json.loads(annotation_json)
            checked, bad_atoms, bad_bonds = check.check_sample(annotation, "engine_smiles")
            result.update(status="passed" if bad_atoms == bad_bonds == 0 else "failed",
                          engine_smiles=annotation["engine_smiles"], checked_fragments=checked,
                          invalid_atom_mappings=bad_atoms, invalid_bond_mappings=bad_bonds)
        else:
            result["status"] = "failed"
        report["records"].append(result)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    successful = [row for row in report["records"] if row["status"] == "passed"]
    report["counts"] = dict(Counter(row["status"] for row in report["records"]))
    total = sum(row["n_peaks"] for row in successful)
    report["metrics"] = {"matched_peak_fraction": sum(row["n_matched"] for row in successful) / max(total, 1),
                          "annotated_spectra": len(successful), "checked_fragments": sum(row["checked_fragments"] for row in successful)}
    report["completed"] = True
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"counts": report["counts"], "metrics": report["metrics"]}), flush=True)
    return int(bool(report["counts"].get("failed")))


if __name__ == "__main__":
    sys.exit(main())
