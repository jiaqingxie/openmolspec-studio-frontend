import pytest

from openmolspec_bench.nmrgym_source_labels import (
    assigned_proposal,
    literature_proposal,
    parse_report,
)


def test_explicit_nucleus_range_and_hz_are_separate():
    text = (
        "¹H NMR (400 MHz, DMSO-d6) δ 7.73–7.62 (m, 2H), "
        "2.92 (dd, J = 53.6, 11.2 Hz, 2H), 1.62 (dd, J = 31.7 Hz, 11.8 Hz, 2H); "
        "¹³C{¹H} NMR (101 MHz) δ 154.84, 153.64; ³¹P NMR δ 53.6"
    )
    peaks = parse_report(text, "1H")
    assert [p.center for p in peaks] == pytest.approx([7.675, 2.92, 1.62])
    assert peaks[1].coupling_hz == (53.6, 11.2)
    assert peaks[2].coupling_hz == (31.7, 11.8)
    assert [p.center for p in parse_report(text, "13C")] == [154.84, 153.64]
    original = [7.73, 7.62, 2.92, 53.6, 11.2, 1.62, 31.7, 11.8]
    reason, corrected = literature_proposal(original, [154.84, 153.64], text, text)
    assert reason == "coupling_in_shift_list"
    assert corrected == pytest.approx([7.675, 2.92, 1.62])
    assert literature_proposal(original, [154.84, 100.0], text, text) is None


def test_an_untyped_or_ambiguous_source_cannot_supply_training_labels():
    for text in [
        "13C NMR δ 35, 143",
        "1H and 13C NMR δ 3, 143",
        "1H NMR δ 7.4, 2 Hz",
        "1H NMR δ 7.4 (d, 2H",
        "1H NMR signals appeared near 7.4",
    ]:
        assert parse_report(text, "1H") is None
    assert parse_report("1H NMR δ 2.9 (d, J=53.6 ppm, 1H)", "1H")[0].coupling_hz == ()
    assert [s.center for s in parse_report("¹H NMR δ −2.5, −2.5, 86.0", "1H")] == [
        -2.5,
        -2.5,
        86.0,
    ]
    reason, h = literature_proposal(
        [32.0, 140.0], [32.0, 140.0], "1H NMR δ 3.4, 3.4", "13C NMR δ 32.0, 140.0"
    )
    assert (reason, h) == ("copied_carbon_list", [3.4, 3.4])


def test_assigned_replacement_restores_repeated_peaks_and_requires_evidence():
    p = {
        "Spectrum 1H 1": "5.98;0;3|7.43;0;8|7.43;0;10|8.13;0;6|",
        "Spectrum 13C 0": "127.94;0;1|169.89;0;2|183.07;0;3|",
    }
    h, c = [183.07, 5.98, 8.13, 7.43], [127.94, 169.89]
    assert assigned_proposal(h, c, p) == (
        "assigned_carbon_in_proton_list",
        [5.98, 7.43, 7.43, 8.13],
    )
    assert assigned_proposal(h, [0.01], p) is None
    assert assigned_proposal(h, c, {**p, "Program": "0:ACD/Labs"}) is None
    assert assigned_proposal(
        h, c, {**p, "Spectrum 1H 2": "5.98;0;3|8.13;0;6|7.43;0;8|3.4;0;7|"}
    ) == ("conflicting_source_spectra", None)
    assert assigned_proposal([183.07], c, {"Spectrum 13C 0": p["Spectrum 13C 0"]}) == (
        "carbon_only_record",
        [],
    )
