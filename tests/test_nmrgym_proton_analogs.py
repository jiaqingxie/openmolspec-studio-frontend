import numpy as np
from openmolspec.nmrgym_analogs import ProtonSpectrumLibrary


def test_fixed_peak_count_when_transferring_nearby_training_peaks(tmp_path):
    bit_vector = np.zeros(512, dtype=np.uint8)
    bit_vector[[2, 17, 300]] = 1
    words = np.tile(np.packbits(bit_vector).view(np.uint64), (9, 1))
    library_path = tmp_path / "library.npz"
    np.savez(
        library_path, words=words, ends=np.arange(0, 19, 2), ppm=np.tile([1.06, 3.1], 9)
    )
    library = ProtonSpectrumLibrary(library_path)
    selected, _ = library.nearest(bit_vector)
    np.testing.assert_array_equal(selected, np.arange(8))
    predicted = np.array([1.0, 3.2])
    profile = dict(method="assignment", width_ppm=0.35, mix=1.0)
    refined = library.adjust(predicted, bit_vector, profile)
    assert len(refined) == 2 and 1.0 < refined[0] < 1.06 and 3.1 < refined[1] < 3.2
    np.testing.assert_array_equal(
        library.adjust(predicted, 1 - bit_vector, profile), predicted
    )
