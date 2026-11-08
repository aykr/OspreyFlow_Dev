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
