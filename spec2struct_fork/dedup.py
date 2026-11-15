"""Build a molecule-unique training view from verified H/C-NMR examples."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path


SPLITS = ("train", "val", "test")


def record_score(records: list[dict]) -> tuple[int, int, int]:
    """Prefer records with numeric shifts, then more source text."""
    return (sum(bool(re.search(r"\d", str(record["chemical_shift"]))) for record in records),
            min(sum(len(str(record["chemical_shift"])) for record in records), 8192),
            len(records))


def provenance(item: dict) -> dict:
    return {key: item.get(key) for key in ("patent_id", "year", "source")}


def reduce_group(rows: list[dict]) -> dict:
    """Select the strongest H and C evidence for one canonical molecule."""
    if not rows:
        raise ValueError("Cannot reduce an empty molecule group")
    first = rows[0]
    best_h = max((item for item in rows if item["h_nmr"]),
                 key=lambda item: record_score(item["h_nmr"]), default=None)
    best_c = max((item for item in rows if item["c_nmr"]),
                 key=lambda item: record_score(item["c_nmr"]), default=None)
    h_records = best_h["h_nmr"] if best_h else []
    c_records = best_c["c_nmr"] if best_c else []
    return {
        "smiles": first["smiles"], "formula": first["formula"],
        "h_nmr": h_records, "c_nmr": c_records,
        "modality_mask": [int(bool(h_records)), int(bool(c_records))],
        "scaffold": first["scaffold"],
        "patent_id": first.get("patent_id"), "year": first.get("year"),
        "source": first.get("source"), "source_rows": len(rows),
        "h_provenance": provenance(best_h) if best_h else None,
        "c_provenance": provenance(best_c) if best_c else None,
    }


def _write_group(rows: list[dict], target, counts: Counter, split: str) -> None:
    result = reduce_group(rows)
    target.write(json.dumps(result, ensure_ascii=False) + "\n")
    counts["examples"] += 1
    counts[split] += 1
    counts["source_rows"] += len(rows)
    counts["duplicate_rows"] += len(rows) - 1
    counts["molecules_with_duplicates"] += int(len(rows) > 1)
    counts["h_records"] += len(result["h_nmr"])
    counts["c_records"] += len(result["c_nmr"])
    mask = result["modality_mask"]
    category = "h_and_c" if mask == [1, 1] else "h_only" if mask[0] else "c_only"
    counts[category] += 1
    if (result["h_provenance"] and result["c_provenance"]
            and result["h_provenance"] != result["c_provenance"]):
        counts["modalities_from_different_sources"] += 1


def deduplicate(source_dir: Path, output_dir: Path, sort_memory: str = "1G") -> dict:
    summary = json.loads((source_dir / "summary.json").read_text(encoding="utf-8"))
    verification = json.loads((source_dir / "verification.json").read_text(encoding="utf-8"))
    if summary.get("format_version") != 2 or verification.get("status") != "passed":
        raise ValueError("Source must be a verified H/C-NMR format-2 dataset")
    if verification.get("counts", {}).get("examples") != summary["counts"]["examples"]:
        raise ValueError("Source verification count differs from summary")
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    work = output_dir / ".sort_tmp"
    work.mkdir()
    counts: Counter = Counter()
    for split in SPLITS:
        source = source_dir / f"{split}.jsonl"
        keyed = work / f"{split}.keyed"
        ordered = work / f"{split}.ordered"
        with source.open("r", encoding="utf-8") as stream, keyed.open("w", encoding="utf-8") as target:
            for number, line in enumerate(stream, 1):
                item = json.loads(line)
                target.write(item["smiles"] + "\t" + line)
                if number % 1000000 == 0:
                    print(json.dumps({"stage": "key", "split": split, "rows": number}), flush=True)
        with ordered.open("wb") as target:
            subprocess.run(
                ["sort", "-t", "\t", "-k1,1", "-S", sort_memory,
                 "--parallel=2", "-T", str(work), str(keyed)],
                stdout=target, check=True,
                env={**os.environ, "LC_ALL": "C"})
        keyed.unlink()
        current = None
        group: list[dict] = []
        partial = output_dir / f"{split}.jsonl.partial"
        with ordered.open("r", encoding="utf-8") as stream, partial.open("x", encoding="utf-8") as target:
            for number, line in enumerate(stream, 1):
                smiles, payload = line.split("\t", 1)
                item = json.loads(payload)
                if item["smiles"] != smiles:
                    raise ValueError(f"Sort key differs from molecule in {split}:{number}")
                if current is not None and smiles != current:
                    _write_group(group, target, counts, split)
                    group = []
                current = smiles
                group.append(item)
                if number % 1000000 == 0:
                    print(json.dumps({"stage": "merge", "split": split,
                                      "rows": number, "unique": counts[split]}), flush=True)
            if group:
                _write_group(group, target, counts, split)
        ordered.unlink()
        partial.replace(output_dir / f"{split}.jsonl")
        print(json.dumps({"stage": "done", "split": split,
                          "unique": counts[split]}), flush=True)
    work.rmdir()
    if counts["source_rows"] != summary["counts"]["examples"]:
        raise ValueError("Deduplication did not consume every source row")
    result = {
        "format_version": 2, "source": str(source_dir.resolve()),
        "seed": summary["seed"], "split_method": summary["split_method"],
        "deduplicated_by": "canonical_smiles",
        "selection": "Best numeric-shift H row and C row per molecule; full measurements remain in source",
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
    print(json.dumps(deduplicate(args.source_dir, args.output_dir, args.sort_memory), indent=2))


if __name__ == "__main__":
    main()
