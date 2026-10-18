# P-1 triage — is the bundle itself sound?

A perfect app cannot pass a broken bundle, and every bundle leaves genkit "never proven
solvable". Spend two minutes here before spending hours building.

## Do

1. `"$KIT/golden/bin/gauntlet" "$B" --only T0`
2. Read every finding. T0 checks that `workflows.yaml` parses, every declared slot is in
   `[metadata.services]`, every cited test exists, every route a test requests is named in the
   brief, and no browser substep needs something the grader cannot do (a second tab, a
   download, an inbox, a long wait, two actors at once).
3. A **blocking** finding is a bundle defect. Do not work around it in the app. Describe it to
   the member — the file, the line, why a correct app fails — so it is routed to the bundle
   author. The member may waive one with a reason (`FIX-PROTOCOL.md`, Waivers).
4. **Advisory** findings (a judged criterion that points at the brief) go in your notes for P6:
   they predict criteria the judge may hold back.

## Exit

`golden-status "$B" --advance` — T0 green (or its blocking findings waived).
