"""Every stand-in for `app._case_report` in `tests/` has its shape (SE8f; `process/CLAUDE.md`
rules 12 and 15). No store.

SE8b made `_case_report` answer `tuple[ReportFigures, bool]`. A stand-in in a test that needs a live
store went on answering a bare `ReportFigures`, and the feed route answered 500 where the test
expected 200. A gate with no store never ran that test, and CI's `mypy` does not check `tests/`.
This reads the real function's return annotation and holds every stand-in to it, from the sources
alone: `async def`, the same annotation as written and, where the annotation is a tuple of a fixed
length, every `return` a tuple of that length written out. An annotation by itself is checked by
nothing here, so one that says a pair over a body that returns the bare model is red too.

A stand-in is whatever a test puts in the function's place: assigned to `<module>._case_report`,
given to `setattr`, `setitem`, `patch` or `patch.object` by that name, passed as `_case_report=`,
held under the key `"_case_report"`, or chosen by `x if name == "_case_report" else y`. It must be
a function in the same file, or a call of a function there that returns one. Anything else (a
lambda, a mock, an imported name) is reported: its shape cannot be read. Putting back the saved
original is not a stand-in. Not seen: a name held in a variable and given to `setattr`, with none
of the above.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from services.api import app as app_module

NAME = "_case_report"
TESTS = Path(__file__).resolve().parents[2]
#: The files that stand in today: a scan that stops finding these is reading nothing.
KNOWN = {
    "services/api/test_export_ledger_completeness.py",
    "services/api/test_investigation_access_store.py",
}

Function = ast.FunctionDef | ast.AsyncFunctionDef


def real_annotation() -> str:
    """`_case_report`'s return annotation, as written."""
    annotation = inspect.signature(app_module._case_report).return_annotation
    assert isinstance(annotation, str), f"{NAME} has no return annotation to read: {annotation!r}"
    return annotation


def _normal(annotation: ast.expr) -> str:
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        annotation = ast.parse(annotation.value, mode="eval").body
    return ast.unparse(annotation)


def _tuple_length(annotation: str) -> int | None:
    """The length of a `tuple[A, B]` annotation; None for any other, `tuple[A, ...]` included."""
    node = ast.parse(annotation, mode="eval").body
    if not (isinstance(node, ast.Subscript) and ast.unparse(node.value) == "tuple"):
        return None
    if not isinstance(node.slice, ast.Tuple):
        return None
    items = node.slice.elts
    if any(isinstance(i, ast.Constant) and i.value is Ellipsis for i in items):
        return None
    return len(items)


def _own(scope: ast.AST) -> Iterator[ast.AST]:
    """The nodes of a scope itself: a nested function or class is yielded, never entered."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, Function | ast.ClassDef | ast.Lambda):
            stack.extend(ast.iter_child_nodes(node))


class _Source:
    """One test file: what it puts in `_case_report`'s place, and what is wrong with each."""

    def __init__(self, text: str, where: str, annotation: str) -> None:
        self.tree = ast.parse(text, filename=where)
        self.where = where
        self.annotation = _normal(ast.parse(annotation, mode="eval").body)
        self.parents = {c: p for p in ast.walk(self.tree) for c in ast.iter_child_nodes(p)}

    def _scopes(self, node: ast.AST) -> Iterator[ast.AST]:
        while node in self.parents:
            node = self.parents[node]
            if isinstance(node, Function | ast.Module):
                yield node

    def _bindings(self, name: str, scopes: Iterator[ast.AST]) -> list[ast.AST]:
        """What binds `name` in the nearest of `scopes` that binds it."""
        for scope in scopes:
            found: list[ast.AST] = []
            if isinstance(scope, Function):
                arguments = ast.walk(scope.args)
                found += [a for a in arguments if isinstance(a, ast.arg) and a.arg == name]
            for node in _own(scope):
                if isinstance(node, Function) and node.name == name:
                    found.append(node)
                elif isinstance(node, ast.Name) and node.id == name:
                    if isinstance(node.ctx, ast.Store):
                        found.append(self.parents[node])
            if found:
                return found
        return []

    def installs(self) -> Iterator[tuple[ast.AST, ast.expr | None, int | None]]:
        """Each place something is put in the function's place: the node, what is put there (None
        when the call names no replacement) and, for one name of a tuple assigned from a single
        value, its position."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    yield from self._assigned(node, target, node.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value == NAME:
                        yield node, value, None
            elif isinstance(node, ast.IfExp):
                test = node.test
                if isinstance(test, ast.Compare) and isinstance(test.ops[0], ast.Eq):
                    sides = [test.left, *test.comparators]
                    if any(isinstance(s, ast.Constant) and s.value == NAME for s in sides):
                        yield node, node.body, None
            elif isinstance(node, ast.Call):
                yield from self._called(node)

    def _assigned(
        self, node: ast.AST, target: ast.expr, value: ast.expr
    ) -> Iterator[tuple[ast.AST, ast.expr, int | None]]:
        if isinstance(target, ast.Tuple | ast.List):
            for position, element in enumerate(target.elts):
                if not self._is_the_function(element):
                    continue
                if isinstance(value, ast.Tuple | ast.List) and len(value.elts) == len(target.elts):
                    yield node, value.elts[position], None
                else:
                    yield node, value, position
        elif self._is_the_function(target):
            yield node, value, None

    @staticmethod
    def _is_the_function(target: ast.expr) -> bool:
        if isinstance(target, ast.Attribute):
            return target.attr == NAME
        return (
            isinstance(target, ast.Subscript)
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == NAME
        )

    def _called(self, node: ast.Call) -> Iterator[tuple[ast.AST, ast.expr | None, None]]:
        for keyword in node.keywords:
            if keyword.arg == NAME:
                yield node, keyword.value, None
        called = ast.unparse(node.func).split(".")
        by_name = called[-1] in {"setattr", "setitem", "patch"}
        if not (by_name or called[-2:] == ["patch", "object"]):
            return
        for position, argument in enumerate(node.args):
            if not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)):
                continue
            if argument.value != NAME and not argument.value.endswith("." + NAME):
                continue
            rest = node.args[position + 1 :]
            named = [k.value for k in node.keywords if k.arg in {"new", "value"}]
            yield node, rest[0] if rest else next(iter(named), None), None

    def _is_restore(self, node: ast.AST, value: ast.expr, position: int | None) -> bool:
        """`value` is a name saved from `<module>._case_report` itself, at the same position."""
        if not isinstance(value, ast.Name):
            return False
        bindings = self._bindings(value.id, self._scopes(node))
        if not bindings:
            return False
        for binding in bindings:
            if not isinstance(binding, ast.Assign):
                return False
            saved: ast.expr = binding.value
            if position is not None:
                if not (isinstance(saved, ast.Tuple) and position < len(saved.elts)):
                    return False
                saved = saved.elts[position]
            if not (isinstance(saved, ast.Attribute) and saved.attr == NAME):
                return False
        return True

    def _functions(self, node: ast.AST, value: ast.expr) -> list[Function] | None:
        """The functions `value` names, or None when they cannot all be read here."""
        if isinstance(value, ast.Name):
            bindings = self._bindings(value.id, self._scopes(node))
            functions = [b for b in bindings if isinstance(b, Function)]
            return functions if functions and len(functions) == len(bindings) else None
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            factories = self._functions(node, value.func)
            made: list[Function] = []
            for factory in factories or []:
                returns = [r for r in _own(factory) if isinstance(r, ast.Return)]
                if not isinstance(factory, ast.FunctionDef) or not returns:
                    return None
                for statement in returns:
                    if not isinstance(statement.value, ast.Name):
                        return None
                    inner = self._functions(statement, statement.value)
                    if inner is None:
                        return None
                    made += inner
            return made or None
        return None

    def _wrong(self, function: Function) -> Iterator[str]:
        at = f"{self.where}:{function.lineno}: the stand-in `{function.name}`"
        if not isinstance(function, ast.AsyncFunctionDef):
            yield f"{at} is not `async def`, and {NAME} is awaited"
        declared = None if function.returns is None else _normal(function.returns)
        if declared != self.annotation:
            yield f"{at} is annotated `{declared}`; {NAME} returns `{self.annotation}`"
        length = _tuple_length(self.annotation)
        if length is None:
            return
        returns = [r for r in _own(function) if isinstance(r, ast.Return)]
        if not returns and not isinstance(function.body[-1], ast.Raise):
            yield f"{at} returns nothing; {NAME} returns `{self.annotation}`"
        for statement in returns:
            value = statement.value
            if not (
                isinstance(value, ast.Tuple)
                and len(value.elts) == length
                and not any(isinstance(e, ast.Starred) for e in value.elts)
            ):
                shown = "None" if value is None else ast.unparse(value)
                yield (
                    f"{self.where}:{statement.lineno}: the stand-in `{function.name}` returns "
                    f"`{shown}`, not a tuple of {length} written out, as `{self.annotation}` is"
                )

    def check(self) -> tuple[int, list[str]]:
        """How many stand-ins the file puts in the function's place, and what is wrong."""
        stood_in = 0
        problems: list[str] = []
        for node, value, position in self.installs():
            if value is not None and self._is_restore(node, value, position):
                continue
            stood_in += 1
            functions = None
            if value is not None and position is None:
                functions = self._functions(node, value)
            if functions is None:
                shown = "a default mock" if value is None else f"`{ast.unparse(value)}`"
                problems.append(
                    f"{self.where}:{getattr(node, 'lineno', 0)}: {shown} stands in for {NAME} and "
                    "its shape cannot be read: stand in with a function written in this file"
                )
                continue
            for function in functions:
                problems += [p for p in self._wrong(function) if p not in problems]
        return stood_in, problems


def scan(root: Path, annotation: str) -> tuple[set[str], list[str]]:
    """The files under `root` that stand in for the function, and every disagreement."""
    files: set[str] = set()
    problems: list[str] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if NAME not in text:
            continue
        where = path.relative_to(root).as_posix()
        stood_in, wrong = _Source(text, where, annotation).check()
        if stood_in:
            files.add(where)
        problems += wrong
    return files, problems


def test_every_stand_in_for_case_report_has_its_shape() -> None:
    files, problems = scan(TESTS, real_annotation())
    assert not problems, "stand-ins that disagree with _case_report:\n" + "\n".join(problems)
    assert KNOWN <= files, f"the scan no longer sees the known stand-ins: {KNOWN - files}"


# --- the guard shown able to fail, in the shapes the tree writes (rule 15) ----------------------

PAIR = "tuple[ReportFigures, bool]"

#: The stand-in as it stood on main after SE8b, installed and put back as that test does it.
STALE = """
async def test_x():
    async def _figures(*_: Any, **__: Any) -> ReportFigures:
        now = datetime.now(UTC)
        return ReportFigures(period_weeks=12, as_of=now.date(), generated_at=now, alerts_total=0)

    original = (app_module._case_report, app_module.reports_module.feed_rows)
    app_module._case_report = _figures  # type: ignore[assignment]
    try:
        pass
    finally:
        app_module._case_report, app_module.reports_module.feed_rows = original
"""

RIGHT = """
async def test_x():
    async def _figures(*_: Any, **__: Any) -> tuple[ReportFigures, bool]:
        return ReportFigures(period_weeks=12), False

    original = (app_module._case_report, app_module.reports_module.feed_rows)
    app_module._case_report = _figures
    app_module._case_report, app_module.reports_module.feed_rows = original
"""

#: A factory held under the function's name, as the ledger's route cases hold theirs.
FACTORY = """
def _the_figures(lowered: bool = False) -> Any:
    async def figures(*args: Any, **kwargs: Any) -> {declared}:
        return {returned}

    return figures


def _cases():
    return {{"_case_report": _the_figures()}}
"""

BARE = """
async def fake(*_: Any) -> tuple[ReportFigures, bool]:
    return ReportFigures(period_weeks=12)
"""


@pytest.mark.parametrize(
    "source", [RIGHT, FACTORY.format(declared=PAIR, returned="Figures(), lowered")]
)
def test_the_guard_passes_a_stand_in_of_the_right_shape(source: str) -> None:
    assert _Source(source, "planted.py", PAIR).check() == (1, [])


def test_the_guard_reports_the_stand_in_se8b_left_behind() -> None:
    stood_in, problems = _Source(STALE, "planted.py", PAIR).check()
    assert stood_in == 1, "the restore is not a stand-in"
    assert len(problems) == 2, problems
    assert "is annotated `ReportFigures`" in problems[0]
    assert "returns `ReportFigures(" in problems[1]


def test_a_right_annotation_over_a_bare_model_is_reported() -> None:
    bare = "ReportFigures(period_weeks=12)"
    source = RIGHT.replace(f"{bare}, False", bare)
    _, (problem,) = _Source(source, "planted.py", PAIR).check()
    assert "returns `ReportFigures(period_weeks=12)`, not a tuple of 2" in problem


@pytest.mark.parametrize(
    ("declared", "returned", "said"),
    [
        ("Any", "Figures(), lowered", "is annotated `Any`"),
        (PAIR, "Figures()", "not a tuple of 2"),
        (PAIR, "Figures(), lowered, 1", "not a tuple of 2"),
    ],
)
def test_a_factorys_stand_in_is_read(declared: str, returned: str, said: str) -> None:
    source = FACTORY.format(declared=declared, returned=returned)
    _, (problem,) = _Source(source, "planted.py", PAIR).check()
    assert said in problem


@pytest.mark.parametrize(
    "install",
    [
        "app_module._case_report = fake",
        "app_module._case_report, other = fake, 1",
        'app_module.__dict__["_case_report"] = fake',
        'monkeypatch.setattr(app_module, "_case_report", fake)',
        'monkeypatch.setattr("services.api.app._case_report", fake)',
        'monkeypatch.setitem(vars(app_module), "_case_report", fake)',
        'mock.patch.object(app_module, "_case_report", new=fake)',
        'patch("services.api.app._case_report", fake)',
        "patch.multiple(app_module, _case_report=fake)",
        'monkeypatch.setattr(app_module, attr, fake if attr == "_case_report" else value)',
    ],
)
def test_every_way_of_standing_in_is_seen(install: str) -> None:
    source = BARE + textwrap.dedent(
        f"""
        def test_x(monkeypatch, attr, value):
            {install}
        """
    )
    stood_in, (problem,) = _Source(source, "planted.py", PAIR).check()
    assert stood_in == 1 and "not a tuple of 2" in problem, problem


@pytest.mark.parametrize(
    "install",
    [
        "app_module._case_report = AsyncMock(return_value=figures)",
        "app_module._case_report = lambda *_: figures",
        "app_module._case_report = imported_fake",
        'mock.patch.object(app_module, "_case_report")',
        'mock.patch.object(app_module, "_case_report", return_value=figures)',
        "app_module._case_report, other = pair",
    ],
)
def test_a_stand_in_that_cannot_be_read_is_reported(install: str) -> None:
    _, (problem,) = _Source(f"def test_x():\n    {install}\n", "planted.py", PAIR).check()
    assert "its shape cannot be read" in problem


def test_a_stand_in_that_is_not_awaitable_is_reported() -> None:
    source = RIGHT.replace("async def _figures", "def _figures")
    _, (problem,) = _Source(source, "planted.py", PAIR).check()
    assert "is not `async def`" in problem


def test_a_change_to_the_real_annotation_makes_the_tree_red() -> None:
    """The guard reads the annotation: it is no copy of today's. A third value in it, and every
    stand-in in the tree disagrees."""
    _, problems = scan(TESTS, "tuple[ReportFigures, bool, int]")
    for known in KNOWN:
        assert any(p.startswith(known) and "not a tuple of 3" in p for p in problems), known
