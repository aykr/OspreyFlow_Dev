# Slice WS4a · WS4 · The three gates the workspace's move to Sigma 4 is judged by, on Sigma 3 (round 1 merges `away/WS4a`; the owner, 26 November 2026)

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

**The owner's answers to the report's five questions (26 November 2026, 12:15 UTC; `RULINGS.md`):**

- **Q1 (a):** GG2a's merge writes the `sigma` entry in `apps/pages/VERSION_WINDOW.yaml` (workspace 3.0.3, pages 4.0.6,
  the day it opens), and WS4b removes it. **You write no window entry.**
- **Q2 (b): CI's reference set first.** The comparison's references are made on CI's runner before the comparison is
  wired, not on the server's SwiftShader. You **write the diff** that makes them there (the CI step and its upload, beside
  `away/WS4a_diffs/COMPARE_CI.diff`, say which), **for the owner; apply nothing to CI**. Until that set exists, the
  server-made references are not a gate's.
- **Q3 (a): one "ready" moment for both front ends in 0.7.0.** The workspace's budget keeps "mounted", like for like
  with the page service's, for WS4b. **This replaces the owner's 10:35 GG2a Q2 (a)** (no stricter first-frame end is
  built anywhere in 0.7.0). Say in your report where each front end's ready moment is read.
- **Q4 (a), once you add a test for the release-local diff:** `away/WS4a_diffs/I20_RELEASE_LOCAL.diff` (to
  `tools/release_local.py`) has no test. **Add one to the same diff**, in the shape of `tests/test_release_owed.py`'s
  cases: a release is refused, in words naming the entry, while the window lists anything, and is not refused when it is
  empty. **Red first (rule 15):** in a scratch copy of main with the diff applied, the case fails with
  `window_refusal()`'s call removed from `main()` and passes with it; record both runs in your report. The diff, with its
  test, and `I20_PUBLISH.diff` stay diffs for the owner.
- **Q5:** I20's third test (`test_no_sigma_page_merges_in_the_window.py`) comes with GG2a's merge, not here.

Then:

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

`npm test --workspace apps/workspace`; `npm run lint`; `npm run typecheck`; (the I20 script and its two new tests run through the acceptance command: they arrive with the away branch);
`node scripts/no_react_check.mjs`; the two acceptance Python tests and `test_no_react_check.py`, `test_pages_foundation.py`;
`ruff check .`.

## Out of scope

Sigma 4 in the workspace (WS4b); the version-window entry (GG2a's merge, Q1); CI and Makefile wiring (the owner's diffs,
Q2's included); I20's third test, `test_no_sigma_page_merges_in_the_window.py` (GG2a's merge, Q5); applying the release
gates' diffs (yours to extend with Q4's test, the owner's to apply).
