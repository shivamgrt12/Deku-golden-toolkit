---
description: Build and prove the golden app for a task bundle, phase by phase, until golden-status says GOLDEN
argument-hint: "<bundle-path>"
allowed-tools: Bash(golden/bin/*:*), Bash(./golden/bin/*:*), Read, Edit, Write, Glob, Grep, Agent
---

Build the golden app for the bundle at `$ARGUMENTS`.

Read `golden/RUN.md` in full and follow it. It is the procedure of record — do not improvise an
order, and never report a phase done without the script output that proves it.

Start with:

```bash
golden/bin/golden-status $ARGUMENTS
```

and do exactly what its `next:` line says, phase file by phase file.

**Critics run in a fresh context.** When a phase says to run `golden/prompts/critic-*.md` or
`source-reconcile.md`, spawn a subagent with the Agent tool, give it only the files that prompt
names, and act on its findings yourself.

**Stop and ask the member** at the two human gates — approving `DESIGN.md` (P1) and the final sign-off (P7).
After SR, go straight on to the official runs (P6) without asking. Never run `--approve` or `--waive` yourself.
