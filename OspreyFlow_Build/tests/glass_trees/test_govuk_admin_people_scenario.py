"""Scenario AP: the Admin People list, a read-only page of the GOV.UK tree (slice AD3a; ADR-152 decisions 1, 4, 5, 6, 7 and 12; the
owner's rulings of 24 November 2026: "AD3 is Admin", a GOV.UK page may exist before its Default twin, a missing scenario is the first
item of the part's brief, and a non-viewer gets 404, the same as a missing thing).

**There is no React-first proof** (decision 12 asks for one only "where one exists"): the React People section
(`apps/workspace/src/admin/sections/People.tsx`) has controls and no scenario in `spec/08`. The scenario is written first, from that
section, the Conduit's own routes and the ADR's text, and the page test (`apps/pages/test/govuk/admin-people.test.ts`) is the proof.

This file holds the document, the page test, the `admin` function row, the route list and the page module in step:

* a scenario with no page test, or a page test with no scenario     -> `test_every_scenario_has_a_page_test_and_back`
* a row whose cited words are not in the file it cites               -> `test_every_row_cites_words_that_are_in_the_source`
* a scenario that does not say what the page shows, who may see it
  and that it works with scripts off                                 -> `test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off`
* the `admin` row left without its scenario ids, given a route while
  the function is incomplete, or `needs-you` touched                 -> `test_the_admin_row_carries_the_scenario_and_no_route`
* a route list that is not the paths the tree has pages for          -> `test_the_route_list_has_both_pages`
* the page module not the `admin` row's, at the path, for the GOV.UK
  tree alone, answering GET alone, or not in the one table of pages -> `test_the_page_module_is_the_admin_rows_at_its_path`
* the old "no scenario" list still holding `admin`                   -> `test_the_known_without_scenario_list_no_longer_holds_admin`

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and plants every fault in an
in-memory copy of what it read; it never writes into the repository. The files, from the repository's root:
`OspreyFlow_Build/spec/{08_ACCEPTANCE_SCENARIOS,03_CONDUIT_MIDDLEWARE,06_DECISIONS}.md`,
`OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py`, and under `OspreyFlow_Core`: `apps/pages/FUNCTIONS.yaml`,
`apps/pages/tree-govuk/routes.yaml`, `apps/pages/test/govuk/admin-people.test.ts`, `apps/pages/test/govuk/keyboard/admin-people.spec.ts`,
`apps/pages/server/{adminPeople,pageList,pages,conduit,app}.ts`, `apps/pages/server/views/adminPeopleWords.ts`,
`packages/schemas/admin.py`, `packages/glass-shared/src/help/roles.ts`, `services/api/app.py`,
`apps/workspace/src/admin/sections/People.tsx`.

Every planted fault is the real inputs with one thing changed (rule 15), run through the same `problems` the real inputs go through,
which finds nothing in them.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

BUILD = Path(__file__).resolve().parents[2]
ROOT = BUILD.parent
CORE = ROOT / "OspreyFlow_Core"
PAGES = CORE / "apps" / "pages"
SPEC = BUILD / "spec"

SPEC_08 = SPEC / "08_ACCEPTANCE_SCENARIOS.md"
FUNCTIONS = PAGES / "FUNCTIONS.yaml"
ROUTES = PAGES / "tree-govuk" / "routes.yaml"
PAGE_TEST = PAGES / "test" / "govuk" / "admin-people.test.ts"
KEYBOARD_TEST = PAGES / "test" / "govuk" / "keyboard" / "admin-people.spec.ts"
PAGE_MODULE = PAGES / "server" / "adminPeople.ts"
PAGE_LIST = PAGES / "server" / "pageList.ts"
KNOWN_LIST = BUILD / "tests" / "glass_trees" / "test_functions_yaml.py"

SECTION = "## Scenario AP"
ID = re.compile(r"^AP\d+$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')(AP\d+): """)
PAGE_TEST_NAME = "admin-people.test.ts"
PATH = "/admin/people"
EXPECTED_IDS = [f"AP{n}" for n in range(1, 12)]
EXPECTED_FUNCTIONS = 49

#: What each behaviour of the page is, by id: a behaviour with no scenario is one nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "a table of the people the Conduit sends: caption, column headers, row headers, in order": ("AP1",),
    "each role in words, never an identifier": ("AP2",),
    "each person's state in words": ("AP3",),
    "an empty list, a failed read, an ended session": ("AP4",),
    "a refusal is the page of a path nothing serves, with none of the Conduit's words": ("AP5",),
    "everything the Conduit sends drawn, nothing chosen by the page, no count": ("AP6",),
    "the Conduit asked as the person, two reads, nothing of the browser's, no write": ("AP7",),
    "structure, no control, no script, the stops in order, by keyboard": ("AP8",),
    "British English, its own words, the Studio's session words": ("AP9",),
    "the GOV.UK tree serves it, the Default tree does not, the lists name it": ("AP10",),
    "each check is red against the real page with one thing changed": ("AP11",),
}

#: The `admin` row's own columns, as they stood before this slice, apart from `scenario`: nothing else of the row moves.
ADMIN_ROW_NAME_STARTS = "Admin: every section in"
ADMIN_ROW_WHERE = "apps/workspace/src/admin/ except needsYou (6,326), plus apps/workspace/src/models/ (458)"


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
        if not line.startswith("| AP"):
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


def inputs() -> dict[str, Any]:
    """Everything `problems` reads, as text or parsed data: a plant changes one entry."""
    return {
        "spec_08": read(SPEC_08),
        "functions": yaml.safe_load(read(FUNCTIONS))["functions"],
        "routes": yaml.safe_load(read(ROUTES))["routes"],
        "page_test": read(PAGE_TEST),
        "page_module": read(PAGE_MODULE),
        "page_list": read(PAGE_LIST),
        "known": read(KNOWN_LIST),
    }


# ---------------------------------------------------------------------------------------------------- the checks


def scenario_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    section = section_of(data["spec_08"])
    if not section:
        return [f"spec/08 has no section headed {SECTION!r}"]
    rows = rows_of(section)
    if not rows:
        return ["the scenario AP section has no table row"]
    for row_id, cells in rows.items():
        if not ID.match(row_id):
            found.append(f"{row_id} is not an id of the form AP<number>")
        behaviour, read_from, page_test, tree = cells
        if not behaviour:
            found.append(f"{row_id} says no behaviour")
        if tree != "GOV.UK":
            found.append(f"{row_id} runs on {tree!r}: the People page is the GOV.UK tree's")
        if not read_from:
            found.append(f"{row_id} says nothing of what it was read from")
        if PAGE_TEST_NAME not in page_test:
            found.append(f"{row_id} names no page test")
    if list(rows) != EXPECTED_IDS:
        found.append(f"the scenario's ids are {list(rows)}, not {EXPECTED_IDS}")
    for behaviour, ids in BRIEF.items():
        for row_id in ids:
            if row_id not in rows:
                found.append(f"the behaviour {behaviour!r} has no scenario {row_id}")
    named_in_tests = set(TITLE.findall(data["page_test"]))
    for row_id in sorted(set(rows) - named_in_tests):
        found.append(f"{row_id} names {PAGE_TEST_NAME} but no case of it is titled {row_id}")
    for row_id in sorted(named_in_tests - set(rows)):
        found.append(f"{PAGE_TEST_NAME} has a case titled {row_id}, which is no scenario")
    return found


def prose_problems(data: dict[str, Any]) -> list[str]:
    """The scenario says, in its own words, what the page shows, who may see it and that it works with scripts off."""
    section = section_of(data["spec_08"])
    found: list[str] = []
    for label, text in (
        ("what the page is", "**What the page is.**"),
        ("who may see it", "**Who may see it.**"),
        ("scripts off", "**Works with scripts off.**"),
        ("the right", "the holders of the right to manage people"),
        ("the refusal", "a 404 with the very same page as a path nothing serves"),
        ("read-only", "read-only"),
        ("the Default tree", "answers `/admin/people` as a path nothing serves"),
        ("the filtering rule", "filters nothing after the answer comes"),
    ):
        if text not in section:
            found.append(f"the scenario does not say {label}: {text!r}")
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


def function_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    rows = {row["id"]: row for row in data["functions"]}
    if len(data["functions"]) != EXPECTED_FUNCTIONS:
        found.append(f"FUNCTIONS.yaml has {len(data['functions'])} rows, not {EXPECTED_FUNCTIONS}")
    admin = rows.get("admin")
    if admin is None:
        return [*found, "the admin row is missing"]
    ids = [item.strip() for item in admin["scenario"].split(",") if item.strip()]
    if ids != EXPECTED_IDS or ids != list(rows_of(section_of(data["spec_08"]))):
        found.append(f"the admin row's scenario is {admin['scenario']!r}, not the section's ids {EXPECTED_IDS}")
    if admin["route"] != "":
        found.append(f"the admin row has the route {admin['route']!r}: the function is not complete, so its route stays empty")
    if admin["status"] != "planned":
        found.append(f"the admin row's status is {admin['status']!r}, not planned")
    if not admin["name"].startswith(ADMIN_ROW_NAME_STARTS) or admin["where"] != ADMIN_ROW_WHERE:
        found.append("the admin row's name or where has moved: only its scenario is this slice's to fill")
    needs = rows.get("needs-you")
    if needs is None or needs["scenario"] != "" or needs["route"] != "":
        found.append("the needs-you row is not as it was: no scenario and no route")
    help_row = rows.get("help")
    if help_row is None or help_row["route"] != "/help":
        found.append("the help row's route is not /help")
    routed = sorted(row["route"] for row in data["functions"] if row.get("route"))
    if routed != ["/help"]:
        found.append(f"the rows that have a route are {routed!r}, not just /help")
    return found


def route_problems(data: dict[str, Any]) -> list[str]:
    if data["routes"] != ["/help", PATH]:
        return [f"the route list is {data['routes']!r}: the tree has two pages, /help and {PATH}"]
    return []


def module_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    text = data["page_module"]
    for label, needle in (
        ("its id", 'id: "admin"'),
        ("its path", f'path: "{PATH}"'),
        ("the GOV.UK tree alone", 'trees: ["govuk"]'),
        ("GET alone", 'methods: ["GET"]'),
    ):
        if needle not in text:
            found.append(f"the page module does not name {label}: {needle!r}")
    if not re.search(r"\badminPeople\b", data["page_list"]):
        found.append("the one table of pages (pageList.ts) does not hold the People page")
    if PATH not in " ".join(data["routes"]):
        found.append(f"the route list does not hold {PATH}")
    return found


def known_list_problems(data: dict[str, Any]) -> list[str]:
    block = re.search(r"KNOWN_WITHOUT_SCENARIO = \{(.*?)\n\}", data["known"], flags=re.S)
    if block is None:
        return ["test_functions_yaml.py has no KNOWN_WITHOUT_SCENARIO list"]
    return ['KNOWN_WITHOUT_SCENARIO still holds "admin": the list may only shrink'] if '"admin"' in block.group(1) else []


# ---------------------------------------------------------------------------------------------------- the real inputs


def test_the_real_inputs_have_no_problem() -> None:
    data = inputs()
    for check in (
        scenario_problems,
        prose_problems,
        citation_problems,
        function_problems,
        route_problems,
        module_problems,
        known_list_problems,
    ):
        assert check(data) == [], check.__name__


def test_every_scenario_has_a_page_test_and_back() -> None:
    assert scenario_problems(inputs()) == []
    assert PAGE_TEST.is_file()
    assert KEYBOARD_TEST.is_file(), "AP8 names keyboard/admin-people.spec.ts, which is not a file"
    section = section_of(read(SPEC_08))
    assert "keyboard/admin-people.spec.ts" in section
    assert "test_govuk_admin_people_scenario.py" in section


def test_every_row_cites_words_that_are_in_the_source() -> None:
    assert citation_problems(inputs()) == []


def test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off() -> None:
    assert prose_problems(inputs()) == []


def test_the_admin_row_carries_the_scenario_and_no_route() -> None:
    assert function_problems(inputs()) == []


def test_the_route_list_has_both_pages() -> None:
    assert route_problems(inputs()) == []


def test_the_page_module_is_the_admin_rows_at_its_path() -> None:
    assert module_problems(inputs()) == []


def test_the_known_without_scenario_list_no_longer_holds_admin() -> None:
    assert known_list_problems(inputs()) == []


# ---------------------------------------------------------------------------------------------------- planted faults (rule 15)


def _without_row(row_id: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        data["spec_08"] = "\n".join(line for line in data["spec_08"].splitlines() if not line.startswith(f"| {row_id} |"))

    return plant


def _replace(key: str, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        assert old in data[key], f"the plant's anchor {old!r} is not in {key}"
        data[key] = data[key].replace(old, new, 1)

    return plant


def _row(row_id: str, **changes: Any) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        next(r for r in data["functions"] if r.get("id") == row_id).update(changes)

    return plant


PLANTS: list[tuple[str, Callable[[dict[str, Any]], None], Callable[[dict[str, Any]], list[str]], str]] = [
    ("a scenario row removed", _without_row("AP5"), scenario_problems, "no scenario AP5"),
    ("a page test case with no scenario row", _without_row("AP11"), scenario_problems, "titled AP11"),
    ("a row run on the other tree", _replace("spec_08", "| GOV.UK |", "| Default |"), scenario_problems, "GOV.UK tree's"),
    (
        "a case retitled so the page test names no AP4",
        _replace("page_test", 'it("AP4: ', 'it("AP44: '),
        scenario_problems,
        "titled AP4",
    ),
    ("the refusal sentence left out", _replace("spec_08", "a 404 with the very same page as a path nothing serves", "a refusal"), prose_problems, "the refusal"),
    ("scripts off left out", _replace("spec_08", "**Works with scripts off.**", "**Works.**"), prose_problems, "scripts off"),
    ("who may see it left out", _replace("spec_08", "**Who may see it.**", "**Who.**"), prose_problems, "who may see it"),
    (
        "words a source does not hold",
        _replace("spec_08", '.tsx` "People and their roles"', '.tsx` "People and their duties"'),
        citation_problems,
        "does not hold",
    ),
    ("the admin row without its scenario", _row("admin", scenario=""), function_problems, "scenario"),
    ("the admin row routed while incomplete", _row("admin", route=PATH), function_problems, "stays empty"),
    ("the admin row's where moved", _row("admin", where="apps/workspace/src/admin/"), function_problems, "has moved"),
    ("the needs-you row given a scenario", _row("needs-you", scenario="AP1"), function_problems, "needs-you"),
    ("the help row unrouted", _row("help", route=""), function_problems, "help row"),
    ("a route in the list the code has no page for", lambda d: d["routes"].append("/welcome"), route_problems, "two pages"),
    ("the People path left out of the list", lambda d: d["routes"].remove(PATH), route_problems, "two pages"),
    ("the page at another path", _replace("page_module", f'path: "{PATH}"', 'path: "/admin/persons"'), module_problems, "its path"),
    ("the page for both trees", _replace("page_module", 'trees: ["govuk"]', 'trees: ["default", "govuk"]'), module_problems, "GOV.UK tree alone"),
    ("the page answering POST", _replace("page_module", 'methods: ["GET"]', 'methods: ["GET", "POST"]'), module_problems, "GET alone"),
    ("the page under another row", _replace("page_module", 'id: "admin"', 'id: "needs-you"'), module_problems, "its id"),
    ("the page left out of the table of pages", _replace("page_list", "adminPeople", "somethingElse"), module_problems, "does not hold the People page"),
    ("admin left in the known list", _replace("known", '"needs-you",', '"needs-you", "admin",'), known_list_problems, "still holds"),
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
