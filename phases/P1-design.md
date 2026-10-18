# P1 design — fix the design contract before the interface exists

The judge and the design probe grade typography, colour, spacing, motion and accessibility. A
contract written first makes every one of those checkable without a judgement call.

## Read

- `## UI/UX notes`, `## Front-end specification` (if present) and every visual literal in the
  brief: hex values, type scale, timings, breakpoints.
- `task.toml [metadata].design_direction` — the drawn direction (genkit reference/L §L.6). Your
  design expresses it; it is not negotiable.
- Every `judge.toml` criterion whose dimension is `ui_visual`, `motion`, `accessibility` or
  `responsiveness` — each must map to a token in your contract.
- `_handoff/golden/inputs/site/` — a captured reference site: learn its rhythm and hierarchy,
  never copy its brand, copy, logo or images.

## Skills

`ui-ux-pro-max` (design-system generator), the `taste-skill` style that matches the
`design_direction`, `frontend-design`, `layout-rigor`. See `skills/ROUTING.yaml`.

## Produce

**`solution/DESIGN.md`** from `templates/DESIGN.md`. Exact values only — no "around", no
"something like". **The brief is the design authority:** every value the brief's UI sections pin
is copied verbatim with `Source: brief: <section>`; only where the brief is silent do you decide,
with `Source: decided: <why>` following the brief's intent and the direction. Every brief value you
do not carry (for example one the brief forbids) goes under `## Brief values not carried` with the
reason. Never contradict the brief — a conflict is a bundle defect to report.

It covers:

- `design_direction: <token>` matching `task.toml`;
- palette by role in hex (ground, ink, muted, accent, focus, success, warning, danger) with AA
  pairs stated; alpha variants derived with `color-mix()`;
- typefaces, the weights used (usually two), a type scale, the prose measure (55–85 characters);
- one spacing unit, one radius, one border width, one elevation;
- motion: duration tokens in ms, easing, what animates, what `prefers-reduced-motion` does;
- the focus treatment (ring width, offset, colour);
- `## Finish`: the polish that makes it read as a shipped product — hover and press, busy
  controls, skeletons, content entering, view changes, depth, designed states — each built from
  the motion and colour tokens and **only as far as the motion character allows** (below);
- breakpoints, and what the navigation becomes at the narrow one;
- a mapping: each visual judge criterion → the token that satisfies it.

Optionally a fenced ```` ```golden-overrides ```` block may relax a G6 default **with a reason**
(for example `max_font_weights: 4` for a direction that needs a display weight).

## Finish — as far as the brief allows, never further

A brief that is silent about polish is not asking for a bare app: the judge grades whether it
looks like a product a company shipped. Fill every `## Finish` row the motion character allows,
using `modern-effects` (its native-CSS parts: `@starting-style`, View Transitions, scroll-driven
animations, `@property`, OKLCH, grain, layered depth). The brief and the direction still win:

| Motion character | Finish it allows |
|---|---|
| `none-except-focus` | no motion rows (`none: none-except-focus`); finish comes from depth, borders, type and designed states |
| `instant` | state changes with no duration; skeletons without shimmer; depth and states as usual |
| `mechanical` | short linear transitions on hover/press and entering content; no easing curve, no overshoot |
| `eased` | eased hover/press, `@starting-style` entrances, View Transitions between views, skeleton shimmer |
| `springy` | all of `eased`, with a visible overshoot-and-settle on entrances and presses |

Every treatment reads a token, names its properties (no `transition: all`), is CSS or
`element.animate()`, and is removed under `prefers-reduced-motion`. Effects that load a library
(GSAP, Three.js, WebGL, Lenis) only where the brief itself asks for that spectacle — then follow
`award-caliber-motion`, which keeps them off anything graded.

## Visual ambition — as striking as the PRD and reference site

When `inputs/` holds a PRD or a captured site, the app must reach **their** level of visual
impact, not a safe default. `sources.md ## Visual signature` (from `prompts/source-reconcile.md`)
lists what makes them striking: 3D scenes, scroll storytelling, animated gradients, parallax
depth, cursor-reactive surfaces, kinetic type, rich micro-interactions. Fill `## Visual ambition`:

- **Level:** `standard` (Finish only), `rich` (Finish plus a few signature moments in CSS /
  WAAPI) or `showcase` (signature moments may use Three.js / WebGL / GSAP as decoration). Match
  the sources: a site built around a 3D hero is `showcase`.
- **Signature moments:** each one names its page and surface, the PRD section or site screenshot
  it is borrowed from, what builds it, and its fallback. Re-express the idea in this app's
  palette, type and direction — never copy the source's brand, art, models or copy.
- **instruction.md still wins.** A moment the brief rules out ("nothing bouncing", "no hero
  imagery inside the signed-in pages", reduced motion) is not built; list it under
  `## Brief values not carried` with the brief's line. The direction decides the character: on
  `glass-depth` a showcase is light, refraction and layered depth, not a bouncing toy.
- **Placement:** heavy scenes go on surfaces that frame the task (landing, sign-in, empty
  states, headers, backgrounds). On the screens where the user works, signature moments stay
  light and never sit between the user and a control.

Load `award-caliber-motion` for every `showcase` or `rich` plan (it splits graded from decorative
motion), and `webgl-components` / `premium-3d-website` for 3D moments.

## Media — plan it, source it, show it

The brief decides whether there is media. Fill `## Media` and `## Not media` in DESIGN.md: every
brief unit that mentions a picture, icon or video lands in one of them (the lint lists any you
miss). Prefer, in order: `svg-css`, `seeded-renderer`, `rendered-video`, `fetch`,
`member-supplied`. Never add media the brief does not ask for — that is unasked scope.

For `fetch` and `member-supplied` rows:

1. `"$KIT/golden/bin/golden-media" "$B"` — fetches candidates (Openverse + Wikimedia Commons for
   photos; Lucide / Heroicons for icon lists). **Only CC0 and public domain**, never from Flickr,
   never a Commons file tagged with personality or trademark rights; CC BY only with
   `--allow-cc-by` and a member's agreement. It records each file's licence and creator **from
   the source's own API**, and writes the contact sheet
   `_handoff/golden/media-sheet.html` + `media/sheet.png`.
2. Look at the candidates (open the image files) and pick the one that serves the brief and the
   direction: `golden-media "$B" --choose <need>=<id>`. A gallery takes several ids, comma-separated.
   **If none fits, do not settle**: switch the row to `member-supplied` and name the file you need.
3. A `member-supplied` row waits for the member's file in `_handoff/golden/inputs/media/`. P1 does
   not exit without it; ask the member, and never put a placeholder in the meantime.

## Preview, then ask

1. `"$KIT/golden/bin/golden-design-preview" "$B"` — runs the design lint (carriage: every brief
   value accounted for; source on every row) and renders `_handoff/golden/design/preview.html` with
   screenshots at 390 and 1440px. Fix every lint problem it prints.
2. Look at the screenshots yourself first. If it does not look like a shipped product, revise
   `DESIGN.md` and re-run.
3. **Stop and ask the member to review** with `phases/P1-review.md`, pointing them at the two
   screenshots, the media contact sheet (if any media is fetched or supplied) and the count of
   decided values. They approve with
   `golden-status "$B" --approve P1 --note "..."`. Never record the approval yourself.

## Exit

`golden-status "$B" --advance`: design lint and media plan green, the preview and the contact sheet
current for this exact `DESIGN.md`, and the member's approval. Do not build the interface before approval.
