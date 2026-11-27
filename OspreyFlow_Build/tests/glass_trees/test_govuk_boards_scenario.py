"""Scenario BD: a case's drawing boards and one board's drawn items and links as tables on the GOV.UK tree (slice GG4a), and making,
sharing and deleting a board as scripts-off forms (slice GG4c, BD18 onward); ADR-143 decisions 3 to 5; ADR-152 decisions 1, 4, 5, 6, 7
and 12; the owner's rulings of 25 November 2026 on GG4a's draft (every proposal (a), and, for question 2, his exception (b): GG4a starts
before GG3, since a board draws without Sigma) and of 26 November 2026 on GG4c's (every proposal (a); no unshare route).

**There is no React-first proof** (decision 12 asks for one only "where one exists"): the React boards are a place of buttons and a
drawing surface, and the `drawing-boards` row has no journey. The scenario is written first, from those screens, the Conduit's own routes
and the ADR's text, and the page tests (`apps/pages/test/govuk/boards.test.ts` for BD1 to BD17, `boards-write.test.ts` for BD18 onward)
are the proof.

This file holds the document, the page test, the `drawing-boards` row, the route list, the page module and the field census in step:

* a scenario with no page test, or a page test with no scenario     -> `test_every_scenario_has_a_page_test_and_back`
* a row whose cited words are not in the file it cites               -> `test_every_row_cites_words_that_are_in_the_source`
* a scenario that does not say what the page shows, who may see it,
  that it works with scripts off, or what it leaves out             -> `test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off`
* the row without its scenario ids, given a route while the function
  is incomplete                                                      -> `test_the_boards_row_carries_the_scenario_and_no_route`
* a route list that is not the paths the tree has pages for          -> `test_the_route_list_has_the_six_pages`
* the page module not the row's, at the path, for the GOV.UK tree
  alone, answering GET and POST alone, or not in the one table       -> `test_the_page_module_is_the_boards_rows_at_its_path`
* a write route whose rights, case gate, creator check or body
  refusal is no longer what the fixture Conduit copies, an unshare
  route, a form passed through to the Conduit, the owner's words
  changed in the page or missing from the scenario                   -> `test_the_writes_are_the_routes_and_the_owners_words`
* a field of the routes' models neither drawn by the page nor named
  as left out, a name for no field, the page's never-sent or
  may-be-absent lists not the models' own                            -> `test_the_field_census_is_the_models_fields`
* a closed field's values not the models' own                        -> `test_the_page_allows_exactly_the_models_values`
* the checked fields not the scenario's "Checked, not drawn" sentence -> `test_the_field_census_is_the_models_fields`
* a drawn item's source said until GG4b: either source field not left
  out, a table with a column for it, the words for a missing note, or
  a scenario that does not say why                                    -> `test_no_source_is_drawn_until_gg4b`

The models are read from their source by `ast` (the classes' annotated fields; `exclude=True` for a field never on the wire; and the keys a
`model_serializer` pops when unset, for a field that may be absent), so a field added to a route's model fails this test until the page
draws it or the scenario names it as left out.

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and plants every fault in an
in-memory copy of what it read; it never writes into the repository. The files, from the repository's root:
`OspreyFlow_Build/spec/{08_ACCEPTANCE_SCENARIOS,03_CONDUIT_MIDDLEWARE,06_DECISIONS}.md`, and under `OspreyFlow_Core`:
`apps/pages/FUNCTIONS.yaml`, `apps/pages/tree-govuk/routes.yaml`, `apps/pages/test/govuk/boards.test.ts`,
`apps/pages/test/govuk/boards-write.test.ts`, `apps/pages/test/govuk/keyboard/boards.spec.ts`,
`apps/pages/test/govuk/scripts-off/boards.spec.ts`,
`apps/pages/server/{boards,pageList,pages,conduit}.ts`, `apps/pages/server/views/{boardsWords,notFoundWords}.ts`,
`services/api/{app,boards}.py`, `services/api/working_set/models.py`, `packages/schemas/{boards,domain}.py`, `packages/ontology/handling.py`,
`apps/workspace/src/workingset/ViewOverCapDialog.tsx`,
`apps/workspace/src/boards/{BoardsPlace,BoardEditor}.tsx`.

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
PAGE_TEST = PAGES / "test" / "govuk" / "boards.test.ts"
WRITE_TEST = PAGES / "test" / "govuk" / "boards-write.test.ts"
APP = CORE / "services" / "api" / "app.py"
KEYBOARD_TEST = PAGES / "test" / "govuk" / "keyboard" / "boards.spec.ts"
SCRIPTS_OFF_TEST = PAGES / "test" / "govuk" / "scripts-off" / "boards.spec.ts"
PAGE_MODULE = PAGES / "server" / "boards.ts"
WORDS = PAGES / "server" / "views" / "boardsWords.ts"
PAGE_LIST = PAGES / "server" / "pageList.ts"
BOARDS = CORE / "packages" / "schemas" / "boards.py"
DOMAIN = CORE / "packages" / "schemas" / "domain.py"
WORKING_SET = CORE / "services" / "api" / "working_set" / "models.py"

#: Each closed field's allowed values: the page's list (in `boardsWords.ts`) and where the model's own are defined (an enum's members'
#: values, or a `Literal` alias), so a value added to a model fails here and never reaches a reader's page as "could not be read".
VALUES: dict[str, tuple[str, Path, str]] = {
    "STARTS": ("BoardStart", BOARDS, "literal"),
    "STATES": ("ProvenanceState", DOMAIN, "enum"),
    "OPTIONS": ("LimitOption", WORKING_SET, "literal"),
    # A field's own `Literal` (`Class.field`), not an alias: found missing by the review of 25 November.
    "BASES": ("Edge.basis", DOMAIN, "field"),
    "CAP_KINDS": ("LimitExceeded.cap_kind", WORKING_SET, "field"),
    "CLASSES": ("DrawnAssertion.provenance_class", DOMAIN, "field"),
}

SECTION = "## Scenario BD"
ID = re.compile(r"^BD\d+$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')(BD\d+): """)
PATH = "/cases/boards"
EXPECTED_IDS = [f"BD{n}" for n in range(1, 32)]
#: Which page test proves each row: GG4a's rows in its file, GG4c's (the writes) in theirs.
TEST_FILES: dict[str, str] = {
    row_id: ("boards.test.ts" if int(row_id[2:]) <= 17 else "boards-write.test.ts") for row_id in EXPECTED_IDS
}
ROW = "drawing-boards"
ROW_NAME = "Drawing boards (and a watch or alert drawn from them)"
ROW_WHERE = "apps/workspace/src/boards/"

#: Each model the page reads, and the file it is defined in.
MODELS: dict[str, Path] = {
    "Board": BOARDS,
    "BoardOpened": BOARDS,
    "Node": DOMAIN,
    "Edge": DOMAIN,
    "Provenance": DOMAIN,
    "DrawnAssertion": DOMAIN,
    "Grading": DOMAIN,
    "Handling": DOMAIN,
    "LimitExceeded": WORKING_SET,
}

#: What each behaviour of the page is, by id: a behaviour with no scenario is one nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "the boards as a table in the Conduit's order, each name a link, the route's count": ("BD1",),
    "no board: a sentence, never an empty table": ("BD2",),
    "one board: drawn items, loaded items, links": ("BD3", "BD4"),
    "every refusal: one 404": ("BD5",),
    "the withdrawn count, the creator's alone, above zero": ("BD6",),
    "an item hidden by its marking: nowhere": ("BD7",),
    "past the cap: the three options in words": ("BD8",),
    "one read per render, as the person, no write": ("BD9",),
    "a failed read, an ended session": ("BD10",),
    "the strict reader": ("BD11",),
    "the field census": ("BD12",),
    "an empty board said in words": ("BD13",),
    "structure and keyboard": ("BD14",),
    "scripts off": ("BD15",),
    "the trees, the lists and the words": ("BD16",),
    "each check red against the real page with one thing changed": ("BD17",),
    "the new board, offered on both rights": ("BD18",),
    "a blank board made: one post, then 303": ("BD19",),
    "a wrong name: the error summary, the words kept, nothing sent": ("BD20",),
    "a refusal for the right or the level, in the page's words": ("BD21",),
    "a share, told it cannot be undone": ("BD22",),
    "share and delete only on may_draw; a non-creator: a missing board": ("BD23",),
    "a delete asked first, then the banner once": ("BD24",),
    "the anti-forgery token": ("BD25",),
    "a failed write and an ended session": ("BD26",),
    "one call per write, so one audit row": ("BD27",),
    "the writes by keyboard": ("BD28",),
    "the writes with scripts off": ("BD29",),
    "the fixture refuses a write as the route does": ("BD30",),
    "each write check red against the real page with one thing changed": ("BD31",),
}

#: The words the owner ruled for the writes (26 November 2026): each in the page's words module and in the scenario.
RULED_WORDS = (
    "New drawing board",
    "Share with the case",
    "You cannot make boards in this case",
    "Delete this board?",
    "What was drawn on it stays in the case.",
    "The board was deleted. What was drawn on it stays in the case.",
)
#: The write routes, each with whether it asks `own_board` (the board's creator): what the fixture's order of refusals copies.
WRITE_ROUTES: dict[str, bool] = {"make_board": False, "share_board": True, "delete_board": True}


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
        if not line.startswith("| BD"):
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


CENSUS_LINE = re.compile(r"^\s*(\w+): \{ drawn: \[([^\]]*)\], checked: \[([^\]]*)\], left: \[([^\]]*)\] \},?$", re.MULTILINE)
NOT_SENT = re.compile(r"export const NOT_SENT[^=]*= \[([^\]]*)\]")


def names(listed: str) -> list[str]:
    return re.findall(r'"([^"]+)"', listed)


def census_of(words: str) -> dict[str, tuple[list[str], list[str], list[str]]]:
    """`{model: (drawn, checked, left out)}` as the page's words module declares them (`CENSUS` in `boardsWords.ts`)."""
    block = re.search(r"export const CENSUS = \{(.*?)\n\} as const;", words, flags=re.DOTALL)
    if block is None:
        return {}
    return {m.group(1): (names(m.group(2)), names(m.group(3)), names(m.group(4))) for m in CENSUS_LINE.finditer(block.group(1))}


def checked_sentence(section: str) -> dict[str, list[str]]:
    """`{model: [field, ...]}` from the scenario's "Checked, not drawn" paragraph: each `of `Model`, `field` (why)` clause."""
    para = next((p for p in section.split("\n\n") if p.startswith("**Checked, not drawn, by field name.**")), "")
    body = para.split(":", 1)[1] if ":" in para else ""
    body = re.sub(r"\([^)]*\)", "", body)
    out: dict[str, list[str]] = {}
    for clause in body.split(";"):
        head = re.match(r"\s*of `(\w+)`, (.*)", clause, flags=re.DOTALL)
        if head:
            out[head.group(1)] = re.findall(r"`(\w+)`", head.group(2))
    return out


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


MAY_BE_ABSENT = re.compile(r"export const MAY_BE_ABSENT[^=]*= \[([^\]]*)\]")


def popped_fields(source: str, name: str) -> set[str]:
    """The keys the class `name`'s own `model_serializer` pops from what it sends when they are unset (`data.pop("drawn", None)`):
    fields that may be absent from a body."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == name:
            out: set[str] = set()
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and any(
                    (isinstance(d, ast.Call) and getattr(d.func, "id", None) == "model_serializer") or getattr(d, "id", None) == "model_serializer"
                    for d in item.decorator_list
                ):
                    for call in ast.walk(item):
                        if (
                            isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Attribute)
                            and call.func.attr == "pop"
                            and call.args
                            and isinstance(call.args[0], ast.Constant)
                        ):
                            out.add(call.args[0].value)
            return out
    return set()


def inputs() -> dict[str, Any]:
    """Everything `problems` reads, as text or parsed data: a plant changes one entry."""
    return {
        "spec_08": read(SPEC_08),
        "functions": yaml.safe_load(read(FUNCTIONS))["functions"],
        "routes": yaml.safe_load(read(ROUTES))["routes"],
        "page_test": read(PAGE_TEST),
        "write_test": read(WRITE_TEST),
        "app": read(APP),
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
        return ["the scenario BD section has no table row"]
    for row_id, cells in rows.items():
        if not ID.match(row_id):
            found.append(f"{row_id} is not an id of the form BD<number>")
        behaviour, read_from, page_test, tree = cells
        if not behaviour:
            found.append(f"{row_id} says no behaviour")
        if tree != "GOV.UK":
            found.append(f"{row_id} runs on {tree!r}: the boards page is the GOV.UK tree's")
        if not read_from:
            found.append(f"{row_id} says nothing of what it was read from")
        wanted = TEST_FILES.get(row_id, "boards-write.test.ts")
        if f"`{wanted}`" not in page_test:
            found.append(f"{row_id} names no page test: {wanted}")
    if list(rows) != EXPECTED_IDS:
        found.append(f"the scenario's ids are {list(rows)}, not {EXPECTED_IDS}")
    for behaviour, ids in BRIEF.items():
        for row_id in ids:
            if row_id not in rows:
                found.append(f"the behaviour {behaviour!r} has no scenario {row_id}")
    for key, name in (("page_test", "boards.test.ts"), ("write_test", "boards-write.test.ts")):
        titled = set(TITLE.findall(data[key]))
        proved = {r for r in rows if TEST_FILES.get(r) == name}
        for row_id in sorted(proved - titled):
            found.append(f"{row_id} names {name} but no case of it is titled {row_id}")
        for row_id in sorted(titled - proved):
            found.append(f"{name} has a case titled {row_id}, which is no scenario of its own")
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
        ("no 'not shared' sentence", "never a sentence that the board is not shared with them"),
        ("the hidden item", "absent from every table and every count, with no gap"),
        ("the withdrawn count", "which it does to the board's creator alone"),
        ("the writes", "It writes three things and no others"),
        ("post, then a redirect", "post, then `303` to a `GET`"),
        ("no unshare", "there is no unshare route, and none is asked for here"),
        ("nothing passed through", "the form's fields are never passed through"),
        ("no maker named", "names who made a board"),
        ("no source on a write's page", "none shows a drawn item's source or a document's identifier"),
        ("the Default tree", "answers `/cases/boards` as a path nothing serves"),
        ("the filtering rule", "filters nothing after the answer comes"),
        ("the route's own count", "never one the page makes"),
        ("the owner's exception", "his exception (b): GG4a starts now, before GG3"),
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
    if ids != EXPECTED_IDS or ids != list(rows_of(section_of(data["spec_08"]))):
        found.append(f"the {ROW} row's scenario is {row['scenario']!r}, not the section's ids")
    if row["route"] != "":
        found.append(f"the {ROW} row has the route {row['route']!r}: the function is not complete, so its route stays empty")
    if row["status"] != "planned":
        found.append(f"the {ROW} row's status is {row['status']!r}, not planned")
    if row["name"] != ROW_NAME or row["where"] != ROW_WHERE or row["slice"] != "GG4":
        found.append(f"the {ROW} row's name, where or slice has moved: only its scenario is this slice's to fill")
    routed = sorted(r["route"] for r in data["functions"] if r.get("route"))
    if routed != ["/help", "/reports"]:
        found.append(f"the rows that have a route are {routed!r}, not just /help and /reports")
    return found


def route_problems(data: dict[str, Any]) -> list[str]:
    expected = ["/help", "/admin/people", "/reports", "/packs/trends", "/cases", PATH, "/alert-queue"]
    if data["routes"] != expected:
        return [f"the route list is {data['routes']!r}: the tree has seven pages, {expected}"]
    return []


def module_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    text = data["page_module"]
    for label, needle in (
        ("its id", f'id: "{ROW}"'),
        ("its path", f'path: "{PATH}"'),
        ("the GOV.UK tree alone", 'trees: ["govuk"]'),
        ("GET and POST alone", 'methods: ["GET", "POST"]'),
    ):
        if needle not in text:
            found.append(f"the page module does not name {label}: {needle!r}")
    if not re.search(r"\bboardsPage\b", data["page_list"]):
        found.append("the one table of pages (pageList.ts) does not hold the boards page")
    return found


def census_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    census = census_of(data["words"])
    sentence = left_out_sentence(section_of(data["spec_08"]))
    checks = checked_sentence(section_of(data["spec_08"]))
    not_sent_block = NOT_SENT.search(data["words"])
    not_sent = set(names(not_sent_block.group(1))) if not_sent_block else None
    absent_block = MAY_BE_ABSENT.search(data["words"])
    may_be_absent = set(names(absent_block.group(1))) if absent_block else None
    if not_sent is None:
        found.append("boardsWords.ts declares no NOT_SENT list")
    if may_be_absent is None:
        found.append("boardsWords.ts declares no MAY_BE_ABSENT list")
    all_excluded: set[str] = set()
    all_popped: set[str] = set()
    for model, source in data["models"].items():
        parsed = model_fields(source, model)
        if parsed is None:
            found.append(f"the model {model} is not in its source")
            continue
        fields, excluded = parsed
        all_excluded |= {f"{model}.{field}" for field in excluded}
        all_popped |= {f"{model}.{field}" for field in popped_fields(source, model) & set(fields)}
        if model not in census:
            found.append(f"the page's census has no line for {model}")
            continue
        drawn, checked, left = census[model]
        for field in sorted(set(fields) - set(drawn) - set(checked) - set(left)):
            found.append(f"{model}.{field} is neither drawn nor checked by the page nor named as left out")
        for field in sorted((set(drawn) | set(checked) | set(left)) - set(fields)):
            found.append(f"the census names {model}.{field}, which the model does not have")
        for field in sorted((set(drawn) & set(left)) | (set(drawn) & set(checked)) | (set(checked) & set(left))):
            found.append(f"the census has {model}.{field} in two of its lists")
        if sorted(checks.get(model, [])) != sorted(checked):
            found.append(f"the scenario's checked sentence names {checks.get(model, [])} of {model}, the page checks {checked}")
        if sorted(sentence.get(model, [])) != sorted(left):
            found.append(
                f"the scenario's left-out sentence names {sentence.get(model, [])} of {model}, the page leaves out {left}"
            )
    if not_sent is not None and not_sent != all_excluded:
        found.append(f"NOT_SENT is {sorted(not_sent)}, but the fields never on the wire are {sorted(all_excluded)}")
    if may_be_absent is not None and may_be_absent != all_popped:
        found.append(f"MAY_BE_ABSENT is {sorted(may_be_absent)}, but the fields a model leaves out when unset are {sorted(all_popped)}")
    for model in sorted((set(sentence) | set(checks)) - set(data["models"])):
        found.append(f"the scenario's census sentences name {model}, which the page does not read")
    return found


def field_literal(source: str, name: str) -> list[str] | None:
    """The values of the `Literal` in the annotation of `Class.field` (`name`), in order, from `source` (`None` is not one)."""
    cls, field = name.split(".")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.target.id == field:
                    for sub_node in ast.walk(item.annotation):
                        if isinstance(sub_node, ast.Subscript) and isinstance(sub_node.value, ast.Name) and sub_node.value.id == "Literal":
                            items = sub_node.slice.elts if isinstance(sub_node.slice, ast.Tuple) else [sub_node.slice]
                            return [e.value for e in items if isinstance(e, ast.Constant)]
    return None


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
            found.append(f"boardsWords.ts declares no {listed} list")
            continue
        source = data["value_sources"][path]
        model = field_literal(source, name) if how == "field" else model_values(source, name, how)
        if model is None:
            found.append(f"{name} is not in {path.name}")
        elif sorted(names(page.group(1))) != sorted(model):
            found.append(f"the page's {listed} are {names(page.group(1))}, but {name} holds {model}")
    return found


#: The two tables that held a source on the away branch, each with the columns it has until GG4b (the owner's ruling of 26 November
#: 2026): the page's list in `boardsWords.ts`, and the scenario row that names them.
NO_SOURCE_COLUMNS: dict[str, tuple[str, list[str]]] = {
    "drawnColumns": ("BD3", ["Item", "Type", "Marking", "Grading"]),
    "linkColumns": ("BD4", ["Link", "Type", "From", "To", "Drawn or loaded", "Marking", "Grading"]),
}
SOURCE_FIELDS = ("source_note", "source_document")


def source_problems(data: dict[str, Any]) -> list[str]:
    """No drawn item's source is said until GG4b: the route sends the document to every reader of the board, and a drawn item needs a
    note or a document, so either field, or a note's absence, would tell a reader a document is there."""
    found: list[str] = []
    section = section_of(data["spec_08"])
    census = census_of(data["words"])
    _, _, left = census.get("DrawnAssertion", ([], [], []))
    for field in SOURCE_FIELDS:
        if field not in left:
            found.append(f"DrawnAssertion.{field} is not left out by the page")
    rows = rows_of(section)
    for listed, (row_id, columns) in NO_SOURCE_COLUMNS.items():
        page = re.search(rf"^\s*{listed}: \[([^\]]*)\],", data["words"], flags=re.MULTILINE)
        if page is None or names(page.group(1)) != columns:
            found.append(f"the page's {listed} are {names(page.group(1)) if page else None}, not {columns}")
        said = f"columns {', '.join(columns)}"
        behaviour = rows.get(row_id, [""])[0]
        if not re.search(re.escape(said) + r"(?=[);.])", behaviour):
            found.append(f"{row_id} does not say its {said!r} and no other")
    for word in ("noNote", "loadedSource"):
        if re.search(rf"\b{word}\b", data["words"]):
            found.append(f"boardsWords.ts still holds the words {word}")
    paragraph = next((p for p in section.split("\n\n") if p.startswith("**Left out, by field name.**")), "")
    if "`source_note` and `source_document` (left out until GG4b" not in paragraph:
        found.append("the left-out sentence does not say the two source fields are left out until GG4b, and why")
    return found


def route_facts(source: str, name: str) -> tuple[str, dict[str, str], set[str]] | None:
    """Of the route function `name`: its decorators as text, its parameters' annotations, and the methods it calls."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            decorators = "\n".join(ast.unparse(d) for d in node.decorator_list)
            params = {a.arg: ast.unparse(a.annotation) for a in node.args.args if a.annotation is not None}
            called = {
                c.func.attr for c in ast.walk(node) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            }
            return decorators, params, called
    return None


def write_problems(data: dict[str, Any]) -> list[str]:
    """The writes: the routes' gates the fixture copies, no unshare route, the page's own body, and the owner's words."""
    found: list[str] = []
    app = data["app"]
    for name, owns in WRITE_ROUTES.items():
        facts = route_facts(app, name)
        if facts is None:
            found.append(f"the route {name} is not in app.py")
            continue
        decorators, params, called = facts
        if "dependencies=_DRAWS" not in decorators:
            found.append(f"{name} no longer asks the drawing rights before anything else (the fixture's first refusal)")
        if params.get("investigation") != "InvestigationEditorDep":
            found.append(f"{name} no longer stands behind the case's Editor gate (the fixture's second refusal)")
        if owns and "own_board" not in called:
            found.append(f"{name} no longer asks for the board's creator")
    if "_DRAWS = [Depends(require_right(Right.DRAW_ON_BOARDS)), Depends(require_right(Right.INVESTIGATE))]" not in app:
        found.append("the drawing rights are not draw_on_boards then investigate, as the fixture asks them")
    if re.search(r"/boards/\{board_id\}/(?:unshare|private)|def unshare_board", app):
        found.append("the Conduit has an unshare route: the page and the scenario say there is none")
    body = re.search(r"class BoardInput\(BaseModel\):.*?(?=\nclass )", data["models"]["Board"], flags=re.DOTALL)
    if body is None or 'ConfigDict(extra="forbid")' not in body.group(0):
        found.append("BoardInput no longer forbids an extra field, which the fixture refuses")
    if 'json: { name, start: "blank" }' not in data["page_module"]:
        found.append("the page does not build a new board's body itself, from the name and a blank start")
    if re.search(r"json:\s*(?:req\.body|fields|body)\b", data["page_module"]):
        found.append("the page passes a form through to the Conduit")
    section = section_of(data["spec_08"])
    for words in RULED_WORDS:
        if f'"{words}"' not in data["words"]:
            found.append(f"boardsWords.ts does not hold the ruled words {words!r}")
        if words not in section:
            found.append(f"the scenario does not say the ruled words {words!r}")
    return found


CHECKS = (
    write_problems,
    source_problems,
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
    assert KEYBOARD_TEST.is_file(), "BD14 names keyboard/boards.spec.ts, which is not a file"
    assert SCRIPTS_OFF_TEST.is_file(), "BD15 names scripts-off/boards.spec.ts, which is not a file"
    section = section_of(read(SPEC_08))
    for name in ("keyboard/boards.spec.ts", "scripts-off/boards.spec.ts", "test_govuk_boards_scenario.py"):
        assert name in section, name


def test_every_row_cites_words_that_are_in_the_source() -> None:
    assert citation_problems(inputs()) == []


def test_the_scenario_says_what_it_shows_who_sees_it_and_scripts_off() -> None:
    assert prose_problems(inputs()) == []


def test_the_boards_row_carries_the_scenario_and_no_route() -> None:
    assert function_problems(inputs()) == []


def test_the_route_list_has_the_six_pages() -> None:
    assert route_problems(inputs()) == []


def test_the_page_module_is_the_boards_rows_at_its_path() -> None:
    assert module_problems(inputs()) == []


def test_the_field_census_is_the_models_fields() -> None:
    assert census_problems(inputs()) == []


def test_the_page_allows_exactly_the_models_values() -> None:
    assert values_problems(inputs()) == []


def test_no_source_is_drawn_until_gg4b() -> None:
    assert source_problems(inputs()) == []


def test_the_writes_are_the_routes_and_the_owners_words() -> None:
    assert write_problems(inputs()) == []


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
    """A change inside Scenario BD's own section: other scenarios carry some of the same sentences."""

    def plant(data: dict[str, Any]) -> None:
        section = section_of(data["spec_08"])
        assert old in section, f"the plant's anchor {old!r} is not in Scenario BD"
        data["spec_08"] = data["spec_08"].replace(section, section.replace(old, new, 1), 1)

    return plant


def _model(model: str, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        assert old in data["models"][model], f"the plant's anchor {old!r} is not in {model}'s source"
        data["models"][model] = data["models"][model].replace(old, new, 1)

    return plant


def _app(old: str, new: str, after: str) -> Callable[[dict[str, Any]], None]:
    """A change to app.py at the first `old` after the words `after` (the same gate is written on many routes)."""

    def plant(data: dict[str, Any]) -> None:
        start = data["app"].index(after)
        at = data["app"].index(old, start)
        data["app"] = data["app"][:at] + new + data["app"][at + len(old) :]

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


def _in_class(path: Path, cls: str, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    """A change in the class `cls`'s own body: the same annotation is written in other classes of the file (`domain.py` has three
    `basis` fields), and a change to the first one in the file would plant in another model (found when this plant first passed)."""

    def plant(data: dict[str, Any]) -> None:
        source = data["value_sources"][path]
        start = source.index(f"class {cls}(")
        end = source.find("\nclass ", start + 1)
        body = source[start : end if end != -1 else len(source)]
        assert old in body, f"the plant's anchor {old!r} is not in {cls}"
        data["value_sources"][path] = source[:start] + body.replace(old, new, 1) + source[start + len(body) :]

    return plant


PLANTS: list[tuple[str, Callable[[dict[str, Any]], None], Callable[[dict[str, Any]], list[str]], str]] = [
    ("a scenario row removed", _without_row("BD6"), scenario_problems, "no scenario BD6"),
    ("a page test case with no scenario row", _without_row("BD17"), scenario_problems, "titled BD17"),
    ("a row run on the other tree", _tree_of_row("BD3", "Default"), scenario_problems, "BD3 runs on"),
    ("a case retitled so the page test names no BD4", _replace("page_test", 'it("BD4: ', 'it("BD44: '), scenario_problems, "titled BD4"),
    (
        "the refusal sentence left out",
        _in_section("**the same 404 page, words and status, as a path nothing serves**", "a refusal"),
        prose_problems,
        "the refusal",
    ),
    ("scripts off left out", _in_section("**Works with scripts off.**", "**Works.**"), prose_problems, "scripts off"),
    (
        "the hidden item's rule left out",
        _in_section("absent from every table and every count, with no gap", "left out"),
        prose_problems,
        "the hidden item",
    ),
    (
        "the creator's alone left out",
        _in_section("which it does to the board's creator alone", "which it does"),
        prose_problems,
        "the withdrawn count",
    ),
    (
        "words a source does not hold",
        _in_section('"someone else\'s private board, another case\'s, and none at all alike"', '"a board the reader may not see"'),
        citation_problems,
        "does not hold",
    ),
    ("the row without its scenario", _row(ROW, scenario=""), function_problems, "scenario"),
    ("the row with one id short", _row(ROW, scenario=", ".join(EXPECTED_IDS[:-1])), function_problems, "scenario"),
    ("the row routed while incomplete", _row(ROW, route=PATH), function_problems, "stays empty"),
    ("the row's slice moved", _row(ROW, slice="GG4a"), function_problems, "has moved"),
    ("a route in the list the code has no page for", lambda d: d["routes"].append("/welcome"), route_problems, "seven pages"),
    ("the boards path left out of the list", lambda d: d["routes"].remove(PATH), route_problems, "seven pages"),
    ("the page at another path", _replace("page_module", f'path: "{PATH}"', 'path: "/boards"'), module_problems, "its path"),
    ("the page for both trees", _replace("page_module", 'trees: ["govuk"]', 'trees: ["default", "govuk"]'), module_problems, "GOV.UK tree alone"),
    (
        "the page answering DELETE",
        _replace("page_module", 'methods: ["GET", "POST"]', 'methods: ["GET", "POST", "DELETE"]'),
        module_problems,
        "GET and POST alone",
    ),
    ("a write's test retitled", _replace("write_test", 'it("BD24: ', 'it("BD42: '), scenario_problems, "titled BD24"),
    (
        "a write row naming the read's test",
        _in_section("| `boards-write.test.ts`, `keyboard/boards.spec.ts` |", "| `boards.test.ts`, `keyboard/boards.spec.ts` |"),
        scenario_problems,
        "BD28 names no page test",
    ),
    (
        "no unshare left unsaid",
        _in_section("there is no unshare route, and none is asked for here", "sharing is for good"),
        prose_problems,
        "no unshare",
    ),
    (
        "the share route without the drawing rights",
        _app("dependencies=_DRAWS)", "dependencies=_READS_BOARDS)", '/boards/{board_id}/share", '),
        write_problems,
        "share_board no longer asks the drawing rights",
    ),
    (
        "the delete route at the Viewer level",
        _app("InvestigationEditorDep", "InvestigationViewerDep", "async def delete_board("),
        write_problems,
        "delete_board no longer stands behind",
    ),
    (
        "the delete route not asking for the creator",
        _app("boards.own_board(", "boards.board(", "async def delete_board("),
        write_problems,
        "delete_board no longer asks for the board's creator",
    ),
    (
        "the rights asked the other way round",
        _app(
            "Right.DRAW_ON_BOARDS)), Depends(require_right(Right.INVESTIGATE))]",
            "Right.INVESTIGATE)), Depends(require_right(Right.DRAW_ON_BOARDS))]",
            "_DRAWS = [",
        ),
        write_problems,
        "draw_on_boards then investigate",
    ),
    (
        "an unshare route added",
        _app(
            "@app.delete(",
            '@app.post("/v1/investigations/{investigation_id}/boards/{board_id}/unshare")\n'
            "async def unshare_board() -> None: ...\n\n\n@app.delete(",
            "async def share_board(",
        ),
        write_problems,
        "has an unshare route",
    ),
    (
        "the new board's model taking extra fields",
        _model(
            "Board",
            'or from a selection on the canvas."""\n\n    model_config = ConfigDict(extra="forbid")\n',
            'or from a selection on the canvas."""\n\n    model_config = ConfigDict()\n',
        ),
        write_problems,
        "forbids an extra field",
    ),
    ("the form passed through", _replace("page_module", 'json: { name, start: "blank" }', "json: req.body"), write_problems, "passes a form through"),
    (
        "the refusal's words changed",
        _replace("words", '"You cannot make boards in this case"', '"You are not allowed to make boards"'),
        write_problems,
        "does not hold the ruled words",
    ),
    (
        "the banner's words changed",
        _replace("words", '"The board was deleted. What was drawn on it stays in the case."', '"The board was deleted."'),
        write_problems,
        "does not hold the ruled words",
    ),
    ("the page under another row", _replace("page_module", f'id: "{ROW}"', 'id: "cases-and-views"'), module_problems, "its id"),
    (
        "the page left out of the table of pages",
        lambda d: d.update(page_list=d["page_list"].replace("boardsPage", "somethingElse")),
        module_problems,
        "does not hold the boards page",
    ),
    # The census: a field added to a route's model, a name the page lists that the model lacks, a left-out name dropped from the
    # scenario, a field drawn and left out at once, the wire lists not the models' own.
    (
        "a field added to the board's model",
        _model("Board", "    shared: bool = False\n", "    shared: bool = False\n    pinned: bool = False\n"),
        census_problems,
        "Board.pinned is neither drawn",
    ),
    (
        "a field added to the drawn assertion",
        _model("DrawnAssertion", '    icon: str | None = Field(default=None, title="DrawnIcon")\n', '    icon: str | None = Field(default=None, title="DrawnIcon")\n    colour: str | None = None\n'),
        census_problems,
        "DrawnAssertion.colour is neither drawn",
    ),
    (
        "a census name for no field",
        _replace("words", '"grading_grades", "may_promote"]', '"grading_grades", "may_promote", "may_share"]'),
        census_problems,
        "BoardOpened.may_share, which the model does not have",
    ),
    (
        "a left-out field dropped from the scenario's sentence",
        _in_section("`ceiling`, ", ""),
        census_problems,
        "left-out sentence names",
    ),
    (
        "a field both drawn and left out",
        _replace("words", 'Grading: { drawn: ["scheme", "source", "intelligence", "handling"], checked: [], left: [] }', 'Grading: { drawn: ["scheme", "source", "intelligence", "handling"], checked: [], left: ["scheme"] }'),
        census_problems,
        "in two of its lists",
    ),
    (
        "a field never on the wire read as required",
        _replace("words", 'export const NOT_SENT: readonly string[] = ["Edge.weight_components"]', "export const NOT_SENT: readonly string[] = []"),
        census_problems,
        "never on the wire",
    ),
    (
        "the model's exclude taken away",
        _model("Edge", "weight_components: WeightComponents | None = Field(default=None, exclude=True)", "weight_components: WeightComponents | None = Field(default=None)"),
        census_problems,
        "never on the wire",
    ),
    (
        "a field that may be absent read as required",
        _replace("words", 'export const MAY_BE_ABSENT: readonly string[] = ["Provenance.drawn", "Provenance.gazetteer"]', 'export const MAY_BE_ABSENT: readonly string[] = ["Provenance.gazetteer"]'),
        census_problems,
        "MAY_BE_ABSENT",
    ),
    (
        "the model's serializer no longer leaving out the drawn assertion",
        _model("Provenance", 'data.pop("drawn", None)', "pass"),
        census_problems,
        "MAY_BE_ABSENT",
    ),
    (
        "a start added to the model",
        _source(BOARDS, 'BoardStart = Literal["blank", "view", "selection"]', 'BoardStart = Literal["blank", "view", "selection", "drawing"]'),
        values_problems,
        "BoardStart holds",
    ),
    (
        "a provenance state added to the model",
        _source(DOMAIN, '    UNRESOLVED = "unresolved"\n', '    UNRESOLVED = "unresolved"\n    WITHDRAWN = "withdrawn"\n'),
        values_problems,
        "ProvenanceState holds",
    ),
    (
        "a checked field dropped from the scenario's sentence",
        _in_section("of `Edge`, `id` (named once, and as drawn when it carries an assertion); ", ""),
        census_problems,
        "checked sentence names",
    ),
    (
        "a field added to the cap's refusal",
        _model("LimitExceeded", "    would_be: int\n", "    would_be: int\n    hint: str = \"\"\n"),
        census_problems,
        "LimitExceeded.hint is neither drawn",
    ),
    (
        "a basis added to the model's links",
        _in_class(DOMAIN, "Edge", 'basis: Literal["direct", "probabilistic"] | None = None', 'basis: Literal["direct", "probabilistic", "asserted"] | None = None'),
        values_problems,
        "Edge.basis holds",
    ),
    (
        "a cap kind added to the model",
        _source(WORKING_SET, 'cap_kind: Literal["nodes", "edges", "pairs"]', 'cap_kind: Literal["nodes", "edges", "pairs", "hops"]'),
        values_problems,
        "LimitExceeded.cap_kind holds",
    ),
    (
        "a cap option dropped from the page",
        _replace("words", 'export const OPTIONS = ["save_as_view", "filter", "promote_to_batch"] as const;', 'export const OPTIONS = ["save_as_view", "filter"] as const;'),
        values_problems,
        "the page's OPTIONS",
    ),
    # No source until GG4b.
    (
        "the source note claimed as drawn again",
        _replace("words", '"original_grading", "source_note", "source_document"', '"original_grading", "source_document"'),
        source_problems,
        "DrawnAssertion.source_note is not left out",
    ),
    (
        "the drawn table's source column back",
        _replace("words", 'drawnColumns: ["Item", "Type", "Marking", "Grading"],', 'drawnColumns: ["Item", "Type", "Marking", "Grading", "Source note"],'),
        source_problems,
        "the page's drawnColumns",
    ),
    (
        "the links table's source column back",
        _replace("words", '"Drawn or loaded", "Marking", "Grading"],', '"Drawn or loaded", "Marking", "Grading", "Source note"],'),
        source_problems,
        "the page's linkColumns",
    ),
    (
        "the words for a missing note back",
        _replace("words", "  drawnNote:", '  noNote: "No note given",\n  drawnNote:'),
        source_problems,
        "still holds the words noNote",
    ),
    (
        "the loaded link's source words back",
        _replace("words", "  drawnNote:", '  loadedSource: "A dataset this case reads",\n  drawnNote:'),
        source_problems,
        "still holds the words loadedSource",
    ),
    (
        "the scenario's drawn columns ending in a source",
        _in_section("columns Item, Type, Marking, Grading;", "columns Item, Type, Marking, Grading, Source note;"),
        source_problems,
        "BD3 does not say",
    ),
    (
        "the scenario's link columns ending in a source",
        _in_section("Drawn or loaded, Marking, Grading)", "Drawn or loaded, Marking, Grading, Source note)"),
        source_problems,
        "BD4 does not say",
    ),
    (
        "the reason for leaving the source out dropped",
        _in_section("(left out until GG4b", "(left out"),
        source_problems,
        "left out until GG4b",
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
