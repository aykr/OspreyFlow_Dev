# studio lane · report · L1.2 (phase 6: the canvas as editor, the Map editor, guided mode), 7 November 2026

1. **Met in the harness, not yet walked live: the reports pipeline built from scratch in guided mode.** Proved by keys alone in `keyboard/ingest-studio.spec.ts`, "the reports pipeline is built from scratch in guided mode by keyboard". The walk is: name it, choose its registered source, Preview the rows, map a report to a Document with the keyboard bind, Test, then Deploy as v1. Expert mode opens the same drawer from the canvas ("a step's drawer opens beside the canvas…").
2. **Met: `MapScreen` tests migrated and green.** The five files are now `map/MapEditor.*.test.tsx`, with the same assertions run against the Map editor. Vitest passes 2601 of 2602. The one failure is `matrix/MatrixView.budget.test.tsx`, a timing budget that took 3.9 s against 2.5 s under full-suite load; it passes alone, and this branch doesn't touch matrix.
3. **Met: keyboard green.** Full suite 539/539. There are ten new cases, each shown red with its handler removed, plus a planted lost save of the mode choice.
4. **Met: axe green.** Full suite 352/352. There are eight new Studio states, each scanned in dark, light and GOV.UK.
   - The scan found a real defect: bound Map columns were faded below 4.5:1 contrast. They are now outlined and labelled "bound".
5. **Met: Preview access test (rule 4).** `tests/ingest/test_node_preview_access.py` was shown red on each read path by switching off that path's masking.
6. **Met: spec 09 updated.** §1.0 and §4 are updated, and the §4 keyboard-bind gap is closed. ADR-140 Amendment 8 is written and its reservation is marked `written`.
7. **Met: friction fragment.** `process/friction/2026-11-07-studio-phase-6-canvas.md`.
8. **Left:**
   - *Show YAML* is not built.
   - No live walk was done against the dev stack (no lease taken).
   - The SAME_AS score waits for phase 8 (your Q2 a).
   - The mode is kept per browser (your Q1 a).
9. **Commits** (11, on `13a77d1`): `65785b4` (the access test), `b8a3f78` (Preview and the mode preference), `d75c09b` (the drawer and guided list), `ba5d0b5` (the Map strip and keyboard bind), `440a1bc` (the fixes), `795b0f3` (the test migration), `0b9aafe` (the keyboard and axe cases), `e83a35e` (spec 09), `b04566d` (Amendment 8), `bbb844f` (the friction row), and this report.
10. **Request: `keyboard/actionRegistry.ts`.** Apply `process/lanes/studio/L1.2_action_registry.diff` with `git apply OspreyFlow_Build/process/lanes/studio/L1.2_action_registry.diff` from the repository root. It adds the ten ids; with them in, `ingest-studio.spec.ts` passes 26/26.
11. **Request: `OspreyFlow_Core/DEMO_GUIDE.md` chapter 4** (not this lane's file). It should say that the pipeline opens in guided mode, that Test and Deploy open in the drawer, and that Map has a strip and *Choose* / *Bind here*.
12. **Questions for the owner:** none.
13. **Hand check, no stack needed.** From the repository root: `cd OspreyFlow_Core/apps/workspace && npx vite --port 5185`.
    - Open http://localhost:5185/keyboard/ingest-studio-harness.html. Click *Open Visit bookings*, then *Source: Call log*, *Preview* and *Run preview*.
    - Then *Map: Map*, *Open map editor*, *Choose* on "called", *Entity 1*, and *Bind called here: name*.
    - Then *Expert* and *Test*.
    - Repeat with `?brand=govuk` added to the URL.
14. **Running:** nothing of mine. No dev stack, no lease, no background jobs.
