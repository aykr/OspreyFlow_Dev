# Platform-b · stateless · GitHub's `conformance` job: the second Conduit refused by Postgres

13 November 2026, on `sol`, offline (no lane stack, no server). From `gh run view 43310891764 --log-failed`.

**What fails.** `test_statelessness.py` and `test_statelessness_clickhouse.py` start two real Conduits beside the
suite's own stores. The second exits at start-up: `asyncpg.exceptions.TooManyConnectionsError: sorry, too many clients
already` (the reason CI fix 2 now prints). GitHub's `postgres:16` service runs at its default `max_connections` 100.

**Why, measured** (`probe_connections.py`: real Conduits from main 7b664a3, a throwaway Postgres 15 on this Mac, ArcadeDB
a stand-in answering every command with an empty result, since start-up asks it first):
- at 100 (`red-100.raw.txt`): one Conduit up holds **50** client connections (51 with the probe's own `psql`); two fill
  the 100, so the probe's own `psql` is refused; the third exits with GitHub's own words. In CI the suite's own pools
  hold the rest, so there the second fails.
- at 400 (`green-400.raw.txt`): three Conduits up, 151 held.

Fifty is the Conduit's stores' pools at their minimum (about 45 pools at `min_size=1`, two at 2). The lane stacks have
allowed 400 since 10 November for exactly this (`scripts/stack_lease.sh`, `PG_CONNECTIONS`, "one Conduit's asyncpg pools
open 47 connections at their minimum"); CI never followed. That is why the same tests pass on the server.

**Fix (the owner's, `.github/`):** `ci-postgres-connections.diff`: the `conformance` job raises its Postgres to 400
(`ALTER SYSTEM`, a restart of that service container, ready-wait, read back), as `stack_lease.sh` does. No product code
changes.

**Guard (rule 12):** `tests/test_ci_postgres_connections.py` holds the job to the lane stacks' `PG_CONNECTIONS`: red on
main's `ci.yml`, red with the diff planted at 300, green with the diff (`guard.raw.txt`). It is red on main until the
diff lands, so the two merge together; `test-file-coverage-check` is green with both.

**Proof on GitHub, at the owner's next push:** `conformance` green, or red with a reason other than connections.

**Finding beyond CI, not changed here:** a deployed Small's own Postgres is rendered with no `max_connections` (the
default 100), and one Conduit holds 50 at rest, beside Keycloak, the gateway's database, Superset and any worker. A
second Conduit replica, or a worker with the same stores, would meet the same refusal. Worth a CARRIES row: either bound
the stores' pools (`min_size=0` where idle is the norm) or render `max_connections` with the product's own number.
