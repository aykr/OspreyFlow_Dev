# The performance budget figures after slice E, on the owner's Mac (22 November 2026)

**What this is.** The comparison the owner asked for (file 014, point 4; the chat ruling of 22 November: three runs after slice E, compare the middle value with the middle of the before-runs; only a move larger than the run-to-run spread counts), against `PL4_BUDGET_FIGURES_2026-11-22.md` (taken at 08:21 to 08:23 before slice E).

**When and how.** 22 November 2026, **18:12:26 to 18:14:32 UTC (2 minutes 6 seconds)**; **main at slice E's merge `e2728af` plus the line's records (`c108dab`); the owner's series (the line fixes, the table entry and the gate line, `1691c27d` to `431bbbe`) landed on main during the runs, about 18:12, and touches no file the workspace builds or the budget tests read**; load average 4.3 at the start; **no builder, verifier, merge or server run of the line was running** (AD1a's builder had just stopped; the demo server runs on another machine). The listing at the start showed a few Chromium processes from the Playwright cache that were already alive (not started by this run, and not identified: another session of the owner's, or a leftover). The same commands as before, from `OspreyFlow_Core`: `npm run test:budget --workspace apps/workspace` three times, and `OSPREY_PORTS_SLOT=25 npm run test:perf --workspace apps/workspace` three times (the before-run had two browser runs, as one before-run was lost to slice E's merge).

## Unit budget (vitest's own duration for each test)

| Test | Limit | Before (3 runs, middle) | After (3 runs, middle) |
| --- | --- | --- | --- |
| `MatrixView.budget.test.tsx` | `< 2,500 ms` | 2,553, 2,481, 2,532 (**2,532**) | 2,247, 2,309, 2,303 (**2,303**) |
| `settledAnchor.budget.test.ts` | `< 1,000 ms` | 85, 90, 90 (**90**) | 77, 74, 91 (**77**) |
| `communityLinks.budget.test.ts` | `< 2,000 ms` | 51, 58, 56 (**56**) | 62, 59, 56 (**59**) |

All three passed in all three runs. **No figure is worse than the before-run's spread** (the Matrix view is 229 ms better, inside the limit with 197 ms to spare where before it was printed at 2,532 against 2,500: the figure vitest prints includes set-up; the test asserts its own inner time). The community figure is 3 ms above the middle (inside the before-runs' own spread of 51 to 58).

## Browser budget (Playwright, Chromium, software render)

| Measure | Limit | Before (2 runs) | After (3 runs, middle) |
| --- | --- | --- | --- |
| first frame (`perf first frame`) | `< 30,000 ms` | 7,155, 8,047 | 6,474, 6,386, 6,904 (**6,474**) |
| `readyAt` | (printed) | 2,715, 2,672 | 2,546, 2,389, 2,425 (**2,425**) |
| DOM content loaded | (printed) | 1,267, 1,191 | 1,035, 1,005, 975 (**1,005**) |
| sweep, ms per frame | `< 3,000 ms` | 1,885.1, 1,587.7 | 988.3, 1,173.8, 1,594.8 (**1,173.8**) |
| long frames (script and rendering, ms long in all) | (printed) | 2,860, 3,027 | 2,881, 2,741, 2,960 (**2,881**) |
| modules loaded | (printed) | 170 | 170, 170, 170 |
| `community-links.spec.ts` | passes | passed | passed (32.9, 33.1, 36.9 s) |

All four browser tests passed in all three runs.

## The reading

**Nothing moved beyond the spread in the bad direction, and no limit is near.** Every figure is at or better than the before-runs (the first frame and the sweep are lower than both before-runs; the long-frame total sits inside their range). I read the improvement as the quieter Mac and the lighter module graph, not as a proven gain from slice E: the before-runs were taken at a load of 6.3 and these at 4.3, and the run count is small. **The comparison asked for finds no regression; slice E's budget is met.**
