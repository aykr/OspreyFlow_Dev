# T1 part 4 · parallel live runs · plan (admin, 10 November 2026 evening)

From the brief on main (`BRIEF.md`, T1 part 4). The spec is silent on parallel test workers; the test database
lifecycle is `packages/adapters/graph_arcadedb/testing.py`'s docstring. No shared test file is
touched: the isolation is one plugin, `tests/worker_isolation.py`, loaded with `-p tests.worker_isolation` on the run's
own command line, so no conftest changes tonight.

## Where each store's name is decided, and the lever

| Store | Today, every live test shares | Per worker (gwN, run id R) | Lever |
| --- | --- | --- | --- |
| ArcadeDB | `ospreyflow`, hard-coded at `run_resources.py:202`, `worker_main.py:160` and 21 test call sites; `ARCADEDB_DATABASE` set by 19 test sites changes nothing for the Conduit | `ospreyflow_xR_gwN` | wrap `ArcadeDBConfig.from_env`: `ospreyflow` only; `conformance_*` per-test names pass through |
| Postgres | `POSTGRES_DB` (default `ospreyflow`) | `ospreyflow_xR_gwN`, created at worker start | `POSTGRES_DB` |
| Valkey | db 0 | db N+1 (so at most 15 workers) | `VALKEY_DB` |
| ClickHouse | per-test names already (`conformance_*`, `conduit_*`, `stateless_*`) | left alone: `CLICKHOUSE_DATABASE` overrides an explicit name (`client.py:96`) | none |
| DuckDB (the default analytics engine) | `ANALYTICS_DB_PATH`, the Data folder's file, single writer | a file in the worker's own temporary folder | `ANALYTICS_DB_PATH` |
| Object store | `ospreyflow-*` buckets | `ospreyflow-xR-gwN-*` | `MINIO_BUCKET_PREFIX` |

Teardown: each worker drops its Postgres and ArcadeDB databases, flushes its Valkey db, deletes its buckets and its
folder, each store tried on its own. A killed earlier run's leftovers (`*_x*_gw*`) are swept only when the top-level
command sets `OSPREY_WORKER_SWEEP=1`.

**What the plugin cannot redirect goes to one worker** (`xdist_group("serial")`, `--dist loadgroup`, required when
`-n` is given): child processes (two `uvicorn` Conduits in `test_statelessness*.py`, `scripts.seed_pid` in
`test_pid_seed_live.py`, which also has a fixed scratch folder, and the live proof's own child pytest) and the files
whose Valkey client ignores `VALKEY_DB` (`db=0`, or no `db` at all). During a serial test the in-process redirect is
off too, so the test and its children open the one shared `ospreyflow` (the lane review's finding: in-process and
child had been on two graphs). The serial tests run one at a time on that worker; nothing else opens the shared name.

## Tests first (rule 15)

1. Offline: each worker's names are distinct and the plugin rewrites `ospreyflow` only; the serial files land on one
   worker; `-n` without `loadgroup` refuses. Red: without the plugin, two workers' names are equal.
2. Live: a planted file under `-n 2`, two workers writing the same key or row in each store and meeting at a barrier,
   each asserting it never sees the other's. Red: the same run with the plugin off fails for every store.
3. Live: rule 3's access-control tests unchanged under `-n 4` (`test_route_rights.py`, the graph_port suite's access
   cases).
4. Measure: the graph_port suite on one commit, one lease, serial then `-n 4` then `-n 8`.

## Decisions taken

- (After the lane review) a worker is known by xdist's `config.workerinput`, never by the inherited
  `PYTEST_XDIST_WORKER`, so a nested pytest is not taken for its parent's worker; the sweep of a killed run's names
  runs only when the top-level command sets `OSPREY_WORKER_SWEEP=1`; stores are made and cleared only under a lease
  or `OSPREY_WORKER_STORES=1` (the live proof's inner run, so it also runs in CI's conformance job).
- Valkey pub/sub channels are server-wide, not per database, and are left shared. The first reason given here,
  "investigation ids keep them apart", was wrong (the orchestrator's review, item 14): tests reuse fixed case ids. A
  publish from another worker only starts a sync against the receiving worker's own stores, so no rows cross, but it
  can send an extra frame to a test asserting that none arrives. That is recorded in the friction row, not fixed.
- `test_revoked_principal_precheck.py` stays serial though it never connects (its `ValkeyConfig(db=0)` matches the
  check): one small file, and the check stays simple.
- Rule 3's live tests under the plugin: the 18 live access-control and withheld-read files plus `test_route_rights.py`,
  serial and at 4 workers, the same pass and fail set (graph_port's own databases are per test, so it measures the
  workers, not the redirect).
- pytest-xdist 3.8.0 and execnet 2.1.2 (both MIT) in Core's dev group, as their own commit at the branch's head.
- The plugin goes on the command line, not into `tests/conftest.py`: the brief says no shared test file tonight. Wiring
  it into the conftest, the lease's `live` verb and the Makefile is a diff for the orchestrator.
- ClickHouse is left alone (see above), a departure from the brief's list. The orchestrator accepted it, in its
  message of 10 November 2026: "The ClickHouse departure is accepted: leave it… Record it in the brief's exit and the
  friction row."
- (After both reviews) Names carry their start time, and the sweep takes only names older than `STALE_AFTER` (six
  hours, longer than the longest run measured, about an hour). It runs at the start of every live `-n` run, with no
  opt-in flag, as the orchestrator's review proposed.
- (After both reviews) A nested run's Valkey databases come after its outer run's, through
  `OSPREY_WORKER_VALKEY_TAKEN`. `-n auto` is given what is left, not refused.
- (After both reviews) The test stacks' Postgres allows 400 connections. `stack_lease.sh up` sets it on each stack it
  starts. This was the orchestrator's decision (a), ratified for that one setting and written into the brief. Only
  the `osprey-test-*` stacks change.
- (After both reviews) The rule 3 access set stays a list of files: the 18 live access-control and withheld-read files,
  plus `test_route_rights.py`. A rule 3 marker would be a change to `pytest.ini` and to each of those files, all
  shared test files, so it is named and left for the orchestrator.
- (After both reviews, the lane review's 14) Without a lane, the plugin still points `POSTGRES_DB` at a database it
  does not make. That is left as it is: such a run has the offline ports, which reach nothing, and the port guard
  refuses any live port without a lease. Refusing it would refuse `make test -n` itself.
- (After both reviews) The plugin's S3 handle (`_buckets`) and its ArcadeDB sweep stay its own. The live proof's
  bucket removal now uses `object_transfer.store_from_env`. The plugin keeps `ObjectStorageConfig`, which `s3_bucket`
  reads, so that the plugin and the code under test see one endpoint. `testing.py`'s sweep takes only `conformance_*`
  names.
- (After both reviews) Wiring the plugin into `tests/conftest.py`, so it no longer needs `-p`, is a diff for the
  orchestrator (`conftest-T1p4.diff`), with the Makefile's parallel `make test` (`makefile-T1p4.diff`).
- (After the merger's review) The stores are made and cleared inside the run (an autouse session fixture), not at
  configure and unconfigure: only a test's report reaches xdist's controller after `workerfinished`. A worker that
  runs no test makes nothing.
- (After the merger's review) Files that start containers join the serial group rather than a group of their own.
  That costs nothing in `make test`, where the serial files are all ignored, and it means no container file runs
  beside a serial file's `down -v`.
- (After the merger's review) CI's `test` job stays serial. `makefile-T1p4.diff` changes the Makefile's `test`
  target only, and `ci-yml-T1p4.diff` changes no worker count. Parallel CI would be a separate change to `ci.yml`.
