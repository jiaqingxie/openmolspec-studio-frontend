from scripts.evaluate_agent import grade


def test_formula_grade_accepts_scientific_subscripts():
    case = {"tool": "inspect_molecule", "formula": "C2H6O"}
    calls = [{"name": "inspect_molecule", "result": {"formula": "C2H6O", "molecule_id": "ethanol"}}]
    assert grade(case, calls, "乙醇的分子式为 C₂H₆O。", None)


def test_spectrum_reuse_requires_success_on_the_referenced_spectrum():
    case = {"tool": "retrieve_candidates", "job": True}
    failed = {
        "name": case["tool"], "args": {"ir_id": "predicted-ir"},
        "result": {"status": "failed", "input_refs": {"ir_id": "predicted-ir"}},
    }
    unrelated = {
        "name": case["tool"], "args": {"ir_id": "different-ir"},
        "result": {"status": "succeeded", "input_refs": {"ir_id": "different-ir"}},
    }
    assert not grade(case, [failed, unrelated], "", "predicted-ir")
    assert not grade(case, [{**unrelated, "args": failed["args"]}], "", "predicted-ir")
    succeeded = {**failed, "result": {**failed["result"], "status": "succeeded"}}
    assert grade(case, [succeeded], "", "predicted-ir")
