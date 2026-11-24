"""Scenario HP: the Help page, the first page of the GOV.UK tree (slice GR2a; ADR-152 decisions 6, 7, 12 and 13; the
owner's rulings of 24 November 2026), and the licence register's entry for `govuk-frontend`.

**There is no React-first proof for a GOV.UK page** (decision 12 asks for one only "where one exists"): the React Help page
(`apps/workspace/src/help/RolesHelpPage.tsx`) is a page of words in a workspace panel, with no scenario in `spec/08`. The
scenario is written first, from the React page's content and the ADR text, and the page test
(`apps/pages/test/govuk/help.test.ts`) is the proof. The owner ruled on 24 November 2026 that the first Help slice creates
the GOV.UK tree, its switch, the gates' reach and the route list, that a GOV.UK page may exist before its Default twin, and
that the reports row is split into figures and dashboards and the top bar kept apart from Help.

This file holds the document, the page test, the function rows, the route list and the register in step (items 1 and 6 of the
slice's brief; items 2 to 5 are the vitest file's and the gates' own tests):

* a scenario with no page test, or a page test with no scenario     -> `test_every_scenario_has_a_page_test_and_back`
* a row whose cited words are not in the file it cites               -> `test_every_row_cites_words_that_are_in_the_source`
* `spec/02` silent on the tree, its switch, or the ruling            -> `test_spec_02_says_what_the_tree_and_its_switch_are`
* the `help` row left without its scenarios, route or slice, the top
  bar still holding Help, or `reports` not split                     -> `test_the_function_rows_are_split_as_the_owner_ruled`
* a route list that is not the paths the tree has pages for          -> `test_the_route_list_is_the_one_help_page`
* no register row for `govuk-frontend`, a licence that is not MIT, or
  the identity condition left out of the row or of section 7          -> `test_the_register_has_govuk_frontend_with_its_condition`

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and plants every fault
in an in-memory copy of what it read; it never writes into the repository. The files, from the repository's root:
`OspreyFlow_Build/spec/{08_ACCEPTANCE_SCENARIOS,02_GLASS_FRONTEND,00_ARCHITECTURE}.md`, `OspreyFlow_Build/spec/LICENCE_REGISTER.yaml`,
`OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py`, and under `OspreyFlow_Core`: `apps/pages/FUNCTIONS.yaml`,
`apps/pages/tree-govuk/routes.yaml`, `apps/pages/test/govuk/help.test.ts`, `apps/pages/test/govuk/keyboard/help.spec.ts`,
`apps/pages/test/govuk/scripts-off/help.spec.ts`, `apps/pages/server/views/helpWords.ts`,
`apps/pages/server/{pages,help,pageList,config}.ts`, `packages/glass-shared/src/help/roles.ts`,
`apps/workspace/src/help/RolesHelpPage.tsx`.

Every planted fault is the real inputs with one thing changed (rule 15), run through the same `problems` the real inputs go
through, which finds nothing in them.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from tools import licence_register

BUILD = Path(__file__).resolve().parents[2]
ROOT = BUILD.parent
CORE = ROOT / "OspreyFlow_Core"
PAGES = CORE / "apps" / "pages"
SPEC = BUILD / "spec"

SPEC_08 = SPEC / "08_ACCEPTANCE_SCENARIOS.md"
SPEC_02 = SPEC / "02_GLASS_FRONTEND.md"
SPEC_00 = SPEC / "00_ARCHITECTURE.md"
REGISTER = SPEC / "LICENCE_REGISTER.yaml"
FUNCTIONS = PAGES / "FUNCTIONS.yaml"
ROUTES = PAGES / "tree-govuk" / "routes.yaml"
PAGE_TEST = PAGES / "test" / "govuk" / "help.test.ts"
KEYBOARD_TESTS = {
    "keyboard/help.spec.ts": PAGES / "test" / "govuk" / "keyboard" / "help.spec.ts",
    "scripts-off/help.spec.ts": PAGES / "test" / "govuk" / "scripts-off" / "help.spec.ts",
}

SECTION = "## Scenario HP"
ID = re.compile(r"^HP\d+$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')(HP\d+): """)
PAGE_TEST_NAME = "help.test.ts"

#: What each behaviour of the page and its tree is, by id: a behaviour with no scenario is one nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "the roles, places, levels, teams and rights, in roles.ts's words, none copied": ("HP1",),
    "a heading, a skip link, the landmarks, captioned tables, definition lists, section links": ("HP2",),
    "the session and no right: unsigned goes to sign-in, anyone signed in sees it": ("HP3",),
    "no Conduit call, no write: GET only, no form but sign-out": ("HP4",),
    "complete with scripts off, and the tab order a keyboard follows": ("HP5",),
    "the page's own words are British English and its own; roles.ts's are not copied": ("HP6",),
    "the tree switch: govuk serves the page and its Home; default and unset do not; others refused": ("HP7",),
    "a route a tree has no page for answers as it does today": ("HP8",),
    "the route list is the paths the tree has pages for": ("HP9",),
    "each check is red against the real page with one thing changed": ("HP10",),
}

SPLIT_ROWS = {
    "top-bar-home": "Top bar, context banner, Home, Welcome",
    "help": "Help: the roles, teams and Authors, and what each right lets a person do",
    "reports-figures": "Reports: Reports and Figures views, trends, packs, published and data feeds",
    "reports-dashboards": "Reports: embedded dashboards and the alert monitoring board",
}
EXPECTED_FUNCTIONS = 49


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _find_file(name: str) -> Path | None:
    for base in (BUILD, CORE, ROOT):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------------------------------- reading the scenario


def section_of(spec_08: str) -> str:
    start = spec_08.find(SECTION)
    if start == -1:
        return ""
    end = spec_08.find("\n## ", start + 1)
    return spec_08[start : end if end != -1 else len(spec_08)]


def rows_of(section: str) -> dict[str, list[str]]:
    """`{id: [behaviour, read-from, page test, tree]}` for each table row of the section."""
    rows: dict[str, list[str]] = {}
    for line in section.splitlines():
        if not line.startswith("| HP"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if len(cells) == 5:
            rows[cells[0]] = cells[1:]
    return rows


def cited(cell: str) -> list[tuple[str, list[str]]]:
    """Each `path` of a read-from cell with the quoted words that go with it (the parts are split at `;`)."""
    out: list[tuple[str, list[str]]] = []
    for part in cell.split(";"):
        paths = re.findall(r"`([^`]+)`", part)
        words = re.findall(r'"([^"]+)"', part)
        if paths and words:
            out.append((paths[0], words))
    return out


def page_test_ids(text: str) -> set[str]:
    return set(TITLE.findall(text))


def inputs() -> dict[str, Any]:
    """Everything `problems` reads, as text or parsed data: a plant changes one entry."""
    return {
        "spec_08": read(SPEC_08),
        "spec_02": read(SPEC_02),
        "spec_00": read(SPEC_00),
        "register": yaml.safe_load(read(REGISTER))["rows"],
        "functions": yaml.safe_load(read(FUNCTIONS))["functions"],
        "routes": yaml.safe_load(read(ROUTES))["routes"],
        "page_test": read(PAGE_TEST),
    }


# ---------------------------------------------------------------------------------------------------- the checks


def scenario_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    section = section_of(data["spec_08"])
    if not section:
        return [f"spec/08 has no section headed {SECTION!r}"]
    rows = rows_of(section)
    if not rows:
        return ["the scenario HP section has no table row"]
    for row_id, cells in rows.items():
        if not ID.match(row_id):
            found.append(f"{row_id} is not an id of the form HP<number>")
        behaviour, read_from, page_test, tree = cells
        if not behaviour:
            found.append(f"{row_id} says no behaviour")
        if tree != "GOV.UK":
            found.append(f"{row_id} runs on {tree!r}: the Help page is the GOV.UK tree's")
        if not read_from:
            found.append(f"{row_id} says nothing of what it was read from")
        if PAGE_TEST_NAME not in page_test and "spec.ts" not in page_test and ".py" not in page_test:
            found.append(f"{row_id} names no page test")
    for behaviour, ids in BRIEF.items():
        for row_id in ids:
            if row_id not in rows:
                found.append(f"the behaviour {behaviour!r} has no scenario {row_id}")
    named_in_tests = page_test_ids(data["page_test"])
    page_rows = {row_id for row_id, cells in rows.items() if PAGE_TEST_NAME in cells[2]}
    for row_id in sorted(page_rows - named_in_tests):
        found.append(f"{row_id} names {PAGE_TEST_NAME} but no case of it is titled {row_id}")
    for row_id in sorted(named_in_tests - set(rows)):
        found.append(f"{PAGE_TEST_NAME} has a case titled {row_id}, which is no scenario")
    for text in ("needs no sign-in beyond the session", "scripts off"):
        if text not in section:
            found.append(f"the scenario's own text does not say {text!r}")
    return found


def citation_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for row_id, cells in rows_of(section_of(data["spec_08"])).items():
        for path, words in cited(cells[1]):
            source = _find_file(path)
            if source is None:
                found.append(f"{row_id} cites {path}, which is not a file")
                continue
            text = read(source)
            found += [f"{row_id}: {path} does not hold {word!r}" for word in words if word not in text]
    return found


def spec_02_problems(data: dict[str, Any]) -> list[str]:
    match = re.search(r"^### 2\.0e .*$", data["spec_02"], flags=re.M)
    if not match:
        return ["spec/02 has no section 2.0e on the GOV.UK tree"]
    rest = data["spec_02"][match.end() :]
    end = re.search(r"^#{2,3} ", rest, flags=re.M)
    body = rest[: end.start() if end else len(rest)]
    found: list[str] = []
    for text in (
        "OSPREY_PAGES_TREE",
        "`default`",
        "`govuk`",
        "tree-govuk",
        "before its Default twin",
        "24 November 2026",
        "no new Home path",
        "routes.yaml",
    ):
        if text not in body:
            found.append(f"spec/02 section 2.0e does not say {text!r}")
    return found


def function_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    rows = {row["id"]: row for row in data["functions"]}
    if len(data["functions"]) != EXPECTED_FUNCTIONS:
        found.append(f"FUNCTIONS.yaml has {len(data['functions'])} rows, not {EXPECTED_FUNCTIONS}")
    for gone in ("top-bar-home-help", "reports"):
        if gone in rows:
            found.append(f"the row {gone} is still there: the owner ruled it split")
    for row_id, name in SPLIT_ROWS.items():
        if row_id not in rows:
            found.append(f"the row {row_id} is missing")
        elif rows[row_id]["name"] != name:
            found.append(f"the row {row_id} is named {rows[row_id]['name']!r}, not {name!r}")
    help_row = rows.get("help")
    if help_row:
        scenario_ids = {item.strip() for item in help_row["scenario"].split(",") if item.strip()}
        if not scenario_ids or not all(ID.match(item) for item in scenario_ids):
            found.append(f"the help row's scenario is {help_row['scenario']!r}, not HP ids")
        elif scenario_ids != set(rows_of(section_of(data["spec_08"]))):
            found.append("the help row's scenario ids are not the section's rows")
        if help_row["slice"] != "GR2a":
            found.append(f"the help row's slice is {help_row['slice']!r}, not GR2a")
        if help_row["route"] != "/help":
            found.append(f"the help row's route is {help_row['route']!r}, not /help")
        if "help/" in rows.get("top-bar-home", {}).get("where", ""):
            found.append("the top bar row still holds the help folder")
    if rows.get("top-bar-home", {}).get("slice", "").split(" ")[0] != "R1":
        found.append("the top bar stays R1 (the owner, 24 November 2026)")
    if rows.get("reports-figures", {}).get("slice") != "GR3":
        found.append("the figures row's slice is not GR3")
    dashboards = rows.get("reports-dashboards", {})
    if dashboards.get("slice") != "none named" or dashboards.get("route") or dashboards.get("scenario"):
        found.append("the dashboards row must be later: slice 'none named', no route, no scenario")
    return found


def route_problems(data: dict[str, Any]) -> list[str]:
    routed = sorted(row["route"] for row in data["functions"] if row.get("route"))
    if data["routes"] != ["/help"]:
        return [f"the route list is {data['routes']!r}: the tree has one page, /help"]
    if routed != ["/help"]:
        return [f"the rows that have a route are {routed!r}, not just /help"]
    return []


def register_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    rows = [row for row in data["register"] if row.get("name") == "govuk-frontend"]
    if len(rows) != 1:
        return [f"the register has {len(rows)} rows named govuk-frontend, not one"]
    row = rows[0]
    if row.get("licence") != "MIT":
        found.append(f"govuk-frontend's licence is {row.get('licence')!r}, not MIT")
    if row.get("test") != "osi-software":
        found.append("govuk-frontend passes by osi-software")
    condition = " ".join(str(row.get(key, "")) for key in ("note", "ships")).lower()
    for text in ("crown", "logotype", "gds transport", "identity switch", "gov.uk addresses"):
        if text not in condition:
            found.append(f"the govuk-frontend row does not say {text!r}")
    found += [
        message
        for message in licence_register.find_register_violations([row], [])
        if "govuk-frontend" in message and "names something no code names" not in message
    ]
    start = data["spec_00"].find("## 7. Licence register")
    end = data["spec_00"].find("\n## 8.", start)
    section = data["spec_00"][start:end]
    table_row = re.search(r"^\| `govuk-frontend` \|.*$", section, flags=re.M)
    if not table_row:
        found.append("section 7 has no table row for govuk-frontend")
    else:
        text = table_row.group(0).lower()
        for needle in ("mit", "crown", "logotype", "gds transport", "identity switch", "gov.uk addresses"):
            if needle not in text:
                found.append(f"section 7's govuk-frontend row does not say {needle!r}")
    return found


# ---------------------------------------------------------------------------------------------------- the real inputs


def test_the_real_inputs_have_no_problem() -> None:
    data = inputs()
    for check in (scenario_problems, citation_problems, spec_02_problems, function_problems, route_problems, register_problems):
        assert check(data) == [], check.__name__


def test_every_scenario_has_a_page_test_and_back() -> None:
    assert scenario_problems(inputs()) == []
    assert PAGE_TEST.is_file()
    for name, path in KEYBOARD_TESTS.items():
        assert path.is_file(), f"HP5 names {name}, which is not a file"
    section = section_of(read(SPEC_08))
    for name in KEYBOARD_TESTS:
        assert name in section, f"no row of the scenario names {name}"


def test_every_row_cites_words_that_are_in_the_source() -> None:
    assert citation_problems(inputs()) == []


def test_spec_02_says_what_the_tree_and_its_switch_are() -> None:
    assert spec_02_problems(inputs()) == []


def test_the_function_rows_are_split_as_the_owner_ruled() -> None:
    assert function_problems(inputs()) == []


def test_the_route_list_is_the_one_help_page() -> None:
    assert route_problems(inputs()) == []


def test_the_register_has_govuk_frontend_with_its_condition() -> None:
    assert register_problems(inputs()) == []


# ---------------------------------------------------------------------------------------------------- planted faults (rule 15)


def _without_row(row_id: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        data["spec_08"] = "\n".join(
            line for line in data["spec_08"].splitlines() if not line.startswith(f"| {row_id} |")
        )

    return plant


def _replace(key: str, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        assert old in data[key], f"the plant's anchor {old!r} is not in {key}"
        data[key] = data[key].replace(old, new, 1)

    return plant


def _row(rows_key: str, row_id: str, **changes: Any) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        row = next(r for r in data[rows_key] if r.get("id") == row_id)
        row.update(changes)

    return plant


def _register_row(**changes: Any) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        next(r for r in data["register"] if r.get("name") == "govuk-frontend").update(changes)

    return plant


def _drop(key: str, row_id: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        data[key] = [r for r in data[key] if r.get("id") != row_id and r.get("name") != row_id]

    return plant


PLANTS: list[tuple[str, Callable[[dict[str, Any]], None], Callable[[dict[str, Any]], list[str]], str]] = [
    ("a scenario row removed", _without_row("HP4"), scenario_problems, "no scenario HP4"),
    ("a page test case with no scenario row", _without_row("HP9"), scenario_problems, "titled HP9"),
    ("a row run on the other tree", _replace("spec_08", "| GOV.UK |", "| Default |"), scenario_problems, "GOV.UK tree's"),
    ("the session sentence left out", _replace("spec_08", "needs no sign-in beyond the session", "needs a session"), scenario_problems, "beyond the session"),
    ("words a source does not hold", _replace("spec_08", "Roles, teams and Authors", "Roles, teams and Writers"), citation_problems, "does not hold"),
    ("the switch left out of spec/02", _replace("spec_02", "OSPREY_PAGES_TREE", "THE_TREE_SETTING"), spec_02_problems, "OSPREY_PAGES_TREE"),
    ("the ruling left out of spec/02", _replace("spec_02", "before its Default twin", "later"), spec_02_problems, "Default twin"),
    ("the help row without its route", _row("functions", "help", route=""), function_problems, "route"),
    ("the help row with no scenario", _row("functions", "help", scenario=""), function_problems, "scenario"),
    ("the help row on the wrong slice", _row("functions", "help", slice="R7"), function_problems, "GR2a"),
    ("the old combined top bar row back", _row("functions", "top-bar-home", id="top-bar-home-help"), function_problems, "owner ruled it split"),
    ("reports not split", _row("functions", "reports-figures", id="reports"), function_problems, "owner ruled it split"),
    ("the dashboards row given a slice", _row("functions", "reports-dashboards", slice="GR3"), function_problems, "must be later"),
    ("a route in the list the code has no page for", lambda d: d["routes"].append("/welcome"), route_problems, "one page"),
    ("a row routed with the list left short", _row("functions", "top-bar-home", route="/"), route_problems, "not just /help"),
    ("no register row", _drop("register", "govuk-frontend"), register_problems, "not one"),
    ("a licence that is not MIT", _register_row(licence="GPL-3.0-only"), register_problems, "not MIT"),
    ("the identity condition left out of the row", _register_row(note="A package.", ships="Not shipped."), register_problems, "does not say"),
    ("the section 7 row missing", _replace("spec_00", "| `govuk-frontend` |", "| `govuk-frontend-x` |"), register_problems, "no table row"),
]


@pytest.mark.parametrize(("label", "plant", "check", "expected"), PLANTS, ids=[p[0] for p in PLANTS])
def test_the_check_fails_for_each_planted_fault(
    label: str,
    plant: Callable[[dict[str, Any]], None],
    check: Callable[[dict[str, Any]], list[str]],
    expected: str,
) -> None:
    data = inputs()
    assert check(data) == []
    plant(data)
    found = check(data)
    assert found, f"{label}: the check found nothing"
    assert any(expected in message for message in found), (label, found)
