# v0.6.0 fix: resolution with an all-empty date of birth (rules-b, 16 November 2026)

**The failure.** v0.6.0's package test on 0c158b8: the worker's job `01M7HH04PV17TWBRPNKRZXGQ26`
(`resolve_entity_type`) failed with `_duckdb.BinderException: No function matches ... 'year(INTEGER)'` from
`linker.predict()` (`services/resolve/resolver.py:63`).

**Why.**
- R1's load maps a Person's names and a phone alone, no date of birth (`platform/gates/r1_kind_row_template.yaml`).
- A resolution run reads every Person in the deployment (`services/resolve/trigger.py`), and in R1 none has one.
- `_nodes_to_dataframe` therefore built an all-`None` object column, which DuckDB types as INTEGER.
- `Person`'s blocking rule `year(date_of_birth)` (`packages/ontology/default.yaml:134`) cannot bind INTEGER.

The bug is not new: the resolver's content is unchanged since 18 September, and the post-ingest enqueue has been
there since Phase 6. The failure was silent: the worker marks the job failed and logs it, and nothing reads that.

**The fix.** `_nodes_to_dataframe` gives a DATE or DATETIME column that is empty in every row a `datetime64` dtype
of `NaT`. DuckDB reads it as a TIMESTAMP of NULLs, which `year()` binds. A column with any date in it is left as it
was.

## Proof
- **Red first** (`red-first.txt`), on main ec28df1: the two new cases raise `year(INTEGER)`. The third (dates of
  birth unchanged) passes before and after, as it should.
- **Plants** (`plants.py`, `plants.txt`): 5 of 5 wrong fixes caught by the three cases:
  - no fix;
  - every date column emptied;
  - `any()` for `all()`;
  - the empty column typed as text;
  - the failure swallowed into no candidates.
- **ruff** (check, and format on `resolver.py`) and **mypy** on `resolver.py`: clean. `test_resolver.py` was
  already unformatted on main (line 61), and is left so.
- **Offline**, pinned to dead ports, on the Mac: `tests/resolve`, the resolution scenarios
  (`test_phase6_extraction_and_resolution.py`, `test_fixture_corp_shape.py`,
  `test_phase8_exit_criterion_end_to_end.py`), `tests/services/api/test_evaluation.py` and `test_seed_pid.py`.
  - 250 passed. Every one of the other 27 (11 failed, 16 errors) is a connection to the absent Postgres, ArcadeDB
    or Valkey; none is an assertion.
  - Those 27 need a stack. See "Live" below.
- `changelog_check.py --tag v0.6.0` and its tests pass.

## Live
Not run at the time of the ready-to-merge message unless recorded below.

## Left out
A numeric or year-only date of birth (`year(BIGINT)`, or `ValueError` in `date.fromisoformat`): `CARRIES.md`, as
the orchestrator ruled.
