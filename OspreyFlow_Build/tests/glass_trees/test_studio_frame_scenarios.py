"""Scenario S: the Ingest Studio's frame and its Releases screen (slice IS5a; ADR-152 decision 12,
"each rebuilt screen's acceptance scenario is written first, run against today's React screen,
then the page is built to pass it").

`spec/08_ACCEPTANCE_SCENARIOS.md` ("Scenario S") holds one row per behaviour of the React screen
the page rebuilds. Each row names (a) the React source it was read from, by path and by words that
must be in that file today, and (b) the page's test that proves it, by id; the Studio's rows run on
the Default tree. This file holds the three in step:

* the document, `FUNCTIONS.yaml`'s `studio-frame` and `studio-releases` rows, and the page tests
  are one list of ids
* a scenario with no page test, or a page test with no scenario
      -> `test_every_scenario_has_a_page_test_and_back`
* a row whose React words are not in the file it cites (a scenario written from memory, not from
  the screen) -> `test_every_row_cites_words_that_are_in_the_react_source`
* a line of the brief with no scenario -> `test_every_line_of_the_brief_has_a_scenario`
* the two FUNCTIONS rows left without their scenarios -> `test_the_function_rows_name_the_scenarios`
* the three keyboard cases and their scripts-off twins (rule 13)
      -> `test_the_keyboard_cases_are_in_the_pages_runner`

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only,
by path:
`OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md`,
`OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py`, and under `OspreyFlow_Core`:
`apps/pages/FUNCTIONS.yaml`, `apps/pages/test/default/studio-frame.test.ts`,
`apps/pages/test/default/studio-releases.test.ts`, `apps/pages/keyboard/studio-releases.spec.ts`,
and the React files a row cites (`apps/workspace/src/ingest/IngestStudio.tsx`,
`studio/ReadinessStrip.tsx`, `studio/rightsGate.tsx`, `releases/ReleasesTab.tsx`,
`releases/ReleasesTab.test.tsx`, `apps/workspace/keyboard/ingest-studio.spec.ts`,
`packages/glass-shared/src/ingest/releases/releasesApi.ts`).

Every planted fault is the real inputs with one thing changed (rule 15), run through the same
`problems` the real inputs go through, which finds nothing in them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

BUILD = Path(__file__).resolve().parents[2]
CORE = BUILD.parent / "OspreyFlow_Core"
SPEC = BUILD / "spec" / "08_ACCEPTANCE_SCENARIOS.md"
FUNCTIONS = CORE / "apps" / "pages" / "FUNCTIONS.yaml"
FUNCTIONS_TEST = BUILD / "tests" / "glass_trees" / "test_functions_yaml.py"

#: The three files a row's page test may be in, by the name a row cites.
PAGE_TESTS = {
    "studio-frame.test.ts": CORE / "apps" / "pages" / "test" / "default" / "studio-frame.test.ts",
    "studio-releases.test.ts": CORE
    / "apps"
    / "pages"
    / "test"
    / "default"
    / "studio-releases.test.ts",
    "keyboard/studio-releases.spec.ts": CORE
    / "apps"
    / "pages"
    / "keyboard"
    / "studio-releases.spec.ts",
}

SECTION = "## Scenario S"
ID = re.compile(r"^(SF\d+|SR\d+|SK\d+|SO\d+)$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')((?:SF|SR|SK|SO)\d+): """)

#: The scenarios the slice must have, by what the brief lists (each line of "What the React screen
#: does today").
#: A line of the brief with no scenario is a behaviour nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "no case open: the words": ("SF1",),
    "the dataset switch, its words and its refusal": ("SF2",),
    "the Working through the case line": ("SF3",),
    "the readiness strip, not live": ("SF4",),
    "the Needs-you reminder and its note, and the unread words": ("SF5",),
    "five tabs as links, typed text lost on a tab switch": ("SF6",),
    "the rights gate": ("SF7",),
    "the help overlay, typed text surviving it": ("SF8", "SK4"),
    "the Needs-you jump as a link carrying the request": ("SF9",),
    "a silent failure of the case list says words": ("SF10",),
    "access control on every frame route": ("SF11",),
    "Releases: no-dataset notice and intro copy": ("SR1",),
    "Releases: export fields, call, result words, CLI hint": ("SR2",),
    "Releases: a refused export, and one words for no such dataset and not allowed": ("SR3",),
    "Releases: export not allowed without its rights": ("SR4",),
    "Releases: per-file downloads from a route": ("SR5",),
    "Releases: the folder upload keeps its paths and drops the folder's name": ("SR6",),
    "Releases: Check, the plan's words": ("SR7",),
    "Releases: Import only after a clean check, drafts, nothing live": ("SR8",),
    "Releases: replace-own-draft with the version the check named": ("SR9",),
    "Releases: a refusal at the write goes on from a new check": ("SR10",),
    "Releases: import and its steps not allowed without their rights": ("SR11",),
    "Releases: CSRF on every POST, the upload's token first": ("SR12",),
    "Releases: the staged bundle, held by the session only": ("SR13",),
    "Releases: Check with no folder says words": ("SR14",),
    "Releases: the bundle in no log, address, cookie or page-data block": ("SR15",),
    "Releases: errors said as words, the words gates": ("SR16",),
    "the three keyboard cases": ("SK1", "SK2", "SK3"),
    "the same three with scripts off": ("SO1", "SO2", "SO3"),
}

#: A row that is a duty of the page with no counterpart in the React screen says so, with a
#: reason; no other row may.
PAGE_ONLY = {"SR12", "SR13", "SR15"}
NONE_PREFIX = "none:"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def section_of(spec: str) -> str:
    """Scenario S's text, to the next `## ` heading; empty when there is no such section."""
    start = spec.find(SECTION)
    if start < 0:
        return ""
    section = spec[start:]
    end = section.find("\n## ", len(SECTION))
    return section if end < 0 else section[:end]


def rows_of(spec: str) -> dict[str, list[str]]:
    """Scenario S's table rows by id, each as its five cells; `{}` when there is no such section."""
    section = section_of(spec)
    out: dict[str, list[str]] = {}
    for line in section.splitlines():
        cells = (
            [c.strip() for c in line.strip().strip("|").split("|")]
            if line.startswith("| S")
            else []
        )
        if len(cells) == 5 and ID.match(cells[0]):
            out[cells[0]] = cells
    return out


def titles_in(text: str) -> set[str]:
    return set(TITLE.findall(text))


def cited(cell: str) -> list[tuple[str, list[str]]]:
    """`path` then its quoted words, for each path a React-source cell cites."""
    return [
        (path, re.findall(r'"([^"]+)"', words))
        for path, words in re.findall(r'`([^`]+)`((?:\s*;?\s*"[^"]+")*)', cell)
    ]


def problems(
    spec: str, page_tests: dict[str, str], react: dict[str, str], functions: list[dict[str, str]]
) -> list[str]:
    """Every fault in the scenarios, the page tests, the React words they cite and the function
    rows, in words."""
    found: list[str] = []
    rows = rows_of(spec)
    if not rows:
        return [f"spec/08 has no `{SECTION}` section with scenario rows"]
    section = section_of(spec)
    if re.search(r"target\s+model", section, re.IGNORECASE):
        found.append('Scenario S says "target model": the screens say "domain model"')
    titled = {name: titles_in(text) for name, text in page_tests.items()}
    for sid, cells in rows.items():
        _, behaviour, source, page, tree = cells
        if tree != "Default":
            found.append(f"{sid} runs on {tree!r}, not on the Default tree")
        if not behaviour:
            found.append(f"{sid} says nothing of the behaviour")
        # (b) the page's test
        name = page.strip("` ")
        if name not in page_tests:
            found.append(
                f"{sid} names the page test {name!r}, which is not one of {sorted(page_tests)}"
            )
        elif sid not in titled[name]:
            found.append(f"{sid} names {name}, which has no test titled {sid}")
        # (a) the React source
        if source.startswith(NONE_PREFIX):
            if sid not in PAGE_ONLY:
                found.append(f"{sid} claims no React behaviour, but only {sorted(PAGE_ONLY)} may")
            elif len(source) < len(NONE_PREFIX) + 30:
                found.append(f"{sid} claims no React behaviour without saying why")
            continue
        sources = cited(source)
        if not sources:
            found.append(f"{sid} cites no React source")
        for path, words in sources:
            text = react.get(path)
            if text is None:
                found.append(f"{sid} cites {path}, which is not a file this test reads")
                continue
            if not words:
                found.append(f"{sid} cites {path} with no words from it")
            for phrase in words:
                if norm(phrase) not in norm(text):
                    found.append(f"{sid} cites {path} for {phrase!r}, which is not in it today")
    for name, ids in titled.items():
        for orphan in sorted(ids - set(rows)):
            found.append(f"{name} has a test for {orphan}, which is no scenario of spec/08")
    for sid in rows:
        if not any(sid in ids for ids in titled.values()):
            found.append(f"{sid} has no page test")
    for line, ids in BRIEF.items():
        for sid in ids:
            if sid not in rows:
                found.append(f"the brief's line {line!r} needs {sid}, which spec/08 does not have")
    mapped = {sid for ids in BRIEF.values() for sid in ids}
    for sid in sorted(set(rows) - mapped):
        found.append(f"{sid} answers no line of the brief")
    by_id = {row["id"]: row for row in functions}
    frame, releases = by_id.get("studio-frame"), by_id.get("studio-releases")
    if frame is None or releases is None:
        found.append("FUNCTIONS.yaml lacks the studio-frame or studio-releases row")
    else:
        for row, prefixes in ((frame, ("SF",)), (releases, ("SR", "SK", "SO"))):
            want = sorted(
                (sid for sid in rows if sid.startswith(prefixes)), key=lambda s: (s[:2], int(s[2:]))
            )
            have = [part.strip() for part in row["scenario"].split(",") if part.strip()]
            if sorted(have) != sorted(want):
                found.append(f"FUNCTIONS row {row['id']} names scenarios {have}, not {want}")
            if row["route"]:
                found.append(
                    f"FUNCTIONS row {row['id']} has a GOV.UK route: "
                    "this slice builds the Default tree only"
                )
    return found


# ---------------------------------------------------------------------------- the real inputs


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def real() -> tuple[str, dict[str, str], dict[str, str], list[dict[str, str]]]:
    spec = read(SPEC)
    tests = {name: read(path) for name, path in PAGE_TESTS.items() if path.is_file()}
    wanted: set[str] = set()
    for cells in rows_of(spec).values():
        wanted.update(path for path, _ in cited(cells[2]))
    react = {path: read(CORE / path) for path in wanted if (CORE / path).is_file()}
    functions = yaml.safe_load(read(FUNCTIONS))["functions"]
    return spec, tests, react, functions


def test_there_is_a_scenario_s_in_spec_08() -> None:
    spec, *_ = real()
    assert SECTION in spec, "spec/08 has no Scenario S for the Studio's frame and Releases"
    assert len(rows_of(spec)) >= 30


def test_the_real_inputs_have_no_problem() -> None:
    assert problems(*real()) == []


def test_every_scenario_has_a_page_test_and_back() -> None:
    spec, tests, _, _ = real()
    assert set(tests) == set(PAGE_TESTS), "a page test file is missing"
    ids = set(rows_of(spec))
    covered = {sid for text in tests.values() for sid in titles_in(text)}
    assert ids == covered


def test_every_row_cites_words_that_are_in_the_react_source() -> None:
    spec, _, react, _ = real()
    for sid, cells in rows_of(spec).items():
        if cells[2].startswith(NONE_PREFIX):
            continue
        for path, words in cited(cells[2]):
            assert path in react, f"{sid} cites {path}, which is not there"
            for phrase in words:
                assert norm(phrase) in norm(react[path]), f"{sid}: {phrase!r} is not in {path}"


def test_every_line_of_the_brief_has_a_scenario() -> None:
    spec, *_ = real()
    ids = set(rows_of(spec))
    assert {sid for line in BRIEF.values() for sid in line} <= ids
    assert ids <= {sid for line in BRIEF.values() for sid in line}


def test_the_function_rows_name_the_scenarios() -> None:
    spec, _, _, functions = real()
    rows = {row["id"]: row for row in functions}
    for function_id in ("studio-frame", "studio-releases"):
        assert rows[function_id]["scenario"].strip(), f"{function_id} has no scenario"
        assert rows[function_id]["route"] == "", (
            "the GOV.UK tree's route stays empty: this is the Default tree's page"
        )
    assert rows_of(spec)
    # The list of functions with no scenario may only shrink (test_functions_yaml.py): these two
    # have theirs now.
    known = read(FUNCTIONS_TEST)
    listed = known[
        known.index("KNOWN_WITHOUT_SCENARIO") : known.index(
            "}", known.index("KNOWN_WITHOUT_SCENARIO")
        )
    ]
    assert '"studio-frame"' not in listed and '"studio-releases"' not in listed


def test_the_keyboard_cases_are_in_the_pages_runner() -> None:
    """Rule 13: each Releases action has a case that proves it end to end on the page, with
    scripts and without."""
    spec = real()[0]
    text = read(PAGE_TESTS["keyboard/studio-releases.spec.ts"])
    assert titles_in(text) >= {"SK1", "SK2", "SK3", "SK4", "SO1", "SO2", "SO3"}
    for needle in ("javaScriptEnabled: false", "keyboard.press", "webkitRelativePath"):
        assert needle in text, f"the pages' keyboard spec never says {needle!r}"
    for sid in ("SO1", "SO2", "SO3"):
        assert "scripts off" in rows_of(spec)[sid][1].lower()


# ---------------------------------------------------------------------------- planted faults


def planted() -> tuple[str, dict[str, str], dict[str, str], list[dict[str, str]]]:
    spec, tests, react, functions = real()
    return spec, dict(tests), dict(react), [dict(row) for row in functions]


def test_a_scenario_row_removed_is_caught() -> None:
    spec, tests, react, functions = planted()
    kept = "\n".join(line for line in spec.splitlines() if not line.startswith("| SR9 |"))
    found = problems(kept, tests, react, functions)
    assert any("has a test for SR9, which is no scenario" in p for p in found)
    assert any("FUNCTIONS row studio-releases names scenarios" in p for p in found)


def test_a_page_test_removed_is_caught() -> None:
    spec, tests, react, functions = planted()
    tests["studio-releases.test.ts"] = re.sub(
        r'it\(\s*"SR8: ', 'it("dropped: ', tests["studio-releases.test.ts"]
    )
    found = problems(spec, tests, react, functions)
    assert "SR8 has no page test" in found or any(
        "SR8 names studio-releases.test.ts, which has no test titled SR8" in p for p in found
    )


def test_react_words_that_are_not_in_the_screen_are_caught() -> None:
    spec, tests, react, functions = planted()
    changed = spec.replace(
        '"Open a case to use the Ingest Studio"', '"Choose a case to use the Ingest Studio"'
    )
    assert changed != spec
    found = problems(changed, tests, react, functions)
    assert any("SF1 cites" in p and "Choose a case" in p for p in found)


def test_a_react_source_that_changed_under_a_row_is_caught() -> None:
    spec, tests, react, functions = planted()
    path = "apps/workspace/src/ingest/releases/ReleasesTab.tsx"
    react[path] = react[path].replace("Would write", "Will write")
    found = problems(spec, tests, react, functions)
    assert any("SR7 cites" in p and "Would write" in p for p in found)


def test_a_line_of_the_brief_with_no_scenario_is_caught() -> None:
    spec, tests, react, functions = planted()
    tests["studio-frame.test.ts"] = re.sub(r'it\(\s*"SF9: ', 'it("', tests["studio-frame.test.ts"])
    kept = "\n".join(line for line in spec.splitlines() if not line.startswith("| SF9 |"))
    found = problems(kept, tests, react, functions)
    assert any(
        "the brief's line 'the Needs-you jump as a link carrying the request' needs SF9" in p
        for p in found
    )


def test_a_row_on_another_tree_is_caught() -> None:
    spec, tests, react, functions = planted()
    changed = re.sub(r"(\| SF1 \|[^\n]*\|) Default \|", r"\1 GOV.UK |", spec)
    assert changed != spec
    assert any("SF1 runs on 'GOV.UK'" in p for p in problems(changed, tests, react, functions))


def test_a_row_may_claim_no_react_behaviour_only_where_the_page_alone_has_the_duty() -> None:
    spec, tests, react, functions = planted()
    changed = re.sub(
        r"(\| SR7 \| [^|]*\|)[^|]*\|",
        r"\1 none: the React screen has nothing like this for the page to keep, so cites none |",
        spec,
    )
    assert changed != spec
    assert any(
        "SR7 claims no React behaviour" in p for p in problems(changed, tests, react, functions)
    )


def test_a_function_row_with_a_govuk_route_is_caught() -> None:
    spec, tests, react, functions = planted()
    for row in functions:
        if row["id"] == "studio-releases":
            row["route"] = "/studio/releases"
    assert any("has a GOV.UK route" in p for p in problems(spec, tests, react, functions))


def test_the_words_gate_finds_target_model_in_the_scenarios() -> None:
    spec, tests, react, functions = planted()
    changed = spec + "\n" + "Edit target model\n"
    assert any("target model" in p for p in problems(changed, tests, react, functions))


def test_a_document_with_no_section_is_one_problem() -> None:
    _, tests, react, functions = planted()
    assert problems("# 08\n", tests, react, functions) == [
        "spec/08 has no `## Scenario S` section with scenario rows"
    ]


@pytest.mark.parametrize("sid", ["SF1", "SR1", "SK1", "SO1"])
def test_each_kind_of_id_is_read(sid: str) -> None:
    assert ID.match(sid)
