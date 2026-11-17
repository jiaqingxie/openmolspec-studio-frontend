"""Export legacy DataFrame pickles as resumable Parquet + HDF5 shards."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import h5py
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from openmolspec.core.progress import track

from .common import atomic_json, output_dir, resolve_path


EXPORT_VERSION = "1.0.0"
_EXPORT_FRAME: Optional[pd.DataFrame] = None
_EXPORT_DESTINATION: Optional[Path] = None
_EXPORT_KIND = ""
_EXPORT_COMPRESSION: Optional[str] = None
FIELD_ALIASES = {
    "atom": "atomic_numbers",
    "coordinate": "coordinates",
    "freq": "frequencies",
    "ir": "ir_spectrum",
    "raman": "raman_spectrum",
    "isotropic": "nmr_isotropic",
    "anisotropy": "nmr_anisotropy",
    "shielding_tensor": "nmr_tensor",
}


def _normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {
        source: target for source, target in FIELD_ALIASES.items()
        if source in frame.columns and target not in frame.columns
    }
    return frame.rename(columns=rename)


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and np.isnan(value):
        return False
    return True


def _as_numeric_array(value: Any) -> Optional[np.ndarray]:
    if not _present(value) or isinstance(value, (str, bytes, dict)):
        return None
    if not isinstance(value, (np.ndarray, list, tuple)):
        return None
    try:
        array = np.asarray(value)
    except (TypeError, ValueError):
        return None
    if array.dtype.kind not in "biufc":
        return None
    return array


def _array_columns(frame: pd.DataFrame) -> List[str]:
    fields = []
    for column in frame.columns:
        for value in frame[column]:
            if not _present(value):
                continue
            if _as_numeric_array(value) is not None:
                fields.append(column)
            break
    return fields


def _metadata_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (dict, list, tuple, np.ndarray)):
        return json.dumps(value, ensure_ascii=False, default=lambda item: np.asarray(item).tolist())
    return value


def _write_array(group: h5py.Group, values: Sequence[Any], compression: Optional[str]) -> Dict[str, Any]:
    arrays: List[Optional[np.ndarray]] = [_as_numeric_array(value) for value in values]
    present = np.asarray([array is not None for array in arrays], dtype=np.bool_)
    nonempty = [array for array in arrays if array is not None]
    dtype = np.result_type(*[array.dtype for array in nonempty]) if nonempty else np.dtype("float64")
    # Raman intensity is scientifically required to remain float64.
    if group.name.rsplit("/", 1)[-1] in {"raman_spectrum", "raman_activities"}:
        dtype = np.dtype("float64")
    offsets = np.zeros(len(arrays) + 1, dtype=np.uint64)
    dimensions = max((array.ndim for array in nonempty), default=1)
    shapes = np.full((len(arrays), dimensions), -1, dtype=np.int64)
    flattened = []
    for index, array in enumerate(arrays):
        if array is not None:
            cast = np.asarray(array, dtype=dtype)
            flattened.append(cast.reshape(-1))
            shapes[index, : cast.ndim] = cast.shape
            offsets[index + 1] = offsets[index] + cast.size
        else:
            offsets[index + 1] = offsets[index]
    data = np.concatenate(flattened) if flattened else np.asarray([], dtype=dtype)
    options = {"compression": compression, "shuffle": True} if compression else {}
    group.create_dataset("values", data=data, **options)
    group.create_dataset("offsets", data=offsets, **options)
    group.create_dataset("shapes", data=shapes, **options)
    group.create_dataset("present", data=present, **options)
    group.attrs["dtype"] = str(dtype)
    group.attrs["encoding"] = "flattened values + row offsets + original shapes"
    return {
        "dtype": str(dtype),
        "present_rows": int(present.sum()),
        "values": int(data.size),
        "max_ndim": int(dimensions),
    }


def _record_ids(frame: pd.DataFrame, kind: str) -> pd.Series:
    sample = frame.get("sample_id", pd.Series(frame.index, index=frame.index)).astype(str)
    if kind == "trajectory":
        steps = frame.get("step_index", pd.Series(range(len(frame)), index=frame.index)).astype(str)
        return sample + ":opt:" + steps
    return sample


def _write_shard(
    frame: pd.DataFrame,
    destination: Path,
    shard_index: int,
    kind: str,
    compression: Optional[str],
) -> Dict[str, Any]:
    stem = f"shard-{shard_index:05d}"
    hdf5_path = destination / f"{stem}.h5"
    metadata_path = destination / f"{stem}.parquet"
    sidecar_path = destination / f"{stem}.json"
    if hdf5_path.exists() and metadata_path.exists() and sidecar_path.exists():
        with sidecar_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    frame = _normalise_columns(frame.reset_index(drop=True))
    arrays = _array_columns(frame)
    metadata_columns = [column for column in frame.columns if column not in arrays]
    metadata = frame[metadata_columns].copy()
    for column in metadata.select_dtypes(include="object").columns:
        metadata[column] = metadata[column].map(_metadata_value)
    metadata.insert(0, "record_id", _record_ids(frame, kind))
    metadata.insert(1, "row_in_shard", np.arange(len(frame), dtype=np.int32))
    metadata.insert(2, "shard", stem)

    destination.mkdir(parents=True, exist_ok=True)
    hdf5_temp = hdf5_path.with_name(f".{hdf5_path.name}.partial-{os.getpid()}")
    metadata_temp = metadata_path.with_name(f".{metadata_path.name}.partial-{os.getpid()}")
    field_summary: Dict[str, Any] = {}
    with h5py.File(hdf5_temp, "w") as handle:
        handle.attrs["export_version"] = EXPORT_VERSION
        handle.attrs["record_count"] = len(frame)
        handle.attrs["kind"] = kind
        handle.create_dataset(
            "record_id",
            data=np.asarray(metadata["record_id"], dtype=object),
            dtype=h5py.string_dtype("utf-8"),
        )
        array_root = handle.create_group("arrays")
        for field in arrays:
            field_summary[field] = _write_array(array_root.create_group(field), frame[field].tolist(), compression)
    metadata.to_parquet(metadata_temp, index=False)
    hdf5_temp.replace(hdf5_path)
    metadata_temp.replace(metadata_path)
    result = {
        "shard": stem,
        "records": int(len(frame)),
        "metadata_file": metadata_path.name,
        "array_file": hdf5_path.name,
        "array_fields": field_summary,
    }
    atomic_json(sidecar_path, result)
    return result


def _write_shard_task(task: Tuple[int, int, int]) -> Dict[str, Any]:
    shard_index, start, stop = task
    if _EXPORT_FRAME is None or _EXPORT_DESTINATION is None:
        raise RuntimeError("release export worker was not initialized")
    return _write_shard(
        _EXPORT_FRAME.iloc[start:stop],
        _EXPORT_DESTINATION,
        shard_index,
        _EXPORT_KIND,
        _EXPORT_COMPRESSION,
    )


def export_pickle(
    source: Path,
    destination: Path,
    *,
    kind: str,
    shard_size: int,
    compression: Optional[str] = "lzf",
    workers: int = 1,
) -> Dict[str, Any]:
    """Export selected release records as Python pickle data."""
    if shard_size < 1:
        raise ValueError("shard_size must be positive")
    frame = pd.read_pickle(source)
    tasks = [
        (shard_index, start, min(start + shard_size, len(frame)))
        for shard_index, start in enumerate(range(0, len(frame), shard_size))
    ]
    if workers > 1 and tasks:
        # fork shares the already-loaded, read-only DataFrame copy-on-write;
        # each process writes a distinct pair of shard files.
        global _EXPORT_FRAME, _EXPORT_DESTINATION, _EXPORT_KIND, _EXPORT_COMPRESSION
        _EXPORT_FRAME = frame
        _EXPORT_DESTINATION = destination
        _EXPORT_KIND = kind
        _EXPORT_COMPRESSION = compression
        context = mp.get_context("fork")
        with context.Pool(processes=workers) as pool:
            iterator = pool.imap_unordered(_write_shard_task, tasks)
            shards = list(track(
                iterator,
                total=len(tasks),
                desc=f"Release export: {destination.name}",
                unit="shard",
            ))
        _EXPORT_FRAME = None
    else:
        shards = []
        for task in track(
            tasks,
            total=len(tasks),
            desc=f"Release export: {destination.name}",
            unit="shard",
        ):
            shard_index, start, stop = task
            shards.append(_write_shard(
                frame.iloc[start:stop], destination, shard_index, kind, compression
            ))
    shards.sort(key=lambda value: value["shard"])
    summary = {
        "export_version": EXPORT_VERSION,
        "kind": kind,
        "source": str(source),
        "source_bytes": source.stat().st_size,
        "records": int(len(frame)),
        "shard_size": int(shard_size),
        "shard_count": len(shards),
        "compression": compression,
        "workers": int(workers),
        "field_aliases": FIELD_ALIASES,
        "shards": shards,
    }
    atomic_json(destination / "manifest.json", summary)
    del frame
    return {key: value for key, value in summary.items() if key != "shards"}


def export_release(config: Mapping[str, Any], only: Optional[str] = None) -> Dict[str, Any]:
    """Export the configured molecular release formats."""
    options = config["release"]["export"]
    destination = output_dir(config) / "payload"
    compression = options.get("compression", "lzf")
    workers = int(options.get("workers", 1))
    results: Dict[str, Any] = {}

    if only in (None, "frequency"):
        results["frequency"] = export_pickle(
            resolve_path(config, config["inputs"]["frequency_pickle"]),
            destination / "frequency",
            kind="frequency",
            shard_size=int(options.get("frequency_shard_size", 10_000)),
            compression=compression,
            workers=workers,
        )
    if only in (None, "nmr"):
        results["nmr"] = export_pickle(
            resolve_path(config, config["inputs"]["nmr_pickle"]),
            destination / "nmr",
            kind="nmr",
            shard_size=int(options.get("nmr_shard_size", 10_000)),
            compression=compression,
            workers=workers,
        )
    if only in (None, "trajectory"):
        trajectories = config["inputs"].get("trajectory_pickles", [])
        for value in trajectories:
            source = resolve_path(config, value)
            name = source.stem.replace("openspec_", "").replace("_opt_trajectories", "")
            results[f"trajectory/{name}"] = export_pickle(
                source,
                destination / "trajectories" / name,
                kind="trajectory",
                shard_size=int(options.get("trajectory_shard_size", 25_000)),
                compression=compression,
                workers=workers,
            )
    index_payload(config)
    return results


def _index_one(
    directory: Path,
    manifest: Mapping[str, Any],
    origins: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    index_path = directory / "index.parquet"
    temporary = index_path.with_name(f".{index_path.name}.partial-{os.getpid()}")
    writer: Optional[pq.ParquetWriter] = None
    indexed = 0
    try:
        for shard in manifest.get("shards", []):
            metadata_path = directory / shard["metadata_file"]
            schema_names = pq.ParquetFile(metadata_path).schema_arrow.names
            columns = [column for column in (
                "record_id", "sample_id", "step_index", "shard", "row_in_shard"
            ) if column in schema_names]
            table = pq.read_table(metadata_path, columns=columns)
            if origins is not None and "sample_id" in table.column_names:
                indexed_frame = table.to_pandas()
                matched = origins.reindex(indexed_frame["sample_id"].astype(str))
                for column in ("source_dataset", "source_id", "molecule_id"):
                    indexed_frame[column] = pd.array(
                        matched[column].to_numpy(), dtype="string"
                    )
                table = pa.Table.from_pandas(indexed_frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            writer.write_table(table)
            indexed += table.num_rows
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        pa.table({"record_id": pa.array([], type=pa.string())}).to_pandas().to_parquet(
            temporary, index=False
        )
    temporary.replace(index_path)
    if indexed != int(manifest["records"]):
        raise RuntimeError(f"index count mismatch for {directory}: {indexed} != {manifest['records']}")
    return {
        "kind": manifest["kind"],
        "records": indexed,
        "shard_count": int(manifest["shard_count"]),
        "index": str(index_path.name),
        "manifest": "manifest.json",
    }


def index_payload(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Rebuild global indices and a complete payload summary from shard manifests."""

    payload = output_dir(config) / "payload"
    records_path = output_dir(config) / "catalog" / "records.parquet"
    origins = None
    if records_path.exists():
        origins = pd.read_parquet(
            records_path,
            columns=["sample_id", "source_dataset", "source_id", "molecule_id"],
        )
        if origins["sample_id"].duplicated().any():
            raise ValueError("catalog record sample_id values must be unique for payload indexing")
        origins["sample_id"] = origins["sample_id"].astype(str)
        origins = origins.set_index("sample_id")
    results: Dict[str, Any] = {}
    for manifest_path in sorted(payload.rglob("manifest.json")):
        with manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        relative = manifest_path.parent.relative_to(payload).as_posix()
        results[relative] = _index_one(manifest_path.parent, manifest, origins=origins)
    summary = {
        "export_version": EXPORT_VERSION,
        "payload_count": len(results),
        "total_records": int(sum(item["records"] for item in results.values())),
        "payloads": results,
    }
    atomic_json(payload / "summary.json", summary)
    return summary


def read_array_row(path: str | Path, field: str, row: int) -> Optional[np.ndarray]:
    """Read one array from a release shard; useful for examples and tests."""

    with h5py.File(path, "r") as handle:
        group = handle[f"arrays/{field}"]
        if not bool(group["present"][row]):
            return None
        start, stop = int(group["offsets"][row]), int(group["offsets"][row + 1])
        shape = tuple(int(value) for value in group["shapes"][row] if value >= 0)
        return np.asarray(group["values"][start:stop]).reshape(shape)
