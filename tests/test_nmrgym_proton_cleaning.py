from pathlib import Path
import importlib.util

module_spec = importlib.util.spec_from_file_location(
    "clean_nmrgym_proton",
    Path(__file__).resolve().parents[1] / "scripts/clean_nmrgym_proton.py",
)
qc = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(qc)


def test_repeats_are_valid_and_threshold_is_strict():
    h = [3.8, 3.8, 3.8, 5.1]
    assert qc.reasons("CCO", h, [19.0, 43.0]) == []
    assert h == [3.8, 3.8, 3.8, 5.1]
    assert qc.reasons("CCO", [50.0], []) == []
    assert qc.reasons("CCO", [20000.0], []) == ["extreme_organic"]


def test_charge_radical_and_metals_stay_in_review_without_second_evidence():
    for smiles in ("[NH4+]", "[CH3]", "[Fe+2]", "[Na+].[Cl-]"):
        assert qc.reasons(smiles, [112.0], []) == []
    assert qc.reasons("[Fe+2]", [112.0, 2.0, 2.0], [2.0, 112.0, 2.0]) == [
        "cross_nucleus_copy"
    ]
    assert qc.reasons("[Fe+2]", [112.0, 2.0, 2.0], [2.0, 112.0]) == []
