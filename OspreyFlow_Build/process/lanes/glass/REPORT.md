# glass lane · report · L2.2 three places, after the second review (7 November 2026)

1. **Each role sees only its places, and hidden places' routes refuse it: met.** `test_place_routes.py` reads every check a route makes: decorator right, signature Studio role, administrator role. It records what the routes answer every role, legacy role and `right:` grant in `shell/placesByRole.json`; `placesFor` is held to that record (`places.test.tsx`). Analyst → Glass; DE → all three; Admin → Glass + Admin; Reports Viewer → Glass; source_author, source_approver and loader → Studio; compliance → none. Seven `test_an_analyst_is_refused_on_the_dataset_s_sources_routes` cases show 403 from the Studio role on main's code.
2. **Red on record:**
   - Place test: `SourceAuthorDep` removed from `list_dataset_sources` (5 failures); `schedule_pipelines` planted in Admin's rights (2); an Admin file importing a Studio API call through `dataset` (`test_a_planted_call_from_another_place_is_found`).
   - `App.test.tsx`: the hand-off guard removed (2); the kept view removed (1).
   - `places.test.tsx`: a right planted in the Glass's rights.
3. **Routes.** No route moved and no role lost a right. `app.py` differs from main only by the run history (`read_data_feeds` → `run_pipelines`). Analysts and Reports Viewers lose it; no screen of theirs calls it (its callers are `ingest/api.ts` only). `loader` and `right:run_pipelines` are now answered there. The schedule preview (reads no store, `test_the_schedule_preview_reads_no_store`) and `GET /v1/exports` (no screen calls it) are named exemptions. `test_a_schedule_an_administrator_owns_still_runs` reads `scheduler.py`'s own check.
4. **Hand-off: met.** `?view=ingest|admin` opens a place only if the rights open it (3 `App.test.tsx` cases). Admin opens outside the case even with one open, and the Glass no longer draws `AdminPlace`.
5. **Cross-link: met.** The case goes through the real `investigationId` and `openCase`, with a real reload. The view is kept in session storage (`placeMemory.ts`), so Back after a case change in the Studio returns to the last Glass view. The keyboard case fails with that removed.
6. **Banner.** Case · Boards (coming) · Monitoring. The Studio banner no longer repeats datasets; naming the Studio's dataset needs a hook in Lane 1's `ingest/IngestStudio.tsx`, request (b).
7. **Keyboard: met.** Full suite 535/535: 533 on port 5195 while another lane held 5185, plus `keyboard.spec.ts` re-run on 5185 (76/76), since its same-origin case and registry check are bound to 5185. **Axe: met** in dark, light and GOV.UK (34). **Vitest:** 2602 pass (the Matrix budget is load-only; it passes alone). **Python:** the place, route-rights, Lane 1 and gate tests pass (208).
8. **Docs: met.** `spec/02` §2.0a and DEMO_GUIDE (§3.7a, the demo analyst's roles; §8a) state the true checks. Amendments: ADR-145 Am. 1 rewritten; ADR-090 Am. 5 and ADR-115 Am. 6 written; ADR-067 Am. 1 not written.
9. **Commits:** rebased on main (`git log main..lane/glass`).
10. **Requests:** (a) the four `SHELL_ACTIONS` ids, at merge. (b) A Lane 1 hook naming the Studio's chosen dataset, if the banner should show it. (c) Ratify `App.tsx`, `rights/visibility.ts`, the harness files, the run-history right and the Lane 1 tests' `loader`.
11. **Questions and answers (via the orchestrator):** the seven routes' premise was wrong, so they stay as on main; the preview is exempt (A); Proposed types stay in Admin until L3.5; places a person can't open are hidden, not dimmed.
12. **Hand check.** From `OspreyFlow_Core`: `.venv/bin/ospreyflow start --build`, then `.venv/bin/ospreyflow open`.
    - Analyst: one card.
    - Engineer: in a case choose Map, then *Open … in the Ingest Studio ↗*, change case, then *← Back*: Map returns on the new case.
    - Admin: *Admin* → *Proposed types*.
    - Repeat with `?brand=govuk`.
13. **Still running:** nothing of mine. No dev stack or lease used.
