# Slice SE7b · SE7 · The two live case-view store tests pass the new `chosen` argument, and a pure test stops a changed signature stranding a live test again (a follow-up of SE7; tests only, no product code)

- **Build id:** SE7 (security lane; the queue rule lets a security build start whatever the queue holds).
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing (SE7 is merged: `518ef97`).
- **Status of this brief:** written by the conductor on 21 November 2026 (night) from GitHub's own log. **GitHub's run on `a56d616` (and, by the same cause, very probably the run on `7479243`) is red in the `conformance` job on exactly two tests: `OspreyFlow_Build/tests/services/api/test_case_views_store.py::test_a_view_round_trips_with_its_lens` (line about 57) and `::test_postgres_turns_a_drawings_boards_into_views_and_back` (line about 201). Both fail with `TypeError: StoredCaseView.wire() missing 1 required keyword-only argument: 'chosen'`.** SE7 (`ac457bb`, merged at `518ef97`) changed `StoredCaseView.wire()` in `OspreyFlow_Core/services/api/case_views.py` so that the count comes from the caller (the visible count, never the stored ids); these two tests need a live Postgres, so they run only in GitHub's `conformance` job and the Mac's gate ("merged with the live step off") never ran them. **The product is right; the tests were not updated.**

## What

1. **The two tests pass the argument the new signature asks for.** Read `StoredCaseView.wire` and how SE7's pure tests (`tests/services/api/test_case_view_counts.py`) and the routes call it; give each live test the count its assertion expects, **as the visible count a caller would supply, not the stored length** (the whole point of SE7 is that the stored count is never put on the wire: do not write `len(read.node_ids)` as the argument to make a test pass unless the test's own subject is that equality, and say why). **Look for every other call of `.wire(` in `OspreyFlow_Build/tests` (grep the whole tree, including the other live files `test_case_views_*`, `test_unconverted_case_merge_live.py` and the harness) and fix any that omit `chosen`.** Report each.
2. **You cannot run these two tests: they need the leased Postgres test stack (rule 14: one holder; the line holds the lease for merges, not builders). Do not take the lease and do not start `make dev-up`. Say in your report that they were not run here and that GitHub's `conformance` job is the check.** The pure test below is the check you can run.
3. **The pure guard (rule 12, the invariant "no test calls `wire()` without `chosen`" is exercised by something that does not need a database):** `OspreyFlow_Build/tests/services/api/test_case_view_wire_callers.py`, pure, red first on main (it must fail on today's tree for the two live tests): it parses every `*.py` under `OspreyFlow_Build/tests` with `ast`, finds every call whose function is an attribute named `wire` on an expression that can be a `StoredCaseView` (a name or attribute chain ending in the view variable; judge by reading how the tests name them: if a plain attribute name match over-reports on another class's `wire()`, restrict by the file's imports and say what you did), and asserts each passes `chosen=`. Plant (rule 15, the shape the code reads at its real call site): a temporary copy of `test_case_views_store.py` with `chosen=` removed from one call; red; green on the real tree. **Say which folders it walks** (a scan-map row is written from that).

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_case_view_wire_callers.py` (red first on main; the plant red; green after the two live tests are fixed).

## Checks

Pure only (store ports pinned to 9): the new test; `tests/services/api/test_case_view_counts.py` and `test_case_views.py` (SE7's pure tests, must stay green); `tests/test_doc_citations_check.py`; `ruff check .` in `OspreyFlow_Core` and ruff format on the files changed. Before your final report run by hand what the conductor runs again: ruff on every file changed and the scan-map check for the test you add.

## Out of scope

Any product code (`case_views.py`, the routes); SE7's rulings (`missing` is 0 for everyone until the store records deletions: the owner's); starting any stack; the other live tests owed.
