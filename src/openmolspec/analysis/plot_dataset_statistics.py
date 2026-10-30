"""Compare OpenMolSpec with established QM and spectroscopy datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


DATASETS = ["QM9S", "QMe14S", "ChEMBL IR/Raman", "SQuIRL", "ANI-1", "QM7-X", "QCML", "OpenMolSpec"]
# Year of the first public release/publication used for this comparison.
# OpenMolSpec is marked as 2026 because this is the current project release
# context, not because a journal publication has already appeared.
PUBLIC_YEAR = {
    "QM9S": 2023,
    "QMe14S": 2025,
    "ChEMBL IR/Raman": 2025,
    "SQuIRL": 2026,
    "ANI-1": 2017,
    "QM7-X": 2021,
    "QCML": 2025,
    "OpenMolSpec": 2026,
}
MOLECULES = [133_885, 186_102, 220_000, 133_885, 57_462, None, None, 1_164_603]
CONFIGURATIONS = [None, None, None, None, 20_000_000, 4_200_000, 33_500_000, 32_333_251]

# Released labels/configurations, not model-predicted properties.
MODALITIES = ["IR", "Raman", "NMR", "Energy", "Forces", "Trajectories"]
COVERAGE = np.array([
    [1, 1, 0, 1, 0, 0],  # QM9S
    [1, 1, 1, 1, 1, 1],  # QMe14S
    [1, 1, 0, 1, 0, 0],  # ChEMBL IR/Raman
    [1, 0, 0, 1, 0, 0],  # SQuIRL
    [0, 0, 0, 1, 0, 1],  # ANI-1
    [0, 0, 0, 1, 1, 1],  # QM7-X
    [0, 0, 0, 1, 1, 1],  # QCML
    [1, 1, 1, 1, 1, 1],  # OpenMolSpec
])


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def current_openmolspec_counts(root: Path) -> tuple[int, int, int, int, int]:
    analysis = read_json(root / "reports/analysis/summary.json")
    return (
        analysis["unique_canonical_smiles"],
        analysis["trajectory_frames"],
        analysis["frequency_success"],
        analysis["nmr_success"],
        analysis["tri_modal_unique_inchikey"],
    )


def plot_comparison(root: Path, output: Path) -> None:
    (
        unique_molecules,
        trajectory_frames,
        freq_success,
        nmr_success,
        tri_modal_unique,
    ) = current_openmolspec_counts(root)
    molecules = MOLECULES.copy()
    configurations = CONFIGURATIONS.copy()
    molecules[-1] = unique_molecules
    configurations[-1] = trajectory_frames

    plt.rcParams.update({
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "figure.dpi": 140,
        "savefig.dpi": 300,
        "font.family": "DejaVu Sans",
    })
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    fig.suptitle(
        "OpenMolSpec versus established molecular QM and spectroscopy datasets",
        fontsize=16, fontweight="bold",
    )
    display_names = np.array([f"{name} ({PUBLIC_YEAR[name]})" for name in DATASETS])
    colors = ["#2f6fdb" if name == "OpenMolSpec" else "#a9b9cc" for name in DATASETS]

    # A. Molecule scale.
    ax = axes[0, 0]
    values = np.array(molecules, dtype=float)
    mask = ~np.isnan(values)
    ax.barh(display_names[mask], values[mask], color=np.array(colors)[mask])
    ax.set_xscale("log")
    ax.set_title("A  Unique-molecule scale")
    ax.set_xlabel("Molecules (log scale)")
    ax.grid(axis="x", alpha=0.25, which="both")
    ax.set_axisbelow(True)
    ax.text(0.98, 0.04, f"OpenMolSpec: {unique_molecules / 1e6:.2f}M",
            transform=ax.transAxes, ha="right", va="bottom",
            bbox={"boxstyle": "round", "facecolor": "#eef4ff", "edgecolor": "#2f6fdb"})

    # B. Non-equilibrium configurations or optimization frames.
    ax = axes[0, 1]
    values = np.array(configurations, dtype=float)
    mask = ~np.isnan(values)
    ax.barh(display_names[mask], values[mask], color=np.array(colors)[mask])
    ax.set_xscale("log")
    ax.set_title("B  Non-equilibrium configuration scale")
    ax.set_xlabel("Configurations or frames (log scale)")
    ax.grid(axis="x", alpha=0.25, which="both")
    ax.set_axisbelow(True)
    ax.text(0.98, 0.04, f"OpenMolSpec: {trajectory_frames / 1e6:.1f}M frames",
            transform=ax.transAxes, ha="right", va="bottom",
            bbox={"boxstyle": "round", "facecolor": "#fff5e8", "edgecolor": "#f4a261"})

    # C. Label/configuration coverage.
    ax = axes[1, 0]
    ax.imshow(COVERAGE, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(np.arange(len(MODALITIES)), MODALITIES)
    ax.set_yticks(np.arange(len(DATASETS)), display_names)
    ax.set_title("C  Released modality / configuration coverage")
    ax.tick_params(axis="x", rotation=25)
    for i in range(COVERAGE.shape[0]):
        for j in range(COVERAGE.shape[1]):
            ax.text(j, i, "✓" if COVERAGE[i, j] else "—", ha="center", va="center",
                    color="white" if COVERAGE[i, j] else "#75808c", fontsize=13,
                    fontweight="bold")

    # D. OpenMolSpec-specific differentiators.
    ax = axes[1, 1]
    ax.axis("off")
    ax.set_title("D  OpenMolSpec differentiators", pad=12)
    lines = [
        ("1.16M", "unique canonical molecules"),
        (f"{tri_modal_unique / 1e6:.2f}M", "unique IR + Raman + NMR molecules"),
        ("32.3M", "energy–force optimization frames"),
        (f"{freq_success / 1e6:.2f}M", "successfully parsed frequency records"),
        (f"{nmr_success / 1e6:.2f}M", "successfully parsed NMR records"),
    ]
    y = 0.9
    for value, label in lines:
        ax.text(0.05, y, value, transform=ax.transAxes, fontsize=21,
                fontweight="bold", color="#2f6fdb", va="center")
        ax.text(0.36, y, label, transform=ax.transAxes, fontsize=11, va="center")
        y -= 0.16
    ax.text(0.05, 0.08,
            "The differentiator is the intersection of large chemical coverage,\n"
            "multi-spectral supervision, and force-field-relevant off-equilibrium data.",
            transform=ax.transAxes, fontsize=10, color="#444444", va="bottom")

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path,
                        default=Path("docs/figures/openmolspec_comparison.png"))
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    plot_comparison(args.root, output)


if __name__ == "__main__":
    main()
