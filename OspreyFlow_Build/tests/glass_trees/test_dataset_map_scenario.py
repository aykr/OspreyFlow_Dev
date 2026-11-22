"""Scenario DM: the Studio's dataset map as a server-rendered page, Default tree (slice IS3; ADR-152
decision 12, "each rebuilt screen's acceptance scenario is written first").

**There is no React dataset map to read the behaviour from** (`FUNCTIONS.yaml`'s `studio-dataset-map` row says so),
so the scenario is written against the ADR text, the prototype's Pipelines list, the words the Studio already uses and
the owner's ruling of 21 November 2026 (in `slices/IS3.md`: "show the dataset as a table with no 'runs after' column.
IS6 adds the column when it stores the order. Do not show an empty column or a suggestion nothing backs").

`spec/08_ACCEPTANCE_SCENARIOS.md` ("Scenario DM") holds one row per behaviour. Each row names (a) what it was read from, by
path and by words that must be in that file today, and (b) the page test that proves it, by id. `spec/09_INGEST_STUDIO.md`
(section 1.2) says what the table shows, that it is read-only, and that "runs after" is IS6's and shown only when the
order is stored. This file holds the document, the two sections, the page test, the page's own files and the
`studio-dataset-map` row of `apps/pages/FUNCTIONS.yaml` in step:

* a scenario with no page test, or a page test with no scenario -> `test_every_scenario_has_a_page_test_and_back`
* a row whose cited words are not in the file it cites -> `test_every_row_cites_words_that_are_in_the_source`
* the section of spec/09 that does not say read-only, IS6's order and the four columns
  -> `test_spec_09_says_what_the_table_shows`
* the FUNCTIONS row left without its scenarios, or given a GOV.UK route -> `test_the_function_row_names_the_scenarios`
* a "runs after" or a suggestion in the page's words or template -> `test_the_page_s_words_say_nothing_of_the_order_of_runs`
* the words gates (`ui_words_check`, `colour_drift_check`, `no_branches_check`, `design_check`) not reading the page's own
  files -> `test_each_gate_reads_the_page_s_own_files`

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and copies two of
them (the page's words and its template) into a temporary folder to plant a violation in; it never writes into the
repository. The files, from the repository's root: `OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md`,
`OspreyFlow_Build/spec/09_INGEST_STUDIO.md`, `OspreyFlow_Build/spec/06_DECISIONS.md`,
`OspreyFlow_Build/spec/ingest_studio_redesign/ingest_studio_prototype.html`,
`OspreyFlow_Build/process/CLAUDE.md`, `OspreyFlow_Build/process/lanes/v062/slices/IS3.md`,
`OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py`, and under `OspreyFlow_Core`: `apps/pages/FUNCTIONS.yaml`,
`apps/pages/test/default/dataset-map.test.ts`, `apps/pages/server/datasetMap.ts`, `apps/pages/server/pageList.ts`,
`apps/pages/server/views/datasetMapWords.ts`, `apps/pages/tree-default/studio/dataset-map.njk`,
`apps/pages/server/views/studioWords.ts`, `apps/pages/server/conduit.ts`,
`apps/workspace/src/ingest/studio/{vocabulary.ts,ModelTab.tsx}`,
`apps/workspace/src/ingest/dag/{PipelineCanvas.tsx,pipelineLayout.ts}`.

Every planted fault is the real inputs with one thing changed (rule 15), run through the same `problems` the real inputs go
through, which finds nothing in them.
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
PAGE_TEST = PAGES / "test" / "default" / "dataset-map.test.ts"
ROUTE = PAGES / "server" / "datasetMap.ts"
PAGE_LIST = PAGES / "server" / "pageList.ts"
WORDS = PAGES / "server" / "views" / "datasetMapWords.ts"
TEMPLATE = PAGES / "tree-default" / "studio" / "dataset-map.njk"

SECTION = "## Scenario DM"
ID = re.compile(r"^DM\d+$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|')(DM\d+): """)
PAGE_TEST_NAME = "dataset-map.test.ts"

#: What each behaviour of the table is, by id: a behaviour with no scenario is one nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "a table: caption, column headers, one row header per pipeline, no script": ("DM1",),
    "no runs-after column, no empty column, no suggestion, no line (the owner's ruling)": ("DM2",),
    "the stages, as the Studio's own words, in the canvas's layout order": ("DM3",),
    "the status and the version, as the Studio's own words": ("DM4",),
    "rows sorted by pipeline name, and said": ("DM5",),
    "the empty dataset, said in words": ("DM6",),
    "only this dataset's pipelines": ("DM7",),
    "one refusal for no right, no such dataset and not allowed; no row, count or name": ("DM8",),
    "a read that failed is said, never an empty table": ("DM9",),
    "the model place, in plain words": ("DM10",),
    "asked of the Conduit as the person, and nothing else": ("DM11",),
    "no script needed, no action beyond links, every control labelled": ("DM12",),
    "the service's own page under /studio, a GET only": ("DM13",),
    "every check is red against a planted fault": ("DM14",),
}

#: A row that is a duty of the page with no counterpart in a source says so, with a reason; no other row may.
PAGE_ONLY = {"DM5", "DM6", "DM14"}
NONE_PREFIX = "none:"
#: The words the page must never say: the order of runs is IS6's, shown only when it is stored.
ORDER_WORDS = re.compile(
    r"runs?\s+after|suggest|run\s+order|order\s+of\s+runs|depends\s+on", re.IGNORECASE
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def section_of(spec: str) -> str:
    """Scenario DM's text, to the next `## ` heading; empty when there is no such section."""
    start = spec.find(SECTION)
    if start < 0:
        return ""
    section = spec[start:]
    end = section.find("\n## ", len(SECTION))
    return section if end < 0 else section[:end]


def rows_of(spec: str) -> dict[str, list[str]]:
    """Scenario DM's table rows by id, each as its five cells; `{}` when there is no such section."""
    out: dict[str, list[str]] = {}
    for line in section_of(spec).splitlines():
        cells = (
            [c.strip() for c in line.strip().strip("|").split("|")]
            if line.startswith("| DM")
            else []
        )
        if len(cells) == 5 and ID.match(cells[0]):
            out[cells[0]] = cells
    return out


def titles_in(text: str) -> set[str]:
    return set(TITLE.findall(text))


def cited(cell: str) -> list[tuple[str, list[str]]]:
    """`path` then its quoted words, for each path a source cell cites (paths from the repository's root)."""
    return [
        (path, re.findall(r'"([^"]+)"', words))
        for path, words in re.findall(r'`([^`]+)`((?:\s*;?\s*"[^"]+")*)', cell)
    ]


def spec_09_section(spec: str) -> str:
    start = spec.find("### 1.2 The dataset map")
    if start < 0:
        return ""
    end = spec.find("\n## ", start)
    return spec[start:] if end < 0 else spec[start:end]


def problems(
    spec_08: str,
    spec_09: str,
    page_test: str,
    sources: dict[str, str],
    functions: list[dict[str, str]],
    words: dict[str, str],
) -> list[str]:
    """Every fault in the scenarios, the section of spec/09, the page test, the cited words, the function row and the
    page's own words, in words."""
    found: list[str] = []
    rows = rows_of(spec_08)
    if not rows:
        return [f"spec/08 has no `{SECTION}` section with scenario rows"]
    titled = titles_in(page_test)
    for sid, cells in rows.items():
        _, behaviour, source, page, tree = cells
        if tree != "Default":
            found.append(f"{sid} runs on {tree!r}, not on the Default tree")
        if not behaviour:
            found.append(f"{sid} says nothing of the behaviour")
        name = page.strip("` ")
        if name != PAGE_TEST_NAME:
            found.append(f"{sid} names the page test {name!r}, not {PAGE_TEST_NAME!r}")
        elif sid not in titled:
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
    for orphan in sorted(titled - set(rows)):
        found.append(f"{PAGE_TEST_NAME} has a test for {orphan}, which is no scenario of spec/08")
    for sid in rows:
        if sid not in titled:
            found.append(f"{sid} has no page test")
    for line, ids in BRIEF.items():
        for sid in ids:
            if sid not in rows:
                found.append(f"the brief's line {line!r} needs {sid}, which spec/08 does not have")
    for sid in sorted(set(rows) - {sid for ids in BRIEF.values() for sid in ids}):
        found.append(f"{sid} answers no line of the brief")
    section = section_of(spec_08)
    if re.search(r"target\s+model", section, re.IGNORECASE):
        found.append('Scenario DM says "target model": the screens say "domain model"')

    # spec/09's section: what the table shows, read-only, IS6's order
    text = norm(spec_09_section(spec_09))
    if not text:
        found.append("spec/09 has no section 1.2 on the dataset map")
    else:
        for need, why in (
            ("read-only", "that the page is read-only"),
            ("IS6", "that the order of runs is IS6's"),
            (
                "only when the order is stored",
                'that "runs after" is shown only when the order is stored',
            ),
            ("Pipeline, Status, Version and Stages", "the four columns"),
            ("no empty column", "that no empty column is drawn"),
            ("Scenario DM", "the scenario that tests it"),
        ):
            if need not in text:
                found.append(f"spec/09 section 1.2 does not say {why} (looked for {need!r})")

    # the FUNCTIONS row
    by_id = {row["id"]: row for row in functions}
    row = by_id.get("studio-dataset-map")
    if row is None:
        found.append("FUNCTIONS.yaml lacks the studio-dataset-map row")
    else:
        have = sorted(part.strip() for part in row["scenario"].split(",") if part.strip())
        if have != sorted(rows):
            found.append(
                f"FUNCTIONS row studio-dataset-map names scenarios {have}, not {sorted(rows)}"
            )
        if row["route"]:
            found.append(
                "FUNCTIONS row studio-dataset-map has a GOV.UK route: this slice builds the Default tree only"
            )

    # the page's own words
    for name, body in words.items():
        for hit in ORDER_WORDS.finditer(body):
            found.append(
                f"{name} says {hit.group(0)!r}: the order of runs is IS6's, and shown only once stored"
            )
    return found


# ---------------------------------------------------------------------------- the real inputs


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def real() -> tuple[str, str, str, dict[str, str], list[dict[str, str]], dict[str, str]]:
    spec_08 = read(SPEC_08)
    wanted: set[str] = set()
    for cells in rows_of(spec_08).values():
        wanted.update(path for path, _ in cited(cells[2]))
    sources = {path: read(ROOT / path) for path in wanted if (ROOT / path).is_file()}
    functions = yaml.safe_load(read(FUNCTIONS))["functions"]
    words = {path.name: read(path) for path in (WORDS, TEMPLATE) if path.is_file()}
    page_test = read(PAGE_TEST) if PAGE_TEST.is_file() else ""
    return spec_08, read(SPEC_09), page_test, sources, functions, words


def test_there_is_a_scenario_dm_in_spec_08() -> None:
    spec_08, *_ = real()
    assert SECTION in spec_08, "spec/08 has no Scenario DM for the Studio's dataset map"
    assert len(rows_of(spec_08)) == len(BRIEF)


def test_the_real_inputs_have_no_problem() -> None:
    assert problems(*real()) == []


def test_every_scenario_has_a_page_test_and_back() -> None:
    spec_08, _, page_test, *_ = real()
    assert PAGE_TEST.is_file(), "the page test is missing"
    assert set(rows_of(spec_08)) == titles_in(page_test)


def test_every_row_cites_words_that_are_in_the_source() -> None:
    spec_08, _, _, sources, *_ = real()
    for sid, cells in rows_of(spec_08).items():
        if cells[2].startswith(NONE_PREFIX):
            continue
        for path, quoted in cited(cells[2]):
            assert path in sources, f"{sid} cites {path}, which is not there"
            for phrase in quoted:
                assert norm(phrase) in norm(sources[path]), f"{sid}: {phrase!r} is not in {path}"


def test_spec_09_says_what_the_table_shows() -> None:
    _, spec_09, *_ = real()
    assert spec_09_section(spec_09), "spec/09 has no section 1.2 on the dataset map"
    assert "Scenario DM" in spec_09_section(spec_09)


def test_the_function_row_names_the_scenarios() -> None:
    spec_08, _, _, _, functions, _ = real()
    row = {r["id"]: r for r in functions}["studio-dataset-map"]
    assert row["scenario"].strip(), "studio-dataset-map has no scenario"
    assert row["route"] == "", (
        "the GOV.UK tree's route stays empty: this is the Default tree's page"
    )
    # The list of functions with no scenario may only shrink (test_functions_yaml.py): this one has its own now.
    known = read(FUNCTIONS_TEST)
    listed = known[
        known.index("KNOWN_WITHOUT_SCENARIO") : known.index(
            "}", known.index("KNOWN_WITHOUT_SCENARIO")
        )
    ]
    assert '"studio-dataset-map"' not in listed
    assert set(rows_of(spec_08))


def test_the_page_is_the_function_rows_and_is_registered() -> None:
    route = read(ROUTE)
    assert 'id: "studio-dataset-map"' in route
    assert 'path: "/studio/dataset-map"' in route
    assert 'methods: ["GET"]' in route
    assert "studioDatasetMap" in read(PAGE_LIST)


def test_the_page_s_words_say_nothing_of_the_order_of_runs() -> None:
    words = real()[5]
    assert set(words) == {WORDS.name, TEMPLATE.name}, "the page's words or template is missing"
    assert not [name for name, body in words.items() if ORDER_WORDS.search(body)]


def test_the_page_reads_its_words_from_the_studio_s_own() -> None:
    """The stage and status words are the Studio's own (`PipelineCanvas.tsx`'s `KIND_NAMES`, `vocabulary.ts`'s
    `STATUS_WORDS`): each pair is in the page's words, so a changed word in the screen is a change here too."""
    canvas = read(CORE / "apps/workspace/src/ingest/dag/PipelineCanvas.tsx")
    vocabulary = read(CORE / "apps/workspace/src/ingest/studio/vocabulary.ts")
    words = read(WORDS)
    kinds = dict(re.findall(r'^\s{2}(\w+): "([^"]+)",', canvas[canvas.index("KIND_NAMES") :], re.M))
    assert {"domain_model", "source", "map", "load", "sql", "fuzzy_match"} <= set(kinds)
    for kind, label in kinds.items():
        assert re.search(rf'\b{kind}: "{re.escape(label)}"', words), (
            f"the page's words do not say {kind} as {label!r}"
        )
    statuses = dict(re.findall(r'^\s{2}(\w+): "([^"]+)",', vocabulary, re.M))
    assert statuses == {
        "draft": "draft",
        "published": "deployed",
        "flagged": "needs attention",
        "superseded": "previous version",
    }
    for status, label in statuses.items():
        assert re.search(rf'\b{status}: "{re.escape(label)}"', words), (
            f"the page's words do not say {status} as {label!r}"
        )


# ---------------------------------------------------------------------------- planted faults


def planted() -> tuple[str, str, str, dict[str, str], list[dict[str, str]], dict[str, str]]:
    spec_08, spec_09, page_test, sources, functions, words = real()
    return spec_08, spec_09, page_test, dict(sources), [dict(r) for r in functions], dict(words)


def test_a_scenario_row_removed_is_caught() -> None:
    spec_08, spec_09, page_test, sources, functions, words = planted()
    kept = "\n".join(line for line in spec_08.splitlines() if not line.startswith("| DM7 |"))
    found = problems(kept, spec_09, page_test, sources, functions, words)
    assert any("has a test for DM7, which is no scenario" in p for p in found)
    assert any("FUNCTIONS row studio-dataset-map names scenarios" in p for p in found)


def test_a_page_test_renamed_is_caught() -> None:
    spec_08, spec_09, page_test, sources, functions, words = planted()
    changed = re.sub(r'it\(\s*"DM8: ', 'it("dropped: ', page_test)
    assert changed != page_test
    found = problems(spec_08, spec_09, changed, sources, functions, words)
    assert any("DM8 names dataset-map.test.ts, which has no test titled DM8" in p for p in found)


def test_cited_words_that_are_not_in_the_source_are_caught() -> None:
    spec_08, spec_09, page_test, sources, functions, words = planted()
    path = "OspreyFlow_Core/apps/workspace/src/ingest/studio/vocabulary.ts"
    assert path in sources
    sources[path] = sources[path].replace("needs attention", "needs a look")
    found = problems(spec_08, spec_09, page_test, sources, functions, words)
    assert any("DM4 cites" in p and "needs attention" in p for p in found)


def test_a_source_that_is_not_read_is_caught() -> None:
    spec_08, spec_09, page_test, sources, functions, words = planted()
    sources.pop("OspreyFlow_Build/spec/ingest_studio_redesign/ingest_studio_prototype.html")
    found = problems(spec_08, spec_09, page_test, sources, functions, words)
    assert any("DM1 cites" in p and "prototype" in p for p in found)


def test_a_row_may_claim_no_source_only_where_the_page_alone_has_the_duty() -> None:
    spec_08, spec_09, page_test, sources, functions, words = planted()
    changed = re.sub(
        r"(\| DM4 \| [^|]*\|)[^|]*\|",
        r"\1 none: the Studio's words are not read from anywhere, so this cites none |",
        spec_08,
    )
    assert changed != spec_08
    found = problems(changed, spec_09, page_test, sources, functions, words)
    assert any("DM4 claims no source" in p for p in found)


def test_a_row_on_another_tree_is_caught() -> None:
    spec_08, spec_09, page_test, sources, functions, words = planted()
    changed = re.sub(r"(\| DM1 \|[^\n]*\|) Default \|", r"\1 GOV.UK |", spec_08)
    assert changed != spec_08
    found = problems(changed, spec_09, page_test, sources, functions, words)
    assert any("DM1 runs on 'GOV.UK'" in p for p in found)


def test_spec_09_without_the_stored_order_sentence_is_caught() -> None:
    spec_08, spec_09, page_test, sources, functions, words = planted()
    changed = spec_09.replace("only when the order is stored", "whenever it is wanted")
    assert changed != spec_09
    found = problems(spec_08, changed, page_test, sources, functions, words)
    assert any("shown only when the order is stored" in p for p in found)
    removed = spec_09.replace("### 1.2 The dataset map", "### 1.2 Something else")
    assert any(
        "no section 1.2" in p
        for p in problems(spec_08, removed, page_test, sources, functions, words)
    )


def test_a_function_row_with_a_govuk_route_or_no_scenario_is_caught() -> None:
    spec_08, spec_09, page_test, sources, functions, words = planted()
    for row in functions:
        if row["id"] == "studio-dataset-map":
            row["route"] = "/studio/dataset-map"
    assert any(
        "has a GOV.UK route" in p
        for p in problems(spec_08, spec_09, page_test, sources, functions, words)
    )
    for row in functions:
        if row["id"] == "studio-dataset-map":
            row["route"] = ""
            row["scenario"] = ""
    found = problems(spec_08, spec_09, page_test, sources, functions, words)
    assert any("names scenarios []" in p for p in found)


@pytest.mark.parametrize(
    "phrase",
    ["Runs after", "runs after", "A suggested order", "Suggestion", "The run order", "Depends on"],
)
def test_a_word_about_the_order_of_runs_in_the_page_is_caught(phrase: str) -> None:
    spec_08, spec_09, page_test, sources, functions, words = planted()
    for name in (WORDS.name, TEMPLATE.name):
        changed = dict(words)
        changed[name] = words[name] + f'\n<th scope="col">{phrase}</th>\n'
        found = problems(spec_08, spec_09, page_test, sources, functions, changed)
        assert any(name in p and "IS6" in p for p in found), (name, phrase, found)


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


def _rel(path: Path) -> str:
    return path.relative_to(CORE).as_posix()


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
    assert f"{_rel(target)}:" in out, out


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
    assert f"{_rel(target)}:" in out, out


@pytest.mark.parametrize("source", [WORDS, TEMPLATE], ids=lambda p: p.name)
def test_the_branches_gate_reads_the_page_s_own_files(source: Path, tmp_core: Path) -> None:
    assert source.is_file(), f"{source.name} is not written yet"

    def found() -> list[str]:
        files = no_branches_check.tree_files(tmp_core, no_branches_check.SCANNED)
        return [f[0] for f in no_branches_check.findings(files)]

    assert found() == []
    target = _plant(tmp_core, source, "no_branches")
    assert found() == [_rel(target)]


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
