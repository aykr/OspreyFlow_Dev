"""`make authorized-query-check` (`06_DECISIONS.md` ADR-041, accepted option (b)) — a mechanical,
not documentary, control for the fetch-then-check authorization bug class `review.py`,
`sites.py`, `investigations.py`, `studio_recipes.py` and `pattern_store.py` each independently
carried at one point: a `*_authorized` store method that fetches a row unscoped and compares the
owner in Python after, rather than filtering the principal into the query's own `WHERE` clause —
access control lives in the adapter. Documentation named this shape and its fix three times
before this script
existed and it kept recurring; this is the forcing function ADR-041 accepted instead.

Static, not runtime: an AST walk over every `services/api/*.py` file, not a live-database probe.
Flags a *method* (first parameter `self` — a store's own method, not a module-level route
dependency like `app.py`'s `get_authorized_investigation`, which legitimately delegates with no
SQL of its own) whose name contains "authorized" and which takes a `principal` parameter, unless
at least one SQL-issuing call in its own body (`conn.fetch`/`fetchrow`/`fetchval`/`execute`, a
string argument containing "select") also passes a `principal.<attr>` expression as one of that
same call's arguments — the shape every fixed instance now has. A method that delegates to a
different, unscoped method (the exact bug this check exists to catch) has no such call in its own
body and is flagged, by construction, without needing to trace across function boundaries.

Heuristic, not a proof — named here rather than left implicit, the same disclosure
`06_DECISIONS.md` ADR-041 makes at accept time: a `principal.<attr>` argument present in the right
call proves a predicate was *passed*, not that it was *placed correctly* in the `WHERE` clause — a
query could reference it for an unrelated purpose and still pass. ADR-041's own option (a) (a
composition point) would close that gap; this script is the cheaper control that works against the
codebase as it exists today, not the strongest one that would need a query-builder abstraction
this codebase does not have yet.
"""

from __future__ import annotations

import ast
import sys

from tools.layout import REPO as REPO_ROOT
from tools.layout import rel

CHECKED_DIR = REPO_ROOT / "services" / "api"

_QUERY_METHODS = {"fetch", "fetchrow", "fetchval", "execute"}


def _is_principal_attr(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "principal"
    )


def _is_sql_select_call(node: ast.Call) -> bool:
    if not (isinstance(node.func, ast.Attribute) and node.func.attr in _QUERY_METHODS):
        return False
    if not node.args:
        return False
    first = node.args[0]
    return (
        isinstance(first, ast.Constant)
        and isinstance(first.value, str)
        and "select" in first.value.lower()
    )


def _call_has_principal_arg(node: ast.Call) -> bool:
    return any(_is_principal_attr(a) for a in node.args) or any(
        _is_principal_attr(kw.value) for kw in node.keywords
    )


def _is_authorized_store_method(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    if "authorized" not in fn.name.lower():
        return False
    positional = fn.args.args
    if not positional or positional[0].arg != "self":
        return False  # a module-level route dependency (app.py), not a store's own method
    names = {a.arg for a in positional} | {a.arg for a in fn.args.kwonlyargs}
    return "principal" in names


def check_source(path: str, source: str) -> list[str]:
    """Returns one message per `*_authorized` store method whose own body has no SQL SELECT call
    binding a `principal.<attr>` argument."""
    tree = ast.parse(source, filename=path)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        if not _is_authorized_store_method(node):
            continue
        calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
        select_calls = [c for c in calls if _is_sql_select_call(c)]
        if any(_call_has_principal_arg(c) for c in select_calls):
            continue
        violations.append(
            f"{path}:{node.lineno}: {node.name}() is named '*authorized*' and takes a "
            "'principal' parameter, but no SQL SELECT call in its own body binds a "
            "'principal.<attr>' argument — the fetch-then-check shape ADR-041 (06_DECISIONS.md) "
            "exists to stop."
        )
    return violations


def main() -> int:
    files = sorted(CHECKED_DIR.glob("*.py"))
    violations: list[str] = []
    for path in files:
        violations.extend(
            check_source(str(rel(path, REPO_ROOT)), path.read_text())
        )
    for v in violations:
        print(f"authorized-query-check: {v}", file=sys.stderr)
    if violations:
        return 1
    print(f"authorized-query-check: {len(files)} files under services/api, no offenders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
