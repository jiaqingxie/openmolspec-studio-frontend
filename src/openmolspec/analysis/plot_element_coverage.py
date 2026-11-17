"""Plot documented element coverage of OpenMolSpec and public reference sets.

OpenMolSpec is derived from the current descriptor cache. Reference element
sets are restricted to datasets whose published descriptions state the
element range explicitly. Hydrogen is shown as present chemically, including
when it is implicit in a SMILES string.

Example:
    python -m openmolspec.analysis.plot_element_coverage
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import pandas as pd


ELEMENTS = [
    "H", "B", "C", "N", "O", "F", "Al", "Si", "P", "S", "Cl", "Br",
    "As", "Se", "I", "Ge",
]

# Element sets used for this project-level comparison. These are documented
# or explicitly assigned comparison assumptions, not atom counts.
REFERENCE_ELEMENTS = {
    "ANI-1": {"H", "C", "N", "O"},
    "QM9S": {"H", "C", "N", "O", "F"},
    "SQuIRL": {"H", "C", "N", "O", "F"},
    "QM7-X": {"H", "C", "N", "O", "S", "Cl"},
    "ChEMBL IR/Raman": {"H", "C", "N", "O", "F", "P", "S", "Cl", "Br"},
    "QCML": {"H", "C", "N", "O"},
    "QMe14S": {"H", "B", "C", "N", "O", "F", "Al", "Si", "P", "S", "Cl", "Br", "As", "Se"},
}
PUBLIC_YEAR = {
    "ANI-1": 2017,
    "QM9S": 2023,
    "SQuIRL": 2026,
    "QM7-X": 2021,
    "ChEMBL IR/Raman": 2025,
    "QCML": 2025,
    "QMe14S": 2025,
    "OpenMolSpec": 2026,
}


def openmolspec_elements(root: Path) -> set[str]:
    """Collect the element coverage of the OpenMolSpec records."""
    path = root / "reports/analysis/chemical_descriptors.parquet"
    table = pd.read_parquet(path, columns=["elements"])
    result: set[str] = set()
    for value in table["elements"].dropna():
        result.update(str(value).split(","))
    # Most H atoms are implicit in canonical SMILES. Include H explicitly for
    # chemical coverage; explicit-H records are also present in the cache.
    result.add("H")
    return result


def coverage_frame(open_elements: set[str]) -> pd.DataFrame:
    """Build a tabular element-coverage summary for the compared collections."""
    sets = dict(REFERENCE_ELEMENTS)
    sets["OpenMolSpec"] = open_elements
    rows = []
    for dataset, elements in sets.items():
        rows.append({"dataset": dataset, **{element: int(element in elements) for element in ELEMENTS}})
    result = pd.DataFrame(rows).set_index("dataset")
    result.index = [f"{name} ({PUBLIC_YEAR[name]})" for name in result.index]
    result["element_count"] = result.sum(axis=1)
    return result


def plot_coverage(frame: pd.DataFrame, output: Path) -> None:
    """Draw the element-coverage comparison."""
    plt.rcParams.update({"font.size": 10, "figure.dpi": 140, "savefig.dpi": 300})
    fig = plt.figure(figsize=(16, 8.5), constrained_layout=True)
    grid = fig.add_gridspec(1, 2, width_ratios=[4.8, 1.7])
    ax = fig.add_subplot(grid[0, 0])
    heat = frame[ELEMENTS]
    image = ax.imshow(
        heat.to_numpy(), aspect="auto",
        cmap=ListedColormap(["#edf2f7", "#2f6fdb"]), vmin=0, vmax=1,
    )
    ax.set_xticks(range(len(ELEMENTS)), ELEMENTS)
    ax.set_yticks(range(len(heat.index)), heat.index)
    for row in range(heat.shape[0]):
        for col in range(heat.shape[1]):
            value = int(heat.iloc[row, col])
            ax.text(col, row, str(value), ha="center", va="center",
                    color="white" if value else "#536273", fontsize=9)
    ax.set_xticks([x - .5 for x in range(1, len(ELEMENTS))], minor=True)
    ax.set_yticks([y - .5 for y in range(1, len(heat.index))], minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.set_title("Element coverage reported for public molecular datasets", fontweight="bold", pad=14)
    ax.set_xlabel("Element symbol")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=0)
    ax.axhline(len(frame.index) - 1, color="#173f73", linewidth=3)

    ax2 = fig.add_subplot(grid[0, 1])
    counts = frame["element_count"].sort_values()
    colors = ["#2f6fdb" if name.startswith("OpenMolSpec") else "#a9b9cc" for name in counts.index]
    ax2.barh(counts.index, counts.values, color=colors)
    ax2.set_title("Documented elements")
    ax2.set_xlabel("Count")
    ax2.grid(axis="x", alpha=.25)
    ax2.set_axisbelow(True)
    for i, value in enumerate(counts.values):
        ax2.text(value + .15, i, str(int(value)), va="center", fontsize=9)

    fig.suptitle("OpenMolSpec element-space comparison", fontsize=18, fontweight="bold")
    fig.text(
        0.01, -0.015,
        "Blue = element included in the comparison set. H is included for chemical coverage even when implicit in SMILES. "
        "QCML and ChEMBL IR/Raman use the element sets specified for this project comparison.",
        ha="left", va="bottom", fontsize=9, color="#444",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    """Run the plot element coverage command-line workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("docs/figures/openmolspec_element_coverage.png"))
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    elements = openmolspec_elements(args.root)
    frame = coverage_frame(elements)
    plot_coverage(frame, output)
    print("OpenMolSpec elements:", ", ".join(sorted(elements)))
    print(frame.to_string())
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
