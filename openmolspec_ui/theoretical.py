from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.constants import atomic_mass, c, elementary_charge


@dataclass(frozen=True)
class HarmonicModes:
    frequencies_cm1: np.ndarray
    cartesian_modes: np.ndarray
    rigid_rank: int


def harmonic_modes(
    hessian_ev_angstrom2: np.ndarray,
    positions_angstrom: np.ndarray,
    masses_amu: np.ndarray,
) -> HarmonicModes:
    """Solve internal harmonic modes using OpenMolSpec's rigid-mode projection."""
    hessian = np.asarray(hessian_ev_angstrom2, dtype=np.float64)
    positions = np.asarray(positions_angstrom, dtype=np.float64)
    masses = np.asarray(masses_amu, dtype=np.float64)
    atoms = len(masses)
    if hessian.shape != (3 * atoms, 3 * atoms) or positions.shape != (atoms, 3):
        raise ValueError("Hessian, positions and masses have incompatible shapes.")
    if not all(np.isfinite(value).all() for value in (hessian, positions, masses)):
        raise ValueError("Theoretical reconstruction received non-finite values.")
    if np.any(masses <= 0):
        raise ValueError("Atomic masses must be positive.")

    symmetric = 0.5 * (hessian + hessian.T)
    centered = positions - np.average(positions, axis=0, weights=masses)
    translations = np.tile(np.eye(3), (atoms, 1)) / np.sqrt(atoms)
    rotations = np.stack(
        [
            np.cross(np.broadcast_to(axis, centered.shape), centered).reshape(-1)
            for axis in np.eye(3)
        ],
        axis=1,
    )
    rotation_u, rotation_s, _ = np.linalg.svd(rotations, full_matrices=False)
    threshold = max(float(rotation_s.max(initial=0.0)) * 1e-7, 1e-14)
    rotation_basis = rotation_u[:, rotation_s > threshold]

    sqrt_mass = np.repeat(np.sqrt(masses), 3)
    rigid_candidates = (
        np.concatenate((translations, rotation_basis), axis=1)
        * sqrt_mass[:, None]
    )
    rigid_u, rigid_s, _ = np.linalg.svd(rigid_candidates, full_matrices=True)
    rigid_threshold = max(float(rigid_s.max(initial=0.0)) * 1e-7, 1e-14)
    rigid_rank = int(np.sum(rigid_s > rigid_threshold))
    internal_basis = rigid_u[:, rigid_rank:]

    mass_weighted = symmetric / sqrt_mass[:, None] / sqrt_mass[None, :]
    projected = internal_basis.T @ mass_weighted @ internal_basis
    eigenvalues, eigenvectors = np.linalg.eigh(0.5 * (projected + projected.T))
    frequencies = (
        np.sign(eigenvalues)
        * np.sqrt(np.abs(eigenvalues) * elementary_charge / (atomic_mass * 1e-20))
        / (2 * np.pi * c * 100)
    )
    mass_weighted_modes = internal_basis @ eigenvectors
    cartesian_modes = mass_weighted_modes / sqrt_mass[:, None]
    return HarmonicModes(frequencies, cartesian_modes, rigid_rank)


def mode_activities(
    cartesian_modes: np.ndarray,
    dipole_derivative: np.ndarray,
    polarizability_derivative: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Project Cartesian response derivatives onto normal modes."""
    modes = np.asarray(cartesian_modes, dtype=np.float64)
    dedipole = np.asarray(dipole_derivative, dtype=np.float64)
    depolar = np.asarray(polarizability_derivative, dtype=np.float64)
    atoms = dedipole.shape[0]
    if dedipole.shape != (atoms, 3, 3) or depolar.shape != (atoms, 3, 3, 3):
        raise ValueError("Response derivative tensors have incompatible shapes.")
    if modes.shape[0] != 3 * atoms:
        raise ValueError("Normal modes and response derivatives have different atom counts.")

    dipole_modes = modes.T @ dedipole.reshape(3 * atoms, 3)
    ir_activity = np.einsum("mi,mi->m", dipole_modes, dipole_modes)

    polar_modes = np.einsum(
        "cm,cij->mij", modes, depolar.reshape(3 * atoms, 3, 3)
    )
    isotropic = np.trace(polar_modes, axis1=1, axis2=2) / 3.0
    xx, yy, zz = polar_modes[:, 0, 0], polar_modes[:, 1, 1], polar_modes[:, 2, 2]
    xy, yz, zx = polar_modes[:, 0, 1], polar_modes[:, 1, 2], polar_modes[:, 2, 0]
    anisotropy_sq = 0.5 * (
        (xx - yy) ** 2
        + (yy - zz) ** 2
        + (zz - xx) ** 2
        + 6.0 * (xy**2 + yz**2 + zx**2)
    )
    raman_activity = 45.0 * isotropic**2 + 7.0 * anisotropy_sq
    return np.maximum(ir_activity, 0.0), np.maximum(raman_activity, 0.0)


def _minmax(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    low, high = float(values.min()), float(values.max())
    if not np.isfinite(low) or not np.isfinite(high):
        raise ValueError("Reconstructed spectrum contains non-finite values.")
    if high <= low:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0).astype(np.float32)


def reconstruct_spectra(
    hessian: np.ndarray,
    positions: np.ndarray,
    atomic_numbers: np.ndarray,
    dedipole: np.ndarray,
    depolar: np.ndarray,
    *, qm9s_modes: bool = False,
) -> dict[str, Any]:
    """Rebuild OpenMolSpec-style theoretical IR/Raman spectra from tensors."""
    from ase.data import atomic_masses
    from openmolspec.core.constants import SPECTRUM_PARAMETERS
    from openmolspec.parsing.gaussian import lorentzian_broadening, raman_intensity

    numbers = np.asarray(atomic_numbers, dtype=np.int64)
    modes = harmonic_modes(hessian, positions, atomic_masses[numbers])
    ir_activity, raman_activity = mode_activities(
        modes.cartesian_modes, dedipole, depolar
    )
    frequencies = (
        modes.frequencies_cm1
        * float(SPECTRUM_PARAMETERS["frequency_scaling_factor"])
    )
    valid = np.isfinite(frequencies) & (frequencies > 0)
    frequencies = frequencies[valid]
    ir_activity = ir_activity[valid]
    raman_activity = raman_activity[valid]
    if not len(frequencies):
        raise ValueError("Predicted Hessian has no positive internal vibrational modes.")

    grid = np.linspace(
        float(SPECTRUM_PARAMETERS["frequency_min_cm-1"]),
        float(SPECTRUM_PARAMETERS["frequency_max_cm-1"]),
        int(SPECTRUM_PARAMETERS["frequency_grid_size"]),
    )
    ir = lorentzian_broadening(
        frequencies,
        ir_activity,
        grid,
        float(SPECTRUM_PARAMETERS["ir_broadening_sigma_cm-1"]),
    )
    broadened_raman = lorentzian_broadening(
        frequencies,
        raman_activity,
        grid,
        float(SPECTRUM_PARAMETERS["raman_broadening_sigma_cm-1"]),
    )
    raman = raman_intensity(
        grid,
        broadened_raman,
        temp=float(SPECTRUM_PARAMETERS["raman_temperature_K"]),
        excitation_wavelength=float(
            SPECTRUM_PARAMETERS["raman_excitation_wavelength_nm"]
        ),
    )
    result = {
        "wavenumber": grid.astype(np.float32),
        "ir": _minmax(ir),
        "raman": _minmax(raman),
        "mode_frequencies": frequencies.astype(np.float32),
        "ir_activities": ir_activity.astype(np.float32),
        "raman_activities": raman_activity.astype(np.float32),
        "rigid_rank": modes.rigid_rank,
    }

    if qm9s_modes:
        from rdkit import Chem

        periodic_table = Chem.GetPeriodicTable()
        masses = np.array([periodic_table.GetMostCommonIsotopeMass(int(z)) for z in numbers])
        normal_modes = harmonic_modes(hessian, positions, masses)
        mode_ir, mode_raman = mode_activities(normal_modes.cartesian_modes, dedipole, depolar)
        result["qm9s_mode_frequencies"] = normal_modes.frequencies_cm1 * float(SPECTRUM_PARAMETERS["frequency_scaling_factor"])
        result["qm9s_ir_activities"] = mode_ir
        result["qm9s_raman_activities"] = mode_raman
    return result
