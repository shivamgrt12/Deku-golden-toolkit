# P3 frontend — the interface, to DESIGN.md

## Skills

`frontend-design`, `layout-rigor`, the `taste-skill` style for the direction, `modern-effects`
for `## Finish` (its native-CSS parts), `media-assets` for imagery. `award-caliber-motion`,
`webgl-components` and `premium-3d-website` wherever DESIGN.md `## Visual ambition` plans them
(graded motion stays CSS / WAAPI — `OVERRIDES.md`).

## Build

1. Tokens first: implement DESIGN.md as CSS custom properties; every colour, size, duration and
   radius reads a token.
2. Every page and state the brief names: loading, empty, error, success, denied. No dead control,
   no "coming soon", no placeholder copy.
3. Make the app **legible to a stranger**: state in words, not only colour; labelled controls;
   a visible confirmation after every action; URLs that reflect what is on screen.
4. **Walkthrough tests** — `solution/golden_tests/walkthrough/test_*.py`, one Playwright test
   per browser substep of `workflows.yaml`, marked `@pytest.mark.substep("<workflow_id>", <n>)`
   (n counts browser substeps only, from 1). Fixtures: `page`, `base_url`, `browser`. Each test
   performs exactly what the substep's `do:` says and asserts what a user would see. Any console
   error on the page fails the test.

5. **Brief-gap tests** — for every `not in checklist` unit in PLAN.md `## Brief coverage`, the
   named test in `solution/golden_tests/brief/` (Playwright `page` or plain `httpx`, same
   fixtures). It proves a requirement no grader checks. G4 fails if one is missing or red.

6. **Signed-in pages for the audit** — if the app has a sign-in, write
   `solution/golden_tests/audit.py` so G5 and G6 audit the pages behind it too (they crawl
   anonymously otherwise, and G5 fails when a sign-in exists without this file):

   ```python
   ROUTES = {"member": ["/runs", "/week", "/goal"]}     # where each session starts its crawl

   def login_member(page, base_url):                    # sign in exactly as a user does
       page.goto(base_url + "/login")
       page.get_by_label("Email").fill("<seeded email from the brief>")
       page.get_by_label("Password").fill("<seeded password from the brief>")
       page.get_by_role("button", name="Sign in").click()
       page.wait_for_url("**/runs")

   SESSIONS = {"member": login_member}                  # one per role whose pages differ
   ```

7. **Media** — build the `svg-css` and `seeded-renderer` rows in code. For `fetch` and
   `member-supplied` rows, `"$KIT/golden/bin/golden-media" "$B" --vendor <dir under solution/app,
   e.g. public/media>`: each chosen file is resized to twice its shown width and saved as WebP
   (SVG as-is), with its licence recorded. It prints the credit line for every CC BY file —
   place them on a credits line or page. Inline icon SVGs in the markup (they draw with
   `currentColor`, so they take the text colour and theme with it). Any other media or font file in the app needs a row in
   `_handoff/golden/sources.md ## Assets`. Set `width` and `height` on every `<img>` and a
   `poster` on every `<video>`; G5 fails a picture that does not render, is a flat field, or is
   far larger than its box.

8. **Finish pass** — once every page works, build each `## Finish` row of DESIGN.md on every
   page it applies to: hover and press on every control, a busy state on every submitting
   button, skeletons where data loads, entrances (`@starting-style`) for lists, panels, toasts
   and dialogs, View Transitions between views, the stated depth and surface treatment. Use the
   motion tokens only, name the properties, and check that `prefers-reduced-motion` removes it all.
   Re-run the walkthrough tests afterwards: an entrance must never delay a control a test clicks.

9. **Signature moments** — build every `## Visual ambition` row, to the standard of the
   reference it is borrowed from (`award-caliber-motion`; `webgl-components` /
   `premium-3d-website` for 3D). Decorative engines (Three.js, WebGL, GSAP, Lenis) are npm
   dependencies bundled into the app, never a CDN. Each scene:
   - is created with `failIfMajorPerformanceCaveat: true` and falls back to its stated CSS
     version when that fails — the graders' headless Chromium renders WebGL in software, and
     software WebGL prints console warnings that G5 fails;
   - reserves its box before it loads (no layout shift), caps device-pixel-ratio at 2, pauses
     off-screen and in a hidden tab, and stops under `prefers-reduced-motion`;
   - never covers, delays or intercepts a control (`pointer-events: none` on decorative layers);
   - has a CSS fallback that is striking in its own right (layered gradients, depth, CSS 3D
     transforms, scroll-driven animation): the graders' browser and every screenshot see the
     fallback, so it carries the visual score.

   Then compare: open the reference screenshots beside yours. If yours is visibly plainer, it is
   not done.

## Run

`"$KIT/golden/bin/gauntlet" "$B" --only G4,G5,G6`. G5 audits every reachable page at 320, 390,
834 and 1440px (devtools + axe); G6 measures contrast, text size, `transition: all`, weights and
measure; full-page screenshots land in `evidence/G5/pages/screens/`. **Open the screenshots** —
then run `prompts/critic-visual.md` in a fresh context and fix what it finds.

## Exit

G4–G6 green, critic-visual has no blocking finding, then `golden-status "$B" --advance`.
