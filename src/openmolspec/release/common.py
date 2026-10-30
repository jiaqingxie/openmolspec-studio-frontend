"""Shared helpers for versioned OpenMolSpec release construction."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

import numpy as np
import yaml


def load_config(path: str | Path) -> Dict[str, Any]:
    config_path = Path(path).resolve()
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or "release" not in config:
        raise ValueError("release configuration must contain a 'release' mapping")
    config["_config_path"] = str(config_path)
    return config


def resolve_path(config: Mapping[str, Any], value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    # Release configs are kept below configs/, while paths are repository-relative.
    config_path = Path(str(config["_config_path"]))
    repository = config_path.parent.parent
    return (repository / path).resolve()


def output_dir(config: Mapping[str, Any]) -> Path:
    return resolve_path(config, config["release"]["output_dir"])


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=json_default)
        handle.write("\n")
    temporary.replace(path)


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def stable_digest(value: str, seed: int = 0) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode("utf-8")).hexdigest()


def file_sha256(path: Path, block_size: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def files_below(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".partial-" not in path.name:
            yield path
