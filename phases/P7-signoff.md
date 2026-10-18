# P7 signoff — a human reads it

## Do

1. `"$KIT/golden/bin/gauntlet" "$B" --only G11` renders `_handoff/golden/report.md` from the
   receipts: every stage, its evidence, what was executed and what was only audited.
2. Tell the member it is ready and where to look: the report, the screenshot set
   (`evidence/G5/pages/screens/`, every route at four widths), the walkthrough frames, and
   **`_handoff/golden/member-review.md`** — every checklist gap (with its golden test's assertions),
   every `context` label, every unit the spec review could not observe, and every **member
   check** (a unit its tests prove only partly, with the missing part named — open the app and
   check that part). They tick `[x]` or
   write `REJECT: <why>` under each; a rejection reopens the phase that owns it. P7 cannot close
   until every item is decided and none is rejected.
3. The member reads it — taste on sight is the one thing no script settles — and either signs
   off (`golden-status "$B" --approve P7`) or names what to change, which reopens the phase that
   owns it.

The bundle is GOLDEN when P7 is approved. Nothing else makes it so.
