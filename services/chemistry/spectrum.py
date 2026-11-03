"""Shared upload and prediction spectrum records for preview and model input."""

from __future__ import annotations

import math
import re

import numpy as np

from openmolspec_ui.spectra import SPECTRUM_AXIS, minmax

from .schemas import ParseSpectrumRequest
from .store import json_value


INTENSITY_UNITS = {"a.u.", "au", "relative", "normalized", "normalized [0,1]", "arbitrary units"}
WAVENUMBER_HEADERS = {"wavenumber", "wavenumber_cm-1", "wavenumber_cm^-1", "shift", "raman_shift"}
WAVELENGTH_HEADERS = {"wavelength", "wavelength_nm"}
INTENSITY_HEADERS = {"y", "intensity", "intensity_au", "absorbance", "transmittance", "signal"}


def normalize_model_input(values) -> np.ndarray:
    with np.errstate(over="ignore", invalid="ignore"):
        normalized = minmax(np.asarray(values, dtype=np.float32))
    if not np.isfinite(normalized).all():
        raise ValueError("Spectrum exceeds the model normalizer's numerical range.")
    if not np.any(normalized):
        raise ValueError("A flat spectrum cannot be used as a model input.")
    return normalized


def parse_upload(request: ParseSpectrumRequest) -> dict:
    rows: list[list[float]] = []
    header_seen = False
    for line_number, line in enumerate(request.content.splitlines(), start=1):
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith(("#", "//")):
            continue
        # A delimited empty field is malformed, not an omitted column.
        if re.search(r"[,;\t]", line):
            tokens = [part.strip() for part in re.split(r"[,;\t]", line)]
        else:
            tokens = line.split()
        try:
            values = [float(token) for token in tokens]
        except ValueError as error:
            fields = [token.lower().replace(" ", "_") for token in tokens]
            valid_header = (len(fields) == 1 and fields[0] in INTENSITY_HEADERS) or (
                len(fields) == 2 and fields[0] in WAVENUMBER_HEADERS | WAVELENGTH_HEADERS | {"x"}
                and fields[1] in INTENSITY_HEADERS
            )
            if not rows and not header_seen and valid_header:
                if len(fields) == 2 and (
                    (fields[0] in WAVELENGTH_HEADERS and request.axis_unit == "cm^-1")
                    or (fields[0] in WAVENUMBER_HEADERS and request.axis_unit == "nm")
                ):
                    raise ValueError("The spectrum header conflicts with the declared axis unit.") from error
                header_seen = True
                continue
            raise ValueError(f"Invalid numeric spectrum row at line {line_number}.") from error
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Nonfinite spectrum value at line {line_number}.")
        if len(values) not in (1, 2) or (rows and len(rows[0]) != len(values)):
            raise ValueError("Provide one intensity column or consistent axis and intensity columns.")
        rows.append(values)
    if len(rows) < 2:
        raise ValueError("A spectrum must contain at least two numeric points.")
    values = np.asarray(rows, dtype=np.float64)
    return spectrum_record(
        name=request.name,
        modality=request.modality,
        axis=values[:, 0] if values.shape[1] == 2 else None,
        intensity=values[:, -1],
        axis_unit=request.axis_unit,
        intensity_unit=request.intensity_unit,
        domain=request.domain,
        axis_mode=request.axis_mode,
        provenance={"source": "upload", "metadata_basis": "user_declared"},
    )


def spectrum_record(*, name, modality, axis, intensity, axis_unit, intensity_unit, domain,
                    axis_mode, provenance) -> dict:
    intensity = np.asarray(intensity, dtype=np.float64)
    axis = None if axis is None else np.asarray(axis, dtype=np.float64)
    if intensity.ndim != 1 or len(intensity) < 2 or not np.isfinite(intensity).all():
        raise ValueError("Spectrum intensity must contain at least two finite values.")
    if axis is not None and (axis.shape != intensity.shape or not np.isfinite(axis).all()):
        raise ValueError("Spectrum axis and intensity must contain matching finite values.")
    if axis is not None and len(np.unique(axis)) != len(axis):
        raise ValueError("Spectrum axis contains duplicate positions.")
    if axis is not None and axis_unit in {"cm^-1", "nm"} and np.any(axis <= 0):
        raise ValueError("Wavenumbers and wavelengths must be positive.")
    if axis_mode == "model_grid" and axis is not None:
        raise ValueError("Model-grid mode accepts one intensity column. Use explicit mode for axis/intensity pairs.")

    raw = {"wavenumber": axis, "intensity": intensity, "axis_unit": axis_unit,
           "intensity_unit": intensity_unit}
    steps: list[str] = []
    reasons: list[str] = []
    preview_unit = axis_unit
    if axis is None:
        if axis_mode == "model_grid" and len(intensity) == len(SPECTRUM_AXIS) and axis_unit == "cm^-1":
            axis = SPECTRUM_AXIS
            steps.append("assigned_declared_model_grid")
        else:
            axis = np.arange(1, len(intensity) + 1)
            preview_unit = "index"
            reasons.append("Provide an explicit axis or declare a 1024-point cm^-1 model grid.")
    elif np.any(np.diff(axis) < 0):
        order = np.argsort(axis)
        axis, intensity = axis[order], intensity[order]
        steps.append("sorted_axis")

    if domain != "theoretical":
        reasons.append("Model inputs must be declared theoretical.")
    if axis_unit != "cm^-1":
        reasons.append("The model expects wavenumbers in cm^-1.")
    declared_intensity_unit = intensity_unit.strip().lower()
    if declared_intensity_unit not in INTENSITY_UNITS:
        reasons.append("Declare relative, normalized or arbitrary intensity units.")
    if declared_intensity_unit.startswith("normalized") and (np.min(intensity) < 0 or np.max(intensity) > 1):
        reasons.append("Normalized intensity must remain in the declared [0,1] range.")
    if preview_unit == "cm^-1" and (axis[0] > SPECTRUM_AXIS[0] or axis[-1] < SPECTRUM_AXIS[-1]):
        reasons.append("The measured axis does not cover the full 400–4000 cm^-1 model grid.")
    if np.min(intensity) == np.max(intensity):
        reasons.append("A flat spectrum cannot be used as a model input.")

    preview_intensity_unit = intensity_unit
    if not reasons:
        try:
            # Full coverage is required above. Explicit NaN boundary values make
            # accidental extrapolation fail closed if the grid policy changes.
            aligned = np.interp(SPECTRUM_AXIS, axis, intensity, left=np.nan, right=np.nan)
            normalized = normalize_model_input(aligned)
        except ValueError as error:
            reasons.append(str(error))
        else:
            if not np.array_equal(axis, SPECTRUM_AXIS):
                steps.append("interpolated_within_coverage")
            axis, intensity = SPECTRUM_AXIS, normalized
            preview_intensity_unit = "normalized [0,1]"
            steps.append("minmax_normalized")
    return json_value({
        "name": name, "modality": modality, "domain": domain,
        "axis_mode": axis_mode, "axis_unit": preview_unit, "intensity_unit": preview_intensity_unit,
        "wavenumber": axis, "intensity": intensity, "raw": raw,
        "quality": {"model_eligible": not reasons, "reasons": reasons},
        "processing": {"steps": steps, "extrapolated": False},
        "provenance": provenance,
    })


def legacy_spectrum(spectrum: dict) -> dict:
    if "quality" in spectrum:
        return spectrum
    return {
        **spectrum, "domain": "unknown", "axis_mode": "explicit", "axis_unit": "unknown",
        "intensity_unit": "unknown", "raw": None, "processing": {"steps": []},
        "quality": {"model_eligible": False, "reasons": ["Legacy spectrum lacks raw data and declared units. Reupload to calculate."]},
        "provenance": {"source": "legacy"},
    }


def compact_spectrum(spectrum: dict) -> dict:
    axis = spectrum["wavenumber"]
    raw = spectrum.get("raw")
    raw_axis = raw["wavenumber"] if raw else None
    if raw_axis is None:
        peak_axis, peak_intensity = axis, spectrum["intensity"]
        basis = "preview_samples"
    else:
        peak_axis, peak_intensity = zip(*sorted(zip(raw_axis, raw["intensity"])))
        basis = "original_samples"
    peaks = sorted(
        (i for i in range(1, len(peak_axis) - 1)
         if peak_intensity[i - 1] < peak_intensity[i] > peak_intensity[i + 1]),
        key=peak_intensity.__getitem__, reverse=True,
    )[:8]
    return {
        "spectrum_id": spectrum["id"], "name": spectrum["name"], "modality": spectrum["modality"],
        "domain": spectrum["domain"], "axis_unit": spectrum["axis_unit"],
        "intensity_unit": spectrum["intensity_unit"], "points": len(axis),
        "axis_range": [min(axis), max(axis)] if axis else None,
        "raw_points": len(raw["intensity"]) if raw else None,
        "raw_axis_range": [min(raw_axis), max(raw_axis)] if raw_axis else None,
        "peak_summary": {
            "basis": basis, "method": "strict local maxima ranked by sampled intensity",
            "axis_unit": raw["axis_unit"] if raw_axis is not None else spectrum["axis_unit"],
            "intensity_unit": raw["intensity_unit"] if raw_axis is not None else spectrum["intensity_unit"],
            "peaks": [{"position": peak_axis[i], "intensity": peak_intensity[i]} for i in peaks],
        },
        "quality": spectrum["quality"], "processing": spectrum["processing"],
        "provenance": spectrum["provenance"],
    }
