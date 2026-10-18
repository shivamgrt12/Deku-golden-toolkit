# source-reconcile — PRD / site against the brief (run in a FRESH context)

You are given: `instruction.md` (the brief, binding), and the supplied sources under
`_handoff/golden/inputs/` (a PRD and/or a captured reference site, advisory).

Produce `_handoff/golden/sources.md` from `golden/templates/sources.md`.

1. For every concrete decision a source offers (a page, a field, copy, an empty state, a colour,
   a layout, imagery): find what the brief says about the same subject.
   - Brief **silent** → it may enter the app; list it under Decisions with its source.
   - Brief **agrees** → nothing to record; the brief already carries it.
   - Brief **disagrees** → a Conflict. The brief wins. Record both sides, status `open`.
2. A feature that exists ONLY in a source is not built. List it under Conflicts as
   "source-only feature" so the member can route it to the bundle author.
3. From a reference site take rhythm, hierarchy and density — never brand names, logos, copy
   text or images. Imagery is sourced separately with a licence (Assets table).
3b. Fill `## Visual signature`: what makes the PRD's UI direction and the site striking — 3D
   scenes, scroll-driven storytelling, animated gradients, depth and parallax, cursor-reactive
   surfaces, kinetic type, notable micro-interactions — each with where it appears (PRD section
   or screenshot file). Describe the effect, never the brand. P1 matches this level.
4. Change every resolved conflict's status to `routed` only after the member confirms they have
   told the bundle author.

Output only the file. Quote the brief line for every "brief says" cell that is not "silent".
