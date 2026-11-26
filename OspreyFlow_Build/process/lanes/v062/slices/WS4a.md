# Slice WS4a · WS4 · The three gates the workspace's move to Sigma 4 is judged by, on Sigma 3 (round 1 merges `away/WS4a`; the owner, 26 November 2026)

> **Start held until the owner answers the away report's questions (the owner, 13:40).**

- **Build id:** WS4 (the React workspace's drawing library; ADR-152 decisions 6 and 9, invariant I20; ADR-002 Amendment 1)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** nothing (the away branch is from main at `41ed4f195`); it may start beside GG2a (the owner's early start, 26 November, about 10:35 UTC)
- **The owner's rulings:** every proposal (a) of `slices/drafts_2026-11-25/WS4a.md` with the 26 November corrections
  (`slices/drafts_2026-11-26/INDEX.md`), as the away round took them (D268). **No Sigma 4 change** (that is WS4b): the
  workspace stays on Sigma 3.0.3 and its lockfile is unchanged.

## Round 1 (D247; the conductor, 26 November 2026): merge `away/WS4a` first

**Your first step: merge the local branch `away/WS4a` into your branch** (the owner fetched it to the Mac). Keep both
sides where main has moved. Its report, `process/lanes/v062/away/WS4a_AWAY_REPORT.md` on that branch, is the record: read
it whole, "What to read first" before anything. **Every figure in it was taken on the server (SwiftShader, under load);
none is a measurement of the Mac or CI.** Its diffs in `away/WS4a_diffs/` (CI, Core Makefile, release, publish) **stay
diffs for the owner: apply none.**

Then, under the owner's answers to the report's five questions (written into this brief before the start):

1. **I20:** `node scripts/same_drawing_versions_check.mjs` green on main's lockfile with `apps/pages/VERSION_WINDOW.yaml`
   empty; `test_same_drawing_versions.py` green, with one of its planted lockfile shapes run again red at the real call
   site (rule 15). **If GG2a has merged before you,** its lockfile fails I20 until the window entry the report gives is
   written: write it only as the owner's answer to question 1 says.
2. **The readiness marks:** `test_no_sigma_class_names_in_the_workspace.py` green and shown red with one `sigma-` class
   name planted; the budget gate (`npm run test:perf --workspace apps/workspace`) green here, its figures recorded with
   the machine and said to be this machine's.
3. **The comparison:** `canvasCompare.test.ts` green; the comparison spec (`npm run test:canvas-compare --workspace
   apps/workspace`) **is not run by you** if its references were made on another WebGL renderer (it refuses): say what
   it answered. It stays out of `test:keyboard` (question 2).

## Acceptance test

`OspreyFlow_Build/tests/glass_trees/test_same_drawing_versions.py`,
`OspreyFlow_Build/tests/glass_trees/test_no_sigma_class_names_in_the_workspace.py` and
`OspreyFlow_Core/apps/workspace/keyboard/canvasCompare.test.ts` (all new on the away branch; none is on main, so they are
red on main and green after round 1's merge).

## Checks (pure; store ports pinned to 9)

`npm test --workspace apps/workspace`; `npm run lint`; `npm run typecheck`; `node scripts/same_drawing_versions_check.mjs`;
`node scripts/no_react_check.mjs`; the two acceptance Python tests and `test_no_react_check.py`, `test_pages_foundation.py`;
`ruff check .`.

## Out of scope

Sigma 4 in the workspace (WS4b); CI and Makefile wiring (the owner's diffs); I20's third test,
`test_no_sigma_page_merges_in_the_window.py` (the report's question 5); the release gates' diffs.
