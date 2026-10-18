"""Phase exit checks: what must be true before `golden-status --advance` moves on.

A phase is never left on an agent's word. Each exit names either a host lint
(P0, P1) or the gauntlet stages whose CURRENT receipts must be PASS, plus the
member approval where a human owns the gate.
"""
from __future__ import annotations

import design_preview as DP
import media as M
import member_review as MR
import phaselints as L
import receipts as R
import state as S
from stages import BY_ID

# phase -> (lint functions, gauntlet stages that must be current PASS, approval required)
EXITS = {
    "P-1": ([], ["T0"], None),
    "P0":  ([L.plan_lint, L.sources_lint], [], None),
    "P1":  ([L.design_lint, M.media_plan_lint, DP.contrast_claims_lint, DP.preview_lint], [], "P1"),
    "P2":  ([], ["G0", "G1", "G2", "G3"], None),
    "P3":  ([M.assets_lint], ["G4", "G5", "G6"], None),
    "P4":  ([], ["G7"], None),
    "P5":  ([], ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "SR"], None),
    "P6":  ([], ["G10"], None),
    "P7":  ([MR.lint], ["G11"], "P7"),
}


def exit_problems(b, st: dict, phase: str) -> list[str]:
    lints, stages, approval = EXITS[phase]
    problems = [p for lint in lints for p in lint(b)]
    latest, current = R.latest(R.read(b)), R.input_hashes(b)
    for sid in stages:
        row = latest.get(sid)
        if row is None:
            problems.append(f"{sid} has not run -- golden/bin/gauntlet <bundle> --only {sid}")
        elif R.is_stale(row, current, BY_ID[sid].depends_on):
            problems.append(f"{sid} is STALE: the app or bundle changed after it ran -- re-run it")
        elif row["verdict"] != R.PASS:
            problems.append(f"{sid} is {row['verdict']}: {row['summary']}")
    if approval and approval not in st.get("approvals", {}):
        # Reported last: the member is asked only once the machine checks are green.
        problems.append(f"waiting for the member: {S.HUMAN_GATES[approval]} "
                        f"(golden/bin/golden-status <bundle> --approve {approval})")
    return problems


def advance(b, st: dict) -> tuple[bool, list[str]]:
    phase = st["phase"]
    problems = exit_problems(b, st, phase)
    if problems:
        return False, problems
    order = S.PHASE_IDS
    if phase == order[-1]:
        return True, []
    S.advance(b, st, order[order.index(phase) + 1], note=f"{phase} exit check green")
    return True, []
