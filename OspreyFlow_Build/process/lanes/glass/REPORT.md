# glass lane · report · L2.2 three places, after review (7 November 2026)

1. **Roles see only their places; hidden places' routes refuse them: met, no xfail.** `test_place_routes.py` (67 tests) covers the 4 roles, Super user, 4 legacy roles and every `right:` grant (offered places; 403 `right_required` on every route of a hidden place), and checks each call site in the workspace's source against its route's places. Red on record: 26 failures before re-homing; `invite_person_route`'s and `list_studio_recipe_drafts`'s checks removed; a planted Admin→Studio call (`test_a_planted_call_from_another_place_is_found`).
2. **Re-homed, no role loses a right (ADR-145 Am. 1).** The upload is a Glass route; the schedule routes are Admin's too. To `edit_pipelines` from `add_ingest_files`: `/v1/ingest/connections`, dataset `source-files`, `sources` GET/POST, `sources/{s}`, `profile`, `lineage`. To `run_pipelines` from `read_data_feeds`: run history. Callers: `ingest/sources/api.ts` (the first six), `ingest/api.ts` (runs); `sources/{s}` has none. No Glass or Admin screen calls any of the eight. Administrators keep `schedule_pipelines`, so `scheduler.py` still runs their schedules (`test_a_schedule_an_administrator_owns_still_runs`).
3. **Keyboard: met.** `shell.spec.ts` covers the switcher (both brands), cross-link, banner sections and Home's cards. Each went red with its handler removed; the cross-link went red with `useLastGlassView`'s memory removed. That case changes the case and view first and asserts both return. `shell`/`start`/`top-bar`/`admin` specs: 59 pass. The full keyboard suite (534) was last run before this round.
4. **Axe: met.** Dark, light and GOV.UK, 34 pass; the Admin place is now in `places-harness`.
5. **Docs: met.** `spec/02` §2.0a states the places as built; the banner is the fourth row (41px; 91px under GOV.UK); the rail and Proposed-types lines are corrected. DEMO_GUIDE §8a gives each account's places. Written: ADR-145 Am. 1, ADR-090 Am. 5, ADR-115 Am. 6. ADR-067 Am. 1 is not written: the upload's route and right are unchanged.
6. **Other fixes.** `placesFor(null)` offers nothing. Home's cards take their names and keys from `places.json`. The banner draws Case · Boards (coming) · Monitoring. Not built: the Studio's "Dataset ‹name› ▾" and "feeds n cases" (Am. 1, item 5).
7. **Python tier (`make test`, rebased):** 7649 pass. The 12 failures also fail on a clean checkout of main, so none is this branch's: `test_revert_elements_by_type`, `test_write_onto_a_reverted_node`, `test_unfiltered_node_lookup_confined` and `test_test_file_coverage_check` (six live tests not wired), from main's Studio work; `test_deployment_schema` and `test_layout` (local `osprey.yaml`, `graphify-out`), from this machine. Mine, `test_core_stands_alone`, is fixed.
8. **Commits:** rebased on main, 13 ahead (`git log main..lane/glass`).
9. **Lane 1:** readers in `test_run_ledger_read_side`, `test_run_counts_withheld` and `test_studio_schedule_routes` gained `loader` (run history needs a pipeline right).
10. **Orchestrator:** commit the four `SHELL_ACTIONS` ids just before the merge. Add `App.tsx` and `rights/**` to the ownership map.
11. **Questions and answers:**
    - Place rule? Narrow the rights, later revised to "re-home the routes".
    - Proposed types? Admin until L3.5.
    - Who edits `App.tsx` and `visibility.ts`? Glass.
    - Places a person can't open? Hidden, not dimmed.
12. **Hand check.** From `OspreyFlow_Core`, run `.venv/bin/ospreyflow start --build`, then `.venv/bin/ospreyflow open`.
    - Analyst: Home shows *The Glass* card only.
    - Engineer: three cards. In a case, switch to Map, then *Open … in the Ingest Studio ↗* and *← Back to case …*: Map returns.
    - Admin: *Admin* → *Proposed types*.
    - Repeat with `?brand=govuk`: the places sit in the blue header.
13. **Still running:** nothing of mine. No dev stack or lease used.
