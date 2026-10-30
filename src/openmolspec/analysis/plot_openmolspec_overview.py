"""
Create a publication-style overview figure for OpenMolSpec.

The figure compares OpenMolSpec with representative public molecular
quantum-chemistry and spectroscopy datasets in terms of:

A. Historical release timeline and molecular scale
B. Unique-molecule scale
C. Configuration / trajectory scale
D. Elemental diversity
E. Released data-type breadth
F. OpenMolSpec processing funnel

External counts are approximate headline values reported in the corresponding
dataset publications/releases and are not recomputed under a common protocol.

Example:
    python -m openmolspec.analysis.plot_openmolspec_overview
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter


# ============================================================
# Dataset metadata
# ============================================================

DATASETS = [
    "ANI-1",
    "QM7-X",
    "QM9S",
    "QMe14S",
    "ChEMBL IR/Raman",
    "QCML",
    "SQuIRL",
    "OpenMolSpec",
]

YEARS = np.array([
    2017,
    2021,
    2023,
    2025,
    2025,
    2025,
    2026,
    2026,
])

# Approximate number of unique molecules.
MOLECULES = np.array([
    57_462,      # ANI-1
    np.nan,      # QM7-X: configuration-centered dataset
    133_885,     # QM9S
    186_102,     # QMe14S
    220_000,     # ChEMBL IR/Raman
    np.nan,      # QCML
    133_885,     # SQuIRL / QM9-scale molecular space
    np.nan,      # OpenMolSpec: loaded from local summary
])

# Approximate number of structures / configurations / trajectory frames.
#
# Note:
# These values are "headline-scale" quantities and are not necessarily
# defined identically between datasets.
CONFIGURATIONS = np.array([
    20_000_000,  # ANI-1
    4_200_000,   # QM7-X
    np.nan,      # QM9S
    600_000,     # QMe14S, approximate AIMD configurations
    np.nan,      # ChEMBL IR/Raman
    33_500_000,  # QCML
    np.nan,      # SQuIRL
    np.nan,      # OpenMolSpec: loaded from local summary
])


# ============================================================
# Element coverage
# ============================================================

ELEMENT_SETS = {
    "ANI-1": {
        "H", "C", "N", "O"
    },

    "QM7-X": {
        "H", "C", "N", "O", "S", "Cl"
    },

    "QM9S": {
        "H", "C", "N", "O", "F"
    },

    "QMe14S": {
        "H", "B", "C", "N", "O", "F",
        "Al", "Si", "P", "S", "Cl", "Br", "As", "Se"
    },

    # The ChEMBL IR/Raman publication does not explicitly define
    # a complete element whitelist. This set is therefore treated
    # as the comparison assumption used in this figure.
    "ChEMBL IR/Raman": {
        "H", "C", "N", "O", "F", "P", "S", "Cl", "Br"
    },

    "QCML": {
        "H", "C", "N", "O"
    },

    "SQuIRL": {
        "H", "C", "N", "O", "F"
    },

    "OpenMolSpec": {
        "H", "B", "C", "N", "O", "F",
        "Si", "P", "S", "Cl", "Br",
        "As", "Se", "I", "Ge"
    },
}


# ============================================================
# Released data types
# ============================================================

# Instead of treating all six entries as equivalent "modalities",
# group them into three scientifically clearer categories:
#
# Spectroscopy:
#   IR, Raman, NMR
#
# Properties:
#   Energy, Forces
#
# Dynamics:
#   Optimization / MD / trajectory configurations
#
DATA_TYPE_GROUPS = [
    "Spectroscopy",
    "Properties",
    "Dynamics",
]

DATA_TYPE_COVERAGE = {
    "ANI-1": {
        "Spectroscopy": 0,
        "Properties": 1,     # energy
        "Dynamics": 1,
    },

    "QM7-X": {
        "Spectroscopy": 0,
        "Properties": 2,     # energy + forces
        "Dynamics": 1,
    },

    "QM9S": {
        "Spectroscopy": 2,   # IR + Raman
        "Properties": 1,     # energy/property label
        "Dynamics": 0,
    },

    "QMe14S": {
        "Spectroscopy": 3,   # IR + Raman + NMR
        "Properties": 2,     # energy + forces
        "Dynamics": 1,
    },

    "ChEMBL IR/Raman": {
        "Spectroscopy": 2,   # IR + Raman
        "Properties": 0,
        "Dynamics": 0,
    },

    "QCML": {
        "Spectroscopy": 0,
        "Properties": 2,     # energy + forces
        "Dynamics": 1,
    },

    "SQuIRL": {
        "Spectroscopy": 1,   # IR
        "Properties": 0,
        "Dynamics": 0,
    },

    "OpenMolSpec": {
        "Spectroscopy": 3,   # IR + Raman + NMR
        "Properties": 2,     # energy + forces
        "Dynamics": 1,       # optimization trajectories
    },
}


# ============================================================
# Plotting constants
# ============================================================

BLUE = "#2F6FDB"
LIGHT_BLUE = "#91B4EE"

GRAY = "#A9B9CC"
LIGHT_GRAY = "#E9EEF4"
DARK_GRAY = "#536273"

ORANGE = "#F4A261"
GREEN = "#2A9D8F"
PURPLE = "#8064A2"

TEXT = "#263442"
TITLE = "#173F73"
GRID = "#D7DEE8"


# ============================================================
# Helpers
# ============================================================

def load_local_summary(root: Path) -> tuple[dict, pd.DataFrame]:
    """Load OpenMolSpec statistics generated by the local analysis pipeline."""

    summary_path = root / "reports/analysis/summary.json"
    source_path = root / "reports/analysis/source_statistics.parquet"

    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    else:
        # Fallback values for standalone figure generation.
        summary = {
            "unique_inchikey": 1_158_074,
            "tri_modal_records": 1_167_024,
            "tri_modal_unique_inchikey": 1_030_780,
            "frequency_success": 1_249_283,
            "nmr_success": 1_170_783,
            "trajectory_frames": 32_333_251,
        }

    if source_path.exists():
        source = pd.read_parquet(source_path)
    else:
        source = pd.DataFrame()

    return summary, source


def add_panel_label(ax, label: str) -> None:
    """Add journal-style panel label."""

    ax.text(
        -0.10,
        1.08,
        label,
        transform=ax.transAxes,
        fontsize=18,
        fontweight="bold",
        va="top",
        ha="left",
        color=TITLE,
    )


def human_number(value: float, decimals: int = 1) -> str:
    """Format numbers as k / M."""

    if value >= 1e6:
        return f"{value / 1e6:.{decimals}f}M"

    if value >= 1e3:
        return f"{value / 1e3:.0f}k"

    return f"{value:.0f}"


def log_tick_formatter(value, _position):
    """Readable formatter for log-scale axes."""

    if value >= 1e6:
        return f"{value / 1e6:g}M"

    if value >= 1e3:
        return f"{value / 1e3:g}k"

    return f"{value:g}"


def clean_axis(ax) -> None:
    """Apply common publication-style axis formatting."""

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.spines["left"].set_color("#B9C3CF")
    ax.spines["bottom"].set_color("#B9C3CF")

    ax.tick_params(
        axis="both",
        colors=DARK_GRAY,
        length=3,
    )


# ============================================================
# Main figure
# ============================================================

def overview_plot(root: Path, output: Path) -> None:

    summary, source = load_local_summary(root)

    molecules = MOLECULES.copy()
    configurations = CONFIGURATIONS.copy()

    molecules[-1] = summary["unique_inchikey"]
    configurations[-1] = summary["trajectory_frames"]

    names_year = [
        f"{name}"
        for name, year in zip(DATASETS, YEARS)
    ]

    # --------------------------------------------------------
    # Global style
    # --------------------------------------------------------

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 11.2,

        "axes.titlesize": 14.0,
        "axes.titleweight": "bold",
        "axes.labelsize": 11.5,

        "xtick.labelsize": 10.2,
        "ytick.labelsize": 10.2,

        "figure.dpi": 140,
        "savefig.dpi": 300,

        "axes.labelcolor": TEXT,
        "xtick.color": DARK_GRAY,
        "ytick.color": DARK_GRAY,
        "text.color": TEXT,
    })

    fig = plt.figure(
        figsize=(22.5, 11.5),
        facecolor="white",
    )

    grid = fig.add_gridspec(
        2,
        3,
        left=0.065,
        right=0.985,
        top=0.885,
        bottom=0.105,
        hspace=0.42,
        wspace=0.38,
    )

    # Dataset order is deliberately kept consistent in B-E.
    dataset_order = np.arange(len(DATASETS))

    # ========================================================
    # A. Dataset evolution and molecular scale
    # ========================================================

    ax = fig.add_subplot(grid[0, 0])

    mask = ~np.isnan(molecules)

    for x, y, name in zip(
        YEARS[mask],
        molecules[mask],
        np.array(DATASETS)[mask],
    ):
        if name == "OpenMolSpec":
            ax.scatter(
                x,
                y,
                s=220,
                marker="*",
                color=BLUE,
                edgecolor="white",
                linewidth=1.0,
                zorder=5,
            )
        else:
            ax.scatter(
                x,
                y,
                s=65,
                marker="o",
                color=GRAY,
                edgecolor="white",
                linewidth=0.8,
                zorder=3,
            )


    annotation_offsets = {
        "ANI-1": (5, 6),
        "QM9S": (5, 6),
        "QMe14S": (-8, 8),
        "ChEMBL IR/Raman": (5, -15),
        "SQuIRL": (-28, -16),
        "OpenMolSpec": (-60, 8),
    }

    for x, y, name in zip(
        YEARS[mask],
        molecules[mask],
        np.array(DATASETS)[mask],
    ):
        dx, dy = annotation_offsets.get(name, (5, 5))

        ax.annotate(
            name,
            xy=(x, y),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=10.0,
            color=BLUE if name == "OpenMolSpec" else DARK_GRAY,
            fontweight="bold" if name == "OpenMolSpec" else "normal",
        )

    ax.set_yscale("log")

    ax.set_xlim(2016.3, 2026.7)
    ax.set_ylim(3e4, 2e6)

    ax.set_xticks([
        2017,
        2019,
        2021,
        2023,
        2025,
        2026,
    ])

    ax.yaxis.set_major_formatter(
        FuncFormatter(log_tick_formatter)
    )

    ax.set_title(
        "Dataset evolution and molecular scale",
        loc="left",
    )

    ax.set_xlabel("First public release / publication year")
    ax.set_ylabel("Unique molecules")

    ax.grid(
        axis="y",
        alpha=0.65,
        linewidth=0.7,
        color=GRID,
        which="major",
    )

    clean_axis(ax)
    add_panel_label(ax, "A")
    
    # ========================================================
    # B. Molecule scale
    # ========================================================

    ax = fig.add_subplot(grid[0, 1])

    valid_indices = [
        i
        for i in dataset_order
        if not np.isnan(molecules[i])
    ]

    y = np.arange(len(valid_indices))

    labels = [
        names_year[i]
        for i in valid_indices
    ]

    values = np.array([
        molecules[i]
        for i in valid_indices
    ])

    colors = [
        BLUE if DATASETS[i] == "OpenMolSpec" else GRAY
        for i in valid_indices
    ]

    ax.barh(
        y,
        values,
        color=colors,
        height=0.62,
        edgecolor="none",
    )

    ax.set_yticks(y, labels)
    ax.invert_yaxis()

    ax.set_xscale("log")
    ax.set_xlim(3e4, 2.2e6)

    ax.xaxis.set_major_formatter(
        FuncFormatter(log_tick_formatter)
    )

    ax.set_title(
        "Molecular scale",
        loc="left",
    )

    ax.set_xlabel("Unique molecules")

    ax.grid(
        axis="x",
        alpha=0.65,
        linewidth=0.7,
        color=GRID,
        which="major",
    )

    ax.set_axisbelow(True)

    for yi, value, idx in zip(
        y,
        values,
        valid_indices,
    ):
        color = BLUE if DATASETS[idx] == "OpenMolSpec" else DARK_GRAY

        ax.text(
            value * 1.07,
            yi,
            human_number(value, decimals=2 if value >= 1e6 else 0),
            va="center",
            ha="left",
            fontsize=10.0,
            color=color,
            fontweight="bold" if DATASETS[idx] == "OpenMolSpec" else "normal",
        )

    clean_axis(ax)
    add_panel_label(ax, "B")

    # ========================================================
    # C. Configuration / trajectory scale
    # ========================================================

    ax = fig.add_subplot(grid[0, 2])

    valid_indices = [
        i for i in range(len(DATASETS))
        if not np.isnan(configurations[i])
    ]

    labels = [names_year[i] for i in valid_indices]
    values = np.array([configurations[i] for i in valid_indices])

    y = np.arange(len(valid_indices))

    # Keep all reference datasets neutral and highlight OpenMolSpec only.
    colors = [
        BLUE if DATASETS[i] == "OpenMolSpec" else GRAY
        for i in valid_indices
    ]

    bars = ax.barh(
        y,
        values,
        height=0.56,
        color=colors,
        edgecolor="none",
        zorder=3,
    )

    ax.set_yticks(y, labels)
    ax.invert_yaxis()

    # Large dynamic range: 0.6M -> 33.5M
    ax.set_xscale("log")
    ax.set_xlim(3e5, 7e7)

    ax.set_xticks([
        5e5,
        1e6,
        5e6,
        1e7,
        5e7,
    ])

    ax.xaxis.set_major_formatter(
        FuncFormatter(log_tick_formatter)
    )

    ax.set_title(
        "Configurational scale",
        loc="left",
    )

    ax.set_xlabel("Configurations / trajectory frames")

    # Major grid only — minor log grids make the panel visually noisy.
    ax.grid(
        axis="x",
        which="major",
        color=GRID,
        linewidth=0.7,
        alpha=0.65,
        zorder=0,
    )

    ax.grid(
        axis="x",
        which="minor",
        visible=False,
    )

    # Value labels
    for yi, value, idx in zip(y, values, valid_indices):

        is_openmolspec = DATASETS[idx] == "OpenMolSpec"

        if value >= 1e6:
            label = f"{value / 1e6:.1f}M"
        else:
            label = f"{value / 1e3:.0f}k"

        ax.annotate(
            label,
            xy=(value, yi),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            fontsize=10.0,
            color=BLUE if is_openmolspec else DARK_GRAY,
            fontweight="bold" if is_openmolspec else "normal",
        )

    clean_axis(ax)
    add_panel_label(ax, "C")

    # ========================================================
    # D. Element coverage
    # ========================================================

    ax = fig.add_subplot(grid[1, 0])

    ELEMENTS = [
        "H", "B", "C", "N", "O", "F",
        "Al", "Si", "P", "S", "Cl", "Br",
        "As", "Se", "I", "Ge",
    ]

    y = np.arange(len(DATASETS))

    for yi, name in enumerate(DATASETS):

        for xi, element in enumerate(ELEMENTS):

            if element in ELEMENT_SETS[name]:

                color = BLUE if name == "OpenMolSpec" else GRAY

                ax.barh(
                    yi,
                    0.82,
                    left=xi - 0.41,
                    height=0.58,
                    color=color,
                    edgecolor="none",
                )

    # Dataset labels
    ax.set_yticks(y, names_year)
    ax.invert_yaxis()

    # Element names directly on x-axis
    ax.set_xticks(
        np.arange(len(ELEMENTS)),
        ELEMENTS,
    )

    ax.set_xlim(-0.6, len(ELEMENTS) - 0.4)

    ax.set_title(
        "Element coverage",
        loc="left",
    )

    ax.set_xlabel("Chemical elements")

    # Vertical separators
    for x in np.arange(len(ELEMENTS) - 1) + 0.5:
        ax.axvline(
            x,
            color=GRID,
            linewidth=0.6,
            alpha=0.45,
            zorder=0,
        )

    ax.tick_params(
        axis="x",
        labelsize=10.0,
    )

    # Optional note for ChEMBL
    chembl_idx = DATASETS.index("ChEMBL IR/Raman")

    ax.text(
        len(ELEMENTS) - 0.2,
        chembl_idx,
        "*",
        ha="left",
        va="center",
        fontsize=10.5,
        color=DARK_GRAY,
    )

    clean_axis(ax)
    add_panel_label(ax, "D")

    # ========================================================
    # E. Released data-type coverage
    # ========================================================

    ax = fig.add_subplot(grid[1, 1])

    DATA_TYPES = [
        "IR",
        "Raman",
        "NMR",
        "Energy",
        "Forces",
        "Trajectories",
    ]

    DATA_TYPE_SETS = {
        "ANI-1": {
            "Energy",
            "Trajectories",
        },

        "QM7-X": {
            "Energy",
            "Forces",
            "Trajectories",
        },

        "QM9S": {
            "IR",
            "Raman",
            "Energy",
        },

        "QMe14S": {
            "IR",
            "Raman",
            "NMR",
            "Energy",
            "Forces",
            "Trajectories",
        },

        "ChEMBL IR/Raman": {
            "IR",
            "Raman",
        },

        "QCML": {
            "Energy",
            "Forces",
            "Trajectories",
        },

        "SQuIRL": {
            "IR",
        },

        "OpenMolSpec": {
            "IR",
            "Raman",
            "NMR",
            "Energy",
            "Forces",
            "Trajectories",
        },
    }

    y = np.arange(len(DATASETS))

    for yi, name in enumerate(DATASETS):

        for xi, data_type in enumerate(DATA_TYPES):

            if data_type in DATA_TYPE_SETS[name]:

                # Different functional categories use subtle colors,
                # while OpenMolSpec remains consistently highlighted.
                if name == "OpenMolSpec":
                    color = BLUE

                elif data_type in {"IR", "Raman", "NMR"}:
                    color = PURPLE

                elif data_type in {"Energy", "Forces"}:
                    color = GREEN

                else:
                    color = ORANGE

                ax.barh(
                    yi,
                    0.82,
                    left=xi - 0.41,
                    height=0.58,
                    color=color,
                    edgecolor="none",
                )

    ax.set_yticks(y, names_year)
    ax.invert_yaxis()

    ax.set_xticks(
        np.arange(len(DATA_TYPES)),
        DATA_TYPES,
    )

    ax.set_xlim(-0.6, len(DATA_TYPES) - 0.4)

    ax.set_title(
        "Released data-type coverage",
        loc="left",
    )

    ax.set_xlabel("Released data types")

    for x in np.arange(len(DATA_TYPES) - 1) + 0.5:
        ax.axvline(
            x,
            color=GRID,
            linewidth=0.6,
            alpha=0.45,
            zorder=0,
        )

    ax.tick_params(
        axis="x",
        rotation=20,
        labelsize=10.0,
    )

    clean_axis(ax)
    add_panel_label(ax, "E")

    # ========================================================
    # F. OpenMolSpec processing funnel
    # ========================================================

    ax = fig.add_subplot(grid[1, 2])

    if not source.empty and "frequency_logs" in source.columns:
        frequency_input = int(source["frequency_logs"].sum())
    else:
        frequency_input = 1_319_379

    funnel_labels = [
        "Frequency input",
        "Frequency parsed",
        "NMR parsed",
        "Strict tri-modal records",
        "Strict tri-modal unique",
    ]

    funnel_values = np.array([
        frequency_input,
        summary["frequency_success"],
        summary["nmr_success"],
        summary["tri_modal_records"],
        summary["tri_modal_unique_inchikey"],
    ])

    funnel_colors = [
        "#DCE4EF",
        ORANGE,
        GREEN,
        PURPLE,
        BLUE,
    ]

    y = np.arange(len(funnel_labels))

    ax.barh(
        y,
        funnel_values,
        color=funnel_colors,
        height=0.60,
        edgecolor="none",
    )

    ax.set_yticks(y, funnel_labels)
    ax.invert_yaxis()

    ax.set_xlim(
        0,
        max(funnel_values) * 1.23,
    )

    ax.set_title(
        "OpenMolSpec processing yield",
        loc="left",
    )

    ax.set_xlabel("Records / unique molecules")

    ax.xaxis.set_major_formatter(
        FuncFormatter(log_tick_formatter)
    )

    ax.grid(
        axis="x",
        alpha=0.65,
        linewidth=0.7,
        color=GRID,
    )

    ax.set_axisbelow(True)

    for yi, value in enumerate(funnel_values):

        if yi == 0:
            annotation = human_number(value, decimals=2)

        else:
            retention = 100 * value / funnel_values[0]

            annotation = (
                f"{human_number(value, decimals=2)}"
                f"  ({retention:.1f}%)"
            )

        ax.text(
            value + max(funnel_values) * 0.015,
            yi,
            annotation,
            va="center",
            fontsize=10.0,
            color=BLUE if yi == len(funnel_values) - 1 else DARK_GRAY,
            fontweight="bold" if yi == len(funnel_values) - 1 else "normal",
        )

    clean_axis(ax)
    add_panel_label(ax, "F")

    # ========================================================
    # Global title and notes
    # ========================================================

    fig.suptitle(
        "OpenMolSpec: large-scale multimodal molecular spectroscopy "
        "with quantum-chemical trajectories",
        fontsize=23.0,
        fontweight="bold",
        color=TEXT,
        x=0.065,
        ha="left",
        y=0.965,
    )

    fig.text(
        0.065,
        0.925,
        "Comparison with representative molecular quantum-chemistry "
        "and spectroscopy datasets",
        fontsize=12.5,
        color=DARK_GRAY,
        ha="left",
    )

    # footnote = (
    #     "External statistics are approximate headline values reported by the original "
    #     "dataset publications/releases and are not recomputed under a common protocol. "
    #     "Configuration counts may refer to conformations, AIMD structures, or optimization "
    #     "frames depending on the dataset. "
    #     "*The ChEMBL IR/Raman publication does not explicitly report a complete element "
    #     "whitelist; the displayed count follows the comparison assumption used here."
    # )

    # fig.text(
    #     0.065,
    #     0.025,
    #     footnote,
    #     fontsize=7.7,
    #     color="#657487",
    #     ha="left",
    #     va="bottom",
    #     wrap=True,
    # )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fig.savefig(
        output,
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )

    # Optional vector version for papers.
    if output.suffix.lower() == ".png":
        pdf_output = output.with_suffix(".pdf")

        fig.savefig(
            pdf_output,
            bbox_inches="tight",
            facecolor="white",
        )

        print(f"Saved {pdf_output}")

    plt.close(fig)

    print(f"Saved {output}")


# ============================================================
# CLI
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Root directory of the OpenMolSpec repository.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "docs/figures/openmolspec_overview.png"
        ),
        help="Output figure path.",
    )

    args = parser.parse_args()

    output = (
        args.output
        if args.output.is_absolute()
        else args.root / args.output
    )

    overview_plot(
        root=args.root,
        output=output,
    )


if __name__ == "__main__":
    main()
