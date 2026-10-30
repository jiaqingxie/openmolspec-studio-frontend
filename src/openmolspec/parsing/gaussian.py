"""Shared Gaussian log parser used by the extraction entry points.

This module owns the common archive parsing, text-property extraction, tensor
reconstruction and vibrational-spectrum generation logic. The legacy scripts
keep their public CLI and class names, but delegate runtime parsing here.
Scientific defaults are explicit constructor arguments so differences between
legacy workflows remain visible instead of being hidden in duplicated code.
"""

import re
from typing import Any, Dict, Mapping, Optional

import numpy as np
from rdkit import Chem

from openmolspec.core.constants import (
    ANGSTROM_TO_METER,
    BOLTZMANN_CONSTANT,
    CM_TO_HZ,
    PLANCK_CONSTANT,
    SPEED_OF_LIGHT,
    SPECTRUM_PARAMETERS,
)
from openmolspec.core.processing import classify_exception


def lorentzian_broadening(x0, y0, grid, sigma=12.0):
    """Broaden discrete peaks onto a fixed grid with a Lorentzian line shape."""

    x0 = np.asarray(x0, dtype=np.float64)
    y0 = np.asarray(y0, dtype=np.float64)
    grid = np.asarray(grid, dtype=np.float64)
    if len(x0) != len(y0):
        raise ValueError("frequency and intensity lengths differ")
    diff = x0[:, np.newaxis] - grid[np.newaxis, :]
    line = (sigma / (2 * np.pi)) / (diff**2 + 0.25 * sigma**2)
    return np.sum(y0[:, np.newaxis] * line, axis=0)


def raman_intensity(freq, raman_activity, temp=298.0, excitation_wavelength=532.0):
    """Convert Raman activity to intensity using the existing project formula."""

    freq = np.asarray(freq, dtype=np.float64)
    activity = np.asarray(raman_activity, dtype=np.float64)
    if len(freq) != len(activity):
        raise ValueError("Raman frequency and activity lengths differ")
    incident_frequency = CM_TO_HZ / (excitation_wavelength * 1e-7)
    frequency_si = np.where(freq * CM_TO_HZ == 0, 1e-5, freq * CM_TO_HZ)
    activity_si = activity * (ANGSTROM_TO_METER**4) / 45.0
    exponential = np.exp(-PLANCK_CONSTANT * SPEED_OF_LIGHT * frequency_si / (BOLTZMANN_CONSTANT * temp))
    thermal = 1.0 / (1.0 - exponential)
    frequency_factor = ((incident_frequency - frequency_si) ** 4) / frequency_si
    return activity_si * frequency_factor * thermal


class GaussianLogParser:
    """Parse one Gaussian log into the legacy OpenSpec property dictionary."""

    def __init__(
        self,
        file_path: str,
        unique_id: str,
        smiles_map: Optional[Mapping[str, str]] = None,
        *,
        frequency_scaling_factor: float = SPECTRUM_PARAMETERS["frequency_scaling_factor"],
        ir_broadening_sigma: float = SPECTRUM_PARAMETERS["ir_broadening_sigma_cm-1"],
        raman_broadening_sigma: float = SPECTRUM_PARAMETERS["raman_broadening_sigma_cm-1"],
    ):
        self.file_path = file_path
        self.unique_id = unique_id
        self.frequency_scaling_factor = frequency_scaling_factor
        self.ir_broadening_sigma = ir_broadening_sigma
        self.raman_broadening_sigma = raman_broadening_sigma
        self.properties: Dict[str, Any] = {"filename": file_path}
        self.error_type = None
        self.error_message = None
        if smiles_map is not None:
            self.properties["smiles"] = smiles_map.get(unique_id)
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                self.text = handle.read()
            parts = self.text.split("----------------------------------------------------------------------")
            if len(parts) < 2:
                raise ValueError("Invalid Gaussian log format: Archive not found")
            arc_raw = parts[-1].replace("\n ", "").split(r"\@", 1)[0]
            arc_fields = arc_raw.split("\\\\")
            labels = ["job", "input", "notation", "coordinates", "properties", "hessian", "force"]
            self.arc_dict = {labels[i]: arc_fields[i] for i in range(min(len(labels), len(arc_fields)))}
            self.parse_all()
        except Exception as exc:
            self.error_type = classify_exception(exc)
            self.error_message = str(exc)

    def parse_all(self):
        self._parse_coordinates()
        self._parse_archive_properties()
        self._parse_text_properties()
        self._parse_spectrum()
        self._format_tensors()

    def _parse_coordinates(self):
        coordinates = self.arc_dict["coordinates"].split("\\")[1:]
        atoms = []
        xyz = []
        for line in coordinates:
            parts = line.split(",")
            if len(parts) != 4:
                continue
            atoms.append(Chem.Atom(parts[0]).GetAtomicNum())
            xyz.extend(float(value) for value in parts[1:])
        if not atoms:
            raise ValueError("No atomic coordinates found")
        self.properties["atom"] = np.asarray(atoms, dtype=np.int32)
        self.properties["coordinate"] = np.asarray(xyz, dtype=np.float32)

    def _parse_archive_properties(self):
        property_text = self.arc_dict["properties"].replace("\\\\", "\\")
        tags = {
            "HF": "energy", "ZeroPoint": "zpve", "Dipole": "dipole",
            "DipoleDeriv": "dipole_deriv", "Polar": "polar",
            "PolarDeriv": "polar_deriv", "ETot": "U", "HTot": "H", "GTot": "G",
        }
        raw: Dict[str, Any] = {}
        if "hessian" in self.arc_dict:
            raw["hessian"] = np.fromstring(self.arc_dict["hessian"].replace("\\", ","), sep=",", dtype=np.float32)
        for item in property_text.split("\\"):
            if "=" not in item:
                continue
            tag, value = item.split("=", 1)
            if tag in tags:
                raw[tags[tag]] = np.fromstring(value.replace("\\", ","), sep=",", dtype=np.float32)
        if "energy" in raw and "zpve" in raw:
            raw["U0"] = raw["energy"] + raw["zpve"]
        # Some Gaussian builds omit ETot/HTot/GTot from the archive section
        # (they still print the thermal corrections in the log body). Fall
        # back to the text lines so U/H/G are not silently lost for those logs.
        fallback_patterns = {
            "U": r"Sum of electronic and thermal Energies=\s*([-+]?\d+\.\d+)",
            "H": r"Sum of electronic and thermal Enthalpies=\s*([-+]?\d+\.\d+)",
            "G": r"Sum of electronic and thermal Free Energies=\s*([-+]?\d+\.\d+)",
        }
        for key, pattern in fallback_patterns.items():
            if key not in raw:
                match = re.search(pattern, self.text)
                if match:
                    raw[key] = np.asarray([float(match.group(1))], dtype=np.float32)
        self.properties.update(raw)

    def _parse_text_properties(self):
        patterns = {
            "dipole_total": r"Dipole moment.*?Tot=\s+([-+]?\d+\.\d+)",
            "homo_lumo": r"Alpha\s+occ\. eigenvalues --\s+.*?\s+([-+]?\d+\.\d+)\s*\n\s*Alpha virt\. eigenvalues --\s+([-+]?\d+\.\d+)",
            "octapole": r"Octapole moment.*?XXX=\s*([-+]?\d+\.\d+).*?YYY=\s*([-+]?\d+\.\d+).*?ZZZ=\s*([-+]?\d+\.\d+).*?XYY=\s*([-+]?\d+\.\d+).*?XXY=\s*([-+]?\d+\.\d+).*?XXZ=\s*([-+]?\d+\.\d+).*?XZZ=\s*([-+]?\d+\.\d+).*?YZZ=\s*([-+]?\d+\.\d+).*?YYZ=\s*([-+]?\d+\.\d+).*?XYZ=\s*([-+]?\d+\.\d+)",
            "quadrupole": r"Quadrupole moment.*?XX=\s*([-+]?\d+\.\d+).*?YY=\s*([-+]?\d+\.\d+).*?ZZ=\s*([-+]?\d+\.\d+).*?XY=\s*([-+]?\d+\.\d+).*?XZ=\s*([-+]?\d+\.\d+).*?YZ=\s*([-+]?\d+\.\d+).*?Traceless Quadrupole",
        }
        homo_lumo = re.findall(patterns["homo_lumo"], self.text, re.S)
        if homo_lumo:
            homo, lumo = map(float, homo_lumo[-1])
            self.properties.update({"homo": homo, "lumo": lumo, "gap": lumo - homo})
        dipole = re.findall(patterns["dipole_total"], self.text, re.S)
        if dipole:
            self.properties["dipole_total"] = float(dipole[-1])
        octapole = re.findall(patterns["octapole"], self.text, re.S)
        if octapole:
            self.properties["octapole"] = np.asarray(octapole[-1], dtype=np.float32)
        quadrupole = re.findall(patterns["quadrupole"], self.text, re.S)
        if quadrupole:
            self.properties["quadrupole"] = np.asarray(quadrupole[-1], dtype=np.float32)

    @staticmethod
    def _values(pattern: str, text: str) -> np.ndarray:
        return np.asarray([float(value) for match in re.findall(pattern, text) for value in match.split()], dtype=np.float64)

    def _parse_spectrum(self):
        frequencies = self._values(r"Frequencies --\s+(.*)", self.text)
        ir = self._values(r"IR Inten    --\s+(.*)", self.text)
        raman = self._values(r"Raman Activ --\s+(.*)", self.text)
        if not len(frequencies):
            return
        lengths = min(len(frequencies), len(ir), len(raman))
        if lengths == 0:
            raise ValueError("Frequency and spectrum intensity sections are incomplete")
        frequencies = frequencies[:lengths] * self.frequency_scaling_factor
        ir = ir[:lengths]
        raman = raman[:lengths]
        grid = np.linspace(
            SPECTRUM_PARAMETERS["frequency_min_cm-1"],
            SPECTRUM_PARAMETERS["frequency_max_cm-1"],
            int(SPECTRUM_PARAMETERS["frequency_grid_size"]),
        )
        broadened_ir = lorentzian_broadening(frequencies, ir, grid, self.ir_broadening_sigma)
        broadened_raman_activity = lorentzian_broadening(frequencies, raman, grid, self.raman_broadening_sigma)
        self.properties.update({
            "freq": frequencies,
            "ir": broadened_ir,
            "raman": raman_intensity(grid, broadened_raman_activity),
        })

    def _format_tensors(self):
        if "polar_deriv" in self.properties:
            atom_count = len(self.properties["polar_deriv"]) // 18
        elif "dipole_deriv" in self.properties:
            atom_count = len(self.properties["dipole_deriv"]) // 9
        elif "hessian" in self.properties:
            size = int(((-1 + np.sqrt(1 + 8 * len(self.properties["hessian"]))) / 2))
            atom_count = size // 3
        else:
            atom_count = len(self.properties.get("atom", []))
        if "hessian" in self.properties:
            size = 3 * atom_count
            matrix = np.zeros((size, size), dtype=np.float32)
            matrix[np.tril_indices(size)] = self.properties["hessian"][: size * (size + 1) // 2]
            self.properties["hessian"] = matrix + matrix.T - np.diag(matrix.diagonal())
        if "dipole_deriv" in self.properties:
            self.properties["dipole_deriv"] = self.properties["dipole_deriv"].reshape(atom_count, 3, 3) * 4.8032
        if "polar_deriv" in self.properties:
            raw = self.properties["polar_deriv"].reshape(atom_count, 3, 6)
            tensor = np.zeros((atom_count, 3, 3, 3), dtype=np.float32)
            for index, (left, right) in enumerate(((0, 0), (0, 1), (1, 1), (0, 2), (1, 2), (2, 2))):
                tensor[:, :, left, right] = tensor[:, :, right, left] = raw[:, :, index]
            self.properties["polar_deriv"] = tensor * 1.8897
        if "quadrupole" in self.properties:
            values = np.asarray(self.properties["quadrupole"]).reshape(-1)
            if len(values) >= 6:
                matrix = np.zeros((3, 3), dtype=np.float32)
                matrix[0, 0], matrix[1, 1], matrix[2, 2] = values[:3]
                matrix[0, 1] = matrix[1, 0] = values[3]
                matrix[0, 2] = matrix[2, 0] = values[4]
                matrix[1, 2] = matrix[2, 1] = values[5]
                self.properties["quadrupole"] = matrix
        if "polar" in self.properties:
            values = np.asarray(self.properties["polar"]).reshape(-1)
            if len(values) >= 6:
                matrix = np.zeros((3, 3), dtype=np.float32)
                matrix[0, 0], matrix[1, 1], matrix[2, 2] = values[0], values[2], values[5]
                matrix[0, 1] = matrix[1, 0] = values[1]
                matrix[0, 2] = matrix[2, 0] = values[3]
                matrix[1, 2] = matrix[2, 1] = values[4]
                self.properties["polar"] = matrix
        if "octapole" in self.properties:
            values = np.asarray(self.properties["octapole"]).reshape(-1)
            if len(values) >= 10:
                tensor = np.zeros((3, 3, 3), dtype=np.float32)
                index_groups = (
                    ((0, 0, 0),), ((1, 1, 1),), ((2, 2, 2),),
                    ((0, 1, 1), (1, 0, 1), (1, 1, 0)),
                    ((0, 0, 1), (0, 1, 0), (1, 0, 0)),
                    ((0, 0, 2), (0, 2, 0), (2, 0, 0)),
                    ((0, 2, 2), (2, 0, 2), (2, 2, 0)),
                    ((1, 2, 2), (2, 1, 2), (2, 2, 1)),
                    ((1, 1, 2), (1, 2, 1), (2, 1, 1)),
                    ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)),
                )
                for value, positions in zip(values[:10], index_groups):
                    for i, j, k in positions:
                        tensor[i, j, k] = value
                self.properties["octapole"] = tensor
        for key in ("energy", "zpve", "U0", "U", "H", "G", "dipole", "homo", "lumo", "gap", "dipole_total", "freq", "ir", "raman"):
            if key in self.properties:
                self.properties[key] = np.asarray(self.properties[key]).squeeze()


class GaussianNMRParser:
    """Parse Gaussian shielding output into an OpenSpec NMR record."""

    _number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"

    def __init__(
        self,
        file_path: str,
        unique_id: str,
        smiles_map: Optional[Mapping[str, str]] = None,
        *,
        broadening_sigma: float = SPECTRUM_PARAMETERS["nmr_broadening_sigma"],
    ):
        self.file_path = file_path
        self.unique_id = unique_id
        self.broadening_sigma = broadening_sigma
        self.properties: Dict[str, Any] = {
            "sample_id": unique_id,
            "filename": file_path,
        }
        if smiles_map is not None:
            self.properties["smiles"] = smiles_map.get(unique_id)
        self.error_type = None
        self.error_message = None
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                self.text = handle.read()
            self._parse()
        except Exception as exc:
            self.error_type = classify_exception(exc)
            self.error_message = str(exc)

    @staticmethod
    def _float(value: str) -> float:
        return float(value.replace("D", "E").replace("d", "e"))

    def _parse(self) -> None:
        shielding_pattern = re.compile(
            rf"^\s*\d+\s+([A-Za-z]+)\s+Isotropic\s*=\s*({self._number})"
            rf"\s+Anisotropy\s*=\s*({self._number})",
            re.MULTILINE,
        )
        shielding = shielding_pattern.findall(self.text)
        if not shielding:
            raise ValueError("No NMR shielding values found")

        atoms = np.asarray([Chem.Atom(element).GetAtomicNum() for element, _, _ in shielding], dtype=np.int32)
        isotropic = np.asarray([self._float(value) for _, value, _ in shielding], dtype=np.float64)
        anisotropy = np.asarray([self._float(value) for _, _, value in shielding], dtype=np.float64)

        tensor_pattern = re.compile(
            rf"XX\s*=\s*({self._number})\s+YX\s*=\s*({self._number})\s+ZX\s*=\s*({self._number})\s+"
            rf"XY\s*=\s*({self._number})\s+YY\s*=\s*({self._number})\s+ZY\s*=\s*({self._number})\s+"
            rf"XZ\s*=\s*({self._number})\s+YZ\s*=\s*({self._number})\s+ZZ\s*=\s*({self._number})",
            re.MULTILINE,
        )
        tensors = tensor_pattern.findall(self.text)
        if len(tensors) != len(shielding):
            raise ValueError(
                f"NMR shielding/tensor count mismatch: {len(shielding)} vs {len(tensors)}"
            )
        tensor = np.asarray(
            [[self._float(value) for value in row] for row in tensors],
            dtype=np.float64,
        ).reshape(len(tensors), 3, 3)
        grid = np.linspace(
            SPECTRUM_PARAMETERS["nmr_frequency_min"],
            SPECTRUM_PARAMETERS["nmr_frequency_max"],
            int(SPECTRUM_PARAMETERS["nmr_grid_size"]),
        )
        spectrum = lorentzian_broadening(
            isotropic,
            np.ones_like(isotropic),
            grid,
            sigma=self.broadening_sigma,
        )
        self.properties.update({
            "atom": atoms,
            "isotropic": isotropic,
            "anisotropy": anisotropy,
            "shielding_tensor": tensor,
            "nmr_shifts": isotropic,
            "nmr_grid": grid,
            "nmr_spectrum": spectrum,
        })
