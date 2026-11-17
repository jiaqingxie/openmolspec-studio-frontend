"""Generate deterministic dataset splits and molecule/scaffold leakage reports."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from openmolspec.quality.dedup import build_identity_table
from tqdm import tqdm


SPLIT_NAMES = ("train", "validation", "test")


def _stable_order(values: Iterable[str], seed: int) -> List[str]:
    return sorted(values, key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest())


def _partition_groups(groups: Dict[str, List[int]], seed: int, ratios: Dict[str, float]) -> Dict[str, List[int]]:
    ordered = _stable_order(groups, seed)
    total = sum(len(groups[key]) for key in ordered)
    targets = {name: ratios[name] * total for name in SPLIT_NAMES}
    output = {name: [] for name in SPLIT_NAMES}
    counts = {name: 0 for name in SPLIT_NAMES}
    for key in tqdm(ordered, desc="Assign split groups", unit="group", leave=False):
        destination = min(SPLIT_NAMES, key=lambda name: counts[name] / max(targets[name], 1.0))
        output[destination].extend(groups[key])
        counts[destination] += len(groups[key])
    return output


def _row_partition(frame: pd.DataFrame, seed: int, ratios: Dict[str, float]) -> Dict[str, List[int]]:
    indices = list(frame.index)
    ordered = sorted(indices, key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest())
    n = len(ordered)
    train_end = int(ratios["train"] * n)
    validation_end = train_end + int(ratios["validation"] * n)
    return {
        "train": ordered[:train_end],
        "validation": ordered[train_end:validation_end],
        "test": ordered[validation_end:],
    }


def _groups(identity: pd.DataFrame, field: str) -> Dict[str, List[int]]:
    groups: Dict[str, List[int]] = {}
    for row_index, value in tqdm(
        zip(identity["row_index"], identity[field]),
        total=len(identity),
        desc=f"Group by {field}",
        unit="record",
        leave=False,
    ):
        key = str(value) if pd.notna(value) else f"__missing__:{row_index}"
        groups.setdefault(key, []).append(row_index)
    return groups


def _source_groups(frame: pd.DataFrame) -> Dict[str, List[int]]:
    groups: Dict[str, List[int]] = {}
    for index, record in tqdm(
        frame.iterrows(), total=len(frame), desc="Group by source", unit="record", leave=False
    ):
        source = record.get("source_dataset")
        if source is None or pd.isna(source) or not str(source).strip():
            sample_id = record.get("sample_id", record.get("filename", ""))
            if sample_id is not None and not pd.isna(sample_id) and "-" in str(sample_id):
                source = str(sample_id).split("-", 1)[0]
            else:
                source = "__unknown_source__"
        groups.setdefault(str(source), []).append(index)
    return groups


def leakage_report(identity: pd.DataFrame, splits: Dict[str, List[int]]) -> Dict[str, pd.DataFrame]:
    """Summarize molecular-group overlap between dataset splits."""
    rows = []
    for field, label in (("canonical_smiles", "molecule"), ("inchikey", "inchikey"), ("scaffold", "scaffold")):
        values = {name: set(identity.loc[identity["row_index"].isin(indices), field].dropna()) for name, indices in splits.items()}
        for left_index, left in enumerate(SPLIT_NAMES):
            for right in SPLIT_NAMES[left_index + 1:]:
                rows.append({
                    "identity_type": label,
                    "left_split": left,
                    "right_split": right,
                    "overlap_count": len(values[left] & values[right]),
                })
    return pd.DataFrame(rows)


def generate(frame: pd.DataFrame, seed: int = 2025, ratios: Optional[Dict[str, float]] = None, workers: int = 1):
    """Assign molecular records to grouped training, validation and test splits."""
    ratios = ratios or {"train": 0.8, "validation": 0.1, "test": 0.1}
    if abs(sum(ratios.values()) - 1.0) > 1e-8:
        raise ValueError("Split ratios must sum to 1.0")
    identity = build_identity_table(frame, workers=workers)
    splits = {
        "random": _row_partition(frame, seed, ratios),
        "molecule": _partition_groups(_groups(identity, "inchikey"), seed, ratios),
        "scaffold": _partition_groups(_groups(identity, "scaffold"), seed, ratios),
        "source": _partition_groups(_source_groups(frame), seed, ratios),
    }
    leakage = {name: leakage_report(identity, split) for name, split in splits.items()}
    return identity, splits, leakage, ratios


def run(dataset: str, output: str, seed: int = 2025, train: float = 0.8, validation: float = 0.1, test: float = 0.1, workers: int = 1):
    """Run the datasets splits workflow with the supplied settings."""
    path = Path(dataset)
    frame = pd.read_pickle(path) if path.suffix in (".pkl", ".pickle") else pd.read_parquet(path)
    identity, splits, leakage, ratios = generate(
        frame, seed, {"train": train, "validation": validation, "test": test}, workers=workers
    )
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    summary = {"dataset": str(path), "seed": seed, "ratios": ratios, "splits": {}}
    for name, split in splits.items():
        payload = {
            "dataset": str(path), "dataset_version": "openspec-v1.0",
            "seed": seed, "algorithm": name, "ratios": ratios,
            "indices": {key: [int(value) for value in values] for key, values in split.items()},
            "counts": {key: len(values) for key, values in split.items()},
        }
        with open(out / f"{name}_split.json", "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        leakage[name].to_csv(out / f"{name}_leakage.csv", index=False)
        summary["splits"][name] = payload["counts"]
    identity.to_parquet(out / "split_identity.parquet", index=False)
    with open(out / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    return summary


def main():
    """Run the splits command-line workflow."""
    parser = argparse.ArgumentParser(description="Generate deterministic OpenSpec splits")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=2025)
    parser.add_argument("--train", type=float, default=0.8)
    parser.add_argument("--validation", type=float, default=0.1)
    parser.add_argument("--test", type=float, default=0.1)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(run(
        args.dataset, args.output, args.seed, args.train, args.validation, args.test, args.workers
    ), indent=2))


if __name__ == "__main__":
    main()
