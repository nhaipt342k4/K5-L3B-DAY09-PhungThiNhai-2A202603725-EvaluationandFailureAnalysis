"""M5: extra slice_check cases beyond the public vector.
Run: python -m pytest -q -m student -o addopts= -k advanced_slice"""
import copy

import pytest

pytestmark = pytest.mark.student


def _rows(fail=()):
    """6 items x 5 seeds; items 0-2 carry money_movement. `fail` = set of (item, seed) that fail."""
    return [{"item_id": f"E-{i:03d}", "seed": s, "slices": ["money_movement"] if i < 3 else [],
             "pass_rate": (i, s) not in fail} for i in range(6) for s in (1, 2, 3, 4, 5)]


def _rep(rows):
    return {"manifest": {"eval_set_sha": "x", "items": 6, "seeds": [1, 2, 3, 4, 5]}, "rows": rows,
            "metrics": {}, "evaluator_failures": []}


SPEC = {"metrics": [], "bootstrap": {"n_resamples": 1000, "rng": 2027, "confidence": 0.95},
        "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.5,
                    "no_significant_drop": True, "blocking": True}]}


def test_lab9_advanced_slice_identical_report_merges():
    from lab9 import gate

    base = _rep(_rows())
    assert gate.slice_check(base, base, SPEC)[0] == []


def test_lab9_advanced_slice_ci_drop_blocks_above_floor():
    # Every money item fails 2/5 seeds: slice mean 0.6 is above min 0.5, but the paired CI is < 0.
    from lab9 import gate

    pr = _rep(_rows({(i, s) for i in range(3) for s in (1, 2)}))
    blocked, lines = gate.slice_check(pr, _rep(_rows()), SPEC)
    assert blocked == ["slice:money_movement/pass_rate"]
    assert "CI" in lines[0]


def test_lab9_advanced_slice_empty_slice_blocks():
    # Relabelling every item out of the slice must not turn the slice into a vacuous pass.
    from lab9 import gate

    pr = _rep(_rows())
    for r in pr["rows"]:
        r["slices"] = []
    assert gate.slice_check(pr, _rep(_rows()), SPEC)[0] == ["slice:money_movement/pass_rate"]


def test_lab9_advanced_slice_non_blocking_only_warns():
    from lab9 import gate

    spec = copy.deepcopy(SPEC)
    spec["slices"][0]["blocking"] = False
    pr = _rep(_rows({(i, s) for i in range(3) for s in (1, 2, 3, 4, 5)}))
    blocked, lines = gate.slice_check(pr, _rep(_rows()), spec)
    assert blocked == [] and lines[0].rstrip().endswith("warn")
