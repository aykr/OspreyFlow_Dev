"""`apps/pages/FUNCTIONS.yaml` and `apps/pages/PARITY_EXCEPTIONS.yaml` (ADR-152 Amendment 1, slice PL4a).

Amendment 1 says the GOV.UK tree is *complete* when every row of `FUNCTIONS.yaml` has its page, less the
owner-agreed lines of `PARITY_EXCEPTIONS.yaml`. It names no schema; the owner accepted these columns.

  FUNCTIONS.yaml            functions: one row per function, 49 in all (the 46 rows of the front-end
                            inventory, part B, the sign-in page's GOV.UK assets, and the three rows the
                            owner's rulings of 24 November 2026 added by splitting two: `top-bar-home-help`
                            into `top-bar-home` and `help`, and `reports` into `reports-figures` and
                            `reports-dashboards`; slice GR2a)
                            id, name, where, slice, scenario, route, status
  PARITY_EXCEPTIONS.yaml    exceptions: id, reason, scope, agreed

Which test fails if the invariant is broken (rule 12):

* a function dropped from the list (the tree would be "complete" with a function never built)
      -> `test_the_real_files_hold_49_functions` and `test_a_row_removed_is_caught` (an ordinary row, which
         has no exception line, so the count in `check` is the only thing that can find it)
* two rows with one id           -> `test_a_duplicate_id_is_caught`
* an exception that excuses nothing real (a typo, or a function since removed)
      -> `test_an_exception_naming_a_missing_id_is_caught`
* a "scripts off only" line read as a full exception (the tree would drop a function that the scripts-on
  tree still needs)  -> `test_a_scripts_off_line_is_never_read_as_a_full_exception`
* a function given a route with no scenario (decision 12: no page before its scenario)
      -> `test_a_row_with_a_route_has_a_scenario`
* a function with no scenario at all (decision 12) -> flagged by `test_functions_with_no_scenario_are_flagged`,
  which fails when a *new* function arrives with none and warns with the list that remains

Every planted fault is the real file's content with one thing changed (rule 15), run through the same
`check` the real files go through, which finds nothing in the real files.
"""

from __future__ import annotations

import copy
import re
import warnings
from pathlib import Path
from typing import Any

import pytest
import yaml

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
FUNCTIONS = CORE / "apps" / "pages" / "FUNCTIONS.yaml"
EXCEPTIONS = CORE / "apps" / "pages" / "PARITY_EXCEPTIONS.yaml"

FUNCTION_COLUMNS = ("id", "name", "where", "slice", "scenario", "route", "status")
EXCEPTION_COLUMNS = ("id", "reason", "scope", "agreed")

# `status`: a function nobody has built a GOV.UK page for is `planned`; the owner has not yet ruled on a
# line of the frame row and the status bar (`owner to rule`); a function that is wholly a parity exception
# is `parity exception`.
STATUSES = ("planned", "owner to rule", "parity exception")

# `scope`: a whole function the GOV.UK tree leaves out; one named part of a function (the rest stays a
# function); a behaviour that needs scripts, excused for the scripts-off case only.
WHOLE = "whole function"
PART = "part of a function"
SCRIPTS_OFF = "scripts off only"
SCOPES = (WHOLE, PART, SCRIPTS_OFF)

# A scripts-off line names a class of behaviour, not a function: the three the owner agreed on 20 November.
SCRIPTS_OFF_CLASS = ("scripts-off-resize", "scripts-off-reorder", "scripts-off-drawn-canvas")

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EXPECTED_FUNCTIONS = 49

# Functions with no spec/08 scenario today (ADR-152 decision 12: each gets one before its page is built).
# The list may only shrink: a new function with none fails the test. A slice that writes a scenario removes
# the id here and fills the row's `scenario`.
KNOWN_WITHOUT_SCENARIO = {
    "studio-screening-lists",
    "studio-pipeline-canvas",
    "studio-preview",
    "studio-checks",
    "studio-runs-promotions",
    "studio-runs-drawn-merge",
    "studio-runs-external-orchestration",
    "working-set",
    "ask-chat",
    "drawing-boards",
    "matrix-ownership",
    "reports-dashboards",
    "needs-you",
    "top-bar-home",
    "govuk-frame",
    "panel-frames",
    "sign-in-session",
    "signin-govuk-assets",
}


def load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def real_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    return load(FUNCTIONS), load(EXCEPTIONS)


def full_exceptions(exceptions: list[dict[str, str]]) -> set[str]:
    """The function ids the GOV.UK tree is excused from entirely. Only `whole function` counts: a
    `part of a function` line leaves the function in, and a `scripts off only` line excuses a behaviour
    for the scripts-off case, never a function."""
    return {line["id"] for line in exceptions if line.get("scope") == WHOLE}


def without_scenario(functions: list[dict[str, str]], exceptions: list[dict[str, str]]) -> list[str]:
    """Functions needing a page that have no spec/08 scenario (ADR-152 decision 12)."""
    excused = full_exceptions(exceptions)
    return [row["id"] for row in functions if not row.get("scenario") and row["id"] not in excused]


def check(functions_doc: Any, exceptions_doc: Any) -> list[str]:
    """Every problem in the two files, in words. The real files must give none."""
    problems: list[str] = []
    if not isinstance(functions_doc, dict) or not isinstance(functions_doc.get("functions"), list):
        return ["FUNCTIONS.yaml has no `functions:` list"]
    if not isinstance(exceptions_doc, dict) or not isinstance(exceptions_doc.get("exceptions"), list):
        return ["PARITY_EXCEPTIONS.yaml has no `exceptions:` list"]
    functions: list[dict[str, str]] = functions_doc["functions"]
    exceptions: list[dict[str, str]] = exceptions_doc["exceptions"]

    seen: set[str] = set()
    for index, row in enumerate(functions):
        label = f"function row {index + 1}"
        if not isinstance(row, dict):
            problems.append(f"{label} is not a mapping")
            continue
        if tuple(row) != FUNCTION_COLUMNS:
            problems.append(f"{label} ({row.get('id')}) has columns {tuple(row)}, not {FUNCTION_COLUMNS}")
            continue
        if not all(isinstance(row[column], str) for column in FUNCTION_COLUMNS):
            problems.append(f"{label} ({row['id']}) has a value that is not text")
            continue
        if not SLUG.match(row["id"]):
            problems.append(f"{label}: id {row['id']!r} is not a short slug")
        if row["id"] in seen:
            problems.append(f"duplicate function id {row['id']}")
        seen.add(row["id"])
        for column in ("name", "where", "slice", "status"):
            if not row[column].strip():
                problems.append(f"function {row['id']} has an empty {column}")
        if row["status"] not in STATUSES:
            problems.append(f"function {row['id']} has status {row['status']!r}, not one of {STATUSES}")
        if row["route"] and not row["scenario"]:
            problems.append(f"function {row['id']} has a route but no scenario (ADR-152 decision 12)")

    # The tree is "complete" when every row has its page: a row dropped from the list is a function never built.
    if len(functions) != EXPECTED_FUNCTIONS:
        problems.append(f"FUNCTIONS.yaml has {len(functions)} functions, not the {EXPECTED_FUNCTIONS} of the inventory")

    exception_ids: set[str] = set()
    for index, line in enumerate(exceptions):
        label = f"exception row {index + 1}"
        if not isinstance(line, dict) or tuple(line) != EXCEPTION_COLUMNS:
            problems.append(f"{label} does not have exactly the columns {EXCEPTION_COLUMNS}")
            continue
        if not all(isinstance(line[column], str) and line[column].strip() for column in EXCEPTION_COLUMNS):
            problems.append(f"{label} ({line['id']}) has an empty or non-text value")
            continue
        if line["id"] in exception_ids:
            problems.append(f"duplicate exception id {line['id']}")
        exception_ids.add(line["id"])
        if line["scope"] not in SCOPES:
            problems.append(f"exception {line['id']} has scope {line['scope']!r}, not one of {SCOPES}")
        elif line["scope"] == SCRIPTS_OFF:
            if line["id"] not in SCRIPTS_OFF_CLASS:
                problems.append(f"scripts-off exception {line['id']} is not in the class {SCRIPTS_OFF_CLASS}")
        elif line["id"] not in seen:
            problems.append(f"exception {line['id']} names no function in FUNCTIONS.yaml")
    for row in functions:
        if isinstance(row, dict) and row.get("status") == "parity exception" and row["id"] not in full_exceptions(exceptions):
            problems.append(f"function {row['id']} is marked `parity exception` but has no whole-function line")
    for function_id in full_exceptions(exceptions):
        row = next((r for r in functions if r.get("id") == function_id), None)
        if row is not None and row["route"]:
            problems.append(f"function {function_id} is a whole exception and also has a route")
    return problems


def planted() -> tuple[dict[str, Any], dict[str, Any]]:
    functions_doc, exceptions_doc = real_documents()
    return copy.deepcopy(functions_doc), copy.deepcopy(exceptions_doc)


# ---------------------------------------------------------------------------------------------- the real files


def test_the_real_files_have_no_problem() -> None:
    assert check(*real_documents()) == []


def test_the_real_files_hold_49_functions() -> None:
    functions_doc, _ = real_documents()
    rows = functions_doc["functions"]
    assert len(rows) == EXPECTED_FUNCTIONS
    assert all(tuple(row) == FUNCTION_COLUMNS for row in rows)
    assert len({row["id"] for row in rows}) == EXPECTED_FUNCTIONS


def test_the_owners_rulings_of_20_november_are_in_the_files() -> None:
    functions_doc, exceptions_doc = real_documents()
    rows = {row["id"]: row for row in functions_doc["functions"]}
    lines = exceptions_doc["exceptions"]

    # Panel frames (517) and the Studio dataset map (482) are functions with an empty route, not exceptions.
    assert rows["panel-frames"]["route"] == "" and rows["panel-frames"]["slice"] == "PL8"
    assert rows["studio-dataset-map"]["route"] == "" and rows["studio-dataset-map"]["slice"] == "IS3"
    excepted = {line["id"] for line in lines}
    assert "panel-frames" not in excepted and "studio-dataset-map" not in excepted

    # Rows 515 and 516 wait for the owner: functions with an empty route and the status "owner to rule",
    # in neither file as a whole exception.
    for function_id in ("govuk-frame", "status-bar"):
        assert rows[function_id]["status"] == "owner to rule" and rows[function_id]["route"] == ""
        assert function_id not in full_exceptions(lines)

    # Only the light/dark switch, a part of 515, is an exception, and the rest of 515 stays a function.
    switch = [line for line in lines if line["id"] == "govuk-frame"]
    assert [line["scope"] for line in switch] == [PART]
    assert "light/dark" in switch[0]["reason"]

    # The three whole-function exceptions the owner listed (478, 496, 520).
    assert full_exceptions(lines) == {"admin-proposed-types", "studio-api-helpers", "app-shell"}
    for function_id in full_exceptions(lines):
        assert rows[function_id]["status"] == "parity exception"

    # The scripts-off lines: resize, reorder and the drawn canvas, each for scripts off only.
    scripts_off = {line["id"] for line in lines if line["scope"] == SCRIPTS_OFF}
    assert scripts_off == set(SCRIPTS_OFF_CLASS)

    # Every line is the owner's, with who agreed it and why.
    assert all("owner" in line["agreed"].lower() and line["reason"].strip() for line in lines)


def test_functions_with_no_scenario_are_flagged() -> None:
    functions_doc, exceptions_doc = real_documents()
    flagged = without_scenario(functions_doc["functions"], exceptions_doc["exceptions"])
    warnings.warn(
        f"{len(flagged)} functions have no spec/08 scenario (ADR-152 decision 12): {', '.join(flagged)}",
        stacklevel=1,
    )
    new = sorted(set(flagged) - KNOWN_WITHOUT_SCENARIO)
    assert new == [], f"a function with no scenario that this slice did not list: {new}"
    # The three whole-function exceptions have no page to build, so no scenario is asked of them.
    assert not set(flagged) & full_exceptions(exceptions_doc["exceptions"])


def test_the_flag_finds_a_function_without_a_scenario_and_not_one_with() -> None:
    rows = [
        {"id": "a", "scenario": "A1"},
        {"id": "b", "scenario": ""},
        {"id": "c", "scenario": ""},
    ]
    assert without_scenario(rows, [{"id": "c", "scope": WHOLE}]) == ["b"]
    # A line for part of a function, or for scripts off, excuses nothing.
    assert without_scenario(rows, [{"id": "c", "scope": PART}]) == ["b", "c"]
    assert without_scenario(rows, [{"id": "c", "scope": SCRIPTS_OFF}]) == ["b", "c"]


# ---------------------------------------------------------------------------------------------- planted faults


@pytest.mark.parametrize("removed", ["search", "panel-frames"])
def test_a_row_removed_is_caught(removed: str) -> None:
    """An ordinary row, with no exception line to give it away: only the count can catch it (rule 15)."""
    functions_doc, exceptions_doc = planted()
    assert removed not in {line["id"] for line in exceptions_doc["exceptions"]}
    functions_doc["functions"] = [row for row in functions_doc["functions"] if row["id"] != removed]
    assert len(functions_doc["functions"]) == EXPECTED_FUNCTIONS - 1
    problems = check(functions_doc, exceptions_doc)
    assert problems == [f"FUNCTIONS.yaml has {EXPECTED_FUNCTIONS - 1} functions, not the {EXPECTED_FUNCTIONS} of the inventory"]


def test_a_whole_function_row_removed_leaves_its_exception_naming_nothing() -> None:
    functions_doc, exceptions_doc = planted()
    functions_doc["functions"] = [row for row in functions_doc["functions"] if row["id"] != "app-shell"]
    problems = check(functions_doc, exceptions_doc)
    assert any("exception app-shell names no function" in problem for problem in problems)
    assert any("not the 49 of the inventory" in problem for problem in problems)


def test_a_duplicate_id_is_caught() -> None:
    functions_doc, exceptions_doc = planted()
    functions_doc["functions"].append(copy.deepcopy(functions_doc["functions"][3]))
    problems = check(functions_doc, exceptions_doc)
    assert any(problem.startswith("duplicate function id") for problem in problems)


def test_an_exception_naming_a_missing_id_is_caught() -> None:
    functions_doc, exceptions_doc = planted()
    exceptions_doc["exceptions"].append(
        {"id": "no-such-function", "reason": "x", "scope": WHOLE, "agreed": "the owner"}
    )
    problems = check(functions_doc, exceptions_doc)
    assert "exception no-such-function names no function in FUNCTIONS.yaml" in problems


def test_a_scripts_off_line_is_never_read_as_a_full_exception() -> None:
    functions_doc, exceptions_doc = planted()
    # The real scripts-off lines excuse no function ...
    assert full_exceptions(exceptions_doc["exceptions"]).isdisjoint(SCRIPTS_OFF_CLASS)
    # ... and a scripts-off line that names a real function does not make it a full exception either,
    # and is itself a problem (a scripts-off line names a class of behaviour).
    exceptions_doc["exceptions"].append(
        {"id": "graph-canvas", "reason": "x", "scope": SCRIPTS_OFF, "agreed": "the owner"}
    )
    assert "graph-canvas" not in full_exceptions(exceptions_doc["exceptions"])
    assert any("scripts-off exception graph-canvas" in p for p in check(functions_doc, exceptions_doc))
    # And the converse: a whole-function line may not name a scripts-off class.
    functions_doc, exceptions_doc = planted()
    exceptions_doc["exceptions"].append(
        {"id": "scripts-off-resize", "reason": "x", "scope": WHOLE, "agreed": "the owner"}
    )
    assert "exception scripts-off-resize names no function in FUNCTIONS.yaml" in check(functions_doc, exceptions_doc)


def test_a_row_with_a_route_has_a_scenario() -> None:
    functions_doc, exceptions_doc = planted()
    # A function that has no scenario yet (the dataset map had none until slice IS3 wrote its own).
    row = next(r for r in functions_doc["functions"] if r["id"] == "studio-pipeline-canvas")
    assert row["scenario"] == ""
    row["route"] = "/studio/pipeline-canvas"
    assert any("studio-pipeline-canvas has a route but no scenario" in p for p in check(functions_doc, exceptions_doc))
    row["scenario"] = "B13"
    assert check(functions_doc, exceptions_doc) == []


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda row: row.pop("scenario"), "has columns"),
        (lambda row: row.update(status="done"), "has status 'done'"),
        (lambda row: row.update(id="Not A Slug"), "is not a short slug"),
        (lambda row: row.update(where=""), "has an empty where"),
    ],
)
def test_a_malformed_row_is_caught(mutate: Any, expected: str) -> None:
    functions_doc, exceptions_doc = planted()
    mutate(functions_doc["functions"][0])
    assert any(expected in problem for problem in check(functions_doc, exceptions_doc))


def test_a_whole_exception_that_keeps_a_route_is_caught() -> None:
    functions_doc, exceptions_doc = planted()
    row = next(r for r in functions_doc["functions"] if r["id"] == "app-shell")
    row["route"] = "/x"
    row["scenario"] = "A1"
    assert any("is a whole exception and also has a route" in p for p in check(functions_doc, exceptions_doc))
