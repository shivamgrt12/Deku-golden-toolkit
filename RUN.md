# golden/RUN.md — build a golden app for one task bundle

You are building the **golden app**: the reference solution for a Deku task bundle. The client
uses it as the correct answer every evaluated agent is measured against, so it must be correct
everywhere anyone looks — every grader green, a clean deploy, nothing stubbed, a modern
interface, clean devtools, a backend that refuses abuse cleanly.

You do not decide when it is done. **Scripts do.** Every phase ends on a check that writes a
receipt bound to the exact bytes of the app. Saying "it works" moves nothing.

Read this whole file once, then loop on `golden-status` until it says the bundle is GOLDEN.

---

## How to run commands

Set two absolute paths once and use them everywhere. Never `cd`; one command per call.

```bash
KIT="<absolute path to deku-task-kit>"
B="<absolute path to the bundle>"
```

| Command | When |
|---|---|
| `"$KIT/golden/bin/golden-status" "$B"` | **start of every session and after every step** — it names the phase and the exact next command |
| `"$KIT/golden/bin/golden-status" "$B" --advance` | a phase's work is done: runs its exit check and moves on only if green |
| `"$KIT/golden/bin/gauntlet" "$B" --only G3` | run one gauntlet stage (or `--from G5`) |
| `"$KIT/golden/bin/golden-bridge" start` | before G9 / G10 — the graders run on the member's Claude subscription |
| `"$KIT/golden/bin/golden-media" "$B"` | P1, when `## Media` has `fetch` or `member-supplied` rows — candidates + contact sheet; `--choose <need>=<id>`; P3: `--vendor <dir>` |

Exit code `0` is green, `2` is red or blocked. **BLOCKED is never a pass.** Read the stage's
`problems` list in the output — every red line names what to fix.

---

## The loop

```
golden-status  ->  open phases/<phase>.md  ->  do the work  ->  run the phase's checks
      ^                                                                |
      |                         red?  FIX-PROTOCOL.md  <---------------+
      |                                                                |
      +---------------  golden-status --advance  <------- green -------+
```

1. Run `golden-status`. It prints the phase, every stage's verdict (PASS / FAIL / BLOCKED /
   STALE), and the next command.
2. Open `phases/<phase>.md` for that phase and do exactly what it says. Load only the skills
   it names (`skills/ROUTING.yaml`).
3. Run the checks it names. On any red line follow `FIX-PROTOCOL.md` — never improvise.
4. When its checks are green, `golden-status --advance`. Two phases stop for the **member**:
   P1 (approve `DESIGN.md`) and P7 (sign off). P6 follows SR without stopping. At those,
   **stop and ask the member**; never record an approval yourself.

A receipt goes **STALE** the moment the app changes after it passed. That is intended: a fix in
P5 re-opens P2–P4 until their stages are re-run green. `golden-status` tells you which.

---

## The phases

| Phase | File | You produce | Exit check |
|---|---|---|---|
| P-1 triage | `phases/P-1-triage.md` | nothing — you check the bundle is sound | T0 |
| P0 intake | `phases/P0-intake.md` | `_handoff/golden/PLAN.md` (every checklist id and every brief unit accounted for), `sources.md` | plan + brief coverage + sources lint |
| P1 design | `phases/P1-design.md` | `solution/DESIGN.md` (incl. `## Media`) + its preview + the media contact sheet (`golden-media`) | design lint + media plan + current preview, **member approves** (`phases/P1-review.md`) |
| P2 backend | `phases/P2-backend.md` | data model, seed, API, `run.json`, `solve.sh` | G0 G1 G2 G3 |
| P3 frontend | `phases/P3-frontend.md` | the interface, `golden_tests/walkthrough/` | G4 G5 G6 |
| P4 hardening | `phases/P4-hardening.md` | `golden_tests/abuse/` and the fixes it forces | G7 |
| P5 simplify | `phases/P5-simplify.md` | less code; then the spec review | G8, **SR** (every brief unit met) |
| P6 grade | `phases/P6-grade.md` | nothing new — official runs | G10 (G9 optional) |
| P7 signoff | `phases/P7-signoff.md` | `report.md`, `member-review.md` | G11, **member decides every review item and signs off** |

---

## What outranks what

When two sources disagree, the higher one wins. Never resolve a conflict silently: write it in
`_handoff/golden/sources.md` and tell the member.

```
instruction.md + solution/checklist.md     the contract -- what the agent is asked to build
tests/ (test_output.py, workflows.yaml,    what is checked -- never edit, never special-case
        judge.toml)
OVERRIDES.md                               house rules that beat every skill
solution/DESIGN.md                         your design contract, once the member approves it
_handoff/golden/inputs/ (PRD, site)        richness where the brief is SILENT, never more
skills                                     advice, loaded per phase
```

The bundle is the contract. **You never edit `instruction.md`, `tests/`, `task.toml` or
`environment/`.** If one of them is wrong, that is a bundle defect: stop, describe it, and route it
to the bundle author through the member.

---

## Non-negotiables

Read `OVERRIDES.md` before P2. The four that cause silent, expensive failures:

1. **Build to the brief, not to the tests.** Read the tests to know what will be checked, never
   to decide what to build. A value only the tests know, appearing in the app, fails G8.
2. **Motion is CSS or `element.animate()` only.** The verifier reads Chrome's Animation domain,
   which cannot see `requestAnimationFrame`; a GSAP tween looks perfect and scores zero.
3. **Every credential and literal comes verbatim from `instruction.md`.** An invented password
   once scored a complete app 0.
4. **`solution/app/` starts cold from its own `run.json`.** Grading builds it in a clean
   container; nothing from your machine survives.

When the same check is red three times, stop and escalate per `FIX-PROTOCOL.md`.
