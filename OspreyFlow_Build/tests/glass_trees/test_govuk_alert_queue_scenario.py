"""Scenario AQ: the alert queue as a read-only page of the GOV.UK tree (slice RM1a; ADR-152 decisions 1, 4, 5, 6, 7 and 12; invariants
I1, I2, I5, I7, I9, I10 and I15; the owner's rulings of 24 November 2026: "RM1 is alerts, rules and watches", a missing scenario is the
first item of a part's brief, a GOV.UK page may exist before its Default twin, no oracle for what a reader may not see).

**Which of B12, B13, B14 and B20 the queue page proves: none.** B12 adds an endpoint to a hotlist, B13 fires an alert on an ingest, B14
opens one alert at its own address and B20 saves a pattern as a monitor: none says what a person who only reads the queue is shown. So the
scenario is new (`spec/08`, "Scenario AQ"), written first, and `apps/pages/test/govuk/alert-queue.test.ts` is the proof; the `alerts-rules-
watches` row of `FUNCTIONS.yaml` names its rows beside B12, B13, B14 and B20.

This file holds the document, the page test, the function row, the route list, the four tests that pin a route, and the page's own
source in step (items 1 and 2 of the slice's brief; the access rules are the vitest file's, and this file holds the source to the one
thing a source can be held to: nothing in it filters, counts or draws what an alert rests on):

* a scenario with no page test, or a page test with no scenario     -> `test_every_scenario_has_a_page_test_and_back`
* a row whose cited words are not in the file it cites               -> `test_every_row_cites_words_that_are_in_the_source`
* the `alerts-rules-watches` row without its route, scenarios or
  slice, or the route list not the tree's two pages                 -> `test_the_function_row_and_the_route_list_are_in_step`
* a route pinned in three of the four places and not the fourth      -> `test_every_place_that_pins_the_routes_names_the_queue`
* a page source that filters or counts rows after the Conduit sent
  them, or names what an alert rests on                              -> `test_the_page_source_filters_nothing_and_draws_no_evidence`

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and plants every fault in an
in-memory copy of what it read; it never writes into the repository. The files, from the repository's root:
`OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md`, `OspreyFlow_Build/tests/glass_trees/{test_tree_parity,test_govuk_help_scenario}.py`,
`OspreyFlow_Build/tests/harness/test_pages_setting.py`, and under `OspreyFlow_Core`: `apps/pages/FUNCTIONS.yaml`,
`apps/pages/tree-govuk/{routes.yaml,alert-queue.njk}`, `apps/pages/test/govuk/{alert-queue.test.ts,help.test.ts}`,
`apps/pages/test/govuk/keyboard/alert-queue.spec.ts`, `apps/pages/server/{alertQueue,pageList,pages}.ts`,
`apps/pages/server/views/alertQueueWords.ts`, `apps/workspace/src/alerts/AlertQueue.tsx`, `services/api/app.py`,
`apps/pages/server/conduit.ts`.

Every planted fault is the real inputs with one thing changed (rule 15), run through the same `problems` the real inputs go through,
which finds nothing in them; a source plant takes the shape the code really has (a `.filter(` over the rows, a `|length` in the template).
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
PAGE_TEST = PAGES / "test" / "govuk" / "alert-queue.test.ts"
KEYBOARD_TEST = PAGES / "test" / "govuk" / "keyboard" / "alert-queue.spec.ts"
TEMPLATE = PAGES / "tree-govuk" / "alert-queue.njk"
PAGE_SOURCES = {
    "server/alertQueue.ts": PAGES / "server" / "alertQueue.ts",
    "server/views/alertQueueWords.ts": PAGES / "server" / "views" / "alertQueueWords.ts",
}
#: The four places that name the tree's routes, and each must name this one (the conductor's note of 25 November 2026).
PINS = {
    "tests/glass_trees/test_tree_parity.py": BUILD / "tests" / "glass_trees" / "test_tree_parity.py",
    "tests/glass_trees/test_govuk_help_scenario.py": BUILD / "tests" / "glass_trees" / "test_govuk_help_scenario.py",
    "tests/harness/test_pages_setting.py": BUILD / "tests" / "harness" / "test_pages_setting.py",
    "apps/pages/test/govuk/help.test.ts": PAGES / "test" / "govuk" / "help.test.ts",
}

SECTION = "## Scenario AQ"
ID = re.compile(r"^AQ\d+$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')(AQ\d+): """)
PAGE_TEST_NAME = "alert-queue.test.ts"
ROUTE = "/alert-queue"
ROW = "alerts-rules-watches"

#: What each behaviour of the page is, by id: a behaviour with no scenario is one nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "the table: caption, scoped headers, a row for each alert the Conduit sent, nothing else of the alert": ("AQ1",),
    "kinds, states and the time said in words, the React queue's words": ("AQ2",),
    "no case: the cases the Conduit sends as links, no queue read": ("AQ3",),
    "empty and unreadable, in words, never a zero": ("AQ4",),
    "a refusal is the words and status of a path nothing serves": ("AQ5",),
    "read as the person, with nothing the browser sent": ("AQ6",),
    "a hidden alert is not named or counted; nothing is filtered after retrieval; no count": ("AQ7",),
    "read-only: GET alone, no form but sign-out, no control that acts": ("AQ8",),
    "scripts off, structure, and the tab order a keyboard follows": ("AQ9",),
    "the route, the tree switch, the page's own words": ("AQ10",),
    "each check is red against the real page with one thing changed": ("AQ11",),
}

#: The calls on a list of rows that would leave some of them out, put them in another order or make a number of them: none belongs in a
#: page that draws what the Conduit sent. (`.map` and `for … of` draw each row once; `.length` is how emptiness is told, and is allowed
#: only in a comparison with 0 or 1, never in a template.)
FILTERING_CALLS = (".filter(", ".slice(", ".splice(", ".sort(", ".reduce(", ".find(", ".flatMap(", ".some(", ".every(")
TEMPLATE_COUNTS = ("|length", "| length", "loop.length", "|count", "| count", "loop.index", "|batch", "|slice", "|first", "|last", "|sort")
#: What an alert rests on: the page draws the alert's own words and five facts, never these.
EVIDENCE_FIELDS = ("referent_node_ids", "citations", "edge_ids", "event_ids", "alert_node_id", "referent_node", "evidence")
SOURCE_FILES = ("server/alertQueue.ts", "server/views/alertQueueWords.ts")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


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
        if not line.startswith("| AQ"):
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
        "functions": yaml.safe_load(read(FUNCTIONS))["functions"],
        "routes": yaml.safe_load(read(ROUTES))["routes"],
        "page_test": read(PAGE_TEST),
        "template": read(TEMPLATE),
        "sources": {name: read(path) for name, path in PAGE_SOURCES.items()},
        "pins": {name: read(path) for name, path in PINS.items()},
        "keyboard_test": read(KEYBOARD_TEST),
    }


# ---------------------------------------------------------------------------------------------------- the checks


def scenario_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    section = section_of(data["spec_08"])
    if not section:
        return [f"spec/08 has no section headed {SECTION!r}"]
    rows = rows_of(section)
    if not rows:
        return ["the scenario AQ section has no table row"]
    for row_id, cells in rows.items():
        if not ID.match(row_id):
            found.append(f"{row_id} is not an id of the form AQ<number>")
        behaviour, read_from, page_test, tree = cells
        if not behaviour:
            found.append(f"{row_id} says no behaviour")
        if tree != "GOV.UK":
            found.append(f"{row_id} runs on {tree!r}: the alert queue page is the GOV.UK tree's")
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
    for text in ("Which of B12, B13, B14 and B20 the queue page proves: none", "read-only", "one case at a time", "not `/alerts`"):
        if text not in section.replace("**", ""):
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


def function_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    rows = {row["id"]: row for row in data["functions"]}
    row = rows.get(ROW)
    if row is None:
        return [f"the row {ROW} is missing"]
    scenario_ids = {item.strip() for item in row["scenario"].split(",") if item.strip()}
    section_ids = set(rows_of(section_of(data["spec_08"])))
    for old in ("B12", "B13", "B14", "B20"):
        if old not in scenario_ids:
            found.append(f"the {ROW} row's scenario has lost {old}: the row keeps its three halves")
    if section_ids and not section_ids <= scenario_ids:
        found.append(f"the {ROW} row's scenario does not name {sorted(section_ids - scenario_ids)}")
    if row["slice"] != "RM1":
        found.append(f"the {ROW} row's slice is {row['slice']!r}, not RM1")
    if row["route"] != ROUTE:
        found.append(f"the {ROW} row's route is {row['route']!r}, not {ROUTE}")
    if "apps/pages/server/alertQueue.ts" not in row["where"]:
        found.append(f"the {ROW} row's `where` does not name the page, apps/pages/server/alertQueue.ts")
    if row["status"] != "planned":
        found.append(f"the {ROW} row's status is {row['status']!r}: the row still has its rules and watches to build")
    routed = {r["id"]: r["route"] for r in data["functions"] if r.get("route")}
    # Help's row (GR2a) and the alert monitoring row (GR3a, `/reports`) carry the other two routes on the line; the Admin People list's does not.
    if routed != {ROW: ROUTE, "help": "/help", "reports-figures": "/reports"}:
        found.append(f"the rows that have a route are {routed!r}, not the queue's, Help's and the alert monitoring page's")
    if len(data["functions"]) != 50:
        found.append(f"FUNCTIONS.yaml has {len(data['functions'])} rows, not 50: this slice adds none")
    return found


def route_problems(data: dict[str, Any]) -> list[str]:
    # The tree's pages on the line: Help (GR2a), the Admin People list (AD3a), the alert monitoring page (GR3a), trends shown together (GR4a) and this one.
    if sorted(data["routes"]) != sorted(["/help", "/admin/people", "/reports", "/packs/trends", ROUTE]):
        return [f"the route list is {data['routes']!r}: the tree has five pages, /help, /admin/people, /reports, /packs/trends and {ROUTE}"]
    return []


def pin_problems(data: dict[str, Any]) -> list[str]:
    return [
        f"{name} does not name {ROUTE}: a route in the tree's list is pinned there"
        for name, text in data["pins"].items()
        if ROUTE not in text
    ]


def source_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for name in SOURCE_FILES:
        text = data["sources"].get(name, "")
        if not text:
            found.append(f"{name} is not a file")
            continue
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("*", "/*", "//")))
        for call in FILTERING_CALLS:
            if call in code:
                found.append(f"{name} calls {call.strip('.(')} on what the Conduit sent: the page filters nothing after retrieval")
        for field in EVIDENCE_FIELDS:
            if re.search(rf"\b{field}\b", code):
                found.append(f"{name} names {field}: the page draws what an alert says, never what it rests on")
    template = data["template"]
    if not template:
        found.append("tree-govuk/alert-queue.njk is not a file")
    code = re.sub(r"\{#.*?#\}", "", template, flags=re.S)
    for count in TEMPLATE_COUNTS:
        if count in code:
            found.append(f"the template uses {count.strip()}: the page states no count of its own")
    for field in EVIDENCE_FIELDS:
        if re.search(rf"\b{field}\b", code):
            found.append(f"the template names {field}")
    if "<form" in code and 'action="/session/sign-out"' not in code:
        found.append("the template has a form that is not the sign-out")
    return found


def keyboard_problems(data: dict[str, Any]) -> list[str]:
    text = data["keyboard_test"]
    if not text:
        return ["test/govuk/keyboard/alert-queue.spec.ts is not a file: rule 13 asks for the tab order in the tree's folder"]
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    found: list[str] = []
    if "tabOrder(page)" not in code:
        found.append("the keyboard case does not read the tab order")
    if re.search(r"\.click\(|page\.mouse", code):
        found.append("the keyboard case uses a pointer")
    return found


CHECKS = (
    scenario_problems,
    citation_problems,
    function_problems,
    route_problems,
    pin_problems,
    source_problems,
    keyboard_problems,
)


# ---------------------------------------------------------------------------------------------------- the real inputs


def test_the_real_inputs_have_no_problem() -> None:
    data = inputs()
    for check in CHECKS:
        assert check(data) == [], check.__name__


def test_every_scenario_has_a_page_test_and_back() -> None:
    assert scenario_problems(inputs()) == []
    assert PAGE_TEST.is_file()
    assert KEYBOARD_TEST.is_file(), "AQ9 names keyboard/alert-queue.spec.ts, which is not a file"
    assert "keyboard/alert-queue.spec.ts" in section_of(read(SPEC_08))


def test_every_row_cites_words_that_are_in_the_source() -> None:
    assert citation_problems(inputs()) == []


def test_the_function_row_and_the_route_list_are_in_step() -> None:
    data = inputs()
    assert function_problems(data) == []
    assert route_problems(data) == []


def test_every_place_that_pins_the_routes_names_the_queue() -> None:
    assert pin_problems(inputs()) == []


def test_the_page_source_filters_nothing_and_draws_no_evidence() -> None:
    assert source_problems(inputs()) == []


def test_the_tab_order_is_proved_in_the_trees_keyboard_folder() -> None:
    assert keyboard_problems(inputs()) == []


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


def _in_section(old: str, new: str) -> Callable[[dict[str, Any]], None]:
    """A change inside the AQ section of spec/08 alone (the first `old` after its heading)."""

    def plant(data: dict[str, Any]) -> None:
        start = data["spec_08"].find(SECTION)
        assert start != -1 and old in data["spec_08"][start:], f"the plant's anchor {old!r} is not in the AQ section"
        data["spec_08"] = data["spec_08"][:start] + data["spec_08"][start:].replace(old, new, 1)

    return plant


def _in(key: str, name: str, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    """A change inside one entry of a dict of texts (`sources` or `pins`)."""

    def plant(data: dict[str, Any]) -> None:
        assert old in data[key][name], f"the plant's anchor {old!r} is not in {name}"
        # Every occurrence: a pin names the route more than once (a docstring, an assertion), and a plant that leaves one is no plant.
        data[key][name] = data[key][name].replace(old, new)

    return plant


def _append(key: str, name: str, extra: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        data[key][name] = data[key][name] + "\n" + extra

    return plant


def _row(row_id: str, **changes: Any) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        next(r for r in data["functions"] if r.get("id") == row_id).update(changes)

    return plant


QUEUE = "server/alertQueue.ts"
WORDS = "server/views/alertQueueWords.ts"

PLANTS: list[tuple[str, Callable[[dict[str, Any]], None], Callable[[dict[str, Any]], list[str]], str]] = [
    ("a scenario row removed", _without_row("AQ7"), scenario_problems, "no scenario AQ7"),
    ("a page test case with no scenario row", _without_row("AQ11"), scenario_problems, "titled AQ11"),
    ("a row run on the other tree", _in_section("| GOV.UK |", "| Default |"), scenario_problems, "GOV.UK tree's"),
    ("the which-scenario answer left out", _replace("spec_08", "the queue page proves: none", "the queue page proves B14"), scenario_problems, "proves: none"),
    ("the one-case-at-a-time sentence left out", _replace("spec_08", "one case at a time", "all cases"), scenario_problems, "one case at a time"),
    ("words a source does not hold", _replace("spec_08", '"Watched pattern"', '"Watched rumour"'), citation_problems, "does not hold"),
    ("the row without its route", _row(ROW, route=""), function_problems, "route"),
    ("the row on the wrong slice", _row(ROW, slice="R7"), function_problems, "RM1"),
    ("the row that lost a scenario of its other halves", _row(ROW, scenario="AQ1, AQ2, AQ3, AQ4, AQ5, AQ6, AQ7, AQ8, AQ9, AQ10, AQ11"), function_problems, "B12"),
    ("the row that does not name the page", _row(ROW, where="apps/workspace/src/alerts/"), function_problems, "does not name the page"),
    ("a row marked built while its halves are not", _row(ROW, status="built"), function_problems, "status"),
    ("a second row given a route", _row("admin", route="/admin"), function_problems, "not the queue's, Help's"),
    ("the route left out of the list", lambda d: d["routes"].remove(ROUTE), route_problems, "five pages"),
    ("a route in the list the code has no page for", lambda d: d["routes"].append("/rules"), route_problems, "five pages"),
    ("the harness test not told", _in("pins", "tests/harness/test_pages_setting.py", ROUTE, "/elsewhere"), pin_problems, "test_pages_setting"),
    ("the tree parity test not told", _in("pins", "tests/glass_trees/test_tree_parity.py", ROUTE, "/elsewhere"), pin_problems, "test_tree_parity"),
    ("the help scenario's route list not told", _in("pins", "tests/glass_trees/test_govuk_help_scenario.py", ROUTE, "/elsewhere"), pin_problems, "test_govuk_help_scenario"),
    ("HP9 not told", _in("pins", "apps/pages/test/govuk/help.test.ts", ROUTE, "/elsewhere"), pin_problems, "help.test.ts"),
    ("rows filtered after retrieval", _append("sources", QUEUE, "const shown = rows.filter((row) => row.state !== 'closed');"), source_problems, "filter"),
    ("rows cut to a page", _append("sources", QUEUE, "const shown = rows.slice(0, 20);"), source_problems, "slice"),
    ("rows sorted by the page", _append("sources", WORDS, "const ordered = rows.sort((a, b) => a.when.localeCompare(b.when));"), source_problems, "sort"),
    ("an alert's evidence named in the words", _append("sources", WORDS, "const cited = alert.citations;"), source_problems, "citations"),
    ("an alert's nodes named in the page", _append("sources", QUEUE, "const nodes = alert.referent_node_ids;"), source_problems, "referent_node_ids"),
    ("a count in the template", _replace("template", "<table", "<p>{{ rows|length }} alerts</p><table"), source_problems, "count of its own"),
    ("a form that is not the sign-out", _replace("template", "<table", '<form method="post" action="/alert-queue/close"><table'), source_problems, "not the sign-out"),
    ("a source that is not there", lambda d: d["sources"].update({QUEUE: ""}), source_problems, "is not a file"),
    ("a keyboard case that uses the pointer", _replace("keyboard_test", "tabOrder", "tabOrder(); await page.getByRole('link').click()"), keyboard_problems, "pointer"),
    ("a keyboard case that does not read the tab order", lambda d: d.update({"keyboard_test": "// nothing"}), keyboard_problems, "tab order"),
]


@pytest.mark.parametrize(("label", "plant", "check", "expected"), PLANTS, ids=[p[0] for p in PLANTS])
def test_the_check_fails_for_each_planted_fault(
    label: str,
    plant: Callable[[dict[str, Any]], None],
    check: Callable[[dict[str, Any]], list[str]],
    expected: str,
) -> None:
    data = inputs()
    assert check(data) == [], f"{label}: the real inputs are not clean for this check"
    plant(data)
    found = check(data)
    assert found, f"{label}: the check found nothing"
    assert any(expected in message for message in found), (label, found)
