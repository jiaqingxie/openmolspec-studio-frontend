"""Build reproducible OpenSpec sample manifests and legacy JSON maps.

The script combines frequency/property and NMR Gaussian-log collections into a
single manifest. It preserves source IDs, uses one global ID convention, checks
SMILES consistency between modalities, and writes an audit report instead of
silently dropping unmatched records.

Typical layout expected by the default configuration::

    <freq-root>/<dataset>/<dataset>_log/*.log
    <freq-root>/<dataset>/<dataset>_label.json
    <nmr-root>/<dataset>_nmr/<dataset>_nmr_log/*.log
    <nmr-root>/<dataset>_nmr/<dataset>_label.json

The path discovery also tries nearby label-file alternatives to support the
layouts used by the original script and ``notebooks/hash.ipynb``.
"""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from rdkit import Chem, RDLogger
from rdkit.Chem.inchi import MolToInchiKey
from rdkit.Chem.Scaffolds.MurckoScaffold import MurckoScaffoldSmiles

# Keep direct script execution importable without installing the package.
# importable without requiring the repository to be installed as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from openmolspec.core.progress import status, track


DEFAULT_DATASETS = (
    "nist_ir",
    "pah",
    "pcqm4mv2",
    "qm9",
    "rxn",
    "sdbs",
    "wiley_ir",
    "wiley_raman",
    "peptide",
    "zinc_v1",
    "zinc_v2",
)
DEFAULT_NMR_DATASETS = DEFAULT_DATASETS
MANIFEST_CACHE_VERSION = "2"
IDENTITY_FIELDS = ("smiles", "canonical_smiles", "inchikey", "scaffold")
PUBLIC_ROW_FIELDS = (
    "sample_id",
    "source_dataset",
    "source_id",
    "smiles",
    "canonical_smiles",
    "inchikey",
    "scaffold",
    "log_path",
    "source_file_hash",
    "frequency_file_hash",
    "nmr_file_hash",
    "label_path",
    "label_status",
    "label_errors",
    "available_modalities",
    "frequency_log_path",
    "nmr_log_path",
)
AUDIT_FIELDS = (
    "sample_id",
    "source_dataset",
    "source_id",
    "modality",
    "status",
    "error_type",
    "log_path",
    "label_path",
)

# Prefix every source, including QM9/ZINC, to prevent cross-source collisions.
SOURCE_PREFIXES = {
    "nist_ir": "NISTIR",
    "pah": "PAH",
    "pcqm4mv2": "PCQM4MV2",
    "qm9": "QM9",
    "rxn": "RXN",
    "sdbs": "SDBS",
    "wiley_ir": "WILEYIR",
    "wiley_raman": "WILEYRAMAN",
    "peptide": "PEPTIDE",
    "zinc_v1": "ZINCV1",
    "zinc_v2": "ZINCV2",
}

# These collections remain useful for spectra/properties/trajectories even
# when a molecular-identity label is absent. SDBS labels are available
# separately as InChI; peptide identity is encoded by the source filename.
ALLOW_MISSING_LABEL_DATASETS = {"sdbs", "peptide"}
STANDARD_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
MODIFIED_AMINO_ACIDS = {
    "pS": ("S", "OG", "P"),
    "pT": ("T", "OG1", "P"),
    "pY": ("Y", "OH", "P"),
    "pH1": ("H", "ND1", "P"),
    "pH2": ("H", "NE2", "P"),
    "sS": ("S", "OG", "S"),
    "sT": ("T", "OG1", "S"),
    "sY": ("Y", "OH", "S"),
}


def configure_rdkit_logging(show_warnings: bool = False) -> None:
    """Keep RDKit diagnostics from corrupting progress output.

    Invalid labels and canonicalization failures are retained in the manifest
    audit table.  The high-volume RDKit warning stream is therefore hidden by
    default, while errors remain visible.  Set ``show_warnings`` when
    investigating a particular label.
    """

    if show_warnings:
        RDLogger.EnableLog("rdApp.warning")
    else:
        RDLogger.DisableLog("rdApp.warning")


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> Optional[str]:
    """Return a file hash, or ``None`` when the file cannot be read."""

    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(block_size), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


def _label_signature(path: Optional[Path]) -> Optional[str]:
    """Return a cheap cache invalidation signature for one label file."""

    if path is None:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return f"{path}:{stat.st_size}:{stat.st_mtime_ns}"


def _bounded_thread_map(function, items, workers: int, pending_factor: int = 4):
    """Yield unordered thread results without submitting every item at once."""

    iterator = iter(items)
    max_pending = max(workers, workers * pending_factor)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = set()
        for _ in range(max_pending):
            try:
                pending.add(executor.submit(function, next(iterator)))
            except StopIteration:
                break
        while pending:
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                yield future.result()
                try:
                    pending.add(executor.submit(function, next(iterator)))
                except StopIteration:
                    pass


def _clean_cached_value(value):
    """Convert pandas/Arrow cache values back to plain Python values."""

    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        converted = value.tolist()
        if isinstance(converted, list):
            return converted
    if value is None or isinstance(value, (str, bytes, bool, int, float, list, dict)):
        if isinstance(value, float) and pd.isna(value):
            return None
        return value
    try:
        return None if pd.isna(value) else value
    except (TypeError, ValueError):
        return value


def _clean_cached_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        field: _clean_cached_value(row.get(field))
        for field in PUBLIC_ROW_FIELDS
    }


def _write_cache(
    cache_path: Path,
    rows: List[Dict[str, Any]],
    file_metadata: Dict[str, Tuple[int, int]],
    *,
    label_signature: Optional[str],
) -> None:
    """Atomically write one collection shard and its cache metadata."""

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_rows = []
    for row in rows:
        item = dict(row)
        size, mtime_ns = file_metadata[row["log_path"]]
        item["_file_size"] = size
        item["_file_mtime_ns"] = mtime_ns
        cache_rows.append(item)
    temporary = cache_path.with_suffix(cache_path.suffix + ".partial")
    cache_columns = list(PUBLIC_ROW_FIELDS) + ["_file_size", "_file_mtime_ns"]
    pd.DataFrame(cache_rows, columns=cache_columns).to_parquet(
        temporary,
        index=False,
    )
    os.replace(temporary, cache_path)
    metadata_path = cache_path.with_suffix(".json")
    metadata_temporary = metadata_path.with_suffix(".json.partial")
    with metadata_temporary.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "cache_version": MANIFEST_CACHE_VERSION,
                "label_signature": label_signature,
                "records": len(rows),
            },
            handle,
            ensure_ascii=False,
        )
    os.replace(metadata_temporary, metadata_path)


def _read_cache(
    cache_path: Optional[Path],
    *,
    label_signature: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    """Load a valid collection cache keyed by source log path."""

    if cache_path is None or not cache_path.is_file():
        return {}
    metadata_path = cache_path.with_suffix(".json")
    try:
        with metadata_path.open(encoding="utf-8") as handle:
            metadata = json.load(handle)
        if metadata.get("cache_version") != MANIFEST_CACHE_VERSION:
            return {}
        if metadata.get("label_signature") != label_signature:
            return {}
        frame = pd.read_parquet(cache_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if "log_path" not in frame.columns:
        return {}
    return {
        str(row["log_path"]): row
        for row in frame.to_dict(orient="records")
        if isinstance(row.get("log_path"), str) and row["log_path"]
    }


def _cache_integer_matches(value: Any, expected: int) -> bool:
    """Compare cached integer metadata without treating NaN as an integer."""

    try:
        return not pd.isna(value) and int(value) == expected
    except (TypeError, ValueError, OverflowError):
        return False


def _cache_hash_available(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def normalize_smiles(smiles: Any) -> Dict[str, Optional[str]]:
    """Validate and canonicalize a SMILES or InChI molecular identifier."""

    if smiles is None:
        return {"smiles": None, "canonical_smiles": None, "inchikey": None, "scaffold": None, "error": "SMILES_MISSING"}
    text = str(smiles).strip()
    if not text:
        return {"smiles": text, "canonical_smiles": None, "inchikey": None, "scaffold": None, "error": "SMILES_MISSING"}
    is_inchi = text.startswith("InChI=")
    molecule = Chem.MolFromInchi(text) if is_inchi else Chem.MolFromSmiles(text)
    if molecule is None:
        error = "INCHI_INVALID" if is_inchi else "SMILES_INVALID"
        return {"smiles": text, "canonical_smiles": None, "inchikey": None, "scaffold": None, "error": error}
    try:
        canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
        return {
            # Downstream parsers consume SMILES. Preserve a supplied SMILES,
            # but convert SDBS-style InChI labels to isomeric canonical SMILES.
            "smiles": canonical if is_inchi else text,
            "canonical_smiles": canonical,
            "inchikey": MolToInchiKey(molecule) or None,
            "scaffold": MurckoScaffoldSmiles(mol=molecule, includeChirality=True) or "__ACYCLIC__",
            "error": None,
        }
    except Exception as exc:  # record the error; do not discard the label
        return {"smiles": text, "canonical_smiles": None, "inchikey": None, "scaffold": None, "error": type(exc).__name__}


def normalize_peptide_sequence(source: str) -> Dict[str, Optional[str]]:
    """Build a standard or modified peptide from a hyphen-delimited ID.

    ``p*`` residues carry phosphate and ``s*`` residues carry sulfate. The
    modification is attached to the named atom in the corresponding residue,
    preserving the peptide bonds and stereochemistry created by RDKit.
    """

    residues = str(source).split("-")
    supported = STANDARD_AMINO_ACIDS | MODIFIED_AMINO_ACIDS.keys()
    unsupported = sorted({residue for residue in residues if residue not in supported})
    if unsupported:
        return {
            "smiles": None,
            "canonical_smiles": None,
            "inchikey": None,
            "scaffold": None,
            "error": f"PEPTIDE_RESIDUE_UNSUPPORTED:{','.join(unsupported)}",
        }
    base_sequence = "".join(
        MODIFIED_AMINO_ACIDS.get(residue, (residue, None, None))[0]
        for residue in residues
    )
    molecule = Chem.MolFromSequence(base_sequence)
    if molecule is None:
        return {
            "smiles": None,
            "canonical_smiles": None,
            "inchikey": None,
            "scaffold": None,
            "error": "PEPTIDE_SEQUENCE_INVALID",
        }
    editable = Chem.RWMol(molecule)
    try:
        for residue_number, residue in enumerate(residues, start=1):
            modification = MODIFIED_AMINO_ACIDS.get(residue)
            if modification is None:
                continue
            _, target_name, center_symbol = modification
            residue_atoms = {
                atom.GetPDBResidueInfo().GetName().strip(): atom
                for atom in editable.GetAtoms()
                if atom.GetPDBResidueInfo() is not None
                and atom.GetPDBResidueInfo().GetResidueNumber() == residue_number
            }
            target = residue_atoms.get(target_name)
            if target is None:
                raise ValueError(f"missing atom {target_name} in residue {residue_number}")

            # Phosphohistidine replaces an imidazole N-H where present. For
            # pH1, ND1 is substituted and NE2 must also use the unprotonated
            # tautomer to match the source pH1 residue definition.
            target.SetNumExplicitHs(0)
            target.SetNoImplicit(True)
            if residue == "pH1":
                ne2 = residue_atoms["NE2"]
                ne2.SetNumExplicitHs(0)
                ne2.SetNoImplicit(True)

            center_index = editable.AddAtom(Chem.Atom(center_symbol))
            editable.AddBond(target.GetIdx(), center_index, Chem.BondType.SINGLE)
            oxoacid_bonds = (
                (Chem.BondType.DOUBLE, Chem.BondType.SINGLE, Chem.BondType.SINGLE)
                if center_symbol == "P"
                else (Chem.BondType.DOUBLE, Chem.BondType.DOUBLE, Chem.BondType.SINGLE)
            )
            for bond_type in oxoacid_bonds:
                oxygen_index = editable.AddAtom(Chem.Atom("O"))
                editable.AddBond(center_index, oxygen_index, bond_type)

        molecule = editable.GetMol()
        Chem.SanitizeMol(molecule)
    except Exception as exc:
        return {
            "smiles": None,
            "canonical_smiles": None,
            "inchikey": None,
            "scaffold": None,
            "error": f"PEPTIDE_MODIFICATION_ERROR:{type(exc).__name__}",
        }
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    return normalize_smiles(canonical)


def source_id(raw_id: str, dataset: str) -> Tuple[str, str]:
    """Return globally unique sample ID and original source ID."""

    source = str(raw_id)
    prefix = SOURCE_PREFIXES.get(dataset, dataset.upper())
    return f"{prefix}-{source}", source


def label_candidates(
    dataset_dir: Path,
    log_dir: Path,
    dataset: str,
    fallback_dirs: Iterable[Path] = (),
) -> List[Path]:
    """Return likely label JSON paths in priority order."""

    candidates = [
        dataset_dir / f"{dataset}_label.json",
        log_dir.with_name(log_dir.name.replace("_log", "_label.json")),
        log_dir / f"{dataset}_label.json",
    ]
    for directory in fallback_dirs:
        candidates.append(directory / f"{dataset}_label.json")
    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def load_labels(candidates: Iterable[Path]) -> Tuple[Dict[str, Any], Optional[Path], Optional[str]]:
    for path in candidates:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                labels = json.load(handle)
            if not isinstance(labels, dict):
                return {}, path, "LABEL_JSON_NOT_OBJECT"
            return {str(key): value for key, value in labels.items()}, path, None
        except (OSError, json.JSONDecodeError) as exc:
            return {}, path, f"LABEL_READ_ERROR:{type(exc).__name__}"
    return {}, None, "LABEL_FILE_NOT_FOUND"


def collect_collection(
    root: Path,
    dataset: str,
    *,
    nmr: bool = False,
    hash_files: bool = True,
    label_fallback_dirs: Iterable[Path] = (),
    workers: int = 1,
    cache_path: Optional[Path] = None,
    incremental: bool = True,
    min_file_age_seconds: float = 0.0,
    identity_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
    audit_all_records: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Collect one frequency/property or NMR collection.

    Collection shards are reused when path, size, mtime, label metadata and
    cache schema are unchanged. ``identity_lookup`` lets NMR records reuse the
    already-normalized frequency identity, which is also required for peptide
    collections whose sequence is encoded in the filename.
    """

    workers = max(1, int(workers))

    if nmr:
        dataset_dir = root / f"{dataset}_nmr"
        log_dir = dataset_dir / f"{dataset}_nmr_log"
        modality = "nmr"
    else:
        dataset_dir = root / dataset
        log_dir = dataset_dir / f"{dataset}_log"
        modality = "frequency"

    rows: List[Dict[str, Any]] = []
    audit: List[Dict[str, Any]] = []
    candidates = label_candidates(
        dataset_dir,
        log_dir,
        dataset,
        label_fallback_dirs,
    )
    label_path = next((path for path in candidates if path.is_file()), None)
    label_error = None if label_path is not None else "LABEL_FILE_NOT_FOUND"
    label_signature = _label_signature(label_path)
    prefix = SOURCE_PREFIXES.get(dataset, dataset.upper())

    if not log_dir.is_dir():
        audit.append({
            "source_dataset": prefix,
            "modality": modality,
            "status": "failed",
            "error_type": "LOG_DIRECTORY_NOT_FOUND",
            "log_path": str(log_dir),
            "label_path": str(label_path) if label_path else None,
        })
        return rows, audit

    now = time.time()
    discovered = []
    for entry in os.scandir(log_dir):
        if not entry.is_file() or not entry.name.lower().endswith(".log"):
            continue
        try:
            stat = entry.stat()
        except OSError:
            continue
        log_path = Path(entry.path)
        if min_file_age_seconds > 0 and now - stat.st_mtime < min_file_age_seconds:
            audit.append({
                "sample_id": None,
                "source_dataset": prefix,
                "source_id": log_path.stem,
                "modality": modality,
                "status": "skipped",
                "error_type": "SOURCE_FILE_TOO_RECENT",
                "log_path": str(log_path),
                "label_path": str(label_path) if label_path else None,
            })
            continue
        discovered.append((log_path, int(stat.st_size), int(stat.st_mtime_ns)))
    discovered.sort(key=lambda item: item[0].name)
    file_metadata = {
        str(path): (size, mtime_ns)
        for path, size, mtime_ns in discovered
    }

    cached = _read_cache(
        cache_path if incremental else None,
        label_signature=label_signature,
    )
    rows_by_path: Dict[str, Dict[str, Any]] = {}
    changed = []
    hash_field = "nmr_file_hash" if nmr else "frequency_file_hash"
    for item in discovered:
        log_path, size, mtime_ns = item
        key = str(log_path)
        previous = cached.get(key)
        reusable = previous is not None and (
            _cache_integer_matches(previous.get("_file_size"), size)
            and _cache_integer_matches(previous.get("_file_mtime_ns"), mtime_ns)
            and (not hash_files or _cache_hash_available(previous.get(hash_field)))
        )
        if reusable:
            rows_by_path[key] = _clean_cached_row(previous)
        else:
            changed.append(item)
    reused_count = len(rows_by_path)

    # Large label maps are unnecessary on a fully cached shard. Load them only
    # when at least one source log needs to be normalized or re-hashed.
    labels: Dict[str, Any] = {}
    if changed:
        labels, loaded_label_path, label_error = load_labels(candidates)
        if loaded_label_path is not None:
            label_path = loaded_label_path

    def collect_one(item):
        log_path, initial_size, initial_mtime_ns = item
        raw_id = log_path.stem
        # Some NMR collections prefix filenames (e.g. NISTIR-1) while their
        # label JSON keeps the original source ID (e.g. 1). Normalize both
        # forms to one global ID and try both keys in the label map.
        if raw_id.startswith(f"{prefix}-"):
            original_id = raw_id[len(prefix) + 1:]
            sample_id = f"{prefix}-{original_id}"
        else:
            sample_id, original_id = source_id(raw_id, dataset)
        label_found = raw_id in labels or original_id in labels
        label = labels.get(raw_id, labels.get(original_id))
        reused_identity = None
        if identity_lookup is not None:
            candidate = identity_lookup.get(sample_id)
            if candidate and candidate.get("canonical_smiles"):
                # Reuse the frequency identity only when NMR has no separate
                # label or already uses the same representation. Distinct NMR
                # labels are normalized independently so merge_records can
                # still report a genuine cross-modal identity conflict.
                label_text = str(label).strip() if label_found else None
                if not label_found or label_text in {
                    candidate.get("smiles"),
                    candidate.get("canonical_smiles"),
                }:
                    reused_identity = {
                        field: candidate.get(field)
                        for field in IDENTITY_FIELDS
                    }
                    reused_identity["error"] = None
        peptide_derived = dataset == "peptide" and not label_found
        if reused_identity is not None:
            normalized = reused_identity
            label_found = True
        elif peptide_derived:
            normalized = normalize_peptide_sequence(original_id)
        else:
            normalized = normalize_smiles(label)
        if peptide_derived and normalized["error"] is None:
            label_found = True
        label_valid = label_found and normalized["error"] is None
        allow_missing_label = not nmr and dataset in ALLOW_MISSING_LABEL_DATASETS
        status = "matched" if label_valid else "structure_only" if allow_missing_label else "unmatched"
        errors = []
        # A separate label JSON is intentionally optional for peptide: its
        # standard sequence is encoded in the log filename.
        if label_error and dataset != "peptide" and reused_identity is None:
            errors.append(label_error)
        if peptide_derived:
            if normalized["error"]:
                errors.append(normalized["error"])
        elif reused_identity is None and raw_id not in labels and original_id not in labels:
            errors.append("LABEL_MISSING")
        elif normalized["error"]:
            errors.append(normalized["error"])
        file_hash = sha256_file(log_path) if hash_files else None
        try:
            final_stat = log_path.stat()
        except OSError:
            final_stat = None
        if final_stat is None or (
            int(final_stat.st_size) != initial_size
            or int(final_stat.st_mtime_ns) != initial_mtime_ns
        ):
            return None, {
                "sample_id": sample_id,
                "source_dataset": prefix,
                "source_id": original_id,
                "modality": modality,
                "status": "skipped",
                "error_type": "SOURCE_FILE_CHANGED_DURING_SCAN",
                "log_path": str(log_path),
                "label_path": str(label_path) if label_path else None,
            }
        row = {
            "sample_id": sample_id,
            "source_dataset": prefix,
            "source_id": original_id,
            "smiles": normalized["smiles"],
            "canonical_smiles": normalized["canonical_smiles"],
            "inchikey": normalized["inchikey"],
            "scaffold": normalized["scaffold"],
            "log_path": str(log_path),
            # ``source_file_hash`` remains for compatibility. The modality-
            # specific fields preserve both hashes after cross-modal merging.
            "source_file_hash": file_hash,
            "frequency_file_hash": file_hash if not nmr else None,
            "nmr_file_hash": file_hash if nmr else None,
            "label_path": str(label_path) if label_path else None,
            "label_status": status,
            "label_errors": errors,
            "available_modalities": [modality] if status in {"matched", "structure_only"} else [],
            "frequency_log_path": str(log_path) if not nmr and status in {"matched", "structure_only"} else None,
            "nmr_log_path": str(log_path) if nmr and status == "matched" else None,
        }
        report = {
            "sample_id": sample_id,
            "source_dataset": prefix,
            "source_id": original_id,
            "modality": modality,
            "status": status,
            "error_type": ";".join(errors) if errors else None,
            "log_path": str(log_path),
            "label_path": str(label_path) if label_path else None,
        }
        return row, report

    if workers > 1 and len(changed) > 1:
        results = _bounded_thread_map(collect_one, changed, workers)
        results = track(
            results,
            total=len(changed),
            desc=f"{prefix} {modality} manifest",
            unit="log",
            leave=False,
        )
        for row, report in results:
            if row is not None:
                rows_by_path[row["log_path"]] = row
            if report["status"] == "skipped":
                audit.append(report)
    else:
        for log_path in track(
            changed,
            total=len(changed),
            desc=f"{prefix} {modality} manifest",
            unit="log",
            leave=False,
        ):
            row, report = collect_one(log_path)
            if row is not None:
                rows_by_path[row["log_path"]] = row
            if report["status"] == "skipped":
                audit.append(report)

    rows = [rows_by_path[str(path)] for path, _, _ in discovered if str(path) in rows_by_path]
    if cache_path is not None:
        _write_cache(
            cache_path,
            rows,
            file_metadata,
            label_signature=label_signature,
        )
    if cached:
        status(
            f"{prefix} {modality} cache: {reused_count:,} reused, "
            f"{len(changed):,} changed/new"
        )

    for row in rows:
        if not audit_all_records and row["label_status"] == "matched":
            continue
        audit.append({
            "sample_id": row["sample_id"],
            "source_dataset": row["source_dataset"],
            "source_id": row["source_id"],
            "modality": modality,
            "status": row["label_status"],
            "error_type": ";".join(row.get("label_errors") or []) or None,
            "log_path": row["log_path"],
            "label_path": row.get("label_path"),
        })

    if label_error and not discovered:
        audit.append({
            "source_dataset": prefix,
            "modality": modality,
            "status": "failed",
            "error_type": label_error,
            "log_path": str(log_dir),
            "label_path": str(label_path) if label_path else None,
        })
    return rows, audit


def merge_records(records: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """Merge frequency and NMR rows by global sample ID and check SMILES."""

    grouped: Dict[str, Dict[str, Any]] = {}
    audit: List[Dict[str, Any]] = []
    for row in track(
        records,
        total=len(records),
        desc="Merge manifests",
        unit="record",
    ):
        sample_id = row["sample_id"]
        if sample_id not in grouped:
            grouped[sample_id] = dict(row)
            continue
        current = grouped[sample_id]
        if current.get("canonical_smiles") and row.get("canonical_smiles") and current["canonical_smiles"] != row["canonical_smiles"]:
            current.setdefault("label_errors", []).append("SMILES_MODALITY_MISMATCH")
            current["label_status"] = "conflict"
            audit.append({
                "sample_id": sample_id,
                "source_dataset": current.get("source_dataset"),
                "modality": "cross-modal",
                "status": "conflict",
                "error_type": "SMILES_MODALITY_MISMATCH",
                "log_path": row.get("log_path"),
                "label_path": row.get("label_path"),
            })
        elif not current.get("canonical_smiles") and row.get("canonical_smiles"):
            for field in ("smiles", "canonical_smiles", "inchikey", "scaffold"):
                current[field] = row.get(field)
            if row.get("label_status") == "matched":
                current["label_status"] = "matched"
        for field in ("frequency_log_path", "nmr_log_path"):
            if row.get(field):
                current[field] = row[field]
        modalities = set(current.get("available_modalities", [])) | set(row.get("available_modalities", []))
        current["available_modalities"] = sorted(modalities)
        current["source_file_hash"] = current.get("source_file_hash") or row.get("source_file_hash")
        current["frequency_file_hash"] = (
            current.get("frequency_file_hash") or row.get("frequency_file_hash")
        )
        current["nmr_file_hash"] = current.get("nmr_file_hash") or row.get("nmr_file_hash")
        current["label_errors"] = sorted(set(current.get("label_errors", []) + row.get("label_errors", [])))
    frame = pd.DataFrame(grouped.values()).reindex(columns=PUBLIC_ROW_FIELDS)
    if not frame.empty:
        frame = frame.sort_values("sample_id").reset_index(drop=True)
    return frame, audit


def write_outputs(
    frame: pd.DataFrame,
    audit: pd.DataFrame,
    output_dir: Path,
    *,
    write_compatibility_json: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output_dir / "openspec_manifest.parquet", index=False)
    audit = audit.reindex(columns=AUDIT_FIELDS)
    audit.to_parquet(output_dir / "label_audit.parquet", index=False)

    if write_compatibility_json:
        labeled = frame[frame["smiles"].notna() & frame["canonical_smiles"].notna()]
        smiles_map = dict(zip(labeled["sample_id"], labeled["smiles"]))
        freq_map = {
            row.sample_id: row.frequency_log_path
            for row in frame.itertuples()
            if isinstance(row.frequency_log_path, str) and row.frequency_log_path
        }
        nmr_map = {
            row.sample_id: row.nmr_log_path
            for row in frame.itertuples()
            if isinstance(row.nmr_log_path, str) and row.nmr_log_path
        }
        with (output_dir / "openspec_smiles.json").open("w", encoding="utf-8") as handle:
            json.dump(smiles_map, handle, ensure_ascii=False, separators=(",", ":"))
        with (output_dir / "openspec_freq_files.json").open("w", encoding="utf-8") as handle:
            json.dump(freq_map, handle, ensure_ascii=False, separators=(",", ":"))
        with (output_dir / "openspec_nmr_files.json").open("w", encoding="utf-8") as handle:
            json.dump(nmr_map, handle, ensure_ascii=False, separators=(",", ":"))
    else:
        legacy_names = (
            "openspec_smiles.json",
            "openspec_freq_files.json",
            "openspec_nmr_files.json",
        )
        stale = [name for name in legacy_names if (output_dir / name).exists()]
        if stale:
            status(
                "Compatibility JSON disabled; existing legacy maps were not "
                f"updated and are ignored by the staged pipeline: {', '.join(stale)}"
            )

    summary = {
        "records": int(len(frame)),
        "matched_records": int((frame["label_status"] == "matched").sum()),
        "unmatched_records": int((frame["label_status"] == "unmatched").sum()),
        "structure_only_records": int((frame["label_status"] == "structure_only").sum()),
        "conflict_records": int((frame["label_status"] == "conflict").sum()),
        "frequency_records": int(frame["frequency_log_path"].notna().sum()),
        "nmr_records": int(frame["nmr_log_path"].notna().sum()),
        "both_frequency_and_nmr": int((frame["frequency_log_path"].notna() & frame["nmr_log_path"].notna()).sum()),
        "unique_canonical_smiles": int(frame["canonical_smiles"].dropna().nunique()),
        "missing_source_file_hash": int(frame["source_file_hash"].isna().sum()),
        "missing_frequency_file_hash": int(
            (frame["frequency_log_path"].notna() & frame["frequency_file_hash"].isna()).sum()
        ),
        "missing_nmr_file_hash": int(
            (frame["nmr_log_path"].notna() & frame["nmr_file_hash"].isna()).sum()
        ),
        "audit_rows": int(len(audit)),
        "skipped_source_files": int((audit["status"] == "skipped").sum()),
        "compatibility_json": bool(write_compatibility_json),
    }
    with (output_dir / "label_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the OpenSpec frequency/NMR manifest")
    parser.add_argument("--freq-root", default="/inspire/hdd/project/chemicalreaction/luxinyu-240207020178/hpc/mols/freq")
    parser.add_argument("--nmr-root", default="/inspire/hdd/project/chemicalreaction/luxinyu-240207020178/hpc/mols/nmr")
    parser.add_argument("--output-dir", default="datasets")
    parser.add_argument("--datasets", nargs="+", default=list(DEFAULT_DATASETS))
    parser.add_argument("--nmr-datasets", nargs="+", default=list(DEFAULT_NMR_DATASETS))
    parser.add_argument("--no-nmr", action="store_true", help="Do not scan the NMR root")
    parser.add_argument("--no-hash-files", action="store_true", help="Skip SHA-256 calculation for source logs")
    parser.add_argument("--workers", type=int, default=1, help="Threads used for manifest scanning and hashing")
    parser.add_argument("--cache-dir", help="Per-dataset incremental manifest cache directory")
    parser.add_argument("--no-incremental", action="store_true", help="Ignore existing manifest cache shards")
    parser.add_argument(
        "--min-file-age-seconds",
        type=float,
        default=0.0,
        help="Skip logs modified more recently than this many seconds",
    )
    parser.add_argument(
        "--audit-all-records",
        action="store_true",
        help="Include successful rows in label_audit.parquet (larger and slower)",
    )
    parser.add_argument(
        "--no-compatibility-json",
        action="store_true",
        help="Write Parquet only; omit legacy id-keyed JSON maps",
    )
    parser.add_argument(
        "--show-rdkit-warnings",
        action="store_true",
        help="Show RDKit warning messages. They are hidden by default and retained as audit errors when actionable.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.workers <= 0:
        args.workers = os.cpu_count() or 1
    configure_rdkit_logging(args.show_rdkit_warnings)
    records: List[Dict[str, Any]] = []
    audit: List[Dict[str, Any]] = []
    hash_files = not args.no_hash_files
    freq_root = Path(args.freq_root)
    nmr_root = Path(args.nmr_root)
    output_dir = Path(args.output_dir)
    cache_root = (
        Path(args.cache_dir)
        if args.cache_dir
        else output_dir.parent / "cache" / "manifest"
    )

    status(f"Frequency manifests: {len(args.datasets)} datasets")
    for dataset in args.datasets:
        rows, report = collect_collection(
            freq_root,
            dataset,
            hash_files=hash_files,
            workers=args.workers,
            cache_path=cache_root / "frequency" / f"{dataset}.parquet",
            incremental=not args.no_incremental,
            min_file_age_seconds=args.min_file_age_seconds,
            audit_all_records=args.audit_all_records,
        )
        records.extend(rows)
        audit.extend(report)
    identity_lookup = {
        row["sample_id"]: row
        for row in records
        if row.get("canonical_smiles")
    }
    if not args.no_nmr:
        status(f"NMR manifests: {len(args.nmr_datasets)} datasets")
        for dataset in args.nmr_datasets:
            rows, report = collect_collection(
                nmr_root,
                dataset,
                nmr=True,
                hash_files=hash_files,
                label_fallback_dirs=(freq_root / dataset,),
                workers=args.workers,
                cache_path=cache_root / "nmr" / f"{dataset}.parquet",
                incremental=not args.no_incremental,
                min_file_age_seconds=args.min_file_age_seconds,
                identity_lookup=identity_lookup,
                audit_all_records=args.audit_all_records,
            )
            records.extend(rows)
            audit.extend(report)

    manifest, merge_audit = merge_records(records)
    audit.extend(merge_audit)
    audit_frame = pd.DataFrame(audit)
    summary = write_outputs(
        manifest,
        audit_frame,
        output_dir,
        write_compatibility_json=not args.no_compatibility_json,
    )
    summary.update({
        "freq_root": str(freq_root),
        "nmr_root": None if args.no_nmr else str(nmr_root),
        "hash_files": hash_files,
        "datasets": list(args.datasets),
        "nmr_datasets": [] if args.no_nmr else list(args.nmr_datasets),
        "incremental": not args.no_incremental,
        "manifest_cache_dir": str(cache_root),
        "min_file_age_seconds": args.min_file_age_seconds,
        "audit_all_records": args.audit_all_records,
    })
    with (Path(args.output_dir) / "label_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
