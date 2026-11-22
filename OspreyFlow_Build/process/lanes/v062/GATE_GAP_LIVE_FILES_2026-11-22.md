# How many files filed as live need no stack, and so never run before a merge (22 November 2026, 15:42 UTC)

**The owner's question (22 November, with the choice (b) on `test_route_rights.py`).** Written by the conductor from a measured run, with its limits stated.

## The answer

- **The live set is 325 test files** (`python -m tools.live_select --all`, from `OspreyFlow_Build`): the files and folders in the `make test` target's `--ignore` list. `make test` does not run them; it only imports them (`live-collect`).
- **At least 45 of the 325 need no stack at all, by a measured run.** I ran the 78 whose text shows no store (no `mark.store`, no ArcadeDB, Postgres, Valkey, ClickHouse, object-store, Docker, `_live` or stack-lease word) in one process with every store port the guard watches pinned to a closed port (`ARCADEDB_HTTP_PORT`, `POSTGRES_PORT`, `VALKEY_PORT`, `CLICKHOUSE_HTTP_PORT`, `LITELLM_PORT`, `OPENSEARCH_PORT` all 9), at low priority, 6 minutes 55 seconds: **858 tests passed, 40 failed, 83 errored, 15 skipped.** Per file: **45 pass every test; 30 have a failure or error with the stores closed (they need a stack); 3 skip everything.**
- **42 of the 45 are under `tests/ingest/`, and 3 are conformance guards** (`tests/conformance/analytics_port/test_guard.py`, `tests/conformance/model_port/test_guard.py`, `tests/conformance/model_port/test_suite_extract.py`). The list is below.
- **Why they never run before a merge: the Makefile ignores the whole folders `tests/ingest`, `tests/golden` and `tests/conformance/model_port` by folder, not by file.** So a file that needs nothing is ignored with the ones that do. The Studio's staging, recipe-rule, handling and transform tests (the `test_pid_recipe_*`, `test_staging_*`, `test_handling_*`, `test_pipeline_*` files) are among the 45, and none of them ran on the Mac's gate or on the demo server.

## What the number is not

- **It is a lower bound.** The 247 files whose text shows a store were not run (a run of all of them against closed stores is possible but I judged it unsafe unattended: the object store is reached by a C++ client the port guard cannot see, `tests/store_mark.py` says so). **Many of them hold single tests that need no stack**, as `test_route_rights.py::test_every_route_names_the_right_the_table_gives_it` does (the choice (b) above). I have not counted those.
- **"Passed with the stores closed" is not "needs no stack" for certain.** A test that reaches the object store alone, or a child process, would not be seen failing. The 45 files' text names none of them, so I read the figure as 45 files to check, not 45 proven.
- **The 30 files that failed** may fail for another reason on this machine (a missing tool, the load); I did not look at each.
- **A pass with the stores closed does not show the test would also pass when it is added to `make test`**: it ran at low priority in one process, not under `-n` with the other files.

## What follows, if the owner wants it

A second diff to the Makefile that replaces the three folder-level `--ignore`s with file-level ones for the 30 files that fail and the files in those folders not in the 45, so the 45 run in `make test` as part of the existing line. It is larger than the one-line diff of `GATE_GAP_ROUTE_RIGHTS.diff`, touches `live_select`'s view of the live set, and needs `test-file-coverage-check`'s ci.yml list kept in step (ci.yml is the owner's). **I have not written it; the owner decides whether he wants it.**

## The 45 files (module names, from the run)

`tests.conformance.analytics_port.test_guard`, `tests.conformance.model_port.test_guard`, `tests.conformance.model_port.test_suite_extract`, and under `tests.ingest.`: `test_account_ref_engine`, `test_committed_recipes_pin`, `test_dedup_key`, `test_deduplicate_problems`, `test_events_carry_their_load`, `test_handling_from_columns_review`, `test_handling_read_paths`, `test_link_spans`, `test_load_report_markings`, `test_named_packs`, `test_node_preview_access`, `test_optional_bindings`, `test_osm_gazetteer_connector`, `test_phase7_exit`, `test_phase8_exit`, `test_pid_monitoring_recipes`, `test_pid_recipe_r1`, `test_pid_recipe_r11`, `test_pid_recipe_r14`, `test_pid_recipes_pass_rules`, `test_pid_seed_order`, `test_pipeline_extract_markings`, `test_pipeline_graph`, `test_recipe_rules`, `test_reference_list_rows`, `test_rerun_events`, `test_row_elements`, `test_run_yields_the_loop`, `test_site_grid_connector`, `test_sql_transform`, `test_staged_counts`, `test_staged_pipeline_run`, `test_staging_catalogue`, `test_staging_golden`, `test_staging_marked_rows`, `test_staging_pipeline_nodes`, `test_structured_transform_parts`, `test_subscribed_has_no_default`, `test_transform_connector_defaults`, `test_typologies`, `test_visits_pipeline_fixture`, `test_watermark`.
