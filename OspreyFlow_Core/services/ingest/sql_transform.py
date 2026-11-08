"""The SQL transform, expert mode's one SELECT (ADR-140 decision 12; R4, R15; the redesign's phase
8; brief §5.3). `schemas.staging.SqlStep` is its record.

**The sandbox** is a private, in-memory DuckDB connection per run of the step (`sandbox_connection`):

- **read-only, no file or network function.** `enable_external_access` is off, so DuckDB opens no
  file, URL or extension (`read_csv`, `read_parquet('https://…')`, `httpfs`, `COPY`, `ATTACH`,
  `INSTALL` are each refused by DuckDB itself); extensions neither autoload nor autoinstall; the
  Python client's scan of a variable named in `FROM` is off; nothing spills to disk.
- **no table but its inputs.** The connection holds only the step's input tables, each under its
  own name, so another case's or dataset's staged table is simply not there; and the gate refuses,
  before DuckDB runs anything, a table function of any kind (`read_csv`, `query`, `range`,
  `duckdb_settings`…), a qualified name and any table the step does not read.
- **a time and a memory limit.** `memory_limit` is the connection's; the time limit interrupts the
  query (`con.interrupt`). The configuration is locked, so the SELECT cannot change either.
- **the person's own principal** (`readable`): a row the person running it may not read is not put
  in the table at all, so it is absent, never masked, and nothing over the table counts it; the
  step's report counts how many were withheld (rule 2), a count withheld with every other.

**The gate** (`sql_gate_problems`; the save gate, Test, a drawer's sample and Deploy all ask it):
exactly one statement, and that a SELECT; the tables above; and a `_ref` column carried through.
**`_ref`** (R15, brief §5.2): each input row carries a `_ref` token; every output column named `_ref`
or starting `_ref_` is read back as the refs of the input rows it names (a token, or a list of them
from `list(_ref)`), so each output row names every input row it came from and the element Map
writes from it lists them all. At the run, the output must hold such a column, an aggregating
SELECT must carry each as a list, and each input table with rows must reach the output through one.

Nothing here evaluates text in Python, and a refusal names its cause, never a cell's value.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Iterator, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import duckdb
import pyarrow as pa

from schemas.staging import SqlStep

from .staging_catalogue import (
    StagedRef,
    StagedTable,
    StagedTableRow,
    StagingError,
    StepReport,
)

#: The sandbox's limits (ADR-140 decision 12). Seconds of wall time per step, and DuckDB's own
#: memory limit; both deliberately modest for a staging step over a pipeline's tables.
SQL_TIME_LIMIT_S = 30.0
SQL_MEMORY_LIMIT = "512MB"

REF_COLUMN = "_ref"

_SANDBOX: dict[str, Any] = {
    "enable_external_access": False,
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "allow_unsigned_extensions": False,
    "python_enable_replacements": False,
    "temp_directory": "",
    "threads": 1,
}


def sandbox_connection(*, memory_limit: str = SQL_MEMORY_LIMIT) -> duckdb.DuckDBPyConnection:
    """A private in-memory DuckDB connection with the sandbox's settings, locked."""
    return duckdb.connect(
        ":memory:",
        config={**_SANDBOX, "memory_limit": memory_limit, "lock_configuration": True},
    )


# --- The gate ---------------------------------------------------------------------------------


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _ctes(tree: Any) -> set[str]:
    names: set[str] = set()
    for node in _walk(tree):
        cte_map = node.get("cte_map")
        if isinstance(cte_map, dict):
            names.update(str(entry.get("key", "")).casefold() for entry in cte_map.get("map", []))
    return names


def _is_ref_name(name: str) -> bool:
    folded = name.casefold()
    return folded == REF_COLUMN or folded.startswith(REF_COLUMN + "_")


def _carries_a_ref(select_node: dict[str, Any]) -> bool:
    """Whether a SELECT's own list can give a `_ref` column: an item aliased `_ref…`, a column
    `_ref…` unaliased, or a `*` that does not exclude `_ref`. A set operation (UNION) judges each
    side; anything the AST does not let us judge here is left to the run's check."""
    if select_node.get("type") == "SET_OPERATION_NODE":
        return all(
            _carries_a_ref(select_node.get(side) or {}) for side in ("left", "right")
        )
    if select_node.get("type") != "SELECT_NODE":
        return True
    for item in select_node.get("select_list", []):
        alias = str(item.get("alias") or "")
        if alias:
            if _is_ref_name(alias):
                return True
            continue
        if item.get("class") == "COLUMN_REF" and _is_ref_name(str(item["column_names"][-1])):
            return True
        if item.get("class") == "STAR" and not any(
            _is_ref_name(str(e)) for e in item.get("exclude_list", [])
        ):
            return True
    return False


#: The aggregates that carry every row they fold as a list (R15): `list(_ref)`, `array_agg(_ref)`.
_LIST_AGGREGATES = frozenset({"list", "array_agg"})


def _names(expression: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(n).casefold() for n in expression.get("column_names", []))


def _one_for_many(select_node: dict[str, Any]) -> list[str]:
    """Each `_ref…` item of a SELECT that does not carry every row it stands for: a `_ref…` item
    is a `_ref…` column (in a grouped SELECT, one it groups on), or `list(_ref…)`; anything else
    (`any_value(_ref)`, `min(_ref)`, a constant, an expression) names one row, or none, for many."""
    grouped = {
        _names(g) for g in select_node.get("group_expressions", []) if g.get("class") == "COLUMN_REF"
    }
    has_groups = bool(select_node.get("group_expressions"))
    found: list[str] = []
    for item in select_node.get("select_list", []):
        if item.get("class") == "STAR":
            continue
        alias = str(item.get("alias") or "")
        name = alias or (
            str(item["column_names"][-1]) if item.get("class") == "COLUMN_REF" else ""
        )
        if not _is_ref_name(name):
            continue
        if item.get("class") == "COLUMN_REF" and _is_ref_name(str(item["column_names"][-1])):
            if not has_groups or _names(item) in grouped:
                continue
        elif (
            item.get("class") == "FUNCTION"
            and str(item.get("function_name", "")).casefold() in _LIST_AGGREGATES
            and len(item.get("children", [])) == 1
            and item["children"][0].get("class") == "COLUMN_REF"
            and _is_ref_name(str(item["children"][0]["column_names"][-1]))
        ):
            continue
        found.append(name)
    return found


#: Scalar functions a SQL step may not call: each reads the deployment, never a row.
_DENIED_FUNCTIONS = frozenset({"current_setting", "getenv", "read_blob", "read_text"})


def _first_line(message: str) -> str:
    """DuckDB's error, first line, with any quoted text taken out: it can quote a cell's value."""
    line = message.strip().splitlines()[0] if message.strip() else "an error"
    return re.sub(r"'[^']*'", "'…'", re.sub(r'"[^"]*"', '"…"', line))


def sql_gate_problems(step: SqlStep) -> list[str]:
    """What the save gate refuses in a SQL step, in words, without running it over any row."""
    sql = step.select
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as exc:
        return [f"step {step.id!r}'s SELECT cannot be read as SQL: {_first_line(str(exc))}"]
    if len(statements) != 1:
        return [
            f"step {step.id!r} is one SELECT statement, not {len(statements)}: a SQL step runs "
            "a single SELECT and nothing else"
        ]
    if statements[0].type != duckdb.StatementType.SELECT:
        return [
            f"step {step.id!r}'s statement is not a SELECT: a SQL step reads its tables and "
            "changes nothing"
        ]
    con = sandbox_connection(memory_limit="64MB")
    try:
        found = con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()
    finally:
        con.close()
    tree = json.loads(found[0]) if found else {"error": True}
    if tree.get("error"):
        return [f"step {step.id!r}'s SELECT cannot be read as SQL"]
    problems: list[str] = []
    inputs = {name.casefold() for name in step.inputs}
    ctes = _ctes(tree)
    for node in _walk(tree):
        kind = node.get("type")
        if kind == "TABLE_FUNCTION":
            name = (node.get("function") or {}).get("function_name", "?")
            problems.append(
                f"step {step.id!r} reads through a table function ({name}), which a SQL step may "
                "not: it reads only the tables named in its inputs"
            )
        elif kind == "BASE_TABLE":
            table = str(node.get("table_name", ""))
            qualified = node.get("schema_name") or node.get("catalog_name")
            if qualified or table.casefold() not in inputs | ctes:
                shown = table if len(table) <= 64 else table[:61] + "…"
                problems.append(
                    f"step {step.id!r} reads {shown!r}, which is not one of the tables it reads "
                    f"({', '.join(step.inputs)})"
                )
        elif node.get("class") == "FUNCTION":
            name = str(node.get("function_name", "")).casefold()
            if name in _DENIED_FUNCTIONS:
                problems.append(f"step {step.id!r} calls {name}, which a SQL step may not")
        if kind == "SELECT_NODE":
            for name in _one_for_many(node):
                problems.append(
                    f"step {step.id!r} carries {name!r} as one row's ref, or none, for the rows it "
                    "stands for: carry a _ref column as it is (in a GROUP BY, one it groups on), "
                    "or an aggregate's as list(_ref)"
                )
    top = tree["statements"][0]["node"]
    if not _carries_a_ref(top):
        problems.append(
            f"step {step.id!r}'s SELECT drops the _ref column: carry each input row's _ref "
            "through (an aggregate as list(_ref)), so every row it gives names the rows it came "
            "from"
        )
    return list(dict.fromkeys(problems))


# --- The run ----------------------------------------------------------------------------------


def _token(table: str, index: int) -> str:
    return f"{table}#{index}"


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (int, Decimal, str)):
        text = str(value)
        return text if text.strip() else None
    raise TypeError(type(value).__name__)


def run_sql_step(
    step: SqlStep,
    tables: Sequence[StagedTable],
    *,
    readable: Callable[[StagedRef], bool] | None = None,
    time_limit: float = SQL_TIME_LIMIT_S,
    memory_limit: str = SQL_MEMORY_LIMIT,
    check: bool = True,
) -> tuple[StagedTable, StepReport]:
    """Run the step's SELECT over `tables` (its inputs, in its order) in the sandbox. `readable`:
    whether the person running it may read a row, judged by each row's refs; a row they may not is
    left out of its table. `check=False` skips the gate, for the tests that prove the sandbox holds
    without it. Raises `StagingError`, in words, for anything refused."""
    if check:
        problems = sql_gate_problems(step)
        if problems:
            raise StagingError(problems)
    else:
        statements = []
        try:
            statements = duckdb.extract_statements(step.select)
        except duckdb.Error as exc:
            raise StagingError([f"step {step.id!r}'s SELECT cannot be read as SQL"]) from exc
        if len(statements) != 1:
            raise StagingError(
                [f"step {step.id!r} is one SELECT statement, not {len(statements)}"]
            )
    by_token: dict[str, tuple[StagedRef, ...]] = {}
    rows_in = withheld = 0
    con = sandbox_connection(memory_limit=memory_limit)
    try:
        for table in tables:
            if REF_COLUMN in table.columns:
                raise StagingError(
                    [f"the table {table.name!r} has a column named _ref, which a SQL step keeps"]
                )
            kept: list[tuple[int, StagedTableRow]] = []
            for index, row in enumerate(table.rows):
                if readable is not None and not all(readable(ref) for ref in row.refs):
                    withheld += 1
                    continue
                kept.append((index, row))
            rows_in += len(kept)
            data: dict[str, list[str | None]] = {
                c: [row.cells.get(c) for _, row in kept] for c in table.columns
            }
            data[REF_COLUMN] = [_token(table.name, index) for index, _ in kept]
            for index, row in kept:
                by_token[_token(table.name, index)] = row.refs
            schema = pa.schema([pa.field(name, pa.string()) for name in data])
            con.register(table.name, pa.table(data, schema=schema))
        result = _execute(con, step, time_limit)
    finally:
        con.close()
    names = [field.name for field in result.schema]
    refs_at = [i for i, name in enumerate(names) if _is_ref_name(name)]
    if not refs_at:
        raise StagingError(
            [f"step {step.id!r}'s SELECT gives no _ref column: carry each input row's _ref through"]
        )
    columns = [name for i, name in enumerate(names) if i not in refs_at]
    if len(set(c.casefold() for c in columns)) != len(columns):
        raise StagingError([f"step {step.id!r}'s SELECT gives two columns of the same name"])
    out: list[StagedTableRow] = []
    reached: set[str] = set()
    used: set[str] = set()
    for record in result.to_pylist():
        tokens: list[str] = []
        for i in refs_at:
            value = record[names[i]]
            for token in value if isinstance(value, list) else [value]:
                if token is None:
                    continue
                if token not in by_token:
                    raise StagingError(
                        [f"step {step.id!r} gives a _ref that names no input row: carry each "
                         "row's _ref through unchanged"]  # fmt: skip
                    )
                tokens.append(token)
        if not tokens:
            raise StagingError(
                [f"step {step.id!r} gives a row that carries no input row's _ref: every row it "
                 "gives must name the rows it came from"]  # fmt: skip
            )
        refs: list[StagedRef] = []
        for token in dict.fromkeys(tokens):
            used.add(token)
            reached.add(token.rsplit("#", 1)[0])
            refs.extend(r for r in by_token[token] if r not in refs)
        try:
            cells = {c: _text(record[c]) for c in columns}
        except TypeError as exc:
            raise StagingError(
                [f"step {step.id!r} gives a column holding a {exc}, which a staged table cannot "
                 "hold: give it as text (string_agg, CAST … AS VARCHAR)"]  # fmt: skip
            ) from exc
        out.append(StagedTableRow(cells, tuple(refs)))
    if out:
        dropped = [t.name for t in tables if t.rows and t.name not in reached]
        if dropped:
            raise StagingError(
                [f"step {step.id!r}'s SELECT drops the _ref of {name!r}: carry it through as a "
                 "_ref_… column, so each row names the rows of it it came from" for name in dropped]
            )  # fmt: skip
    # Rule 2: an input row no output row names (a WHERE, an inner join) is counted, never lost
    # without a word.
    report = StepReport(
        step.id, "sql", rows_in=rows_in, rows_out=len(out), rows_withheld=withheld,
        filtered_out=rows_in - len(used),
    )  # fmt: skip
    return StagedTable(step.id, columns, out), report


def _execute(con: duckdb.DuckDBPyConnection, step: SqlStep, time_limit: float) -> Any:
    timer = threading.Timer(time_limit, con.interrupt)
    timer.start()
    try:
        return con.execute(step.select).to_arrow_table()
    except duckdb.InterruptException as exc:
        raise StagingError(
            [f"step {step.id!r} ran past its time limit of {time_limit:g} seconds and was stopped"]
        ) from exc
    except duckdb.OutOfMemoryException as exc:
        raise StagingError([f"step {step.id!r} ran past its memory limit and was stopped"]) from exc
    except duckdb.Error as exc:
        raise StagingError(
            [f"step {step.id!r}'s SELECT was refused: {_first_line(str(exc))}"]
        ) from exc
    finally:
        timer.cancel()
