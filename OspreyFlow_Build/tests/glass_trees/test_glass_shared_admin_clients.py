"""The roles' words, the record of the places each role opens and the Admin client move to `packages/glass-shared`, and the
guides, Home's figures and an entity's picture split from their browser halves (ADR-152 decision 6, "the Conduit client"; slice
PL4d3e, the tenth of the PL4 slices after A, B, B2, B3, C, D1, D2, D3a, D3b, D3c and D3d; the owner's rulings of 20 and
21 November 2026, among them that these three files do not wait for AD1a). Nothing changes on screen. This unblocks the Admin
pages, Home's page and any page that draws an entity's picture.

**Four files moved whole, three were split, and one definition moved out of a React file.**

* Moved whole, their lines unchanged but for the import lines (the record unchanged byte for byte): `shell/placesByRole.json`
  (the record `test_place_routes.py` holds to the routes), `help/roles.ts` (the roles', rights', places' and levels' words),
  `admin/api.ts` (the Admin client; 13 importers, all React sections) and `home/homeData.ts` (Home's figures and `loadHome`,
  with its fetcher handed in).
* `home/guides.ts` split at the browser. The package keeps `home/guides.ts`: the guide ids, the card each opens under, the words,
  `guideUrl`, `OpenGuideDeps` and `openGuide`, whose two browser calls (a blank tab and a saved file) are now **required**
  dependencies. The workspace's `home/guideDownloads.ts` holds the two (`window.open`, an `<a download>` clicked) and its
  `openGuide` is the package's with both supplied, so a screen that opens a guide only changed its import line.
* `canvas/entityPictures.ts` split at the canvas. The package keeps the store and the client; the one browser dependency, the
  thumbnail step (`thumbnailFromFile`, which draws on a canvas), is handed in (`bindEntityThumbnail`). The workspace's file of
  the same name binds it and passes the package's names on, so no importer changed.
* `alertRuleGroup`, its `RuleGroup` type and the kind table it reads moved out of `reports/figureParts.tsx` (a React file) into the
  package's `reports/ruleGroup.ts`, because Home's figures read it. That is the one edit to a React file beyond import lines.

**Two names were written twice, and the index says which is which.** The Admin client's `listDatasets` and `testConnection` are
the Admin ones; the package already gives a `listDatasets` (the cases client's) and a `testConnection` (the models client's). The
index names the Admin ones `listAdminDatasets` and `testAdminConnection`, and the importers that wrote the old names write
`listAdminDatasets as listDatasets`, so only their import line changed. The package's `PlaceId` is not imported from the
workspace: `home/guides.ts` takes the same four places as the keys of `PLACE_WORDS`.

Which test fails if the invariant is broken (rule 12):

* a file not where it should be, an old one back, or the index leaving one out or giving a name twice:
  `test_the_files_are_where_they_should_be`, `test_the_index_exports_every_name_of_every_new_module`, with
  `test_an_index_that_drops_or_doubles_a_name_is_found`;
* a file of the package importing React, a drawing library, a package at all, or a file of the workspace or the harness:
  `test_the_new_files_import_no_react_no_package_and_no_workspace_path`, with a plant of each in each file;
* **a browser object in the package** (`window`, `document`, `sessionStorage`, `localStorage`):
  `test_the_package_files_use_no_page_or_tab_object`, with a plant of each in each file (the brief's own: one in `guides.ts`), and
  `test_the_browser_half_keeps_the_page` (the calls are where they belong);
* a whole file changed in more than its import lines at the commit that moved it, or the record in any byte:
  `test_the_move_changed_no_line_but_the_imports`; a split that adds or loses a line it should not:
  `test_the_guides_split_changed_no_line_but_the_two_dependencies`, `test_the_pictures_split_changed_no_line_but_the_binding`,
  `test_the_rule_group_move_changed_no_line`, with `test_a_split_that_adds_or_loses_a_line_is_found`;
* a file naming an old path, written whole or in pieces (`/ "help" / "roles.ts"`): `test_no_tracked_file_names_an_old_path`, with
  `test_an_old_path_written_in_pieces_or_whole_is_found`; an importer still reaching one, or reaching into the package's folder:
  `test_every_import_of_a_moved_module_reaches_the_package`, with `test_an_old_path_put_back_in_one_importer_is_found`; a browser
  call taken from the package instead of the browser half: `test_the_browser_calls_are_taken_from_the_browser_half`;
* **a Python test that reads a moved file at its old place, or stops reading it at the new**: `test_the_readers_read_the_new_paths`,
  with `test_the_guide_role_words_reader_reads_the_package_copy`, `test_the_people_words_reader_reads_the_package_copy` and
  `test_the_place_routes_record_is_written_and_read_at_the_package_path` (a stale copy at the new path is red, rewritten is green);
* a spec, or a file one imports, naming a file that does not exist: `test_every_import_reached_from_a_spec_resolves`;
* a gate that stops reading the files, or reads fewer: `test_each_gate_reads_no_fewer_files_than_before`, and one plant for
  each gate in a **moved** file;
* a word-walker that does not read the files: `test_the_people_name_walk_reads_each_package_file`,
  `test_the_view_word_walk_reads_each_package_file`, `test_a_place_held_by_both_roots_is_read_from_both` (keyed by root) and
  `test_the_vitest_walkers_name_the_new_folders`;
* an image `COPY` naming a moved path, or missing what the harness needs: `test_no_image_copies_a_path_that_moved`,
  `test_the_harness_image_copies_what_the_new_files_need`, each shown red by `test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found`.

**This file walks:** `git ls-files` over the whole repository (the old-path test, whole and in pieces); the tracked `.ts`, `.tsx`,
`.mts`, `.mjs`, `.js` and `.jsx` files under `OspreyFlow_Core/apps/` (the import tests, the browser-call test, the spec walk, which
starts at every tracked `*.spec.ts` and `*.spec.tsx` in `apps/workspace` and `apps/harness` and follows their imports) and under
`OspreyFlow_Core/packages/glass-shared/src` (the new files, the index, the package's own imports); `apps/workspace/src` and
`packages/glass-shared/src` through the two Python word-walkers it imports (each in a temporary copy); the three Python readers it
repoints (`test_guide_role_words.py`, `test_people_section_words.py`, `test_place_routes.py`), each run on a temporary copy of the
tree they read; `apps/workspace/Dockerfile` and `harness/Dockerfile` by name; `copyTextsTestKit.ts` and the three vitest walkers by
name; the git history of the renames and of the splits (`git log`, `git show`); and temporary copies built inside `tmp_path` for the
plants (written there, never in the repository), among them copies of `packages/glass-shared/src`.
"""

# The planted lines below are the real call-site shapes, kept on one line as the tree wrote them (rule 15), and the
# prose beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from unittest import mock

import pytest
from tools import colour_drift_check, design_check, no_branches_check, ui_words_check
from tools.layout import CORE, ROOT

from tests import test_guide_navigation_words as navigation
from tests import test_guide_role_words as roles_words
from tests import test_people_section_words as people
from tests.glass_trees import test_glass_shared_case_clients as case
from tests.glass_trees import test_glass_shared_clients as clients
from tests.glass_trees import test_glass_shared_link_clients as link
from tests.glass_trees import test_glass_shared_plain_clients as plain
from tests.glass_trees import test_glass_shared_plain_logic as earlier
from tests.harness import test_harness_frontend_copies as image
from tests.services.api import test_place_routes as place_routes

PACKAGE = "OspreyFlow_Core/packages/glass-shared/"
SHARED = PACKAGE + "src/"
SHARED_SRC = CORE / "packages" / "glass-shared" / "src"
APPS = "OspreyFlow_Core/apps/"
WORKSPACE_SRC = APPS + "workspace/src/"
PACKAGE_NAME = "@ospreyflow/glass-shared"

#: The four files that moved whole (relative to `SHARED`; the old place is the same relative path under `apps/workspace/src/`).
RECORD = "shell/placesByRole.json"
WHOLE = (RECORD, "help/roles.ts", "admin/api.ts", "home/homeData.ts")
#: The guides' plain half, whose workspace half is `home/guideDownloads.ts`; the old file's place in the workspace is gone.
GUIDES = "home/guides.ts"
DOWNLOADS = "home/guideDownloads.ts"
#: The entity pictures' plain half; the workspace's file of the same name binds the thumbnail step (it is not an old path).
PICTURES = "canvas/entityPictures.ts"
#: The new module of the rule group, and the React file it left.
RULE_GROUP = "reports/ruleGroup.ts"
FIGURE_PARTS = "reports/figureParts.tsx"

#: The six TypeScript files of the package this slice adds (the record is data, not source).
PACKAGE_FILES = tuple(rel for rel in WHOLE if rel.endswith(".ts")) + (GUIDES, PICTURES, RULE_GROUP)
OLD_OF = {rel: WORKSPACE_SRC + rel for rel in (*WHOLE, GUIDES)}
_OLD_STEMS = {old.removesuffix(".ts") for old in OLD_OF.values()}

#: The names the index gives under another, because a new file wrote a name that an earlier module already gives:
#: (file, the name it wrote, the name the package exports it as).
RENAMED_BY_THE_INDEX = (
    ("admin/api.ts", "listDatasets", "listAdminDatasets"),
    ("admin/api.ts", "testConnection", "testAdminConnection"),
)

#: The places that may name an old path because they are a record of the past: the decision log, and the build record
#: under `process/`. They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone
#: (`test_every_named_exception_still_has_its_reason`).
NAMED = {
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_glass_shared_admin_clients.py": "this test",
    # The declared-units test names each unit's source module by its place under the package or the workspace, as the declaration
    # does (`home/guides.ts`): a label on a row, never a path it reads.
    "OspreyFlow_Build/tests/glass_trees/test_pl4d3e_declared_units.py": "source-module labels of the declared units",
    # A published guide: its sentence naming `help/roles.ts` (and its version row for 1.61) cannot change without a new version and
    # a PDF printed by a person (ADR-114 Amendment 26, `tools/docs_pdf.py`), which this slice does not publish. It follows at the
    # guide's next version; the specification's copy of the sentence already names the package path.
    "OspreyFlow_Core/docs/administration-guide.md": "a published guide: a new version and its PDF are a person's step",
    # The declaration itself: each row's source-module column is a label (`home/guides.ts`), generated from the units, never a path.
    "OspreyFlow_Build/tests/fixtures/pl4d3e_declared_units.txt": "source-module labels of the declared units",
    # The citation allowlist names the old path of the roles' words on purpose: records that stay as written cite it, and it is
    # now absent (its own comment says so).
    "OspreyFlow_Build/tests/fixtures/citation_allowlist.txt": "the old path, deliberately absent and cited by records",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

#: The forms an old path takes in prose and code: not `help/roles.test.ts` or `home/guides.test.ts` (the tests stayed in the
#: workspace, beside where the files were), not the Admin client's route (`v1/admin/...`), and not the same words with the
#: package's place in front of them.
_NAME_FORMS = (
    r"help/roles",
    r"shell/placesByRole",
    r"home/homeData",
    r"home/guides",
    r"apps/workspace/src/admin/api",
)
_TEXT_FORM = re.compile(
    rf"(?<!glass-shared/src/)(?<!v1/)(?<![\w-])(?:{'|'.join(_NAME_FORMS)})\b(?![\w-])(?!\.(?:css|test\.|spec\.|py|bak))"
)
#: The segments of one written apart: `join(HERE, "..", "src", "help", "roles")`, Python's `/ "help" / "roles.ts"`.
_SEGMENT_FORM = re.compile(
    r"""["'](?:help["']\s*[,/]\s*["']roles|shell["']\s*[,/]\s*["']placesByRole|home["']\s*[,/]\s*["'](?:homeData|guides)"""
    r"""|admin["']\s*[,/]\s*["']api)(?:\.ts|\.json)?["']"""
)
#: What stands in front of a path that is the package's: `"glass-shared", "src", ` written apart, or the readers' own name for the
#: package's `src` (`SHARED / "help" / "roles.ts"`, `SHARED_SRC / "shell/placesByRole.json"`).
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


def _exists_at(commit: str, path: str) -> bool:
    try:
        earlier._git("cat-file", "-e", f"{commit}:{path}")
    except Exception:
        return False
    return True


# ------------------------------------------------------------------------------------------------- the real tree: files


def test_the_files_are_where_they_should_be() -> None:
    names = earlier.tracked()
    for rel in WHOLE:
        new, old = SHARED + rel, OLD_OF[rel]
        assert (ROOT / new).is_file(), f"{new} is not in packages/glass-shared/src"
        assert not (ROOT / old).exists(), f"{old} is still where it was"
        assert new in names and old not in names
    # The guides: the package's half is `home/guides.ts`; the workspace's old file is gone, its browser half is `guideDownloads`.
    assert (ROOT / (SHARED + GUIDES)).is_file() and SHARED + GUIDES in names
    assert not (ROOT / OLD_OF[GUIDES]).exists(), "the workspace still holds home/guides.ts"
    assert (ROOT / (WORKSPACE_SRC + DOWNLOADS)).is_file() and WORKSPACE_SRC + DOWNLOADS in names
    assert not (ROOT / (SHARED + DOWNLOADS)).exists(), f"{DOWNLOADS} is in the package"
    # The pictures are held by both: the package's plain half and the workspace's binding.
    for place in (SHARED + PICTURES, WORKSPACE_SRC + PICTURES):
        assert (ROOT / place).is_file() and place in names, f"{place} is missing"
    # The rule group is the package's; the React file it left stays in the workspace and is not in the package.
    assert (ROOT / (SHARED + RULE_GROUP)).is_file() and SHARED + RULE_GROUP in names
    assert (ROOT / (WORKSPACE_SRC + FIGURE_PARTS)).is_file()
    assert not (ROOT / (SHARED + FIGURE_PARTS)).exists(), "the React figure parts are in the package"
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    for rel in PACKAGE_FILES:
        stem = "./" + rel.removesuffix(".ts")
        assert re.search(
            rf"""^export\s+(?:type\s+)?(?:\*|\{{[^}}]*\}})\s+from\s+["']{re.escape(stem)}["'];""",
            index,
            re.M,
        ), f"packages/glass-shared/src/index.ts does not export {stem}"
    assert re.search(
        rf"""^export\s+\{{\s*default\s+as\s+PLACES_BY_ROLE\s*\}}\s+from\s+["']\./{re.escape(RECORD)}["'](?:\s+with\s+\{{\s*type:\s*["']json["']\s*\}})?;""",
        index,
        re.M,
    ), "the index does not give the record as PLACES_BY_ROLE"


def _modules_of(index: str, root: Path = SHARED_SRC) -> dict[str, str]:
    """Every module the index names (these six and the earlier slices'), keyed by its place under `src`."""
    named = {f"{m.removeprefix('./')}.ts" for m in link._STAR.findall(index)}
    named |= {f"{m.removeprefix('./')}.ts" for _, m in link._BRACED.findall(index)}
    named |= set(PACKAGE_FILES)
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in sorted(named)}


def index_problems(
    index: str,
    sources: dict[str, str],
    required: Iterable[str] | None = None,
    renames: tuple[tuple[str, str, str], ...] = case.RENAMED_BY_THE_INDEX + RENAMED_BY_THE_INDEX,
) -> list[str]:
    """D3c's check of an index (a file it does not export, a name no export carries, a name two modules give), with the
    earlier slice's rename and this slice's two added to the ones it already knows (`renames` says which)."""
    with mock.patch.object(plain, "RENAMED_BY_THE_INDEX", plain.RENAMED_BY_THE_INDEX + renames):
        return plain.index_problems(index, sources, required)


def test_the_index_exports_every_name_of_every_new_module() -> None:
    """Every name of the six files is exported, by its own name or the one the index renames it to, and no name is given by
    two modules at once (they are read beside every other module the index names, so a clash with an earlier slice's client is
    found too: `listDatasets` is the cases client's and `testConnection` the models client's)."""
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    assert index_problems(index, _modules_of(index), PACKAGE_FILES) == []


def test_an_index_that_drops_or_doubles_a_name_is_found() -> None:
    """Red for the check above (rule 15), in the shape the move could leave: the index as it should be, clean; the rename lost
    (the Admin client's `listDatasets` given beside the cases client's); a name left out of a braced export; a file left out."""
    sources = {
        "toy/cases.ts": "export function listDatasets(id: string): string { return id; }\n",
        "toy/admin.ts": "export function listDatasets(api: number): number { return api; }\nexport const AUDIT = 1;\n",
    }
    index = (
        'export { listDatasets } from "./toy/cases";\n'
        'export { listDatasets as listAdminDatasets, AUDIT } from "./toy/admin";\n'
    )
    toy = (("toy/admin.ts", "listDatasets", "listAdminDatasets"),)  # the rename the real table holds for `admin/api.ts`
    assert index_problems(index, sources, renames=toy) == []
    assert any(
        "two modules, one name" in p
        for p in index_problems(index.replace("listDatasets as listAdminDatasets", "listDatasets"), sources, renames=toy)
    )
    assert any("AUDIT" in p for p in index_problems(index.replace(", AUDIT", ""), sources, renames=toy))
    assert any(
        "not exported" in p
        for p in index_problems('export { listDatasets } from "./toy/cases";\n', sources, renames=toy)
    )
    assert any(
        "listAdminDatasets" in p
        for p in index_problems(index.replace("listDatasets as listAdminDatasets, ", ""), sources, renames=toy)
    )


# ----------------------------------------------------------------------------------- React, workspace, packages: never


def test_the_new_files_import_no_react_no_package_and_no_workspace_path() -> None:
    """The D2 file's check reads every file of the package, these six too; here they are shown to be among them, and a bare
    package (anything that is not a relative path or the generated schemas) is refused as well: no new dependency."""
    sources = clients._package_sources()
    for rel in PACKAGE_FILES:
        assert SHARED + rel in sources, f"{rel} is not among the package's sources"
    problems = [
        p for rel in PACKAGE_FILES for p in clients.package_import_problems(ROOT, SHARED + rel)
    ]
    assert problems == [], f"{len(problems)} import(s) the package may not make: {problems[:10]}"
    bare = {rel: _bare_imports(_text(SHARED + rel)) for rel in PACKAGE_FILES}
    assert {rel: found for rel, found in bare.items() if found} == {}, "a new file imports a package"


def _bare_imports(text: str) -> list[str]:
    return [spec for spec in earlier._IMPORT_SPEC.findall(text) if not spec.startswith(".")]


def test_a_react_workspace_or_package_import_in_a_new_file_is_found(package_copy: Path) -> None:
    """Red for the check above (rule 15): in each of the six, the lines the file would carry if it grew a hook, a path into the
    workspace (among them the way the workspace wrote a schema import, which is not the package's way, and the places a guide
    file's browser half lives), or a new dependency. Each file is clean first, so the plant is what is found."""
    plants = (
        'import { useEffect } from "react";\n',
        'import { saveAs } from "../../../../apps/workspace/src/home/guideDownloads";\n',
        'import { thumbnailFromFile } from "../../../../apps/workspace/src/canvas/iconImage";\n',
        'import type { Node } from "../../../../packages/schemas/generated";\n',
        'import { create } from "zustand";\n',
    )
    for rel in PACKAGE_FILES:
        target = package_copy / (SHARED + rel)
        real = target.read_text(encoding="utf-8")
        assert clients.package_import_problems(package_copy, SHARED + rel) == [], (
            f"{rel} is not clean to begin with"
        )
        assert _bare_imports(real) == []
        for line in plants:
            target.write_text(line + real, encoding="utf-8")
            assert clients.package_import_problems(package_copy, SHARED + rel), (
                f"{line!r} is not found in {rel}"
            )
        target.write_text('import lodash from "lodash";\n' + real, encoding="utf-8")
        assert _bare_imports(target.read_text(encoding="utf-8")) == ["lodash"]
        target.write_text(real, encoding="utf-8")


# ------------------------------------------------------------------------- the page and the tab: never, in the package

#: What the package may not touch, in any file of the six (a comment naming one is refused too: the rule is read plainly,
#: and the prose is written around it).
_PAGE_OBJECT = re.compile(r"\b(window|document|sessionStorage|localStorage)\b")


def page_objects(text: str) -> list[str]:
    return sorted({m.group(1) for m in _PAGE_OBJECT.finditer(text)})


def test_the_package_files_use_no_page_or_tab_object() -> None:
    found = {rel: page_objects(_text(SHARED + rel)) for rel in PACKAGE_FILES}
    assert {rel: names for rel, names in found.items() if names} == {}, (
        "a package file touches the page or the tab"
    )


def test_a_page_or_tab_object_in_a_package_file_is_found(package_copy: Path) -> None:
    """Red for the check above (rule 15): in each of the six, a use of each of the four, in the shape the browser half wrote
    them (`window.open`, `document.createElement`), clean first. `guides.ts` with `window.open` put back in it is the case the
    brief names."""
    plants = {
        "sessionStorage": '\nexport const kept = sessionStorage.getItem("osprey.case");\n',
        "window": '\nexport const tab = () => window.open("", "_blank");\n',
        "document": '\nexport const link = () => document.createElement("a");\n',
        "localStorage": '\nexport const saved = localStorage.getItem("osprey.theme");\n',
    }
    for rel in PACKAGE_FILES:
        target = package_copy / (SHARED + rel)
        real = target.read_text(encoding="utf-8")
        assert page_objects(real) == [], f"{rel} is not clean to begin with"
        for word, plant in plants.items():
            target.write_text(real + plant, encoding="utf-8")
            assert page_objects(target.read_text(encoding="utf-8")) == [word], (
                f"{word} is not found in {rel}"
            )
        target.write_text(real, encoding="utf-8")


def test_the_browser_half_keeps_the_page() -> None:
    """The calls the package may not make are made where they belong. The guides' `guideDownloads.ts` makes the blank tab and
    the download and hands both to the package's `openGuide`, which now requires them; the pictures' binding hands the thumbnail
    step in; and the package's `openGuide` has no default for either."""
    downloads = _text(WORKSPACE_SRC + DOWNLOADS)
    assert "window.open(" in downloads and "document.createElement(" in downloads
    assert re.search(rf"""from\s+["']{re.escape(PACKAGE_NAME)}["']""", downloads), (
        "it does not take the guides from the package"
    )
    assert {"saveAs", "openBlankTab", "openGuide"} <= link._exported_names(downloads)
    guides = _text(SHARED + GUIDES)
    assert re.search(r"^\s+openTab: \(\) => Window \| null;", guides, re.M), "openTab is not a required dependency"
    assert re.search(r"^\s+save: \(url: string, name: string\) => void;", guides, re.M), (
        "save is not a required dependency"
    )
    assert "deps.openTab ??" not in guides and "deps.save ??" not in guides, "a default for a browser call came back"
    binding = _text(WORKSPACE_SRC + PICTURES)
    assert "bindEntityThumbnail(thumbnailFromFile)" in binding
    assert re.search(r"""from\s+["']\./iconImage["']""", binding)
    pictures = _text(SHARED + PICTURES)
    assert {"bindEntityThumbnail", "loadEntityPictures", "entityPictureFor", "setEntityPicture"} <= link._exported_names(pictures)
    assert "thumbnailFromFile" not in re.sub(r"//[^\n]*", "", pictures), "the package calls the canvas step itself"


# ------------------------------------------------------------------------------------------ how a move is compared


def test_the_move_changed_no_line_but_the_imports() -> None:
    """Each whole file is read as the commit that renamed it left it against the commit before: git's own detection finds the
    rename, and the two sides are compared there, never against the working tree (a later edit would be read as the move's).
    The record is compared byte for byte. A shallow clone has no history to read: skipped, as the earlier move tests are."""
    earlier._skip_if_shallow()
    for rel in WHOLE:
        new, old = SHARED + rel, OLD_OF[rel]
        commit = earlier._git(
            "log", "--follow", "-M", "--diff-filter=R", "--format=%H", "-1", "--", new
        ).strip()
        assert commit, f"git finds no rename into {new}: the file was not moved with `git mv`"
        was, now = earlier._git("show", f"{commit}^:{old}"), earlier._git("show", f"{commit}:{new}")
        assert was, f"{old} is not in the commit before the rename"
        if rel.endswith(".json"):
            assert was == now, f"{new} is not the record, byte for byte"
        else:
            assert earlier.only_import_lines_changed(was, now) == [], (
                f"{new} changed in more than its import lines"
            )


def test_a_moved_file_changed_in_more_than_its_imports_is_found() -> None:
    """Red for the comparison above: the real client's schema import moved (the package's way of writing it), once alone and
    once with a line of the code changed."""
    was = 'import type { Right } from "../../../../packages/schemas/generated";\n\nexport const CAP = 7;\n'
    moved = was.replace("../../../../packages/schemas/generated", "../../../schemas/generated")
    assert earlier.only_import_lines_changed(was, moved) == []
    assert earlier.only_import_lines_changed(was, moved.replace("7", "8")) != []


#: The code lines (comments, blank lines, import statements and lines of only brackets are not code lines here) the guides
#: split adds and loses, and nothing else. Added: the two dependencies are now required (the optional ones are lost), the call
#: sites use them with no default, the four places are the keys of `PLACE_WORDS`, and the workspace half holds `saveAs` (now
#: exported), the blank tab and the package's `openGuide` with both supplied.
GUIDES_ADDED = Counter(
    {
        "type PlaceId = keyof typeof PLACE_WORDS;": 1,
        "openTab: () => Window | null;": 1,
        "save: (url: string, name: string) => void;": 1,
        "const tab = showsPdf ? deps.openTab() : null;": 1,
        "deps.save(url, GUIDE_FILE[guide]);": 1,
        "export function saveAs(url: string, name: string): void {": 1,
        "export function openBlankTab(): Window | null {": 1,
        'return window.open("", "_blank");': 1,
        'export type BrowserGuideDeps = Omit<OpenGuideDeps, "openTab" | "save"> & Partial<Pick<OpenGuideDeps, "openTab" | "save">>;': 1,
        "export function openGuide(guide: GuideId, deps: BrowserGuideDeps): Promise<string | null> {": 1,
        "return openGuideWith(guide, { ...deps, openTab: deps.openTab ?? openBlankTab, save: deps.save ?? saveAs });": 1,
    }
)
GUIDES_LOST = Counter(
    {
        "openTab?: () => Window | null;": 1,
        "save?: (url: string, name: string) => void;": 1,
        "function saveAs(url: string, name: string): void {": 1,
        'const tab = showsPdf ? (deps.openTab ?? (() => window.open("", "_blank")))() : null;': 1,
        "(deps.save ?? saveAs)(url, GUIDE_FILE[guide]);": 1,
    }
)
#: The pictures split: the thumbnail step is held and handed in (its type, the holder, the binding function, the guard that
#: it is bound, and the call), the workspace's file binds it and passes the package's names on. The one line lost is the call
#: that drew it itself.
PICTURES_ADDED = Counter(
    {
        "export type EntityThumbnail = (blob: Blob) => Promise<string>;": 1,
        "let makeThumbnail: EntityThumbnail | null = null;": 1,
        "export function bindEntityThumbnail(make: EntityThumbnail): void {": 1,
        "makeThumbnail = make;": 1,
        'if (!makeThumbnail) throw new Error("no thumbnail step is bound");': 1,
        "return makeThumbnail(await response.blob());": 1,
        "bindEntityThumbnail(thumbnailFromFile);": 1,
        "export {": 1,
        "entityPictureFor,": 1,
        "forgetEntityPictures,": 1,
        "loadEntityPictures,": 1,
        "onEntityPicturesChange,": 1,
        "removeEntityPicture,": 1,
        "setEntityPicture,": 1,
        "setEntityPictureForTest,": 1,
        "type PictureApi,": 1,
        '} from "@ospreyflow/glass-shared";': 1,
    }
)
PICTURES_LOST = Counter({"return thumbnailFromFile(await response.blob());": 1})


def _split_at(
    added_in: str, old: str, package: str, workspace: str
) -> tuple[Counter[str], Counter[str]]:
    """The split's code lines against the old file's, read at the commit that added the file named `added_in` (one that did
    not exist before it); `old` is read in the commit before."""
    commit = earlier._git("log", "--diff-filter=A", "--format=%H", "-1", "--", added_in).strip()
    assert commit, f"git finds no commit that added {added_in}"
    assert _exists_at(f"{commit}^", old), f"{old} is not in the commit before the split"
    return earlier.split_differences(
        earlier._git("show", f"{commit}^:{old}"),
        earlier._git("show", f"{commit}:{package}"),
        earlier._git("show", f"{commit}:{workspace}"),
    )


def test_the_guides_split_changed_no_line_but_the_two_dependencies() -> None:
    """`home/guides.ts` in the commit before the split, against the two halves in the commit that wrote the browser half:
    between them they hold every code line the old file did, and only the lines `GUIDES_ADDED` writes out beyond them."""
    earlier._skip_if_shallow()
    added, lost = _split_at(
        WORKSPACE_SRC + DOWNLOADS, OLD_OF[GUIDES], SHARED + GUIDES, WORKSPACE_SRC + DOWNLOADS
    )
    assert added == GUIDES_ADDED, f"lines the split added: {dict(added)}"
    assert lost == GUIDES_LOST, f"lines the split lost: {dict(lost)}"


def test_the_pictures_split_changed_no_line_but_the_binding() -> None:
    """The same for `canvas/entityPictures.ts`: at the commit that added the package's half, against the old file in the
    commit before it."""
    earlier._skip_if_shallow()
    added, lost = _split_at(
        SHARED + PICTURES, WORKSPACE_SRC + PICTURES, SHARED + PICTURES, WORKSPACE_SRC + PICTURES
    )
    assert added == PICTURES_ADDED, f"lines the split added: {dict(added)}"
    assert lost == PICTURES_LOST, f"lines the split lost: {dict(lost)}"


def test_the_rule_group_move_changed_no_line() -> None:
    """The one edit to a React file: `reports/figureParts.tsx` in the commit before, against the same file and the package's
    `reports/ruleGroup.ts` after. Between them they hold every code line the old file did and no other: `alertRuleGroup`, its
    type and the table it reads moved, byte for byte."""
    earlier._skip_if_shallow()
    added, lost = _split_at(
        SHARED + RULE_GROUP, WORKSPACE_SRC + FIGURE_PARTS, SHARED + RULE_GROUP, WORKSPACE_SRC + FIGURE_PARTS
    )
    assert added == Counter(), f"lines the move added: {dict(added)}"
    assert lost == Counter(), f"lines the move lost: {dict(lost)}"
    moved = _text(SHARED + RULE_GROUP)
    assert {"alertRuleGroup", "RuleGroup"} <= link._exported_names(moved)
    assert "alertRuleGroup" not in _text(WORKSPACE_SRC + FIGURE_PARTS), "the React file still defines it"


def test_a_split_that_adds_or_loses_a_line_is_found() -> None:
    """Red for the comparisons above, at the real call-site shape: the old `openGuide` lines, split cleanly (the optional
    dependency made required: the allowed lines), then with a line added to one half, a line lost, and the browser call kept in
    both halves."""
    old = (
        "export interface OpenGuideDeps {\n  openTab?: () => Window | null;\n}\n"
        'export function open(deps: OpenGuideDeps) {\n  const tab = (deps.openTab ?? (() => window.open("", "_blank")))();\n}\n'
    )
    package = (
        "export interface OpenGuideDeps {\n  openTab: () => Window | null;\n}\n"
        "export function open(deps: OpenGuideDeps) {\n  const tab = deps.openTab();\n}\n"
    )
    workspace = 'export function openBlankTab() {\n  return window.open("", "_blank");\n}\n'
    added, lost = earlier.split_differences(old, package, workspace)
    assert lost == Counter(
        {
            "openTab?: () => Window | null;": 1,
            'const tab = (deps.openTab ?? (() => window.open("", "_blank")))();': 1,
        }
    )
    assert "const tab = deps.openTab();" in added
    more, _ = earlier.split_differences(old, package + "export const CAP = 7;\n", workspace)
    assert more - added == Counter({"export const CAP = 7;": 1})
    _, gone = earlier.split_differences(
        old, package.replace("export function open(deps: OpenGuideDeps) {\n", ""), workspace
    )
    assert gone - lost == Counter({"export function open(deps: OpenGuideDeps) {": 1})
    kept = 'const tab = window.open("", "_blank");\n'
    both, _ = earlier.split_differences(kept, kept, kept)
    assert both == Counter({kept.strip(): 1})  # the same line in both halves: kept twice, and found


# ---------------------------------------------------------------------------------------------------- the old paths


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


def test_an_old_path_written_in_pieces_or_whole_is_found(tmp_path: Path) -> None:
    """Red for the walk above (rule 15), in the shapes the readers wrote it: whole, in a `Path(...) /` join, as `os.path.join`
    arguments and through an f-string, each clean beside the package's place written the way the three readers now write it."""
    clean = (
        'ROLES = SHARED / "help" / "roles.ts"\n'
        'RECORD = SHARED_SRC / "shell/placesByRole.json"\n'
        'LONG = CORE / "packages" / "glass-shared" / "src" / "home" / "guides.ts"\n'
        'FIGURES = "packages/glass-shared/src/home/homeData.ts"\n'
    )
    planted = {
        "a join": 'ROLES = WORKSPACE / "help" / "roles.ts"\n',
        "a whole path": 'RECORD = CORE / "apps/workspace/src/shell/placesByRole.json"\n',
        "a join of home": 'GUIDES = SRC / "home" / "guides.ts"\n',
        "os.path.join": 'HOME = os.path.join(SRC, "home", "homeData.ts")\n',
        "the Admin client": 'API = REPO / "apps" / "workspace" / "src" / "admin" / "api.ts"\n',
        "an f-string": 'TEXT = f"{CORE}/apps/workspace/src/help/roles.ts"\n',
        "a bare shorthand": "# read from help/roles.ts, the words\n",
    }
    target = tmp_path / "reader.py"
    target.write_text(clean, encoding="utf-8")
    assert old_path_mentions(tmp_path, ["reader.py"]) == [], "the new place is read as an old one"
    for case_name, line in planted.items():
        target.write_text(clean + line, encoding="utf-8")
        assert old_path_mentions(tmp_path, ["reader.py"]), f"{case_name} is not found"


def test_every_named_exception_still_has_its_reason() -> None:
    """An exception outlives its reason when the file it excuses no longer names an old path: left in `NAMED` it keeps that
    file outside the walk, and an old path could be written back into it unseen (rule 12)."""
    stale = [rel for rel in NAMED if not old_path_mentions(ROOT, [rel])]
    assert stale == [], (
        f"{stale} no longer name an old path: remove them from NAMED, and the walk will cover them"
    )


# ----------------------------------------------------------------------------------------------------- the imports


def _package_names(root: Path) -> set[str]:
    """Every name the six files export, read from the package's copies (the old ones are gone), and the two the index renames."""
    names = {new for _, _, new in RENAMED_BY_THE_INDEX} | {"PLACES_BY_ROLE"}
    for rel in PACKAGE_FILES:
        try:
            names |= link._exported_names((root / (SHARED + rel)).read_text(encoding="utf-8"))
        except OSError:
            continue
    return names


_IMPORT_CLAUSE = re.compile(
    r"""(?:^|\n)\s*import\s+(?:type\s+)?(\{[^}]*\})\s*from\s*["']([^"']+)["']""", re.S
)


def imports_not_reaching(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The relative specifiers that resolve to an old path, or into the package's folder instead of its name; and the number
    of files that import a name of the six from the package. Resolution is by path alone: an old file need not exist."""
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
                rf"""(?:^|\n)\s*import\s+(?:type\s+)?(\{{[^}}]*\}})\s*from\s*["']{re.escape(PACKAGE_NAME)}["']""",
                text,
            )
        ):
            importers += 1
        for clause, spec in _IMPORT_CLAUSE.findall(text):
            if re.search(r"/figureParts$", spec) and {"alertRuleGroup", "RuleGroup"} & earlier._names(clause):
                bad.append(f"{rel}: {spec} (the rule group is the package's: take it from {PACKAGE_NAME})")
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
    assert importers >= 40, (
        f"only {importers} file(s) under OspreyFlow_Core import a name of the six from {PACKAGE_NAME}: the walk found too few imports, or the importers were not repointed"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach the package by its name: {bad[:10]}"


#: The browser's half of the guides: the one name a screen takes from `guideDownloads`, and nothing else is taken from there.
BROWSER_CALLS = {"openGuide"}


def browser_call_imports(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The imports that take `openGuide` from anywhere but a `guideDownloads` module or the package's test files, and the number
    of files that take it from the browser half. The package's own `openGuide` takes two dependencies a screen does not have."""
    bad: list[str] = []
    takers = 0
    for rel in rels:
        if Path(rel).suffix not in earlier._SOURCE_SUFFIXES or not rel.startswith(APPS):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        taken = False
        for clause, spec in _IMPORT_CLAUSE.findall(text):
            wanted = BROWSER_CALLS & earlier._names(clause)
            if not wanted:
                continue
            if spec.endswith("/guideDownloads"):
                taken = True
            elif not rel.endswith(("guides.test.ts", "/guideDownloads.ts")):  # the package's own test, and the browser half itself, call the package's `openGuide`
                bad.append(f"{rel}: {sorted(wanted)} from {spec}")
        takers += taken
    return bad, takers


def test_the_browser_calls_are_taken_from_the_browser_half() -> None:
    bad, takers = browser_call_imports(ROOT, earlier.tracked())
    assert takers >= 3, (
        f"only {takers} file(s) take openGuide from guideDownloads: the walk found too few"
    )
    assert bad == [], f"{len(bad)} import(s) take openGuide from elsewhere: {bad[:10]}"


def test_a_browser_call_taken_from_the_package_is_found(tmp_path: Path) -> None:
    """Red for the check above (rule 15), on the lines the tree holds: the app's, the start screen's and the guides' own test,
    written to take the call from the package (which would call it without a tab) or from the old file."""
    cases = {
        APPS + "workspace/src/App.tsx": (
            'import { openGuide } from "./home/guideDownloads";',
            f'import {{ openGuide }} from "{PACKAGE_NAME}";',
        ),
        APPS + "workspace/src/shell/startScreen.tsx": (
            'import { openGuide } from "../home/guideDownloads";',
            'import { openGuide } from "../home/guides";',
        ),
    }
    for rel, (clean, planted) in cases.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(clean + "\n", encoding="utf-8")
        assert browser_call_imports(tmp_path, [rel]) == ([], 1), rel
        target.write_text(planted + "\n", encoding="utf-8")
        assert browser_call_imports(tmp_path, [rel])[0], f"{planted!r} is not found in {rel}"


_PLANTED_IMPORTS = {
    # (path of the file that held the line, the line as the tree wrote it, the line it has now)
    "the roles' words, from a screen in a child folder": (
        WORKSPACE_SRC + "admin/AdminPlace.tsx",
        'import { whyNotByRole } from "../help/roles";',
        f'import {{ whyNotByRole }} from "{PACKAGE_NAME}";',
    ),
    "the roles' words, from a grandchild folder": (
        WORKSPACE_SRC + "admin/sections/People.tsx",
        'import { rightName } from "../../help/roles";',
        f'import {{ rightName }} from "{PACKAGE_NAME}";',
    ),
    "the roles' words, beside them (a sibling)": (
        WORKSPACE_SRC + "help/RolesHelpPage.tsx",
        'import { HELP_TITLE, LEVEL_WORDS, rightName } from "./roles";',
        f'import {{ HELP_TITLE, LEVEL_WORDS, rightName }} from "{PACKAGE_NAME}";',
    ),
    "the record, in a test": (
        WORKSPACE_SRC + "shell/places.test.tsx",
        'import BY_ROLE from "./placesByRole.json";',
        f'import {{ PLACES_BY_ROLE as BY_ROLE }} from "{PACKAGE_NAME}";',
    ),
    "the record, from a test in another folder": (
        WORKSPACE_SRC + "ingest/studio/rightsGate.test.tsx",
        'import BY_ROLE from "../../shell/placesByRole.json";',
        f'import {{ PLACES_BY_ROLE as BY_ROLE }} from "{PACKAGE_NAME}";',
    ),
    "the Admin client, beside it (a sibling named api)": (
        WORKSPACE_SRC + "admin/Schedules.tsx",
        'import { changeSchedule, type AdminApi } from "./api";',
        f'import {{ changeSchedule, type AdminApi }} from "{PACKAGE_NAME}";',
    ),
    "the Admin client, from a section": (
        WORKSPACE_SRC + "admin/sections/Audit.tsx",
        'import { readAudit, type AdminApi, type AuditQuery } from "../api";',
        f'import {{ readAudit, type AdminApi, type AuditQuery }} from "{PACKAGE_NAME}";',
    ),
    "the Admin client's dataset list, under its new name": (
        WORKSPACE_SRC + "admin/sections/Connections.tsx",
        'import { listDatasets, testConnection, type AdminApi } from "../api";',
        f'import {{ listAdminDatasets as listDatasets, testAdminConnection as testConnection, type AdminApi }} from "{PACKAGE_NAME}";',
    ),
    "Home's figures, from the shell": (
        WORKSPACE_SRC + "shell/startScreen.tsx",
        'import type { HomeSummary } from "../home/homeData";',
        f'import type {{ HomeSummary }} from "{PACKAGE_NAME}";',
    ),
    "Home's figures, in its own test (a sibling)": (
        WORKSPACE_SRC + "home/homeData.test.ts",
        'import { loadHome, openInQueue, summariseHome, whenLabel, type HomeInputs } from "./homeData";',
        f'import {{ loadHome, openInQueue, summariseHome, whenLabel, type HomeInputs }} from "{PACKAGE_NAME}";',
    ),
    "the guides' words, from a screen": (
        WORKSPACE_SRC + "welcome/WorkspaceWelcome.tsx",
        'import { GUIDE_FOR_PLACE } from "../home/guides";',
        f'import {{ GUIDE_FOR_PLACE }} from "{PACKAGE_NAME}";',
    ),
    "the guides' words, beside them (a sibling)": (
        WORKSPACE_SRC + "home/HomePage.tsx",
        'import { GUIDE_FOR_PLACE, WORDS as GUIDE_WORDS, guideUrl, type GuideId } from "./guides";',
        f'import {{ GUIDE_FOR_PLACE, WORDS as GUIDE_WORDS, guideUrl, type GuideId }} from "{PACKAGE_NAME}";',
    ),
    "the guide's address, from the keyboard harness (a path outside src)": (
        APPS + "workspace/keyboard/top-bar-harness.tsx",
        'import { guideUrl } from "../src/home/guides";',
        f'import {{ guideUrl }} from "{PACKAGE_NAME}";',
    ),
    "the rule group, from the figures' alerts panel": (
        WORKSPACE_SRC + "reports/AlertsPanel.tsx",
        'import { AGE_BANDS, alertRuleGroup, groupKey, groupName, NUMBER, plural, Section, type RuleGroup } from "./figureParts";',
        f'import {{ AGE_BANDS, groupKey, groupName, NUMBER, plural, Section }} from "./figureParts";\nimport {{ alertRuleGroup, type RuleGroup }} from "{PACKAGE_NAME}";',
    ),
    "a deep import into the package": (
        WORKSPACE_SRC + "admin/AdminPlace.tsx",
        'import { whyNotByRole } from "../../../../packages/glass-shared/src/help/roles";',
        f'import {{ whyNotByRole }} from "{PACKAGE_NAME}";',
    ),
    "an old path in a comment of the workspace (the roles' words)": (
        WORKSPACE_SRC + "admin/tips.tsx",
        "// in the words of `help/roles.ts`, the one source the help page and the guides take too. A tip names",
        "// in the words of `packages/glass-shared/src/help/roles.ts`, the one source the help page and the guides take too. A tip names",
    ),
    "the record, named in the specification": (
        "OspreyFlow_Build/spec/02_GLASS_FRONTEND.md",
        "singly (`shell/placesByRole.json`, which the Glass's `placesFor` is held to); checks that `places.json`",
        "singly (`packages/glass-shared/src/shell/placesByRole.json`, which the Glass's `placesFor` is held to); checks that `places.json`",
    ),
    "Home's figures, in the alerts gap map": (
        "OspreyFlow_Build/spec/glass_redesign/ALERTS_GAP_MAP.md",
        '     <case>" (`apps/workspace/src/home/homeData.ts` 101–127).',
        '     <case>" (`packages/glass-shared/src/home/homeData.ts` 101–127).',
    ),
}


@pytest.mark.parametrize("case_name", sorted(_PLANTED_IMPORTS))
def test_an_old_path_put_back_in_one_importer_is_found(case_name: str, package_copy: Path) -> None:
    """Red for the two walks above (rule 15): each line the tree really held, put back in the file that held it (or one the
    move could have left it in). The same file with the new line is clean first, so the plant is what is found and not something
    else in the file. The package's own copies are in the tree under `package_copy`, so the names are known."""
    rel, old_line, new_line = _PLANTED_IMPORTS[case_name]
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


def test_a_file_that_names_none_of_the_new_names_is_not_counted_as_an_importer(
    package_copy: Path,
) -> None:
    """The importers' floor means something only if a file that takes some other name from the package is not one."""
    rel = WORKSPACE_SRC + "theme/ThemeToggle.tsx"
    (package_copy / rel).parent.mkdir(parents=True)
    (package_copy / rel).write_text(
        f'import {{ applyTheme }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
    )
    assert imports_not_reaching(package_copy, [rel]) == ([], 0)
    for name in (
        "whyNotByRole",
        "PLACES_BY_ROLE",
        "listAdminDatasets",
        "summariseHome",
        "openGuide",
        "alertRuleGroup",
        "bindEntityThumbnail",
    ):
        (package_copy / rel).write_text(
            f'import {{ {name} }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
        )
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
    """Red for the walk above, at the shapes the move could leave: the top bar's harness still importing the guide's address by
    the old path, and the index exporting a file that is not there."""
    spec = APPS + "workspace/keyboard/top-bar.spec.ts"
    harness = APPS + "workspace/keyboard/top-bar-harness.tsx"
    files = {
        spec: 'import { mount } from "./top-bar-harness";\n',
        harness: (
            f'import {{ guideUrl }} from "{PACKAGE_NAME}";\n'
            'import { openGuide } from "../src/home/guideDownloads";\n'
        ),
        WORKSPACE_SRC + "home/guideDownloads.ts": "export const openGuide = 1;\n",
        SHARED + "index.ts": 'export * from "./home/guides";\n',
        SHARED + "home/guides.ts": "export const WORDS = {};\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == []
    clean = (tmp_path / harness).read_text(encoding="utf-8")
    (tmp_path / harness).write_text(clean.replace("guideDownloads", "guides"), encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [f"{harness}: ../src/home/guides"]
    (tmp_path / harness).write_text(clean, encoding="utf-8")
    (tmp_path / SHARED / "home" / "guides.ts").unlink()
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [f"{SHARED}index.ts: ./home/guides"]


# ------------------------------------------------------------------------------------------ the Python readers


def test_the_readers_read_the_new_paths() -> None:
    """The three Python tests that read a moved file read it where it is now: the package's `src`, never the workspace's. The
    file is there and the old place holds nothing."""
    assert roles_words.ROLES_TS == SHARED_SRC / "help" / "roles.ts" and roles_words.ROLES_TS.is_file()
    assert roles_words.PLACES_BY_ROLE == SHARED_SRC / "shell" / "placesByRole.json"
    assert roles_words.PLACES_BY_ROLE.is_file()
    assert roles_words.WELCOME == CORE / "apps" / "workspace" / "src" / "welcome" / "WelcomeAbout.tsx"
    assert roles_words.WELCOME.is_file(), "the welcome page is a React file and stays in the workspace"
    assert place_routes.BY_ROLE_JSON == SHARED_SRC / "shell" / "placesByRole.json"
    assert place_routes.BY_ROLE_JSON.is_file()
    old = CORE / "apps" / "workspace" / "src"
    assert not (old / "help" / "roles.ts").exists() and not (old / "shell" / "placesByRole.json").exists()


def _core_with(tmp_path: Path, *, package: bool, workspace: bool) -> Path:
    """A root laid out as `OspreyFlow_Core`, holding the real `help/roles.ts` at the package's place, the workspace's, or both,
    with one right's name added to `RIGHT_NAMES` so a read of it can be told from a read of any other."""
    real = (SHARED_SRC / "help" / "roles.ts").read_text(encoding="utf-8")
    planted = real.replace(
        'edit_target_model: "Edit domain model",',
        'edit_target_model: "Edit domain model",\n  planted_right: "Planted words",',
    )
    assert planted != real, "RIGHT_NAMES has changed shape: the plant has nowhere to go"
    for held, where in ((package, "packages/glass-shared/src"), (workspace, "apps/workspace/src")):
        if held:
            (tmp_path / where / "help").mkdir(parents=True)
            (tmp_path / where / "help" / "roles.ts").write_text(planted, encoding="utf-8")
    return tmp_path


def test_the_people_words_reader_reads_the_package_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keyed by root (rule 15): a copy of `roles.ts` with one more right name at the package's place is read; the same copy at
    the workspace's old place only is not found (the reader says it, loudly); and the real tree is read as it is."""
    real = people._glass_right_names()
    assert real.get("edit_target_model") == "Edit domain model" and "planted_right" not in real
    monkeypatch.setattr(people, "CORE", _core_with(tmp_path / "package", package=True, workspace=False))
    assert people._glass_right_names()["planted_right"] == "Planted words"
    monkeypatch.setattr(people, "CORE", _core_with(tmp_path / "workspace", package=False, workspace=True))
    with pytest.raises(FileNotFoundError):
        people._glass_right_names()


def test_the_guide_role_words_reader_reads_the_package_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guides' drift test reads the words from the package's `roles.ts` and the places from the package's record: a copy at
    the package's place with one role's sentence changed is read (and a guide's role table is red against it), the same words at
    the workspace's old place are not found, and the real words are green against every guide."""
    copy = tmp_path / "package" / "src"
    (copy / "help").mkdir(parents=True)
    (copy / "shell").mkdir(parents=True)
    real = (SHARED_SRC / "help" / "roles.ts").read_text(encoding="utf-8")
    sentence = "Investigates cases, works alerts and keeps watches. Reads figures and boards."
    assert sentence in real
    (copy / "help" / "roles.ts").write_text(real.replace(sentence, "Looks at cases."), encoding="utf-8")
    shutil.copyfile(SHARED_SRC / "shell" / "placesByRole.json", copy / "shell" / "placesByRole.json")
    guide = (CORE / "docs" / "user-guide.md").read_text(encoding="utf-8")
    assert roles_words.role_drift(guide, roles_words.roles_ts()) == [], "the real words are not green"
    monkeypatch.setattr(roles_words, "ROLES_TS", copy / "help" / "roles.ts")
    planted = roles_words.roles_ts()
    assert planted["roles"]["analyst"][1] == "Looks at cases."
    assert roles_words.role_drift(guide, planted), "a changed role sentence is not red against the guide"
    old = tmp_path / "workspace" / "src"
    (old / "help").mkdir(parents=True)
    monkeypatch.setattr(roles_words, "ROLES_TS", old / "help" / "roles.ts")
    with pytest.raises(FileNotFoundError):
        roles_words.roles_ts()
    assert json.loads(roles_words.PLACES_BY_ROLE.read_text(encoding="utf-8"))["roles"]["analyst"]["places"]


def test_the_place_routes_record_is_written_and_read_at_the_package_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generator is `test_the_record_of_places_by_role_is_the_routes`: it compares the record with what the routes answer,
    and with `OSPREY_WRITE_PLACES_BY_ROLE=1` writes it first. A stale copy at the (package) path it names is red; the same call
    with the variable set rewrites that file, byte for byte what the real record holds, and is green. Red then green, on a copy:
    the real record is never written."""
    real = place_routes.BY_ROLE_JSON.read_text(encoding="utf-8")
    stale = tmp_path / "shell" / "placesByRole.json"
    stale.parent.mkdir()
    document = json.loads(real)
    document["roles"]["analyst"]["places"] = ["admin"]
    stale.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    monkeypatch.setattr(place_routes, "BY_ROLE_JSON", stale)
    monkeypatch.delenv("OSPREY_WRITE_PLACES_BY_ROLE", raising=False)
    with pytest.raises(AssertionError):
        place_routes.test_the_record_of_places_by_role_is_the_routes()  # red: the stale copy at the package path
    monkeypatch.setenv("OSPREY_WRITE_PLACES_BY_ROLE", "1")
    place_routes.test_the_record_of_places_by_role_is_the_routes()  # green: the generator wrote it
    assert stale.read_text(encoding="utf-8") == real, "the generator wrote something other than the record"
    monkeypatch.undo()
    assert place_routes.BY_ROLE_JSON.read_text(encoding="utf-8") == real, "the real record was written"


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
    """Neither image names a moved file in a `COPY`, and each copies the package's source."""
    for dockerfile in (WORKSPACE_IMAGE, image.DOCKERFILE):
        text = dockerfile.read_text(encoding="utf-8")
        assert stale_copies(text) == [], f"{dockerfile.name} copies a path that moved"
        assert "packages/glass-shared/src" in clients.copy_sources(text), (
            f"{dockerfile.parent.name}/{dockerfile.name} does not copy packages/glass-shared/src"
        )


def test_the_harness_image_copies_what_the_new_files_need() -> None:
    """The harness frontend reaches the package's index, and by it every file: each file it reaches is under a `COPY`, and
    every `COPY` of a workspace path still names something that exists and is reached. The walk reaches the six, and the record
    the roles' words read."""
    reached = image._reached_workspace_files()
    copied = image._copied_paths()
    assert image._missing(copied, reached) == []
    assert earlier.dangling(copied, reached) == []
    names = {str(p.relative_to(CORE.resolve())) for p in reached}
    for rel in PACKAGE_FILES:
        assert f"packages/glass-shared/src/{rel}" in names, f"the walk does not reach the package's {rel}"
    assert f"packages/glass-shared/src/{RECORD}" in names, "the walk does not reach the record"


def test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found() -> None:
    """Red for the checks above (rule 15), on the real stages: the package's line taken out of the harness image (the files the
    index reaches are missing), a line a moved file once needed put in (it copies a file that is not there), and the same two
    faults on the workspace image."""
    real = image.DOCKERFILE.read_text(encoding="utf-8")
    reached = image._reached_workspace_files()
    assert stale_copies(real) == []
    assert image._missing(image._copied_paths(real), reached) == []

    shared = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    assert shared in real
    missing = image._missing(image._copied_paths(real.replace(shared, "", 1)), reached)
    for rel in PACKAGE_FILES:
        assert f"packages/glass-shared/src/{rel}" in missing, f"{rel} is not found missing"

    for rel in ("help/roles.ts", "admin/api.ts", "shell/placesByRole.json"):
        line = f"COPY apps/workspace/src/{rel} ./apps/workspace/src/{rel}\n"
        stale = real.replace(shared, shared + line, 1)
        assert stale_copies(stale) == [f"apps/workspace/src/{rel}"]
        assert earlier.dangling(image._copied_paths(stale), reached) == [f"apps/workspace/src/{rel}"]

    workspace = WORKSPACE_IMAGE.read_text(encoding="utf-8")
    assert stale_copies(workspace) == []
    package_line = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    assert package_line in workspace
    assert "packages/glass-shared/src" not in clients.copy_sources(
        workspace.replace(package_line, "", 1)
    )
    assert stale_copies(workspace + "COPY apps/workspace/src/home/guides.ts ./x\n") == [
        "apps/workspace/src/home/guides.ts"
    ]


# --------------------------------------------------------------------------------------------------- the four gates

#: The files each gate read on main before this slice: the number each reported or, where it reports none, the files its own
#: rules select (measured on 21 November 2026, on the tip PL4d3e started from, a3e2fa5, after PL4d3d). The files moved from a
#: folder each gate reads to another it reads, and two were added, so the numbers do not fall: none may.
FILES_BEFORE = {"colour-drift": 495, "design-check": 901, "ui-words": 499, "no-branches": 1750}


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


def test_the_colour_drift_check_reports_a_plant_in_a_new_file(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    mirrors = dict(colour_drift_check.SCANNED).get(SHARED_SRC)
    assert mirrors is not None, "the colour-drift check does not read the package"
    monkeypatch.setattr(colour_drift_check, "CORE", shared_copy.parent.parent.parent)
    monkeypatch.setattr(colour_drift_check, "SCANNED", ((shared_copy, mirrors),))
    assert colour_drift_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    earlier._append(
        shared_copy, "home/homeData.ts", '\nexport const STRIPE = { background: "#12ab34", padding: 8 };\n'
    )
    assert colour_drift_check.main() == 1
    assert "packages/glass-shared/src/home/homeData.ts:" in capsys.readouterr().out


def test_the_design_detector_reports_a_plant_in_a_new_file(
    shared_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(design_check, "SCANNED", [shared_copy])
    assert design_check.unexcused(design_check.detect(design_check.SCANNED)) == [], (
        "the clean copy already has findings"
    )
    earlier._append(
        shared_copy,
        "admin/api.ts",
        "\nexport const TOAST_STYLE = {\n"
        '  background: "var(--surface-raised)", borderLeft: "3px solid var(--error)", borderRadius: "8px",\n'
        '  padding: "12px 16px", boxShadow: "var(--overlay-shadow)",\n'
        "};\n",
    )
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [("api.ts", "side-tab")]
    assert "admin" in found[0]["file"]


def test_the_ui_words_check_reports_a_plant_in_a_new_file(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = shared_copy.parent.parent / "no-src"
    empty.mkdir()
    monkeypatch.setattr(ui_words_check, "SHARED_SRC", shared_copy)
    monkeypatch.setattr(ui_words_check, "GLASS_SRC", empty)
    monkeypatch.setattr(ui_words_check, "DESIGN_PACKAGE", empty)
    assert ui_words_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    earlier._append(shared_copy, "help/roles.ts", '\nexport const LABEL = "Target model";\n')
    assert ui_words_check.main() == 1
    assert "packages/glass-shared/src/help/roles.ts:" in capsys.readouterr().out


def test_the_no_branches_check_reports_a_plant_in_a_new_file(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    top = "packages/glass-shared/src"
    assert top in no_branches_check.SCANNED
    walk = no_branches_check.tree_files
    tmp_core = shared_copy.parent.parent.parent
    monkeypatch.setattr(no_branches_check, "tree_files", lambda: walk(tmp_core, [top]))
    assert no_branches_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    earlier._append(shared_copy, "canvas/entityPictures.ts", '\nexport const BRANCH_CASE = "branch-by-filter";\n')
    assert no_branches_check.main() == 1
    assert f"{top}/canvas/entityPictures.ts:" in capsys.readouterr().out


# -------------------------------------------------------------------------------------------------- the word-walkers

#: The six as (folder, stem) pairs, never written as a path (the old-path scan reads the other walkers' tables too).
_MOVED = {
    "help": ("roles",),
    "admin": ("api",),
    "home": ("guides", "homeData"),
    "reports": ("ruleGroup",),
    "canvas": ("entityPictures",),
}
MOVED_FILES = tuple(f"{folder}/{stem}.ts" for folder, stems in _MOVED.items() for stem in stems)


def test_the_moved_table_is_the_list_of_six() -> None:
    assert sorted(MOVED_FILES) == sorted(PACKAGE_FILES)


@pytest.mark.parametrize("client", MOVED_FILES)
def test_the_people_name_walk_reads_each_package_file(client: str, tmp_path: Path) -> None:
    """The walk behind `test_people_section_words.py` reads the file at its place in the package; the same copy, clean, finds
    nothing, and with an old name planted at the line a person's words sit on it is found."""
    read = {p.relative_to(CORE).as_posix() for p in people._glass_files()}
    assert f"packages/glass-shared/src/{client}" in read, client
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
    copy.write_text(real + '\nexport const planted = "Set it in Admin › People.";\n', encoding="utf-8")
    assert found() == [real.count("\n") + 2]


@pytest.mark.parametrize("client", MOVED_FILES)
def test_the_view_word_walk_reads_each_package_file(client: str, tmp_path: Path) -> None:
    """The same for the walk behind `test_guide_navigation_words.py`: read at its place in the package, clean finds nothing,
    an old view word on screen is found, and in a comment (which a person never sees) it is not. The pictures and the guides
    are held by both roots, so each is read under both."""
    sources = navigation.glass_sources()
    assert client in sources or f"shared:{client}" in sources, client
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


def test_the_browser_half_and_the_binding_are_read_from_the_workspace_root() -> None:
    """The two files that stayed in the workspace are read by the walkers through the workspace's own root; the pictures are
    held by both roots (the package's plain half and the workspace's binding), so the package's is read under `shared:`."""
    read = {p.relative_to(CORE).as_posix() for p in people._glass_files()}
    sources = navigation.glass_sources()
    for rel in (DOWNLOADS, PICTURES):
        assert f"apps/workspace/src/{rel}" in read, rel
        assert rel in sources, rel
    assert f"shared:{PICTURES}" in sources, "the package's half of the pictures is not read under its root"


@pytest.mark.parametrize("planted_in", [0, 1])
def test_a_place_held_by_both_roots_is_read_from_both(planted_in: int, tmp_path: Path) -> None:
    """Keyed by root (D2's last finding): a place that two roots both hold is kept under both. The pictures are held by the
    workspace (its binding) and by the package (its plain half) at once: an old word in either is found, the second root's
    under `shared:`."""
    roots = (tmp_path / f"a{planted_in}", tmp_path / f"b{planted_in}")
    for n, root in enumerate(roots):
        (root / "canvas").mkdir(parents=True)
        (root / "canvas" / "entityPictures.ts").write_text(
            'export const word = "Clear view";\n' if n == planted_in else "export const word = 1;\n",
            encoding="utf-8",
        )
    expected = "canvas/entityPictures.ts" if planted_in == 0 else "shared:canvas/entityPictures.ts"
    assert navigation.old_view_words_on_screen(navigation.glass_sources(roots)) == [
        f"{expected}: 'Clear view'"
    ]


KIT = CORE / "apps" / "workspace" / "src" / "copyTextsTestKit.ts"
_KIT_FOLDERS = re.compile(r"^export const MOVED_FOLDERS = /(.*)/;$", re.M)


def test_the_vitest_walkers_name_the_new_folders() -> None:
    """`copyWords`, `copyNoClient` and `resolvedPrincipal` walk the kit's two roots, and each has a case that plants in a copy of
    every file the kit lists as an admin client. The kit selects the package's folders by `MOVED_FOLDERS`: every folder of the
    six is among them (the vitest cases themselves run under `npm test --workspace apps/workspace`)."""
    kit = KIT.read_text(encoding="utf-8")
    found = _KIT_FOLDERS.search(kit)
    assert found, "copyTextsTestKit.ts does not state MOVED_FOLDERS as one regular expression on a line of its own"
    folders = re.compile(found.group(1))
    for rel in PACKAGE_FILES:
        assert folders.search(f"/glass-shared/src/{rel}"), f"MOVED_FOLDERS does not select {rel}"
    assert "ROOTS" in kit and "SHARED_SRC" in kit
    assert "ADMIN_CLIENTS" in kit and "plantedAdminClients" in kit, (
        "the kit does not list the admin clients or plant in them"
    )
    block = kit[kit.index("const ADMIN_STEMS") :].split("};", 1)[0]
    for folder, stems in _MOVED.items():
        assert re.search(rf"""["']?{re.escape(folder)}["']?\s*:""", block) and all(
            f'"{stem}"' in block for stem in stems
        ), f"the kit's list of admin clients leaves out {folder}"
    for walker in ("copyWords.test.ts", "copyNoClient.test.ts", "auth/resolvedPrincipal.test.ts"):
        text = (KIT.parent / walker).read_text(encoding="utf-8")
        assert "ADMIN_CLIENTS" in text and "plantedAdminClients" in text, (
            f"{walker} has no plant in the admin clients"
        )
    # The selector is a real filter: a folder none of the files are in is not selected.
    assert not folders.search("/glass-shared/src/keyboard/actionRegistry.ts")


def test_no_new_dependency_was_added_to_the_package() -> None:
    """The package's manifest names the two packages it did before and keeps its one entry (the files import none, and the
    record is re-exported from the index, so the exports map did not change)."""
    manifest = json.loads(
        (CORE / "packages" / "glass-shared" / "package.json").read_text(encoding="utf-8")
    )
    assert sorted(manifest.get("dependencies", {})) == ["graphology", "zustand"]
    assert manifest.get("exports") == {".": "./src/index.ts"}
