---
description: Build and prove the golden app for a task bundle, phase by phase, until golden-status says GOLDEN
---

Build the golden app for the bundle at `$ARGUMENTS`.

Read `golden/RUN.md` in full and follow it — it is the procedure of record. Start with
`golden/bin/golden-status $ARGUMENTS` and do exactly what its `next:` line says, one phase file
at a time. Never report a phase done without the script output that proves it.

**Critics run in a fresh context.** When a phase says to run `golden/prompts/critic-*.md` or
`source-reconcile.md`, delegate it to a subagent (for example `@general`) with only the files that
prompt names, then act on its findings yourself.

**Stop and ask the member** at the two human gates — approving `DESIGN.md` (P1) and the final sign-off (P7).
After SR, go straight on to the official runs (P6) without asking. Never run `--approve` or `--waive` yourself.
