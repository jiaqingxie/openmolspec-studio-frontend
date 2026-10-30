"""Draw the OpenMolSpec benchmark-utility overview figure.

The figure summarizes physical validation, 200k-to-1M scaling, and
incremental spectroscopic-modality complementarity using frozen manuscript
evidence.  It intentionally reports frequency-domain Hessian errors rather
than only Cartesian matrix-element errors.

Example
-------
python -m openmolspec.analysis.plot_benchmark_overview
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import PercentFormatter


BLUE = "#2F6FDB"
LIGHT_BLUE = "#A9C5F5"
PURPLE = "#7957C8"
GRAY = "#A9B9CC"
DARK_GRAY = "#536273"
GRID = "#D7DEE8"
TEXT = "#263442"


def repository_root() -> Path:
    """Return the repository root for the standard ``src`` layout."""

    return Path(__file__).resolve().parents[3]


def resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _panel_title(axis: plt.Axes, title: str) -> None:
    axis.set_title(title, loc="left", fontweight="bold", pad=10)


def _paired_bar_panel(
    axis: plt.Axes,
    title: str,
    categories: Sequence[str],
    values_200k: Sequence[float],
    values_1m: Sequence[float],
    value_formats: Sequence[str],
    y_limits: tuple[float, float],
) -> None:
    """Draw paired 200k/1M bars after normalizing each 200k result to one."""

    baseline = np.asarray(values_200k, dtype=float)
    scaled = np.asarray(values_1m, dtype=float)
    relative = scaled / baseline
    x = np.arange(len(categories), dtype=float)
    width = 0.34
    bars_200k = axis.bar(
        x - width / 2,
        np.ones_like(relative),
        width,
        color=LIGHT_BLUE,
        label="200k",
        zorder=2,
    )
    bars_1m = axis.bar(
        x + width / 2,
        relative,
        width,
        color=BLUE,
        label="1M",
        zorder=3,
    )

    axis.set_xticks(x, categories)
    axis.set_ylabel("Relative test MAE (200k = 1.0)")
    axis.set_ylim(*y_limits)
    axis.axhline(1.0, color=GRAY, linestyle="--", linewidth=1.0, zorder=1)
    axis.grid(axis="y", color=GRID, alpha=0.7)
    axis.set_axisbelow(True)
    axis.legend(frameon=False, ncol=2, loc="upper right")
    _panel_title(axis, title)

    for index, (old, new, value, value_format) in enumerate(
        zip(baseline, scaled, relative, value_formats)
    ):
        axis.annotate(
            value_format.format(old),
            xy=(bars_200k[index].get_x() + bars_200k[index].get_width() / 2, 1.0),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7.3,
            color=DARK_GRAY,
        )
        axis.annotate(
            value_format.format(new),
            xy=(bars_1m[index].get_x() + bars_1m[index].get_width() / 2, value),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7.3,
            color=BLUE,
            fontweight="bold",
        )


def _generation_curve(
    result: dict[str, object],
) -> np.ndarray:
    return np.asarray(
        [result[f"exact_canonical_top{rank}"] for rank in (1, 3, 5, 10)],
        dtype=float,
    )


def plot_benchmark_overview(
    summary: dict[str, object],
    evaluations: dict[str, object],
    output: Path,
) -> dict[str, object]:
    """Create the four-panel benchmark overview and return plotted values."""

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 9.5,
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
    figure, axes = plt.subplots(2, 2, figsize=(14.5, 10.2), constrained_layout=True)

    # A: structure-to-response scaling, including frequency-domain Hessian error.
    h200r5 = evaluations["hessian_200k_r5"]["result"]["means"]
    h1mr5 = evaluations["hessian_1000k_r5"]["result"]["means"]
    nmr = summary["structure2nmr"]
    nmr_200 = nmr["200k"]["test"]
    nmr_1m = nmr["1000k"]["test"]
    response = summary["structure2response"]
    response_200 = response["200k"]
    response_1m = response["1000k"]
    structure_200 = [
        h200r5["prediction_frequency_mae_cm1"],
        nmr_200["MAE_H"],
        nmr_200["MAE_C"],
        response_200["dedipole"]["test"]["MAE_dedipole"],
        response_200["depolar"]["test"]["MAE_depolar"],
    ]
    structure_1m = [
        h1mr5["prediction_frequency_mae_cm1"],
        nmr_1m["MAE_H"],
        nmr_1m["MAE_C"],
        response_1m["dedipole"]["test"]["MAE_dedipole"],
        response_1m["depolar"]["test"]["MAE_depolar"],
    ]
    structure_names = [
        "Frequency\n(cm⁻¹)",
        r"$^1$H shift" + "\n(ppm)",
        r"$^{13}$C shift" + "\n(ppm)",
        "Dipole deriv.\n(D Å⁻¹)",
        "Polar. deriv.\n(Bohr³ Å⁻¹)",
    ]
    _paired_bar_panel(
        axes[0, 0],
        "A  Structure → spectroscopic response scaling",
        structure_names,
        structure_200,
        structure_1m,
        ["{:.3f}", "{:.4f}", "{:.4f}", "{:.4f}", "{:.4f}"],
        (0.86, 1.04),
    )

    # B: multimodal spectrum-to-property scaling.
    properties = summary["spectrum2property"]
    property_keys = ["dipole", "polar_iso", "gap"]
    metric_keys = ["MAE_dipole_total", "MAE_polar_iso", "MAE_gap"]
    property_names = ["Dipole magnitude", "Isotropic polarizability", "HOMO–LUMO gap"]
    units = ["D", "Å³", "eV"]
    property_200 = [properties["200k"][key]["test"][metric] for key, metric in zip(property_keys, metric_keys)]
    property_1m = [properties["1000k"][key]["test"][metric] for key, metric in zip(property_keys, metric_keys)]
    _paired_bar_panel(
        axes[0, 1],
        "B  Spectrum → property scaling",
        ["Dipole magnitude\n(D)", "Isotropic polar.\n(Å³)", "HOMO–LUMO gap\n(eV)"],
        property_200,
        property_1m,
        ["{:.3f}", "{:.3f}", "{:.3f}"],
        (0.77, 1.04),
    )

    # C: training-set scaling for full-modality generation.
    ranks = np.asarray([1, 3, 5, 10])
    generation_200 = _generation_curve(evaluations["vib2mol_200k_generation"]["result"])
    generation_1m = _generation_curve(evaluations["vib2mol_1000k_generation"]["result"])
    axis = axes[1, 0]
    axis.plot(ranks, generation_200, marker="o", markersize=6, linewidth=2.5,
              color="#7895C5", label="200k")
    axis.plot(ranks, generation_1m, marker="o", markersize=6, linewidth=2.8,
              color=BLUE, label="1M")
    axis.fill_between(ranks, generation_200, generation_1m, color=LIGHT_BLUE, alpha=0.28)
    axis.set_xticks(ranks, ["@1", "@3", "@5", "@10"])
    axis.set_ylim(0.60, 0.96)
    axis.set_xlabel("Beam rank")
    axis.set_ylabel("Canonical exact match")
    axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.grid(color=GRID, alpha=0.7)
    axis.set_axisbelow(True)
    axis.legend(frameon=False, loc="lower right")
    _panel_title(axis, "C  Spectrum → structure scaling")
    for x, low, high in zip(ranks, generation_200, generation_1m):
        axis.text(x, high + 0.009, f"{high:.1%}", ha="center", va="bottom", fontsize=7.8, color=BLUE)
        axis.text(x, low - 0.010, f"{low:.1%}", ha="center", va="top", fontsize=7.8, color=DARK_GRAY)

    # D: fixed-budget modality complementarity at one million molecules.
    ir = _generation_curve(evaluations["vib2mol_1000k_ir_generation"]["result"])
    ir_raman = _generation_curve(evaluations["vib2mol_1000k_ir_raman_generation"]["result"])
    full = generation_1m
    axis = axes[1, 1]
    for values, color, label in (
        (ir, DARK_GRAY, "IR"),
        (ir_raman, PURPLE, "IR + Raman"),
        (full, BLUE, r"IR + Raman + $^1$H/$^{13}$C NMR"),
    ):
        axis.plot(ranks, values, marker="o", markersize=5.5, linewidth=2.5, color=color, label=label)
    axis.set_xticks(ranks, ["@1", "@3", "@5", "@10"])
    axis.set_ylim(0.50, 0.96)
    axis.set_xlabel("Beam rank")
    axis.set_ylabel("Canonical exact match")
    axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.grid(color=GRID, alpha=0.7)
    axis.set_axisbelow(True)
    axis.legend(frameon=False, loc="lower right")
    _panel_title(axis, "D  Incremental modality complementarity (1M)")
    for values, color in ((ir, DARK_GRAY), (ir_raman, PURPLE), (full, BLUE)):
        axis.annotate(
            f"{values[0]:.1%}",
            xy=(ranks[0], values[0]),
            xytext=(7, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=8.0,
            color=color,
            fontweight="bold",
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, bbox_inches="tight", facecolor="white")
    figure.savefig(output.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(figure)

    return {
        "hessian_frequency_mae_cm1": {
            "200k_5A": structure_200[0],
            "1000k_5A": structure_1m[0],
            "cutoff_reference_5A": h200r5["cutoff_reference_frequency_mae_cm1"],
        },
        "structure2nmr": {"200k": nmr_200, "1000k": nmr_1m},
        "structure2response": {
            "200k": response_200,
            "1000k": response_1m,
        },
        "spectrum2property_mae": {
            "properties": property_names,
            "units": units,
            "200k": property_200,
            "1000k": property_1m,
        },
        "vib2mol_generation": {
            "ranks": ranks.tolist(),
            "200k_full": generation_200.tolist(),
            "1000k_ir": ir.tolist(),
            "1000k_ir_raman": ir_raman.tolist(),
            "1000k_full": full.tolist(),
        },
    }


def parse_args() -> argparse.Namespace:
    root = repository_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=root / "openmolspec-manuscripts/evidence/benchmark_summary.json",
    )
    parser.add_argument(
        "--evaluations",
        type=Path,
        default=root / "openmolspec-manuscripts/evidence/benchmark_evaluations.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "docs/figures/openmolspec_benchmark_overview.png",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = repository_root()
    summary_path = resolve(root, args.summary)
    evaluations_path = resolve(root, args.evaluations)
    output = resolve(root, args.output)
    plotted = plot_benchmark_overview(
        _load_json(summary_path),
        _load_json(evaluations_path),
        output,
    )
    metadata_path = output.with_suffix(".json")
    metadata_path.write_text(json.dumps(plotted, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Wrote {output.with_suffix('.pdf')}")
    print(f"Wrote {metadata_path}")


if __name__ == "__main__":
    main()
