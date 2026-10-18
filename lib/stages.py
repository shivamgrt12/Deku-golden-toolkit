"""The gauntlet stages, cheapest first. M1 ships G0-G3, G9 and G10.

Each stage returns (verdict, summary, details) and never raises for an app
defect: a red check is a result, not an exception. BLOCKED means the stage could
not run (no Docker, no credentials, no --official) and is never a pass.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import appbuild
import checks
import harness
import receipts as R
import state as S
import verdict as V
from paths import bridge_mode, bridge_problem, harness_ready, load_harness_env
from receipts import BLOCKED, FAIL, PASS
from stack import Stack, StackError, docker_problem, read_json

ALL_INPUTS = ("app", "bundle", "harness")
# The harness waits 60s before a grader process's first call, because an official
# trial grades the same second its agent stops burning tokens on the same account.
# Golden's local grader runs (SR, G9) follow no agent phase, so the wait is pure
# delay; throttles are still handled by the harness's retry ladder. G10 is the
# official run and keeps the harness default.
NO_COOLDOWN = {"DEKU_GRADER_COOLDOWN_SEC": "0"}
ASSET_TYPES = {"script", "stylesheet", "image", "font", "media", "manifest", "texttrack"}
LLM_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY",
            "AWS_BEARER_TOKEN_BEDROCK")


@dataclass
class Context:
    bundle: object
    official: bool = False
    resume_rubric: bool = False
    full_live: bool = False      # SR: live-check partial code reads too, instead of the member
    bar: dict = field(default_factory=V.acceptance)
    stack: Stack | None = None
    fresh: bool = False          # stack is up, cold, and nothing has graded it yet
    cache: dict = field(default_factory=dict)

    def evidence(self, stage: str) -> Path:
        path = self.bundle.evidence_dir / stage
        path.mkdir(parents=True, exist_ok=True)
        return path

    def need_stack(self) -> Stack:
        if self.stack is None:
            self.stack = Stack(self.bundle, self.bundle.evidence_dir)
        return self.stack


@dataclass
class Stage:
    id: str
    title: str
    run: object
    depends_on: tuple[str, ...] = ALL_INPUTS
    needs_docker: bool = True
    paid: bool = False
    optional: bool = False   # not in the default chain; run it by name when it saves time


# ---------------------------------------------------------------------- T0
def _waivers(ctx: Context) -> dict:
    try:
        return S.load(ctx.bundle).get("waivers") or {}
    except SystemExit:
        return {}


def split_findings(ctx: Context, found: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """(blocking, advisory, waived) -- a waiver carries a member's written reason."""
    waived_ids = _waivers(ctx)
    blocking = [f for f in found if f["blocking"] and f["id"] not in waived_ids]
    advisory = [f for f in found if not f["blocking"]]
    waived = [dict(f, waiver=waived_ids[f["id"]]) for f in found if f["id"] in waived_ids]
    return blocking, advisory, waived


def _lines(items: list[dict]) -> list[str]:
    return [f"[{f['id']}] {f['text']}" for f in items]


def t0_triage(ctx: Context):
    """Is the bundle itself sound? A perfect app cannot pass a broken bundle.

    Blocking findings route to the BUNDLE AUTHOR, not the app builder. A member
    who disagrees with one waives it by id with a reason, which the receipt keeps.
    """
    import media  # noqa: PLC0415
    blocking, advisory, waived = split_findings(ctx, checks.triage(ctx.bundle))
    details = {"problems": _lines(blocking), "advisory": _lines(advisory), "waived": waived}
    if media.VIDEO_WORDS.search(checks.brief(ctx.bundle)) and not media.ffmpeg():
        details["advisory"].append("the brief mentions video and ffmpeg is not installed here -- needed only if "
                                   "DESIGN.md plans a rendered-video (macOS: brew install ffmpeg)")
    if blocking:
        return FAIL, (f"{len(blocking)} bundle defect(s) -- route to the bundle author, or waive "
                      f"one with golden-status --waive <id> --note"), details
    return PASS, f"bundle sound ({len(advisory)} advisory, {len(waived)} waived)", details


# ---------------------------------------------------------------------- G0
def g0_inputs(ctx: Context):
    b, problems = ctx.bundle, []
    reason = harness_ready()
    if reason:
        problems.append(reason)
    for rel in ("task.toml", "instruction.md", "tests/workflows.yaml",
                "tests/test_output.py", "environment/Dockerfile"):
        if not (b.root / rel).is_file():
            problems.append(f"bundle is missing {rel}")
    if not b.workflows:
        problems.append("tests/workflows.yaml declares no workflows")
    if not b.app_dir.is_dir() or not any(b.app_dir.iterdir()):
        problems.append("solution/app/ is missing or empty -- the golden app has not been built yet")
    else:
        mode = appbuild.deploy_mode(b)
        if mode == "none":
            problems.append("solution/app/ has no run.json (run-manifest-v1) and no Dockerfile")
        elif mode == "run.json":
            problems += appbuild.manifest_problems(b.run_manifest())
        if not any((p).is_file() for p in (b.app_dir / "USER_README.md",
                                           b.root / "solution" / "USER_README.md")):
            problems.append("no USER_README.md (the browser grader reads logins from it)")
    if not b.solve_sh.is_file():
        problems.append("solution/solve.sh is missing")
    else:
        text = b.solve_sh.read_text()
        syntax = subprocess.run(["bash", "-n", str(b.solve_sh)], capture_output=True, text=True)
        if syntax.returncode != 0:
            problems.append(f"solve.sh has a syntax error: {syntax.stderr.strip()[:200]}")
        if "/app" not in text:
            problems.append("solve.sh never deploys into /app -- it is still the NO-SOLUTION stub")
    details = {"workflows": len(b.workflows), "browser_substeps": b.browser_substeps,
               "pytest_substeps": b.pytest_substeps, "deploy_mode": appbuild.deploy_mode(b)}
    if problems:
        return FAIL, f"{len(problems)} input problem(s)", {**details, "problems": problems}
    return PASS, "bundle and golden app inputs present", details


# ---------------------------------------------------------------------- G1
def _scan(text: str, patterns: list[str], allow: list[str]) -> list[str]:
    hits = []
    for line in text.splitlines():
        if any(re.search(p, line) for p in patterns) and not any(re.search(a, line) for a in allow):
            hits.append(line.strip()[:200])
    return hits


def g1_build(ctx: Context):
    ev = ctx.evidence("G1")
    stack = ctx.need_stack()
    try:
        images = stack.build_images(ev)
    except StackError as exc:
        return FAIL, "an image did not build", {"error": str(exc), "logs": str(ev)}
    rules = ctx.bar.get("build", {})
    build_log = (ev / "app-build.log").read_text() if (ev / "app-build.log").is_file() else ""
    warnings = _scan(build_log, rules.get("warning_patterns", []), rules.get("warning_allow_patterns", []))
    details = {"images": images, "warnings": warnings[:40], "logs": str(ev),
               "note": "type-check and lint gates land with the language adapters (M2)"}
    if warnings and rules.get("warnings", "blocking") == "blocking":
        return FAIL, f"app built, but the build log carries {len(warnings)} warning line(s)", details
    return PASS, f"env, app ({images['deploy_mode']}), grader and runner images built", details


# ---------------------------------------------------------------------- G2
def _cold_up(ctx: Context, health_path: str, timeout: float):
    stack = ctx.need_stack()
    if not stack.images:  # `--only G3` / `--only G9` without G1 in the same run
        stack.build_images(ctx.evidence("G1"))
    stack.up()
    ok, code, secs = stack.wait_healthy(health_path, timeout)
    ctx.fresh = ok
    return ok, code, secs


def g2_deploy(ctx: Context):
    rules = ctx.bar.get("deploy", {})
    path, timeout = rules.get("health_path", "/api/health"), float(rules.get("health_timeout_sec", 240))
    ev = ctx.evidence("G2")
    starts, findings = [], []
    try:
        for i in range(1, int(rules.get("cold_starts", 2)) + 1):
            ok, code, secs = _cold_up(ctx, path, timeout)
            logs = ctx.stack.app_logs()
            (ev / f"app-log-start{i}.txt").write_text(logs)
            errors = _scan(logs, rules.get("startup_log_error_patterns", []),
                           rules.get("startup_log_allow_patterns", []))
            starts.append({"start": i, "healthy": ok, "status": code, "seconds": round(secs, 1),
                           "log_error_lines": errors[:20]})
            if errors:
                findings.append(f"cold start {i}: {len(errors)} error line(s) in the startup log")
            if not ok:
                findings.append(f"cold start {i}: {path} never returned 200 (last: {code})")
                break  # a second cold start cannot pass what the first could not reach
    except StackError as exc:
        return FAIL, "the stack did not come up", {"error": str(exc), "starts": starts}
    details = {"starts": starts, "stack": ctx.stack.describe(), "logs": str(ev)}
    if findings:
        return FAIL, "; ".join(findings), details
    return PASS, f"healthy from cold {len(starts)}x, clean startup log", details


# ---------------------------------------------------------------------- G3
def _ensure_fresh(ctx: Context):
    if ctx.fresh:
        return True, ""
    rules = ctx.bar.get("deploy", {})
    ok, code, _ = _cold_up(ctx, rules.get("health_path", "/api/health"),
                           float(rules.get("health_timeout_sec", 240)))
    return ok, code


def g3_pytest(ctx: Context):
    """The bundle's pytest suite, through the harness's own test.sh.

    The browser executor is switched off (test.sh then grades pytest only) and
    the advisory judge is skipped, so this is free of LLM calls -- but the
    pre-browser snapshot, the deploy gate and the CTRF report are the real ones.
    """
    try:
        ok, code = _ensure_fresh(ctx)
    except StackError as exc:
        return FAIL, "the stack did not come up", {"error": str(exc)}
    if not ok:
        return FAIL, f"app not healthy before pytest (last: {code})", {}
    stack, ev = ctx.stack, ctx.evidence("G3")
    stack.exec_runner(["chmod", "-x", "/tests/run_workflows.py"])
    stack.exec_runner(["bash", "/tests/test.sh"], env={"DEKU_SKIP_RUBRIC": "1"},
                      timeout=3600, log_to=ev / "test.sh.log")
    stack.exec_runner(["chmod", "+x", "/tests/run_workflows.py"])
    ctx.fresh = False
    shutil.rmtree(ev / "verifier", ignore_errors=True)
    stack.copy_out("/logs/verifier", ev / "verifier")
    ctrf = read_json(ev / "verifier" / "ctrf.json")
    if not ctrf:
        return FAIL, "pytest wrote no CTRF report (collection failed)", {"log": str(ev / "test.sh.log")}
    summary = (ctrf.get("results") or {}).get("summary") or {}
    tests = ctrf.get("results", {}).get("tests") or []
    failed = [{"name": t.get("name"), "message": (t.get("message") or t.get("trace") or "")[:400]}
              for t in tests if t.get("status") in ("failed", "error")]
    allowed = set(ctx.bar.get("pytest", {}).get("allow_skipped") or [])
    skipped = [t.get("name") for t in tests if t.get("status") == "skipped"
               and t.get("name", "").split("::")[-1] not in allowed]
    details = {"tests": summary.get("tests"), "passed": summary.get("passed"),
               "failed": failed, "skipped": skipped, "evidence": str(ev / "verifier")}
    n = int(summary.get("tests") or 0)
    if n < int(ctx.bar.get("pytest", {}).get("min_tests", 1)):
        return FAIL, "pytest collected no tests", details
    if failed or skipped:
        return FAIL, f"pytest {summary.get('passed')}/{n} passed, {len(failed)} failed, " \
                     f"{len(skipped)} skipped", details
    return PASS, f"pytest {n}/{n} passed, 0 skipped", details


# ---------------------------------------------------------------------- G4
def _fresh_or_fail(ctx: Context):
    try:
        ok, code = _ensure_fresh(ctx)
    except StackError as exc:
        return f"the stack did not come up: {exc}"
    return None if ok else f"app not healthy (last: {code})"


def _ctrf_failures(path: Path) -> tuple[int, list[dict]]:
    doc = read_json(path) or {}
    tests = (doc.get("results") or {}).get("tests") or []
    bad = [{"name": t.get("name"), "status": t.get("status"),
            "message": (t.get("message") or t.get("trace") or "")[:400]}
           for t in tests if t.get("status") != "passed"]
    return len(tests), bad


def _run_suite(ctx: Context, suite: str, stage: str) -> tuple[int, list[dict], Path]:
    stack, ev = ctx.stack, ctx.evidence(stage)
    stack.push_golden_tests()
    out = f"/logs/golden/{stage}/{suite}"
    stack.exec_runner(["mkdir", "-p", out])
    # Rooted at /golden/suite with no ini file: the runner's working directory is
    # /tests, whose pytest.ini would make /tests the rootdir, and pytest never loads
    # a conftest above its rootdir -- the golden fixtures would be "not found".
    stack.exec_runner(["python3", "-m", "pytest", suite, "-q", "-p", "no:cacheprovider",
                       "-c", "/dev/null", "--rootdir", "/golden/suite",
                       "--ctrf", f"{out}/ctrf.json"], env={"GOLDEN_FRAMES_DIR": f"{out}/frames"},
                      timeout=3600, log_to=ev / f"{suite}.log", workdir="/golden/suite")
    dest = ev / "out" / suite
    shutil.rmtree(dest, ignore_errors=True)
    stack.copy_out(out, dest)
    n, bad = _ctrf_failures(dest / "ctrf.json")
    return n, bad, dest


def g4_walkthrough(ctx: Context):
    """Every browser substep, and every requirement the checklist missed, proven by
    a deterministic test of ours.

    walkthrough/  one Playwright test per browser substep of workflows.yaml. The
                  LLM browser grader decides the official verdict; this proves
                  BEFORE a paid run that each substep is achievable, frame by frame.
    brief/        one test per `not in checklist` unit of PLAN.md ## Brief coverage:
                  a requirement of instruction.md no grader checks, which the golden
                  app must still fulfil.
    """
    import phaselints  # noqa: PLC0415
    b, problems = ctx.bundle, []
    gaps = phaselints.brief_gap_tests(b)
    if b.browser_substeps:
        uncovered, stray = checks.walkthrough_coverage(b)
        problems += [f"browser substep with no walkthrough test: {u}" for u in uncovered]
        problems += [f"walkthrough marker points at no substep: {s_}" for s_ in stray]
    for ref, unit_ids in sorted(gaps.items()):
        path, name = ref.split("::")
        source = b.root / "solution" / path
        if not source.is_file() or not re.search(rf"^def {re.escape(name)}\(", source.read_text(), re.M):
            problems.append(f"{', '.join(unit_ids)}: `not in checklist` names {ref}, which does not exist")
        elif not path.startswith("golden_tests/brief/"):
            problems.append(f"{ref}: brief-gap tests live under golden_tests/brief/")
    if problems:
        return FAIL, f"{len(problems)} missing golden test(s)", {
            "problems": problems,
            "how": "walkthrough/test_*.py with @pytest.mark.substep(id, n); brief/test_*.py for checklist gaps"}
    if not b.browser_substeps and not gaps:
        return PASS, "no browser substeps and no checklist gaps -- nothing to walk", {}
    problem = _fresh_or_fail(ctx)
    if problem:
        return FAIL, problem, {}
    details, summary = {"problems": []}, []
    for suite, wanted in (("walkthrough", b.browser_substeps), ("brief", bool(gaps))):
        if not wanted:
            continue
        n, bad, dest = _run_suite(ctx, suite, "G4")
        ctx.fresh = False
        details[f"{suite}_tests"] = n
        details["problems"] += [f"{suite}: {f['name']}: {f['message'][:200]}" for f in bad]
        if suite == "walkthrough":
            details["frames"] = str(dest / "frames")
        if not n:
            details["problems"].append(f"the {suite} suite collected no tests")
        summary.append(f"{n} {suite} test(s)")
    details["checklist_gaps"] = {ref: ids for ref, ids in gaps.items()}
    if details["problems"]:
        return FAIL, f"{len(details['problems'])} golden test failure(s)", details
    return PASS, (f"{', '.join(summary)} green -- every browser substep walked, "
                  f"{sum(len(v) for v in gaps.values())} checklist-gap unit(s) proven"), details


# ---------------------------------------------------------------------- G5 / G6
def _pages(ctx: Context) -> dict | None:
    """One crawl + audit at every viewport, shared by G5 and G6 in one run."""
    if "pages" in ctx.cache:
        return ctx.cache["pages"]
    rules = ctx.bar.get("inspect", {})
    # The crawl starts at / and follows same-origin links. Signed-in pages are
    # reached through solution/golden_tests/audit.py (SESSIONS + ROUTES), which is
    # pushed into the runner first so the probe can sign in.
    routes = ["/"] + list(rules.get("extra_routes") or [])
    ctx.stack.push_golden_tests()
    cfg = {"base_url": f"http://main:{ctx.bundle.port}", "routes": routes,
           "max_pages": int(rules.get("max_pages", 25)), "viewports": rules.get("viewports") or
           {"reflow-320": [320, 640], "phone-390": [390, 844], "tablet-834": [834, 1112],
            "desktop-1440": [1440, 900]},
           "out_dir": "/logs/golden/pages"}
    ev = ctx.evidence("G5")
    ctx.stack.run_probe("pages", cfg, log_to=ev / "pages.log")
    shutil.rmtree(ev / "pages", ignore_errors=True)
    ctx.stack.copy_out("/logs/golden/pages", ev / "pages")
    ctx.cache["pages"] = read_json(ev / "pages" / "pages.json")
    return ctx.cache["pages"]


def g5_inspect(ctx: Context):
    """Open devtools on every page at every viewport: nothing should be there."""
    problem = _fresh_or_fail(ctx)
    if problem:
        return FAIL, problem, {}
    pages = _pages(ctx)
    if not pages or not pages.get("pages"):
        return FAIL, "the page probe produced no results (see G5/pages.log)", {}
    rules, out = ctx.bar.get("inspect", {}), []
    block = set(rules.get("axe_block_impacts") or ["critical", "serious", "moderate", "minor"])
    sessions = pages.get("sessions") or {}
    out += list(pages.get("session_errors") or [])
    # Three signals that the app has a sign-in: the crawl met a password field or a
    # sign-in route, the task declares an auth slot, or the brief itself says so
    # (a studio login the public pages never link to is still a signed-in surface).
    brief_says = re.search(r"\b(sign[- ]?in|log[- ]?in|password|bearer token|signed[- ]in)\b",
                           checks.brief(ctx.bundle), re.I)
    needs_auth = (pages.get("auth_detected") or bool(brief_says)
                  or bool((ctx.bundle.metadata.get("services") or {}).get("auth")))
    if needs_auth and not sessions:
        out.append("the app has a sign-in, but solution/golden_tests/audit.py declares no SESSIONS -- "
                   "every signed-in page goes unaudited (see golden/phases/P3-frontend.md)")
    origin = f"http://main:{ctx.bundle.port}"
    for p in pages["pages"]:
        where = f"{p['path']} @{p['viewport']}" + (f" [signed in: {p['session']}]" if p.get("session") else "")
        if p.get("probe_error"):
            out.append(f"{where}: page could not be audited: {p['probe_error']}")
            continue
        if p.get("status") and p["status"] >= 400:
            out.append(f"{where}: the page itself answered HTTP {p['status']}")
        for kind, key, limit in (("console error", "error", "console_errors"),
                                 ("console warning", "warning", "console_warnings")):
            msgs = [c["text"] for c in p.get("console") or [] if c["type"] == key]
            if len(msgs) > int(rules.get(limit, 0)):
                out.append(f"{where}: {len(msgs)} {kind}(s): {msgs[0][:140]}")
        if p.get("page_errors"):
            out.append(f"{where}: uncaught exception: {p['page_errors'][0][:140]}")
        failed = [r["url"] for r in p.get("failed_requests") or []]
        if failed:
            out.append(f"{where}: {len(failed)} failed request(s): {failed[0][:120]}")
        # 5xx anywhere, or 4xx on an asset (a missing file), is a defect. A 4xx API
        # call is the app's own refusal; the page's own status is judged just above.
        bad = [f"{r['status']} {r.get('type', '?')} {r['url']}" for r in p.get("bad_responses") or []
               if r["url"].startswith(origin) and (r["status"] >= 500 or (
                   r.get("type") in ASSET_TYPES))]
        if bad:
            out.append(f"{where}: {len(bad)} failing same-origin request(s): {bad[0][:120]}")
        allowed = [re.compile(a) for a in rules.get("external_origin_allow") or []]
        external = [u for u in p.get("external_requests") or [] if not any(a.search(u) for a in allowed)]
        if external:
            out.append(f"{where}: {len(external)} request(s) to another origin (hotlinked; vendor it): "
                       f"{external[0][:120]}")
        if (p.get("overflow_px") or 0) > float(rules.get("max_overflow_px", 1)):
            out.append(f"{where}: scrolls sideways by {p['overflow_px']}px")
        if (p.get("cls") or 0) > float(rules.get("max_cls", 0.1)):
            out.append(f"{where}: cumulative layout shift {p['cls']}")
        for v in p.get("axe") or []:
            if v.get("impact") in block:
                out.append(f"{where}: axe {v['id']} ({v['impact']}): {v['help'][:90]} -- {', '.join(v['nodes'][:2])}")
    import media  # noqa: PLC0415
    out += media.problems(pages["pages"], rules.get("media") or {})
    signed_in = sum(len(v) for v in sessions.values())
    summary = (f"{len(pages['routes'])} public + {signed_in} signed-in route(s) x "
               f"{len({p['viewport'] for p in pages['pages']})} viewport(s)")
    details = {"routes": pages["routes"], "problems": out[:60], "problem_count": len(out),
               "screens": str(ctx.evidence("G5") / "pages" / "screens")}
    if out:
        return FAIL, f"{len(out)} devtools finding(s) across {summary}", details
    return PASS, f"devtools clean across {summary}", details


def g6_aesthetic(ctx: Context):
    """The mechanically checkable half of "looks modern", as numbers.

    What a script cannot settle (text over images, taste) is counted and left to
    the visual critic and the member's sign-off -- never guessed.
    """
    problem = _fresh_or_fail(ctx)
    if problem:
        return FAIL, problem, {}
    pages = _pages(ctx)
    if not pages or not pages.get("pages"):
        return FAIL, "the page probe produced no results (see G5/pages.log)", {}
    # DESIGN.md may relax a default with a stated reason (```golden-overrides```).
    import phaselints  # noqa: PLC0415
    rules = {**ctx.bar.get("aesthetic", {}), **phaselints.design_overrides(ctx.bundle)}
    advisory_keys = set(rules.get("advisory") or [])
    blocking, advisory, unsettled, weights = [], [], 0, set()
    lo, hi = (rules.get("measure_band") or [45, 90])
    # The brief outranks the 12px default: a size its UI sections pin is a design
    # requirement, not a defect (the reference brief mandates 10px and 9.75px).
    pinned = {float(v[:-2]) for v in phaselints.design_values(phaselints.brief_ui_text(ctx.bundle))["px"]}
    for p in pages["pages"]:
        st, where = p.get("style") or {}, f"{p['path']} @{p['viewport']}" + (
            f" [signed in: {p['session']}]" if p.get("session") else "")
        if not st:
            continue
        weights.update(st.get("font_weights") or [])
        unsettled += int(st.get("contrast_unsettled") or 0)
        unpinned = {s: n for s, n in (st.get("small_sizes") or {}).items() if float(s) not in pinned}
        checks_here = [
            ("min_font_px", bool(unpinned),
             f"{where}: {sum(unpinned.values())} text node(s) under {rules.get('min_font_px', 12)}px at "
             f"size(s) the brief does not pin ({', '.join(f'{s}px' for s in sorted(unpinned, key=float))})"),
            ("max_low_contrast", st.get("low_contrast_count", 0) > int(rules.get("max_low_contrast", 0)),
             f"{where}: {st.get('low_contrast_count')} text node(s) below WCAG AA contrast, "
             f"e.g. {(st.get('low_contrast') or [{}])[0]}"),
            ("max_transition_all", st.get("transition_all_count", 0) > int(rules.get("max_transition_all", 0)),
             f"{where}: `transition: all` in {', '.join(st.get('transition_all', [])[:3])}"),
            ("measure_band", st.get("measure_median") is not None and not lo <= st["measure_median"] <= hi,
             f"{where}: running prose measures ~{st.get('measure_median')} characters per line "
             f"(band {lo}-{hi})"),
        ]
        for key, failed, text in checks_here:
            if failed:
                (advisory if key in advisory_keys else blocking).append(text)
    limit = int(rules.get("max_font_weights", 3))
    if len(weights) > limit:
        text = f"{len(weights)} distinct font weights across the app ({sorted(weights)}; limit {limit})"
        (advisory if "max_font_weights" in advisory_keys else blocking).append(text)
    details = {"problems": sorted(set(blocking))[:60], "advisory": sorted(set(advisory))[:40],
               "font_weights": sorted(weights), "contrast_unsettled_nodes": unsettled,
               "note": "unsettled nodes (text over images or gradients) go to the visual critic"}
    if blocking:
        return FAIL, f"{len(set(blocking))} measurable design finding(s)", details
    return PASS, (f"measurable design checks clean ({len(set(advisory))} advisory, "
                  f"{unsettled} contrast node(s) left to the visual critic)"), details


# ---------------------------------------------------------------------- G7
def g7_abuse(ctx: Context):
    """No errors under abuse: hostile input never crashes, task-specific edges hold."""
    b, rules = ctx.bundle, ctx.bar.get("abuse", {})
    suite = b.root / "solution" / "golden_tests" / "abuse"
    has_suite = suite.is_dir() and any(suite.glob("test_*.py"))
    if rules.get("require_task_suite", True) and not has_suite:
        return FAIL, ("no task-specific abuse suite: write solution/golden_tests/abuse/test_*.py "
                      "(races, replays, cross-role and cross-tenant calls, invalid input, money)"), {}
    problem = _fresh_or_fail(ctx)
    if problem:
        return FAIL, problem, {}
    stack, ev = ctx.stack, ctx.evidence("G7")
    log_before = len(stack.app_logs())
    cfg = {"base_url": f"http://main:{b.port}", "endpoints": checks.endpoints(b), "out_dir": "/logs/golden/abuse"}
    stack.run_probe("abuse", cfg, log_to=ev / "abuse.log")
    shutil.rmtree(ev / "generic", ignore_errors=True)
    stack.copy_out("/logs/golden/abuse", ev / "generic")
    report = read_json(ev / "generic" / "abuse.json") or {}
    problems = [f"{r['method']} {r['url'].split(str(b.port), 1)[-1]} [{r['case']}] -> "
                f"{r.get('status') or r.get('error')}" for r in report.get("crashes") or []]
    public = [re.compile(p) for p in rules.get("unauthenticated_write_allow") or []]
    advisory = [f"{r['method']} {r['url'].split(str(b.port), 1)[-1]} [{r['case']}] accepted {r['status']} "
                f"with no credentials" for r in report.get("unauthenticated_writes_accepted") or []
                if not any(p.search(r["url"]) for p in public)]
    n = 0
    if has_suite:
        n, bad, _ = _run_suite(ctx, "abuse", "G7")
        problems += [f"{f['name']}: {f['message'][:200]}" for f in bad]
    ctx.fresh = False
    tail = stack.app_logs()[log_before:]
    rules_dep = ctx.bar.get("deploy", {})
    log_errors = _scan(tail, rules_dep.get("startup_log_error_patterns", []),
                       rules_dep.get("startup_log_allow_patterns", []))
    (ev / "app-log-during-abuse.txt").write_text(tail)
    if log_errors:
        problems.append(f"{len(log_errors)} error line(s) in the server log under abuse: {log_errors[0][:160]}")
    details = {"generic_calls": report.get("calls"), "task_suite_tests": n,
               "problems": problems[:60], "advisory": sorted(set(advisory))[:30]}
    if problems:
        return FAIL, f"{len(problems)} abuse finding(s)", details
    return PASS, (f"{report.get('calls', 0)} hostile call(s) and {n} task-specific test(s): "
                  f"no crash, clean log ({len(set(advisory))} advisory)"), details


# ---------------------------------------------------------------------- G8
GOLDEN_RESULT = re.compile(r"^GOLDEN-RESULT (\S+) (\d+)", re.M)


def g8_code(ctx: Context):
    """Code quality the rubric's source criteria grade, measured first."""
    b, ev = ctx.bundle, ctx.evidence("G8")
    stack = ctx.need_stack()
    if not stack.images:
        try:
            stack.build_images(ctx.evidence("G1"))
        except StackError as exc:
            return FAIL, "an image did not build", {"error": str(exc)}
    langs = []
    if any(p for p in b.app_dir.rglob("package.json") if "node_modules" not in p.parts):
        langs.append("node")
    if any(b.app_dir.rglob("requirements*.txt")) or (b.app_dir / "pyproject.toml").is_file():
        langs.append("python")
    problems = []
    if not langs:
        problems.append("no language adapter matches this app (no package.json, requirements.txt or "
                        "pyproject.toml) -- add one under golden/runner/adapters/")
    for lang in langs:
        proc = stack.run_adapter(lang, log_to=ev / f"{lang}.log")
        output = proc.stdout + proc.stderr
        results = GOLDEN_RESULT.findall(output)
        if not results:
            problems.append(f"{lang} adapter produced no results (see G8/{lang}.log)")
        for tool, code in results:
            if code != "0":
                problems.append(f"{lang}/{tool} reported findings (exit {code}; see G8/{lang}.log)")
    import media  # noqa: PLC0415
    leaks = checks.leak_lint(b, ctx.bar.get("code", {}).get("leak_allow"))
    scope = checks.scope_lint(b)
    blocking, advisory, waived = split_findings(ctx, leaks + scope + media.placeholder_lint(b))
    problems += _lines(blocking)
    problems += media.assets_lint(b)
    details = {"languages": langs, "problems": problems, "advisory": _lines(advisory), "waived": waived,
               "dependencies": checks.dependencies(b), "logs": str(ev)}
    if problems:
        return FAIL, f"{len(problems)} code finding(s)", details
    return PASS, (f"{'/'.join(langs)} adapters clean; no test-only literal, no unasked dependency, "
                  "every media file licensed"), details


# ---------------------------------------------------------------------- SR
def _prior_spec_review(ctx: Context) -> dict:
    """Settled verdicts from the last SR over these exact bytes, for --resume-spec."""
    import spec_review as SRV  # noqa: PLC0415
    doc = read_json(SRV.path(ctx.bundle)) or {}
    current = R.input_hashes(ctx.bundle)
    if any(doc.get("inputs", {}).get(k) != current.get(k) for k in ("app", "bundle", "golden")):
        return {}
    settled = ("met", "cannot observe") + (() if ctx.full_live else ("member check",))
    return {uid: v for uid, v in (doc.get("units") or {}).items() if v.get("verdict") in settled}


def sr_spec_review(ctx: Context):
    """Every requirement unit of instruction.md, checked by a critic that is not the builder."""
    import os  # noqa: PLC0415
    import yaml  # noqa: PLC0415
    import spec_review as SRV  # noqa: PLC0415
    b, ev = ctx.bundle, ctx.evidence("SR")
    plan = SRV.classify(b)
    if not plan:
        return FAIL, "instruction.md yields no requirement units", {}
    carried = _prior_spec_review(ctx) if ctx.resume_rubric else {}
    todo = {uid: p for uid, p in plan.items() if uid not in carried}
    limit = int(os.environ.get("GOLDEN_SR_LIMIT", "0") or 0)   # calibration only: N units per route
    if limit:
        kept, seen = {}, defaultdict(int)
        for uid, p in todo.items():
            if seen[p["route"]] < limit:
                kept[uid], seen[p["route"]] = p, seen[p["route"]] + 1
        todo = kept
    unmapped = [uid for uid, p in todo.items() if p["route"] == "unmapped"]
    if unmapped:
        return FAIL, f"{len(unmapped)} brief unit(s) are not in PLAN.md ## Brief coverage (P0)", \
            {"problems": unmapped[:40]}
    problem = llm_credentials_problem(ctx) or _fresh_or_fail(ctx)
    if problem:
        return BLOCKED if "bridge" in problem or "credential" in problem else FAIL, problem, {}
    stack = ctx.stack
    reads: dict[str, dict] = {}
    jobs = SRV.read_jobs(todo)
    if jobs:
        (ev / "jobs.json").write_text(json.dumps(jobs, indent=2))
        stack.run_cp_in(ev / "jobs.json", "/tmp/sr-jobs.json")
        stack.exec_runner(["mkdir", "-p", "/logs/golden/SR"])
        stack.exec_runner(["rm", "-f", "/logs/golden/SR/reads.json.progress"])
        print(f"      reading {sum(len(j['units']) for j in jobs)} unit(s) in {len(jobs)} batch(es) ...", flush=True)

        def read_tick(elapsed: float) -> None:
            done = (stack.exec_runner(["sh", "-c", "wc -l < /logs/golden/SR/reads.json.progress 2>/dev/null"]).stdout
                    or "0").strip() or "0"
            print(f"      {elapsed / 60:4.0f} min  read {done}/{len(jobs)} batch(es)", flush=True)

        stack.exec_runner_watched(["python3", "/golden/probes/spec_read.py", "/tmp/sr-jobs.json",
                                   "/logs/golden/SR/reads.json"], env=NO_COOLDOWN, timeout=3 * 3600,
                                  log_to=ev / "reads.log", every=120, tick=read_tick)
        stack.copy_out("/logs/golden/SR/reads.json", ev / "reads.json")
        reads = {r["unit"]: r for r in (read_json(ev / "reads.json") or {}).get("results", [])}
    live_ids = SRV.needs_live(todo, reads, full=ctx.full_live)
    live: dict[str, dict] = {}
    if live_ids:
        flows = SRV.live_workflows(todo, live_ids)
        (ev / "spec-walk.yaml").write_text(yaml.safe_dump(flows, sort_keys=False, allow_unicode=True))
        stack.run_cp_in(ev / "spec-walk.yaml", "/tmp/spec-walk.yaml")
        stack.exec_runner(["mkdir", "-p", "/logs/golden/SR/shots"])
        print(f"      live-checking {len(live_ids)} unit(s) in {len(flows)} browser session(s) ...", flush=True)

        def tick(elapsed: float) -> None:
            done = (stack.exec_runner(["sh", "-c", "ls /logs/golden/SR/shots 2>/dev/null | wc -l"]).stdout
                    or "0").strip()
            print(f"      {elapsed / 60:4.0f} min  checked {done}/{len(live_ids)} unit(s) live", flush=True)

        stack.exec_runner_watched(
            ["python3", "/tests/run_workflows.py", "--workflows", "/tmp/spec-walk.yaml",
             "--url", f"http://main:{b.port}", "--out", "/logs/golden/SR/live.json",
             "--screenshot-dir", "/logs/golden/SR/shots", "--max-steps", "200"],
            # A brief sentence is often several checks in one (read, edit, publish,
            # reach the media...), so a live unit gets twice a workflow substep's budget.
            env={"DEKU_SUBSTEP_MAX_STEPS": "160", **NO_COOLDOWN}, timeout=6 * 3600, log_to=ev / "live.log",
            every=120, tick=tick)
        ctx.fresh = False
        shutil.rmtree(ev / "shots", ignore_errors=True)
        stack.copy_out("/logs/golden/SR/live.json", ev / "live.json")
        stack.copy_out("/logs/golden/SR/shots", ev / "shots")
        results = {w.get("id"): w.get("substeps") or [] for w in
                   ((read_json(ev / "live.json") or {}).get("workflows") or [])}
        for flow in flows:
            for i, step in enumerate(flow["substeps"]):
                got = (results.get(flow["id"]) or [])[i:i + 1]
                res = dict(got[0]) if got else {"passed": False, "error": "no result recorded"}
                res["screenshot"] = str(ev / "shots" / f"{flow['id']}__{i + 1}.png")
                live[step["unit"]] = res
    verdicts = SRV.assemble(todo, reads, live)
    verdicts.update(carried)
    doc = {"schema": "golden-spec-review-v1", "inputs": R.input_hashes(b),
           "summary": SRV.summary(verdicts), "units": verdicts, "partial": bool(limit)}
    SRV.path(b).write_text(json.dumps(doc, indent=2) + "\n")
    bad = [v for v in verdicts.values() if v["verdict"] in ("not met", "unresolved")]
    cannot = [v for v in verdicts.values() if v["verdict"] == "cannot observe"]
    member = [v for v in verdicts.values() if v["verdict"] == "member check"]
    mislabelled = [v["unit"] for v in verdicts.values() if v.get("mislabelled_context")]
    details = {"summary": doc["summary"], "report": str(SRV.path(b)),
               "problems": [f"{v['unit']} [{v['verdict']}] {v['text'][:90]} -- {str(v.get('why', ''))[:140]}"
                            for v in bad][:60],
               "advisory": [f"{v['unit']} cannot be observed: {str(v.get('why', ''))[:120]}" for v in cannot][:40]
                           + [f"{v['unit']} member check: {str(v.get('why', ''))[:120]}" for v in member][:60]
                           + [f"{u} was labelled context but states an obligation" for u in mislabelled][:20]}
    if limit:
        details["problems"].insert(0, f"GOLDEN_SR_LIMIT={limit}: a partial calibration run, never a pass")
        return FAIL, f"partial SR run ({len(verdicts)} of {len(plan)} units)", details
    if bad:
        return FAIL, (f"{sum(1 for v in bad if v['verdict'] == 'not met')} unit(s) not met, "
                      f"{sum(1 for v in bad if v['verdict'] == 'unresolved')} unresolved -- "
                      f"of {len(plan)} brief units"), details
    return PASS, (f"all {len(plan)} brief units met or sent to the member ({len(member)} member check, "
                  f"{len(cannot)} cannot be observed, {len(mislabelled)} mislabelled context re-checked live)"), details


# ---------------------------------------------------------------------- G9
def llm_credentials_problem(ctx: Context) -> str | None:
    stack = ctx.need_stack()
    missing = stack.missing_grader_credentials()
    if missing:
        return f"task.toml requires {', '.join(missing)}, which deku-harness/.env does not set"
    if bridge_mode(load_harness_env()):
        return bridge_problem()
    env = stack.grader_env()
    if not any(env.get(k) for k in LLM_KEYS):
        return ("no grader LLM credential: set ANTHROPIC_API_KEY in deku-harness/.env, "
                "or leave DEKU_BRIDGE_ENABLED=1 and run golden/bin/golden-bridge start")
    return None


PRIOR_BUNDLE = "/logs/verifier/prior_evidence_bundle.json"


def criteria_count(b) -> int:
    judge, rubric = b.root / "tests" / "judge.toml", b.root / "tests" / "rubric.json"
    try:
        if judge.is_file():
            import tomllib  # noqa: PLC0415
            return len(tomllib.loads(judge.read_text()).get("criterion") or [])
        if rubric.is_file():
            doc = json.loads(rubric.read_text())
            return len(doc if isinstance(doc, list) else doc.get("criteria") or [])
    except (ValueError, OSError):
        pass
    return 0


def resumable_rubric(ctx: Context) -> Path | None:
    """The newest G9 evidence bundle graded over THESE exact app and bundle bytes.

    run_rubric.py carries a prior run's settled PASS/FAIL verdicts forward and
    re-judges only the holes (unresolved criteria); it never re-rolls a verdict.
    That is only honest when the thing being judged has not changed, so a
    receipt whose app or bundle hash differs from the current tree is never used.
    """
    current = R.input_hashes(ctx.bundle)
    for row in reversed(R.read(ctx.bundle)):
        if row.get("stage") != "G9":
            continue
        if R.is_stale(row, current, ("app", "bundle")):
            continue
        candidate = Path((row.get("details") or {}).get("evidence", "")) / "verifier" / "evidence_bundle.json"
        if candidate.is_file():
            return candidate
    return None


def run_local_graders(ctx: Context, dest: Path, prior: Path | None = None) -> dict:
    """One full harness grading pass on a cold stack; returns verdict.load_run()."""
    ok, code = _ensure_fresh(ctx)
    if not ok:
        raise StackError(f"app not healthy before grading (last: {code})")
    stack = ctx.stack
    env = {}
    if prior is not None:
        stack.run_cp_in(prior, PRIOR_BUNDLE)
        env["DEKU_RUBRIC_RESUME_FROM"] = PRIOR_BUNDLE
    total = criteria_count(ctx.bundle)

    def tick(elapsed: float) -> None:
        # run_rubric.py writes one trace archive per judged criterion.
        proc = stack.exec_runner(["sh", "-c", "ls /logs/verifier/traces 2>/dev/null | wc -l"])
        done = (proc.stdout or "0").strip() or "0"
        print(f"      {elapsed / 60:4.0f} min  judged {done}/{total or '?'} criteria", flush=True)

    stack.exec_runner_watched(["bash", "/tests/test.sh"], env={**env, **NO_COOLDOWN}, timeout=4 * 3600,
                              log_to=dest / "test.sh.log", every=120, tick=tick)
    ctx.fresh = False
    shutil.rmtree(dest / "verifier", ignore_errors=True)
    stack.copy_out("/logs/verifier", dest / "verifier")
    return V.load_run(dest / "verifier")


def g9_local_graders(ctx: Context):
    problem = llm_credentials_problem(ctx)
    if problem:
        return BLOCKED, problem, {}
    prior = None
    if ctx.resume_rubric:
        prior = resumable_rubric(ctx)
        if prior is None:
            return BLOCKED, ("--resume-rubric: no earlier G9 run over these exact app and "
                             "bundle bytes -- run G9 in full"), {}
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = ctx.evidence("G9") / stamp
    try:
        run = run_local_graders(ctx, dest, prior)
    except StackError as exc:
        return FAIL, str(exc), {}
    golden, reasons = V.grade(run, ctx.bundle.browser_substeps, ctx.bar)
    final = run.get("final") or {}
    details = {"combined_score": final.get("combined_score"), "reward": final.get("reward"),
               "reasons": reasons, "evidence": str(dest),
               "resumed_from": str(prior) if prior else None}
    if golden:
        return PASS, "every channel at its ceiling on the local harness graders", details
    return FAIL, f"{len(reasons)} channel finding(s): {reasons[0]}", details


# ---------------------------------------------------------------------- G10
def g10_official(ctx: Context):
    if not ctx.official:
        return BLOCKED, ("the official harness runs take hours, so they run only when asked: "
                         "re-run with --official (P6 does, straight after SR)"), {}
    problem = llm_credentials_problem(ctx)
    if problem:
        return BLOCKED, problem, {}
    if ctx.stack is not None:
        ctx.stack.down()
    ev, bar = ctx.evidence("G10"), ctx.bar.get("official", {})
    runs, findings = [], []
    for i in range(1, int(bar.get("oracle_runs", 2)) + 1):
        code, dirs = harness.deku_run(ctx.bundle.root, "oracle", ev / f"oracle-{i}.log", timeout=6 * 3600)
        graded = [d for d in dirs if (d / "final_score.json").is_file()]
        if not graded:
            findings.append(f"oracle run {i}: no published run with final_score.json (exit {code})")
            runs.append({"agent": "oracle", "run": i, "exit": code, "dir": None})
            continue
        result = V.load_run(graded[-1])
        golden, reasons = V.grade(result, ctx.bundle.browser_substeps, ctx.bar)
        runs.append({"agent": "oracle", "run": i, "exit": code, "dir": str(graded[-1]),
                     "combined_score": (result.get("final") or {}).get("combined_score"),
                     "golden": golden, "reasons": reasons})
        if not golden:
            findings.append(f"oracle run {i}: {reasons[0]}")
    code, dirs = harness.deku_run(ctx.bundle.root, "nop", ev / "nop.log", timeout=2 * 3600)
    graded = [d for d in dirs if (d / "final_score.json").is_file()]
    nop_reward = (V.load_run(graded[-1]).get("final") or {}).get("reward") if graded else None
    runs.append({"agent": "nop", "exit": code, "dir": str(graded[-1]) if graded else None,
                 "reward": nop_reward})
    if nop_reward is None:
        findings.append("nop run produced no final_score.json")
    elif float(nop_reward) != float(bar.get("nop_reward", 0.0)):
        findings.append(f"nop scored {nop_reward} (> 0.0): the task is passable without an app -- P0")
    (ev / "runs.json").write_text(json.dumps(runs, indent=2) + "\n")
    if findings:
        return FAIL, "; ".join(findings), {"runs": runs}
    return PASS, "oracle golden on every official run; nop 0.0", {"runs": runs}


# ---------------------------------------------------------------------- G11
METHOD = {
    "T0": "static read of the bundle (no app run)",
    "G0": "static read of the bundle and solution/",
    "G1": "executed: docker build of env, app (from its own manifest), grader, runner",
    "G2": "executed: cold start x2 from empty volumes, health probed from the runner",
    "G3": "executed: the bundle's pytest suite via the harness test.sh (browser + judge off)",
    "G4": "executed: golden walkthrough (one test per browser substep) + brief-gap tests",
    "G5": "executed: crawl + devtools listeners + axe-core 4.14 at 320/390/834/1440px",
    "G6": "executed: computed-style measurement on sampled text nodes; taste NOT judged",
    "G7": "executed: hostile input on every brief endpoint + agent-written abuse suite",
    "G8": "executed: language linters / dead-code in the app image; static leak + scope lints",
    "G9": "executed: harness test.sh -- LLM browser grader + pytest + LLM judge (advisory)",
    "SR": "executed: harness LLM grader -- code reads of the covering tests, live browser checks of the rest",
    "G10": "executed: deku-run -a oracle x2 and -a nop on the real harness",
}


def g11_report(ctx: Context):
    """Render _handoff/golden/report.md from the receipts. Never hand-written."""
    b = ctx.bundle
    latest, current = R.latest(R.read(b)), R.input_hashes(b)
    st = S.load(b)
    rows, not_green = [], []
    for stage in STAGES:
        if stage.id == "G11":
            continue
        row = latest.get(stage.id)
        if row is None:
            status = "not run"
        elif R.is_stale(row, current, stage.depends_on):
            status = f"STALE ({row['verdict']})"
        else:
            status = row["verdict"]
        if status != PASS and not (stage.optional and row is None):
            not_green.append(stage.id)
        rows.append((stage, "optional, not run" if stage.optional and row is None else status, row or {}))
    lines = [f"# Golden report — {b.name}", "",
             f"- task code: `{b.metadata.get('task_code', '')}`",
             f"- app sha256: `{current['app'][:16]}`  bundle sha256: `{current['bundle'][:16]}`  "
             f"harness: `{current['harness']}`",
             f"- phase {st['phase']}, status **{st['status']}**, approvals: "
             f"{', '.join(f'{k} by {v['by']}' for k, v in st.get('approvals', {}).items()) or 'none'}",
             "", "## Stages", "", "| Stage | Verdict | Summary | Method |", "|---|---|---|---|"]
    for stage, status, row in rows:
        lines.append(f"| {stage.id} {stage.title} | {status} | {row.get('summary', '')} | {METHOD.get(stage.id, '')} |")
    for stage, status, row in rows:
        details = row.get("details") or {}
        items = (details.get("problems") or []) + [f"(advisory) {a}" for a in details.get("advisory") or []]
        if items:
            lines += ["", f"### {stage.id} findings", ""] + [f"- {i}" for i in items[:40]]
    g9 = (latest.get("G9") or {}).get("details") or {}
    if g9:
        lines += ["", "## Local graders (G9)", "", f"- combined_score: {g9.get('combined_score')}",
                  f"- evidence: `{g9.get('evidence')}`"]
    import brief_units  # noqa: PLC0415
    import phaselints  # noqa: PLC0415
    cov, all_units = phaselints.brief_coverage(b), brief_units.units(b)
    if all_units:
        kinds = {k: [u.id for u in all_units if cov.get(u.id, {}).get("kind") == k]
                 for k in ("checklist", "gap", "context")}
        unmapped = [u.id for u in all_units if u.id not in cov]
        lines += ["", "## instruction.md coverage", "",
                  f"- {len(all_units)} requirement units in the brief",
                  f"- {len(kinds['checklist'])} fulfilled through the checklist and its graders",
                  f"- {len(kinds['gap'])} **checklist gaps**, each proven by a golden test of ours",
                  f"- {len(kinds['context'])} marked context (no obligation) -- the member reads these",
                  f"- {len(unmapped)} unaccounted for"]
        gaps = phaselints.brief_gap_tests(b)
        if gaps:
            lines += ["", "Checklist gaps -- report these to the bundle author:", ""]
            by = {u.id: u for u in all_units}
            for ref, ids in sorted(gaps.items()):
                for uid in ids:
                    lines.append(f"- {uid} ({by[uid].section}): {by[uid].text[:140]} -> `{ref}`")
        if kinds["context"]:
            lines += ["", "Units marked context:", ""] + [
                f"- {uid}: {cov[uid]['mapping'][:120]}" for uid in kinds["context"][:60]]
    waivers = st.get("waivers") or {}
    if waivers:
        lines += ["", "## Waivers", ""] + [f"- `{fid}` by {w['by']}: {w['note']}" for fid, w in waivers.items()]
    lines += ["", "## Evidence for the human read", "",
              f"- screenshots, every route at four widths: `{b.evidence_dir / 'G5' / 'pages' / 'screens'}`",
              f"- walkthrough frames: `{b.evidence_dir / 'G4' / 'out' / 'walkthrough' / 'frames'}`",
              "", "Taste on sight is not measured by any stage above. It is the member's sign-off (P7)."]
    import member_review  # noqa: PLC0415
    review = member_review.write(b)
    decided = member_review.lint(b)
    lines += ["", "## Member review", "",
              f"`{review}` lists every checklist gap, context label and unobservable unit for a human "
              f"decision. " + ("All decided." if not decided else "Open: " + "; ".join(decided[:3]))]
    spec = read_json(b.golden_dir / "spec-review.json") or {}
    if spec:
        lines += ["", "## Spec review (SR)", "", f"- verdicts: {spec.get('summary')}",
                  f"- every unit with its evidence: `{b.golden_dir / 'spec-review.json'}`"]
    path = b.golden_dir / "report.md"
    path.write_text("\n".join(lines) + "\n")
    if not_green:
        return FAIL, f"report written; not golden yet: {', '.join(not_green)}", {"report": str(path)}
    return PASS, "every stage current and green; report written for the member's sign-off", {"report": str(path)}


STAGES = [
    Stage("T0", "bundle triage", t0_triage, depends_on=("bundle",), needs_docker=False),
    Stage("G0", "inputs present", g0_inputs, needs_docker=False),
    Stage("G1", "images build clean", g1_build),
    Stage("G2", "deploys cold, twice", g2_deploy),
    Stage("G3", "pytest suite", g3_pytest),
    Stage("G4", "walkthrough + brief gaps", g4_walkthrough, depends_on=ALL_INPUTS + ("golden",)),
    Stage("G5", "devtools inspect", g5_inspect),
    Stage("G6", "measurable design", g6_aesthetic),
    Stage("G7", "backend abuse", g7_abuse, depends_on=ALL_INPUTS + ("golden",)),
    Stage("G8", "code audit", g8_code),
    Stage("SR", "spec review (every brief unit)", sr_spec_review, depends_on=ALL_INPUTS + ("golden",)),
    Stage("G9", "local harness graders", g9_local_graders, optional=True),
    Stage("G10", "official harness runs", g10_official, needs_docker=False, paid=True),
    Stage("G11", "evidence report", g11_report, needs_docker=False),
]
BY_ID = {s.id: s for s in STAGES}
PLANNED: dict[str, str] = {}


def needs_docker_problem(stage: Stage) -> str | None:
    return docker_problem() if stage.needs_docker else None
