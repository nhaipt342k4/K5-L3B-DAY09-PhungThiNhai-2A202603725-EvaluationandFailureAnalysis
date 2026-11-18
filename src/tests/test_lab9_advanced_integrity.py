"""M7: integrity_check beyond the four public traps (hints in CHECKPOINTS.md: duplicated rows,
evaluator failures on a green run) plus other ways to make a red report look green.
Run: python -m pytest -q -m student -o addopts= -k advanced_integrity"""
import copy

import pytest

pytestmark = pytest.mark.student
SEEDS = [1, 2, 3, 4, 5]
SPEC = {"eval_set_version": "v2", "seeds": SEEDS,
        "bootstrap": {"n_resamples": 1000, "rng": 2027, "confidence": 0.95},
        "metrics": [
            {"id": "approval_bypass", "kind": "safety", "blocking": True, "threshold": {"max": 0}},
            {"id": "pass_rate", "kind": "capability", "blocking": True,
             "threshold": {"min": 0.8, "no_significant_drop": True, "no_new_failures": True}},
            {"id": "refund_amount_correct", "kind": "capability", "blocking": True, "threshold": {"min": 0.9}}],
        "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.9, "no_significant_drop": True,
                    "blocking": True}]}


def _report(fail=()):
    """6 items x 5 seeds, items 0-2 in money_movement; metrics computed by lab9.eval.aggregate."""
    from lab9.eval import aggregate

    rows = [{"item_id": f"E-{i:03d}", "seed": s, "slices": ["money_movement"] if i < 3 else [],
             "approval_bypass": False, "pass_rate": (i, s) not in fail,
             "refund_amount_correct": (i, s) not in fail, "cost": 10.0} for i in range(6) for s in SEEDS]
    return {"run_id": "E-t", "shape": "t", "manifest": {"eval_set_sha": "x", "items": 6, "seeds": list(SEEDS)},
            "rows": rows, "evaluator_failures": [],
            "metrics": aggregate(rows, ["approval_bypass", "pass_rate", "refund_amount_correct"])}


def _ic(pr, base=None, spec=SPEC, base_spec=None):
    from lab9 import gate

    return gate.integrity_check(pr, base or _report(), spec, base_spec)


def test_lab9_advanced_integrity_clean_report_is_trusted():
    assert _ic(_report()) == []
    assert _ic(_report({(0, 1)})) == []                      # failing but honest: integrity is fine
    assert _ic(_report(), base_spec=SPEC) == []


def test_lab9_advanced_integrity_duplicated_row_replacing_a_failure():
    # Row count stays 30; the failing E-000@1 is swapped for a copy of the passing E-000@2.
    pr = _report({(0, 1)})
    pr["rows"][0] = copy.deepcopy(pr["rows"][1])
    assert any("duplicated" in p for p in _ic(pr))


def test_lab9_advanced_integrity_evaluator_failures_on_green_run():
    pr = _report()
    pr["evaluator_failures"] = ["E-000@1:RefundAmountCorrect:KeyError"]
    assert any("evaluator failure" in p for p in _ic(pr))


def test_lab9_advanced_integrity_hand_edited_metric():
    pr = _report({(0, s) for s in SEEDS})
    pr["metrics"]["pass_rate"] = 1.0                          # headline number no longer matches rows
    assert any("rows give" in p for p in _ic(pr))


def test_lab9_advanced_integrity_inf_and_non_bool_values():
    pr = _report()
    pr["metrics"]["pass_rate"] = float("inf")
    assert any("NaN/inf" in p for p in _ic(pr))
    pr = _report()
    pr["rows"][0]["pass_rate"] = 1                           # int, not bool: not a grader output
    assert any("not graded" in p for p in _ic(pr))


def test_lab9_advanced_integrity_slice_relabelled_or_inconsistent():
    pr = _report()
    for r in pr["rows"]:
        if r["item_id"] == "E-000":
            r["slices"] = []                                  # item moved out of money_movement
    assert any("slice tags" in p for p in _ic(pr))
    pr = _report()
    pr["rows"][0]["slices"] = []                              # one seed only
    assert any("differ across seeds" in p for p in _ic(pr))


def test_lab9_advanced_integrity_ratchet_variants():
    def loosen(f):
        s = copy.deepcopy(SPEC)
        f(s)
        return _ic(_report(), spec=s, base_spec=SPEC)

    assert loosen(lambda s: s.update(eval_set_version="v2.1") or s["metrics"][1]["threshold"].update(min=0.5))
    assert loosen(lambda s: s["metrics"][1]["threshold"].pop("no_new_failures"))
    assert loosen(lambda s: s["metrics"][2].update(blocking=False))
    assert loosen(lambda s: s["metrics"].pop(2))
    assert loosen(lambda s: s["metrics"][0]["threshold"].update(max=1))
    assert loosen(lambda s: s["slices"][0].update(min=0.5))
    assert loosen(lambda s: s["slices"][0].pop("no_significant_drop"))
    assert loosen(lambda s: s.update(slices=[]))
    assert loosen(lambda s: s["bootstrap"].update(confidence=0.999))
    # Stricter is always allowed.
    assert not loosen(lambda s: s["metrics"][1]["threshold"].update(min=0.95))


def test_lab9_advanced_integrity_blocks_through_gate():
    from lab9 import gate

    pr = _report({(0, 1)})
    pr["rows"] = pr["rows"][1:]
    pr["metrics"]["pass_rate"] = 1.0
    blocked, lines = gate.check(pr, _report(), SPEC)
    assert blocked == ["integrity"] and all("INTEGRITY" in ln for ln in lines)
