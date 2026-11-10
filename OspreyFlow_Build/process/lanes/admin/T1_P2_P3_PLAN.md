# admin · T1 parts 2 and 3 plan (10 November 2026)

From the brief (`process/lanes/admin/BRIEF.md`):
- **part 2:** live runs carry only what needs a store; an unmarked store test fails loudly;
- **part 3:** live tests are selected by what changed, with the full set nightly.

The carry from the batched schema: `test-file-coverage-check` decides what is live by the names a file imports.

## Today

What is live is a file list held in three places: the Makefile's `test` target (`--ignore=` ×~170), its `test-live`
target, and `ci.yml`'s live jobs. `test-file-coverage-check` holds the three to one another, and guesses which files
need a store from the names they import. It is wrong both ways:
- an offline `MockTransport` test reads as live;
- a test that reaches a store through a fixture, and imports no marker name, reads as offline.

A whole file is live or not. Part 1's measured run shows live files holding tests that need no store, and these then
run nowhere offline.

## Part 2: one marker, enforced where the connection is made

1. `pytest.mark.store`, registered in `pytest.ini`: "needs a real store (ArcadeDB, Postgres, Valkey, ClickHouse, the
   object store)".
2. **Enforcement at the real call site.** `tests/port_guard.py` already wraps `socket.socket.connect`. It is extended
   so that a connection to any pinned store port, made while an unmarked test runs, fails that test with
   `UnmarkedStoreTest`. Like `LivePortRefused`, this is not an `OSError`, and it names the test, the store and the port.
   This replaces the import-name guess with what the test actually does.
   - Red first: an unmarked test planted in the real shape (an `arcadedb_adapter` open, an `asyncpg.connect`, a
     Valkey client) fails loudly. A marked one passes.
3. **Marking.** One `pytestmark = pytest.mark.store` line at the top of each live file, a mechanical change of one
   line per file, made in one commit so lanes rebase over it. A mixed file, whose no-store tests the meter's table
   names, keeps the module mark at first. Splitting those tests out is part 2b, file by file, each one's owner's.
4. **Selection by marker.** `make test` becomes `pytest -m "not store"` with no `--ignore` list, and a live run
   becomes `pytest -m store`. This is a Makefile diff, the owner's. `ci.yml`'s live jobs select by marker and
   folder, also a diff.
5. **`test-file-coverage-check`** changes to: every file holding a store-marked test is reached by a live job; no
   file is listed twice. The name heuristic goes, and the runtime guard is the classifier.

## Part 3: selection by change

Built on today's live set, the Makefile's `--ignore` list, which part 2's marks replace later. `OspreyFlow_Build/tools/live_select.py` and `OspreyFlow_Build/tools/live_map.tsv` give, for
a lane's diff against main:
- the live test files whose imports reach a changed Python file (including imports inside functions, and
  modules named in a string);
- for paths imports cannot see, a rule from the map (`none`, `all`, or named tests);
- the full set for any path no rule covers, and for a removed Python file;
- `test_route_rights.py` always, so the selection is never empty.

`stack_lease.sh live <lane>` runs that selection (with `-m store` once part 2 lands). The full set stays a nightly run on main, the
orchestrator's to schedule.
- Red first: a change under an unmapped path selects the full set; an empty diff selects route rights; a change
  to the graph adapter selects `conformance/graph_port`.

Measured over main's last 18 lane merges, each merge's diff selects 184.5 of the 291 live files on average (63%); 11 needed all of them, since they touch modules nearly every live test imports (`T1_P3_RED_RECORD.md`).

## Order

Part 3's selector and its tests come first: they are in scripts only, with no file outside admin's map. Then part 2's
guard, its marker and its red. The one-line marks across the live files follow as their own commit. Finally the
Makefile and `ci.yml` diffs, applied at merge.

## Carries for the mark commit (part 2, tomorrow), from my lane-reviewer's second pass

- **Mark what needs a store, not all that is live.** The `--ignore` list also holds files needing a model, Keycloak or
  Docker: `conformance/model_port`, `recognise_port`, `golden`, `test_revoked_principal_precheck.py`, and the harness
  image and bundle tests. Mark those with their own marker (`live`), or leave them out of `store`, using the guard's
  report from a full live run (`OSPREY_STORE_MARK_REPORT`). This decides what `-m store` and `-m "not store"` mean.
- **One commit, in this order:**
  1. the script;
  2. `tools/live_select.py` reading the marks, not the Makefile;
  3. `test-file-coverage-check` reading the marks, so the name heuristic goes;
  4. the Makefile and `ci.yml` diffs;
  5. `OSPREY_STORE_MARK=fail`.

  Each of the first three reads the `--ignore` list today, which the Makefile diff removes.
- **Before fail mode,** run report mode once over `make test` and record how many unmarked tests reach the closed
  ports. Then decide the exemption for a test that exercises the "store unavailable" path on purpose.
- **The guard's blind spots**, each named in its docstring:
  - child processes: follow them as `port_guard_site` does;
  - uvloop in CI;
  - pooled connections;
  - attribution between tests;
  - xdist (part 4): one report per worker, and the controller prints nothing.
- **Rule 11:** an ADR-142 amendment and a `SESSIONS_RUNBOOK.md` §4 entry for the marker and the duty to mark a new store
  test, with the `ci.yml` gate comment updated. The marker is registered in `tests/store_mark.py`, not `pytest.ini`.
