"""The SQL transform, expert mode's one SELECT (ADR-140 decision 12; R4, R15; the redesign's phase
8; brief §5.3). `schemas.staging.SqlStep` is its record.

**The sandbox** is a private, in-memory DuckDB connection per run of the step
(`sandbox_connection`):

- **read-only, no file or network function.** `enable_external_access` is off, so DuckDB opens no
  file, URL or extension (`read_csv`, `read_parquet('https://…')`, `httpfs`, `COPY`, `ATTACH`,
  `INSTALL` are each refused by DuckDB itself); extensions neither autoload nor autoinstall; the
  Python client's scan of a variable named in `FROM` is off; nothing spills to disk.
- **no table but its inputs.** The connection holds only the step's input tables, each under its
  own name, so another case's or dataset's staged table is simply not there. DuckDB's own catalogue
  (`pg_catalog`, `information_schema`, `duckdb_settings()`) is on every connection's search path,
  holding settings and the sandbox's own table names and no row of another case; the gate refuses
  it, as it refuses, before DuckDB runs anything, a table function of any kind (`read_csv`, `query`,
  `range`…), `SHOW`, `DESCRIBE` and `SUMMARIZE`, a qualified name, and any table that is neither an
  input nor a CTE visible where it is named (CTE names are judged by scope).
- **a time and a memory limit.** `memory_limit` is the connection's; the time limit interrupts the
  query (`con.interrupt`). The configuration is locked, so the SELECT cannot change either.
- **the person's own principal** (`readable`): a row the person running it may not read is not put
  in the table at all, so it is absent, never masked, and nothing over the table counts it; the
  step's report counts how many were withheld (rule 2), a count withheld with every other.

**The gate** (`sql_gate_problems`; the save gate, Test, a drawer's sample, Deploy and every run ask
it): exactly one statement, and that a SELECT; the tables above; a `_ref` column carried through,
and never named through a list of column names (`c(pin, _ref)` renames by position).
**`_ref`** (R15, brief §5.2): each input row carries a `_ref` token; every output column named
`_ref` or starting `_ref_` is read back as the refs of the input rows it names (a token, or a list
of them from `list(_ref)`), so each output row names every input row it came from and the element
Map writes from it lists them all. A `_ref` item is a `_ref` column (in a grouped SELECT, one it
groups on) or `list(_ref)`. At the run, the output must hold such a column, and each input table
with rows must reach the output through one. Tokens are numbered over the rows the reader may read,
so none tells where a withheld row was.

**Never another row's values, never a lower marking** (the orchestrator's review of L1.5): a
window function, a subquery inside an expression (scalar, `IN`, `EXISTS`), `COLUMNS(…)`, a
recursive CTE and any table read twice in one SELECT are refused always, so no row is given another
row's values or its `_ref`; `* REPLACE`, `* RENAME` and a qualified `EXCLUDE` may not touch
`_ref`; and tokens carry a nonce drawn for each run, so none can be written by hand. Where the
pipeline binds a marking to a column (`marked`, the columns `defaults.handling_columns` and Map's
handling bindings name), Map
judges each row's marking from those cells, so the step runs **row by row**: no join, aggregate,
`GROUP BY`, `INTERSECT` or `EXCEPT`, and each marked column passed through as it is from its own
row, never rewritten, renamed, computed or dropped; the gate refuses what it can see and the run
compares every marked cell with its input row's.

**Bounded output**: at most `SQL_ROW_LIMIT` rows and `SQL_BYTE_LIMIT` bytes, counted batch by batch
as DuckDB gives them, within the time limit; past either the step is refused in words, never cut
short (rule 2).

Nothing here evaluates text in Python, and a refusal names its cause, never a cell's value: DuckDB's
own message is never repeated (it can quote, or print unquoted, a value it could not convert), only
the kind of refusal and the line of the SELECT.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from collections.abc import Callable, Collection, Iterator, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from functools import cache
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
#: The most a step may give (the orchestrator's review of L1.5, item 5): refused past either, in
#: words, never truncated (rule 2).
SQL_ROW_LIMIT = 1_000_000
SQL_BYTE_LIMIT = 256 * 1024 * 1024
_BATCH_ROWS = 8192

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


def _scoped(
    node: Any, scope: frozenset[str] = frozenset()
) -> Iterator[tuple[dict[str, Any], frozenset[str]]]:
    """Every node with the CTE names visible at it: a `WITH`'s names are visible within the query
    that declares them (its body and its CTEs, a recursive one included), never outside it, so a
    CTE named like a catalogue table inside a subquery does not let the outer query read the table
    (the lane review of L1.5, item 1)."""
    if isinstance(node, dict):
        cte_map = node.get("cte_map")
        entries = cte_map.get("map") if isinstance(cte_map, dict) else None
        if entries:
            # A CTE sees only the CTEs declared before it, never itself or a later one (a
            # forward or recursive reference names DuckDB's catalogue or nothing); the query's
            # body sees them all.
            earlier = scope
            for entry in entries:
                yield from _scoped(entry.get("value"), earlier)
                earlier = earlier | {str(entry.get("key", "")).casefold()}
            scope = earlier
        yield node, scope
        for key, value in node.items():
            if key != "cte_map":
                yield from _scoped(value, scope)
    elif isinstance(node, list):
        for value in node:
            yield from _scoped(value, scope)


def _is_ref_name(name: str) -> bool:
    folded = name.casefold()
    return folded == REF_COLUMN or folded.startswith(REF_COLUMN + "_")


def _carries_a_ref(select_node: dict[str, Any]) -> bool:
    """Whether a SELECT's own list can give a `_ref` column: an item aliased `_ref…`, a column
    `_ref…` unaliased, or a `*` that does not exclude `_ref`. A set operation (UNION) judges each
    side; anything the AST does not let us judge here is left to the run's check."""
    if select_node.get("type") == "SET_OPERATION_NODE":
        return all(_carries_a_ref(select_node.get(side) or {}) for side in ("left", "right"))
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
        if item.get("class") == "STAR" and not _star_touches(item, _is_ref_name, "exclude"):
            return True
    return False


def _star_names(item: dict[str, Any], part: str) -> list[str]:
    """The column names a `*`'s EXCLUDE, REPLACE or RENAME names (a qualified EXCLUDE's and a
    RENAME's key as their column; a RENAME's new name too)."""
    names: list[str] = []
    if part == "exclude":
        names += [str(e) for e in item.get("exclude_list", [])]
        names += [str(e.get("column", "")) for e in item.get("qualified_exclude_list", [])]
    elif part == "replace":
        names += [str(e.get("key", "")) for e in item.get("replace_list", [])]
    else:
        for e in item.get("rename_list", []):
            key = e.get("key")
            names.append(str(key.get("column", "")) if isinstance(key, dict) else str(key))
            names.append(str(e.get("value", "")))
    return names


def _star_touches(item: dict[str, Any], hit: Callable[[str], bool], part: str) -> bool:
    return any(hit(name) for name in _star_names(item, part))


#: The aggregates that carry every row they fold as a list (R15): `list(_ref)`, `array_agg(_ref)`.
_LIST_AGGREGATES = frozenset({"list", "array_agg"})


def _names(expression: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(n).casefold() for n in expression.get("column_names", []))


def _one_for_many(select_node: dict[str, Any]) -> list[str]:
    """Each `_ref…` item of a SELECT that does not carry every row it stands for: a `_ref…` item
    is a `_ref…` column (in a grouped SELECT, one it groups on), or `list(_ref…)`; anything else
    (`any_value(_ref)`, `min(_ref)`, a constant, an expression) names one row, or none, for many."""
    grouped = {
        _names(g)
        for g in select_node.get("group_expressions", [])
        if g.get("class") == "COLUMN_REF"
    }
    has_groups = bool(select_node.get("group_expressions"))
    found: list[str] = []
    for item in select_node.get("select_list", []):
        if item.get("class") == "STAR":
            continue
        alias = str(item.get("alias") or "")
        name = alias or (str(item["column_names"][-1]) if item.get("class") == "COLUMN_REF" else "")
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
#: `error()` raises its argument, a cell's value, as the refusal's words.
_DENIED_FUNCTIONS = frozenset({"current_setting", "getenv", "read_blob", "read_text", "error"})


@cache
def _aggregates() -> frozenset[str]:
    """DuckDB's own aggregate functions, by name, from its catalogue (on a connection of ours)."""
    con = sandbox_connection(memory_limit="64MB")
    try:
        found = con.execute(
            "SELECT DISTINCT lower(function_name) FROM duckdb_functions() "
            "WHERE function_type = 'aggregate'"
        ).fetchall()
    finally:
        con.close()
    return frozenset(str(name) for (name,) in found)


#: A refusal's words by DuckDB's kind of error: fixed, so no value of a row is ever repeated (the
#: orchestrator's review of L1.5, item 3: a conversion error prints the value unquoted).
_REFUSED_AS: tuple[tuple[type[duckdb.Error], str], ...] = (
    (duckdb.ParserException, "cannot be read as SQL"),
    (duckdb.PermissionException, "reads a file or the network, which is disabled by configuration"),
    (duckdb.CatalogException, "names a table or function that does not exist in the sandbox"),
    (duckdb.BinderException, "names a column or function its tables do not have"),
    (duckdb.ConversionException, "could not convert a value to the type it asks for"),
    (duckdb.OutOfRangeException, "computed a value out of range"),
    (duckdb.InvalidInputException, "gave a function a value it could not take"),
)


def _refused_words(exc: duckdb.Error) -> str:
    """What DuckDB refused, in our words alone, and where: the line of the SELECT, never its text
    nor DuckDB's message."""
    words = next(
        (said for kind, said in _REFUSED_AS if isinstance(exc, kind)),
        f"was refused by the database ({type(exc).__name__})",
    )
    line = re.search(r"\bLINE (\d+):", str(exc))
    return f"{words} (line {line.group(1)})" if line else words


def _row_by_row_problems(step: SqlStep, node: dict[str, Any], marks: set[str]) -> list[str]:
    """What a SQL step may not do where the pipeline binds a marking to a column (the
    orchestrator's review of L1.5, item 1: Map judges a row's marking by those cells, so a step
    folding rows, or rewriting a marked cell, would give a row a lower marking than the rows its
    values came from)."""
    found: list[str] = []
    why = "this pipeline binds a marking to a column, so a SQL step runs row by row"
    kind, cls = node.get("type"), node.get("class")
    if kind == "JOIN":
        found.append(f"step {step.id!r} joins tables, which it may not: {why}")
    elif kind == "SET_OPERATION_NODE" and node.get("setop_type") in ("INTERSECT", "EXCEPT"):
        found.append(f"step {step.id!r} uses {node['setop_type']}, which it may not: {why}")
    elif kind == "SELECT_NODE":
        if node.get("group_expressions") or node.get("group_sets") or node.get("having"):
            found.append(f"step {step.id!r} groups rows (GROUP BY, HAVING): {why}")
        for item in node.get("select_list", []):
            alias = str(item.get("alias") or "").casefold()
            column = ""
            if item.get("class") == "COLUMN_REF":
                column = str(item["column_names"][-1]).casefold()
            renamed = column in marks and alias not in ("", column)
            if (alias in marks and alias != column) or renamed:
                found.append(
                    f"step {step.id!r} gives the marked column {(alias or column)!r} other than "
                    f"as itself, from its own row: {why}, each marked column as it is"
                )
    if cls == "FUNCTION" and str(node.get("function_name", "")).casefold() in _aggregates():
        found.append(
            f"step {step.id!r} calls the aggregate {str(node['function_name']).casefold()}, which "
            f"it may not: {why}"
        )
    if cls == "STAR":
        hit = lambda name: name.casefold() in marks  # noqa: E731
        if _star_touches(node, hit, "replace") or _star_touches(node, hit, "rename"):
            found.append(
                f"step {step.id!r} rewrites or renames a marked column through * REPLACE or * "
                f"RENAME: {why}, each marked column as it is"
            )
        if _star_touches(node, hit, "exclude"):
            found.append(
                f"step {step.id!r} drops a marked column through * EXCLUDE: {why}, each marked "
                "column as it is"
            )
    return found


def sql_gate_problems(step: SqlStep, *, marked: Collection[str]) -> list[str]:
    """What the save gate refuses in a SQL step, in words, without running it over any row.
    `marked`: the columns the pipeline binds a marking to (`marked_columns`); any at all and the
    step runs row by row."""
    sql = step.select
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as exc:
        return [f"step {step.id!r}'s SELECT {_refused_words(exc)}"]
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
    tree: dict[str, Any] = json.loads(found[0]) if found else {"error": True}
    if tree.get("error"):
        return [f"step {step.id!r}'s SELECT cannot be read as SQL"]
    problems: list[str] = []
    inputs = {name.casefold() for name in step.inputs}
    marks = {name.casefold() for name in marked}
    scans: dict[str, int] = {}
    for node, ctes in _scoped(tree):
        kind = node.get("type")
        cls = node.get("class")
        if cls == "WINDOW":
            problems.append(
                f"step {step.id!r} uses a window function (OVER, QUALIFY), which a SQL step may "
                "not: it would give one row the values of others"
            )
        elif cls == "SUBQUERY":
            problems.append(
                f"step {step.id!r} has a subquery inside an expression (a scalar, IN or EXISTS "
                "subquery), which a SQL step may not: read a table in FROM or a WITH instead"
            )
        if cls == "STAR":
            if node.get("columns"):
                problems.append(
                    f"step {step.id!r} chooses columns by COLUMNS(…), which a SQL step may not: "
                    "name its columns"
                )
            if _star_touches(node, _is_ref_name, "replace") or _star_touches(
                node, _is_ref_name, "rename"
            ):
                problems.append(
                    f"step {step.id!r} rewrites or renames _ref through * REPLACE or * RENAME: "
                    "carry each row's _ref as it is"
                )
        if marks:
            problems.extend(_row_by_row_problems(step, node, marks))
        if kind == "SHOW_REF":
            problems.append(
                f"step {step.id!r} describes or summarises a table (SHOW, DESCRIBE, SUMMARIZE), "
                "which a SQL step may not: it selects from its tables"
            )
        # A column alias list renames by position, so `c(pin, _ref)` would call any column `_ref`
        # (an aggregate's one value among them) past the rule below (the lane review, item 3).
        for renamed in (node.get("aliases"), node.get("column_name_alias")):
            if isinstance(renamed, list) and any(_is_ref_name(str(n)) for n in renamed):
                problems.append(
                    f"step {step.id!r} names a column _ref through a list of column names: carry "
                    "_ref by its own name (an aggregate's as list(_ref) AS _ref)"
                )
        if kind == "TABLE_FUNCTION":
            name = (node.get("function") or {}).get("function_name", "?")
            problems.append(
                f"step {step.id!r} reads through a table function ({name}), which a SQL step may "
                "not: it reads only the tables named in its inputs"
            )
        elif kind == "BASE_TABLE":
            table = str(node.get("table_name", ""))
            scans[table.casefold()] = scans.get(table.casefold(), 0) + 1
            qualified = node.get("schema_name") or node.get("catalog_name")
            if qualified or table.casefold() not in inputs | set(ctes):
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
    for table, times in scans.items():
        if times > 1:
            problems.append(
                f"step {step.id!r} reads {table!r} {times} times, which a SQL step may not: read "
                "each table once, so every row it gives names the row it came from"
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


def _token(nonce: str, table: str, index: int) -> str:
    """A row's `_ref` token: a nonce drawn for this run, so no token can be written by hand into a
    SELECT (the orchestrator's review of L1.5, item 2), then its table and its place among the rows
    the reader may read."""
    return f"{nonce}:{table}#{index}"


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


def _blank(value: str | None) -> str | None:
    return value if value is not None and value.strip() else None


def run_sql_step(
    step: SqlStep,
    tables: Sequence[StagedTable],
    *,
    marked: Collection[str],
    readable: Callable[[StagedRef], bool] | None = None,
    time_limit: float = SQL_TIME_LIMIT_S,
    memory_limit: str = SQL_MEMORY_LIMIT,
    row_limit: int = SQL_ROW_LIMIT,
    byte_limit: int = SQL_BYTE_LIMIT,
    check: bool = True,
) -> tuple[StagedTable, StepReport]:
    """Run the step's SELECT over `tables` (its inputs, in its order) in the sandbox. `marked`: the
    columns the pipeline binds a marking to; any at all and each row it gives must come from one
    input row with every marked cell as that row has it. `readable`: whether the person running it
    may read a row, judged by each row's refs; a row they may not is left out of its table.
    `check=False` skips the gate, for the tests that prove the sandbox holds without it. Raises
    `StagingError`, in words, for anything refused."""
    if check:
        problems = sql_gate_problems(step, marked=marked)
        if problems:
            raise StagingError(problems)
    else:
        statements = []
        try:
            statements = duckdb.extract_statements(step.select)
        except duckdb.Error as exc:
            raise StagingError([f"step {step.id!r}'s SELECT {_refused_words(exc)}"]) from exc
        if len(statements) != 1:
            raise StagingError([f"step {step.id!r} is one SELECT statement, not {len(statements)}"])
    nonce = secrets.token_hex(12)
    by_token: dict[str, tuple[StagedTable, StagedTableRow]] = {}
    rows_in = withheld = 0
    con = sandbox_connection(memory_limit=memory_limit)
    try:
        for table in tables:
            # Folded, and the prefix too: every output column `_ref…` is read back as refs.
            if any(_is_ref_name(c) for c in table.columns):
                raise StagingError(
                    [f"the table {table.name!r} has a column named _ref or _ref_…, which a SQL "
                     "step keeps for its refs"]
                )  # fmt: skip
            kept: list[StagedTableRow] = []
            for row in table.rows:
                if readable is not None and not all(readable(ref) for ref in row.refs):
                    withheld += 1
                    continue
                kept.append(row)
            rows_in += len(kept)
            data: dict[str, list[str | None]] = {
                c: [row.cells.get(c) for row in kept] for c in table.columns
            }
            # Numbered over the kept rows only, so no token tells where a withheld row was (the
            # lane review, item 5).
            data[REF_COLUMN] = [_token(nonce, table.name, n) for n in range(len(kept))]
            for n, row in enumerate(kept):
                by_token[_token(nonce, table.name, n)] = (table, row)
            schema = pa.schema([pa.field(name, pa.string()) for name in data])
            con.register(table.name, pa.table(data, schema=schema))
        result = _execute(con, step, time_limit, row_limit, byte_limit)
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
                        [
                            f"step {step.id!r} gives a _ref that names no input row: carry each "
                            "row's _ref through unchanged"
                        ]  # fmt: skip
                    )
                tokens.append(token)
        if not tokens:
            raise StagingError(
                [
                    f"step {step.id!r} gives a row that carries no input row's _ref: every row it "
                    "gives must name the rows it came from"
                ]  # fmt: skip
            )
        tokens = list(dict.fromkeys(tokens))
        try:
            cells = {c: _text(record[c]) for c in columns}
        except TypeError as exc:
            raise StagingError(
                [
                    f"step {step.id!r} gives a column holding a {exc}, which a staged table cannot "
                    "hold: give it as text (string_agg, CAST … AS VARCHAR)"
                ]  # fmt: skip
            ) from exc
        if marked:
            _check_marked(step, marked, columns, cells, [by_token[t] for t in tokens])
        refs: list[StagedRef] = []
        for token in tokens:
            used.add(token)
            table, row = by_token[token]
            reached.add(table.name)
            refs.extend(r for r in row.refs if r not in refs)
        out.append(StagedTableRow(cells, tuple(refs)))
    if out:
        dropped = [t.name for t in tables if t.rows and t.name not in reached]
        if dropped:
            raise StagingError(
                [f"step {step.id!r}'s SELECT drops the _ref of {name!r}: carry it through as a "
                 "_ref_… column, so each row names the rows of it it came from" for name in dropped]
            )  # fmt: skip
    # Rule 2: an input row no output row names (a WHERE, an inner join) is counted, never lost
    # without a word; every token is a row's own (a nonce, no window, no table read twice), so
    # each one used is a row given.
    report = StepReport(
        step.id, "sql", rows_in=rows_in, rows_out=len(out), rows_withheld=withheld,
        filtered_out=rows_in - len(used),
    )  # fmt: skip
    return StagedTable(step.id, columns, out), report


def _check_marked(
    step: SqlStep,
    marked: Collection[str],
    columns: Sequence[str],
    cells: dict[str, str | None],
    came_from: Sequence[tuple[StagedTable, StagedTableRow]],
) -> None:
    """The run's own check where a marking is bound to a column, whatever the gate could see: the
    row comes from one input row, and each marked column that row has is given as it has it, under
    its own name; none is computed where the row has none. Words name the column, never a value."""
    why = "this pipeline binds a marking to a column, so a SQL step runs row by row"
    if len(came_from) != 1:
        raise StagingError(
            [f"step {step.id!r} gives a row made from {len(came_from)} input rows: {why}"]
        )
    ((table, row),) = came_from
    for column in marked:
        had, gives = column in table.columns, column in columns
        if had and not gives:
            raise StagingError(
                [f"step {step.id!r} drops the marked column {column!r}: {why}, each marked "
                 "column as it is"]
            )  # fmt: skip
        if gives and not had:
            raise StagingError(
                [f"step {step.id!r} computes the marked column {column!r}, which its input row "
                 f"does not have: {why}, each marked column as it is"]
            )  # fmt: skip
        if had and _blank(cells.get(column)) != _blank(row.cells.get(column)):
            raise StagingError(
                [f"step {step.id!r} rewrites the marked column {column!r}: {why}, each marked "
                 "column as its own row has it"]
            )  # fmt: skip


def _execute(
    con: duckdb.DuckDBPyConnection,
    step: SqlStep,
    time_limit: float,
    row_limit: int,
    byte_limit: int,
) -> pa.Table:
    """The SELECT's rows, read batch by batch within the time limit, refused (never cut short) past
    the row or byte limit, before any of it becomes Python values."""
    timer = threading.Timer(time_limit, con.interrupt)
    timer.start()
    try:
        reader = con.execute(step.select).to_arrow_reader(_BATCH_ROWS)
        batches: list[pa.RecordBatch] = []
        rows = size = 0
        for batch in reader:
            rows += batch.num_rows
            size += batch.nbytes
            if rows > row_limit or size > byte_limit:
                raise StagingError(
                    [f"step {step.id!r} gives more than {row_limit:,} rows or "
                     f"{byte_limit // (1024 * 1024):,} MB, which a SQL step may not: its output is "
                     "never cut short, so narrow its SELECT"]
                )  # fmt: skip
            batches.append(batch)
        return pa.Table.from_batches(batches, schema=reader.schema)
    except duckdb.InterruptException as exc:
        raise StagingError(
            [f"step {step.id!r} ran past its time limit of {time_limit:g} seconds and was stopped"]
        ) from exc
    except duckdb.OutOfMemoryException as exc:
        raise StagingError([f"step {step.id!r} ran past its memory limit and was stopped"]) from exc
    except duckdb.Error as exc:
        raise StagingError([f"step {step.id!r}'s SELECT {_refused_words(exc)}"]) from exc
    finally:
        timer.cancel()
