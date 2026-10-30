from __future__ import annotations

import io
import re
from dataclasses import dataclass

import numpy as np


SPECTRUM_AXIS = np.linspace(400.0, 4000.0, 1024, dtype=np.float32)


@dataclass(frozen=True)
class Spectrum:
    wavenumber: np.ndarray
    intensity: np.ndarray
    name: str


@dataclass(frozen=True)
class SpectralInput:
    ir: np.ndarray | None = None
    raman: np.ndarray | None = None
    nmr_h: np.ndarray | None = None
    nmr_c: np.ndarray | None = None

    def require_vibrational_spectrum(self) -> None:
        if self.ir is None and self.raman is None:
            raise ValueError("请至少提供 IR 或 Raman 谱图。")


def minmax(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if values.shape != (1024,) or not np.isfinite(values).all():
        raise ValueError("模型输入必须是 1024 个有限数值。")
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return np.zeros_like(values)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def _numeric_rows(text: str) -> list[list[float]]:
    rows: list[list[float]] = []
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith(("#", "//")):
            continue
        parts = [item for item in re.split(r"[\s,;\t]+", line) if item]
        try:
            numeric = [float(item) for item in parts]
        except ValueError:
            continue
        if numeric:
            rows.append(numeric)
    return rows


def parse_spectrum(content: bytes | str, name: str = "spectrum") -> Spectrum:
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("gb18030")
    else:
        text = content
    rows = _numeric_rows(text)
    if len(rows) < 2:
        raise ValueError("没有读到足够的数值行；请上传一列强度或两列波数/强度数据。")
    widths = {len(row) for row in rows}
    if widths == {1}:
        intensity = np.asarray([row[0] for row in rows], dtype=np.float64)
        axis = np.linspace(400.0, 4000.0, len(intensity))
    else:
        pairs = [row[:2] for row in rows if len(row) >= 2]
        if len(pairs) < 2:
            raise ValueError("两列谱图至少需要两个有效数据点。")
        values = np.asarray(pairs, dtype=np.float64)
        axis, intensity = values[:, 0], values[:, 1]
    valid = np.isfinite(axis) & np.isfinite(intensity)
    axis, intensity = axis[valid], intensity[valid]
    order = np.argsort(axis)
    axis, intensity = axis[order], intensity[order]
    axis, unique_index = np.unique(axis, return_index=True)
    intensity = intensity[unique_index]
    in_range = (axis >= 400.0) & (axis <= 4000.0)
    if in_range.sum() < 2:
        raise ValueError("谱图需要在 400–4000 cm⁻¹ 范围内至少包含两个数据点。")
    resampled = np.interp(SPECTRUM_AXIS, axis, intensity).astype(np.float32)
    return Spectrum(SPECTRUM_AXIS.copy(), minmax(resampled), name)


def parse_peaks(text: str) -> np.ndarray | None:
    if not text.strip():
        return None
    tokens = [token for token in re.split(r"[\s,;]+", text.strip()) if token]
    try:
        values = np.asarray([float(token) for token in tokens], dtype=np.float32)
    except ValueError as error:
        raise ValueError("NMR 峰位只能包含数字，并以逗号、空格或换行分隔。") from error
    if not np.isfinite(values).all():
        raise ValueError("NMR 峰位包含非有限数值。")
    return np.sort(values)


def spectrum_template() -> bytes:
    output = io.StringIO()
    output.write("wavenumber_cm-1,intensity\n")
    for wave in np.linspace(400, 4000, 10):
        output.write(f"{wave:.2f},0.0\n")
    return output.getvalue().encode("utf-8")

