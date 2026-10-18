#!/usr/bin/env python3
"""SR's static reads, run in the runner with the HARNESS's own LLM client.

    python3 /golden/probes/spec_read.py <jobs.json> <out.json>

Two kinds of job, each a batch of brief units from one section:

  code      "does this test prove ALL of this requirement?" -- the unit's text
            beside the source of the test(s) that cover it. A test that proves
            only part is reported `partial`, and the host sends that unit to a
            live check instead of trusting the test.
  context   "is this sentence really free of obligation?" -- for units the
            builder labelled `context:`. One that states an obligation is
            reported `obligation`, and the host live-checks it.

The model, provider and bridge are the harness's (run_workflows.make_llm,
DEKU_GRADER_MODEL), so the critic is the same independent grader the official
runs use -- never the agent that built the app.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, "/tests")
from run_workflows import DEFAULT_GRADER_MODEL, make_llm  # noqa: E402

SYSTEM = {
    "code": (
        "You audit whether automated tests PROVE requirements from a product brief. For each "
        "requirement you get its text and the source of the test(s) claimed to cover it. A test "
        "proves a requirement only if its assertions would FAIL whenever any part of the "
        "requirement is false. Asserting a status code when the requirement also says nothing is "
        "stored, or checking one of three listed fields, is PARTIAL. The tests are judged TOGETHER: "
        "a requirement proven half by one test and half by another is FULL. Each test comes with the "
        "module-level constants and helpers it uses; judge only from the code shown, and never assume "
        "an unshown helper checks more. When you answer partial, `missing` must name the part of the "
        "requirement no shown assertion checks. Report through the tool, one verdict per unit."),
    "context": (
        "You audit sentences from a product brief that the builder labelled as context. A sentence is "
        "an OBLIGATION only if it asks the running application to do, show, store, send, refuse or "
        "contain something a visitor or a test could observe -- a behaviour, a piece of content, a "
        "quantity, a constraint on what the app does. It is CONTEXT if it is about the brief itself, "
        "the scope of the work, the build process or history ('there is no starting codebase'), the "
        "motivation or philosophy behind a requirement ('that last action is the whole product', 'the "
        "north star is restraint'), or a summary whose concrete requirements are stated in other "
        "sentences. Judge each sentence on its own words. Report through the tool, one verdict per unit."),
}
TOOL = {
    "code": {
        "name": "report", "description": "One verdict per requirement unit.",
        "input_schema": {"type": "object", "required": ["verdicts"], "properties": {"verdicts": {
            "type": "array", "items": {"type": "object", "required": ["unit", "verdict", "reason"],
                                       "properties": {
                                           "unit": {"type": "string"},
                                           "verdict": {"type": "string", "enum": ["full", "partial"]},
                                           "missing": {"type": "string"},
                                           "reason": {"type": "string"}}}}}}},
    "context": {
        "name": "report", "description": "One verdict per labelled unit.",
        "input_schema": {"type": "object", "required": ["verdicts"], "properties": {"verdicts": {
            "type": "array", "items": {"type": "object", "required": ["unit", "verdict", "reason"],
                                       "properties": {
                                           "unit": {"type": "string"},
                                           "verdict": {"type": "string", "enum": ["context", "obligation"]},
                                           "reason": {"type": "string"}}}}}}},
}


def prompt(job: dict) -> str:
    parts = [f"Section of the brief: {job['section']}", ""]
    for u in job["units"]:
        parts.append(f"## {u['id']}\nRequirement: {u['text']}")
        if job["kind"] == "code":
            for src in u.get("tests") or []:
                parts.append(f"Test `{src['ref']}`:\n```python\n{src['source'][:11000]}\n```")
        else:
            parts.append(f"Builder's reason for labelling it context: {u.get('reason', '')}")
        parts.append("")
    return "\n".join(parts)


def parse(payload: dict) -> list[dict]:
    for block in payload.get("content") or []:
        if block.get("type") == "tool_use":
            return (block.get("input") or {}).get("verdicts") or []
    text = " ".join(b.get("text", "") for b in payload.get("content") or [] if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return (json.loads(m.group(0)) if m else {}).get("verdicts") or []
    except ValueError:
        return []


def keyed(found: list[dict], units: list[dict]) -> dict[str, dict]:
    """Verdicts by unit id, tolerant of how the critic labels them ("B-011 ", "unit B-011").

    A one-unit request that returns exactly one verdict is that unit's, whatever
    label it carries -- the id is a bookkeeping key, not something to fail on.
    """
    out: dict[str, dict] = {}
    for v in found:
        m = re.search(r"B-\d{3}", str(v.get("unit", "")))
        if m:
            out[m.group(0)] = v
    if len(units) == 1 and len(found) == 1 and units[0]["id"] not in out:
        out[units[0]["id"]] = found[0]
    return out


def main() -> int:
    jobs = json.load(open(sys.argv[1]))
    model = os.environ.get("DEKU_GRADER_MODEL", DEFAULT_GRADER_MODEL)
    llm, results = make_llm(model), []
    for i, job in enumerate(jobs, 1):
        print(f"  spec read {i}/{len(jobs)}: {job['kind']} x{len(job['units'])} ({job['section'][:40]})",
              flush=True)
        try:
            payload = llm.message(SYSTEM[job["kind"]], [{"role": "user", "content": prompt(job)}],
                                  [TOOL[job["kind"]]], max_tokens=4096)
            verdicts = keyed(parse(payload), job["units"])
        except Exception as exc:  # recorded per unit; the host treats it as unresolved
            verdicts = {}
            error = f"{exc.__class__.__name__}: {str(exc)[:200]}"
        else:
            error = None
        # A batched answer can skip a unit. Ask again for each skipped one on its own
        # before recording it as unresolved -- a dropped unit is a lost verdict, not a fail.
        for u in [u for u in job["units"] if u["id"] not in verdicts and not error]:
            try:
                single = llm.message(SYSTEM[job["kind"]],
                                     [{"role": "user", "content": prompt({**job, "units": [u]})}],
                                     [TOOL[job["kind"]]], max_tokens=2048)
                verdicts.update(keyed(parse(single), [u]))
            except Exception:
                pass
        # One line per finished job, so the host can show progress while this runs.
        with open(sys.argv[2] + ".progress", "a") as fh:
            fh.write(f"{i}\n")
        for u in job["units"]:
            v = verdicts.get(u["id"])
            results.append({"unit": u["id"], "kind": job["kind"],
                            "verdict": (v or {}).get("verdict"), "reason": (v or {}).get("reason", ""),
                            "missing": (v or {}).get("missing", ""),
                            "error": None if v else (error or "the critic returned no verdict for this unit")})
    json.dump({"model": model, "results": results}, open(sys.argv[2], "w"), indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
