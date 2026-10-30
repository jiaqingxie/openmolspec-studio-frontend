"""Molecular identity and duplicate analysis for OpenSpec records."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd
from rdkit import Chem
from rdkit.Chem.inchi import MolToInchiKey
from rdkit.Chem.Scaffolds.MurckoScaffold import MurckoScaffoldSmiles
from tqdm import tqdm


def _value(record: pd.Series, *names: str) -> Optional[str]:
    for name in names:
        value = record.get(name)
        if value is not None and not pd.isna(value):
            text = str(value).strip()
            if text:
                return text
    return None


def molecule_identity(smiles: Optional[str]) -> Dict[str, Optional[str]]:
    """Return canonical SMILES, InChIKey and scaffold for one SMILES."""

    if not smiles:
        return {"canonical_smiles": None, "inchikey": None, "scaffold": None, "identity_error": "SMILES_MISSING"}
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return {"canonical_smiles": None, "inchikey": None, "scaffold": None, "identity_error": "SMILES_INVALID"}
    try:
        canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
        inchikey = MolToInchiKey(molecule)
        scaffold = MurckoScaffoldSmiles(mol=molecule, includeChirality=True) or "__ACYCLIC__"
        return {
            "canonical_smiles": canonical,
            "inchikey": inchikey or None,
            "scaffold": scaffold,
            "identity_error": None,
        }
    except Exception as exc:
        return {"canonical_smiles": None, "inchikey": None, "scaffold": None, "identity_error": type(exc).__name__}


def _identity_row(item):
    index, record = item
    sample_id = _value(record, "sample_id", "filename") or str(index)
    source_dataset = _value(record, "source_dataset")
    if source_dataset is None and "-" in sample_id:
        source_dataset = sample_id.split("-", 1)[0]
    source_id = _value(record, "source_id")
    if source_id is None and "-" in sample_id:
        source_id = sample_id.split("-", 1)[1]
    smiles = _value(record, "canonical_smiles", "smiles")
    identity = molecule_identity(smiles)
    return {
        "row_index": index,
        "sample_id": sample_id,
        "source_dataset": source_dataset,
        "source_id": source_id,
        "smiles": smiles,
        **identity,
    }


def build_identity_table(frame: pd.DataFrame, workers: int = 1) -> pd.DataFrame:
    tasks = frame.iterrows()
    if workers > 1 and len(frame) > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            rows = list(tqdm(
                executor.map(_identity_row, tasks),
                total=len(frame), desc="Molecular identity", unit="record",
            ))
    else:
        rows = [_identity_row(item) for item in tqdm(
            tasks, total=len(frame), desc="Molecular identity", unit="record"
        )]
    result = pd.DataFrame(rows)
    for field in ("canonical_smiles", "inchikey", "scaffold"):
        result[f"{field}_duplicate"] = result[field].notna() & result[field].duplicated(keep=False)
    result["exact_record_key"] = result.apply(
        lambda row: hashlib.sha256(
            json.dumps({"sample_id": row.sample_id, "smiles": row.smiles}, sort_keys=True).encode()
        ).hexdigest(), axis=1
    )
    result["exact_record_duplicate"] = result["exact_record_key"].duplicated(keep=False)
    return result


def analyze(frame: pd.DataFrame, workers: int = 1) -> Dict[str, Any]:
    identity = build_identity_table(frame, workers=workers)
    non_null = lambda field: int(identity[field].notna().sum())
    summary = {
        "records": int(len(identity)),
        "canonical_smiles_available": non_null("canonical_smiles"),
        "inchikey_available": non_null("inchikey"),
        "scaffold_available": non_null("scaffold"),
        "exact_record_duplicate_records": int(identity["exact_record_duplicate"].sum()),
        "canonical_smiles_duplicate_records": int(identity["canonical_smiles_duplicate"].sum()),
        "inchikey_duplicate_records": int(identity["inchikey_duplicate"].sum()),
        "scaffold_duplicate_records": int(identity["scaffold_duplicate"].sum()),
        "cross_source_canonical_overlap_records": int(
            identity.groupby("canonical_smiles")["source_dataset"].nunique().gt(1).sum()
        ) if "source_dataset" in identity else 0,
        "identity_errors": identity["identity_error"].dropna().value_counts().to_dict(),
        "identity_policy": {
            "stereoisomers": "isomeric canonical SMILES and InChIKey are retained",
            "tautomers": "not collapsed automatically",
            "salts_fragments": "not collapsed automatically",
            "charges_isotopes": "preserved by RDKit canonicalization where represented",
            "conformers": "same molecular identity, distinct records retained for analysis",
        },
    }
    return {"identity": identity, "summary": summary}


def run(dataset: str, output: str, workers: int = 1) -> Dict[str, Any]:
    path = Path(dataset)
    frame = pd.read_pickle(path) if path.suffix in (".pkl", ".pickle") else pd.read_parquet(path)
    result = analyze(frame, workers=workers)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    result["identity"].to_parquet(out / "dedup_report.parquet", index=False)
    with open(out / "dedup_summary.json", "w", encoding="utf-8") as handle:
        json.dump(result["summary"], handle, indent=2, ensure_ascii=False, default=str)
    return result["summary"]


def main():
    parser = argparse.ArgumentParser(description="Analyze OpenSpec molecular identity and duplicates")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(run(args.dataset, args.output, workers=args.workers), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
