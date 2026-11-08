# rules-b · L2.12 · plan (8 November 2026)

Working from: ADR-145 Amendment 4 decisions 8–10 and 12 and its tests; ADR-146 decision 9 and
Amendment 2 point 3; ADR-134 decision 2; ADR-111 (and Amendment 3); spec 02 (the Glass) for the
Figures tab and Dashboards; spec 03 for the report route. Orchestrator's answers of 8 November: App.tsx
and Home additive, listed for ratification with exact lines; canvas badge, Admin's tips and *See the
trend* as patches for their owners; the boards' Alerts panel mount left to L3.3/L3.4; drawing figures
null until L3.4, their panel hidden while null.

## Schemas (own commit, head of the branch)
`packages/schemas/domain.py`: `MonitoringFigures.open_by_source` (`AgeCount`: rule group, typology,
age band, count, open alerts only), `MonitoringFigures.team` (`TeamCount` per rule group: unassigned,
mine, older than seven days, closed, closed as not of interest), `ReportFigures.drawing`
(`DrawingFigures | None`, null until L3.4). Generated TS regenerated.

## Conduit
`services/api/reports.py`: the two new sections from the same visible queue (rule 3), `mine` against the
reader; `feed_rows` carries them as figures only.

## Glass (`apps/workspace/src/reports/**`, `help/**` new)
- `AlertsPanel.tsx`: open by source and age; the newest few only for a reader the queue's rows go to;
  rows open the address only where the place is offered; `outlined` for the journey.
- `ReportsView.tsx` → the case's *Figures*: heading, the Alerts panel, the Drawing panel (when served),
  the "From alert … · ← Back to your alerts" banner.
- `ReportsPlace.tsx`: the Dashboards tab removed (the second door).
- `AlertMonitoringBoard.tsx`: D2's board, filtered by rule group and period; Alerts panel included.
- `EmbeddedDashboards.tsx`: a leading native board (Alert monitoring) first in the chooser.
- `journey.ts`: the Reports Viewer's URLs (Figures from an alert, the board from an alert) and reading them.
- `alertBadges.ts` + overlay (mount is a patch for case).
- `help/roles.ts` (one source of words), `help/RolesHelpPage.tsx`; Admin's and the Studio's tips as patches.
- Out of map, additive, for ratification: `App.tsx` (Figures label, board, journey), `home/HomePage.tsx`,
  `home/homeData.ts` (the Reports Viewer's two actions).

## Tests first, each red by a plant at the real call site
1. `test_monitoring_dashboard.py`: the new sections count as specified; a hidden alert changes neither
   (red: sections counted over the unscoped store read); `mine` is the reader's (red: assignee unchecked).
2. `test_reports_viewer_journey.py` (HTTP, rule 4): the Reports Viewer reaches the case's report and the
   dashboards list and is refused an alert's address, its detail and the queue's write routes (red: the
   place gate dropped from the address).
3. Vitest: AlertsPanel (rows withheld from a counts-only reader, red with the check removed; address
   only where offered), ReportsPlace has no Dashboards tab (red with it back), the board's filter, the
   Figures journey banner, Home's Reports Viewer row offers exactly two actions and never the address,
   help/roles.ts the only source of the tips.
4. Keyboard (rule 13): Figures' Alerts panel row, the board chosen and filtered, the journey's Back,
   Home's two actions; registry ids as a diff (`registry-L2.12.patch`). Axe in dark, light, GOV.UK.
