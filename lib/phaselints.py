"""Exit checks for the authoring phases P0 and P1 (PLAN.md, sources.md, DESIGN.md).

These are the cheap mechanical floors under documents a critic and the member
then read. They prove completeness, not quality: every checklist id has a
home, no conflict is left open, every design value is concrete.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ID = re.compile(r"\bC-[A-Z]{2}-\d+\b")
RANGE = re.compile(r"\b(C-[A-Z]{2})-(\d+)\s*\.\.\s*(?:C-[A-Z]{2}-)?(\d+)\b")
ITEM = re.compile(r"^-\s*\[[ xX]\]\s*`(C-[A-Z]{2}-\d+)`", re.M)
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
TODO = re.compile(r"\bTODO\b|\bTBD\b")
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def leftover_placeholder(text: str, template: str) -> str | None:
    """A `<...>` placeholder copied from the template and never replaced, or a TODO.

    Only the template's own placeholders count, so real markup mentioned in a
    design document (`<button>`) is never mistaken for one.
    """
    tpl = (TEMPLATES / template).read_text()
    for placeholder in sorted(set(re.findall(r"<[^<>\n]+>", tpl))):
        if placeholder in text:
            return placeholder
    m = TODO.search(text)
    return m.group(0) if m else None


def plan_path(b) -> Path:
    return b.golden_dir / "PLAN.md"


def design_path(b) -> Path:
    return b.root / "solution" / "DESIGN.md"


def checklist_ids(b) -> list[str]:
    path = b.root / "solution" / "checklist.md"
    return ITEM.findall(path.read_text()) if path.is_file() else []


def _section(text: str, title: str) -> str:
    m = re.search(rf"^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else ""


def _mapped_ids(coverage: str) -> set[str]:
    out = set()
    for line in coverage.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[1] or set(cells[1]) <= set("-: "):
            continue  # a row with nothing in "Satisfied by" maps nothing
        for prefix, lo, hi in RANGE.findall(cells[0]):
            out.update(f"{prefix}-{n:0{len(lo)}d}" for n in range(int(lo), int(hi) + 1))
        out.update(ID.findall(cells[0]))
    return out


def plan_lint(b) -> list[str]:
    path = plan_path(b)
    if not path.is_file():
        return [f"{path.relative_to(b.root)} does not exist -- start from golden/templates/PLAN.md"]
    text, problems = path.read_text(), []
    ids = checklist_ids(b)
    if not ids:
        problems.append("solution/checklist.md has no parseable items -- a bundle defect (P-1)")
    mapped = _mapped_ids(_section(text, "Coverage"))
    missing = [i for i in ids if i not in mapped]
    if missing:
        problems.append(f"{len(missing)} of {len(ids)} checklist ids have no row in ## Coverage: "
                        f"{', '.join(missing[:12])}{' ...' if len(missing) > 12 else ''}")
    stray = sorted(mapped - set(ids))
    if stray:
        problems.append(f"## Coverage names ids the checklist does not have: {', '.join(stray[:8])}")
    for title in ("Domain model", "Routes", "Literals ledger"):
        body = _section(text, title)
        rows = [l for l in body.splitlines() if l.strip().startswith("|") and not set(l) <= set("|-: ")]
        if len(rows) < 2:  # the header row alone
            problems.append(f"## {title} is empty")
    left = leftover_placeholder(text, "PLAN.md")
    if left:
        problems.append(f"PLAN.md still carries a placeholder: {left!r}")
    problems += brief_coverage_lint(b)
    # Only list items are questions; the template's explanatory sentence is not one.
    open_items = [l for l in _section(text, "Open questions").splitlines()
                  if re.match(r"^\s*[-*]\s+\S", l) and not re.match(r"^\s*[-*]\s+none\.?\s*$", l, re.I)]
    if open_items:
        problems.append(f"## Open questions has {len(open_items)} unanswered question(s) -- "
                        f"ask the member before P2")
    return problems


UNIT_RANGE = re.compile(r"\bB-(\d{3})\s*\.\.\s*(?:B-)?(\d{3})\b")
UNIT_ID = re.compile(r"\bB-(\d{3})\b")
GOLDEN_TEST_REF = re.compile(r"(golden_tests/[\w./-]+\.py)::(test_\w+)")


def brief_coverage(b) -> dict[str, dict]:
    """PLAN.md ## Brief coverage as {unit id: {"mapping", "kind", "ids", "test", "earned"}}."""
    path = plan_path(b)
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    for line in _section(path.read_text(), "Brief coverage").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not UNIT_ID.search(cells[0]):
            continue
        mapping = cells[1]
        unit_ids = set()
        for lo, hi in UNIT_RANGE.findall(cells[0]):
            unit_ids.update(f"B-{n:03d}" for n in range(int(lo), int(hi) + 1))
        unit_ids.update(f"B-{n}" for n in UNIT_ID.findall(UNIT_RANGE.sub("", cells[0])))
        low = mapping.lower()
        kind = ("context" if low.startswith("context") else
                "gap" if low.startswith("not in checklist") else "checklist")
        ids = set(ID.findall(mapping))
        for prefix, lo, hi in RANGE.findall(mapping):
            ids.update(f"{prefix}-{n:0{len(lo)}d}" for n in range(int(lo), int(hi) + 1))
        test = GOLDEN_TEST_REF.search(mapping)
        for uid in unit_ids:
            out[uid] = {"mapping": mapping, "kind": kind, "ids": ids,
                        "test": f"{test.group(1)}::{test.group(2)}" if test else None,
                        "earned": "earned:" in low}
    return out


def brief_coverage_lint(b) -> list[str]:
    """Every requirement unit of instruction.md is accounted for -- the brief, not the
    checklist, is what the golden app must fulfil 100%."""
    import brief_units as BU  # noqa: PLC0415
    found = BU.units(b)
    if not found:
        return []
    cov, items = brief_coverage(b), BU.checklist(b)
    problems = []
    missing = [u.id for u in found if u.id not in cov]
    if missing:
        problems.append(f"{len(missing)} of {len(found)} brief units have no row in ## Brief coverage "
                        f"(see _handoff/golden/brief-units.md): {', '.join(missing[:12])}"
                        f"{' ...' if len(missing) > 12 else ''}")
    known = {u.id for u in found}
    stray = sorted(set(cov) - known)
    if stray:
        problems.append(f"## Brief coverage names units the brief does not have: {', '.join(stray[:8])}")
    by_id = {u.id: u for u in found}
    for uid, row in sorted(cov.items()):
        if uid not in by_id:
            continue
        if row["kind"] == "checklist":
            unknown = sorted(row["ids"] - set(items))
            if not row["ids"]:
                problems.append(f"{uid}: mapping {row['mapping'][:60]!r} is neither checklist ids, "
                                f"`not in checklist: <golden test>` nor `context: <why>`")
            elif unknown:
                problems.append(f"{uid}: maps to checklist ids that do not exist: {', '.join(unknown[:5])}")
            elif not row["earned"]:
                text = " ".join(items[i][0] for i in row["ids"] if i in items)
                if not (BU.words(by_id[uid].text) & BU.words(text)):
                    problems.append(f"{uid}: shares no wording with {', '.join(sorted(row['ids'])[:4])} -- "
                                    f"map it to the items that state it, or add `(earned: <why>)`")
        elif row["kind"] == "gap" and not row["test"]:
            problems.append(f"{uid}: `not in checklist` must name the golden test that proves it, "
                            f"as golden_tests/brief/<file>.py::test_<name>")
        elif row["kind"] == "context" and len(row["mapping"].split(":", 1)[-1].strip()) < 8:
            problems.append(f"{uid}: `context:` needs the reason this unit states no obligation")
    return problems


def brief_gap_tests(b) -> dict[str, list[str]]:
    """{golden test ref: [unit ids]} for every `not in checklist` unit."""
    out: dict[str, list[str]] = {}
    for uid, row in brief_coverage(b).items():
        if row["kind"] == "gap" and row["test"]:
            out.setdefault(row["test"], []).append(uid)
    return out


def sources_lint(b) -> list[str]:
    inputs = b.golden_dir / "inputs"
    if not inputs.is_dir() or not any(inputs.iterdir()):
        return []  # no PRD or site supplied: nothing to reconcile
    path = b.golden_dir / "sources.md"
    if not path.is_file():
        return ["inputs/ holds a PRD or site but _handoff/golden/sources.md does not exist "
                "-- run prompts/source-reconcile.md"]
    text, problems = path.read_text(), []
    conflicts = _section(text, "Conflicts")
    for line in conflicts.splitlines():
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0] and not set(cells[0]) <= set("-: ") and cells[0] != "conflict":
            if cells[-1] != "routed":
                problems.append(f"conflict not routed to the bundle author: {cells[0][:80]}")
    for line in _section(text, "Decisions").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] and cells[0].lower() != "decision" and not set(cells[0]) <= set("-: "):
            if cells[2].lower() != "silent":
                problems.append(f"decision {cells[0][:60]!r} is not on a subject the brief is silent "
                                f"about (brief says: {cells[2][:60]!r}) -- the brief wins")
    return problems


# ------------------------------------------------------------ brief carriage
# The H2 sections of a brief that carry its visual design. Their H3 children
# ("### Type", "### Motion", ...) are included with them.
UI_HEADING = re.compile(r"^##\s+(?:UI\s*/\s*UX notes|UI/UX|Front-?end specification|Design|Visual design|Brand)\b.*$",
                        re.M | re.I)
PX = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)px\b")
MS = re.compile(r"(?<![\w.])(\d+)\s?ms\b")
SECONDS = re.compile(r"(?<![\w.])(\d*\.\d+|\d+)s\b")
EASING = re.compile(r"cubic-bezier\(\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+\s*\)")


def _ms(seconds: str) -> str:
    value = float(seconds) * 1000
    return f"{int(value)}ms" if value == int(value) else f"{value:g}ms"
FONT = re.compile(r'"([A-Z][A-Za-z0-9]*(?: [A-Z][A-Za-z0-9]*)*)"')
GENERIC_FONTS = {"Times New Roman", "Helvetica Neue", "Helvetica", "Arial", "Times", "Georgia",
                 "Courier New", "Menlo", "Consolas", "Segoe UI", "Roboto", "Inter", "System UI"}


def brief_ui_text(b) -> str:
    path = b.root / "instruction.md"
    if not path.is_file():
        return ""
    text, out = path.read_text(), []
    for m in UI_HEADING.finditer(text):
        nxt = re.search(r"^##\s", text[m.end():], re.M)
        out.append(text[m.start(): m.end() + (nxt.start() if nxt else len(text))])
    return "\n".join(out)


def design_values(text: str) -> dict[str, set[str]]:
    """Every concrete design value in a text, normalised so `200 ms` == `200ms`."""
    return {
        "colour": {h.lower() for h in HEX.findall(text)},
        "px": {f"{v}px" for v in PX.findall(text)},
        "ms": {f"{v}ms" for v in MS.findall(text)} | {_ms(v) for v in SECONDS.findall(text)},
        "easing": {re.sub(r"\s+", "", e).replace("(0.", "(.").replace(",0.", ",.")
                   for e in EASING.findall(text)},
        "font": {f for f in FONT.findall(text) if f not in GENERIC_FONTS},
    }


def _tables(text: str):
    """Yield (section title, header cells, row cells) for every markdown table row."""
    section, header = "", None
    for line in text.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            section, header = h.group(1), None
            continue
        if not line.strip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        yield section, header, cells


def design_source_lint(b, text: str) -> list[str]:
    """Every token row names its source; a `brief:` row carries only brief values."""
    problems, brief = [], design_values(brief_ui_text(b))
    exempt = {"Judged criteria mapping", "Brief values not carried"}
    for section, header, cells in _tables(text):
        if section in exempt or "source" not in header:
            continue
        idx = header.index("source")
        if idx >= len(cells) or not any(c for i, c in enumerate(cells) if i != idx):
            continue  # an untouched template row is caught as a placeholder elsewhere
        source, label = cells[idx], cells[0] or "(row)"
        if not re.match(r"^(brief|decided)\s*:\s*\S", source, re.I):
            problems.append(f"## {section} '{label}': Source must be `brief: <section>` or "
                            f"`decided: <why>` (got {source or 'nothing'!r})")
            continue
        if source.lower().startswith("brief"):
            row = design_values(" ".join(c for i, c in enumerate(cells) if i != idx))
            for kind in ("colour", "px", "ms", "easing"):
                foreign = row[kind] - brief[kind]
                if foreign:
                    problems.append(f"## {section} '{label}' is marked brief but carries "
                                    f"{', '.join(sorted(foreign))}, which the brief does not "
                                    f"contain -- mark it decided, with why")
    return problems


def design_carriage_lint(b, text: str) -> list[str]:
    """Every design value the brief names is carried, or accounted for in writing."""
    brief = design_values(brief_ui_text(b))
    accounted = design_values(_section(text, "Brief values not carried"))
    body = text.replace(_section(text, "Brief values not carried"), "")
    carried = design_values(body)
    problems = []
    for kind in ("colour", "font", "ms", "easing", "px"):
        missing = sorted(brief[kind] - carried[kind] - accounted[kind])
        if missing:
            problems.append(f"{len(missing)} {kind} value(s) from the brief's UI sections are neither "
                            f"in the design nor listed under ## Brief values not carried: "
                            f"{', '.join(missing[:12])}{' ...' if len(missing) > 12 else ''}")
    forbidden = re.findall(r"^\|\s*`?(#[0-9a-fA-F]{3,6})`?\s*\|\s*([^|]*forbid[^|]*)\|", text, re.M | re.I)
    for value, _ in forbidden:
        if value.lower() in carried["colour"]:
            problems.append(f"{value} is listed as forbidden by the brief yet appears in the design")
    return problems


def design_overrides(b) -> dict:
    """The ```golden-overrides``` block of DESIGN.md: relaxations of G6 defaults."""
    path = design_path(b)
    if not path.is_file():
        return {}
    m = re.search(r"```golden-overrides\s*\n(.*?)```", path.read_text(), re.S)
    try:
        return (yaml.safe_load(m.group(1)) or {}) if m else {}
    except yaml.YAMLError:
        return {}


def design_lint(b) -> list[str]:
    path = design_path(b)
    if not path.is_file():
        return ["solution/DESIGN.md does not exist -- start from golden/templates/DESIGN.md"]
    text, problems = path.read_text(), []
    want = str(b.metadata.get("design_direction") or "").strip()
    m = re.search(r"^design_direction:\s*(\S+)", text, re.M)
    if want and (not m or m.group(1) != want):
        problems.append(f"DESIGN.md must state `design_direction: {want}` (task.toml's drawn direction)")
    for title in ("Palette", "Typography", "Motion", "Focus", "Breakpoints", "Judged criteria mapping"):
        if not _section(text, title).strip():
            problems.append(f"## {title} is missing or empty")
    if len(set(h.lower() for h in HEX.findall(_section(text, "Palette")))) < 4:
        problems.append("## Palette names fewer than four hex values")
    if not re.search(r"\b\d{2,4}\s*ms\b", _section(text, "Motion")):
        problems.append("## Motion names no duration in ms")
    if "reduce" not in _section(text, "Motion").lower():
        problems.append("## Motion does not say what prefers-reduced-motion does")
    if not re.search(r"\d+\s*px", _section(text, "Focus")):
        problems.append("## Focus gives no ring width / offset in px")
    left = leftover_placeholder(text, "DESIGN.md")
    if left:
        problems.append(f"DESIGN.md still carries a placeholder: {left!r}")
    problems += design_source_lint(b, text)
    problems += design_carriage_lint(b, text)
    judge = b.root / "tests" / "judge.toml"
    if judge.is_file():
        import tomllib  # noqa: PLC0415
        visual = [c.get("id") for c in tomllib.loads(judge.read_text()).get("criterion") or []
                  if (c.get("annotations") or {}).get("dimension") in
                  ("ui_visual", "motion", "accessibility", "responsiveness")]
        mapping = _section(text, "Judged criteria mapping")
        unmapped = [cid for cid in visual if not re.search(rf"\b{re.escape(str(cid))}\b", mapping)]
        if unmapped:
            problems.append(f"## Judged criteria mapping leaves out visual criteria: {', '.join(unmapped)}")
    return problems
