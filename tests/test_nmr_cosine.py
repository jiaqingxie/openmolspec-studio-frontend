"""Check the analytic peak-profile cosine against directly sampled spectra."""

import numpy as np
import pytest

from openmolspec_bench.nmr_cosine import peak_profile_cosine


def test_matches_direct_spectrum_cosine():
    grid = np.linspace(-100, 100, 100001)
    width = 0.4
    p, y = [0.4, 1.25, 1.8], [0.3, 1.4]

    def spectrum(peaks):
        return sum(1 / (1 + (2 * (grid - peak) / width) ** 2) for peak in peaks)

    a, b = spectrum(p), spectrum(y)
    direct = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    assert peak_profile_cosine(p, y, width) == pytest.approx(direct, abs=1e-8)


def test_single_peak_and_width_sensitivity():
    assert peak_profile_cosine([20], [21], 1) == pytest.approx(0.5)
    assert peak_profile_cosine([20], [21], 2) == pytest.approx(0.8)


def test_joint_hsqc_coordinates_and_extra_peaks():
    widths = [1, 0.05]
    ref = [[10, 1], [50, 4]]
    assert peak_profile_cosine(ref[::-1], ref, widths) == pytest.approx(1)
    assert peak_profile_cosine([[10, 4], [50, 1]], ref, widths) < 0.01
    assert peak_profile_cosine([[11, 1.05]], [[10, 1]], widths) == pytest.approx(0.25)
    assert 0 < peak_profile_cosine(ref + [[80, 6]], ref, widths) < 1


@pytest.mark.parametrize(
    "peaks,width", [([], 1), ([np.nan], 1), ([1], 0), ([[1, 2]], 1)]
)
def test_undefined_cosine_is_reported(peaks, width):
    with pytest.raises(ValueError):
        peak_profile_cosine(peaks, [1], width)
