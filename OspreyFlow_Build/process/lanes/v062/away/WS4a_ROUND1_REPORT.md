# WS4a, round 1: report (26 November 2026, the builder on the owner's Mac)

`away/WS4a` is merged into `lane/slice-WS4a` (no conflict). The away round's report is `WS4a_AWAY_REPORT.md` beside
this one. **Every figure below was taken on the owner's Mac while other seats ran on it** (Apple M3 Pro, 12 CPUs,
36 GB, macOS 26.7.3, Node 24.10.0 where CI uses 22; load averages 12 to 47). None is a CI figure or a quiet-machine
one. The workspace stays on Sigma 3.0.3 and `package-lock.json` is as on main. Nothing in CI, no Makefile, release
script or publish script was changed. Synthetic data only.

## The owner's five answers

| Question | Done |
| --- | --- |
| Q1 (a), GG2a's merge writes the window entry | No entry written; `windows: []`. GG2a has not merged: `apps/pages` on main pins no Sigma. A trial merge of `lane/slice-GG2a` (`37492cc`) into this branch has no conflict, its `perf/` edits included |
| Q2 (b), CI's reference set first | `WS4a_diffs/COMPARE_CI_REFERENCES.diff`, for the owner (below). Nothing applied; the server-made references gate nothing |
| Q3 (a), one "ready" moment | The workspace keeps "mounted". Where each is read, and one difference, below |
| Q4 (a), a test for the release-local diff | Added to `WS4a_diffs/I20_RELEASE_LOCAL.diff`, red then green (below). It and `I20_PUBLISH.diff` stay the owner's |
| Q5, I20's third test with GG2a's merge | Not built |

## Q2: `COMPARE_CI_REFERENCES.diff`, and which diff when

1. **Apply `COMPARE_CI_REFERENCES.diff` first.** It adds three temporary steps at the end of CI's
   `glass-perf-a11y-keyboard` job: make the ten references on the runner, upload them as the artifact
   `canvas-compare-references`, and compare Sigma 3 with them three times (for the tolerance). None can turn the job
   red. The committed set is removed first, so the upload can only be the runner's. Every CI run makes a new set until
   the steps go (about 3 minutes more a run, going by this Mac); take any one run's. Not a `workflow_dispatch` job
   in `ci`, whose runs `release_green.py` would count for a commit, nor a second workflow, whose runs on main
   `watch-github` would read as main's latest.
2. Commit that artifact's ten pictures and `REFERENCES.json` to `keyboard/canvas-compare/`, put the three runs'
   figures in `TOLERANCE.json`'s `set_from`, and take the three steps out.
3. Then apply `COMPARE_CI.diff`, and `COMPARE_CORE_MAKEFILE.diff` after `I20_CORE_MAKEFILE.diff` (it does not apply
   without it).

**One choice for the owner to see before applying:** `make-references.mjs` refuses under CI. The step runs it with
`env -u CI`, which lifts that for that one command. If you would sooner have the command take a named switch of its
own, that is a code change, not made here.

**Rehearsed, not run on CI** (`WS4a_records/rehearse_compare_ci_references.py` and `.log`): the steps' own text, with
`CI=true`, on this Mac. Without `env -u CI` the command refused (exit 2); with it, ten references; three
self-comparisons, 0 pixels differing at all in every scene; the committed references restored byte for byte. Left
out: the `git config user.name` line (it would write the shared repository config) and the upload action.

## Q3: where each front end's ready moment is read

- **The React workspace.** `markRenderer` (`src/canvas/canvasMarks.ts`), called by `GlassCanvas.tsx` once the renderer
  and its community-link layer are made, sets `data-canvas-state="mounted"` on the "Network canvas" element.
  `perf/harness.tsx` watches for it and sets `window.__PERF__.readyAt`; `perf/perf.spec.ts` waits for that. The gated
  figure is `elapsedMs`, from before `page.goto` until the wait returns.
- **The page service** (GG2a's, not on main; read on `lane/slice-GG2a` at `37492cc`, so its files are named here by
  folder). `mountGraph`, in the `graph` folder of the pages' `modules/`, sets `data-graph-state="ready"` and the mark
  `graph-ready` after one more scheduled render's `afterRender` and the animation frame after it. Its perf spec (the
  pages' `test/perf/` folder), `ready()`, waits for that selector; the gated figure is `elapsedMs` in `open()`.
- **They are not the same instant, and this slice changes neither.** Sigma 3.0.3's constructor calls `refresh()`,
  which renders at once, so "mounted" comes after the first draw but before the browser is known to have shown it. The
  page's "ready" is later by one render and one frame (its own comment: the figure "errs slow"). For WS4b the
  workspace's mark is like for like between Sigma 3 and Sigma 4 as long as Sigma 4 also draws in its constructor
  (GG2a's module says 4.0.6 does; not tried here in the workspace). Also, each gate's wall-clock figure ends only
  when the browser answers: here the workspace's was 11,280 ms against a `readyAt` of 3,221 ms, with three long frames
  after `readyAt`.

## Q4: the release-local diff's test

The diff now also changes `tests/test_release_owed.py`; its `release_local.py` half is byte for byte the away
round's. Two cases run the real `same_drawing_versions_check.mjs --release` over a copy of the real lockfile: with
GG2a's shape of Sigma 4.0.6 pin **listed** in the window (the merge check would pass), the release is refused before
anything is built, in words naming `sigma`, both versions and the day; with `windows: []`, it goes on.

`WS4a_records/plant_release_window.py` and `.log`, in a scratch copy with the diff applied:

| Run | Result |
| --- | --- |
| The diff applied | 9 passed |
| `window_refusal()`'s call removed from `main()` | **1 failed**: the refusal case (`main` returned 0, not 1) |
| `window_refusal()` refusing whatever the window holds | **2 failed**: both new cases |
| Restored | 9 passed |

The scratch copy is this branch's tree (main with this slice): main without it has no check script to ask.
`release_local.py` and `test_release_owed.py` are the same on main and here, and the diff applies to them. The two
files have four lint findings before the diff and the same four after.

## The three gates

**I20.** The script passes on the lockfile with the window empty, with and without `--release`. Planted again at the
real call site: Sigma 3.1.0 nested under `@sigma/node-border` in this checkout's own `package-lock.json`, the script
run with no argument: exit 1, "apps/workspace reaches two versions of sigma: 3.0.3 (node_modules/sigma) and 3.1.0
(node_modules/@sigma/node-border/node_modules/sigma)", and `test_the_real_tree_passes` failed with the same words.
Restored: both green, the lockfile's SHA-256 unchanged (`3ae975ce…`).

**The readiness marks.** `canvas.sigma-nodes` planted back into `perf/perf.spec.ts`: the class-name check failed,
naming `perf/perf.spec.ts:112`; restored, 12 passed.

**The budget gate** (`WS4a_records/perf-mac-round1.log`), green, 4 passed, load 42 before and after:

| Figure (this Mac, loaded) | Measured | CI's gate |
| --- | --- | --- |
| First frame, `elapsedMs` | 11,280 ms | under 30,000 |
| The page's own `readyAt` | 3,221 ms | not gated |
| Sweep | 2,262.4 ms a frame, 8 frames | under 3,000 |

Red here too (`perf-mac-red-unmarked-round1.log`): `markRenderer`'s call removed from `GlassCanvas.tsx`, the first
frame case timed out at 60 s in `waitForFunction`; the file restored byte for byte.

**The comparison.** `canvasCompare.test.ts`: 13 passed. The comparison spec was run once to get its answer
(`compare-on-the-mac-refused.log`): it **refused**. The references were made with "…SwiftShader Device (Subzero)…";
this Mac draws with "…SwiftShader Device (LLVM 10.0.0)…". The ten scene cases failed at that check, comparing
nothing; the tolerance-ceiling and reference-record cases passed. It stays out of `test:keyboard`.

## The away report's gaps

It was committed with `SEE_PLANT_3`, `SEE_SUITE`, `SECTION_FIGURES` and `SECTION_TAIL` unfilled. It is left as it
was. What its records hold:

- **Case 3** (`plant_compare.log`, "PLANT 5 case 3"): `drawsCommunityLinks` planted off, 1 failed and 10 passed, the
  red one the `communities` scene.
- **The server's budget, three runs before and three after** (`perf-before.log`, `perf-after.log`): middle first
  frame 12,247 ms before and 12,380 ms after; middle `readyAt` 4,285 and 4,496 ms; sweeps 1,944 to 2,368 ms a frame
  before and 1,875 to 2,128 after. The third "after" run was the slowest first frame (13,758 ms), with the load higher
  (14 to 19).
- **Case 13, the whole suite:** no record of it. Run here instead, below (after only, not before and after).

## Checks, and the whole suite (case 13)

- `npm test --workspace apps/workspace`: 410 files, 3,977 tests passed; the 3 budget tests passed.
- `npm run lint`, `npm run typecheck`, `no_react_check.mjs`, `version_isolation_check.mjs`: pass. `typecheck` does not
  read the workspace's `keyboard/` or `perf/` folders (`tsconfig.json` says why), so the new files there are not
  type-checked by it.
- The two acceptance Python files (37 passed), `test_no_react_check.py` and `test_pages_foundation.py` (65 passed),
  `ruff check .`: pass. The guard refused one call of mine that named the acceptance environment, so the last two
  were run by hand in the worktree's own `.venv`; the Stop hook runs the frozen commands.
- `citation-check`, `client-name-check`, `test-file-coverage-check`, `route-coverage-check`, `design-check`: pass.
- `test:keyboard` (run in three shards at `a3ecfdd`): **1,515 passed, 5 skipped, 0 failed** of 1,520, the changed
  `canvas-look.spec.ts` and `link-selection.spec.ts` among them.
- `test:a11y` (at `a3ecfdd`): **1,226 passed, 0 failed.** Sharding splits by file, so one shard held 1,221 and another
  the other 5. Two shards started while the first still held its port failed before testing anything, and were run
  again after it.
- `test:perf`: 4 passed, above.

## For the owner

1. `COMPARE_CI_REFERENCES.diff`, its `env -u CI` included (above).
2. The two front ends' ready moments differ by one render and one frame (Q3). Nothing was changed for it.
