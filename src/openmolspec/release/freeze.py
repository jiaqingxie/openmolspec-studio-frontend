"""Create an immutable release lock with provenance and SHA-256 inventories."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.metadata
import platform
from pathlib import Path
import subprocess
from typing import Any, Dict, Iterable, Mapping

import pandas as pd

from openmolspec.core.schema import schema_as_dict

from .common import atomic_json, file_sha256, files_below, output_dir, resolve_path


FREEZE_VERSION = "1.0.0"


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    import json
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _source_files(repository: Path) -> Iterable[Path]:
    for relative in ("src/openmolspec", "benchmarks", "configs", "tests"):
        root = repository / relative
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if "upstream" in path.relative_to(root).parts:
                continue
            if path.is_file() and path.suffix in {".py", ".yaml", ".yml"}:
                yield path
    for name in ("pyproject.toml", "README.md", "AGENTS.md", "docs/release_workflow.md"):
        path = repository / name
        if path.is_file():
            yield path


def _git_state(repository: Path) -> Dict[str, Any]:
    def run(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args], cwd=repository, text=True, capture_output=True, check=False
        )
        return completed.stdout.strip()

    status = run("status", "--porcelain")
    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status),
        "dirty_paths": status.splitlines(),
    }


def _inventory(paths: Iterable[Path], workers: int) -> pd.DataFrame:
    unique = sorted({path.resolve() for path in paths if path.is_file()})

    def inspect(path: Path) -> Dict[str, Any]:
        stat = path.stat()
        return {
            "path": str(path),
            "bytes": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "sha256": file_sha256(path),
        }

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        return pd.DataFrame(executor.map(inspect, unique))


def freeze_release(config: Mapping[str, Any], hash_workers: int = 2) -> Dict[str, Any]:
    """Freeze the release inventory and its file-identity metadata."""
    root = output_dir(config)
    root.mkdir(parents=True, exist_ok=True)
    repository = Path(str(config["_config_path"])).parent.parent
    input_values = [Path(str(config["_config_path"]))]
    for key, value in config["inputs"].items():
        if key == "trajectory_pickles":
            input_values.extend(resolve_path(config, item) for item in value)
        elif isinstance(value, str):
            input_values.append(resolve_path(config, value))
    input_inventory = _inventory(input_values, hash_workers)
    input_inventory.to_parquet(root / "input_checksums.parquet", index=False)

    source_inventory = _inventory(_source_files(repository), hash_workers)
    source_inventory["path"] = source_inventory["path"].map(
        lambda value: str(Path(value).relative_to(repository))
    )
    source_inventory.to_parquet(root / "source_checksums.parquet", index=False)

    excluded = {root / "release_checksums.parquet", root / "release-lock.json"}
    release_inventory = _inventory(
        (path for path in files_below(root) if path not in excluded), hash_workers
    )
    release_inventory["path"] = release_inventory["path"].map(
        lambda value: str(Path(value).relative_to(root))
    )
    release_inventory.to_parquet(root / "release_checksums.parquet", index=False)

    packages = {}
    for name in ("numpy", "pandas", "pyarrow", "h5py", "rdkit", "PyYAML"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    lock = {
        "freeze_version": FREEZE_VERSION,
        "release_id": config["release"]["release_id"],
        "dataset_version": config["release"]["dataset_version"],
        "release_status": config["release"].get("status", "unspecified"),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(config["_config_path"]),
        "git": _git_state(repository),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": packages,
        },
        "schema": schema_as_dict(),
        "input_file_count": int(len(input_inventory)),
        "input_bytes": int(input_inventory["bytes"].sum()),
        "source_file_count": int(len(source_inventory)),
        "release_file_count": int(len(release_inventory)),
        "release_bytes": int(release_inventory["bytes"].sum()),
        "checksums": {
            "inputs": "input_checksums.parquet",
            "source": "source_checksums.parquet",
            "release": "release_checksums.parquet",
        },
        "summaries": {
            "catalog": _read_json(root / "catalog" / "summary.json"),
            "splits": _read_json(root / "splits" / "summary.json"),
            "release_gate": _read_json(root / "validation" / "summary.json"),
            "internal_qc": _read_json(root / "validation" / "internal" / "summary.json"),
            "publication_validation": _read_json(root / "validation" / "publication" / "summary.json"),
            "payload": _read_json(root / "payload" / "summary.json"),
        },
        "immutability_policy": (
            "Do not modify files in this directory after freezing. Create a new release_id "
            "for any data, schema, processing, or split change."
        ),
    }
    atomic_json(root / "release-lock.json", lock)
    return lock
