"""Scenario DR: one document of a case in the reader, read-only, on the GOV.UK tree (slice GG3b; ADR-152 decisions 1, 4, 5, 6, 7 and
12; the owner's rulings of 26 November 2026 on GG3b's draft, D268: every proposal (a), and GG3b started after GR1a by his exception).

**There is no React-first proof** (decision 12 asks for one only "where one exists"): the React reader is a dialog opened from the
canvas, and neither of the `documents` row's journeys (A6, B6) reads one document by its address. The scenario is written first, from
that screen, the Conduit's own routes and the ADR's text, and the page test (`apps/pages/test/govuk/document.test.ts`) is the proof.

This file holds the document, the page test, the `documents` row, the route list, the page module and the field census in step:

* a scenario with no page test, or a page test with no scenario     -> `test_every_scenario_has_a_page_test_and_back`
* a row whose cited words are not in the file it cites               -> `test_every_row_cites_words_that_are_in_the_source`
* a scenario that does not say what the page shows, who may see it,
  that it works with scripts off, or what it leaves out             -> `test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off`
* the row without its scenario ids or its journeys, given a route
  while the function is incomplete                                   -> `test_the_documents_row_carries_the_scenario_and_no_route`
* a route list that is not the paths the tree has pages for          -> `test_the_route_list_has_the_eight_pages`
* the page module not the row's, at the path, for the GOV.UK tree
  alone, answering GET alone, or not in the one table of pages       -> `test_the_page_module_is_the_documents_rows_at_its_path`
* a field of the route's models neither drawn by the page nor named
  as left out, a name for no field, or a field never on the wire
  that the page's strict reader requires                             -> `test_the_field_census_is_the_models_fields`
* the page's provenance states not the model's                       -> `test_the_page_allows_exactly_the_models_values`

The models are read from their source by `ast` (the classes' annotated fields, and `exclude=True` for a field never on the wire), so a
field added to the route's model fails this test until the page draws it or the scenario names it as left out.

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and plants every fault in an
in-memory copy of what it read; it never writes into the repository. The files, from the repository's root:
`OspreyFlow_Build/spec/{08_ACCEPTANCE_SCENARIOS,01_DOMAIN_MODEL,03_CONDUIT_MIDDLEWARE,06_DECISIONS}.md`,
`OspreyFlow_Build/process/CLAUDE.md`, and under `OspreyFlow_Core`: `apps/pages/FUNCTIONS.yaml`, `apps/pages/tree-govuk/routes.yaml`,
`apps/pages/test/govuk/document.test.ts`, `apps/pages/test/govuk/keyboard/document.spec.ts`,
`apps/pages/test/govuk/scripts-off/document.spec.ts`, `apps/pages/server/{document,pageList,pages,headers,forward,app}.ts`,
`apps/pages/server/views/{documentWords,notFoundWords}.ts`, `services/api/{app,document_reader,document_content,dossier}.py`,
`packages/schemas/domain.py`, `packages/adapters/media_objectstore/__init__.py`, `apps/workspace/src/reader/DocumentReader.tsx`,
`apps/workspace/src/dossier/HighlightedMessage.tsx`.

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
PAGE_TEST = PAGES / "test" / "govuk" / "document.test.ts"
KEYBOARD_TEST = PAGES / "test" / "govuk" / "keyboard" / "document.spec.ts"
SCRIPTS_OFF_TEST = PAGES / "test" / "govuk" / "scripts-off" / "document.spec.ts"
PAGE_MODULE = PAGES / "server" / "document.ts"
WORDS = PAGES / "server" / "views" / "documentWords.ts"
PAGE_LIST = PAGES / "server" / "pageList.ts"
DOCUMENT_READER = CORE / "services" / "api" / "document_reader.py"
DOSSIER = CORE / "services" / "api" / "dossier.py"
DOMAIN = CORE / "packages" / "schemas" / "domain.py"

#: Each closed field's allowed values: the page's list (in `documentWords.ts`) and where the model's own are defined (an enum's
#: members' values), so a value added to the model fails here and never reaches a reader's page as "could not be read".
VALUES: dict[str, tuple[str, Path, str]] = {
    "PROVENANCE_STATES": ("ProvenanceState", DOMAIN, "enum"),
}

SECTION = "## Scenario DR"
ID = re.compile(r"^DR\d+$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')(DR\d+): """)
PAGE_TEST_NAME = "document.test.ts"
PATH = "/cases/document"
EXPECTED_IDS = [f"DR{n}" for n in range(1, 20)]
JOURNEYS = ["A6", "B6"]
ROW = "documents"
ROW_NAME = "Documents: reader, a node's Messages, adding files"
ROW_WHERE = "apps/workspace/src/reader/, apps/workspace/src/dossier/, apps/workspace/src/content/"
#: Every page of the tree, in the list's own order: main's seven first, this one the eighth (round 1 took main in).
ROUTE_LIST = ["/help", "/admin/people", "/reports", "/packs/trends", "/cases", "/cases/boards", "/alert-queue", PATH]

#: Each model the page reads, and the file it is defined in.
MODELS: dict[str, Path] = {
    "DocumentReaderView": DOCUMENT_READER,
    "MessageSpan": DOSSIER,
}

#: What each behaviour of the page is, by id: a behaviour with no scenario is one nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "the text with its spans marked, the table, provenance in words": ("DR1",),
    "touching and overlapping spans, places as the Conduit counts": ("DR2",),
    "an email's time, no sender or recipient named": ("DR3",),
    "a cut text said": ("DR4",),
    "a picture": ("DR5",),
    "a film": ("DR6",),
    "any other file a link": ("DR7",),
    "no title": ("DR8",),
    "every refusal: one 404": ("DR9",),
    "one read per render, as the person, no write": ("DR10",),
    "a failed read, an ended session": ("DR11",),
    "the strict reader": ("DR12",),
    "no graph id": ("DR13",),
    "markup as text": ("DR14",),
    "nosniff on the file": ("DR15",),
    "structure, keyboard and scripts off": ("DR16",),
    "the field census": ("DR17",),
    "the trees, the lists and the words": ("DR18",),
    "each check red against the real page with one thing changed": ("DR19",),
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
        if not line.startswith("| DR"):
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


def names(listed: str) -> list[str]:
    return re.findall(r'"([^"]+)"', listed)


def census_of(words: str) -> dict[str, tuple[list[str], list[str]]]:
    """`{model: (drawn, left out)}` as the page's words module declares them (`CENSUS` in `documentWords.ts`)."""
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
            # The backticked names outside each clause's parentheses (`a` (why), `b` (why)): a parenthesis may itself hold others.
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
        return ["the scenario DR section has no table row"]
    for row_id, cells in rows.items():
        if not ID.match(row_id):
            found.append(f"{row_id} is not an id of the form DR<number>")
        behaviour, read_from, page_test, tree = cells
        if not behaviour:
            found.append(f"{row_id} says no behaviour")
        if tree != "GOV.UK":
            found.append(f"{row_id} runs on {tree!r}: the reader page is the GOV.UK tree's")
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
        ("read-only", "read-only"),
        ("the Default tree", "answers `/cases/document` as a path nothing serves"),
        ("the filtering rule", "filters nothing after the answer comes"),
        ("rule 5", 'rule 5: "Proposed by a model, not yet confirmed" for an inferred one'),
        ("a cut text", '"This is the start of the message: the rest was not loaded."'),
        ("one read", "reads `GET /v1/investigations/{case}/documents/{document}/reader` once and nothing else"),
        ("the file's second read", "audits as `read_document_file`"),
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
    if routed != ["/help", "/reports"]:
        found.append(f"the rows that have a route are {routed!r}, not just /help and /reports")
    return found


def route_problems(data: dict[str, Any]) -> list[str]:
    if data["routes"] != ROUTE_LIST:
        return [f"the route list is {data['routes']!r}: the tree has eight pages, {ROUTE_LIST}"]
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
    if not re.search(r"\bdocumentPage\b", data["page_list"]):
        found.append("the one table of pages (pageList.ts) does not hold the reader page")
    return found


def census_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    census = census_of(data["words"])
    sentence = left_out_sentence(section_of(data["spec_08"]))
    for model, source in data["models"].items():
        parsed = model_fields(source, model)
        if parsed is None:
            found.append(f"the model {model} is not in its source")
            continue
        fields, excluded = parsed
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
        # The strict reader requires every field the census names (`REQUIRED`): a field never on the wire would refuse every answer.
        for field in sorted(excluded & (set(drawn) | set(left))):
            found.append(f"{model}.{field} is never on the wire, but the page's strict reader requires it")
        if sorted(sentence.get(model, [])) != sorted(left):
            found.append(
                f"the scenario's left-out sentence names {sentence.get(model, [])} of {model}, the page leaves out {left}"
            )
    for model in sorted(set(sentence) - set(data["models"])):
        found.append(f"the scenario's left-out sentence names {model}, which the page does not read")
    return found


def model_values(source: str, name: str, how: str) -> list[str] | None:
    """The values of the enum `name` (its members' string values), in order, from `source`."""
    for node in ast.walk(ast.parse(source)):
        if how == "enum" and isinstance(node, ast.ClassDef) and node.name == name:
            return [
                item.value.value
                for item in node.body
                if isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)
            ]
    return None


def values_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for listed, (name, path, how) in VALUES.items():
        page = re.search(rf"export const {listed}(?::[^=]*)? = \[([^\]]*)\]", data["words"])
        if page is None:
            found.append(f"documentWords.ts declares no {listed} list")
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
    assert KEYBOARD_TEST.is_file(), "DR16 names keyboard/document.spec.ts, which is not a file"
    assert SCRIPTS_OFF_TEST.is_file(), "DR16 names scripts-off/document.spec.ts, which is not a file"
    section = section_of(read(SPEC_08))
    for name in ("keyboard/document.spec.ts", "scripts-off/document.spec.ts", "test_govuk_document_scenario.py"):
        assert name in section, name


def test_every_row_cites_words_that_are_in_the_source() -> None:
    assert citation_problems(inputs()) == []


def test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off() -> None:
    assert prose_problems(inputs()) == []


def test_the_documents_row_carries_the_scenario_and_no_route() -> None:
    assert function_problems(inputs()) == []


def test_the_route_list_has_the_eight_pages() -> None:
    assert route_problems(inputs()) == []


def test_the_page_module_is_the_documents_rows_at_its_path() -> None:
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
    """A change inside Scenario DR's own section: other scenarios carry some of the same sentences."""

    def plant(data: dict[str, Any]) -> None:
        section = section_of(data["spec_08"])
        assert old in section, f"the plant's anchor {old!r} is not in Scenario DR"
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


def _source(path: Path, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        assert old in data["value_sources"][path], f"the plant's anchor {old!r} is not in {path.name}"
        data["value_sources"][path] = data["value_sources"][path].replace(old, new, 1)

    return plant


PLANTS: list[tuple[str, Callable[[dict[str, Any]], None], Callable[[dict[str, Any]], list[str]], str]] = [
    ("a scenario row removed", _without_row("DR9"), scenario_problems, "no scenario DR9"),
    ("a page test case with no scenario row", _without_row("DR19"), scenario_problems, "titled DR19"),
    ("a row run on the other tree", _tree_of_row("DR3", "Default"), scenario_problems, "DR3 runs on"),
    ("a case retitled so the page test names no DR4", _replace("page_test", 'it("DR4: ', 'it("DR44: '), scenario_problems, "titled DR4"),
    (
        "the refusal sentence left out",
        _in_section("**the same 404 page, words and status, as a path nothing serves**", "a refusal"),
        prose_problems,
        "the refusal",
    ),
    ("scripts off left out", _in_section("**Works with scripts off.**", "**Works.**"), prose_problems, "scripts off"),
    (
        "rule 5's words left out",
        _in_section('(rule 5: "Proposed by a model, not yet confirmed" for an inferred one', "(rule 5"),
        prose_problems,
        "rule 5",
    ),
    (
        "words a source does not hold",
        _in_section('.py` "By the email\'s direction"', '.py` "By the email\'s sender"'),
        citation_problems,
        "does not hold",
    ),
    (
        "a path that is not a file",
        _in_section("`services/api/dossier.py` \"class MessageSpan(BaseModel):\"", "`services/api/spans.py` \"class MessageSpan(BaseModel):\""),
        citation_problems,
        "which is not a file",
    ),
    ("the row without its scenario", _row(ROW, scenario="A6, B6"), function_problems, "scenario"),
    ("the row without its journeys", _row(ROW, scenario=", ".join(EXPECTED_IDS)), function_problems, "scenario"),
    ("the row routed while incomplete", _row(ROW, route=PATH), function_problems, "stays empty"),
    ("the row's where moved", _row(ROW, where="apps/workspace/src/reader/"), function_problems, "has moved"),
    ("a route in the list the code has no page for", lambda d: d["routes"].append("/welcome"), route_problems, "eight pages"),
    ("the reader's path left out of the list", lambda d: d["routes"].remove(PATH), route_problems, "eight pages"),
    ("the page at another path", _replace("page_module", f'path: "{PATH}"', 'path: "/document"'), module_problems, "its path"),
    ("the page for both trees", _replace("page_module", 'trees: ["govuk"]', 'trees: ["default", "govuk"]'), module_problems, "GOV.UK tree alone"),
    ("the page answering POST", _replace("page_module", 'methods: ["GET"]', 'methods: ["GET", "POST"]'), module_problems, "GET alone"),
    ("the page under another row", _replace("page_module", f'id: "{ROW}"', 'id: "cases-and-views"'), module_problems, "its id"),
    (
        "the page left out of the table of pages",
        lambda d: d.update(page_list=d["page_list"].replace("documentPage", "somethingElse")),
        module_problems,
        "does not hold the reader page",
    ),
    # The census: a field added to the route's model, a name the page lists that the model lacks, a left-out name dropped from the
    # scenario, a field drawn and left out at once, a field taken off the wire that the reader still requires.
    (
        "a field added to the reader's model",
        _model("DocumentReaderView", "    has_file: bool = False\n", "    has_file: bool = False\n    sender_name: str | None = None\n"),
        census_problems,
        "DocumentReaderView.sender_name is neither drawn",
    ),
    (
        "a field added to a span",
        _model("MessageSpan", "    entity_type: str\n", "    entity_type: str\n    confidence: float\n"),
        census_problems,
        "MessageSpan.confidence is neither drawn",
    ),
    (
        "a census name for no field",
        _replace("words", 'MessageSpan: { drawn: ["start", "end", "entity_type", "provenance_state"], left: ["node_id"] }', 'MessageSpan: { drawn: ["start", "end", "entity_type", "provenance_state"], left: ["node_id", "node"] }'),
        census_problems,
        "MessageSpan.node, which the model does not have",
    ),
    (
        "a left-out field dropped from the scenario's sentence",
        _in_section("`edge_id` and `event_id` (graph ids", "`edge_id` (graph ids"),
        census_problems,
        "left-out sentence names",
    ),
    (
        "a field both drawn and left out",
        _replace("words", 'left: ["node_id"] }', 'left: ["node_id", "entity_type"] }'),
        census_problems,
        "both drawn and left out",
    ),
    (
        "a field taken off the wire that the reader still requires",
        _model("DocumentReaderView", "    has_file: bool = False\n", "    has_file: bool = Field(default=False, exclude=True)\n"),
        census_problems,
        "never on the wire",
    ),
    (
        "a provenance state added to the model",
        _source(DOMAIN, '    UNRESOLVED = "unresolved"\n', '    UNRESOLVED = "unresolved"\n    CONFIRMED = "confirmed"\n'),
        values_problems,
        "ProvenanceState holds",
    ),
    (
        "a provenance state dropped from the page",
        _replace("words", 'export const PROVENANCE_STATES = ["asserted", "inferred", "unresolved"] as const;', 'export const PROVENANCE_STATES = ["asserted", "inferred"] as const;'),
        values_problems,
        "the page's PROVENANCE_STATES",
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
