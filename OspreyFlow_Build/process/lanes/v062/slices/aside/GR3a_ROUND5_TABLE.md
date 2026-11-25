# GR3a, round 5: every open case (the conductor, 25 November 2026, 04:48 UTC)

From the round-4 verifier's record (tip `80cfc04b44`) and a read-only scout's comparison of every figure the React
alert monitoring board draws with what this page draws, field by field of `MonitoringFigures`
(`OspreyFlow_Core/packages/schemas/domain.py` about lines 1517 to 1531). **Every other figure is already drawn by the
page; this round's work is the rows below and nothing else.**

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **The open-alerts figures are not drawn.** The board draws "N alerts open" and the table "Open alerts by source and age" (source × the four age bands) from `monitoring.open_by_source` (`apps/workspace/src/reports/AlertsPanel.tsx` about lines 63 to 97). `readReport` (`apps/pages/server/views/alertMonitoringWords.ts` about lines 247 to 254) never reads the field; `monitoringView` draws no section for it. | `alertMonitoringWords.ts`, `alert-monitoring.njk` | The page reads `open_by_source` and draws the count and a captioned table of the same figures (a chart as well only if you draw one for the other sections: plain SVG with classes, no library, no inline style, a table of the same figures beside it). Drawn whether or not anything was raised in the period. |
| 2 | **The fixture never sends open alerts.** `fakeReportConduit.ts` (about line 144) always sends `open_by_source: []`, so no test could see row 1 (rule 15). | the fixture Conduit | The fixture builds `open_by_source` as the real route does (read the route's own code for how it counts: open alerts the reader may see, by source and age band), and a world with open alerts and nothing raised in the period exists. Red first: the page's case for row 1 fails before the fix. |
| 3 | **The scenario's reason is wrong for these figures.** `spec/08_ACCEPTANCE_SCENARIOS.md` about line 806 says the panel is left out because "the panel's rows are a way into an alert": that covers the Newest list (a second route, `fetchNewestAlerts`) and the rule filter, not the open-by-age counts. AM5 (about line 796) says the page "never hides a figure the route sent". | `spec/08` | The sentence names only the Newest list and the rule filter as left out, and the open-alerts count and table as drawn. **No other exception is made on your own:** the owner's rule of 20 November 2026 allows one only where a figure is impossible or meaningless on a server-rendered page, and only with his agreement; if you believe one is, stop and say so. |

Out of this round: the rule filter and the Newest list (excluded by the scenario); held rows, which this page already
draws and the board does not; `kyc`, `pole` and `drawing`, which neither draws.
