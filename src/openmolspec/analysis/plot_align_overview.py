"""Draw the main OpenMolSpec Align overview figure.

The figure compares OpenMolSpec with representative public molecular
datasets and summarizes the strict Align catalog. Total atom counts include
hydrogen and are never inferred from implicit-H SMILES. Functional-group
prevalence is computed as non-exclusive molecule-level SMARTS presence.

Example
-------
python -m openmolspec.analysis.plot_align_overview
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter
from rdkit import Chem


DATASETS = [
    "QM9S",
    "QMe14S",
    "ChEMBL IR/Raman",
    "SQuIRL",
    "Multimodal Spec.",
    "SpecX Large",
    "OpenMolSpec",
]
YEARS = {
    "QM9S": 2023,
    "QMe14S": 2025,
    "ChEMBL IR/Raman": 2025,
    "SQuIRL": 2026,
    "Multimodal Spec.": 2024,
    "SpecX Large": 2026,
    "OpenMolSpec": 2026,
}

FIDELITY_LEVELS = [
    "Classical /\nempirical",
    "Mixed-\nfidelity",
    "GGA /\nDZ",
    "Hybrid /\nTZ",
    "Hybrid / TZ\n+ diffuse",
    "RSH /\naug-TZ",
]
DATASET_FIDELITY = {
    "Multimodal Spec.": 1,
    "SpecX Large": 2,
    "ChEMBL IR/Raman": 3,
    "QM9S": 4,
    "QMe14S": 4,
    "OpenMolSpec": 5,
    "SQuIRL": 6,
}
FIDELITY_PROTOCOLS = {
    "Multimodal Spec.": "GAFF/LAMMPS IR; MestReNova NMR; predicted MS/MS",
    "SpecX Large": "GAFF/LAMMPS IR; MestReNova NMR; DFT Raman; TD-DFT UV; CFM-ID MS/MS",
    "ChEMBL IR/Raman": "PBEPBE/6-31G",
    "QM9S": "B3LYP/def-TZVP",
    "QMe14S": "B3LYP/TZVP",
    "OpenMolSpec": "B3LYP-D3(BJ)/6-311+G(d,p) vibration; OPBE/6-311+G(2d,p) NMR",
    "SQuIRL": "ωB97X-D/aug-cc-pVTZ IR",
}

# Approximate headline values from the comparison used by the repository.
# OpenMolSpec counts are replaced at runtime by the frozen local release.
MOLECULE_COUNTS = {
    "QM9S": 133_885,
    "QMe14S": 186_102,
    "ChEMBL IR/Raman": 220_000,
    "SQuIRL": 133_885,
    # Alberts et al. (2024), all listed spectral modalities available.
    "Multimodal Spec.": 794_403,
    # SpecX (2026): Large benchmark split, not the 1.70M filtered pool.
    "SpecX Large": 994_386,
}
SPECTRAL_MODALITIES = ["IR", "Raman", "NMR", "MS", "UV–Vis"]
SPECTRAL_COVERAGE = {
    "QM9S": ("●", "●", "–", "–", "–"),
    "QMe14S": ("●", "●", "◐", "–", "–"),
    "ChEMBL IR/Raman": ("●", "●", "–", "–", "–"),
    "SQuIRL": ("●", "–", "–", "–", "–"),
    "Multimodal Spec.": ("○", "–", "○", "○", "–"),
    "SpecX Large": ("○", "●", "○", "○", "○"),
    "OpenMolSpec": ("●", "●", "●", "–", "–"),
}

ELEMENT_SYMBOLS = {
    1: "H",
    5: "B",
    6: "C",
    7: "N",
    8: "O",
    9: "F",
    13: "Al",
    14: "Si",
    15: "P",
    16: "S",
    17: "Cl",
    32: "Ge",
    33: "As",
    34: "Se",
    35: "Br",
    53: "I",
}
ELEMENT_ORDER = [
    "H", "B", "C", "N", "O", "F", "Al", "Si",
    "P", "S", "Cl", "Br", "As", "Se", "I", "Ge",
]

# Deliberately broad, interpretable groups for dataset-composition reporting.
# Categories are non-exclusive: one molecule can contribute to several bars.
FUNCTIONAL_GROUP_SMARTS = {
    "Aromatic": "[a;r]",
    "Carbonyl": "[CX3]=[OX1]",
    "Amine": "[NX3;!$([N][C,S,P]=[O,S,N]);!$([N+])]",
    "Ether": "[OD2;!$([O][C,S,P]=O)]([#6])[#6]",
    "Amide": "[NX3][CX3](=[OX1])",
    "Halogen": "[F,Cl,Br,I]",
    "Hydroxyl": "[OX2H;!$([O][C,S,P]=O)]",
    "Ester": "[CX3](=[OX1])[OX2][#6]",
    "Carboxylic acid": "[CX3](=[OX1])[OX2H1]",
    "Nitrile": "[CX2]#[NX1]",
    "Sulfonyl": "[SX4](=[OX1])(=[OX1])",
    "Nitro": "[$([NX3+](=O)[O-]),$([NX3](=O)=O)]",
    "Thiol": "[SX2H]",
    "Phosphoryl": "[PX4](=[OX1])",
}

BLUE = "#2F6FDB"
LIGHT_BLUE = "#A9C5F5"
GRAY = "#A9B9CC"
DARK_GRAY = "#536273"
GRID = "#D7DEE8"
TEXT = "#263442"


def repository_root() -> Path:
    """Return the repository root for the standard ``src`` layout."""

    return Path(__file__).resolve().parents[3]


def resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def compact_count(value: float, _position: float | None = None) -> str:
    if value >= 1_000_000:
        millions = value / 1_000_000
        return f"{millions:.2f}M" if millions < 10 else f"{millions:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def _read_release_counts(catalog_summary: Path, dataset_summary: Path) -> tuple[int, int]:
    catalog = json.loads(catalog_summary.read_text(encoding="utf-8"))
    dataset = json.loads(dataset_summary.read_text(encoding="utf-8"))
    return int(catalog["align_unique_molecules"]), int(dataset["trajectory_frames"])


def _element_string(atomic_numbers: np.ndarray) -> str:
    symbols = [ELEMENT_SYMBOLS.get(int(number), f"Z{int(number)}") for number in np.unique(atomic_numbers)]
    order = {symbol: index for index, symbol in enumerate(ELEMENT_ORDER)}
    symbols.sort(key=lambda symbol: (order.get(symbol, len(order)), symbol))
    return ",".join(symbols)


def build_align_geometry_cache(
    align_path: Path,
    frequency_index_path: Path,
    frequency_payload_dir: Path,
    cache_path: Path,
) -> pd.DataFrame:
    """Build molecule-level atom statistics from matched Align geometries."""

    align = pd.read_parquet(
        align_path,
        columns=["inchikey", "frequency_sample_id"],
    )
    frequency_index = pd.read_parquet(
        frequency_index_path,
        columns=["sample_id", "shard", "row_in_shard"],
    )
    if frequency_index["sample_id"].duplicated().any():
        raise ValueError("frequency payload index contains duplicate sample_id values")

    frame = align.merge(
        frequency_index,
        left_on="frequency_sample_id",
        right_on="sample_id",
        how="left",
        validate="one_to_one",
    )
    missing = int(frame["shard"].isna().sum())
    if missing:
        raise ValueError(f"{missing:,} Align molecules are absent from the frequency payload index")

    frame = frame.reset_index(drop=True)
    total_atoms = np.zeros(len(frame), dtype=np.int32)
    heavy_atoms = np.zeros(len(frame), dtype=np.int32)
    elements = np.empty(len(frame), dtype=object)

    grouped = frame.groupby("shard", sort=True, observed=True)
    for shard_number, (shard, group) in enumerate(grouped, start=1):
        h5_path = frequency_payload_dir / f"{shard}.h5"
        if not h5_path.exists():
            raise FileNotFoundError(h5_path)
        rows = group["row_in_shard"].to_numpy(dtype=np.int64, copy=False)
        positions = group.index.to_numpy(dtype=np.int64, copy=False)
        with h5py.File(h5_path, "r") as handle:
            atomic_group = handle["arrays/atomic_numbers"]
            offsets = np.asarray(atomic_group["offsets"], dtype=np.int64)
            values = np.asarray(atomic_group["values"], dtype=np.int32)

        for position, row in zip(positions, rows):
            atomic_numbers = values[offsets[row]:offsets[row + 1]]
            if atomic_numbers.size == 0:
                raise ValueError(f"empty atomic-number array for {frame.at[position, 'frequency_sample_id']}")
            total_atoms[position] = atomic_numbers.size
            heavy_atoms[position] = int(np.count_nonzero(atomic_numbers > 1))
            elements[position] = _element_string(atomic_numbers)

        if shard_number % 20 == 0 or shard_number == grouped.ngroups:
            print(f"[Align composition] processed {shard_number}/{grouped.ngroups} frequency shards")

    result = pd.DataFrame({
        "inchikey": frame["inchikey"],
        "total_atom_count": total_atoms,
        "heavy_atom_count": heavy_atoms,
        "elements": elements,
    })
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_path, index=False)
    return result


def load_align_composition(
    align_path: Path,
    frequency_index_path: Path,
    frequency_payload_dir: Path,
    cache_path: Path,
    rebuild_cache: bool,
) -> pd.DataFrame:
    expected_rows = pd.read_parquet(align_path, columns=["inchikey"]).shape[0]
    if cache_path.exists() and not rebuild_cache:
        cached = pd.read_parquet(cache_path)
        required = {"inchikey", "total_atom_count", "heavy_atom_count", "elements"}
        if required.issubset(cached.columns) and len(cached) == expected_rows:
            return cached
        print("[Align composition] cache schema/count mismatch; rebuilding")
    return build_align_geometry_cache(
        align_path,
        frequency_index_path,
        frequency_payload_dir,
        cache_path,
    )


def element_prevalence(values: Iterable[object]) -> pd.Series:
    counts: Counter[str] = Counter()
    for value in values:
        if pd.isna(value):
            continue
        counts.update(str(value).split(","))
    return pd.Series(dict(counts), dtype=np.int64)


def load_functional_group_summary(
    align_path: Path,
    cache_path: Path,
    rebuild_cache: bool,
) -> dict[str, object]:
    """Count molecule-level functional-group presence in the Align split."""

    expected_rows = pd.read_parquet(align_path, columns=["inchikey"]).shape[0]
    if cache_path.exists() and not rebuild_cache:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if (
            int(cached.get("molecules", -1)) == expected_rows
            and cached.get("smarts") == FUNCTIONAL_GROUP_SMARTS
        ):
            return cached
        print("[Align functional groups] cache schema/count mismatch; rebuilding")

    queries = {
        name: Chem.MolFromSmarts(smarts)
        for name, smarts in FUNCTIONAL_GROUP_SMARTS.items()
    }
    invalid_queries = [name for name, query in queries.items() if query is None]
    if invalid_queries:
        raise ValueError(f"invalid functional-group SMARTS: {invalid_queries}")

    smiles = pd.read_parquet(
        align_path,
        columns=["canonical_smiles"],
    )["canonical_smiles"]
    counts = Counter({name: 0 for name in queries})
    invalid_smiles = 0
    for index, value in enumerate(smiles, start=1):
        molecule = Chem.MolFromSmiles(str(value)) if pd.notna(value) else None
        if molecule is None:
            invalid_smiles += 1
        else:
            for name, query in queries.items():
                if molecule.HasSubstructMatch(query):
                    counts[name] += 1
        if index % 100_000 == 0 or index == len(smiles):
            print(f"[Align functional groups] processed {index:,}/{len(smiles):,} molecules")

    summary: dict[str, object] = {
        "molecules": int(len(smiles)),
        "invalid_smiles": int(invalid_smiles),
        "counting_rule": "non-exclusive molecule-level SMARTS presence",
        "smarts": dict(FUNCTIONAL_GROUP_SMARTS),
        "counts": {name: int(counts[name]) for name in queries},
        "prevalence": {
            name: float(counts[name] / len(smiles)) for name in queries
        },
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _fidelity_panel(
    axis: plt.Axes,
    counts: dict[str, int],
    openmolspec_count: int,
    annotation_offsets: dict[str, tuple[float, float]],
) -> None:
    values = dict(counts)
    values["OpenMolSpec"] = openmolspec_count
    names = [name for name in DATASETS if name in values]
    for name in names:
        highlighted = name == "OpenMolSpec"
        fidelity = DATASET_FIDELITY[name]
        axis.scatter(
            fidelity,
            values[name],
            s=150 if highlighted else 72,
            marker="*" if highlighted else "o",
            color=BLUE if highlighted else GRAY,
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
        x_offset, y_offset = annotation_offsets.get(name, (6, 6))
        centered_on_point = name == "Multimodal Spec."
        axis.annotate(
            f"{name}\n{compact_count(values[name])}",
            xy=(fidelity, values[name]),
            xytext=(x_offset, y_offset),
            textcoords="offset points",
            ha="center" if centered_on_point else ("left" if x_offset >= 0 else "right"),
            va="bottom" if y_offset >= 0 else "top",
            multialignment="center",
            fontsize=8.5,
            color=BLUE if highlighted else DARK_GRAY,
            fontweight="bold" if highlighted else "normal",
        )
    minimum = min(values[name] for name in names)
    maximum = max(values[name] for name in names)
    axis.set_yscale("log")
    axis.set_xlim(0.55, len(FIDELITY_LEVELS) + 0.45)
    axis.set_ylim(minimum / 1.6, maximum * 1.8)
    axis.set_xticks(np.arange(1, len(FIDELITY_LEVELS) + 1), FIDELITY_LEVELS)
    axis.set_xlabel("Approximate spectral-generation protocol / computational complexity")
    axis.set_ylabel("Unique molecules (log scale)")
    axis.set_title(
        "A  Molecular scale versus computational fidelity",
        loc="left",
        fontweight="bold",
    )
    axis.grid(color=GRID, alpha=0.65, which="major")
    axis.set_axisbelow(True)
    axis.yaxis.set_major_formatter(FuncFormatter(compact_count))


def _integer_distribution(
    axis: plt.Axes,
    values: pd.Series,
    title: str,
    xlabel: str,
) -> dict[str, float]:
    array = values.dropna().to_numpy(dtype=np.int32)
    cutoff = int(np.ceil(np.quantile(array, 0.999)))
    clipped = np.minimum(array, cutoff)
    bins = np.arange(int(clipped.min()) - 0.5, cutoff + 1.5, 1.0)
    weights = np.full(clipped.shape, 100.0 / clipped.size)
    axis.hist(clipped, bins=bins, weights=weights, color=BLUE, alpha=0.88, linewidth=0)
    median = float(np.median(array))
    axis.axvline(median, color="#D55E00", linestyle="--", linewidth=1.8)
    axis.text(
        median,
        axis.get_ylim()[1] * 0.93,
        f"median = {median:g}",
        color="#A84300",
        ha="left",
        va="top",
        fontsize=8.5,
    )
    axis.set_xlabel(xlabel)
    axis.set_ylabel("Align molecules (%)")
    axis.set_title(title, loc="left", fontweight="bold")
    axis.grid(axis="y", color=GRID, alpha=0.65)
    axis.set_axisbelow(True)
    axis.yaxis.set_major_formatter(PercentFormatter(100.0))
    ticks = list(axis.get_xticks())
    if cutoff not in ticks:
        ticks.append(float(cutoff))
    ticks = sorted(tick for tick in ticks if array.min() <= tick <= cutoff)
    labels = [f"≥{cutoff}" if tick == cutoff else f"{tick:g}" for tick in ticks]
    axis.set_xticks(ticks, labels)
    return {
        "count": int(array.size),
        "median": median,
        "mean": float(array.mean()),
        "p99.9": float(np.quantile(array, 0.999)),
        "maximum": int(array.max()),
        "display_cutoff": cutoff,
    }


def _scaffold_occupancy_buckets(
    axis: plt.Axes,
    scaffold_keys: pd.Series,
) -> dict[str, float]:
    """Show how rare and common Bemis--Murcko scaffolds contribute."""

    all_keys = scaffold_keys.astype("string")
    if all_keys.isna().any() or all_keys.str.strip().eq("").any():
        raise ValueError("Align split contains missing scaffold partition keys")
    acyclic_mask = all_keys.eq("__ACYCLIC__")
    acyclic_molecules = int(acyclic_mask.sum())
    # Bemis--Murcko does not define a meaningful scaffold for acyclic
    # molecules.  Treating all of them as one scaffold would substantially
    # inflate the high-occupancy tail, so report them separately.
    keys = all_keys.loc[~acyclic_mask]
    counts = keys.value_counts(sort=True)
    occupancies = counts.to_numpy(dtype=np.int64, copy=False)
    bucket_specs = [
        (1, 1, "1"),
        (2, 5, "2–5"),
        (6, 10, "6–10"),
        (11, 100, "11–100"),
        (101, np.iinfo(np.int64).max, ">100"),
    ]
    scaffold_fractions = []
    molecule_fractions = []
    bucket_summary: dict[str, dict[str, float | int]] = {}
    for lower, upper, label in bucket_specs:
        selected = occupancies[(occupancies >= lower) & (occupancies <= upper)]
        scaffold_fraction = selected.size / occupancies.size
        molecule_fraction = selected.sum() / occupancies.sum()
        scaffold_fractions.append(scaffold_fraction)
        molecule_fractions.append(molecule_fraction)
        bucket_summary[label] = {
            "scaffolds": int(selected.size),
            "scaffold_fraction": float(scaffold_fraction),
            "molecules": int(selected.sum()),
            "molecule_fraction": float(molecule_fraction),
        }

    x = np.arange(len(bucket_specs), dtype=float)
    width = 0.36
    scaffold_bars = axis.bar(
        x - width / 2,
        scaffold_fractions,
        width,
        color=BLUE,
        label="Share of scaffolds",
    )
    molecule_bars = axis.bar(
        x + width / 2,
        molecule_fractions,
        width,
        color="#D97706",
        label="Share of molecules",
    )
    axis.set_xticks(x, [spec[2] for spec in bucket_specs])
    axis.set_xlabel("Cyclic molecules sharing the same scaffold")
    axis.set_ylabel("Share within cyclic subset (%)")
    axis.set_title("E  Cyclic scaffold diversity and occupancy", loc="left", fontweight="bold")
    axis.grid(axis="y", color=GRID, alpha=0.65)
    axis.set_axisbelow(True)
    axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.legend(frameon=False, loc="upper center", ncols=2)
    axis.set_ylim(0, max(max(scaffold_fractions), max(molecule_fractions)) * 1.22)
    for bars in (scaffold_bars, molecule_bars):
        for bar in bars:
            value = bar.get_height()
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.012,
                f"{value:.1%}",
                ha="center",
                va="bottom",
                fontsize=7.4,
                color=DARK_GRAY,
                rotation=90 if value < 0.07 else 0,
            )

    singleton_scaffolds = int(np.count_nonzero(occupancies == 1))
    singleton_fraction = singleton_scaffolds / occupancies.size
    axis.text(
        0.50,
        0.69,
        (
            f"{occupancies.size:,} cyclic scaffolds\n"
            f"{acyclic_molecules:,} acyclic molecules excluded"
        ),
        transform=axis.transAxes,
        ha="center",
        va="center",
        fontsize=8.2,
        color=DARK_GRAY,
    )
    return {
        "cyclic_molecules": int(occupancies.sum()),
        "unique_cyclic_scaffolds": int(occupancies.size),
        "singleton_scaffolds": singleton_scaffolds,
        "singleton_scaffold_fraction": float(singleton_fraction),
        "median_occupancy": float(np.median(occupancies)),
        "mean_occupancy": float(np.mean(occupancies)),
        "maximum_occupancy": int(occupancies.max()),
        "acyclic_molecules_excluded": acyclic_molecules,
        "occupancy_buckets": bucket_summary,
    }


def plot_overview(
    composition: pd.DataFrame,
    scaffold_keys: pd.Series,
    functional_group_summary: dict[str, object],
    align_molecules: int,
    trajectory_frames: int,
    output: Path,
) -> dict[str, object]:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "legend.fontsize": 8.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "text.color": TEXT,
        "axes.labelcolor": TEXT,
        "xtick.color": TEXT,
        "ytick.color": TEXT,
        "figure.dpi": 150,
        "savefig.dpi": 400,
    })
    figure, axes = plt.subplots(2, 3, figsize=(18, 9.6), constrained_layout=True)

    _fidelity_panel(
        axes[0, 0],
        MOLECULE_COUNTS,
        align_molecules,
        {
            "Multimodal Spec.": (0, -10),
            "SpecX Large": (7, 7),
            "ChEMBL IR/Raman": (7, 7),
            "QM9S": (-7, -8),
            "QMe14S": (7, 8),
            "OpenMolSpec": (7, 8),
            "SQuIRL": (-7, 8),
        },
    )
    coverage = [SPECTRAL_COVERAGE[name] for name in DATASETS]
    axis = axes[0, 1]
    axis.set_facecolor("#F7F9FC")
    axis.axhspan(len(DATASETS) - 1.5, len(DATASETS) - 0.5, color=LIGHT_BLUE, zorder=0)
    axis.set_xlim(-0.5, len(SPECTRAL_MODALITIES) - 0.5)
    axis.set_ylim(len(DATASETS) - 0.5, -0.5)
    axis.set_xticks(np.arange(len(SPECTRAL_MODALITIES)), SPECTRAL_MODALITIES)
    axis.tick_params(
        axis="x",
        top=True,
        labeltop=True,
        bottom=False,
        labelbottom=False,
        length=0,
        pad=7,
    )
    axis.set_yticks(np.arange(len(DATASETS)), DATASETS)
    axis.tick_params(axis="y", length=0)
    for boundary in np.arange(-0.5, len(DATASETS), 1.0):
        axis.axhline(boundary, color="#DDE4EC", linewidth=0.8, zorder=1)
    for boundary in np.arange(-0.5, len(SPECTRAL_MODALITIES), 1.0):
        axis.axvline(boundary, color="#DDE4EC", linewidth=0.8, zorder=1)
    for row, dataset in enumerate(DATASETS):
        for column, symbol in enumerate(coverage[row]):
            if dataset == "OpenMolSpec" and symbol == "●":
                color = BLUE
            elif symbol == "●":
                color = "#5D79A0"
            elif symbol == "◐":
                color = "#5D79A0"
            else:
                color = "#7B8794"
            axis.text(
                column,
                row,
                symbol,
                ha="center",
                va="center",
                color=color,
                fontsize=16,
                fontweight="bold",
                zorder=2,
            )
    axis.axhline(len(DATASETS) - 1.5, color=BLUE, linewidth=1.8, zorder=3)
    axis.set_xlabel(
        "● quantum-calculated    ○ classical/predicted    ◐ partial coverage    – unavailable",
        fontsize=7.8,
        color=DARK_GRAY,
        labelpad=10,
    )
    axis.set_title(
        "B  Released spectroscopic modality coverage",
        loc="left",
        fontweight="bold",
        pad=30,
    )
    axis.spines["top"].set_visible(True)
    axis.spines["right"].set_visible(True)

    total_summary = _integer_distribution(
        axes[0, 2],
        composition["total_atom_count"],
        "C  Total atom-count distribution",
        "Atoms per aligned molecule (including H)",
    )
    scaffold_summary = _scaffold_occupancy_buckets(
        axes[1, 1],
        scaffold_keys,
    )

    counts = element_prevalence(composition["elements"])
    elements = [element for element in ELEMENT_ORDER if counts.get(element, 0) > 0]
    elements.extend(sorted(set(counts.index) - set(elements)))
    prevalence = counts.reindex(elements).fillna(0).to_numpy(dtype=float) / len(composition)
    axis = axes[1, 0]
    bars = axis.bar(elements, prevalence, color=BLUE, width=0.75)
    positive = prevalence[prevalence > 0]
    lower = max(1e-6, 10 ** np.floor(np.log10(positive.min())))
    axis.set_yscale("log")
    axis.set_ylim(lower, 1.5)
    axis.set_xlabel("Element")
    axis.set_ylabel("Fraction of Align molecules (log scale)")
    axis.set_title("D  Element prevalence", loc="left", fontweight="bold")
    axis.grid(axis="y", color=GRID, alpha=0.65, which="major")
    axis.set_axisbelow(True)
    for bar, value in zip(bars, prevalence):
        if value >= 1e-3:
            common = value >= 0.08
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                value / 1.35 if common else value * 1.18,
                f"{value:.1%}" if value >= 0.01 else f"{value:.2%}",
                rotation=90,
                ha="center",
                va="top" if common else "bottom",
                fontsize=7.5,
                color="white" if common else DARK_GRAY,
                fontweight="bold" if common else "normal",
            )

    functional_prevalence = {
        str(name): float(value)
        for name, value in dict(functional_group_summary["prevalence"]).items()
    }
    ordered_groups = sorted(
        functional_prevalence,
        key=functional_prevalence.get,
    )
    group_values = np.asarray(
        [functional_prevalence[name] for name in ordered_groups],
        dtype=float,
    )
    axis = axes[1, 2]
    bars = axis.barh(ordered_groups, group_values, color=BLUE, height=0.70)
    axis.set_xlim(0, max(group_values) * 1.18)
    axis.set_xlabel("Fraction of Align molecules")
    axis.set_title("F  Functional-group prevalence", loc="left", fontweight="bold")
    axis.grid(axis="x", color=GRID, alpha=0.65)
    axis.set_axisbelow(True)
    axis.xaxis.set_major_formatter(PercentFormatter(1.0))
    for bar, value in zip(bars, group_values):
        axis.text(
            value + max(group_values) * 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.1%}" if value >= 0.01 else f"{value:.2%}",
            ha="left",
            va="center",
            fontsize=7.3,
            color=DARK_GRAY,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, bbox_inches="tight", facecolor="white")
    pdf_path = output.with_suffix(".pdf")
    figure.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    plt.close(figure)

    return {
        "align_molecules": int(align_molecules),
        "trajectory_frames": int(trajectory_frames),
        "computational_fidelity": {
            name: {
                "level": int(DATASET_FIDELITY[name]),
                "category": FIDELITY_LEVELS[DATASET_FIDELITY[name] - 1].replace("\n", " "),
                "protocol": FIDELITY_PROTOCOLS[name],
            }
            for name in DATASETS
        },
        "spectroscopic_modality_coverage": {
            "modalities": SPECTRAL_MODALITIES,
            "symbol_meaning": {
                "●": "quantum-calculated",
                "○": "classical/predicted",
                "◐": "partial coverage",
                "–": "unavailable",
            },
            "datasets": {
                name: dict(zip(SPECTRAL_MODALITIES, SPECTRAL_COVERAGE[name]))
                for name in DATASETS
            },
        },
        "total_atom_count": total_summary,
        "scaffold_occupancy": scaffold_summary,
        "element_prevalence": {
            element: float(value) for element, value in zip(elements, prevalence)
        },
        "functional_group_prevalence": functional_group_summary,
        "figure": str(output),
        "pdf": str(pdf_path),
    }


def main() -> None:
    root_default = repository_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root_default)
    parser.add_argument(
        "--align",
        type=Path,
        default=Path("builds/openmolspec-20260830/release-v1/splits/align_split.parquet"),
    )
    parser.add_argument(
        "--catalog-summary",
        type=Path,
        default=Path("builds/openmolspec-20260830/release-v1/catalog/summary.json"),
    )
    parser.add_argument(
        "--dataset-summary",
        type=Path,
        default=Path("openmolspec-manuscripts/evidence/dataset_summary.json"),
    )
    parser.add_argument(
        "--frequency-index",
        type=Path,
        default=Path("builds/openmolspec-20260830/release-v1/payload/frequency/index.parquet"),
    )
    parser.add_argument(
        "--frequency-payload-dir",
        type=Path,
        default=Path("builds/openmolspec-20260830/release-v1/payload/frequency"),
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("reports/analysis/align_geometry_composition.parquet"),
    )
    parser.add_argument(
        "--functional-group-cache",
        type=Path,
        default=Path("reports/analysis/align_functional_groups.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/figures/openmolspec_align_overview.png"),
    )
    parser.add_argument("--rebuild-cache", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    align_path = resolve(root, args.align)
    catalog_summary = resolve(root, args.catalog_summary)
    dataset_summary = resolve(root, args.dataset_summary)
    frequency_index = resolve(root, args.frequency_index)
    frequency_payload_dir = resolve(root, args.frequency_payload_dir)
    cache_path = resolve(root, args.cache)
    functional_group_cache = resolve(root, args.functional_group_cache)
    output = resolve(root, args.output)

    align_molecules, trajectory_frames = _read_release_counts(
        catalog_summary,
        dataset_summary,
    )
    composition = load_align_composition(
        align_path,
        frequency_index,
        frequency_payload_dir,
        cache_path,
        args.rebuild_cache,
    )
    scaffold_keys = pd.read_parquet(
        align_path,
        columns=["split_scaffold"],
    )["split_scaffold"]
    functional_group_summary = load_functional_group_summary(
        align_path,
        functional_group_cache,
        args.rebuild_cache,
    )
    if len(composition) != align_molecules:
        raise ValueError(
            f"Align count mismatch: catalog={align_molecules:,}, geometry={len(composition):,}"
        )
    if len(scaffold_keys) != align_molecules:
        raise ValueError(
            f"Align count mismatch: catalog={align_molecules:,}, scaffolds={len(scaffold_keys):,}"
        )
    summary = plot_overview(
        composition,
        scaffold_keys,
        functional_group_summary,
        align_molecules,
        trajectory_frames,
        output,
    )
    summary_path = output.with_suffix(".json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
