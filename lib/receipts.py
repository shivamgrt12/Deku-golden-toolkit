"""Receipts: the only evidence that a gauntlet stage ran, and over which bytes.

An agent saying "G3 is green" is not evidence. A receipt is: one JSON line per
stage run, carrying the verdict and the SHA-256 of every input it read. When
the app changes after a stage passed, the hash no longer matches and the stage
is STALE -- `golden-status` asks for it again. Same idea as genkit's
`_handoff/<project>.gates.jsonl` (ISSUES C-02): a verdict is bound to bytes.
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import hashlib
import json
from pathlib import Path

# Never part of the app's identity: installed trees, caches, build output the
# manifest regenerates, and the two reserved empty directories.
IGNORE_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
               ".mypy_cache", ".ruff_cache", ".git", ".next", ".turbo",
               ".browser_screenshots", ".downloads"}
IGNORE_FILES = {".DS_Store", "*.log", "*.pyc"}

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"


def _ignored(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in IGNORE_FILES)


def tree_sha(*roots: Path) -> str:
    """One SHA-256 over every file under `roots`, by relative path and content."""
    h = hashlib.sha256()
    for root in roots:
        root = Path(root)
        if root.is_file():
            h.update(root.name.encode() + b"\0" + root.read_bytes() + b"\0")
            continue
        if not root.is_dir():
            h.update(f"<missing:{root.name}>".encode())
            continue
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if any(part in IGNORE_DIRS for part in rel.parts) or not path.is_file():
                continue
            if _ignored(path.name):
                continue
            h.update(str(rel).encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def input_hashes(bundle) -> dict[str, str]:
    """The four things a verdict can go stale against."""
    from paths import harness_sha  # noqa: PLC0415
    return {
        "app": tree_sha(bundle.app_dir, bundle.solve_sh),
        "bundle": tree_sha(bundle.root / "task.toml", bundle.root / "instruction.md",
                           bundle.root / "tests", bundle.env_dir),
        "harness": harness_sha(),
        # The golden suites and the brief mapping they prove: a new or changed
        # golden test, or a remapped brief unit, re-opens the stages that run them.
        "golden": tree_sha(bundle.root / "solution" / "golden_tests", bundle.golden_dir / "PLAN.md"),
    }


def path(bundle) -> Path:
    return bundle.golden_dir / "receipts.jsonl"


def append(bundle, stage: str, verdict: str, summary: str,
           details: dict | None = None, inputs: dict | None = None) -> dict:
    row = {
        "stage": stage,
        "verdict": verdict,
        "summary": summary,
        "at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": inputs if inputs is not None else input_hashes(bundle),
        "details": details or {},
    }
    target = path(bundle)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def read(bundle) -> list[dict]:
    target = path(bundle)
    if not target.is_file():
        return []
    rows = []
    for line in target.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def latest(rows: list[dict]) -> dict[str, dict]:
    """The most recent receipt per stage."""
    out: dict[str, dict] = {}
    for row in rows:
        out[row["stage"]] = row
    return out


def is_stale(row: dict, current: dict[str, str], depends_on: tuple[str, ...]) -> bool:
    """True when any input this stage depends on has changed since it ran."""
    then = row.get("inputs") or {}
    return any(then.get(key) != current.get(key) for key in depends_on)
