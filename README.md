# golden — build and prove the golden app for a task bundle

A genkit bundle leaves the kit `MECHANICALLY-GREEN, NO-SOLUTION`. `golden/` turns it into a
bundle with a **proven** golden app: the reference solution the client measures every agent
against. It must pass every grader, deploy clean, hide nothing broken, look like a shipped
product and refuse abuse cleanly.

"Proven" is the point. A stage is green only when a script says so and writes a receipt bound to
the exact bytes of the app (`_handoff/golden/receipts.jsonl`). Change the app and the receipt goes
STALE. An agent saying "it works" moves nothing.

## Install

The toolkit lives **inside** a `deku-task-kit` checkout as `golden/`, beside `genkit/` and
`deku-harness/`. You need the kit (harness submodule set up with `./scripts/setup.sh`), Docker
Desktop running, and the `claude` CLI logged in with a Claude Max account. No API key.

```bash
cd /path/to/deku-task-kit
git clone https://github.com/shivamgrt12/Deku-golden-toolkit.git golden
golden/bin/golden-install          # /golden command for Claude Code, Cursor and OpenCode + skills
golden/bin/golden-bridge start     # graders on your Claude login
golden/bin/gauntlet --self-test    # must print "N passed"
```

Already have a `golden/` folder from a zip? Move it aside first (`mv golden golden-old`), clone,
then delete the old one.

## Update

```bash
cd /path/to/deku-task-kit/golden
git pull
bin/golden-install                 # refreshes the editor commands and skills
```

Pull before starting a new bundle. A bundle already in progress keeps working after a pull; any
stage whose rules changed simply re-runs. Never edit `golden/` from inside a bundle run. If the
toolkit looks wrong, report it with the stage's output.

## Use

Open the kit folder in Cursor, Claude Code or OpenCode and run `/golden <absolute bundle path>`,
or tell the agent *"follow golden/RUN.md for `<bundle>`"*. `golden/bin/golden-status <bundle>`
shows where things stand and the next command at any time. `INSTALL.md` covers troubleshooting.

---

## Building a golden app

Open the kit in **Cursor, Claude Code or OpenCode** and run the `golden` command with the bundle
path (`/golden <bundle>`), or tell the agent: *"follow golden/RUN.md for `<bundle>`"*. Optional
inputs first:

```bash
golden/bin/golden-init <bundle> --prd companion.md --site https://reference.example
```

The agent works through nine phases. You are needed at two points:

| Phase | What happens | You |
|---|---|---|
| P-1 triage | the bundle itself is checked (T0) | route any bundle defect to its author |
| P0 intake | `PLAN.md`: every checklist id mapped; PRD / site reconciled into `sources.md` | answer open questions |
| P1 design | `DESIGN.md`: exact tokens, type, motion, focus, finish | **approve the design** |
| P2 backend | data, API, cold deploy (G0–G3) | |
| P3 frontend | interface, walkthrough tests, devtools + design probes (G4–G6) | |
| P4 hardening | abuse suite (G7) | |
| P5 simplify | code audit (G8), then spec review (SR) | |
| P6 grade | official runs (G10), straight after SR; G9 only when iterating | |
| P7 signoff | evidence report (G11) + `member-review.md` | **decide every review item, sign off** |

At any moment `golden/bin/golden-status <bundle>` shows the phase, every stage's verdict, and
the exact next command.

## The gauntlet

| Stage | Proves | Cost |
|---|---|---|
| T0 triage | `workflows.yaml` parses, declared slots, cited tests exist, test routes are in the brief, no browser substep the grader cannot do | free |
| G0 inputs | the app, a foreground `run.json`, `USER_README.md`, a real `solve.sh` | free |
| G1 build | env image, the app from its own manifest in a clean context, grader + runner images, no build warnings | free |
| G2 deploy | cold start twice from empty volumes, health 200, clean startup log | free |
| G3 pytest | the bundle's own suite via the harness `test.sh`: 0 failed, 0 skipped | free |
| G4 walkthrough | every browser substep driven by a Playwright test, frame per step, no console error | free |
| G5 inspect | every reachable page at 320/390/834/1440px: no console error or warning, failed request, 4xx/5xx, hotlink, sideways scroll, layout shift, axe violation | free |
| G6 design | AA contrast, no text < 12px, no `transition: all`, font-weight count, prose measure | free |
| G7 abuse | hostile input on every brief endpoint never crashes; the task-specific abuse suite passes; clean server log | free |
| G8 code | type check / lint / dead code for the app's language; no test-only literal in the app; no unasked dependency | free |
| SR spec review | **every requirement unit of instruction.md** checked by the harness's own grader: a code read of the test that covers it (partial → live), or a live browser check; context labels re-checked | subscription (~1–2 h) |
| G9 graders (optional) | the harness's browser grader, pytest and judge against the local deploy — run only to iterate cheaply after a G10 failure | subscription |
| G10 official | `deku-run -a oracle` ×2 and `-a nop` | subscription + time |
| G11 report | `_handoff/golden/report.md` from the receipts | free |

`golden/bin/gauntlet <bundle>` runs every free stage cheapest first and stops at the first red;
`--only G5,G6` or `--from G7` runs part of it; `--official` adds G10. Exit `0` green, `2` red or
blocked — **BLOCKED is never a pass**.

**Golden is not `reward == 1.0`.** `reward.json` is the pytest pass rate alone, so an app with a
broken interface still scores 1.0. G9 / G10 require scoring basis `complete`, combined 1.0,
workflow 1.0, pytest 1.0 with no skips, rubric × coverage 1.0, nothing invalid or degraded and an
empty review queue. Thresholds: [`acceptance.yaml`](acceptance.yaml).

## When the graders disagree with each other

The browser grader and the judge are LLMs; a verdict can flip between runs on the same app.

```bash
golden/bin/golden-noise <bundle> --runs 3 --yes     # ~1 h per run on a 28-criterion bundle
```

grades from cold N times and sorts every substep and criterion into *stable green*, *stable red*
(an app defect — fix it) and *flapping* (grader noise or a racy app — make the app unambiguous).
After a fix with the app otherwise unchanged, `gauntlet <bundle> --only G9 --resume-rubric`
re-judges only unresolved criteria and never re-rolls a settled verdict.

## Files

| Path | What |
|---|---|
| `RUN.md` | the agent entrypoint (all three tools) |
| `phases/` | one file per phase: inputs, skills, steps, exit check |
| `OVERRIDES.md` | house rules that outrank every skill |
| `FIX-PROTOCOL.md` | what to do on a red check; three strikes; waivers |
| `prompts/` | fresh-context critics: visual, spec (blind to tests), code; PRD / site reconciliation |
| `templates/` | `PLAN.md`, `DESIGN.md`, `sources.md` |
| `skills/` | pinned third-party skills, `ROUTING.yaml` (which phase loads which), `PROVENANCE.md` |
| `acceptance.yaml` | every threshold; `DESIGN.md` may relax a G6 default with a reason |
| `runner/` | the grader-side probes, axe-core, language adapters |
| `lib/` | the gauntlet, state, receipts, lints |
| `selftest/` | unit tests, plus Docker calibration on the verified reference task |

## Where the work lives in a bundle

```
solution/app/            the golden app (run.json, USER_README.md)
solution/solve.sh        deploys it for the oracle
solution/DESIGN.md       the approved design contract
solution/golden_tests/   walkthrough/ and abuse/ suites (never shipped into tests/)
_handoff/golden/         state, receipts, PLAN.md, sources.md, inputs/, evidence/, report.md
```

## Changing the toolkit (maintainers)

```bash
cd /path/to/deku-task-kit/golden
bin/gauntlet --self-test           # must stay green
git add -A && git commit -m "..." && git push
```

Edit the editor commands in `editor/`, never their installed copies at the kit root;
`bin/golden-install` copies them out. Re-vendoring a skill follows `skills/PROVENANCE.md`.
