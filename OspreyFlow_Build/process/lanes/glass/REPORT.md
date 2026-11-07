# glass lane · report · L2.2 three places, after the third review (7 November 2026)

1. **Each role sees only the places it can use, and a hidden place's routes refuse it: met.** `test_place_routes.py` reads a route's declared checks: the decorator right, the Studio role in its signature or dependencies, `require_admin_role`. Checks inside a route's body are not read. The Studio is offered for its entry read (recipe registry, `edit_pipelines`); Admin for one of its tabs' first reads; the Glass for any of its routes.
   - `placesByRole.json` records every role, legacy role and `right:` grant, and `placesFor` is held to it.
   - Analyst → Glass. DE → all three. Admin → Glass + Admin. Reports Viewer → Glass. source_author → Studio.
   - source_approver, loader and compliance → no place. The first two keep their own Studio routes, recorded as `answered_hidden`.
2. **Red on record:**
   - `loader`'s `run_pipelines` planted in the Studio (2 failures); `SourceAuthorDep` removed from `list_dataset_sources` (5); a planted Admin import of a Studio call.
   - `App.test.tsx`: the startScreen guard removed (1); Admin-with-a-case start reverted (2).
   - `shell.spec.ts`: `dossier` kept as a view (the Messages case, 1); the kept view removed.
3. **Routes.** `app.py` differs from the merge base only by the run history (`read_data_feeds` → `run_pipelines`). It stops answering Analysts, Reports Viewers and `right:read_data_feeds` alone; it now answers `loader` and `right:run_pipelines`. `right:edit_pipelines` alone is refused on the seven dataset routes and the upload (both also need `add_ingest_files`).
   - Exempt: the preview (reads no store); `/v1/exports` (an Admin route by `^/v1/exports$`, exempt while no screen calls it, which a test checks).
   - The scheduler test calls `ScheduleExecutor._owner`: an admin's schedule passes, an analyst's is refused.
4. **Hand-off and Back: met.** The guard sits in `startScreen` and runs before anything is drawn. Messages is not kept as the view to return to (a keyboard case: Messages → Studio → change case → Back → Map). The dead "admin" view is removed.
5. **Keyboard: met.** 536/536 in one run on port 5185. Run with `CI=1`, Playwright must start its own Vite (`reuseExistingServer` is off) and fails if the port is taken, so that Vite came from this worktree's `apps/workspace`. **Axe: met** in dark, light and GOV.UK (34).
6. **Vitest:** the full run had 2601 pass and 1 failure, the Matrix budget (`MatrixView.budget.test.tsx`, a timing budget), which passes alone. **Python:** 210 pass (place, route rights, Lane 1, gates).
7. **Docs: met.** ADR-145 Am. 1 is under its reserved title (points 1–6 as settled; compliance offered no place). `spec/02` §2.0a and DEMO_GUIDE §8a are updated. `ADR_RESERVATIONS.md` is as main.
8. **Requests:** (a) the four `SHELL_ACTIONS` ids at merge; (b) a Lane 1 hook to name the Studio's dataset in the banner, if wanted; (c) the ratifications as you listed them.
9. **Questions and answers:** all three rounds settled by you under the owner's delegation, none open.
10. **Hand check.** From `OspreyFlow_Core`: `.venv/bin/ospreyflow start --build`, then `.venv/bin/ospreyflow open`.
    - Analyst: one card.
    - Engineer: Map → *Open … in the Ingest Studio ↗* → change case → *← Back*: Map, new case.
    - Admin: *Admin* → *Proposed types*.
    - Repeat with `?brand=govuk`.
11. **Still running:** nothing. No dev stack or lease used.
