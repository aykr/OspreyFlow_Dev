"""The ingest, sources, releases, maps, models and update-notice Conduit clients live in `packages/glass-shared`, and
nothing names the place they came from (ADR-152 decision 6, "the Conduit client"; slice PL4d2, the fifth of the PL4
slices after A, B, B2, B3, C and D1; the owner's rulings of 20 November 2026).

Six plain TypeScript files moved whole from `OspreyFlow_Core/apps/workspace/src/` to
`OspreyFlow_Core/packages/glass-shared/src/`, at the same place under it, their bytes unchanged but for the import lines:

* `ingest/api.ts` (the Ingest Studio's calls), `ingest/sources/api.ts` (the sources), `ingest/releases/releasesApi.ts`,
* `admin/sections/MapsApi.ts`, `admin/sections/ModelsApi.ts`, `admin/updateNotice.ts`.

Each calls `fetch` against the Conduit and takes the bearer token as an argument. None touches the page, and none imports
React, a drawing library or a store. The generated schemas are reached the way the package's own `workingset/store.ts`
reaches them (`../../../schemas/generated`, a type import).

**Two files did not move, and the test says why.** `admin/api.ts` imports `../help/roles` for its words about a refusal, and
`help/roles.ts` reads `shell/placesByRole.json`, a record that lives in the workspace: the Python tests
(`test_place_routes.py`, `test_guide_role_words.py`) pin it at that path and generate it there, and the package may never
import a workspace file. `test_the_admin_client_stays_while_its_words_need_the_workspace` fails if either file moves
without the record, or if the package starts to import it.

Every importer followed (the workspace, its tests, the Playwright harnesses and specs outside `src/`, the harness). The
tests stayed in the workspace, and a test that replaced a client with a double now replaces the package's export of it.
This file is the proof that none was left behind and that each guard can fail.

Which test fails if the invariant is broken (rule 12):

* a file is not where it should be, an old one is back, or the index does not export it:
  `test_the_six_clients_are_in_the_package_and_not_in_the_workspace`;
* a file of the package importing React or a drawing library (as a value or a type), or a file of the workspace or the
  harness (any relative path that leaves the package for `apps/`), or a schema import that no longer resolves:
  `test_the_package_s_clients_import_no_react_and_no_workspace_path`, with `test_a_react_import_in_a_moved_client_is_found`
  and `test_a_workspace_import_in_a_moved_client_is_found`;
* a client changed in more than its import lines at the commit that moved it:
  `test_the_move_changed_no_line_but_the_imports`, shown red by `test_a_moved_client_changed_in_more_than_its_imports_is_found`;
* a file of any kind naming an old path, in a form the repository writes it in: `test_no_tracked_file_names_an_old_path`
  (the whole repository; only the decision log and the build record may keep one, and the files in `NAMED`, each with why);
* an importer that still reaches an old path, or reaches into the package's folder instead of its name:
  `test_every_import_of_a_moved_client_reaches_the_package`, with `test_an_old_path_put_back_in_one_importer_is_found`;
* a spec, or a file one imports (by any chain of imports), naming a file that does not exist, which Playwright would meet at
  collection and no unit test would: `test_every_import_reached_from_a_spec_resolves` (the Playwright collection check's own
  half: the count of tests and files is measured by `npx playwright test --list`, which this file does not run);
* either image's `COPY` lines naming a path that moved, or missing what the harness needs:
  `test_no_image_copies_a_path_that_moved`, `test_the_harness_image_copies_what_the_clients_need`, each shown red by
  `test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found`.

Each guard is shown red on a planted regression in the shape the real code writes it (rule 15): the planted lines are
lines the tree wrote on the day before the move, each placed at the path of a file that held one, and each case first
shows the same file clean with the new line.

**This file walks:** `git ls-files` over the whole repository (the old-path test); the tracked `.ts`, `.tsx`, `.mts`,
`.mjs`, `.js` and `.jsx` files under `OspreyFlow_Core/apps/` (the import tests, the spec walk, which starts at every tracked
`*.spec.ts` and `*.spec.tsx` in `apps/workspace` and `apps/harness` and follows their imports) and under
`OspreyFlow_Core/packages/glass-shared/src` (the moved files, the index, the package's own imports);
`apps/workspace/Dockerfile` and `harness/Dockerfile` by name; the git history of the rename (`git log`, `git show`); and
temporary copies built inside `tmp_path` for the plants (written there, never in the repository).
"""

# The planted lines below are the real call-site shapes, kept on one line as the tree wrote them (rule 15), and the
# prose beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable
from pathlib import Path

import pytest
from tools.layout import CORE, ROOT

from tests.glass_trees import test_glass_shared_plain_logic as earlier
from tests.harness import test_harness_frontend_copies as image

PACKAGE = "OspreyFlow_Core/packages/glass-shared/"
SHARED = PACKAGE + "src/"
SHARED_SRC = CORE / "packages" / "glass-shared" / "src"
APPS = "OspreyFlow_Core/apps/"
WORKSPACE_SRC = APPS + "workspace/src/"
PACKAGE_NAME = "@ospreyflow/glass-shared"
GENERATED = "OspreyFlow_Core/packages/schemas/generated"

#: The six files that moved whole: where each is now (relative to `SHARED`; its old place is the same relative path under
#: `apps/workspace/src/`).
WHOLE = (
    "ingest/api.ts",
    "ingest/sources/api.ts",
    "ingest/releases/releasesApi.ts",
    "admin/sections/MapsApi.ts",
    "admin/sections/ModelsApi.ts",
    "admin/updateNotice.ts",
)
OLD_OF = {rel: WORKSPACE_SRC + rel for rel in WHOLE}
_OLD_STEMS = {old.removesuffix(".ts") for old in OLD_OF.values()}

#: The two that stay, and the record that keeps them there.
STAYS = ("admin/api.ts", "help/roles.ts")
RECORD = "shell/placesByRole.json"

#: The places that may name an old path because they are a record of the past: the decision log, and the build record
#: under `process/`. They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone
#: (`test_every_named_exception_still_has_its_reason`).
NAMED = {
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_glass_shared_clients.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

_NAME_FORMS = (
    r"ingest/api",
    r"ingest/sources/api",
    r"ingest/releases/releasesApi",
    r"sections/MapsApi",
    r"sections/ModelsApi",
    r"admin/updateNotice",
)
#: Not `updateNotice.test.ts`: the test stayed in the workspace, beside where the file was.
_TEXT_FORM = re.compile(
    rf"(?<!glass-shared/src/)(?<![\w-])(?:{'|'.join(_NAME_FORMS)})\b(?!\.(?:css|test\.|spec\.|py))"
)
#: A bare file name with its extension, as a guide writes it: `releasesApi.ts`.
_FILE_FORM = re.compile(r"(?<![\w/.-])(?:releasesApi|MapsApi|ModelsApi)\.ts\b")
#: The segments of one written apart: `join(HERE, "..", "src", "ingest", "api")`, Python's `/ "ingest" / "api.ts"`.
_SEGMENT_FORM = re.compile(
    r"""["'](?:ingest["']\s*[,/]\s*["']api|ingest["']\s*[,/]\s*["']sources["']\s*[,/]\s*["']api"""
    r"""|ingest["']\s*[,/]\s*["']releases["']\s*[,/]\s*["']releasesApi|sections["']\s*[,/]\s*["'](?:MapsApi|ModelsApi)"""
    r"""|admin["']\s*[,/]\s*["']updateNotice)(?:\.ts)?["']"""
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
                    continue  # `"glass-shared", "src", "ingest", "api"` is the new place written apart
                line = text.count("\n", 0, hit.start()) + 1
                found.append((rel, line, text.splitlines()[line - 1].strip()))
    return sorted(set(found))


def _kept_out(rel: str) -> bool:
    if rel in NAMED:
        return True
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in HISTORY)


# ----------------------------------------------------------------------------------------------------- the imports

_PACKAGE_IMPORT = re.compile(rf"""["']{re.escape(PACKAGE_NAME)}(/[^"']*)?["']""")


def imports_not_reaching(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The relative specifiers that resolve to an old path, or into the package's folder instead of its name; and the
    number of files that import a name a moved client exports from the package. Resolution is by path alone: an old file
    need not exist."""
    bad: list[str] = []
    importers = 0
    names = _client_names(root)
    for rel in rels:
        if Path(rel).suffix not in earlier._SOURCE_SUFFIXES or not rel.startswith("OspreyFlow_Core/"):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for hit in _PACKAGE_IMPORT.finditer(text):
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
            if stem in _OLD_STEMS:
                bad.append(f"{rel}: {hit.group(1)} (an old path)")
            elif target.startswith(PACKAGE) and not rel.startswith(PACKAGE):
                bad.append(f"{rel}: {hit.group(1)} (into the package's folder, not its name)")
    return bad, importers


def _exported_names(text: str) -> set[str]:
    return set(re.findall(r"^export\s+(?:async\s+)?(?:function|const|let|class|type|interface|enum)\s+(\w+)", text, re.M))


def _client_names(root: Path) -> set[str]:
    """Every name the six clients export, read from the package's copies (the old ones are gone). Names a client shares
    with something else the package exports are not used to find importers, so a clash cannot inflate the count."""
    names: set[str] = set()
    for rel in WHOLE:
        try:
            names |= _exported_names((root / (SHARED + rel)).read_text(encoding="utf-8"))
        except OSError:
            continue
    return names


# ------------------------------------------------------------------------------------ plain, and nothing from the workspace

_RELATIVE_SPEC = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\(\s*)["'](\.{1,2}/[^"'\n]*)["']""")
_ABSOLUTE_SPEC = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\(\s*)["']([^."'\n][^"'\n]*)["']""")


def package_import_problems(root: Path, rel: str) -> list[str]:
    """What is wrong with one file of the package's source: React or a drawing library (as a value or a type), a relative
    import that leaves the package for anywhere but the generated schemas, a schema import that names nothing, one that
    spells `packages/` out the long way, and a package of the workspace's own by name."""
    text = (root / rel).read_text(encoding="utf-8")
    problems = [f"{rel}: imports {name}" for name in earlier.forbidden_imports(text)]
    for spec in _RELATIVE_SPEC.findall(text):
        target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
        if target.startswith(SHARED):
            continue
        if target == GENERATED or target.startswith(GENERATED + "/"):
            if not (root / (GENERATED + "/index.ts")).is_file():
                problems.append(f"{rel}: {spec} names no generated schemas")
            if "/packages/" in "/" + spec:
                problems.append(f"{rel}: {spec} reaches the schemas by the workspace's depth, not the package's way")
            continue
        problems.append(f"{rel}: {spec} leaves the package for {target}")
    for spec in _ABSOLUTE_SPEC.findall(text):
        if spec.startswith("@ospreyflow/") and spec != PACKAGE_NAME:
            problems.append(f"{rel}: imports {spec}, a package of the workspace")
    return problems


def _package_sources() -> list[str]:
    return sorted(
        rel
        for rel in earlier.tracked()
        if rel.startswith(SHARED) and rel.endswith(".ts") and ".test." not in rel
    )


# ---------------------------------------------------------------------------------------------- how a move is compared


def _skip_if_shallow() -> None:
    earlier._skip_if_shallow()


# ----------------------------------------------------------------------------------------------- the real tree: cases


def test_the_six_clients_are_in_the_package_and_not_in_the_workspace() -> None:
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
            rf"""^export\s+(?:\*|\{{[^}}]*\}})\s+from\s+["']{re.escape(stem)}["'];""", index, re.M
        ), f"packages/glass-shared/src/index.ts does not export {stem}"


def test_the_admin_client_stays_while_its_words_need_the_workspace() -> None:
    """`admin/api.ts` takes its words from `help/roles.ts`, which reads a record the workspace holds. Either both of those
    and the record move together (a decision of the owner's, with the Python tests that pin the record's path) or neither
    does; and the package never imports a workspace file."""
    names = earlier.tracked()
    for rel in STAYS:
        assert WORKSPACE_SRC + rel in names, f"{WORKSPACE_SRC}{rel} left the workspace"
        assert SHARED + rel not in names, f"{SHARED}{rel} is in the package, which cannot reach the record"
    roles = (ROOT / (WORKSPACE_SRC + "help/roles.ts")).read_text(encoding="utf-8")
    assert f'"../{RECORD}"' in roles, "help/roles.ts no longer reads the record: this exception's reason is gone"
    assert WORKSPACE_SRC + RECORD in names, "the record is not where the Python tests pin it"
    assert SHARED + RECORD not in names
    admin = (ROOT / (WORKSPACE_SRC + "admin/api.ts")).read_text(encoding="utf-8")
    assert '"../help/roles"' in admin, "admin/api.ts no longer imports the roles' words: this exception's reason is gone"


def test_the_package_s_clients_import_no_react_and_no_workspace_path() -> None:
    sources = _package_sources()
    assert len(sources) >= 30, f"only {len(sources)} package sources found: the walk is not seeing the package"
    for rel in WHOLE:
        assert SHARED + rel in sources
    problems = [p for rel in sources for p in package_import_problems(ROOT, rel)]
    assert problems == [], f"{len(problems)} import(s) the package may not make: {problems[:10]}"


def test_a_react_import_in_a_moved_client_is_found(tmp_path: Path) -> None:
    """Red for the check above (rule 15): the lines a client would carry if it grew a hook or a store, put into the file
    that would hold them. Each file is clean first, so the plant is what is found."""
    planted = {
        "ingest/api.ts": 'import { useEffect } from "react";',
        "admin/sections/ModelsApi.ts": 'import type { ReactNode } from "react";',
        "ingest/sources/api.ts": 'import { create } from "zustand";',
        "admin/updateNotice.ts": 'import { renderToString } from "react-dom/server";',
        "ingest/releases/releasesApi.ts": 'import maplibregl from "maplibre-gl";',
    }
    for rel, line in planted.items():
        real = (ROOT / (SHARED + rel)).read_text(encoding="utf-8")
        target = tmp_path / (SHARED + rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / GENERATED).mkdir(parents=True, exist_ok=True)
        (tmp_path / (GENERATED + "/index.ts")).write_text("export {};\n", encoding="utf-8")
        target.write_text(real, encoding="utf-8")
        assert package_import_problems(tmp_path, SHARED + rel) == [], f"{rel} is not clean to begin with"
        target.write_text(line + "\n" + real, encoding="utf-8")
        found = package_import_problems(tmp_path, SHARED + rel)
        assert found, f"{line!r} is not found in {rel}"
    # `zustand`'s main entry pulls React in; only `zustand/vanilla` is named by the package.
    assert package_import_problems(tmp_path, SHARED + "ingest/sources/api.ts") != []


def test_a_workspace_import_in_a_moved_client_is_found(tmp_path: Path) -> None:
    """Red for the check above, in the shapes the move could leave: the admin client's own import of the roles' words, put
    into a moved client at the depth it has in the package; a schema import written at the workspace's depth, so that it
    names nothing a package can reach; the long way to the same schemas; and a file of the workspace imported by name."""
    rel = "admin/sections/MapsApi.ts"
    real = (ROOT / (SHARED + rel)).read_text(encoding="utf-8")
    target = tmp_path / (SHARED + rel)
    target.parent.mkdir(parents=True)
    (tmp_path / GENERATED).mkdir(parents=True)
    (tmp_path / (GENERATED + "/index.ts")).write_text("export {};\n", encoding="utf-8")
    target.write_text(real, encoding="utf-8")
    assert package_import_problems(tmp_path, SHARED + rel) == []
    plants = {
        "the roles' words": 'import { rightName, rolesHolding } from "../../help/roles";\n',
        "the record": 'import BY_ROLE from "../../../../../apps/workspace/src/shell/placesByRole.json";\n',
        "a workspace module by a long path": 'import { applyTheme } from "../../../../../apps/workspace/src/theme/ThemeToggle";\n',
        "the schemas, one level too far": 'import type { MapsAdminView } from "../../../../../schemas/generated";\n',
        "the schemas, the long way": 'import type { MapsAdminView } from "../../../../packages/schemas/generated";\n',
    }
    for case, line in plants.items():
        target.write_text(line + real, encoding="utf-8")
        assert package_import_problems(tmp_path, SHARED + rel), f"{case} is not found"


def test_the_move_changed_no_line_but_the_imports() -> None:
    """Each file is read as the commit that renamed it left it against the commit before: git's own detection finds the
    rename, and the two sides are compared there, never against the working tree (a later edit would be read as the move's).
    A shallow clone has no history to read: skipped, as the earlier move tests in this folder are."""
    _skip_if_shallow()
    for rel in WHOLE:
        new, old = SHARED + rel, OLD_OF[rel]
        commit = earlier._git("log", "--follow", "-M", "--diff-filter=R", "--format=%H", "-1", "--", new).strip()
        assert commit, f"git finds no rename into {new}: the file was not moved with `git mv`"
        assert earlier._git("show", f"{commit}^:{old}"), f"{old} is not in the commit before the rename"
        assert (
            earlier.only_import_lines_changed(earlier._git("show", f"{commit}^:{old}"), earlier._git("show", f"{commit}:{new}"))
            == []
        ), f"{new} changed in more than its import lines"


def test_a_moved_client_changed_in_more_than_its_imports_is_found() -> None:
    """Red for the comparison above: the real update notice's schema import moved to the package's way, once alone and once
    with a second line changed."""
    was = 'import type { UpdateNotice } from "../../../../packages/schemas/generated";\n\nexport const WINDOW_DAYS = 14;\n'
    moved = was.replace("../../../../packages/schemas/generated", "../../../schemas/generated")
    assert earlier.only_import_lines_changed(was, moved) == []
    assert earlier.only_import_lines_changed(was, moved.replace("14", "30")) != []
    multi = 'import type {\n  A,\n  B,\n} from "../../../../packages/schemas/generated";\n'
    assert earlier.only_import_lines_changed(multi, multi.replace("../../../../packages/", "../../../")) == []


def test_no_tracked_file_names_an_old_path() -> None:
    rels = [rel for rel in earlier.tracked() if not _kept_out(rel)]
    assert len(rels) > 1000, "the walk found too few files: git ls-files is not listing the repository"
    found = old_path_mentions(ROOT, rels)
    shown = "\n".join(f"  {rel}:{line}: {text[:140]}" for rel, line, text in found[:40])
    assert found == [], f"{len(found)} place(s) still name an old path; the files are now in {SHARED}:\n{shown}"


def test_every_named_exception_still_has_its_reason() -> None:
    """An exception outlives its reason when the file it excuses no longer names an old path: left in `NAMED` it keeps that
    file outside the walk, and an old path could be written back into it unseen (rule 12)."""
    stale = [rel for rel in NAMED if not old_path_mentions(ROOT, [rel])]
    assert stale == [], f"{stale} no longer name an old path: remove them from NAMED, and the walk will cover them"


def test_every_import_of_a_moved_client_reaches_the_package() -> None:
    bad, importers = imports_not_reaching(ROOT, earlier.tracked())
    assert importers >= 55, (
        f"only {importers} file(s) under OspreyFlow_Core import a client's name from {PACKAGE_NAME}: the walk found too few imports, or the importers were not repointed"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach the package by its name: {bad[:10]}"


_PLANTED_IMPORTS = {
    # (path of the file that held the line, the line as the tree wrote it, the line it has now)
    "the studio's calls, from the app": (
        WORKSPACE_SRC + "App.tsx",
        'import { fetchHandlingScheme } from "./ingest/api";',
        f'import {{ fetchHandlingScheme }} from "{PACKAGE_NAME}";',
    ),
    "the studio's calls, from a screen beside them": (
        WORKSPACE_SRC + "ingest/ProfileScreen.tsx",
        'import { fetchProfile } from "./api";',
        f'import {{ fetchProfile }} from "{PACKAGE_NAME}";',
    ),
    "the studio's calls, from a folder below": (
        WORKSPACE_SRC + "ingest/dag/PipelineStudio.tsx",
        'import { fetchDraft } from "../api";',
        f'import {{ fetchDraft }} from "{PACKAGE_NAME}";',
    ),
    "the studio's calls, from the inspector": (
        WORKSPACE_SRC + "inspector/linkHandling.ts",
        'import { fetchHandlingScheme } from "../ingest/api";',
        f'import {{ fetchHandlingScheme }} from "{PACKAGE_NAME}";',
    ),
    "the sources' calls, from the admin screen": (
        WORKSPACE_SRC + "admin/sections/Connections.tsx",
        'import { listSources } from "../../ingest/sources/api";',
        f'import {{ listSources }} from "{PACKAGE_NAME}";',
    ),
    "the sources' calls, beside them": (
        WORKSPACE_SRC + "ingest/sources/SourcePage.tsx",
        'import { sourceProfile } from "./api";',
        f'import {{ sourceProfile }} from "{PACKAGE_NAME}";',
    ),
    "the releases' calls, beside them": (
        WORKSPACE_SRC + "ingest/releases/ReleasesTab.tsx",
        'import { releaseName } from "./releasesApi";',
        f'import {{ releaseName }} from "{PACKAGE_NAME}";',
    ),
    "the maps' calls, from the section": (
        WORKSPACE_SRC + "admin/sections/Maps.tsx",
        'import { readMaps, type MapsApi } from "./MapsApi";',
        f'import {{ readMaps, type MapsApi }} from "{PACKAGE_NAME}";',
    ),
    "the models' calls, from a test": (
        WORKSPACE_SRC + "admin/sections/ModelsUsage.test.tsx",
        'import { readUsage } from "./ModelsApi";',
        f'import {{ readUsage }} from "{PACKAGE_NAME}";',
    ),
    "the update notice, from the system section": (
        WORKSPACE_SRC + "admin/sections/System.tsx",
        'import { updateWords } from "../updateNotice";',
        f'import {{ updateWords }} from "{PACKAGE_NAME}";',
    ),
    "a partial double of the studio's calls": (
        WORKSPACE_SRC + "ingest/map/MapEditor.rename.test.tsx",
        'vi.mock("../api", async (importOriginal) => {\n  const actual = await importOriginal<typeof import("../api")>();',
        f'vi.mock("{PACKAGE_NAME}", async (importOriginal) => {{\n  const actual = await importOriginal<typeof import("{PACKAGE_NAME}")>();',
    ),
    "a deep import into the package": (
        WORKSPACE_SRC + "admin/sections/Maps.tsx",
        'import { readMaps } from "../../../../../packages/glass-shared/src/admin/sections/MapsApi";',
        f'import {{ readMaps }} from "{PACKAGE_NAME}";',
    ),
    "an old path in a guide": (
        "OspreyFlow_Core/README.md",
        "The Studio's calls are in `apps/workspace/src/ingest/api.ts`; each takes the bearer token as an argument.",
        "The Studio's calls are in `packages/glass-shared/src/ingest/api.ts`; each takes the bearer token as an argument.",
    ),
    "an old path in a comment of a script": (
        "OspreyFlow_Core/harness/govuk_chrome.js",
        "(`updateWords` in `apps/workspace/src/admin/updateNotice.ts`, whose wording this follows).",
        "(`updateWords` in `packages/glass-shared/src/admin/updateNotice.ts`, whose wording this follows).",
    ),
    "a bare file name in a guide": (
        "OspreyFlow_Core/docs/administration-guide.md",
        "The maps screen reads `MapsApi.ts` and nothing else.",
        "The maps screen reads the maps client and nothing else.",
    ),
    "the sources' calls, written in segments": (
        APPS + "workspace/a11y/plants/run.mjs",
        'const sources = join(HERE, "..", "..", "src", "ingest", "sources", "api");',
        'const sources = join(HERE, "..", "..", "..", "..", "packages", "glass-shared", "src", "ingest", "sources", "api");',
    ),
}


@pytest.mark.parametrize("case", sorted(_PLANTED_IMPORTS))
def test_an_old_path_put_back_in_one_importer_is_found(case: str, tmp_path: Path) -> None:
    """Red for the two walks above (rule 15): each line the tree really held, put back in the file that held it (or one the
    move could have left it in). The same file with the new line is clean first, so the plant is what is found and not
    something else in the file. The package's own copies are in the tree under `tmp_path`, so the names are known."""
    rel, old_line, new_line = _PLANTED_IMPORTS[case]
    for client in WHOLE:
        copy = tmp_path / (SHARED + client)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text((ROOT / (SHARED + client)).read_text(encoding="utf-8"), encoding="utf-8")
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_line + "\n", encoding="utf-8")
    assert imports_not_reaching(tmp_path, [rel])[0] == [] and old_path_mentions(tmp_path, [rel]) == []
    target.write_text(old_line + "\n", encoding="utf-8")
    assert imports_not_reaching(tmp_path, [rel])[0] or old_path_mentions(tmp_path, [rel]), (
        f"neither walk finds {old_line!r} in {rel}"
    )


def test_a_file_that_names_no_client_is_not_counted_as_an_importer(tmp_path: Path) -> None:
    """The importers' floor means something only if a file that takes some other name from the package is not one."""
    for client in WHOLE:
        copy = tmp_path / (SHARED + client)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text((ROOT / (SHARED + client)).read_text(encoding="utf-8"), encoding="utf-8")
    rel = WORKSPACE_SRC + "theme/ThemeToggle.tsx"
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text(f'import {{ applyTheme }} from "{PACKAGE_NAME}";\n', encoding="utf-8")
    assert imports_not_reaching(tmp_path, [rel]) == ([], 0)
    (tmp_path / rel).write_text(f'import {{ fetchProfile }} from "{PACKAGE_NAME}";\n', encoding="utf-8")
    assert imports_not_reaching(tmp_path, [rel]) == ([], 1)


def test_every_import_reached_from_a_spec_resolves() -> None:
    """The Playwright collection check's own half: a spec that imports a file that is gone fails at collection, which no unit
    test runs. Every relative import, reached from any spec by any chain, names a file."""
    rels = earlier.tracked()
    specs = earlier.spec_files(rels)
    assert len(specs) >= 100, f"only {len(specs)} spec files found: the walk is not seeing the specs"
    missing, reached = earlier.unresolved_from_specs(ROOT, specs)
    assert reached >= 400, f"the walk reached only {reached} files: it is not following imports"
    assert missing == [], f"{len(missing)} import(s) name no file: {missing[:10]}"


def test_a_spec_that_imports_a_path_that_no_longer_exists_is_found(tmp_path: Path) -> None:
    """Red for the walk above, at the shapes the move could leave: a spec's harness still importing a client by the old path
    (the line the tree held in a harness under `keyboard/`), and the package's index exporting a file that is not there."""
    spec = APPS + "workspace/keyboard/admin-maps.spec.ts"
    harness = APPS + "workspace/keyboard/admin-maps-harness.tsx"
    files = {
        spec: 'import { mount } from "./admin-maps-harness";\n',
        harness: f'import {{ readMaps }} from "{PACKAGE_NAME}";\n',
        SHARED + "index.ts": 'export * from "./admin/sections/MapsApi";\n',
        SHARED + "admin/sections/MapsApi.ts": "export const readMaps = 1;\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == []
    # The old line, put back: the client is no longer at that path.
    (tmp_path / harness).write_text('import { readMaps } from "../src/admin/sections/MapsApi";\n', encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [f"{harness}: ../src/admin/sections/MapsApi"]
    # The index exporting a file the package does not hold.
    (tmp_path / harness).write_text(f'import {{ readMaps }} from "{PACKAGE_NAME}";\n', encoding="utf-8")
    (tmp_path / SHARED / "admin" / "sections" / "MapsApi.ts").unlink()
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [f"{SHARED}index.ts: ./admin/sections/MapsApi"]


# ------------------------------------------------------------------------------------------------------- the images

WORKSPACE_IMAGE = CORE / "apps" / "workspace" / "Dockerfile"


def copy_sources(dockerfile: str) -> list[str]:
    """The source argument of every `COPY` in a Dockerfile that copies from the build context (not `--from=`)."""
    sources = []
    for line in re.sub(r"\\\n", " ", dockerfile).splitlines():
        words = line.split()
        if not words or words[0].upper() != "COPY" or any(w.startswith("--from=") for w in words):
            continue
        args = [w for w in words[1:] if not w.startswith("--")]
        sources.extend(args[:-1])
    return sources


def stale_copies(dockerfile: str) -> list[str]:
    """The sources a stage copies that name the place a client moved from: the file itself, or the folder only it filled."""
    old = {"/".join(p.split("/")[3:]) for p in OLD_OF.values()}  # `ingest/api.ts` under `apps/workspace/src/`
    return sorted(
        src
        for src in copy_sources(dockerfile)
        if src.startswith("apps/workspace/src/") and src.removeprefix("apps/workspace/src/") in old
    )


def test_no_image_copies_a_path_that_moved() -> None:
    """Neither image names a moved file in a `COPY` (the workspace image copies `apps/workspace` whole and the package's
    source beside it; the harness image names parts of the workspace, and none of them is a client), and each copies the
    package's source."""
    for dockerfile in (WORKSPACE_IMAGE, image.DOCKERFILE):
        text = dockerfile.read_text(encoding="utf-8")
        assert stale_copies(text) == [], f"{dockerfile.name} copies a path that moved"
        assert "packages/glass-shared/src" in copy_sources(text), (
            f"{dockerfile.parent.name}/{dockerfile.name} does not copy packages/glass-shared/src"
        )


def test_the_harness_image_copies_what_the_clients_need() -> None:
    """The harness frontend reaches the package's index, and by it every client: each file it reaches is under a `COPY`, and
    every `COPY` of a workspace path still names something that exists and is reached. The walk reaches the six clients."""
    reached = image._reached_workspace_files()
    copied = image._copied_paths()
    assert image._missing(copied, reached) == []
    assert earlier.dangling(copied, reached) == []
    names = {str(p.relative_to(CORE.resolve())) for p in reached}
    for rel in WHOLE:
        assert f"packages/glass-shared/src/{rel}" in names, f"the walk does not reach the package's {rel}"


def test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found() -> None:
    """Red for the checks above (rule 15), on the real stages: the package's line taken out of the harness image (the clients
    the index reaches are missing), each line a moved file once needed put in (each copies a file that is not there), and the
    same two faults on the workspace image."""
    real = image.DOCKERFILE.read_text(encoding="utf-8")
    reached = image._reached_workspace_files()
    assert stale_copies(real) == []
    assert (
        image._missing(image._copied_paths(real), reached) == []
        and earlier.dangling(image._copied_paths(real), reached) == []
    )

    shared = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    assert shared in real
    missing = image._missing(image._copied_paths(real.replace(shared, "", 1)), reached)
    for rel in WHOLE:
        assert f"packages/glass-shared/src/{rel}" in missing, f"{rel} is not found missing"
    assert "packages/glass-shared/src/index.ts" in missing

    for rel in ("ingest/api.ts", "ingest/sources/api.ts", "admin/updateNotice.ts"):
        line = f"COPY apps/workspace/src/{rel} ./apps/workspace/src/{rel}\n"
        stale = real.replace(shared, shared + line, 1)
        assert stale_copies(stale) == [f"apps/workspace/src/{rel}"]
        assert earlier.dangling(image._copied_paths(stale), reached) == [f"apps/workspace/src/{rel}"]

    workspace = WORKSPACE_IMAGE.read_text(encoding="utf-8")
    assert stale_copies(workspace) == []
    package_line = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    assert package_line in workspace
    assert "packages/glass-shared/src" not in copy_sources(workspace.replace(package_line, "", 1))
    assert stale_copies(workspace + "COPY apps/workspace/src/ingest/releases/releasesApi.ts ./x\n") == [
        "apps/workspace/src/ingest/releases/releasesApi.ts"
    ]
