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
    """Read a YAML release configuration.

    Parameters
    ----------
    path : str or pathlib.Path
        YAML file containing a ``release`` mapping.

    Returns
    -------
    dict
        Parsed configuration with its absolute path in ``_config_path``.

    Raises
    ------
    ValueError
        If the YAML document is not a release configuration mapping.
    """
    config_path = Path(path).resolve()
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or "release" not in config:
        raise ValueError("release configuration must contain a 'release' mapping")
    config["_config_path"] = str(config_path)
    return config


def resolve_path(config: Mapping[str, Any], value: str | Path) -> Path:
    """Resolve a release path relative to its repository.

    Parameters
    ----------
    config : mapping
        Configuration returned by :func:`load_config`.
    value : str or pathlib.Path
        Absolute path or path relative to the parent of the config directory.

    Returns
    -------
    pathlib.Path
        Resolved release input or output path.
    """
    path = Path(value)
    if path.is_absolute():
        return path
    # Release configs are kept below configs/, while paths are repository-relative.
    config_path = Path(str(config["_config_path"]))
    repository = config_path.parent.parent
    return (repository / path).resolve()


def output_dir(config: Mapping[str, Any]) -> Path:
    """Resolve the configured release destination.

    Parameters
    ----------
    config : mapping
        Release configuration containing ``release.output_dir``.

    Returns
    -------
    pathlib.Path
        Release output directory.
    """
    return resolve_path(config, config["release"]["output_dir"])


def atomic_json(path: Path, payload: Any) -> None:
    """Write JSON through a temporary file and atomically replace its destination.

    Parameters
    ----------
    path : pathlib.Path
        JSON destination; parent directories are created as needed.
    payload : object
        JSON-compatible data, with NumPy and path values converted by
        :func:`json_default`.

    Returns
    -------
    None
        Writes an indented UTF-8 JSON file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=json_default)
        handle.write("\n")
    temporary.replace(path)


def json_default(value: Any) -> Any:
    """Convert path and NumPy values for JSON encoding.

    Parameters
    ----------
    value : object
        A path, NumPy scalar or NumPy array.

    Returns
    -------
    str, number or list
        JSON-compatible representation.

    Raises
    ------
    TypeError
        If the object has no supported conversion.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def stable_digest(value: str, seed: int = 0) -> str:
    """Hash a value with a deterministic seed prefix.

    Parameters
    ----------
    value : str
        Identifier to hash.
    seed : int, default 0
        Namespace seed prepended to the identifier.

    Returns
    -------
    str
        SHA-256 hexadecimal digest of ``f'{seed}:{value}'``.
    """
    return hashlib.sha256(f"{seed}:{value}".encode("utf-8")).hexdigest()


def file_sha256(path: Path, block_size: int = 16 * 1024 * 1024) -> str:
    """Compute a file checksum using bounded-memory reads.

    Parameters
    ----------
    path : pathlib.Path
        File to hash.
    block_size : int, default 16777216
        Bytes read per iteration.

    Returns
    -------
    str
        SHA-256 hexadecimal digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def files_below(root: Path) -> Iterable[Path]:
    """Iterate over release files in stable path order.

    Parameters
    ----------
    root : pathlib.Path
        Directory searched recursively.

    Yields
    ------
    pathlib.Path
        Regular files, excluding temporary ``.partial-`` files.
    """
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".partial-" not in path.name:
            yield path
