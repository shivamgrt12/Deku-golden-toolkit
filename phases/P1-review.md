# P1 review — what the member checks before approving DESIGN.md

You are approving the design contract the whole interface will be built to. The brief
(`instruction.md`) is the design authority; `DESIGN.md` makes it concrete and complete. Open:

- `_handoff/golden/design/preview@1440.png` and `preview@390.png` (or `preview.html` in a browser)
- `solution/DESIGN.md`
- the brief's `## UI/UX notes` and `## Front-end specification`

## 1. Is everything from the brief there? — mostly mechanical

The design lint already proved that every colour, px value, timing, easing curve and named font
in the brief's UI sections is either in `DESIGN.md` or listed under **Brief values not carried**
with a reason. Your part:

- [ ] Read the **Brief values not carried** table. Every reason is true ("the brief forbids it",
      "a measurement of one element, built in CSS") — none is "not needed" for something the brief
      asks for.
- [ ] Anything the brief states in words rather than values (a mood, "serif throughout", "the
      accent appears once per screen") is reflected in the preview.

## 2. Is each decided value consistent? — this is the real review

Every value badged **decided** in the preview is a design call the agent made where the brief is
silent. Hover a badge for its reason. For each:

- [ ] It follows the brief's stated intent and mood.
- [ ] It fits the drawn `design_direction` (shown at the top of the preview) — its type
      personality, motion character, density and layout archetype (genkit reference/L §L.6).
- [ ] Contrast numbers under each swatch reach AA: 4.5:1 for text, 3:1 for large text and UI.
- [ ] Motion matches the direction's character (`none-except-focus` means nothing animates but the
      focus ring; `mechanical` means short and linear).
- [ ] States (empty, loading, error, success, denied) are designed, not left as plain text.
- [ ] `## Finish` fills every row the motion character allows (hover/press, loading, entering
      content, view changes, depth). An app that is merely correct looks unfinished to the judge.
- [ ] `## Visual ambition` matches the PRD / reference site: put their screenshots beside the
      plan. If they are striking (3D, scroll storytelling, rich motion) and the plan is
      `standard`, send it back. Each signature moment fits the direction and the brief.

A thin brief means many decided rows; that is expected, and it is exactly where your judgement
is needed.

## 3. Media — what will be on screen

Open `_handoff/golden/media-sheet.html` (or `media/sheet.png`) beside `## Media` in DESIGN.md. The
lint already proved every media sentence of the brief is planned or explained under `## Not media`.

- [ ] Each chosen file (green border) fits its brief sentence and the direction's mood — not a
      generic stock look. Ask for another candidate, or supply your own file, if not.
- [ ] No chosen photo shows an identifiable person, a brand logo, a product's trademark or a
      recognisable artwork or building that may be protected — a CC0 licence covers the
      photographer's copyright, not those. Pick another candidate if it does.
- [ ] Nothing is planned that the brief does not ask for.
- [ ] Each `## Not media` reason is true.

## 4. Does it look like a shipped product?

- [ ] On sight, at both widths, it reads as a deliberate product — not a template, not
      scaffolding, no generic purple gradient or default component kit.
- [ ] The phone width is designed, not squeezed.
- [ ] The focus ring is clearly visible.

## Record the decision

Approve with what you checked, so the reason travels with the bundle:

```bash
golden/bin/golden-status <bundle> --approve P1 --note "decided palette and states fit editorial-serif; R14-R17 mapped"
```

Or reply to the agent with what to change; it edits `DESIGN.md`, re-runs the lint and the preview,
and asks again. Changing `DESIGN.md` after approval makes the preview stale and P1 re-opens.
