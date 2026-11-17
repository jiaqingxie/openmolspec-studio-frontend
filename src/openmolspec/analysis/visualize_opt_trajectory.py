"""Visualize one molecular optimization trajectory as an animated GIF."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.animation import FuncAnimation, PillowWriter
from rdkit import Chem


ATOM_COLORS = {
    1: "#E8E8E8",
    6: "#303030",
    7: "#3050F8",
    8: "#FF0D0D",
    9: "#90E050",
    15: "#FF8000",
    16: "#FFFF30",
    17: "#1FF01F",
    35: "#A62929",
    53: "#940094",
}


def align_coordinates(reference, coordinates):
    """Align two molecular coordinate arrays for geometric comparison."""
    reference_centered = reference - reference.mean(axis=0)
    coordinates_centered = coordinates - coordinates.mean(axis=0)
    covariance = coordinates_centered.T @ reference_centered
    left, _, right = np.linalg.svd(covariance)
    rotation = left @ right
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right
    return coordinates_centered @ rotation


def infer_bonds(atomic_numbers, coordinates, scale=1.25):
    """Infer molecular bonds from elements and Cartesian coordinates."""
    periodic_table = Chem.GetPeriodicTable()
    bonds = []
    for left in range(len(atomic_numbers)):
        for right in range(left + 1, len(atomic_numbers)):
            if atomic_numbers[left] == atomic_numbers[right] == 1:
                continue
            cutoff = scale * (
                periodic_table.GetRcovalent(int(atomic_numbers[left]))
                + periodic_table.GetRcovalent(int(atomic_numbers[right]))
            )
            distance = np.linalg.norm(coordinates[left] - coordinates[right])
            if 0.4 < distance <= cutoff:
                bonds.append((left, right))
    return bonds


def main():
    """Run the visualize opt trajectory command-line workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Trajectory pickle")
    parser.add_argument("--sample-id", help="Molecule identifier; defaults to the longest trajectory")
    parser.add_argument("--output", default="trajectory_demo.gif")
    parser.add_argument("--max-frames", type=int, default=80)
    parser.add_argument("--fps", type=int, default=8)
    args = parser.parse_args()

    frame = pd.read_pickle(args.input)
    sample_id = args.sample_id
    if sample_id is None:
        sample_id = frame.groupby("sample_id").size().idxmax()
    trajectory = frame[frame["sample_id"] == sample_id].sort_values("step_index").reset_index(drop=True)
    if trajectory.empty:
        parser.error(f"sample ID not found: {sample_id}")

    selected = np.linspace(0, len(trajectory) - 1, min(args.max_frames, len(trajectory)), dtype=int)
    trajectory = trajectory.iloc[np.unique(selected)].reset_index(drop=True)
    atomic_numbers = np.asarray(trajectory.iloc[0]["atomic_numbers"], dtype=np.int32)
    reference = np.asarray(trajectory.iloc[-1]["coordinates"], dtype=np.float64)
    coordinates = np.stack([
        align_coordinates(reference, np.asarray(value, dtype=np.float64))
        for value in trajectory["coordinates"]
    ])
    bonds = infer_bonds(atomic_numbers, coordinates[-1])

    energies = trajectory["energy"].to_numpy(dtype=float)
    relative_energies = (energies - np.nanmin(energies)) * 627.509474
    max_forces = np.asarray([
        np.nan if value is None else np.linalg.norm(np.asarray(value), axis=1).max()
        for value in trajectory["forces"]
    ])

    figure = plt.figure(figsize=(11, 5.5), constrained_layout=True)
    molecule_axis = figure.add_subplot(1, 2, 1, projection="3d")
    metric_axis = figure.add_subplot(1, 2, 2)
    atom_colors = [ATOM_COLORS.get(int(number), "#B0B0B0") for number in atomic_numbers]
    atom_sizes = [45 if number == 1 else 95 for number in atomic_numbers]

    extent = np.max(np.abs(coordinates)) * 1.08
    extent = max(float(extent), 1.0)
    molecule_axis.set_xlim(-extent, extent)
    molecule_axis.set_ylim(-extent, extent)
    molecule_axis.set_zlim(-extent, extent)
    molecule_axis.set_box_aspect((1, 1, 1))
    molecule_axis.set_axis_off()

    steps = trajectory["step_index"].to_numpy()
    metric_axis.plot(steps, relative_energies, color="#2667FF", linewidth=2, label="Relative energy")
    metric_axis.set_xlabel("Optimization step")
    metric_axis.set_ylabel("Relative energy (kcal/mol)", color="#2667FF")
    metric_axis.tick_params(axis="y", labelcolor="#2667FF")
    force_axis = metric_axis.twinx()
    force_axis.plot(steps, max_forces, color="#E4572E", linewidth=1.7, alpha=0.8, label="Maximum atomic force")
    force_axis.set_ylabel("Max atomic force (Hartree/Bohr)", color="#E4572E")
    force_axis.tick_params(axis="y", labelcolor="#E4572E")
    energy_marker, = metric_axis.plot([], [], "o", color="#2667FF", markersize=7)
    force_marker, = force_axis.plot([], [], "o", color="#E4572E", markersize=7)

    def update(frame_index):
        molecule_axis.cla()
        molecule_axis.set_xlim(-extent, extent)
        molecule_axis.set_ylim(-extent, extent)
        molecule_axis.set_zlim(-extent, extent)
        molecule_axis.set_box_aspect((1, 1, 1))
        molecule_axis.set_axis_off()
        xyz = coordinates[frame_index]
        for left, right in bonds:
            molecule_axis.plot(*xyz[[left, right]].T, color="#808080", linewidth=1.5, alpha=0.8)
        molecule_axis.scatter(
            xyz[:, 0], xyz[:, 1], xyz[:, 2], s=atom_sizes, c=atom_colors,
            edgecolors="#202020", linewidths=0.35, depthshade=True,
        )
        step = steps[frame_index]
        molecule_axis.set_title(
            f"{sample_id}  |  step {step}/{steps[-1]}\n"
            f"Erel={relative_energies[frame_index]:.3f} kcal/mol, "
            f"Fmax={max_forces[frame_index]:.5f} Hartree/Bohr"
        )
        energy_marker.set_data([step], [relative_energies[frame_index]])
        force_marker.set_data([step], [max_forces[frame_index]])
        return energy_marker, force_marker

    animation = FuncAnimation(figure, update, frames=len(trajectory), interval=1000 / args.fps, blit=False)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    animation.save(output, writer=PillowWriter(fps=args.fps), dpi=120)
    plt.close(figure)
    print(f"Saved {len(trajectory)} frames for {sample_id} to {output}")


if __name__ == "__main__":
    main()
