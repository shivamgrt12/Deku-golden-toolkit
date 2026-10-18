import copy

import verdict as V

PERFECT = {
    "final": {
        "combined_score": 1.0, "reward": 1.0, "invalid": [], "degraded": [], "pending": [],
        "scoring": {"basis": "complete"},
        "components": {
            "workflow": {"score": 1.0, "passed": 9, "total": 9},
            "pytest": {"score": 1.0, "passed": 40, "total": 40, "graded": 40},
            "rubric": {"score": 1.0, "score_discounted": 1.0, "criteria": 12, "passed": 12,
                       "unresolved": 0, "coverage": 1.0},
        },
    },
    "workflows": {"summary": {"workflows_total": 9, "workflows_passed": 9},
                  "workflows": [{"id": "w1", "passed": True, "substeps": []}]},
    "review_queue": {"count": 0, "criteria": []},
}


def run(**overrides):
    doc = copy.deepcopy(PERFECT)
    for dotted, value in overrides.items():
        node = doc
        *parents, leaf = dotted.split("__")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return doc


def test_perfect_run_is_golden():
    golden, reasons = V.grade(run(), browser_substeps=12)
    assert golden, reasons


def test_reward_one_is_not_enough():
    """The trap: reward.json is the pytest rate alone. A broken UI still scores 1.0."""
    doc = run(final__combined_score=0.81,
              final__components__workflow__score=0.6667)
    assert doc["final"]["reward"] == 1.0
    golden, reasons = V.grade(doc, browser_substeps=12)
    assert not golden
    assert any("combined_score" in r for r in reasons)
    assert any("workflow score" in r for r in reasons)


def test_skipped_pytest_is_not_golden():
    golden, reasons = V.grade(run(final__components__pytest__graded=38), browser_substeps=0)
    assert not golden and any("skipped" in r for r in reasons)


def test_review_queue_blocks_golden():
    golden, reasons = V.grade(run(review_queue={"count": 2, "criteria": ["R3", "R7"]}), 12)
    assert not golden and any("human review" in r for r in reasons)


def test_invalid_run_is_not_golden():
    golden, reasons = V.grade(run(final__invalid=["browser_results_missing"]), 12)
    assert not golden and any("invalid" in r for r in reasons)


def test_rubric_coverage_discount_counts():
    golden, reasons = V.grade(run(final__components__rubric__score_discounted=0.9167), 12)
    assert not golden and any("rubric" in r for r in reasons)


def test_pytest_only_workflows_read_from_summary():
    """No browser substeps -> contract.py leaves the workflow channel pending."""
    doc = run(final__pending=["workflow"], final__combined_score=None,
              final__scoring={"basis": "partial_pending_review: workflow"})
    golden, reasons = V.grade(doc, browser_substeps=0)
    assert golden, reasons
    doc["workflows"]["summary"]["workflows_passed"] = 8
    golden, reasons = V.grade(doc, browser_substeps=0)
    assert not golden and any("workflows 8/9" in r for r in reasons)


def test_failed_workflow_names_its_substeps():
    doc = run()
    doc["workflows"]["workflows"] = [{"id": "checkout_denied", "passed": False, "critical_failed": True,
                                      "substeps": [{"ref": "test_output.py::test_denied", "passed": False}]}]
    golden, reasons = V.grade(doc, 12)
    assert not golden
    assert any("checkout_denied (critical failed): test_output.py::test_denied" in r for r in reasons)


def test_missing_final_score():
    golden, reasons = V.grade({"final": None}, 12)
    assert not golden and "final_score.json missing" in reasons[0]


def test_a_workflow_passing_at_ninety_percent_is_not_golden():
    """The harness passes a 10-substep, no-critical workflow with one red substep."""
    doc = run()
    steps = [{"ref": f"step {i}", "passed": True} for i in range(9)] + [{"ref": "Verify the footer", "passed": False}]
    doc["workflows"]["workflows"] = [{"id": "site_edges", "passed": True, "substeps": steps}]
    golden, reasons = V.grade(doc, browser_substeps=10)
    assert not golden
    assert any("passed at the 90% bar but substep(s) failed: Verify the footer" in r for r in reasons)
