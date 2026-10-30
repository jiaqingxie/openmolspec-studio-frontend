"""Non-destructive internal validation for legacy and v1-style datasets."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

import numpy as np
import pandas as pd
from tqdm import tqdm


PROPERTY_FIELDS = ("energy", "zpve", "dipole", "polar", "homo", "lumo", "gap", "U", "H", "G")
SPECTRUM_FIELDS = ("freq", "ir", "raman", "frequencies", "ir_spectrum", "raman_spectrum")


def _array(value: Any):
    if value is None:
        return None
    try:
        return np.asarray(value)
    except (TypeError, ValueError):
        return None


def _finite(value: Any) -> bool:
    values = _array(value)
    if values is None:
        return False
    try:
        return bool(np.all(np.isfinite(values)))
    except (TypeError, ValueError):
        return False


def validate_record(record: Mapping[str, Any], sample_id: Any) -> Dict[str, Any]:
    """Validate one record and return flags without changing the record."""

    errors: List[str] = []
    flags: List[str] = []
    atom = record.get("atomic_numbers", record.get("atom"))
    coordinates = record.get("coordinates", record.get("coordinate"))
    frequencies = record.get("frequencies", record.get("freq"))
    ir = record.get("ir_spectrum", record.get("ir"))
    raman = record.get("raman_spectrum", record.get("raman"))

    if atom is None:
        errors.append("MISSING_ATOMIC_NUMBERS")
    else:
        atom_array = _array(atom)
        if atom_array is None or atom_array.ndim != 1:
            errors.append("INVALID_ATOMIC_NUMBERS")
        elif np.any(atom_array <= 0) or np.any(atom_array > 118):
            errors.append("INVALID_ATOMIC_NUMBER")

    if coordinates is not None:
        coordinate_array = _array(coordinates)
        atom_count = len(_array(atom)) if _array(atom) is not None else 0
        if coordinate_array is None or coordinate_array.size != 3 * atom_count:
            errors.append("ATOM_COORDINATE_COUNT_MISMATCH")
        elif not _finite(coordinates):
            errors.append("NONFINITE_COORDINATES")
    else:
        flags.append("MISSING_COORDINATES")

    hessian = record.get("hessian")
    if hessian is not None and atom is not None:
        shape = _array(hessian)
        n = 3 * len(_array(atom))
        if shape is None or shape.shape != (n, n):
            errors.append("INVALID_HESSIAN_SHAPE")
        elif not _finite(hessian):
            errors.append("NONFINITE_HESSIAN")

    if frequencies is not None:
        freq_array = _array(frequencies)
        if freq_array is None or not _finite(frequencies):
            errors.append("INVALID_FREQUENCIES")
        elif np.any(freq_array < 0):
            flags.append("IMAGINARY_FREQUENCIES_PRESENT")
    else:
        flags.append("MISSING_FREQUENCIES")

    if frequencies is not None and record.get("ir_intensities") is not None:
        if len(_array(frequencies)) != len(_array(record["ir_intensities"])):
            errors.append("FREQUENCY_IR_LENGTH_MISMATCH")
    if frequencies is not None and record.get("raman_activities") is not None:
        activities = record["raman_activities"]
        if len(_array(frequencies)) != len(_array(activities)):
            errors.append("FREQUENCY_RAMAN_LENGTH_MISMATCH")

    for field in PROPERTY_FIELDS + SPECTRUM_FIELDS:
        if field in record and record[field] is not None and not _finite(record[field]):
            errors.append(f"NONFINITE_{field.upper()}")

    if ir is not None and _array(ir).ndim != 1:
        errors.append("INVALID_IR_SPECTRUM_SHAPE")
    if raman is not None and _array(raman).ndim != 1:
        errors.append("INVALID_RAMAN_SPECTRUM_SHAPE")

    return {
        "sample_id": str(sample_id),
        "schema_valid": len(errors) == 0,
        "qc_pass": len(errors) == 0,
        "errors": sorted(set(errors)),
        "quality_flags": sorted(set(flags)),
    }


def _stats(
    frame: pd.DataFrame,
    fields: Iterable[str],
    *,
    quantile_sample_limit: int = 10_000_000,
) -> pd.DataFrame:
    """Compute exact moments/extrema and sampled quantiles without expansion.

    A fixed-grid spectrum column can contain billions of scalar values. Building
    a Python list of every value is prohibitively expensive. Count, mean,
    standard deviation, minimum and maximum are accumulated exactly with numpy;
    quantiles and MAD use a deterministic, evenly distributed sample bounded by
    ``quantile_sample_limit`` and are labelled accordingly in the output.
    """

    rows = []
    for field in fields:
        if field not in frame:
            continue
        count = 0
        total = 0.0
        total_squares = 0.0
        minimum = np.inf
        maximum = -np.inf
        sample = np.empty(quantile_sample_limit, dtype=np.float64)
        sample_count = 0
        values_per_record = max(1, quantile_sample_limit // max(len(frame), 1))
        present_records = 0
        for row_index, value in enumerate(frame[field]):
            array = _array(value)
            if array is None:
                continue
            try:
                numeric = np.asarray(array, dtype=np.float64).reshape(-1)
            except (TypeError, ValueError):
                continue
            numeric = numeric[np.isfinite(numeric)]
            if numeric.size == 0:
                continue
            present_records += 1
            count += int(numeric.size)
            total += float(numeric.sum(dtype=np.float64))
            total_squares += float(np.square(numeric).sum(dtype=np.float64))
            minimum = min(minimum, float(numeric.min()))
            maximum = max(maximum, float(numeric.max()))
            remaining = quantile_sample_limit - sample_count
            if remaining <= 0:
                continue
            take = min(values_per_record, numeric.size, remaining)
            if take == numeric.size:
                chosen = numeric
            elif take == 1:
                chosen = numeric[(row_index * 2654435761) % numeric.size:][:1]
            else:
                offset = (row_index * 2654435761) % numeric.size
                positions = (offset + np.linspace(0, numeric.size - 1, take, dtype=np.int64)) % numeric.size
                chosen = numeric[positions]
            sample[sample_count:sample_count + take] = chosen
            sample_count += take
        if count == 0:
            rows.append({"field": field, "count": 0, "missing_rate": 1.0})
            continue
        sampled = sample[:sample_count]
        quantiles = np.quantile(sampled, [0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99])
        median = float(quantiles[3])
        mad = float(np.median(np.abs(sampled - median)))
        variance = max(0.0, (total_squares - total * total / count) / max(count - 1, 1))
        rows.append({
            "field": field,
            "count": count,
            "missing_rate": float(1.0 - present_records / len(frame)) if len(frame) else 1.0,
            "mean": float(total / count),
            "std": float(np.sqrt(variance)),
            "median": median,
            "MAD": mad,
            "min": float(minimum),
            "1%": float(quantiles[0]),
            "5%": float(quantiles[1]),
            "25%": float(quantiles[2]),
            "50%": median,
            "75%": float(quantiles[4]),
            "95%": float(quantiles[5]),
            "99%": float(quantiles[6]),
            "max": float(maximum),
            "quantiles_approximate": sample_count < count,
            "quantile_sample_count": int(sample_count),
        })
    return pd.DataFrame(rows)


def validate_dataframe(frame: pd.DataFrame, workers: int = 1) -> Dict[str, pd.DataFrame]:
    """Validate all rows and return report tables."""

    sample_ids = frame.get("sample_id", frame.get("filename", pd.Series(frame.index)))
    tasks = [(row, sample_ids.iloc[index]) for index, (_, row) in enumerate(frame.iterrows())]
    if workers > 1 and len(tasks) > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            rows = list(tqdm(
                executor.map(lambda task: validate_record(*task), tasks),
                total=len(tasks), desc="Internal QC", unit="record",
            ))
    else:
        rows = [validate_record(row, sample_id) for row, sample_id in tqdm(
            tasks, total=len(tasks), desc="Internal QC", unit="record"
        )]
    results = pd.DataFrame(rows)
    duplicate_ids = sample_ids.duplicated(keep=False)
    if duplicate_ids.any():
        results.loc[duplicate_ids.to_numpy(), "errors"] = results.loc[duplicate_ids.to_numpy(), "errors"].apply(
            lambda values: sorted(set(values + ["DUPLICATE_SAMPLE_ID"]))
        )
        results.loc[duplicate_ids.to_numpy(), "schema_valid"] = False
        results.loc[duplicate_ids.to_numpy(), "qc_pass"] = False

    errors = results.explode("errors").dropna(subset=["errors"])
    missing = results.explode("quality_flags").dropna(subset=["quality_flags"])
    attrition = pd.DataFrame([
        {"stage": "raw_input", "count": len(frame), "status": "observed"},
        {"stage": "parsed", "count": len(frame), "status": "observed_from_input"},
        {"stage": "optimization_converged", "count": None, "status": "not_available"},
        {"stage": "schema_valid", "count": int(results["schema_valid"].sum()), "status": "computed"},
        {"stage": "QC_pass", "count": int(results["qc_pass"].sum()), "status": "computed"},
        {"stage": "deduplicated", "count": None, "status": "not_available"},
        {"stage": "final_release", "count": None, "status": "not_available"},
    ])
    return {
        "records": results,
        "error_breakdown": errors,
        "missingness": missing,
        "attrition": attrition,
        "property_statistics": _stats(frame, PROPERTY_FIELDS),
        "spectrum_statistics": _stats(frame, SPECTRUM_FIELDS),
    }


def run(dataset: str, output: str, workers: int = 1) -> Dict[str, Any]:
    """Run internal QC on a pickle or Parquet DataFrame."""

    input_path = Path(dataset)
    frame = pd.read_pickle(input_path) if input_path.suffix in (".pkl", ".pickle") else pd.read_parquet(input_path)
    reports = validate_dataframe(frame, workers=workers)
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    reports["records"].to_parquet(output_path / "record_qc.parquet", index=False)
    for name in ("attrition", "error_breakdown", "missingness", "property_statistics", "spectrum_statistics"):
        reports[name].to_csv(output_path / f"{name}.csv", index=False)
    summary = {
        "input": str(input_path),
        "records": int(len(frame)),
        "schema_valid": int(reports["records"]["schema_valid"].sum()),
        "qc_pass": int(reports["records"]["qc_pass"].sum()),
        "error_count": int(len(reports["error_breakdown"])),
        "flag_count": int(len(reports["missingness"])),
    }
    with open(output_path / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run non-destructive OpenSpec internal QC")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(run(args.dataset, args.output, workers=args.workers), indent=2))


if __name__ == "__main__":
    main()
