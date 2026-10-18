# P2 backend — data, API and a cold deploy

## Skills

`api-contract`, `postgres-bundle`, `integration-sourcing`, `fullstack-guardian`,
`superpowers:test-driven-development`.

## Build

1. **`solution/app/`** in the stack the brief names. `run.json` (`install`, `build`, foreground
   `serve`), `USER_README.md` with the seeded logins the brief pins.
2. **One config module** reading every host, port and credential from the environment
   (`task.toml [environment.env]` names them).
3. The schema: the brief's entities, its constraints enforced **in the database** where the
   brief makes them invariants (unique keys, foreign keys, checks).
4. **One idempotent seed** creating exactly the seed records the brief pins.
5. The API: every endpoint in the brief, exact paths, fields, statuses. Authorisation decided
   on the server. Refusals are a deliberate 4xx with a machine code and a sentence.
6. **`solution/solve.sh`**: copies `solution/app` to `/app`, installs, builds, starts `serve`
   detached, waits for `/api/health`. (Start from the reference task's `solve.sh`.)

Work test-first against `tests/test_output.py`: run G3, read the first failure, fix its cause,
repeat. Do not read ahead and pre-shape the app to test internals.

## Exit

`"$KIT/golden/bin/gauntlet" "$B" --from G0` until G0–G3 are green (G4+ will be red until P3 —
that is expected), then `golden-status "$B" --advance`.
