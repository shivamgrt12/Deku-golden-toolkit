"""SR -- Spec Review: is every requirement unit of instruction.md actually met?

The graders check the checklist; the checklist is genkit's reading of the brief;
the builder's PLAN.md maps the brief to the checklist. Each link can be weaker
than it looks. SR checks the far end -- the brief itself -- against the app,
with a critic that is not the builder (the harness's own LLM grader):

  unit proven by a pytest test       CODE READ: does the test assert all of it?
  unit walked by a G4 walkthrough    CODE READ: does the walkthrough assert all of it?
                                     (its live, independent check is G10's browser
                                     grader, which walks the same substep anyway)
  unit labelled `context:`           CONTEXT READ: is it really free of obligation?
  units no deterministic test        LIVE CHECK: the harness browser grader uses the
  covers -- checklist gaps proven    running app as a visitor would and reports
  only by our own test, judge-only   met / not met with a screenshot
  units, a context that is an
  obligation
  a code read that came back         MEMBER CHECK (default): listed in member-review.md
  partial                            with what the critic says is missing; the member
                                     checks that part in the app at P7. With
                                     --full-live it is live-checked instead (~3.5 min
                                     a unit, so hours on a large brief).

Every unit ends with one verdict in _handoff/golden/spec-review.json. SR is green
when none is `not met` and none is unresolved; `cannot observe` and `member check`
units are allowed but go to the member.
"""
from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from pathlib import Path

import brief_units as BU
import phaselints as L

ID = re.compile(r"C-[A-Z]{2}-\d+")
SUBSTEP_MARK = re.compile(r"@pytest\.mark\.substep\(\s*[\"']([\w-]+)[\"']\s*,\s*(\d+)\s*\)")
LIVE_BATCH = 8          # live checks per generated workflow (one browser session each)
READ_BATCH = 6          # units per static-read LLM call (each carries its tests and their helpers)
# A live grader that FAILS a unit while saying it could not see it has not found a
# defect: "cannot be verified through the browser", "a meta-statement about the
# brief" -> `cannot observe`, which goes to the member rather than failing SR.
UNOBSERVABLE = re.compile(
    r"cannot (?:be )?(?:observ|verif|check|test|determin|confirm)|not (?:an? )?(?:observ|verif|testable)|"
    r"(?:no|without) (?:way|means) to (?:observ|verif)|meta[- ]statement|not (?:about|a claim about) "
    r"(?:the )?(?:running )?app|outside (?:what|the scope of what) (?:the )?browser", re.I)


# ---------------------------------------------------------------- who grades what
def _functions(path: Path) -> dict[str, str]:
    """Top-level test function name -> its source, for one file."""
    try:
        text = path.read_text()
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return {}
    lines = text.splitlines()
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            start = (node.decorator_list[0].lineno if node.decorator_list else node.lineno) - 1
            out[node.name] = "\n".join(lines[start:node.end_lineno])
    return out


def grader_map(b) -> dict[str, dict]:
    """checklist item -> {"pytest": {name: source}, "walkthrough": {name: source}, "judge": bool}."""
    out: dict[str, dict] = defaultdict(lambda: {"pytest": {}, "walkthrough": {}, "judge": False})
    tests = b.root / "tests"
    sources: dict[str, str] = {}
    for f in sorted(tests.glob("test_*.py")):
        sources.update(_functions(f))
    for name, src in sources.items():           # `cov:` in a test's docstring
        doc = re.search(r'"""(.*?)"""', src, re.S)
        for iid in ID.findall(doc.group(1) if doc else ""):
            out[iid]["pytest"][name] = src
    walk: dict[tuple[str, int], dict[str, str]] = defaultdict(dict)
    wdir = b.root / "solution" / "golden_tests" / "walkthrough"
    if wdir.is_dir():
        for f in sorted(wdir.rglob("test_*.py")):
            for name, src in _functions(f).items():
                for wf, idx in SUBSTEP_MARK.findall(src):
                    walk[(wf, int(idx))][f"walkthrough/{f.name}::{name}"] = src
    for wf in b.workflows:
        n_browser = 0
        for step in wf.get("substeps") or []:
            ids = ID.findall(str(step.get("cov") or ""))
            if step.get("kind") == "browser":
                n_browser += 1
                for iid in ids:
                    out[iid]["walkthrough"].update(walk.get((wf.get("id"), n_browser), {}))
            elif step.get("kind") == "pytest":
                name = str(step.get("test") or "").split("::")[-1]
                for iid in ids:
                    if name in sources:
                        out[iid]["pytest"][name] = sources[name]
    _from_matrix(b, out, sources, walk)
    prov = sorted(b.golden_dir.parent.glob("*rubric-provenance.json"))
    if prov:
        try:
            data = json.loads(prov[0].read_text())
            for v in data.values():
                for iid in (v.get("items") if isinstance(v, dict) else v) or []:
                    out[iid]["judge"] = True
        except (ValueError, AttributeError):
            pass
    return out


MATRIX_CELL = re.compile(r"^(pytest|browser|rubric):(?:[\w./-]+::)?([\w-]+)(?:\[(\d+)\])?$")


def _from_matrix(b, out: dict, sources: dict[str, str], walk: dict) -> None:
    """genkit's tests/traceability-matrix.csv: which grader covers which checklist item.

    Current bundles record coverage here rather than in test docstrings or on
    pytest substeps: the second row names each column's grader
    (`pytest:test_output.py::test_x`, `browser:<workflow>[n]`, `rubric:R3`), and
    each requirement row lists its checklist ids in `member_ids` with YES under
    every grader that covers it.
    """
    path = b.root / "tests" / "traceability-matrix.csv"
    if not path.is_file():
        return
    import csv  # noqa: PLC0415
    with path.open(newline="") as fh:
        table = list(csv.reader(fh))
    if len(table) < 3 or "member_ids" not in table[0]:
        return
    ids_col = table[0].index("member_ids")
    graders = {i: MATRIX_CELL.match(cell.strip()) for i, cell in enumerate(table[1]) if cell.strip()}
    for row in table[2:]:
        ids = ID.findall(row[ids_col]) if ids_col < len(row) else []
        for i, m in graders.items():
            if not m or i >= len(row) or row[i].strip().upper() != "YES":
                continue
            kind, name, idx = m.groups()
            for iid in ids:
                if kind == "pytest" and name in sources:
                    out[iid]["pytest"][name] = sources[name]
                elif kind == "browser" and idx:
                    out[iid]["walkthrough"].update(walk.get((name, int(idx)), {}))
                elif kind == "rubric":
                    out[iid]["judge"] = True


MAX_TESTS = 6           # tests shown to the critic per unit, most relevant first
DEF_CAP = 1500          # chars of one module-level definition shown with a test
CONTEXT_CAP = 5000      # chars of definitions shown with one test
STOP = {"the", "and", "for", "with", "that", "this", "from", "every", "each", "its", "are", "not",
        "test", "tests", "into", "one", "any", "has", "have", "when", "only", "never", "than", "then"}


def _definitions(b) -> dict[str, str]:
    """Module-level names in the test files (constants, helpers, fixtures) -> their source."""
    out: dict[str, str] = {}
    files = sorted((b.root / "tests").glob("*.py"))
    golden = b.root / "solution" / "golden_tests"
    if golden.is_dir():
        files += sorted(golden.rglob("*.py"))
    for f in files:
        try:
            text = f.read_text()
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue
        lines = text.splitlines()
        for node in tree.body:
            names = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("test_"):
                    names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            if names:
                start = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno) - 1
                src = "\n".join(lines[start:node.end_lineno])
                if len(src) > DEF_CAP:
                    src = src[:DEF_CAP] + "\n    # ... (truncated)"
                for n in names:
                    out.setdefault(n, src)
    return out


def _used_names(src: str) -> set[str]:
    try:
        return {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
    except SyntaxError:
        return set(re.findall(r"\b[A-Za-z_]\w*\b", src))


def with_context(src: str, defs: dict[str, str]) -> str:
    """A test plus the module-level definitions it uses, two levels deep.

    The critic is told never to assume what an unshown helper checks, so a test
    shown without its RUN_FIELDS or its request helper reads as `partial` even
    when it proves the whole requirement.
    """
    seen, shown, frontier = set(), [], _used_names(src)
    for _ in range(2):
        nxt = set()
        for name in sorted(frontier):
            if name in defs and name not in seen:
                seen.add(name)
                shown.append(defs[name])
                nxt |= _used_names(defs[name])
        frontier = nxt
    body, total = [], 0
    for d in dict.fromkeys(shown):
        if total + len(d) > CONTEXT_CAP:
            body.append("# ... (further definitions omitted)")
            break
        body.append(d)
        total += len(d)
    return src if not body else src + "\n\n# --- module-level definitions this test uses ---\n" + "\n\n".join(body)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP}


def pick_tests(text: str, tests: dict[str, str]) -> list[str]:
    """The MAX_TESTS tests whose name and docstring share most words with the unit."""
    want = _words(text)

    def score(item):
        name, src = item
        doc = re.search(r'"""(.*?)"""', src, re.S)
        return (-len(want & _words(name.replace("_", " ") + " " + (doc.group(1) if doc else ""))), name)

    return [n for n, _ in sorted(tests.items(), key=score)[:MAX_TESTS]]


# ---------------------------------------------------------------- the plan
def classify(b) -> dict[str, dict]:
    """unit id -> {"route": code|context|live|unmapped, "tests": [...], ...}."""
    units, cov, gmap = BU.units(b), L.brief_coverage(b), grader_map(b)
    defs = _definitions(b)
    plan = {}
    for u in units:
        row = cov.get(u.id)
        base = {"unit": u.id, "section": u.section, "text": u.text}
        if row is None:
            plan[u.id] = {**base, "route": "unmapped"}
        elif row["kind"] == "context":
            plan[u.id] = {**base, "route": "context", "reason": row["mapping"].split(":", 1)[-1].strip()}
        elif row["kind"] == "gap":
            plan[u.id] = {**base, "route": "live", "why": "checklist gap: proven only by our own test",
                          "golden_test": row["test"]}
        else:
            pytest = {n: s for i in row["ids"] for n, s in gmap.get(i, {}).get("pytest", {}).items()}
            walks = {n: s for i in row["ids"] for n, s in gmap.get(i, {}).get("walkthrough", {}).items()}
            if pytest or walks:
                # Both kinds together: a requirement is often proven half by an API
                # test and half by the walkthrough that shows it on the page.
                pool = {f"tests::{n}": s for n, s in pytest.items()} | dict(walks)
                chosen = pick_tests(u.text, pool)
                plan[u.id] = {**base, "route": "code", "by": "pytest" if pytest else "walkthrough",
                              "ids": sorted(row["ids"]),
                              "tests": [{"ref": n, "source": with_context(pool[n], defs)} for n in chosen]}
            else:
                plan[u.id] = {**base, "route": "live", "ids": sorted(row["ids"]),
                              "why": "judged by an LLM only" if any(gmap.get(i, {}).get("judge") for i in row["ids"])
                              else "no deterministic test covers it"}
    return plan


def read_jobs(plan: dict[str, dict]) -> list[dict]:
    by: dict[tuple[str, str], list] = defaultdict(list)
    for p in plan.values():
        if p["route"] == "code":
            by[("code", p["section"])].append({"id": p["unit"], "text": p["text"], "tests": p["tests"]})
        elif p["route"] == "context":
            by[("context", p["section"])].append({"id": p["unit"], "text": p["text"], "reason": p["reason"]})
    jobs = []
    for (kind, section), units in by.items():
        for i in range(0, len(units), READ_BATCH):
            jobs.append({"kind": kind, "section": section, "units": units[i:i + READ_BATCH]})
    return jobs


LIVE_PROMPT = ("Check, by using the running app as a visitor would (sign in with the documented "
               "credentials only if the requirement concerns a signed-in role), that this requirement "
               "from the product brief holds. Pass only if every part of it is observably true; if a part "
               "cannot be observed through the browser, fail and say which part. Requirement: «{text}»")


def live_workflows(plan: dict[str, dict], unit_ids: list[str]) -> list[dict]:
    """The live checks as a workflows.yaml the harness browser grader runs."""
    by: dict[str, list[str]] = defaultdict(list)
    for uid in unit_ids:
        by[plan[uid]["section"]].append(uid)
    flows = []
    for section, ids in by.items():
        for i in range(0, len(ids), LIVE_BATCH):
            chunk = ids[i:i + LIVE_BATCH]
            slug = re.sub(r"[^a-z0-9]+", "_", section.lower()).strip("_")[:40] or "brief"
            flows.append({"id": f"sr_{slug}_{i // LIVE_BATCH + 1}",
                          "purpose": f"spec review of {section}",
                          "substeps": [{"kind": "browser", "do": LIVE_PROMPT.format(text=plan[u]["text"]),
                                        "unit": u} for u in chunk]})
    return flows


# ---------------------------------------------------------------- verdicts
def assemble(plan: dict[str, dict], reads: dict[str, dict], live: dict[str, dict]) -> dict[str, dict]:
    """One verdict per unit: met | not met | cannot observe | unresolved."""
    out = {}
    for uid, p in plan.items():
        v = {"unit": uid, "section": p["section"], "text": p["text"], "route": p["route"]}
        r, l = reads.get(uid), live.get(uid)
        if p["route"] == "unmapped":
            v.update(verdict="not met", why="not accounted for in PLAN.md ## Brief coverage")
        elif l is not None:                                  # a live check settles it
            if p["route"] == "code":
                v["code_read"] = {"verdict": "partial", "missing": (r or {}).get("missing", ""),
                                  "reason": (r or {}).get("reason", "")}
            if p["route"] == "context":
                v["context_read"] = {"verdict": "obligation", "reason": (r or {}).get("reason", "")}
                v["mislabelled_context"] = True
            if l.get("error") == "grader_step_cap" or "step cap" in str(l.get("note", "")):
                # Running out of steps proves nothing about the app.
                v.update(verdict="unresolved", why="inconclusive: the live check ran out of steps before "
                         "reaching a verdict -- re-run with --resume-spec; if it repeats, the unit is too "
                         "large for one check and the member decides")
            elif l.get("error"):
                v.update(verdict="unresolved", why=f"live check could not run: {l.get('error')}")
            elif l.get("passed"):
                v.update(verdict="met", evidence={"note": l.get("note", ""), "screenshot": l.get("screenshot")})
            elif UNOBSERVABLE.search(l.get("note", "")):
                v.update(verdict="cannot observe", why=l.get("note", ""), evidence={"screenshot": l.get("screenshot")})
            else:
                v.update(verdict="not met", why=l.get("note", ""), evidence={"screenshot": l.get("screenshot")})
        elif r is not None and not r.get("error"):
            if p["route"] == "code" and r.get("verdict") == "full":
                v.update(verdict="met", evidence={"by": p["by"], "tests": [t["ref"] for t in p["tests"]],
                                                  "reason": r.get("reason", "")})
            elif p["route"] == "code" and r.get("verdict") == "partial":
                v.update(verdict="member check", why=r.get("missing") or r.get("reason", ""),
                         evidence={"by": p["by"], "tests": [t["ref"] for t in p["tests"]],
                                   "reason": r.get("reason", "")})
            elif p["route"] == "context" and r.get("verdict") == "context":
                v.update(verdict="met", evidence={"context": p["reason"], "critic": r.get("reason", "")})
            else:
                v.update(verdict="unresolved", why="escalated to a live check that has not run")
        else:
            v.update(verdict="unresolved", why=(r or {}).get("error") or "not checked yet")
        out[uid] = v
    return out


def needs_live(plan: dict[str, dict], reads: dict[str, dict], full: bool = False) -> list[str]:
    """Units the browser grader checks: no test covers them, or (with full) a read was partial."""
    ids = []
    for uid, p in plan.items():
        r = reads.get(uid) or {}
        if p["route"] == "live":
            ids.append(uid)
        elif p["route"] == "code" and r.get("verdict") == "partial" and full:
            ids.append(uid)
        elif p["route"] == "context" and r.get("verdict") == "obligation":
            ids.append(uid)
    return ids


def summary(verdicts: dict[str, dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for v in verdicts.values():
        counts[v["verdict"]] += 1
    return dict(counts)


def path(b) -> Path:
    return b.golden_dir / "spec-review.json"
