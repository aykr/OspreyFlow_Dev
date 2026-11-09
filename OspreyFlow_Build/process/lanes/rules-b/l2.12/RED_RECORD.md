# rules-b · L2.12 · red record

Each new case shown red by a plant at its real call site, then green with the plant removed. Offline,
closed ports (59991–59994), no lease.

## 1. The panel's and the board's figures (`test_alert_panel_figures.py`)
- Before `reports.py` computed them: 4 failed, 1 passed (`_monitoring_figures` took no reader).
- Plant: `mine` counted as any claim (`elif alert.assignee is not None`) →
  `test_mine_is_the_readers_own_claims_only` FAILED.
- Plant: `closed` taken as still in the queue → `test_open_by_source_…` and `test_the_team_view_…` FAILED.
- Plant: not of interest narrowed to False positive → `test_the_team_view_…` FAILED.
- Restored: 5 passed.

## 2. The Reports Viewer's journey over HTTP (`test_reports_viewer_journey.py`)
- Plant in `app.py`: `Depends(require_rules_place)` taken off `GET /v1/alerts/{alert_id}` →
  `test_a_reports_viewer_is_refused_every_way_into_an_alert` FAILED
  (`{'open_alert_at_address': 500}`: past its checks to the missing store).
- Restored: 4 passed.

## 3. The Alerts panel (`reports/AlertsPanel.test.tsx`), green first, so each red by a plant
- Plant: the open total taken from the queue's rows (`newest.length`), not the Conduit's figures →
  `counts only what the Conduit counted …` and `shows only the rule group …` FAILED (rule 7).
- Plant: every row a button whatever the reader → `opens an alert at its address only for a reader
  Rules and Monitoring is offered to` FAILED.
- Plant in `api.ts`: a 403 on the queue's rows taken as a failure, not as counts-only →
  `shows a reader refused the queue's rows the counts alone` FAILED.
- Restored: 5 passed.

## 4. The case's Figures and the second door (`ReportsPlace.test.tsx`, `ReportsView.test.tsx`, `EmbeddedDashboards.test.tsx`)
- Plant in `ReportsPlace.tsx`: a *Dashboards* tab put back → `is gone: … no Dashboards tab` and
  `has one door, the Glass's rail` FAILED.
- Plant in `ReportsView.tsx`: the Alerts panel not outlined when opened from an alert → `opened from an
  alert, says so, outlines …` FAILED.
- Plant: the way back not focused on opening → the same case FAILED.
- Restored: 108 passed (reports/).

## 5. The Alert monitoring board (`reports/AlertMonitoringBoard.test.tsx`)
- Plant in `EmbeddedDashboards.tsx`: the Glass's own board sent to Superset for a guest token (the
  `drawsItself` guard removed) → `is the first board on the Dashboards, drawn by the Glass with no
  Superset token asked for it` FAILED.
- Plant in `AlertMonitoringBoard.tsx`: the rule filter ignored → `opens filtered to an alert's rule and
  period, and every figure follows the filter` FAILED.
- Restored: 4 passed.

## 6. The Reports Viewer's journey (`reports/journey.test.ts`, `home/HomePage.test.tsx`, `App.test.tsx`)
- Plant in `journey.ts`: a noted journey taken for any case → `is taken once, for its own case alone` FAILED.
- Plant in `HomePage.tsx`: a third way, *Open the alert*, on the Viewer's row → `offers a Reports Viewer
  … its case's Figures and its dashboard and nothing else` FAILED.
- Plant: the journey offered to a reader the place is offered to → `keeps the alert's own address …`
  FAILED.
- Plant in `App.tsx`: the noted journey never taken → both App journey cases FAILED.
- Plant: *← Back to your alerts* not returning Home → `… and Back goes Home` FAILED.
- Restored: green. Found red on main too, not this step's: `layout/PanelFrames.test.tsx` (6) and
  `App.chrome.test.tsx`'s Inspector case, also red in a clean checkout of main at 24e2c8e.
