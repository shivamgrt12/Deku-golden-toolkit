"""Is a graded run golden? Decided from the harness's own output files.

The trap this module exists to avoid: `reward.json` is the pytest pass rate
ALONE (harness/verifier/contract.py). An app with perfect JSON endpoints and a
broken interface scores reward 1.0. Golden means every channel at its ceiling,
read from final_score.json, workflows.json and review_queue.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from paths import GOLDEN


def acceptance() -> dict:
    return yaml.safe_load((GOLDEN / "acceptance.yaml").read_text()) or {}


def _load(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def load_run(run_dir: Path) -> dict:
    """The grading artifacts of one run, wherever the harness put them."""
    run_dir = Path(run_dir)

    def first(*names):
        for name in names:
            for candidate in (run_dir / name, run_dir / "verifier" / name):
                doc = _load(candidate)
                if doc is not None:
                    return doc
        return None

    return {"final": first("final_score.json"),
            "workflows": first("workflows.json"),
            "review_queue": first("review_queue.json"),
            "judge": first("judge.json"),
            "ctrf": first("ctrf.json")}


def _close(value, target: float) -> bool:
    return isinstance(value, (int, float)) and abs(float(value) - target) < 1e-9


def grade(run: dict, browser_substeps: int, bar: dict | None = None) -> tuple[bool, list[str]]:
    """(golden?, reasons it is not). An empty reason list means golden."""
    bar = (bar or acceptance()).get("graders", {})
    final, workflows = run.get("final"), run.get("workflows")
    reasons: list[str] = []
    if not final:
        return False, ["final_score.json missing -- the run did not reach the scorer"]

    invalid = final.get("invalid") or []
    if invalid:
        reasons.append(f"invalid run: {', '.join(map(str, invalid))}")
    if final.get("degraded") and not bar.get("allow_degraded", False):
        reasons.append(f"degraded: {'; '.join(map(str, final['degraded']))}")

    basis = (final.get("scoring") or {}).get("basis", "")
    pending = list(final.get("pending") or [])
    components = final.get("components") or {}

    # A task whose workflows carry no browser substep has nothing for the browser
    # grader to report, so contract.py marks the workflow channel pending and
    # leaves combined_score null. That is the task's shape, not a hole in the
    # measurement -- the workflow verdict is then read from workflows.json.
    workflow_from_summary = browser_substeps == 0 and pending == ["workflow"]

    if basis != "complete" and not workflow_from_summary and bar.get("require_complete_basis", True):
        reasons.append(f"scoring basis is {basis!r}, not 'complete' (pending: {pending})")
    if not workflow_from_summary and not _close(final.get("combined_score"), bar.get("combined_score", 1.0)):
        reasons.append(f"combined_score {final.get('combined_score')} < {bar.get('combined_score', 1.0)}")

    summary = (workflows or {}).get("summary") or {}
    if workflow_from_summary:
        total, passed = summary.get("workflows_total"), summary.get("workflows_passed")
        if not total or passed != total:
            reasons.append(f"workflows {passed}/{total} passed")
    else:
        wf = components.get("workflow") or {}
        if not _close(wf.get("score"), bar.get("workflow_score", 1.0)):
            reasons.append(f"workflow score {wf.get('score')} ({wf.get('passed')}/{wf.get('total')})")

    py = components.get("pytest") or {}
    if not _close(py.get("score"), bar.get("pytest_score", 1.0)):
        reasons.append(f"pytest score {py.get('score')} ({py.get('passed')}/{py.get('graded')})")
    if py.get("graded") != py.get("total"):
        reasons.append(f"pytest skipped {int(py.get('total') or 0) - int(py.get('graded') or 0)} test(s)")

    rb = components.get("rubric") or {}
    if not _close(rb.get("score_discounted"), bar.get("rubric_score_discounted", 1.0)):
        reasons.append(f"rubric {rb.get('passed')}/{rb.get('criteria')} met, "
                       f"{rb.get('unresolved')} unresolved, coverage {rb.get('coverage')}")

    queue = run.get("review_queue")
    count = (queue or {}).get("count") if isinstance(queue, dict) else None
    if count is None and isinstance(run.get("judge"), dict):
        count = ((run["judge"].get("review_queue") or {}).get("count"))
    if count and count > bar.get("max_review_queue", 0):
        reasons.append(f"{count} rubric criterion/criteria held for human review "
                       f"(judge confidence below threshold)")

    # Every SUBSTEP, not just every workflow. The harness passes a workflow at a
    # 0.90 substep ratio with no critical failure, so a 10-substep workflow with
    # no critical step "passes" with one broken substep -- and its workflow score
    # still reads 1.0. A golden app leaves no substep red.
    for wf in (workflows or {}).get("workflows") or []:
        failed = [s.get("ref", "")[:70] for s in wf.get("substeps") or [] if s.get("passed") is not True]
        if not wf.get("passed"):
            tag = " (critical failed)" if wf.get("critical_failed") else ""
            reasons.append(f"workflow {wf.get('id')}{tag}: {'; '.join(failed) or 'not passed'}")
        elif failed:
            reasons.append(f"workflow {wf.get('id')} passed at the 90% bar but substep(s) failed: "
                           f"{'; '.join(failed)}")
    return not reasons, reasons
