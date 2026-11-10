# admin · T1 part 4 red record (10 November 2026): each pytest-xdist worker its own stores

Each lever was planted out at its real call site, its test run red, and the file put back and green. The plants
were run by a script, one at a time, offline: closed ports, no lane. The offline cases run a planted test file under
`-n 2` in a subprocess. Each test records the names its worker's code would open, through the calls the Conduit makes:
- `ArcadeDBConfig.from_env(database="ospreyflow")`, by keyword and by position;
- `PostgresConfig.from_env()` and `ValkeyConfig.from_env()`;
- `s3_bucket`;
- the analytics path.

The plugin and its proofs landed in one commit (`196afc4`), so the history does not show the tests red before the
code. What shows it is below.
- **The leak itself:** the same planted run without the plugin, where two workers share every name, kept as a test
  (`test_without_the_plugin_two_workers_share_every_name_the_red`).
- **Each lever planted out on its own.**

| Plant | File | Test | Red |
| --- | --- | --- | --- |
| No plugin: two workers, the same names in every store (kept as a test) | — | `test_worker_isolation.py::test_without_the_plugin_…_the_red` | asserted |
| ArcadeDB's `from_env` not redirected | `OspreyFlow_Build/tests/worker_isolation.py` | `…two_workers_open_different_names_in_every_store` | 1 failed |
| `POSTGRES_DB` not set per worker | the same | the same | 1 failed |
| `VALKEY_DB` left at 0 | the same | the same, and `…more_workers_than_valkey_has_databases…` | 2 failed |
| `MINIO_BUCKET_PREFIX` not set | the same | `…different_names_in_every_store` | 1 failed |
| `ANALYTICS_DB_PATH` not set | the same | the same | 1 failed |
| A per-test `conformance_*` name rewritten too | the same | the same | 1 failed |
| Serial files not grouped | the same | `…each_serial_file_exists_and_is_grouped` | 1 failed |
| **After my lane-reviewer's pass** (11 cases; the plants above re-run on the fixed files, each red again): | | | |
| The group added after xdist reads it (`trylast`) | `OspreyFlow_Build/tests/worker_isolation.py` | `…serial_files_run_on_one_worker_on_the_shared_graph…`, through xdist itself | 1 failed |
| A serial test kept on the worker's own graph while its children open the shared one | the same | the same | 1 failed |
| A worker known by the inherited `PYTEST_XDIST_WORKER` (a nested pytest takes its parent's names) | the same | `…child_that_inherits_a_worker_s_environment…` | 1 failed |
| 16 workers let start, each refusing only once its stores are made | the same | `…refused_before_any_worker_starts` | 1 failed |
| A Valkey client given no `db` not counted as db 0 (`test_schedule_executor.py`'s shape) | `OspreyFlow_Build/tests/test_worker_isolation.py` | `…serial_check_names_a_file_that_should_be_serial` | 1 failed |

**Found by the serial check on its first run (rule 15).** On the live set, the check named three files that the survey
had missed:
- `test_revoked_principal_precheck.py` and `test_valkey_store.py` hard-code Valkey's db 0, and are now serial.
- `test_pid_scale_seed_live.py` was a false match: `scripts.seed_pid` matched `scripts.seed_pid_scale`. The pattern is
  now bounded, and the in-process scale seeder is kept as a planted shape the check must not name.

**Found by the lane review, then checked against the tree.**
- **Two Valkey clients missed.** `test_schedule_executor.py` and `test_studio_load_stamps_its_case_dataset_live.py`
  open Valkey with no `db` at all, which is db 0. The pattern only knew a literal `db=0`, so the check is now read from
  the syntax tree. A pattern cannot follow `db=int(os.environ.get(...))`, which wrongly named
  `test_worker_replicas.py`.
- **Two graphs in the serial tests.** A serial test opened the redirected graph in-process while its children
  opened `ospreyflow`. Now the redirect is off for a serial test's duration.
- **Nested runs.** A nested pytest would have taken its parent's names and dropped them. Workers are now known by
  xdist's `workerinput`.
- **An unbounded sweep.** The sweep would have dropped a running run's names. It now runs only when asked
  (`OSPREY_WORKER_SWEEP=1`).

## Live (stack b, the lease admin took at 17:45:01Z)

Pending the leased run: `tests/test_worker_isolation_live.py`, two workers writing the same key in ArcadeDB,
Postgres, Valkey and the object store, with the plugin each sees only its own; without it (the planted leak) each sees
both.
