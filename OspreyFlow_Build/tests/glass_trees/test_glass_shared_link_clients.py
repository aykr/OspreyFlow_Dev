"""The link, inspector, question, reader, views, boards-promotions and analytics Conduit clients live in
`packages/glass-shared`, and nothing names the place they came from (ADR-152 decision 6, "the Conduit client"; slice
PL4d3b, the seventh of the PL4 slices after A, B, B2, B3, C, D1, D2 and D3a; the owner's rulings of 20 and 21 November 2026).

Sixteen plain TypeScript files moved whole from `OspreyFlow_Core/apps/workspace/src/` to
`OspreyFlow_Core/packages/glass-shared/src/`, at the same place under it, their bytes unchanged but for the import lines:

* the inspector's: `inspector/emailDocuments.ts`, `linkChangeApi.ts`, `linkEventsApi.ts`, `linkNotesApi.ts`;
* the link types': `linktypes/http.ts` (the shared fetch helper and refusal), `linkTypesApi.ts`, `modelProposalsApi.ts`;
* the questions' and the reader's: `questions/questionsApi.ts`, `questions/graphFacts.ts`, `reader/readerApi.ts`,
  `dossier/api.ts`, `dossier/models.ts`;
* the saved views', the batch expansion's, the boards' promotions' and the analytics': `views/viewsApi.ts`,
  `workingset/batchExpansionApi.ts`, `boards/promotionsApi.ts`, `analytics/api.ts`.

Each calls `fetch` against the Conduit (or is a helper of one that does) and takes the bearer token as an argument. None
touches the page, and none imports React, a drawing library or a store. `emailDocuments.ts` has a parameter called
`window` (the timeline's brushed window): it is a value the caller passes, not the browser's.

**One file came along that the brief did not list.** `questions/questionsApi.ts` takes its citation types from
`questions/graphFacts.ts`, which is plain (no import, no page), so it moved beside it; leaving it would have left the
question client importing a workspace path, which the package may never do.

**Three names were written twice, and the index says which is which.** `send` is the report clients' (their case helper),
the link types' (`linktypes/http`) and the promotions' (`boards/promotionsApi`); `rejectProposal` is the link types' and
the questions'. Two `export *` of the same name is an error in TypeScript and silently dropped in the browser, so the
index names the link types' `send` as `sendLinkType`, the promotions' as `sendPromotion` and the questions'
`rejectProposal` as `rejectQuestionProposal`; every other name goes through as it was
(`test_the_index_exports_every_name_of_every_moved_client`).

Every importer followed (the workspace, its tests, the keyboard and accessibility harnesses outside `src/`). The tests
stayed in the workspace, and a test that replaced a client with a double now replaces the package's export of it. This
file is the proof that none was left behind and that each guard can fail.

Which test fails if the invariant is broken (rule 12):

* a file is not where it should be, an old one is back, or the index does not export it:
  `test_the_sixteen_clients_are_in_the_package_and_not_in_the_workspace`, and a name of one that the index leaves out
  (or two modules giving one name): `test_the_index_exports_every_name_of_every_moved_client`, with
  `test_an_index_that_drops_or_doubles_a_name_is_found`;
* a file of the package importing React or a drawing library, or a file of the workspace or the harness, or a schema
  import that no longer resolves: the D2 file's `test_the_package_s_clients_import_no_react_and_no_workspace_path` reads
  every file of the package, these sixteen too; here `test_the_new_clients_are_among_the_files_that_check_reads` proves it
  does, and `test_a_react_or_workspace_import_in_a_moved_client_is_found` plants one in each;
* a moved client importing the package by its own name (a cycle through the index, which the workspace's way of writing
  it would leave behind): `test_no_moved_client_imports_the_package_by_its_name`, with a plant in each;
* a client changed in more than its import lines at the commit that moved it:
  `test_the_move_changed_no_line_but_the_imports`;
* a file of any kind naming an old path: `test_no_tracked_file_names_an_old_path`;
* an importer that still reaches an old path, or reaches into the package's folder instead of its name:
  `test_every_import_of_a_moved_client_reaches_the_package`, with `test_an_old_path_put_back_in_one_importer_is_found`
  (the lines the tree really held, among them a `vi.mock` of a client and a namespace import of one);
* a spec, or a file one imports, naming a file that does not exist (what Playwright would meet at collection):
  `test_every_import_reached_from_a_spec_resolves`;
* each of four gates that stops reading the moved files, or reads fewer files than before the move:
  `test_each_gate_reads_no_fewer_files_than_before`, and one plant for each gate in a **moved** file;
* each word-walker that does not read the moved files: the Python walkers by
  `test_the_people_name_walk_reads_each_moved_client` and `test_the_view_word_walk_reads_each_moved_client` (a plant in
  a copy of each of the sixteen, clean beside it), `test_a_moved_clients_place_held_by_both_roots_is_read_from_both`
  (keyed by root); the vitest walkers (`copyWords`, `copyNoClient`, `resolvedPrincipal`) by
  `test_the_vitest_walkers_name_the_new_folders`, which reads the kit they share, whose own cases plant in a copy of each;
* either image's `COPY` lines naming a path that moved, or missing what the harness needs:
  `test_no_image_copies_a_path_that_moved`, `test_the_harness_image_copies_what_the_clients_need`, each shown red by
  `test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found`.

**This file walks:** `git ls-files` over the whole repository (the old-path test); the tracked `.ts`, `.tsx`, `.mts`,
`.mjs`, `.js` and `.jsx` files under `OspreyFlow_Core/apps/` (the import tests, the spec walk, which starts at every tracked
`*.spec.ts` and `*.spec.tsx` in `apps/workspace` and `apps/harness` and follows their imports) and under
`OspreyFlow_Core/packages/glass-shared/src` (the moved files, the index, the package's own imports);
`apps/workspace/src` and `packages/glass-shared/src` through the two Python word-walkers it imports (each in a
temporary copy); `apps/workspace/Dockerfile` and `harness/Dockerfile` by name; `copyTextsTestKit.ts` and the three vitest
walkers by name; the git history of the rename (`git log`, `git show`); and temporary copies built inside `tmp_path` for
the plants (written there, never in the repository), among them copies of `packages/glass-shared/src`.
"""

# The planted lines below are the real call-site shapes, kept on one line as the tree wrote them (rule 15), and the
# prose beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from pathlib import Path

import pytest
from tools import colour_drift_check, design_check, no_branches_check, ui_words_check
from tools.layout import CORE, ROOT

from tests import test_guide_navigation_words as navigation
from tests import test_people_section_words as people
from tests.glass_trees import test_glass_shared_clients as clients
from tests.glass_trees import test_glass_shared_plain_logic as earlier
from tests.harness import test_harness_frontend_copies as image

PACKAGE = "OspreyFlow_Core/packages/glass-shared/"
SHARED = PACKAGE + "src/"
SHARED_SRC = CORE / "packages" / "glass-shared" / "src"
APPS = "OspreyFlow_Core/apps/"
WORKSPACE_SRC = APPS + "workspace/src/"
PACKAGE_NAME = "@ospreyflow/glass-shared"

#: The sixteen files that moved whole: where each is now (relative to `SHARED`; its old place is the same relative path
#: under `apps/workspace/src/`).
WHOLE = (
    "inspector/emailDocuments.ts",
    "inspector/linkChangeApi.ts",
    "inspector/linkEventsApi.ts",
    "inspector/linkNotesApi.ts",
    "linktypes/http.ts",
    "linktypes/linkTypesApi.ts",
    "linktypes/modelProposalsApi.ts",
    "questions/questionsApi.ts",
    "questions/graphFacts.ts",
    "reader/readerApi.ts",
    "dossier/api.ts",
    "dossier/models.ts",
    "views/viewsApi.ts",
    "workingset/batchExpansionApi.ts",
    "boards/promotionsApi.ts",
    "analytics/api.ts",
)
OLD_OF = {rel: WORKSPACE_SRC + rel for rel in WHOLE}
_OLD_STEMS = {old.removesuffix(".ts") for old in OLD_OF.values()}

#: The names the index gives under another, because two moved files (or a moved file and an earlier one) wrote the same
#: name: (file, the name it wrote, the name the package exports it as).
RENAMED_BY_THE_INDEX = (
    ("linktypes/http.ts", "send", "sendLinkType"),
    ("boards/promotionsApi.ts", "send", "sendPromotion"),
    ("questions/questionsApi.ts", "rejectProposal", "rejectQuestionProposal"),
)

#: The places that may name an old path because they are a record of the past: the decision log, and the build record
#: under `process/`. They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone
#: (`test_every_named_exception_still_has_its_reason`).
NAMED = {
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_glass_shared_link_clients.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

_NAME_FORMS = (
    r"inspector/emailDocuments",
    r"inspector/linkChangeApi",
    r"inspector/linkEventsApi",
    r"inspector/linkNotesApi",
    r"linktypes/http",
    r"linktypes/linkTypesApi",
    r"linktypes/modelProposalsApi",
    r"questions/questionsApi",
    r"questions/graphFacts",
    r"reader/readerApi",
    r"dossier/api",
    r"dossier/models",
    r"views/viewsApi",
    r"workingset/batchExpansionApi",
    r"boards/promotionsApi",
    r"analytics/api",
)
#: Not a route (`/v1/analytics/...` is the Conduit's address, not a file), and not `viewsApi.test.ts` or the like (the tests
#: stayed in the workspace, beside where the file was).
_TEXT_FORM = re.compile(
    rf"(?<!glass-shared/src/)(?<!v1/)(?<![\w-])(?:{'|'.join(_NAME_FORMS)})\b(?!\.(?:css|test\.|spec\.|py|bak))"
)
#: A bare file name with its extension, as a guide writes it: `linkEventsApi.ts`. Not `promotionsApi.ts`: the Studio's Runs
#: grid has a file of that name of its own, which stays.
_FILE_FORM = re.compile(
    r"(?<![\w/.-])(?:emailDocuments|linkChangeApi|linkEventsApi|linkNotesApi|linkTypesApi|modelProposalsApi|questionsApi|readerApi|viewsApi|batchExpansionApi|graphFacts)\.ts\b"
)
#: The segments of one written apart: `join(HERE, "..", "src", "views", "viewsApi")`, Python's `/ "reader" / "readerApi.ts"`.
_SEGMENT_FORM = re.compile(
    r"""["'](?:inspector["']\s*[,/]\s*["'](?:emailDocuments|linkChangeApi|linkEventsApi|linkNotesApi)"""
    r"""|linktypes["']\s*[,/]\s*["'](?:http|linkTypesApi|modelProposalsApi)"""
    r"""|questions["']\s*[,/]\s*["'](?:questionsApi|graphFacts)|reader["']\s*[,/]\s*["']readerApi"""
    r"""|dossier["']\s*[,/]\s*["'](?:api|models)|views["']\s*[,/]\s*["']viewsApi"""
    r"""|workingset["']\s*[,/]\s*["']batchExpansionApi|boards["']\s*[,/]\s*["']promotionsApi"""
    r"""|analytics["']\s*[,/]\s*["']api)(?:\.ts)?["']"""
)
_PACKAGE_SEGMENTS = re.compile(r"""["']glass-shared["']\s*[,/]\s*["']src["']\s*[,/]\s*$""")


def old_path_mentions(root: Path, rels: Iterable[str]) -> list[tuple[str, int, str]]:
    """`(file, line, text)` for each place under `root` that names an old path. `rels` are repository-relative."""
    found: list[tuple[str, int, str]] = []
    for rel in rels:
        if rel.startswith(SHARED):
            continue  # inside the package a module is named by its place in the package
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # gone from the working tree, or not text
        for form in (_TEXT_FORM, _FILE_FORM, _SEGMENT_FORM):
            for hit in form.finditer(text):
                if form is _SEGMENT_FORM and _PACKAGE_SEGMENTS.search(text[: hit.start()]):
                    continue  # `"glass-shared", "src", "views", "viewsApi"` is the new place written apart
                line = text.count("\n", 0, hit.start()) + 1
                found.append((rel, line, text.splitlines()[line - 1].strip()))
    return sorted(set(found))


def _kept_out(rel: str) -> bool:
    if rel in NAMED:
        return True
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in HISTORY)


# ----------------------------------------------------------------------------------------------------- the imports

_PACKAGE_IMPORT = re.compile(rf"""["']{re.escape(PACKAGE_NAME)}(/[^"']*)?["']""")
_DECLARED = re.compile(
    r"^export\s+(?:async\s+)?(?:function|const|let|class|type|interface|enum)\s+(\w+)", re.M
)
_LISTED = re.compile(r"^export\s+(?:type\s+)?\{([^}]*)\}", re.M)


def _exported_names(text: str) -> set[str]:
    """Every name a file exports, by a declaration or in a list (`export type { A, B };`, `export { A as B } from`)."""
    names = set(_DECLARED.findall(text))
    for listed in _LISTED.findall(text):
        for item in listed.split(","):
            item = re.sub(r"^\s*type\s+", "", item.strip())
            if item:
                names.add(item.split(" as ")[-1].strip())
    return names


def _client_names(root: Path) -> set[str]:
    """Every name the sixteen clients export, read from the package's copies (the old ones are gone)."""
    names: set[str] = set()
    for rel in WHOLE:
        try:
            names |= _exported_names((root / (SHARED + rel)).read_text(encoding="utf-8"))
        except OSError:
            continue
    return names


def imports_not_reaching(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The relative specifiers that resolve to an old path, or into the package's folder instead of its name; and the
    number of files that import a name a moved client exports from the package. Resolution is by path alone: an old file
    need not exist."""
    bad: list[str] = []
    importers = 0
    names = _client_names(root) | {new for _, _, new in RENAMED_BY_THE_INDEX}
    for rel in rels:
        if Path(rel).suffix not in earlier._SOURCE_SUFFIXES or not rel.startswith(
            "OspreyFlow_Core/"
        ):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for hit in _PACKAGE_IMPORT.finditer(text):
            if hit.group(1):
                bad.append(
                    f"{rel}: {PACKAGE_NAME}{hit.group(1)} (the package is imported by its name)"
                )
        if not rel.startswith(SHARED) and any(
            names & earlier._names(m.group(1))
            for m in re.finditer(
                rf"""(?:^|\n)\s*import\s+(?:type\s+)?(\{{[^}}]*\}})\s*from\s*["']{re.escape(PACKAGE_NAME)}["']""",
                text,
            )
        ):
            importers += 1
        for hit in earlier._RELATIVE.finditer(text):
            target = earlier._target(rel, hit.group(1))
            stem = earlier._stem(target)
            if stem in _OLD_STEMS:
                bad.append(f"{rel}: {hit.group(1)} (an old path)")
            elif target.startswith(PACKAGE) and not rel.startswith(PACKAGE):
                bad.append(f"{rel}: {hit.group(1)} (into the package's folder, not its name)")
    return bad, importers


@pytest.fixture
def package_copy(tmp_path: Path) -> Path:
    """A repository-shaped root, `<tmp>/OspreyFlow_Core/packages/glass-shared/src`, holding a copy of the real package and
    a stub for the generated schemas; the real one is never written."""
    shutil.copytree(
        SHARED_SRC, tmp_path / SHARED, ignore=shutil.ignore_patterns("node_modules", "*.test.ts")
    )
    generated = tmp_path / "OspreyFlow_Core/packages/schemas/generated"
    generated.mkdir(parents=True)
    (generated / "index.ts").write_text("export {};\n", encoding="utf-8")
    return tmp_path


# ----------------------------------------------------------------------------------------------- the real tree: cases

_STAR = re.compile(r"""^export\s+\*\s+from\s+["']([^"']+)["'];""", re.M)
#: A record the index passes on (`export { default as X } from "./x/y.json"`, PL4d3e) is data, not a module of source: it is
#: not read as one.
_BRACED = re.compile(r"""^export\s+(?:type\s+)?\{([^}]*)\}\s+from\s+["']([^"']+(?<!\.json))["'];""", re.M)


def index_problems(
    index: str, sources: dict[str, str], required: Iterable[str] | None = None
) -> list[str]:
    """What is wrong with an index as the way in to `sources` (file -> its text): a file it does not export at all, a name
    of a file that no `export *` or braced export of it carries, and a name that two modules give at once. A braced export
    gives the name it renames to; a name a file only passes on from another (a type re-exported) is carried by that other.
    `sources` is every module the index names (so a name two of them give is found, a client's against an earlier one's);
    `required` the files that must be exported (by default all of them)."""
    problems = []
    required = list(sources) if required is None else list(required)
    stars = {module.removeprefix("./") + ".ts" for module in _STAR.findall(index)}
    braced: dict[str, set[str]] = {}
    for listed, module in _BRACED.findall(index):
        given = braced.setdefault(module.removeprefix("./") + ".ts", set())
        for item in listed.split(","):
            item = re.sub(r"^\s*type\s+", "", item.strip())
            if item:
                given.add(item.split(" as ")[-1].strip())
    gives: dict[str, list[str]] = {}
    for rel, text in sources.items():
        if rel in stars:
            for name in _exported_names(text):
                gives.setdefault(name, []).append(rel)
        for name in braced.get(rel, ()):
            gives.setdefault(name, []).append(rel)
    for rel in required:
        text = sources[rel]
        if rel not in stars and rel not in braced:
            problems.append(f"{rel} is not exported from the index")
            continue
        for name in sorted(_exported_names(text)):
            if name in gives:
                continue
            if rel in braced and name in {old for f, old, _ in RENAMED_BY_THE_INDEX if f == rel}:
                continue
            problems.append(f"{rel}: {name} is not exported from the index")
    for name, files in sorted(gives.items()):
        if len(set(files)) > 1:
            # one declaration passed on by a second file (a type re-exported) is one binding, not two
            owners = [
                f
                for f in set(files)
                if re.search(
                    rf"^export\s+(?:async\s+)?(?:function|const|let|class|type|interface|enum)\s+{re.escape(name)}\b",
                    sources[f],
                    re.M,
                )
            ]
            if len(owners) != 1:
                problems.append(f"{name} is given by {sorted(set(files))}: two modules, one name")
    for rel, old, new in RENAMED_BY_THE_INDEX:
        if rel in sources and new not in braced.get(rel, ()):
            problems.append(f"{rel}: {old} is not given as {new}")
    return problems


def test_the_sixteen_clients_are_in_the_package_and_not_in_the_workspace() -> None:
    names = earlier.tracked()
    for rel in WHOLE:
        new, old = SHARED + rel, OLD_OF[rel]
        assert (ROOT / new).is_file(), f"{new} is not in packages/glass-shared/src"
        assert not (ROOT / old).exists(), f"{old} is still where it was"
        assert new in names and old not in names
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    for rel in WHOLE:
        stem = "./" + rel.removesuffix(".ts")
        assert re.search(
            rf"""^export\s+(?:type\s+)?(?:\*|\{{[^}}]*\}})\s+from\s+["']{re.escape(stem)}["'];""",
            index,
            re.M,
        ), f"packages/glass-shared/src/index.ts does not export {stem}"


def _modules_of(index: str, root: Path = SHARED_SRC) -> dict[str, str]:
    """Every module the index names (the sixteen and the earlier slices'), keyed by its place under `src`."""
    named = {f"{m.removeprefix('./')}.ts" for m in _STAR.findall(index)}
    named |= {f"{m.removeprefix('./')}.ts" for _, m in _BRACED.findall(index)}
    named |= set(WHOLE)
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in sorted(named)}


def test_the_index_exports_every_name_of_every_moved_client() -> None:
    """Every name of every moved client is exported, by its own name or the one the index renames it to, and no name is
    given by two modules at once (the sixteen are read beside every other module the index names, so a clash with an
    earlier slice's client is found too)."""
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    assert index_problems(index, _modules_of(index), WHOLE) == []


def test_an_index_that_drops_or_doubles_a_name_is_found() -> None:
    """Red for the check above (rule 15), on the shapes the move could leave: the index as the real one is, clean; a braced
    export that leaves a name out; a second module giving a name already given; a file left out; the rename lost."""
    sources = {
        "boards/promotionsApi.ts": "export type A = 1;\nexport async function send(): Promise<void> {}\nexport const promote = 1;\n",
        "other/caseHttp.ts": "export async function send(): Promise<void> {}\n",
        "linktypes/http.ts": "export async function send(): Promise<void> {}\nexport class LinkTypeError {}\n",
        "linktypes/linkTypesApi.ts": 'export { LinkTypeError } from "./http";\nexport function rejectProposal(): void {}\n',
        "questions/questionsApi.ts": "export function rejectProposal(): void {}\nexport function askQuestion(): void {}\n",
    }
    index = (
        'export * from "./other/caseHttp";\n'
        'export { LinkTypeError, send as sendLinkType } from "./linktypes/http";\n'
        'export * from "./linktypes/linkTypesApi";\n'
        'export { askQuestion, rejectProposal as rejectQuestionProposal } from "./questions/questionsApi";\n'
        'export { type A, promote, send as sendPromotion } from "./boards/promotionsApi";\n'
    )

    def found(text: str, files: dict[str, str] = sources) -> list[str]:
        return index_problems(text, files)

    assert found(index) == []
    assert any("promote" in p for p in found(index.replace("promote, ", "")))
    assert any(
        "two modules, one name" in p for p in found(index.replace("send as sendPromotion", "send"))
    )
    assert any(
        "not exported" in p for p in found(index.replace('export * from "./other/caseHttp";\n', ""))
    )
    assert any(
        "rejectQuestionProposal" in p
        for p in found(index.replace("rejectProposal as rejectQuestionProposal", "rejectProposal"))
    )
    assert any(
        "two modules, one name" in p
        for p in found(
            index.replace(
                "askQuestion, rejectProposal as rejectQuestionProposal",
                "askQuestion, rejectProposal as rejectProposal",
            )
        )
    )


def test_the_new_clients_are_among_the_files_that_check_reads() -> None:
    """D2's check walks every `.ts` file of the package (tests apart): the sixteen are in it."""
    sources = clients._package_sources()
    for rel in WHOLE:
        assert SHARED + rel in sources, f"{rel} is not among the package's sources"
    problems = [p for rel in WHOLE for p in clients.package_import_problems(ROOT, SHARED + rel)]
    assert problems == [], f"{len(problems)} import(s) the package may not make: {problems[:10]}"


def test_a_react_or_workspace_import_in_a_moved_client_is_found(package_copy: Path) -> None:
    """Red for the check above (rule 15): in each of the sixteen, the lines the client would carry if it grew a hook, a
    store, or a path into the workspace (among them the way the workspace wrote a schema import, which is not the package's
    way). Each file is clean first, so the plant is what is found."""
    plants = (
        'import { useEffect } from "react";\n',
        'import { WITHHELD_SENTENCE } from "../statusbar/StatusBar";\n',
        'import { create } from "zustand";\n',
        'import BY_ROLE from "../../../../apps/workspace/src/shell/places.json";\n',
        'import type { Node } from "../../../../packages/schemas/generated";\n',
    )
    for rel in WHOLE:
        target = package_copy / (SHARED + rel)
        real = target.read_text(encoding="utf-8")
        assert clients.package_import_problems(package_copy, SHARED + rel) == [], (
            f"{rel} is not clean to begin with"
        )
        for line in plants:
            target.write_text(line + real, encoding="utf-8")
            assert clients.package_import_problems(package_copy, SHARED + rel), (
                f"{line!r} is not found in {rel}"
            )
        target.write_text(real, encoding="utf-8")


def self_imports(root: Path, rel: str) -> list[str]:
    """The lines of one package file that import the package by its own name: a cycle through the index."""
    text = (root / rel).read_text(encoding="utf-8")
    return [f"{rel}: {hit.group(0)}" for hit in _PACKAGE_IMPORT.finditer(text)]


def test_no_moved_client_imports_the_package_by_its_name() -> None:
    """The workspace wrote `from "@ospreyflow/glass-shared"` for the working-set types and the model deadline; inside the
    package they are the sibling modules, imported by their paths."""
    found = [line for rel in WHOLE for line in self_imports(ROOT, SHARED + rel)]
    assert found == [], f"{len(found)} moved client(s) import the package by its name: {found}"


def test_a_self_import_in_a_moved_client_is_found(package_copy: Path) -> None:
    """Red for the check above, at the shape the workspace wrote: a type from the working set, and a value from the model
    deadline, each by the package's name. Clean first."""
    for rel in WHOLE:
        target = package_copy / (SHARED + rel)
        real = target.read_text(encoding="utf-8")
        assert self_imports(package_copy, SHARED + rel) == []
        for line in (
            'import type { LimitExceeded } from "@ospreyflow/glass-shared";\n',
            'import { modelDeadline, unreachedWords } from "@ospreyflow/glass-shared";\n',
        ):
            target.write_text(line + real, encoding="utf-8")
            assert self_imports(package_copy, SHARED + rel), f"{line!r} is not found in {rel}"
        target.write_text(real, encoding="utf-8")


def test_the_move_changed_no_line_but_the_imports() -> None:
    """Each file is read as the commit that renamed it left it against the commit before: git's own detection finds the
    rename, and the two sides are compared there, never against the working tree (a later edit would be read as the move's).
    A shallow clone has no history to read: skipped, as the earlier move tests in this folder are."""
    earlier._skip_if_shallow()
    for rel in WHOLE:
        new, old = SHARED + rel, OLD_OF[rel]
        commit = earlier._git(
            "log", "--follow", "-M", "--diff-filter=R", "--format=%H", "-1", "--", new
        ).strip()
        assert commit, f"git finds no rename into {new}: the file was not moved with `git mv`"
        assert earlier._git("show", f"{commit}^:{old}"), (
            f"{old} is not in the commit before the rename"
        )
        assert (
            earlier.only_import_lines_changed(
                earlier._git("show", f"{commit}^:{old}"), earlier._git("show", f"{commit}:{new}")
            )
            == []
        ), f"{new} changed in more than its import lines"


def test_no_tracked_file_names_an_old_path() -> None:
    rels = [rel for rel in earlier.tracked() if not _kept_out(rel)]
    assert len(rels) > 1000, (
        "the walk found too few files: git ls-files is not listing the repository"
    )
    found = old_path_mentions(ROOT, rels)
    shown = "\n".join(f"  {rel}:{line}: {text[:140]}" for rel, line, text in found[:40])
    assert found == [], (
        f"{len(found)} place(s) still name an old path; the files are now in {SHARED}:\n{shown}"
    )


def test_every_named_exception_still_has_its_reason() -> None:
    """An exception outlives its reason when the file it excuses no longer names an old path: left in `NAMED` it keeps that
    file outside the walk, and an old path could be written back into it unseen (rule 12)."""
    stale = [rel for rel in NAMED if not old_path_mentions(ROOT, [rel])]
    assert stale == [], (
        f"{stale} no longer name an old path: remove them from NAMED, and the walk will cover them"
    )


def test_every_import_of_a_moved_client_reaches_the_package() -> None:
    bad, importers = imports_not_reaching(ROOT, earlier.tracked())
    assert importers >= 50, (
        f"only {importers} file(s) under OspreyFlow_Core import a client's name from {PACKAGE_NAME}: the walk found too few imports, or the importers were not repointed"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach the package by its name: {bad[:10]}"


_PLANTED_IMPORTS = {
    # (path of the file that held the line, the line as the tree wrote it, the line it has now)
    "the views' calls, from the app": (
        WORKSPACE_SRC + "App.tsx",
        'import { type CaseView, type CaseViewOpened, listViews, openView, saveView } from "./views/viewsApi";',
        f'import {{ type CaseView, type CaseViewOpened, listViews, openView, saveView }} from "{PACKAGE_NAME}";',
    ),
    "the views' calls, from a keyboard harness outside src": (
        APPS + "workspace/keyboard/harness.tsx",
        'import { saveView } from "../src/views/viewsApi";',
        f'import {{ saveView }} from "{PACKAGE_NAME}";',
    ),
    "the batch expansion's type, from a keyboard harness outside src": (
        APPS + "workspace/keyboard/batch-expansion-harness.tsx",
        'import type { BatchExpansionRequest } from "../src/workingset/batchExpansionApi";',
        f'import type {{ BatchExpansionRequest }} from "{PACKAGE_NAME}";',
    ),
    "the link change's type, from a keyboard harness outside src": (
        APPS + "workspace/keyboard/link-change-harness.tsx",
        'import type { LinkChangeResult } from "../src/inspector/linkChangeApi";',
        f'import type {{ LinkChangeResult }} from "{PACKAGE_NAME}";',
    ),
    "the dossier's model, from the accessibility showcase": (
        APPS + "workspace/a11y/showcase.tsx",
        'import type { DocumentView } from "../src/dossier/models";',
        f'import type {{ DocumentView }} from "{PACKAGE_NAME}";',
    ),
    "the fact bringer, from the keyboard harness": (
        APPS + "workspace/keyboard/harness.tsx",
        'import { bringFactIntoView } from "../src/questions/graphFacts";',
        f'import {{ bringFactIntoView }} from "{PACKAGE_NAME}";',
    ),
    "the analytics calls, from the cross-filter store": (
        WORKSPACE_SRC + "crossfilter/store.ts",
        'import { fetchFirstSeen } from "../analytics/api";',
        f'import {{ fetchFirstSeen }} from "{PACKAGE_NAME}";',
    ),
    "a double of an analytics call, as a vi.mock": (
        WORKSPACE_SRC + "map/HotspotHistogram.stale.test.tsx",
        'vi.mock("../analytics/api", () => ({',
        f'vi.mock("{PACKAGE_NAME}", () => ({{',
    ),
    "the analytics module as a namespace, to spy on": (
        WORKSPACE_SRC + "crossfilter/store.test.ts",
        'import * as api from "../analytics/api";',
        f'import * as api from "{PACKAGE_NAME}";',
    ),
    "the promotions' two helpers, from the Studio's Runs grid": (
        WORKSPACE_SRC + "ingest/runs/drawnMergeApi.ts",
        'import { answered, send } from "../../boards/promotionsApi";',
        f'import {{ answered, sendPromotion as send }} from "{PACKAGE_NAME}";',
    ),
    "the link types' calls, beside them": (
        WORKSPACE_SRC + "linktypes/DefineLinkType.tsx",
        'import { LinkTypeError, proposeLinkType, type LinkTypeProposal } from "./linkTypesApi";',
        f'import {{ LinkTypeError, proposeLinkType, type LinkTypeProposal }} from "{PACKAGE_NAME}";',
    ),
    "the model proposals' calls, beside them": (
        WORKSPACE_SRC + "linktypes/ModelProposals.tsx",
        'import { decideModelProposal, listModelProposals, type ModelProposal } from "./modelProposalsApi";',
        f'import {{ decideModelProposal, listModelProposals, type ModelProposal }} from "{PACKAGE_NAME}";',
    ),
    "the question's answer type, beside it": (
        WORKSPACE_SRC + "questions/AnswerActions.tsx",
        'import type { QuestionAnswer } from "./questionsApi";',
        f'import type {{ QuestionAnswer }} from "{PACKAGE_NAME}";',
    ),
    "the reader's view, from the inspector": (
        WORKSPACE_SRC + "inspector/Inspector.tsx",
        'import type { DocumentReaderView } from "../reader/readerApi";',
        f'import type {{ DocumentReaderView }} from "{PACKAGE_NAME}";',
    ),
    "the link events' words, from the canvas": (
        WORKSPACE_SRC + "canvas/GlassCanvas.tsx",
        'import { eventsEntryLabel, eventsNoun, mayCarryText } from "../inspector/linkEventsApi";',
        f'import {{ eventsEntryLabel, eventsNoun, mayCarryText }} from "{PACKAGE_NAME}";',
    ),
    "the email documents, beside them": (
        WORKSPACE_SRC + "inspector/LinkEvents.tsx",
        'import { emailsOutcomeText, showEmailsAsDocuments } from "./emailDocuments";',
        f'import {{ emailsOutcomeText, showEmailsAsDocuments }} from "{PACKAGE_NAME}";',
    ),
    "the last line of a many-line import of the notes' calls": (
        WORKSPACE_SRC + "inspector/LinkNotes.tsx",
        '} from "./linkNotesApi";',
        f'}} from "{PACKAGE_NAME}";',
    ),
    "a deep import into the package": (
        WORKSPACE_SRC + "views/ViewsPanel.tsx",
        'import { listViews } from "../../../../packages/glass-shared/src/views/viewsApi";',
        f'import {{ listViews }} from "{PACKAGE_NAME}";',
    ),
    "a bare file name in a guide": (
        "OspreyFlow_Core/docs/administration-guide.md",
        "The saved views' calls are in `viewsApi.ts` and nowhere else.",
        "The saved views' calls are in the views module and nowhere else.",
    ),
    "an old path in the function record": (
        "OspreyFlow_Core/apps/pages/FUNCTIONS.yaml",
        '    where: "apps/workspace/src/linktypes/ModelProposals.tsx, modelProposalsApi.ts, mounted apps/workspace/src/ingest/IngestStudio.tsx:20,219 (shares linktypes/http.ts 53 and packages/glass-shared/src/linktypes/linkTypesApi.ts 171)"',
        '    where: "apps/workspace/src/linktypes/ModelProposals.tsx, packages/glass-shared/src/linktypes/modelProposalsApi.ts, mounted apps/workspace/src/ingest/IngestStudio.tsx:20,219 (shares packages/glass-shared/src/linktypes/http.ts 53 and packages/glass-shared/src/linktypes/linkTypesApi.ts 171)"',
    ),
    "the views' calls, written in segments": (
        APPS + "workspace/a11y/plants/run.mjs",
        'const views = join(HERE, "..", "..", "src", "views", "viewsApi");',
        'const views = join(HERE, "..", "..", "..", "..", "packages", "glass-shared", "src", "views", "viewsApi");',
    ),
}


@pytest.mark.parametrize("case", sorted(_PLANTED_IMPORTS))
def test_an_old_path_put_back_in_one_importer_is_found(case: str, package_copy: Path) -> None:
    """Red for the two walks above (rule 15): each line the tree really held, put back in the file that held it (or one the
    move could have left it in). The same file with the new line is clean first, so the plant is what is found and not
    something else in the file. The package's own copies are in the tree under `package_copy`, so the names are known."""
    rel, old_line, new_line = _PLANTED_IMPORTS[case]
    target = package_copy / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_line + "\n", encoding="utf-8")
    assert (
        imports_not_reaching(package_copy, [rel])[0] == []
        and old_path_mentions(package_copy, [rel]) == []
    )
    target.write_text(old_line + "\n", encoding="utf-8")
    assert imports_not_reaching(package_copy, [rel])[0] or old_path_mentions(package_copy, [rel]), (
        f"neither walk finds {old_line!r} in {rel}"
    )


def test_a_file_that_names_no_client_is_not_counted_as_an_importer(package_copy: Path) -> None:
    """The importers' floor means something only if a file that takes some other name from the package is not one."""
    rel = WORKSPACE_SRC + "theme/ThemeToggle.tsx"
    (package_copy / rel).parent.mkdir(parents=True)
    (package_copy / rel).write_text(
        f'import {{ applyTheme }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
    )
    assert imports_not_reaching(package_copy, [rel]) == ([], 0)
    for name in ("listViews", "sendPromotion", "rejectQuestionProposal"):
        (package_copy / rel).write_text(
            f'import {{ {name} }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
        )
        assert imports_not_reaching(package_copy, [rel]) == ([], 1), name


def test_every_import_reached_from_a_spec_resolves() -> None:
    """The Playwright collection check's own half: a spec that imports a file that is gone fails at collection, which no unit
    test runs. Every relative import, reached from any spec by any chain, names a file."""
    specs = earlier.spec_files(earlier.tracked())
    assert len(specs) >= 100, (
        f"only {len(specs)} spec files found: the walk is not seeing the specs"
    )
    missing, reached = earlier.unresolved_from_specs(ROOT, specs)
    assert reached >= 400, f"the walk reached only {reached} files: it is not following imports"
    assert missing == [], f"{len(missing)} import(s) name no file: {missing[:10]}"


def test_a_spec_that_imports_a_path_that_no_longer_exists_is_found(tmp_path: Path) -> None:
    """Red for the walk above, at the shapes the move could leave: a spec's harness still importing a client by the old path
    (the line the tree held in `keyboard/batch-expansion-harness.tsx`), and the index exporting a file that is not there."""
    spec = APPS + "workspace/keyboard/batch-expansion.spec.ts"
    harness = APPS + "workspace/keyboard/batch-expansion-harness.tsx"
    files = {
        spec: 'import { mount } from "./batch-expansion-harness";\n',
        harness: f'import {{ openView }} from "{PACKAGE_NAME}";\n',
        SHARED + "index.ts": 'export * from "./views/viewsApi";\n',
        SHARED + "views/viewsApi.ts": "export const openView = 1;\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == []
    (tmp_path / harness).write_text(
        'import { openView } from "../src/views/viewsApi";\n', encoding="utf-8"
    )
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [
        f"{harness}: ../src/views/viewsApi"
    ]
    (tmp_path / harness).write_text(
        f'import {{ openView }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
    )
    (tmp_path / SHARED / "views" / "viewsApi.ts").unlink()
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [
        f"{SHARED}index.ts: ./views/viewsApi"
    ]


# ------------------------------------------------------------------------------------------------------- the images

WORKSPACE_IMAGE = CORE / "apps" / "workspace" / "Dockerfile"


def stale_copies(dockerfile: str) -> list[str]:
    """The sources a stage copies that name the place a client moved from: the file itself."""
    old = {"/".join(p.split("/")[4:]) for p in OLD_OF.values()}  # under `apps/workspace/src/`
    return sorted(
        src
        for src in clients.copy_sources(dockerfile)
        if src.startswith("apps/workspace/src/") and src.removeprefix("apps/workspace/src/") in old
    )


def test_no_image_copies_a_path_that_moved() -> None:
    """Neither image names a moved file in a `COPY`, and each copies the package's source."""
    for dockerfile in (WORKSPACE_IMAGE, image.DOCKERFILE):
        text = dockerfile.read_text(encoding="utf-8")
        assert stale_copies(text) == [], f"{dockerfile.name} copies a path that moved"
        assert "packages/glass-shared/src" in clients.copy_sources(text), (
            f"{dockerfile.parent.name}/{dockerfile.name} does not copy packages/glass-shared/src"
        )


def test_the_harness_image_copies_what_the_clients_need() -> None:
    """The harness frontend reaches the package's index, and by it every client: each file it reaches is under a `COPY`, and
    every `COPY` of a workspace path still names something that exists and is reached. The walk reaches the sixteen."""
    reached = image._reached_workspace_files()
    copied = image._copied_paths()
    assert image._missing(copied, reached) == []
    assert earlier.dangling(copied, reached) == []
    names = {str(p.relative_to(CORE.resolve())) for p in reached}
    for rel in WHOLE:
        assert f"packages/glass-shared/src/{rel}" in names, (
            f"the walk does not reach the package's {rel}"
        )


def test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found() -> None:
    """Red for the checks above (rule 15), on the real stages: the package's line taken out of the harness image (the
    clients the index reaches are missing), a line a moved file once needed put in (it copies a file that is not there),
    and the same two faults on the workspace image."""
    real = image.DOCKERFILE.read_text(encoding="utf-8")
    reached = image._reached_workspace_files()
    assert stale_copies(real) == []
    assert image._missing(image._copied_paths(real), reached) == []

    shared = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    assert shared in real
    missing = image._missing(image._copied_paths(real.replace(shared, "", 1)), reached)
    for rel in WHOLE:
        assert f"packages/glass-shared/src/{rel}" in missing, f"{rel} is not found missing"

    for rel in ("views/viewsApi.ts", "analytics/api.ts", "dossier/models.ts"):
        line = f"COPY apps/workspace/src/{rel} ./apps/workspace/src/{rel}\n"
        stale = real.replace(shared, shared + line, 1)
        assert stale_copies(stale) == [f"apps/workspace/src/{rel}"]
        assert earlier.dangling(image._copied_paths(stale), reached) == [
            f"apps/workspace/src/{rel}"
        ]

    workspace = WORKSPACE_IMAGE.read_text(encoding="utf-8")
    assert stale_copies(workspace) == []
    package_line = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    assert package_line in workspace
    assert "packages/glass-shared/src" not in clients.copy_sources(
        workspace.replace(package_line, "", 1)
    )
    assert stale_copies(workspace + "COPY apps/workspace/src/reader/readerApi.ts ./x\n") == [
        "apps/workspace/src/reader/readerApi.ts"
    ]


# --------------------------------------------------------------------------------------------------- the four gates

#: The files each gate read on main before this move: the number each reported or, where it reports none, the files its own
#: rules select (measured on 21 November 2026, on the tip PL4d3b started from, after PL4d3a). The sixteen clients moved from a
#: folder each gate reads to another it reads, so the numbers do not fall: none may.
FILES_BEFORE = {"colour-drift": 489, "design-check": 898, "ui-words": 496, "no-branches": 1743}


def test_each_gate_reads_no_fewer_files_than_before() -> None:
    now = {
        "colour-drift": colour_drift_check.scanned_count(),
        "design-check": earlier._design_files(design_check.SCANNED),
        "ui-words": earlier._ui_words_files(),
        "no-branches": len(no_branches_check.tree_files()),
    }
    assert all(now[gate] >= before for gate, before in FILES_BEFORE.items()), (
        f"a gate reads fewer files than before: now {now}, before {FILES_BEFORE}"
    )


@pytest.fixture
def shared_copy(tmp_path: Path) -> Path:
    """`<tmp>/packages/glass-shared/src`, a copy of the real folder; the real one is never written."""
    copy = tmp_path / "packages" / "glass-shared" / "src"
    shutil.copytree(SHARED_SRC, copy, ignore=shutil.ignore_patterns("node_modules"))
    return copy


def test_the_colour_drift_check_reports_a_plant_in_a_moved_client(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    mirrors = dict(colour_drift_check.SCANNED).get(SHARED_SRC)
    assert mirrors is not None, "the colour-drift check does not read the package"
    monkeypatch.setattr(colour_drift_check, "CORE", shared_copy.parent.parent.parent)
    monkeypatch.setattr(colour_drift_check, "SCANNED", ((shared_copy, mirrors),))
    assert colour_drift_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    earlier._append(
        shared_copy,
        "views/viewsApi.ts",
        '\nexport const STRIPE = { background: "#12ab34", padding: 8 };\n',
    )
    assert colour_drift_check.main() == 1
    assert "packages/glass-shared/src/views/viewsApi.ts:" in capsys.readouterr().out


def test_the_design_detector_reports_a_plant_in_a_moved_client(
    shared_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(design_check, "SCANNED", [shared_copy])
    assert design_check.unexcused(design_check.detect(design_check.SCANNED)) == [], (
        "the clean copy already has findings"
    )
    earlier._append(
        shared_copy,
        "inspector/linkNotesApi.ts",
        "\nexport const TOAST_STYLE = {\n"
        '  background: "var(--surface-raised)", borderLeft: "3px solid var(--error)", borderRadius: "8px",\n'
        '  padding: "12px 16px", boxShadow: "var(--overlay-shadow)",\n'
        "};\n",
    )
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [
        ("linkNotesApi.ts", "side-tab")
    ]


def test_the_ui_words_check_reports_a_plant_in_a_moved_client(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = shared_copy.parent.parent / "no-src"
    empty.mkdir()
    monkeypatch.setattr(ui_words_check, "SHARED_SRC", shared_copy)
    monkeypatch.setattr(ui_words_check, "GLASS_SRC", empty)
    monkeypatch.setattr(ui_words_check, "DESIGN_PACKAGE", empty)
    assert ui_words_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    earlier._append(shared_copy, "reader/readerApi.ts", '\nexport const LABEL = "Target model";\n')
    assert ui_words_check.main() == 1
    assert "packages/glass-shared/src/reader/readerApi.ts:" in capsys.readouterr().out


def test_the_no_branches_check_reports_a_plant_in_a_moved_client(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    top = "packages/glass-shared/src"
    assert top in no_branches_check.SCANNED
    walk = no_branches_check.tree_files
    tmp_core = shared_copy.parent.parent.parent
    monkeypatch.setattr(no_branches_check, "tree_files", lambda: walk(tmp_core, [top]))
    assert no_branches_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    earlier._append(
        shared_copy, "analytics/api.ts", '\nexport const BRANCH_CASE = "branch-by-filter";\n'
    )
    assert no_branches_check.main() == 1
    assert f"{top}/analytics/api.ts:" in capsys.readouterr().out


# -------------------------------------------------------------------------------------------------- the word-walkers

#: The sixteen as (folder, stem) pairs, never written as a path (the old-path scan reads the other walkers' tables too).
_MOVED = {
    "inspector": ("emailDocuments", "linkChangeApi", "linkEventsApi", "linkNotesApi"),
    "linktypes": ("http", "linkTypesApi", "modelProposalsApi"),
    "questions": ("questionsApi", "graphFacts"), "reader": ("readerApi",), "dossier": ("api", "models"),
    "views": ("viewsApi",), "workingset": ("batchExpansionApi",), "boards": ("promotionsApi",), "analytics": ("api",),
}  # fmt: skip
MOVED_CLIENTS = tuple(f"{folder}/{stem}.ts" for folder, stems in _MOVED.items() for stem in stems)


def test_the_moved_table_is_the_list_of_sixteen() -> None:
    assert sorted(MOVED_CLIENTS) == sorted(WHOLE)


@pytest.mark.parametrize("client", MOVED_CLIENTS)
def test_the_people_name_walk_reads_each_moved_client(client: str, tmp_path: Path) -> None:
    """The walk behind `test_people_section_words.py` reads the client at its place in the package and not at its old one;
    the same copy, clean, finds nothing, and with an old name planted at the line a person's words sit on it is found."""
    read = {p.relative_to(CORE).as_posix() for p in people._glass_files()}
    assert f"packages/glass-shared/src/{client}" in read, client
    assert f"apps/workspace/src/{client}" not in read, client
    real = (CORE / "packages/glass-shared/src" / client).read_text(encoding="utf-8")
    copy = tmp_path / "src" / client
    copy.parent.mkdir(parents=True)
    copy.write_text(real, encoding="utf-8")

    def found() -> list[int]:
        return [
            n
            for p in people._glass_files((tmp_path / "src",))
            for n in people._text(p.read_text(encoding="utf-8"), comments=True)
        ]

    assert found() == []
    copy.write_text(
        real + '\nexport const planted = "Set it in Admin › People.";\n', encoding="utf-8"
    )
    assert found() == [real.count("\n") + 2]


@pytest.mark.parametrize("client", MOVED_CLIENTS)
def test_the_view_word_walk_reads_each_moved_client(client: str, tmp_path: Path) -> None:
    """The same for the walk behind `test_guide_navigation_words.py`: read at its place in the package, clean finds nothing,
    an old view word on screen is found, and in a comment (which a person never sees) it is not."""
    sources = navigation.glass_sources()
    assert client in sources, client
    assert not (navigation.SRC / client).exists(), client
    real = (navigation.GLASS_ROOTS[1] / client).read_text(encoding="utf-8")
    copy = tmp_path / "src" / client
    copy.parent.mkdir(parents=True)
    copy.write_text(real, encoding="utf-8")
    assert navigation.old_view_words_on_screen(navigation.glass_sources((tmp_path / "src",))) == []
    copy.write_text(real + '\nexport const planted = "Clear view";\n', encoding="utf-8")
    assert navigation.old_view_words_on_screen(navigation.glass_sources((tmp_path / "src",))) == [
        f"{client}: 'Clear view'"
    ]
    copy.write_text(real + "\n// Clear view, a comment\n", encoding="utf-8")
    assert navigation.old_view_words_on_screen(navigation.glass_sources((tmp_path / "src",))) == []


@pytest.mark.parametrize("planted_in", [0, 1])
def test_a_moved_clients_place_held_by_both_roots_is_read_from_both(
    planted_in: int, tmp_path: Path
) -> None:
    """Keyed by root (D2's last finding): a place that two roots both hold is kept under both. A client's place held by the
    workspace and by the package at once: an old word in either is found, the second root's under `shared:`."""
    roots = (tmp_path / f"a{planted_in}", tmp_path / f"b{planted_in}")
    for n, root in enumerate(roots):
        (root / "views").mkdir(parents=True)
        (root / "views" / "viewsApi.ts").write_text(
            'export const word = "Clear view";\n'
            if n == planted_in
            else "export const word = 1;\n",
            encoding="utf-8",
        )
    expected = "views/viewsApi.ts" if planted_in == 0 else "shared:views/viewsApi.ts"
    assert navigation.old_view_words_on_screen(navigation.glass_sources(roots)) == [
        f"{expected}: 'Clear view'"
    ]


KIT = CORE / "apps" / "workspace" / "src" / "copyTextsTestKit.ts"
_KIT_FOLDERS = re.compile(r"^export const MOVED_FOLDERS = /(.*)/;$", re.M)


def test_the_vitest_walkers_name_the_new_folders() -> None:
    """`copyWords`, `copyNoClient` and `resolvedPrincipal` walk the kit's two roots, and each has a case that plants in a copy
    of every file the kit lists as a link client. The kit selects the package's folders by `MOVED_FOLDERS`: every folder of
    the sixteen is among them (the vitest cases themselves run under `npm test --workspace apps/workspace`)."""
    kit = KIT.read_text(encoding="utf-8")
    found = _KIT_FOLDERS.search(kit)
    assert found, (
        "copyTextsTestKit.ts does not state MOVED_FOLDERS as one regular expression on a line of its own"
    )
    folders = re.compile(found.group(1))
    for rel in WHOLE:
        assert folders.search(f"/glass-shared/src/{rel}"), f"MOVED_FOLDERS does not select {rel}"
    assert "ROOTS" in kit and "SHARED_SRC" in kit
    assert "LINK_CLIENTS" in kit and "plantedLinkClients" in kit, (
        "the kit does not list the link clients or plant in them"
    )
    block = kit[kit.index("const LINK_STEMS") :].split("};", 1)[0]
    for folder, stems in _MOVED.items():
        assert re.search(rf"\b{folder}:", block) and all(f'"{stem}"' in block for stem in stems), (
            f"the kit's list of link clients leaves out {folder}"
        )
    for walker in ("copyWords.test.ts", "copyNoClient.test.ts", "auth/resolvedPrincipal.test.ts"):
        text = (KIT.parent / walker).read_text(encoding="utf-8")
        assert "LINK_CLIENTS" in text and "plantedLinkClients" in text, (
            f"{walker} has no plant in the link clients"
        )
    # The selector is a real filter: a folder the clients are not in is not selected.
    assert not folders.search("/glass-shared/src/keyboard/actionRegistry.ts")
