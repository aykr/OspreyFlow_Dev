"""The cases client splits from its browser half, and the needs-you, dataset and pack helpers join the plain code in
`packages/glass-shared` (ADR-152 decision 6, "the Conduit client"; slice PL4d3d, the ninth of the PL4 slices after A, B,
B2, B3, C, D1, D2, D3a, D3b and D3c; the owner's rulings of 20 and 21 November 2026). Nothing changes on screen.

**Two files were split, one was written out, and five moved.**

* `investigation/cases.ts` (287 lines, 23 importers) split at the page. The package keeps its own `investigation/cases.ts`:
  the types, the pack list and its labels, `scopeBadge`, `caseLabel`, `orderCases`, `datasetLabel`, `caseUrl` and the
  requests (`listDatasets`, `caseDatasets`, `setCaseDatasets`, `caseIsOpenable`, `listCases`, `createCase`, `renameCase`
  and the request half of removing a case, `removeCaseOnServer`). It holds no `window`, `document`, `sessionStorage` or
  `localStorage`. The workspace keeps `investigation/caseNavigation.ts`: `openCase` and `openCaseView` (they remember the
  case in the tab and reload the page) and `removeCase` (the package's request, then the tab forgets the case). Every
  importer takes each name from the half that holds it.
* `admin/needsYou/openings.ts` (the *Needs you* request that waits for the place that takes it) held the request in the
  tab's session storage. The package now holds the waiting, taking and listening, and where a request is kept is handed
  in (`bindOpeningsStorage`); the workspace's file of the same name binds the tab's storage and passes the five names on,
  so no importer changed.
* `ExternalOrchestration.tsx` made four requests inline. They are now `ingest/runs/externalOrchestrationApi.ts` in the
  package (the screen stays React, in the workspace, and calls them; `airflowDag` and `ORCHESTRATION_WORDS` stay in it).
* Moved whole, bytes unchanged but for the import lines: `admin/needsYou/needsYouApi.ts` (the `GET /v1/me/needs-you`
  client), `ingest/studio/datasets.ts`, `ingest/studio/packs.ts`, and `time/utcStamp.ts` (the package's `caseLabel` writes a
  moment with it, so it came along; it imports nothing).

**One name was written twice, and the index says which is which.** `caseUrl` is the case's address (this slice) and the
report clients' address of a request (D3a). Two `export *` of one name is an error in TypeScript and silently dropped in
the browser, so the index names the case's `caseOpenUrl`, and the importers that wrote `caseUrl` write
`caseOpenUrl as caseUrl`, so only their import line changed.

Which test fails if the invariant is broken (rule 12):

* a file not where it should be, an old one back, or the index leaving one out or giving a name twice:
  `test_the_files_are_where_they_should_be`, `test_the_index_exports_every_name_of_every_new_module`, with
  `test_an_index_that_drops_or_doubles_a_name_is_found`;
* a file of the package importing React, a drawing library, a package at all, or a file of the workspace or the harness:
  `test_the_new_files_import_no_react_no_package_and_no_workspace_path`, with a plant of each in each file;
* **a browser object in the package** (`window`, `document`, `sessionStorage`, `localStorage`):
  `test_the_package_files_use_no_page_or_tab_object`, with a plant of each in each of the seven, and
  `test_the_browser_half_keeps_the_tab` (the calls are where they belong);
* a whole file changed in more than its import lines at the commit that moved it:
  `test_the_move_changed_no_line_but_the_imports`; a split that adds or loses a line it should not:
  `test_the_cases_split_changed_no_line_but_the_session_wiring`, `test_the_openings_split_changed_no_line_but_the_storage_wiring`,
  with `test_a_split_that_adds_or_loses_a_line_is_found`;
* the four requests back in the screen, or lost from the module: `test_the_screen_calls_the_four_requests_it_no_longer_makes`,
  with `test_a_fetch_put_back_in_the_screen_or_lost_from_the_module_is_found`;
* a file naming an old path: `test_no_tracked_file_names_an_old_path`; an importer still reaching one, or reaching into the
  package's folder: `test_every_import_of_a_moved_module_reaches_the_package`, with
  `test_an_old_path_put_back_in_one_importer_is_found`; a browser call taken from the package instead of the browser half:
  `test_the_browser_calls_are_taken_from_the_browser_half`;
* a spec, or a file one imports, naming a file that does not exist: `test_every_import_reached_from_a_spec_resolves`;
* a gate that stops reading the files, or reads fewer: `test_each_gate_reads_no_fewer_files_than_before`, and one plant for
  each gate in a **moved** file;
* a word-walker that does not read the files: `test_the_people_name_walk_reads_each_package_file`,
  `test_the_view_word_walk_reads_each_package_file`, `test_a_place_held_by_both_roots_is_read_from_both` (keyed by root) and
  `test_the_vitest_walkers_name_the_new_folders`;
* an image `COPY` naming a moved path, or missing what the harness needs: `test_no_image_copies_a_path_that_moved`,
  `test_the_harness_image_copies_what_the_new_files_need`, each shown red by
  `test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found`.

**This file walks:** `git ls-files` over the whole repository (the old-path test); the tracked `.ts`, `.tsx`, `.mts`,
`.mjs`, `.js` and `.jsx` files under `OspreyFlow_Core/apps/` (the import tests, the browser-call test, the spec walk, which
starts at every tracked `*.spec.ts` and `*.spec.tsx` in `apps/workspace` and `apps/harness` and follows their imports) and
under `OspreyFlow_Core/packages/glass-shared/src` (the new files, the index, the package's own imports);
`apps/workspace/src` and `packages/glass-shared/src` through the two Python word-walkers it imports (each in a temporary
copy); `apps/workspace/Dockerfile` and `harness/Dockerfile` by name; `copyTextsTestKit.ts` and the three vitest walkers by
name; the git history of the rename and of the split (`git log`, `git show`); and temporary copies built inside `tmp_path`
for the plants (written there, never in the repository), among them copies of `packages/glass-shared/src`.
"""

# The planted lines below are the real call-site shapes, kept on one line as the tree wrote them (rule 15), and the
# prose beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from unittest import mock

import pytest
from tools import colour_drift_check, design_check, no_branches_check, ui_words_check
from tools.layout import CORE, ROOT

from tests import test_guide_navigation_words as navigation
from tests import test_people_section_words as people
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

#: The four files that moved whole: where each is now (relative to `SHARED`; its old place is the same relative path under
#: `apps/workspace/src/`).
WHOLE = (
    "time/utcStamp.ts",
    "admin/needsYou/needsYouApi.ts",
    "ingest/studio/datasets.ts",
    "ingest/studio/packs.ts",
)
#: The plain half of the cases client: the old file's place in the workspace is gone.
CASES = "investigation/cases.ts"
#: The browser half of it, which stays in the workspace.
NAVIGATION = "investigation/caseNavigation.ts"
#: The split file whose workspace half keeps its name (it binds the tab's storage).
OPENINGS = "admin/needsYou/openings.ts"
#: The new module of the four requests, and the screen that calls them.
ORCHESTRATION = "ingest/runs/externalOrchestrationApi.ts"
SCREEN = "ingest/runs/ExternalOrchestration.tsx"

#: The seven files of the package this slice adds.
PACKAGE_FILES = (CASES, *WHOLE, OPENINGS, ORCHESTRATION)
OLD_OF = {rel: WORKSPACE_SRC + rel for rel in (CASES, *WHOLE)}
_OLD_STEMS = {old.removesuffix(".ts") for old in OLD_OF.values()}

#: The report clients' module that also writes `caseUrl`, in two pieces: D3a's old-path walk reads this file too.
REPORT_HTTP = "reports/" + "caseHttp"

#: The names the index gives under another, because a new file wrote a name that an earlier module of the package already
#: gives: (file, the name it wrote, the name the package exports it as).
RENAMED_BY_THE_INDEX = (("investigation/cases.ts", "caseUrl", "caseOpenUrl"),)

#: The names the browser half holds: the package does not export them, and no importer takes them from it.
BROWSER_CALLS = {"openCase", "openCaseView", "removeCase"}

#: The places that may name an old path because they are a record of the past: the decision log, and the build record
#: under `process/`. They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone
#: (`test_every_named_exception_still_has_its_reason`).
NAMED = {
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_glass_shared_case_clients.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

_NAME_FORMS = (
    r"investigation/cases",
    r"time/utcStamp",
    r"admin/needsYou/needsYouApi",
    r"ingest/studio/datasets",
    r"ingest/studio/packs",
)
#: Not `cases.test.ts` or the like (the tests stayed in the workspace, beside where the file was), and not a route.
_TEXT_FORM = re.compile(
    rf"(?<!glass-shared/src/)(?<!v1/)(?<![\w-])(?:{'|'.join(_NAME_FORMS)})\b(?!\.(?:css|test\.|spec\.|py|bak))"
)
#: A bare file name with its extension, as a guide writes it: `needsYouApi.ts`.
_FILE_FORM = re.compile(r"(?<![\w/.-])(?:needsYouApi|utcStamp)\.ts\b")
#: The shorthand a record uses for the Studio's folder: `studio/datasets.ts`, `studio/packs.ts`.
_SHORT_FORM = re.compile(r"(?<![\w/.-])studio/(?:datasets|packs)\.ts\b")


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
        for form in (_TEXT_FORM, _FILE_FORM, _SHORT_FORM):
            for hit in form.finditer(text):
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
    return (
        subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}:{path}"], capture_output=True
        ).returncode
        == 0
    )


# ------------------------------------------------------------------------------------------------- the real tree: files


def test_the_files_are_where_they_should_be() -> None:
    names = earlier.tracked()
    for rel in (CASES, *WHOLE):
        new, old = SHARED + rel, OLD_OF[rel]
        assert (ROOT / new).is_file(), f"{new} is not in packages/glass-shared/src"
        assert not (ROOT / old).exists(), f"{old} is still where it was"
        assert new in names and old not in names
    # The browser half of the cases client stays in the workspace and is not in the package.
    assert (ROOT / (WORKSPACE_SRC + NAVIGATION)).is_file(), f"{NAVIGATION} is not in the workspace"
    assert WORKSPACE_SRC + NAVIGATION in names
    assert not (ROOT / (SHARED + NAVIGATION)).exists(), f"{NAVIGATION} is in the package"
    # The openings are held by both: the package's plain half and the workspace's binding.
    for place in (SHARED + OPENINGS, WORKSPACE_SRC + OPENINGS):
        assert (ROOT / place).is_file() and place in names, f"{place} is missing"
    # The new module is the package's; the screen stays React in the workspace and is not in the package.
    assert (ROOT / (SHARED + ORCHESTRATION)).is_file() and SHARED + ORCHESTRATION in names
    assert (ROOT / (WORKSPACE_SRC + SCREEN)).is_file()
    assert not (ROOT / (SHARED + SCREEN)).exists(), "the React screen is in the package"
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    for rel in PACKAGE_FILES:
        stem = "./" + rel.removesuffix(".ts")
        assert re.search(
            rf"""^export\s+(?:type\s+)?(?:\*|\{{[^}}]*\}})\s+from\s+["']{re.escape(stem)}["'];""",
            index,
            re.M,
        ), f"packages/glass-shared/src/index.ts does not export {stem}"


def _modules_of(index: str, root: Path = SHARED_SRC) -> dict[str, str]:
    """Every module the index names (these seven and the earlier slices'), keyed by its place under `src`."""
    named = {f"{m.removeprefix('./')}.ts" for m in link._STAR.findall(index)}
    named |= {f"{m.removeprefix('./')}.ts" for _, m in link._BRACED.findall(index)}
    named |= set(PACKAGE_FILES)
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in sorted(named)}


def index_problems(
    index: str, sources: dict[str, str], required: Iterable[str] | None = None
) -> list[str]:
    """D3c's check of an index (a file it does not export, a name no export carries, a name two modules give), with this
    slice's one rename added to the ones it already knows."""
    with mock.patch.object(
        plain, "RENAMED_BY_THE_INDEX", plain.RENAMED_BY_THE_INDEX + RENAMED_BY_THE_INDEX
    ):
        return plain.index_problems(index, sources, required)


def test_the_index_exports_every_name_of_every_new_module() -> None:
    """Every name of the seven files is exported, by its own name or the one the index renames it to, and no name is given
    by two modules at once (they are read beside every other module the index names, so a clash with an earlier slice's
    client is found too: `caseUrl` is the report clients')."""
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    assert index_problems(index, _modules_of(index), PACKAGE_FILES) == []


def test_an_index_that_drops_or_doubles_a_name_is_found() -> None:
    """Red for the check above (rule 15), on the shapes the move could leave: the index as it should be, clean; the rename
    lost (the case's address given twice); a name left out of a braced export; the cases file starred beside the report
    clients' (the real clash); a file left out."""
    sources = {
        REPORT_HTTP
        + ".ts": "export function caseUrl(api: number, path: string): string { return path; }\n",
        "investigation/cases.ts": "export function caseUrl(id: string): string { return id; }\nexport const POLE_LABEL = 1;\n",
    }
    index = (
        f'export * from "./{REPORT_HTTP}";\n'
        'export { caseUrl as caseOpenUrl, POLE_LABEL } from "./investigation/cases";\n'
    )
    assert index_problems(index, sources) == []
    assert any(
        "two modules, one name" in p
        for p in index_problems(index.replace("caseUrl as caseOpenUrl", "caseUrl"), sources)
    )
    assert any(
        "POLE_LABEL" in p for p in index_problems(index.replace(", POLE_LABEL", ""), sources)
    )
    starred = f'export * from "./{REPORT_HTTP}";\nexport * from "./investigation/cases";\n'
    assert any("two modules, one name" in p for p in index_problems(starred, sources))
    assert any(
        "not exported" in p for p in index_problems(f'export * from "./{REPORT_HTTP}";\n', sources)
    )
    assert any(
        "caseOpenUrl" in p
        for p in index_problems(index.replace("caseUrl as caseOpenUrl, ", ""), sources)
    )


# ----------------------------------------------------------------------------------- React, workspace, packages: never


def test_the_new_files_import_no_react_no_package_and_no_workspace_path() -> None:
    """The D2 file's check reads every file of the package, these seven too; here they are shown to be among them, and a
    bare package (anything that is not a relative path or the generated schemas) is refused as well: no new dependency."""
    sources = clients._package_sources()
    for rel in PACKAGE_FILES:
        assert SHARED + rel in sources, f"{rel} is not among the package's sources"
    problems = [
        p for rel in PACKAGE_FILES for p in clients.package_import_problems(ROOT, SHARED + rel)
    ]
    assert problems == [], f"{len(problems)} import(s) the package may not make: {problems[:10]}"
    bare = {rel: _bare_imports(_text(SHARED + rel)) for rel in PACKAGE_FILES}
    assert {rel: found for rel, found in bare.items() if found} == {}, (
        "a new file imports a package"
    )


def _bare_imports(text: str) -> list[str]:
    return [spec for spec in earlier._IMPORT_SPEC.findall(text) if not spec.startswith(".")]


def test_a_react_workspace_or_package_import_in_a_new_file_is_found(package_copy: Path) -> None:
    """Red for the check above (rule 15): in each of the seven, the lines the file would carry if it grew a hook, a path into
    the workspace (among them the way the workspace wrote a schema import, which is not the package's way), or a new
    dependency. Each file is clean first, so the plant is what is found."""
    plants = (
        'import { useEffect } from "react";\n',
        'import { rememberCaseView } from "../views/lensHandoff";\n',
        'import { INVESTIGATION_ID_SESSION_KEY } from "../../../../apps/workspace/src/investigation/investigationId";\n',
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

#: What the package may not touch, in any file of the seven (a comment naming one is refused too: the rule is read
#: plainly, and the prose is written around it).
_PAGE_OBJECT = re.compile(r"\b(window|document|sessionStorage|localStorage)\b")


def page_objects(text: str) -> list[str]:
    return sorted({m.group(1) for m in _PAGE_OBJECT.finditer(text)})


def test_the_package_files_use_no_page_or_tab_object() -> None:
    found = {rel: page_objects(_text(SHARED + rel)) for rel in PACKAGE_FILES}
    assert {rel: names for rel, names in found.items() if names} == {}, (
        "a package file touches the page or the tab"
    )


def test_a_page_or_tab_object_in_a_package_file_is_found(package_copy: Path) -> None:
    """Red for the check above (rule 15): in each of the seven, a use of each of the four, in the shape the browser half
    wrote them (`sessionStorage.setItem`, `window.location.assign`), clean first. `cases.ts` with `sessionStorage` in it is
    the case the brief names."""
    plants = {
        "sessionStorage": '\nexport const kept = sessionStorage.getItem("osprey.case");\n',
        "window": "\nexport const go = (url: string) => window.location.assign(url);\n",
        "document": "\nexport const title = document.title;\n",
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


def test_the_browser_half_keeps_the_tab() -> None:
    """The calls the package may not make are made where they belong: the workspace's `caseNavigation.ts` exports the three
    browser names, uses the tab and the page, and takes the rest from the package by its name; the package's `cases.ts`
    exports none of the three (it exports the request half of removing a case under another name), and the workspace's
    `openings.ts` binds the tab's own storage."""
    nav = _text(WORKSPACE_SRC + NAVIGATION)
    assert link._exported_names(nav) == BROWSER_CALLS
    assert "sessionStorage" in nav and "window.location.assign" in nav
    assert re.search(rf"""from\s+["']{re.escape(PACKAGE_NAME)}["']""", nav), (
        "it does not take the plain half from the package"
    )
    assert not re.search(r"""from\s+["']\./cases["']""", nav)
    names = link._exported_names(_text(SHARED + CASES))
    assert BROWSER_CALLS & names == set(), f"the package exports {sorted(BROWSER_CALLS & names)}"
    assert "removeCaseOnServer" in names
    binding = _text(WORKSPACE_SRC + OPENINGS)
    assert "sessionStorage" in binding and "bindOpeningsStorage(" in binding
    plain_half = _text(SHARED + OPENINGS)
    assert {
        "bindOpeningsStorage",
        "requestOpening",
        "peekOpening",
        "takeOpening",
        "onOpening",
    } <= link._exported_names(plain_half)
    for name in ("onOpening", "peekOpening", "requestOpening", "takeOpening"):
        assert re.search(rf"\b{name}\b", binding), f"the binding does not pass {name} on"


# ------------------------------------------------------------------------------------------ how a move is compared

#: The code lines (comments, blank lines, import statements and lines of only brackets are not code lines here) the cases
#: split adds and loses, and nothing else: `removeCase` is the package's request and the workspace's wrapper that forgets
#: the case in the tab, so the signature is written in both and the request is called by its new name. No line is lost: the
#: session-clearing lines are the workspace's now.
CASES_ADDED = Counter(
    {
        "export async function removeCaseOnServer(": 1,
        "apiBaseUrl: string,": 1,
        "bearerToken: string,": 1,
        "id: string,": 1,
        "): Promise<void> {": 1,
        "await removeCaseOnServer(apiBaseUrl, bearerToken, id);": 1,
    }
)
#: The openings split: the three calls on the browser's storage are now on a storage handed in (looked up at each use, as the
#: browser's global was), the interface it must have and the call that hands it in are new, and the workspace's file passes
#: the package's names on and binds the tab's.
OPENINGS_ADDED = Counter(
    {
        "export interface OpeningsStorage {": 1,
        "getItem(key: string): string | null;": 1,
        "setItem(key: string, value: string): void;": 1,
        "removeItem(key: string): void;": 1,
        "let storage: () => OpeningsStorage | null = () => null;": 1,
        "const raw = storage()?.getItem(KEY);": 1,
        "if (openings.length === 0) storage()?.removeItem(KEY);": 1,
        "else storage()?.setItem(KEY, JSON.stringify(openings));": 1,
        "export function bindOpeningsStorage(open: () => OpeningsStorage | null): void {": 1,
        "storage = open;": 1,
        "waiting = stored();": 1,
        'export { onOpening, peekOpening, requestOpening, takeOpening, type Opening } from "@ospreyflow/glass-shared";': 1,
        "bindOpeningsStorage(() => sessionStorage);": 1,
    }
)
OPENINGS_LOST = Counter(
    {
        "const raw = sessionStorage.getItem(KEY);": 1,
        "if (openings.length === 0) sessionStorage.removeItem(KEY);": 1,
        "else sessionStorage.setItem(KEY, JSON.stringify(openings));": 1,
    }
)
#: The lines the screen lost to the module and nothing else: the helper that made the address and the one that said a
#: refusal, the shared header, and each request's own lines. What the module gained is read by its own test.
SCREEN_LOST = Counter(
    {
        "const url = recipeUrl(apiBaseUrl, investigationId, pipeline.recipe_id);": 2,
        ".then(async (r) => {": 2,
        "function recipeUrl(apiBaseUrl: string, investigationId: string, recipeId: string): string {": 1,
        "const headers = { Authorization: `Bearer ${bearerToken}` };": 1,
        "fetch(`${url}/quota`, { headers: { Authorization: `Bearer ${bearerToken}` } })": 1,
        ".then((r) => (r.ok ? (r.json() as Promise<RunQuotaUse>) : null))": 1,
        "fetch(`${url}/owned-externally`, { headers: { Authorization: `Bearer ${bearerToken}` } })": 1,
        ".then((r) => (r.ok ? (r.json() as Promise<ExternallyOwnedInput | null>) : null))": 1,
        "fetch(`${url}/owned-externally`, {": 1,
        'headers: { ...headers, "Content-Type": "application/json" },': 1,
        "body: JSON.stringify({ client_id: client.trim() }),": 1,
        "})": 1,
        "setOwned((await r.json()) as ExternallyOwnedInput);": 1,
        'fetch(`${url}/owned-externally`, { method: "DELETE", headers })': 1,
    }
)


def test_the_move_changed_no_line_but_the_imports() -> None:
    """Each whole file is read as the commit that renamed it left it against the commit before: git's own detection finds
    the rename, and the two sides are compared there, never against the working tree (a later edit would be read as the
    move's). A shallow clone has no history to read: skipped, as the earlier move tests in this folder are."""
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


def test_a_moved_file_changed_in_more_than_its_imports_is_found() -> None:
    """Red for the comparison above: the real client's schema import moved (the package's way of writing it), once alone and
    once with a line of the code changed."""
    was = 'import type { NeedsYou } from "../../../../../packages/schemas/generated";\n\nexport type { NeedsYou };\nexport const CAP = 7;\n'
    moved = was.replace(
        "../../../../../packages/schemas/generated", "../../../../schemas/generated"
    )
    assert earlier.only_import_lines_changed(was, moved) == []
    assert earlier.only_import_lines_changed(was, moved.replace("7", "8")) != []


def _split_at(
    added_in: str, old: str, package: str, workspace: str
) -> tuple[Counter[str], Counter[str]]:
    """The split's code lines against the old file's, read at the commit that added the half named `added_in` (a file
    that did not exist before it)."""
    commit = earlier._git("log", "--diff-filter=A", "--format=%H", "-1", "--", added_in).strip()
    assert commit, f"git finds no commit that added {added_in}"
    assert _exists_at(f"{commit}^", old), f"{old} is not in the commit before the split"
    return earlier.split_differences(
        earlier._git("show", f"{commit}^:{old}"),
        earlier._git("show", f"{commit}:{package}"),
        earlier._git("show", f"{commit}:{workspace}"),
    )


def test_the_cases_split_changed_no_line_but_the_session_wiring() -> None:
    """`investigation/cases.ts` in the commit before the split, against the two halves in the commit that wrote the browser
    half: between them they hold every code line the old file did, and only the lines `CASES_ADDED` writes out beyond them.
    `openCase` and `openCaseView` moved line for line; so did the session-clearing lines of `removeCase`."""
    earlier._skip_if_shallow()
    added, lost = _split_at(
        WORKSPACE_SRC + NAVIGATION,
        OLD_OF[CASES],
        SHARED + CASES,
        WORKSPACE_SRC + NAVIGATION,
    )
    assert added == CASES_ADDED, f"lines the split added: {dict(added)}"
    assert lost == Counter(), f"lines the split lost: {dict(lost)}"
    commit = earlier._git(
        "log", "--diff-filter=A", "--format=%H", "-1", "--", WORKSPACE_SRC + NAVIGATION
    ).strip()
    assert not _exists_at(commit, OLD_OF[CASES]), (
        "the workspace still holds cases.ts after the split"
    )


def test_the_openings_split_changed_no_line_but_the_storage_wiring() -> None:
    """The same for `admin/needsYou/openings.ts`: at the commit that added the package's half, against the old file in the
    commit before it."""
    earlier._skip_if_shallow()
    added, lost = _split_at(
        SHARED + OPENINGS, WORKSPACE_SRC + OPENINGS, SHARED + OPENINGS, WORKSPACE_SRC + OPENINGS
    )
    assert added == OPENINGS_ADDED, f"lines the split added: {dict(added)}"
    assert lost == OPENINGS_LOST, f"lines the split lost: {dict(lost)}"


def test_a_split_that_adds_or_loses_a_line_is_found() -> None:
    """Red for the comparisons above, at the real call-site shape: the old `openings.ts` storage lines, split cleanly
    (the three calls moved to a handed-in storage: those are the allowed lines), then with a line added to one half, a line
    lost, and the session-clearing kept in both halves of the cases split."""
    old = (
        "export function store(openings: number[]): void {\n  try {\n"
        "    if (openings.length === 0) sessionStorage.removeItem(KEY);\n  } catch {\n    // none\n  }\n}\n"
    )
    package = (
        "export function store(openings: number[]): void {\n  try {\n"
        "    if (openings.length === 0) storage()?.removeItem(KEY);\n  } catch {\n    // none\n  }\n}\n"
    )
    workspace = "bindOpeningsStorage(() => sessionStorage);\n"
    added, lost = earlier.split_differences(old, package, workspace)
    assert added == Counter(
        {
            "if (openings.length === 0) storage()?.removeItem(KEY);": 1,
            "bindOpeningsStorage(() => sessionStorage);": 1,
        }
    )
    assert lost == Counter({"if (openings.length === 0) sessionStorage.removeItem(KEY);": 1})
    more, _ = earlier.split_differences(old, package + "export const CAP = 7;\n", workspace)
    assert more - added == Counter({"export const CAP = 7;": 1})
    _, gone = earlier.split_differences(old, package.replace("  } catch {\n", ""), workspace)
    assert gone - lost == Counter({"} catch {": 1})
    kept = "try {\n  sessionStorage.removeItem(KEY);\n} catch {\n  // none\n}\n"
    both, _ = earlier.split_differences(kept, kept, kept)
    assert both == Counter(
        {"try {": 1, "sessionStorage.removeItem(KEY);": 1, "} catch {": 1}
    )  # the same lines in both halves: kept twice, and found


# -------------------------------------------------------------------------------- the four requests of the screen


_FETCH = re.compile(r"\bfetch\(")


def test_the_screen_calls_the_four_requests_it_no_longer_makes() -> None:
    """The screen holds no `fetch` and no address; the package's module holds the four (a quota read, an owner read, a PUT
    and a DELETE), the refusal words each says in, and the address helper. The screen calls the four by name, from the
    package, and keeps `airflowDag` and `ORCHESTRATION_WORDS` (which its own test imports)."""
    screen = _text(WORKSPACE_SRC + SCREEN)
    module = _text(SHARED + ORCHESTRATION)
    assert not _FETCH.search(screen), "the screen still makes a request itself"
    assert (
        "/owned-externally" not in screen and "/quota" not in screen and "recipeUrl" not in screen
    )
    assert len(_FETCH.findall(module)) == 4, "the module does not make exactly four requests"
    assert "/quota" in module and module.count("/owned-externally") == 3
    assert 'method: "PUT"' in module and 'method: "DELETE"' in module
    assert '"Marking it owned externally"' in module and '"Taking it back"' in module
    assert "Authorization: `Bearer ${bearerToken}`" in module
    assert {
        "readQuota",
        "readOwnedExternally",
        "markOwnedExternally",
        "clearOwnedExternally",
        "recipeUrl",
    } <= link._exported_names(module)
    assert page_objects(module) == []
    for name in ("readQuota", "readOwnedExternally", "markOwnedExternally", "clearOwnedExternally"):
        assert re.search(rf"\b{name}\(", screen), f"the screen does not call {name}"
    imported = re.search(
        rf"""import\s*(\{{[^}}]*\}})\s*from\s*["']{re.escape(PACKAGE_NAME)}["']""", screen
    )
    assert imported and {
        "readQuota",
        "readOwnedExternally",
        "markOwnedExternally",
        "clearOwnedExternally",
    } <= earlier._names(imported.group(1))
    assert {"airflowDag", "ORCHESTRATION_WORDS", "ExternalOrchestration"} <= link._exported_names(
        screen
    )


def test_the_screen_lost_no_line_but_the_four_requests() -> None:
    """The screen at the commit before the module was written, against the screen and the module after it: no code line of
    the old screen is lost but the ones `SCREEN_LOST` writes out (the helper that made the address, the refusal helper and
    each request's own lines)."""
    earlier._skip_if_shallow()
    _, lost = _split_at(
        SHARED + ORCHESTRATION,
        WORKSPACE_SRC + SCREEN,
        SHARED + ORCHESTRATION,
        WORKSPACE_SRC + SCREEN,
    )
    assert lost == SCREEN_LOST, f"lines the split lost: {dict(lost)}"


def test_a_fetch_put_back_in_the_screen_or_lost_from_the_module_is_found() -> None:
    """Red for the checks above, on the shapes the file really held: the screen's old `fetch` of the quota put back, and a
    module that has lost a request."""
    screen = "  readQuota(apiBaseUrl, bearerToken, investigationId, id).then(setQuota);\n"
    assert not _FETCH.search(screen)
    assert _FETCH.search(
        screen
        + "    fetch(`${url}/quota`, { headers: { Authorization: `Bearer ${bearerToken}` } })\n"
    )
    module = (
        "fetch(`${url}/quota`, {});\nfetch(`${url}/owned-externally`, {});\n"
        'fetch(`${url}/owned-externally`, { method: "PUT" });\nfetch(`${url}/owned-externally`, { method: "DELETE" });\n'
    )
    assert len(_FETCH.findall(module)) == 4
    assert (
        len(
            _FETCH.findall(
                module.replace('fetch(`${url}/owned-externally`, { method: "DELETE" });\n', "")
            )
        )
        == 3
    )


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


def test_every_named_exception_still_has_its_reason() -> None:
    """An exception outlives its reason when the file it excuses no longer names an old path: left in `NAMED` it keeps that
    file outside the walk, and an old path could be written back into it unseen (rule 12)."""
    stale = [rel for rel in NAMED if not old_path_mentions(ROOT, [rel])]
    assert stale == [], (
        f"{stale} no longer name an old path: remove them from NAMED, and the walk will cover them"
    )


# ----------------------------------------------------------------------------------------------------- the imports


def _package_names(root: Path) -> set[str]:
    """Every name the seven files export, read from the package's copies (the old ones are gone), and the one the index
    gives the case's address."""
    names = {new for _, _, new in RENAMED_BY_THE_INDEX}
    for rel in PACKAGE_FILES:
        try:
            names |= link._exported_names((root / (SHARED + rel)).read_text(encoding="utf-8"))
        except OSError:
            continue
    return names


def imports_not_reaching(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The relative specifiers that resolve to an old path, or into the package's folder instead of its name; and the number
    of files that import a name of the seven from the package. Resolution is by path alone: an old file need not exist."""
    bad: list[str] = []
    importers = 0
    names = _package_names(root)
    for rel in rels:
        if Path(rel).suffix not in earlier._SOURCE_SUFFIXES or not rel.startswith(
            "OspreyFlow_Core/"
        ):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for hit in link._PACKAGE_IMPORT.finditer(text):
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


def test_every_import_of_a_moved_module_reaches_the_package() -> None:
    bad, importers = imports_not_reaching(ROOT, earlier.tracked())
    assert importers >= 40, (
        f"only {importers} file(s) under OspreyFlow_Core import a name of the seven from {PACKAGE_NAME}: the walk found too few imports, or the importers were not repointed"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach the package by its name: {bad[:10]}"


_IMPORT_CLAUSE = re.compile(
    r"""(?:^|\n)\s*import\s+(?:type\s+)?(\{[^}]*\})\s*from\s*["']([^"']+)["']""", re.S
)


def browser_call_imports(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The imports that take `openCase`, `openCaseView` or `removeCase` from anywhere but the browser half, and the number
    of files that take one from it."""
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
            if spec.endswith("/caseNavigation"):
                taken = True
            else:
                bad.append(f"{rel}: {sorted(wanted)} from {spec}")
        takers += taken
    return bad, takers


def test_the_browser_calls_are_taken_from_the_browser_half() -> None:
    bad, takers = browser_call_imports(ROOT, earlier.tracked())
    assert takers >= 4, (
        f"only {takers} file(s) take a browser call from caseNavigation: the walk found too few"
    )
    assert bad == [], f"{len(bad)} import(s) take a browser call from elsewhere: {bad[:10]}"


def test_a_browser_call_taken_from_the_package_is_found(tmp_path: Path) -> None:
    """Red for the check above (rule 15), on the lines the tree holds: the app's, the picker's and the harness's, written to
    take the call from the package or from the old file."""
    cases = {
        APPS + "workspace/src/App.tsx": (
            'import { openCase, openCaseView } from "./investigation/caseNavigation";',
            f'import {{ openCase, openCaseView }} from "{PACKAGE_NAME}";',
        ),
        APPS + "workspace/src/investigation/CasePicker.tsx": (
            'import { removeCase } from "./caseNavigation";',
            'import { removeCase } from "./cases";',
        ),
        APPS + "workspace/keyboard/places-harness.tsx": (
            'import { openCase } from "../src/investigation/caseNavigation";',
            'import { openCase } from "../src/investigation/cases";',
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
    "the app's case calls, in one import (the browser half and the package's apart)": (
        WORKSPACE_SRC + "App.tsx",
        'import { caseIsOpenable, listCases, openCase, openCaseView } from "./investigation/cases";',
        f'import {{ caseIsOpenable, listCases }} from "{PACKAGE_NAME}";\nimport {{ openCase, openCaseView }} from "./investigation/caseNavigation";',
    ),
    "the keyboard harness's open call (a path outside src)": (
        APPS + "workspace/keyboard/places-harness.tsx",
        'import { openCase } from "../src/investigation/cases";',
        'import { openCase } from "../src/investigation/caseNavigation";',
    ),
    "the case list's calls, beside them (a sibling named cases)": (
        WORKSPACE_SRC + "investigation/CaseList.tsx",
        'import { type CaseListing, caseLabel, listCases, orderCases } from "./cases";',
        f'import {{ type CaseListing, caseLabel, listCases, orderCases }} from "{PACKAGE_NAME}";',
    ),
    "the rules place's case list, from a parent folder": (
        WORKSPACE_SRC + "alerts/RulesPlace.tsx",
        'import { listCases, type AccessLevel } from "../investigation/cases";',
        f'import {{ listCases, type AccessLevel }} from "{PACKAGE_NAME}";',
    ),
    "the case picker's removal, with the calls beside it": (
        WORKSPACE_SRC + "investigation/CasePicker.tsx",
        'import { type CaseListing, caseLabel, datasetLabel, listCases, orderCases, removeCase } from "./cases";',
        f'import {{ type CaseListing, caseLabel, datasetLabel, listCases, orderCases }} from "{PACKAGE_NAME}";\nimport {{ removeCase }} from "./caseNavigation";',
    ),
    "the case address, from the reports' journey": (
        WORKSPACE_SRC + "reports/journey.ts",
        'import { caseUrl } from "../investigation/cases";',
        f'import {{ caseOpenUrl as caseUrl }} from "{PACKAGE_NAME}";',
    ),
    "the moment's words, from the reports view": (
        WORKSPACE_SRC + "reports/ReportsView.tsx",
        'import { utcStampOf } from "../time/utcStamp";',
        f'import {{ utcStampOf }} from "{PACKAGE_NAME}";',
    ),
    "the moment's words, in its own test (a sibling)": (
        WORKSPACE_SRC + "time/utcStamp.test.ts",
        'import { utcStamp, utcStampOf } from "./utcStamp";',
        f'import {{ utcStamp, utcStampOf }} from "{PACKAGE_NAME}";',
    ),
    "the needs-you client, the last line of a many-line import": (
        WORKSPACE_SRC + "admin/needsYou/NeedsYou.tsx",
        '} from "./needsYouApi";',
        f'}} from "{PACKAGE_NAME}";',
    ),
    "the needs-you client's type, from the home page (a parent folder)": (
        WORKSPACE_SRC + "home/answersFor.ts",
        'import type { NeedsYou } from "../admin/needsYou/needsYouApi";',
        f'import type {{ NeedsYou }} from "{PACKAGE_NAME}";',
    ),
    "the needs-you client, loaded by a test as it is needed": (
        WORKSPACE_SRC + "admin/needsYou/NeedsYou.test.tsx",
        '    const { readNeedsYou } = await import("./needsYouApi");',
        f'    const {{ readNeedsYou }} = await import("{PACKAGE_NAME}");',
    ),
    "the cases, loaded by their test as they are needed": (
        WORKSPACE_SRC + "investigation/cases.test.ts",
        '    const { datasetLabel } = await import("./cases");',
        f'    const {{ datasetLabel }} = await import("{PACKAGE_NAME}");',
    ),
    "the studio's datasets, from the Studio (a child folder)": (
        WORKSPACE_SRC + "ingest/IngestStudio.tsx",
        'import { caseForDataset, currentDataset, studioDatasets } from "./studio/datasets";',
        f'import {{ caseForDataset, currentDataset, studioDatasets }} from "{PACKAGE_NAME}";',
    ),
    "the studio's datasets, in their own test (a sibling)": (
        WORKSPACE_SRC + "ingest/studio/datasets.test.ts",
        'import { caseForDataset, currentDataset, studioDatasets } from "./datasets";',
        f'import {{ caseForDataset, currentDataset, studioDatasets }} from "{PACKAGE_NAME}";',
    ),
    "the studio's model in words, beside it (a sibling named packs)": (
        WORKSPACE_SRC + "ingest/studio/ModelTab.tsx",
        'import { modelInWords } from "./packs";',
        f'import {{ modelInWords }} from "{PACKAGE_NAME}";',
    ),
    "a deep import into the package": (
        WORKSPACE_SRC + "alerts/RulesPlace.tsx",
        'import { listCases } from "../../../../packages/glass-shared/src/investigation/cases";',
        f'import {{ listCases }} from "{PACKAGE_NAME}";',
    ),
    "an old path in a comment of the workspace (the open call)": (
        WORKSPACE_SRC + "alerts/address.ts",
        "// that case on the alert. Switching case reloads the page (`investigation/cases.ts`'s `openCase`),",
        "// that case on the alert. Switching case reloads the page (`investigation/caseNavigation.ts`'s `openCase`),",
    ),
    "a bare file name in a record": (
        "OspreyFlow_Core/apps/pages/FUNCTIONS.yaml",
        'where: "apps/workspace/src/ingest/studio/ModelTab.tsx (20, a placeholder), studio/packs.ts"',
        'where: "apps/workspace/src/ingest/studio/ModelTab.tsx (20, a placeholder), packages/glass-shared/src/ingest/studio/packs.ts"',
    ),
    "the studio's shorthand in the specification": (
        "OspreyFlow_Build/spec/09_INGEST_STUDIO.md",
        "higher level first (`studio/datasets.ts`). A dataset a case only reads is not offered",
        "higher level first (`packages/glass-shared/src/ingest/studio/datasets.ts`). A dataset a case only reads is not offered",
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
        "listCases",
        "caseOpenUrl",
        "readNeedsYou",
        "utcStamp",
        "modelInWords",
        "bindOpeningsStorage",
    ):
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
    """Red for the walk above, at the shapes the move could leave: the places harness still importing the open call by the old
    path, and the index exporting a file that is not there."""
    spec = APPS + "workspace/keyboard/places.spec.ts"
    harness = APPS + "workspace/keyboard/places-harness.tsx"
    files = {
        spec: 'import { mount } from "./places-harness";\n',
        harness: (
            'import { openCase } from "../src/investigation/caseNavigation";\n'
            f'import {{ listCases }} from "{PACKAGE_NAME}";\n'
        ),
        WORKSPACE_SRC + "investigation/caseNavigation.ts": "export const openCase = 1;\n",
        SHARED + "index.ts": 'export * from "./time/utcStamp";\n',
        SHARED + "time/utcStamp.ts": "export const MONTHS = [];\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == []
    clean = (tmp_path / harness).read_text(encoding="utf-8")
    (tmp_path / harness).write_text(clean.replace("caseNavigation", "cases"), encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [
        f"{harness}: ../src/investigation/cases"
    ]
    (tmp_path / harness).write_text(clean, encoding="utf-8")
    (tmp_path / SHARED / "time" / "utcStamp.ts").unlink()
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [
        f"{SHARED}index.ts: ./time/utcStamp"
    ]


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
    every `COPY` of a workspace path still names something that exists and is reached. The walk reaches the seven."""
    reached = image._reached_workspace_files()
    copied = image._copied_paths()
    assert image._missing(copied, reached) == []
    assert earlier.dangling(copied, reached) == []
    names = {str(p.relative_to(CORE.resolve())) for p in reached}
    for rel in PACKAGE_FILES:
        assert f"packages/glass-shared/src/{rel}" in names, (
            f"the walk does not reach the package's {rel}"
        )


def test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found() -> None:
    """Red for the checks above (rule 15), on the real stages: the package's line taken out of the harness image (the files
    the index reaches are missing), a line a moved file once needed put in (it copies a file that is not there), and the
    same two faults on the workspace image."""
    real = image.DOCKERFILE.read_text(encoding="utf-8")
    reached = image._reached_workspace_files()
    assert stale_copies(real) == []
    assert image._missing(image._copied_paths(real), reached) == []

    shared = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    assert shared in real
    missing = image._missing(image._copied_paths(real.replace(shared, "", 1)), reached)
    for rel in PACKAGE_FILES:
        assert f"packages/glass-shared/src/{rel}" in missing, f"{rel} is not found missing"

    for rel in ("investigation/cases.ts", "time/utcStamp.ts", "ingest/studio/packs.ts"):
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
    assert stale_copies(
        workspace + "COPY apps/workspace/src/admin/needsYou/needsYouApi.ts ./x\n"
    ) == ["apps/workspace/src/admin/needsYou/needsYouApi.ts"]


# --------------------------------------------------------------------------------------------------- the four gates

#: The files each gate read on main before this slice: the number each reported or, where it reports none, the files its own
#: rules select (measured on 21 November 2026, on the tip PL4d3d started from, after PL4d3c). The files moved from a folder
#: each gate reads to another it reads, and two files were added, so the numbers do not fall: none may.
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
        shared_copy,
        "ingest/studio/datasets.ts",
        '\nexport const STRIPE = { background: "#12ab34", padding: 8 };\n',
    )
    assert colour_drift_check.main() == 1
    assert "packages/glass-shared/src/ingest/studio/datasets.ts:" in capsys.readouterr().out


def test_the_design_detector_reports_a_plant_in_a_new_file(
    shared_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(design_check, "SCANNED", [shared_copy])
    assert design_check.unexcused(design_check.detect(design_check.SCANNED)) == [], (
        "the clean copy already has findings"
    )
    earlier._append(
        shared_copy,
        "admin/needsYou/needsYouApi.ts",
        "\nexport const TOAST_STYLE = {\n"
        '  background: "var(--surface-raised)", borderLeft: "3px solid var(--error)", borderRadius: "8px",\n'
        '  padding: "12px 16px", boxShadow: "var(--overlay-shadow)",\n'
        "};\n",
    )
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [
        ("needsYouApi.ts", "side-tab")
    ]
    assert "needsYou" in found[0]["file"]


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
    earlier._append(
        shared_copy, "investigation/cases.ts", '\nexport const LABEL = "Target model";\n'
    )
    assert ui_words_check.main() == 1
    assert "packages/glass-shared/src/investigation/cases.ts:" in capsys.readouterr().out


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
    earlier._append(
        shared_copy,
        "ingest/runs/externalOrchestrationApi.ts",
        '\nexport const BRANCH_CASE = "branch-by-filter";\n',
    )
    assert no_branches_check.main() == 1
    assert f"{top}/ingest/runs/externalOrchestrationApi.ts:" in capsys.readouterr().out


# -------------------------------------------------------------------------------------------------- the word-walkers

#: The seven as (folder, stem) pairs, never written as a path (the old-path scan reads the other walkers' tables too).
_MOVED = {
    "investigation": ("cases",),
    "time": ("utcStamp",),
    "admin/needsYou": ("needsYouApi", "openings"),
    "ingest/studio": ("datasets", "packs"),
    "ingest/runs": ("externalOrchestrationApi",),
}
MOVED_FILES = tuple(f"{folder}/{stem}.ts" for folder, stems in _MOVED.items() for stem in stems)


def test_the_moved_table_is_the_list_of_seven() -> None:
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
    copy.write_text(
        real + '\nexport const planted = "Set it in Admin › People.";\n', encoding="utf-8"
    )
    assert found() == [real.count("\n") + 2]


@pytest.mark.parametrize("client", MOVED_FILES)
def test_the_view_word_walk_reads_each_package_file(client: str, tmp_path: Path) -> None:
    """The same for the walk behind `test_guide_navigation_words.py`: read at its place in the package, clean finds nothing,
    an old view word on screen is found, and in a comment (which a person never sees) it is not."""
    sources = navigation.glass_sources()
    assert client in sources, client
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
    """The two files that stayed in the workspace are read by the walkers through the workspace's own root."""
    read = {p.relative_to(CORE).as_posix() for p in people._glass_files()}
    sources = navigation.glass_sources()
    for rel in (NAVIGATION, OPENINGS):
        assert f"apps/workspace/src/{rel}" in read, rel
    assert NAVIGATION in sources and OPENINGS in sources
    assert f"shared:{OPENINGS}" in sources, (
        "the package's half of the openings is not read under its root"
    )


@pytest.mark.parametrize("planted_in", [0, 1])
def test_a_place_held_by_both_roots_is_read_from_both(planted_in: int, tmp_path: Path) -> None:
    """Keyed by root (D2's last finding): a place that two roots both hold is kept under both. The openings are held by the
    workspace (its binding) and by the package (its plain half) at once: an old word in either is found, the second root's
    under `shared:`."""
    roots = (tmp_path / f"a{planted_in}", tmp_path / f"b{planted_in}")
    for n, root in enumerate(roots):
        (root / "admin" / "needsYou").mkdir(parents=True)
        (root / "admin" / "needsYou" / "openings.ts").write_text(
            'export const word = "Clear view";\n'
            if n == planted_in
            else "export const word = 1;\n",
            encoding="utf-8",
        )
    expected = (
        "admin/needsYou/openings.ts" if planted_in == 0 else "shared:admin/needsYou/openings.ts"
    )
    assert navigation.old_view_words_on_screen(navigation.glass_sources(roots)) == [
        f"{expected}: 'Clear view'"
    ]


KIT = CORE / "apps" / "workspace" / "src" / "copyTextsTestKit.ts"
_KIT_FOLDERS = re.compile(r"^export const MOVED_FOLDERS = /(.*)/;$", re.M)


def test_the_vitest_walkers_name_the_new_folders() -> None:
    """`copyWords`, `copyNoClient` and `resolvedPrincipal` walk the kit's two roots, and each has a case that plants in a copy
    of every file the kit lists as a case client. The kit selects the package's folders by `MOVED_FOLDERS`: every folder of
    the seven is among them (the vitest cases themselves run under `npm test --workspace apps/workspace`)."""
    kit = KIT.read_text(encoding="utf-8")
    found = _KIT_FOLDERS.search(kit)
    assert found, (
        "copyTextsTestKit.ts does not state MOVED_FOLDERS as one regular expression on a line of its own"
    )
    folders = re.compile(found.group(1))
    for rel in PACKAGE_FILES:
        assert folders.search(f"/glass-shared/src/{rel}"), f"MOVED_FOLDERS does not select {rel}"
    assert "ROOTS" in kit and "SHARED_SRC" in kit
    assert "CASE_CLIENTS" in kit and "plantedCaseClients" in kit, (
        "the kit does not list the case clients or plant in them"
    )
    block = kit[kit.index("const CASE_STEMS") :].split("};", 1)[0]
    for folder, stems in _MOVED.items():
        assert re.search(rf"""["']?{re.escape(folder)}["']?\s*:""", block) and all(
            f'"{stem}"' in block for stem in stems
        ), f"the kit's list of case clients leaves out {folder}"
    for walker in ("copyWords.test.ts", "copyNoClient.test.ts", "auth/resolvedPrincipal.test.ts"):
        text = (KIT.parent / walker).read_text(encoding="utf-8")
        assert "CASE_CLIENTS" in text and "plantedCaseClients" in text, (
            f"{walker} has no plant in the case clients"
        )
    # The selector is a real filter: a folder none of the files are in is not selected.
    assert not folders.search("/glass-shared/src/keyboard/actionRegistry.ts")


def test_no_new_dependency_was_added_to_the_package() -> None:
    """The package's manifest names the two packages it did before (the new files import none)."""
    manifest = json.loads(
        (CORE / "packages" / "glass-shared" / "package.json").read_text(encoding="utf-8")
    )
    assert sorted(manifest.get("dependencies", {})) == ["graphology", "zustand"]
