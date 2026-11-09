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
from pathlib import Path

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
    {"pin": "P1", "called": "+447700900650"},
    {"pin": "P1", "called": "+447700900651"},
    {"pin": "P2", "called": "+447700900758"},
    {"pin": "P1", "called": "+447700900652"},
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
        [step], sources=["visits", "pin_calls"], lists=[], dataset_id="pid", marked=()
    )


def _run(step: SqlStep, **kwargs: object) -> StagedTable:
    return run_staging(
        [step], sources=_tables(), lists={}, dataset_id="pid", marked=(), **kwargs  # type: ignore[arg-type]
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
    assert sql_gate_problems(step, marked=()) and set(sql_gate_problems(step, marked=())) <= set(_gate(step))


@pytest.mark.parametrize(
    ("select", "words"),
    [
        # Each carries `_ref`, so nothing but the sandbox stands between it and the file or network
        # (rule 15: a planted read that failed for its missing `_ref` proved nothing of the sandbox).
        ("SELECT v.*, x.* FROM visits v, read_csv('/etc/hosts') x", "disabled by configuration"),
        ("SELECT v.*, x.* FROM visits v, 'http://example.invalid/rows.csv' x", "disabled by configuration"),
        ("SELECT v.*, x.* FROM visits v, read_parquet('https://example.invalid/x.parquet') x",
         "disabled by configuration"),
        ("SELECT v.*, x.* FROM visits v, read_text('/etc/hosts') x", "disabled by configuration"),
    ],
)
def test_the_sandbox_refuses_a_file_or_network_read_without_the_gate(select: str, words: str) -> None:
    """The gate taken away: the sandbox itself reads no file and no network, in DuckDB's words."""
    with pytest.raises(StagingError) as refused:
        run_sql_step(_step(select, ("visits",)), [_tables()["visits"]], check=False, marked=())
    assert any(words in p for p in refused.value.problems), refused.value.problems


def test_the_sandbox_refuses_a_second_statement_without_the_gate() -> None:
    with pytest.raises(StagingError) as refused:
        run_sql_step(
            _step("SELECT *, _ref FROM visits; SELECT 1", ("visits",)),
            [_tables()["visits"]],
            check=False, marked=()
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
        run_sql_step(_step(select, ("visits",)), [_tables()["visits"]], check=False, marked=())
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
        'SELECT *, _ref FROM "loads/other-load/staged/visits.parquet"',
        "SELECT *, _ref FROM visits_secret",
    ],
)
def test_a_query_over_a_table_it_does_not_read_is_refused(select: str) -> None:
    """Rule 3: a SQL step reads its declared inputs, this pipeline's own tables, and nothing else.
    The gate refuses another case's or dataset's staged table by name; without the gate the sandbox
    holds no such table (`_ref` carried, so nothing else refuses it: rule 15)."""
    assert any("is not one of the tables it reads" in p for p in _gate(_step(select, ("visits",))))
    with pytest.raises(StagingError) as refused:
        run_sql_step(_step(select, ("visits",)), [_tables()["visits"]], check=False, marked=())
    words = " ".join(refused.value.problems)
    assert "does not exist" in words or "disabled by configuration" in words, words


@pytest.mark.parametrize(
    "select",
    [
        "SELECT v.*, s.* FROM visits v, pg_catalog.pg_tables s",
        "SELECT v.*, s.* FROM visits v, duckdb_settings() s",
        "SELECT v.*, s.* FROM visits v, pg_settings s",
        "SELECT v.*, s.* FROM visits v, information_schema.tables s",
        # The lane review of L1.5, item 1: a CTE of the same name inside a subquery is not the
        # outer query's, so the outer name is DuckDB's catalogue, and refused.
        "SELECT v.*, s.name FROM visits v, (WITH pg_settings AS (SELECT 1 AS x) "
        "SELECT x FROM pg_settings) w, pg_settings s",
    ],
)
def test_the_gate_refuses_duckdb_s_own_catalogue(select: str) -> None:
    """DuckDB's catalogue is on its search path inside the sandbox too (it holds settings and the
    sandbox's own table names, no row of another case): the gate is what refuses it, by name and by
    scope, before anything runs, and every run of a step asks the gate (`check=False` is the tests'
    alone)."""
    problems = _gate(_step(select, ("visits",)))
    assert any(
        "is not one of the tables it reads" in p or "table function" in p for p in problems
    ), problems


@pytest.mark.parametrize(
    "select",
    [
        "WITH c(pin, _ref) AS (SELECT pin, min(_ref) FROM pin_calls GROUP BY pin) SELECT * FROM c",
        "SELECT * FROM (SELECT pin, min(_ref) FROM pin_calls GROUP BY pin) s(pin, _ref)",
    ],
)
def test_a_column_alias_list_cannot_name_a_column_ref(select: str) -> None:
    """The lane review, item 3: a list of column names renames by position, so it could call an
    aggregate's one value `_ref`, past the one-for-many rule."""
    problems = _gate(_step(select, ("pin_calls",)))
    assert any("through a list of column names" in p for p in problems), problems


@pytest.mark.parametrize(
    "select",
    ["SUMMARIZE visits", "DESCRIBE visits", "SHOW TABLES", "SELECT *, 1 AS _ref FROM (SUMMARIZE visits)"],
)
def test_show_describe_and_summarize_are_refused(select: str) -> None:
    problems = _gate(_step(select, ("visits",)))
    assert any("describes or summarises" in p for p in problems), problems


def test_a_ref_tells_nothing_of_a_withheld_row() -> None:
    """The lane review, item 5: tokens are numbered over the rows the reader may read, so one
    carried into a cell (`_ref AS r`) shows no gap where a withheld row was."""
    step = _step("SELECT booking_id, _ref AS r, _ref FROM visits ORDER BY booking_id", ("visits",))
    out = run_staging(
        [step], sources=_tables(), lists={}, dataset_id="pid", may_read=_hide(1), marked=()
    ).output  # fmt: skip
    tokens = [r.cells["r"] or "" for r in out.rows]
    assert len(set(tokens)) == 2 and not any("#" in t or "visits" in t for t in tokens)
    assert [ref.row_index for r in out.rows for ref in r.refs] == [0, 2]


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
            check=False, marked=()
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
        may_read=_hide(2), marked=()
    )  # fmt: skip
    names = {r.cells["visitor_name"] for r in result.output.rows}
    assert names == {"S. Whitlow", "J Pryce"}
    (report,) = result.reports
    assert (report.rows_in, report.rows_withheld, report.rows_out) == (2, 1, 2)
    # Not even a count over it: an aggregate over the table counts only what the reader may read.
    counted = run_staging(
        [_step("SELECT count(*) AS n, list(_ref) AS _ref FROM visits", ("visits",))],
        sources=_tables(), lists={}, dataset_id="pid", may_read=_hide(2), marked=()
    ).output  # fmt: skip
    assert counted.rows[0].cells["n"] == "2"


def test_a_query_past_its_time_limit_is_stopped() -> None:
    many = source_table("visits", [{"n": str(i)} for i in range(400)], load_id="L")
    select = "SELECT count(*) AS n FROM visits a, visits b, visits c, visits d, visits e"
    with pytest.raises(StagingError) as refused:
        run_sql_step(_step(select, ("visits",)), [many], time_limit=0.3, check=False, marked=())
    assert any("time limit" in p for p in refused.value.problems), refused.value.problems


def test_a_query_past_its_memory_limit_is_stopped() -> None:
    many = source_table("visits", [{"n": str(i)} for i in range(400)], load_id="L")
    select = "SELECT count(*) AS n, list(a._ref) AS _ref FROM visits a, visits b, visits c, visits d"
    with pytest.raises(StagingError) as refused:
        # Past the gate (it refuses a table read four times): the sandbox's own limit is the test.
        run_sql_step(
            _step(select, ("visits",)), [many], memory_limit="64MB", time_limit=20, check=False,
            marked=(),
        )  # fmt: skip
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
    assert "Whitlow" not in words and "could not convert" in words


# --- The orchestrator's review of L1.5 (ADR-140 Amendment 14) ---------------------------------
#
# 1. A marking bound to a column is never lowered: where the pipeline binds one, a SQL step runs
#    row by row and passes each marked column through as its own row has it.

MARKED_VISITS = [
    {"booking_id": "VB-1", "pin": "P1", "visitor_name": "S. Whitlow", "classification": "SECRET"},
    {"booking_id": "VB-2", "pin": "P1", "visitor_name": "J Pryce", "classification": ""},
    {"booking_id": "VB-3", "pin": "P2", "visitor_name": "A. Khan", "classification": "OFFICIAL"},
]
MARKED = frozenset({"classification"})


def _marked_tables() -> dict[str, StagedTable]:
    return {"visits": source_table("visits", MARKED_VISITS, load_id="L:visits")}


def _marked_gate(select: str) -> list[str]:
    return staging_rule_violations(
        [_step(select, ("visits",))], sources=["visits"], lists=[], dataset_id="pid",
        marked=MARKED,
    )  # fmt: skip


def _marked_run(select: str, *, check: bool = True) -> StagedTable:
    if check:
        return run_staging(
            [_step(select, ("visits",))], sources=_marked_tables(), lists={}, dataset_id="pid",
            marked=MARKED,
        ).output  # fmt: skip
    table, _report = run_sql_step(
        _step(select, ("visits",)), [_marked_tables()["visits"]], marked=MARKED, check=False
    )
    return table


@pytest.mark.parametrize(
    "select",
    [
        "SELECT * REPLACE (NULL AS classification) FROM visits",
        "SELECT * REPLACE ('OFFICIAL' AS classification) FROM visits",
        "SELECT booking_id, 'OFFICIAL' AS classification, _ref FROM visits",
        "SELECT booking_id, lower(classification) AS classification, _ref FROM visits",
        "SELECT * EXCLUDE (classification) FROM visits",
        "SELECT * RENAME (classification AS grade) FROM visits",
        "SELECT booking_id, classification AS grade, _ref FROM visits",
        # A window copy: every row given every visitor's name, at its own marking.
        "SELECT *, string_agg(visitor_name, ';') OVER () AS everyone FROM visits",
        # A self-join: a lower-marked row given a higher-marked row's values.
        "SELECT v.*, w.visitor_name AS other FROM visits v JOIN visits w ON w.pin = v.pin",
        "SELECT pin, max(classification) AS classification, list(_ref) AS _ref FROM visits "
        "GROUP BY pin",
        "SELECT pin, string_agg(visitor_name, ';') AS names, list(_ref) AS _ref FROM visits "
        "GROUP BY pin",
        "SELECT * FROM visits EXCEPT SELECT * FROM visits WHERE pin = 'P2'",
    ],
)
def test_the_gate_refuses_a_step_that_could_lower_a_marking(select: str) -> None:
    """Map judges each row's marking from the cells of its marked columns, so a step that rewrote
    one, or gave one row others' values, would hold them at a lower marking (the review's blocker).
    Red with the row-by-row rules taken out of the gate."""
    problems = _marked_gate(select)
    assert any("marking" in p or "window" in p or "times" in p for p in problems), problems
    assert not any(v in " ".join(problems) for v in ("Whitlow", "SECRET"))


@pytest.mark.parametrize(
    "select",
    [
        "SELECT * REPLACE (NULL AS classification) FROM visits",
        "SELECT * REPLACE ('OFFICIAL' AS classification) FROM visits",
        "SELECT booking_id, 'OFFICIAL' AS classification, _ref FROM visits",
        "SELECT * EXCLUDE (classification) FROM visits",
        "SELECT v.*, w._ref AS _ref_w FROM visits v JOIN visits w ON w.pin = v.pin",
    ],
)
def test_the_run_refuses_a_marked_cell_not_its_own_row_s(select: str) -> None:
    """The run's own check, past the gate: each row from one input row, each marked cell as that
    row has it. Red with the run's check taken out."""
    with pytest.raises(StagingError) as refused:
        _marked_run(select, check=False)
    words = " ".join(refused.value.problems)
    assert "marking" in words, words
    assert "SECRET" not in words and "Whitlow" not in words


def test_a_row_by_row_step_over_marked_columns_runs() -> None:
    out = _marked_run(
        "SELECT booking_id, upper(visitor_name) AS shout, classification, _ref FROM visits "
        "WHERE pin = 'P1' ORDER BY booking_id"
    )
    assert [(r.cells["booking_id"], r.cells["classification"]) for r in out.rows] == [
        ("VB-1", "SECRET"), ("VB-2", None),
    ]  # fmt: skip
    assert _marked_run("SELECT * FROM visits ORDER BY booking_id").rows[0].cells[
        "classification"
    ] == "SECRET"


def test_without_a_marked_column_a_step_may_still_join_and_fold() -> None:
    """The rule is the marked pipeline's: one whose rows all share the source's marking may join
    and aggregate (the phase 8 exit's own SELECT does), and every row still names every row."""
    assert _gate(_step(COUNTS)) == []


# 2. `_ref` cannot be forged: a token is a row's own.


REWRITES = "rewrites or renames _ref through"
WINDOW = "window function"
TWICE = "times, which a SQL step may not"
SUBQUERY = "subquery inside an expression"
IN_EXPRESSION = "reads _ref inside an expression"
DROPS = "drops the _ref column"
#: The second pass's two shapes: a string function over a row's own token, carried out through a
#: struct's `.*` or a UNION's column, building another row's (the old `table#n` tokens).
STRUCT_FORGERY = (
    "SELECT q.booking_id, s.* FROM (SELECT booking_id, struct_pack(_ref := "
    "regexp_replace(_ref, '#[0-9]+$', '#0')) AS s FROM visits) q"
)
UNION_FORGERY = (
    "SELECT _ref, booking_id AS info FROM visits UNION ALL "
    "SELECT regexp_replace(_ref, '#[0-9]+$', '#0'), _ref FROM pin_calls"
)


@pytest.mark.parametrize(
    ("select", "words"),
    [
        ("SELECT * REPLACE ('visits#0' AS _ref) FROM visits", REWRITES),
        ("SELECT * REPLACE (first(_ref) OVER () AS _ref) FROM visits", REWRITES),
        ("SELECT booking_id, first(_ref) OVER (ORDER BY booking_id) AS _ref FROM visits", WINDOW),
        ("SELECT * RENAME (_ref AS r), 1 AS n FROM visits", REWRITES),
        ("SELECT * RENAME (booking_id AS _ref_b) FROM visits", REWRITES),
        ("SELECT v.booking_id, w._ref FROM visits v JOIN visits w ON w.pin = v.pin", TWICE),
        ("WITH c AS (SELECT * FROM visits) SELECT a.booking_id, b._ref FROM c a, c b", TWICE),
        ("SELECT booking_id, (SELECT min(_ref) FROM pin_calls) AS _ref_c, _ref FROM visits",
         SUBQUERY),
        ("SELECT booking_id, _ref FROM visits WHERE pin IN (SELECT pin FROM pin_calls)", SUBQUERY),
        ("SELECT booking_id, _ref FROM visits WHERE EXISTS (SELECT 1 FROM pin_calls)", SUBQUERY),
        ("SELECT booking_id, _ref FROM visits QUALIFY row_number() OVER () = 1", WINDOW),
        ("SELECT COLUMNS('.*') FROM visits", "COLUMNS("),
        ("SELECT * EXCLUDE (visits._ref), 1 AS n FROM visits", DROPS),
        ("SELECT * EXCLUDE (VISITS._REF) FROM visits", DROPS),
        ("SELECT booking_id, _ref FROM visits ORDER BY _ref", IN_EXPRESSION),
        ("SELECT booking_id, upper(_ref) AS r, _ref FROM visits", IN_EXPRESSION),
        (STRUCT_FORGERY, IN_EXPRESSION),
        (UNION_FORGERY, IN_EXPRESSION),
    ],
)  # fmt: skip
def test_the_gate_refuses_a_forged_or_borrowed_ref(select: str, words: str) -> None:
    """The review's item 2 and its second pass: a `_ref` rewritten, renamed, copied from another
    row (a window, a self-join, a CTE read twice, a subquery), read inside an expression (a string
    function over it, a struct carrying it) or dropped through a qualified EXCLUDE; each refused
    for its own reason. Red with each rule taken out of the gate."""
    problems = _gate(_step(select, ("visits", "pin_calls")))
    assert any(words in p for p in problems), problems


@pytest.mark.parametrize("select", [STRUCT_FORGERY, UNION_FORGERY])
def test_a_ref_built_from_another_row_s_is_refused_at_run_staging(select: str) -> None:
    """The second pass's shapes at the real call site, `run_staging`: both credited every row to
    row 0, so `filtered_out` was wrong (rule 2). The gate refuses them (red with its `_ref`-in-an-
    expression rule out)."""
    with pytest.raises(StagingError) as refused:
        _run(_step(select))
    assert any(IN_EXPRESSION in p for p in refused.value.problems), refused.value.problems


@pytest.mark.parametrize(
    ("select", "inputs"),
    [(STRUCT_FORGERY, ("visits",)), (UNION_FORGERY, ("visits", "pin_calls"))],
)
def test_past_the_gate_a_string_function_cannot_build_another_row_s_ref(
    select: str, inputs: tuple[str, ...]
) -> None:
    """And past the gate, the run's own guard: each row's token is drawn at random, so a string
    function over it gives back the row's own token, never another's; every row is credited to
    itself and none is miscounted as filtered out (rule 2). Red with `table#n` tokens again: every
    row credited to row 0, the others counted as filtered out."""
    tables = [_tables()[name] for name in inputs]
    out, report = run_sql_step(_step(select, inputs), tables, marked=(), check=False)
    credited = [(ref.source, ref.row_index) for row in out.rows for ref in row.refs]
    assert len(credited) == len(set(credited)) == sum(len(t.rows) for t in tables), credited
    assert report.filtered_out == 0


def test_a_token_written_by_hand_names_no_row() -> None:
    """Each row's token is drawn at random for each run: one read from an earlier run, or
    guessed, names no row of this one. Red with predictable tokens (`visits#0` again)."""
    shown = _run(_step("SELECT booking_id, _ref AS r, _ref FROM visits", ("visits",)))
    earlier = shown.rows[0].cells["r"]
    assert earlier and "visits" not in earlier and "#" not in earlier
    for forged in (earlier, "visits#0"):
        with pytest.raises(StagingError) as refused:
            run_sql_step(
                _step(f"SELECT booking_id, '{forged}' AS _ref FROM visits", ("visits",)),
                [_tables()["visits"]], marked=(), check=False,
            )  # fmt: skip
        assert any("names no input row" in p for p in refused.value.problems)


@pytest.mark.parametrize("name", ["_REF", "_ref_calls", "_Ref_x"])
def test_an_input_column_named_like_a_ref_is_refused(name: str) -> None:
    """Every output column named `_ref…`, in any case, is read back as refs: an input column of
    such a name would be read as one."""
    table = source_table("visits", [{"booking_id": "VB-1", name: "x"}], load_id="L")
    with pytest.raises(StagingError) as refused:
        run_sql_step(_step("SELECT * FROM visits", ("visits",)), [table], marked=())
    # The refusal names the column's clash itself (rule 15: a looser check passed on a later
    # refusal, the clash's value read back as a ref that names no row).
    assert any("has a column named _ref or _ref_" in p for p in refused.value.problems)


def test_a_forward_reference_to_a_later_cte_is_not_a_cte() -> None:
    """A CTE sees only the CTEs declared before it, so `pg_settings` named in the first is
    DuckDB's catalogue (or nothing), never the second: refused."""
    select = (
        "WITH a AS (SELECT * FROM pg_settings), pg_settings AS (SELECT * FROM visits) "
        "SELECT v.*, a.name FROM visits v, a"
    )
    assert any("is not one of the tables it reads" in p for p in _gate(_step(select, ("visits",))))


def test_filtered_out_counts_the_rows_no_row_names() -> None:
    _table, report = run_sql_step(
        _step("SELECT booking_id, _ref FROM visits WHERE pin = 'P1'", ("visits",)),
        [_tables()["visits"]], marked=(),
    )  # fmt: skip
    assert (report.rows_in, report.rows_out, report.filtered_out) == (3, 1, 2)


# 3. A refusal never repeats a value, quoted or not.


@pytest.mark.parametrize(
    ("select", "value"),
    [
        ("SELECT error(visitor_name) AS e, _ref FROM visits", "Whitlow"),
        ("SELECT CAST(n AS TINYINT) AS t, _ref FROM visits", "98765"),
        ("SELECT CAST(visitor_name AS DATE) AS d, _ref FROM visits", "Whitlow"),
    ],
)
def test_a_refusal_never_repeats_a_value_unquoted(select: str, value: str) -> None:
    """DuckDB's own message prints a value it could not convert (unquoted, for `error()` and a
    cast out of range): the words are ours, the kind and the line alone. Red with DuckDB's message
    passed on."""
    rows = [{"visitor_name": "S. Whitlow", "n": "98765"}]
    table = source_table("visits", rows, load_id="L")
    with pytest.raises(StagingError) as refused:
        run_sql_step(_step(select, ("visits",)), [table], marked=(), check=False)
    words = " ".join(refused.value.problems)
    assert value not in words, words
    assert words.endswith(("(line 1)", "a value it could not take")), words
    # And the gate refuses error() by name, before anything runs.
    if "error(" in select:
        assert any("calls error" in p for p in _gate(_step(select, ("visits",))))


def test_a_select_that_cannot_be_read_never_repeats_its_text() -> None:
    problems = _gate(_step("SELECT 'S. Whitlow' FROM WHERE", ("visits",)))
    assert problems and not any("Whitlow" in p for p in problems), problems


# 5. The output is bounded, refused past the bound, never cut short (rule 2).


def test_a_step_giving_more_rows_than_its_limit_is_refused_not_cut() -> None:
    """Red with the limit taken out: all 5,000 rows come back."""
    with pytest.raises(StagingError) as refused:
        run_sql_step(
            _step("SELECT unnest(range(5000)) AS n, _ref FROM visits", ("visits",)),
            [_tables()["visits"]], marked=(), row_limit=1000,
        )  # fmt: skip
    assert any("never cut short" in p for p in refused.value.problems)


def test_a_step_giving_more_bytes_than_its_limit_is_refused_not_cut() -> None:
    with pytest.raises(StagingError) as refused:
        run_sql_step(
            _step("SELECT repeat(visitor_name, 10000) AS long, _ref FROM visits", ("visits",)),
            [_tables()["visits"]], marked=(), byte_limit=20_000,
        )  # fmt: skip
    assert any("never cut short" in p for p in refused.value.problems)


def test_a_hundred_million_rows_are_refused_at_the_limit_in_words() -> None:
    """The review's own shape, at the real limits: refused promptly, before the rows become
    Python values."""
    with pytest.raises(StagingError) as refused:
        run_sql_step(
            _step("SELECT unnest(range(100000000)) AS n, _ref FROM visits", ("visits",)),
            [_tables()["visits"]], marked=(),
        )  # fmt: skip
    words = " ".join(refused.value.problems)
    assert "never cut short" in words or "memory limit" in words, words


# 6. Another dataset's staged Parquet, by its object-store or file path (rule 3).


def test_another_dataset_s_staged_parquet_is_never_read(tmp_path: Path) -> None:
    """The real shapes: another dataset's staged table by its object-store path and by a local
    path that exists and holds a row. The gate refuses both by name; past the gate the sandbox
    reads no file (red with external access turned on: the other dataset's row comes back)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    other = tmp_path / "loads" / "other-load" / "staged" / "visits.parquet"
    other.parent.mkdir(parents=True)
    pq.write_table(pa.table({"booking_id": ["OTHER-DATASET-ROW"], "_ref": ["x"]}), other)
    for path in (str(other), "s3://staging/loads/other-load/staged/visits.parquet"):
        for select in (
            f"SELECT v.*, o.booking_id AS theirs FROM visits v, '{path}' o",
            f"SELECT v.*, o.booking_id AS theirs FROM visits v, read_parquet('{path}') o",
        ):
            problems = _gate(_step(select, ("visits",)))
            assert any(
                "is not one of the tables it reads" in p or "table function" in p for p in problems
            ), problems
            with pytest.raises(StagingError) as refused:
                run_sql_step(_step(select, ("visits",)), [_tables()["visits"]], marked=(),
                             check=False)  # fmt: skip
            words = " ".join(refused.value.problems)
            assert "disabled by configuration" in words, words
            assert "OTHER-DATASET-ROW" not in words


# 4. Test runs the steps off the event loop, as Preview and the run do.


async def test_test_runs_a_slow_sql_step_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A SQL step that takes a second must not stop every other request for that second. The
    SELECT made slow at DuckDB's call; the event loop keeps ticking while Test runs it. Red with
    `dry_run_staged_recipe` staging on the loop (no `asyncio.to_thread`): no tick in the second."""
    import asyncio
    import time

    from services.ingest import sql_transform
    from services.ingest.staged_run import dry_run_staged_recipe

    from tests.ingest.test_fuzzy_match import LOADER, ONTOLOGY, SCHEME, _recipe
    from tests.ingest.test_fuzzy_match import _sources as fuzzy_sources
    from tests.ingest.recipe_test_support import ValidatingGraph

    real = sql_transform._execute

    def slow(*args: object, **kwargs: object) -> object:
        time.sleep(1.0)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sql_transform, "_execute", slow)
    recipe = _recipe(0.6)
    sql = SqlStep(
        id="calls", kind="sql", inputs=["visits"], select="SELECT *, _ref FROM visits",
        summary="Passes the visits through.",
    )  # fmt: skip
    recipe = recipe.model_copy(update={"staging": [sql]})
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        await dry_run_staged_recipe(
            recipe, sources=fuzzy_sources(), lists={}, dataset_id="pid",
            graph=ValidatingGraph(ONTOLOGY), ontology=ONTOLOGY, principal=LOADER,  # type: ignore[arg-type]
            scheme=SCHEME,
        )  # fmt: skip
    finally:
        task.cancel()
    assert ticks >= 10, ticks


async def test_test_and_the_run_read_the_recipe_s_marked_columns() -> None:
    """The real call site of Test and the load (`staged_run._stage`): the recipe's own marked
    columns reach the gate, so a folding SELECT over a pipeline binding a marking is refused there
    too. Red with `_stage` passing none."""
    from services.ingest.staged_run import dry_run_staged_recipe

    from tests.ingest.recipe_test_support import ValidatingGraph
    from tests.ingest.test_fuzzy_match import LOADER, ONTOLOGY, SCHEME, _recipe
    from tests.ingest.test_fuzzy_match import _sources as fuzzy_sources

    recipe = _recipe(0.6)
    folding = SqlStep(
        id="calls", kind="sql", inputs=["visits"],
        select="SELECT family, count(*) AS n, list(_ref) AS _ref FROM visits GROUP BY family",
        summary="Counts each family's visits.",
    )  # fmt: skip
    defaults = recipe.defaults.model_copy(update={"handling_columns": {"classification": "grade"}})
    recipe = recipe.model_copy(update={"staging": [folding], "defaults": defaults})
    with pytest.raises(StagingError) as refused:
        await dry_run_staged_recipe(
            recipe, sources=fuzzy_sources(), lists={}, dataset_id="pid",
            graph=ValidatingGraph(ONTOLOGY), ontology=ONTOLOGY, principal=LOADER,  # type: ignore[arg-type]
            scheme=SCHEME,
        )  # fmt: skip
    assert any("binds a marking to a column" in p for p in refused.value.problems)
