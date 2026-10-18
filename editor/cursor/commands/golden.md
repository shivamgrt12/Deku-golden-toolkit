# /golden — build and prove the golden app for a task bundle

Build the golden app for the bundle path given after the command.

1. Read `golden/RUN.md` in full and follow it — it is the procedure of record.
2. Run `golden/bin/golden-status <bundle>` in the terminal and do exactly what its `next:` line
   says, one phase file at a time (`golden/phases/`).
3. Never report a phase done without the script output that proves it. Exit code 2 is red or
   blocked, never a pass.

**Critics run in a fresh context.** When a phase says to run `golden/prompts/critic-*.md` or
`source-reconcile.md`, open a NEW chat (or a background agent), attach only the files that prompt
names, paste its findings back here, and act on them.

**Stop and ask the member** at the two human gates — approving `DESIGN.md` (P1) and the final sign-off (P7).
After SR, go straight on to the official runs (P6) without asking. Never run `--approve` or `--waive` yourself.
