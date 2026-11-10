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

**Fail mode reports as an ERROR at teardown.** The test's teardown report is the one turned failed, since a connection
can be made by a fixture's teardown too. pytest therefore lists it as an error, named with the store and the port.

**The mark commit, dry-run** on a scratch copy of today's `OspreyFlow_Build`:
- `python -m tools.write_store_marks` marked 292 files, all of the live set, and `--check` then passed.
  - 254 files got a new `pytestmark = pytest.mark.store`, and 54 of those also needed `import pytest`.
  - The rest extended a mark they already had: the graph port's `parametrize` and the `skipif`s.
- pytest on the copy, by absolute path:
  - `-m store` collected 3342 tests;
  - `-m "not store"` collected none of the live files' tests (3342 deselected).
  - The two collection errors were not the marks'. One was the scratch copy's own (`test_committed_recipes_pin.py` runs
    `git ls-files`, and the copy is no repository). The other is **a defect on main**: the live
    `tests/services/api/test_schedule_notice.py` imports `alert_to_view` from `services.api.watch_routes`, which L2.10
    removed. `make test` leaves live files out, so nothing caught it. It was reported to the orchestrator.

**`make live-collect`** (`makefile-T1p2-collect.diff`, the orchestrator's addition; the owner's Makefile, applied at
merge). `make test` gains a step that imports every live file, offline, and runs none of their tests. It needs no
marks, since pytest imports a file before `-m` deselects anything, so it works today.
- At main 94a74c5 it is **red on the real defect**: exit 2, `ERROR ../OspreyFlow_Build/tests/services/api/test_schedule_notice.py`.
- With that one file left out of the same collection, it is green (exit 0).

So `test_schedule_notice.py` is the only live file on main that cannot import. The orchestrator has carried its fix to
rules, since rules knows what replaced `alert_to_view`. Until then the step is red on main, and that is its purpose.
