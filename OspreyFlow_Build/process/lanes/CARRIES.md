# Carries between lanes

Requests one lane makes of another lane's files, kept by the orchestrator until the receiving lane's next brief
takes them (then struck through with the brief's commit). Newest last.

| For | Item | From | Into |
| --- | --- | --- | --- |
| admin | Remove Admin's *Proposed types* section: proposals are decided on the Studio's Model tab (ADR-090 Amendment 4) | case-b, L3.5 | L2.7 |
| admin | *Admin › Connections* gains the SQL and API connection settings' fields | studio-b, L1.6 | L2.7 |
| admin | ADR-144 decision 6's count on *Admin › System*: cases converted to views, with the migration's report | case, L3.2 | L2.5b |
| rules | The rule's list picker reads `GET /v1/datasets/{id}/reference-lists/offered`, so a rule offers only subscribed lists | studio-b, L1.6 | L2.10 or L2.11 |
| ~~rules~~ | ~~Ask to search shows `model_limit_reached`~~ (done in platform's P3, `246b51d`) | platform, P2 | — |
| case | L3.4: a withdrawal leaves in place a promoted link the withdrawer may not see (settled, `MORNING.md` item 60) | case, L3.3 | L3.4 |
| studio-b | Wire the subscribed list ids into `studio_staging` and `reference_list_import`, and retire L1.4's stand-in import, once L1.4 is on main | studio-b, L1.6 | after L1.4 |
| studio | L1.5 first: Test of a pipeline with no staging steps still counts over masked rows (pre-existing rule 3 oracle) | independent review of L1.4 | L1.5 |
| admin | The Model tab's proposal notifications (count, reminder, Needs you) for analyst-defined link types | case-b, L3.5 | L2.7 |
| case | Mount rules-b's alert badge overlay in GlassCanvas.tsx (patch in process/lanes/rules-b/) and the boards' Alerts panel | rules-b, L2.12 | L3.4 or at rules-b's merge |
| admin | Admin's tips (Roles, People, Datasets) from help/roles.ts (patch in process/lanes/rules-b/) | rules-b, L2.12 | L2.7 |
| rules | *See the trend* in the queue's detail opening the board filtered (patch in process/lanes/rules-b/) | rules-b, L2.12 | L2.10 or L2.11 |
| case | A case's own proposed link types usable at once on its boards, through LinkTypeService.case_types (decision 9); case-b's L3.5 closes the cross-case leak (hidden types left out of BoardService.link_types) | case-b, L3.5 | L3.4 |
| case | The promotion writer calls LinkTypeService.promotion_refusals; test_every_promotion_writer_asks_which_links_may_go holds it | case-b, L3.5 | L3.4 |
| case | DatasetStore's bootstrap takes AccessExclusiveLock even when nothing changes (ALTER TABLE … ADD COLUMN IF NOT EXISTS), so a starting replica waits behind live reads and one process can deadlock itself: check the catalogue first, or a one-shot migration (found by admin's L2.6 live run) | admin, L2.6 | L3.4 or a hygiene step |
| studio | A gazetteer loaded through the Studio into a case's own dataset keeps its source identifiers (osm_id, uprn) in node reads; withhold them as ADR-147 Amendment 1 does for gazetteer-* datasets (rule 7) | platform, P4 | L1.5 or L1.6 |
| rules | The Lists tab read-only (no add, import or refresh of an ADR-133 list), then retired once the picker and re-screening read Studio lists (ADR-133 Amendment 9, the owner's ruling of 9 November) | studio-b, L1.6 | L2.11 |
| platform | map_admin._is_inside to call schemas.sources.address_is_inside (it misses NAT64, 6to4 and shared space) | studio-b, L1.6 | after L1.6, P5 or a hygiene step |
| docs | Operator prose for the SQL and API connector settings and the private-host allow-list (ADR-140 Amendment 15) | studio-b, L1.6 | D2a |
| studio-b | getaddrinfo called synchronously in async routes (map_admin.py:381; own_networks in connector_reads.py:185) moved off the event loop | independent review of L1.6 | L1.7 or a hygiene step |
| studio-b | The SQL connector's byte cap checked before a row is held (prefetch 500 at sql_connector.py:206-217) and counted in bytes, not characters | independent review of L1.6 | L1.7 |
| release | The Java runtime's NOTICE and GPL-2.0 source offer, before any image carrying it is published (ADR-147 Amendment 2) | platform, P5 | the release step |
| case | The case dataset picker stops composing a gazetteer-* dataset; a case adds a gazetteer by copy (the owner's ruling 6) | platform, P5 | after L3.4 |
| orchestrator | test_lanes_heartbeat.py::test_shows_run_at_once_do_not_mix_their_lines drops a Needs-you line under heavy load (studio's L1.5 make ci, 9 November); passes alone 5/5. Find the race in show's temporary files and fix, red first | studio, L1.5 | a tooling step |
| studio | The PID recipe's r1 and r14 interval cases red on main: loaded links' valid_from keeps the row's time of day (2024-06-03 00:46:06) where the plan expects the start of the day for a date-only interval; find which side changed precision (a Studio load or the PID build) and fix, red first | rules, L2.10 live run | L1.5 if small, else L1.7 |
| admin | Admin's read-only display of the grading scheme (GET /v1/grading-scheme is ready) | case-b, L3.7 | L2.7 |
| platform | The backup set includes grading-scheme.yaml (harness/backup.py) | case-b, L3.7 | P6 |
| case | Export board_store's item columns and row helper for the grading change (instead of case-b's copy) | case-b, L3.7 | L3.6 |
| studio-b | A subscribed list's Lookup passes save and publish but is refused at the drawer's sample, Test and the run: staging_catalogue.run_staging re-judges with subscribed=(); studio_staging's sample, studio_verify (dry_run_staged_recipe) and pipeline_run (prepare_staged_load) pass none; staged_lists has no callers. Thread subscribed through all three, with a live test through run_staging, red first (rule 12) | studio, L1.5 review | L1.8 |
| ~~case-b~~ | ~~`keyboard/boards.spec.ts:225` ("an item is edited by keyboard") times out on main since L3.7, and :423's registry check with it~~ (fixed by case on `lane/case` in `f6def92`, red record `gates/701c027.kb-red.txt`: since L3.7 the Glass takes grades from the opened board's grading_grades, and `keyboard/boards-harness.tsx` supplied none; the harness now offers GRADING_PARTS["5x5x5"], nothing in src/ changed; reaches main with case's L3.4) | rules, L2.10 | — |
| platform | P5b, after P5 merges: ADR-114 Amendment 37 (written): every install names `folders.backups` at setup, no backup ever written inside the checkout, each deployment's sets in their own subfolder, `doctor` naming sets left behind and warning about a synced backups folder; the amendment's table names each test | the owner, 9 November | P5b |
