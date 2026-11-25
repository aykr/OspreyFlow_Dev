"""I6 and I22's source: the GOV.UK tree's state is derived by one function (ADR-152 Amendment 1, decision 1; PL7a1).

`govuk_tree_state` in `scripts/tree_parity.py` returns "complete" when every row of `apps/pages/FUNCTIONS.yaml`
has its GOV.UK route in the GOV.UK tree's route list, less the rows that a line of
`apps/pages/PARITY_EXCEPTIONS.yaml` excuses whole; otherwise "partial". Nothing records the state and nobody
writes it. This file is the state's authority (the ADR's I6 case); the renderer will call the same function.

The route list is `apps/pages/tree-govuk/routes.yaml`, a `routes:` list of paths. The ADR names the list
("`tree-govuk`'s route list, I6's list") but not its file. The tree was created by slice GR2a with one page
(Help, `/help`), so the list exists today; a list that is absent still means partial: a missing list can never
be read as "every row is routed".

Which test fails if the invariant is broken (rule 12):

* a row with no GOV.UK route, and the state still reads complete
      -> `test_a_function_without_its_govuk_route_keeps_the_tree_partial` (the name I22 gives it),
         `test_the_planted_fault_complete_with_a_row_unrouted_is_caught`
* the exceptions file ignored, so an excused row still holds the tree back (or, read the other way, an
  exception that excuses more than its one row)
      -> `test_an_exception_line_removes_exactly_one_row`, `test_the_planted_fault_exceptions_ignored_is_caught`
* a route in the list that belongs to another function, and the row it was meant for counts as routed
      -> `test_a_route_present_for_the_wrong_function_does_not_count`,
         `test_the_planted_fault_any_route_counts_is_caught`
* two rows on one GOV.UK route, so one function's page counts for another and the tree reads complete early
      -> `test_two_rows_on_one_route_are_refused_not_complete`, `test_the_real_rows_share_no_route`,
         `test_the_planted_fault_no_duplicate_route_check_is_caught`
* a part-of-a-function or "scripts off only" line read as a whole-function exception
      -> `test_a_part_or_scripts_off_line_excuses_no_row`
* an absent or empty file read as "complete"
      -> `test_absent_files_are_partial`, `test_the_real_tree_is_partial`
* the real tree reading complete before its pages exist -> `test_the_real_tree_is_partial`
* the no-argument call (the way the renderer will call it) reading the wrong files, which every
  "absent means partial" branch would hide -> `test_the_defaults_point_at_the_real_files`,
  `test_the_no_argument_call_reads_the_default_files`,
  `test_the_planted_fault_a_wrong_default_path_is_caught`

Rule 15: each plant replaces one of the function's own internals (`_row_has_page`, `_required_rows`) so the real
`govuk_tree_state` runs, on the same fixture files the passing cases use, and must be caught by the same
`parity_problems` check that finds nothing in the real function. The fixtures are the real files' own shape
(the real rows and the real exception lines), not a hand-written approximation.

Folders walked: none. The test reads `apps/pages/FUNCTIONS.yaml` and `apps/pages/PARITY_EXCEPTIONS.yaml` by name
and writes the rest under its own `tmp_path`, so its scan-map row is `-`.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from scripts import tree_parity

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
REAL_FUNCTIONS = CORE / "apps" / "pages" / "FUNCTIONS.yaml"
REAL_EXCEPTIONS = CORE / "apps" / "pages" / "PARITY_EXCEPTIONS.yaml"

COMPLETE = "complete"
PARTIAL = "partial"


# --- fixtures ----------------------------------------------------------------------------------------------


def real_rows() -> list[dict[str, Any]]:
    return yaml.safe_load(REAL_FUNCTIONS.read_text(encoding="utf-8"))["functions"]


def real_exceptions() -> list[dict[str, Any]]:
    return yaml.safe_load(REAL_EXCEPTIONS.read_text(encoding="utf-8"))["exceptions"]


def whole_function_ids(exceptions: list[dict[str, Any]]) -> set[str]:
    return {line["id"] for line in exceptions if line["scope"] == "whole function"}


def route_for(row_id: str) -> str:
    return f"/{row_id}"


class Tree:
    """Files under a temporary folder, in the shape the real ones have."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.functions = root / "FUNCTIONS.yaml"
        self.exceptions = root / "PARITY_EXCEPTIONS.yaml"
        self.routes = root / "tree-govuk" / "routes.yaml"

    def write(
        self,
        rows: list[dict[str, Any]],
        exceptions: list[dict[str, Any]] | None,
        routes: list[str] | None,
    ) -> Tree:
        self.functions.write_text(yaml.safe_dump({"functions": rows}), encoding="utf-8")
        if exceptions is not None:
            self.exceptions.write_text(yaml.safe_dump({"exceptions": exceptions}), encoding="utf-8")
        if routes is not None:
            self.routes.parent.mkdir(parents=True, exist_ok=True)
            self.routes.write_text(yaml.safe_dump({"routes": routes}), encoding="utf-8")
        return self

    def state(self) -> str:
        return tree_parity.govuk_tree_state(
            functions=self.functions, exceptions=self.exceptions, route_list=self.routes
        )


def routed(rows: list[dict[str, Any]], exceptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The real rows, each given its own route, except the rows an exception excuses whole (those stay empty)."""
    excused = whole_function_ids(exceptions)
    out = copy.deepcopy(rows)
    for row in out:
        row["route"] = "" if row["id"] in excused else route_for(row["id"])
    return out


def complete_tree(tmp_path: Path) -> tuple[Tree, list[dict[str, Any]], list[dict[str, Any]]]:
    rows, exceptions = real_rows(), real_exceptions()
    rows = routed(rows, exceptions)
    routes = [row["route"] for row in rows if row["route"]]
    return Tree(tmp_path).write(rows, exceptions, routes), rows, exceptions


# --- the check the plants are measured by ------------------------------------------------------------------


def parity_problems(tmp_path: Path) -> list[str]:
    """Every way `govuk_tree_state` disagrees with the rule, on fixtures shaped like the real files. Empty for
    the real function. Each plant below must make it non-empty, by the case it names."""
    problems: list[str] = []
    rows, exceptions = real_rows(), real_exceptions()
    excused = whole_function_ids(exceptions)
    needed = [row for row in rows if row["id"] not in excused]
    all_routes = [route_for(row["id"]) for row in needed]

    def fresh(name: str) -> Tree:
        return Tree(tmp_path / name)

    full = fresh("full").write(routed(rows, exceptions), exceptions, all_routes)
    if full.state() != COMPLETE:
        problems.append("every required row routed, but not complete")

    gap = needed[3]["id"]
    unrouted = [r for r in all_routes if r != route_for(gap)]
    one_missing = fresh("missing").write(routed(rows, exceptions), exceptions, unrouted)
    if one_missing.state() != PARTIAL:
        problems.append("a row's route missing from the list, but not partial")

    # An exception line removes exactly one row from the requirement: the unrouted row is excused whole.
    excuse = {"id": gap, "reason": "fixture", "scope": "whole function", "agreed": "fixture"}
    excused_gap = fresh("excused").write(routed(rows, exceptions), [*exceptions, excuse], unrouted)
    if excused_gap.state() != COMPLETE:
        problems.append("the one unrouted row is excused whole, but not complete")
    other = needed[5]["id"]
    two_gaps = [r for r in unrouted if r != route_for(other)]
    still = fresh("still").write(routed(rows, exceptions), [*exceptions, excuse], two_gaps)
    if still.state() != PARTIAL:
        problems.append("an exception for one row also excused another")

    # The list holds a route that belongs to a function other than the one that lacks its own.
    stray = [*unrouted, route_for(gap) + "/new"]
    wrong = fresh("wrong").write(routed(rows, exceptions), exceptions, stray)
    if wrong.state() != PARTIAL:
        problems.append("a route present for another function made the row count")
    return problems


# --- the cases ---------------------------------------------------------------------------------------------


def test_the_real_tree_is_partial() -> None:
    """Today `FUNCTIONS.yaml` has 49 rows and the GOV.UK tree has three pages, Help (slice GR2a), the Admin People list (slice AD3a) and
    trends shown together (slice GR4a): three routes in the list, and one row with a route, since neither the `admin` function nor the
    `reports-figures` one is complete (their routes stay empty)."""
    assert len(real_rows()) == 49
    assert tree_parity.govuk_tree_state() == PARTIAL
    assert tree_parity.ROUTE_LIST.is_file(), "the GOV.UK tree's route list is gone"
    assert tree_parity._routes(tree_parity.ROUTE_LIST) == ["/help", "/admin/people", "/reports", "/packs/trends"]  # GR3a added the third page, GR4a the fourth
    assert [row["id"] for row in real_rows() if row["route"]] == ["reports-figures", "help"]


def real_defaults_problems() -> list[str]:
    """Where the no-argument call would read, against the real files by name. Empty for the real module."""
    problems: list[str] = []
    for name, real in (("FUNCTIONS", REAL_FUNCTIONS), ("EXCEPTIONS", REAL_EXCEPTIONS)):
        default = getattr(tree_parity, name)
        if default != real or not default.is_file():
            problems.append(f"{name} is not the real {real.name}")
    # The route list belongs to the GOV.UK tree, under the same `apps/pages` folder as the other two.
    if tree_parity.ROUTE_LIST != REAL_FUNCTIONS.parent / "tree-govuk" / "routes.yaml":
        problems.append("ROUTE_LIST is not apps/pages/tree-govuk/routes.yaml")
    return problems


def test_the_defaults_point_at_the_real_files() -> None:
    """The real call is partial whatever it reads (every absent file means partial), so say where it reads."""
    assert real_defaults_problems() == []
    assert len(tree_parity._mappings(tree_parity.FUNCTIONS, "functions") or []) == 49
    assert tree_parity._mappings(tree_parity.EXCEPTIONS, "exceptions"), (
        "the real exception lines did not load"
    )


def test_the_no_argument_call_reads_the_default_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the defaults pointed at a complete fixture tree, `govuk_tree_state()` says complete: it reads them."""
    tree, _, _ = complete_tree(tmp_path)
    assert tree.state() == COMPLETE
    assert tree_parity.govuk_tree_state() == PARTIAL  # the real files, before the patch
    monkeypatch.setattr(tree_parity, "FUNCTIONS", tree.functions)
    monkeypatch.setattr(tree_parity, "EXCEPTIONS", tree.exceptions)
    monkeypatch.setattr(tree_parity, "ROUTE_LIST", tree.routes)
    assert tree_parity.govuk_tree_state() == COMPLETE
    # Each default is read on its own: take the route list away and the same call is partial.
    tree.routes.unlink()
    assert tree_parity.govuk_tree_state() == PARTIAL


def test_the_real_rows_with_no_routes_are_partial_even_with_a_route_list(tmp_path: Path) -> None:
    tree = Tree(tmp_path).write(real_rows(), real_exceptions(), ["/", "/health", "/cases"])
    assert tree.state() == PARTIAL


def test_every_row_routed_and_no_exceptions_is_complete(tmp_path: Path) -> None:
    rows = [
        {"id": "a", "route": "/a", "scenario": "A1"},
        {"id": "b", "route": "/b", "scenario": "A2"},
    ]
    assert Tree(tmp_path).write(rows, [], ["/a", "/b"]).state() == COMPLETE


def test_the_real_rows_all_routed_less_the_real_exceptions_are_complete(tmp_path: Path) -> None:
    tree, _, _ = complete_tree(tmp_path)
    assert tree.state() == COMPLETE


def test_a_function_without_its_govuk_route_keeps_the_tree_partial(tmp_path: Path) -> None:
    rows = [{"id": "a", "route": "/a"}, {"id": "b", "route": "/b"}]
    assert Tree(tmp_path).write(rows, [], ["/a"]).state() == PARTIAL


def test_a_row_with_an_empty_route_is_partial_whatever_the_list_holds(tmp_path: Path) -> None:
    rows = [{"id": "a", "route": ""}, {"id": "b", "route": "/b"}]
    assert Tree(tmp_path).write(rows, [], ["/b", ""]).state() == PARTIAL


def test_an_exception_line_removes_exactly_one_row(tmp_path: Path) -> None:
    rows = [{"id": "a", "route": ""}, {"id": "b", "route": "/b"}, {"id": "c", "route": ""}]
    excuse = [{"id": "a", "reason": "r", "scope": "whole function", "agreed": "x"}]
    one = Tree(tmp_path / "one")
    assert one.write(rows, excuse, ["/b"]).state() == PARTIAL  # c is still required
    both = [*excuse, {"id": "c", "reason": "r", "scope": "whole function", "agreed": "x"}]
    two = Tree(tmp_path / "two")
    assert two.write(rows, both, ["/b"]).state() == COMPLETE


def test_a_part_or_scripts_off_line_excuses_no_row(tmp_path: Path) -> None:
    rows = [{"id": "a", "route": ""}, {"id": "scripts-off-resize", "route": ""}]
    lines = [
        {"id": "a", "reason": "r", "scope": "part of a function", "agreed": "x"},
        {"id": "scripts-off-resize", "reason": "r", "scope": "scripts off only", "agreed": "x"},
    ]
    assert Tree(tmp_path).write(rows, lines, []).state() == PARTIAL


def test_an_exception_naming_no_row_excuses_nothing(tmp_path: Path) -> None:
    rows = [{"id": "a", "route": ""}]
    line = [{"id": "ghost", "reason": "r", "scope": "whole function", "agreed": "x"}]
    assert Tree(tmp_path).write(rows, line, []).state() == PARTIAL


def test_a_route_present_for_the_wrong_function_does_not_count(tmp_path: Path) -> None:
    # b's page exists; a's route is not in the list. A list of the right length, or any non-empty list, is not enough.
    rows = [{"id": "a", "route": "/a"}, {"id": "b", "route": "/b"}]
    assert Tree(tmp_path / "x").write(rows, [], ["/b", "/other"]).state() == PARTIAL
    # A near miss is not a match: a prefix, a longer path, a different case.
    for listed in (["/a/new", "/b"], ["/", "/b"], ["/A", "/b"], ["/b", "/ab"]):
        folder = tmp_path / "".join(c for c in "".join(listed) if c.isalnum() or c == "_")
        assert Tree(folder).write(rows, [], listed).state() == PARTIAL, listed


def test_two_rows_on_one_route_are_refused_not_complete(tmp_path: Path) -> None:
    """Rows a and b both claim /b and the list holds /b: a has no page of its own, yet each row's route is listed."""
    rows = [{"id": "a", "route": "/b"}, {"id": "b", "route": "/b"}, {"id": "c", "route": "/c"}]
    tree = Tree(tmp_path / "dup").write(rows, [], ["/b", "/c"])
    with pytest.raises(ValueError) as refused:
        tree.state()
    # The error names both rows, and the route, so the copy-paste is found without a search.
    for named in ("'a'", "'b'", "'/b'"):
        assert named in str(refused.value), refused.value
    # Refused whatever the rest says: with the list or the exceptions absent it is still an error, not "partial".
    with pytest.raises(ValueError):
        Tree(tmp_path / "dup_noroutes").write(rows, [], None).state()
    # An excused row's route still counts for the check: the copy-paste is the same fault.
    excuse = [{"id": "a", "reason": "r", "scope": "whole function", "agreed": "x"}]
    with pytest.raises(ValueError):
        Tree(tmp_path / "dup_excused").write(rows, excuse, ["/b", "/c"]).state()
    # Empty routes are not routes: many unrouted rows are not duplicates of each other.
    unrouted = [{"id": "a", "route": ""}, {"id": "b", "route": ""}, {"id": "c"}]
    assert Tree(tmp_path / "empties").write(unrouted, [], ["/x"]).state() == PARTIAL


def test_the_real_rows_share_no_route() -> None:
    routes = [row["route"] for row in real_rows() if row.get("route")]
    assert len(routes) == len(set(routes))


def test_absent_files_are_partial(tmp_path: Path) -> None:
    rows = [{"id": "a", "route": "/a"}]
    # The route list is absent (the tree does not exist yet): never complete.
    assert Tree(tmp_path / "no_routes").write(rows, [], None).state() == PARTIAL
    # The exceptions file is absent: no line is agreed, so every row is required.
    absent_exc = Tree(tmp_path / "no_exc").write(rows, None, ["/a"])
    assert absent_exc.state() == COMPLETE
    absent_exc_gap = Tree(tmp_path / "no_exc_gap").write(
        [*rows, {"id": "b", "route": ""}], None, ["/a"]
    )
    assert absent_exc_gap.state() == PARTIAL
    # The function list is absent, or lists nothing: there is nothing to be complete.
    gone = Tree(tmp_path / "gone").write(rows, [], ["/a"])
    gone.functions.unlink()
    assert gone.state() == PARTIAL
    assert Tree(tmp_path / "empty").write([], [], ["/a"]).state() == PARTIAL


@pytest.mark.parametrize("bad", ["routes: not-a-list", "routes: [1, 2]", "- /a", ": : :"])
def test_a_malformed_route_list_is_an_error_not_complete(tmp_path: Path, bad: str) -> None:
    tree = Tree(tmp_path).write([{"id": "a", "route": "/a"}], [], None)
    tree.routes.parent.mkdir(parents=True)
    tree.routes.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError):
        tree.state()


def test_the_function_finds_nothing_wrong_with_itself(tmp_path: Path) -> None:
    assert parity_problems(tmp_path) == []


# --- planted faults, at the function's own call sites (rule 15) -----------------------------------------------


def _plant(monkeypatch: pytest.MonkeyPatch, name: str, replacement: Callable[..., Any]) -> None:
    assert hasattr(tree_parity, name), (
        f"{name} is not an internal of tree_parity: the plant would prove nothing"
    )
    monkeypatch.setattr(tree_parity, name, replacement)


def test_the_planted_fault_complete_with_a_row_unrouted_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant(monkeypatch, "_row_has_page", lambda row, routes: True)
    problems = parity_problems(tmp_path)
    assert "a row's route missing from the list, but not partial" in problems


def test_the_planted_fault_exceptions_ignored_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant(monkeypatch, "_required_rows", lambda rows, exceptions: list(rows))
    problems = parity_problems(tmp_path)
    assert "every required row routed, but not complete" in problems
    assert "the one unrouted row is excused whole, but not complete" in problems


def test_the_planted_fault_an_exception_excusing_every_row_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant(monkeypatch, "_required_rows", lambda rows, exceptions: [] if exceptions else list(rows))
    problems = parity_problems(tmp_path)
    assert "a row's route missing from the list, but not partial" in problems


def test_the_planted_fault_any_route_counts_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant(monkeypatch, "_row_has_page", lambda row, routes: bool(routes))
    problems = parity_problems(tmp_path)
    assert "a route present for another function made the row count" in problems


def test_the_planted_fault_a_prefix_counts_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant(
        monkeypatch,
        "_row_has_page",
        lambda row, routes: any(r.startswith(str(row.get("route") or "\0")) for r in routes),
    )
    problems = parity_problems(tmp_path)
    assert "a route present for another function made the row count" in problems


def test_the_planted_fault_no_duplicate_route_check_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove the check at its call site: the same fixture the refusal case uses now reads complete."""
    rows = [{"id": "a", "route": "/b"}, {"id": "b", "route": "/b"}, {"id": "c", "route": "/c"}]
    tree = Tree(tmp_path).write(rows, [], ["/b", "/c"])
    _plant(monkeypatch, "_check_unique_routes", lambda rows: None)
    assert tree.state() == COMPLETE  # the quiet early "complete" the check exists to stop
    monkeypatch.undo()
    with pytest.raises(ValueError):
        tree.state()


def test_the_planted_fault_a_wrong_default_path_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fault the real-tree case cannot see: a default one folder too high still reads partial."""
    monkeypatch.setattr(tree_parity, "FUNCTIONS", CORE / "apps" / "FUNCTIONS.yaml")
    assert (
        tree_parity.govuk_tree_state() == PARTIAL
    )  # the wrong path is silently "partial": that is the hazard
    assert "FUNCTIONS is not the real FUNCTIONS.yaml" in real_defaults_problems()
    monkeypatch.undo()
    monkeypatch.setattr(tree_parity, "ROUTE_LIST", CORE / "apps" / "tree-govuk" / "routes.yaml")
    assert "ROUTE_LIST is not apps/pages/tree-govuk/routes.yaml" in real_defaults_problems()
