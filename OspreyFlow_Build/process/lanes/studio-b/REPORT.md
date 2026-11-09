# studio-b lane · report · L1.6 (phase 9: connectors, and the screening-list connector; ADR-140 Amendment 13), 9 November 2026

1. **Phase 9's exit: met.** `visit_bookings` is registered from a synthetic NOMIS replica through the register route with an incremental watermark, and *Refresh now* reads only the new rows (`test_sql_connector_live.py::test_the_exit_…_through_the_routes`). A SQL source's file then loads only the new row into ArcadeDB (`…::test_a_sql_sources_refreshed_file_loads_only_new_rows`). SQL, API and JSON connections all name their secret and never hold it (`test_connector_schemas.py`, `test_connector_routes.py`).
2. **Each template maps its golden file: met.** There are seven templates: OFAC SDN, OFSI, UK Sanctions List, UN, EU, OpenSanctions and blank. All golden files are synthetic, and each format template's output equals its adapter's own golden file (`tests/connectors/test_list_templates.py`).
3. **A rule offers only subscribed lists; another dataset's list never: met at the route.** `test_list_connector.py` (offered equals what the gate reads), `test_list_connector_routes.py`, `test_subscribed_lists_seam.py`. The rule's picker itself is the rules lane's (requested).
4. **Import idempotent per version: met,** proven on the real keeper too (`test_list_rows_parquet_live.py`).
5. **Import replaces L1.4's stand-in: met.** A dataset's own list is imported from its own files, and the seam is wired for the gate, Test, the drawer's sample and the run. The stand-in's CLI is retired.
6. **Keyboard (rule 13) and axe: met.** `sources-connectors.spec.ts` has 12 ids (the diff is in `L1.6_action_registry.diff`). `every-harness` covers 10 states in dark, light and GOV.UK: 40 passed.
7. **Live, under lease studio-b on stack b,** twice: 22:39Z–22:54Z and 23:31Z–23:34:51Z. 110+13 passed. The two failures are main's own (`L1.6_RED_RECORD.md`), and no timing figure is claimed.
8. **Lane review: done.** The lane-reviewer found 19 items: 3 blocking, 11 must-fix, 5 minor. All are fixed with red-then-green except item 14's second store, which is put to the owner, and item 17, which is moot once the failure's words were hidden from source authors.
9. **Gates at 64bf352** (`gates/`, explained in `64bf352.explained.md`). The lane's failures are fixed at 9092601. Two place tests met ADR-146 decision 2 (`load_screening_lists` acting only in Rules and Monitoring), which conflicted with Amendment 9's import in Studio › Sources. The orchestrator ruled (a): ADR-146 Amendment 3 is written and the place test's rule changed, shown red. The final gates are at the head in `gates/`.
10. **Left:** scheduled polling of SQL and API sources (waits on R17); Admin › Connections' fields (admin lane); the rule's list picker and re-screening against Studio lists (rules lane, after the owner rules on the store of record); pruning an incremental file.
11. **Requests at merge:** ratify the files below; mark ADR-140 Amendment 13 and ADR-146 Amendment 3 "written". **Questions:** the store of record (with the owner). **Running:** nothing; no lease held.

## Decisions taken (each logged for the owner to overrule)

- **`connectors/**` ownership** (A) read as covering `services/ingest/connectors/**`; ratified by the orchestrator (R2).
- **A connector read lands as a CSV in the dataset's folder** (A, versus a new run path per kind): one run path, watch, watermark and confinement for all sources.
- **Secrets by name from `deployment.env`** (`OSPREY_CONNECTION_SECRET_<NAME>`; A, versus a new secret store): every owned service reads the file (`harness/render.py`).
- **The egress "request" is a refusal naming the operator** (A, versus a request queue): `OSPREY_CONNECTOR_EGRESS` is set only by an operator.
- **SQL: table and columns only** (A, versus an expert query): the sandboxed SELECT is L1.5's.
- **Incremental files keep earlier rows** (A, after review item 5; versus advancing the cursor only on load): nothing is lost, and each run's watermark dedupes.
- **The UK Sanctions List gets a template too** (A): OFSI's list closed on 28 January 2026.
- **Deployment-list routes under `load_screening_lists`** (A, as ADR-133's): reconciled with ADR-146 by its Amendment 3 (the orchestrator's ruling (a)).
- **Subscriptions under the Sources step's gate** (`add_ingest_files` and the source author role, A).
- **Own-list import reads the dataset's own files, with no SHA check** (A): a dataset's data is the user's, as any source file; rule 9 binds the repository and CI.
- **The stand-in's `import_list` kept as the tests' synthetic seed;** only the CLI is retired (A).
- **The store of record: this one (a), as logged;** ADR-133's store and Lists tab are left fully working until the owner rules.

## Files outside the lane's map (ratification asked)

`services/api/connector_reads.py` (the Sources step's read service); `app.py`'s *Test connection* route (R4) and `_MonitoringSchedules`' optional field (the list scheduler); `studio_staging.py`, `studio_verify.py`, `pipeline_run.py`, `recipe_run.py`, `run_resources.py` and `reference_list_import.py` (R3's seam); `tests/services/api/{test_route_rights,test_run_resources,test_recipe_run_path,test_place_routes,test_admin_sections}.py` and `tests/ingest/test_reference_list_rows.py` (tables naming the new routes and stores); `shell/placesByRole.json` (the rules lane's record); `keyboard/actionRegistry.ts`, `a11y/every-harness.spec.ts`, `OspreyFlow_Build/Makefile` and `.github/workflows/ci.yml` (shared; also carried as diffs).

## Commits

`git log main..lane/studio-b`: the schemas commit first (`d9ad737`-line), templates, the list service, routes, connectors, the Glass, keyboard and a11y, CI, the spec, friction, the review round, the seam, and the gate fixes (`9092601`).
