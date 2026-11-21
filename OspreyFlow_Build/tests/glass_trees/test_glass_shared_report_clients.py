"""The report, export, alert and pattern Conduit clients live in `packages/glass-shared`, and nothing names the place
they came from (ADR-152 decision 6, "the Conduit client"; slice PL4d3a, the sixth of the PL4 slices after A, B, B2, B3,
C, D1 and D2; the owner's rulings of 20 and 21 November 2026).

Twelve plain TypeScript files moved whole from `OspreyFlow_Core/apps/workspace/src/` to
`OspreyFlow_Core/packages/glass-shared/src/`, at the same place under it, their bytes unchanged but for the import lines:

* `reports/api.ts`, `caseHttp.ts`, `dashboards.ts`, `trendsApi.ts`, `packsApi.ts` (the reports' calls) and
  `reports/packText.ts` (the words a pack and a trend are described in);
* `export/api.ts` (the export call), `alerts/api.ts` (the alert queue, rules and lists), `alerts/names.ts` and
  `alerts/closingReasons.ts` (the words `packText` uses), `patterns/api.ts` and `models/modelDeadline.ts`.

Each calls `fetch` against the Conduit (or is a helper of one that does) and takes the bearer token as an argument. None
touches the page, and none imports React, a drawing library or a store.

**One line left a React file.** `export/api.ts` took `WITHHELD_SENTENCE` from `statusbar/StatusBar.tsx`, which is React.
The constant moved, byte for byte, to a new plain module of the package, `export/withheldSentence.ts`, and
`StatusBar.tsx` imports it from the package; nothing else in that file changed
(`test_the_withheld_sentence_is_the_bases_byte_for_byte`, shown red by
`test_a_withheld_sentence_that_changed_or_a_status_bar_that_changed_more_is_found`).

Every importer followed (the workspace, its tests, the export-capture and keyboard harnesses outside `src/`). The tests
stayed in the workspace. This file is the proof that none was left behind and that each guard can fail.

Which test fails if the invariant is broken (rule 12):

* a file is not where it should be, an old one is back, or the index does not export it:
  `test_the_twelve_clients_are_in_the_package_and_not_in_the_workspace`;
* a file of the package importing React or a drawing library, or a file of the workspace or the harness, or a schema
  import that no longer resolves: the D2 file's `test_the_package_s_clients_import_no_react_and_no_workspace_path` reads
  every file of the package, these twelve too; here `test_the_new_clients_are_among_the_files_that_check_reads` proves it
  does, and `test_a_react_or_workspace_import_in_a_moved_client_is_found` plants one in each;
* a client changed in more than its import lines at the commit that moved it:
  `test_the_move_changed_no_line_but_the_imports`;
* a file of any kind naming an old path: `test_no_tracked_file_names_an_old_path`;
* an importer that still reaches an old path, or reaches into the package's folder instead of its name:
  `test_every_import_of_a_moved_client_reaches_the_package`, with `test_an_old_path_put_back_in_one_importer_is_found`;
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
  `test_a_stage_with_a_stale_copy_or_a_copy_gone_is_found`.

**This file walks:** `git ls-files` over the whole repository (the old-path test); the tracked `.ts`, `.tsx`, `.mts`,
`.mjs`, `.js` and `.jsx` files under `OspreyFlow_Core/apps/` (the import tests, the spec walk, which starts at every tracked
`*.spec.ts` and `*.spec.tsx` in `apps/workspace` and `apps/harness` and follows their imports) and under
`OspreyFlow_Core/packages/glass-shared/src` (the moved files, the index, the package's own imports);
`apps/workspace/src` and `packages/glass-shared/src` through the two Python word-walkers it imports (each in a
temporary copy); `apps/workspace/Dockerfile` and `harness/Dockerfile` by name; `copyTextsTestKit.ts` by name; the git
history of the rename (`git log`, `git show`); and temporary copies built inside `tmp_path` for the plants (written there,
never in the repository), among them copies of `packages/glass-shared/src` for the gate plants.
"""

# The planted lines below are the real call-site shapes, kept on one line as the tree wrote them (rule 15), and the
# prose beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import re
import shutil
from collections import Counter
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

#: The twelve files that moved whole: where each is now (relative to `SHARED`; its old place is the same relative path
#: under `apps/workspace/src/`).
WHOLE = (
    "reports/api.ts",
    "reports/caseHttp.ts",
    "reports/dashboards.ts",
    "reports/trendsApi.ts",
    "reports/packsApi.ts",
    "reports/packText.ts",
    "export/api.ts",
    "alerts/api.ts",
    "alerts/names.ts",
    "alerts/closingReasons.ts",
    "patterns/api.ts",
    "models/modelDeadline.ts",
)
OLD_OF = {rel: WORKSPACE_SRC + rel for rel in WHOLE}
_OLD_STEMS = {old.removesuffix(".ts") for old in OLD_OF.values()}

#: The one new module: the constant `export/api.ts` took from a React file.
SENTENCE_MODULE = "export/withheldSentence.ts"
STATUS_BAR = WORKSPACE_SRC + "statusbar/StatusBar.tsx"
#: What stays: the stray backup beside the export client belongs to the next slice (D3c).
BACKUP = WORKSPACE_SRC + "export/api.ts.bak"

#: The places that may name an old path because they are a record of the past: the decision log, and the build record
#: under `process/`. They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone
#: (`test_every_named_exception_still_has_its_reason`).
NAMED = {
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_glass_shared_report_clients.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

_NAME_FORMS = (
    r"reports/api",
    r"reports/caseHttp",
    r"reports/dashboards",
    r"reports/trendsApi",
    r"reports/packsApi",
    r"reports/packText",
    r"export/api",
    r"alerts/api",
    r"alerts/names",
    r"alerts/closingReasons",
    r"patterns/api",
    r"models/modelDeadline",
)
#: Not a route (`/v1/reports/dashboards` is the Conduit's address, not a file), and not `api.test.ts`, `packText.test.ts` or the like (the tests stayed in the workspace, beside where the file was), and
#: not `api.ts.bak` (the backup stays until D3c).
_TEXT_FORM = re.compile(
    rf"(?<!glass-shared/src/)(?<!v1/)(?<![\w-])(?:{'|'.join(_NAME_FORMS)})\b(?!\.(?:css|test\.|spec\.|py|ts\.bak|bak))"
)
#: A bare file name with its extension, as a guide writes it: `packText.ts`.
_FILE_FORM = re.compile(
    r"(?<![\w/.-])(?:packText|trendsApi|packsApi|caseHttp|closingReasons|modelDeadline|names)\.ts\b"
)
#: The segments of one written apart: `join(HERE, "..", "src", "reports", "api")`, Python's `/ "reports" / "api.ts"`. Not
#: `"reports", "dashboards"`: that pair is two of the Glass's view names in a list, never a path.
_SEGMENT_FORM = re.compile(
    r"""["'](?:reports["']\s*[,/]\s*["'](?:api|caseHttp|trendsApi|packsApi|packText)"""
    r"""|export["']\s*[,/]\s*["']api|alerts["']\s*[,/]\s*["'](?:api|names|closingReasons)"""
    r"""|patterns["']\s*[,/]\s*["']api|models["']\s*[,/]\s*["']modelDeadline)(?:\.ts)?["']"""
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
                    continue  # `"glass-shared", "src", "reports", "api"` is the new place written apart
                line = text.count("\n", 0, hit.start()) + 1
                found.append((rel, line, text.splitlines()[line - 1].strip()))
    return sorted(set(found))


def _kept_out(rel: str) -> bool:
    if rel in NAMED:
        return True
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in HISTORY)


# ----------------------------------------------------------------------------------------------------- the imports

_PACKAGE_IMPORT = re.compile(rf"""["']{re.escape(PACKAGE_NAME)}(/[^"']*)?["']""")


def _exported_names(text: str) -> set[str]:
    return set(
        re.findall(
            r"^export\s+(?:async\s+)?(?:function|const|let|class|type|interface|enum)\s+(\w+)",
            text,
            re.M,
        )
    )


def _client_names(root: Path) -> set[str]:
    """Every name the twelve clients export, read from the package's copies (the old ones are gone)."""
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
    names = _client_names(root)
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


# ----------------------------------------------------------------------------------------------- the real tree: cases


def test_the_twelve_clients_are_in_the_package_and_not_in_the_workspace() -> None:
    names = earlier.tracked()
    for rel in WHOLE:
        new, old = SHARED + rel, OLD_OF[rel]
        assert (ROOT / new).is_file(), f"{new} is not in packages/glass-shared/src"
        assert not (ROOT / old).exists(), f"{old} is still where it was"
        assert new in names and old not in names
    assert SHARED + SENTENCE_MODULE in names, f"{SHARED}{SENTENCE_MODULE} is not in the package"
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    for rel in (*WHOLE, SENTENCE_MODULE):
        stem = "./" + rel.removesuffix(".ts")
        assert re.search(
            rf"""^export\s+(?:\*|\{{[^}}]*\}})\s+from\s+["']{re.escape(stem)}["'];""", index, re.M
        ), f"packages/glass-shared/src/index.ts does not export {stem}"
    assert BACKUP in names, "the backup beside the export client is D3c's: it is left where it is"


def test_the_new_clients_are_among_the_files_that_check_reads() -> None:
    """D2's check walks every `.ts` file of the package (tests apart): the twelve and the sentence's module are in it."""
    sources = clients._package_sources()
    for rel in (*WHOLE, SENTENCE_MODULE):
        assert SHARED + rel in sources, f"{rel} is not among the package's sources"
    problems = [
        p
        for rel in (*WHOLE, SENTENCE_MODULE)
        for p in clients.package_import_problems(ROOT, SHARED + rel)
    ]
    assert problems == [], f"{len(problems)} import(s) the package may not make: {problems[:10]}"


def test_a_react_or_workspace_import_in_a_moved_client_is_found(tmp_path: Path) -> None:
    """Red for the check above (rule 15): in each of the twelve, the lines the client would carry if it grew a hook, a
    store, or a path into the workspace. Each file is clean first, so the plant is what is found."""
    generated = "OspreyFlow_Core/packages/schemas/generated"
    (tmp_path / generated).mkdir(parents=True)
    (tmp_path / (generated + "/index.ts")).write_text("export {};\n", encoding="utf-8")
    plants = (
        'import { useEffect } from "react";\n',
        'import { WITHHELD_SENTENCE } from "../statusbar/StatusBar";\n',
        'import { create } from "zustand";\n',
        'import BY_ROLE from "../../../../apps/workspace/src/shell/placesByRole.json";\n',
        'import type { Node } from "../../../../packages/schemas/generated";\n',
    )
    for rel in (*WHOLE, SENTENCE_MODULE):
        real = (ROOT / (SHARED + rel)).read_text(encoding="utf-8")
        target = tmp_path / (SHARED + rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(real, encoding="utf-8")
        for dependency in (
            *WHOLE,
            SENTENCE_MODULE,
            "/".join(("workingset", "models.ts")),
        ):  # so a sibling import resolves
            sibling = tmp_path / (SHARED + dependency)
            sibling.parent.mkdir(parents=True, exist_ok=True)
            if not sibling.exists():
                sibling.write_text(
                    (ROOT / (SHARED + dependency)).read_text(encoding="utf-8"), encoding="utf-8"
                )
        assert clients.package_import_problems(tmp_path, SHARED + rel) == [], (
            f"{rel} is not clean to begin with"
        )
        for line in plants:
            target.write_text(line + real, encoding="utf-8")
            assert clients.package_import_problems(tmp_path, SHARED + rel), (
                f"{line!r} is not found in {rel}"
            )
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


_SENTENCE_LINE = re.compile(r'^export const WITHHELD_SENTENCE = ".*";$', re.M)


def sentence_problems(before: str, after: str, module: str) -> list[str]:
    """What is wrong with moving the constant out of the status bar's file: `before` and `after` are that file on either
    side of the move, `module` the package's new module. The constant's line must be the one the status bar held, the status
    bar must have lost that line and gained only imports, and nothing else of it may differ."""
    held = _SENTENCE_LINE.findall(before)
    if len(held) != 1:
        return [
            f"the status bar held {len(held)} definitions of the sentence before the move, not one"
        ]
    problems = []
    if held[0] not in module.splitlines():
        problems.append("the package's module does not hold the status bar's line byte for byte")
    if _SENTENCE_LINE.findall(after):
        problems.append("the status bar still defines the sentence")
    was, now = (
        Counter(ln for ln in before.splitlines() if ln.strip()),
        Counter(ln for ln in after.splitlines() if ln.strip()),
    )
    removed, added = was - now, now - was
    if removed != Counter({held[0]: 1}):
        problems.append(f"the status bar lost more than the constant's line: {sorted(removed)[:3]}")
    for line in added:
        if not (line.startswith("import ") and f'"{PACKAGE_NAME}"' in line) and not line.startswith(
            ("  ", "}", ")")
        ):
            problems.append(
                f"the status bar gained a line that is not an import of the package: {line!r}"
            )
    if not any(
        f'"{PACKAGE_NAME}"' in ln and "WITHHELD_SENTENCE" in ln for ln in after.splitlines()
    ):
        # a multi-line import names the constant on a line of its own
        if not re.search(
            rf'import\s*\{{[^}}]*\bWITHHELD_SENTENCE\b[^}}]*\}}\s*from\s*"{re.escape(PACKAGE_NAME)}"',
            after,
        ):
            problems.append("the status bar does not import the sentence from the package")
    return problems


def test_the_withheld_sentence_is_the_bases_byte_for_byte() -> None:
    """The base is the commit before the one that moved `export/api.ts`: the sentence the status bar held there is the line
    in the package's module now, and the status bar changed in nothing but that line and the import that replaces it."""
    earlier._skip_if_shallow()
    new = SHARED + "export/api.ts"
    commit = earlier._git(
        "log", "--follow", "-M", "--diff-filter=R", "--format=%H", "-1", "--", new
    ).strip()
    assert commit, f"git finds no rename into {new}: the file was not moved with `git mv`"
    before = earlier._git("show", f"{commit}^:{STATUS_BAR}")
    after = earlier._git("show", f"{commit}:{STATUS_BAR}")
    module = earlier._git("show", f"{commit}:{SHARED}{SENTENCE_MODULE}")
    assert sentence_problems(before, after, module) == []
    # And the module as it is now still holds the base's line.
    assert (
        _SENTENCE_LINE.findall(before)[0]
        in (ROOT / (SHARED + SENTENCE_MODULE)).read_text(encoding="utf-8").splitlines()
    )


def test_a_withheld_sentence_that_changed_or_a_status_bar_that_changed_more_is_found() -> None:
    """Red for the comparison above (rule 15), on the lines the real status bar has: the constant moved cleanly, the
    sentence reworded, a second line lost, a line added that is not an import, the old definition left behind."""
    line = (
        'export const WITHHELD_SENTENCE = "This case holds material you are not cleared to see.";'
    )
    before = f'import {{ useState }} from "react";\n\nexport interface P {{\n  a: number;\n}}\n\n{line}\n\nexport function StatusBar() {{\n  return 1;\n}}\n'
    after = before.replace(line + "\n\n", "").replace(
        'import { useState } from "react";\n',
        f'import {{ useState }} from "react";\n\nimport {{ WITHHELD_SENTENCE }} from "{PACKAGE_NAME}";\n',
    )
    module = f"// header\n{line}\n"
    assert sentence_problems(before, after, module) == []
    assert sentence_problems(before, after, module.replace("cleared", "allowed")), (
        "a reworded sentence is not found"
    )
    assert sentence_problems(
        before, after, module.replace("  ", " ").replace("export const", "export  const")
    ), "a changed line is not found"
    assert sentence_problems(before, after.replace("return 1;", "return 2;"), module), (
        "a second changed line is not found"
    )
    assert sentence_problems(before, before, module), "the old definition left behind is not found"
    assert sentence_problems(
        before,
        after.replace(f'import {{ WITHHELD_SENTENCE }} from "{PACKAGE_NAME}";\n', ""),
        module,
    ), "a missing import is not found"
    assert sentence_problems(before, after.replace(PACKAGE_NAME, "./elsewhere"), module), (
        "an import from elsewhere is not found"
    )


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
    assert importers >= 40, (
        f"only {importers} file(s) under OspreyFlow_Core import a client's name from {PACKAGE_NAME}: the walk found too few imports, or the importers were not repointed"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach the package by its name: {bad[:10]}"


_PLANTED_IMPORTS = {
    # (path of the file that held the line, the line as the tree wrote it, the line it has now)
    "the reports' calls, from a screen beside them": (
        WORKSPACE_SRC + "reports/PublishedTab.tsx",
        'import type { ReportsApi } from "./api";',
        f'import type {{ ReportsApi }} from "{PACKAGE_NAME}";',
    ),
    "the reports' calls, from the boards": (
        WORKSPACE_SRC + "boards/BoardAlerts.tsx",
        'import { fetchReport, type ReportsApi } from "../reports/api";',
        f'import {{ fetchReport, type ReportsApi }} from "{PACKAGE_NAME}";',
    ),
    "the case calls, from the brief": (
        WORKSPACE_SRC + "investigation/briefApi.ts",
        'import { fieldOf, refusal, send, type Reply } from "../reports/caseHttp";',
        f'import {{ fieldOf, refusal, send, type Reply }} from "{PACKAGE_NAME}";',
    ),
    "the trends' calls, from the brief": (
        WORKSPACE_SRC + "investigation/briefApi.ts",
        'import { listTrends } from "../reports/trendsApi";',
        f'import {{ listTrends }} from "{PACKAGE_NAME}";',
    ),
    "the dashboards' calls, beside them": (
        WORKSPACE_SRC + "reports/EmbeddedDashboards.tsx",
        'import { type DashboardsApi, dashboardGuestToken, listEmbeddedDashboards } from "./dashboards";',
        f'import {{ type DashboardsApi, dashboardGuestToken, listEmbeddedDashboards }} from "{PACKAGE_NAME}";',
    ),
    "the packs' calls, beside them": (
        WORKSPACE_SRC + "reports/ExportControl.tsx",
        'import { exportPack } from "./packsApi";',
        f'import {{ exportPack }} from "{PACKAGE_NAME}";',
    ),
    "the pack words, from the print document": (
        WORKSPACE_SRC + "reports/TrendChart.tsx",
        'import { formatDay, formatNumber, periodKey, periodsOf, trendSentence } from "./packText";',
        f'import {{ formatDay, formatNumber, periodKey, periodsOf, trendSentence }} from "{PACKAGE_NAME}";',
    ),
    "the pack words, from a harness outside src": (
        APPS + "workspace/keyboard/alert-reporting-harness.tsx",
        'import { WITHHELD_ITEMS_SENTENCE } from "../src/reports/packText";',
        f'import {{ WITHHELD_ITEMS_SENTENCE }} from "{PACKAGE_NAME}";',
    ),
    "the export call, from a harness outside src": (
        APPS + "workspace/export-capture/harness.tsx",
        'import type { ExportMark } from "../src/export/api";',
        f'import type {{ ExportMark }} from "{PACKAGE_NAME}";',
    ),
    "the export call, from the canvas": (
        WORKSPACE_SRC + "canvas/GlassCanvas.tsx",
        'import type { ExportMark } from "../export/api";',
        f'import type {{ ExportMark }} from "{PACKAGE_NAME}";',
    ),
    "the alert calls, from the ownership client": (
        WORKSPACE_SRC + "ownership/api.ts",
        'import type { CanvasOutcome } from "../alerts/api";',
        f'import type {{ CanvasOutcome }} from "{PACKAGE_NAME}";',
    ),
    "the alert calls, from the watches": (
        WORKSPACE_SRC + "watches/GlassWatchActions.tsx",
        'import { raiseAlert } from "../alerts/api";',
        f'import {{ raiseAlert }} from "{PACKAGE_NAME}";',
    ),
    "the alert words, from the canvas": (
        WORKSPACE_SRC + "canvas/labelChoices.ts",
        'import { TYPOLOGY_LABELS } from "../alerts/names";',
        f'import {{ TYPOLOGY_LABELS }} from "{PACKAGE_NAME}";',
    ),
    "the closing reasons, beside them": (
        WORKSPACE_SRC + "alerts/AlertQueue.tsx",
        'import { CLOSING_REASONS, closingReasonLabel, type ClosingReason } from "./closingReasons";',
        f'import {{ CLOSING_REASONS, closingReasonLabel, type ClosingReason }} from "{PACKAGE_NAME}";',
    ),
    "the pattern calls, from the monitor": (
        WORKSPACE_SRC + "watches/MonitorPanel.tsx",
        'import { listPatterns } from "../patterns/api";',
        f'import {{ listPatterns }} from "{PACKAGE_NAME}";',
    ),
    "the model deadline, from the reader": (
        WORKSPACE_SRC + "reader/readerApi.ts",
        'import { modelDeadline, unreachedWords } from "../models/modelDeadline";',
        f'import {{ modelDeadline, unreachedWords }} from "{PACKAGE_NAME}";',
    ),
    "a dynamic import of the pack words": (
        WORKSPACE_SRC + "reports/packAlert.test.tsx",
        'const { trendSentence } = await import("./packText");',
        f'const {{ trendSentence }} = await import("{PACKAGE_NAME}");',
    ),
    "a deep import into the package": (
        WORKSPACE_SRC + "reports/PacksTab.tsx",
        'import { listPacks } from "../../../../packages/glass-shared/src/reports/packsApi";',
        f'import {{ listPacks }} from "{PACKAGE_NAME}";',
    ),
    "an old path in a guide": (
        "OspreyFlow_Core/README.md",
        "The reports' calls are in `apps/workspace/src/reports/api.ts`; each takes the bearer token as an argument.",
        "The reports' calls are in `packages/glass-shared/src/reports/api.ts`; each takes the bearer token as an argument.",
    ),
    "an old path in a comment of a script": (
        "OspreyFlow_Core/harness/govuk_chrome.js",
        "(`TYPOLOGY_LABELS` in `apps/workspace/src/alerts/names.ts`, whose wording this follows).",
        "(`TYPOLOGY_LABELS` in `packages/glass-shared/src/alerts/names.ts`, whose wording this follows).",
    ),
    "a bare file name in a guide": (
        "OspreyFlow_Core/docs/administration-guide.md",
        "The pack text lives in `packText.ts` and nowhere else.",
        "The pack text lives in the pack words module and nowhere else.",
    ),
    "the alert calls, written in segments": (
        APPS + "workspace/a11y/plants/run.mjs",
        'const alerts = join(HERE, "..", "..", "src", "alerts", "api");',
        'const alerts = join(HERE, "..", "..", "..", "..", "packages", "glass-shared", "src", "alerts", "api");',
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
    assert (
        imports_not_reaching(tmp_path, [rel])[0] == [] and old_path_mentions(tmp_path, [rel]) == []
    )
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
    (tmp_path / rel).write_text(
        f'import {{ applyTheme }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
    )
    assert imports_not_reaching(tmp_path, [rel]) == ([], 0)
    (tmp_path / rel).write_text(
        f'import {{ listPatterns }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
    )
    assert imports_not_reaching(tmp_path, [rel]) == ([], 1)


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
    (the line the tree held in `keyboard/alert-reporting-harness.tsx`), and the index exporting a file that is not there."""
    spec = APPS + "workspace/keyboard/alert-reporting.spec.ts"
    harness = APPS + "workspace/keyboard/alert-reporting-harness.tsx"
    files = {
        spec: 'import { mount } from "./alert-reporting-harness";\n',
        harness: f'import {{ WITHHELD_ITEMS_SENTENCE }} from "{PACKAGE_NAME}";\n',
        SHARED + "index.ts": 'export * from "./reports/packText";\n',
        SHARED + "reports/packText.ts": "export const WITHHELD_ITEMS_SENTENCE = 1;\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == []
    (tmp_path / harness).write_text(
        'import { WITHHELD_ITEMS_SENTENCE } from "../src/reports/packText";\n', encoding="utf-8"
    )
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [
        f"{harness}: ../src/reports/packText"
    ]
    (tmp_path / harness).write_text(
        f'import {{ WITHHELD_ITEMS_SENTENCE }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
    )
    (tmp_path / SHARED / "reports" / "packText.ts").unlink()
    assert earlier.unresolved_from_specs(tmp_path, [spec])[0] == [
        f"{SHARED}index.ts: ./reports/packText"
    ]


# ------------------------------------------------------------------------------------------------------- the images

WORKSPACE_IMAGE = CORE / "apps" / "workspace" / "Dockerfile"


def stale_copies(dockerfile: str) -> list[str]:
    """The sources a stage copies that name the place a client moved from: the file itself."""
    old = {
        "/".join(p.split("/")[4:]) for p in OLD_OF.values()
    }  # `reports/api.ts` under `apps/workspace/src/`
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
    for rel in (*WHOLE, SENTENCE_MODULE):
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
    for rel in (*WHOLE, SENTENCE_MODULE):
        assert f"packages/glass-shared/src/{rel}" in missing, f"{rel} is not found missing"

    for rel in ("reports/api.ts", "alerts/api.ts", "models/modelDeadline.ts"):
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
    assert stale_copies(workspace + "COPY apps/workspace/src/patterns/api.ts ./x\n") == [
        "apps/workspace/src/patterns/api.ts"
    ]


# --------------------------------------------------------------------------------------------------- the four gates

#: The files each gate read on main before this move: the number each reported or, where it reports none, the files its own
#: rules select (measured on 21 November 2026, on the tip PL4d3a started from, the same figures as before D2). The twelve
#: clients moved from a folder each gate reads to another it reads, so the numbers do not fall: none may.
FILES_BEFORE = {"colour-drift": 488, "design-check": 897, "ui-words": 495, "no-branches": 1742}


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
        "alerts/api.ts",
        '\nexport const STRIPE = { background: "#12ab34", padding: 8 };\n',
    )
    assert colour_drift_check.main() == 1
    assert "packages/glass-shared/src/alerts/api.ts:" in capsys.readouterr().out


def test_the_design_detector_reports_a_plant_in_a_moved_client(
    shared_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(design_check, "SCANNED", [shared_copy])
    assert design_check.unexcused(design_check.detect(design_check.SCANNED)) == [], (
        "the clean copy already has findings"
    )
    earlier._append(
        shared_copy,
        "reports/dashboards.ts",
        "\nexport const TOAST_STYLE = {\n"
        '  background: "var(--surface-raised)", borderLeft: "3px solid var(--error)", borderRadius: "8px",\n'
        '  padding: "12px 16px", boxShadow: "var(--overlay-shadow)",\n'
        "};\n",
    )
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [
        ("dashboards.ts", "side-tab")
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
    earlier._append(shared_copy, "reports/packText.ts", '\nexport const LABEL = "Target model";\n')
    assert ui_words_check.main() == 1
    assert "packages/glass-shared/src/reports/packText.ts:" in capsys.readouterr().out


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
        shared_copy, "patterns/api.ts", '\nexport const BRANCH_CASE = "branch-by-filter";\n'
    )
    assert no_branches_check.main() == 1
    assert f"{top}/patterns/api.ts:" in capsys.readouterr().out


# -------------------------------------------------------------------------------------------------- the word-walkers

#: The twelve as (folder, stem) pairs, never written as a path (the old-path scan reads the other walkers' tables too).
_MOVED = {
    "reports": ("api", "caseHttp", "dashboards", "trendsApi", "packsApi", "packText"),
    "export": ("api",), "alerts": ("api", "names", "closingReasons"), "patterns": ("api",), "models": ("modelDeadline",),
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
        (root / "alerts").mkdir(parents=True)
        (root / "alerts" / "names.ts").write_text(
            'export const word = "Clear view";\n'
            if n == planted_in
            else "export const word = 1;\n",
            encoding="utf-8",
        )
    expected = "alerts/names.ts" if planted_in == 0 else "shared:alerts/names.ts"
    assert navigation.old_view_words_on_screen(navigation.glass_sources(roots)) == [
        f"{expected}: 'Clear view'"
    ]


KIT = CORE / "apps" / "workspace" / "src" / "copyTextsTestKit.ts"
_KIT_FOLDERS = re.compile(r"^export const MOVED_FOLDERS = /(.*)/;$", re.M)


def test_the_vitest_walkers_name_the_new_folders() -> None:
    """`copyWords`, `copyNoClient` and `resolvedPrincipal` walk the kit's two roots, and each has a case that plants in a copy
    of every file the kit selects as a moved client. The kit selects them by the folders in `MOVED_FOLDERS`: every folder of
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
    for walker in ("copyWords.test.ts", "copyNoClient.test.ts", "auth/resolvedPrincipal.test.ts"):
        text = (KIT.parent / walker).read_text(encoding="utf-8")
        assert "REPORT_CLIENTS" in text and "plantedCopy" in text, (
            f"{walker} has no plant in the report clients"
        )
    # The selector is a real filter: a folder the clients are not in is not selected.
    assert not folders.search("/glass-shared/src/keyboard/actionRegistry.ts")
