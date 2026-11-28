"""The workspace's pure leaves and stores live in `packages/glass-shared`, and nothing names the place they came from
(ADR-152 decision 6, "logic, stores, the panel pattern, the Conduit client, the keyboard action registry"; slice PL4c, the
third of the PL4 slices after A, B and B2; the owner's confirmations of 20 November 2026).

Six plain TypeScript files moved from `OspreyFlow_Core/apps/workspace/` to `OspreyFlow_Core/packages/glass-shared/src/`,
their bytes unchanged but for their import lines, and are exported from the package's index:

* `keyboard/actionRegistry.ts` (it was `apps/workspace/keyboard/actionRegistry.ts`),
* `workingset/store.ts` and `workingset/models.ts`,
* `color/textContrast.ts`,
* `map/contrast.ts` and `map/conduitRequest.ts`.

Every importer followed them (about 70 keyboard specs, about 100 files for the store and the models, a handful for the
rest) and imports the package by its name. The tests stayed in the workspace. This file is the proof that none was left
behind and that each guard of the move can fail.

Which test fails if the invariant is broken (rule 12):

* a file is not where it should be, an old one is back, or the index does not export one:
  `test_the_six_files_are_in_the_package_and_not_in_the_workspace`;
* a file moved with more than its import lines changed: `test_the_move_changed_no_line_but_the_imports`;
* a file of any kind still names an old path, in a form the repository writes it in (a path to open, import, copy or
  cite; `/`-joined or written apart): `test_no_tracked_file_names_an_old_path`, which walks `git ls-files` over the
  **whole repository** (`OspreyFlow_Core`, `OspreyFlow_Build` and the repository root's own files). Only the decision log
  and the build record (`process/`) may keep one (they are history), and the few files named in `NAMED`, each with why;
* an import in `apps/` that still reaches an old path, reaches into the package's folder instead of its name, or a walk
  that read too few files to say so: `test_every_import_of_a_moved_module_reaches_the_package`;
* the workspace's registry-coverage test (and the harness's `actions.ts`, through which the harness reads the registry)
  not reading the registry from the package, or the workspace test no longer scanning its own folder's specs:
  `test_the_two_registry_coverage_tests_read_the_registry_from_the_package`;
* the manifest listing more or less than `graphology` and `zustand` as dependencies, at the ranges the workspace uses,
  or a name from the React family anywhere, or a source file importing `zustand` other than through `zustand/vanilla`
  (whose main entry pulls React in): `test_the_manifest_lists_graphology_and_zustand_and_nothing_from_react`,
  `test_the_source_imports_zustand_only_through_vanilla`, `test_the_lint_rule_refuses_the_zustand_that_pulls_in_react` and
  (for `import("zustand")` as a type or an expression, in every extension) `test_the_lint_selectors_refuse_the_zustand_that_pulls_in_react_as_a_type_or_a_dynamic_import`;
* each of four gates (`make colour-drift-check`, `design-check`, `ui-words-check`, `no-branches-check`) that stops
  reading `packages/glass-shared/src`, or reads fewer files than it did before the move:
  `test_each_gate_reads_packages_glass_shared_src`, `test_each_gate_reads_no_fewer_files_than_before` and one plant case
  for each gate, shown clean beside it;
* the two images that do not copy the package's source, so an imported moved file stops building:
  `test_the_two_images_copy_the_package_s_source`.

Each guard is shown red on a planted regression in the shape the real code writes it (rule 15): the planted lines are
lines the tree wrote on the day before the move, each placed at the path of a file that held one, and each case first
shows the same file clean with the new line. A plant some other rule would also have caught proves nothing.

**This file walks:** `git ls-files` over the whole repository (the old-path test); the tracked `.ts`, `.tsx`, `.mts`,
`.mjs`, `.js` and `.jsx` files under `OspreyFlow_Core/apps/` (the import test); `OspreyFlow_Core/packages/glass-shared/`
(its source and manifest); and temporary copies of `packages/glass-shared/src` for the plants (copied, never written:
`make test` runs on several workers, and a plant in the real folder would be seen by every reader of it). It also reads
`harness/Dockerfile` and `apps/workspace/Dockerfile` by name, and the four gates walk what they are configured to walk.
"""

# The planted lines below are the real call-site shapes, kept on one line as the tree wrote them (rule 15), and the
# prose beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import difflib
import json
import posixpath
import re
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest
from tools import colour_drift_check, design_check, no_branches_check, ui_words_check
from tools.layout import CORE, ROOT

PACKAGE = "OspreyFlow_Core/packages/glass-shared/"
SHARED = PACKAGE + "src/"
SHARED_SRC = CORE / "packages" / "glass-shared" / "src"
WORKSPACE = "OspreyFlow_Core/apps/workspace/"

#: The six files: where each is now (relative to `SHARED`) and where it was.
MOVED = {
    "keyboard/actionRegistry.ts": WORKSPACE + "keyboard/actionRegistry.ts",
    "workingset/store.ts": WORKSPACE + "src/workingset/store.ts",
    "workingset/models.ts": WORKSPACE + "src/workingset/models.ts",
    "color/textContrast.ts": WORKSPACE + "src/color/textContrast.ts",
    "map/contrast.ts": WORKSPACE + "src/map/contrast.ts",
    "map/conduitRequest.ts": WORKSPACE + "src/map/conduitRequest.ts",
}
NEW_RELS = tuple(SHARED + rel for rel in MOVED)
OLD_RELS = tuple(MOVED.values())
#: An old path without its extension: what an import's specifier resolves to.
_OLD_STEMS = {old.removesuffix(".ts") for old in OLD_RELS}
PACKAGE_NAME = "@ospreyflow/glass-shared"

#: The places that may name an old path because they are a record of the past: the decision log, and the build record
#: under `process/` (the lanes' briefs, the build plan, the handovers). They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone
#: (`test_every_named_exception_still_has_its_reason`).
NAMED = {
    # The citation check's allowlist: the decision log and the records name the old paths, and the allowlist says why
    # that is not a dead citation. It must name them to do so.
    "OspreyFlow_Build/tests/fixtures/citation_allowlist.txt": "the allowlist for the records that name the old paths",
    # The tool's own docstring tells the incident of 25 September 2026 (a citation to a file that never existed) as it
    # happened, with the path the registry had on that day: history, written into a tool.
    "OspreyFlow_Build/tools/doc_citations_check.py": "a docstring that recounts a past incident",
    # The lane reviewer's checklist lists the shared files a lane must not change; the file is the owner's, outside this
    # slice's reach (the guard refuses a builder there), and the owner follows the move in it.
    ".claude/agents/lane-reviewer.md": "the owner's file, outside the slice's reach",
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_glass_shared_leaves.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

#: A moved file's name written as a path, in the places the repository writes one: not the new place.
_NAME_FORMS = (
    r"keyboard/actionRegistry",
    r"workingset/(?:store|models)",
    r"color/textContrast",
    r"map/(?:contrast|conduitRequest)",
)
_TEXT_FORM = re.compile(rf"(?<!glass-shared/src/)\b(?:{'|'.join(_NAME_FORMS)})\b")
#: The segments of one written apart: `join(HERE, "..", "..", "src", "color", "textContrast")`, Python's
#: `/ "workingset" / "store.ts"` (the gap may be a line break inside the brackets).
_SEGMENT_FORM = re.compile(
    r"""["'](?:keyboard["']\s*[,/]\s*["']actionRegistry|workingset["']\s*[,/]\s*["'](?:store|models)"""
    r"""|color["']\s*[,/]\s*["']textContrast|map["']\s*[,/]\s*["'](?:contrast|conduitRequest))(?:\.ts)?["']"""
)
_PACKAGE_SEGMENTS = re.compile(r"""["']glass-shared["']\s*[,/]\s*["']src["']\s*[,/]\s*$""")


def old_path_mentions(root: Path, rels: Iterable[str]) -> list[tuple[str, int, str]]:
    """`(file, line, text)` for each place under `root` that names an old path. `rels` are repository-relative."""
    found: list[tuple[str, int, str]] = []
    for rel in rels:
        if rel.startswith(SHARED):
            continue  # inside the package a module is named by its place in the package (`./keyboard/actionRegistry`)
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # gone from the working tree, or not text
        for form in (_TEXT_FORM, _SEGMENT_FORM):
            for hit in form.finditer(text):
                if form is _SEGMENT_FORM and _PACKAGE_SEGMENTS.search(text[: hit.start()]):
                    continue  # `"glass-shared", "src", "color", "textContrast"` is the new place written apart
                line = text.count("\n", 0, hit.start()) + 1
                found.append((rel, line, text.splitlines()[line - 1].strip()))
    return sorted(set(found))


def tracked(root: Path = ROOT) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return sorted(name for name in out.decode("utf-8").split("\0") if name)


def _kept_out(rel: str) -> bool:
    """History and the named exceptions are not looked at."""
    if rel in NAMED:
        return True
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in HISTORY)


# ----------------------------------------------------------------------------------------------------- the imports

_SOURCE_SUFFIXES = {".ts", ".tsx", ".mts", ".mjs", ".js", ".jsx"}
#: Any quoted relative path: an import, a re-export, `import("...")`, `vi.mock("...")`, `importActual<typeof import("...")>("...")`.
_RELATIVE = re.compile(r"""["'`](\.{1,2}/[^"'`\n]*)["'`]""")
_PACKAGE_IMPORT = re.compile(rf"""["']{re.escape(PACKAGE_NAME)}(/[^"']*)?["']""")


def imports_not_reaching(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The relative specifiers that resolve to an old path, or into the package's folder instead of its name, and
    the number of files that import the package by its name. Resolution is by path alone: an old file need not exist."""
    bad: list[str] = []
    importers = 0
    for rel in rels:
        if Path(rel).suffix not in _SOURCE_SUFFIXES or not rel.startswith(
            WORKSPACE.rsplit("workspace/", 1)[0]
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
        if _PACKAGE_IMPORT.search(text):
            importers += 1
        for hit in _RELATIVE.finditer(text):
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(rel), hit.group(1).split("?", 1)[0])
            )
            if target.removesuffix(".ts").removesuffix(".tsx") in _OLD_STEMS:
                bad.append(f"{rel}: {hit.group(1)} (an old path)")
            elif target.startswith(PACKAGE):
                bad.append(f"{rel}: {hit.group(1)} (into the package's folder, not its name)")
    return bad, importers


# ------------------------------------------------------------------------------------------------ the manifest and zustand

_REACT_FAMILY = re.compile(
    r"^(react|react-dom|react-.+|@types/react|@types/react-dom|@types/react-.+|preact.*)$"
)
_ZUSTAND = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\(\s*)["'](zustand(?:/[^"']*)?)["']"""
)


def manifest_problems(
    shared_manifest: dict[str, dict[str, str]], workspace_manifest: dict[str, dict[str, str]]
) -> list[str]:
    problems = []
    dependencies = shared_manifest.get("dependencies", {})
    if sorted(dependencies) != ["graphology", "zustand"]:
        problems.append(f"dependencies are {sorted(dependencies)}, not ['graphology', 'zustand']")
    for name in ("graphology", "zustand"):
        wanted = workspace_manifest.get("dependencies", {}).get(name)
        if dependencies.get(name) != wanted:
            problems.append(f"{name} is {dependencies.get(name)!r}, the workspace uses {wanted!r}")
    for kind in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name in shared_manifest.get(kind, {}):
            if _REACT_FAMILY.match(name):
                problems.append(f"{kind} names {name}")
    return problems


def zustand_problems(root: Path) -> tuple[list[str], int]:
    """Each import of `zustand` in the package's source other than `zustand/vanilla`, and the imports of it looked at."""
    bad: list[str] = []
    seen = 0
    for path in sorted((root / "packages" / "glass-shared" / "src").rglob("*.ts")):
        for hit in _ZUSTAND.finditer(path.read_text(encoding="utf-8")):
            seen += 1
            if hit.group(1) != "zustand/vanilla":
                bad.append(f"{path.relative_to(root).as_posix()}: {hit.group(1)}")
    return bad, seen


def _eslint_messages(source: str, filename: str, rule_suffix: str) -> list[str]:
    done = subprocess.run(
        ["npx", "--no-install", "eslint", "--stdin", "--stdin-filename", f"packages/glass-shared/src/{filename}", "--format", "json"],
        cwd=CORE, input=source, capture_output=True, text=True, check=False,
    )  # fmt: skip
    results = json.loads(done.stdout)
    return [
        m["message"]
        for r in results
        for m in r["messages"]
        if str(m.get("ruleId", "")).endswith(rule_suffix)
    ]


def eslint_refusals(source: str) -> list[str]:
    """The `no-restricted-imports` messages ESLint gives `source` read as a file of the shared package (a name, never a file)."""
    return _eslint_messages(source, "planted.ts", "no-restricted-imports")


def eslint_syntax_refusals(source: str, filename: str = "planted.ts") -> list[str]:
    """The `no-restricted-syntax` messages: the selectors for `import("name")` as a type and as an expression."""
    return _eslint_messages(source, filename, "no-restricted-syntax")


# ---------------------------------------------------------------------------------------------------- the images

WORKSPACE_DOCKERFILE = "OspreyFlow_Core/apps/workspace/Dockerfile"
HARNESS_DOCKERFILE = "OspreyFlow_Core/harness/Dockerfile"
_COPY = re.compile(r"^COPY\s+(packages/glass-shared/\S*)\s+(\S+)\s*$", re.M)


def _frontend_stage(dockerfile: str) -> str:
    return dockerfile.split("AS frontend-builder", 1)[1].split("\nFROM ", 1)[0]


def image_problems(text: str) -> list[str]:
    """What is wrong with the lines of one image's build stage that copy the package: its `src` is copied, to the same
    place, and nothing but `src` and the manifest is (the tests and the config stay out)."""
    copies = _COPY.findall(text)
    problems = []
    if ("packages/glass-shared/src", "./packages/glass-shared/src") not in [
        (s.rstrip("/"), t.rstrip("/")) for s, t in copies
    ]:
        problems.append("no `COPY packages/glass-shared/src ./packages/glass-shared/src`")
    problems += [
        f"copies {s}"
        for s, _ in copies
        if s.rstrip("/") not in {"packages/glass-shared/src", "packages/glass-shared/package.json"}
    ]
    return problems


# ----------------------------------------------------------------------------------------------- the real tree: cases


def test_the_six_files_are_in_the_package_and_not_in_the_workspace() -> None:
    names = tracked()
    for new, old in zip(NEW_RELS, OLD_RELS, strict=True):
        assert (ROOT / new).is_file(), f"{new} is not in packages/glass-shared/src"
        assert not (ROOT / old).exists(), f"{old} is still where it was"
        assert new in names and old not in names
    index = (SHARED_SRC / "index.ts").read_text(encoding="utf-8")
    for rel in MOVED:
        stem = "./" + rel.removesuffix(".ts")
        assert re.search(
            rf"""^export\s+(?:\*|\{{[^}}]*\}})\s+from\s+["']{re.escape(stem)}["'];""", index, re.M
        ), f"packages/glass-shared/src/index.ts does not export {stem}"


_IMPORT_LINE = re.compile(
    r"""^\s*(?:import\b.*|\}\s*from\s+["'][^"']*["'];?|.*\bfrom\s+["'][^"']*["'];?)$"""
)


def only_import_lines_changed(was: str, now: str) -> list[str]:
    """The changed lines that are not import lines."""
    return [
        d
        for d in difflib.ndiff(was.splitlines(), now.splitlines())
        if d[:2] in {"- ", "+ "} and not _IMPORT_LINE.match(d[2:])
    ]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def test_the_move_changed_no_line_but_the_imports() -> None:
    """Each file is read as the commit that renamed it left it against the commit before: the rename is found by
    git's own detection, at the same bytes but for the lines naming a module. (A shallow clone has no history to read:
    skipped, as the two earlier move tests in this folder are.)"""
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        pytest.skip("a shallow clone has no history: the move commit cannot be read")
    for new, old in zip(NEW_RELS, OLD_RELS, strict=True):
        commit = _git(
            "log", "--follow", "-M", "--diff-filter=R", "--format=%H", "-1", "--", new
        ).strip()
        assert commit, f"git finds no rename into {new}: the file was not moved with `git mv`"
        was = _git("show", f"{commit}^:{old}")
        now = _git("show", f"{commit}:{new}")
        assert only_import_lines_changed(was, now) == [], (
            f"{new} changed in more than its import lines"
        )


def test_a_moved_file_changed_in_more_than_its_imports_is_found() -> None:
    """Red for the comparison above (rule 15): the real store's header line moved, once alone and once with a second
    line changed beside it."""
    was = 'import { createStore, type StoreApi } from "zustand/vanilla";\nimport type { Edge, Node } from "../../../../packages/schemas/generated";\nconst cap = 10_000;\n'
    moved = was.replace("../../../../packages/schemas/generated", "../../../schemas/generated")
    assert only_import_lines_changed(was, moved) == []
    assert only_import_lines_changed(was, moved.replace("10_000", "20_000")) != []


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
    assert importers >= 120, (
        f"only {importers} file(s) under apps/ import {PACKAGE_NAME}: the walk found too few imports, or the importers were not repointed"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach the package by its name: {bad[:10]}"


def test_the_two_registry_coverage_tests_read_the_registry_from_the_package() -> None:
    """The workspace's test enumerates `ALL_REGISTRIES` and so imports it from the package, still scanning its own
    folder's specs. The harness's test does not import the registry at all (it scans its own folder's text, and says
    why: importing it would demand the workspace's registries be covered there too); what it reads the registry
    through is the harness's `actions.ts`, which imports `defineActionRegistry` from the package and re-exports the
    proving helpers from `apps/provedActions.ts`."""
    keyboard = CORE / "apps" / "workspace" / "keyboard"
    workspace = (keyboard / "registryCoverage.test.ts").read_text(encoding="utf-8")
    harness = (CORE / "apps" / "harness" / "keyboard" / "registryCoverage.test.ts").read_text(
        encoding="utf-8"
    )
    harness_actions = (CORE / "apps" / "harness" / "keyboard" / "actions.ts").read_text(
        encoding="utf-8"
    )
    assert re.search(
        rf"""import\s*\{{[^}}]*\bALL_REGISTRIES\b[^}}]*\}}\s*from\s*["']{re.escape(PACKAGE_NAME)}["']""",
        workspace,
    ), (
        f"the workspace's registryCoverage.test.ts does not import ALL_REGISTRIES from {PACKAGE_NAME}"
    )
    assert re.search(
        rf"""import\s*\{{[^}}]*\bdefineActionRegistry\b[^}}]*\}}\s*from\s*["']{re.escape(PACKAGE_NAME)}["']""",
        harness_actions,
    ), f"the harness's actions.ts does not import defineActionRegistry from {PACKAGE_NAME}"
    # The declarations come from the package; the two that prove and check them are test-side, in the one store both
    # apps' keyboard suites share, which keeps a run's proofs outside the worker's memory (CO3e).
    assert re.search(
        r"""export\s*\{[^}]*\bassertAllCovered\b[^}]*\}\s*from\s*["']\.\./\.\./provedActions["']""",
        harness_actions,
    ), "the harness's actions.ts does not re-export assertAllCovered from apps/provedActions"
    # Neither reaches the registry by a path, nor reads the package's folder for specs.
    assert "workspace/keyboard/actionRegistry" not in harness + harness_actions
    # The scan stays where the specs are: the workspace's own folder, never the package's.
    assert "const KEYBOARD_DIR = dirname(fileURLToPath(import.meta.url));" in workspace
    assert len(list(keyboard.glob("*.spec.ts"))) >= 90


_PLANTED_IMPORTS = {
    # (path of the file that held the line, the line as the tree wrote it, the line it has now)
    "the store, from a harness": (
        WORKSPACE + "keyboard/harness.tsx",
        'import { createWorkingSet } from "../src/workingset/store";',
        f'import {{ createWorkingSet }} from "{PACKAGE_NAME}";',
    ),
    "the registry, from a spec": (
        WORKSPACE + "keyboard/shell.spec.ts",
        'import { SHELL_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";',
        f'import {{ SHELL_ACTIONS, assertAllCovered, registerCovered }} from "{PACKAGE_NAME}";',
    ),
    "the registry, from the harness": (
        "OspreyFlow_Core/apps/harness/keyboard/actions.ts",
        'import { defineActionRegistry } from "../../workspace/keyboard/actionRegistry";',
        f'import {{ defineActionRegistry }} from "{PACKAGE_NAME}";',
    ),
    "the models, a type, from a component": (
        WORKSPACE + "src/canvas/CapRefusalPrompt.tsx",
        'import type { LimitExceeded } from "../workingset/models";',
        f'import type {{ LimitExceeded }} from "{PACKAGE_NAME}";',
    ),
    "the store, beside it": (
        WORKSPACE + "src/workingset/ViewOverCapGate.test.tsx",
        'import { createWorkingSet } from "./store";',
        f'import {{ createWorkingSet }} from "{PACKAGE_NAME}";',
    ),
    "the contrast, beside it": (
        WORKSPACE + "src/map/style.ts",
        'import { contrastRatio, NON_TEXT_FLOOR } from "./contrast";',
        f'import {{ contrastRatio, NON_TEXT_FLOOR }} from "{PACKAGE_NAME}";',
    ),
    "the request transform, beside it": (
        WORKSPACE + "src/map/MapView.tsx",
        'import { conduitRequest } from "./conduitRequest";',
        f'import {{ conduitRequest }} from "{PACKAGE_NAME}";',
    ),
    "a mock of the store": (
        WORKSPACE + "src/App.matrix.test.tsx",
        'vi.mock("./workingset/store", async () => {',
        f'vi.mock("{PACKAGE_NAME}", async () => {{',
    ),
    "a deep import into the package": (
        WORKSPACE + "src/App.tsx",
        'import { createWorkingSet } from "../../../packages/glass-shared/src/workingset/store";',
        f'import {{ createWorkingSet }} from "{PACKAGE_NAME}";',
    ),
    "the judge, written in segments": (
        WORKSPACE + "a11y/plants/run.mjs",
        'const judgement = join(HERE, "..", "..", "src", "color", "textContrast");',
        'const judgement = join(HERE, "..", "..", "..", "..", "packages", "glass-shared", "src", "color", "textContrast");',
    ),
}


@pytest.mark.parametrize("case", sorted(_PLANTED_IMPORTS))
def test_an_old_path_put_back_in_one_importer_is_found(case: str, tmp_path: Path) -> None:
    """Red for the two walks above (rule 15): each line the tree really held, put back in the file that held it. The
    same file with the new line is clean first, so the plant is what is found and not something else in the file."""
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


def test_the_manifest_lists_graphology_and_zustand_and_nothing_from_react() -> None:
    shared = json.loads(
        (CORE / "packages" / "glass-shared" / "package.json").read_text(encoding="utf-8")
    )
    workspace = json.loads(
        (CORE / "apps" / "workspace" / "package.json").read_text(encoding="utf-8")
    )
    assert manifest_problems(shared, workspace) == []


def test_a_manifest_that_lists_more_or_less_or_react_is_found() -> None:
    """Red for the check above: the real workspace's ranges, then a shared manifest planted in each of its failings."""
    workspace = {"dependencies": {"graphology": "^0.26.0", "zustand": "^5.0.2", "react": "^19.3.1"}}
    good = {"dependencies": {"graphology": "^0.26.0", "zustand": "^5.0.2"}}
    assert manifest_problems(good, workspace) == []
    assert manifest_problems({"dependencies": {"graphology": "^0.26.0"}}, workspace)  # one short
    assert manifest_problems(
        {"dependencies": {**good["dependencies"], "immer": "^11.1.21"}}, workspace
    )  # one more
    assert manifest_problems(
        {"dependencies": {**good["dependencies"], "react": "^19.3.1"}}, workspace
    )  # React
    assert manifest_problems(
        {**good, "devDependencies": {"@types/react": "^19.3.0"}}, workspace
    )  # React's types
    assert manifest_problems(
        {"dependencies": {"graphology": "^0.25.0", "zustand": "^5.0.2"}}, workspace
    )  # another range


def test_the_source_imports_zustand_only_through_vanilla() -> None:
    bad, seen = zustand_problems(ROOT / "OspreyFlow_Core")
    assert seen >= 1, (
        "the walk found no import of zustand in the package: the store is not there, or the pattern does not match it"
    )
    assert bad == []


def test_an_import_of_zustand_other_than_vanilla_is_found(tmp_path: Path) -> None:
    """Red for the check above, at the store's own line: the real store's `zustand/vanilla` import is clean, and
    `import { create } from "zustand"` in its place (and `zustand/react`, and a type import) is not."""
    store = (SHARED_SRC / "workingset" / "store.ts").read_text(encoding="utf-8")
    line = 'import { createStore, type StoreApi } from "zustand/vanilla";'
    assert line in store, "the store no longer imports zustand/vanilla by that line"
    target = tmp_path / "packages" / "glass-shared" / "src" / "workingset" / "store.ts"
    target.parent.mkdir(parents=True)
    target.write_text(store, encoding="utf-8")
    assert zustand_problems(tmp_path) == ([], 1)
    for planted in (
        'import { create } from "zustand";',
        'import { useStore } from "zustand/react";',
        'import type { StoreApi } from "zustand";',
        'import { create } from "zustand/traditional";',
    ):
        target.write_text(store.replace(line, planted, 1), encoding="utf-8")
        assert len(zustand_problems(tmp_path)[0]) == 1, f"{planted} is not found"


def test_the_lint_rule_refuses_the_zustand_that_pulls_in_react() -> None:
    """The lint block for the package is what sees a type import and a name no bundle reaches (`eslint.config.js`).
    The real store's line is let through; the main entry, `zustand/react` and their type imports are refused."""
    assert (
        eslint_refusals(
            'import { createStore } from "zustand/vanilla";\nexport const s = createStore;\n'
        )
        == []
    )
    for planted in (
        'import { create } from "zustand";\nexport const s = create;\n',
        'import { useStore } from "zustand/react";\nexport const s = useStore;\n',
        'import type { StoreApi } from "zustand";\nexport type S = StoreApi<number>;\n',
    ):
        assert eslint_refusals(planted), f"the lint rule lets {planted.splitlines()[0]!r} through"


@pytest.mark.parametrize("filename", ["planted.ts", "planted.tsx", "planted.mts", "planted.cts"])
def test_the_lint_selectors_refuse_the_zustand_that_pulls_in_react_as_a_type_or_a_dynamic_import(
    filename: str,
) -> None:
    """The `zustand(?!\\/vanilla$)` part of `SHARED_BANNED_MODULE` (rule 15): feeds the two selectors for the
    `import("zustand")` that is not an import statement. The `zustand/vanilla` entry is let through in both shapes first,
    so what is refused is the lookahead's work and not a blanket ban on the name; then the main entry and `zustand/react`
    are refused in both, in every extension the lint block covers."""
    for allowed in (
        'export type S = import("zustand/vanilla").StoreApi<number>;\n',
        'export const later = () => import("zustand/vanilla");\n',
    ):
        assert eslint_syntax_refusals(allowed, filename) == [], f"{allowed.strip()!r} is refused"
    for planted in (
        'export type S = import("zustand").StoreApi<number>;\n',
        'export type S = import("zustand/react").UseBoundStore<number>;\n',
        'export const later = () => import("zustand");\n',
        'export const later = () => import("zustand/react");\n',
    ):
        assert len(eslint_syntax_refusals(planted, filename)) == 1, (
            f"the lint selectors let {planted.strip()!r} through in {filename}"
        )


# --------------------------------------------------------------------------------------------------- the four gates

#: The files each gate read on main before the move (so a move that dropped a root, or a gate that read fewer files,
#: shows as a fall): the number each reported or, where it reports none, the files its own rules select.
FILES_BEFORE = {"colour-drift": 482, "design-check": 890, "ui-words": 488, "no-branches": 1734}


def _design_files(roots: Iterable[Path]) -> int:
    return sum(
        1
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".css", ".ts", ".tsx"}
        and "node_modules" not in path.parts
    )


def _ui_words_files(roots: Iterable[Path]) -> int:
    return sum(
        1
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in ui_words_check.SUFFIXES
        and "node_modules" not in path.parts
        and not ui_words_check._skipped(path.relative_to(root))
    )


def _ui_words_roots() -> list[Path]:
    return [
        ui_words_check.GLASS_SRC,
        ui_words_check.DESIGN_PACKAGE,
        *([p] if (p := getattr(ui_words_check, "SHARED_SRC", None)) else []),
    ]


def test_each_gate_reads_packages_glass_shared_src() -> None:
    assert SHARED_SRC.is_dir()
    roots = {
        "colour-drift": [root for root, _ in colour_drift_check.SCANNED],
        "design-check": list(design_check.SCANNED),
        "ui-words": _ui_words_roots(),
        "no-branches": [CORE / top for top in no_branches_check.SCANNED],
    }
    for gate, held in roots.items():
        assert SHARED_SRC in held, f"{gate} does not read packages/glass-shared/src"


def test_each_gate_reads_no_fewer_files_than_before() -> None:
    now = {
        "colour-drift": colour_drift_check.scanned_count(),
        "design-check": _design_files(design_check.SCANNED),
        "ui-words": _ui_words_files(_ui_words_roots()),
        "no-branches": len(no_branches_check.tree_files()),
    }
    assert all(now[gate] >= before for gate, before in FILES_BEFORE.items()), (
        f"a gate reads fewer files than before: now {now}, before {FILES_BEFORE}"
    )
    # The files that moved are among the ones read: six more than the package held (its tests are not read).
    assert all(
        now[gate] > FILES_BEFORE[gate] for gate in ("colour-drift", "design-check", "no-branches")
    ), now


@pytest.fixture
def shared_copy(tmp_path: Path) -> Path:
    """`<tmp>/packages/glass-shared/src`, a copy of the real folder; the real one is never written."""
    copy = tmp_path / "packages" / "glass-shared" / "src"
    shutil.copytree(SHARED_SRC, copy, ignore=shutil.ignore_patterns("node_modules"))
    return copy


def test_the_colour_drift_check_reports_a_plant_in_the_package(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The shape a stray colour takes in a plain module: a hex in a style object.
    plant = shared_copy / "planted.ts"
    mirrors = dict(colour_drift_check.SCANNED).get(SHARED_SRC)
    assert mirrors is not None, "the colour-drift check does not read packages/glass-shared/src"
    monkeypatch.setattr(colour_drift_check, "CORE", shared_copy.parent.parent.parent)
    monkeypatch.setattr(colour_drift_check, "SCANNED", ((shared_copy, mirrors),))
    assert colour_drift_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    plant.write_text(
        'export const stripe = { background: "#12ab34", padding: 8 };\n', encoding="utf-8"
    )
    assert colour_drift_check.main() == 1
    assert "packages/glass-shared/src/planted.ts:1: #12ab34" in capsys.readouterr().out


def test_the_design_detector_reports_a_plant_in_the_package(
    shared_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert SHARED_SRC in design_check.SCANNED, (
        "the design check does not read packages/glass-shared/src"
    )
    # The gate's own call is `unexcused(detect(SCANNED))`, its package root pointed at the copy.
    monkeypatch.setattr(design_check, "SCANNED", [shared_copy])
    assert design_check.unexcused(design_check.detect(design_check.SCANNED)) == [], (
        "the clean copy already has findings"
    )
    plant = shared_copy / "planted.ts"
    # The shape the old toast had, as a plain module holds a style: a side stripe on a card-like object.
    plant.write_text(
        "export const TOAST_STYLE = {\n"
        '  background: "var(--surface-raised)", borderLeft: "3px solid var(--error)", borderRadius: "8px",\n'
        '  padding: "12px 16px", boxShadow: "var(--overlay-shadow)",\n'
        "};\n",
        encoding="utf-8",
    )
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [("planted.ts", "side-tab")]


def test_the_ui_words_check_reports_a_plant_in_the_package(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert getattr(ui_words_check, "SHARED_SRC", None) == SHARED_SRC, (
        "the UI-words check does not read packages/glass-shared/src"
    )
    empty = shared_copy.parent.parent / "no-src"
    empty.mkdir()
    monkeypatch.setattr(ui_words_check, "SHARED_SRC", shared_copy)
    monkeypatch.setattr(ui_words_check, "GLASS_SRC", empty)
    monkeypatch.setattr(ui_words_check, "DESIGN_PACKAGE", empty)
    assert ui_words_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    # The shape a words table's constant takes in a plain module.
    (shared_copy / "planted.ts").write_text(
        'export const LABEL = "Target model";\n', encoding="utf-8"
    )
    assert ui_words_check.main() == 1
    assert "packages/glass-shared/src/planted.ts:1:" in capsys.readouterr().out


def test_the_no_branches_check_reports_a_plant_in_the_package(
    shared_copy: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    top = "packages/glass-shared/src"
    assert top in no_branches_check.SCANNED, (
        "the no-branches check does not read packages/glass-shared/src"
    )
    # `tree_files` binds its defaults at definition: the gate's walk is replaced, not a constant. It is given the
    # gate's own SCANNED entry for the package, in the temporary copy's place.
    walk = no_branches_check.tree_files
    tmp_core = shared_copy.parent.parent.parent
    monkeypatch.setattr(no_branches_check, "tree_files", lambda: walk(tmp_core, [top]))
    assert no_branches_check.main() == 0, "the clean copy of the package is already reported"
    capsys.readouterr()
    (shared_copy / "planted.ts").write_text(
        'export const BRANCH_CASE = "branch-by-filter";\n', encoding="utf-8"
    )
    assert no_branches_check.main() == 1
    assert f"{top}/planted.ts:1:" in capsys.readouterr().out


def test_the_no_branches_check_still_excuses_only_the_registry_s_one_pipeline_line() -> None:
    """The registry holds one action named for a pipeline's branch in the Studio's DAG, which the check now reads (it
    sat outside `apps/workspace/src`). It is excused by that line's exact text, not the file: a case's branch written
    anywhere else in the registry is still found."""
    registry = (SHARED_SRC / "keyboard" / "actionRegistry.ts").read_text(encoding="utf-8")
    path = "packages/glass-shared/src/keyboard/actionRegistry.ts"
    assert no_branches_check.findings({path: registry}) == []
    assert (
        no_branches_check.findings({path: registry + '\nexport const X = "branch-by-filter";\n'})
        != []
    )


# ---------------------------------------------------------------------------------------------------- the images


def test_the_two_images_copy_the_package_s_source() -> None:
    workspace = (ROOT / WORKSPACE_DOCKERFILE).read_text(encoding="utf-8")
    harness = _frontend_stage((ROOT / HARNESS_DOCKERFILE).read_text(encoding="utf-8"))
    assert image_problems(workspace) == [], "apps/workspace/Dockerfile"
    assert image_problems(harness) == [], "harness/Dockerfile's frontend-builder"


def test_an_image_without_the_copy_or_with_more_is_found() -> None:
    """Red for the check above (rule 15): each real stage with only the line taken out, as the Dockerfile writes it,
    and with the whole folder copied in its place."""
    line = "COPY packages/glass-shared/src ./packages/glass-shared/src\n"
    for path, stage in ((WORKSPACE_DOCKERFILE, lambda t: t), (HARNESS_DOCKERFILE, _frontend_stage)):
        real = stage((ROOT / path).read_text(encoding="utf-8"))
        assert line in real, f"{path} has no `{line.strip()}` line"
        assert image_problems(real) == []
        assert image_problems(real.replace(line, "", 1))
        assert image_problems(
            real.replace(line, "COPY packages/glass-shared ./packages/glass-shared\n", 1)
        )
