"""Visualize the chemical distribution of the molecule-unique align catalog.

Example:
    python -m openmolspec.analysis.plot_align_chemical_distribution
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter


COLORS = {
    "train": "#2474B5",
    "validation": "#E69F00",
    "test": "#D55E00",
}
SPLIT_ORDER = ("train", "validation", "test")


def _millions(value: float, _position: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def _elements(values: Iterable[object]) -> pd.Series:
    counts: Dict[str, int] = {}
    for value in values:
        if pd.isna(value):
            continue
        for element in str(value).split(","):
            element = element.strip()
            if element:
                counts[element] = counts.get(element, 0) + 1
    return pd.Series(counts, dtype=np.int64).sort_values(ascending=False)


def _distribution_summary(frame: pd.DataFrame) -> Dict[str, object]:
    numeric = [
        "molecular_weight", "heavy_atom_count", "ring_count",
        "aromatic_ring_count", "rotatable_bonds", "fraction_csp3",
    ]
    summary: Dict[str, object] = {
        "molecules": int(len(frame)),
        "split_counts": {key: int(value) for key, value in frame["split"].value_counts().items()},
        "unique_scaffolds": int(frame["split_scaffold"].nunique()),
        "unique_sources": int(frame["align_source"].nunique()),
    }
    summary["descriptor_quantiles"] = {
        column: {
            str(quantile): float(value)
            for quantile, value in frame[column].quantile([0.01, 0.25, 0.5, 0.75, 0.99]).items()
        }
        for column in numeric
    }
    element_counts = _elements(frame["elements"])
    summary["element_counts"] = {key: int(value) for key, value in element_counts.items()}
    summary["source_counts"] = {
        key: int(value) for key, value in frame["align_source"].value_counts().items()
    }
    return summary


def plot_distribution(frame: pd.DataFrame, output: Path) -> None:
    """Draw the chemical-space distributions of the aligned molecular data."""
    plt.rcParams.update({
        "font.size": 13,
        "axes.titlesize": 16,
        "axes.labelsize": 14,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 11,
        "figure.dpi": 150,
        "savefig.dpi": 300,
    })
    fig, axes = plt.subplots(2, 3, figsize=(20, 12), constrained_layout=True)

    # A/B: normalized split-wise distributions reveal covariate shift while
    # remaining readable despite the deliberately unequal split sizes.
    distributions = (
        (axes[0, 0], "molecular_weight", "Molecular weight (g mol$^{-1}$)", 90),
        (axes[0, 1], "heavy_atom_count", "Heavy-atom count", 55),
    )
    for ax, column, label, bins in distributions:
        upper = float(frame[column].quantile(0.995))
        edges = np.linspace(max(0.0, float(frame[column].min())), upper, bins + 1)
        for split in SPLIT_ORDER:
            values = frame.loc[frame["split"].eq(split), column].dropna()
            ax.hist(
                values.clip(upper=upper), bins=edges, density=True,
                histtype="step", linewidth=2.2, color=COLORS[split],
                label=f"{split.capitalize()} ({len(values):,})",
            )
        ax.set_xlabel(label)
        ax.set_ylabel("Probability density")
        ax.legend(frameon=False)
        ax.grid(alpha=0.18)
    axes[0, 0].set_title("A  Molecular-weight distribution", loc="left", fontweight="bold")
    axes[0, 1].set_title("B  Molecular-size distribution", loc="left", fontweight="bold")

    # C: density in the two most interpretable size dimensions.
    sample = frame.sample(n=min(250_000, len(frame)), random_state=2025)
    x_max = float(frame["heavy_atom_count"].quantile(0.995))
    y_max = float(frame["molecular_weight"].quantile(0.995))
    hb = axes[0, 2].hexbin(
        sample["heavy_atom_count"].clip(upper=x_max),
        sample["molecular_weight"].clip(upper=y_max),
        gridsize=55, bins="log", mincnt=1, cmap="viridis",
    )
    fig.colorbar(hb, ax=axes[0, 2], label="log$_{10}$(sampled molecules per bin)")
    axes[0, 2].set_xlabel("Heavy-atom count")
    axes[0, 2].set_ylabel("Molecular weight (g mol$^{-1}$)")
    axes[0, 2].set_title("C  Chemical size space", loc="left", fontweight="bold")

    # D: molecule-level element prevalence (an element is counted once per molecule).
    element_counts = _elements(frame["elements"])
    preferred = ["C", "N", "O", "F", "P", "S", "Cl", "Br", "I", "B", "Si"]
    elements = [element for element in preferred if element in element_counts]
    elements += [
        element for element in element_counts.index
        if element not in elements and element != "H"
    ]
    elements = elements[:16]
    prevalence = element_counts.reindex(elements).fillna(0) / len(frame)
    bars = axes[1, 0].bar(elements, prevalence, color="#3A86A8", width=0.78)
    axes[1, 0].set_ylabel("Fraction of align molecules")
    axes[1, 0].set_xlabel("Element (implicit H not included)")
    axes[1, 0].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1, 0].set_title("D  Heavy-element prevalence", loc="left", fontweight="bold")
    axes[1, 0].set_ylim(0, 1.06)
    axes[1, 0].grid(axis="y", alpha=0.18)
    for bar, value in zip(bars, prevalence):
        if value >= 0.01:
            axes[1, 0].text(
                bar.get_x() + bar.get_width() / 2, value - 0.012, f"{value:.1%}",
                ha="center", va="top", fontsize=9, rotation=90,
                color="white" if value >= 0.08 else "#222222",
            )

    # E: provenance of the selected multimodal record for each unique molecule.
    sources = frame["align_source"].fillna("UNKNOWN").value_counts().sort_values()
    axes[1, 1].barh(sources.index, sources.values, color="#5B8C5A")
    axes[1, 1].set_xlabel("Unique align molecules")
    axes[1, 1].xaxis.set_major_formatter(FuncFormatter(_millions))
    axes[1, 1].set_title("E  Source contribution", loc="left", fontweight="bold")
    axes[1, 1].grid(axis="x", alpha=0.18)
    for index, value in enumerate(sources.values):
        axes[1, 1].text(value, index, f" {value:,}", va="center", fontsize=9)

    # F: rank-frequency curve shows both dominant and long-tail scaffolds.
    scaffold_counts = frame.groupby("split_scaffold", observed=True).size().sort_values(ascending=False)
    ranks = np.arange(1, len(scaffold_counts) + 1)
    axes[1, 2].loglog(ranks, scaffold_counts.values, color="#7B4F9D", linewidth=1.8)
    axes[1, 2].fill_between(ranks, scaffold_counts.values, 1, color="#7B4F9D", alpha=0.12)
    singleton_count = int((scaffold_counts == 1).sum())
    acyclic_count = int(scaffold_counts.get("__ACYCLIC__", 0))
    annotation = (
        f"{len(scaffold_counts):,} unique scaffolds\n"
        f"{singleton_count:,} singleton scaffolds\n"
        f"{acyclic_count:,} acyclic molecules"
    )
    axes[1, 2].text(
        0.97, 0.94, annotation, transform=axes[1, 2].transAxes,
        ha="right", va="top", bbox={"boxstyle": "round", "fc": "white", "alpha": 0.9},
    )
    axes[1, 2].set_xlabel("Scaffold rank")
    axes[1, 2].set_ylabel("Molecules per scaffold")
    axes[1, 2].set_title("F  Scaffold frequency and long tail", loc="left", fontweight="bold")
    axes[1, 2].grid(which="both", alpha=0.16)

    fig.suptitle(
        "OpenMolSpec Align: Chemical-Space Distribution",
        fontsize=24, fontweight="bold",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")
    fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Run the plot align chemical distribution command-line workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--align",
        type=Path,
        default=Path("builds/openmolspec-20260830/release-v1/splits/align_split.parquet"),
    )
    parser.add_argument(
        "--descriptors",
        type=Path,
        default=Path("reports/analysis/chemical_descriptors.parquet"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/figures/openmolspec_align_chemical_distribution.png"),
    )
    args = parser.parse_args()

    align_columns = [
        "inchikey", "split", "split_scaffold", "align_source",
    ]
    descriptor_columns = [
        "inchikey", "valid_smiles", "heavy_atom_count", "molecular_weight",
        "ring_count", "aromatic_ring_count", "rotatable_bonds", "fraction_csp3", "elements",
    ]
    align = pd.read_parquet(args.align, columns=align_columns)
    descriptors = pd.read_parquet(args.descriptors, columns=descriptor_columns)
    frame = align.merge(descriptors, on="inchikey", how="left", validate="one_to_one")
    missing = int(frame["valid_smiles"].isna().sum())
    if missing:
        raise ValueError(f"{missing:,} align molecules are missing descriptor rows")
    frame = frame.loc[frame["valid_smiles"]].copy()

    plot_distribution(frame, args.output)
    summary_path = args.output.with_suffix(".json")
    summary_path.write_text(
        json.dumps(_distribution_summary(frame), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "align_molecules": int(len(frame)),
        "figure": str(args.output),
        "pdf": str(args.output.with_suffix(".pdf")),
        "summary": str(summary_path),
    }, indent=2))


if __name__ == "__main__":
    main()
