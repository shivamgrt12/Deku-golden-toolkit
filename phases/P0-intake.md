# P0 intake — understand the contract before writing a line

Most of "perfect" is decided here. An app built on a misread brief fails dozens of checks that
no amount of fixing later converges.

## Read, in this order

1. `instruction.md` — the contract, end to end.
2. `solution/checklist.md` — every obligation as a `C-XX-NN` item.
3. `solution/TRUTH.md` — the ordered path and the checker each step must satisfy.
4. `tests/workflows.yaml` — what is graded, and which substeps are `critical`.
5. `tests/test_output.py` + `conftest.py` — **to learn what is checked, never to decide what to
   build.** The literals you use come from the brief.
6. `tests/judge.toml` — the judged criteria and their yes/no rules.
7. `_handoff/golden/inputs/` — a PRD or captured reference site, if the member supplied one.

## Skills

`brief-to-domain` (domain model, route map, literals ledger), `superpowers:brainstorming`.

## Produce

**`_handoff/golden/PLAN.md`** from `templates/PLAN.md`:

- the domain model (entities = the brief's nouns, nothing more), roles and permissions;
- the route map: every page and every `/api` endpoint, with the checklist ids it serves;
- **a coverage table: every checklist id → where it is satisfied** (route, table, screen,
  rule). Ranges are allowed (`C-OV-01..C-OV-09`). An id with nowhere to live means a gap in your
  plan or an ambiguity in the brief — say which;
- **brief coverage — the brief, not the checklist, is what the golden app must fulfil 100%.**
  `_handoff/golden/brief-units.md` numbers every requirement unit of `instruction.md` (every
  bullet, table row and sentence, B-001 onward) with suggested checklist items. Map every unit
  in `## Brief coverage` to exactly one of:
  - the checklist id(s) that state it — check the suggestion, never copy it blindly;
  - `not in checklist: golden_tests/brief/<file>.py::test_<name>` — the checklist missed it, so
    you write that golden test in P2/P3 and G4 runs it; it is also reported to the bundle author;
  - `context: <why>` — the unit explains or motivates and states no obligation.
  Ranges (`B-040..B-052`) are fine for consecutive units with one mapping;
- the literals ledger: every value the brief pins that the app must reproduce exactly;
- open questions — ambiguities you will NOT guess at; ask the member.

**`_handoff/golden/sources.md`** from `templates/sources.md` — only if `inputs/` holds a PRD or
site. Run `prompts/source-reconcile.md` in a fresh context to produce it: every decision taken
from them, the brief's position on it (must be "silent"), and every conflict found.

## Exit

`golden-status "$B" --advance` — runs the plan lint (every checklist id mapped, no `TODO`) and
the sources lint (no open conflict). Fix what it names.
