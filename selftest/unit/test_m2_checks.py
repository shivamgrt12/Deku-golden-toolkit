import json

import checks
import cli
import receipts as R
import state as S
from bundle import Bundle
from stages import Context, split_findings, t0_triage


def _workflows(root, text):
    (root / "tests" / "workflows.yaml").write_text(text)


def test_unparseable_workflows_is_a_bundle_defect(reference):
    _workflows(reference, "- id: w\n  substeps:\n    - kind: pytest\n      cov: C-CF-01 (earned: why)\n")
    b = Bundle.load(reference)
    assert b.workflows_error
    assert any(f["check"] == "workflows-unparseable" for f in checks.triage(b))


def test_unpassable_browser_substep_is_flagged(reference):
    _workflows(reference, "- id: w\n  substeps:\n    - kind: browser\n"
                          "      do: Open the invoice in a new tab and verify the total\n")
    found = [f for f in checks.triage(Bundle.load(reference)) if f["check"] == "unpassable-substep"]
    assert found and "second tab or window" in found[0]["text"]


def test_test_route_missing_from_brief(reference):
    tests = reference / "tests" / "test_output.py"
    tests.write_text(tests.read_text() + '\n\ndef test_ghost(client):\n    client.get("/api/ghost-route")\n')
    found = [f for f in checks.triage(Bundle.load(reference)) if f["check"] == "route-not-in-brief"]
    assert any("/api/ghost-route" in f["text"] for f in found)


def test_reference_brief_routes_are_all_known(reference):
    assert not [f for f in checks.triage(Bundle.load(reference)) if f["check"] == "route-not-in-brief"]


def test_waiver_clears_one_blocking_finding(reference):
    toml = reference / "task.toml"
    toml.write_text(toml.read_text().replace('\n[metadata.services]\nbackend = "postgres"\n', "\n"))
    b = Bundle.load(reference)
    ctx = Context(bundle=b, bar={})
    verdict, _, details = t0_triage(ctx)
    assert verdict == R.FAIL
    fid = details["problems"][0].split("]")[0].strip("[")
    assert cli.main(["status", str(reference), "--waive", fid, "--note", "harness copy declares it"]) == 0
    assert S.load(b)["waivers"][fid]["note"] == "harness copy declares it"
    assert t0_triage(ctx)[0] == R.PASS


def test_leak_lint_catches_a_hardcoded_expected_value(reference):
    tests = reference / "tests" / "test_output.py"
    tests.write_text(tests.read_text() + '\n\ndef test_secret_value(client):\n'
                     '    assert client.get("/api/works").json()["motto"] == "Zebra Quantum Fog 77"\n')
    app = reference / "solution" / "app" / "app.py"
    app.write_text(app.read_text() + '\nMOTTO = "Zebra Quantum Fog 77"\n')
    found = checks.leak_lint(Bundle.load(reference))
    assert any("Zebra Quantum Fog 77" in f["text"] for f in found)


def test_reference_app_has_no_leak_or_scope_finding(reference):
    b = Bundle.load(reference)
    assert checks.leak_lint(b) == [] and checks.scope_lint(b) == []


def test_scope_lint_flags_an_unasked_analytics_dependency(reference):
    req = reference / "solution" / "app" / "requirements.txt"
    req.write_text(req.read_text() + "posthog==3.0.0\n")
    found = checks.scope_lint(Bundle.load(reference))
    assert any("posthog" in f["text"] and "analytics" in f["text"] for f in found)


def test_walkthrough_coverage(reference):
    _workflows(reference, "- id: guest_rsvps\n  substeps:\n"
                          "    - kind: browser\n      do: Open the event\n"
                          "    - kind: browser\n      do: Press attend\n")
    b = Bundle.load(reference)
    uncovered, _ = checks.walkthrough_coverage(b)
    assert uncovered == ["guest_rsvps #1", "guest_rsvps #2"]
    wt = checks.walkthrough_dir(b)
    wt.mkdir(parents=True)
    (wt / "test_rsvp.py").write_text('import pytest\n\n@pytest.mark.substep("guest_rsvps", 1)\n'
                                     'def test_a(page): ...\n\n@pytest.mark.substep("guest_rsvps", 3)\n'
                                     'def test_b(page): ...\n')
    uncovered, stray = checks.walkthrough_coverage(b)
    assert uncovered == ["guest_rsvps #2"] and stray == ["guest_rsvps #3"]


def test_endpoints_from_the_reference_brief(reference):
    eps = checks.endpoints(Bundle.load(reference))
    assert {"method": "GET", "path": "/api/talents/{slug}"} in eps
    assert all(e["path"].startswith("/api/") for e in eps)


def test_leak_lint_accepts_a_keyword_the_brief_spells_out():
    from checks import spelled_out
    brief = "`JetBrains Mono` with tabular numerals for every figure; a line through cancelled runs."
    assert spelled_out("tabular-nums", brief)
    assert spelled_out("line-through", brief)
    assert not spelled_out("weekly-mileage-cap", brief)     # a test-only value stays a leak
    assert not spelled_out("tabular", brief)                # not a hyphenated keyword
