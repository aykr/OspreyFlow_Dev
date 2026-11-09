# rules-b lane · report · L2.12, reporting folded into the places (9 November 2026; after the orchestrator's independent review of 211a6dc and its fix round)

1. **Figures replace the Reports view: met.** The Figures tab has the Alerts panel and the Drawing panel (the drawing figures are null until L3.4). The second dashboards door is removed. Proved by `test_alert_panel_figures.py` and the `AlertsPanel`, `ReportsView`, `ReportsPlace` and `EmbeddedDashboards` tests. Every panel and board case is shown red by a plant (RED_RECORD §12).
2. **Every figure counted as the reader, by audience (rules 3, 7): met.** `test_monitoring_dashboard.py`'s audience case covers a colleague, another unit, an only-me alert claimed by its owner, and another case's reader on the same dataset. The other unit's figures are now pinned exactly, not as a subset. Red by plants in `alerts.py`'s queue scope; the exact pin is red by a plant that takes the other unit's rows away (live, RED_RECORD §14).
3. **The Reports Viewer reaches only decision 10's list: met.** In `test_reports_viewer_journey.py`:
   - Each destination returns a 200 through the real case gate (red with the case refusing).
   - Every route naming a right beyond the list refuses (over 200 routes; red with a right given, and with `share_case` taken off `rename_investigation`).
   - The **24** routes that name no right are pinned and weighed. main's `get_grading_scheme_route` (L3.7) is weighed as reference settings, like the yardstick; that case was red at the rebased head before the change.
4. **Feed: met.** Neither format carries the team view's *mine* to a board (red first on the JSON feed). Spec 03 says so.
5. **Alert monitoring board, help page, roles' words: met.**
   - The board's Superset guard is now one guard, red alone, on the mount and on the guest token.
   - The board's Rule and Period selects are operated by typed keys; each is red with its handler removed.
   - `AGE_BANDS` is typed against the generated age band in both directions, each direction shown red by `tsc`.
   - `whyNot`, which named people, is removed (the owner's ruling (c)); red first.
6. **Canvas badge, Admin's tips, See the trend: patches.** Each passes `git apply --check` at the head (`PATCHES.md`). Admin's tips are **narrowed**: `admin-tips.patch` gives each right's tip in Admin › Roles' role form, plus the help door. The rest is carried to admin after L2.6 (`CARRIES.md`): Roles' tables and team editor, People, Datasets, levels, and a refusal naming roles through studio-b's `whyNotByRole`.
7. **Keyboard and axe: met.** `alert-figures.spec.ts`: 8 ids in `registry-L2.12.patch`, unchanged. Axe: 742 passed in dark, light and GOV.UK.
8. **Gates at 6221632** (on main 99d92a8; offline, closed ports 59991–59994, OSPREY_LANE unset; `gates/6221632.*`):
   - `make -k ci`: green except this machine's checks: `trivy` and the eight `trivy-image-*` (no Docker daemon; the vulnerability DB download failed), `opentofu-check` and `chart-check`.
   - `make -k test`: 9,453 passed, 24 failed and 30 errors. All are harness cases that need Docker, plus main's known four (`osprey.yaml`, the Valkey port, `graphify-out` at the root, the phone fixture).
   - The vitest half stopped with pytest's failure, so it was run on its own: 2,802 passed plus the harness's 45 (`6221632.vitest.txt`).
   - Keyboard, with `registry-L2.12.patch` applied: 688 passed. 2 failed: `boards.spec.ts:225` and `:423`, main's own failure since L3.7, fixed on `lane/case` (CARRIES row).
   - At a1a8c04 (`whyNot` removed, nothing else changed), vitest: 2,801 passed and 1 failed, `MatrixView.budget` at 2,855 ms against 2,500 on a shared machine. It passed when re-run alone and at 6221632 (`a1a8c04.vitest.txt`).
9. **Live run:** rules-b lease on stack g (on the server), at 6221632, 16:22–16:32Z. 232 passed across 24 files, `test_route_rights.py` included (`gates/6221632.live.txt`). Then a plant run on the server's copy only, red then restored (`6221632.live-plant.txt`). Stack down, lease released.
10. **Found on the way:**
    - The earlier review's items 2 and 4 have no record; RED_RECORD §12 says so, and this review stands in for them.
    - The effect's `drawsItself` check could never run; it is gone.
    - studio-b's `L1.8_roles_words.patch` now applies here only with reduced context (`git apply -C1`), because `whyNot` was its neighbour.
11. **Left:**
    - The boards' Alerts panel mount (L3.3/L3.4) and the Studio's help door.
    - Admin's tips beyond the role form (carried to admin).
    - The Alerts panel reads the whole active queue to show five. Carried to rules: a typed `limit` on `read_alert_queue`, never a bare slice (rule 2).
12. **For ratification at merge** (files outside the lane's map):
    - The schemas commit (`packages/schemas/domain.py`, `generated/MonitoringFigures.ts`, `generated/ReportFigures.ts`), taken separately and first.
    - `services/api/app.py` (the feed route leaving out *mine*, 3341887).
    - `tests/services/api/test_reports.py` and `test_monitoring_dashboard.py`.
    - `apps/workspace/src/App.tsx` and `App.test.tsx`; `home/HomePage.tsx`, `HomePage.test.tsx`, `homeData.ts` and `homeData.test.ts`; `shell/startScreen.tsx`.
    - The shared test kit where the view switch says *Figures*: `a11y/every-harness.spec.ts`, `keyboard/{reports,shell}.spec.ts`, `keyboard/{reports,top-bar,places,case-screen-options}-harness.tsx`, `live/capture-kit.ts`.
    - `process/lanes/CARRIES.md` (two rows).
13. **Requests:**
    - Apply `registry-L2.12.patch` in the merge, and pass the other three patches on after it.
    - studio-b's roles-words patch takes `-C1`, or a rebuild at its `whyNotByRole` hunk.
14. **Questions for the owner:** none. **Still running:** nothing.
