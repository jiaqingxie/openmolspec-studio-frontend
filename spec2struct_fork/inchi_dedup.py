"""Merge molecule-unique H/C-NMR examples by standard InChI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from .data import assigned_split
from .dedup import SPLITS, provenance, record_score


def standard_inchi(smiles: str, chem) -> str | None:
    mol = chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        value = chem.MolToInchi(mol)
    except Exception:
        return None
    return value if value.startswith("InChI=1S/") and "\t" not in value else None


def merge_inchi_group(inchi: str, rows: list[dict], seed: int) -> tuple[str, dict]:
    """Choose one target SMILES and the strongest H/C rows for an InChI."""
    base = min(rows, key=lambda item: item["smiles"])
    if any(item["formula"] != base["formula"] for item in rows):
        raise ValueError(f"Formula disagreement for {inchi}")
    best_h = max((item for item in rows if item["h_nmr"]),
                 key=lambda item: record_score(item["h_nmr"]), default=None)
    best_c = max((item for item in rows if item["c_nmr"]),
                 key=lambda item: record_score(item["c_nmr"]), default=None)
    h_records = best_h["h_nmr"] if best_h else []
    c_records = best_c["c_nmr"] if best_c else []
    result = {
        "inchi": inchi, "smiles": base["smiles"], "formula": base["formula"],
        "h_nmr": h_records, "c_nmr": c_records,
        "modality_mask": [int(bool(h_records)), int(bool(c_records))],
        "scaffold": base["scaffold"],
        "patent_id": base.get("patent_id"), "year": base.get("year"),
        "source": base.get("source"),
        "source_rows": sum(item["source_rows"] for item in rows),
        "smiles_variants": len(rows),
        "h_smiles": best_h["smiles"] if best_h else None,
        "c_smiles": best_c["smiles"] if best_c else None,
        "h_provenance": best_h.get("h_provenance") or provenance(best_h) if best_h else None,
        "c_provenance": best_c.get("c_provenance") or provenance(best_c) if best_c else None,
    }
    return assigned_split(result["scaffold"], seed), result


def _write_group(inchi: str, rows: list[dict], targets: dict, counts: Counter,
                 seed: int) -> None:
    split, item = merge_inchi_group(inchi, rows, seed)
    targets[split].write(json.dumps(item, ensure_ascii=False) + "\n")
    counts["examples"] += 1
    counts[split] += 1
    counts["source_rows"] += item["source_rows"]
    counts["smiles_rows"] += item["smiles_variants"]
    counts["inchi_duplicate_smiles_rows"] += item["smiles_variants"] - 1
    counts["inchi_with_multiple_smiles"] += int(item["smiles_variants"] > 1)
    counts["h_records"] += len(item["h_nmr"])
    counts["c_records"] += len(item["c_nmr"])
    mask = item["modality_mask"]
    category = "h_and_c" if mask == [1, 1] else "h_only" if mask[0] else "c_only"
    counts[category] += 1


def deduplicate_inchi(source_dir: Path, output_dir: Path,
                      sort_memory: str = "1G") -> dict:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.error")
    RDLogger.DisableLog("rdApp.warning")
    summary = json.loads((source_dir / "summary.json").read_text(encoding="utf-8"))
    verification = json.loads((source_dir / "verification.json").read_text(encoding="utf-8"))
    if (summary.get("deduplicated_by") != "canonical_smiles"
            or verification.get("status") != "passed"):
        raise ValueError("Input must be the verified canonical-SMILES unique view")
    if verification.get("counts", {}).get("examples") != summary["counts"]["examples"]:
        raise ValueError("Input verification count differs from summary")
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    work = output_dir / ".sort_tmp"
    work.mkdir()
    keyed = work / "inchi.keyed"
    ordered = work / "inchi.ordered"
    rejected = output_dir / "inchi_failures.jsonl"
    counts: Counter = Counter()
    with keyed.open("w", encoding="utf-8") as target, rejected.open("x", encoding="utf-8") as errors:
        for split in SPLITS:
            with (source_dir / f"{split}.jsonl").open("r", encoding="utf-8") as stream:
                for line in stream:
                    item = json.loads(line)
                    counts["input_smiles_rows"] += 1
                    inchi = standard_inchi(item["smiles"], Chem)
                    if inchi is None:
                        counts["inchi_failures"] += 1
                        counts["failed_source_rows"] += item["source_rows"]
                        errors.write(line)
                    else:
                        target.write(inchi + "\t" + line)
                    if counts["input_smiles_rows"] % 100000 == 0:
                        print(json.dumps({"stage": "inchi", "rows": counts["input_smiles_rows"],
                                          "failures": counts["inchi_failures"]}), flush=True)
    with ordered.open("wb") as target:
        subprocess.run(
            ["sort", "-t", "\t", "-k1,1", "-S", sort_memory,
             "--parallel=2", "-T", str(work), str(keyed)],
            stdout=target, check=True, env={**os.environ, "LC_ALL": "C"})
    keyed.unlink()
    partial = {split: output_dir / f"{split}.jsonl.partial" for split in SPLITS}
    targets = {split: path.open("x", encoding="utf-8") for split, path in partial.items()}
    try:
        current = None
        group: list[dict] = []
        with ordered.open("r", encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                inchi, payload = line.split("\t", 1)
                if current is not None and inchi != current:
                    _write_group(current, group, targets, counts, summary["seed"])
                    group = []
                current = inchi
                group.append(json.loads(payload))
                if number % 100000 == 0:
                    print(json.dumps({"stage": "merge", "rows": number,
                                      "unique_inchi": counts["examples"]}), flush=True)
            if group:
                _write_group(current, group, targets, counts, summary["seed"])
    finally:
        for target in targets.values():
            target.close()
    ordered.unlink()
    work.rmdir()
    if counts["input_smiles_rows"] != summary["counts"]["examples"]:
        raise ValueError("Not every input SMILES row was processed")
    if counts["source_rows"] + counts["failed_source_rows"] != summary["counts"]["source_rows"]:
        raise ValueError("Original source-row count was not reconciled")
    for split in SPLITS:
        partial[split].replace(output_dir / f"{split}.jsonl")
    result = {
        "format_version": 2, "source": str(source_dir.resolve()),
        "seed": summary["seed"],
        "split_method": "SHA256(seed:representative Murcko scaffold), 80/10/10; one InChI per split",
        "deduplicated_by": "standard_inchi",
        "selection": "Lexicographically smallest source SMILES target; strongest H and C rows per InChI",
        "counts": dict(counts),
    }
    (output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sort-memory", default="1G")
    args = parser.parse_args()
    print(json.dumps(deduplicate_inchi(args.source_dir, args.output_dir,
                                       args.sort_memory), indent=2))


if __name__ == "__main__":
    main()
