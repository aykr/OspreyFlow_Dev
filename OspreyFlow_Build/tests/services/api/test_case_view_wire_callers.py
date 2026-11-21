"""No test calls `StoredCaseView.wire()` without `chosen=` (C045; rules 12 and 15).

`StoredCaseView.wire(*, chosen)` has no default: the count a reader is sent is the one *they* may
see, never the stored ids' (SE7). The first change of that signature left two tests that need a
live Postgres (`test_case_views_store.py`) calling `wire()` bare, and nothing ran them until
GitHub's `conformance` job did. This is the pure test that would have caught it: it needs no
database, so the Mac's gate runs it.

**What it walks.** Every `*.py` under `OspreyFlow_Build/tests`, at any depth (the live files, the
harness, the scenarios, the conformance suites), parsed with `ast`; nothing else. A file that
does not parse fails the test, so a file is never skipped silently.

**How it tells `StoredCaseView.wire` from another class's `wire`.** By the signature, not the
name of the variable: `StoredCaseView.wire` takes no positional argument, so a call of an
attribute named `wire` with positional arguments (`boards.wire(board, principal)`, which is
`BoardStore.wire`) is another method's and is left alone, and every `.wire(...)` with none must
carry `chosen=`. The one unbound shape, `StoredCaseView.wire(view, ...)`, has `self` as its
positional and is held to the same rule. A `**splat` is not accepted as carrying `chosen`: the
keyword is written out where it can be read.

**Shown red (rule 15).** `test_the_check_fails_with_chosen_removed_from_a_live_call` plants the
fault in a copy of `test_case_views_store.py` at the shape its real call site has (a `.wire(`
on a view read back from the store, `chosen=` taken off) and asserts the finder names it; and
the unbound and splat shapes each have a case.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parents[2]
LIVE_FILE = Path(__file__).with_name("test_case_views_store.py")


def _is_stored_view_wire(call: ast.Call) -> bool:
    """A call of an attribute named `wire` that is, by its arguments, `StoredCaseView.wire`'s."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "wire"):
        return False
    if isinstance(func.value, ast.Name) and func.value.id == "StoredCaseView":
        return len(call.args) <= 1  # the unbound form: `self` is the one positional
    return not call.args


def wire_calls_without_chosen(source: str, name: str) -> list[str]:
    """`name:line` of each `StoredCaseView.wire` call in `source` that does not pass `chosen=`."""
    found = []
    for node in ast.walk(ast.parse(source, filename=name)):
        if not (isinstance(node, ast.Call) and _is_stored_view_wire(node)):
            continue
        if not any(keyword.arg == "chosen" for keyword in node.keywords):
            found.append(f"{name}:{node.lineno}")
    return sorted(found)


def _count_wire_calls(source: str) -> int:
    tree = ast.parse(source)
    return sum(isinstance(n, ast.Call) and _is_stored_view_wire(n) for n in ast.walk(tree))


def test_every_wire_call_in_the_tests_passes_chosen() -> None:
    found: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        found += wire_calls_without_chosen(
            path.read_text(encoding="utf-8"), str(path.relative_to(TESTS.parent))
        )
    assert not found, f"StoredCaseView.wire() called without chosen=: {found}"


def test_the_walk_sees_the_live_files_calls() -> None:
    """Not vacuous: the files that need a live Postgres are in the walk, and their calls are
    found (so a pass is not a scan that read nothing)."""
    assert LIVE_FILE.is_file() and LIVE_FILE.is_relative_to(TESTS)
    assert _count_wire_calls(LIVE_FILE.read_text(encoding="utf-8")) >= 2
    assert len(list(TESTS.rglob("*.py"))) > 100


def test_the_check_fails_with_chosen_removed_from_a_live_call() -> None:
    """Rule 15, at the real call site: a copy of the live store test with `chosen=` taken off one
    call, as the first change of the signature left it."""
    real = LIVE_FILE.read_text(encoding="utf-8")
    assert wire_calls_without_chosen(real, "real") == []
    planted, removed = re.subn(r"\.wire\(chosen=[^)]*\)", ".wire()", real, count=1)
    assert removed == 1, "the live test has no `.wire(chosen=...)` call to plant the fault in"
    assert len(wire_calls_without_chosen(planted, "planted")) == 1
    assert wire_calls_without_chosen(planted, "planted")[0].startswith("planted:")


@pytest.mark.parametrize(
    ("call", "reported"),
    [
        ("held.wire()", True),
        ("held.wire(chosen=2)", False),
        ("held.wire(chosen=None)", False),
        ("StoredCaseView.wire(held)", True),
        ("StoredCaseView.wire(held, chosen=1)", False),
        ("held.wire(**given)", True),
        ("boards.wire(board, principal)", False),
        ("await boards.wire(board, principal)", False),
    ],
)
def test_the_check_reports_each_shape(call: str, reported: bool) -> None:
    source = f"async def t():\n    return {call}\n"
    assert bool(wire_calls_without_chosen(source, "shape")) is reported
