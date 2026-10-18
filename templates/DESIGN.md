# DESIGN — <task name>

design_direction: <token from task.toml [metadata].design_direction>

The brief is the design authority. This file makes it concrete and complete; it never
reinterprets it. Every row says where its value came from:

- `brief: <section>` — the value is in `instruction.md`, copied **verbatim**;
- `decided: <why>` — the brief is silent; the value follows the brief's intent and the
  design direction, and the reason says how.

A value that contradicts the brief is not a design choice; it is a bundle defect to report.

## Palette

| Role | Hex | Used for | AA pair | Source |
|---|---|---|---|---|
| ground | | | | |
| ink | | | ink on ground: <ratio> | |
| muted | | | | |
| accent | | | | |
| focus | | | | |
| danger | | | | |

Alpha variants are derived with `color-mix()`, never hand-picked.

## Typography

| Token | Family (with fallback stack) | Weight | Size / line height | Used for | Source |
|---|---|---|---|---|---|
| | | | | | |

Prose measure: <55-85> characters.

## Space, shape, depth

| Token | Value | Source |
|---|---|---|
| spacing unit | | |
| radius | | |
| border width | | |
| elevation | | |

## Motion

| Token | Duration (ms) | Easing | What animates (named properties) | Source |
|---|---|---|---|---|
| | | | | |

Reduced motion (`prefers-reduced-motion: reduce`): <what changes; transitions removed, video paused>.
Graded motion is CSS or `element.animate()` only.

## Finish

What makes it feel like a shipped product, within the direction's motion character. Every row the
character allows is filled; a row it rules out says `none: <character>`.

| Moment | Treatment (tokens, named properties) | Source |
|---|---|---|
| hover / press | | |
| disabled / busy control | | |
| loading (skeleton or progress) | | |
| content entering (lists, panels, toasts, dialogs) | | |
| route / view change | | |
| depth and surface (layering, texture, tint) | | |
| empty / success / error states | | |

## Visual ambition

The level of visual impact the PRD and reference site set (`_handoff/golden/sources.md
## Visual signature`), matched in this app's own design language. No PRD or site: write
`none supplied` and the direction alone sets the level.

Level: <standard | rich | showcase> — <why, citing the PRD section or site screenshot>

| Signature moment | Where (page, surface) | Borrowed from | Built with | Graded or decorative | Fallback (no WebGL, reduced motion, narrow) |
|---|---|---|---|---|---|
| | | | | | |

## Focus

| Property | Value | Source |
|---|---|---|
| ring | <width>px <style> <colour token> | |
| offset | <px> | |

## Breakpoints

| Width | What changes | Source |
|---|---|---|
| 320 | | |
| 390 | | |
| 834 | | |
| 1440 | | |

## States

| State | Treatment | Source |
|---|---|---|
| empty | | |
| loading | | |
| error | | |
| success | | |
| denied | | |

## Media

Every picture, icon and video the brief asks for, by brief unit (`_handoff/golden/brief-units.md`).
Produced by is one of `svg-css` (drawn in code, the default), `seeded-renderer` (drawn by the app
from stored data), `rendered-video` (code-drawn frames encoded with ffmpeg), `fetch` (a freely
licensed file from `golden-media`), `member-supplied` (a file the member provides). For `fetch`,
Search / files is the search (`runner at dusk city street`) or an icon list (`lucide: timer, route`);
for `member-supplied`, the file names expected in `_handoff/golden/inputs/media/`. Write `none`
under this heading when the brief asks for no media.

| Need | Brief units | Produced by | Search / files | Shown at (px) | Alt |
|---|---|---|---|---|---|
| | | | | | |

## Not media

Every brief unit that mentions media without asking for any, and why.

| Brief units | Why it is not a media need |
|---|---|
| | |

## Judged criteria mapping

Every visual / motion / accessibility / responsiveness criterion in `tests/judge.toml`, and the
token or rule above that satisfies it.

| Criterion | Satisfied by |
|---|---|
| | |

## Brief values not carried

Every colour, px value, timing or font the brief's UI sections name that does NOT appear above,
with the reason. "The brief forbids it" is a reason; silence is not.

| Value | Why it is not in this design |
|---|---|
