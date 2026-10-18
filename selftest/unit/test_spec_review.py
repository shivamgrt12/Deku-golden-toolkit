import brief_units as BU
import cli
import member_review as MR
import phaselints as L
import receipts as R
import spec_review as SRV
from bundle import Bundle
from test_phases import _plan, brief_rows

GAP_TEST = '''import httpx


def test_footer_names_the_house(base_url):
    r = httpx.get(base_url + "/")
    assert r.status_code == 200
    assert "Cirrus" in r.text
'''


def _bundle_with_plan(reference, edit=None):
    b = Bundle.load(reference)
    rows = brief_rows(b).splitlines()
    if edit:
        rows = edit(rows)
    _plan(b, lambda ids: "\n".join(f"| {i} | here |" for i in ids), brief="\n".join(rows))
    return b


def _gap_and_context(rows):
    rows[0] = "| B-001 | not in checklist: golden_tests/brief/test_house.py::test_footer_names_the_house |"
    rows[1] = "| B-002 | context: explains why the house exists; asks the app for nothing |"
    return rows


def test_units_are_routed_by_how_strongly_they_are_proven(reference):
    b = _bundle_with_plan(reference, _gap_and_context)
    plan = SRV.classify(b)
    assert plan["B-001"]["route"] == "live" and "checklist gap" in plan["B-001"]["why"]
    assert plan["B-002"]["route"] == "context"
    code = [p for p in plan.values() if p["route"] == "code"]
    assert code and all(p["by"] == "pytest" and p["tests"] for p in code)
    assert all("def test_" in t["source"] for p in code for t in p["tests"])


def test_unmapped_units_are_routed_unmapped(reference):
    b = _bundle_with_plan(reference, lambda rows: rows[1:])
    assert SRV.classify(b)["B-001"]["route"] == "unmapped"


def test_obligations_escalate_to_live_and_partial_reads_only_with_full_live(reference):
    b = _bundle_with_plan(reference, _gap_and_context)
    plan = SRV.classify(b)
    code_unit = next(u for u, p in plan.items() if p["route"] == "code")
    reads = {code_unit: {"verdict": "partial", "missing": "nothing stored"},
             "B-002": {"verdict": "obligation", "reason": "names the house"}}
    live = SRV.needs_live(plan, reads)
    assert {"B-001", "B-002"} <= set(live) and code_unit not in live
    assert code_unit in SRV.needs_live(plan, reads, full=True)


def test_verdicts_are_assembled_from_reads_and_live_checks(reference):
    b = _bundle_with_plan(reference, _gap_and_context)
    plan = SRV.classify(b)
    code_units = [u for u, p in plan.items() if p["route"] == "code"][:3]
    reads = {code_units[0]: {"verdict": "full", "reason": "asserts all of it"},
             code_units[1]: {"verdict": "partial", "missing": "the stored row"},
             "B-002": {"verdict": "obligation", "reason": "names the house"}}
    live = {"B-001": {"passed": True, "note": "footer reads Cirrus"},
            code_units[1]: {"passed": False, "note": "the row is not stored"},
            "B-002": {"passed": False, "note": "this cannot be observed through the browser"},
            code_units[2]: {"passed": False, "error": "grader_unavailable"}}
    v = SRV.assemble(plan, reads, live)
    assert v["B-001"]["verdict"] == "met"
    assert v[code_units[0]]["verdict"] == "met" and v[code_units[0]]["evidence"]["by"] == "pytest"
    assert v[code_units[1]]["verdict"] == "not met" and v[code_units[1]]["code_read"]["verdict"] == "partial"
    assert v["B-002"]["verdict"] == "cannot observe" and v["B-002"]["mislabelled_context"]
    assert v[code_units[2]]["verdict"] == "unresolved"


def test_live_checks_become_harness_workflows(reference):
    b = _bundle_with_plan(reference, _gap_and_context)
    plan = SRV.classify(b)
    ids = [u for u in plan][:20]
    flows = SRV.live_workflows(plan, ids)
    assert all(len(f["substeps"]) <= SRV.LIVE_BATCH for f in flows)
    assert len({f["id"] for f in flows}) == len(flows)
    step = flows[0]["substeps"][0]
    assert step["kind"] == "browser" and plan[step["unit"]]["text"] in step["do"]
    assert not step["do"].startswith("Verify")   # the grader treats "Verify" as look-only


def test_member_review_lists_gaps_with_their_assertions_and_keeps_decisions(reference):
    b = _bundle_with_plan(reference, _gap_and_context)
    test = reference / "solution" / "golden_tests" / "brief" / "test_house.py"
    test.parent.mkdir(parents=True)
    test.write_text(GAP_TEST)
    text = MR.write(b).read_text()
    assert "Proven by: `golden_tests/brief/test_house.py::test_footer_names_the_house`" in text
    assert '`assert "Cirrus" in r.text`' in text
    assert "Builder's reason: explains why the house exists" in text
    undecided = next(p for p in MR.lint(b) if "not decided" in p)
    assert "B-001" in undecided and "B-002" in undecided
    path = MR.path(b)
    path.write_text(path.read_text().replace("- [ ] B-001", "- [x] B-001").replace(
        "- [ ] B-002", "- [ ] B-002").replace(
        "Builder's reason: explains why the house exists; asks the app for nothing",
        "Builder's reason: explains why the house exists; asks the app for nothing\n"
        "      REJECT: it names the house, which the footer must show"))
    MR.write(b)                                          # regenerate: decisions survive
    problems = MR.lint(b)
    assert "- [x] B-001" in path.read_text()
    assert any("member rejected B-002" in p and "reopen P0" in p for p in problems)


def test_g9_is_optional_in_the_default_chain():
    class A:
        only = None; from_ = None; official = False; with_g9 = False
    ids = [s.id for s in cli.select(A())]
    assert "G9" not in ids and "SR" in ids and ids.index("SR") == ids.index("G8") + 1
    A.with_g9 = True
    assert "G9" in [s.id for s in cli.select(A())]
    A.with_g9, A.from_ = False, "G9"
    assert [s.id for s in cli.select(A())][0] == "G9"


def test_p6_needs_g10_not_g9(reference):
    import phases
    assert phases.EXITS["P6"][1] == ["G10"]
    assert "SR" in phases.EXITS["P5"][1]


def test_report_does_not_count_an_unrun_optional_g9(reference):
    b = Bundle.load(reference)
    for sid in ("T0", "G0"):
        R.append(b, sid, R.PASS, "ok")
    cli.main(["gauntlet", str(reference), "--only", "G11"])
    report = (b.golden_dir / "report.md").read_text()
    assert "| G9 local harness graders | optional, not run |" in report
    assert "G9" not in R.latest(R.read(b))["G11"]["summary"]


def test_unobservable_wording_is_cannot_observe_not_a_failure():
    for note in ("It cannot be verified through the running app.",
                 "This is a meta-statement in the product brief about scope, not an observable UI behavior.",
                 "The requirement is not about the running app's behaviour.",
                 "There is no way to observe the repository history from a browser."):
        assert SRV.UNOBSERVABLE.search(note), note
    for note in ("The footer link is styled like plain text.", "The page returned 500."):
        assert not SRV.UNOBSERVABLE.search(note), note


def test_running_out_of_steps_is_inconclusive_not_a_failure(reference):
    b = _bundle_with_plan(reference, _gap_and_context)
    plan = SRV.classify(b)
    v = SRV.assemble(plan, {}, {"B-001": {"passed": False, "error": "grader_step_cap",
                                          "note": "step cap hit (80 steps used) without reaching a verdict"}})
    assert v["B-001"]["verdict"] == "unresolved" and "inconclusive" in v["B-001"]["why"]


def test_critic_labels_are_matched_tolerantly():
    import importlib.util, sys, types
    sys.modules.setdefault("run_workflows", types.SimpleNamespace(DEFAULT_GRADER_MODEL="m", make_llm=None))
    spec = importlib.util.spec_from_file_location(
        "spec_read", str(SRV.Path(__file__).resolve().parents[2] / "runner" / "probes" / "spec_read.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    units = [{"id": "B-011"}, {"id": "B-012"}]
    got = mod.keyed([{"unit": "B-011 ", "verdict": "full"}, {"unit": "unit B-012", "verdict": "partial"}], units)
    assert got["B-011"]["verdict"] == "full" and got["B-012"]["verdict"] == "partial"
    assert mod.keyed([{"unit": "the requirement", "verdict": "full"}], [{"id": "B-011"}])["B-011"]["verdict"] == "full"


def test_grader_map_reads_genkits_traceability_matrix(reference):
    import re as _re
    from bundle import Bundle
    import spec_review as SRV
    src = (reference / "tests" / "test_output.py").read_text()
    name = _re.search(r"^def (test_\w+)", src, _re.M).group(1)
    (reference / "tests" / "traceability-matrix.csv").write_text(
        "req_id,req_desc,member_ids,T1,T2,R1,covered\n"
        f",,,pytest:test_output.py::{name},pytest:test_output.py::test_not_there,rubric:R1,\n"
        "A01,one,C-ZZ-01;C-ZZ-02,YES,,,YES\n"
        "A02,two,C-ZZ-03,,YES,YES,YES\n")
    gmap = SRV.grader_map(Bundle.load(reference))
    assert name in gmap["C-ZZ-01"]["pytest"] and name in gmap["C-ZZ-02"]["pytest"]
    assert not gmap["C-ZZ-03"]["pytest"]            # a column naming no real test maps nothing
    assert gmap["C-ZZ-03"]["judge"]


def test_critic_sees_the_helpers_a_test_uses_and_the_most_relevant_tests():
    import spec_review as SRV
    defs = {"RUN_FIELDS": 'RUN_FIELDS = {"id", "run_date"}', "post_run": "def post_run(c):\n    return api(c)",
            "api": "def api(c):\n    return c", "UNUSED": "UNUSED = 1"}
    src = "def test_x(c):\n    assert set(post_run(c)) == RUN_FIELDS"
    shown = SRV.with_context(src, defs)
    assert "RUN_FIELDS = " in shown and "def post_run" in shown and "def api" in shown   # two levels deep
    assert "UNUSED" not in shown
    tests = {f"tests::test_unrelated_{i}": f"def test_unrelated_{i}(): pass" for i in range(8)}
    tests["tests::test_week_total_sums_runs_dated_monday_to_sunday"] = "def t(): pass"
    picked = SRV.pick_tests("Totals every Monday-to-Sunday week.", tests)
    assert picked[0].endswith("monday_to_sunday") and len(picked) == SRV.MAX_TESTS


def test_partial_reads_go_to_the_member_unless_full_live():
    import spec_review as SRV
    plan = {"B-001": {"unit": "B-001", "section": "S", "text": "t", "route": "code", "by": "pytest",
                      "tests": [{"ref": "tests::test_a", "source": ""}]},
            "B-002": {"unit": "B-002", "section": "S", "text": "u", "route": "live"}}
    reads = {"B-001": {"verdict": "partial", "missing": "no assertion on highlights"}}
    assert SRV.needs_live(plan, reads) == ["B-002"]
    assert SRV.needs_live(plan, reads, full=True) == ["B-001", "B-002"]
    v = SRV.assemble(plan, reads, {"B-002": {"passed": True, "note": "ok"}})
    assert v["B-001"]["verdict"] == "member check" and "highlights" in v["B-001"]["why"]
    assert v["B-002"]["verdict"] == "met"
