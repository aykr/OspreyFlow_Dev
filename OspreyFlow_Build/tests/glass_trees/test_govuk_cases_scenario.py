"""Scenario CS: the reader's cases and one case's page with its brief, read-only, on the GOV.UK tree (slice GR1a; ADR-152 decisions 1,
4, 5, 6, 7 and 12; the owner's rulings of 25 November 2026 on GR1a's draft: every proposal (a), and GR1a started before GG2b).

**There is no React-first proof** (decision 12 asks for one only "where one exists"): the React case list and brief are a menu and an
editor, and none of the `cases-and-views` row's journeys (A7, B14, B21) is about them. The scenario is written first, from those
screens, the Conduit's own routes and the ADR's text, and the page test (`apps/pages/test/govuk/cases.test.ts`) is the proof.

This file holds the document, the page test, the `cases-and-views` row, the route list, the page module and the field census in step:

* a scenario with no page test, or a page test with no scenario     -> `test_every_scenario_has_a_page_test_and_back`
* a row whose cited words are not in the file it cites               -> `test_every_row_cites_words_that_are_in_the_source`
* a scenario that does not say what the page shows, who may see it,
  that it works with scripts off, or what it leaves out             -> `test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off`
* the row without its scenario ids or its journeys, given a route
  while the function is incomplete                                   -> `test_the_cases_row_carries_the_scenario_and_no_route`
* a route list that is not the paths the tree has pages for          -> `test_the_route_list_has_the_three_pages`
* the page module not the row's, at the path, for the GOV.UK tree
  alone, answering GET alone, or not in the one table of pages       -> `test_the_page_module_is_the_cases_rows_at_its_path`
* a field of the route's models neither drawn by the page nor named
  as left out, a name for no field, or the page's required list not
  the fields the route sends                                         -> `test_the_field_census_is_the_models_fields`

The models are read from their source by `ast` (the classes' annotated fields, and `exclude=True` for a field never on the wire), so a
field added to a route's model fails this test until the page draws it or the scenario names it as left out.

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and plants every fault in an
in-memory copy of what it read; it never writes into the repository. The files, from the repository's root:
`OspreyFlow_Build/spec/{08_ACCEPTANCE_SCENARIOS,03_CONDUIT_MIDDLEWARE,06_DECISIONS}.md`, and under `OspreyFlow_Core`:
`apps/pages/FUNCTIONS.yaml`, `apps/pages/tree-govuk/routes.yaml`, `apps/pages/test/govuk/cases.test.ts`,
`apps/pages/test/govuk/keyboard/cases.spec.ts`, `apps/pages/test/govuk/scripts-off/cases.spec.ts`,
`apps/pages/server/{cases,pageList,pages,conduit}.ts`, `apps/pages/server/views/{casesWords,notFoundWords}.ts`,
`services/api/{app,investigations,case_brief}.py`, `packages/glass-shared/src/investigation/cases.ts`,
`packages/glass-shared/src/help/roles.ts`, `apps/workspace/src/investigation/CaseBrief.tsx`.

Every planted fault is the real inputs with one thing changed (rule 15), run through the same `problems` the real inputs go through,
which finds nothing in them.
"""

from __future__ import annotations

import ast
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
PAGE_TEST = PAGES / "test" / "govuk" / "cases.test.ts"
KEYBOARD_TEST = PAGES / "test" / "govuk" / "keyboard" / "cases.spec.ts"
SCRIPTS_OFF_TEST = PAGES / "test" / "govuk" / "scripts-off" / "cases.spec.ts"
PAGE_MODULE = PAGES / "server" / "cases.ts"
WORDS = PAGES / "server" / "views" / "casesWords.ts"
PAGE_LIST = PAGES / "server" / "pageList.ts"
APP = CORE / "services" / "api" / "app.py"
INVESTIGATIONS = CORE / "services" / "api" / "investigations.py"
CASE_BRIEF = CORE / "services" / "api" / "case_brief.py"
DOMAIN = CORE / "packages" / "schemas" / "domain.py"

#: Each closed field's allowed values: the page's list (in `casesWords.ts`) and where the model's own are defined (an enum's members'
#: values, or a `Literal` alias), so a value added to a model fails here and never reaches a reader's page as "could not be read".
VALUES: dict[str, tuple[str, Path, str]] = {
    "LEVELS": ("AccessLevel", INVESTIGATIONS, "enum"),
    "PACKS": ("DomainPack", DOMAIN, "literal"),
    "STATUSES": ("RequirementStatus", CASE_BRIEF, "literal"),
    "KINDS": ("AttachmentKind", CASE_BRIEF, "literal"),
}

SECTION = "## Scenario CS"
ID = re.compile(r"^CS\d+$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')(CS\d+): """)
PAGE_TEST_NAME = "cases.test.ts"
PATH = "/cases"
EXPECTED_IDS = [f"CS{n}" for n in range(1, 16)]
JOURNEYS = ["A7", "B14", "B21"]
ROW = "cases-and-views"
ROW_NAME = "Cases, case brief, saved views, history (also access, settings, datasets, domains, new case)"
ROW_WHERE = "apps/workspace/src/investigation/, apps/workspace/src/views/, apps/workspace/src/history/"

#: Each model the page reads, and the file it is defined in.
MODELS: dict[str, Path] = {
    "InvestigationListing": APP,
    "Investigation": INVESTIGATIONS,
    "CaseBrief": CASE_BRIEF,
    "BriefRequirement": CASE_BRIEF,
    "BriefAttachment": CASE_BRIEF,
}

#: What each behaviour of the page is, by id: a behaviour with no scenario is one nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "the list as a table in the Conduit's order, each name a link": ("CS1",),
    "no case: a sentence, never an empty table": ("CS2",),
    "a closed tab listed, in the reader's own words": ("CS3",),
    "one case's page: its facts and its brief, attachments by kind": ("CS4",),
    "an empty brief said in words": ("CS5",),
    "no level, other unit, no such case: one 404": ("CS6",),
    "the brief's 403: the same 404": ("CS7",),
    "one read of the case per render, as the person, no write": ("CS8",),
    "a failed read, an ended session": ("CS9",),
    "the strict reader": ("CS10",),
    "the field census": ("CS11",),
    "structure and keyboard": ("CS12",),
    "scripts off": ("CS13",),
    "the trees, the lists and the words": ("CS14",),
    "each check red against the real page with one thing changed": ("CS15",),
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _find_file(name: str) -> Path | None:
    for base in (BUILD, CORE, ROOT):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------------------------------- reading the inputs


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
        if not line.startswith("| CS"):
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


def model_fields(source: str, name: str) -> tuple[list[str], set[str]] | None:
    """The annotated fields of the class `name` in `source`, in order, and those marked `exclude=True` (never on the wire)."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == name:
            fields: list[str] = []
            excluded: set[str] = set()
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == "model_config":
                        continue
                    fields.append(item.target.id)
                    value = item.value
                    if isinstance(value, ast.Call) and any(
                        k.arg == "exclude" and isinstance(k.value, ast.Constant) and k.value.value is True
                        for k in value.keywords
                    ):
                        excluded.add(item.target.id)
            return fields, excluded
    return None


CENSUS_LINE = re.compile(r"^\s*(\w+): \{ drawn: \[([^\]]*)\], left: \[([^\]]*)\] \},?$", re.MULTILINE)
NOT_SENT = re.compile(r"export const NOT_SENT[^=]*= \[([^\]]*)\]")


def names(listed: str) -> list[str]:
    return re.findall(r'"([^"]+)"', listed)


def census_of(words: str) -> dict[str, tuple[list[str], list[str]]]:
    """`{model: (drawn, left out)}` as the page's words module declares them (`CENSUS` in `casesWords.ts`)."""
    block = re.search(r"export const CENSUS = \{(.*?)\n\} as const;", words, flags=re.DOTALL)
    if block is None:
        return {}
    return {m.group(1): (names(m.group(2)), names(m.group(3))) for m in CENSUS_LINE.finditer(block.group(1))}


def left_out_sentence(section: str) -> dict[str, list[str]]:
    """`{model: [field, ...]}` from the scenario's "Left out, by field name" paragraph: each `Of `Model`:` part, its backticked fields."""
    para = next((p for p in section.split("\n\n") if p.startswith("**Left out, by field name.**")), "")
    # The clause after the last model ("Every other field ...") names what is drawn, not what is left out.
    para = para.split("Every other field")[0]
    out: dict[str, list[str]] = {}
    for part in re.split(r"(?=Of `)", para):
        head = re.match(r"Of `(\w+)`: (.*)", part, flags=re.DOTALL)
        if head:
            # The backticked names at the head of each clause (`a` (why), `b` (why)): a clause's parenthesis may itself hold none.
            body = re.sub(r"\([^)]*\)", "", head.group(2))
            out[head.group(1)] = re.findall(r"`(\w+)`", body)
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
        "words": read(WORDS),
        "models": {name: read(path) for name, path in MODELS.items()},
        "value_sources": {path: read(path) for _, path, _ in VALUES.values()},
    }


# ---------------------------------------------------------------------------------------------------- the checks


def scenario_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    section = section_of(data["spec_08"])
    if not section:
        return [f"spec/08 has no section headed {SECTION!r}"]
    rows = rows_of(section)
    if not rows:
        return ["the scenario CS section has no table row"]
    for row_id, cells in rows.items():
        if not ID.match(row_id):
            found.append(f"{row_id} is not an id of the form CS<number>")
        behaviour, read_from, page_test, tree = cells
        if not behaviour:
            found.append(f"{row_id} says no behaviour")
        if tree != "GOV.UK":
            found.append(f"{row_id} runs on {tree!r}: the cases page is the GOV.UK tree's")
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
    """The scenario says, in its own words, what the page shows, who may see it, that it works with scripts off and what it leaves out."""
    section = section_of(data["spec_08"])
    found: list[str] = []
    for label, text in (
        ("what the page is", "**What the page is.**"),
        ("who may see it", "**Who may see it.**"),
        ("scripts off", "**Works with scripts off.**"),
        ("what it leaves out", "**Left out, by field name.**"),
        ("the refusal", "**the same 404 page, words and status, as a path nothing serves**"),
        ("the brief's refusal", "gets the very same 404 page"),
        ("the closed tab", 'with the words "You closed this case\'s tab" after its name'),
        ("read-only", "read-only"),
        ("the Default tree", "answers `/cases` as a path nothing serves"),
        ("the filtering rule", "filters nothing after the answer comes"),
        ("attachments by kind", "an attachment said by its kind alone"),
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
    row = rows.get(ROW)
    if row is None:
        return [f"the {ROW} row is missing"]
    ids = [item.strip() for item in row["scenario"].split(",") if item.strip()]
    if ids != JOURNEYS + EXPECTED_IDS or ids[len(JOURNEYS) :] != list(rows_of(section_of(data["spec_08"]))):
        found.append(f"the {ROW} row's scenario is {row['scenario']!r}, not its journeys and the section's ids")
    if row["route"] != "":
        found.append(f"the {ROW} row has the route {row['route']!r}: the function is not complete, so its route stays empty")
    if row["status"] != "planned":
        found.append(f"the {ROW} row's status is {row['status']!r}, not planned")
    if row["name"] != ROW_NAME or row["where"] != ROW_WHERE:
        found.append(f"the {ROW} row's name or where has moved: only its scenario is this slice's to fill")
    routed = sorted(r["route"] for r in data["functions"] if r.get("route"))
    if routed != ["/help"]:
        found.append(f"the rows that have a route are {routed!r}, not just /help")
    return found


def route_problems(data: dict[str, Any]) -> list[str]:
    expected = ["/help", "/admin/people", PATH]
    if data["routes"] != expected:
        return [f"the route list is {data['routes']!r}: the tree has three pages, {expected}"]
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
    if not re.search(r"\bcasesPage\b", data["page_list"]):
        found.append("the one table of pages (pageList.ts) does not hold the cases page")
    return found


def census_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    census = census_of(data["words"])
    sentence = left_out_sentence(section_of(data["spec_08"]))
    not_sent_block = NOT_SENT.search(data["words"])
    not_sent = set(names(not_sent_block.group(1))) if not_sent_block else None
    if not_sent is None:
        found.append("casesWords.ts declares no NOT_SENT list")
    all_excluded: set[str] = set()
    for model, source in data["models"].items():
        parsed = model_fields(source, model)
        if parsed is None:
            found.append(f"the model {model} is not in its source")
            continue
        fields, excluded = parsed
        all_excluded |= excluded
        if model not in census:
            found.append(f"the page's census has no line for {model}")
            continue
        drawn, left = census[model]
        for field in sorted(set(fields) - set(drawn) - set(left)):
            found.append(f"{model}.{field} is neither drawn by the page nor named as left out")
        for field in sorted((set(drawn) | set(left)) - set(fields)):
            found.append(f"the census names {model}.{field}, which the model does not have")
        for field in sorted(set(drawn) & set(left)):
            found.append(f"the census has {model}.{field} both drawn and left out")
        if sorted(sentence.get(model, [])) != sorted(left):
            found.append(
                f"the scenario's left-out sentence names {sentence.get(model, [])} of {model}, the page leaves out {left}"
            )
    if not_sent is not None and not_sent != all_excluded:
        found.append(f"NOT_SENT is {sorted(not_sent)}, but the fields never on the wire are {sorted(all_excluded)}")
    for model in sorted(set(sentence) - set(data["models"])):
        found.append(f"the scenario's left-out sentence names {model}, which the page does not read")
    return found


def model_values(source: str, name: str, how: str) -> list[str] | None:
    """The values of the enum `name` (its members' string values) or of the `Literal` alias `name`, in order, from `source`."""
    for node in ast.walk(ast.parse(source)):
        if how == "enum" and isinstance(node, ast.ClassDef) and node.name == name:
            return [
                item.value.value
                for item in node.body
                if isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)
            ]
        if how == "literal" and isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            value = node.value
            if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name) and value.value.id == "Literal":
                items = value.slice.elts if isinstance(value.slice, ast.Tuple) else [value.slice]
                return [e.value for e in items if isinstance(e, ast.Constant)]
    return None


def values_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for listed, (name, path, how) in VALUES.items():
        page = re.search(rf"export const {listed}(?::[^=]*)? = \[([^\]]*)\]", data["words"])
        if page is None:
            found.append(f"casesWords.ts declares no {listed} list")
            continue
        model = model_values(data["value_sources"][path], name, how)
        if model is None:
            found.append(f"{name} is not in {path.name}")
        elif sorted(names(page.group(1))) != sorted(model):
            found.append(f"the page's {listed} are {names(page.group(1))}, but {name} holds {model}")
    return found


CHECKS = (
    scenario_problems,
    prose_problems,
    citation_problems,
    function_problems,
    route_problems,
    module_problems,
    census_problems,
    values_problems,
)


# ---------------------------------------------------------------------------------------------------- the real inputs


def test_the_real_inputs_have_no_problem() -> None:
    data = inputs()
    for check in CHECKS:
        assert check(data) == [], check.__name__


def test_every_scenario_has_a_page_test_and_back() -> None:
    assert scenario_problems(inputs()) == []
    assert KEYBOARD_TEST.is_file(), "CS12 names keyboard/cases.spec.ts, which is not a file"
    assert SCRIPTS_OFF_TEST.is_file(), "CS13 names scripts-off/cases.spec.ts, which is not a file"
    section = section_of(read(SPEC_08))
    for name in ("keyboard/cases.spec.ts", "scripts-off/cases.spec.ts", "test_govuk_cases_scenario.py"):
        assert name in section, name


def test_every_row_cites_words_that_are_in_the_source() -> None:
    assert citation_problems(inputs()) == []


def test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off() -> None:
    assert prose_problems(inputs()) == []


def test_the_cases_row_carries_the_scenario_and_no_route() -> None:
    assert function_problems(inputs()) == []


def test_the_route_list_has_the_three_pages() -> None:
    assert route_problems(inputs()) == []


def test_the_page_module_is_the_cases_rows_at_its_path() -> None:
    assert module_problems(inputs()) == []


def test_the_field_census_is_the_models_fields() -> None:
    assert census_problems(inputs()) == []


def test_the_page_allows_exactly_the_models_values() -> None:
    assert values_problems(inputs()) == []


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
    """A change inside Scenario CS's own section: other scenarios carry some of the same sentences."""

    def plant(data: dict[str, Any]) -> None:
        section = section_of(data["spec_08"])
        assert old in section, f"the plant's anchor {old!r} is not in Scenario CS"
        data["spec_08"] = data["spec_08"].replace(section, section.replace(old, new, 1), 1)

    return plant


def _model(model: str, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        assert old in data["models"][model], f"the plant's anchor {old!r} is not in {model}'s source"
        data["models"][model] = data["models"][model].replace(old, new, 1)

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


PLANTS: list[tuple[str, Callable[[dict[str, Any]], None], Callable[[dict[str, Any]], list[str]], str]] = [
    ("a scenario row removed", _without_row("CS6"), scenario_problems, "no scenario CS6"),
    ("a page test case with no scenario row", _without_row("CS15"), scenario_problems, "titled CS15"),
    ("a row run on the other tree", _tree_of_row("CS3", "Default"), scenario_problems, "CS3 runs on"),
    ("a case retitled so the page test names no CS4", _replace("page_test", 'it("CS4: ', 'it("CS44: '), scenario_problems, "titled CS4"),
    (
        "the refusal sentence left out",
        _in_section("**the same 404 page, words and status, as a path nothing serves**", "a refusal"),
        prose_problems,
        "the refusal",
    ),
    ("scripts off left out", _in_section("**Works with scripts off.**", "**Works.**"), prose_problems, "scripts off"),
    (
        "the closed tab's words left out",
        _in_section('with the words "You closed this case\'s tab" after its name', "marked"),
        prose_problems,
        "the closed tab",
    ),
    (
        "words a source does not hold",
        _in_section('.py` "this account has closed the case\'s tab"', '.py` "this account has hidden the case"'),
        citation_problems,
        "does not hold",
    ),
    ("the row without its scenario", _row(ROW, scenario="A7, B14, B21"), function_problems, "scenario"),
    ("the row without its journeys", _row(ROW, scenario=", ".join(EXPECTED_IDS)), function_problems, "scenario"),
    ("the row routed while incomplete", _row(ROW, route=PATH), function_problems, "stays empty"),
    ("the row's where moved", _row(ROW, where="apps/workspace/src/investigation/"), function_problems, "has moved"),
    ("a route in the list the code has no page for", lambda d: d["routes"].append("/welcome"), route_problems, "three pages"),
    ("the cases path left out of the list", lambda d: d["routes"].remove(PATH), route_problems, "three pages"),
    ("the page at another path", _replace("page_module", f'path: "{PATH}"', 'path: "/case"'), module_problems, "its path"),
    ("the page for both trees", _replace("page_module", 'trees: ["govuk"]', 'trees: ["default", "govuk"]'), module_problems, "GOV.UK tree alone"),
    ("the page answering POST", _replace("page_module", 'methods: ["GET"]', 'methods: ["GET", "POST"]'), module_problems, "GET alone"),
    ("the page under another row", _replace("page_module", f'id: "{ROW}"', 'id: "admin"'), module_problems, "its id"),
    (
        "the page left out of the table of pages",
        lambda d: d.update(page_list=d["page_list"].replace("casesPage", "somethingElse")),
        module_problems,
        "does not hold the cases page",
    ),
    # The census: a field added to the route's model, a name the page lists that the model lacks, a left-out name dropped from the
    # scenario, a field drawn and left out at once, the wire list not the model's excluded fields.
    (
        "a field added to the listing's model",
        _model("InvestigationListing", "    tab_hidden: bool = False\n", "    tab_hidden: bool = False\n    pinned: bool = False\n"),
        census_problems,
        "InvestigationListing.pinned is neither drawn",
    ),
    (
        "a field added to an attachment",
        _model("BriefAttachment", "class BriefAttachment(BaseModel):\n    kind: AttachmentKind\n", "class BriefAttachment(BaseModel):\n    kind: AttachmentKind\n    added_by: str\n"),
        census_problems,
        "BriefAttachment.added_by is neither drawn",
    ),
    (
        "a census name for no field",
        _replace("words", 'left: ["id", "created_by", "owning_unit", "domains_chosen"]', 'left: ["id", "created_by", "owning_unit", "domains_chosen", "unit"]'),
        census_problems,
        "Investigation.unit, which the model does not have",
    ),
    (
        "a left-out field dropped from the scenario's sentence",
        _in_section("`owning_unit` (a unit's identifier), ", ""),
        census_problems,
        "left-out sentence names",
    ),
    (
        "a field both drawn and left out",
        _replace("words", 'BriefAttachment: { drawn: ["kind"], left: ["id", "title"] }', 'BriefAttachment: { drawn: ["kind", "title"], left: ["id", "title"] }'),
        census_problems,
        "both drawn and left out",
    ),
    (
        "a field never on the wire read as required",
        _replace("words", 'export const NOT_SENT: readonly string[] = ["domains_chosen"]', "export const NOT_SENT: readonly string[] = []"),
        census_problems,
        "never on the wire",
    ),
    (
        "the model's exclude taken away",
        _model("Investigation", "domains_chosen: bool = Field(default=False, exclude=True)", "domains_chosen: bool = Field(default=False)"),
        census_problems,
        "never on the wire",
    ),
]


def _source(path: Path, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        assert old in data["value_sources"][path], f"the plant's anchor {old!r} is not in {path.name}"
        data["value_sources"][path] = data["value_sources"][path].replace(old, new, 1)

    return plant


PLANTS += [
    (
        "a kind added to the model's attachments",
        _source(CASE_BRIEF, 'AttachmentKind = Literal["trend", "pattern", "assessment", "view"]', 'AttachmentKind = Literal["trend", "pattern", "assessment", "view", "document"]'),
        values_problems,
        "AttachmentKind holds",
    ),
    (
        "a level added to the model",
        _source(INVESTIGATIONS, '    AUTHOR = "author"\n', '    AUTHOR = "author"\n    OWNER = "owner"\n'),
        values_problems,
        "AccessLevel holds",
    ),
    (
        "a pack added to the model",
        _source(DOMAIN, 'DomainPack = Literal["fibo", "niem", "stix"]', 'DomainPack = Literal["fibo", "niem", "stix", "pole"]'),
        values_problems,
        "DomainPack holds",
    ),
    (
        "a status dropped from the page",
        _replace("words", 'export const STATUSES = ["open", "answered"] as const;', 'export const STATUSES = ["open"] as const;'),
        values_problems,
        "the page's STATUSES",
    ),
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
