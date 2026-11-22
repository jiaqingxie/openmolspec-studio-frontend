import numpy as np
from openmolspec.nmrgym_proton import GRID, adapter_outputs, decode, resample


def test_zero_residual_preserves_site_curve_and_decodes_learned_count():
    base = resample([1.0, 5.0], len(GRID))
    features = np.tile(base, 3)[None, :]
    weights = {
        "w1": np.zeros((2, features.shape[1])),
        "b1": np.zeros(2),
        "w2": np.zeros((2, 2)),
        "b2": np.zeros(2),
        "out": np.zeros((len(GRID) + 1, 2)),
        "bias": np.r_[np.zeros(len(GRID)), np.log(2)],
    }
    curves, counts = adapter_outputs(features, [2], weights)
    assert counts.tolist() == [4]
    np.testing.assert_allclose(curves[0], base)
    np.testing.assert_allclose(decode(curves[0], 4, [], 0), [1, 7 / 3, 11 / 3, 5])


def test_one_peak_and_snap_keep_repeated_peaks():
    assert decode([2.0, 3.0, 4.0], 1, [], 0).tolist() == [3.0]
    assert decode([2.01, 2.05, 5.0], 3, [2.0, 6.0], 0, 0.1).tolist() == [2.0, 2.0, 5.0]
