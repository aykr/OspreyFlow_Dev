# T1 part 4 · parallel live runs · plan (admin, 10 November 2026 evening)

From the brief on main (`BRIEF.md`, T1 part 4) and spec 04 §1.4 (the test database lifecycle). No shared test file is
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
folder. The controller sweeps leftovers of a killed earlier run (`*_x*_gw*` names only, on the lane's own leased stack).

**What the plugin cannot redirect goes to one worker** (`xdist_group("serial")`, `--dist loadgroup`, required when
`-n` is given): child processes (two `uvicorn` Conduits in `test_statelessness*.py`, `scripts.seed_pid` in
`test_pid_seed_live.py`, which also has a fixed scratch folder) and the four files that hard-code
`Valkey(..., db=0)`. They run one at a time, as today, while the rest runs in parallel.

## Tests first (rule 15)

1. Offline: each worker's names are distinct and the plugin rewrites `ospreyflow` only; the serial files land on one
   worker; `-n` without `loadgroup` refuses. Red: without the plugin, two workers' names are equal.
2. Live: a planted file under `-n 2`, two workers writing the same key or row in each store and meeting at a barrier,
   each asserting it never sees the other's. Red: the same run with the plugin off fails for every store.
3. Live: rule 3's access-control tests unchanged under `-n 4` (`test_route_rights.py`, the graph_port suite's access
   cases).
4. Measure: the graph_port suite on one commit, one lease, serial then `-n 4` then `-n 8`.

## Decisions taken

- pytest-xdist 3.8.0 and execnet 2.1.2 (both MIT) in Core's dev group, as their own commit at the branch's head.
- The plugin goes on the command line, not into `tests/conftest.py`: the brief says no shared test file tonight. Wiring
  it into the conftest, the lease's `live` verb and the Makefile is a diff for the orchestrator.
- ClickHouse is left alone (see above). The graph_port sweep's one-hour window is kept; no test runs that long.
