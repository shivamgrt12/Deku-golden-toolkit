# PLAN — <task name>

## Domain model

| Entity | Fields that matter | Owned by | Invariants (enforced where) |
|---|---|---|---|
| | | | |

## Roles and permissions

| Role | Can | Cannot (refused at the API with) |
|---|---|---|
| | | |

## Routes

| Route | Kind (page / api) | Serves checklist ids |
|---|---|---|
| | | |

## Coverage

Every checklist id, and where it is satisfied. Ranges are allowed (`C-OV-01..C-OV-09`) when one
place satisfies all of them. The plan lint fails any id missing from this table.

| Checklist ids | Satisfied by |
|---|---|
| | |

## Brief coverage

Every requirement unit of `instruction.md` (listed, numbered and with suggestions in
`_handoff/golden/brief-units.md`), and how it is fulfilled. Ranges are allowed
(`B-040..B-052`). Each row is exactly one of:

- checklist ids that state it (`C-UF-01, C-UF-02`) -- the graders check it;
- `not in checklist: golden_tests/brief/FILE.py::test_NAME` -- a checklist gap; our own
  golden test proves it, and it is reported to the bundle author;
- `context: REASON` -- the unit explains or motivates and states no obligation.

The plan lint fails any unit missing from this table.

| Brief units | Fulfilled by |
|---|---|
| | |

## Literals ledger

Every value the brief pins that the app must reproduce exactly (accounts, passwords, statuses,
copy, counts, seed records).

| Literal | Where the brief pins it | Where the app uses it |
|---|---|---|
| | | |

## Open questions

Ambiguities you will not guess at. Each is asked of the member before P2.

- none
