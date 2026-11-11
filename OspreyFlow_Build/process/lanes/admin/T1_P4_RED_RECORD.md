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

Two runs, one lease, both logs in `gates/` with secrets masked: `t1p4_live_stack_b_b5d8000.txt` and
`t1p4_live_stack_b_4a66115.txt`.

- **First run, at `b5d8000`.** The isolation proof's red failed for the wrong reason. One worker dropped the probe type
  in the shared `ospreyflow` while the other's DELETE ran (`SchemaException`, "Type with name 'T1Probe_3208680a' was
  not found"). The fix at `4a66115` adds a barrier before DROP TYPE, waits for the type before writing, and adds a
  `clean` step. That step removed what the first run had left: one Postgres table, one Valkey key and one object
  folder, all under `3208680a`. The same run measured the graph_port suite: 483 s serially, 379 s at 4 workers, 282 s
  at 8, all 376 passing each way. That was the plugin as it stood at `b5d8000`, before both reviews, so it is measured
  again at the head.
- **Second run, at `4a66115` (3436 s).** Both tests passed (70 s): with the plugin, each of two workers wrote the same
  key in ArcadeDB, Postgres, Valkey and the object store and saw only its own; without it, each saw both, in all four
  stores.
- **Rule 3's access set: 124 passed serially (1155 s). At 4 workers (2209 s), 75 of the 124 did not pass.** pytest
  reports 49 passed, 5 failed and 94 errors: 70 at setup and 24 at teardown. The JUnit file gives 125 outcomes, since it
  counts `test_an_alert_citing_a_changed_link_follows_it_to_its_successor` twice, once failed and once as a teardown
  error. All 109 error lines are `asyncpg.exceptions.TooManyConnectionsError` ("sorry, too many clients already"),
  raised at a Conduit's start (`TestClient` lifespan) or a store's `connect`.
  - Of the 49 that ran to the end, none saw another worker's row. The other 75 never reached their assertions, so
    they show nothing either way.
  - The likely cause is Postgres's connection limit, not the redirect. It is not proven: there was no control run, and
    stack b's `SHOW max_connections` was not recorded.
  - What points that way: the 46 `create_pool` calls the Conduit can make (45 in `services/api`, one in
    `services/report_sync/mart.py`) have `min_size` adding up to 47. That is a static sum: it does not show the
    lifespan opens them all, and it ignores growth towards `max_size`.
  - Postgres's default `max_connections` is 100 (named at `06_DECISIONS.md:29434`, for the product, not the test
    stacks).
  - **Not yet shown equal at any N.** The orchestrator decided the stacks go to 400 (below). The check is then `-n 4`
    on a stack whose `up` printed 400.

## The test stacks' Postgres at 400 connections (the orchestrator's decision (a), 10 November 2026)

`stack_lease.sh up` now reads each test stack's `SHOW max_connections`. Where it is under 400, `up` runs `ALTER SYSTEM`
and restarts that container alone, then reads the value again. It fails if Postgres never answers or still allows
fewer. The fake docker in `tests/test_stack_lease.py` models the real server's refusals: `ALTER SYSTEM` changes nothing
until a restart, and `psql` fails while the server starts. The recording fakes answer as a Postgres already at 400.

| Plant | Red |
| --- | --- |
| The script before the change | 3 failed (raises to 400; fails when still fewer; fails when it never answers) |
| `ALTER SYSTEM` without the restart | 1 failed (`…raises…to_400…restarts_it_once`) |
| One try, no wait for a starting server | 2 failed (`…raises…`, `…still_allows_fewer`) |

Not yet shown on a real stack: the next leased `up` prints `max_connections 400`.

## After both reviews (10 November 2026 evening)

Each lever, the old ones and those both reviews added, was planted out at its real call site by
`t1/t1p4_plants.py`. Its output, committed, is `gates/t1p4_plants_offline.txt`: one line per plant, naming the failed
tests. The tables above came from runs that were not kept, and that file replaces them as the evidence.

What changed, by finding:
- **A nested run flushed the outer run's Valkey databases** (my reviewer, 4). The controller now exports how many it
  took (`OSPREY_WORKER_VALKEY_TAKEN`), and a nested run's workers count on after them. It is refused before any worker
  starts if that would pass db 15.
- **A nested run's sweep could drop the outer run's stores** (the orchestrator, 3). Names now carry their start time
  (`ospreyflow_x<run>_t<started>_gwN`, as `testing.py` stamps its own). The sweep runs at the start of every live
  `-n` run but takes only names older than six hours, so a running run's are never taken. `OSPREY_WORKER_SWEEP` is
  gone.
- **`-n auto` was refused on the 16-core server** (the orchestrator, 17). It is now given what fits
  (`pytest_xdist_auto_num_workers`).
- **The serial check missed whole shapes** (the orchestrator, 4; my reviewer, 13): a fixed `docker compose -p`
  project, a multiprocessing child, any `-m scripts.…`, `-m cli` or uvicorn child, and Valkey's db 0 given by position
  or in a `**{…, "db": 0}` literal. On the live set it named three files, now in `SERIAL`:
  - `test_apply_env.py`;
  - `test_six_screen_live_exit.py`;
  - `test_sustained_load.py`.
- **Teardown was claimed but not checked** (my reviewer, 5):
  - the live proof now asserts that nothing of its inner run's names is left in any store (`_left_behind`);
  - offline, one store failing to clear does not leave the others, and a start that fails part-way is still cleared.
- **The red run raced on absent shared names** (my reviewer, 7). Each worker now makes what is missing in turn, gw0
  first. The bucket is removed only after both workers' objects are.
- **The live proof ran in CI's `test` job** (my reviewer, 10; the orchestrator, 8). It now needs a lease, or CI with
  `OSPREY_TEST_ARCADEDB_CONTAINER`, which only the conformance job sets.
- **`test_valkey_config.py` assumed db 0 and port 6379** (the orchestrator, 11). It now clears `VALKEY_DB` and
  `VALKEY_PORT`. It was red under `VALKEY_DB=7` (2 failed) and under the offline port pin (1 failed); green after.

## Live at the head (stack e, the lease admin took at 2026-11-10T21:15:07Z)

Logs: `gates/t1p4_live_stack_e_14677db.txt` and `gates/t1p4_live_stack_e_9577288.txt`.
- **`up` on a real stack** printed "Test stack e's Postgres (osprey-test-e-pg): max_connections 400."
- **Rule 3's access set** (test_route_rights.py and the 18 live access-control and withheld-read files): the same 124
  passed serially (1085 s) and at 4 workers (1881 s), with no failure either way. This is the brief's "the same pass
  and fail set". It is slower in parallel, not faster.
  - The cause is not established. Each worker makes its own graph and schema at start, and every access file opens
    its own databases on the one ArcadeDB server. graph_port below shows that server capping the gain at about 2×.
  - That is part 5's question (the slow waits), and it is recorded, not hidden.
- **graph_port at the head:** 376 passed each way; 475 s serially, 241 s at 4 workers (1.97×), 226 s at 8 (2.10×).
  The figures at `b5d8000`, before both reviews, were 483, 379 and 282 s.
- **The isolation proof** at 14677db: its own assertions held in both runs (with the plugin, each worker saw only
  its own key in all four stores; without it, both). Both runs then failed in the new teardown check with
  `KeyError: 'names'`: the planted test replaced, rather than added to, the dict holding its names.
  - Fixed at 9577288. Both tests pass on the same lease (9 s), including the check that nothing of the inner run's
    names is left in any store.

`make test` serial against parallel, offline on the server at d5908a6 (`gates/t1p4_make_test_d5908a6.txt`): the
same 10609 outcomes serially (1889 s), at `-n auto` (408 s, 4.6×) and at `-n 8` (392 s, 4.8×).
- Four failures are the same in all three runs:
  - `test_no_new_drift_beyond_the_allowlist`, the live proof not yet in the ignore lists. It clears with the
    Makefile and `ci.yml` diffs, as shown with both applied.
  - `test_deployment_guard`'s teardown scan, which took the serial check's planted `down -v` string for a real
    teardown. Fixed at 78cd4f8 (the planted shape asks for `ps`).
  - `test_render_memory`'s OpenSearch case and the webapp GPU preflight, which fail on that host whatever the order.
- The first comparison, at 92c66a0's plugin (`gates/t1p4_make_test_first.txt`), differed in three places:
  - each worker's own Keycloak "never became ready" (now the containers group);
  - `test_valkey_config` (fixed);
  - `-n auto` refused on 16 CPUs (now capped).

## After the merger's review of 0d01cfa (10 November 2026, late)

Every lever below is in `t1/t1p4_plants.py`, each shown red in `gates/t1p4_plants_offline.txt`.

- **Teardown did not fail closed** (1). The stores were cleared in `pytest_unconfigure`. That is after xdist's
  worker has sent `workerfinished` (`remote.py`, `pytest_sessionfinish`), and the controller marks the worker down
  and reads only a keyboard interrupt (status 2) from what follows (`workermanage.py`, `dsession.py`). So a store
  that failed to clear still exited 0.
  - The stores are now made at the worker's first test and cleared at its last, in an autouse session fixture
    (`_worker_stores`). A failure either way is that test's error, which the controller counts.
  - It is proved through xdist itself. A planted conftest stands in for the stores, records each make and clear,
    and refuses one on demand. The cases: a clear that fails fails the run, and the others are still cleared; a make
    that fails part-way fails the run, and what it made is cleared.
  - The old in-process unit cases are gone. The one that called the loaded plugin's `pytest_configure` and
    `pytest_unconfigure` would, under `-n`, have overwritten that worker's real state (2).
- **The Valkey cap failed closed only in the simple case** (3):
  - A replacement for a crashed worker (`gw<count + k>`) is refused.
  - Each worker claims its database for its run (`SET NX`, holding the run's id, lapsing after `STALE_AFTER`). A
    database another run holds is refused. The claim's proof is a stand-in that answers as Valkey does: `SET NX`
    on a held key returns None and leaves it.
- **Detection** (4):
  - `run --rm -d` (`test_workspace_bundle.py`) and the TLS fixtures imported relatively (all four of their users)
    are now known; the old pattern matched neither.
  - The serial check knows `--project-name`, and `-p` after `-f` on a later line.
  - Container files now join the serial group, so none runs beside a serial file tearing down a fixed compose
    project.
- **A serial test now gets Valkey's db 0 as well as the shared graph** (5).
  - Of the 14 test files that subscribe to a case channel or connect a socket, two read pub/sub messages:
    `test_repoint_journal_callers_live.py` and `test_valkey_store.py`. Both use a fresh case id per test (`new_id()`,
    a timestamp), and both assert what arrives, not that nothing does. No test asserting that no frame arrives
    exists today.
- **The live proof's inner runs** no longer inherit an outer worker's names (6).
- **Minor:**
  - stores are made only where `OSPREY_LANE` names a lease's holder, as the port guard reads it;
  - a nested run does not sweep;
  - the run's header names its workers and Valkey databases.
- **`make test`'s comparison** (7):
  - it now compares each skip's reason too, and logs the worker count;
  - "clears with the diffs applied" has its log (`gates/t1p4_coverage_with_diffs.txt`);
  - it is re-run at the head below.
  - Its timings are unleased: offline runs on the shared test server, beside other lanes' runs, so they are
    contended figures (rule 14).
