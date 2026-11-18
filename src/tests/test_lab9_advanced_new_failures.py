"""M6: a regression that only MOVES failures to other seeds keeps every mean identical.
Run: python -m pytest -q -m student -o addopts= -k advanced_new_failures"""
import pytest

pytestmark = pytest.mark.student
SEEDS = (11, 22, 33, 44, 55)


def _rep(bad_seed):
    rows = [{"item_id": f"E-{i:03d}", "seed": s, "slices": [],
             "pass_rate": not (i == 0 and s == bad_seed)} for i in range(4) for s in SEEDS]
    mean = sum(r["pass_rate"] for r in rows) / len(rows)
    return {"manifest": {"eval_set_sha": "x", "items": 4, "seeds": list(SEEDS)}, "rows": rows,
            "metrics": {"pass_rate": mean}, "evaluator_failures": []}


def _spec(**th):
    return {"metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                         "threshold": {"min": 0.9, "no_significant_drop": True, **th}}]}


def test_lab9_advanced_new_failures_lists_moved_trial():
    from lab9 import gate

    assert gate.new_failures(_rep(33), _rep(55), "pass_rate") == [("E-000", 33)]
    assert gate.new_failures(_rep(55), _rep(55), "pass_rate") == []


def test_lab9_advanced_moved_failure_needs_the_rule():
    from lab9 import gate

    pr, base = _rep(33), _rep(55)       # same mean, same pass^5, paired CI exactly 0
    assert gate.check(pr, base, _spec())[0] == []
    assert gate.check(pr, base, _spec(no_new_failures=True))[0] == ["pass_rate"]
    assert gate.check(base, base, _spec(no_new_failures=True))[0] == []
