# rules-b analytics-field: refusals in words, not bare 500s

An out-of-map change for this step, on the orchestrator's word (14 November 2026). It was found by
case-b and platform-b, and branched from main 4ac03de.

| Item | Status | Proved by |
| --- | --- | --- |
| A field name that is not one is refused before any SQL, by both adapters, with the port's `AnalyticsFieldRefused` (`FIELD_NAME_RULE`; the name sent is never held or echoed) | done | conformance `test_a_field_name_that_is_not_one_is_refused_in_the_ports_words` × 9 field sites × 2 adapters; the smuggle case now expects the typed refusal |
| Every route answers it 422 `field_name_refused`, the words exact | done | `tests/services/api/test_analytics_field_refused.py` (7 bodies over 5 routes, real DuckDB adapter, table intact after) |
| A7 over the wire: 422 with the exact body, not `>= 400` | tightened, **not run** (needs a rendered deployment) | `test_a7_an_unknown_field_name_is_refused_rather_than_ignored` |
| A total of amounts at or past 10^28 is refused in the port's words (`AMOUNT_TOTAL_RULE`), answered 422 `amount_total_out_of_range` | done | conformance `test_a_total_past_the_decimals_range_is_refused_never_wrapped` (the words on both adapters); `test_rule_sentence_routes.py::test_a_preview_whose_total_is_too_large_to_count_is_refused_in_words` |
| Spec | done | spec 08's A7 "Closed" section; a dated note under ADR-133 Amendment 10 |

## Shown red (rule 15)
- `plants.txt` (offline, DuckDB): 11 plants, every one red. Each was made at its call site: the old bare
  `ValueError`; the guard dropped; geocode's property past the guard; no handler; the handler answering
  400; no amount handler; the 10^28 check skipped; DuckDB's overflow let through raw. Controls: the DuckDB
  suite 145, the field route test 7, the rule-sentence routes 10.
- `live.txt` (stack f, rules-b's lease): the analytics_port suite on ClickHouse, 145 passed.
  `live-plant.txt`: ClickHouse's guard planted back to its bare `ValueError`, 10 failed. Restored, then
  the stack was brought down and released (`live-up.txt`, `live-down.txt`).

## Gates (via `stack_lease.sh offline`)
- `make -k ci` at 23b9ce5: exit 0 (`make-ci.txt`).
- `make test` at 23b9ce5: exit 2, 13538 passed and 3 failed, JS all green (`make-test.txt`). None of the
  three is this change's:
  - `test_service_inventory`: `services/search_index`, a folder holding only `__pycache__`, was left
    in the worktree by the D(iii) branch. It has been removed locally, and the test passes.
  - `test_worker_isolation`, `test_write_store_marks` and make's `live-collect`: main's Makefile
    (602b139) names `tests/services/search_index/test_feed_live.py`, which is not on main until
    rules-v052-index lands. Main fails these the same way. This branch does not touch the Makefile.

## Shared files
None. No Makefile, ci.yml or registry change is needed: the new test file is in `make test`'s default
collection, and the coverage check shows no drift.
