# WS4b: the workspace on Sigma 4 (the owner's rulings D280 to D286, 26 and 27 November 2026)

**Build WS4. Round 1 merges four away branches** (D247), in this order:
1. `away/WS4b`: the port itself.
2. `away/WS4b-perf`: the perf experiments.
3. `away/WS4b-look`: the accepted look.
4. `away/WS4b-speed`: the speed work.

All four are on the `server-backup` remote (`git fetch server-backup away/WS4b away/WS4b-perf away/WS4b-look away/WS4b-speed`). Read their reports first: `process/lanes/v062/away/WS4b_AWAY_REPORT.md`, `WS4B_PERF_REPORT.md`, the look round's report, and `WS4B_SPEED_REPORT.md`.

**This slice starts only after WS4a is merged.** Decision 9: only GG2c merges before WS4b. The comparison's Sigma 3 references and its command are WS4a's.

## The owner's rulings this slice carries out

1. **The look (D286):** accepted as drawn on `away/WS4b-look`.
   - The export carries every link.
   - Link labels are written beside the line, as Sigma 3 wrote them, through a local 2D edge-label layer on Sigma 4.
   - Everything else is Sigma 4's own drawing.
2. **The speed (D282), as built on `away/WS4b-speed`:**
   - Q1 the label-side fix stays.
   - Q2 the reducers are declared as reading item state, with one refresh when the camera stops, and a test that fails if Sigma's private field moves.
   - Q4 link picking only from the neighbourhood band in; keyboard link selection unchanged.
   - Q5 the chunked texture refresh for `@sigma/node-image` 4.
   - Q7 the Conduit's expansion figure stands; no new gate.
   - Q8 community links are judged again after Q2 and Q4.
3. **Q3 (D286): `pickingDownSizingRatio` is 4.** WS4b-speed measured it: better pointing than 2, and faster. **Add a test on the smallest drawn node, at its edge:** hover and click there find it. Make it red first, with the ratio planted back at 2 or 8 at its real call site (rule 15).
4. **The canvas-look references** are remade on this look with WS4a's command, under the reason **"Sigma 4's look, accepted by the owner on 27 November 2026"**. Commit the new references and the command's record.
5. **Two diffs for the owner's approval before this slice merges.** Write both as files and change no decision record yourself. End the round's report with **"WAITS: the owner's approval of WS4B_ADR152_DECISION9.diff and WS4B_WEBGL2.diff"**.
   - `process/lanes/v062/WS4B_ADR152_DECISION9.diff`: ADR-152 decision 9's amendment, which records what moved to Sigma 4, the look accepted, and the speed figures (Q6 below).
   - `process/lanes/v062/WS4B_WEBGL2.diff`: the WebGL 2 requirement (D280 Q2), where the spec states the browser floor.

## Q6, the figures to carry (WS4B_SPEED_REPORT.md)

Three interleaved runs each, on the server:
- **The first frame passed in every run of this branch** (19.1 to 24.2 s), and failed in every run of the tree before (34.1 to 35.3 s).
- **The sweep is about three times as fast** (3.5 to 3.8 s a frame, against 8.4 to 10.6 s), but **still red against its 3 s.**
- **Community links are red in both,** as before.

The gate is not changed (D282 Q6). The merge's full gate and CI judge it. **Say in your report which perf specs are red at your tip, and give their figures. Never loosen a budget.**

### The two speed items (the owner, 27 November 2026, about 09:40; never accepted narrower)

1. **The sweep.**
   - **Round 1 measures it again, with `pickingDownSizingRatio` at 4**, using `perf.spec.ts`'s sweep. Give each run's figure per frame, three runs if the machine allows.
   - The budget itself is judged on **CI's runner (three runs)** and once on **the owner's Mac** (D280 Q6). The conductor takes CI's figures after round 1, and the owner runs the Mac measurement.
   - **If the sweep still misses on CI after ratio 4, the slice stops.** The conductor brings the owner the figures, with WS4c (ADR-119's lever) as the option.
   - Do not change any gate or budget, and do not start WS4c's work here.
2. **Community links (`perf/community-links.spec.ts`).**
   - Round 1 runs it and records its result.
   - **If it is still red after round 1, round 2 takes it** (WS4b-perf's Q8): its own fix, red first, with nothing loosened. Round 2's instructions come in this brief, or in the verifier's findings.

## Acceptance test

`apps/workspace/src/canvas/reducerDependency.test.ts` and `apps/workspace/src/canvas/linkPicking.test.ts`, both from `away/WS4b-speed`. They are new and red on main, and green once the four branches are merged. Add the Q3 edge test beside `linkPicking.test.ts`, or in its own file, and name it.

## Checks

The workspace's unit tests, lint, typecheck, `no_react_check`, the glass-trees version-window and class-name tests, and `ruff` (the row). The keyboard, a11y and perf Playwright suites are run by the merge's full gate.

## Out of scope

- GG2a's pages, already on Sigma 4.
- WS4c, which comes only if the budget still misses after this slice.
- Any change to a budget's figure.
