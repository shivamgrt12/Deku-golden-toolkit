# OVERRIDES — house rules that outrank every skill

Skills are advice written for websites in general. These rules exist because this app is graded
by a specific harness, and each one has cost a real run when ignored. When a skill says otherwise,
this file wins. The gauntlet enforces most of them; the rest are read by the critics.

## Contract

| Rule | Why |
|---|---|
| Every route, field name, status, seeded account, password and copy string the brief pins is used **verbatim**. | Graders assert the exact literal. An invented-but-plausible value scores a complete app 0. |
| Build nothing the brief and checklist do not ask for — no extra page, module, table, role or setting. | `scope_discipline` is graded; an unasked feature is a defect, not a bonus. |
| Where the brief is silent, a PRD or reference site may add richness (copy, empty states, imagery mood), recorded in `sources.md`. Never where the brief speaks. | The brief is the only file the evaluated agent sees. |
| No value that only the tests know appears in the app. | Teaching to the test; G8 fails it. |

## Runtime

| Rule | Why |
|---|---|
| `solution/app/run.json` declares `install`, `build` and a **foreground** `serve`. No `setsid`, `nohup`, `&`. | The verifier builds and supervises the app itself. |
| Bind `0.0.0.0`, port from `APP_PUBLIC_PORT`, every host and credential from the environment, read in **one** config module. | A loopback listener is unreachable; a hardcoded value breaks a clean deploy. |
| `GET /api/health` returns 200 only when the app can actually serve. | The deploy gate trusts it. |
| One idempotent seed routine; re-running it after a restart changes nothing. | Every grade starts from a cold, empty database. |
| Derived values (counts, ordinals, totals) are computed at read time, never stored where they drift. | Stored derivations go stale under the very edits graders make. |
| Money is integer minor units end to end; no float parses money anywhere. | Rounding defects are graded as data integrity. |
| No second datastore, cache, queue, mail vendor, analytics, consent banner or beacon. | Unasked infrastructure; G8 flags it. |

## Interface

| Rule | Why |
|---|---|
| Graded motion is CSS transitions/animations or `element.animate()` only. GSAP, `requestAnimationFrame`, canvas or WebGL may decorate, never carry a graded animation. | The motion probe reads Chrome's Animation domain, which cannot see rAF. |
| Decorative 3D and motion (DESIGN.md `## Visual ambition`) is allowed and expected when the PRD or site has it: bundled from npm, never a CDN; falls back to CSS when WebGL is software-only; reserves its box; pauses off-screen; never covers or delays a control. It is decoration, not a feature — no new page, control or setting. | The member wants the reference's visual level; the graders need a clean console, no layout shift and reachable controls. |
| No `transition: all`. Every transition names its properties. | G6 fails it; it animates layout properties by accident. |
| `prefers-reduced-motion` removes transitions and pauses video without stripping the design. | Graded on the presentation channel. |
| AA contrast everywhere, no text under 12px, a visible focus ring with offset, every icon-only control labelled. | G5 (axe) and G6 measure all of it. |
| No horizontal scroll at 320px on any route — including with long user-entered words. | WCAG reflow; a long unbroken slug is the usual culprit. |
| State is stated in words, not only in colour; actions confirm visibly; URLs reflect state. | Correct UX, and it is what makes the LLM browser grader read the app the same way every run. |
| Devtools stays empty: no console error or warning from the app's code, no uncaught exception, no 5xx, no missing asset (a 4xx on a script, stylesheet, image or font), no layout shift. **The brief's own HTTP semantics are not defects:** a 404 not-found page and a 4xx refusal from the API are correct, and Chrome's automatic "Failed to load resource" line for them is ignored. Never wrap a refusal in a 200 to keep the console quiet. | G5 and every walkthrough test fail on the defects. |
| Assets are vendored with a licence; nothing is hotlinked from another origin at run time. | Grading must be reproducible offline-of-the-internet. |
| Media comes only from DESIGN.md `## Media`: drawn in code first, then a licensed file (CC0, public domain, CC BY with credit, or member-supplied). Never a placeholder — no picsum, placehold.co, grey box or lorem image, not even "for now". | G8 fails placeholders and unlicensed files; G5 fails a picture that does not render or is far larger than its box. |
