# GG2a, round 1: the line's scan, red six times (the conductor, 25 November 2026, 22:35 UTC)

Your frozen checks are green, but **the line's own scans are red** at `f04937f`, so the round never ends green. You do
not run the scans; this is what they say. **Fix this row, then finish round 1 as its brief says.**

| # | Open case | Done when |
| --- | --- | --- |
| 1 | `tests/glass_trees/`'s "Core stands alone" scan: `AssertionError: Core names the Build folder in: ['OspreyFlow_Core/apps/pages/test/server/budgetPageNotServed.test.ts']`. A file under `OspreyFlow_Core` may not name `OspreyFlow_Build` (Core stands alone; GR4a round 1 met the same rule and held its list in the test itself). | `budgetPageNotServed.test.ts` names no Build path: what it reads from the Build tree it holds itself or reads from Core. Run the scan that found it (grep `Core names the Build folder` under `OspreyFlow_Build/tests/` for its file) and show it green, plus your frozen checks. |
