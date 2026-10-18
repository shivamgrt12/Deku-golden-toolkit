# P5 simplify — the least code that does all of it

## Skills

`ponytail` (`/ponytail-review`, `/ponytail-audit`) — before adding any abstraction ask: does this
need to exist, is it already here, is it in the platform, can it be one line.

## Do

1. Run `"$KIT/golden/bin/gauntlet" "$B" --only G8`: type check / lint / dead-code for the app's
   language, test-only literals, unasked dependencies.
2. Remove dead code, unused exports and dependencies; collapse duplicate helpers into one per
   invariant; confirm one config module and one call path for the acting user.
3. Run `prompts/critic-code.md` in a fresh context; fix what it finds.
4. Every removal can break something: `golden-status` shows which earlier receipts went stale —
   re-run them (`gauntlet "$B" --from G1`).

## Spec review (SR)

When G1–G8 are green, run `"$KIT/golden/bin/gauntlet" "$B" --only SR` (start the bridge first).
It checks **every brief unit** against the app with the harness's own LLM grader — not you:

- a unit proven by a pytest test or a G4 walkthrough: the critic reads the most relevant tests
  (with the helpers they use) beside the sentence and answers whether they assert **all** of it;
  a partial answer names the missing part, and the unit goes to the member's P7 list as a
  **member check** (`--full-live` checks it live instead — hours on a large brief);
- a checklist gap, a judge-only unit, or anything not deterministically proven: the
  harness browser grader checks it live on the running app, with a screenshot;
- a `context:` unit: the critic decides whether it really asks for nothing; if it states an
  obligation, it is checked live too.

Every unit gets a verdict in `_handoff/golden/spec-review.json`. Fix every `not met` by its
root cause (FIX-PROTOCOL), then re-run SR — the app changed, so it re-checks in full. With the
app unchanged (for example after a grader hiccup), `--resume-spec` re-checks only what is not
met yet. Expect under an hour on a ~200-unit brief (about 40 min of code reads plus ~3.5 min
per live unit); it prints progress. A `member check` does not fail SR, but look at each one:
where the missing part is a real gap, fixing the app or adding a golden test is cheaper than
the member finding it at P7.

## Exit

G1–G8 and SR all green and current, then `golden-status "$B" --advance`.
