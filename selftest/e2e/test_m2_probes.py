"""Each M2 probe must catch a planted defect -- a probe that cannot fail is not a check.

Run with: golden/bin/gauntlet --self-test --e2e   (needs Docker)
"""
import shutil
from pathlib import Path

import cli
import receipts as R
from bundle import Bundle

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "reference_golden_tests"
APP = "solution/app"


def _with_suites(reference):
    shutil.copytree(FIXTURE, reference / "solution" / "golden_tests", dirs_exist_ok=True)
    return reference


def _plant(reference, rel, old, new):
    path = reference / APP / rel
    text = path.read_text()
    assert old in text, f"planted-defect anchor moved in {rel}; update the calibration"
    path.write_text(text.replace(old, new, 1))


def _verdict(reference, stage):
    return R.latest(R.read(Bundle.load(reference)))[stage]


def test_console_error_is_caught_by_inspect(reference):
    _plant(_with_suites(reference), "templates/base.html", "</body>",
           "<script>console.error('golden planted defect')</script></body>")
    assert cli.main(["gauntlet", str(reference), "--only", "G5"]) == 2
    row = _verdict(reference, "G5")
    assert row["verdict"] == "FAIL"
    assert any("console error" in p and "golden planted defect" in p for p in row["details"]["problems"])


def test_transition_all_is_caught_by_the_design_probe(reference):
    _plant(_with_suites(reference), "static/css/site.css", "/* ===",
           "body { transition: all .2s ease; }\n/* ===")
    assert cli.main(["gauntlet", str(reference), "--only", "G6"]) == 2
    row = _verdict(reference, "G6")
    assert any("transition: all" in p for p in row["details"]["problems"])


def test_route_that_crashes_on_garbage_is_caught_by_abuse(reference):
    _plant(_with_suites(reference), "cirrus/api_public.py",
           'def health() -> tuple[Response, int]:\n',
           'def health() -> tuple[Response, int]:\n'
           '    from flask import request as _r\n'
           '    int(_r.args.get("n", "0"))\n')
    # the generic probe needs an endpoint whose bad input reaches the crash
    brief = reference / "instruction.md"
    brief.write_text(brief.read_text() + "\n`GET /api/health?n={n}`\n")
    assert cli.main(["gauntlet", str(reference), "--only", "G7"]) == 2
    row = _verdict(reference, "G7")
    assert any("-> 500" in p for p in row["details"]["problems"])


def test_dead_code_is_caught_by_the_code_audit(reference):
    _plant(_with_suites(reference), "app.py", "app = create_app()\n",
           "app = create_app()\nimport json as _golden_unused\n\n\ndef _golden_never_called():\n"
           "    return 1\n")
    assert cli.main(["gauntlet", str(reference), "--only", "G8"]) == 2
    row = _verdict(reference, "G8")
    assert any("ruff" in p or "vulture" in p for p in row["details"]["problems"])


def test_low_contrast_and_unpinned_small_text_still_fail(reference):
    """The design probe was loosened for unmeasurable and brief-mandated text;
    real low contrast and an unpinned small size must still be caught."""
    _plant(_with_suites(reference), "templates/base.html", "</body>",
           '<p style="color:#333333;background:#060403;font-size:11px">golden planted faint note</p></body>')
    assert cli.main(["gauntlet", str(reference), "--only", "G6"]) == 2
    problems = " ".join(_verdict(reference, "G6")["details"]["problems"])
    assert "below WCAG AA contrast" in problems and "golden planted faint note" in problems
    assert "size(s) the brief does not pin (11.0px)" in problems or "(11px)" in problems


def test_abuse_suite_actually_runs(reference):
    _with_suites(reference)
    cli.main(["gauntlet", str(reference), "--only", "G7"])
    # 3 test functions; CTRF collapses the 4 parametrized forged-token cases into one entry
    assert _verdict(reference, "G7")["details"]["task_suite_tests"] == 3
