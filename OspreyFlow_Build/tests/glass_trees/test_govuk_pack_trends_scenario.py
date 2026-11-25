"""Scenario TS: trends shown together, a read-only page of the GOV.UK tree (slice GR4a; ADR-152 decisions 5, 6, 7, 10 and 12,
invariant I21; the owner's rulings of 25 November 2026: GR4a's 1(a) to 5, and GR3a's strict reader and field census, carried to
every GOV.UK page).

**There is no React-first proof** (decision 12 asks for one only "where one exists"): the React workspace has no page that shows a
pack's trends together. The scenario is written first, from the pack routes and models, the React pack view's words and the decision
log, and the page test (`apps/pages/test/govuk/pack-trends.test.ts`) is the proof.

This file holds the document, the page test, the `reports-figures` function row, the route list and the page module in step:

* a scenario with no page test, or a page test with no scenario       -> `test_every_scenario_has_a_page_test_and_back`
* a row whose cited words are not in the file it cites                 -> `test_every_row_cites_words_that_are_in_the_source`
* a scenario that does not say what the page shows, who may see it,
  that it reads strictly and that it works with scripts off            -> `test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off`
* a field named as left out that no generated type has                 -> `test_every_field_named_as_left_out_is_a_field_of_the_generated_types`
* the `reports-figures` row left without its scenario ids, given a
  route while the function is incomplete, or its name or where moved   -> `test_the_figures_row_carries_the_scenario_and_no_route`
* a route list that is not the paths the tree has pages for            -> `test_the_route_list_has_the_three_pages`
* the page module not the row's, at the path, for the GOV.UK tree
  alone, answering GET alone, or not in the one table of pages         -> `test_the_page_module_is_the_figures_rows_at_its_path`
* the old "no scenario" list still holding `reports-figures`           -> `test_the_known_without_scenario_list_no_longer_holds_the_row`

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and plants every fault in an
in-memory copy of what it read; it never writes into the repository. The files, from the repository's root:
`OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md` and the files its rows cite,
`OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py`, and under `OspreyFlow_Core`: `apps/pages/FUNCTIONS.yaml`,
`apps/pages/tree-govuk/routes.yaml`, `apps/pages/test/govuk/pack-trends.test.ts`, `apps/pages/test/govuk/keyboard/pack-trends.spec.ts`,
`apps/pages/test/govuk/scripts-off/pack-trends.spec.ts`, `apps/pages/server/{packTrends,pageList}.ts`,
`packages/schemas/generated/{PackDraft,PublishedPack}.ts`.

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
GENERATED = CORE / "packages" / "schemas" / "generated"

SPEC_08 = SPEC / "08_ACCEPTANCE_SCENARIOS.md"
FUNCTIONS = PAGES / "FUNCTIONS.yaml"
ROUTES = PAGES / "tree-govuk" / "routes.yaml"
PAGE_TEST = PAGES / "test" / "govuk" / "pack-trends.test.ts"
KEYBOARD_TEST = PAGES / "test" / "govuk" / "keyboard" / "pack-trends.spec.ts"
SCRIPTS_OFF_TEST = PAGES / "test" / "govuk" / "scripts-off" / "pack-trends.spec.ts"
PAGE_MODULE = PAGES / "server" / "packTrends.ts"
PAGE_LIST = PAGES / "server" / "pageList.ts"
KNOWN_LIST = BUILD / "tests" / "glass_trees" / "test_functions_yaml.py"

SECTION = "## Scenario TS"
ID = re.compile(r"^TS\d+$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')(TS\d+): """)
PAGE_TEST_NAME = "pack-trends.test.ts"
PATH = "/packs/trends"
ROW = "reports-figures"
EXPECTED_IDS = [f"TS{n}" for n in range(1, 16)]
EXPECTED_FUNCTIONS = 49
EXPECTED_ROUTES = ["/help", "/admin/people", PATH]

#: The owner's table of cases for GR4a (`process/lanes/v062/slices/GR4a.md`), by number, and the rows that carry each.
CASES: dict[str, tuple[str, ...]] = {
    "1: three trend items in a stored order other than creation order": ("TS1",),
    "2: a middle item the reader can no longer read (I21)": ("TS2",),
    "3: a pack with no trend items": ("TS3",),
    "4: a reader without the right to read the pack": ("TS4", "TS9"),
    "5: a pack in another case the reader cannot see": ("TS5",),
    "6: no answer, or a 401": ("TS6",),
    "7: a body missing a required field": ("TS7",),
    "8: keyboard": ("TS11",),
    "9: no script": ("TS12",),
    "the field census (the owner's ruling 6)": ("TS8",),
    "planted faults and the fixture's refusals (rule 15)": ("TS15",),
}

#: The interfaces the census walks, and the generated file each is read from.
CENSUS_TYPES = {
    "PackDraft": "PackDraft.ts",
    "ReportPack": "PackDraft.ts",
    "PublishedPack": "PublishedPack.ts",
    "PackItem": "PackDraft.ts",
    "TrendFigures": "PackDraft.ts",
    "TrendDefinitionInput": "PackDraft.ts",
    "TrendResult": "PackDraft.ts",
    "TrendPoint": "PackDraft.ts",
}

#: The `reports-figures` row's own columns, as they stood before this slice, apart from `scenario`.
ROW_NAME = "Reports: Reports and Figures views, trends, packs, published and data feeds"
ROW_WHERE = "apps/workspace/src/reports/ (includes reportsTestKit.ts 145)"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _find_file(name: str) -> Path | None:
    for base in (BUILD, CORE, ROOT):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def section_of(spec_08: str) -> str:
    start = spec_08.find(SECTION)
    if start == -1:
        return ""
    end = spec_08.find("\n## ", start + 1)
    return spec_08[start : end if end != -1 else len(spec_08)]


def rows_of(section: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in section.splitlines():
        if not line.startswith("| TS"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if len(cells) == 5:
            rows[cells[0]] = cells[1:]
    return rows


def cited(cell: str) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for part in cell.split(";"):
        paths = re.findall(r"`([^`]+)`", part)
        words = re.findall(r'"([^"]+)"', part)
        if paths and words:
            out.append((paths[0], words))
    return out


def fields_of(text: str, name: str) -> list[str]:
    found = re.search(rf"export interface {name} \{{\n(.*?)\n\}}", text, flags=re.DOTALL)
    return re.findall(r"^  ([a-z_]+)\??: ", found.group(1), flags=re.MULTILINE) if found else []


def left_out(section: str) -> list[str]:
    sentence = re.search(r"\*\*Left out, by field name\*\*([^\n]*)", section)
    return re.findall(r"`([A-Za-z]+\.[a-z_]+)`", sentence.group(1)) if sentence else []


def inputs() -> dict[str, Any]:
    return {
        "spec_08": read(SPEC_08),
        "functions": yaml.safe_load(read(FUNCTIONS))["functions"],
        "routes": yaml.safe_load(read(ROUTES))["routes"],
        "page_test": read(PAGE_TEST),
        "page_module": read(PAGE_MODULE),
        "page_list": read(PAGE_LIST),
        "known": read(KNOWN_LIST),
        "generated": {name: read(GENERATED / file) for name, file in CENSUS_TYPES.items()},
    }


# ---------------------------------------------------------------------------------------------------- the checks


def scenario_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    section = section_of(data["spec_08"])
    if not section:
        return [f"spec/08 has no section headed {SECTION!r}"]
    rows = rows_of(section)
    if not rows:
        return ["the scenario TS section has no table row"]
    for row_id, cells in rows.items():
        if not ID.match(row_id):
            found.append(f"{row_id} is not an id of the form TS<number>")
        behaviour, read_from, page_test, tree = cells
        if not behaviour:
            found.append(f"{row_id} says no behaviour")
        if tree != "GOV.UK":
            found.append(f"{row_id} runs on {tree!r}: the page is the GOV.UK tree's")
        if not read_from:
            found.append(f"{row_id} says nothing of what it was read from")
        if PAGE_TEST_NAME not in page_test:
            found.append(f"{row_id} names no page test")
    if list(rows) != EXPECTED_IDS:
        found.append(f"the scenario's ids are {list(rows)}, not {EXPECTED_IDS}")
    for case, ids in CASES.items():
        for row_id in ids:
            if row_id not in rows:
                found.append(f"the owner's case {case!r} has no scenario {row_id}")
    named_in_tests = set(TITLE.findall(data["page_test"]))
    for row_id in sorted(set(rows) - named_in_tests):
        found.append(f"{row_id} names {PAGE_TEST_NAME} but no case of it is titled {row_id}")
    for row_id in sorted(named_in_tests - set(rows)):
        found.append(f"{PAGE_TEST_NAME} has a case titled {row_id}, which is no scenario")
    return found


def prose_problems(data: dict[str, Any]) -> list[str]:
    section = section_of(data["spec_08"])
    found: list[str] = []
    for label, text in (
        ("what the page is", "**What the page is.**"),
        ("who may see it", "**Who may see it.**"),
        ("that it reads strictly", "**Reads strictly.**"),
        ("the fields left out", "**Left out, by field name**"),
        ("scripts off", "**Works with scripts off.**"),
        ("the owner's name for it", '"Trends shown together"'),
        ("the pack's snapshots", "the pack's own snapshots"),
        ("the stored order", "in the pack's stored order"),
        ("the refusal", "a 404 with the very same page as a path nothing serves"),
        ("I21", "never draws an empty chart for it"),
        ("read-only", "read-only"),
        ("the drawing board kept apart", "no code, route or word of it reuses the drawing board's names"),
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


def census_problems(data: dict[str, Any]) -> list[str]:
    """Each field the scenario names as left out is a field of a generated type the census walks: a name that drifts is red."""
    named = left_out(section_of(data["spec_08"]))
    if not named:
        return ["the scenario names no field as left out"]
    found: list[str] = []
    for key in named:
        type_name, _, field = key.partition(".")
        text = data["generated"].get(type_name)
        if text is None:
            found.append(f"{key}: {type_name} is not a type the census walks")
        elif field not in fields_of(text, type_name):
            found.append(f"{key}: the generated {type_name} has no field {field}")
    if len(set(named)) != len(named):
        found.append("a field is named as left out twice")
    return found


def function_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    rows = {row["id"]: row for row in data["functions"]}
    if len(data["functions"]) != EXPECTED_FUNCTIONS:
        found.append(f"FUNCTIONS.yaml has {len(data['functions'])} rows, not {EXPECTED_FUNCTIONS}")
    row = rows.get(ROW)
    if row is None:
        return [*found, f"the {ROW} row is missing"]
    ids = [item.strip() for item in row["scenario"].split(",") if item.strip()]
    if ids != EXPECTED_IDS or ids != list(rows_of(section_of(data["spec_08"]))):
        found.append(f"the {ROW} row's scenario is {row['scenario']!r}, not the section's ids {EXPECTED_IDS}")
    if row["route"] != "":
        found.append(f"the {ROW} row has the route {row['route']!r}: the function is not complete, so its route stays empty")
    if row["status"] != "planned":
        found.append(f"the {ROW} row's status is {row['status']!r}, not planned")
    if row["name"] != ROW_NAME or row["where"] != ROW_WHERE:
        found.append(f"the {ROW} row's name or where has moved: only its scenario is this slice's to fill")
    dashboards = rows.get("reports-dashboards")
    if dashboards is None or dashboards["scenario"] != "" or dashboards["route"] != "":
        found.append("the reports-dashboards row is not as it was: no scenario and no route")
    routed = sorted(r["route"] for r in data["functions"] if r.get("route"))
    if routed != ["/help"]:
        found.append(f"the rows that have a route are {routed!r}, not just /help")
    return found


def route_problems(data: dict[str, Any]) -> list[str]:
    if data["routes"] != EXPECTED_ROUTES:
        return [f"the route list is {data['routes']!r}: the tree has three pages, {EXPECTED_ROUTES}"]
    return []


def module_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    text = data["page_module"]
    for label, needle in (
        ("its id", f'id: "{ROW}"'),
        ("its path", f'path: "{PATH}"'),
        ("the GOV.UK tree alone", 'trees: ["govuk"]'),
        ("GET alone", 'methods: ["GET"]'),
    ):
        if needle not in text:
            found.append(f"the page module does not name {label}: {needle!r}")
    if not re.search(r"\bpackTrends\b", data["page_list"]):
        found.append("the one table of pages (pageList.ts) does not hold the page")
    if "board" in PATH or re.search(r"board", text.split("*/", 1)[-1], flags=re.IGNORECASE):
        found.append("the page module says board outside its head comment")
    return found


def known_list_problems(data: dict[str, Any]) -> list[str]:
    block = re.search(r"KNOWN_WITHOUT_SCENARIO = \{(.*?)\n\}", data["known"], flags=re.DOTALL)
    if block is None:
        return ["test_functions_yaml.py has no KNOWN_WITHOUT_SCENARIO list"]
    return [f'KNOWN_WITHOUT_SCENARIO still holds "{ROW}": the list may only shrink'] if f'"{ROW}"' in block.group(1) else []


CHECKS = (
    scenario_problems,
    prose_problems,
    citation_problems,
    census_problems,
    function_problems,
    route_problems,
    module_problems,
    known_list_problems,
)


# ---------------------------------------------------------------------------------------------------- the real inputs


def test_the_real_inputs_have_no_problem() -> None:
    data = inputs()
    for check in CHECKS:
        assert check(data) == [], check.__name__


def test_every_scenario_has_a_page_test_and_back() -> None:
    assert scenario_problems(inputs()) == []
    assert PAGE_TEST.is_file()
    assert KEYBOARD_TEST.is_file(), "TS11 names keyboard/pack-trends.spec.ts, which is not a file"
    assert SCRIPTS_OFF_TEST.is_file(), "TS12 names scripts-off/pack-trends.spec.ts, which is not a file"
    section = section_of(read(SPEC_08))
    for name in ("keyboard/pack-trends.spec.ts", "scripts-off/pack-trends.spec.ts", "test_govuk_pack_trends_scenario.py"):
        assert name in section, name


def test_every_row_cites_words_that_are_in_the_source() -> None:
    assert citation_problems(inputs()) == []


def test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off() -> None:
    assert prose_problems(inputs()) == []


def test_every_field_named_as_left_out_is_a_field_of_the_generated_types() -> None:
    assert census_problems(inputs()) == []


def test_the_figures_row_carries_the_scenario_and_no_route() -> None:
    assert function_problems(inputs()) == []


def test_the_route_list_has_the_three_pages() -> None:
    assert route_problems(inputs()) == []


def test_the_page_module_is_the_figures_rows_at_its_path() -> None:
    assert module_problems(inputs()) == []


def test_the_known_without_scenario_list_no_longer_holds_the_row() -> None:
    assert known_list_problems(inputs()) == []


def test_the_scenario_sits_before_scenario_s() -> None:
    """Scenario S is the last section the Studio words gate reads (AD3a round 5): a scenario after it would be read as the Studio's."""
    spec = read(SPEC_08)
    assert spec.find(SECTION) < spec.find("## Scenario S ")


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


def _replace_all(key: str, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        assert old in data[key], f"the plant's anchor {old!r} is not in {key}"
        data[key] = data[key].replace(old, new)

    return plant


def _tree_of_row(row_id: str, tree: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        lines = data["spec_08"].splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith(f"| {row_id} |"))
        assert lines[index].endswith("| GOV.UK |")
        lines[index] = lines[index][: -len("| GOV.UK |")] + f"| {tree} |"
        data["spec_08"] = "\n".join(lines)

    return plant


def _row(row_id: str, **changes: Any) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        next(r for r in data["functions"] if r.get("id") == row_id).update(changes)

    return plant


def _field_gone(type_name: str, field: str) -> Callable[[dict[str, Any]], None]:
    """The generated type as if the schema had renamed a field the scenario names as left out."""

    def plant(data: dict[str, Any]) -> None:
        text = data["generated"][type_name]
        anchor = f"export interface {type_name} {{\n"
        start = text.index(anchor)
        end = text.index("\n}", start)
        body = text[start:end]
        assert f"\n  {field}" in body
        data["generated"][type_name] = text[:start] + body.replace(f"\n  {field}", f"\n  {field}_renamed") + text[end:]

    return plant


PLANTS: list[tuple[str, Callable[[dict[str, Any]], None], Callable[[dict[str, Any]], list[str]], str]] = [
    ("a scenario row removed", _without_row("TS5"), scenario_problems, "no scenario TS5"),
    ("a page test case with no scenario row", _without_row("TS15"), scenario_problems, "titled TS15"),
    ("a row run on the other tree", _tree_of_row("TS3", "Default"), scenario_problems, "TS3 runs on"),
    ("a case retitled so the page test names no TS4", _replace("page_test", 'it("TS4: ', 'it("TS44: '), scenario_problems, "titled TS4"),
    ("the refusal sentence left out", _replace("spec_08", "a 404 with the very same page as a path nothing serves", "a refusal"), prose_problems, "the refusal"),
    ("the strict reading left out", _replace("spec_08", "**Reads strictly.**", "**Reads.**"), prose_problems, "reads strictly"),
    ("scripts off left out", _replace("spec_08", "**Works with scripts off.**", "**Works.**"), prose_problems, "scripts off"),
    ("I21 left out", _replace("spec_08", "never draws an empty chart for it", "draws it"), prose_problems, "I21"),
    ("the snapshots ruling left out", _replace("spec_08", "the pack's own snapshots", "the trends' live figures"), prose_problems, "snapshots"),
    ("words a source does not hold", _replace("spec_08", '`services/api/packs.py` "ORDER BY position"', '`services/api/packs.py` "ORDER BY title"'), citation_problems, "does not hold"),
    ("a field left out that the type no longer has", _field_gone("PackItem", "added_by"), census_problems, "no field added_by"),
    ("a left-out field of a type the census does not walk", _replace("spec_08", "`ReportPack.id`", "`PackVersionSummary.version`"), census_problems, "not a type the census walks"),
    ("a left-out field named twice", _replace("spec_08", "`ReportPack.investigation_id`", "`ReportPack.id`"), census_problems, "twice"),
    ("the row without its scenario", _row(ROW, scenario=""), function_problems, "scenario"),
    ("the row routed while incomplete", _row(ROW, route=PATH), function_problems, "stays empty"),
    ("the row's where moved", _row(ROW, where="apps/workspace/src/reports/"), function_problems, "has moved"),
    ("the dashboards row given a scenario", _row("reports-dashboards", scenario="TS1"), function_problems, "reports-dashboards"),
    ("a route in the list the code has no page for", lambda d: d["routes"].append("/welcome"), route_problems, "three pages"),
    ("the path left out of the list", lambda d: d["routes"].remove(PATH), route_problems, "three pages"),
    ("the page at another path", _replace("page_module", f'path: "{PATH}"', 'path: "/packs/board"'), module_problems, "its path"),
    ("the page for both trees", _replace("page_module", 'trees: ["govuk"]', 'trees: ["default", "govuk"]'), module_problems, "GOV.UK tree alone"),
    ("the page answering POST", _replace("page_module", 'methods: ["GET"]', 'methods: ["GET", "POST"]'), module_problems, "GET alone"),
    ("the page under another row", _replace("page_module", f'id: "{ROW}"', 'id: "reports-dashboards"'), module_problems, "its id"),
    ("the page left out of the table of pages", _replace_all("page_list", "packTrends", "somethingElse"), module_problems, "does not hold the page"),
    ("the word board in the page's code", _replace("page_module", "export const packTrends", "const boardName = 1;\nexport const packTrends"), module_problems, "says board"),
    ("the row left in the known list", _replace("known", '"reports-dashboards",', f'"reports-dashboards", "{ROW}",'), known_list_problems, "still holds"),
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
