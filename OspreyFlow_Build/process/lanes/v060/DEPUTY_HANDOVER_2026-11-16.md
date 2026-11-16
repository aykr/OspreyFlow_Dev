# v0.6.0 · the deputy orchestrator's handover (16 November 2026, ~11:30Z)

The owner, 16 Nov: the orchestrator's account (ayan) is low on tokens; merge and coordination work moves to a sol
lane. **case is the deputy orchestrator** from now until the release. The orchestrator keeps only: stage 5 (the
release, public), the GOV.UK rebuild's trigger, and the owner's one-line reports. Read `process/CLAUDE.md` rule 14,
`v060/RULINGS.md`, `v060/OWNER_WORD_IN_ADVANCE_2026-11-15.md` and the top of `MORNING.md` first.

## What the owner has given (standing)
- Take the recommended option; record it (MORNING.md or the record) and report after. Still the owner's: anything
  disrupting the GOV.UK demo, a key or secret they must type, a permission refusal, dropping or deferring what an ADR
  or the client page requires.
- **For this handover the owner lets the deputy merge to main and push** (ADR-142's "only the orchestrator merges"
  delegated by the owner, 16 Nov). One push at a time; a push cancels the running CI (concurrency group), so push
  only when CI on main has finished or the run is superseded on purpose.
- Never commit `OspreyFlow_Core/osprey.yaml`. No .github or Makefile change without the owner. Synthetic data only.
  Never pkill by pattern. Pure test lines carry `ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9`.

## Where things stand
- **ea5fc61**: CI green (run 43842428591). platform-b's package test on it is at row 8 of 11, finishing ~12:00Z. It
  is the **fallback release** if the Glass candidate trips.
- **The Glass rows join v0.6.0** (the owner, 16 Nov). Merged in `~/dev/osprey-wt/merge2`, NOT YET COMMITTED:
  - committed there: `e27a820` (case's B, three conflicts resolved: the decision log and reservations kept both
    sides; the user guide's history row became 1.74; OWNER_BRIEF:23's citation made plain text);
  - staged on top: case-b's A+C merge (`--no-commit`), its `registry.patch`, the guide 1.74 row extended for §5.2,
    the CHANGELOG's Glass entry ("Fewer rows above the graph"), the user guide PDF reprinted (the other three PDFs
    and manifest entries restored).
  - Passed on that tree: tsc, eslint, 303 guide/spec/docs/changelog tests, citation, ADR reservations, test-file
    coverage, `scripts.changelog_check --tag v0.6.0`.
  - Owed: the whole vitest (`npx vitest run --root apps/workspace`), the whole keyboard suite
    (`OSPREY_PORTS_SLOT=20 npx playwright test --config apps/workspace/keyboard/playwright.config.ts --workers 8`)
    and every-harness (`… --config apps/workspace/a11y/playwright.config.ts`) from `OspreyFlow_Core`.

## The deputy's next steps
1. Take over `~/dev/osprey-wt/merge2` (the orchestrator has stopped its runs there). Do not reset it. Link
   `OspreyFlow_Core/node_modules` to the main checkout's if missing. Run the three owed suites. Green: commit
   (`merge: case-b v061 glass-rows A+C into v0.6.0 …`), add LANDED.md rows for both merges (`e27a820 36e05c8 case
   v061-glass-rows`, `<A+C merge> 30edfaf case-b v061-glass-rows-ac`), mark progress rows done, `merge --ff-only` main
   in the main checkout, push. Red: fix at merge if trivial, otherwise tell the orchestrator in one line.
2. Send platform-b the exact pushed commit as the new C: stage 3 items, then stage 4 from row 0 on it once ea5fc61's
   run has ended and been recorded. Update `route.tsv` (c3 and 4g) and the stages (`lanes_heartbeat.sh stages`).
3. Watch CI on it (`gh run watch <id>`). A flake: `gh run rerun <id> --failed` once the run completes, with the
   reason recorded in CARRIES.md. Known flakes: rule-audit 503, typology tx-expiry, worker-isolation live red,
   map-view.spec camera.
4. platform-b's §2 stops come to you. Tooling-only, C unchanged, red-then-green: platform-b proceeds itself. A product
   finding: decide by the recommendation (fix now if it would hurt a client; else v0.6.1 list in `v060/RULINGS.md`),
   then tell the orchestrator in one line.
5. Keep the heartbeat true: route.tsv, progress.tsv, owner_due.tsv, each lane's stages.
6. When **CI is green and the package test has passed on the same C**, message the orchestrator: "release-ready
   <C>". The orchestrator runs RELEASE_STEPS.md with that C.

## After the release (still the deputy's)
- Resume the demo lane on sol for the GOV.UK rebuild (`demo/REBUILD_2026-11-18.md`), then put the Gemini key
  command at the top of MORNING.md and the item back in owner_due.tsv.
- Merge platform-b's tooling branch (lane/platform-b-v060-chart-before-listing) and rules-b's focus-move audit
  (lane/rules-b-v060-focus-move-audit, 74cc258).
