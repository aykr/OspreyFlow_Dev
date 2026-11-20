"""The theme, the brand, the palette and the plain halves of three layout stores and the invite form live in
`packages/glass-shared`, and nothing names the place they came from (ADR-152 decision 6, "logic, stores, the panel
pattern"; slice PL4d1, the fourth of the PL4 slices after A, B, B2, B3 and C; the owner's rulings of 20 November 2026).

Seven plain TypeScript files moved whole from `OspreyFlow_Core/apps/workspace/src/` to
`OspreyFlow_Core/packages/glass-shared/src/`, at the same place under it, their bytes unchanged:

* `theme/theme.ts`, `brand/brand.ts`, `welcome/statement.ts`,
* `color/palette.ts`, `color/tokens.ts`, `color/oklab.ts`, `color/nodeGlyphs.ts`.

Four files were split: the plain half went to the package, the React half stayed where it was (I1: no React in the
package), and the half that stayed is only the hook (or the context) over what moved:

* `layout/layoutSizes.ts`: `useLayoutSizes` stays; `layout/panelOrder.ts`: `useSidePanelOrder` stays;
* `layout/sidePanelState.ts`: `useSidePanelMode` and `useWide` stay;
* `admin/inviter.ts`: `InviterContext` and `useInviter` stay.

Every importer followed (the workspace, the harness, the Playwright harnesses and showcases outside `src/`, every test).
The tests stayed in the workspace. This file is the proof that none was left behind and that each guard can fail.

Which test fails if the invariant is broken (rule 12):

* a whole file is not where it should be, an old one is back, or the index does not export it:
  `test_the_seven_files_are_in_the_package_and_not_in_the_workspace`;
* a split file's workspace half exports more than its hooks, a half is missing, or the package's half is not exported:
  `test_each_split_file_keeps_only_its_hooks_in_the_workspace`;
* a file of the package importing React (or a drawing library), as a value or a type, in either half or a whole file:
  `test_the_package_s_copies_import_no_react`, with `test_a_react_import_in_a_moved_file_is_found`;
* a moved file changed in more than its import lines, or a split file's two halves differing from the old file by
  more than the hook wiring written out in `ALLOWED`: `test_the_move_changed_no_line_but_the_imports`,
  `test_the_split_changed_no_line_but_the_hook_wiring`, each shown red by a planted second change;
* a file of any kind naming an old path, in a form the repository writes it in:
  `test_no_tracked_file_names_an_old_path` (the whole repository; only the decision log and the build record may keep
  one, and the files in `NAMED`, each with why);
* an importer that still reaches an old path, reaches into the package's folder instead of its name, or imports from a
  split file's workspace half anything but its hooks: `test_every_import_of_a_moved_module_reaches_the_package`;
* a spec, or a file one imports (by any chain of imports), naming a file that does not exist, which Playwright would
  meet at collection and no unit test would: `test_every_import_reached_from_a_spec_resolves` (the Playwright
  collection check's own half: the count of tests and files is measured by `npx playwright test --list`, which this
  file does not run);
* the harness image's `COPY` lines missing a file a moved file now needs, or still copying one that moved:
  `test_the_harness_image_copies_what_the_moved_files_need`;
* each of four gates (`make colour-drift-check`, `design-check`, `ui-words-check`, `no-branches-check`) that stops
  reading the moved files, or reads fewer files than before the move: `test_each_gate_reads_no_fewer_files_than_before`,
  and one plant for each gate in a **moved** file, shown clean beside it.

Each guard is shown red on a planted regression in the shape the real code writes it (rule 15): the planted lines are
lines the tree wrote on the day before the move, each placed at the path of a file that held one, and each case first
shows the same file clean with the new line.

**This file walks:** `git ls-files` over the whole repository (the old-path test); the tracked `.ts`, `.tsx`, `.mts`,
`.mjs`, `.js` and `.jsx` files under `OspreyFlow_Core/apps/` (the import tests, the spec walk, which starts at every
tracked `*.spec.ts` and `*.spec.tsx` in `apps/workspace` and `apps/harness` and follows their imports, and the
package's own index); `OspreyFlow_Core/packages/glass-shared/src` (the moved files, the exports); `harness/Dockerfile`
by name; the git history of the rename (`git log`, `git show`); and temporary copies of `packages/glass-shared/src` for
the gate plants (copied, never written: `make test` runs on several workers, and a plant in the real folder would be
seen by every reader of it).
"""

# The planted lines below are the real call-site shapes, kept on one line as the tree wrote them (rule 15), and the
# prose beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import difflib
import posixpath
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pytest
from tools import colour_drift_check, design_check, no_branches_check, ui_words_check
from tools.layout import CORE, ROOT

from tests.harness import test_harness_frontend_copies as image

PACKAGE = "OspreyFlow_Core/packages/glass-shared/"
SHARED = PACKAGE + "src/"
SHARED_SRC = CORE / "packages" / "glass-shared" / "src"
APPS = "OspreyFlow_Core/apps/"
WORKSPACE_SRC = APPS + "workspace/src/"
PACKAGE_NAME = "@ospreyflow/glass-shared"

#: The seven files that moved whole: where each is now (relative to `SHARED`; its old place is the same relative path
#: under `apps/workspace/src/`).
WHOLE = (
    "theme/theme.ts",
    "brand/brand.ts",
    "welcome/statement.ts",
    "color/palette.ts",
    "color/tokens.ts",
    "color/oklab.ts",
    "color/nodeGlyphs.ts",
)
OLD_OF = {rel: WORKSPACE_SRC + rel for rel in WHOLE}
_OLD_STEMS = {old.removesuffix(".ts") for old in OLD_OF.values()}

#: The four split files: the hooks (or the context) that stay in the workspace's file of the same name, and some of the
#: plain names the package's file of the same name must now export.
SPLIT = {
    "layout/layoutSizes.ts": (
        {"useLayoutSizes"},
        {
            "clamp",
            "normaliseLayoutSizes",
            "getLayoutSizes",
            "onLayoutSizesChange",
            "setSideWidth",
            "LayoutSizes",
        },
    ),
    "layout/panelOrder.ts": (
        {"useSidePanelOrder"},
        {
            "SIDE_PANEL_IDS",
            "normaliseSidePanelOrder",
            "getSidePanelOrder",
            "moveSidePanel",
            "onSidePanelOrderChange",
        },
    ),
    "layout/sidePanelState.ts": (
        {"useSidePanelMode", "useWide"},
        {
            "isWide",
            "setSidePanelMode",
            "toggleSidePanel",
            "forgetSidePanelForTest",
        },
    ),
    "admin/inviter.ts": (
        {"InviterContext", "useInviter"},
        {"Inviter", "InviterRead", "givableLevels", "givableCodes"},
    ),
}
_SPLIT_STEMS = {WORKSPACE_SRC + rel.removesuffix(".ts"): hooks for rel, (hooks, _) in SPLIT.items()}

#: The code lines (comments, blank lines, import statements and lines of only brackets are not code lines here) a split
#: adds and loses, and nothing else: `useSidePanelMode` subscribes to the module's private `listeners` and reads its
#: private `current`, so the package exports those two under names that say what they are, and the hook is the code it
#: was over them (imported under its old names). No line is lost.
ALLOWED = {
    "layout/sidePanelState.ts": {
        "added": ["export { listeners as sidePanelListeners, current as currentSidePanelMode };"],
        "lost": [],
    },
}

#: The places that may name an old path because they are a record of the past: the decision log, and the build record
#: under `process/`. They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone
#: (`test_every_named_exception_still_has_its_reason`).
NAMED = {
    # The citation check's allowlist: the decision log and the records name three old paths, and the allowlist says why
    # that is not a dead citation. It must name them to do so.
    "OspreyFlow_Build/tests/fixtures/citation_allowlist.txt": "the allowlist for the records that name the old paths",
    # The colour check's two mirror names, by name relative to the folder it scans (`packages/glass-shared/src`), and
    # the check's own unit test, which builds trees of its own with the same relative names.
    "OspreyFlow_Build/tools/colour_drift_check.py": "mirror names relative to the scanned root",
    "OspreyFlow_Build/tests/test_colour_drift_check.py": "synthetic trees with names relative to a root of their own",
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_glass_shared_plain_logic.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

_NAME_FORMS = (
    r"theme/theme",
    r"brand/brand",
    r"color/(?:palette|tokens|oklab|nodeGlyphs)",
    r"welcome/statement",
)
#: Not `color/tokens.test.ts`, `theme/theme.test.ts`: the tests stayed in the workspace, beside where the files were.
_TEXT_FORM = re.compile(
    rf"(?<!glass-shared/src/)(?<![\w-])(?:{'|'.join(_NAME_FORMS)})\b(?!\.(?:css|test\.|spec\.))"
)
#: The segments of one written apart: `join(HERE, "..", "src", "theme", "theme")`, Python's `/ "theme" / "theme.ts"`.
_SEGMENT_FORM = re.compile(
    r"""["'](?:theme["']\s*[,/]\s*["']theme|brand["']\s*[,/]\s*["']brand|color["']\s*[,/]\s*["'](?:palette|tokens|oklab|nodeGlyphs)"""
    r"""|welcome["']\s*[,/]\s*["']statement)(?:\.ts)?["']"""
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
        for form in (_TEXT_FORM, _SEGMENT_FORM):
            for hit in form.finditer(text):
                if form is _SEGMENT_FORM and _PACKAGE_SEGMENTS.search(text[: hit.start()]):
                    continue  # `"glass-shared", "src", "color", "palette"` is the new place written apart
                line = text.count("\n", 0, hit.start()) + 1
                found.append((rel, line, text.splitlines()[line - 1].strip()))
    return sorted(set(found))


def tracked(root: Path = ROOT) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return sorted(name for name in out.decode("utf-8").split("\0") if name)


def _kept_out(rel: str) -> bool:
    if rel in NAMED:
        return True
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in HISTORY)


# ----------------------------------------------------------------------------------------------------- the imports

_SOURCE_SUFFIXES = {".ts", ".tsx", ".mts", ".mjs", ".js", ".jsx"}
#: Any quoted relative path: an import, a re-export, `import("...")`, `vi.mock("...")`.
_RELATIVE = re.compile(r"""["'`](\.{1,2}/[^"'`\n]*)["'`]""")
_PACKAGE_IMPORT = re.compile(rf"""["']{re.escape(PACKAGE_NAME)}(/[^"']*)?["']""")
_STATIC_CLAUSE = re.compile(r"""(?:^|\n)\s*(?:import|export)\s+(?:type\s+)?([^;'"]*?)\s*from\s*$""")
_DESTRUCTURED = re.compile(r"""\{([^}]*)\}\s*=\s*await\s+import\(\s*$""")


def _target(rel: str, spec: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec.split("?", 1)[0]))


def _stem(path: str) -> str:
    return path.removesuffix(".tsx").removesuffix(".ts")


def _names(clause: str) -> set[str]:
    """The names a `{ a, type B as C }` clause takes from a module; anything not a plain named import is `*`."""
    clause = re.sub(r"/\*.*?\*/|//[^\n]*", "", clause, flags=re.S).strip()
    if not (clause.startswith("{") and clause.endswith("}")):
        return {"*"}
    names = set()
    for part in clause[1:-1].split(","):
        part = part.strip().removeprefix("type ").strip()
        if part:
            names.add(part.split(" as ")[0].strip())
    return names


def imports_not_reaching(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The relative specifiers that resolve to an old path, or into the package's folder instead of its name, or take
    from a split file's workspace half anything but its hooks; and the number of files that import the package by its
    name. Resolution is by path alone: an old file need not exist."""
    bad: list[str] = []
    importers = 0
    for rel in rels:
        if Path(rel).suffix not in _SOURCE_SUFFIXES or not rel.startswith("OspreyFlow_Core/"):
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
        if _PACKAGE_IMPORT.search(text) and not rel.startswith(SHARED):
            importers += 1
        for hit in _RELATIVE.finditer(text):
            target = _target(rel, hit.group(1))
            stem = _stem(target)
            before = text[max(0, hit.start() - 2000) : hit.start()]
            if stem in _OLD_STEMS:
                bad.append(f"{rel}: {hit.group(1)} (an old path)")
            elif target.startswith(PACKAGE) and not rel.startswith(PACKAGE):
                bad.append(f"{rel}: {hit.group(1)} (into the package's folder, not its name)")
            elif stem in _SPLIT_STEMS:
                found = _STATIC_CLAUSE.search(before) or _DESTRUCTURED.search(before)
                taken = _names(found.group(1)) if found else {"*"}
                extra = sorted(taken - _SPLIT_STEMS[stem])
                if extra:
                    bad.append(
                        f"{rel}: {hit.group(1)} takes {extra}, which the package holds now (only {sorted(_SPLIT_STEMS[stem])} stay)"
                    )
    return bad, importers


# ------------------------------------------------------------------------------------------------ the spec walk

_IMPORT_SPEC = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\(\s*)["']([^"'\n]+)["']""")
_RESOLVE_SUFFIXES = (
    "",
    ".ts",
    ".tsx",
    ".mts",
    ".js",
    ".mjs",
    ".jsx",
    ".json",
    ".css",
    "/index.ts",
    "/index.tsx",
)


def _resolve(root: Path, importer: str, spec: str) -> str | None:
    """The repository-relative file `spec` names from `importer`, `""` for a package installed by npm, `None` when a
    relative path names nothing."""
    if spec == PACKAGE_NAME:
        return SHARED + "index.ts"
    if not spec.startswith("."):
        return ""
    base = _target(importer, spec)
    for suffix in _RESOLVE_SUFFIXES:
        if (root / (base + suffix)).is_file():
            return base + suffix
    return None


def unresolved_from_specs(root: Path, specs: Iterable[str]) -> tuple[list[str], int]:
    """Every relative import, reached from the specs by any chain of imports, that names nothing; and the files reached."""
    pending = list(specs)
    seen: set[str] = set()
    missing: list[str] = []
    while pending:
        rel = pending.pop()
        if rel in seen:
            continue
        seen.add(rel)
        if Path(rel).suffix not in _SOURCE_SUFFIXES:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        code = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith(("//", "*", "/*"))
        )
        for spec in _IMPORT_SPEC.findall(code):
            found = _resolve(root, rel, spec)
            if found is None:
                missing.append(f"{rel}: {spec}")
            elif found:
                pending.append(found)
    return sorted(set(missing)), len(seen)


def spec_files(rels: Iterable[str]) -> list[str]:
    return [
        rel
        for rel in rels
        if rel.startswith((APPS + "workspace/", APPS + "harness/"))
        and re.search(r"\.spec\.tsx?$", rel)
    ]


# ------------------------------------------------------------------------------------------------ React, never, in the package

_FORBIDDEN_IMPORT = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\(\s*)["'](react|react-dom|react/[^"']*|react-dom/[^"']*|sigma|@sigma/[^"']*|maplibre-gl)["']"""
)


def forbidden_imports(text: str) -> list[str]:
    return [m.group(1) for m in _FORBIDDEN_IMPORT.finditer(text)]


def _package_files() -> list[str]:
    return [SHARED + rel for rel in (*WHOLE, *SPLIT)]


# ---------------------------------------------------------------------------------------------- how a move is compared

_IMPORT_LINE = re.compile(
    r"""^\s*(?:import\b.*|\}\s*from\s+["'][^"']*["'];?|.*\bfrom\s+["'][^"']*["'];?)$"""
)
_IMPORT_STATEMENT = re.compile(r"^import\s[^;]*?;[ \t]*$", re.M | re.S)
_PUNCTUATION = {"}", "},", "});", ");", "};", "]", "],", "];", ")", "),"}


def only_import_lines_changed(was: str, now: str) -> list[str]:
    """The changed lines that are not import lines."""
    return [
        d
        for d in difflib.ndiff(was.splitlines(), now.splitlines())
        if d[:2] in {"- ", "+ "} and not _IMPORT_LINE.match(d[2:])
    ]


def code_lines(text: str) -> Counter[str]:
    """The code lines of a file: no import statement, no comment, no blank line, no line of only brackets."""
    lines: Counter[str] = Counter()
    for line in _IMPORT_STATEMENT.sub("", text).splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("//", "/*", "*")) and stripped not in _PUNCTUATION:
            lines[stripped] += 1
    return lines


def split_differences(old: str, package: str, workspace: str) -> tuple[Counter[str], Counter[str]]:
    """The code lines the two halves hold that the old file did not (added), and that the old file held and neither half
    does (lost)."""
    was = code_lines(old)
    now = code_lines(package) + code_lines(workspace)
    return now - was, was - now


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def _skip_if_shallow() -> None:
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        pytest.skip("a shallow clone has no history: the move commit cannot be read")


# ----------------------------------------------------------------------------------------------- the real tree: cases


def test_the_seven_files_are_in_the_package_and_not_in_the_workspace() -> None:
    names = tracked()
    for rel in WHOLE:
        new, old = SHARED + rel, OLD_OF[rel]
        assert (ROOT / new).is_file(), f"{new} is not in packages/glass-shared/src"
        assert not (ROOT / old).exists(), f"{old} is still where it was"
        assert new in names and old not in names
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    for rel in (*WHOLE, *SPLIT):
        stem = "./" + rel.removesuffix(".ts")
        assert re.search(
            rf"""^export\s+(?:\*|\{{[^}}]*\}})\s+from\s+["']{re.escape(stem)}["'];""", index, re.M
        ), f"packages/glass-shared/src/index.ts does not export {stem}"


def _exported_names(text: str) -> set[str]:
    return set(
        re.findall(
            r"^export\s+(?:async\s+)?(?:function|const|let|class|type|interface)\s+(\w+)",
            text,
            re.M,
        )
    )


def split_problems(stays: str, moved: str, hooks: set[str], plain: set[str]) -> list[str]:
    """What is wrong with one split file: the workspace's half (`stays`) must export just the hooks, import React and take
    what it wraps from the package; the package's half (`moved`) must export the plain names and no hook."""
    problems = []
    if _exported_names(stays) != hooks:
        problems.append(
            f"the workspace half exports {sorted(_exported_names(stays))}, not just {sorted(hooks)}"
        )
    if not re.search(r"""\bfrom\s*["']react["']""", stays):
        problems.append("the workspace half no longer imports react")
    if not _PACKAGE_IMPORT.search(stays):
        problems.append(f"the workspace half does not take what it wraps from {PACKAGE_NAME}")
    if not plain <= _exported_names(moved):
        problems.append(
            f"the package half does not export {sorted(plain - _exported_names(moved))}"
        )
    if hooks & _exported_names(moved):
        problems.append("the package half holds a hook")
    return problems


def test_each_split_file_keeps_only_its_hooks_in_the_workspace() -> None:
    for rel, (hooks, plain) in SPLIT.items():
        stays = (ROOT / (WORKSPACE_SRC + rel)).read_text(encoding="utf-8")
        moved = (ROOT / (SHARED + rel)).read_text(encoding="utf-8")
        assert split_problems(stays, moved, hooks, plain) == [], rel


def test_a_split_file_with_a_plain_function_left_behind_or_a_hook_moved_is_found() -> None:
    """Red for the check above (rule 15): the real halves of `layout/layoutSizes.ts` are clean, and each fault is planted in
    the shape the file would have: a plain function left in the workspace's half, a hook moved into the package's, the
    package's half missing a function, and the workspace's half without its import of the package."""
    hooks, plain = SPLIT["layout/layoutSizes.ts"]
    stays = (ROOT / (WORKSPACE_SRC + "layout/layoutSizes.ts")).read_text(encoding="utf-8")
    moved = (ROOT / (SHARED + "layout/layoutSizes.ts")).read_text(encoding="utf-8")
    assert split_problems(stays, moved, hooks, plain) == []
    clamp = "export function clamp(value: number, min: number, max: number): number {\n  return Math.max(min, Math.min(max, value));\n}\n"
    assert split_problems(stays + clamp, moved, hooks, plain)
    hook = stays[stays.index("export function useLayoutSizes") :]
    assert split_problems(stays, moved + hook, hooks, plain)
    assert split_problems(
        stays, moved.replace("export function clamp(", "function clamp("), hooks, plain
    )
    assert split_problems(stays.replace(PACKAGE_NAME, "./elsewhere"), moved, hooks, plain)


def test_the_package_s_copies_import_no_react() -> None:
    for rel in _package_files():
        assert forbidden_imports((ROOT / rel).read_text(encoding="utf-8")) == [], (
            f"{rel} imports React or a drawing library"
        )


def test_a_react_import_in_a_moved_file_is_found() -> None:
    """Red for the check above (rule 15): the lines the tree really wrote, put into the file that held them. Each file
    is clean first, so the plant is what is found."""
    planted = {
        "admin/inviter.ts": 'import { createContext, useContext } from "react";',
        "layout/layoutSizes.ts": 'import { useSyncExternalStore } from "react";',
        "layout/panelOrder.ts": 'import { useSyncExternalStore } from "react";',
        "layout/sidePanelState.ts": 'import { useSyncExternalStore } from "react";',
        "theme/theme.ts": 'import { useEffect } from "react/jsx-runtime";',
    }
    for rel, line in planted.items():
        real = (ROOT / (SHARED + rel)).read_text(encoding="utf-8")
        assert forbidden_imports(real) == [], f"{rel} is not clean to begin with"
        assert forbidden_imports(line + "\n" + real) != [], f"{line!r} is not found in {rel}"
    assert forbidden_imports('import type { Map } from "maplibre-gl";\n') == ["maplibre-gl"]
    assert forbidden_imports('const graph = import("sigma");\n') == ["sigma"]


def test_the_move_changed_no_line_but_the_imports() -> None:
    """Each whole file is read as the commit that renamed it left it against the commit before: git's own detection finds
    the rename, and the two sides are compared there, never against the working tree (a later edit would be read as
    the move's). A shallow clone has no history to read: skipped, as the earlier move tests in this folder are."""
    _skip_if_shallow()
    for rel in WHOLE:
        new, old = SHARED + rel, OLD_OF[rel]
        commit = _git(
            "log", "--follow", "-M", "--diff-filter=R", "--format=%H", "-1", "--", new
        ).strip()
        assert commit, f"git finds no rename into {new}: the file was not moved with `git mv`"
        assert (
            only_import_lines_changed(
                _git("show", f"{commit}^:{old}"), _git("show", f"{commit}:{new}")
            )
            == []
        ), f"{new} changed in more than its import lines"


def test_a_moved_file_changed_in_more_than_its_imports_is_found() -> None:
    """Red for the comparison above: the real theme's import line moved, once alone and once with a second line changed."""
    was = 'import { currentBrand } from "../brand/brand";\n\nconst THEME_COOKIE_MAX_AGE_S = 60 * 60 * 24 * 365;\n'
    moved = was.replace("../brand/brand", "../brand/brand.js")
    assert only_import_lines_changed(was, moved) == []
    assert only_import_lines_changed(was, moved.replace("365", "30")) != []


def test_the_split_changed_no_line_but_the_hook_wiring() -> None:
    """Each split file, at the commit that added the package's half, against the old file in the commit before it: the
    two halves between them hold every code line the old file did, and none that it did not, but the lines `ALLOWED`
    writes out."""
    _skip_if_shallow()
    for rel in SPLIT:
        new, old = SHARED + rel, WORKSPACE_SRC + rel
        commit = _git("log", "--diff-filter=A", "--format=%H", "-1", "--", new).strip()
        assert commit, f"git finds no commit that added {new}"
        added, lost = split_differences(
            _git("show", f"{commit}^:{old}"),
            _git("show", f"{commit}:{new}"),
            _git("show", f"{commit}:{old}"),
        )
        allowed = ALLOWED.get(rel, {})
        assert added == Counter(allowed.get("added", [])), (
            f"{rel}: lines the split added: {dict(added)}"
        )
        assert lost == Counter(allowed.get("lost", [])), (
            f"{rel}: lines the split lost: {dict(lost)}"
        )
        # The rewritten header: the file no longer "imports nothing but React".
        for place in (new, old):
            assert "imports nothing but react" not in _git("show", f"{commit}:{place}").lower(), (
                f"{place} still says it imports nothing but React"
            )


def test_a_split_that_adds_or_loses_a_line_is_found() -> None:
    """Red for the comparison above, at the real call-site shape: the old `panelOrder.ts` hook and a plain function, split
    cleanly (both empty), then with a line added to one half, a line lost, and a function kept in both halves."""
    old = (
        'import { useSyncExternalStore } from "react";\n\n'
        "export function getSidePanelOrder(): number {\n  return load();\n}\n\n"
        "export function useSidePanelOrder(): number {\n"
        "  return useSyncExternalStore(onSidePanelOrderChange, getSidePanelOrder, getSidePanelOrder);\n}\n"
    )
    package = "export function getSidePanelOrder(): number {\n  return load();\n}\n"
    workspace = (
        'import { useSyncExternalStore } from "react";\nimport { getSidePanelOrder } from "@ospreyflow/glass-shared";\n\n'
        "export function useSidePanelOrder(): number {\n"
        "  return useSyncExternalStore(onSidePanelOrderChange, getSidePanelOrder, getSidePanelOrder);\n}\n"
    )
    assert split_differences(old, package, workspace) == (Counter(), Counter())
    added, _ = split_differences(old, package + "export const CAP = 7;\n", workspace)
    assert added == Counter({"export const CAP = 7;": 1})
    _, lost = split_differences(
        old, package, workspace.replace("getSidePanelOrder, getSidePanelOrder", "getSidePanelOrder")
    )
    assert lost  # the hook's own line changed: one line lost
    added, _ = split_differences(old, package + workspace.split("\n\n", 1)[1], workspace)
    assert added  # the hook kept in both halves


def test_no_tracked_file_names_an_old_path() -> None:
    rels = [rel for rel in tracked() if not _kept_out(rel)]
    assert len(rels) > 1000, (
        "the walk found too few files: git ls-files is not listing the repository"
    )
    found = old_path_mentions(ROOT, rels)
    shown = "\n".join(f"  {rel}:{line}: {text[:140]}" for rel, line, text in found[:40])
    assert found == [], (
        f"{len(found)} place(s) still name an old path; the files are now in {SHARED}:\n{shown}"
    )


def test_every_named_exception_still_has_its_reason() -> None:
    """An exception outlives its reason when the file it excuses no longer names an old path: left in `NAMED` it keeps
    that file outside the walk, and an old path could be written back into it unseen (rule 12)."""
    stale = [rel for rel in NAMED if not old_path_mentions(ROOT, [rel])]
    assert stale == [], (
        f"{stale} no longer name an old path: remove them from NAMED, and the walk will cover them"
    )


def test_every_import_of_a_moved_module_reaches_the_package() -> None:
    bad, importers = imports_not_reaching(ROOT, tracked())
    assert importers >= 150, (
        f"only {importers} file(s) under OspreyFlow_Core import {PACKAGE_NAME}: the walk found too few imports, or the importers were not repointed"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach the package by its name: {bad[:10]}"


_PLANTED_IMPORTS = {
    # (path of the file that held the line, the line as the tree wrote it, the line it has now)
    "the theme, from a harness": (
        APPS + "harness/src/main.tsx",
        'import { applyTheme, readStoredTheme } from "../../workspace/src/theme/theme";',
        f'import {{ applyTheme, readStoredTheme }} from "{PACKAGE_NAME}";',
    ),
    "the statement, from the install page": (
        APPS + "harness/src/InstallApp.tsx",
        'import { PRODUCT_STATEMENT } from "../../workspace/src/welcome/statement";',
        f'import {{ PRODUCT_STATEMENT }} from "{PACKAGE_NAME}";',
    ),
    "the theme, from a Playwright harness outside src": (
        APPS + "workspace/keyboard/harness.tsx",
        'import { applyTheme } from "../src/theme/theme";',
        f'import {{ applyTheme }} from "{PACKAGE_NAME}";',
    ),
    "the theme, beside it": (
        APPS + "workspace/src/theme/ThemeToggle.tsx",
        'import { applyTheme, currentTheme, onThemeChange, storeTheme, type Theme } from "./theme";',
        f'import {{ applyTheme, currentTheme, onThemeChange, storeTheme, type Theme }} from "{PACKAGE_NAME}";',
    ),
    "the brand, from a component": (
        WORKSPACE_SRC + "welcome/WelcomeAbout.tsx",
        'import { currentBrand } from "../brand/brand";',
        f'import {{ currentBrand }} from "{PACKAGE_NAME}";',
    ),
    "the glyphs, from a component": (
        WORKSPACE_SRC + "canvas/IconsMenu.tsx",
        'import { NODE_GLYPHS } from "../color/nodeGlyphs";',
        f'import {{ NODE_GLYPHS }} from "{PACKAGE_NAME}";',
    ),
    "the layout sizes, plain names, from the sash": (
        WORKSPACE_SRC + "layout/Sash.tsx",
        'import { clamp } from "./layoutSizes";',
        f'import {{ clamp }} from "{PACKAGE_NAME}";',
    ),
    "the layout sizes, a hook with a plain name beside it, from the timeline": (
        WORKSPACE_SRC + "timeline/Timeline.tsx",
        'import { setTimelineHeight, useLayoutSizes } from "../layout/layoutSizes";',
        f'import {{ setTimelineHeight }} from "{PACKAGE_NAME}";\nimport {{ useLayoutSizes }} from "../layout/layoutSizes";',
    ),
    "the layout sizes, a dynamic import in a test": (
        WORKSPACE_SRC + "timeline/Timeline.cells.test.tsx",
        '    const { getLayoutSizes, setTimelineHeight } = await import("../layout/layoutSizes");',
        f'    const {{ getLayoutSizes, setTimelineHeight }} = await import("{PACKAGE_NAME}");',
    ),
    "the invite form, the plain half, from the people screen": (
        WORKSPACE_SRC + "admin/sections/People.tsx",
        'import { givableCodes, givableLevels, useInviter } from "../inviter";',
        f'import {{ givableCodes, givableLevels }} from "{PACKAGE_NAME}";\nimport {{ useInviter }} from "../inviter";',
    ),
    "an old path in a guide": (
        "OspreyFlow_Core/README.md",
        "The theme module is `apps/workspace/src/theme/theme.ts`; it reads and writes the one cookie.",
        "The theme module is `packages/glass-shared/src/theme/theme.ts`; it reads and writes the one cookie.",
    ),
    "an old path in a comment of a harness script": (
        "OspreyFlow_Core/harness/govuk_chrome.js",
        "(`brandTitle` in `apps/workspace/src/brand/brand.ts`, whose fallbacks this follows).",
        "(`brandTitle` in `packages/glass-shared/src/brand/brand.ts`, whose fallbacks this follows).",
    ),
    "a deep import into the package": (
        WORKSPACE_SRC + "App.tsx",
        'import { applyTheme } from "../../../packages/glass-shared/src/theme/theme";',
        f'import {{ applyTheme }} from "{PACKAGE_NAME}";',
    ),
    "the palette, written in segments": (
        APPS + "workspace/a11y/plants/run.mjs",
        'const palette = join(HERE, "..", "..", "src", "color", "palette");',
        'const palette = join(HERE, "..", "..", "..", "..", "packages", "glass-shared", "src", "color", "palette");',
    ),
}


@pytest.mark.parametrize("case", sorted(_PLANTED_IMPORTS))
def test_an_old_path_put_back_in_one_importer_is_found(case: str, tmp_path: Path) -> None:
    """Red for the two walks above (rule 15): each line the tree really held, put back in the file that held it (or, for a
    hook next to a plain name, the one line that took both). The same file with the new line is clean first, so the plant
    is what is found and not something else in the file."""
    rel, old_line, new_line = _PLANTED_IMPORTS[case]
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_text(new_line + "\n", encoding="utf-8")
    assert (
        imports_not_reaching(tmp_path, [rel])[0] == [] and old_path_mentions(tmp_path, [rel]) == []
    )
    target.write_text(old_line + "\n", encoding="utf-8")
    assert imports_not_reaching(tmp_path, [rel])[0] or old_path_mentions(tmp_path, [rel]), (
        f"neither walk finds {old_line!r} in {rel}"
    )


def test_every_import_reached_from_a_spec_resolves() -> None:
    """The Playwright collection check's own half (item (b)): a spec that imports a file that is gone fails at
    collection, which no unit test runs. Every relative import, reached from any spec by any chain, names a file."""
    rels = tracked()
    specs = spec_files(rels)
    assert len(specs) >= 100, (
        f"only {len(specs)} spec files found: the walk is not seeing the specs"
    )
    missing, reached = unresolved_from_specs(ROOT, specs)
    assert reached >= 400, f"the walk reached only {reached} files: it is not following imports"
    assert missing == [], f"{len(missing)} import(s) name no file: {missing[:10]}"


def test_a_spec_that_imports_a_path_that_no_longer_exists_is_found(tmp_path: Path) -> None:
    """Red for the walk above, at the shapes the move could leave: a spec's harness still importing the old path of the
    theme (the line the tree held), and the package's index exporting a file that is not there."""
    spec = APPS + "workspace/keyboard/toolbar.spec.ts"
    harness = APPS + "workspace/keyboard/glass-toolbar-harness.tsx"
    files = {
        spec: 'import { mount } from "./glass-toolbar-harness";\n',
        harness: f'import {{ applyTheme }} from "{PACKAGE_NAME}";\n',
        SHARED + "index.ts": 'export * from "./theme/theme";\n',
        SHARED + "theme/theme.ts": "export const THEME = 1;\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert unresolved_from_specs(tmp_path, [spec])[0] == []
    # The old line, put back: the theme is no longer at that path.
    (tmp_path / harness).write_text(
        'import { applyTheme } from "../src/theme/theme";\n', encoding="utf-8"
    )
    assert unresolved_from_specs(tmp_path, [spec])[0] == [f"{harness}: ../src/theme/theme"]
    # The index exporting a file the package does not hold.
    (tmp_path / harness).write_text(
        f'import {{ applyTheme }} from "{PACKAGE_NAME}";\n', encoding="utf-8"
    )
    (tmp_path / SHARED / "theme" / "theme.ts").unlink()
    assert unresolved_from_specs(tmp_path, [spec])[0] == [f"{SHARED}index.ts: ./theme/theme"]


# ---------------------------------------------------------------------------------------------------- the harness image


def test_the_harness_image_copies_what_the_moved_files_need() -> None:
    """The stage copies named parts of the workspace and the package: every file the harness frontend reaches is under a
    `COPY`, and every `COPY` of a workspace path names something that still exists and something the frontend still
    reaches (`brand.ts` and `statement.ts` moved, so their lines would copy nothing)."""
    reached = image._reached_workspace_files()
    copied = image._copied_paths()
    assert image._missing(copied, reached) == []
    assert dangling(copied, reached) == []
    names = {str(p.relative_to(CORE.resolve())) for p in reached}
    for rel in ("theme/theme.ts", "brand/brand.ts", "welcome/statement.ts"):
        assert f"packages/glass-shared/src/{rel}" in names, (
            f"the walk does not reach the package's {rel}"
        )
    assert "apps/workspace/src/theme/ThemeToggle.tsx" in names


def dangling(copied: list[Path], reached: set[Path]) -> list[str]:
    """The copied workspace paths that are gone, or that no file the frontend reaches is under."""
    return sorted(
        str(path.relative_to(CORE.resolve()))
        for path in copied
        if path.name != "package.json"
        and (not path.exists() or not any(r.is_relative_to(path) for r in reached))
    )


def test_a_stage_with_a_copy_gone_or_a_stale_one_is_found() -> None:
    """Red for the check above (rule 15), on the real stage: the line a moved file now needs taken out (the package's
    source: the theme, the brand and the statement are missing), the line the theme directory still needs taken out
    (`ThemeToggle.tsx`), and the two lines for files that moved put back (each copies a file that is not there)."""
    real = image.DOCKERFILE.read_text(encoding="utf-8")
    reached = image._reached_workspace_files()
    assert (
        image._missing(image._copied_paths(real), reached) == []
        and dangling(image._copied_paths(real), reached) == []
    )

    shared = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    assert shared in real
    missing = image._missing(image._copied_paths(real.replace(shared, "", 1)), reached)
    for rel in ("theme/theme.ts", "brand/brand.ts", "welcome/statement.ts", "color/palette.ts"):
        assert f"packages/glass-shared/src/{rel}" in missing, f"{rel} is not found missing"

    theme = "COPY apps/workspace/src/theme ./apps/workspace/src/theme\n"
    assert theme in real
    assert image._missing(image._copied_paths(real.replace(theme, "", 1)), reached) == [
        "apps/workspace/src/theme/ThemeToggle.tsx"
    ]

    for line in (
        "COPY apps/workspace/src/brand/brand.ts ./apps/workspace/src/brand/brand.ts\n",
        "COPY apps/workspace/src/welcome/statement.ts ./apps/workspace/src/welcome/statement.ts\n",
    ):
        stale = real.replace(shared, shared + line, 1)
        assert dangling(image._copied_paths(stale), reached) == [line.split()[1]]


# --------------------------------------------------------------------------------------------------- the four gates

#: The files each gate read on main before the move: the number each reported or, where it reports none, the files its
#: own rules select (measured on 20 November 2026, at the tip PL4d1 started from).
FILES_BEFORE = {"colour-drift": 484, "design-check": 893, "ui-words": 491, "no-branches": 1738}


def _design_files(roots: Iterable[Path]) -> int:
    return sum(
        1
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".css", ".ts", ".tsx"}
        and "node_modules" not in path.parts
    )


def _ui_words_files() -> int:
    roots = [ui_words_check.GLASS_SRC, ui_words_check.DESIGN_PACKAGE, ui_words_check.SHARED_SRC]
    return sum(
        1
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in ui_words_check.SUFFIXES
        and "node_modules" not in path.parts
        and not ui_words_check._skipped(path.relative_to(root))
    )


def test_each_gate_reads_no_fewer_files_than_before() -> None:
    now = {
        "colour-drift": colour_drift_check.scanned_count(),
        "design-check": _design_files(design_check.SCANNED),
        "ui-words": _ui_words_files(),
        "no-branches": len(no_branches_check.tree_files()),
    }
    assert all(now[gate] >= before for gate, before in FILES_BEFORE.items()), (
        f"a gate reads fewer files than before: now {now}, before {FILES_BEFORE}"
    )
    # The four split files' package halves are new files the gates read.
    assert all(
        now[gate] > FILES_BEFORE[gate] for gate in ("colour-drift", "design-check", "no-branches")
    ), now


@pytest.fixture
def shared_copy(tmp_path: Path) -> Path:
    """`<tmp>/packages/glass-shared/src`, a copy of the real folder; the real one is never written."""
    copy = tmp_path / "packages" / "glass-shared" / "src"
    shutil.copytree(SHARED_SRC, copy, ignore=shutil.ignore_patterns("node_modules"))
    return copy


def _append(copy: Path, rel: str, text: str) -> None:
    path = copy / rel
    assert path.is_file(), f"{SHARED}{rel} is not in the package: nothing to plant in"
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def test_the_colour_drift_check_reports_a_plant_in_a_moved_file(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # `color/oklab.ts` is not a mirror: the shape a stray colour takes there is a hex in a style object. The mirrors
    # (`color/tokens.ts`, `color/palette.ts`) are exempt in the package by name, as they were in the workspace.
    mirrors = dict(colour_drift_check.SCANNED).get(SHARED_SRC)
    assert mirrors is not None and {"color/tokens.ts", "color/palette.ts"} <= mirrors, (
        "the colour-drift check does not exempt the two mirrors where they are now"
    )
    monkeypatch.setattr(colour_drift_check, "CORE", shared_copy.parent.parent.parent)
    monkeypatch.setattr(colour_drift_check, "SCANNED", ((shared_copy, mirrors),))
    assert colour_drift_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    _append(
        shared_copy,
        "color/oklab.ts",
        '\nexport const STRIPE = { background: "#12ab34", padding: 8 };\n',
    )
    assert colour_drift_check.main() == 1
    assert "packages/glass-shared/src/color/oklab.ts:" in capsys.readouterr().out


def test_the_design_detector_reports_a_plant_in_a_moved_file(
    shared_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(design_check, "SCANNED", [shared_copy])
    assert design_check.unexcused(design_check.detect(design_check.SCANNED)) == [], (
        "the clean copy already has findings"
    )
    # The shape the old toast had, as a plain module holds a style: a side stripe on a card-like object.
    _append(
        shared_copy,
        "theme/theme.ts",
        "\nexport const TOAST_STYLE = {\n"
        '  background: "var(--surface-raised)", borderLeft: "3px solid var(--error)", borderRadius: "8px",\n'
        '  padding: "12px 16px", boxShadow: "var(--overlay-shadow)",\n'
        "};\n",
    )
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [("theme.ts", "side-tab")]


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
    _append(shared_copy, "welcome/statement.ts", '\nexport const LABEL = "Target model";\n')
    assert ui_words_check.main() == 1
    assert "packages/glass-shared/src/welcome/statement.ts:" in capsys.readouterr().out


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
    _append(
        shared_copy, "layout/panelOrder.ts", '\nexport const BRANCH_CASE = "branch-by-filter";\n'
    )
    assert no_branches_check.main() == 1
    assert f"{top}/layout/panelOrder.ts:" in capsys.readouterr().out
