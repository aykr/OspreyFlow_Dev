# GG2c away report: the working set's delta client moves to `glass-shared` (26 November 2026, D246 away round)

**Done, 12:10 UTC.** Every case's green is shown; every planted fault but case 7's (an equality) was shown red at its real call site. Two open points: the integration test was not run against a real Conduit, and the perf case is red on `main` itself on this machine (questions 1 and 5). Branch `away/GG2c` in
`~/away-gg2c`, from `origin/main` at `41ed4f195`. Not pushed, not merged; written now, merges only after WS4b (decision
9). Built as drafted (`drafts/2026-11-26:…/drafts_2026-11-26/GG2c.md`), every proposal (a), as the owner ruled. Synthetic
data only. Every test run through `~/osprey-d246/d246_ns.sh` (nice 19, its own network namespace, no containers).

## What changed

- `git mv` of `apps/workspace/src/workingset/{deltaClient.ts, deltaClient.test.ts, deltaOps.test.ts}` to
  `packages/glass-shared/src/workingset/`. In the client only the header (lines 6 to 23: how each front end authenticates
  the socket today, the workspace's `?ticket=` from `POST /v1/ws-ticket` and the page service's proxy in
  `apps/pages/server/stream.ts`, each cited) and its one import (now `./models`) changed. The behaviour code is
  byte-identical. In `deltaClient.test.ts` the type import of `WorkingSetDelta` became `./models` too (the package does
  not import itself by name); `deltaOps.test.ts` is unchanged.
- `packages/glass-shared/src/index.ts`: `export * from "./workingset/deltaClient"`, plus its line in the header's list.
  The export names collide with nothing already in the package (checked).
- `apps/workspace/src/App.tsx`, `apps/workspace/keyboard/view-over-cap-harness.tsx` and
  `apps/workspace/src/workingset/deltaClient.integration.test.ts`: imports only, now from `@ospreyflow/glass-shared`. The
  integration test stays in the workspace (proposal 1a).
- New tests: `packages/glass-shared/src/workingset/deltaClient.exports.test.ts` (case 1: through the package's entry,
  names the exports and drives a fake socket end to end) and `apps/workspace/src/workingset/deltaClientHome.test.ts`
  (case 4: no copy of the client or its unit tests is left in the workspace, and no workspace file imports a
  `deltaClient` module by a relative path; its third case shows the pattern finding each stale shape). The second file
  is not in the draft's file list. It is needed because nothing else fails for case 4 (P4 below).
- No socket factory for pages (proposal 3a). No scan row: the scan-map rule covers new tests under
  `OspreyFlow_Build/tests` only, and every test here is under `OspreyFlow_Core`.

## Commits

| Commit | What |
| --- | --- |
| `fb73ef417` | case 1's test, red: the package does not export the client (2 failed, run 10:22 UTC) |
| `e68109363` | the move, the index, the importers, the header |
| `60f744f69` | case 4's guard test |
| `faed151b1` | the guard leaves its own file out of the importer scan (the full run's one red, below) |

## The table of cases

Planted faults by `~/osprey-d246/gg2c/plants.py`: each one planted at its real call site, the gate run, the tree restored
by `git checkout` and checked clean. Logs are in `~/osprey-d246/gg2c/plants/`.

| # | Case | Green (at `faed151b1`) | The planted fault, and what showed it red |
| --- | --- | --- | --- |
| 1 | The package exports the client | `deltaClient.exports.test.ts` 2/2 | red at `fb73ef417` before the move; **P1**: the index's export line removed, then the test is red (`expected 'undefined' to be 'function'`) and `npm run typecheck` is red (`App.tsx(192,3): TS2305 … no exported member 'connectDeltaClient'`) |
| 2 | The moved unit tests | in the package's suite: `deltaClient.test.ts` (6), `deltaOps.test.ts` (4) | **P2**: a copy of the unit test left in the workspace with its old import. The workspace's vitest is red (`Cannot find module './deltaClient'`) and so is the case 4 guard. **`test_file_coverage_check` stayed green (exit 0)**: it reads only Python tests and `ci.yml`, so the draft's "the file-coverage check finds it" is wrong (question 2) |
| 3 | No React or drawing library in the package | `no_react_check.mjs` PASS, `version_isolation_check.mjs` PASS, lint green | **P3-react**: `import "react"` in the moved client. `no_react_check` FAILs (`deltaClient.ts imports react`, the package reaches `node_modules/react/…`) and eslint is red (`no-restricted-imports`, I1). **P3-sigma**: `import "sigma"`. `version_isolation_check` FAILs (`packages/glass-shared sigma@3.0.3`) and eslint is red. **P3-maplibre-type**: a type-only import. `version_isolation_check` PASSes, as its header says it cannot see types; eslint is red (I13) |
| 4 | The workspace's importers | `deltaClientHome.test.ts` 3/3 | **P4**: a copy of the client kept in the workspace, and `App.tsx` importing it. The guard is red on both its cases. **`npm run typecheck` stays green**, so only the guard finds this |
| 5 | Gap detection unchanged | `deltaClient.test.ts` 6/6 in the package | **P5**: the sequence check's condition replaced with `false`. Red: `a real gap after a snapshot asks for a resync`, `expected [] to deeply equal [ 2 ]` |
| 6 | The integration test | **not run against a real Conduit**: D246's namespace refuses containers and holds no stack lease. Run anyway: its import resolved; `beforeAll` failed with `ECONNREFUSED 127.0.0.1:<port>` and the file failed (exit 1). Vitest prints its 3 cases as "skipped", but the file fails and the run exits 1, so this is a failure, not a skip | **P6**: the import pointed back at `./deltaClient`. `npm run typecheck` is red (`TS2307 Cannot find module './deltaClient'`), and `test:integration` is red at import (`Cannot find module`), before any server is involved |
| 7 | I11 | see the next section | none: an equality |

## I11: the workspace's whole suite and its budget, before and after, one machine

Machine `gpu-1`, 16 CPUs, Node 22.23.5. "Before" is a detached worktree at `41ed4f195` (`~/away-gg2c-base`, its own
environment); "after" is this branch. Both ran with `OSPREY_PORTS_SLOT=0`: a linked worktree has no row in
`lane_ports.tsv`, and each namespace run has its own loopback, so no other run can meet its ports (question 3). Logs are in
`~/osprey-d246/gg2c/{before,before2,after}/`.

| Step | Before (`41ed4f195`) | After |
| --- | --- | --- |
| workspace vitest | 409 files, 3964 tests passed | 408 files (2 moved out, 1 added), 3957 tests passed (−10 moved, +3 guard) |
| workspace budget config | 3/3 passed (load ≈ 2) | 2/3 in the full run: `MatrixView.budget` opened in 2782 ms against a 2500 ms limit (load ≈ 13). See below |
| glass-shared vitest | 3 files, 463 tests | 6 files (3 moved in or added), all passed |
| typecheck, lint | green | green |
| `no_react_check`, `version_isolation_check` | PASS | PASS |
| keyboard (`keyboard.spec.ts` and the rest) | 1514 passed, 5 skipped | 1514 passed, 5 skipped |
| a11y | 1222 passed | 1222 passed |
| perf (`perf.spec.ts`) | **red before the change**: 3 passed, 1 failed. Sweep 9011.7 ms/frame (re-run: 7549.8) against `< 3000`; first frame 11493 ms (re-run 12409), passed | the same case red: sweep 6475.9 ms/frame; first frame 15143 ms, passed |

**The budget's one red is the machine's load, not the move.** Run three times on each tree, interleaved, at load ≈ 10.5:
before failed 3 of 3 (2891, 2652, 2899 ms); after failed 2 of 3 (2800, 2819 ms, one pass). `MatrixView` does not import the
delta client.

**The perf sweep is red on `main` itself on this machine**, at nice 19 under software rendering. Before and after fail the
same one case and pass the same three. The budget half of I11 is therefore shown equal here, not green (question 1).

## Other checks

- `doc_citations_check` (and so `test_doc_citations_check.py::test_the_repository_itself_is_clean`): **red on `main`
  too**. The same two findings appear on the baseline tree at `41ed4f195`: `process/lanes/v062/slice-line/README.md:131` cites
  the line's test runner (run.sh) by a short path under tests/, where no such file exists. This branch does not touch that file. The other 9 cases of
  `test_doc_citations_check.py` pass. The moved paths add no broken citation.
- `test_file_coverage_check`: green (1295 files, no drift).

## Findings beside the slice

1. **`apps/workspace/keyboard/*.tsx` is outside `tsconfig.json`'s include**, so `npm run typecheck` never reads the
   view-over-cap harness. A broken import there fails only the keyboard run's bundle.
2. **The integration test's header still says it is "skipped automatically (not failed)"** (:11-13). It fails. It is left
   as it is: the draft gives that file imports only.
3. `drafts_2026-11-25/GG2b.md:45` cites the client's old path. It is a dated draft that recorded `main` as it was then, so
   it is left as it is.

## Questions for the owner

1. **The perf gate is red on `main` on this machine** (sweep 7.5 to 9.0 s per frame against 3 s). Is before-equals-after
   on the same machine an acceptable I11 proof here, or must the budget half be run where `perf.spec.ts` is green (CI, or
   the owner's machine)?
2. **Case 2's planted fault, as drafted, cannot be shown red**: `test_file_coverage_check` does not read TypeScript tests.
   In this build the workspace's own vitest run and the new guard test catch it. Should the slice's table be corrected to
   say so, or is a TypeScript half of the coverage check wanted (a separate slice)?
3. **Away worktrees have no row in `lane_ports.tsv`.** Is `OSPREY_PORTS_SLOT=0` inside a D246 namespace acceptable, or
   should away rounds get a row?
4. **The guard test `deltaClientHome.test.ts` is outside the draft's file list.** Keep it, or have the move proved some
   other way?
5. **Case 6 against a real Conduit** needs the stack, so it waits for the seat's container checks or a lease holder's
   `npm run test:integration --workspace apps/workspace`. Who runs it before the merge?
6. **`main`'s `doc_citations_check` is red** (`slice-line/README.md:131`, a short path to run.sh that names no file). That
   belongs to whoever owns the slice-line README, not to this slice. It is noted here so the merge gate's red is not blamed on
   GG2c.

## Round 1 in the line, on the Mac (26 November 2026, D247)

`away/GG2c` was merged into `lane/slice-GG2c` (`6295f58`, no conflict, on `f9b9d54`). **Everything above this section was
measured on the server.** This section is the Mac's own: Node 24.10.0 (the server ran 22.23.5), Playwright slot 21, load
averages between about 8 and 45 while it ran. The report's lines above are as the server wrote them, except the two
quotations of `main`'s broken citation (below).

| Step | The server (after) | The Mac (this branch) |
| --- | --- | --- |
| frozen acceptance | cases 1 and 4 green | the guard 3/3, the export test 2/2 |
| workspace vitest | 408 files, 3957 tests | the same: 408 files, 3957 tests |
| workspace budget config | 2/3 in the full run (`MatrixView.budget`, machine load) | **3/3** |
| glass-shared vitest | 6 files, all passed | 6 files, 475 tests passed |
| typecheck, lint, `no_react_check`, `version_isolation_check` | green | green |
| `test_file_coverage_check` | green, 1295 files | green, 1296 files |
| keyboard | the whole run: 1514 passed, 5 skipped | **only** `view-over-cap.spec.ts` and `views.spec.ts` (the harness this slice edits): 37 passed. The whole run was not repeated |
| a11y | the whole run: 1222 passed | **only** `every-harness.spec.ts` for `view-over-cap-harness.html`: 8 passed. The whole run was not repeated |
| perf | red before and after | **not run** (the owner's question 1) |
| integration test (case 6) | failed, `ECONNREFUSED` | **not run**: it needs the stack, and no lease was taken (the owner's question 5) |

**The frozen acceptance, red on the Mac.** With the client, its unit tests, the index and the three importers put back to
`f9b9d54`'s text and the two new tests kept: the guard failed 2 of 3 (four files left in the workspace; `src/App.tsx` among
five relative importers) and the export test failed 2 of 2 (`expected 'undefined' to be 'function'`).

**The planted faults, run again on the Mac** (each file's bytes saved and written back, the tree checked clean after each):
P1, P2, P3-react, P3-sigma, P3-maplibre-type, P4, P5 and P6 each gave the result the table above records, including the two
that stay green (`test_file_coverage_check` under P2, `typecheck` under P4; and `version_isolation_check` under the
type-only import). P6's `test:integration` half was not run (case 6).

**Case 2, corrected (question 2, ruled (a)).** What catches its plant is the workspace's vitest run and the guard test
`deltaClientHome.test.ts`. `test_file_coverage_check` reads no TypeScript. The draft's table now says so. A TypeScript half
of that check is not this slice's.

**Question 4, ruled (a):** the guard test is kept.

**The citation check (question 6).** Hand-back 61 (`b72aaba`) fixed `main`'s own red: the README is no longer reported. But
on the merged branch the check was **still red, on this report's own two quotations** of the broken path (once at "Other
checks", once at question 6): `away/` is not one of the folders the check skips. Both are reworded here, and the check is
green on this branch. The slice's frozen checks do not run it; the merge's full gate does.

**Still open, the owner's:** questions 1, 3 and 5. Nothing was built for them.

## Round 2 in the line, on the Mac (26 November 2026): the guard walks the whole workspace

**The verifier's finding.** `deltaClientHome.test.ts` walked a hand-written list of folders. `deck-capture/`,
`compute-tier1/`, `scripts/`, `test/`, `map-build/` and the workspace's root files were not on it. **Reproduced first:** with
a copy of the client and a harness importing `../src/workingset/deltaClient` planted in `deck-capture/`, the guard passed
3 of 3.

**The fix.** The guard walks the whole of `apps/workspace`, skipping only `node_modules` and `dist`. It also reads `.jsx`
and `.cjs`, knows a copy or an import of any source extension (before, a `.js` copy or a `./deltaClient.js` import passed),
and fails on a folder it cannot read instead of passing over it. Its new case runs the same scan and the same two
detectors over a planted temporary tree, a folder nobody has made yet included; it was red against the list (`3617c43`).

**Planted again at the real call sites** (the tree checked clean after each): stale files in `deck-capture/`,
`compute-tier1/`, the root and a new folder turned both real cases red; a stale import added to
`deck-capture/fraud-timeline-harness.tsx` turned the import case red.

**The frozen checks, on this fix:** exit 0. `glass-shared` 475 tests; the workspace 3958 tests (round 1's 3957 and the new
case) and its budget config 3/3; lint, typecheck, `no_react_check` and `version_isolation_check` green. The frozen
acceptance: the guard 4/4, the export test 2/2. Keyboard, a11y, perf and the integration test were not run in this round:
it changes the guard test alone.
