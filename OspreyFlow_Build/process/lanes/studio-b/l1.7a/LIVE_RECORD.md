# L1.7a · the live record

Every run was leased by studio-b and run on the server `ospreyflow-test` through `stack_lease.sh remote`, as one
command. The stack was brought down and released after each run.

| Run | Stack | Head | Files | Result |
| --- | --- | --- | --- | --- |
| `live-878f1f8.txt` | d | `878f1f8`, before the first lane review and the rebase | `live_set.sh` (17 files), `-rfE` | 74 passed, 7 failed, 34 skipped |
| `live-c2e3da8.txt` | d | `c2e3da8`, first gated, rebased onto main `15d0d24` | `live_set.sh`, `-rfE` | 74 passed, 7 failed, 34 skipped |
| `baseline-main-15d0d24.txt` | d | main `15d0d24`, in a throwaway worktree (removed) | the 5 files that failed | 5 passed, **the same 7 failed** |
| `live-3064646.txt` | b | `3064646`, the first review round's fixes | `live_set.sh`, `-rA` | 74 passed, 7 failed, 34 skipped |
| `live-51600c6.txt` | b | **`51600c6`, the final gated head** | `live_set.sh` `-rA`, then `live_seed_slow.sh` | 74 passed, 7 failed, 34 skipped; seed 2 passed, 2 failed |

**The 7 fail on main without this branch** (the baseline), and the swap neither causes nor changes them.
- **Datasets and target models:** `test_studio_load_stamps_its_case_dataset_live` (3),
  `test_studio_run_now_stamps_its_case_dataset_live`, `test_snapshot_withdrawal_tells_nothing_live` and
  `test_source_refresh_snapshot_live`. The errors are `SourceUnreadableError` ("That file is not one of this
  dataset's files in the ingest folder") and `target_models.py:79`'s `'list' object has no attribute 'packs'`.
- **Phase 8's exit criterion:** `test_phase8_exit_criterion_end_to_end` has a seed delta of 0 nodes where it
  expects 4.
- They are carried to studio's L1.7 (the orchestrator, CARRIES).

**The slow seed at `51600c6`** (`OSPREYFLOW_RUN_SLOW=1`; the seed is the publish lock's real second writer). It
seeded the whole dataset, committing each recipe through `commit_recipe_file`.
- Passed: `test_a_second_seed_adds_nothing` and `test_the_demo_analyst_fetches_one_picture_through_the_picture_route`.
- Failed, neither from the publish:
  - `test_the_rehearsal_reset_restores_the_starting_state`: `SourceUnreadableError` ("That file is not in the
    ingest folder") from `studio_profile._read_rows`, under `run_published_recipe`. That is the same family as
    main's 7.
  - `test_a_live_reports_run_with_resolution_on_enqueues_a_resolution_job`: `TypeError: publish_reports_fallback()
    missing 1 required keyword-only argument: 'source_location'`, a call outside this branch. In Core, this branch
    changes only `studio_publish.py`, `pyproject.toml` and `uv.lock`.
  - Not run on main for want of a 44-minute baseline: offered as a carry.
- `GitCommitError` appears in none of these runs.

**At the final head, as `-rA` names them:**
- `tests/ingest/test_studio_publish_pipeline.py`, which publishes through `write_and_commit_recipe`: all 8 passed.
- `test_pid_seed_live.py` inside `live_set.sh`: its 4 cases **skipped** (no `OSPREYFLOW_RUN_SLOW`). It ran in full
  in `live_seed_slow.sh`, as above. The earlier runs' "not failed" for it meant skipped.
- `test_route_rights.py` and the rest: `live-51600c6.txt` lists every case.

Every one of L1.7a's own tests is offline. They run in `make test` and are green there (`gates/51600c6.test.*`).
