# `test_reports.py` no longer depends on run order: report (away/reports-order)

Away-round builder on the server's build account (D246), branch `away/reports-order` in `~/away-ro`, from
`042c882f2`. Nothing pushed, merged or rebased; `main`, the workflow file and every Makefile are untouched.
Synthetic data only (the file's own fixtures). Owner's ruling of 26 November: the file must not depend on
run order.

## The cause

Three route tests write to the **running app's own** ArcadeDB database, `ospreyflow`, *before* the app
starts: `_case_with_an_alert`, `_case_with_an_alert_and_one_over_a_hidden_link` and `_pole_case` each
opened `ArcadeDBClient(…database="ospreyflow")` and went straight to `apply_schema`. Nothing in the test
created that database. The app creates it in its lifespan (`services/api/run_resources.py`,
`build_run_resources`: `create_database_if_absent()`), which runs only when `TestClient(app)` is entered,
after the setup has already written. On a fresh ArcadeDB the schema is refused; on GitHub it passed only
because an earlier file in the `conformance` job had created the database. The product is right; the
tests' setup was out of order.

## The fix (test setup only; nothing skipped or loosened; no product code)

`e9aca00c0`, `OspreyFlow_Build/tests/services/api/test_reports.py`: one helper, `_app_graph()`, opens the
app's database as the app's lifespan does (create if absent, then the schema) and closes the client; the
three setups use it instead of their own copies. No assertion, test, marker or fixture value changed.

## The stores

`reports_order_with_stores.sh` (beside this report, `32139aad0`), run inside the account's namespace:
`REPO=~/away-ro bash ~/osprey-d246/d246_ns.sh sh ../OspreyFlow_Build/process/lanes/v062/away/reports_order_with_stores.sh <pytest…>`.
It is away/ci-reds's `ci_reds_with_stores.sh` (PostgreSQL 16, ArcadeDB 26.10.1, Redis 7 for Valkey, the
same ports and binaries in `~/ci-reds-pg/`) with two changes:

1. **ArcadeDB is left fresh.** The ci-reds script created the `ospreyflow` ArcadeDB database itself, which
   hides exactly this defect (the CI_REDS report says so under "Found on the way"). The job's service
   starts with none, so this one creates none. Postgres's `ospreyflow` database is still created, as the
   job's `POSTGRES_DB` does.
2. **The fixture passwords are read from the workflow file at run time** (CI's published service values),
   used for these throwaway stores only, and never echoed, logged or written to this repository.

Every run had its own fresh stores, stopped and deleted by the script's trap when it ended.

**A difference from the brief, named:** the brief said to use the build account's own rootless Docker. The
script it pointed to does not use Docker: it starts the stores as plain processes inside the D246
namespace (rootlesskit, the same tool the rootless Docker uses), and that namespace's wrapper refuses any
container from a test run. I followed the script. **I started no container and no volume.** At the end the
account's rootless Docker had one container, `awaylive-pg-…` (`postgres:16`, created seconds before my
check, host `127.0.0.1:58432`), and the machine had an ArcadeDB server in a container's layout. Neither is
mine, so I left both alone. They cannot have touched these runs: the namespace has its own loopback, and
the host's loopback is out of its reach (`--disable-host-loopback`). Another session is active on this
machine, and the owner may want to know which one.

## Red, then green

| Run (each on fresh stores) | Result |
| --- | --- |
| whole file, at `042c882f2` | **red: 3 failed, 10 passed** |
| `test_the_view_and_the_feed_agree_and_the_feed_is_recorded` alone, at `042c882f2` | **red**: `SchemaApplyError … Database 'ospreyflow' is not available` |
| `test_the_feed_counts_no_alert_over_a_link_the_reader_cannot_read` alone, at `042c882f2` | **red**, the same |
| `test_the_pole_figures_count_nothing_the_reader_cannot_read_at_the_route` alone, at `042c882f2` | **red**, the same |
| each of the three alone, at `e9aca00c0` | **1 passed** each |
| whole file, file order, at `e9aca00c0` | **13 passed** |
| whole file, reverse order (collected IDs, reversed, passed in that order), at `e9aca00c0` | **13 passed**. The first test run is a route test, on a fresh ArcadeDB |

`ruff check` on the file gives the same 3 findings before and after (all already there, import order and
the like; none is on a changed line's logic).

## What this does not show

- Only this file was run. The full `conformance` job, in its own order with all its services, is GitHub's
  to run. The change only adds a create-if-absent before the writes, so an earlier file that has already
  made the database changes nothing.
- Other files may write to the app's `ospreyflow` database before the app starts in the same way. This
  brief covered only this file, and I did not look for them.
