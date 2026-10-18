"""How much of a verdict is the app, and how much is the grader?

The browser grader and the rubric judge are LLMs. One green run proves little:
a substep can pass on a lucky read. This runs the full local grading pass N
times, each on a cold stack, and reports per substep and per criterion whether
the verdict was stable:

  stable green   the app does this, and the grader sees it every time
  stable red     an app defect -- fix it
  flapping       grader noise (or a racy app): read the frames, then make the
                 app legible -- state in words, labelled controls, confirmations

"Golden on two official runs" is only predictable when the flapping list is empty.
"""
from __future__ import annotations

import datetime as _dt
import json
from collections import defaultdict
from pathlib import Path

from stages import Context, run_local_graders


def _items(run: dict) -> dict[str, bool | None]:
    out: dict[str, bool | None] = {}
    for wf in (run.get("workflows") or {}).get("workflows") or []:
        out[f"workflow  {wf.get('id')}"] = bool(wf.get("passed"))
        for i, sub in enumerate(wf.get("substeps") or [], 1):
            ref = str(sub.get("ref") or "")[:80]
            out[f"{sub.get('kind', '?'):8}  {wf.get('id')}#{i}  {ref}"] = sub.get("passed")
    dims = (run.get("judge") or {}).get("dimensions") or {}
    if isinstance(dims, dict):
        for key, dim in dims.items():
            if isinstance(dim, dict):
                passed = dim.get("passed")
                if passed is None and dim.get("score") is not None:
                    passed = float(dim["score"]) > 0
                out[f"rubric    {key}"] = passed
    return out


def summarize(runs: list[dict]) -> dict:
    seen: dict[str, list] = defaultdict(list)
    for run in runs:
        for key, value in _items(run).items():
            seen[key].append(value)
    stable_green, stable_red, flapping, unobserved = [], [], [], []
    for key, values in sorted(seen.items()):
        observed = [v for v in values if v is not None]
        row = {"item": key, "passes": sum(1 for v in observed if v), "runs": len(values),
               "unobserved": len(values) - len(observed)}
        if not observed:
            unobserved.append(row)
        elif all(observed):
            stable_green.append(row)
        elif not any(observed):
            stable_red.append(row)
        else:
            flapping.append(row)
    combined = [(r.get("final") or {}).get("combined_score") for r in runs]
    return {"runs": len(runs), "combined_scores": combined,
            "stable_green": stable_green, "stable_red": stable_red,
            "flapping": flapping, "unobserved": unobserved}


def render(report: dict) -> str:
    lines = [f"# Grader noise -- {report['runs']} cold runs", "",
             f"combined_score per run: {report['combined_scores']}", "",
             f"- stable green: {len(report['stable_green'])}",
             f"- stable red (app defects): {len(report['stable_red'])}",
             f"- flapping (grader noise or racy app): {len(report['flapping'])}",
             f"- never observed: {len(report['unobserved'])}", ""]
    for title, key in (("Stable red", "stable_red"), ("Flapping", "flapping"),
                       ("Never observed", "unobserved")):
        if report[key]:
            lines += [f"## {title}", "", "| item | passed | runs |", "|---|---|---|"]
            lines += [f"| `{r['item']}` | {r['passes']} | {r['runs']} |" for r in report[key]]
            lines.append("")
    return "\n".join(lines)


def measure(ctx: Context, n: int) -> tuple[Path, dict]:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    root = ctx.evidence("noise") / stamp
    runs = []
    for i in range(1, n + 1):
        print(f"  noise run {i}/{n} ...", flush=True)
        runs.append(run_local_graders(ctx, root / f"run-{i}"))
    report = summarize(runs)
    (root / "noise.json").write_text(json.dumps(report, indent=2) + "\n")
    (root / "noise.md").write_text(render(report) + "\n")
    return root, report
