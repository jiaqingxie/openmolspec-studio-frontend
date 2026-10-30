"""Streaming Gaussian optimization-trajectory parser.

The parser associates geometry, energy, forces and convergence diagnostics by
the order of optimization cycles in a Gaussian log.  Gaussian's printed
forces are stored with the explicit convention ``F = -dE/dR``.
"""

import re
from typing import Any, Dict, List, Optional

import numpy as np


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DEde][-+]?\d+)?"
_NUMBER_RE = re.compile(_NUMBER)
_SCF_RE = re.compile(
    rf"SCF Done:\s+E\([^)]*\)\s*=\s*({_NUMBER}).*?after\s+(\d+)\s+cycles",
    re.IGNORECASE,
)


def _float(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))


def _is_separator(line: str) -> bool:
    return bool(re.match(r"^\s*-{5,}\s*$", line))


def _parse_orientation(lines: List[str], start: int):
    """Parse an Input/Standard orientation block after its marker."""

    header = None
    for index in range(start + 1, min(len(lines), start + 12)):
        if "Coordinates" in lines[index]:
            header = index
            break
    if header is None:
        return None, start

    data_start = header + 1
    while data_start < len(lines) and not _is_separator(lines[data_start]):
        data_start += 1
    data_start += 1
    atoms = []
    coordinates = []
    index = data_start
    row_re = re.compile(
        rf"^\s*\d+\s+(\d+)\s+[-+]?\d+\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*$"
    )
    while index < len(lines) and not _is_separator(lines[index]):
        match = row_re.match(lines[index])
        if match:
            atoms.append(int(match.group(1)))
            coordinates.append([_float(match.group(2)), _float(match.group(3)), _float(match.group(4))])
        index += 1
    if not atoms:
        return None, index
    return {
        "atomic_numbers": np.asarray(atoms, dtype=np.int32),
        "coordinates": np.asarray(coordinates, dtype=np.float32),
    }, index


def _parse_forces(lines: List[str], start: int):
    """Parse a Gaussian ``Forces (Hartrees/Bohr)`` table."""

    header = start
    while header < min(len(lines), start + 8) and "X" not in lines[header]:
        header += 1
    data_start = header + 1
    while data_start < len(lines) and not _is_separator(lines[data_start]):
        data_start += 1
    data_start += 1
    forces = []
    index = data_start
    row_re = re.compile(rf"^\s*\d+\s+\d+\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})")
    while index < len(lines) and not _is_separator(lines[index]):
        match = row_re.match(lines[index])
        if match:
            forces.append([_float(match.group(1)), _float(match.group(2)), _float(match.group(3))])
        index += 1
    if not forces:
        return None, index
    return np.asarray(forces, dtype=np.float32), index


def _convergence_value(line: str):
    values = _NUMBER_RE.findall(line)
    if len(values) < 2:
        return None
    # First number is the current value; second is Gaussian's threshold.
    return _float(values[0]), _float(values[1]), line.strip().upper().endswith("YES")


def parse_gaussian_trajectory(path: str) -> Dict[str, Any]:
    """Parse all optimization-cycle information from one Gaussian log."""

    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        lines = handle.readlines()

    steps: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    optimization_completed = False
    normal_termination = False
    frequencies: List[float] = []

    for index, line in enumerate(lines):
        lower = line.lower()
        if "orientation:" in lower and ("input orientation:" in lower or "standard orientation:" in lower):
            geometry, _ = _parse_orientation(lines, index)
            if geometry is not None:
                current = {
                    "step_index": len(steps),
                    **geometry,
                }
                steps.append(current)
            continue

        if current is None:
            if "frequencies --" in lower:
                frequencies.extend(_float(value) for value in _NUMBER_RE.findall(line.split("--", 1)[1]))
            continue

        match = _SCF_RE.search(line)
        if match:
            current["energy"] = _float(match.group(1))
            current["scf_cycles"] = int(match.group(2))
            continue

        if "forces (hartrees/bohr)" in lower:
            forces, _ = _parse_forces(lines, index)
            if forces is not None:
                current["forces"] = forces
            continue

        labels = (
            ("Maximum Force", "max_force", "max_force_threshold"),
            ("RMS     Force", "rms_force", "rms_force_threshold"),
            ("Maximum Displacement", "max_displacement", "max_displacement_threshold"),
            ("RMS     Displacement", "rms_displacement", "rms_displacement_threshold"),
        )
        for label, value_key, threshold_key in labels:
            if label.lower() in lower:
                parsed = _convergence_value(line)
                if parsed is not None:
                    value, threshold, converged = parsed
                    current[value_key] = value
                    current[threshold_key] = threshold
                    current.setdefault("convergence_checks", {})[value_key] = converged
                break

        if "optimization completed." in lower:
            optimization_completed = True
        if "normal termination of gaussian" in lower:
            normal_termination = True
        if "frequencies --" in lower:
            frequencies.extend(_float(value) for value in _NUMBER_RE.findall(line.split("--", 1)[1]))

    cycle_keys = (
        "energy", "forces", "max_force", "rms_force",
        "max_displacement", "rms_displacement",
    )
    unlabeled_geometry_frames = sum(
        not any(key in step for key in cycle_keys) for step in steps
    )
    # Frequency jobs can print extra Input orientation blocks after the
    # optimization has ended.  They are not optimization cycles when they
    # carry no energy, force, or convergence diagnostics.
    steps = [step for step in steps if any(key in step for key in cycle_keys)]
    for new_index, step in enumerate(steps):
        step["step_index"] = new_index

    if optimization_completed and steps:
        steps[-1]["is_converged"] = True
    for step in steps:
        checks = step.pop("convergence_checks", {})
        if "is_converged" not in step and checks:
            step["is_converged"] = bool(checks) and all(checks.values())
        else:
            step.setdefault("is_converged", False)
        step["is_final"] = False
        step["n_steps"] = len(steps)
        step.setdefault("energy", None)
        step.setdefault("scf_cycles", None)
        step.setdefault("forces", None)
        for key in (
            "max_force", "rms_force", "max_displacement", "rms_displacement",
            "max_force_threshold", "rms_force_threshold",
            "max_displacement_threshold", "rms_displacement_threshold",
        ):
            step.setdefault(key, None)
    if steps:
        steps[-1]["is_final"] = True
        steps[-1]["final_frequencies"] = np.asarray(frequencies, dtype=np.float64)
        steps[-1]["n_imaginary_frequencies"] = int(np.sum(np.asarray(frequencies) < 0))
        steps[-1]["minimum_frequency"] = float(min(frequencies)) if frequencies else None
    for step in steps[:-1]:
        step["final_frequencies"] = None
        step["n_imaginary_frequencies"] = None
        step["minimum_frequency"] = None

    return {
        "steps": steps,
        "n_steps": len(steps),
        "unlabeled_geometry_frames": int(unlabeled_geometry_frames),
        "is_converged": optimization_completed,
        "normal_termination": normal_termination,
        "frequencies": np.asarray(frequencies, dtype=np.float64),
        "source_file": path,
    }
