# GG2a, round 5: take main in, then the version window and I20's third test (the conductor, 27 November 2026)

The owner's word of 27 November, about 09:55 UTC (rule 5; D272, D286). **This round starts only after WS4a has merged.** WS4a brings I20 to main (`same_drawing_versions_check.mjs` and its tests), which rows 2 and 3 need. **This round is the three rows below and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | **Take main in.** GG2a conflicts with main in `apps/pages/package.json` and `package-lock.json`, after GG5a's merge (read `git diff aca39a3^1 aca39a3 -- OspreyFlow_Core/apps/pages/package.json` for what main added). **Keep both sides' dependencies in `package.json`. Then regenerate the lockfile with npm** (`npm install` at `OspreyFlow_Core`, the workspace's own npm). **Never hand-merge `package-lock.json`.** Take any other conflict by keeping main's entries first and yours after. | Main is an ancestor of your tip; `npm ci` succeeds from the new lockfile; the lockfile resolves each package one way. |
| 2 | **The version-window entry** (WS4a Q1 (a), D272). `apps/pages/VERSION_WINDOW.yaml` (or the file WS4a's I20 reads; name it) gains the `sigma` entry: workspace 3.0.3, pages 4.0.6, and the day the window opens. Your branch's lockfile then passes I20. WS4b removes the entry when the workspace moves to Sigma 4 (D286). | I20 is green with the entry and red without it. Show both. |
| 3 | **I20's third test** (WS4a Q5): `test_no_sigma_page_merges_in_the_window.py`, as WS4a's report describes it. Make it red first, at the real shape I20 reads (rule 15), then green. | It is red with its plant and green on your branch. Your frozen checks are green. |

Then the verifier checks the round again, the server tests it, and the full gate runs, as usual. If the verifier finds anything beyond these three rows, the slice goes to the owner.
