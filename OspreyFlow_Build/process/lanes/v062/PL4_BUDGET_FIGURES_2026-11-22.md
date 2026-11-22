# The performance budget figures, taken on the owner's Mac before slice E (22 November 2026)

**Why.** ADR-152 invariant I11 ("the React workspace's whole suite and its performance budget, before and after R2, on the same machine"), the owner's ruling of 20 November ("slice E's budget comparison against A's baseline is on the Mac, with nothing else running"), and his file 014 (the Mac run stands; answer 7(c) of file 013 withdrawn). `OspreyFlow_Core/apps/workspace/PL4_BASELINE.json` says the figures "are measured on the owner's Mac with nothing else running (slice E)".

**When and how.** 22 November 2026, **08:21:07 to 08:23:03 UTC: the pause was 1 minute 56 seconds** (no seat, no merge, no builder of the line running; the lock free; load average 6.3 at the start). **Main checkout at `2f6388c`**, the code of PL4d3e's merge (`f4d1634`) plus docs-only commits. Commands, from `OspreyFlow_Core`: `npm run test:budget --workspace apps/workspace` three times (the unit budget run: `vitest run --config vitest.budget.config.ts`), and `OSPREY_PORTS_SLOT=25 npm run test:perf --workspace apps/workspace` twice (the browser budget: `playwright test --config perf/playwright.config.ts`: the fixture of 50,000 nodes and 250,000 links under CI's software render). **Nothing else of the conductor's ran; the owner's own sessions (line fix, demo server) were not touched and may have been running.**

## The unit budget run (three runs; each test's own duration, as vitest prints it)

| Test | Limit in the test | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- | --- |
| `src/matrix/MatrixView.budget.test.tsx`: MatrixView at 50,000 nodes and 250,000 links opens inside §5's first-frame budget | `elapsed < 2,500 ms` (`BUDGET_MS`) | 2,553 ms | 2,481 ms | 2,532 ms |
| `src/canvas/settledAnchor.budget.test.ts`: settledAnchors at the perf fixture's size | `< 1,000 ms` | 85 ms | 90 ms | 90 ms |
| `src/canvas/communityLinks.budget.test.ts`: packBubbles, 50,000 nodes in 40 communities | `< 2,000 ms` | 51 ms | 58 ms | 56 ms |

All three tests passed in every run. **Note on the first row:** the figure vitest prints is the whole test's duration (set-up included); the test asserts its own `elapsed` from inside, which is under the limit, and the printed duration sits near 2,500 ms in all three runs: **the Matrix view's first frame is the tightest budget on this Mac, within a few percent of its limit.**

## The browser budget run (two runs; Playwright, Chromium, software render)

| Measure | Limit in the spec | Run 1 | Run 2 |
| --- | --- | --- | --- |
| `perf first frame` (50k/250k fixture to a first interactive frame) | `< 30,000 ms` (`perf.spec.ts` line 74) | 7,155 ms (`readyAt` 2,715 ms; DOM ready 1,267 ms; 170 modules) | 8,047 ms (`readyAt` 2,672 ms; DOM ready 1,191 ms) |
| `perf sweep` (a sustained pan and zoom: average frame) | `< 3,000 ms` per frame (line 176) | 1,885.1 ms per frame over 9 frames in 16,966 ms | 1,587.7 ms per frame over 9 frames in 14,289 ms |
| long frames (script and rendering) | (no limit asserted; the profile is printed) | 4 in all, 3 after `readyAt`; the longest 2,583 ms (react-dom `performWorkUntilDeadline` at 1,269 ms); 2,860 ms long in all; script 2,852 ms, rendering 1,128 ms | 4 in all; 3,027 ms long in all; script 3,023 ms, rendering 1,229 ms |
| `community-links.spec.ts` (a large working set opens grouped by community) | passes | passed (38.5 s) | passed |

All four browser tests passed in both runs (44.8 s and 41.8 s). **The browser figures vary by about 12% between two runs on a quiet Mac (first frame 7,155 to 8,047 ms; sweep 1,588 to 1,885 ms per frame): "beyond the budget's own tolerance" for the post-slice comparison therefore means a figure outside the limits above, or outside the spread of these runs by more than that noise.**

## What the comparison after slice E uses

The same commands, on the same Mac, nothing else running, once, after slice E has merged (the owner's file 014, point 4). **If a figure moves beyond the tolerance, stop and tell the owner before AD1a and AD1b merge.** Slice E's builder writes these figures into `PL4_BASELINE.json` as its first commit, in place of the `not_recorded` line (a product file: the conductor writes none).
