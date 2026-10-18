"""The official runs: the real harness, end to end, through `deku-run`.

These are the only runs whose numbers the client sees, so the gauntlet never
substitutes for them -- it only makes sure they are not spent on an app that a
local check could have failed for free. Each one costs grader tokens and wall
time, which is why G10 runs only when the member passes --official.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from paths import HARNESS, load_harness_env


def _run_dirs() -> set[Path]:
    out = HARNESS / "output"
    if not out.is_dir():
        return set()
    return {p for p in out.glob("**/run_*") if p.is_dir()}


def deku_run(bundle_root: Path, agent: str, log_to: Path, timeout: float) -> tuple[int, list[Path]]:
    """Run `scripts/deku-run <bundle> -a <agent>`; return (exit code, new run dirs)."""
    before = _run_dirs()
    log_to.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_to.open("w", encoding="utf-8") as fh:
        fh.write(f"$ scripts/deku-run {bundle_root} -a {agent}\n\n")
        fh.flush()
        env = dict(os.environ)
        key = load_harness_env().get("ANTHROPIC_API_KEY")
        if key and not env.get("ANTHROPIC_API_KEY"):
            env["ANTHROPIC_API_KEY"] = key  # the bridge secret in bridge mode
        try:
            proc = subprocess.run([str(HARNESS / "scripts" / "deku-run"), str(bundle_root), "-a", agent],
                                  cwd=str(HARNESS), stdout=fh, stderr=subprocess.STDOUT,
                                  timeout=timeout, stdin=subprocess.DEVNULL, env=env)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            fh.write(f"\n--- golden: timed out after {timeout:.0f}s ---\n")
            code = 124
        fh.write(f"\n--- exit {code} after {time.monotonic() - started:.0f}s ---\n")
    new = sorted(_run_dirs() - before, key=lambda p: p.stat().st_mtime)
    return code, _trial_results(log_to) + new


def _trial_results(log: Path) -> list[Path]:
    """The scored verifier_fresh/ of each trial this run's own log names.

    deku-run publishes output/<task>/<agent>/run_N with score.json, not
    final_score.json; the full grading artifacts stay in
    jobs/<stamp>/<trial>/verifier_fresh/. Reading the trial id from our own log,
    rather than diffing directories, ignores any other run going on at the time.
    """
    trials = re.findall(r"^repackaged (\S+)\s+->", log.read_text(errors="replace"), re.M)
    found = []
    for trial in dict.fromkeys(trials):
        found += [d for d in (HARNESS / "jobs").glob(f"*/{trial}/verifier_fresh")
                  if (d / "final_score.json").is_file()]
    return found
