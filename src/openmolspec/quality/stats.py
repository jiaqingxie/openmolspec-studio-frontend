"""Publication-ready validation statistics for the OpenSpec dataset.

Computes the seven validation analyses required for the Scientific Data
Technical Validation section and writes tables, figures and a machine-readable
summary under ``reports/publication/``.

The pipeline is deliberately non-destructive: records are flagged, never
silently removed, and every flagging rule is recorded explicitly in the output.

Example:
    python -m openmolspec.quality.stats --output reports/publication
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from openmolspec.core.processing import source_parts

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTLIER_MAD_MULTIPLIER = 10.0
OUTLIER_QUANTILES = (0.001, 0.999)

FIELD_UNITS = {
    "energy_per_atom": "Hartree/atom",
    "energy": "Hartree",
    "zpve": "Hartree",
    "homo": "Hartree",
    "lumo": "Hartree",
    "gap": "Hartree",
    "dipole_total": "Debye",
    "max_force_final": "Hartree/Bohr",
    "rms_force_final": "Hartree/Bohr",
    "min_freq": "cm^-1",
    "max_freq": "cm^-1",
    "nmr_max_abs_isotropic": "ppm",
    "nmr_min_isotropic": "ppm",
}

OUTLIER_FIELDS = (
    "energy_per_atom",
    "gap",
    "homo",
    "lumo",
    "dipole_total",
    "max_force_final",
    "min_freq",
    "max_freq",
    "nmr_max_abs_isotropic",
    "nmr_min_isotropic",
)

QUALITATIVE_COLORS = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
    "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
]

_SPECTRUM_SOURCES = (
    "NISTIR", "PAH", "PCQM4MV2", "PEPTIDE", "QM9", "RXN", "SDBS",
    "WILEYIR", "WILEYRAMAN", "ZINCV1", "ZINCV2",
)

# Map trajectory-report filenames / pickle stems to canonical source names.
TRAJECTORY_SOURCE_MAP = {
    "nist_ir": "NISTIR",
    "wiley_ir": "WILEYIR",
    "wiley_raman": "WILEYRAMAN",
    "zinc_v1": "ZINCV1",
    "zinc_v2": "ZINCV2",
    "pah": "PAH",
    "pcqm4mv2": "PCQM4MV2",
    "peptide": "PEPTIDE",
    "qm9": "QM9",
    "rxn": "RXN",
    "sdbs": "SDBS",
}


def _trajectory_source(stem: str) -> str:
    """Extract the canonical source name from a trajectory file stem."""

    key = stem.replace("openspec_", "").replace("_opt_trajectories", "")
    return TRAJECTORY_SOURCE_MAP.get(key, key.upper())


def _fig_style() -> None:
    """Apply a consistent, publication-oriented matplotlib style."""

    plt.rcParams.update(
        {
            "font.size": 10.5,
            "axes.titlesize": 11,
            "axes.labelsize": 10.5,
            "legend.fontsize": 9,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "axes.grid": True,
            "grid.alpha": 0.35,
            "grid.linestyle": "--",
            "figure.dpi": 110,
            "savefig.dpi": 300,
            "font.family": "DejaVu Sans",
        }
    )


# ---------------------------------------------------------------------------
# Feature extraction (with on-disk caching to avoid reloading huge pickles)
# ---------------------------------------------------------------------------


def _freq_summary(values: Any) -> Tuple[float, float, float, float]:
    """Return ``(n_imaginary, min_freq, max_freq, n_freq)`` for one record."""

    if values is None:
        return (np.nan, np.nan, np.nan, np.nan)
    try:
        array = np.asarray(values, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return (np.nan, np.nan, np.nan, np.nan)
    if array.ndim == 0 or array.size == 0 or not np.all(np.isfinite(array)):
        return (np.nan, np.nan, np.nan, np.nan)
    n_imaginary = int(np.sum(array < 0.0))
    return (n_imaginary, float(array.min()), float(array.max()), int(array.size))


def _scalar(values: Any) -> float:
    try:
        return float(np.asarray(values).reshape(-1)[0])
    except (TypeError, ValueError, IndexError):
        return np.nan


def _numeric_array_present(value: Any) -> bool:
    """Return true only for a non-empty finite numerical array.

    Missing object-column values are often represented as scalar ``NaN``;
    checking only ``value is not None`` incorrectly counts those as spectra.
    """

    if value is None:
        return False
    try:
        array = np.asarray(value)
        return bool(array.ndim > 0 and array.size > 0 and np.all(np.isfinite(array)))
    except (TypeError, ValueError):
        return False


def _extract_core_parallel(values: Sequence[Any], workers: int) -> List[Tuple[float, float, float, float]]:
    """Apply :func:`_freq_summary` over a column using a thread pool.

    numpy operations release the GIL, so threads give near-linear speedup for
    this element-wise reduction over per-record arrays.
    """

    if workers <= 1 or len(values) < 2:
        return [_freq_summary(value) for value in values]
    chunk_size = max(1, len(values) // (workers * 4))

    def _apply(chunk: Sequence[Any]) -> List[Tuple[float, float, float, float]]:
        return [_freq_summary(value) for value in chunk]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_apply, values[start:start + chunk_size])
            for start in range(0, len(values), chunk_size)
        ]
        results = [future.result() for future in futures]
    return [item for result in results for item in result]


def extract_core_features(frame: pd.DataFrame, manifest: Optional[pd.DataFrame] = None, workers: int = 1) -> pd.DataFrame:
    """Compute per-record derived features from the core frequency pickle.

    The returned frame has one row per record and is the lightweight table all
    subsequent analyses are based on.
    """

    sample_ids = frame["sample_id"].astype(str)
    atom_counts = frame["atom"].map(lambda values: int(len(values)) if values is not None else np.nan)

    freq_values = list(frame["freq"])
    summaries = _extract_core_parallel(freq_values, workers)
    summary_frame = pd.DataFrame(
        summaries, columns=["n_imaginary", "min_freq", "max_freq", "n_freq"]
    )

    derived = pd.DataFrame(
        {
            "sample_id": sample_ids,
            "n_atoms": atom_counts,
            "raman_present": frame["raman"].map(_numeric_array_present),
            "energy": frame["energy"].map(_scalar),
            "zpve": frame["zpve"].map(_scalar),
            "homo": frame["homo"].map(_scalar),
            "lumo": frame["lumo"].map(_scalar),
            "gap": frame["gap"].map(_scalar),
            "dipole_total": frame["dipole_total"].map(_scalar),
        }
    )
    derived = pd.concat([derived, summary_frame], axis=1)
    derived["energy_per_atom"] = derived["energy"] / derived["n_atoms"]
    derived["has_imaginary_frequency"] = derived["n_imaginary"].map(
        lambda value: bool(value > 0) if pd.notna(value) else False
    )

    if manifest is not None:
        mapping_columns = [column for column in (
            "sample_id", "source_dataset", "inchikey", "canonical_smiles",
            "scaffold", "label_status",
        ) if column in manifest.columns]
        mapping = manifest[mapping_columns].copy()
        mapping["sample_id"] = mapping["sample_id"].astype(str)
        derived = derived.merge(mapping, on="sample_id", how="left")
        derived["source_dataset"] = derived["source_dataset"].fillna(
            derived["sample_id"].map(lambda value: source_parts(value)["source_dataset"])
        )
    else:
        derived["source_dataset"] = derived["sample_id"].map(
            lambda value: source_parts(value)["source_dataset"]
        )
        derived["inchikey"] = None
        derived["canonical_smiles"] = None
        derived["scaffold"] = None
        derived["label_status"] = None

    return derived


def extract_trajectory_features(trajectory_dir: str) -> pd.DataFrame:
    """Collapse all trajectory pickles to one row per record (final frame)."""

    directory = Path(trajectory_dir)
    frames = []
    for path in sorted(directory.glob("*.pickle")):
        if not path.is_file():
            continue
        frame = pd.read_pickle(path)
        if "sample_id" not in frame.columns or "is_final" not in frame.columns:
            continue
        final = frame[frame["is_final"].fillna(False)].copy()
        if final.empty:
            continue
        keep = [column for column in (
            "sample_id", "n_steps", "is_converged", "max_force", "rms_force",
            "energy", "n_imaginary_frequencies", "minimum_frequency",
        ) if column in final.columns]
        final = final[keep]
        final["trajectory_source"] = _trajectory_source(path.stem)
        frames.append(final)
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    result["sample_id"] = result["sample_id"].astype(str)
    return result


def extract_nmr_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute per-record NMR summary features."""

    def summarize(values: Any) -> Tuple[float, float, int]:
        if values is None:
            return (np.nan, np.nan, 0)
        try:
            array = np.asarray(values, dtype=np.float64).reshape(-1)
        except (TypeError, ValueError):
            return (np.nan, np.nan, 0)
        if array.size == 0:
            return (np.nan, np.nan, 0)
        return (float(np.max(np.abs(array))), float(np.min(array)), int(array.size))

    rows = []
    for values in frame["isotropic"]:
        rows.append(summarize(values))
    summary = pd.DataFrame(rows, columns=["nmr_max_abs_isotropic", "nmr_min_isotropic", "n_nmr_atoms"])
    result = pd.DataFrame({"sample_id": frame["sample_id"].astype(str)})
    result = pd.concat([result, summary], axis=1)
    return result


# ---------------------------------------------------------------------------
# Analysis 1: geometry-optimization convergence rate
# ---------------------------------------------------------------------------


def convergence_table(opt_reports_dir: str, trajectory_features: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (per-source convergence table, per-source n_steps statistics)."""

    directory = Path(opt_reports_dir)
    rows = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "summary.json":
            continue
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
        source = report.get("source") or _trajectory_source(path.stem)
        rows.append(
            {
                "source": source,
                "input_logs": int(report.get("input_logs", np.nan)),
                "logs_with_trajectory": int(report.get("logs_with_trajectory", np.nan)),
                "converged_logs": int(report.get("converged_logs", np.nan)),
                "partial_logs": int(report.get("partial_logs", np.nan)),
                "failed_logs": int(report.get("failed_logs", np.nan)),
                "normal_termination_logs": int(report.get("normal_termination_logs", np.nan)),
            }
        )
    table = pd.DataFrame(rows)
    if not table.empty:
        table["convergence_rate"] = table["converged_logs"] / table["input_logs"].replace(0, np.nan)

    nsteps = []
    if not trajectory_features.empty:
        for source, group in trajectory_features.groupby("trajectory_source"):
            steps = group["n_steps"].dropna()
            if steps.empty:
                continue
            nsteps.append(
                {
                    "source": source,
                    "count": int(steps.size),
                    "mean": float(steps.mean()),
                    "std": float(steps.std()),
                    "median": float(steps.median()),
                    "p25": float(steps.quantile(0.25)),
                    "p75": float(steps.quantile(0.75)),
                    "p95": float(steps.quantile(0.95)),
                    "p99": float(steps.quantile(0.99)),
                    "max": float(steps.max()),
                }
            )
    nsteps_table = pd.DataFrame(nsteps)
    return table, nsteps_table


# ---------------------------------------------------------------------------
# Analysis 2: Frequency / Raman / NMR calculation success rates
# ---------------------------------------------------------------------------


def modality_success_table(
    source_statistics: pd.DataFrame,
    core_features: pd.DataFrame,
) -> pd.DataFrame:
    """Return per-source calculation success rates for freq / Raman / NMR."""

    table = source_statistics.copy()
    table = table.rename(
        columns={
            "records": "records",
            "frequency_success": "freq_success",
            "frequency_rate": "freq_rate",
            "nmr_success": "nmr_success",
            "nmr_rate": "nmr_rate",
            "tri_modal_records": "tri_modal",
            "tri_modal_rate": "tri_modal_rate",
        }
    )
    raman = (
        core_features.groupby("source_dataset")["raman_present"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "raman_success", "count": "raman_records"})
        .reset_index()
    )
    raman["raman_rate"] = raman["raman_success"] / raman["raman_records"].replace(0, np.nan)
    table = table.merge(raman, on="source_dataset", how="left")
    table["raman_rate"] = (table["raman_rate"] * 100).round(3)
    for column in ("freq_rate", "nmr_rate", "tri_modal_rate"):
        table[column] = pd.to_numeric(table[column], errors="coerce")
    return table


# ---------------------------------------------------------------------------
# Analysis 3: imaginary frequencies
# ---------------------------------------------------------------------------


def imaginary_frequency_table(core_features: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (per-source imaginary-frequency summary, global count distribution)."""

    rows = []
    for source, group in core_features.groupby("source_dataset"):
        counts = group["n_imaginary"].dropna()
        if counts.empty:
            rows.append({"source": source, "records": int(len(group)), "with_imaginary": 0,
                         "imaginary_fraction": 0.0, "n1": 0, "n2": 0, "n3plus": 0})
            continue
        with_imaginary = int((counts > 0).sum())
        rows.append(
            {
                "source": source,
                "records": int(len(group)),
                "with_imaginary": with_imaginary,
                "imaginary_fraction": with_imaginary / len(group),
                "n1": int((counts == 1).sum()),
                "n2": int((counts == 2).sum()),
                "n3plus": int((counts >= 3).sum()),
            }
        )
    table = pd.DataFrame(rows)

    all_counts = core_features["n_imaginary"].dropna().astype(int)
    max_shown = 10
    distribution = all_counts.value_counts().reindex(range(0, max_shown + 1), fill_value=0)
    rows = []
    for count, n_molecules in distribution.items():
        rows.append(
            {"n_imaginary_frequencies": int(count), "records": int(n_molecules),
             "fraction": float(n_molecules / len(all_counts)) if len(all_counts) else 0.0}
        )
    tail = int((all_counts > max_shown).sum())
    if tail:
        rows.append({"n_imaginary_frequencies": f">{max_shown}", "records": tail,
                     "fraction": float(tail / len(all_counts))})
    distribution_table = pd.DataFrame(rows)
    return table, distribution_table


# ---------------------------------------------------------------------------
# Analysis 4: extreme-value (outlier) detection
# ---------------------------------------------------------------------------


def _robust_statistics(values: pd.Series, field: str) -> Dict[str, Any]:
    finite = pd.to_numeric(values, errors="coerce").dropna()
    row: Dict[str, Any] = {
        "field": field,
        "unit": FIELD_UNITS.get(field, ""),
        "count": int(finite.size),
        "missing_rate": float(values.isna().mean()) if values.size else 1.0,
    }
    if finite.empty:
        row.update({"mean": np.nan, "std": np.nan, "median": np.nan, "MAD": np.nan,
                    "p1": np.nan, "p99": np.nan, "min": np.nan, "max": np.nan,
                    "flag_count": 0, "flag_rate": 0.0})
        return row
    median = float(finite.median())
    mad = float(np.median(np.abs(finite - median)))
    row.update(
        {
            "mean": float(finite.mean()),
            "std": float(finite.std()),
            "median": median,
            "MAD": mad,
            "p1": float(finite.quantile(0.01)),
            "p99": float(finite.quantile(0.99)),
            "min": float(finite.min()),
            "max": float(finite.max()),
        }
    )
    return row


def _flag_mask(values: pd.Series, median: float, mad: float) -> np.ndarray:
    finite = pd.to_numeric(values, errors="coerce").to_numpy(dtype=np.float64)
    lo, hi = np.nanquantile(finite, OUTLIER_QUANTILES)
    mask = np.zeros(finite.size, dtype=bool)
    scale = mad if mad > 0 else float(np.nanstd(finite))
    if scale and np.isfinite(scale):
        mask |= np.abs(finite - median) > OUTLIER_MAD_MULTIPLIER * scale
    mask |= (finite < lo) | (finite > hi)
    mask &= np.isfinite(finite)
    return mask


def outlier_analysis(
    core_features: pd.DataFrame,
    trajectory_features: pd.DataFrame,
    nmr_features: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (per-field robust statistics with flag counts, flagged records)."""

    features = core_features.copy()
    if not trajectory_features.empty:
        trajectory_summary = (
            trajectory_features[["sample_id", "max_force", "rms_force"]]
            .rename(columns={"max_force": "max_force_final", "rms_force": "rms_force_final"})
        )
        features = features.merge(trajectory_summary, on="sample_id", how="left")
    else:
        features["max_force_final"] = np.nan
        features["rms_force_final"] = np.nan
    if not nmr_features.empty:
        features = features.merge(nmr_features, on="sample_id", how="left")
    else:
        features["nmr_max_abs_isotropic"] = np.nan
        features["nmr_min_isotropic"] = np.nan

    rows = []
    flagged_records = []
    for field in OUTLIER_FIELDS:
        if field not in features.columns:
            continue
        values = features[field]
        stats = _robust_statistics(values, field)
        median, mad = stats["median"], stats["MAD"]
        if not np.isfinite(median) or np.isnan(mad):
            stats["flag_count"] = 0
            stats["flag_rate"] = 0.0
            stats["flag_rule"] = f"|x - median| > {OUTLIER_MAD_MULTIPLIER} * MAD or outside {OUTLIER_QUANTILES}"
            rows.append(stats)
            continue
        mask = _flag_mask(values, median, mad)
        stats["flag_count"] = int(mask.sum())
        stats["flag_rate"] = float(mask.mean())
        stats["flag_rule"] = f"|x - median| > {OUTLIER_MAD_MULTIPLIER} * MAD or outside {OUTLIER_QUANTILES}"
        rows.append(stats)
        if mask.any():
            flagged = pd.DataFrame(
                {
                    "sample_id": features["sample_id"].to_numpy()[mask],
                    "field": field,
                    "value": pd.to_numeric(values, errors="coerce").to_numpy(dtype=np.float64)[mask],
                }
            )
            flagged["reason"] = "MAD_OR_QUANTILE"
            flagged_records.append(flagged)

    stats_table = pd.DataFrame(rows)
    flagged_table = (
        pd.concat(flagged_records, ignore_index=True)
        if flagged_records
        else pd.DataFrame(columns=["sample_id", "field", "value", "reason"])
    )
    return stats_table, flagged_table


# ---------------------------------------------------------------------------
# Analysis 5: duplicates and conformer statistics
# ---------------------------------------------------------------------------


def duplicate_conformer_tables(
    core_features: pd.DataFrame,
    dedup_summary_path: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (dedup summary table, conformer-count distribution, per-source conformers)."""

    with open(dedup_summary_path, encoding="utf-8") as handle:
        prior_dedup = json.load(handle)
    # Derive release statistics from the current feature table. The external
    # summary is retained only for backward compatibility and may belong to an
    # earlier extraction run.
    canonical_counts = (
        core_features["canonical_smiles"].dropna().value_counts()
        if "canonical_smiles" in core_features else pd.Series(dtype=np.int64)
    )
    inchikey_counts = (
        core_features["inchikey"].dropna().value_counts()
        if "inchikey" in core_features else pd.Series(dtype=np.int64)
    )
    scaffold_counts = (
        core_features["scaffold"].dropna().value_counts()
        if "scaffold" in core_features else pd.Series(dtype=np.int64)
    )
    cross_source = (
        core_features.dropna(subset=["canonical_smiles"])
        .groupby("canonical_smiles")["source_dataset"].nunique().gt(1).sum()
        if {"canonical_smiles", "source_dataset"}.issubset(core_features.columns)
        else prior_dedup.get("cross_source_canonical_overlap_records", 0)
    )
    dedup = {
        "records": int(len(core_features)),
        "exact_record_duplicate_records": int(core_features["sample_id"].duplicated(keep=False).sum()),
        "canonical_smiles_duplicate_records": (
            int(canonical_counts[canonical_counts > 1].sum()) if not canonical_counts.empty
            else prior_dedup.get("canonical_smiles_duplicate_records", 0)
        ),
        "inchikey_duplicate_records": int(inchikey_counts[inchikey_counts > 1].sum()),
        "scaffold_duplicate_records": (
            int(scaffold_counts[scaffold_counts > 1].sum()) if not scaffold_counts.empty
            else prior_dedup.get("scaffold_duplicate_records", 0)
        ),
        "cross_source_canonical_overlap_records": int(cross_source),
        "prior_summary_records": prior_dedup.get("records"),
    }
    dedup_rows = [
        {"metric": "records", "count": dedup.get("records")},
        {"metric": "exact_record_duplicates", "count": dedup.get("exact_record_duplicate_records")},
        {"metric": "canonical_smiles_duplicate_records", "count": dedup.get("canonical_smiles_duplicate_records")},
        {"metric": "inchikey_duplicate_records", "count": dedup.get("inchikey_duplicate_records")},
        {"metric": "scaffold_duplicate_records", "count": dedup.get("scaffold_duplicate_records")},
        {"metric": "cross_source_canonical_overlap_records", "count": dedup.get("cross_source_canonical_overlap_records")},
    ]
    dedup_table = pd.DataFrame(dedup_rows)

    identity = core_features.dropna(subset=["inchikey"]).copy()
    per_molecule = identity.groupby("inchikey")["sample_id"].count()
    distribution = per_molecule.value_counts().sort_index()
    max_shown = 10
    rows = []
    for count in range(1, max_shown + 1):
        rows.append(
            {"conformers": count, "molecules": int(distribution.get(count, 0)),
             "records": int(count * distribution.get(count, 0))}
        )
    tail_molecules = int(distribution[distribution.index > max_shown].sum())
    tail_records = int((distribution[distribution.index > max_shown] * distribution[distribution.index > max_shown].index).sum())
    if tail_molecules:
        rows.append({"conformers": f">{max_shown}", "molecules": tail_molecules, "records": tail_records})
    conformer_table = pd.DataFrame(rows)

    by_source_rows = []
    for source, group in identity.groupby("source_dataset"):
        counts = group.groupby("inchikey")["sample_id"].count()
        by_source_rows.append(
            {
                "source": source,
                "records": int(len(group)),
                "unique_molecules": int(counts.size),
                "molecules_with_multiple_conformers": int((counts > 1).sum()),
                "max_conformers": int(counts.max()) if counts.size else 0,
                "mean_conformers": float(counts.mean()) if counts.size else np.nan,
            }
        )
    conformer_by_source = pd.DataFrame(by_source_rows)
    return dedup_table, conformer_table, conformer_by_source


# ---------------------------------------------------------------------------
# Analysis 6: per-source success and anomaly rates
# ---------------------------------------------------------------------------


def source_success_anomaly_table(
    convergence: pd.DataFrame,
    modality: pd.DataFrame,
    imaginary: pd.DataFrame,
    outlier_rate_by_source: pd.DataFrame,
    record_qc: pd.DataFrame,
) -> pd.DataFrame:
    """Merge the per-source tables into one combined summary."""

    table = modality.rename(columns={"source_dataset": "source"})

    if not convergence.empty:
        convergence_summary = convergence[["source", "convergence_rate"]].copy()
        convergence_summary["source"] = convergence_summary["source"].str.upper()
        table = table.merge(convergence_summary, on="source", how="left")

    if not imaginary.empty:
        imaginary_summary = imaginary[["source", "imaginary_fraction"]].copy()
        imaginary_summary["source"] = imaginary_summary["source"].str.upper()
        table = table.merge(imaginary_summary, on="source", how="left")

    if outlier_rate_by_source is not None and not outlier_rate_by_source.empty:
        table = table.merge(outlier_rate_by_source, on="source", how="left")

    if not record_qc.empty:
        qc = record_qc.copy()
        qc["source"] = qc["sample_id"].map(
            lambda value: source_parts(value)["source_dataset"]
        ).str.upper()
        qc_rate = qc.groupby("source")["qc_pass"].mean().rename("qc_pass_rate").reset_index()
        table = table.merge(qc_rate, on="source", how="left")

    return table


# ---------------------------------------------------------------------------
# Analysis 7: element / molecular-weight / heavy-atom / conformer distributions
# ---------------------------------------------------------------------------


def element_coverage(descriptors: pd.DataFrame) -> pd.DataFrame:
    """Return molecules-per-element coverage from the descriptor cache."""

    counts: Dict[str, int] = {}
    for value in descriptors["elements"].dropna():
        for element in str(value).split(","):
            element = element.strip()
            if element:
                counts[element] = counts.get(element, 0) + 1
    table = pd.DataFrame(
        sorted(counts.items(), key=lambda item: -item[1]),
        columns=["element", "molecules"],
    )
    table["fraction"] = table["molecules"] / len(descriptors)
    return table


def _quantile_table(values: pd.Series, name: str) -> pd.DataFrame:
    finite = pd.to_numeric(values, errors="coerce").dropna()
    row = {
        "field": name,
        "count": int(finite.size),
        "mean": float(finite.mean()),
        "std": float(finite.std()),
        "median": float(finite.median()),
        "p1": float(finite.quantile(0.01)),
        "p5": float(finite.quantile(0.05)),
        "p25": float(finite.quantile(0.25)),
        "p75": float(finite.quantile(0.75)),
        "p95": float(finite.quantile(0.95)),
        "p99": float(finite.quantile(0.99)),
        "min": float(finite.min()),
        "max": float(finite.max()),
    }
    return pd.DataFrame([row])


def molecular_distribution_tables(descriptors: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Return quantile tables for molecular-weight / heavy-atom / atom-count."""

    return {
        "molecular_weight_distribution": _quantile_table(descriptors["molecular_weight"], "molecular_weight"),
        "heavy_atom_distribution": _quantile_table(descriptors["heavy_atom_count"], "heavy_atom_count"),
        "atom_count_distribution": _quantile_table(descriptors["atom_count"], "atom_count"),
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _save(fig: plt.Figure, output_dir: Path, name: str) -> None:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(figure_dir / name, dpi=300, bbox_inches="tight")
    plt.close(fig)


def figure_convergence(table: pd.DataFrame, output_dir: Path) -> None:
    """Plot geometry-optimization convergence statistics."""
    if table.empty:
        return
    _fig_style()
    fig, axis = plt.subplots(figsize=(9, 4.2))
    order = table.sort_values("convergence_rate", ascending=True)
    x = np.arange(len(order))
    axis.bar(x, order["converged_logs"], color=QUALITATIVE_COLORS[0], label="Converged")
    axis.bar(x, order["partial_logs"], bottom=order["converged_logs"], color=QUALITATIVE_COLORS[1], label="Partial")
    axis.bar(
        x,
        order["failed_logs"],
        bottom=order["converged_logs"] + order["partial_logs"],
        color=QUALITATIVE_COLORS[3],
        label="Failed",
    )
    axis.set_xticks(x)
    axis.set_xticklabels(order["source"], rotation=45, ha="right")
    axis.set_ylabel("Logs")
    axis.set_title("Geometry-optimization outcome by source")
    axis.legend(loc="upper right")
    _save(fig, output_dir, "fig_convergence_by_source.png")


def figure_modality_success(table: pd.DataFrame, output_dir: Path) -> None:
    """Plot extraction success for each spectroscopy modality."""
    if table.empty:
        return
    _fig_style()
    fig, axis = plt.subplots(figsize=(9, 4.2))
    order = table.sort_values("records", ascending=True)
    source_column = "source" if "source" in order.columns else "source_dataset"
    x = np.arange(len(order))
    width = 0.21
    fields = [("freq_rate", "Frequency"), ("raman_rate", "Raman"), ("nmr_rate", "NMR"), ("tri_modal_rate", "Tri-modal")]
    for index, (column, label) in enumerate(fields):
        offset = (index - 1.5) * width
        axis.bar(x + offset, order[column], width=width, color=QUALITATIVE_COLORS[index], label=label)
    axis.set_xticks(x)
    axis.set_xticklabels(order[source_column], rotation=45, ha="right")
    axis.set_ylabel("Success rate (%)")
    axis.set_ylim(0, 100)
    axis.set_title("Calculation success rates by source")
    axis.legend(loc="lower left", ncol=2)
    _save(fig, output_dir, "fig_modality_success_by_source.png")


def figure_imaginary_frequency(core_features: pd.DataFrame, output_dir: Path) -> None:
    """Plot the distribution of imaginary vibrational frequencies."""
    _fig_style()
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    counts = core_features["n_imaginary"].dropna().astype(int)
    max_shown = 8
    hist_counts = counts.clip(upper=max_shown).value_counts().sort_index()
    labels = [str(value) if value < max_shown else f">={max_shown}" for value in hist_counts.index]
    axes[0].bar(labels, hist_counts.values, color=QUALITATIVE_COLORS[0])
    axes[0].set_xlabel("Number of imaginary frequencies")
    axes[0].set_ylabel("Records")
    axes[0].set_title("Imaginary-frequency count distribution")
    axes[0].tick_params(axis="x", rotation=45)

    min_freq = core_features["min_freq"].dropna()
    axes[1].hist(min_freq, bins=80, color=QUALITATIVE_COLORS[1])
    axes[1].set_xlabel("Minimum frequency (cm$^{-1}$)")
    axes[1].set_ylabel("Records")
    axes[1].set_title("Minimum-frequency distribution")
    _save(fig, output_dir, "fig_imaginary_frequency_distribution.png")


def figure_outlier_detection(
    core_features: pd.DataFrame,
    trajectory_features: pd.DataFrame,
    nmr_features: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Plot the numerical outlier summary."""
    _fig_style()
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5))

    descriptors_path = None
    if not core_features.empty:
        valid = core_features.dropna(subset=["energy_per_atom", "n_atoms"])
        median = valid["energy_per_atom"].median()
        mad = np.median(np.abs(valid["energy_per_atom"] - median))
        lo, hi = np.nanquantile(valid["energy_per_atom"], OUTLIER_QUANTILES)
        flagged = (np.abs(valid["energy_per_atom"] - median) > OUTLIER_MAD_MULTIPLIER * (mad or 1e-6)) | \
                  (valid["energy_per_atom"] < lo) | (valid["energy_per_atom"] > hi)
        axes[0, 0].scatter(
            valid["n_atoms"], valid["energy_per_atom"], s=3, alpha=0.25,
            color=QUALITATIVE_COLORS[0], label="All records",
        )
        axes[0, 0].scatter(
            valid.loc[flagged, "n_atoms"], valid.loc[flagged, "energy_per_atom"],
            s=6, color=QUALITATIVE_COLORS[3], label="Flagged",
        )
    axes[0, 0].set_xlabel("Number of atoms")
    axes[0, 0].set_ylabel("Energy per atom (Hartree)")
    axes[0, 0].set_title("Electronic energy per atom")
    axes[0, 0].legend(loc="upper left", markerscale=3)

    if not trajectory_features.empty:
        forces = pd.to_numeric(trajectory_features["max_force"], errors="coerce").dropna()
        axes[0, 1].hist(forces, bins=80, color=QUALITATIVE_COLORS[1])
        axes[0, 1].set_xlabel("Final-frame max force (Hartree/Bohr)")
        axes[0, 1].set_ylabel("Records")
        axes[0, 1].set_title("Final-frame maximum force")
        axes[0, 1].set_xscale("log")

    min_freq = core_features["min_freq"].dropna()
    axes[1, 0].hist(min_freq, bins=100, color=QUALITATIVE_COLORS[0])
    axes[1, 0].set_xlabel("Minimum frequency (cm$^{-1}$)")
    axes[1, 0].set_ylabel("Records")
    axes[1, 0].set_title("Extreme minimum frequencies")

    if not nmr_features.empty:
        isotropic = pd.to_numeric(nmr_features["nmr_max_abs_isotropic"], errors="coerce").dropna()
        axes[1, 1].hist(isotropic, bins=80, color=QUALITATIVE_COLORS[2])
        axes[1, 1].set_xlabel("Max |isotropic| per molecule (ppm)")
        axes[1, 1].set_ylabel("Records")
        axes[1, 1].set_title("NMR isotropic extreme values")
        axes[1, 1].set_xscale("log")

    _save(fig, output_dir, "fig_outlier_detection.png")


def figure_conformer_distribution(conformer_table: pd.DataFrame, output_dir: Path) -> None:
    """Plot the conformer-count distribution across molecules."""
    if conformer_table.empty:
        return
    _fig_style()
    fig, axis = plt.subplots(figsize=(8, 4))
    axis.bar(conformer_table["conformers"].astype(str), conformer_table["molecules"], color=QUALITATIVE_COLORS[0])
    axis.set_xlabel("Records per molecule (conformers)")
    axis.set_ylabel("Molecules")
    axis.set_title("Conformer-count distribution")
    axis.tick_params(axis="x", rotation=45)
    _save(fig, output_dir, "fig_conformer_distribution.png")


def figure_molecular_distributions(
    descriptors: pd.DataFrame,
    element_table: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Plot molecular size and composition distributions."""
    _fig_style()
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5))

    axes[0, 0].bar(element_table["element"], element_table["molecules"], color=QUALITATIVE_COLORS[0])
    axes[0, 0].set_xlabel("Element")
    axes[0, 0].set_ylabel("Molecules")
    axes[0, 0].set_title("Element coverage")
    axes[0, 0].tick_params(axis="x", rotation=45)

    axes[0, 1].hist(descriptors["molecular_weight"].dropna(), bins=80, color=QUALITATIVE_COLORS[1])
    axes[0, 1].set_xlabel("Molecular weight (g/mol)")
    axes[0, 1].set_ylabel("Molecules")
    axes[0, 1].set_title("Molecular-weight distribution")

    axes[1, 0].hist(descriptors["heavy_atom_count"].dropna(), bins=60, color=QUALITATIVE_COLORS[2])
    axes[1, 0].set_xlabel("Heavy-atom count")
    axes[1, 0].set_ylabel("Molecules")
    axes[1, 0].set_title("Heavy-atom distribution")

    axes[1, 1].hist(descriptors["atom_count"].dropna(), bins=60, color=QUALITATIVE_COLORS[0])
    axes[1, 1].set_xlabel("Total atom count")
    axes[1, 1].set_ylabel("Molecules")
    axes[1, 1].set_title("Atom-count distribution")

    _save(fig, output_dir, "fig_molecular_distributions.png")


def figure_source_rates_heatmap(table: pd.DataFrame, output_dir: Path) -> None:
    """Heatmap of per-source success/anomaly rates."""

    columns = [column for column in (
        "freq_rate", "raman_rate", "nmr_rate", "tri_modal_rate",
        "convergence_rate", "imaginary_fraction", "qc_pass_rate",
    ) if column in table.columns]
    if not columns or table.empty:
        return
    _fig_style()
    fig, axis = plt.subplots(figsize=(9, 4.5))
    heat = table[["source"] + columns].copy()
    # Modality rates are percentages; the remaining columns are 0-1 fractions.
    fraction_columns = {"convergence_rate", "imaginary_fraction", "qc_pass_rate"}
    for column in columns:
        heat[column] = pd.to_numeric(heat[column], errors="coerce")
        if column in fraction_columns:
            heat[column] = heat[column] * 100.0
    labels = {"freq_rate": "Freq success", "raman_rate": "Raman success",
              "nmr_rate": "NMR success", "tri_modal_rate": "Tri-modal",
              "convergence_rate": "Opt converged", "imaginary_fraction": "Imaginary freq",
              "qc_pass_rate": "QC pass"}
    axis.set_xticks(range(len(columns)))
    axis.set_xticklabels([labels.get(column, column) for column in columns], rotation=35, ha="right")
    axis.set_yticks(range(len(heat)))
    axis.set_yticklabels(heat["source"])
    data = heat[columns].to_numpy(dtype=np.float64)
    image = axis.imshow(np.ma.masked_invalid(data), cmap="YlGnBu", aspect="auto", vmin=0, vmax=100)
    for row in range(data.shape[0]):
        for col in range(data.shape[1]):
            if np.isfinite(data[row, col]):
                axis.text(col, row, f"{data[row, col]:.0f}", ha="center", va="center", fontsize=7)
    fig.colorbar(image, ax=axis, label="Rate (%)")
    axis.set_title("Per-source success and anomaly rates")
    _save(fig, output_dir, "fig_source_rates_heatmap.png")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _write_table(frame: pd.DataFrame, output_dir: Path, name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / f"{name}.csv", index=False)


def run(
    *,
    pickle_path: str,
    nmr_pickle_path: str,
    manifest_path: str,
    trajectory_dir: str,
    descriptors_path: str,
    opt_reports_dir: str,
    dedup_summary_path: str,
    source_statistics_path: str,
    record_qc_path: str,
    output: str,
    cache_dir: str,
    workers: int,
) -> Dict[str, Any]:
    """Run the full validation-statistics pipeline and return the summary."""

    output_dir = Path(output)
    cache_dir_path = Path(cache_dir)
    cache_dir_path.mkdir(parents=True, exist_ok=True)

    core_cache = cache_dir_path / "core_features.parquet"
    trajectory_cache = cache_dir_path / "trajectory_features.parquet"
    nmr_cache = cache_dir_path / "nmr_features.parquet"

    # --- core features ------------------------------------------------------
    if core_cache.exists():
        core_features = pd.read_parquet(core_cache)
    else:
        manifest = pd.read_parquet(manifest_path) if Path(manifest_path).exists() else None
        core_features = extract_core_features(pd.read_pickle(pickle_path), manifest=manifest, workers=workers)
        core_features.to_parquet(core_cache, index=False)

    # --- trajectory features ------------------------------------------------
    if trajectory_cache.exists():
        trajectory_features = pd.read_parquet(trajectory_cache)
    else:
        trajectory_features = extract_trajectory_features(trajectory_dir)
        trajectory_features.to_parquet(trajectory_cache, index=False)

    # --- NMR features -------------------------------------------------------
    if nmr_cache.exists():
        nmr_features = pd.read_parquet(nmr_cache)
    else:
        nmr_features = extract_nmr_features(pd.read_pickle(nmr_pickle_path))
        nmr_features.to_parquet(nmr_cache, index=False)

    # --- analyses -----------------------------------------------------------
    convergence, nsteps = convergence_table(opt_reports_dir, trajectory_features)
    modality = modality_success_table(
        pd.read_parquet(source_statistics_path),
        core_features,
    )
    imaginary, imaginary_distribution = imaginary_frequency_table(core_features)
    outlier_stats, outlier_records = outlier_analysis(core_features, trajectory_features, nmr_features)
    dedup_table, conformer_distribution, conformer_by_source = duplicate_conformer_tables(
        core_features, dedup_summary_path
    )
    record_qc = (
        pd.read_parquet(record_qc_path)
        if Path(record_qc_path).exists()
        else pd.DataFrame()
    )
    if not outlier_records.empty:
        flagged_ids = set(outlier_records["sample_id"].unique())
        core_flags = core_features.assign(
            is_outlier=core_features["sample_id"].isin(flagged_ids)
        )
        outlier_rate_by_source = (
            core_flags.groupby("source_dataset")["is_outlier"]
            .mean()
            .rename("outlier_rate")
            .reset_index()
        )
        outlier_rate_by_source["source"] = outlier_rate_by_source["source_dataset"].str.upper()
        outlier_rate_by_source = outlier_rate_by_source[["source", "outlier_rate"]]
    else:
        outlier_rate_by_source = None
    combined = source_success_anomaly_table(
        convergence, modality, imaginary, outlier_rate_by_source, record_qc
    )
    descriptors = pd.read_parquet(descriptors_path)
    element_table = element_coverage(descriptors)
    distributions = molecular_distribution_tables(descriptors)

    # --- write tables -------------------------------------------------------
    _write_table(convergence, output_dir, "convergence_by_source")
    _write_table(nsteps, output_dir, "n_steps_stats")
    _write_table(modality, output_dir, "modality_success_by_source")
    _write_table(imaginary, output_dir, "imaginary_frequency_by_source")
    _write_table(imaginary_distribution, output_dir, "imaginary_frequency_count_distribution")
    _write_table(outlier_stats, output_dir, "outlier_summary")
    output_dir.mkdir(parents=True, exist_ok=True)
    outlier_records.to_parquet(output_dir / "outlier_records.parquet", index=False)
    _write_table(dedup_table, output_dir, "duplicate_summary")
    _write_table(conformer_distribution, output_dir, "conformer_count_distribution")
    _write_table(conformer_by_source, output_dir, "conformer_by_source")
    _write_table(combined, output_dir, "source_success_anomaly")
    _write_table(element_table, output_dir, "element_coverage")
    for name, table in distributions.items():
        _write_table(table, output_dir, name)

    # --- figures ------------------------------------------------------------
    figure_convergence(convergence, output_dir)
    figure_modality_success(modality, output_dir)
    figure_imaginary_frequency(core_features, output_dir)
    figure_outlier_detection(core_features, trajectory_features, nmr_features, output_dir)
    figure_conformer_distribution(conformer_distribution, output_dir)
    figure_molecular_distributions(descriptors, element_table, output_dir)
    figure_source_rates_heatmap(combined, output_dir)

    # --- summary ------------------------------------------------------------
    multi_conformer_molecules = 0
    if not conformer_distribution.empty:
        numeric = pd.to_numeric(conformer_distribution["conformers"], errors="coerce")
        multi_conformer_molecules = int(
            conformer_distribution.loc[numeric > 1, "molecules"].sum()
            + conformer_distribution.loc[numeric.isna(), "molecules"].sum()
        )
    summary = {
        "records": int(len(core_features)),
        "raman_records": int(core_features["raman_present"].sum()),
        "records_with_imaginary_frequencies": int(core_features["has_imaginary_frequency"].sum()),
        "unique_inchikey": int(core_features["inchikey"].nunique()) if "inchikey" in core_features else None,
        "molecules_with_multiple_conformers": multi_conformer_molecules,
        "source_count": int(core_features["source_dataset"].nunique()),
        "convergence_rate_global": (
            float(convergence["converged_logs"].sum() / convergence["input_logs"].sum())
            if not convergence.empty and convergence["input_logs"].sum() else None
        ),
        "freq_success_global": (
            float(modality["freq_success"].sum() / modality["records"].sum() * 100.0)
            if not modality.empty else None
        ),
        "raman_success_global": (
            float(modality["raman_success"].sum() / modality["records"].sum() * 100.0)
            if not modality.empty else None
        ),
        "nmr_success_global": (
            float(modality["nmr_success"].sum() / modality["records"].sum() * 100.0)
            if not modality.empty else None
        ),
        "outlier_flag_records": int(outlier_records["sample_id"].nunique()) if not outlier_records.empty else 0,
        "outlier_rule": f"|x - median| > {OUTLIER_MAD_MULTIPLIER} * MAD or outside {OUTLIER_QUANTILES}",
    }
    with open(output_dir / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)
    return summary


def main() -> None:
    """Run the stats command-line workflow."""
    parser = argparse.ArgumentParser(description="Compute OpenSpec publication validation statistics")
    parser.add_argument("--output", default="reports/publication")
    parser.add_argument("--pickle", default="artifacts/processed/openspec.pickle")
    parser.add_argument(
        "--nmr-pickle", default="artifacts/processed/openspec_nmr.pickle"
    )
    parser.add_argument("--manifest", default="datasets/openspec_manifest.parquet")
    parser.add_argument("--trajectory-dir", default="trajectory_outputs")
    parser.add_argument("--descriptors", default="reports/analysis/chemical_descriptors.parquet")
    parser.add_argument("--opt-reports", default="reports/opt_trajectories")
    parser.add_argument("--dedup-summary", default="reports/dedup/dedup_summary.json")
    parser.add_argument("--source-statistics", default="reports/analysis/source_statistics.parquet")
    parser.add_argument("--record-qc", default="reports/internal_qc/record_qc.parquet")
    parser.add_argument("--cache-dir", default="tmp/validation")
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()

    summary = run(
        pickle_path=args.pickle,
        nmr_pickle_path=args.nmr_pickle,
        manifest_path=args.manifest,
        trajectory_dir=args.trajectory_dir,
        descriptors_path=args.descriptors,
        opt_reports_dir=args.opt_reports,
        dedup_summary_path=args.dedup_summary,
        source_statistics_path=args.source_statistics,
        record_qc_path=args.record_qc,
        output=args.output,
        cache_dir=args.cache_dir,
        workers=args.workers,
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
