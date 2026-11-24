"""Render the three-channel WanJuan example from its saved numerical output."""

import argparse
import json
from pathlib import Path

from matplotlib import pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
MEASURED = "#98471B"
PREDICTED = "#136A82"


def peak_rug(ax, observed, predicted, limits):
    ax.vlines(observed, 0.74, 1.12, color=MEASURED, linewidth=1.8)
    ax.vlines(predicted, -0.1, 0.28, color=PREDICTED, linewidth=1.8)
    ax.set(
        xlim=limits,
        ylim=(-0.32, 1.35),
        yticks=[0.09, 0.93],
        yticklabels=["Predicted", "Reported"],
    )
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=ROOT / "results/forward_wanjuan_example.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    fig, axes = plt.subplots(1, 3, figsize=(10.6, 3.35), layout="constrained")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    h = data["proton"]
    reported = [(a + b) / 2 for a, b in h["observed_intervals_ppm"]]
    peak_rug(axes[0], reported, h["predicted_ppm"], (10, 0))
    axes[0].set(title="a   Proton peak positions", xlabel="¹H shift (ppm)")
    p = data["phosphorus"]
    predicted = [r["prediction_ppm"] for r in p["predicted_environments"]]
    peak_rug(axes[1], [p["observed_ppm"]], predicted, (14.15, 13.55))
    axes[1].set(title="b   Phosphorus shift", xlabel="³¹P shift (ppm)")
    axes[1].annotate(
        f'{p["observed_ppm"]:.2f}',
        (p["observed_ppm"], 1.12),
        (0, 4),
        textcoords="offset points",
        ha="center",
        color=MEASURED,
    )
    axes[1].annotate(
        f"{predicted[0]:.2f}",
        (predicted[0], 0.28),
        (0, 4),
        textcoords="offset points",
        ha="center",
        color=PREDICTED,
    )
    ax = axes[2]
    hsqc = data["hsqc"]
    c, h = zip(*(r["ppm"] for r in hsqc["hsqc_predicted"]))
    ax.scatter(h, c, c=PREDICTED, s=24, alpha=0.8, linewidths=0)
    c, h = zip(*hsqc["hsqc_measured"])
    ax.scatter(
        h, c, marker="D", s=52, facecolor="none", edgecolor=MEASURED, linewidth=1.7
    )
    ax.invert_xaxis()
    ax.invert_yaxis()
    ax.margins(0.16)
    ax.set(
        title="c   HSQC cross-peaks", xlabel="¹H shift (ppm)", ylabel="¹³C shift (ppm)"
    )
    ax.legend(
        handles=[
            Line2D(
                [],
                [],
                linestyle="none",
                marker="D",
                markerfacecolor="none",
                markeredgecolor=MEASURED,
                label="Reported pair",
            ),
            Line2D(
                [], [], linestyle="none", marker="o", color=PREDICTED, label="Predicted"
            ),
        ],
        loc="upper left",
        fontsize=8,
        frameon=False,
    )
    fig.savefig(args.output, bbox_inches="tight", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
