# Slice SE8g · SE8 · `test_reports.py` no longer depends on run order (a test-only part; the owner, 26 November 2026, conformance (a))

- **Build id:** SE8 (the export ledger) · **Dial setting:** balanced · **Rounds limit:** 6 · **After:** SE8f (merged)
- **Test-only:** no product file changes. No assertion, test, marker or fixture value is loosened or skipped.

## Why (away/reports-order's report, 26 November 2026)

Three route tests' setups (`_case_with_an_alert`, `_case_with_an_alert_and_one_over_a_hidden_link`, `_pole_case`) write
to the running app's own ArcadeDB database, `ospreyflow`, **before** the app starts, and nothing creates it first: the
app makes it in its lifespan (`services/api/run_resources.py`, `build_run_resources`: `create_database_if_absent()`).
On a fresh ArcadeDB, run alone, each is refused (`SchemaApplyError … Database 'ospreyflow' is not available`); on GitHub
the file passes only because an earlier file of the `conformance` job made the database. It is the owner's condition for
conformance (a): the file must pass alone before the server runs the job's list.

## Round 1 (D247; the conductor, 26 November 2026): merge `away/reports-order` first

**Your first step: merge the local branch `away/reports-order` into your branch** (the owner fetched it to the Mac;
D247's exception for away rounds). Its report, `process/lanes/v062/away/REPORTS_ORDER_REPORT.md` on that branch, is the
record: read it whole. Its fix (`e9aca00`) is one helper, `_app_graph()`, that opens the app's database as the lifespan
does (create if absent, then the schema). **Every figure in it was taken on the server under its namespace, not on the
Mac.** Its helper script `reports_order_with_stores.sh` comes in as a record beside the report; do not run it, change it
or copy any value from it (it reads CI's fixture passwords at run time; the owner approved them for throwaway stores on
the server only).

Then:

1. **A guard so it does not recur unseen (rule 12):** a pure test (no store), `OspreyFlow_Build/tests/services/api/test_app_database_made_before_written.py`,
   that reads the test files under `OspreyFlow_Build/tests/services/api/` (by their syntax tree, not by text) and fails
   when a test's setup opens the app's own database (`ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))`
   or its equivalents: say which shapes you read) and writes to it without `create_database_if_absent()` first.
   **Red on main** (it names `test_reports.py`'s three setups), **green after**; a plant at the real shape (the helper's
   create line removed) red, then restored (rule 15). If it names another file than `test_reports.py`, **stop and
   list them** in your report: the owner decides whether this part grows.
2. Say in your report the scan row the guard needs (test, prefixes, reason); the conductor stages it.

## How it is judged

The frozen checks are pure (the Mac is offline). **The store file is judged by the server's early warning and by
GitHub's `conformance` job after the merge.**

## Checks

The new guard test; `pytest --collect-only` on `test_reports.py` (it imports and collects); `test_doc_citations_check.py`;
`ruff check .`.

## Out of scope

Product code; the workflow file and every Makefile; the server's conformance step itself (line-fix's, after this part);
any other test file (listed, not changed).
