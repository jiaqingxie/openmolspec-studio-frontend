"""Input loading shared by native staged extraction pipelines."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


def load_tasks(
    *,
    path_field: str,
    manifest_path: Optional[str] = None,
    file_dict: Optional[str] = None,
    smiles_dict: Optional[str] = None,
) -> Tuple[List[Tuple[str, str]], Dict[str, str]]:
    """Load extraction tasks from Parquet, falling back to legacy JSON maps."""

    if manifest_path:
        frame = pd.read_parquet(
            manifest_path,
            columns=["sample_id", "smiles", path_field],
        )
        selected = frame[frame[path_field].notna()]
        tasks = list(
            selected[["sample_id", path_field]]
            .astype(str)
            .itertuples(index=False, name=None)
        )
        # Worker processes only need identities for records in this modality.
        # Avoid materializing the full manifest-wide SMILES dictionary.
        labeled = selected[selected["smiles"].notna()]
        smiles = dict(
            zip(labeled["sample_id"].astype(str), labeled["smiles"].astype(str))
        )
        return tasks, smiles

    if not file_dict or not smiles_dict:
        raise ValueError(
            "manifest_path or both file_dict and smiles_dict must be provided"
        )
    with Path(file_dict).open(encoding="utf-8") as handle:
        files = json.load(handle)
    with Path(smiles_dict).open(encoding="utf-8") as handle:
        smiles = json.load(handle)
    return list(files.items()), smiles
