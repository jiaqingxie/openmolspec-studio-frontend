"""Regression tests for paired peak R² and the versioned single-environment holdout."""

import json
from importlib.resources import files

import pytest

from openmolspec_bench.metrics import peak_metrics
from openmolspec_bench.solution_cohort import solution_test_cohort


def test_peak_r2_weights_each_molecule_equally_and_omits_extra_peaks():
    # The first spectrum has one pair, the second has two.
    result = peak_metrics([[2, 75], [5, 11]], [[0], [4, 10]])
    center = 3.5
    sse = 4 + 0.5 + 0.5
    sst = center**2 + 0.5 * (4 - center) ** 2 + 0.5 * (10 - center) ** 2
    assert result["matched_peak_r2"] == pytest.approx(1 - sse / sst)
    assert result["matched_peaks"] == result["reference_peaks"] == 3
    assert result["predicted_peaks"] == 4
    assert result["matched_fraction"] == 0.75


def test_constant_or_single_matched_reference_has_no_r2():
    assert peak_metrics([[5], [4]], [[3], [3]])["matched_peak_r2"] is None
    assert peak_metrics([[5]], [[3]])["matched_peak_r2"] is None


@pytest.mark.parametrize("nucleus,expected", [("31P", 67), ("19F", 159)])
def test_fixed_exclusions_are_bound_to_record_identity_and_reference(nucleus, expected):
    config = json.loads(
        files("openmolspec")
        .joinpath("assets/solution-test-exclusions.json")
        .read_text()
    )
    entry = config["nuclei"][nucleus]
    rows = [dict(record_id=str(i)) for i in range(entry["total_records"])]
    rows.reverse()
    kept, cohort = solution_test_cohort(rows, nucleus, entry["reference_sha256"])
    assert cohort == config["name"] and len(rows) - len(kept) == expected
    assert {int(r["record_id"]) for r in rows} - {
        int(r["record_id"]) for r in kept
    } == set(entry["excluded_record_ids"])
    assert solution_test_cohort(rows, nucleus, "unrelated-reference") == (
        rows,
        "full-test",
    )
    assert solution_test_cohort(
        rows, nucleus, entry["reference_sha256"], full_test=True
    ) == (rows, "full-test")
