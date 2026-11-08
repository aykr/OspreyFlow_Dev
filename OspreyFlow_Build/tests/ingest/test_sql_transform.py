"""The SQL transform's sandbox (ADR-140 decision 12; the redesign's phase 8;
`services/ingest/sql_transform.py`). Each case plants the refusal at the real call site: the save
gate is `staging_catalogue.staging_rule_violations` (what save, Test, a drawer's sample and Deploy
all ask), and the run is `staging_catalogue.run_staging` (what Test and the load both run). What a
mistake would do, and the case that catches it:

- a file or network read (`read_csv`, an `http` URL, `read_parquet` of one), or a second statement,
  reaching DuckDB (`test_the_gate_refuses_…`, and with the gate taken away the sandbox itself
  refuses: `test_the_sandbox_refuses_…_without_the_gate`);
- a SELECT that drops the `_ref` columns, or an aggregate that keeps one row's ref for many
  (`test_a_select_that_drops_ref_is_refused…`, `test_an_aggregate_carries_every_input_row_s_ref`);
- a query over another case's or dataset's staged table, or over anything but its inputs (rule 3:
  `test_a_query_over_a_table_it_does_not_read_is_refused`, the gate and the sandbox both);
- a row the person may not read being in the table, masked or not (`test_a_row_the_reader_may_not_
  read_is_absent`, red with the principal's filter replaced by none);
- a query running without end (`test_a_query_past_its_time_limit_is_stopped`);
- the sandbox's settings being loosened from inside (`test_the_sandbox_cannot_be_unlocked`).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from services.ingest.sql_transform import (
    run_sql_step,
    sandbox_connection,
    sql_gate_problems,
)
from services.ingest.staging_catalogue import (
    StagedRef,
    StagedTable,
    StagingError,
    run_staging,
    source_table,
    staging_rule_violations,
)

from schemas.staging import SqlStep

VISITS = [
    {"booking_id": "VB-1", "pin": "P1", "visitor_name": "S. Whitlow"},
    {"booking_id": "VB-2", "pin": "P2", "visitor_name": "J Pryce"},
    {"booking_id": "VB-3", "pin": "P3", "visitor_name": "A. Khan"},
]
CALLS = [
    {"pin": "P1", "called": "+447700900640"},
    {"pin": "P1", "called": "+447700900641"},
    {"pin": "P2", "called": "+447700900718"},
    {"pin": "P1", "called": "+447700900642"},
]


def _tables() -> dict[str, StagedTable]:
    return {
        "visits": source_table("visits", VISITS, load_id="L:visits"),
        "pin_calls": source_table("pin_calls", CALLS, load_id="L:pin_calls"),
    }


def _step(select: str, inputs: tuple[str, ...] = ("visits", "pin_calls")) -> SqlStep:
    return SqlStep(
        id="calls", kind="sql", inputs=list(inputs), select=select,
        summary="Counts each booking's PIN calls.",
    )  # fmt: skip


COUNTS = (
    "SELECT v.booking_id, v.visitor_name, count(c.pin) AS calls, v._ref AS _ref, "
    "list(c._ref) AS _ref_calls FROM visits v LEFT JOIN pin_calls c ON c.pin = v.pin "
    "GROUP BY v.booking_id, v.visitor_name, v._ref ORDER BY v.booking_id"
)


def _gate(step: SqlStep) -> list[str]:
    return staging_rule_violations(
        [step], sources=["visits", "pin_calls"], lists=[], dataset_id="pid"
    )


def _run(step: SqlStep, **kwargs: object) -> StagedTable:
    return run_staging(
        [step], sources=_tables(), lists={}, dataset_id="pid", **kwargs  # type: ignore[arg-type]
    ).output


def test_a_select_over_its_inputs_runs_and_names_every_input_row() -> None:
    assert _gate(_step(COUNTS)) == []
    out = _run(_step(COUNTS))
    assert out.columns == ["booking_id", "visitor_name", "calls"]  # `_ref` columns are refs
    assert [r.cells["calls"] for r in out.rows] == ["3", "1", "0"]
    first = out.rows[0]
    assert {(r.source, r.row_index) for r in first.refs} == {
        ("visits", 0), ("pin_calls", 0), ("pin_calls", 1), ("pin_calls", 3),
    }  # fmt: skip
    assert all(r.load_id == f"L:{r.source}" for r in first.refs)


@pytest.mark.parametrize(
    ("select", "words"),
    [
        ("SELECT * FROM read_csv('/etc/hosts')", "table function"),
        ("SELECT * FROM visits v JOIN read_csv_auto('x.csv') x ON true", "table function"),
        ("SELECT * FROM 'http://example.invalid/rows.csv'", "is not one of the tables it reads"),
        ("SELECT * FROM read_parquet('https://example.invalid/x.parquet')", "table function"),
        ("SELECT * FROM visits; SELECT * FROM pin_calls", "one SELECT statement, not 2"),
        ("SELECT * FROM visits; DROP TABLE visits", "one SELECT statement, not 2"),
        ("COPY visits TO 'out.csv'", "is not a SELECT"),
        ("ATTACH 'other.duckdb'", "is not a SELECT"),
        ("INSTALL httpfs", "is not a SELECT"),
        ("SELECT * FROM query('SELECT 1')", "table function"),
        ("SELECT booking_id FROM visits", "drops the _ref"),
        ("SELECT * EXCLUDE (_ref) FROM visits", "drops the _ref"),
        ("SELECT FROM WHERE", "cannot be read as SQL"),
    ],
)
def test_the_gate_refuses_what_a_sql_step_may_not_do(select: str, words: str) -> None:
    problems = _gate(_step(select, ("visits",)))
    assert any(words in p for p in problems), problems
    # Rule 2 and the refusal's words: never a value of a row.
    assert not any("Whitlow" in p for p in problems)


def test_the_gate_s_refusal_is_the_sql_gate_s() -> None:
    # The one check the save gate asks is the sandbox module's own (red if the catalogue's gate
    # stops asking it: the dropped-_ref plant above passes the catalogue's other rules).
    step = _step("SELECT booking_id FROM visits", ("visits",))
    assert sql_gate_problems(step) and set(sql_gate_problems(step)) <= set(_gate(step))


@pytest.mark.parametrize(
    "select",
    [
        "SELECT * FROM read_csv('/etc/hosts')",
        "SELECT * FROM 'http://example.invalid/rows.csv'",
        "SELECT * FROM read_parquet('https://example.invalid/x.parquet')",
        "SELECT *, _ref FROM read_text('/etc/hosts')",
    ],
)
def test_the_sandbox_refuses_a_file_or_network_read_without_the_gate(select: str) -> None:
    """The gate taken away: the sandbox still reads no file and no network."""
    with pytest.raises(StagingError) as refused:
        run_sql_step(_step(select, ("visits",)), [_tables()["visits"]], check=False)
    assert refused.value.problems


def test_the_sandbox_refuses_a_second_statement_without_the_gate() -> None:
    with pytest.raises(StagingError) as refused:
        run_sql_step(
            _step("SELECT *, _ref FROM visits; SELECT 1", ("visits",)),
            [_tables()["visits"]],
            check=False,
        )
    assert any("one SELECT statement" in p for p in refused.value.problems)


@pytest.mark.parametrize(
    "select",
    [
        "SELECT booking_id FROM visits",
        "SELECT booking_id, 'x' AS _ref FROM visits",
    ],
)
def test_a_select_that_drops_ref_is_refused_at_the_run_too(select: str) -> None:
    """The run's own check, for a SELECT the static gate cannot judge (a constant named _ref)."""
    with pytest.raises(StagingError) as refused:
        run_sql_step(_step(select, ("visits",)), [_tables()["visits"]], check=False)
    assert any("_ref" in p for p in refused.value.problems)


def test_a_join_that_drops_one_input_s_ref_is_refused() -> None:
    select = "SELECT v.*, c.called FROM visits v JOIN pin_calls c USING (pin)"
    with pytest.raises(StagingError) as refused:
        _run(_step(select))
    assert any("pin_calls" in p and "_ref" in p for p in refused.value.problems)


@pytest.mark.parametrize(
    "kept_one",
    ["any_value(_ref)", "min(_ref)", "max(_ref)", "first(_ref)", "_ref", "'pin_calls#0'"],
)
def test_an_aggregate_that_keeps_one_row_s_ref_for_many_is_refused(kept_one: str) -> None:
    """R15: an aggregate's rows carry every input row's `_ref`, as a list. One row's ref kept for
    many is refused at the gate, before anything runs; a `_ref` grouped on (one row per input row)
    is not one for many, and passes (the case above)."""
    select = f"SELECT pin, count(*) AS n, {kept_one} AS _ref FROM pin_calls GROUP BY pin"
    problems = _gate(_step(select, ("pin_calls",)))
    assert any("list(_ref)" in p for p in problems), problems
    with pytest.raises(StagingError):
        _run(_step(select, ("pin_calls",)))


def test_an_aggregate_carries_every_input_row_s_ref() -> None:
    out = _run(_step(
        "SELECT pin, count(*) AS n, list(_ref) AS _ref FROM pin_calls GROUP BY pin ORDER BY pin",
        ("pin_calls",),
    ))  # fmt: skip
    assert [(r.cells["pin"], r.cells["n"], len(r.refs)) for r in out.rows] == [
        ("P1", "3", 3), ("P2", "1", 1),
    ]  # fmt: skip


@pytest.mark.parametrize(
    "select",
    [
        "SELECT *, _ref FROM other_dataset_bookings",
        'SELECT * FROM "loads/other-load/staged/visits.parquet"',
        "SELECT * FROM visits_secret",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM duckdb_settings()",
    ],
)
def test_a_query_over_a_table_it_does_not_read_is_refused(select: str) -> None:
    """Rule 3: a SQL step reads its declared inputs, this pipeline's own tables, and nothing else:
    another case's or dataset's staged table, a catalogue, a qualified name."""
    assert _gate(_step(select, ("visits",)))
    with pytest.raises(StagingError):
        run_sql_step(_step(select, ("visits",)), [_tables()["visits"]], check=False)


def test_a_qualified_name_is_refused_at_the_gate() -> None:
    # `main.visits` is the input itself in the sandbox, but a qualified name could reach a schema
    # or an attached catalogue elsewhere: the gate reads only bare input names.
    assert _gate(_step("SELECT * FROM main.visits", ("visits",)))


def test_a_python_variable_of_the_same_name_is_never_scanned() -> None:
    """DuckDB's Python client would otherwise read a variable named in FROM from the caller's
    frames; the sandbox turns that off."""
    other_dataset_bookings = _tables()["visits"]  # noqa: F841  (what a replacement scan would find)
    with pytest.raises(StagingError):
        run_sql_step(
            _step("SELECT *, _ref FROM other_dataset_bookings", ("visits",)),
            [_tables()["visits"]],
            check=False,
        )


def _hide(row: int) -> Callable[[StagedRef], bool]:
    return lambda ref: not (ref.source == "visits" and ref.row_index == row)


def test_a_row_the_reader_may_not_read_is_absent() -> None:
    """ADR-140 decision 12: the person's own principal, so a row they may not read is not in the
    table at all, not masked; counted as withheld (rule 2). Red with no filter (the principal
    replaced by an unlimited one): the hidden booking is there."""
    select = "SELECT booking_id, visitor_name, _ref FROM visits ORDER BY booking_id"
    unlimited = _run(_step(select, ("visits",)))
    assert "A. Khan" in {r.cells["visitor_name"] for r in unlimited.rows}
    result = run_staging(
        [_step(select, ("visits",))], sources=_tables(), lists={}, dataset_id="pid",
        may_read=_hide(2),
    )  # fmt: skip
    names = {r.cells["visitor_name"] for r in result.output.rows}
    assert names == {"S. Whitlow", "J Pryce"}
    (report,) = result.reports
    assert (report.rows_in, report.rows_withheld, report.rows_out) == (2, 1, 2)
    # Not even a count over it: an aggregate over the table counts only what the reader may read.
    counted = run_staging(
        [_step("SELECT count(*) AS n, list(_ref) AS _ref FROM visits", ("visits",))],
        sources=_tables(), lists={}, dataset_id="pid", may_read=_hide(2),
    ).output  # fmt: skip
    assert counted.rows[0].cells["n"] == "2"


def test_a_query_past_its_time_limit_is_stopped() -> None:
    many = source_table("visits", [{"n": str(i)} for i in range(400)], load_id="L")
    select = "SELECT count(*) AS n FROM visits a, visits b, visits c, visits d, visits e"
    with pytest.raises(StagingError) as refused:
        run_sql_step(_step(select, ("visits",)), [many], time_limit=0.3, check=False)
    assert any("time limit" in p for p in refused.value.problems), refused.value.problems


def test_a_query_past_its_memory_limit_is_stopped() -> None:
    many = source_table("visits", [{"n": str(i)} for i in range(400)], load_id="L")
    select = "SELECT count(*) AS n, list(a._ref) AS _ref FROM visits a, visits b, visits c, visits d"
    with pytest.raises(StagingError) as refused:
        run_sql_step(_step(select, ("visits",)), [many], memory_limit="64MB", time_limit=20)
    assert any("memory limit" in p for p in refused.value.problems), refused.value.problems


def test_the_sandbox_cannot_be_unlocked() -> None:
    con = sandbox_connection(memory_limit="64MB")
    try:
        for statement in (
            "SET enable_external_access = true",
            "SET memory_limit = '8GB'",
            "SET python_enable_replacements = true",
        ):
            with pytest.raises(Exception, match="locked|disabled|Permission"):
                con.execute(statement)
    finally:
        con.close()
    # And from the step itself: anything but a SELECT is refused before it reaches DuckDB.
    assert any("is not a SELECT" in p for p in _gate(_step("SET memory_limit = '8GB'")))


def test_a_refusal_never_tells_a_cell_s_value() -> None:
    """A DuckDB error can quote a value it could not convert: the words keep the cause only."""
    select = "SELECT CAST(visitor_name AS INTEGER) AS n, _ref FROM visits"
    with pytest.raises(StagingError) as refused:
        _run(_step(select, ("visits",)))
    words = " ".join(refused.value.problems)
    assert "Whitlow" not in words and "Conversion" in words
