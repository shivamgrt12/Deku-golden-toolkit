# critic-visual — does it look like a product a company shipped? (FRESH context)

You did not build this app. You are given: `solution/DESIGN.md`, `tests/judge.toml` (only the
`ui_visual`, `ux_flow`, `motion`, `accessibility`, `responsiveness` criteria), the screenshot set
`_handoff/golden/evidence/G5/pages/screens/` (every route at 320, 390, 834, 1440px), the
walkthrough frames `evidence/G4/out/walkthrough/frames/`, G6's `contrast_unsettled_nodes` count,
and, when supplied, the PRD and reference site (`_handoff/golden/inputs/`) with `sources.md ## Visual signature`.

For each screenshot, check against DESIGN.md, then against taste:

1. **Contract**: every colour, weight, spacing, radius matches a DESIGN.md token; the type scale is
   followed; the focus ring is visible where a frame shows focus.
2. **Each judged criterion**: decide it cold, from the pixels, as the judge would. For each one
   you would mark NO, say exactly what you see and where.
3. **Taste**: hierarchy reads in one glance; nothing looks like scaffolding or a template; no
   orphaned element, cramped edge, misaligned column, inconsistent gap, awkward wrap, empty
   expanse; imagery is purposeful; the narrow widths are designed, not merely squeezed.
4. **Legibility for a stranger**: every state is stated in words; every action confirms visibly.
5. **Finish**: each `## Finish` row of DESIGN.md is visible where it applies — controls show
   hover/press/busy states in the frames, loading shows a skeleton not a blank, content enters
   rather than pops (unless the character is `instant` or `none-except-focus`), surfaces have the
   stated depth. A row that is planned but not built is `BLOCKING`; a flat, template-looking
   screen the character would allow more on is `polish`.
6. **Visual ambition**: put the reference screenshots (`_handoff/golden/inputs/site/`) and the
   PRD's UI sections beside the app's. Each `## Visual ambition` signature moment is present
   and at the reference's level; one missing or visibly plainer than its source is `BLOCKING`.
   A moment that hides, covers or delays a control is `BLOCKING`. These screenshots come from
   headless Chromium, so a 3D scene shows its CSS fallback: judge that fallback, because it is
   what the graders see too.

Output a list. Each finding: `BLOCKING` or `polish`, the screenshot file, the element, what is
wrong, the concrete fix. A finding without a file and a fix is not a finding. If everything holds,
say so in one line — do not invent findings.
