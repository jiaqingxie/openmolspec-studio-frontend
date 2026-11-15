"""Audit prepared H/C-NMR splits and record reproducible file digests."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
import sys
from collections import Counter
from pathlib import Path

from .data import assigned_split


def verify(data_dir: Path, formula_check_every: int = 10000) -> dict:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdMolDescriptors

    RDLogger.DisableLog("rdApp.error")
    summary = json.loads((data_dir / "summary.json").read_text(encoding="utf-8"))
    if summary.get("format_version") != 2:
        raise ValueError("Expected H/C dataset format 2")
    counts = Counter()
    h_types, c_types, sources, years = Counter(), Counter(), Counter(), Counter()
    files = {}
    identity = summary.get("deduplicated_by")
    for split in ("train", "val", "test"):
        path = data_dir / f"{split}.jsonl"
        digest = hashlib.sha256()
        rows = 0
        previous_smiles = None
        previous_inchi = None
        with path.open("rb") as stream:
            for line_number, line in enumerate(stream, 1):
                digest.update(line)
                try:
                    item = json.loads(line)
                    h, c = item["h_nmr"], item["c_nmr"]
                    mask = [int(bool(h)), int(bool(c))]
                    if item["modality_mask"] != mask or not any(mask):
                        raise ValueError("modality mask disagrees with NMR records")
                    if assigned_split(item["scaffold"], summary["seed"]) != split:
                        raise ValueError("scaffold is in the wrong split")
                    if not item["smiles"] or not item["formula"]:
                        raise ValueError("missing SMILES or molecular formula")
                    if summary.get("deduplicated_by") == "canonical_smiles":
                        if previous_smiles is not None and item["smiles"] <= previous_smiles:
                            raise ValueError("deduplicated SMILES are not strictly increasing")
                        previous_smiles = item["smiles"]
                        if not isinstance(item.get("source_rows"), int) or item["source_rows"] < 1:
                            raise ValueError("missing positive source-row count")
                    if identity == "standard_inchi":
                        inchi = item.get("inchi")
                        if not isinstance(inchi, str) or not inchi.startswith("InChI=1S/"):
                            raise ValueError("missing standard InChI")
                        if previous_inchi is not None and inchi <= previous_inchi:
                            raise ValueError("InChI keys are not strictly increasing")
                        previous_inchi = inchi
                        if not isinstance(item.get("source_rows"), int) or item["source_rows"] < 1:
                            raise ValueError("missing positive source-row count")
                        if not isinstance(item.get("smiles_variants"), int) or item["smiles_variants"] < 1:
                            raise ValueError("missing positive SMILES-variant count")
                    for record in h + c:
                        if not record.get("type") or not record.get("chemical_shift"):
                            raise ValueError("empty NMR type or chemical shift")
                    for record in h:
                        h_types[record["type"]] += 1
                        if not re.search(r"\d", record["chemical_shift"]):
                            counts["h_records_without_digits"] += 1
                    for record in c:
                        c_types[record["type"]] += 1
                        if not re.search(r"\d", record["chemical_shift"]):
                            counts["c_records_without_digits"] += 1
                    sources[str(item.get("source") or "unknown")] += 1
                    years[str(item.get("year") or "unknown")] += 1
                    if formula_check_every and counts["examples"] % formula_check_every == 0:
                        molecule = Chem.MolFromSmiles(item["smiles"])
                        if molecule is None or rdMolDescriptors.CalcMolFormula(molecule) != item["formula"]:
                            raise ValueError("SMILES and molecular formula disagree")
                        if identity == "standard_inchi" and Chem.MolToInchi(molecule) != item["inchi"]:
                            raise ValueError("SMILES and InChI disagree")
                        counts["formula_spot_checks"] += 1
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"Invalid record in {path}:{line_number}: {exc}") from exc
                rows += 1
                counts["examples"] += 1
                counts[split] += 1
                counts["h_records"] += len(h)
                counts["c_records"] += len(c)
                if summary.get("deduplicated_by") == "canonical_smiles":
                    counts["source_rows"] += item["source_rows"]
                    counts["duplicate_rows"] += item["source_rows"] - 1
                    counts["molecules_with_duplicates"] += int(item["source_rows"] > 1)
                if identity == "standard_inchi":
                    counts["source_rows"] += item["source_rows"]
                    counts["smiles_rows"] += item["smiles_variants"]
                    counts["inchi_duplicate_smiles_rows"] += item["smiles_variants"] - 1
                    counts["inchi_with_multiple_smiles"] += int(item["smiles_variants"] > 1)
                category = "h_and_c" if mask == [1, 1] else "h_only" if mask[0] else "c_only"
                counts[category] += 1
                if counts["examples"] % 1000000 == 0:
                    print(f"Audited {counts['examples']:,} records", file=sys.stderr, flush=True)
        files[split] = {"rows": rows, "bytes": path.stat().st_size,
                        "sha256": digest.hexdigest()}
    for key in ("examples", "train", "val", "test", "h_only", "c_only",
                "h_and_c", "h_records", "c_records"):
        if counts[key] != summary["counts"].get(key, 0):
            raise ValueError(f"{key}: audited {counts[key]}, summary {summary['counts'].get(key, 0)}")
    if summary.get("deduplicated_by") == "canonical_smiles":
        for key in ("source_rows", "duplicate_rows", "molecules_with_duplicates"):
            if counts[key] != summary["counts"].get(key, 0):
                raise ValueError(f"{key}: audited {counts[key]}, summary {summary['counts'].get(key, 0)}")
    if identity == "standard_inchi":
        for key in ("source_rows", "smiles_rows", "inchi_duplicate_smiles_rows",
                    "inchi_with_multiple_smiles"):
            if counts[key] != summary["counts"].get(key, 0):
                raise ValueError(f"{key}: audited {counts[key]}, summary {summary['counts'].get(key, 0)}")
        failures = data_dir / "inchi_failures.jsonl"
        failed_rows = failed_sources = 0
        with failures.open("r", encoding="utf-8") as stream:
            for line in stream:
                failed_rows += 1
                failed_sources += json.loads(line)["source_rows"]
        if failed_rows != summary["counts"].get("inchi_failures", 0):
            raise ValueError("InChI failure row count disagrees with summary")
        if failed_sources != summary["counts"].get("failed_source_rows", 0):
            raise ValueError("InChI failure source count disagrees with summary")
        if counts["smiles_rows"] + failed_rows != summary["counts"]["input_smiles_rows"]:
            raise ValueError("Input SMILES rows were not reconciled")
        streams = [(data_dir / f"{split}.jsonl").open("r", encoding="utf-8")
                   for split in ("train", "val", "test")]
        try:
            previous = None
            for key in heapq.merge(*(
                (json.loads(line)["inchi"] for line in stream) for stream in streams)):
                if previous is not None and key <= previous:
                    raise ValueError("InChI appears in multiple splits")
                previous = key
        finally:
            for stream in streams:
                stream.close()
    result = {"format_version": 2, "status": "passed", "counts": dict(counts),
              "distributions": {
                  "h_type_top20": h_types.most_common(20),
                  "c_type_top20": c_types.most_common(20),
                  "sources": dict(sources.most_common()),
                  "years": dict(sorted(years.items())),
              }, "files": files}
    (data_dir / "verification.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--formula-check-every", type=int, default=10000,
                        help="Spot-check one SMILES/formula pair per N records; 0 disables")
    args = parser.parse_args()
    if args.formula_check_every < 0:
        parser.error("--formula-check-every cannot be negative")
    print(json.dumps(verify(args.data_dir, args.formula_check_every), indent=2))


if __name__ == "__main__":
    main()
