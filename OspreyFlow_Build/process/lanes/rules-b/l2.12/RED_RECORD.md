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

## 7. One set of words (`help/roles.test.ts`, `help/RolesHelpPage.test.tsx`) and the canvas badge
- Plant in `roles.ts`: `manage_models` left unsaid → `say every right rights.py declares` and the
  planted-right case FAILED, and `tsc` refused it (TS2741). The planted-right case also plants
  `approve_releases` into a copy of `rights.py` and asserts it is found missing.
- Plant in `alertBadges.tsx`: closed alerts marked too → `marks each item an open alert concerns`
  FAILED.

## 8. Keyboard (`keyboard/alert-figures.spec.ts`, with `registry-L2.12.patch` applied uncommitted)
- Handlers removed: the Alerts panel's row (no-op), the Rule select (no-op) and Home's *Open the
  dashboard* (no-op) → the three cases using them FAILED, and the coverage case with them; 4 passed.
- Restored: 8 passed; with `reports.spec.ts` and `shell.spec.ts`, 44 passed.
- Axe (`a11y/every-harness.spec.ts`): `alert-figures-harness.html` in six states × dark, light and GOV.UK,
  18 scans and 6 label checks, all passed. Seen by eye in dark and GOV.UK: the board was clipped by the
  Superset frame's 480 px kept while hidden, and a hotlist row read "Alert:"; both fixed, the label held by
  `AlertsPanel.test.tsx`.

## 9. After the lane review (round 1)
- **Hidden alerts, live, under the rules-b lease on stack b (00:10Z, 9 November):** plant in
  `alert_report` feeding the two new sections from `alerts.list_case_queue` (the store's rows before the
  evidence check) → `test_monitoring_dashboard.py::test_a_hidden_alert_changes_no_dashboard_figure`
  FAILED (its comparison holds the whole `monitoring` section); restored, 5 passed.
- **The call site** (`test_alert_panel_figures.py::test_the_report_counts_mine_as_the_reader_it_is_read_as`,
  offline): plant `reader_id=investigation_id` at `alert_report`'s call → FAILED; restored.
- **A kind L2.10 adds** (`test_a_kind_the_report_does_not_name_is_counted_under_its_own_name`): red on the
  committed `reports.py` (`KeyError: 'analyst'`, the route's 500); green with `.get`.
- The closed-band case `test_the_closed_age_bands_are_the_report_s_own` was added green after the schema's
  `Literal` (its plant would be a fifth band in `AGE_LABELS`); counts now 8 passed in that file.
- **The Reports Viewer's refusals** are derived from `app.routes` (every route about an alert but the two
  shared reads), naming 12 that must be among them. Plant: `send-back` with no checks → FAILED with
  `{'send_back_alert_close': 500}` (a route the hand-written list had missed). The reached half shown able
  to fail: a reader with no role is stopped at all four (`test_the_reached_half_can_fail`). 5 passed.
- **Keyboard, the five not yet shown red:** Back from the Figures, Back from the board, the board chooser,
  *Open in its case* and the help page's Back each made a no-op → those five cases and the coverage case
  FAILED; restored, 8 passed. With §8, all eight actions shown red.
- **The board's team view under the filter:** plant, the team table unfiltered → `opens filtered … every
  figure follows the filter` FAILED.
- **A Superset board under the Glass's slug:** plant, no filter → the new case FAILED (listed twice).
- **The journey ends when its screen is left:** plant, never cleared → the new App case FAILED.
- **The roles' places** are now read from `shell/placesByRole.json`: the hand-copied ones were wrong (the
  Data Engineer and the Super user also open Admin), found by the new `roles.test.ts` case.
- **Admin's patch:** a right's tip read with its box and the help door, by keyboard (`admin.spec.ts`),
  red with `aria-describedby` removed; axe's 2.5.3 label-in-name check failed with the tip inside the
  `<label>`, fixed by moving it beside; 56 axe and 34 keyboard passed with the patch applied.
- **Rule 1, honestly:** the Alerts panel's tests (§3) and the board's (§5) were written beside the code and
  passed first; their reds are plants, not a first run.

## 10. After the lane review (round 2)
- **The newest few under a filter:** a new case with six newer rows of another group; plant, the queue
  cut to the newest five before the filter (`fetchNewestAlerts(api, NEWEST_FEW)`) → FAILED; restored.
- **The reached half, planted where rights are given:** the Reports Viewer's own role without
  `read_reports` (`ROLE_RIGHTS` patched) is stopped at the Figures and both board routes and still reads
  Home's list; replaces the role-less reader of round 1.
- Round 2's item 1 (the worktree changing during the review) was this session's rebase onto main; no
  other agent was in the worktree (`ListAgents`, `pgrep`), and HEAD holds `.get` at both places.
- **See the trend (patch), only with `read_reports`:** a new App case as the Rule author (no
  `read_reports`); plant, the button offered whatever the rights → FAILED; restored. Leaving the
  Dashboards now ends the trend's filter. The patch's App test sits before the evidence test's comment.
