import re

import cli
import phaselints as L
import receipts as R
import state as S
from bundle import Bundle


def _status(capsys, root, *extra):
    assert cli.main(["status", str(root), *extra]) == 0
    return capsys.readouterr().out


def test_phase_flow_is_driven_by_receipts_and_approvals(reference, capsys):
    b = Bundle.load(reference)
    assert f"--only T0" in _status(capsys, reference)
    R.append(b, "T0", R.PASS, "bundle sound")
    assert "--advance" in _status(capsys, reference)
    out = _status(capsys, reference, "--advance")
    assert "advanced to P0" in out and "P0-intake.md" in out
    assert "PLAN.md still carries a placeholder" in out  # init seeded the template

    st = S.load(b)
    S.advance(b, st, "P6")
    R.append(b, "G9", R.PASS, "every channel at its ceiling")
    out = _status(capsys, reference)
    assert "STOP" not in out and "--only G10 --official" in out    # no member gate before G10


def test_init_seeds_templates_and_a_prd(reference, tmp_path):
    prd = tmp_path / "companion.md"
    prd.write_text("# PRD\n")
    assert cli.main(["init", str(reference), "--prd", str(prd)]) == 0
    b = Bundle.load(reference)
    assert (b.golden_dir / "PLAN.md").is_file()
    assert (reference / "solution" / "DESIGN.md").is_file()
    assert (b.golden_dir / "inputs" / "prd.md").read_text() == "# PRD\n"
    assert (b.golden_dir / "sources.md").is_file()


def brief_rows(b):
    """Map every brief unit the way an agent would: to its suggested item, else context."""
    import brief_units as BU
    items, rows = BU.checklist(b), []
    for u in BU.units(b):
        s = BU.suggest(u, items)
        rows.append(f"| {u.id} | {s[0]} |" if s else f"| {u.id} | context: explains the design, states no obligation |")
    return "\n".join(rows)


def _plan(b, coverage_rows, brief=None):
    ids = L.checklist_ids(b)
    body = (f"# PLAN\n\n## Domain model\n\n| Entity | x |\n|---|---|\n| item | y |\n\n"
            f"## Routes\n\n| Route | x |\n|---|---|\n| / | page |\n\n"
            f"## Coverage\n\n| Checklist ids | Satisfied by |\n|---|---|\n{coverage_rows(ids)}\n\n"
            f"## Brief coverage\n\n| Brief units | Fulfilled by |\n|---|---|\n{brief if brief is not None else brief_rows(b)}\n\n"
            f"## Literals ledger\n\n| Literal | x |\n|---|---|\n| producer@example.com | seed |\n\n"
            f"## Open questions\n\n- none\n")
    (b.golden_dir).mkdir(parents=True, exist_ok=True)
    L.plan_path(b).write_text(body)
    return ids


def test_plan_lint_accepts_ranges_and_reports_gaps(reference):
    b = Bundle.load(reference)

    def by_section(ids):
        rows, groups = [], {}
        for i in ids:
            groups.setdefault(i[:4], []).append(int(i[5:]))
        for prefix, nums in groups.items():
            rows.append(f"| {prefix}-{min(nums):02d}..{max(nums):02d} | the {prefix} surface |")
        return "\n".join(rows)

    ids = _plan(b, by_section)
    assert len(ids) == 770
    assert L.plan_lint(b) == []
    _plan(b, lambda ids: by_section(ids).replace(by_section(ids).splitlines()[0] + "\n", "", 1))
    assert any("checklist ids have no row" in p for p in L.plan_lint(b))


def test_design_lint_requires_a_concrete_contract(reference):
    b = Bundle.load(reference)
    path = L.design_path(b)
    path.write_text((cli.GOLDEN / "templates" / "DESIGN.md").read_text())
    problems = " | ".join(L.design_lint(b))
    assert "design_direction: editorial-serif" in problems
    assert "placeholder" in problems
    assert "Judged criteria mapping leaves out visual criteria" in problems


def test_design_overrides_relax_g6_with_a_reason(reference):
    b = Bundle.load(reference)
    L.design_path(b).write_text("# DESIGN\n\n```golden-overrides\nmax_font_weights: 4  # display face\n```\n")
    assert L.design_overrides(b) == {"max_font_weights": 4}


def test_g11_report_renders_from_receipts(reference):
    b = Bundle.load(reference)
    S.init(b)
    R.append(b, "T0", R.PASS, "bundle sound")
    assert cli.main(["gauntlet", str(reference), "--only", "G11"]) == 2
    report = (b.golden_dir / "report.md").read_text()
    assert "| T0 bundle triage | PASS | bundle sound |" in report
    assert re.search(r"\| G3 pytest suite \| not run \|", report)
    assert "Taste on sight is not measured" in report



def test_brief_coverage_fails_every_unaccounted_unit(reference):
    b = Bundle.load(reference)
    _plan(b, lambda ids: "\n".join(f"| {i} | here |" for i in ids), brief="")
    problems = " | ".join(L.plan_lint(b))
    assert "of 486 brief units have no row in ## Brief coverage" in problems


def test_brief_coverage_mapping_rules(reference):
    b = Bundle.load(reference)
    rows = brief_rows(b).splitlines()
    rows[0] = "| B-001 | C-ZZ-99 |"                                   # unknown id
    rows[1] = "| B-002 | not in checklist: a test somewhere |"       # gap without a test ref
    rows[2] = "| B-003 | context: ok |"                              # context without a reason
    _plan(b, lambda ids: "\n".join(f"| {i} | here |" for i in ids), brief="\n".join(rows))
    problems = " | ".join(L.plan_lint(b))
    assert "B-001: maps to checklist ids that do not exist: C-ZZ-99" in problems
    assert "B-002: `not in checklist` must name the golden test" in problems
    assert "B-003: `context:` needs the reason" in problems


def test_a_mapping_with_no_shared_wording_needs_earned(reference):
    import brief_units as BU
    b = Bundle.load(reference)
    unit = BU.units(b)[0]
    items = BU.checklist(b)
    far = next(i for i, (t, _) in items.items() if not (BU.words(unit.text) & BU.words(t)))
    rows = brief_rows(b).splitlines()
    rows[0] = f"| {unit.id} | {far} |"
    _plan(b, lambda ids: "\n".join(f"| {i} | here |" for i in ids), brief="\n".join(rows))
    assert any(f"{unit.id}: shares no wording" in p for p in L.plan_lint(b))
    rows[0] = f"| {unit.id} | {far} (earned: the item restates this unit in other words) |"
    _plan(b, lambda ids: "\n".join(f"| {i} | here |" for i in ids), brief="\n".join(rows))
    assert not any(f"{unit.id}:" in p for p in L.plan_lint(b))


def test_g4_requires_the_golden_test_of_every_checklist_gap(reference):
    from stages import Context, g4_walkthrough
    b = Bundle.load(reference)
    rows = brief_rows(b).splitlines()
    rows[0] = "| B-001 | not in checklist: golden_tests/brief/test_overview.py::test_house_is_named |"
    _plan(b, lambda ids: "\n".join(f"| {i} | here |" for i in ids), brief="\n".join(rows))
    verdict, _, details = g4_walkthrough(Context(bundle=b, bar={}))
    assert verdict == R.FAIL
    assert "B-001: `not in checklist` names golden_tests/brief/test_overview.py::test_house_is_named, which does not exist" in details["problems"]
