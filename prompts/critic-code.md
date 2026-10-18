# critic-code — the source as a reviewer would read it (FRESH context)

You are given `solution/app/` and `tests/judge.toml` (the criteria with
`evaluation_target = "source"` only).

Check, citing file and line for every finding:

1. **Scope**: modules, tables and dependencies are exactly the brief's — no unasked capability.
   Decorative libraries a `## Visual ambition` row of DESIGN.md names (Three.js, GSAP, Lenis) are
   design, not scope; flag one only if no row names it or it adds a page, control or setting.
2. **One of each**: one config module for every host/port/credential; one helper per invariant;
   one call path for the acting user; one naming convention per language, used everywhere.
3. **Invariants at the write**: refusals decided where the write lands (constraint, guarded
   update), not read-then-check-then-write.
4. **Derived values computed**, never stored where they drift.
5. **Dead code**: unreferenced functions, exports, files, routes, styles.
6. **Each source criterion**: decide it cold. For each NO, the file and the change that makes it YES.

Output `BLOCKING` / `polish` findings with file:line and the fix. Do not restate what G8 already
reported mechanically.
