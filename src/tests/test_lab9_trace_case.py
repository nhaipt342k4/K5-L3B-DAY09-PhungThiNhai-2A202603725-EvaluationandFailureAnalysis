"""Regression test for docs/trace_case.md: seeded_regression C-002@11 (FM-03 ticket_trust).

First wrong step = event 3 `model_override` {"delay_days": 5}: the ticket's "trễ 5 ngày" overrides the
DB's delay_days=2, so a claim that must be denied gets a 20.000đ refund. The `fixed` shape on the same
claim@seed must not override and must leave the ledger empty.
Run: python -m pytest -q -m student -o addopts= -k trace_case
"""
import pytest

pytestmark = pytest.mark.student
CLAIM, SEED = "C-002", 11


def _case(shape):
    # Imported here: the overlaid Lab 8 CI collects tests without pydantic-evals installed.
    from lab9.trace_case import investigate

    return investigate(shape, CLAIM, SEED)


def _db_fact_kept(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import DbFactKept

    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return DbFactKept().evaluate(ctx).value


def test_lab9_trace_case_first_wrong_step_is_model_override():
    case = _case("seeded_regression")
    trial, label = case["trial"], case["label"]
    kinds = [e["kind"] for e in trial["events"]]
    # Events 1-2 (handoff, investigator) are correct: the DB says delay_days=2.
    assert kinds[:3] == ["handoff", "investigator", "model_override"]
    assert trial["events"][1]["payload"]["lookup_order"]["order"]["delay_days"] == 2
    assert trial["events"][2]["payload"] == {"delay_days": 5}
    # The step grader catches it, and so does the ledger: money moved on a claim that must be denied.
    assert _db_fact_kept(trial, label) is False
    assert trial["snapshot"]["refund_vnd"] == 20000 != label["refund_vnd"] == 0
    assert trial["lab8_pass"] is False


def test_lab9_trace_case_fixed_keeps_db_fact():
    case = _case("fixed")
    trial, label = case["trial"], case["label"]
    assert "model_override" not in [e["kind"] for e in trial["events"]]
    assert _db_fact_kept(trial, label) is True
    assert trial["snapshot"]["refund_vnd"] == label["refund_vnd"] == 0
    assert trial["result"]["status"] == label["status"] == "denied"
    assert trial["lab8_pass"] is True
