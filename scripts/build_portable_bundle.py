#!/usr/bin/env python3
"""Build a portable OpenMolSpec Studio archive with its runtime assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from openmolspec_ui.config import discover_assets


BUNDLE_NAME = "openmolspec-studio-portable"

BUNDLE_ENTRIES = (
    ".streamlit",
    ".gitignore",
    "README.md",
    "app.py",
    "benchmarks",
    "configs",
    "docs",
    "openmolspec_ui",
    "pyproject.toml",
    "requirements.txt",
    "scripts",
    "setup.sh",
    "src",
    "start.sh",
    "tests",
)
IGNORED_PARTS = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ipynb_checkpoints",
    "__pycache__",
}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def keep(path: Path) -> bool:
    return not any(part in IGNORED_PARTS for part in path.parts) and path.suffix not in IGNORED_SUFFIXES


def files_below(path: Path):
    if path.is_file():
        if keep(path):
            yield path
        return
    for item in sorted(path.rglob("*")):
        if item.is_file() and keep(item):
            yield item


def nearest_resolved_config(checkpoint: Path, root: Path) -> Path | None:
    directory = checkpoint.parent
    while directory != root and root in directory.parents:
        candidate = directory / "resolved_config.yaml"
        if candidate.is_file():
            return candidate
        directory = directory.parent
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=APP_ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=APP_ROOT / "dist" / f"{BUNDLE_NAME}.tar.gz",
    )
    args = parser.parse_args()
    source_root = args.root.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    assets = discover_assets(source_root)
    asset_paths = {
        name: path
        for name, path in vars(assets).items()
        if name != "root" and isinstance(path, Path)
    }
    missing = [name for name in vars(assets) if name != "root" and getattr(assets, name) is None]
    if missing:
        raise SystemExit(f"Missing required assets: {', '.join(missing)}")

    sources: dict[str, Path] = {}
    for entry in BUNDLE_ENTRIES:
        path = source_root / entry
        if not path.exists():
            continue
        for file_path in files_below(path):
            sources[str(file_path.relative_to(source_root))] = file_path
    for path in asset_paths.values():
        sources[str(path.relative_to(source_root))] = path
        if path.suffix in {".pt", ".pth", ".ckpt"}:
            config = nearest_resolved_config(path, source_root)
            if config is not None:
                sources[str(config.relative_to(source_root))] = config

    with tempfile.TemporaryDirectory(prefix="openmolspec-portable-") as temporary:
        metadata_root = Path(temporary)
        manifest = {
            "bundle": BUNDLE_NAME,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_root": str(source_root),
            "runtime_assets": {
                name: {
                    "path": str(path.relative_to(source_root)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
                for name, path in sorted(asset_paths.items())
            },
        }
        manifest_path = metadata_root / "MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        checksums = []
        for archive_path, source_path in sorted(sources.items()):
            checksums.append(f"{sha256(source_path)}  {archive_path}")
        checksums.append(f"{sha256(manifest_path)}  {manifest_path.name}")
        checksum_path = metadata_root / "SHA256SUMS"
        checksum_path.write_text("\n".join(sorted(checksums)) + "\n", encoding="utf-8")

        with tarfile.open(output, "w:gz", compresslevel=1) as archive:
            for archive_path, source_path in sorted(sources.items()):
                archive.add(source_path, arcname=f"{BUNDLE_NAME}/{archive_path}", recursive=False)
            for path in (manifest_path, checksum_path):
                archive.add(path, arcname=f"{BUNDLE_NAME}/{path.name}", recursive=False)

    archive_digest = sha256(output)
    checksum_output = output.with_suffix(output.suffix + ".sha256")
    checksum_output.write_text(f"{archive_digest}  {output.name}\n", encoding="utf-8")
    print(json.dumps({
        "archive": str(output),
        "bytes": output.stat().st_size,
        "sha256": archive_digest,
        "files": len(sources) + 2,
        "checksum": str(checksum_output),
    }, indent=2))


if __name__ == "__main__":
    main()
