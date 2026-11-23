"""Scenario MS: the Studio's Model step as a server-rendered page, with the expected version on the draft's save and
discard (slice IS2a; ADR-152 decision 12, "each rebuilt screen's acceptance scenario is written first").

**There is no React Model step to read the behaviour from**: `ModelTab.tsx` is a sentence about the domain model and a
paragraph saying the rest comes later, with no type list, no form, no fetch and no save. So the scenario is written
against the decision records (ADR-140 Amendment 22 items 3 and 4; ADR-152 decisions 6, 7, 12 and 13; X5 and X7), the
prototype's Model step and the owner's rulings of 21 and 23 November 2026 (`slices/IS2a.md` carries them; `RULINGS.md`
holds them). The owner's message of 23 November was cut off in point (d): the scenario takes it as written and adds the
cases a reader without the right, a dataset not reached and a dataset that does not exist.

`spec/08_ACCEPTANCE_SCENARIOS.md` ("Scenario MS") holds one row per behaviour. Each row names (a) what it was read from,
by path and by words that must be in that file today, and (b) the test that proves it, by id: the page test
`apps/pages/test/default/model-step.test.ts` (MS1 and MS9 to MS19, a test titled with the id) or the Conduit's
`tests/services/api/test_model_draft_expected_version.py` (MS2 to MS8, a test whose name begins with the id). This file
holds the document, the section of `spec/09_INGEST_STUDIO.md` (1.3), the two tests, the page's own files and the two
`apps/pages/FUNCTIONS.yaml` rows in step:

* a scenario with no test, or a test with no scenario -> `test_every_scenario_has_a_test_and_back`
* a row whose cited words are not in the file it cites -> `test_every_row_cites_words_that_are_in_the_source`
* one of the owner's points (a) to (h) with no row -> `BRIEF`, in `problems`
* the section of spec/09 that does not say what the page does, who may act and which words -> `test_spec_09_says_what_the_page_does`
* the FUNCTIONS rows left without the scenarios, or given a GOV.UK route -> `test_the_function_rows_name_the_scenarios`
* "recipe" or "target model" in the page's words or template -> `test_the_page_s_words_never_say_recipe`
* the words gates (`ui_words_check`, `colour_drift_check`, `no_branches_check`, `design_check`) not reading the page's own
  files -> `test_each_gate_reads_the_page_s_own_files`

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and copies two of
them (the page's words and its template) into a temporary folder to plant a violation in; it never writes into the
repository. The files, from the repository's root: `OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md`,
`OspreyFlow_Build/spec/09_INGEST_STUDIO.md`, `OspreyFlow_Build/spec/03_CONDUIT_MIDDLEWARE.md`,
`OspreyFlow_Build/spec/06_DECISIONS.md`, `OspreyFlow_Build/spec/ingest_studio_redesign/ingest_studio_prototype.html`,
`OspreyFlow_Build/process/lanes/v062/RULINGS.md`, `OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py`,
`OspreyFlow_Build/tests/services/api/test_model_draft_expected_version.py`, and under `OspreyFlow_Core`:
`apps/pages/FUNCTIONS.yaml`, `apps/pages/test/default/model-step.test.ts`, `apps/pages/server/model.ts`,
`apps/pages/server/pageList.ts`, `apps/pages/server/conduit.ts`, `apps/pages/server/views/modelWords.ts`,
`apps/pages/server/views/studioWords.ts`, `apps/pages/tree-default/studio/model.njk`,
`services/api/target_models.py`, `services/ingest/recipe_rules.py`,
`apps/workspace/src/ingest/studio/{vocabulary.ts,ModelTab.tsx}`.

Every planted fault is the real inputs with one thing changed (rule 15), run through the same `problems` the real inputs
go through, which finds nothing in them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from tools import colour_drift_check, design_check, no_branches_check, ui_words_check
from tools.layout import PAGES_COPY_ROOTS

BUILD = Path(__file__).resolve().parents[2]
ROOT = BUILD.parent
CORE = ROOT / "OspreyFlow_Core"
PAGES = CORE / "apps" / "pages"
SPEC_08 = BUILD / "spec" / "08_ACCEPTANCE_SCENARIOS.md"
SPEC_09 = BUILD / "spec" / "09_INGEST_STUDIO.md"
FUNCTIONS = PAGES / "FUNCTIONS.yaml"
FUNCTIONS_TEST = BUILD / "tests" / "glass_trees" / "test_functions_yaml.py"
PAGE_TEST = PAGES / "test" / "default" / "model-step.test.ts"
CONDUIT_TEST = BUILD / "tests" / "services" / "api" / "test_model_draft_expected_version.py"
ROUTE = PAGES / "server" / "model.ts"
PAGE_LIST = PAGES / "server" / "pageList.ts"
PLACES_FILE = PAGES / "server" / "views" / "studioWords.ts"
WORDS = PAGES / "server" / "views" / "modelWords.ts"
TEMPLATE = PAGES / "tree-default" / "studio" / "model.njk"

SECTION = "## Scenario MS"
ID = re.compile(r"^MS\d+$")
PAGE_TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')(MS\d+): """)
CONDUIT_NAME = re.compile(r"^(?:async )?def test_(ms\d+)_", re.MULTILINE)
PAGE_NAME = "model-step.test.ts"
CONDUIT_NAME_OF_FILE = "test_model_draft_expected_version.py"
ROWS_OF_FILE = {PAGE_NAME: "page", CONDUIT_NAME_OF_FILE: "conduit"}
FUNCTION_ROWS = ("studio-model-text", "studio-model-proposals")

#: What each of the owner's points is, by what it asks: a point with no scenario is one nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "(a) a type record carries its class, identifiers, matching rule and properties with the indexed flag": (
        "MS1",
        "MS2",
        "MS3",
    ),
    "(b) only the draft's creator can save into it, replace it or discard it; anyone else is told nothing": (
        "MS4",
        "MS11",
    ),
    "(c) a save or a delete carries the expected version; a stale one is refused; typing is kept": (
        "MS5",
        "MS6",
        "MS7",
        "MS9",
        "MS10",
    ),
    "(d) no right, a dataset not reached and one that does not exist: one refusal, no content, count or id": (
        "MS8",
        "MS12",
    ),
    "(e) the step works with scripts off: lists as tables, actions as forms": ("MS14",),
    "(f) a failure to read or save is an alert, never an empty model": ("MS13",),
    "(g) the on-screen word is Pipeline, never recipe": ("MS15",),
    "(h) planted faults for each check, red first": ("MS19",),
    "the Conduit asked as the person, a post needs its token, signed out is sent to sign-in": ("MS16",),
    "every control a native tab stop with a label (rule 13)": ("MS17",),
    "the fake Conduit refuses what the real one refuses (rule 15)": ("MS18",),
}

#: A row that is a duty of the tests with no counterpart in a source says so, with a reason; no other row may.
PAGE_ONLY = {"MS18", "MS19"}
NONE_PREFIX = "none:"
#: The words the page must never say: the screens say Pipeline and domain model.
FORBIDDEN_WORDS = re.compile(r"recipe|target\s+model", re.IGNORECASE)

SPEC_09_HEADING = "### 1.3 The Model step"
#: What spec/09 section 1.3 must say, and why.
SPEC_09_NEEDS: tuple[tuple[str, str], ...] = (
    ("There is no React Model step", "that there is no React screen to copy"),
    ("Scenario MS", "the scenario that tests it"),
    ("expected version", "that a save and a discard carry the expected version"),
    ("a stale one is refused", "that a stale version is refused"),
    ("only its creator", "that only the draft's creator saves into, replaces or discards it"),
    ("matching rule", "that a type carries its matching rule"),
    ("indexed", "that a property carries an indexed flag"),
    ("role=\"alert\"", "that a failure is said in an alert"),
    ("never drawn as an empty model", "that a failure is never an empty model"),
    ("scripts off", "that the page works with scripts off"),
    ("Pipeline", "that the on-screen word is Pipeline"),
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def section_of(spec: str) -> str:
    """Scenario MS's text, to the next `## ` heading; empty when there is no such section."""
    start = spec.find(SECTION)
    if start < 0:
        return ""
    section = spec[start:]
    end = section.find("\n## ", len(SECTION))
    return section if end < 0 else section[:end]


def rows_of(spec: str) -> dict[str, list[str]]:
    """Scenario MS's table rows by id, each as its five cells; `{}` when there is no such section."""
    out: dict[str, list[str]] = {}
    for line in section_of(spec).splitlines():
        cells = (
            [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("| MS") else []
        )
        if len(cells) == 5 and ID.match(cells[0]):
            out[cells[0]] = cells
    return out


def page_titles(text: str) -> set[str]:
    return set(PAGE_TITLE.findall(text))


def conduit_titles(text: str) -> set[str]:
    return {name.upper() for name in CONDUIT_NAME.findall(text)}


def cited(cell: str) -> list[tuple[str, list[str]]]:
    """`path` then its quoted words, for each path a source cell cites (paths from the repository's root)."""
    return [
        (path, re.findall(r'"([^"]+)"', words))
        for path, words in re.findall(r'`([^`]+)`((?:\s*;?\s*"[^"]+")*)', cell)
    ]


def spec_09_section(spec: str) -> str:
    start = spec.find(SPEC_09_HEADING)
    if start < 0:
        return ""
    end = spec.find("\n## ", start)
    return spec[start:] if end < 0 else spec[start:end]


def problems(
    spec_08: str,
    spec_09: str,
    page_test: str,
    conduit_test: str,
    sources: dict[str, str],
    functions: list[dict[str, str]],
    words: dict[str, str],
) -> list[str]:
    """Every fault in the scenarios, the section of spec/09, the two tests, the cited words, the function rows and the
    page's own words, in words."""
    found: list[str] = []
    rows = rows_of(spec_08)
    if not rows:
        return [f"spec/08 has no `{SECTION}` section with scenario rows"]
    on_page, on_conduit = page_titles(page_test), conduit_titles(conduit_test)
    for sid, cells in rows.items():
        _, behaviour, source, test, tree = cells
        if tree != "Default":
            found.append(f"{sid} runs on {tree!r}, not on the Default tree")
        if not behaviour:
            found.append(f"{sid} says nothing of the behaviour")
        name = test.strip("` ")
        if name not in ROWS_OF_FILE:
            found.append(f"{sid} names the test {name!r}, not {PAGE_NAME!r} or {CONDUIT_NAME_OF_FILE!r}")
        elif sid not in (on_page if name == PAGE_NAME else on_conduit):
            found.append(f"{sid} names {name}, which has no test titled {sid}")
        if source.startswith(NONE_PREFIX):
            if sid not in PAGE_ONLY:
                found.append(f"{sid} claims no source, but only {sorted(PAGE_ONLY)} may")
            elif len(source) < len(NONE_PREFIX) + 30:
                found.append(f"{sid} claims no source without saying why")
            continue
        cites = cited(source)
        if not cites:
            found.append(f"{sid} cites no source")
        for path, quoted in cites:
            text = sources.get(path)
            if text is None:
                found.append(f"{sid} cites {path}, which is not a file this test reads")
                continue
            if not quoted:
                found.append(f"{sid} cites {path} with no words from it")
            for phrase in quoted:
                if norm(phrase) not in norm(text):
                    found.append(f"{sid} cites {path} for {phrase!r}, which is not in it today")
    for orphan in sorted((on_page | on_conduit) - set(rows)):
        found.append(f"a test for {orphan} is no scenario of spec/08")
    for sid, cells in rows.items():
        if sid not in on_page | on_conduit:
            found.append(f"{sid} has no test")
        elif sid in on_page and cells[3].strip("` ") != PAGE_NAME:
            found.append(f"{sid} is titled in {PAGE_NAME} but its row names {cells[3]!r}")
        elif sid in on_conduit and cells[3].strip("` ") != CONDUIT_NAME_OF_FILE:
            found.append(f"{sid} is named in {CONDUIT_NAME_OF_FILE} but its row names {cells[3]!r}")
    for line, ids in BRIEF.items():
        for sid in ids:
            if sid not in rows:
                found.append(f"the brief's line {line!r} needs {sid}, which spec/08 does not have")
    for sid in sorted(set(rows) - {sid for ids in BRIEF.values() for sid in ids}):
        found.append(f"{sid} answers no line of the brief")
    section = section_of(spec_08)
    if FORBIDDEN_WORDS.search(re.sub(r"`[^`]*`|\"[^\"]*\"", "", section)):
        found.append('Scenario MS says "recipe" or "target model": the screens say "Pipeline" and "domain model"')
    if "cut off" not in section:
        found.append("Scenario MS does not say that the owner's point (d) was cut off and what it added")

    # spec/09's section: what the page does, who may act, which words
    text = norm(spec_09_section(spec_09))
    if not text:
        found.append("spec/09 has no section 1.3 on the Model step")
    else:
        for need, why in SPEC_09_NEEDS:
            if need not in text:
                found.append(f"spec/09 section 1.3 does not say {why} (looked for {need!r})")

    # the FUNCTIONS rows
    by_id = {row["id"]: row for row in functions}
    for function_id in FUNCTION_ROWS:
        row = by_id.get(function_id)
        if row is None:
            found.append(f"FUNCTIONS.yaml lacks the {function_id} row")
            continue
        have = sorted(part.strip() for part in row["scenario"].split(",") if part.strip())
        if have != sorted(rows):
            found.append(f"FUNCTIONS row {function_id} names scenarios {have}, not {sorted(rows)}")
        if row["route"]:
            found.append(f"FUNCTIONS row {function_id} has a GOV.UK route: this slice builds the Default tree only")

    # the page's own words
    for name, body in words.items():
        for hit in FORBIDDEN_WORDS.finditer(body):
            found.append(f"{name} says {hit.group(0)!r}: the screens say Pipeline and domain model")
    return found


# ---------------------------------------------------------------------------- the real inputs


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def resolve(path: str) -> Path | None:
    """A cited path is written from `OspreyFlow_Core` (a Glass or Conduit file) or from the Build folder."""
    for base in (CORE, BUILD):
        if (base / path).is_file():
            return base / path
    return None


Inputs = tuple[str, str, str, str, dict[str, str], list[dict[str, str]], dict[str, str]]


def real() -> Inputs:
    spec_08 = read(SPEC_08)
    wanted: set[str] = set()
    for cells in rows_of(spec_08).values():
        wanted.update(path for path, _ in cited(cells[2]))
    sources = {path: read(found) for path in wanted if (found := resolve(path)) is not None}
    functions = yaml.safe_load(read(FUNCTIONS))["functions"]
    words = {path.name: read(path) for path in (WORDS, TEMPLATE) if path.is_file()}
    page_test = read(PAGE_TEST) if PAGE_TEST.is_file() else ""
    conduit_test = read(CONDUIT_TEST) if CONDUIT_TEST.is_file() else ""
    return spec_08, read(SPEC_09), page_test, conduit_test, sources, functions, words


def test_there_is_a_scenario_ms_in_spec_08() -> None:
    spec_08, *_ = real()
    assert SECTION in spec_08, "spec/08 has no Scenario MS for the Studio's Model step"
    assert len(rows_of(spec_08)) == len({sid for ids in BRIEF.values() for sid in ids})


def test_the_real_inputs_have_no_problem() -> None:
    assert problems(*real()) == []


def test_every_scenario_has_a_test_and_back() -> None:
    spec_08, _, page_test, conduit_test, *_ = real()
    assert PAGE_TEST.is_file(), "the page test is missing"
    assert CONDUIT_TEST.is_file(), "the Conduit test is missing"
    assert set(rows_of(spec_08)) == page_titles(page_test) | conduit_titles(conduit_test)
    assert not page_titles(page_test) & conduit_titles(conduit_test)


def test_every_row_cites_words_that_are_in_the_source() -> None:
    spec_08, _, _, _, sources, *_ = real()
    for sid, cells in rows_of(spec_08).items():
        if cells[2].startswith(NONE_PREFIX):
            continue
        for path, quoted in cited(cells[2]):
            assert path in sources, f"{sid} cites {path}, which is not there"
            for phrase in quoted:
                assert norm(phrase) in norm(sources[path]), f"{sid}: {phrase!r} is not in {path}"


def test_spec_09_says_what_the_page_does() -> None:
    _, spec_09, *_ = real()
    section = spec_09_section(spec_09)
    assert section, "spec/09 has no section 1.3 on the Model step"
    for need, why in SPEC_09_NEEDS:
        assert need in norm(section), f"spec/09 section 1.3 does not say {why}"


def test_the_function_rows_name_the_scenarios() -> None:
    spec_08, _, _, _, _, functions, _ = real()
    by_id = {r["id"]: r for r in functions}
    known = read(FUNCTIONS_TEST)
    listed = known[
        known.index("KNOWN_WITHOUT_SCENARIO") : known.index("}", known.index("KNOWN_WITHOUT_SCENARIO"))
    ]
    for function_id in FUNCTION_ROWS:
        row = by_id[function_id]
        assert row["scenario"].strip(), f"{function_id} has no scenario"
        assert row["route"] == "", "the GOV.UK tree's route stays empty: this is the Default tree's page"
        # The list of functions with no scenario may only shrink (test_functions_yaml.py): these have one now.
        assert f'"{function_id}"' not in listed
    assert set(rows_of(spec_08))


def test_the_page_is_the_function_row_and_is_registered() -> None:
    route = read(ROUTE)
    assert 'id: "studio-model-text"' in route
    assert 'path: "/studio/model"' in route
    assert 'methods: ["GET", "POST"]' in route
    assert "studioModel" in read(PAGE_LIST)
    # The Model place is a page of this service now: its link is the page's, not the workspace's.
    assert 'id: "model", label: "1 Model", path: "/studio/model"' in read(PLACES_FILE)


def test_the_page_s_words_never_say_recipe() -> None:
    words = real()[6]
    assert set(words) == {WORDS.name, TEMPLATE.name}, "the page's words or template is missing"
    assert not [name for name, body in words.items() if FORBIDDEN_WORDS.search(body)]


def test_the_page_reads_the_studio_s_own_words_for_the_model() -> None:
    """The packs' names are the Studio's own (`studioWords.ts`'s `PACKS`) and the screens' word for a pipeline is the
    Studio's (`vocabulary.ts`: a recipe is a pipeline): the page's words use the first and not the second's old word."""
    words = read(WORDS)
    studio = read(PLACES_FILE)
    for name, label in re.findall(r'\{ name: "(\w+)", label: "([^"]+)" \}', studio):
        assert name in {"fibo", "niem", "stix"}
        assert label  # the page draws these through `modelInWords`, which is the Studio's
    assert "modelInWords" in words or "PACKS" in words
    assert "pipeline" in words.lower()


# ---------------------------------------------------------------------------- planted faults


def planted() -> Inputs:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = real()
    return spec_08, spec_09, page_test, conduit_test, dict(sources), [dict(r) for r in functions], dict(words)


def test_a_scenario_row_removed_is_caught() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    for gone, where in (("MS7", "conduit"), ("MS13", "page")):
        kept = "\n".join(line for line in spec_08.splitlines() if not line.startswith(f"| {gone} |"))
        found = problems(kept, spec_09, page_test, conduit_test, sources, functions, words)
        assert any(f"a test for {gone} is no scenario" in p for p in found), (where, found)
        assert any("names scenarios" in p for p in found)


def test_a_page_test_renamed_is_caught() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    changed = re.sub(r'it\(\s*"MS12: ', 'it("dropped: ', page_test)
    assert changed != page_test
    found = problems(spec_08, spec_09, changed, conduit_test, sources, functions, words)
    assert any("MS12 names model-step.test.ts, which has no test titled MS12" in p for p in found)


def test_a_conduit_test_renamed_is_caught() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    changed = re.sub(r"def test_ms6_", "def test_dropped_", conduit_test)
    assert changed != conduit_test
    found = problems(spec_08, spec_09, page_test, changed, sources, functions, words)
    assert any(
        "MS6 names test_model_draft_expected_version.py, which has no test titled MS6" in p
        for p in found
    )


def test_a_row_naming_the_other_test_file_is_caught() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    changed = re.sub(
        r"(\| MS5 \|[^\n]*\|) `test_model_draft_expected_version.py` \|",
        r"\1 `model-step.test.ts` |",
        spec_08,
    )
    assert changed != spec_08
    found = problems(changed, spec_09, page_test, conduit_test, sources, functions, words)
    assert any("MS5" in p for p in found)


def test_cited_words_that_are_not_in_the_source_are_caught() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    path = "services/api/target_models.py"
    assert path in sources
    sources[path] = sources[path].replace("you meant your draft's version", "you were thinking of")
    found = problems(spec_08, spec_09, page_test, conduit_test, sources, functions, words)
    assert any("MS7 cites" in p and "you meant your draft's version" in p for p in found)


def test_a_source_that_is_not_read_is_caught() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    sources.pop("spec/ingest_studio_redesign/ingest_studio_prototype.html")
    found = problems(spec_08, spec_09, page_test, conduit_test, sources, functions, words)
    assert any("MS1 cites" in p and "prototype" in p for p in found)


def test_a_row_may_claim_no_source_only_where_the_tests_alone_have_the_duty() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    changed = re.sub(
        r"(\| MS4 \| [^|]*\|)[^|]*\|",
        r"\1 none: nobody reads the creator check from anywhere, so this cites none |",
        spec_08,
    )
    assert changed != spec_08
    found = problems(changed, spec_09, page_test, conduit_test, sources, functions, words)
    assert any("MS4 claims no source" in p for p in found)


def test_a_row_on_another_tree_is_caught() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    changed = re.sub(r"(\| MS1 \|[^\n]*\|) Default \|", r"\1 GOV.UK |", spec_08)
    assert changed != spec_08
    found = problems(changed, spec_09, page_test, conduit_test, sources, functions, words)
    assert any("MS1 runs on 'GOV.UK'" in p for p in found)


@pytest.mark.parametrize(
    "need", [need for need, _ in SPEC_09_NEEDS], ids=[why for _, why in SPEC_09_NEEDS]
)
def test_spec_09_without_a_sentence_it_must_say_is_caught(need: str) -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    start = spec_09.find(SPEC_09_HEADING)
    assert start >= 0
    end = spec_09.find("\n## ", start)
    section = spec_09[start:end]
    assert need in norm(section), f"the real section lacks {need!r}"
    changed = spec_09[:start] + norm(section).replace(need, "XXXX") + spec_09[end:]
    found = problems(spec_08, changed, page_test, conduit_test, sources, functions, words)
    assert any(f"looked for {need!r}" in p for p in found)
    removed = spec_09.replace(SPEC_09_HEADING, "### 1.3 Something else")
    assert any(
        "no section 1.3" in p
        for p in problems(spec_08, removed, page_test, conduit_test, sources, functions, words)
    )


def test_a_function_row_with_a_govuk_route_or_no_scenario_is_caught() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    for row in functions:
        if row["id"] == "studio-model-text":
            row["route"] = "/studio/model"
    assert any(
        "has a GOV.UK route" in p
        for p in problems(spec_08, spec_09, page_test, conduit_test, sources, functions, words)
    )
    for row in functions:
        if row["id"] in FUNCTION_ROWS:
            row["route"] = ""
            row["scenario"] = ""
    found = problems(spec_08, spec_09, page_test, conduit_test, sources, functions, words)
    assert sum("names scenarios []" in p for p in found) == len(FUNCTION_ROWS)


@pytest.mark.parametrize(
    "phrase", ["recipe", "Recipe", "A recipe draft", "the target model", "Target model"]
)
def test_a_forbidden_word_in_the_page_is_caught(phrase: str) -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    for name in (WORDS.name, TEMPLATE.name):
        changed = dict(words)
        changed[name] = words[name] + f"\n<h3>{phrase}</h3>\n"
        found = problems(spec_08, spec_09, page_test, conduit_test, sources, functions, changed)
        assert any(name in p and "Pipeline" in p for p in found), (name, phrase, found)


def test_a_scenario_that_says_recipe_is_caught() -> None:
    spec_08, spec_09, page_test, conduit_test, sources, functions, words = planted()
    changed = re.sub(r"(\| MS15 \| )", r"\1A recipe is shown. ", spec_08, count=1)
    assert changed != spec_08
    found = problems(changed, spec_09, page_test, conduit_test, sources, functions, words)
    assert any('says "recipe" or "target model"' in p for p in found)


# ---------------------------------------------------------------------------- the gates read this page's files


@pytest.fixture
def tmp_core(tmp_path: Path) -> Path:
    """A `OspreyFlow_Core` holding the page's own two files at their real places, and nothing else."""
    core = tmp_path / "OspreyFlow_Core"
    for root in PAGES_COPY_ROOTS:
        (core / root).mkdir(parents=True, exist_ok=True)
    for source in (WORDS, TEMPLATE):
        target = core / source.relative_to(CORE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(read(source), encoding="utf-8")
    return core


def _rel(path: Path, core: Path) -> str:
    return path.relative_to(core).as_posix()


#: Each gate, the violation it must find, written the way each of the page's two files writes a string.
PLANTS = {
    WORDS: {
        "ui_words": '\nexport const planted = "Review the target model";\n',
        "colour_drift": '\nexport const planted = "rgba(12, 34, 56, 0.5)";\n',
        "no_branches": "\nexport const branchNodes = () => [];\n",
    },
    TEMPLATE: {
        "ui_words": "\n<p>Review the target model</p>\n",
        "colour_drift": '\n<svg><path fill="#ff00aa" d="M0 0"/></svg>\n',
        "no_branches": "\n<li>Branch of {{ name }}</li>\n",
    },
}


def _plant(core: Path, source: Path, gate: str) -> Path:
    target = core / source.relative_to(CORE)
    target.write_text(read(target) + PLANTS[source][gate], encoding="utf-8")
    return target


def _words(
    core: Path, capsys: pytest.CaptureFixture[str], mp: pytest.MonkeyPatch
) -> tuple[int, str]:
    none = core / "none"
    mp.setattr(ui_words_check, "PAGES_ROOTS", tuple(core / r for r in PAGES_COPY_ROOTS))
    for name in ("GLASS_SRC", "DESIGN_PACKAGE", "SHARED_SRC"):
        mp.setattr(ui_words_check, name, none)
    code = ui_words_check.main()
    return code, capsys.readouterr().out


def _colour(
    core: Path, capsys: pytest.CaptureFixture[str], mp: pytest.MonkeyPatch
) -> tuple[int, str]:
    roots = tuple((core / r, frozenset()) for r in PAGES_COPY_ROOTS)
    mp.setattr(colour_drift_check, "SCANNED", roots)
    mp.setattr(colour_drift_check, "CORE", core)
    mp.setattr(colour_drift_check, "PAGES_ROOTS", tuple(core / r for r in PAGES_COPY_ROOTS))
    code = colour_drift_check.main()
    captured = capsys.readouterr()
    return code, captured.out + captured.err


@pytest.mark.parametrize("source", [WORDS, TEMPLATE], ids=lambda p: p.name)
def test_the_words_gate_reads_the_page_s_own_files(
    source: Path,
    tmp_core: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert source.is_file(), f"{source.name} is not written yet"
    assert _words(tmp_core, capsys, monkeypatch)[0] == 0
    target = _plant(tmp_core, source, "ui_words")
    code, out = _words(tmp_core, capsys, monkeypatch)
    assert code == 1, out
    assert f"{_rel(target, tmp_core)}:" in out, out


@pytest.mark.parametrize("source", [WORDS, TEMPLATE], ids=lambda p: p.name)
def test_the_colour_gate_reads_the_page_s_own_files(
    source: Path,
    tmp_core: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert source.is_file(), f"{source.name} is not written yet"
    assert _colour(tmp_core, capsys, monkeypatch)[0] == 0
    target = _plant(tmp_core, source, "colour_drift")
    code, out = _colour(tmp_core, capsys, monkeypatch)
    assert code == 1, out
    assert f"{_rel(target, tmp_core)}:" in out, out


@pytest.mark.parametrize("source", [WORDS, TEMPLATE], ids=lambda p: p.name)
def test_the_branches_gate_reads_the_page_s_own_files(source: Path, tmp_core: Path) -> None:
    assert source.is_file(), f"{source.name} is not written yet"

    def found() -> list[str]:
        files = no_branches_check.tree_files(tmp_core, no_branches_check.SCANNED)
        return [f[0] for f in no_branches_check.findings(files)]

    assert found() == []
    target = _plant(tmp_core, source, "no_branches")
    assert found() == [_rel(target, tmp_core)]


def test_the_design_detector_reads_the_page_s_template(
    tmp_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert TEMPLATE.is_file(), f"{TEMPLATE.name} is not written yet"
    roots = [tmp_core / r for r in PAGES_COPY_ROOTS]
    assert design_check.unexcused(design_check.detect(roots)) == []
    target = tmp_core / TEMPLATE.relative_to(CORE)
    target.write_text(
        read(target)
        + '\n<div class="card" style="border-left: 4px solid red; border-radius: 8px; padding: 8px 12px; '
        'background: var(--surface-raised)">A status</div>\n',
        encoding="utf-8",
    )
    found = design_check.unexcused(design_check.detect(roots))
    assert [(Path(f["file"]), f["antipattern"]) for f in found] == [(target, "side-tab")], found


def test_each_gate_reads_the_page_s_own_files() -> None:
    """The three roots the page's two files sit under are the roots the gates name (a gate that dropped one would
    read neither file)."""
    for source in (WORDS, TEMPLATE):
        root = next(r for r in PAGES_COPY_ROOTS if source.is_relative_to(CORE / r))
        assert root in {p.relative_to(CORE).as_posix() for p in ui_words_check.PAGES_ROOTS}
        assert root in {p.relative_to(CORE).as_posix() for p, _ in colour_drift_check.SCANNED}
        assert root in {Path(p).relative_to(CORE).as_posix() for p in design_check.SCANNED}
        assert root in no_branches_check.SCANNED
