# admin · T1 part 2 red record (10 November 2026): the guard in report-only mode, and the mark commit as a script

Each check was planted out at its real call site, its test run red, and the file put back and green. These plants were
run by hand, one at a time. Offline: closed ports, no lane. The guard's cases run a planted test file through pytest in
a subprocess, in the shapes a live test takes: an `arcadedb_adapter` open, `asyncpg.connect`, a Valkey ping, and one
client that swallows every error.

| Plant | File | Test | Red |
| --- | --- | --- | --- |
| Not loaded by the root conftest (the test written first) | `OspreyFlow_Build/tests/conftest.py` | `test_store_mark.py::test_the_suite_s_own_conftest_loads_it` | 1 failed |
| Nothing recorded | `OspreyFlow_Build/tests/store_mark.py` | the report-mode and fail-mode cases | 2 failed |
| The mark ignored | the same | the same | 2 failed |
| Fail mode fails nothing | the same | the fail-mode case | 1 failed |
| Valkey's port not counted as a store's | the same | the report-mode and fail-mode cases | 2 failed |
| Every port counted, not only the stores' | the same | the same (a test reaching its own listener was reported) | 2 failed |
| A single mark replaced, not kept | `OspreyFlow_Build/tools/write_store_marks.py` | `test_write_store_marks.py[a_single_mark]` | 1 failed |
| `import pytest` not added | the same | `[no_import_of_pytest]`, `[nothing_imported]` | 2 failed |
| Any `pytestmark` taken for the store mark | the same | `[a_single_mark]`, `[a_list_on_one_line]`, `[a_list_over_lines]` | 3 failed |
| A one-line list left as it was | the same | `[a_list_on_one_line]` and every live file marked in memory | 2 failed |
| **After my lane-reviewer's pass** (19 cases; the plants above re-run on the fixed files, each red again): | | | |
| The code's default ports ignored (CI's offline job pins none) | `OspreyFlow_Build/tests/store_mark.py` | `…store_ports_are_the_run_s_settings_or_the_code_s_defaults` | 1 failed |
| Fail mode rewriting the call report, not the teardown's | the same | the fail-mode case (a fixture that reaches ArcadeDB at teardown) | 1 failed |
| `connect_ex` not watched | the same | the report-mode and fail-mode cases (a raw `connect_ex` to ClickHouse's port) | 2 failed |
| A clean run leaving the last run's list | the same | `…clean_run_still_writes_its_report…` | 1 failed |
| A tuple nested, not spread (pytest rejects it) | `OspreyFlow_Build/tools/write_store_marks.py` | `[a_tuple]` | 1 failed |
| A bare-name `pytestmark` guessed at | the same | `…bare_name_is_refused_not_guessed` | 1 failed |

**Found by the review, in the tests themselves (rule 15).** The mark tests asserted `"test_a" in` the collection's
output. Five of the planted file names hold `test_a`, and a file pytest cannot import prints its name. So a mark that
pytest refused at import passed for five of the eight shapes. The tests now assert the exit code and the node id
`<file>::test_a`.

**The guard's stated limits** are in its docstring:
- the object store (pyarrow's C++ client, below the socket);
- a child process;
- uvloop in CI;
- a reused pooled connection;
- connections between tests, or a background thread's.

The first version claimed to watch the object store, and could not.

**Fail mode reports as an ERROR at teardown.** The test's teardown report is the one turned failed, since a connection
can be made by a fixture's teardown too. pytest therefore lists it as an error, named with the store and the port.

**The mark commit, dry-run** on a scratch copy of today's `OspreyFlow_Build`:
- `python -m tools.write_store_marks` marked 292 files, all of the live set, and `--check` then passed.
  - 254 files got a new `pytestmark = pytest.mark.store`, and 54 of those also needed `import pytest`.
  - The other 38 extended a mark they already had (`parametrize`, `skipif`, `usefixtures`, `asyncio(loop_scope=…)`).
- pytest on the copy, by absolute path:
  - `-m store` collected 3342 tests;
  - `-m "not store"` collected none of the live files' tests (3342 deselected).
  - The two collection errors were not the marks'. One was the scratch copy's own (`test_committed_recipes_pin.py` runs
    `git ls-files`, and the copy is no repository). The other is **a defect on main**: the live
    `tests/services/api/test_schedule_notice.py` imports `alert_to_view` from `services.api.watch_routes`, which L2.10
    removed. `make test` leaves live files out, and CI's `conformance` job, which does run it, runs only on a push, so nothing caught it. It was reported to the orchestrator.

**`make live-collect`** (`makefile-T1p2-collect.diff`, the orchestrator's addition; the owner's Makefile, applied at
merge). `make test` gains a step that imports every live file, offline, and runs none of their tests. It needs no
marks, since pytest imports a file before `-m` deselects anything, so it works today.
- At main 94a74c5 it is **red on the real defect**: exit 2, `ERROR ../OspreyFlow_Build/tests/services/api/test_schedule_notice.py`.
- With that one file left out of the same collection, it is green (exit 0).

So `test_schedule_notice.py` is the only live file on main that cannot import. The orchestrator has carried its fix to
rules, since rules knows what replaced `alert_to_view`. Until then the step is red on main, and that is its purpose.

**Gates at c34f62b** (on main 76260b0):
- `make -k ci` (`gates/c34f62b.ci.txt`): green apart from Docker's checks.
- `make test`, offline on the server, the orchestrator's run (`gates/c34f62b.test.txt`: no stack, no lease, wall 1614 s,
  set-up 15 s): pytest 10,500 passed, 2 failed (the known GPU and Valkey-host cases), 13 skipped; vitest 2,963 passed,
  1 failed (MatrixView's known timing test).

**The guard's report in that run was exactly `{}`.** No unmarked test in `make test`'s set reached a store's port. That
is expected, since `make test` still `--ignore`s every live file. Fail mode will meet its work only when that list
gives way to `-m "not store"`. The empty file is itself proof the guard ran in the real suite, since it writes its
report on every run. Tomorrow's mark commit must show the same `{}` with `make test` run as `-m "not store"`.
