"""Entry point behind golden/bin/*. One command per job, absolute paths only."""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import receipts as R  # noqa: E402
import state as S  # noqa: E402
from bundle import Bundle  # noqa: E402
from paths import GOLDEN  # noqa: E402
import phases  # noqa: E402
from stages import BY_ID, STAGES, Context, needs_docker_problem  # noqa: E402
from stack import StackError  # noqa: E402

BAR = "=" * 64


def _bundle(path: str) -> Bundle:
    return Bundle.load(Path(path).expanduser())


# ------------------------------------------------------------------ init
def seed_templates(b: Bundle) -> list[str]:
    """Copy PLAN.md / DESIGN.md templates into place if absent. Never overwrites.

    Also (re)writes _handoff/golden/brief-units.md, the numbered requirement units
    of instruction.md that PLAN.md ## Brief coverage must account for.
    """
    import brief_units  # noqa: PLC0415
    seeded = []
    if (b.root / "instruction.md").is_file():
        brief_units.write(b)
    for template, dest in (("PLAN.md", b.golden_dir / "PLAN.md"),
                           ("DESIGN.md", b.root / "solution" / "DESIGN.md")):
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(GOLDEN / "templates" / template, dest)
            seeded.append(str(dest.relative_to(b.root)))
    return seeded


def cmd_init(args) -> int:
    b = _bundle(args.bundle)
    st = S.init(b)
    seeded = seed_templates(b)
    inputs = b.golden_dir / "inputs"
    if getattr(args, "prd", None):
        inputs.mkdir(parents=True, exist_ok=True)
        src = Path(args.prd).expanduser().resolve()
        shutil.copy2(src, inputs / f"prd{src.suffix or '.md'}")
        seeded.append(f"_handoff/golden/inputs/prd{src.suffix or '.md'}")
    if getattr(args, "site", None):
        import capture  # noqa: PLC0415
        rc = capture.capture_site(args.site, inputs / "site")
        if rc != 0:
            print(f"golden: site capture failed (exit {rc}); see {inputs / 'site' / 'capture.log'}")
            return 2
        seeded.append("_handoff/golden/inputs/site/")
    if (inputs.is_dir() and any(inputs.iterdir())) and not (b.golden_dir / "sources.md").exists():
        shutil.copy2(GOLDEN / "templates" / "sources.md", b.golden_dir / "sources.md")
        seeded.append("_handoff/golden/sources.md")
    print(f"golden: initialised {b.golden_dir}")
    print(f"  bundle : {b.name}")
    print(f"  phase  : {st['phase']}")
    for item in seeded:
        print(f"  seeded : {item}")
    print(f"next: golden/bin/golden-status {b.root}")
    return 0


# ------------------------------------------------------------------ status
def stage_rows(b: Bundle) -> list[dict]:
    latest = R.latest(R.read(b))
    current = R.input_hashes(b)
    rows = []
    for stage in STAGES:
        row = latest.get(stage.id)
        if row is None:
            status = "optional" if stage.optional else "not run"
        elif R.is_stale(row, current, stage.depends_on):
            status = f"STALE ({row['verdict']})"
        else:
            status = row["verdict"]
        rows.append({"id": stage.id, "title": stage.title, "status": status,
                     "summary": (row or {}).get("summary", ""), "paid": stage.paid})
    return rows


def next_action(b: Bundle, st: dict) -> tuple[str, list[str]]:
    """The one next command, and the current phase's open exit problems."""
    if st["status"] == "GOLDEN":
        return "nothing: this bundle is GOLDEN", []
    phase = st["phase"]
    problems = phases.exit_problems(b, st, phase)
    if not problems:
        return f"golden/bin/golden-status {b.root} --advance", []
    _, stage_ids, _ = phases.EXITS[phase]
    latest, current = R.latest(R.read(b)), R.input_hashes(b)
    for sid in stage_ids:
        row = latest.get(sid)
        if row and row["verdict"] == R.PASS and not R.is_stale(row, current, BY_ID[sid].depends_on):
            continue
        if BY_ID[sid].paid:
            return f"golden/bin/gauntlet {b.root} --only {sid} --official", problems
        return f"golden/bin/gauntlet {b.root} --only {sid}", problems
    if problems[-1].startswith("waiting for the member") and len(problems) == 1:
        return f"STOP -- {problems[-1]}", problems
    return f"work through golden/phases/{phase_file(phase)}, then re-run golden-status", problems


def phase_file(phase: str) -> str:
    # P1 also has P1-review.md, the member's checklist; the agent's file is the other one.
    return next(p.name for p in sorted((GOLDEN / "phases").glob(f"{phase}-*.md"))
                if not p.name.endswith("-review.md"))


def cmd_status(args) -> int:
    b = _bundle(args.bundle)
    st = S.init(b)  # idempotent: never resets an existing run
    seed_templates(b)
    if args.approve:
        st = S.approve(b, st, args.approve, args.who or getpass.getuser(), args.note or "")
        print(f"golden: {args.approve} approved by {st['approvals'][args.approve]['by']}")
    if args.waive:
        st = S.waive(b, st, args.waive, args.who or getpass.getuser(), args.note or "")
        print(f"golden: finding {args.waive} waived -- re-run the stage that raised it")
    if args.phase:
        st = S.advance(b, st, args.phase, args.note or "")
    if args.advance:
        moved, problems = phases.advance(b, st)
        st = S.load(b)
        print(f"golden: advanced to {st['phase']}" if moved and not problems else
              f"golden: {st['phase']} exit check is not green yet")
    rows = stage_rows(b)
    print(BAR)
    print(f" golden status  {b.name}")
    print(f" phase {st['phase']}   status {st['status']}   approvals "
          f"{', '.join(sorted(st['approvals'])) or 'none'}")
    print(BAR)
    for row in rows:
        print(f"  {row['id']:4} {row['title']:24} {row['status']:16} {row['summary'][:60]}")
    action, problems = next_action(b, st)
    print(BAR)
    print(f" phase {st['phase']}: golden/phases/{phase_file(st['phase'])}")
    for p in problems[:15]:
        print(f"   - {p}")
    print(f"next: {action}")
    return 0


# ------------------------------------------------------------------ gauntlet
def select(args) -> list:
    ids = [s.id for s in STAGES]
    if args.only:
        wanted = [x.strip().upper() for x in args.only.split(",") if x.strip()]
        unknown = [w for w in wanted if w not in BY_ID]
        if unknown:
            raise SystemExit(f"golden: unknown stage(s) {unknown}; M1 stages: {', '.join(ids)}")
        return [BY_ID[w] for w in ids if w in wanted]
    start = ids.index(args.from_.upper()) if args.from_ else 0
    chosen = STAGES[start:]
    if not args.official:
        chosen = [s for s in chosen if not s.paid]
    # Optional stages (G9) run only when named or asked for: SR and the free
    # stages already prove what G9 would re-check before the official runs.
    return [s for s in chosen if not s.optional or args.with_g9 or (args.from_ or "").upper() == s.id]


def cmd_gauntlet(args) -> int:
    if args.self_test:
        return selftest(args.e2e)
    if not args.bundle:
        raise SystemExit("golden: gauntlet needs a bundle path (or --self-test)")
    b = _bundle(args.bundle)
    S.init(b)
    ctx = Context(bundle=b, official=args.official,
                  resume_rubric=args.resume_rubric or args.resume_spec, full_live=args.full_live)
    all_green = True
    print(BAR)
    print(f" gauntlet  {b.name}")
    print(BAR)
    try:
        for stage in select(args):
            print(f"[{stage.id}] {stage.title} ...", flush=True)
            problem = needs_docker_problem(stage)
            if problem:
                verdict, summary, details = R.BLOCKED, problem, {}
            else:
                try:
                    verdict, summary, details = stage.run(ctx)
                except StackError as exc:
                    verdict, summary, details = R.FAIL, str(exc).splitlines()[0], {"error": str(exc)}
                except Exception as exc:  # a toolkit defect must not end the run unrecorded
                    import traceback  # noqa: PLC0415
                    verdict, summary = R.BLOCKED, f"golden toolkit error in {stage.id}: {exc!r}"
                    details = {"problems": [summary], "traceback": traceback.format_exc()[-2000:]}
            R.append(b, stage.id, verdict, summary, details)
            print(f"[{stage.id}] {verdict}  {summary}")
            for line in (details.get("problems") or details.get("reasons") or [])[:12]:
                print(f"       - {line}")
            if verdict != R.PASS:
                all_green = False
                if not args.keep_going:
                    break
    finally:
        if ctx.stack is not None and not args.keep:
            ctx.stack.cleanup()
    print(BAR)
    print(" ALL SELECTED STAGES GREEN" if all_green else " NOT GREEN -- see the stage above")
    print(f" receipts: {R.path(b)}")
    print(BAR)
    return 0 if all_green else 2


# ------------------------------------------------------------------ noise
def cmd_noise(args) -> int:
    import noise  # noqa: PLC0415
    from stages import llm_credentials_problem  # noqa: PLC0415
    b = _bundle(args.bundle)
    S.init(b)
    if not args.yes:
        print(f"golden: {args.runs} full grading passes spend grader LLM tokens. "
              f"Re-run with --yes to confirm.")
        return 2
    ctx = Context(bundle=b)
    problem = needs_docker_problem(BY_ID["G1"]) or llm_credentials_problem(ctx)
    if problem:
        print(f"golden: BLOCKED -- {problem}")
        return 2
    try:
        ctx.need_stack().build_images(ctx.evidence("noise"))
        root, report = noise.measure(ctx, args.runs)
    except StackError as exc:
        print(f"golden: noise measurement failed -- {exc}")
        return 2
    finally:
        if ctx.stack is not None:
            ctx.stack.cleanup()
    print(noise.render(report))
    print(f"\nwritten: {root}")
    return 0


def cmd_design_preview(args) -> int:
    import design_preview  # noqa: PLC0415
    import phaselints  # noqa: PLC0415
    b = _bundle(args.bundle)
    S.init(b)
    if not phaselints.design_path(b).is_file():
        print("golden: solution/DESIGN.md does not exist yet (P1)")
        return 2
    out, meta, note = design_preview.build(b)
    print(f"golden: design preview written to {out}")
    print(f"  {meta['brief']} value(s) from the brief, {meta['decided']} decided by the agent")
    for role, pair in meta["contrast"].items():
        print(f"  {role:10} on ground {pair['on_ground']}:1   on ink {pair['on_ink']}:1")
    if note:
        print(f"  note: {note}")
    problems = phaselints.design_lint(b) + design_preview.contrast_claims_lint(b)
    if problems:
        print(f"  design lint: {len(problems)} problem(s) -- fix them before asking for approval:")
        for p in problems[:15]:
            print(f"   - {p}")
        return 2
    print("next: ask the member to review it with golden/phases/P1-review.md, then "
          f"golden/bin/golden-status {b.root} --approve P1 --note \"...\"")
    return 0


def cmd_media(args) -> int:
    import media  # noqa: PLC0415
    b = _bundle(args.bundle)
    S.init(b)
    if not media.L.design_path(b).is_file():
        print("golden: solution/DESIGN.md does not exist yet -- write ## Media first (P1)")
        return 2
    if args.choose:
        for p in media.choose(b, args.choose):
            print(f"golden: {p}")
    elif args.vendor:
        problems = media.vendor(b, args.vendor)
        for p in problems:
            print(f"golden: {p}")
        lines = media.credits(b)
        if lines:
            print("credit these CC BY files in the app (a credits line or page):")
            for line in lines:
                print(f"  {line}")
        return 2 if problems else 0
    else:
        print("golden: fetching candidates for every `fetch` row of ## Media ...")
        media.fetch(b, n=args.count, refresh=args.refresh, allow_by=args.allow_cc_by)
    page, note = media.sheet(b)
    print(f"golden: contact sheet {page}" + (f"\n  note: {note}" if note else f"\n  screenshot {b.golden_dir / 'media' / 'sheet.png'}"))
    problems = media.media_plan_lint(b)
    if problems:
        print(f"  media plan: {len(problems)} open item(s):")
        for p in problems[:20]:
            print(f"   - {p}")
        return 2
    print("  media plan complete -- the member reviews the contact sheet with the design preview at P1")
    return 0


# ------------------------------------------------------------------ self-test
def selftest(e2e: bool) -> int:
    """Unit tests always; the Docker calibration only when asked for (--e2e)."""
    suites = [str(GOLDEN / "selftest" / "unit")]
    if e2e:
        suites.append(str(GOLDEN / "selftest" / "e2e"))
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
           "--rootdir", str(GOLDEN / "selftest"), *suites]
    return subprocess.call(cmd, env=dict(os.environ))


def main(argv=None) -> int:
    prog = Path(sys.argv[0]).name
    ap = argparse.ArgumentParser(prog=prog)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create _handoff/golden/ state for a bundle")
    p.add_argument("bundle")
    p.add_argument("--prd", help="a companion PRD / UI-UX document (advisory input, P0)")
    p.add_argument("--site", help="a reference website URL to capture (advisory input, P0/P1)")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("status", help="where this bundle stands, and what to do next")
    p.add_argument("bundle")
    p.add_argument("--approve", choices=sorted(S.HUMAN_GATES), help="record a member approval")
    p.add_argument("--phase", choices=S.PHASE_IDS, help="move to a phase")
    p.add_argument("--waive", metavar="ID", help="accept one finding by id (needs --note)")
    p.add_argument("--advance", action="store_true", help="run the phase's exit check; move on if green")
    p.add_argument("--who")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("gauntlet", help="run the gauntlet stages, cheapest first")
    p.add_argument("bundle", nargs="?")
    p.add_argument("--only", help="comma-separated stage ids, e.g. G3,G9")
    p.add_argument("--from", dest="from_", help="start at this stage")
    p.add_argument("--official", action="store_true",
                   help="include G10: the official deku-run oracle x2 + nop (hours; P6 runs it after SR)")
    p.add_argument("--full-live", action="store_true",
                   help="SR: live-check partial code reads in the browser too (hours on a large brief) "
                        "instead of listing them for the member")
    p.add_argument("--resume-spec", action="store_true",
                   help="SR: keep units already met over these exact bytes; re-check the rest")
    p.add_argument("--with-g9", action="store_true",
                   help="include the optional G9 local graders in a --from / full run")
    p.add_argument("--resume-rubric", action="store_true",
                   help="G9: re-judge only unresolved rubric criteria; SR: re-check only units "
                        "not yet met -- both only over these exact bytes")
    p.add_argument("--keep", action="store_true", help="leave the stack running afterwards")
    p.add_argument("--keep-going", action="store_true", help="do not stop at the first red stage")
    p.add_argument("--self-test", action="store_true", help="test the gauntlet itself")
    p.add_argument("--e2e", action="store_true", help="with --self-test: also run against Docker")
    p.set_defaults(fn=cmd_gauntlet)

    p = sub.add_parser("design-preview", help="render DESIGN.md as a page + screenshots for P1")
    p.add_argument("bundle")
    p.set_defaults(fn=cmd_design_preview)

    p = sub.add_parser("media", help="P1: fetch, choose and contact-sheet the brief's media; P3: --vendor it")
    p.add_argument("bundle")
    p.add_argument("--choose", action="append", metavar="NEED=ID[,ID]", help="pick candidate(s) for a fetch row")
    p.add_argument("--vendor", metavar="DIR", help="P3: copy chosen files into solution/app/DIR, resized to WebP")
    p.add_argument("--refresh", action="store_true", help="fetch candidates again even if the search is unchanged")
    p.add_argument("--count", type=int, default=8, help="candidates per source per row")
    p.add_argument("--allow-cc-by", action="store_true",
                   help="also offer CC BY files (the app must then credit each creator); default CC0 / public domain")
    p.set_defaults(fn=cmd_media)

    p = sub.add_parser("noise", help="run the local graders N times and report flapping verdicts")
    p.add_argument("bundle")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--yes", action="store_true", help="confirm the grader token spend")
    p.set_defaults(fn=cmd_noise)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
