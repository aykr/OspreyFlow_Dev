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

## 11. After the final lane review (round 3, at the rebased head 9edc5d4)

- **The way back keeps the reader's focus (WCAG 2.4.3):** App builds `journeyBack` afresh on every render,
  and the Figures and the board focused it whenever the object changed, so any re-render pulled focus
  back to *← Back to your alerts*. The keyboard harness passes one stable object, so it could not see this
  (rule 12). New cases in `ReportsView.test.tsx` and `AlertMonitoringBoard.test.tsx` draw the parent again
  with an equal, new way back after focus moved to Period / Rule: both FAILED on the code as it stood (focus
  taken back); green with the effect keyed on the way back being present (`fromAlert !== null`), not on
  its identity. That is the real call site's shape: a fresh object per render, as App passes it.
- The rule-group table had two Glass copies (`AlertsPanel.groupOf`, `homeData.ruleGroupOf`); now one,
  `figureParts.alertRuleGroup`, which both read (the Conduit's `_RULE_GROUP` is its counterpart).

## 12. The orchestrator's review (9 November): its fix round, each red at the real call site

**Item 1, the audience (`test_monitoring_dashboard.py`, real Postgres, rules-b lease on stack c).** The only-me
case now also holds `open_by_source` and `team` for the colleague and the other unit's reader; a new case,
`test_the_panel_and_the_team_view_reach_only_each_alert_s_audience`, adds an "only me" alert claimed by its
owner (in the owner's panel and team view as *mine*, in no one else's) and a reader of another case on the
same dataset. Green on first run (the code was there), so red by plants in `alerts.py`'s queue scope:
- the "only me" audience check dropped (`h.audience = 'team'`) → the only-me case and the new case FAILED
  (2 failed, 4 passed);
- the case dropped from a typology alert's scope → 6 failed, the new case among them (the broader reds are
  rows other tests left in the shared database, read once the case no longer bounds them);
- the unit dropped from a shared alert's scope → 6 failed, the new case among them.
- Restored: 6 passed.

**Item 3, the journey's reached half (`test_reports_viewer_journey.py`).** It counted any non-403 as reached.
Now each destination is asked through the real case gate (`_authorized_at`, a case store that answers as the
real one: a Viewer's level on `case-1` for the viewer, `InvestigationNotFoundError` otherwise) and the report
and queue behind it, and must answer 200; another case is asserted 404. Red: the case store refusing the
viewer → `test_the_reached_half_sees_the_case_s_refusal` asserts the three case routes answer 404, which the
reached case reports (before, a 404 passed it). Home's queue counts joined `REACHED`; the guest token left
it: the Alert monitoring board asks Superset for nothing.

**Item 10, "nothing else" over every route.** `test_a_reports_viewer_is_refused_every_route_beyond_its_rights`
asks every route that names a right (`test_route_rights.py`'s table, over 200) whose right is not on decision
10's list, written in the test; each must refuse by `right_required`/`place_required`. Red twice: planted
where roles get their rights (the Reports Viewer given `triage_alerts`) → the triage routes answered
(`test_the_sweep_finds_a_right_given_beyond_the_list`); and in `app.py`, `share_case` taken off
`rename_investigation` (no alert in its path) → the sweep FAILED with `{'rename_investigation': 500}`;
restored, 8 passed.

**Item 5, the Alerts panel's and the board's cases, each planted now** (a script per plant: edit, run the one
case with `-t`, restore):
- panel: the open total from the rows given, not the Conduit's count → `counts only what the Conduit
  counted` FAILED;
- panel: closed alerts kept among the newest (`api.ts`) → `lists the newest few` FAILED;
- panel: the newest listed oldest first → the same case FAILED;
- panel: a 403 on the rows taken as a failure → `refused the queue's rows` FAILED;
- panel: every row a button whatever the reader → `opens an alert at its address only` FAILED;
- panel: the newest rows not filtered to the group → `shows only the rule group` FAILED;
- panel: never outlined → the same case FAILED;
- panel: the newest few cut before the filter → `are the group's own newest` FAILED;
- panel: analyst alerts named as an unknown typology → `is its own for every kind` FAILED;
- board: the team view drawn short → `draws every section` FAILED;
- board: the rule filter ignored by the weekly figures → `opens filtered to an alert's rule` FAILED;
- board: the alert's period ignored → the same case FAILED;
- board: the way back doing nothing → `says so and goes back` FAILED;
- board: the way back not focused on opening → the same case FAILED;
- board: focused on every redraw (keyed on `fromAlert`'s identity) → `keeps the reader's focus` FAILED;
- board: a Superset board under the Glass's slug kept → `is left out, never shadowing` FAILED;
- **board: the `drawsItself` guard in the embed effect removed alone → `is the first board …` PASSED, not
  red.** §5's record of that plant does not hold at this head: the Superset mount is rendered only when the
  Glass does not draw the board, so the effect finds no mount and asks for no token either way. Two guards,
  each enough; the case is red with both removed (`expected true to be false`: a guest token asked for) and
  green with either kept. The case is right; §5's plant proved less than it claimed (rule 15).
- Restored: 13 passed.

**Item 6, `roles.test.ts`.** It held `RIGHT_WORDS` equal to `rights.py`'s list, so a right another lane adds
turned it red (and `Record<Right, string>` turned the type check red). Shown with `RAISE_ALERTS` planted in
the real `rights.py`: both cases FAILED. Now the words are a subset of the list read at test time (a stale
word is red: `are found stale …`, planted by taking `CREATE_CASE` out of the source read), and a right
without words yet is said by its name (`rightSays`); with the plant in `rights.py`, 5 passed. Restored.

**Item 7, distinct group names.** `groupName` folded every non-typology kind but hotlists and monitors into
the typology fallback, so L2.10's `analyst` and any later kind read alike: the new case FAILED (4 distinct
names of 6) before the change; `analyst` is *Raised by an analyst*, a later kind its own name.

**Item 8, `team_mine` out of the feed.** `test_the_feed_carries_the_panel_sections_as_figures_only` now asserts
no `team_mine` row: FAILED before the change, green after. The feed is pulled by a board as its dashboard
identity (`report_sync` reads the CSV), and a reader's own claims mean nothing there; spec 03 says so.

**Items 2 and 4 of the orchestrator's earlier review are unrecorded.** Neither has a record in this lane's
files, and their text was lost with the previous orchestrator session; what was done for them, if anything,
cannot be told from here. The orchestrator's independent review of 211a6dc (§14) stands in for them.

## 13. My lane-reviewer on the fix round's delta

- **Item 8, the JSON feed too.** The JSON feed (the default) answered the figures whole, *mine* included.
  New `test_neither_feed_format_carries_the_reader_s_own_claims` (through the real feed route, a claimed
  alert of the reader's in the queue): FAILED on the JSON feed (`'mine': 1`) before the route left it out;
  green after; the reader's own Figures still carry it (`[1]`). `test_reports.py`'s live view-equals-feed
  case now compares without *mine*.
- **Item 10, the routes that name no right.** The sweep asked only routes naming a right, and read them from
  `test_route_rights.py`'s table. It now reads each route's right from the app (`_declared`), and
  `test_every_route_naming_no_right_is_one_weighed_for_the_viewer` pins the 23 routes that name none (all
  GETs but the reader's own tab state and connection ticket). Red: `share_case` taken off
  `rename_investigation` in `app.py` → `named no right, not weighed: ['rename_investigation']`; restored.
- **Item 6, the words kept.** The subset check let any of today's words be deleted. `WORDED` pins the 51
  rights worded at this step: one deleted from `roles.ts` (`share_case`) → `keep their own words …` FAILED;
  restored. Admin's tip (`admin-tips.patch`) now says a right with no words yet by its name (`rightSays`),
  not blank; the help page lists the worded rights only, since the Glass has no runtime list of rights.
- The fake case store's `effective_level` gives a level only where `get_authorized` would.
- All four patches applied together at this head: 866 unit and 87 keyboard cases passed.
- Not changed: the board's two Superset guards stay held together by one case (each alone is enough, so no
  behaviour tells one from the other); the other unit's checks bound the groups to typology (`<=`), since
  the case's own typology alerts reach the reader the case gate lets in, and the other unit is refused at
  that gate, not here.

## 14. The orchestrator's independent review of 211a6dc, at the rebase onto main (0a4051d, then a06d114)

- **Item 1, the new route that names no right.** Rebased with no conflict; `make schemas-check` matched
  (504 types) with nothing regenerated. `test_every_route_naming_no_right_is_one_weighed_for_the_viewer`
  FAILED at the rebased head as it should (`named no right, not weighed: ['get_grading_scheme_route']`,
  L3.7's route). Weighed: the deployment's grading scheme, reference settings as `get_yardstick_route` is,
  no record's content, so within decision 10; pinned, green. The nothing-else sweep
  (`test_a_reports_viewer_is_refused_every_route_beyond_its_rights`) passed over every route of main's app,
  L1.6's and L3.7's included; its red half (`test_the_sweep_finds_a_right_given_beyond_the_list`) still red
  by its plant. The four patches each pass `git apply --check` at the rebased head.
- **The other unit's figures pinned whole** (`test_monitoring_dashboard.py`, the audience case): its Alerts
  panel and team view equal the case's typology rows, not a subset of the typology label. It needs
  Postgres: not yet run when this was written; its run and its red (a plant that takes a row away, the
  shape the old `<=` could not see) are recorded with the live run below.
- **`AGE_BANDS` typed against the generated `AgeBand`** (`reports/figureParts.tsx`), both ways: a band
  dropped from the list (`"over 30 days"` removed) → `tsc` TS2322 at `_EVERY_BAND`; a band the schema does
  not have (`"over 31 days"`) → TS2820. Restored: `tsc` clean.
- **The board's Superset guard, one guard red alone.** §12 found the effect's `drawsItself` check and the
  mount's render guard each enough, so no behaviour told one from the other. The effect's check is gone
  (with no mount it never ran); the mount's render guard is the one guard, and `is the first board …` now
  also asserts no Superset mount is drawn. Render guard removed → FAILED (`expected <div …(3)></div> to be
  null`); with that assertion also removed, the plant still FAILED on the next one (`expected true to be
  false`: a guest token asked for), so the behaviour itself is caught, not only its restatement; restored,
  6 passed.
- **The board's Rule and Period selects by keys** (`alert-figures.spec.ts`, rule 13), not `selectOption`:
  typed letters, as `keyboard.spec.ts`'s `chooseOption` does (ArrowDown opens the menu on macOS). Rule's
  `onChange` removed → FAILED (`Expected "hotlists:"`, `Received ""`); Period's removed → FAILED
  (`Expected "26"`, `Received "12"`); restored, 8 passed with `registry-L2.12.patch` applied. The ids are
  unchanged (the Period select is part of `filter-the-alert-monitoring-board-by-keyboard`).
- **Left, not capped: the Alerts panel's whole-queue read** (`reports/api.ts`'s `fetchNewestAlerts`). It reads
  the reader's whole active queue to show the newest few. A cap belongs on rules' `read_alert_queue` (a
  `limit` the queue route does not have), and a client-side slice of a capped read would be rule 2's silent
  truncation; carried to rules in `CARRIES.md`, and said in the report.
- **Lane-reviewer on this delta** found the code sound; its records findings (this section's claims of a
  live run not yet taken, the base hash, the guard's second assertion, the carry's scope, the report not
  updated, the docstring's "each still asks the case's level") are fixed here and in the report.
- **The live run and the whole pin's red** (rules-b lease, stack g on the server, at 6221632 on main 99d92a8,
  16:26–16:33Z): 232 passed across 24 files, `test_route_rights.py` and the new pin included
  (`gates/6221632.live.txt`). Planted on the server's copy only (the worktree untouched, the gates running):
  `queue_scope`'s typology clause given `AND {unit} NOT LIKE 'unit-b-%'`, so the fixture's other unit loses
  the case's typology alerts, rows taken away, the shape the old `<=` passed. The audience case FAILED at
  the other unit's line (`assert [] == [('typology', 'structuring', '1 to 7 days', 1)]`), the owner's and
  the colleague's lines passing before it; the next copy restored `alerts.py`, 6 passed
  (`gates/6221632.live-plant.txt`). Stack down, lease released.
- **`whyNot` removed** (studio-b's review, routed by the orchestrator; the owner's ruling (c) on decision
  12: a refusal names the roles that hold a right, never people). `whyNot(right, holders)` named people, and
  `roles.test.ts` pinned "D. Engineer and S. Lead have it"; no screen used it. New case `name no person who
  holds a right` (no export of `roles.ts` that takes holders or people): FAILED with `whyNot` there
  (`expected [ 'whyNot' ] to deeply equal []`); `whyNot` removed, green; help, reports and home 163 passed,
  `tsc` clean. Roles come from studio-b's `whyNotByRole` (its `L1.8_roles_words.patch`, which now applies
  here with its context reduced to one line, `git apply -C1`).
