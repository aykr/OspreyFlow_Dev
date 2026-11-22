"""The canvas and graph logic, `color/nodeVisual.ts` and `ontology/schema.ts` move to `packages/glass-shared` (ADR-152 decision 6,
"logic, stores, the panel pattern, the Conduit client, the keyboard action registry, structural types for the map and graph";
slice PL4e, the eleventh of the PL4 slices after A, B, B2, B3, C, D1, D2, D3a to D3e; the owner's rulings of 22 November 2026,
files 013 and 014). Nothing changes on screen, and **this slice proves SAME**: the built output is the baseline's apart from
file paths, so nothing here is a declared unit.

**Twenty-five files move whole, and not one of them is split.** Their lines are unchanged but for the import lines (the schema
import written the package's way, and a name that the file took from the package's own index taken from the file that holds it).

* `canvas/` (23): `nodeGestures`, `forceLayout`, `removeNodes`, `edgeSelection`, `settledAnchor`, `nodeDrag`, `nodeHitArea`,
  `chunkedTextureRefresh`, `provenancePatterns`, `singleFlight`, `focusAnnouncement`, `linkLabel`, `zoomBands`, `edgeTypeMenu`,
  `expansionGate`, `expansionPreview`, `expansionOutcome`, `layoutModes`, `cameraMoves`, `communityLinks`, `linkHover`,
  `linksAmong`, `valueIcons`.
* Outside `canvas/` (2): `color/nodeVisual.ts` and `ontology/schema.ts`.

**What stays, by the owner's rulings** (and is held here as it is): `communities`, `communityAssigner`, `communityWorker`,
`labelChoices`, `iconChoices`; the five files that must be split (`iconImage`, `linkMenu`, `selectionActions`, `toolbarCompact`,
`toolbarVisibility`: backlog row 17); the three that import a drawing library (`dottedEdgePrograms`, `communityLinkLayer`,
`labelStyle`); `linkCollapse`, `nodeLabel` and `nodeAttributes` (they import a file that stays), and `entityPictures` (D3e's, which
the workspace's binding keeps).

**The browser globals the package may use.** The package may not name `window`, `document`, `sessionStorage` or `localStorage` (D3e's
rule, read here on code and not on comments: `nodeVisual.ts` has a comment that says "document" glyph, and a move changes no word).
`requestAnimationFrame` is not among them and is used by `chunkedTextureRefresh.ts` (as the default of an injected `nextFrame`) and
`cameraMoves.ts` (to ask a Sigma it is handed, as a parameter, to refresh); `fetch` is used by `linksAmong.ts` and `ontology/schema.ts`
as the other Conduit clients use it, with the address and the bearer token as arguments. The Glass's `graphology` is already a
dependency of the package (slice C), and `linkHover.ts` takes it as a type only.

Which test fails if the invariant is broken (rule 12):

* a file not where it should be, an old one back, one that should stay moved, or the index leaving one out or giving a name twice:
  `test_the_files_are_where_they_should_be`, `test_the_files_that_stay_stay`, `test_the_index_exports_every_name_of_every_moved_module`,
  with `test_an_index_that_drops_or_doubles_a_name_is_found`;
* a file of the package importing React, a drawing library, a package of the workspace, the package by its own name, any bare package
  but `graphology` as a type, or a path of the workspace: `test_the_moved_files_import_no_react_no_drawing_library_and_no_workspace_path`,
  with `test_a_forbidden_import_in_a_moved_file_is_found` (a plant of each, in each file);
* **a page or tab object in the package** (`window`, `document`, `sessionStorage`, `localStorage`):
  `test_the_moved_files_use_no_page_or_tab_object`, with `test_a_page_or_tab_object_in_a_moved_file_is_found` (a plant of each in
  each file, `zoomBands.ts` among them as the brief names, and a comment naming one is not a use);
* **an import-time effect** (the package says `sideEffects: false`): `test_the_moved_files_have_no_top_level_effect`, with
  `test_a_top_level_effect_in_a_moved_file_is_found`;
* a whole file changed in more than its import lines at the commit that moved it: `test_the_move_changed_no_line_but_the_imports`,
  with `test_a_moved_file_changed_in_more_than_its_imports_is_found`;
* a file naming an old path, written whole or in pieces (`/ "canvas" / "zoomBands.ts"`): `test_no_tracked_file_names_an_old_path`,
  with `test_an_old_path_written_in_pieces_or_whole_is_found`; an importer still reaching one: `test_every_import_of_a_moved_module_reaches_the_package`,
  with `test_an_old_path_put_back_in_one_importer_is_found`; a spec naming a file that is gone:
  `test_every_import_reached_from_a_spec_resolves`, with `test_a_spec_that_imports_a_path_that_no_longer_exists_is_found`;
* **a mock that no longer intercepts** (the eight App tests mocked `./ontology/schema`; the module is the package's now, and a second
  `vi.mock` of the package would override the first): `test_the_eight_app_tests_mock_the_package_once`, with
  `test_a_mock_that_names_the_old_module_or_the_package_twice_is_found` (the tests themselves run under
  `npm test --workspace apps/workspace`);
* an image `COPY` naming a moved path, or missing what the harness needs: `test_no_image_copies_a_path_that_moved`,
  `test_the_harness_image_copies_what_the_moved_files_need`, each shown red by `test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found`;
* a gate that stops reading the files, or reads fewer: `test_each_gate_reads_no_fewer_files_than_before`, and one plant for each gate in a
  **moved** file.

**This file walks:** `git ls-files` over the whole repository (the old-path test, whole and in pieces, which skips the decision log and
`OspreyFlow_Build/process/`, and the package's own files, where a module is named by its place); the tracked `.ts`, `.tsx`, `.mts`,
`.mjs`, `.js` and `.jsx` files under `OspreyFlow_Core/` (the import tests, which read the apps, the harness folders, the keyboard and
live folders and the package, and the spec walk, which starts at every tracked `*.spec.ts` and `*.spec.tsx` in `apps/workspace` and
`apps/harness` and follows their imports); the twenty-five moved files and `packages/glass-shared/src/index.ts`; the eight App test
files by name; `apps/workspace/Dockerfile` and `harness/Dockerfile` by name; the four gates' own scan roots, through the gates'
own functions; the manifest of the package; the git history of the renames (`git log`, `git show`); and temporary copies built inside
`tmp_path` for the plants (written there, never in the repository), among them copies of `packages/glass-shared/src`.
"""

# The planted lines below are the real call-site shapes, kept on one line as the tree wrote them (rule 15), and the
# prose beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import json
import posixpath
import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from unittest import mock

import pytest
from tools import colour_drift_check, design_check, no_branches_check, ui_words_check
from tools.layout import CORE, ROOT

from tests.glass_trees import test_glass_shared_admin_clients as admin
from tests.glass_trees import test_glass_shared_case_clients as case
from tests.glass_trees import test_glass_shared_clients as clients
from tests.glass_trees import test_glass_shared_link_clients as link
from tests.glass_trees import test_glass_shared_plain_clients as plain
from tests.glass_trees import test_glass_shared_plain_logic as earlier
from tests.harness import test_harness_frontend_copies as image

PACKAGE = "OspreyFlow_Core/packages/glass-shared/"
SHARED = PACKAGE + "src/"
SHARED_SRC = CORE / "packages" / "glass-shared" / "src"
APPS = "OspreyFlow_Core/apps/"
WORKSPACE_SRC = APPS + "workspace/src/"
PACKAGE_NAME = "@ospreyflow/glass-shared"

#: The twenty-three canvas files: the thirteen that import nothing, then the ten that import the schemas or a file above.
CANVAS_STEMS = (
    "nodeGestures", "forceLayout", "removeNodes", "edgeSelection", "settledAnchor", "nodeDrag", "nodeHitArea",
    "chunkedTextureRefresh", "provenancePatterns", "singleFlight", "focusAnnouncement", "linkLabel", "zoomBands",
    "edgeTypeMenu", "expansionGate", "expansionPreview", "expansionOutcome", "layoutModes", "cameraMoves",
    "communityLinks", "linkHover", "linksAmong", "valueIcons",
)  # fmt: skip
CANVAS = tuple(f"canvas/{stem}.ts" for stem in CANVAS_STEMS)
OUTSIDE = ("color/nodeVisual.ts", "ontology/schema.ts")
#: The twenty-five files moved whole (relative to `SHARED`; the old place is the same relative path under `WORKSPACE_SRC`).
WHOLE = CANVAS + OUTSIDE
OLD_OF = {rel: WORKSPACE_SRC + rel for rel in WHOLE}
_OLD_STEMS = {old.removesuffix(".ts") for old in OLD_OF.values()}

#: What stays in the workspace's `canvas/` by the owner's rulings, with the reason; none is in the package. (`entityPictures` is held
#: by both: the package's plain half is D3e's, the workspace's file binds it.)
STAYS = {
    "canvas/communities.ts": "the community files stay (file 013, 3)",
    "canvas/communityAssigner.ts": "the community files stay (file 013, 3)",
    "canvas/communityWorker.ts": "the community files stay (file 013, 3)",
    "canvas/labelChoices.ts": "reads and writes localStorage (file 013, 4)",
    "canvas/iconChoices.ts": "reads and writes localStorage (file 013, 4)",
    "canvas/iconImage.ts": "must be split (file 013, 5; backlog row 17)",
    "canvas/linkMenu.ts": "must be split (file 013, 5; backlog row 17)",
    "canvas/selectionActions.ts": "must be split (file 013, 5; backlog row 17)",
    "canvas/toolbarCompact.ts": "must be split (file 013, 5; backlog row 17)",
    "canvas/toolbarVisibility.ts": "must be split (file 013, 5; backlog row 17)",
    "canvas/dottedEdgePrograms.ts": "imports a drawing library",
    "canvas/communityLinkLayer.ts": "imports a drawing library",
    "canvas/labelStyle.ts": "imports a drawing library",
    "canvas/linkCollapse.ts": "imports ./communities, which stays",
    "canvas/nodeLabel.ts": "imports ./labelChoices, which stays",
    "canvas/nodeAttributes.ts": "imports ./iconChoices and ./labelChoices, which stay",
}
HELD_BY_BOTH = "canvas/entityPictures.ts"

#: The names the index gives under another because two modules wrote one name: (file, the name it wrote, the name the package
#: exports it as). Filled from what the typechecker found when the index was written (see `index.ts`'s header).
RENAMED_BY_THE_INDEX: tuple[tuple[str, str, str], ...] = ()

#: The places that may name an old path because they are a record of the past: the decision log, and the build record under
#: `process/`. They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone (`test_every_named_exception_still_has_its_reason`).
NAMED = {
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_glass_shared_canvas_logic.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

#: The forms an old path takes in prose and code: not `canvas/linkLabel.test.ts` (the tests stayed in the workspace, beside where the
#: files were), not a longer path (`ontology/schema/ontology.schema.json` is the ontology's own record), and not the same words
#: with the package's place in front of them.
_NAME_FORMS = tuple(re.escape(rel.removesuffix(".ts")) for rel in WHOLE)
_TEXT_FORM = re.compile(
    rf"(?<!glass-shared/src/)(?<!packages/)(?<![\w-])(?:{'|'.join(_NAME_FORMS)})\b(?![\w-])(?!/)(?!\.(?:css|test\.|spec\.|budget\.|py|bak))"
)
_SEGMENT_FORMS = tuple(
    rf"""{folder}["']\s*[,/]\s*["']{stem}"""
    for folder, stem in (rel.removesuffix(".ts").split("/") for rel in WHOLE)
)
#: The segments of one written apart: `join(HERE, "..", "src", "canvas", "zoomBands")`, Python's `/ "canvas" / "zoomBands.ts"`.
_SEGMENT_FORM = re.compile(rf"""["'](?:{'|'.join(_SEGMENT_FORMS)})(?:\.ts)?["']""")
#: What stands in front of a path that is the package's: `"glass-shared", "src", ` written apart, or the readers' own name for the
#: package's `src` (`SHARED / "canvas" / "zoomBands.ts"`, `SHARED_SRC / "canvas/zoomBands.ts"`).
_PACKAGE_BEFORE = re.compile(
    r"""(?:["']glass-shared["']\s*[,/]\s*["']src["']|\bSHARED(?:_SRC)?)\s*[,/]\s*["']?$"""
)


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
        for form in (_TEXT_FORM, _SEGMENT_FORM):
            for hit in form.finditer(text):
                before = text[text.rfind("\n", 0, hit.start()) + 1 : hit.start()]
                if _PACKAGE_BEFORE.search(before + ('"' if form is _SEGMENT_FORM else "")):
                    continue  # the new place, written apart or through the readers' own name for it
                if form is _SEGMENT_FORM and _PACKAGE_BEFORE.search(text[: hit.start()]):
                    continue
                line = text.count("\n", 0, hit.start()) + 1
                found.append((rel, line, text.splitlines()[line - 1].strip()))
    return sorted(set(found))


def _kept_out(rel: str) -> bool:
    if rel in NAMED:
        return True
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in HISTORY)


# ------------------------------------------------------------------------------------------------------ the fixtures


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


@pytest.fixture
def shared_copy(tmp_path: Path) -> Path:
    """`<tmp>/packages/glass-shared/src`, a copy of the real folder; the real one is never written."""
    copy = tmp_path / "packages" / "glass-shared" / "src"
    shutil.copytree(SHARED_SRC, copy, ignore=shutil.ignore_patterns("node_modules"))
    return copy


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------------- the real tree: files


def test_the_files_are_where_they_should_be() -> None:
    names = earlier.tracked()
    assert len(WHOLE) == 25 and len(set(WHOLE)) == 25
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


def test_the_files_that_stay_stay() -> None:
    """The owner's rulings of 22 November (file 013): each file that stays is in the workspace and not in the package, so
    nothing moved that was meant to stay; `entityPictures` is held by both (D3e's plain half and the workspace's binding)."""
    names = earlier.tracked()
    for rel, reason in STAYS.items():
        place, there = WORKSPACE_SRC + rel, SHARED + rel
        assert (ROOT / place).is_file() and place in names, f"{place} should stay in the workspace ({reason})"
        assert not (ROOT / there).exists(), f"{there} moved, and should stay ({reason})"
    for place in (WORKSPACE_SRC + HELD_BY_BOTH, SHARED + HELD_BY_BOTH):
        assert (ROOT / place).is_file() and place in names, f"{place} is missing"
    # The React files of the canvas are not the package's, whatever else moves.
    assert not [p for p in names if p.startswith(SHARED) and p.endswith(".tsx")], "a React file is in the package"


def _modules_of(index: str, root: Path = SHARED_SRC) -> dict[str, str]:
    """Every module the index names (these twenty-five and every earlier slice's), keyed by its place under `src`."""
    named = {f"{m.removeprefix('./')}.ts" for m in link._STAR.findall(index)}
    named |= {f"{m.removeprefix('./')}.ts" for _, m in link._BRACED.findall(index)}
    named |= set(WHOLE)
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in sorted(named)}


def index_problems(
    index: str,
    sources: dict[str, str],
    required: Iterable[str] | None = None,
    renames: tuple[tuple[str, str, str], ...] = (),
) -> list[str]:
    """D3c's check of an index (a file it does not export, a name no export carries, a name two modules give), with every earlier
    slice's renames and this slice's added to the ones it already knows (`renames` says which)."""
    known = case.RENAMED_BY_THE_INDEX + admin.RENAMED_BY_THE_INDEX + RENAMED_BY_THE_INDEX + renames
    with mock.patch.object(plain, "RENAMED_BY_THE_INDEX", plain.RENAMED_BY_THE_INDEX + known):
        return plain.index_problems(index, sources, required)


def test_the_index_exports_every_name_of_every_moved_module() -> None:
    """Every name of the twenty-five files is exported, by its own name or the one the index renames it to, and no name is given by
    two modules at once (they are read beside every other module the index names, so a clash with an earlier slice's file is
    found too)."""
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    assert index_problems(index, _modules_of(index), WHOLE) == []


def test_an_index_that_drops_or_doubles_a_name_is_found() -> None:
    """Red for the check above (rule 15), in the shape the move could leave: the index as it should be, clean; a name given twice
    (a moved file's `Point` beside an earlier module's); a name left out of a braced export; a file left out."""
    sources = {
        "toy/earlier.ts": "export interface Point { x: number }\n",
        "toy/moved.ts": "export interface Point { x: number; y: number }\nexport const LIMIT = 1;\n",
    }
    index = 'export type { Point } from "./toy/earlier";\nexport { type Point as CanvasPoint, LIMIT } from "./toy/moved";\n'
    toy = (("toy/moved.ts", "Point", "CanvasPoint"),)  # the rename a real table would hold
    assert index_problems(index, sources, renames=toy) == []
    assert any(
        "two modules, one name" in p for p in index_problems(index.replace("type Point as CanvasPoint", "type Point"), sources, renames=toy)
    )
    assert any("LIMIT" in p for p in index_problems(index.replace(", LIMIT", ""), sources, renames=toy))
    assert any("not exported" in p for p in index_problems('export type { Point } from "./toy/earlier";\n', sources, renames=toy))


# ----------------------------------------------------------------------------- React, drawing, workspace, packages: never

#: The one bare package a moved file may name: `graphology`, which the package already depends on (slice C), as a type only.
ALLOWED_BARE = {"graphology"}


def _bare_imports(text: str) -> list[str]:
    return [spec for spec in earlier._IMPORT_SPEC.findall(text) if not spec.startswith(".")]


def import_problems(root: Path, rel: str) -> list[str]:
    """What is wrong with one moved file's imports: D2's check (React, a drawing library as a value or a type, a relative import that
    leaves the package, a schema import written the workspace's way, a package of the workspace), and, for these files, the
    package by its own name (a relative import is what the package writes inside itself) and any bare package but `graphology`,
    which may be taken as a type and not as a value."""
    text = (root / rel).read_text(encoding="utf-8")
    problems = clients.package_import_problems(root, rel)
    for spec in _bare_imports(text):
        if spec == PACKAGE_NAME:
            problems.append(f"{rel}: imports the package by its own name (write a relative import)")
        elif spec not in ALLOWED_BARE:
            problems.append(f"{rel}: imports {spec}, a package the shared package does not hold")
    for hit in re.finditer(r"""^import\s+(type\s+)?[^;]*?from\s*["']graphology["']""", text, re.M | re.S):
        if not hit.group(1):
            problems.append(f"{rel}: imports graphology as a value (only as a type: the package draws nothing)")
    return problems


def test_the_moved_files_import_no_react_no_drawing_library_and_no_workspace_path() -> None:
    sources = clients._package_sources()
    for rel in WHOLE:
        assert SHARED + rel in sources, f"{rel} is not among the package's sources"
    problems = [p for rel in WHOLE for p in import_problems(ROOT, SHARED + rel)]
    assert problems == [], f"{len(problems)} import(s) the package may not make: {problems[:10]}"


def test_a_forbidden_import_in_a_moved_file_is_found(package_copy: Path) -> None:
    """Red for the check above (rule 15): in each of the twenty-five, the lines the file would carry if it grew a hook, a drawing
    library (`sigma`, `@sigma/node-image`, `maplibre-gl`), a path into the workspace (among them the way the workspace wrote a
    schema import), the package by its own name, a new dependency, or `graphology` as a value. Each file is clean first, so the
    plant is what is found."""
    plants = (
        'import { useEffect } from "react";\n',
        'import type { Sigma } from "sigma";\n',
        'import { createNodeImageProgram } from "@sigma/node-image";\n',
        'import maplibregl from "maplibre-gl";\n',
        'import { cachedNodeSvgDataUri } from "../../../../apps/workspace/src/color/nodeVisual";\n',
        'import { glyphMarkup } from "../../../../apps/workspace/src/color/nodeGlyphs";\n',
        'import type { Node } from "../../../../packages/schemas/generated";\n',
        'import { glyphMarkup } from "@ospreyflow/glass-shared";\n',
        'import lodash from "lodash";\n',
        'import Graph from "graphology";\n',
    )
    for rel in WHOLE:
        target = package_copy / (SHARED + rel)
        real = target.read_text(encoding="utf-8")
        assert import_problems(package_copy, SHARED + rel) == [], f"{rel} is not clean to begin with"
        for line in plants:
            target.write_text(line + real, encoding="utf-8")
            assert import_problems(package_copy, SHARED + rel), f"{line!r} is not found in {rel}"
        target.write_text(real, encoding="utf-8")


def test_graphology_is_taken_as_a_type_by_the_one_file_that_names_it() -> None:
    """`linkHover.ts` names `graphology` for its `Graph` type; nothing else of the twenty-five names a bare package."""
    bare = {rel: sorted(set(_bare_imports(_text(SHARED + rel)))) for rel in WHOLE}
    assert {rel: found for rel, found in bare.items() if found} == {"canvas/linkHover.ts": ["graphology"]}


# ------------------------------------------------------------------------- the page and the tab: never, in the package

#: What the package may not touch, in any of the twenty-five files. Read on code: a comment is not a use (`nodeVisual.ts` has one
#: that says "document" glyph, and a whole-file move changes no word).
_PAGE_OBJECT = re.compile(r"\b(window|document|sessionStorage|localStorage)\b")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?:(?<=\s)|^)//[^\n]*", re.M)  # after a space or at a line's start: `https://` is not one


def code_of(text: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def page_objects(text: str) -> list[str]:
    return sorted({m.group(1) for m in _PAGE_OBJECT.finditer(code_of(text))})


def test_the_moved_files_use_no_page_or_tab_object() -> None:
    found = {rel: page_objects(_text(SHARED + rel)) for rel in WHOLE}
    assert {rel: names for rel, names in found.items() if names} == {}, "a moved file touches the page or the tab"


def test_a_page_or_tab_object_in_a_moved_file_is_found(package_copy: Path) -> None:
    """Red for the check above (rule 15): in each of the twenty-five, a use of each of the four, in the shape the browser half writes
    them (`window.open`, `document.createElement`), clean first; `zoomBands.ts` with one in it is the case the brief names. A
    comment that names one is not found."""
    plants = {
        "sessionStorage": '\nexport const kept = sessionStorage.getItem("osprey.case");\n',
        "window": '\nexport const tab = () => window.open("", "_blank");\n',
        "document": '\nexport const link = () => document.createElement("a");\n',
        "localStorage": '\nexport const saved = localStorage.getItem("osprey.theme");\n',
    }
    for rel in WHOLE:
        target = package_copy / (SHARED + rel)
        real = target.read_text(encoding="utf-8")
        assert page_objects(real) == [], f"{rel} is not clean to begin with"
        for word, plant in plants.items():
            target.write_text(real + plant, encoding="utf-8")
            assert page_objects(target.read_text(encoding="utf-8")) == [word], f"{word} is not found in {rel}"
        target.write_text(real + '\n// a "document" glyph, a window onto it\n/* localStorage is not used */\n', encoding="utf-8")
        assert page_objects(target.read_text(encoding="utf-8")) == [], f"a comment is read as a use in {rel}"
        target.write_text(real, encoding="utf-8")
    zoom = package_copy / SHARED / "canvas" / "zoomBands.ts"
    zoom.write_text(zoom.read_text(encoding="utf-8") + '\nexport const where = window.location.href;\n', encoding="utf-8")
    assert page_objects(zoom.read_text(encoding="utf-8")) == ["window"]


def test_the_two_browser_calls_the_package_keeps_are_the_ones_it_may() -> None:
    """The rule is not about every browser name: `requestAnimationFrame` is the default of an injected scheduler in
    `chunkedTextureRefresh.ts` and a call on a Sigma `cameraMoves.ts` is handed, and the two Conduit calls take the address and the
    token as arguments, as every other client in the package does."""
    chunked = _text(SHARED + "canvas/chunkedTextureRefresh.ts")
    assert re.search(r"nextFrame: Schedule = \(step\) => requestAnimationFrame\(", chunked), "the scheduler is not injected"
    assert "requestAnimationFrame(" in _text(SHARED + "canvas/cameraMoves.ts")
    for rel, address in (("canvas/linksAmong.ts", "apiBaseUrl"), ("ontology/schema.ts", "baseUrl")):
        text = _text(SHARED + rel)
        assert text.count("fetch(") == 1, f"{rel} does not make exactly one call"
        assert re.search(rf"\b{address}: string,\s*bearerToken: string", text), f"{rel} does not take the address and the token as arguments"


# ------------------------------------------------------------------------------------------------ no import-time effect

_COLUMN_ZERO_OK = re.compile(
    r"^(?:export\s+)?(?:async\s+)?(?:function|class|type|interface|enum|const|let|declare)\b|^import\b|^export\s*[{*]|^export\s+default\b|^[}\])]|^\s*$|^//|^/\*|^\s\*"
)
_PURE_INITIALISER = re.compile(r"new (?:Intl\.NumberFormat|Map|Set|RegExp)\(|\bMath\.\w+\(|=>|\bfunction\b")


def top_level_effects(text: str) -> list[str]:
    """The top-level statements that are not a declaration of something, and the declarations whose initialiser calls something
    that is not on the short list of pure ones (`new Intl.NumberFormat(...)`, `new Map()`, `Math.sqrt(...)`, an arrow function)."""
    found = []
    code = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for number, line in enumerate(code.splitlines(), 1):
        if line[:1] in {" ", "\t"}:
            continue  # inside a declaration
        if not _COLUMN_ZERO_OK.search(line):
            found.append(f"{number}: {line.strip()[:80]}")
        elif re.match(r"^(?:export\s+)?(?:const|let)\b", line):
            initialiser = line.split("=", 1)[1] if "=" in line else ""
            if re.search(r"\w\(", initialiser) and not _PURE_INITIALISER.search(initialiser):
                found.append(f"{number}: {line.strip()[:80]}")
    return found


def test_the_moved_files_have_no_top_level_effect() -> None:
    found = {rel: top_level_effects(_text(SHARED + rel)) for rel in WHOLE}
    assert {rel: effects for rel, effects in found.items() if effects} == {}, "a moved file does something when it is imported"


def test_a_top_level_effect_in_a_moved_file_is_found(package_copy: Path) -> None:
    """Red for the check above (rule 15): in each of the twenty-five, a statement that runs when the module is imported, in the shapes
    a canvas module would take (a call of a registry, an assignment to the page, a listener, a declaration that calls), clean
    first; and the pure initialisers the files really have are not found."""
    plants = (
        '\nregisterLayout("force");\n',
        '\nglobalThis.__layout = 1;\n',
        '\naddEventListener("resize", () => undefined);\n',
        '\nconst TABLE = buildTable(40);\n',
        '\nexport const CACHE = createCache("x");\n',
    )
    for rel in WHOLE:
        target = package_copy / (SHARED + rel)
        real = target.read_text(encoding="utf-8")
        assert top_level_effects(real) == [], f"{rel} is not clean to begin with"
        for plant in plants:
            target.write_text(real + plant, encoding="utf-8")
            assert top_level_effects(target.read_text(encoding="utf-8")), f"{plant.strip()!r} is not found in {rel}"
        target.write_text(real, encoding="utf-8")
    for pure in ("const COUNT = new Intl.NumberFormat(\"en-GB\");", "const GOLDEN = Math.PI * (3 - Math.sqrt(5));", "const seen = new Map<string, string>();"):
        assert top_level_effects(pure + "\n") == [], pure


# ------------------------------------------------------------------------------------------ how a move is compared


def test_the_move_changed_no_line_but_the_imports() -> None:
    """Each whole file is read as the commit that renamed it left it against the commit before: git's own detection finds the
    rename, and the two sides are compared there, never against the working tree (a later edit would be read as the move's). A
    shallow clone has no history to read: skipped, as the earlier move tests are."""
    earlier._skip_if_shallow()
    for rel in WHOLE:
        new, old = SHARED + rel, OLD_OF[rel]
        commit = earlier._git("log", "--follow", "-M", "--diff-filter=R", "--format=%H", "-1", "--", new).strip()
        assert commit, f"git finds no rename into {new}: the file was not moved with `git mv`"
        was, now = earlier._git("show", f"{commit}^:{old}"), earlier._git("show", f"{commit}:{new}")
        assert was, f"{old} is not in the commit before the rename"
        assert earlier.only_import_lines_changed(was, now) == [], f"{new} changed in more than its import lines"


def test_a_moved_file_changed_in_more_than_its_imports_is_found() -> None:
    """Red for the comparison above: the real files' import lines moved (the schema import written the package's way, and a name
    taken from the file that holds it), once alone and once with a line of the code changed."""
    was = (
        'import type { EdgeTypeDef } from "../../../../packages/schemas/generated";\n'
        'import { glyphMarkup, hasGlyph } from "@ospreyflow/glass-shared";\n\n'
        "export const WILDCARD = \"*\";\n"
    )
    moved = was.replace("../../../../packages/schemas/generated", "../../../schemas/generated").replace(
        "@ospreyflow/glass-shared", "../color/nodeGlyphs"
    )
    assert earlier.only_import_lines_changed(was, moved) == []
    assert earlier.only_import_lines_changed(was, moved.replace('"*"', '"?"')) != []


# ---------------------------------------------------------------------------------------------------- the old paths


def test_no_tracked_file_names_an_old_path() -> None:
    rels = [rel for rel in earlier.tracked() if not _kept_out(rel)]
    assert len(rels) > 1000, "the walk found too few files: git ls-files is not listing the repository"
    found = old_path_mentions(ROOT, rels)
    shown = "\n".join(f"  {rel}:{line}: {text[:140]}" for rel, line, text in found[:40])
    assert found == [], f"{len(found)} place(s) still name an old path; the files are now in {SHARED}:\n{shown}"


def test_an_old_path_written_in_pieces_or_whole_is_found(tmp_path: Path) -> None:
    """Red for the walk above (rule 15), in the shapes the readers wrote it: whole, in a `Path(...) /` join, as `os.path.join`
    arguments and through an f-string, each clean beside the package's place written the way the readers write it, and beside
    the longer paths and the tests that stayed."""
    clean = (
        'ZOOM = SHARED / "canvas" / "zoomBands.ts"\n'
        'VISUAL = SHARED_SRC / "color/nodeVisual.ts"\n'
        'LONG = CORE / "packages" / "glass-shared" / "src" / "ontology" / "schema.ts"\n'
        'LAYOUT = "packages/glass-shared/src/canvas/layoutModes.ts"\n'
        'RECORD = "packages/ontology/schema/ontology.schema.json"\n'
        'TEST = "apps/workspace/src/canvas/layoutModes.test.ts"\n'
        'BUDGET = "apps/workspace/src/canvas/settledAnchor.budget.test.ts"\n'
        'KEPT = "apps/workspace/src/canvas/selectionActions.ts"\n'
    )
    planted = {
        "a join": 'ZOOM = WORKSPACE / "canvas" / "zoomBands.ts"\n',
        "a whole path": 'VISUAL = CORE / "apps/workspace/src/color/nodeVisual.ts"\n',
        "a join of ontology": 'SCHEMA = SRC / "ontology" / "schema.ts"\n',
        "os.path.join": 'GATES = os.path.join(SRC, "canvas", "expansionGate.ts")\n',
        "a join with no suffix": 'GATES = os.path.join(SRC, "canvas", "linksAmong")\n',
        "an f-string": 'TEXT = f"{CORE}/apps/workspace/src/canvas/nodeGestures.ts"\n',
        "a bare shorthand": "# read from canvas/forceLayout.ts, the layout\n",
        "a bare shorthand of the visual": "# see color/nodeVisual\n",
    }
    target = tmp_path / "reader.py"
    target.write_text(clean, encoding="utf-8")
    assert old_path_mentions(tmp_path, ["reader.py"]) == [], "the new place is read as an old one"
    for case_name, line in planted.items():
        target.write_text(clean + line, encoding="utf-8")
        assert old_path_mentions(tmp_path, ["reader.py"]), f"{case_name} is not found"


def test_every_named_exception_still_has_its_reason() -> None:
    """An exception outlives its reason when the file it excuses no longer names an old path: left in `NAMED` it keeps that file
    outside the walk, and an old path could be written back into it unseen (rule 12)."""
    stale = [rel for rel in NAMED if not old_path_mentions(ROOT, [rel])]
    assert stale == [], f"{stale} no longer name an old path: remove them from NAMED, and the walk will cover them"


# ----------------------------------------------------------------------------------------------------- the imports


def _package_names(root: Path) -> set[str]:
    """Every name the twenty-five files export, read from the package's copies (the old ones are gone), and the renames."""
    names = {new for _, _, new in RENAMED_BY_THE_INDEX}
    for rel in WHOLE:
        try:
            names |= link._exported_names((root / (SHARED + rel)).read_text(encoding="utf-8"))
        except OSError:
            continue
    return names


def imports_not_reaching(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The relative specifiers that resolve to an old path, or into the package's folder instead of its name; and the number of
    files that import a name of the twenty-five from the package. Resolution is by path alone: an old file need not exist."""
    bad: list[str] = []
    importers = 0
    names = _package_names(root)
    for rel in rels:
        if Path(rel).suffix not in earlier._SOURCE_SUFFIXES or not rel.startswith("OspreyFlow_Core/"):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for hit in link._PACKAGE_IMPORT.finditer(text):
            if hit.group(1):
                bad.append(f"{rel}: {PACKAGE_NAME}{hit.group(1)} (the package is imported by its name)")
        if not rel.startswith(SHARED) and any(
            names & earlier._names(m.group(1))
            for m in re.finditer(
                rf"""(?:^|\n)\s*import\s+(?:type\s+)?(\{{[^}}]*\}})\s*from\s*["']{re.escape(PACKAGE_NAME)}["']""", text
            )
        ):
            importers += 1
        for hit in earlier._RELATIVE.finditer(text):
            target = earlier._target(rel, hit.group(1))
            stem = earlier._stem(target)
            if stem in _OLD_STEMS or target in _OLD_STEMS:
                bad.append(f"{rel}: {hit.group(1)} (an old path)")
            elif target.startswith(PACKAGE) and not rel.startswith(PACKAGE):
                bad.append(f"{rel}: {hit.group(1)} (into the package's folder, not its name)")
    return bad, importers


def test_every_import_of_a_moved_module_reaches_the_package() -> None:
    bad, importers = imports_not_reaching(ROOT, earlier.tracked())
    assert importers >= 60, (
        f"only {importers} file(s) under OspreyFlow_Core import a name of the twenty-five from {PACKAGE_NAME}: the walk found too few imports, or the importers were not repointed"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach the package by its name: {bad[:10]}"


#: Each line the tree really held (the shape an importer wrote), with the line a half-done move would leave: the old path put back.
_PLANTED_IMPORTS = {
    "a test beside its file": (
        WORKSPACE_SRC + "canvas/nodeGestures.test.ts",
        'import { previewCountFrom } from "./nodeGestures";',
        'import { previewCountFrom } from "@ospreyflow/glass-shared";',
    ),
    "a component of the canvas": (
        WORKSPACE_SRC + "canvas/CanvasLegend.tsx",
        'import type { EntityVisual } from "../ontology/schema";',
        'import type { EntityVisual } from "@ospreyflow/glass-shared";',
    ),
    "a panel of another folder": (
        WORKSPACE_SRC + "inspector/LinkDetails.tsx",
        'import { linkTypeName } from "../canvas/linkLabel";',
        'import { linkTypeName } from "@ospreyflow/glass-shared";',
    ),
    "the app": (
        WORKSPACE_SRC + "App.tsx",
        'import { linkTypeName } from "./canvas/linkLabel";',
        'import { linkTypeName } from "@ospreyflow/glass-shared";',
    ),
    "a keyboard harness": (
        APPS + "workspace/keyboard/harness.tsx",
        'import { OntologyRegistry } from "../src/ontology/schema";',
        'import { OntologyRegistry } from "@ospreyflow/glass-shared";',
    ),
    "the perf harness": (
        APPS + "workspace/perf/harness.tsx",
        'import { OntologyRegistry } from "../src/ontology/schema";',
        'import { OntologyRegistry } from "@ospreyflow/glass-shared";',
    ),
    "a file that stays, in the canvas": (
        WORKSPACE_SRC + "canvas/nodeAttributes.ts",
        'import { cachedNodeSvgDataUri, type StrokeStyle } from "../color/nodeVisual";',
        'import { cachedNodeSvgDataUri, type StrokeStyle } from "@ospreyflow/glass-shared";',
    ),
    "the one edit to iconImage": (
        WORKSPACE_SRC + "canvas/iconImage.ts",
        'import { MAX_IMAGE_ICON_CHARS, isSafeImageDataUrl } from "../color/nodeVisual";',
        'import { MAX_IMAGE_ICON_CHARS, isSafeImageDataUrl } from "@ospreyflow/glass-shared";',
    ),
    "a deck harness": (
        APPS + "workspace/deck-capture/fraud-network-harness.tsx",
        'import { OntologyRegistry } from "../src/ontology/schema";',
        'import { OntologyRegistry } from "@ospreyflow/glass-shared";',
    ),
}


@pytest.mark.parametrize("case_name", sorted(_PLANTED_IMPORTS))
def test_an_old_path_put_back_in_one_importer_is_found(case_name: str, package_copy: Path) -> None:
    """Red for the two walks above (rule 15): each line the tree really held, put back in the file that held it. The same file with the
    new line is clean first, so the plant is what is found and not something else in the file."""
    rel, old_line, new_line = _PLANTED_IMPORTS[case_name]
    target = package_copy / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_line + "\n", encoding="utf-8")
    assert imports_not_reaching(package_copy, [rel])[0] == [] and old_path_mentions(package_copy, [rel]) == []
    target.write_text(old_line + "\n", encoding="utf-8")
    assert imports_not_reaching(package_copy, [rel])[0] or old_path_mentions(package_copy, [rel]), (
        f"neither walk finds {old_line!r} in {rel}"
    )


def test_a_file_that_names_none_of_the_moved_names_is_not_counted_as_an_importer(package_copy: Path) -> None:
    """The importers' floor means something only if a file that takes some other name from the package is not one."""
    rel = WORKSPACE_SRC + "theme/ThemeToggle.tsx"
    (package_copy / rel).parent.mkdir(parents=True)
    (package_copy / rel).write_text(f'import {{ applyTheme }} from "{PACKAGE_NAME}";\n', encoding="utf-8")
    assert imports_not_reaching(package_copy, [rel]) == ([], 0)
    for name in ("linkTypeName", "OntologyRegistry", "settleLayout", "cachedNodeSvgDataUri", "showLinksAmong", "WILDCARD"):
        (package_copy / rel).write_text(f'import {{ {name} }} from "{PACKAGE_NAME}";\n', encoding="utf-8")
        assert imports_not_reaching(package_copy, [rel]) == ([], 1), name


def test_every_import_reached_from_a_spec_resolves() -> None:
    """The Playwright collection check's own half: a spec that imports a file that is gone fails at collection, which no unit
    test runs. Every relative import, reached from any spec by any chain, names a file."""
    specs = earlier.spec_files(earlier.tracked())
    assert len(specs) >= 100, f"only {len(specs)} spec files found: the walk is not seeing the specs"
    missing, reached = earlier.unresolved_from_specs(ROOT, specs)
    assert reached >= 400, f"the walk reached only {reached} files: it is not following imports"
    assert missing == [], f"{len(missing)} import(s) name no file: {missing[:10]}"


def test_a_spec_that_imports_a_path_that_no_longer_exists_is_found(tmp_path: Path) -> None:
    """Red for the walk above, at the shapes the move could leave: a keyboard harness still importing the ontology by the old path,
    and the index exporting a file that is not there."""
    spec = APPS + "workspace/keyboard/reader.spec.ts"
    harness = APPS + "workspace/keyboard/reader-harness.tsx"
    files = {
        spec: 'import { mount } from "./reader-harness";\n',
        harness: (
            f'import {{ OntologyRegistry }} from "{PACKAGE_NAME}";\n'
            'import { Reader } from "../src/reader/DocumentReader";\n'
        ),
        WORKSPACE_SRC + "reader/DocumentReader.tsx": "export const Reader = 1;\n",
        SHARED + "index.ts": 'export * from "./ontology/schema";\n',
        SHARED + "ontology/schema.ts": "export class OntologyRegistry {}\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == []
    clean = (tmp_path / harness).read_text(encoding="utf-8")
    (tmp_path / harness).write_text(clean + 'import { OntologyRegistry as Old } from "../src/ontology/schema";\n', encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [f"{harness}: ../src/ontology/schema"]
    (tmp_path / harness).write_text(clean, encoding="utf-8")
    (tmp_path / SHARED / "ontology" / "schema.ts").unlink()
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [f"{SHARED}index.ts: ./ontology/schema"]


# ----------------------------------------------------------------------------------------------- the eight mocks

APP_TESTS = (
    "App.batchExpand.test.tsx",
    "App.chrome.test.tsx",
    "App.expandCap.test.tsx",
    "App.help.test.tsx",
    "App.ontologyRetry.test.tsx",
    "App.search.test.tsx",
    "App.test.tsx",
    "App.views.test.tsx",
)
_MOCK_OF_THE_PACKAGE = re.compile(rf"""^vi\.mock\(\s*["']{re.escape(PACKAGE_NAME)}["']""", re.M)
_ANY_MOCK_OF_THE_PACKAGE = re.compile(rf"""vi\.(?:mock|doMock)\(\s*["']{re.escape(PACKAGE_NAME)}["']""")


def mock_problems(text: str) -> list[str]:
    """What is wrong with one of the eight App tests: a string that still names the old module (a `vi.mock`, an `importActual`, a
    `typeof import(...)` or the import of the namespace), more or fewer than one `vi.mock` of the package (a second overrides the
    first, so `fetchMapConfig` or `fetchOntologyRegistry` would go unmocked), a factory that does not replace
    `fetchOntologyRegistry`, or one that does not start from the package's real exports."""
    problems = []
    if re.search(r"""["'][^"'\n]*ontology/schema["']""", text):
        problems.append("a string still names the old module `ontology/schema`")
    mocks = list(_ANY_MOCK_OF_THE_PACKAGE.finditer(text))
    if len(mocks) != 1:
        problems.append(f"{len(mocks)} `vi.mock` of the package (exactly one: a second overrides the first)")
        return problems
    block = re.split(r"\n\}\)+;", text[mocks[0].start() :], maxsplit=1)[0]
    if not re.search(r"\bfetchOntologyRegistry\s*:", block):
        problems.append("the package's mock does not replace fetchOntologyRegistry")
    if "importActual" not in block:
        problems.append("the package's mock does not start from the package's real exports")
    if not re.search(rf"""import \* as ontologySchema from ["']{re.escape(PACKAGE_NAME)}["']""", text):
        problems.append("the test does not take the mocked namespace from the package")
    return problems


def test_the_eight_app_tests_mock_the_package_once() -> None:
    assert len(APP_TESTS) == 8 and len(set(APP_TESTS)) == 8
    for name in APP_TESTS:
        text = _text(WORKSPACE_SRC + name)
        assert mock_problems(text) == [], f"{name}: {mock_problems(text)}"
        assert _MOCK_OF_THE_PACKAGE.search(text), f"{name}: the mock is not a statement of its own"


def test_a_mock_that_names_the_old_module_or_the_package_twice_is_found() -> None:
    """Red for the check above (rule 15), on the real tests: each of the eight with the old strings put back (the three the tree
    held: the mock, the actual and the namespace), with the factory's one line gone, with a second mock of the package that
    would override the first, and with the mock gone."""
    for name in APP_TESTS:
        real = _text(WORKSPACE_SRC + name)
        assert mock_problems(real) == [], name
        old_mock = real.replace(PACKAGE_NAME, "./ontology/schema", 1)
        assert any("old module" in p for p in mock_problems(old_mock)), f"{name}: the old mock string is not found"
        old_namespace = real.replace(f'import * as ontologySchema from "{PACKAGE_NAME}"', 'import * as ontologySchema from "./ontology/schema"')
        assert mock_problems(old_namespace), f"{name}: the old namespace import is not found"
        assert mock_problems(re.sub(r"\bfetchOntologyRegistry\s*:", "fetchOther:", real, count=1)), f"{name}: a factory without it is not found"
        twice = real + f'\nvi.mock("{PACKAGE_NAME}", async () => ({{ fetchMapConfig: vi.fn() }}));\n'
        assert any("exactly one" in p for p in mock_problems(twice)), f"{name}: a second mock is not found"
        gone = re.sub(r"vi\.mock\(\s*\"@ospreyflow/glass-shared\"", 'vi.mock("./other"', real, count=1)
        assert any("exactly one" in p for p in mock_problems(gone)), f"{name}: the mock gone is not found"


# ------------------------------------------------------------------------------------------------------- the images

WORKSPACE_IMAGE = CORE / "apps" / "workspace" / "Dockerfile"


def stale_copies(dockerfile: str) -> list[str]:
    """The sources a stage copies that name the place a file moved from: the file itself."""
    old = {"/".join(p.split("/")[4:]) for p in OLD_OF.values()}  # under `apps/workspace/src/`
    return sorted(
        src
        for src in clients.copy_sources(dockerfile)
        if src.startswith("apps/workspace/src/") and src.removeprefix("apps/workspace/src/") in old
    )


def test_no_image_copies_a_path_that_moved() -> None:
    """Neither image names a moved file in a `COPY`, and each copies the package's source (the lines are as they were)."""
    for dockerfile in (WORKSPACE_IMAGE, image.DOCKERFILE):
        text = dockerfile.read_text(encoding="utf-8")
        assert stale_copies(text) == [], f"{dockerfile.name} copies a path that moved"
        assert "packages/glass-shared/src" in clients.copy_sources(text), (
            f"{dockerfile.parent.name}/{dockerfile.name} does not copy packages/glass-shared/src"
        )


def test_the_harness_image_copies_what_the_moved_files_need() -> None:
    """The harness frontend reaches the package's index, and by it every file: each file it reaches is under a `COPY`, and every
    `COPY` of a workspace path still names something that exists and is reached. The walk reaches the twenty-five."""
    reached = image._reached_workspace_files()
    copied = image._copied_paths()
    assert image._missing(copied, reached) == []
    assert earlier.dangling(copied, reached) == []
    names = {str(p.relative_to(CORE.resolve())) for p in reached}
    for rel in WHOLE:
        assert f"packages/glass-shared/src/{rel}" in names, f"the walk does not reach the package's {rel}"


def test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found() -> None:
    """Red for the checks above (rule 15), on the real stages: the package's line taken out of the harness image (the files the index
    reaches are missing), a line a moved file once needed put in (it copies a file that is not there), and the same two faults on
    the workspace image."""
    real = image.DOCKERFILE.read_text(encoding="utf-8")
    reached = image._reached_workspace_files()
    assert stale_copies(real) == []
    assert image._missing(image._copied_paths(real), reached) == []

    shared = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    assert shared in real
    missing = image._missing(image._copied_paths(real.replace(shared, "", 1)), reached)
    for rel in WHOLE:
        assert f"packages/glass-shared/src/{rel}" in missing, f"{rel} is not found missing"

    for rel in ("canvas/zoomBands.ts", "color/nodeVisual.ts", "ontology/schema.ts"):
        line = f"COPY apps/workspace/src/{rel} ./apps/workspace/src/{rel}\n"
        stale = real.replace(shared, shared + line, 1)
        assert stale_copies(stale) == [f"apps/workspace/src/{rel}"]
        assert earlier.dangling(image._copied_paths(stale), reached) == [f"apps/workspace/src/{rel}"]

    workspace = WORKSPACE_IMAGE.read_text(encoding="utf-8")
    assert stale_copies(workspace) == []
    assert shared in workspace
    assert "packages/glass-shared/src" not in clients.copy_sources(workspace.replace(shared, "", 1))
    assert stale_copies(workspace + "COPY apps/workspace/src/canvas/linksAmong.ts ./x\n") == ["apps/workspace/src/canvas/linksAmong.ts"]


# --------------------------------------------------------------------------------------------------- the four gates

#: The files each gate read before this slice: the number each reported or, where it reports none, the files its own rules select
#: (measured on 22 November 2026, on the tip PL4e started from, after PL4d3e). The files moved from a folder each gate reads to
#: another it reads, so the numbers do not change: none may fall.
FILES_BEFORE = {"colour-drift": 498, "design-check": 905, "ui-words": 502, "no-branches": 1755}


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


def test_the_colour_drift_check_reports_a_plant_in_a_moved_file(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    mirrors = dict(colour_drift_check.SCANNED).get(SHARED_SRC)
    assert mirrors is not None, "the colour-drift check does not read the package"
    monkeypatch.setattr(colour_drift_check, "CORE", shared_copy.parent.parent.parent)
    monkeypatch.setattr(colour_drift_check, "SCANNED", ((shared_copy, mirrors),))
    assert colour_drift_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    earlier._append(shared_copy, "canvas/layoutModes.ts", '\nexport const STRIPE = { background: "#12ab34", padding: 8 };\n')
    assert colour_drift_check.main() == 1
    assert "packages/glass-shared/src/canvas/layoutModes.ts:" in capsys.readouterr().out


def test_the_design_detector_reports_a_plant_in_a_moved_file(shared_copy: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(design_check, "SCANNED", [shared_copy])
    assert design_check.unexcused(design_check.detect(design_check.SCANNED)) == [], "the clean copy already has findings"
    earlier._append(
        shared_copy,
        "ontology/schema.ts",
        "\nexport const TOAST_STYLE = {\n"
        '  background: "var(--surface-raised)", borderLeft: "3px solid var(--error)", borderRadius: "8px",\n'
        '  padding: "12px 16px", boxShadow: "var(--overlay-shadow)",\n'
        "};\n",
    )
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [("schema.ts", "side-tab")]
    assert "ontology" in found[0]["file"]


def test_the_ui_words_check_reports_a_plant_in_a_moved_file(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = shared_copy.parent.parent / "no-src"
    empty.mkdir()
    monkeypatch.setattr(ui_words_check, "SHARED_SRC", shared_copy)
    monkeypatch.setattr(ui_words_check, "GLASS_SRC", empty)
    monkeypatch.setattr(ui_words_check, "DESIGN_PACKAGE", empty)
    assert ui_words_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    earlier._append(shared_copy, "canvas/edgeTypeMenu.ts", '\nexport const LABEL = "Target model";\n')
    assert ui_words_check.main() == 1
    assert "packages/glass-shared/src/canvas/edgeTypeMenu.ts:" in capsys.readouterr().out


def test_the_no_branches_check_reports_a_plant_in_a_moved_file(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    top = "packages/glass-shared/src"
    assert top in no_branches_check.SCANNED
    walk = no_branches_check.tree_files
    tmp_core = shared_copy.parent.parent.parent
    monkeypatch.setattr(no_branches_check, "tree_files", lambda: walk(tmp_core, [top]))
    assert no_branches_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    earlier._append(shared_copy, "canvas/linkLabel.ts", '\nexport const BRANCH_CASE = "branch-by-filter";\n')
    assert no_branches_check.main() == 1
    assert f"{top}/canvas/linkLabel.ts:" in capsys.readouterr().out


# ----------------------------------------------------------------------------------------------- the manifest


def test_no_new_dependency_and_no_new_entry_was_added_to_the_package() -> None:
    """The package's manifest names the two packages it did before and keeps its one entry (the files import `graphology` as a type
    and no other package, and the index is the way in, so the exports map did not change: a `package.json` change is the owner's)."""
    manifest = json.loads((CORE / "packages" / "glass-shared" / "package.json").read_text(encoding="utf-8"))
    assert sorted(manifest.get("dependencies", {})) == ["graphology", "zustand"]
    assert manifest.get("exports") == {".": "./src/index.ts"}
    assert manifest.get("sideEffects") is False


def test_the_readers_that_stay_still_find_their_files() -> None:
    """The two guide tests that read `canvas/selectionActions.ts` and the report-clients test that reads `canvas/labelChoices.ts`
    read files that stay (the scout found no reader of a moved file by its name or in pieces: the old-path walk above is the proof)."""
    for rel in ("canvas/selectionActions.ts", "canvas/labelChoices.ts"):
        assert (ROOT / (WORKSPACE_SRC + rel)).is_file(), rel
    assert posixpath.basename(WHOLE[0]) == "nodeGestures.ts"
