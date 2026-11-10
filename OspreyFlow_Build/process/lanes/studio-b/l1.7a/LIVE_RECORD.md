# L1.7a · the live record

Each run was leased by studio-b on **stack d**, on the server `ospreyflow-test`, through `stack_lease.sh remote`.
Each set was run as a single command, one after another, and stack d was brought down and released after each.

| Run | Head | Files | Result |
| --- | --- | --- | --- |
| `live-878f1f8.txt` | `878f1f8`, before the lane-reviewer's fixes and the rebase | `live_set.sh` (17 files) | 74 passed, 7 failed, 34 skipped |
| `live-c2e3da8.txt` | `c2e3da8`, the gated head, rebased onto main `15d0d24` | `live_set.sh` | 74 passed, 7 failed, 34 skipped |
| `baseline-main-15d0d24.txt` | main `15d0d24`, in a throwaway worktree (removed) | the 5 files that failed | 5 passed, **the same 7 failed** |

**The 7 fail on main without this branch**, and the swap neither causes nor changes them.
- **Datasets and target models:** `test_studio_load_stamps_its_case_dataset_live` (3),
  `test_studio_run_now_stamps_its_case_dataset_live`, `test_snapshot_withdrawal_tells_nothing_live` and
  `test_source_refresh_snapshot_live`. Their errors are `SourceUnreadableError` ("That file is not one of this
  dataset's files in the ingest folder") and `target_models.py:79`'s `'list' object has no attribute 'packs'`
  (the test's `_Nothing` double).
- **Phase 8's exit criterion:** `test_phase8_exit_criterion_end_to_end` has a seed delta of 0 nodes where it
  expects 4.
- None of the errors is from the publish commit (`GitCommitError` appears nowhere in either run). The baseline's
  identical failures on main, run without dulwich, are what clears the swap. They go to the orchestrator as a
  carry for the owning lane.

**Not failed at the gated head** (each passed or skipped):
- `test_route_rights.py`;
- `tests/ingest/test_studio_publish_pipeline.py`, which publishes through `write_and_commit_recipe` into a
  repository real git made;
- `test_pipeline_run`, `test_staged_run`, `test_staged_pipeline_run`, `test_phase7_exit`, `test_pid_seed_live`
  (the seed's `commit_recipe_file`);
- `test_phase7_stage6c_watch_routes`, `test_recipe_pins_lifespan`, `test_pin_calls_refresh_live`, `test_packs`.

**What these runs do not show.** Each passed or was skipped, but this record cannot say which. The runs used
`-q -rfE`, which names failures and errors but not skips, and the port guard refuses to collect live files without
a lease, so the 34 skips cannot be mapped to files afterwards. A further live run should use `-rA` to name every
case. Every one of L1.7a's own tests is offline: they run in `make test` and are green there
(`gates/c2e3da8.test.explained.md`).
