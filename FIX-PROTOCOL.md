# FIX-PROTOCOL — what to do when a check is red

Every red line is evidence. Treat it like a failing test in a codebase you care about: find the
cause, fix the cause, prove the fix, and make sure nothing else broke.

## The four steps, every time

1. **Quote the failure.** Copy the exact red line from the stage output, and the relevant part of
   its evidence (`_handoff/golden/evidence/<stage>/`). Do not paraphrase it.
2. **State the root cause as a hypothesis**, in one sentence, before touching code:
   *"The talents page overflows at 320px because the slug in each card is an unbreakable word."*
   If you cannot write that sentence, you do not understand the failure yet — read more evidence,
   reproduce it, open the screenshot.
3. **Make the smallest change that removes the cause**, not the symptom. Fixing the card's
   wrapping is a cause fix; hiding the overflow with `overflow-x: hidden` on `body` is a symptom
   fix and is forbidden.
4. **Re-run from the earliest stage the change could affect**, not just the stage that failed.
   A CSS change re-runs G5 and G6. A data-model change re-runs from G1. `golden-status` shows
   which receipts went stale — re-run all of them.

## Never

- Edit `tests/`, `instruction.md`, `task.toml`, `environment/` or `acceptance.yaml` to turn a
  check green. If a check is wrong, it is a bundle or toolkit defect — escalate it.
- Special-case the grader: detect a test's probe values, user agent, timing or data, or render
  something only a check looks for.
- Add `pytest.skip`, swallow an exception, add a retry loop that hides a failure, or catch an
  error just to return 200.
- Re-run a flaky check until it passes and call it fixed. A verdict that flips between runs on
  the same app is a finding in itself: make the app unambiguous (state in words, a stable URL, a
  visible confirmation), then measure it with `golden-noise`.

## Three strikes

When the **same check** is still red after three honest fix cycles:

1. Stop changing code.
2. Write down, for the member: the check, the three hypotheses you tested, what each fix changed,
   and the evidence after each.
3. Ask whether it is (a) a design flaw — go back to P0/P1 and redesign that part, (b) a bundle
   defect — route to the bundle author, or (c) grader noise — run `golden-noise` and let the
   member decide.

Thrashing past three strikes costs the member money and never converges.

## Waivers

A check can be wrong about a specific case (a heuristic that misreads one legitimate line). The
member — not you — may waive one finding by its id with a written reason:

```bash
"$KIT/golden/bin/golden-status" "$B" --waive <id> --note "why this finding does not apply"
```

The reason travels in every later receipt. Propose a waiver with your reasoning; never record one.
