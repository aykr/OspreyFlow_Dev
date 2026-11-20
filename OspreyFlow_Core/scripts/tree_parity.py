"""The GOV.UK tree's state, derived and never written (ADR-152 Amendment 1, decision 1; I6).

`govuk_tree_state()` returns:

  "complete"  when every row of `apps/pages/FUNCTIONS.yaml` has its GOV.UK page, less the rows that
              a line of `apps/pages/PARITY_EXCEPTIONS.yaml` excuses whole;
  "partial"   otherwise.

A row has its page when its own `route` is in the GOV.UK tree's route list,
`apps/pages/tree-govuk/routes.yaml` (a `routes:` list of paths). The ADR names the list but not its
file; this path is the one chosen for it. The match is exact: a prefix, a longer path or another
case is a different route, and a route that sits in the list for another function does not give
this row a page.

Only a line whose `scope` is "whole function" excuses a row. A "part of a function" line leaves the
rest of its function required, and a "scripts off only" line names a class of behaviour and is
excused for the scripts-off case alone (`PARITY_EXCEPTIONS.yaml`'s own header says neither is a full
exception).

What an absent file means, and why it can never read as "complete":

  * the route list is absent (the GOV.UK tree does not exist yet): no row has a page, so the state
    is partial;
  * `FUNCTIONS.yaml` is absent or lists no function: there is nothing to be complete, so the state
    is partial;
  * `PARITY_EXCEPTIONS.yaml` is absent: no line has been agreed, so every row is required (the
    stricter reading).

A file that exists but cannot be read as its shape says (not YAML, `routes` not a list of strings, a
row that is not a mapping) raises `ValueError`: a corrupt record is an error to see, never a quiet
"complete" or a quiet "partial".

Nothing records the state: no file, setting or flag holds "complete".
`tests/glass_trees/test_tree_parity.py` is the state's authority. No renderer calls this function
yet: wiring it into the render is a later slice (PL7a2), and when it lands the renderer will call
this same function, not one of its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import yaml

COMPLETE = "complete"
PARTIAL = "partial"

_PAGES = Path(__file__).resolve().parents[1] / "apps" / "pages"
FUNCTIONS = _PAGES / "FUNCTIONS.yaml"
EXCEPTIONS = _PAGES / "PARITY_EXCEPTIONS.yaml"
ROUTE_LIST = _PAGES / "tree-govuk" / "routes.yaml"

WHOLE_FUNCTION = "whole function"


def _load(path: Path, key: str) -> list[Any] | None:
    """The list under `key` in a YAML file, or None when the file is absent."""
    if not path.is_file():
        return None
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise ValueError(f"{path.name} is not readable YAML: {error}") from error
    if document is None:
        return []
    if not isinstance(document, dict) or not isinstance(document.get(key), list):
        raise ValueError(f"{path.name} must hold a `{key}:` list")
    items: list[Any] = document[key]
    return items


def _mappings(path: Path, key: str) -> list[dict[str, Any]] | None:
    items = _load(path, key)
    if items is None:
        return None
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{path.name}: every entry under `{key}` must be a mapping")
    return items


def _routes(path: Path) -> list[str] | None:
    items = _load(path, "routes")
    if items is None:
        return None
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{path.name}: every entry under `routes` must be a string")
    return items


def _required_rows(
    rows: Sequence[dict[str, Any]], exceptions: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The rows the tree must have a page for: all, less those an exception excuses whole."""
    excused = {line.get("id") for line in exceptions if line.get("scope") == WHOLE_FUNCTION}
    return [row for row in rows if row.get("id") not in excused]


def _row_has_page(row: dict[str, Any], routes: Iterable[str]) -> bool:
    """A row has its page when its own route, exactly, is in the tree's route list."""
    route = row.get("route")
    return isinstance(route, str) and route != "" and route in set(routes)


def govuk_tree_state(
    functions: Path | None = None,
    exceptions: Path | None = None,
    route_list: Path | None = None,
) -> str:
    """The state: "complete" or "partial" (see the module's text).

    A path left out is the real file (`FUNCTIONS`, `EXCEPTIONS`, `ROUTE_LIST`), looked up when the
    function is called, so a test can point the no-argument call at a fixture tree.
    """
    functions = FUNCTIONS if functions is None else functions
    exceptions = EXCEPTIONS if exceptions is None else exceptions
    route_list = ROUTE_LIST if route_list is None else route_list
    rows = _mappings(functions, "functions")
    if not rows:
        return PARTIAL
    routes = _routes(route_list)
    if routes is None:
        return PARTIAL
    lines = _mappings(exceptions, "exceptions") or []
    if all(_row_has_page(row, routes) for row in _required_rows(rows, lines)):
        return COMPLETE
    return PARTIAL


if __name__ == "__main__":
    print(govuk_tree_state())
