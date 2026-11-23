# Slice SE6c · SE6 · Make the SQL connector's read-only check survive a schema its login cannot use; proved on a live Postgres before it merges

- **Build id:** SE6 (privacy). **The owner's ruling of 23 November 2026 (`RULINGS.md`): SE6b stays on main, nothing is reverted, and SE6c is the connector fix alone: steps 1, 2, 3, 5 and 6 below. There is no step 4 (nothing to put back).** GitHub's `conformance` job fails twelve tests of `OspreyFlow_Build/tests/connectors/test_sql_connector_live.py` on SE6b's merge `9a680d5` and on every merge after it (runs `45070698899`, `45078573918`, `45087199508`).
- **Dial setting:** balanced
- **Rounds limit:** the dial's (8)
- **After:** nothing. It starts on main as it is, with SE6b present.
- **Status of this brief:** written by the conductor on 23 November 2026. **The diagnosis below is my reading of the code, not a measurement. Step 1 is the test of it: if the twelve are not red on a live Postgres on main as it is, STOP AT ONCE, change nothing, and write what you ran and saw: the owner then reverts SE6b.**

## What the owner asked, and where this brief differs

The owner asked for: *"the reader can use the mart without being granted the control schema, proved by the SQL connector's live tests on a live stack before it merges."*

**That already holds in SE6b's design, so I read the cause as elsewhere.** `OspreyFlow_Core/services/report_sync/mart.py` (`hiding_statements`, about lines 122 to 143) makes the function the reader's policy asks (`dashboard_is_current`) `SECURITY DEFINER`, so a BI reader reads the mart without any right on `osprey_report_control`. The connector's twelve failing tests do not touch the mart at all: their fixture makes only `nomis_replica_fixture` (`test_sql_connector_live.py` lines 100 to 130).

**What I think happens:** the connector's read-only probe, `_WRITES` in `OspreyFlow_Core/services/ingest/connectors/sql_connector.py` (about lines 43 to 56), runs `has_table_privilege(current_user, quote_ident(schemaname) || '.' || quote_ident(tablename), ...)` for **every table in every schema** of the database. Postgres refuses a by-name lookup in a schema the login has no USAGE on, with `permission denied for schema <name>`. SE6b's live tests in `tests/services/report_sync/test_report_sync.py` create `osprey_report_control` (a fixed name, never dropped by the tests) in the same CI database, so every later connector check meets a schema its reader cannot use and the probe fails. **The first failure's text, "permission denied for schema osprey_report_control", fits; "InsufficientPrivilegeError" on the rest fits; nothing else I read explains why a connector test with no mart in it fails.**

**If that is right, two things are true that the owner should weigh:** (1) the connector has a latent product fault, independent of SE6b: a client's read-only login on any database with a schema it cannot use is refused with a database error instead of being checked (it fails closed, so it is a refusal and not a leak, but it would turn away a good login); (2) the right fix is in the probe, not in a grant. **If the owner prefers a grant-side fix anyway, say so and the brief changes; I do not recommend granting the reader the control schema (that is what SE6b's own test forbids).**

## What (in this order; each red first, planted faults at the shape the code really sees: rule 15)

1. **Reproduce, live, red, on `main` as it is, with SE6b present.** On a **throwaway Postgres** (see "The live stack"), **on one database, not dropped between:** first SE6b's live files (`tests/services/report_sync/test_report_sync.py` and the live case of `tests/services/api/test_report_freshness.py`, about line 89), which create the real `osprey_report_control` schema; then `tests/connectors/test_sql_connector_live.py`. **Expected: the twelve fail as GitHub shows them (`test_a_login_that_can_write_is_refused` first, `permission denied for schema osprey_report_control`).** Keep the output (a file `SE6c_OUT/step1_red.txt` beside this brief's folder; the conductor will read it). **If they are not red, stop: the diagnosis is wrong; the owner reverts SE6b.**
2. **The fix, in the connector's probe only.** The probe asks about tables by their OID (`pg_class.oid`, `has_table_privilege(c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE')`), which does not look the schema up by name. **It must stay as strict as today:** a login that can write any table, in any schema, including one it cannot use, is still refused with the same words ("read-only login only"). A login that owns a table, or is a superuser, is refused as today. State in the report that no refusal was weakened, with the test for each of the three (writable table in a usable schema; writable table in a schema it cannot use; owner/superuser).
3. **Tests.**
   - **Acceptance, pure, red first on main: `OspreyFlow_Build/tests/connectors/test_sql_connector_probe_shape.py` (new).** Reads `sql_connector.py` as one named file and fails if the probe calls `has_table_privilege` with a name built from `schemaname` and `tablename`; a planted copy of today's `_WRITES` text is red, and the fixed text is green. (It reads one named file; it walks no folder.) **The Mac cannot run the live file, so this pure test is what lets the line see "red before, green after"; the live run below is the proof.**
   - **Live, in `test_sql_connector_live.py`:** add cases: (a) a schema the reader cannot use exists beside the fixture, and `check_sql_connection` still passes for the reader and still refuses the writer; (b) a writable table in a schema the writer cannot use is still refused; (c) the existing twelve pass. These need a live Postgres: **they are the proof, run by hand by the builder and again by the verifier.**
4. **(Withdrawn by the owner: nothing to put back. The numbering is kept so his ruling's "steps 1, 2, 3, 5 and 6" reads straight.) Change nothing in SE6b's own files; if a SE6b test fails, stop and report.**
5. **The live proof the owner asked for, before this merges.** On the throwaway Postgres, **in this order on one database, not dropped between:** (i) SE6b's live files, which create the real `osprey_report_control` schema; then (ii) the whole of `tests/connectors/test_sql_connector_live.py` with your fix. **Both green, and the connector file's twelve green with the real control schema present, is the proof**; step 1's red output is the same run before the fix, so the fix is shown to be the cause. Keep the green output in `SE6c_OUT/step5_green.txt`.
6. **Report:** the red and green outputs; the three no-weakening cases; the order of the live run and the database it ran on; and **which other live files make a schema or a role that would meet the same probe** (the conductor lists none today).

## Acceptance test

`OspreyFlow_Build/tests/connectors/test_sql_connector_probe_shape.py` (new, pure, red first). **It walks no folder** (one named source file).

## Checks (pure, store ports pinned to 9; the live run is by hand, below)

The new test; `tests/connectors/` pure files that exist; `tests/services/api/test_removed_identity_mart_rows.py`, `tests/services/api/test_report_freshness.py`, `tests/services/api/test_admin_routes.py`, `tests/services/report_sync/test_report_sync.py` (their pure parts, as SE6b ran them); `ruff check .` in `OspreyFlow_Core`; ruff format on files changed; `make schemas-check` (SE6b changes generated TypeScript). **No `tests/test_layout.py`.**

## The live stack

A throwaway Postgres only (no ArcadeDB needed): a container of its own on a free high port, never the owner's `osprey-local-lite-*` deployment and never port 5432 or 55433 if another session holds it; take `OspreyFlow_Build/scripts/stack_lease.sh`'s lease first (rule 14) and bring it down before releasing it. The builder gives the exact command it ran. **If the seat cannot start a container, it stops and says so; it does not report the live run as done.** The verifier repeats the run from step 5 on its own container.

## Scan-map rows (the owner's rule for the night, 22 November 2026): checked on main before this starts

- `OspreyFlow_Build/tests/connectors/test_sql_connector_probe_shape.py` (new): **walks no folder** (one named file); it needs no row. If the builder's version walks anything, it stops and tells the conductor, which writes a row to `scan_rows/SE6c.tsv` on main first.
- `tests/connectors/test_sql_connector_live.py`, `tests/services/report_sync/test_report_sync.py`: exist; not new; **no row in the scan map**, none needed (neither walks a folder).
- SE6b's tests are on main already and need nothing.
- **Checked by the conductor on 23 November 2026 against the scan map (198 lines):** no row names `tests/connectors/test_sql_connector_live.py`, `tests/services/report_sync/test_report_sync.py` or the new test; none is needed (none walks a folder).

## Out of scope

Any change to SE6b's own design (the stamp, the function, row-level security); granting the reader the control schema; any Conduit route; the protected files; `apps/workspace`; the Makefile and `ci.yml`. **A finding that names a key, a credential or a security rule is stopped and reported, never accepted narrower.**
