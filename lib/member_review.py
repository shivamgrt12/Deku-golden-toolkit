"""member-review.md: the short list a human must decide before sign-off.

Everything else in a golden run is proven by a script or by the independent
critic. Four kinds of brief unit rest on a judgement the member owns:

  checklist gaps     no grader checks them; a golden test of OURS does -- written by
                     the same agent that built the app. Does that test prove it?
  context labels     the builder said the unit asks for nothing. Is that true?
  cannot observe     SR's critic could not see it through a browser. Acceptable?
  member check       the tests prove only part of the unit; the critic names the
                     missing part, and the member checks it in the running app.

Each item shows SR's verdict and, for a gap, the test's assertions pulled out of
its code as plain lines, so it can be judged without reading Python. The member
ticks `[x]` to accept or writes `REJECT: <why>` under it. Regenerating the file
keeps every decision already made; P7 cannot close until every item is decided
and none is rejected.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import brief_units as BU
import phaselints as L

ITEM_LINE = re.compile(r"^- \[([ xX])\] (B-\d{3})\b")
REJECT_LINE = re.compile(r"^\s+REJECT:\s*(.+)$")


def path(b) -> Path:
    return b.golden_dir / "member-review.md"


def assertions(b, ref: str) -> list[str]:
    """The assert / expect lines of one golden test, as plain lines."""
    file, _, name = ref.partition("::")
    src_path = b.root / "solution" / file
    try:
        text = src_path.read_text()
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return ["(the test file could not be read)"]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = text.splitlines()[node.lineno - 1:node.end_lineno]
            found = [l.strip() for l in body if re.search(r"^\s*assert\b|expect\(|\.to_(have|be|contain)", l)]
            return [re.sub(r"\s+", " ", l)[:140] for l in found] or ["(this test asserts nothing)"]
    return ["(no such test function)"]


def decisions(b) -> dict[str, dict]:
    """Decisions already recorded in member-review.md: unit -> {accepted, reject}."""
    out: dict[str, dict] = {}
    if not path(b).is_file():
        return out
    current = None
    for line in path(b).read_text().splitlines():
        m = ITEM_LINE.match(line)
        if m:
            current = m.group(2)
            out[current] = {"accepted": m.group(1).lower() == "x", "reject": None}
            continue
        r = REJECT_LINE.match(line)
        if r and current:
            out[current]["reject"] = r.group(1).strip()
    return out


def items(b) -> list[dict]:
    cov = L.brief_coverage(b)
    units = {u.id: u for u in BU.units(b)}
    spec = {}
    sr_path = b.golden_dir / "spec-review.json"
    if sr_path.is_file():
        try:
            spec = json.loads(sr_path.read_text()).get("units") or {}
        except ValueError:
            spec = {}
    out = []
    for uid, u in units.items():
        row, sr = cov.get(uid), spec.get(uid, {})
        if row and row["kind"] == "gap":
            out.append({"kind": "gap", "unit": uid, "text": u.text, "section": u.section,
                        "test": row["test"], "asserts": assertions(b, row["test"]) if row["test"] else [],
                        "sr": sr})
        elif row and row["kind"] == "context":
            out.append({"kind": "context", "unit": uid, "text": u.text, "section": u.section,
                        "reason": row["mapping"].split(":", 1)[-1].strip(), "sr": sr})
        elif sr.get("verdict") == "cannot observe":
            out.append({"kind": "cannot", "unit": uid, "text": u.text, "section": u.section, "sr": sr})
        elif sr.get("verdict") == "member check":
            out.append({"kind": "partial", "unit": uid, "text": u.text, "section": u.section, "sr": sr,
                        "missing": sr.get("why", ""), "tests": (sr.get("evidence") or {}).get("tests", [])})
    return out


def _sr_line(sr: dict) -> str:
    if not sr:
        return "Spec review: not run yet"
    v = sr.get("verdict", "?")
    extra = " -- the critic says this states an obligation" if sr.get("mislabelled_context") else ""
    why = sr.get("why") or (sr.get("evidence") or {}).get("note") or (sr.get("evidence") or {}).get("critic") or ""
    return f"Spec review: **{v}**{extra}" + (f" -- {str(why)[:160]}" if why else "")


def write(b) -> Path:
    found, made = items(b), decisions(b)
    sections = {"gap": "Checklist gaps -- requirements no grader checks; a golden test of ours proves them",
                "context": "Units labelled context -- the builder says they ask the app for nothing",
                "cannot": "Units the spec review could not observe through the browser",
                "partial": "Partly proven by tests -- check the missing part in the running app"}
    lines = [f"# Member review — {b.name}", "",
             "Decide every item: tick `[x]` to accept, or write `REJECT: <why>` on the line below it.",
             "Regenerating this file keeps your decisions. Sign-off (P7) needs every item decided and none",
             "rejected; a rejection sends the item back to the phase that owns it.", ""]
    for kind, title in sections.items():
        group = [i for i in found if i["kind"] == kind]
        if not group:
            continue
        lines += [f"## {title}", ""]
        for i in group:
            d = made.get(i["unit"], {})
            tick = "x" if d.get("accepted") else " "
            lines.append(f"- [{tick}] {i['unit']} ({i['section']}) \"{i['text'][:220]}\"")
            if kind == "gap":
                lines.append(f"      Proven by: `{i['test']}`")
                lines.append("      The test asserts:")
                lines += [f"        - `{a}`" for a in i["asserts"][:8]]
            elif kind == "context":
                lines.append(f"      Builder's reason: {i['reason'][:200]}")
            if kind == "partial":
                lines.append(f"      Tests: {', '.join(t.split('::')[-1] for t in i['tests'][:4])}")
                lines.append(f"      Check in the app: {str(i['missing'])[:300] or 'the critic named no part -- read the requirement'}")
            else:
                lines.append(f"      {_sr_line(i['sr'])}")
            if d.get("reject"):
                lines.append(f"      REJECT: {d['reject']}")
            lines.append("")
    if not found:
        lines += ["Nothing to review: every brief unit is fulfilled through the checklist's graders.", ""]
    path(b).write_text("\n".join(lines))
    return path(b)


def lint(b) -> list[str]:
    """P7: every item decided, none rejected."""
    found, made = items(b), decisions(b)
    if found and not path(b).is_file():
        return [f"member-review.md does not exist -- run golden/bin/gauntlet <bundle> --only G11"]
    problems = []
    undecided = [i["unit"] for i in found if not made.get(i["unit"], {}).get("accepted")
                 and not made.get(i["unit"], {}).get("reject")]
    if undecided:
        problems.append(f"member review: {len(undecided)} item(s) not decided yet "
                        f"({', '.join(undecided[:10])}{' ...' if len(undecided) > 10 else ''})")
    for i in found:
        d = made.get(i["unit"], {})
        if d.get("reject"):
            owner = {"gap": "P3 (its golden test)", "context": "P0 (its mapping)", "cannot": "P3/P4",
                     "partial": "P3/P4 (fix the app, or add a golden test)"}[i["kind"]]
            problems.append(f"member rejected {i['unit']}: {d['reject'][:120]} -- reopen {owner}")
    return problems
