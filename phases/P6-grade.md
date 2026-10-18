# P6 grade — the real graders

## Do

1. `"$KIT/golden/bin/golden-bridge" start` (once per machine session).
2. **G9 is optional.** SR and the free stages already proved what it would re-check, so the
   default is to go straight to the official runs. Run G9
   (`"$KIT/golden/bin/gauntlet" "$B" --only G9`) only when it is cheaper than G10: after a G10
   failure on judged criteria, iterate with `--only G9 --resume-rubric`, which re-judges just
   the failed criteria in minutes instead of three hours.
3. Golden means every channel at its ceiling: workflow 1.0, pytest 1.0 with no skips, rubric
   score × coverage 1.0, nothing invalid or degraded, an empty review queue.
4. For a red judged criterion, read its rationale in `evidence/G9/<run>/verifier/judge.json`.
   Fix the app if the rationale names a real defect. If the app already meets the criterion,
   do **not** re-roll it — run `golden-noise "$B" --runs 3 --yes` and let the member decide.
5. After an app fix, the whole G9 re-runs (the receipt is stale). With the app unchanged,
   `--resume-rubric` re-judges only unresolved criteria and keeps every settled verdict.
6. `"$KIT/golden/bin/gauntlet" "$B" --only G10 --official` — `deku-run` oracle twice and nop
   once. Golden on both oracle runs; nop exactly 0.0 (above 0 is a P0 bundle defect).

## Exit

G9 and G10 green, then `golden-status "$B" --advance`.
