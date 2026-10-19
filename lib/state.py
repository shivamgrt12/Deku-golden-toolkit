"""The golden run's phase machine, persisted in _handoff/golden/state.json.

State is on disk, not in an agent's context, so a member can stop in Cursor and
resume in Claude Code, OpenCode or Kiro: `golden-status` reconstructs where things
stand from this file plus the receipts.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

PHASES = [
    ("P-1", "triage",    "is the bundle itself sound and solvable?"),
    ("P0",  "intake",    "read the contract; PLAN.md maps every checklist id"),
    ("P1",  "design",    "DESIGN.md fixes tokens, type, motion, focus"),
    ("P2",  "backend",   "data model, seed, API; G1-G3 green"),
    ("P3",  "frontend",  "UI to DESIGN.md; G4-G6 green"),
    ("P4",  "hardening", "abuse cases; G7 green"),
    ("P5",  "simplify",  "dead code, scope, one config; G8 green"),
    ("P6",  "grade",     "local graders, then the official runs; G9-G10 green"),
    ("P7",  "signoff",   "a human reads the report and screenshots"),
]
PHASE_IDS = [p[0] for p in PHASES]

# Phases that need the member, not the agent, to move past them.
HUMAN_GATES = {"P1": "approve DESIGN.md", "P7": "sign off the report"}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def path(bundle) -> Path:
    return bundle.golden_dir / "state.json"


def init(bundle) -> dict:
    target = path(bundle)
    if target.is_file():
        return load(bundle)
    state = {"schema": "golden-state-v1", "bundle": bundle.name,
             "phase": "P-1", "created_at": _now(), "history": [], "approvals": {},
             "status": "IN_PROGRESS"}
    for sub in ("evidence",):
        (bundle.golden_dir / sub).mkdir(parents=True, exist_ok=True)
    save(bundle, state)
    return state


def load(bundle) -> dict:
    target = path(bundle)
    if not target.is_file():
        raise SystemExit(f"golden: no state at {target} -- run golden/bin/golden-init first")
    return json.loads(target.read_text())


def save(bundle, state: dict) -> None:
    target = path(bundle)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, indent=2) + "\n")


def advance(bundle, state: dict, to: str, note: str = "") -> dict:
    if to not in PHASE_IDS:
        raise SystemExit(f"golden: unknown phase {to!r}; one of {', '.join(PHASE_IDS)}")
    state["history"].append({"from": state["phase"], "to": to, "at": _now(), "note": note})
    state["phase"] = to
    save(bundle, state)
    return state


def waive(bundle, state: dict, finding_id: str, who: str, note: str) -> dict:
    """Accept one specific finding, with a written reason the receipts carry."""
    if not note.strip():
        raise SystemExit("golden: a waiver needs --note saying why the finding does not apply")
    state.setdefault("waivers", {})[finding_id] = {"by": who, "at": _now(), "note": note}
    save(bundle, state)
    return state


def approve(bundle, state: dict, gate: str, who: str, note: str = "") -> dict:
    if gate not in HUMAN_GATES:
        raise SystemExit(f"golden: {gate} has no human gate; gates: {', '.join(HUMAN_GATES)}")
    state["approvals"][gate] = {"by": who, "at": _now(), "note": note}
    if gate == "P7":
        state["status"] = "GOLDEN"
    save(bundle, state)
    return state
