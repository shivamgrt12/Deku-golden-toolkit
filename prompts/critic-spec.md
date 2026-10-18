# critic-spec — does it do what the brief says? (FRESH context, blind to the tests)

> **Automated as the SR stage.** `gauntlet --only SR` runs this review with the harness's own grader
> over every numbered brief unit and gates on it. Use this prompt only for an extra manual read.

You are given ONLY `instruction.md`, `solution/checklist.md` and the running app's URL (or its
walkthrough frames). You are deliberately NOT given `tests/`.

1. Walk the brief's `## User flow` and `## Core features` as a first-time user would.
2. For each checklist item of type `capability`, `rule`, `role`, `constraint`: is it observably
   true in the app? Mark each `met`, `not met` (what you saw), or `cannot observe` (why).
3. Note anything the app does that the brief never asked for — over-build is a defect.

Output the three lists. This read catches the defect the tests cannot: an app shaped to the
answer key rather than to the spec.
