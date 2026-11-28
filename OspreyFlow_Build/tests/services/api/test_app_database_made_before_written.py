"""A test's setup makes the app's own database before it writes to it (slice SE8g, rule 12).

**Which test fails if the fault returns.**
`test_every_setup_makes_the_apps_database_before_writing_to_it` names the file, the function and the
line of the first write wherever a function under this folder opens the app's own ArcadeDB database
and writes to it with no `create_database_if_absent()` before.

The fault it guards: the app creates its database, `ospreyflow`, in its lifespan
(`services/api/run_resources.py`, `build_run_resources`). Three setups in `test_reports.py` wrote to
it before the app had started, so on a fresh ArcadeDB, run alone, each was refused ("Database
'ospreyflow' is not available"). The file passed on GitHub only because an earlier file of the
`conformance` job had created the database. Pure: it reads syntax trees and opens no store.

**What it reads:** every `*.py` below `tests/services/api/` (test modules and helper modules), by
syntax tree, never by text.

**What opens the app's own database:** `ArcadeDBClient(config)`, under that name or an import alias,
where `config` (written in place, or bound to a name in the function or at module level, passed by
position or as `config=`) is one of:

* `ArcadeDBConfig.from_env(database="ospreyflow")` or `ArcadeDBConfig.from_env("ospreyflow")`;
* `ArcadeDBConfig(database="ospreyflow")`, or `ArcadeDBConfig(...)` naming no database, whose
  default is `ospreyflow`;
* either, with the database read from the app's own variable: `os.environ["ARCADEDB_DATABASE"]`,
  `os.environ.get("ARCADEDB_DATABASE", ...)` or `os.getenv("ARCADEDB_DATABASE", ...)`;
* either, with the database a name bound to `"ospreyflow"` or to one of those reads.

A function of the same file that returns or yields such a handle without having made the database
passes it on: what its caller binds from it is the app's database too.

**What writes:** a call of one of `WRITES` on that handle (or on what a constructor builds from it,
such as the adapter), or the handle passed to a function of the same file that writes to its
argument. `command`, `sql` and `gremlin` count whatever their text says.

**What makes it first:** `await <that client>.create_database_if_absent()`, or a call of a function
of the same file that does so, earlier in the same function and not under an `if`, a loop, an
`except` or a nested function. Each function answers for itself: what another setup ran earlier does
not count, because that is the dependence on order this guard exists to stop. The rule does not ask
whether the app happens to be running by then.

**Not read:** a database name worked out at run time (a parameter, an f-string); a handle opened by
a helper or fixture of another file; the running app's own handle (`app.state.graph`), which exists
only once the lifespan has made the database.
"""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

FOLDER = Path(__file__).resolve().parent

APP_DATABASE = "ospreyflow"
APP_VARIABLE = "ARCADEDB_DATABASE"
CREATE = "create_database_if_absent"

#: The methods of `ArcadeDBClient` and `GraphArcadeDBAdapter` that change the database, and the
#: three that send it whatever text they are given.
WRITES = frozenset(
    {
        "apply_schema", "revert_schema", "begin_transaction", "commit_transaction",
        "upsert_nodes", "upsert_edges", "bulk_load_edges", "revert_elements", "withdraw_elements",
        "promote_elements", "revert_promotion", "withdraw_layer", "restore_withdrawn",
        "restore_link_state", "strip_provenance_references", "regrade_drawn", "supersede_node",
        "supersede_edge", "clear_pending_index", "command", "sql", "gremlin",
    }
)  # fmt: skip

Function = ast.FunctionDef | ast.AsyncFunctionDef
Position = tuple[int, int]


@dataclass(frozen=True, order=True)
class Unmade:
    """A function that writes to the app's database without having made it."""

    function: str
    line: int


def _last_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _dotted(node: ast.expr) -> str | None:
    """`client` or `self.client`; `None` for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def _unawaited(node: ast.expr) -> ast.expr:
    return node.value if isinstance(node, ast.Await) else node


def _argument(call: ast.Call, keyword: str) -> ast.expr | None:
    for found in call.keywords:
        if found.arg == keyword:
            return found.value
    return None


def _bindings(nodes: Iterator[ast.AST]) -> dict[str, ast.expr]:
    found: dict[str, ast.expr] = {}
    for node in nodes:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                found[node.target.id] = node.value
    return found


def _is_app_database(node: ast.expr, names: dict[str, ast.expr], seen: frozenset[str]) -> bool:
    if isinstance(node, ast.Constant):
        return node.value == APP_DATABASE
    if isinstance(node, ast.Name):
        if node.id in seen or node.id not in names:
            return False
        return _is_app_database(names[node.id], names, seen | {node.id})
    if isinstance(node, ast.Subscript) and _dotted(node.value) == "os.environ":
        return isinstance(node.slice, ast.Constant) and node.slice.value == APP_VARIABLE
    if isinstance(node, ast.Call) and _dotted(node.func) in {"os.environ.get", "os.getenv"}:
        first = node.args[0] if node.args else None
        return isinstance(first, ast.Constant) and first.value == APP_VARIABLE
    return False


def _is_app_config(node: ast.expr, names: dict[str, ast.expr], seen: frozenset[str]) -> bool:
    if isinstance(node, ast.Name):
        if node.id in seen or node.id not in names:
            return False
        return _is_app_config(names[node.id], names, seen | {node.id})
    if not isinstance(node, ast.Call):
        return False
    database = _argument(node, "database")
    if isinstance(node.func, ast.Attribute) and node.func.attr == "from_env":
        if _last_name(node.func.value) != "ArcadeDBConfig":
            return False
        if database is None and node.args:
            database = node.args[0]
        return database is not None and _is_app_database(database, names, frozenset())
    if _last_name(node.func) == "ArcadeDBConfig":
        return database is None or _is_app_database(database, names, frozenset())
    return False


def _unconditional(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """The statements that run whenever the function gets that far."""
    for statement in body:
        yield statement
        if isinstance(statement, ast.Try | ast.With | ast.AsyncWith):
            yield from _unconditional(statement.body)


def _position(node: ast.stmt | ast.expr) -> Position:
    return (node.lineno, node.col_offset)


class _File:
    def __init__(self, source: str) -> None:
        tree = ast.parse(source)
        self.module_names = _bindings(iter(tree.body))
        self.client_names = {"ArcadeDBClient"} | {
            alias.asname
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if alias.name == "ArcadeDBClient" and alias.asname
        }
        self.functions = [n for n in ast.walk(tree) if isinstance(n, Function)]
        self.writers: set[str] = set()  # write to a handle passed to them
        self.makers: set[str] = set()  # make the app's database
        self.passers: set[str] = set()  # hand on the app's database, not yet made
        self._settle()

    def _settle(self) -> None:
        """Each set can grow another, so they are worked out until none changes."""
        while True:
            before = (len(self.writers), len(self.makers), len(self.passers))
            for function in self.functions:
                if self._writes_to_an_argument(function):
                    self.writers.add(function.name)
                names = self._names(function)
                handles = self._handles(function, names)
                made = self._made_at(function, names, handles)
                if made is not None:
                    self.makers.add(function.name)
                if self._passes_on(function, names, handles, made):
                    self.passers.add(function.name)
            if before == (len(self.writers), len(self.makers), len(self.passers)):
                return

    def _names(self, function: Function) -> dict[str, ast.expr]:
        return {**self.module_names, **_bindings(ast.walk(function))}

    def _opens(self, node: ast.expr, names: dict[str, ast.expr]) -> bool:
        """`node` is the app's database: opened here, or handed on by a function of this file."""
        node = _unawaited(node)
        if not isinstance(node, ast.Call):
            return False
        called = _last_name(node.func)
        if called in self.client_names:
            config = node.args[0] if node.args else _argument(node, "config")
            return config is not None and _is_app_config(config, names, frozenset())
        return isinstance(node.func, ast.Name) and called in self.passers

    def _is_handle(self, node: ast.expr, names: dict[str, ast.expr], handles: set[str]) -> bool:
        """The app's database, or what a constructor builds from it."""
        if _dotted(node) in handles or self._opens(node, names):
            return True
        node = _unawaited(node)
        return (
            isinstance(node, ast.Call)
            and (_last_name(node.func) or "")[:1].isupper()
            and any(self._is_handle(a, names, handles) for a in node.args)
        )

    def _handles(self, function: Function, names: dict[str, ast.expr]) -> set[str]:
        """The names in `function` that hold the app's database."""
        bound: list[tuple[ast.expr, ast.expr]] = []
        for node in ast.walk(function):
            if isinstance(node, ast.Assign):
                bound.extend((target, node.value) for target in node.targets)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                bound.append((node.target, node.value))
            elif isinstance(node, ast.With | ast.AsyncWith):
                bound.extend(
                    (item.optional_vars, item.context_expr)
                    for item in node.items
                    if item.optional_vars is not None
                )
        handles: set[str] = set()
        while True:
            before = len(handles)
            for target, value in bound:
                name = _dotted(target)
                if name is None:
                    continue
                if self._is_handle(value, names, handles):
                    handles.add(name)
            if before == len(handles):
                return handles

    def _calls_a_maker(self, node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in self.makers
        )

    def _made_at(
        self, function: Function, names: dict[str, ast.expr], handles: set[str]
    ) -> Position | None:
        """Where `function` first makes the app's database, if it surely does."""
        found: list[Position] = []
        for statement in _unconditional(function.body):
            if isinstance(statement, ast.AsyncWith | ast.With):
                calls = [item.context_expr for item in statement.items]
            elif isinstance(statement, ast.Expr | ast.Assign) and isinstance(
                statement.value, ast.Await
            ):
                awaited = statement.value.value
                if (
                    isinstance(awaited, ast.Call)
                    and isinstance(awaited.func, ast.Attribute)
                    and awaited.func.attr == CREATE
                    and self._is_handle(awaited.func.value, names, handles)
                ):
                    found.append(_position(statement))
                calls = [awaited]
            else:
                continue
            if any(self._calls_a_maker(call) for call in calls):
                found.append(_position(statement))
        return min(found, default=None)

    def _writes_to_an_argument(self, function: Function) -> bool:
        arguments = function.args
        parameters = {
            a.arg
            for a in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
            if a.arg not in {"self", "cls"}
        }
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr in WRITES:
                if _dotted(node.func.value) in parameters:
                    return True
            if isinstance(node.func, ast.Name) and node.func.id in self.writers:
                if any(_dotted(a) in parameters for a in node.args):
                    return True
        return False

    def _first_write(
        self, function: Function, names: dict[str, ast.expr], handles: set[str]
    ) -> Position | None:
        found: list[Position] = []
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr in WRITES:
                if self._is_handle(node.func.value, names, handles):
                    found.append(_position(node))
            if isinstance(node.func, ast.Name) and node.func.id in self.writers:
                passed = [*node.args, *(k.value for k in node.keywords)]
                if any(self._is_handle(a, names, handles) for a in passed):
                    found.append(_position(node))
        return min(found, default=None)

    def _passes_on(
        self,
        function: Function,
        names: dict[str, ast.expr],
        handles: set[str],
        made: Position | None,
    ) -> bool:
        return any(
            isinstance(node, ast.Return | ast.Yield)
            and node.value is not None
            and self._is_handle(node.value, names, handles)
            and (made is None or _position(node) < made)
            for node in ast.walk(function)
        )

    def unmade(self) -> list[Unmade]:
        found: list[Unmade] = []
        for function in self.functions:
            names = self._names(function)
            handles = self._handles(function, names)
            write = self._first_write(function, names, handles)
            made = self._made_at(function, names, handles)
            if write is not None and (made is None or write < made):
                found.append(Unmade(function.name, write[0]))
        return sorted(found)


def unmade_in(source: str) -> list[Unmade]:
    return _File(source).unmade()


def unmade_under(folder: Path) -> list[str]:
    return [
        f"{path.relative_to(folder).as_posix()}::{found.function} (line {found.line})"
        for path in sorted(folder.rglob("*.py"))
        if "__pycache__" not in path.parts
        for found in unmade_in(path.read_text(encoding="utf-8"))
    ]


# --- The tree -------------------------------------------------------------------------------


def test_every_setup_makes_the_apps_database_before_writing_to_it() -> None:
    found = unmade_under(FOLDER)
    assert not found, (
        "these write to the app's own database without creating it first, so on a fresh ArcadeDB, "
        "run alone, they are refused unless something else has made it:\n  " + "\n  ".join(found)
    )


# --- Rule 15: the plant at the real shape ----------------------------------------------------


def test_removing_the_create_line_from_the_real_helper_is_named() -> None:
    """`test_reports.py` as it stands passes; with its one helper's create line removed, the helper
    is named, and so is each of the three setups that take their database from it."""
    source = (FOLDER / "test_reports.py").read_text(encoding="utf-8")
    line = f"        await client.{CREATE}()\n"
    assert source.count(line) == 1, "the helper's create line is not where this plant expects it"
    assert unmade_in(source) == []
    assert [found.function for found in unmade_in(source.replace(line, ""))] == [
        "_app_graph",
        "_case_with_an_alert",
        "_case_with_an_alert_and_one_over_a_hidden_link",
        "_pole_case",
    ]


# --- The shapes ------------------------------------------------------------------------------

OPEN = 'client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))'


def _setup(*lines: str, before: str = "") -> str:
    body = textwrap.indent("\n".join(lines), "    ")
    return f"{before}\nasync def _arrange() -> None:\n{body}\n"


#: Source whose `_arrange` writes to the app's database without having made it.
FLAGGED = {
    "as on main: the schema applied through the adapter": _setup(
        OPEN,
        "try:",
        "    graph = GraphArcadeDBAdapter(client, SCHEME)",
        "    await graph.apply_schema(ontology)",
        "finally:",
        "    await client.aclose()",
    ),
    "the database by position": _setup(
        'client = ArcadeDBClient(ArcadeDBConfig.from_env("ospreyflow"))',
        'await client.command("sql", "INSERT INTO Person")',
    ),
    "the config class with the database named": _setup(
        'client = ArcadeDBClient(ArcadeDBConfig(database="ospreyflow"))',
        "await client.begin_transaction()",
    ),
    "the config class's default database": _setup(
        "client = ArcadeDBClient(config=ArcadeDBConfig())", "await client.begin_transaction()"
    ),
    "the app's variable, with a default": _setup(
        'name = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")',
        "config = ArcadeDBConfig.from_env(name)",
        'await ArcadeDBClient(config).sql("DELETE FROM Person")',
    ),
    "the app's variable, subscripted": _setup(
        'client = ArcadeDBClient(ArcadeDBConfig.from_env(os.environ["ARCADEDB_DATABASE"]))',
        "await client.begin_transaction()",
    ),
    "the app's variable, by getenv": _setup(
        'client = ArcadeDBClient(ArcadeDBConfig.from_env(os.getenv("ARCADEDB_DATABASE")))',
        "await client.begin_transaction()",
    ),
    "module constants": _setup(
        "client = ArcadeDBClient(CONFIG)",
        "await client.begin_transaction()",
        before='DB = "ospreyflow"\nCONFIG = ArcadeDBConfig.from_env(DB)',
    ),
    "an import alias": _setup(
        'client = Store(ArcadeDBConfig.from_env("ospreyflow"))',
        "await client.begin_transaction()",
        before="from adapters.graph_arcadedb.client import ArcadeDBClient as Store",
    ),
    "the write made by a helper of the file": _setup(
        OPEN,
        "graph = GraphArcadeDBAdapter(client, SCHEME)",
        "await _write(graph, [])",
        before="async def _write(g, nodes):\n    await g.upsert_nodes(nodes, None)",
    ),
    "the handle from a helper that does not make it": _setup(
        "async with _open() as graph:",
        "    await graph.apply_schema(ontology)",
        before=f"@asynccontextmanager\nasync def _open():\n    {OPEN}\n"
        "    yield GraphArcadeDBAdapter(client, SCHEME)",
    ),
    "created after the write": _setup(
        OPEN, "await client.begin_transaction()", f"await client.{CREATE}()"
    ),
    "created and not awaited": _setup(
        OPEN, f"client.{CREATE}()", "await client.begin_transaction()"
    ),
    "created only on one path": _setup(
        OPEN,
        "if fresh:",
        f"    await client.{CREATE}()",
        "await client.begin_transaction()",
    ),
    "another database created instead": _setup(
        'other = ArcadeDBClient(ArcadeDBConfig.from_env("scratch"))',
        f"await other.{CREATE}()",
        OPEN,
        "await client.begin_transaction()",
    ),
}

#: Source with nothing to name.
PASSED = {
    "created first": _setup(OPEN, f"await client.{CREATE}()", "await client.begin_transaction()"),
    "created first, inside try": _setup(
        OPEN,
        "try:",
        f"    await client.{CREATE}()",
        "    graph = GraphArcadeDBAdapter(client, SCHEME)",
        "    await graph.apply_schema(ontology)",
        "finally:",
        "    await client.aclose()",
    ),
    "made by a helper of the file that is called first": _setup(
        "await _make()",
        OPEN,
        "await client.begin_transaction()",
        before=f"async def _make():\n    {OPEN}\n    await client.{CREATE}()",
    ),
    "the handle from a helper that makes it": _setup(
        "async with _open() as graph:",
        "    await graph.begin_transaction()",
        before=f"@asynccontextmanager\nasync def _open():\n    {OPEN}\n"
        f"    await client.{CREATE}()\n    yield GraphArcadeDBAdapter(client, SCHEME)",
    ),
    "a database of the test's own": _setup(
        'client = ArcadeDBClient(ArcadeDBConfig.from_env("conformance_1_abc"))',
        "await client.begin_transaction()",
    ),
    "the app's database opened and not written": _setup(
        OPEN, "graph = GraphArcadeDBAdapter(client, SCHEME)", "await graph.get_nodes([], READER)"
    ),
}


@pytest.mark.parametrize("source", FLAGGED.values(), ids=FLAGGED.keys())
def test_a_write_before_the_database_is_made_is_named(source: str) -> None:
    assert "_arrange" in [found.function for found in unmade_in(source)]


@pytest.mark.parametrize("source", PASSED.values(), ids=PASSED.keys())
def test_a_setup_that_makes_it_or_writes_elsewhere_is_not_named(source: str) -> None:
    assert unmade_in(source) == []


def test_the_walk_reaches_a_helper_module_in_a_folder_below(tmp_path: Path) -> None:
    (tmp_path / "working_set").mkdir()
    (tmp_path / "working_set" / "helpers.py").write_text(
        FLAGGED["the database by position"], encoding="utf-8"
    )
    assert unmade_under(tmp_path) == ["working_set/helpers.py::_arrange (line 4)"]
