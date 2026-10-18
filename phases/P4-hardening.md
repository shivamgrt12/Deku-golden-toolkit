# P4 hardening — no errors under abuse

## Skills

`secure-code-guardian`, `fullstack-guardian`.

## Write `solution/golden_tests/abuse/test_*.py`

The edges the generic probe cannot know, derived from the checklist's `role`, `data` and
`constraint` items. At minimum, for each that applies:

- **concurrency**: N simultaneous requests for the same last unit / unique key / remainder →
  exactly one success, the rest a clean refusal, no 5xx;
- **replay**: a repeated idempotency key or action creates no second record — anywhere,
  including the external system (inbox, payments, object store);
- **authorisation**: a lower role, another tenant, no token, a forged token → refused, and the
  protected state unchanged;
- **invalid input**: unknown and malformed ids, wrong types, below-minimum values, missing
  preconditions → refused before any lookup;
- **immutability**: what the brief freezes cannot change by any route or role;
- **money**: integer minor units round-trip exactly.

Use the fixtures `base_url` and plain `httpx`; every literal from the brief. Worked example:
`golden/selftest/fixtures/reference_golden_tests/abuse/`.

## Run

`"$KIT/golden/bin/gauntlet" "$B" --only G7` — your suite, plus hostile input against every
endpoint the brief names; any 5xx, dropped connection or error line in the server log fails.

## Exit

G7 green, then `golden-status "$B" --advance`.
