# admin · T1 part 1: the measured live run and its table (10 November 2026)

**The run.**
- **What it ran:** studio's L1.7 live set, by its own command from `~/osprey-runs/studio.meta/runs/last/cmd.sh`, with
  one file left out (`test_external_runs_live.py`, studio's and not then on main). That is route rights, the whole of
  `tests/ingest` and `tests/conformance/graph_port`, and 20 named files.
- **Where:** the tree was `lane/admin` at 5d9a4a4 (main 2ccdf75 with part 1's commits), on **stack b, under the lease
  admin took at 2026-11-10T10:33Z**.
- **The meter:** `t1/t1_meter.py` was loaded for the run (`-p t1_meter`) and changed no result.
- **Result:** 2,004 passed, 4 failed and 10 skipped, in 12,115 s by pytest. The wall time was 12,117 s (3 h 22 min); the
  wall line then named the lease by its lock directory only, before part 1's review fixed that.
- **Records:** the log is `gates/t1p1-measured.live.txt`, and the meter's 2,018 records are
  `gates/t1p1-measured.meter.jsonl`. `OspreyFlow_Core/.venv/bin/python OspreyFlow_Build/process/lanes/admin/t1/t1_table.py <the meter file> b`, run from the repository root, makes this table from them. Its output is checked against this document.
- **The four failures** were measured, not investigated here. They were on main as it was then, and the
  orchestrator has them:
  - `test_alert_evidence_withheld_live.py::test_a_failure_between_the_graph_commit_and_the_repoint_hides_no_alert`
  - `test_kyc_rules.py::test_a_true_positive_on_a_screening_alert_confirms_its_match_and_a_false_positive_does_not`
  - `test_typology_rule_routes.py::test_the_rule_list_is_the_case_teams_and_nobody_elses`
  - `scenarios/test_phase8_exit_criterion_end_to_end.py::test_phase8_exit_criterion_end_to_end`

**This run is the "before".** It ran before the batched schema (c92eeff) merged, so each `arcadedb_adapter` open
applied the schema one statement at a time.

## Where the time went

2018 tests, 3.36 h of test time (the run's wall: 12,115 s by pytest, 3 h 22 min).

- **Sleeps and polling:** 12.1 min, 6.0% of test time (time inside `time.sleep` and `asyncio.sleep`; an upper bound, since concurrent sleeps are each counted).
- **Tests that reached no store:** 1205 of 2018 (60%), 22.1 min (11.0% of test time).
- **Tests in files that open `arcadedb_adapter` and reached ArcadeDB:** 200, 1.59 h (47% of test time). Each such open applied the schema one statement at a time, about 16 s on a fresh database (the batched schema's live proof), now 0.3 s.


**What it says:**
1. **The schema's set-up was the largest single cost.** Nearly half the run's test time was in the 200 tests whose files
   open their own graph. Each paid about 16 s for a fresh schema; the batched schema now takes 0.3 s for the same open
   (the live proof at f6fe015). An estimate for the same set after the batch: at least 200 × 15 s, about 50 minutes,
   saved. A short re-measure on one file, the same tests before and after, will name the real figure (part 5).
2. **Sleeps are a small share overall (6%), but they make up a few tests:**
   - the PID storyline, 188 of its 222 s;
   - the graph port's chunking cases under Gremlin, about 34 s each in sleeps, and 6 of the 30 slowest;
   - the transaction keep-alive tests, 60 s;
   - the gazetteer copy, 31 s.

   These are part 5's.
3. **60% of the tests in this live set reached no store,** though only 11% of its time. They include the 29
   `[adapter]`/`[stand_in]` cases of `test_run_writes_each_link_once.py`, at up to 159 s each, which reach none. These
   belong in `make test`, offline, once part 2's mark tells them apart.

**The 30 slowest tests**

| # | Test | s | in sleeps, s | stores reached |
| --- | --- | --- | --- | --- |
| 1 | `tests/ingest/test_pid_monitoring_storyline_live.py::test_chapter_nine_raises_exactly_these_alerts_on_the_real_store` | 221.6 | 187.6 | ArcadeDB, Postgres |
| 2 | `tests/ingest/test_run_writes_each_link_once.py::test_a_combined_run_leaves_what_a_run_per_row_leaves[r5_slice-adapter]` | 159.2 | 0.0 | none |
| 3 | `tests/ingest/test_run_writes_each_link_once.py::test_a_combined_run_leaves_what_a_run_per_row_leaves[asserted_link_written_again_with_inferred_writes-adapter]` | 102.2 | 0.0 | none |
| 4 | `tests/ingest/test_run_writes_each_link_once.py::test_a_combined_run_leaves_what_a_run_per_row_leaves[merge_into_an_earlier_load-adapter]` | 100.0 | 0.0 | none |
| 5 | `tests/ingest/test_run_writes_each_link_once.py::test_the_run_sends_one_write_for_each_link_not_for_each_row[adapter]` | 97.5 | 0.0 | none |
| 6 | `tests/ingest/test_run_writes_each_link_once.py::test_each_events_edge_id_is_the_stored_link_between_its_own_ends[adapter]` | 95.4 | 0.0 | none |
| 7 | `tests/ingest/test_run_writes_each_link_once.py::test_a_combined_run_leaves_what_a_run_per_row_leaves[r6_in_seed_order-adapter]` | 77.7 | 0.0 | none |
| 8 | `tests/ingest/test_risk.py::test_a_hidden_alerted_neighbour_leaves_the_score_as_if_it_were_absent` | 75.7 | 0.2 | ArcadeDB, Postgres |
| 9 | `tests/ingest/test_run_writes_each_link_once_live.py::test_a_restricted_pair_for_two_units_is_two_links_each_read_by_its_unit` | 64.1 | 0.3 | ArcadeDB |
| 10 | `tests/ingest/test_run_writes_each_link_once_live.py::test_a_combined_run_reads_back_what_a_run_per_row_leaves_on_a_real_store` | 63.8 | 0.7 | ArcadeDB |
| 11 | `tests/ingest/test_run_writes_each_link_once_live.py::test_a_pair_at_two_classifications_is_two_links_one_seen_without_secret` | 63.6 | 0.3 | ArcadeDB |
| 12 | `tests/ingest/test_run_writes_each_link_once.py::test_a_combined_run_leaves_what_a_run_per_row_leaves[r5_slice-stand_in]` | 62.8 | 0.0 | none |
| 13 | `tests/ingest/test_pipeline_run.py::test_a_fibo_pipeline_loads_accounts_the_bare_core_refuses` | 48.6 | 0.3 | ArcadeDB, Postgres |
| 14 | `tests/ingest/test_case_gazetteer_copies_live.py::test_a_region_is_copied_in_bounded_pages_and_timed` | 46.6 | 31.0 | ArcadeDB |
| 15 | `tests/conformance/graph_port/test_suite.py::test_get_edges_past_one_chunk_returns_exactly_the_readable_ones[graph_arcadedb[gremlin]]` | 43.6 | 33.8 | ArcadeDB |
| 16 | `tests/ingest/test_kyc_rules.py::test_a_confirmed_screening_match_repoints_the_other_alert_citing_it` | 40.8 | 4.1 | ArcadeDB, Postgres, Valkey |
| 17 | `tests/conformance/graph_port/test_suite.py::test_live_edges_touching_past_one_chunk_names_every_link[graph_arcadedb[gremlin]]` | 40.4 | 34.8 | ArcadeDB |
| 18 | `tests/ingest/test_kyc_rules.py::test_a_close_refused_after_its_graph_commit_leaves_the_alert_on_its_confirmed_node` | 40.2 | 3.5 | ArcadeDB, Postgres, Valkey |
| 19 | `tests/ingest/test_alert_evidence_withheld_live.py::test_more_records_settled_at_once_than_the_store_holds_connections_all_finish` | 40.1 | 1.9 | ArcadeDB, Postgres, Valkey |
| 20 | `tests/conformance/graph_port/test_suite.py::test_get_edges_asked_for_an_id_in_the_first_and_the_last_chunk_returns_it_once[graph_arcadedb[gremlin]]` | 39.8 | 33.8 | ArcadeDB |
| 21 | `tests/ingest/test_kyc_rules.py::test_a_close_the_graph_refuses_before_its_commit_leaves_no_repoint_record` | 38.7 | 3.5 | ArcadeDB, Postgres, Valkey |
| 22 | `tests/ingest/test_run_writes_each_link_once.py::test_the_run_sends_one_write_for_each_link_not_for_each_row[stand_in]` | 38.6 | 0.0 | none |
| 23 | `tests/ingest/test_handling_from_columns_live.py::test_a_held_row_is_stored_at_its_rows_marking_and_hidden_from_an_official_reader` | 38.5 | 0.2 | ArcadeDB, Postgres |
| 24 | `tests/ingest/test_kyc_rules.py::test_an_applicant_owned_through_a_trust_by_a_listed_person_is_stopped_at_the_gate` | 38.4 | 3.7 | ArcadeDB, Postgres, Valkey |
| 25 | `tests/ingest/test_run_writes_each_link_once.py::test_each_events_edge_id_is_the_stored_link_between_its_own_ends[stand_in]` | 38.3 | 0.0 | none |
| 26 | `tests/ingest/test_repoint_journal_callers_live.py::test_a_record_whose_writer_is_still_writing_past_the_stale_limit_is_kept[enrich]` | 38.1 | 9.2 | ArcadeDB, Postgres |
| 27 | `tests/conformance/graph_port/test_suite.py::test_get_edges_asked_in_descending_order_across_a_chunk_comes_back_ascending[graph_arcadedb[gremlin]]` | 37.9 | 32.7 | ArcadeDB |
| 28 | `tests/ingest/test_alert_evidence_withheld_live.py::test_a_stale_record_is_dropped_if_its_link_is_live_and_applied_if_superseded` | 37.8 | 0.1 | ArcadeDB, Postgres |
| 29 | `tests/ingest/test_kyc_rules.py::test_a_true_positive_on_a_screening_alert_confirms_its_match_and_a_false_positive_does_not` | 37.7 | 2.9 | ArcadeDB, Postgres, Valkey |
| 30 | `tests/ingest/test_kyc_rules.py::test_the_status_and_risk_are_computed_from_what_the_reader_sees` | 37.7 | 3.1 | ArcadeDB, Postgres, Valkey |

**By file, the 25 slowest**

| File | tests | min | in sleeps, s | tests reaching no store |
| --- | --- | --- | --- | --- |
| `tests/conformance/graph_port/test_suite.py` | 284 | 59.5 | 220 | 3 |
| `tests/ingest/test_alert_evidence_withheld_live.py` | 38 | 20.6 | 16 | 0 |
| `tests/ingest/test_run_writes_each_link_once.py` | 29 | 14.7 | 0 | 29 |
| `tests/ingest/test_repoint_journal_callers_live.py` | 35 | 14.2 | 25 | 0 |
| `tests/conformance/graph_port/test_bulk_loader.py` | 46 | 13.6 | 7 | 0 |
| `tests/ingest/test_kyc_rules.py` | 16 | 9.1 | 33 | 0 |
| `tests/ingest/test_typology_rules.py` | 18 | 7.1 | 4 | 0 |
| `tests/ingest/test_recipe_engine_end_to_end.py` | 15 | 7.0 | 3 | 1 |
| `tests/ingest/test_pid_monitoring_storyline_live.py` | 1 | 3.7 | 188 | 0 |
| `tests/ingest/test_risk.py` | 5 | 3.4 | 1 | 0 |
| `tests/ingest/test_case_gazetteer_copies_live.py` | 10 | 3.4 | 34 | 0 |
| `tests/conformance/graph_port/test_promotion.py` | 17 | 3.3 | 3 | 0 |
| `tests/ingest/test_run_writes_each_link_once_live.py` | 3 | 3.2 | 1 | 0 |
| `tests/ingest/test_studio_publish_pipeline.py` | 8 | 2.7 | 0 | 1 |
| `tests/ingest/test_pipeline_run.py` | 14 | 2.6 | 1 | 3 |
| `tests/ingest/test_pattern_rules.py` | 5 | 2.3 | 3 | 1 |
| `tests/ingest/test_remaining_gazetteers.py` | 7 | 2.1 | 1 | 0 |
| `tests/ingest/test_ownership.py` | 3 | 1.7 | 1 | 0 |
| `tests/ingest/test_crs_reprojection.py` | 5 | 1.4 | 1 | 0 |
| `tests/conformance/graph_port/test_dataset_footprints.py` | 8 | 1.4 | 1 | 1 |
| `tests/ingest/test_handling_from_columns_live.py` | 7 | 1.4 | 1 | 1 |
| `tests/ingest/test_load_report_markings.py` | 10 | 1.2 | 0 | 10 |
| `tests/ingest/test_transaction_keepalive_live.py` | 2 | 1.2 | 60 | 0 |
| `tests/services/api/test_source_refresh_snapshot_live.py` | 5 | 1.2 | 3 | 0 |
| `tests/conformance/graph_port/test_type_aliases.py` | 5 | 1.1 | 1 | 0 |
