"""The remaining plain Conduit clients live in `packages/glass-shared`, nothing names the place they came from, and the
stray backup of the export client is gone (ADR-152 decision 6, "the Conduit client"; slice PL4d3c, the eighth of the PL4
slices after A, B, B2, B3, C, D1, D2, D3a and D3b; the owner's rulings of 20 and 21 November 2026).

Twelve plain TypeScript files moved whole from `OspreyFlow_Core/apps/workspace/src/` to
`OspreyFlow_Core/packages/glass-shared/src/`, at the same place under it, their bytes unchanged but for the import lines:

* the assessment's (`assessment/api.ts`: judgements, assumptions, gaps and the yardstick), the boards' (`boards/boardsApi.ts`),
  the connections' (`connections/connectionsApi.ts`) and the exploring panel's (`explore/exploreApi.ts`);
* the map's provider list (`map/providers.ts`), the metrics' call (`metrics/api.ts`) and the ownership place's
  (`ownership/api.ts`);
* the list-adding call (`search/addFromListApi.ts`), the site calibration's two (`site/api.ts` and its arithmetic,
  `site/bilinear.ts`), the strength explainer's (`strength/api.ts`) and the watches' (`watches/api.ts`).

Each calls `fetch` against the Conduit (or is the plain arithmetic one that does) and takes the bearer token as an
argument. None touches the page, and none imports React, a drawing library or a store.

**Two names were written twice, and the index says which is which.** `listJudgements` is the report clients' (their case
helper) and the assessment's; `Answer` is the promotions' and the boards'. Two `export *` of the same
name is an error in TypeScript and silently dropped in the browser, so the index names the assessment's as
`listAssessmentJudgements` and the boards' as `BoardAnswer`; every other name goes through as it was
(`test_the_index_exports_every_name_of_every_moved_client`). The importers that used the old name write
`listAssessmentJudgements as listJudgements`, so only their import line changes.

**The stray file.** `OspreyFlow_Core/apps/workspace/src/export/api.ts.bak` was a copy of the export client from before
D3a moved the live one, differing at one line, imported by nothing, and holding no key, token, address or client name.
`test_the_stray_backup_is_gone` is red on a tree that still has it (and `test_a_backup_left_in_the_tree_is_found` shows the
check can fail, on the shape `git ls-files` gives).

Every importer followed (the workspace, its tests, the keyboard and accessibility harnesses outside `src/`). The tests
stayed in the workspace, and a test that replaced a client with a double now replaces the package's export of it. This
file is the proof that none was left behind and that each guard can fail.

Which test fails if the invariant is broken (rule 12):

* a file is not where it should be, an old one is back, or the index does not export it:
  `test_the_twelve_clients_are_in_the_package_and_not_in_the_workspace`, and a name of one that the index leaves out
  (or two modules giving one name): `test_the_index_exports_every_name_of_every_moved_client`, with
  `test_an_index_that_drops_or_doubles_a_name_is_found`;
* a file of the package importing React or a drawing library, or a file of the workspace or the harness, or a schema
  import that no longer resolves: the D2 file's `test_the_package_s_clients_import_no_react_and_no_workspace_path` reads
  every file of the package, these twelve too; here `test_the_new_clients_are_among_the_files_that_check_reads` proves it
  does, and `test_a_react_or_workspace_import_in_a_moved_client_is_found` plants one in each;
* a moved client importing the package by its own name (a cycle through the index, which the workspace's way of writing
  it would leave behind): `test_no_moved_client_imports_the_package_by_its_name`, with a plant in each;
* a client changed in more than its import lines at the commit that moved it:
  `test_the_move_changed_no_line_but_the_imports`;
* a file of any kind naming an old path: `test_no_tracked_file_names_an_old_path`;
* an importer that still reaches an old path, or reaches into the package's folder instead of its name:
  `test_every_import_of_a_moved_client_reaches_the_package`, with `test_an_old_path_put_back_in_one_importer_is_found`
  (the lines the tree really held, among them nine `vi.mock` of the map's provider list and a sibling import by `./api`);
* a spec, or a file one imports, naming a file that does not exist (what Playwright would meet at collection):
  `test_every_import_reached_from_a_spec_resolves`;
* each of four gates that stops reading the moved files, or reads fewer files than before the move:
  `test_each_gate_reads_no_fewer_files_than_before`, and one plant for each gate in a **moved** file;
* each word-walker that does not read the moved files: the Python walkers by
  `test_the_people_name_walk_reads_each_moved_client` and `test_the_view_word_walk_reads_each_moved_client` (a plant in
  a copy of each of the twelve, clean beside it), `test_a_moved_clients_place_held_by_both_roots_is_read_from_both`
  (keyed by root); the vitest walkers (`copyWords`, `copyNoClient`, `resolvedPrincipal`) by
  `test_the_vitest_walkers_name_the_new_folders`, which reads the kit they share, whose own cases plant in a copy of each;
* either image's `COPY` lines naming a path that moved, or missing what the harness needs:
  `test_no_image_copies_a_path_that_moved`, `test_the_harness_image_copies_what_the_clients_need`, each shown red by
  `test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found`;
* the stray backup in the tree: `test_the_stray_backup_is_gone`, with `test_a_backup_left_in_the_tree_is_found`.

**This file walks:** `git ls-files` over the whole repository (the old-path test, the backup test); the tracked `.ts`,
`.tsx`, `.mts`, `.mjs`, `.js` and `.jsx` files under `OspreyFlow_Core/apps/` (the import tests, the spec walk, which starts
at every tracked `*.spec.ts` and `*.spec.tsx` in `apps/workspace` and `apps/harness` and follows their imports) and under
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
from tests.glass_trees import test_glass_shared_link_clients as link
from tests.glass_trees import test_glass_shared_plain_logic as earlier
from tests.harness import test_harness_frontend_copies as image

PACKAGE = "OspreyFlow_Core/packages/glass-shared/"
SHARED = PACKAGE + "src/"
SHARED_SRC = CORE / "packages" / "glass-shared" / "src"
APPS = "OspreyFlow_Core/apps/"
WORKSPACE_SRC = APPS + "workspace/src/"
PACKAGE_NAME = "@ospreyflow/glass-shared"

#: The twelve files that moved whole: where each is now (relative to `SHARED`; its old place is the same relative path
#: under `apps/workspace/src/`).
WHOLE = (
    "assessment/api.ts",
    "boards/boardsApi.ts",
    "connections/connectionsApi.ts",
    "explore/exploreApi.ts",
    "map/providers.ts",
    "metrics/api.ts",
    "ownership/api.ts",
    "search/addFromListApi.ts",
    "site/api.ts",
    "site/bilinear.ts",
    "strength/api.ts",
    "watches/api.ts",
)
OLD_OF = {rel: WORKSPACE_SRC + rel for rel in WHOLE}
_OLD_STEMS = {old.removesuffix(".ts") for old in OLD_OF.values()}

#: The names the index gives under another, because a moved file wrote a name that an earlier module of the package
#: already gives: (file, the name it wrote, the name the package exports it as).
RENAMED_BY_THE_INDEX = (
    ("assessment/api.ts", "listJudgements", "listAssessmentJudgements"),
    ("boards/boardsApi.ts", "Answer", "BoardAnswer"),
)

#: The stray file, written in two pieces: this file is read by the old-path walks of the earlier moves, which look for
#: the export client's name.
STRAY = WORKSPACE_SRC + "export/" + "api.ts.bak"

#: The places that may name an old path because they are a record of the past: the decision log, and the build record
#: under `process/`. They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone
#: (`test_every_named_exception_still_has_its_reason`).
NAMED = {
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_glass_shared_plain_clients.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

_NAME_FORMS = (
    r"assessment/api",
    r"boards/boardsApi",
    r"connections/connectionsApi",
    r"explore/exploreApi",
    r"map/providers",
    r"metrics/api",
    r"ownership/api",
    r"search/addFromListApi",
    r"site/api",
    r"site/bilinear",
    r"strength/api",
    r"watches/api",
)
#: Not a route (`/v1/map/providers` is the Conduit's address, not a file), and not `connectionsApi.test.ts` or the like (the
#: tests stayed in the workspace, beside where the file was).
_TEXT_FORM = re.compile(
    rf"(?<!glass-shared/src/)(?<!v1/)(?<![\w-])(?:{'|'.join(_NAME_FORMS)})\b(?!\.(?:css|test\.|spec\.|py|bak))"
)
#: A bare file name with its extension, as a guide writes it: `exploreApi.ts`. Not `api.ts` or `providers.ts`: other
#: folders have files of those names.
_FILE_FORM = re.compile(
    r"(?<![\w/.-])(?:boardsApi|connectionsApi|exploreApi|addFromListApi|bilinear)\.ts\b"
)
#: The segments of one written apart: `join(HERE, "..", "src", "site", "bilinear")`, Python's `/ "site" / "api.ts"`.
_SEGMENT_FORM = re.compile(
    r"""["'](?:assessment["']\s*[,/]\s*["']api|boards["']\s*[,/]\s*["']boardsApi"""
    r"""|connections["']\s*[,/]\s*["']connectionsApi|explore["']\s*[,/]\s*["']exploreApi"""
    r"""|map["']\s*[,/]\s*["']providers|metrics["']\s*[,/]\s*["']api|ownership["']\s*[,/]\s*["']api"""
    r"""|search["']\s*[,/]\s*["']addFromListApi|site["']\s*[,/]\s*["'](?:api|bilinear)"""
    r"""|strength["']\s*[,/]\s*["']api|watches["']\s*[,/]\s*["']api)(?:\.ts)?["']"""
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
                    continue  # `"glass-shared", "src", "site", "api"` is the new place written apart
                line = text.count("\n", 0, hit.start()) + 1
                found.append((rel, line, text.splitlines()[line - 1].strip()))
    return sorted(set(found))


def _kept_out(rel: str) -> bool:
    if rel in NAMED:
        return True
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in HISTORY)


# ----------------------------------------------------------------------------------------------------- the imports


def _client_names(root: Path) -> set[str]:
    """Every name the twelve clients export, read from the package's copies (the old ones are gone)."""
    names: set[str] = set()
    for rel in WHOLE:
        try:
            names |= link._exported_names((root / (SHARED + rel)).read_text(encoding="utf-8"))
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
    stars = {module.removeprefix("./") + ".ts" for module in link._STAR.findall(index)}
    braced: dict[str, set[str]] = {}
    for listed, module in link._BRACED.findall(index):
        given = braced.setdefault(module.removeprefix("./") + ".ts", set())
        for item in listed.split(","):
            item = re.sub(r"^\s*type\s+", "", item.strip())
            if item:
                given.add(item.split(" as ")[-1].strip())
    gives: dict[str, list[str]] = {}
    for rel, text in sources.items():
        if rel in stars:
            for name in link._exported_names(text):
                gives.setdefault(name, []).append(rel)
        for name in braced.get(rel, ()):
            gives.setdefault(name, []).append(rel)
    for rel in required:
        text = sources[rel]
        if rel not in stars and rel not in braced:
            problems.append(f"{rel} is not exported from the index")
            continue
        for name in sorted(link._exported_names(text)):
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


def test_the_twelve_clients_are_in_the_package_and_not_in_the_workspace() -> None:
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
    """Every module the index names (the twelve and the earlier slices'), keyed by its place under `src`."""
    named = {f"{m.removeprefix('./')}.ts" for m in link._STAR.findall(index)}
    named |= {f"{m.removeprefix('./')}.ts" for _, m in link._BRACED.findall(index)}
    named |= set(WHOLE)
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in sorted(named)}


def test_the_index_exports_every_name_of_every_moved_client() -> None:
    """Every name of every moved client is exported, by its own name or the one the index renames it to, and no name is
    given by two modules at once (the twelve are read beside every other module the index names, so a clash with an
    earlier slice's client is found too)."""
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    assert index_problems(index, _modules_of(index), WHOLE) == []


def test_an_index_that_drops_or_doubles_a_name_is_found() -> None:
    """Red for the check above (rule 15), on the shapes the move could leave: the index as the real one is, clean; a braced
    export that leaves a name out; a second module giving a name already given; a file left out; the rename lost."""
    sources = {
        "other/packs.ts": "export async function listJudgements(): Promise<void> {}\n",
        "assessment/api.ts": "export async function listJudgements(): Promise<void> {}\nexport const getYardstick = 1;\n",
        "other/promotions.ts": "export type Answer<T> = { ok: true; value: T };\nexport const promote = 1;\n",
        "boards/boardsApi.ts": "export type Answer<T> = { ok: true; value: T };\nexport const listBoards = 1;\n",
    }
    index = (
        'export * from "./other/packs";\n'
        'export { getYardstick, listJudgements as listAssessmentJudgements } from "./assessment/api";\n'
        'export { type Answer, promote } from "./other/promotions";\n'
        'export { type Answer as BoardAnswer, listBoards } from "./boards/boardsApi";\n'
    )

    def found(text: str, files: dict[str, str] = sources) -> list[str]:
        return index_problems(text, files)

    assert found(index) == []
    assert any("getYardstick" in p for p in found(index.replace("getYardstick, ", "")))
    assert any(
        "two modules, one name" in p
        for p in found(
            index.replace("listJudgements as listAssessmentJudgements", "listJudgements")
        )
    )
    assert any(
        "two modules, one name" in p
        for p in found(index.replace("type Answer as BoardAnswer", "type Answer"))
    )
    assert any(
        "not exported" in p for p in found(index.replace('export * from "./other/packs";\n', ""))
    )
    assert any("BoardAnswer" in p for p in found(index.replace("type Answer as BoardAnswer, ", "")))
    assert any(
        "listAssessmentJudgements" in p
        for p in found(index.replace("listJudgements as listAssessmentJudgements", "getYardstick"))
    )


def test_the_new_clients_are_among_the_files_that_check_reads() -> None:
    """D2's check walks every `.ts` file of the package (tests apart): the twelve are in it."""
    sources = clients._package_sources()
    for rel in WHOLE:
        assert SHARED + rel in sources, f"{rel} is not among the package's sources"
    problems = [p for rel in WHOLE for p in clients.package_import_problems(ROOT, SHARED + rel)]
    assert problems == [], f"{len(problems)} import(s) the package may not make: {problems[:10]}"


def test_a_react_or_workspace_import_in_a_moved_client_is_found(package_copy: Path) -> None:
    """Red for the check above (rule 15): in each of the twelve, the lines the client would carry if it grew a hook, a
    store, or a path into the workspace (among them the way the workspace wrote a schema import, which is not the package's
    way). Each file is clean first, so the plant is what is found."""
    plants = (
        'import { useEffect } from "react";\n',
        'import { WITHHELD_SENTENCE } from "../statusbar/StatusBar";\n',
        'import { create } from "zustand";\n',
        'import BY_ROLE from "../../../../apps/workspace/src/shell/placesByRole.json";\n',
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


def test_no_moved_client_imports_the_package_by_its_name() -> None:
    """The workspace wrote `from "@ospreyflow/glass-shared"` for the working-set types, the expansion's outcome and the
    canvas outcome; inside the package they are the sibling modules, imported by their paths."""
    found = [line for rel in WHOLE for line in link.self_imports(ROOT, SHARED + rel)]
    assert found == [], f"{len(found)} moved client(s) import the package by its name: {found}"


def test_a_self_import_in_a_moved_client_is_found(package_copy: Path) -> None:
    """Red for the check above, at the shapes the workspace wrote: a type from the working set, and a value from the
    expansion's outcome, each by the package's name. Clean first."""
    for rel in WHOLE:
        target = package_copy / (SHARED + rel)
        real = target.read_text(encoding="utf-8")
        assert link.self_imports(package_copy, SHARED + rel) == []
        for line in (
            'import type { WorkingSetDelta } from "@ospreyflow/glass-shared";\n',
            'import { outcomeDeltas, type ExpansionOutcome } from "@ospreyflow/glass-shared";\n',
            'import type { CanvasOutcome } from "@ospreyflow/glass-shared";\n',
        ):
            target.write_text(line + real, encoding="utf-8")
            assert link.self_imports(package_copy, SHARED + rel), f"{line!r} is not found in {rel}"
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
    assert importers >= 30, (
        f"only {importers} file(s) under OspreyFlow_Core import a client's name from {PACKAGE_NAME}: the walk found too few imports, or the importers were not repointed"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach the package by its name: {bad[:10]}"


_PLANTED_IMPORTS = {
    # (path of the file that held the line, the line as the tree wrote it, the line it has now)
    "the assessment's judgements, from the app (a name the index gives apart)": (
        WORKSPACE_SRC + "App.tsx",
        'import { listJudgements } from "./assessment/api";',
        f'import {{ listAssessmentJudgements as listJudgements }} from "{PACKAGE_NAME}";',
    ),
    "the connections' seeding, from the app": (
        WORKSPACE_SRC + "App.tsx",
        'import { seedElements } from "./connections/connectionsApi";',
        f'import {{ seedElements }} from "{PACKAGE_NAME}";',
    ),
    "the strength call, from the app": (
        WORKSPACE_SRC + "App.tsx",
        'import { fetchCaseInfluencers } from "./strength/api";',
        f'import {{ fetchCaseInfluencers }} from "{PACKAGE_NAME}";',
    ),
    "the map's provider list, from the app": (
        WORKSPACE_SRC + "App.tsx",
        'import { defaultProvider, fetchMapConfig, switchableProviders } from "./map/providers";',
        f'import {{ defaultProvider, fetchMapConfig, switchableProviders }} from "{PACKAGE_NAME}";',
    ),
    "the explore panel's types, from the app": (
        WORKSPACE_SRC + "App.tsx",
        'import type { BusyDay, RankedLink } from "./explore/exploreApi";',
        f'import type {{ BusyDay, RankedLink }} from "{PACKAGE_NAME}";',
    ),
    "a double of the map's provider list, as a vi.mock": (
        WORKSPACE_SRC + "App.test.tsx",
        'vi.mock("./map/providers", async () => {',
        f'vi.mock("{PACKAGE_NAME}", async () => {{',
    ),
    "the real provider list under that double": (
        WORKSPACE_SRC + "App.test.tsx",
        'const actual = await vi.importActual<typeof import("./map/providers")>("./map/providers");',
        f'const actual = await vi.importActual<typeof import("{PACKAGE_NAME}")>("{PACKAGE_NAME}");',
    ),
    "the strength calls, from the metrics panel (a parent folder)": (
        WORKSPACE_SRC + "metrics/MetricsPanel.tsx",
        'import { fetchConnectionStrengths, fetchRarity, type RarityScope } from "../strength/api";',
        f'import {{ fetchConnectionStrengths, fetchRarity, type RarityScope }} from "{PACKAGE_NAME}";',
    ),
    "the metrics call, beside it (a sibling named api)": (
        WORKSPACE_SRC + "metrics/filters.ts",
        'import type { ComputeMetricName } from "./api";',
        f'import type {{ ComputeMetricName }} from "{PACKAGE_NAME}";',
    ),
    "the watches' calls, beside them (a sibling named api)": (
        WORKSPACE_SRC + "watches/MonitorPanel.tsx",
        'import { createMonitor, listMonitors, setMonitorSchedule } from "./api";',
        f'import {{ createMonitor, listMonitors, setMonitorSchedule }} from "{PACKAGE_NAME}";',
    ),
    "the boards' calls, beside them": (
        WORKSPACE_SRC + "boards/BoardsPlace.tsx",
        'import { listBoards, makeBoard, startDrawing, type Board } from "./boardsApi";',
        f'import {{ listBoards, makeBoard, startDrawing, type Board }} from "{PACKAGE_NAME}";',
    ),
    "the last line of a many-line import of the boards' calls": (
        WORKSPACE_SRC + "boards/BoardEditor.tsx",
        '} from "./boardsApi";',
        f'}} from "{PACKAGE_NAME}";',
    ),
    "the list-adding call, beside it (the last line of a many-line import)": (
        WORKSPACE_SRC + "search/AddFromList.tsx",
        '} from "./addFromListApi";',
        f'}} from "{PACKAGE_NAME}";',
    ),
    "the site arithmetic, beside it": (
        WORKSPACE_SRC + "site/siteLayer.ts",
        'import type { ControlPoint } from "./bilinear";',
        f'import type {{ ControlPoint }} from "{PACKAGE_NAME}";',
    ),
    "the ownership calls, beside them": (
        WORKSPACE_SRC + "ownership/OwnershipPlace.tsx",
        'import { findEntities, kycStatus, ownershipToCanvas, traceOwnership, type OwnershipApi } from "./api";',
        f'import {{ findEntities, kycStatus, ownershipToCanvas, traceOwnership, type OwnershipApi }} from "{PACKAGE_NAME}";',
    ),
    "the assessment's type, from the report export (a parent folder)": (
        WORKSPACE_SRC + "export/reportExport.ts",
        'import type { Yardstick } from "../assessment/api";',
        f'import type {{ Yardstick }} from "{PACKAGE_NAME}";',
    ),
    "a deep import into the package": (
        WORKSPACE_SRC + "watches/HotlistPanel.tsx",
        'import { listHotlists } from "../../../../packages/glass-shared/src/watches/api";',
        f'import {{ listHotlists }} from "{PACKAGE_NAME}";',
    ),
    "a bare file name in a guide": (
        "OspreyFlow_Core/docs/administration-guide.md",
        "The boards' calls are in `boardsApi.ts` and nowhere else.",
        "The boards' calls are in the boards module and nowhere else.",
    ),
    "an old path in a comment of the workspace": (
        WORKSPACE_SRC + "map/MapView.tsx",
        "   * only the site-image proxy route (`site/api.ts`'s `siteImageUrl`)",
        "   * only the site-image proxy route (`packages/glass-shared/src/site/api.ts`'s `siteImageUrl`)",
    ),
    "the site arithmetic, written in segments": (
        APPS + "workspace/a11y/plants/run.mjs",
        'const bilinear = join(HERE, "..", "..", "src", "site", "bilinear");',
        'const bilinear = join(HERE, "..", "..", "..", "..", "packages", "glass-shared", "src", "site", "bilinear");',
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
    for name in ("listBoards", "listAssessmentJudgements", "BoardAnswer", "fetchMapConfig"):
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
    """Red for the walk above, at the shapes the move could leave: a spec's harness still importing a client by the old path,
    and the index exporting a file that is not there."""
    spec = APPS + "workspace/keyboard/boards.spec.ts"
    harness = APPS + "workspace/keyboard/boards-harness.tsx"
    files = {
        spec: 'import { mount } from "./boards-harness";\n',
        harness: f'import {{ listBoards }} from "{PACKAGE_NAME}";\n',
        SHARED + "index.ts": 'export * from "./boards/boardsApi";\n',
        SHARED + "boards/boardsApi.ts": "export const listBoards = 1;\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == []
    (tmp_path / harness).write_text(
        'import { listBoards } from "../src/boards/boardsApi";\n', encoding="utf-8"
    )
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [
        f"{harness}: ../src/boards/boardsApi"
    ]
    (tmp_path / harness).write_text(
        f'import {{ listBoards }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
    )
    (tmp_path / SHARED / "boards" / "boardsApi.ts").unlink()
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [
        f"{SHARED}index.ts: ./boards/boardsApi"
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
    every `COPY` of a workspace path still names something that exists and is reached. The walk reaches the twelve."""
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

    for rel in ("watches/api.ts", "strength/api.ts", "site/bilinear.ts"):
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
    assert stale_copies(workspace + "COPY apps/workspace/src/map/providers.ts ./x\n") == [
        "apps/workspace/src/map/providers.ts"
    ]


# --------------------------------------------------------------------------------------------------- the four gates

#: The files each gate read on main before this move: the number each reported or, where it reports none, the files its own
#: rules select (measured on 21 November 2026, on the tip PL4d3c started from, after PL4d3b). The twelve clients moved from
#: a folder each gate reads to another it reads, so the numbers do not fall: none may.
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
        "watches/api.ts",
        '\nexport const STRIPE = { background: "#12ab34", padding: 8 };\n',
    )
    assert colour_drift_check.main() == 1
    assert "packages/glass-shared/src/watches/api.ts:" in capsys.readouterr().out


def test_the_design_detector_reports_a_plant_in_a_moved_client(
    shared_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(design_check, "SCANNED", [shared_copy])
    assert design_check.unexcused(design_check.detect(design_check.SCANNED)) == [], (
        "the clean copy already has findings"
    )
    earlier._append(
        shared_copy,
        "strength/api.ts",
        "\nexport const TOAST_STYLE = {\n"
        '  background: "var(--surface-raised)", borderLeft: "3px solid var(--error)", borderRadius: "8px",\n'
        '  padding: "12px 16px", boxShadow: "var(--overlay-shadow)",\n'
        "};\n",
    )
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [("api.ts", "side-tab")]
    assert "strength" in found[0]["file"]


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
    earlier._append(shared_copy, "ownership/api.ts", '\nexport const LABEL = "Target model";\n')
    assert ui_words_check.main() == 1
    assert "packages/glass-shared/src/ownership/api.ts:" in capsys.readouterr().out


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
        shared_copy, "metrics/api.ts", '\nexport const BRANCH_CASE = "branch-by-filter";\n'
    )
    assert no_branches_check.main() == 1
    assert f"{top}/metrics/api.ts:" in capsys.readouterr().out


# -------------------------------------------------------------------------------------------------- the word-walkers

#: The twelve as (folder, stem) pairs, never written as a path (the old-path scan reads the other walkers' tables too).
_MOVED = {
    "assessment": ("api",), "boards": ("boardsApi",), "connections": ("connectionsApi",), "explore": ("exploreApi",),
    "map": ("providers",), "metrics": ("api",), "ownership": ("api",), "search": ("addFromListApi",),
    "site": ("api", "bilinear"), "strength": ("api",), "watches": ("api",),
}  # fmt: skip
MOVED_CLIENTS = tuple(f"{folder}/{stem}.ts" for folder, stems in _MOVED.items() for stem in stems)


def test_the_moved_table_is_the_list_of_twelve() -> None:
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
        (root / "site").mkdir(parents=True)
        (root / "site" / "api.ts").write_text(
            'export const word = "Clear view";\n'
            if n == planted_in
            else "export const word = 1;\n",
            encoding="utf-8",
        )
    expected = "site/api.ts" if planted_in == 0 else "shared:site/api.ts"
    assert navigation.old_view_words_on_screen(navigation.glass_sources(roots)) == [
        f"{expected}: 'Clear view'"
    ]


KIT = CORE / "apps" / "workspace" / "src" / "copyTextsTestKit.ts"
_KIT_FOLDERS = re.compile(r"^export const MOVED_FOLDERS = /(.*)/;$", re.M)


def test_the_vitest_walkers_name_the_new_folders() -> None:
    """`copyWords`, `copyNoClient` and `resolvedPrincipal` walk the kit's two roots, and each has a case that plants in a copy
    of every file the kit lists as a plain client. The kit selects the package's folders by `MOVED_FOLDERS`: every folder of
    the twelve is among them (the vitest cases themselves run under `npm test --workspace apps/workspace`)."""
    kit = KIT.read_text(encoding="utf-8")
    found = _KIT_FOLDERS.search(kit)
    assert found, (
        "copyTextsTestKit.ts does not state MOVED_FOLDERS as one regular expression on a line of its own"
    )
    folders = re.compile(found.group(1))
    for rel in WHOLE:
        assert folders.search(f"/glass-shared/src/{rel}"), f"MOVED_FOLDERS does not select {rel}"
    assert "ROOTS" in kit and "SHARED_SRC" in kit
    assert "PLAIN_CLIENTS" in kit and "plantedPlainClients" in kit, (
        "the kit does not list the plain clients or plant in them"
    )
    block = kit[kit.index("const PLAIN_STEMS") :].split("};", 1)[0]
    for folder, stems in _MOVED.items():
        assert re.search(rf"\b{folder}:", block) and all(f'"{stem}"' in block for stem in stems), (
            f"the kit's list of plain clients leaves out {folder}"
        )
    for walker in ("copyWords.test.ts", "copyNoClient.test.ts", "auth/resolvedPrincipal.test.ts"):
        text = (KIT.parent / walker).read_text(encoding="utf-8")
        assert "PLAIN_CLIENTS" in text and "plantedPlainClients" in text, (
            f"{walker} has no plant in the plain clients"
        )
    # The selector is a real filter: a folder the clients are not in is not selected.
    assert not folders.search("/glass-shared/src/keyboard/actionRegistry.ts")


# ------------------------------------------------------------------------------------------------- the stray backup


def stray_backups(rels: Iterable[str]) -> list[str]:
    """The files among `rels` (repository-relative, as `git ls-files` gives them) that are a backup copy of a source file
    under the product's code: a `.bak` under `OspreyFlow_Core/apps/` or `OspreyFlow_Core/packages/`."""
    return sorted(
        rel
        for rel in rels
        if rel.endswith(".bak") and rel.startswith((APPS, "OspreyFlow_Core/packages/"))
    )


def test_the_stray_backup_is_gone() -> None:
    """Red on a tree that still has the copy of the export client from before D3a moved the live one."""
    names = earlier.tracked()
    assert STRAY not in names, f"{STRAY} is still tracked"
    assert not (ROOT / STRAY).exists(), f"{STRAY} is still in the tree"
    assert stray_backups(names) == []


def test_a_backup_left_in_the_tree_is_found() -> None:
    """Red for the check above (rule 15), on the shape `git ls-files` gives: the stray file itself, another backup beside a
    source file of the package, and a backup of a file that is not part of the product's code (not this check's business)."""
    clean = [WORKSPACE_SRC + "export/ExportPanel.tsx", SHARED + "somewhere/helper.ts"]
    assert stray_backups(clean) == []
    assert stray_backups([*clean, STRAY]) == [STRAY]
    assert stray_backups([*clean, SHARED + "somewhere/helper.ts.bak"]) == [
        SHARED + "somewhere/helper.ts.bak"
    ]
    assert stray_backups([*clean, "OspreyFlow_Build/tests/fixtures/old.csv.bak"]) == []
