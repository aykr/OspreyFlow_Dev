"""`primitives.css`, `scale.css` and `panelType.css` live in `packages/design`, and nothing names the place they came
from (ADR-152 decision 6; slice PL4b2, the third of the PL4 slices; the owner's ruling of 20 November 2026 on "the rest of
the design folder").

The three files moved from `OspreyFlow_Core/apps/workspace/src/design/` to `OspreyFlow_Core/packages/design/`, their
bytes unchanged and `primitives.css` still `@import`ing the other two by `./`, and every file that named the old place
followed them: about 80 imports, nine Vitest readers, the colour-drift check's reach, the install-page stamp and the guides.
This file is the proof that none was left behind and that each guard of the move can fail. (`tokens.css` moved in slice
PL4b: `test_design_tokens_location.py`; the `.tsx` primitives and `fonts.ts` stay in the workspace.)

Which test fails if the invariant is broken (rule 12):

* a file is not where it should be, or an old one is back: `test_the_three_files_are_in_packages_design_and_not_in_the_workspace`;
* a file of any kind still names an old path, in any of the forms the repository writes it in (a path to open, import,
  copy or cite; `/`-joined or written apart; or the bare name inside the old folder): `test_no_tracked_file_names_an_old_path`,
  which walks `git ls-files` over the **whole repository**: `OspreyFlow_Core`, `OspreyFlow_Build` (spec, tests, tools,
  scripts, guides) and the repository root's own files. Only the places below may keep an old path (`HISTORY` and `NAMED`);
* an import that does not reach the one file, or a `primitives.css` that no longer pulls in the other two, in the order
  the cascade reads them: `test_every_import_of_the_three_files_reaches_the_one_file` and
  `test_primitives_css_still_imports_the_other_two_in_order`;
* the colour-drift check that stops looking at the three when they leave the Glass's folder, or stops saying how many
  files it read: `test_the_colour_drift_check_scans_no_fewer_files_than_before` and
  `test_the_drift_check_walks_the_three_files_in_packages_design`;
* the install-page stamp: the images and the two stamp lists already hold `packages/design` (PL4b), so the three files
  are inside them (`test_the_images_and_the_stamp_lists_hold_the_folder_the_files_are_in`), and the move changed no
  stamped byte but the paths: `test_the_move_changed_no_stamped_byte_but_the_paths`.

Each guard is shown red on a planted regression in the shape the real code writes it (rule 15): the planted lines are the
lines that were in the tree on the day before the move, one case per shape, each placed at the path of the file that held
it. A plant that some other rule would also have caught proves nothing, so each case first shows the same file with the
new path clean.
"""

# The planted lines below are the real call-site shapes, kept on one line as the tree wrote them (rule 15), and the
# prose beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import difflib
import re
import subprocess
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest
from tools import colour_drift_check
from tools.layout import CORE, ROOT

NAMES = ("primitives.css", "scale.css", "panelType.css")
NEW_DIR = "OspreyFlow_Core/packages/design/"
OLD_DIR = "OspreyFlow_Core/apps/workspace/src/design/"
NEW_RELS = tuple(NEW_DIR + name for name in NAMES)
OLD_RELS = tuple(OLD_DIR + name for name in NAMES)
PRIMITIVES = NEW_DIR + "primitives.css"

#: The places that may name an old path because they are a record of the past (the decision log, and the build record
#: under `process/`, which holds the lanes' briefs, the build plan and the handovers). They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone.
NAMED = {
    # The citation check's allowlist: the decision log and the records name the old paths, and the allowlist says why
    # that is not a dead citation. It must name them to do so.
    "OspreyFlow_Build/tests/fixtures/citation_allowlist.txt": "the allowlist for the records that name the old paths",
    # Slice PL4b's test builds a tree as it was before the tokens moved, with `design/primitives.css` as one of its
    # files in a temporary folder; the name is the layout it models, not a place in this repository.
    "OspreyFlow_Build/tests/glass_trees/test_design_tokens_location.py": "a test that models the layout before PL4b",
    # This file: it spells out the old paths to look for them.
    "OspreyFlow_Build/tests/glass_trees/test_design_css_location.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old paths, found

_ANY = "(?:primitives|scale|panelType)"
#: `design/<name>`, as a path that is written out: not `packages/design/<name>` (the new one).
_TEXT_FORM = re.compile(rf"(?<!packages/)design/{_ANY}\.css")
#: The segments of it written apart: Python's `/ "design" / "primitives.css"`, TypeScript's `join(here, "..", "design", "scale.css")`
#: (the gap may be a line break inside the brackets).
_SEGMENT_FORM = re.compile(rf"""["']design["']\s*[,/]\s*["']{_ANY}\.css["']""")
_PACKAGES_SEGMENT = re.compile(r"""["']packages["']\)?\s*[,/]\s*$""")
_DESIGN_SEGMENT = re.compile(r"""["']design["']\s*[,/]\s*$""")
#: Inside the old folder itself, a file was named bare: `join(__dirname, "primitives.css")`, `"../primitives.css"`.
_BARE_FORM = re.compile(rf"""["'](?:\./|\.\./)?{_ANY}\.css["']""")


def old_path_mentions(root: Path, rels: Iterable[str]) -> list[tuple[str, int, str]]:
    """`(file, line, text)` for each place under `root` that names an old path. `rels` are repository-relative."""
    found: list[tuple[str, int, str]] = []
    for rel in rels:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # gone from the working tree, or not text
        forms = [_TEXT_FORM, _SEGMENT_FORM]
        if rel.startswith(OLD_DIR):
            forms.append(_BARE_FORM)
        for form in forms:
            for hit in form.finditer(text):
                if form is _SEGMENT_FORM and _PACKAGES_SEGMENT.search(text[: hit.start()]):
                    continue  # `"packages", "design", "primitives.css"` is the new place written apart
                if form is _BARE_FORM and _DESIGN_SEGMENT.search(text[: hit.start()]):
                    continue  # `"design", "primitives.css"` is a path written apart, not the bare name
                line = text.count("\n", 0, hit.start()) + 1
                found.append((rel, line, text.splitlines()[line - 1].strip()))
    return sorted(set(found))


def tracked(root: Path = ROOT) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return sorted(name for name in out.decode("utf-8").split("\0") if name)


def _kept_out(rel: str) -> bool:
    """History and the named exceptions are not looked at. `test_every_named_exception_still_has_its_reason` turns red
    the day one no longer names an old path, so that it is looked at again."""
    if rel in NAMED:
        return True
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in HISTORY)


# ----------------------------------------------------------------------------------------------------- the imports

_IMPORT = re.compile(
    rf"""(?:\bfrom\s*|\bimport\s*\(?\s*|@import\s+(?:url\()?\s*)["']([^"']*{_ANY}\.css[^"']*)["']"""
)
_SOURCE_SUFFIXES = {".ts", ".tsx", ".mts", ".mjs", ".js", ".jsx", ".css"}


def imports_not_reaching(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The imports of one of the three files that do not resolve to that file in `root`'s `packages/design`, and how
    many imports were looked at."""
    bad: list[str] = []
    seen = 0
    for rel in rels:
        path = root / rel
        if path.suffix not in _SOURCE_SUFFIXES or not rel.startswith("OspreyFlow_Core/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for hit in _IMPORT.finditer(text):
            seen += 1
            target = (path.parent / hit.group(1).split("?", 1)[0]).resolve()
            if target != (root / NEW_DIR / target.name).resolve() or not target.is_file():
                bad.append(f"{rel}: {hit.group(1)}")
    return bad, seen


_CSS_IMPORT = re.compile(r"""^@import\s+["']\./(scale|panelType)\.css["'];""", re.M)


def primitives_problems(root: Path) -> list[str]:
    """What is wrong with `primitives.css` as the owner of the other two: each `@import`ed once, by `./`, resolving to a
    file beside it, `scale.css` first and `panelType.css` after it (the cascade reads them in order: a panel's own rule
    wins a tie by being later)."""
    path = root / PRIMITIVES
    if not path.is_file():
        return [f"{PRIMITIVES} is not there"]
    text = path.read_text(encoding="utf-8")
    order = [hit.group(1) for hit in _CSS_IMPORT.finditer(text)]
    problems = []
    if order != ["scale", "panelType"]:
        problems.append(f"imports {order}, not ['scale', 'panelType'] in that order")
    for name in ("scale.css", "panelType.css"):
        if not (path.parent / name).is_file():
            problems.append(f"./{name} does not resolve beside primitives.css")
    return problems


# ---------------------------------------------------------------------------------------------------- the images

_COPY_DESIGN = re.compile(r"^COPY\s+packages/design(?:/\S*)?\s+\S+\s*$", re.M)
WORKSPACE_DOCKERFILE = "OspreyFlow_Core/apps/workspace/Dockerfile"
HARNESS_DOCKERFILE = "OspreyFlow_Core/harness/Dockerfile"


def _frontend_stage(dockerfile: str) -> str:
    return dockerfile.split("AS frontend-builder", 1)[1].split("\nFROM ", 1)[0]


# --------------------------------------------------------------------------------------------- the real tree: cases


def test_the_three_files_are_in_packages_design_and_not_in_the_workspace() -> None:
    names = tracked()
    for new, old in zip(NEW_RELS, OLD_RELS, strict=True):
        assert (ROOT / new).is_file(), f"{new} is not in packages/design"
        assert not (ROOT / old).exists(), f"{old} is still where it was"
        assert new in names and old not in names


def test_no_tracked_file_names_an_old_path() -> None:
    rels = [rel for rel in tracked() if not _kept_out(rel)]
    assert len(rels) > 1000, (
        "the walk found too few files: git ls-files is not listing the repository"
    )
    found = old_path_mentions(ROOT, rels)
    shown = "\n".join(f"  {rel}:{line}: {text[:140]}" for rel, line, text in found[:40])
    assert found == [], (
        f"{len(found)} place(s) still name an old path; the files are now in {NEW_DIR}:\n{shown}"
    )


def test_every_named_exception_still_has_its_reason() -> None:
    """An exception outlives its reason when the file it excuses no longer names an old path. Left in `NAMED` it keeps
    that file outside the walk, and an old path could be written back into it unseen (rule 12). Each name must still hold
    an old path; when one does not, remove it from `NAMED`."""
    stale = [rel for rel in NAMED if not old_path_mentions(ROOT, [rel])]
    assert stale == [], (
        f"{stale} no longer name an old path: remove them from NAMED, and the walk will cover them"
    )


def test_every_import_of_the_three_files_reaches_the_one_file() -> None:
    bad, seen = imports_not_reaching(ROOT, tracked())
    assert seen >= 70, (
        "the walk found too few imports of the three files: the pattern no longer matches the sources"
    )
    assert bad == [], f"{len(bad)} import(s) do not reach {NEW_DIR}: {bad[:10]}"
    # The entrances of the two front ends are among those looked at, whatever the count; and `tokens.css` still comes
    # first in each (the built CSS follows that order).
    for entrance in (
        "OspreyFlow_Core/apps/workspace/src/main.tsx",
        "OspreyFlow_Core/apps/harness/src/main.tsx",
    ):
        assert imports_not_reaching(ROOT, [entrance])[1] == 1, (
            f"{entrance} does not import primitives.css once"
        )
        text = (ROOT / entrance).read_text(encoding="utf-8")
        assert 0 <= text.index("tokens.css") < text.index("primitives.css"), (
            f"{entrance}: the tokens must be imported before the primitives"
        )


def test_primitives_css_still_imports_the_other_two_in_order() -> None:
    assert primitives_problems(ROOT) == []


def test_the_images_and_the_stamp_lists_hold_the_folder_the_files_are_in() -> None:
    """Nothing more is needed in the images or the stamp for the three: they are inside `packages/design`, which both
    images copy and both stamp lists name since PL4b."""
    from harness import install_page_build

    workspace = (ROOT / WORKSPACE_DOCKERFILE).read_text(encoding="utf-8")
    harness = (ROOT / HARNESS_DOCKERFILE).read_text(encoding="utf-8")
    assert _COPY_DESIGN.search(workspace), "apps/workspace/Dockerfile does not COPY packages/design"
    assert _COPY_DESIGN.search(_frontend_stage(harness)), (
        "harness/Dockerfile's frontend-builder does not COPY packages/design"
    )
    stamp = (CORE / "apps" / "harness" / "scripts" / "stamp.mjs").read_text(encoding="utf-8")
    block = stamp.split("export const SOURCES = [", 1)[1].split("];", 1)[0]
    assert '"packages/design"' in block and "packages/design" in install_page_build.SOURCES
    for new in NEW_RELS:  # directly inside the folder that is copied and stamped, not a subfolder
        assert (ROOT / new).parent == CORE / "packages" / "design"


# The install-page stamp (`apps/harness/scripts/stamp.mjs` and `harness/install_page_build.py` list the same folders; the
# hash holds each file's path and its byte hash, so a move changes the stamp even when no byte moved).

_PRODUCT = "OspreyFlow_Core/"
_SOURCES = ("apps/harness/src", "apps/harness/index.html", "apps/harness/package.json",
            "apps/workspace/src/design", "apps/workspace/src/theme", "packages/design")  # fmt: skip


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def _stamped(commit: str) -> dict[str, str]:
    """The stamped files of `commit` as `{path: blob id}`; a blob id is a hash of the file's bytes."""
    found: dict[str, str] = {}
    for source in _SOURCES:
        for line in _git("ls-tree", "-r", commit, "--", _PRODUCT + source).splitlines():
            meta, path = line.split("\t", 1)
            parts = path[len(_PRODUCT) :].split("/")
            if any(p.startswith(".") or p in {"node_modules", "Icon\r"} for p in parts):
                continue
            found[path[len(_PRODUCT) :]] = meta.split()[2]
    return found


def _move_commits() -> set[str]:
    """The commit that renamed each of the three files with its bytes unchanged, one entry per file (a set of one when
    they moved together, as they must)."""
    found = set()
    for new in NEW_RELS:
        out = _git(
            "log", "--follow", "-M100%", "--diff-filter=R", "--format=%H", "-1", "--", new
        ).strip()
        found.add(out)
    return found


def more_than_the_path(
    paths: Iterable[str], was: Callable[[str], str], now: Callable[[str], str]
) -> list[str]:
    """The stamped files, of those named, that differ in more than the lines naming one of the three files."""
    problems = []
    for path in paths:
        changes = [
            d
            for d in difflib.ndiff(was(path).splitlines(), now(path).splitlines())
            if d[:2] in {"- ", "+ "}
        ]
        removed = sum(d[:2] == "- " for d in changes)
        if (
            not changes
            or removed * 2 != len(changes)
            or not all(any(name in d for name in NAMES) for d in changes)
        ):
            problems.append(
                f"{path}: {[d for d in changes if not any(n in d for n in NAMES)] or 'lines added or removed'}"
            )
    return problems


def test_a_stamped_file_changed_in_more_than_the_css_path_is_found() -> None:
    """Red for the comparison below (rule 15): a Vitest reader's real line moved, once alone and once with a second line
    changed beside it."""
    old = 'const CSS = readFileSync(join(__dirname, "primitives.css"), "utf-8");\nimport "./x";\n'
    moved = 'const CSS = readFileSync(join(__dirname, "../../../../packages/design/primitives.css"), "utf-8");\nimport "./x";\n'
    moved_and_more = moved.replace('"./x"', '"./y"')
    assert more_than_the_path(["a.test.ts"], lambda _: old, lambda _: moved) == []
    assert len(more_than_the_path(["a.test.ts"], lambda _: old, lambda _: moved_and_more)) == 1
    assert len(more_than_the_path(["a.test.ts"], lambda _: old, lambda _: old + "x\n")) == 1


def test_the_move_changed_no_stamped_byte_but_the_paths() -> None:
    """The stamp hashes each stamped file's path and its bytes. The owner accepts the new stamp on one condition: that the
    files stamped before the move and after it hold the same bytes, and only their paths differ. This lists both by byte
    hash at the commit that moved the files and the one before it. (A shallow clone has no history to read: skipped, and
    the commit's own run on a full clone is the proof.)"""
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        pytest.skip("a shallow clone has no history: the move commit cannot be read")
    commits = _move_commits()
    assert len(commits) == 1 and "" not in commits, (
        "no one commit in history moved primitives.css, scale.css and panelType.css to packages/design as pure renames "
        f"(the file bytes unchanged): {commits}"
    )
    (commit,) = commits
    before, after = _stamped(f"{commit}^"), _stamped(commit)
    moved = {"apps/workspace/src/design/" + name: "packages/design/" + name for name in NAMES}
    for old, new in moved.items():
        assert old in before and new in after, f"{old} or {new} is not stamped"
        assert before[old] == after[new], f"{new}'s bytes changed in the move"
    gone, came = (
        Counter(before.values()) - Counter(after.values()),
        Counter(after.values()) - Counter(before.values()),
    )
    differing = sorted(
        {p for p, blob in before.items() if gone[blob]}
        | {p for p, blob in after.items() if came[blob]}
    )
    # A stamped file whose bytes had to change is one that names a moved file: the harness entrance, and the Vitest readers
    # in the stamped folders. In each, only the lines that name one of the three differ, the same number each side.
    assert "apps/harness/src/main.tsx" in differing, (
        f"the harness entrance is not among the changed files: {differing}"
    )
    problems = more_than_the_path(
        [p for p in differing if p not in moved and p not in moved.values()],
        lambda path: _git("show", f"{commit}^:{_PRODUCT}{path}"),
        lambda path: _git("show", f"{commit}:{_PRODUCT}{path}"),
    )
    assert problems == [], problems
    assert set(after) - set(before) == set(moved.values()), (
        "a stamped file other than the three appeared"
    )
    assert set(before) - set(after) == set(moved), "a stamped file other than the three went"


# The colour-drift check walked `apps/workspace/src`, where `primitives.css` was. PL4b added `packages/design` to the walk
# (with `tokens.css` exempt by name there); with the three files moved, that walk is what keeps them held to the palette.

#: Scanned on the day before the move (482: `primitives.css`, `scale.css` and `panelType.css` among them, under
#: `apps/workspace/src`). It does not fall without someone deciding it should: a file that leaves the folders the check
#: walks for one it does not lowers the count, and this fails (slices C and D rely on it).
SCANNED_BEFORE_THE_MOVE = 482


def test_the_colour_drift_check_scans_no_fewer_files_than_before(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert colour_drift_check.scanned_count() >= SCANNED_BEFORE_THE_MOVE
    colour_drift_check.main()
    said = re.search(r"scanned (\d+) files", capsys.readouterr().out)
    assert said, "the check does not say how many files it scanned"
    assert int(said.group(1)) == colour_drift_check.scanned_count() >= SCANNED_BEFORE_THE_MOVE


def test_the_drift_check_walks_the_three_files_in_packages_design() -> None:
    scanned = {
        path.relative_to(colour_drift_check.DESIGN_PACKAGE).as_posix()
        for path in colour_drift_check.scanned_files(
            colour_drift_check.DESIGN_PACKAGE, colour_drift_check.TOKENS_FILES
        )
    }
    assert set(NAMES) <= scanned, (
        f"the check does not walk {set(NAMES) - scanned} in packages/design"
    )
    assert "tokens.css" not in scanned, "the tokens are exempt by name in their own folder"


# ------------------------------------------------------------------------------- planted regressions (red, rule 15)
# Each plant is a line as the tree held it before the move, put at the path of the file that held it.


def _tree(tmp_path: Path, files: dict[str, str]) -> list[str]:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return sorted(files)


#: (id, file, the old line, the same line at the new place)
READERS = [
    (
        "vitest-join-dirname-bare",
        OLD_DIR + "accordionStyle.test.ts",
        'const CSS = readFileSync(join(__dirname, "primitives.css"), "utf-8").replace(/\\/\\*[\\s\\S]*?\\*\\//g, "");',
        'const CSS = readFileSync(join(__dirname, "../../../../packages/design/primitives.css"), "utf-8").replace(/\\/\\*[\\s\\S]*?\\*\\//g, "");',
    ),
    (
        "vitest-join-up-one-folder",
        OLD_DIR + "primitives/Toast.test.tsx",
        '    const css = readFileSync(join(__dirname, "..", "primitives.css"), "utf-8");',
        '    const css = readFileSync(join(__dirname, "..", "..", "..", "..", "..", "packages", "design", "primitives.css"), "utf-8");',
    ),
    (
        "vitest-import-meta-url",
        OLD_DIR + "topBarStyle.test.ts",
        '  join(dirname(fileURLToPath(import.meta.url)), "primitives.css"),',
        '  join(dirname(fileURLToPath(import.meta.url)), "../../../../packages/design/primitives.css"),',
    ),
    (
        "vitest-from-the-shell-folder",
        "OspreyFlow_Core/apps/workspace/src/shell/topBarWidths.test.ts",
        'const CSS = readFileSync(join(__dirname, "../design/primitives.css"), "utf-8").replace(/\\/\\*[\\s\\S]*?\\*\\//g, "");',
        'const CSS = readFileSync(join(__dirname, "../../../../packages/design/primitives.css"), "utf-8").replace(/\\/\\*[\\s\\S]*?\\*\\//g, "");',
    ),
    (
        "vitest-segments-in-the-old-folder",
        OLD_DIR + "shellSizes.test.ts",
        'const SCALE = readFileSync(join(__dirname, "scale.css"), "utf-8");',
        'const SCALE = readFileSync(join(__dirname, "../../../../packages/design/scale.css"), "utf-8");',
    ),
    (
        "vitest-segments-written-apart",
        "OspreyFlow_Core/apps/workspace/src/home/homeKey.test.ts",
        'const panel = readFileSync(join(here, "..", "design", "panelType.css"), "utf8");',
        'const panel = readFileSync(join(here, "..", "..", "..", "..", "packages", "design", "panelType.css"), "utf8");',
    ),
    (
        "css-comment",
        "OspreyFlow_Core/apps/workspace/src/questions/askPage.css",
        "/* The drawer's shape: the workspace's drawer (`.drawer`, `design/primitives.css`), its title the panel title's size. */",
        "/* The drawer's shape: the workspace's drawer (`.drawer`, `packages/design/primitives.css`), its title the panel title's size. */",
    ),
    (
        "css-comment-panel-type",
        "OspreyFlow_Core/apps/workspace/src/views/views.css",
        "   Its 16 px here is never what is drawn: the panel is always in a drawer, where `design/panelType.css` sets",
        "   Its 16 px here is never what is drawn: the panel is always in a drawer, where `packages/design/panelType.css` sets",
    ),
    (
        "guide-prose",
        "OspreyFlow_Core/DESIGN.md",
        "notification banner at 19px under the brand, by design. `OspreyFlow_Core/apps/workspace/src/design/panelType.css` holds this,",
        "notification banner at 19px under the brand, by design. `OspreyFlow_Core/packages/design/panelType.css` holds this,",
    ),
    (
        "guide-prose-scale",
        "OspreyFlow_Build/spec/design/DESIGN.md",
        "or select inherits the page's font (`src/design/scale.css`). A heading drawn as a label (`.label`) stays the",
        "or select inherits the page's font (`packages/design/scale.css`). A heading drawn as a label (`.label`) stays the",
    ),
]


@pytest.mark.parametrize(("name", "rel", "old", "new"), READERS, ids=[r[0] for r in READERS])
def test_a_reader_that_names_an_old_path_is_found(
    tmp_path: Path, name: str, rel: str, old: str, new: str
) -> None:
    clean = _tree(tmp_path, {rel: f"{new}\n"})
    assert old_path_mentions(tmp_path, clean) == [], f"the new-path form of {name} must be clean"
    _tree(tmp_path, {rel: f"// before\n{old}\n"})
    assert [(r, n) for r, n, _ in old_path_mentions(tmp_path, [rel])] == [(rel, 2)], (
        f"{name} was not found"
    )


def test_the_old_path_is_found_when_a_python_path_breaks_across_lines(tmp_path: Path) -> None:
    rel = "OspreyFlow_Build/tests/harness/test_x.py"
    old = 'CSS = (\n    REPO_ROOT\n    / "apps"\n    / "src"\n    / "design"\n    / "primitives.css"\n).read_text()\n'
    _tree(tmp_path, {rel: old})
    assert old_path_mentions(tmp_path, [rel]), "a path broken across lines was not found"
    _tree(tmp_path, {rel: old.replace('/ "src"\n    / "design"', '/ "packages"\n    / "design"')})
    assert old_path_mentions(tmp_path, [rel]) == [], (
        "the new place written apart is not the old one"
    )


def test_the_bare_name_is_only_an_old_path_inside_the_old_folder(tmp_path: Path) -> None:
    """`"primitives.css"` is an old path only beside the folder it left; elsewhere (`packages/design`, where the three sit
    together and `primitives.css` imports `./scale.css`) it is just a file's name."""
    elsewhere = "OspreyFlow_Core/packages/design/other.test.ts"
    _tree(tmp_path, {elsewhere: 'join(__dirname, "primitives.css"); @import "./scale.css";\n'})
    assert old_path_mentions(tmp_path, [elsewhere]) == []


def test_the_tokens_files_are_not_these_moves_to_chase(tmp_path: Path) -> None:
    rels = _tree(
        tmp_path,
        {
            "OspreyFlow_Core/x.ts": "// `design/tokens.css` and `design/primitives/Button.tsx` stay put\n"
        },
    )
    assert old_path_mentions(tmp_path, rels) == []


IMPORTS = [
    (
        "the workspace entrance",
        "OspreyFlow_Core/apps/workspace/src/main.tsx",
        'import "./design/primitives.css";',
        'import "../../../packages/design/primitives.css";',
    ),
    (
        "a showcase",
        "OspreyFlow_Core/apps/workspace/a11y/showcase.tsx",
        'import "../src/design/primitives.css";',
        'import "../../../packages/design/primitives.css";',
    ),
    (
        "a keyboard harness",
        "OspreyFlow_Core/apps/workspace/keyboard/admin-harness.tsx",
        'import "../src/design/primitives.css";',
        'import "../../../packages/design/primitives.css";',
    ),
    (
        "the harness entrance",
        "OspreyFlow_Core/apps/harness/src/main.tsx",
        'import "../../workspace/src/design/primitives.css";',
        'import "../../../packages/design/primitives.css";',
    ),
    (
        "a harness spec's page",
        "OspreyFlow_Core/apps/harness/keyboard/setup-harness.tsx",
        'import "../../workspace/src/design/primitives.css";',
        'import "../../../packages/design/primitives.css";',
    ),
]


@pytest.mark.parametrize(("name", "rel", "old", "new"), IMPORTS, ids=[i[0] for i in IMPORTS])
def test_an_import_that_does_not_reach_the_one_file_is_found(
    tmp_path: Path, name: str, rel: str, old: str, new: str
) -> None:
    _tree(tmp_path, {PRIMITIVES: ".x{}\n"})
    # `new` is written for a file three folders below the product; place it so that it resolves from `rel`.
    depth = len(Path(rel).parts) - 2  # below OspreyFlow_Core
    fitted = new.replace("../../../", "../" * depth)
    _tree(tmp_path, {rel: f"{fitted}\n"})
    assert imports_not_reaching(tmp_path, [rel]) == ([], 1), (
        f"the new-path form of {name} must resolve"
    )
    # The old line, resolved from the same place, points at a file that is not there: the old folder holds no copy.
    _tree(tmp_path, {rel: f"import React from 'react';\n{old}\n"})
    bad, seen = imports_not_reaching(tmp_path, [rel])
    assert seen == 1 and len(bad) == 1, f"{name}: the old import was not found"


def test_an_import_of_a_second_copy_of_primitives_is_found(tmp_path: Path) -> None:
    """A second `primitives.css` beside the first is as wrong as the old place: all resolve to the one."""
    rel = "OspreyFlow_Core/apps/workspace/src/main.tsx"
    _tree(tmp_path, {PRIMITIVES: ".x{}\n", "OspreyFlow_Core/apps/workspace/src/theme/primitives.css": ".x{}\n",
                     rel: 'import "./theme/primitives.css";\n'})  # fmt: skip
    assert imports_not_reaching(tmp_path, [rel])[1] == 1
    assert len(imports_not_reaching(tmp_path, [rel])[0]) == 1


def _real(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _real_primitives() -> str:
    """The real file, wherever it is now (so the plants below hold the file's real lines before the move too)."""
    for rel in (PRIMITIVES, OLD_DIR + "primitives.css"):
        if (ROOT / rel).is_file():
            return _real(rel)
    raise AssertionError("primitives.css is nowhere")


def test_primitives_css_with_its_scale_import_removed_is_found(tmp_path: Path) -> None:
    """The real file with line 7 (`@import "./scale.css";`) out, and the other plants in the shapes that would also break
    the cascade: the two imports swapped, an import pointing at a file that is not beside it."""
    real = _real_primitives()
    _tree(tmp_path, {PRIMITIVES: real, NEW_DIR + "scale.css": "s", NEW_DIR + "panelType.css": "p"})
    assert primitives_problems(tmp_path) == [], "the real file, with both beside it, is clean"
    scale, panel = '@import "./scale.css";', '@import "./panelType.css";'
    assert real.count(scale) == 1 and real.count(panel) == 1
    _tree(tmp_path, {PRIMITIVES: real.replace(scale + "\n", "")})
    assert primitives_problems(tmp_path), "the scale import removed was not found"
    _tree(
        tmp_path, {PRIMITIVES: real.replace(scale, "@@").replace(panel, scale).replace("@@", panel)}
    )
    assert primitives_problems(tmp_path), "the two imports swapped were not found"
    _tree(tmp_path, {PRIMITIVES: real})
    (tmp_path / NEW_DIR / "scale.css").unlink()
    assert primitives_problems(tmp_path), "an import with no file beside it was not found"


def test_the_workspace_image_planted_without_its_copy_is_found() -> None:
    """The workspace image's `COPY packages/design` put back as the comment it was before PL4b."""
    real = _real(WORKSPACE_DOCKERFILE)
    assert _COPY_DESIGN.search(real)
    planted = _COPY_DESIGN.sub(
        "# `apps/workspace/src/design`, inside the `COPY apps/workspace` line below.", real
    )
    assert planted != real and not _COPY_DESIGN.search(planted)


def test_the_harness_image_planted_with_the_old_copy_is_found() -> None:
    real = _real(HARNESS_DOCKERFILE)
    assert _COPY_DESIGN.search(_frontend_stage(real))
    planted = _COPY_DESIGN.sub(
        "COPY apps/workspace/src/design ./apps/workspace/src/design", real, count=1
    )
    assert planted != real and not _COPY_DESIGN.search(_frontend_stage(planted))


# The colour-drift check, on a tree in the new layout (its real shape: `apps/workspace/src` and `packages/design`), and
# through `main()` itself, the way `make` runs it: a colour planted outside the tokens in one of the three files.


def _run_the_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    src, design = tmp_path / "apps" / "workspace" / "src", tmp_path / "packages" / "design"
    monkeypatch.setattr(colour_drift_check, "CORE", tmp_path)
    monkeypatch.setattr(colour_drift_check, "GLASS_SRC", src)
    monkeypatch.setattr(colour_drift_check, "DESIGN_PACKAGE", design)
    monkeypatch.setattr(
        colour_drift_check,
        "SCANNED",
        ((src, colour_drift_check.MIRRORS), (design, colour_drift_check.TOKENS_FILES)),
    )
    monkeypatch.setattr(colour_drift_check, "_load_allowlist", lambda: set())
    code = colour_drift_check.main()
    return code, capsys.readouterr().out


def test_a_colour_planted_in_one_of_the_three_files_is_flagged_by_the_check_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real = _real_primitives()
    design = tmp_path / "packages" / "design"
    _tree(design, {"primitives.css": real, "scale.css": "h1 { font-size: 1px; }\n",
                   "panelType.css": ".p { font-size: 1px; }\n",
                   "tokens.css": ":root { --stray: #123456; }\n"})  # fmt: skip
    _tree(tmp_path / "apps" / "workspace" / "src", {"App.tsx": "export {};\n"})
    code, said = _run_the_check(tmp_path, monkeypatch, capsys)
    assert code == 0, (
        f"the real file is clean (and the tokens are exempt in their own folder): {said}"
    )
    assert "scanned 4 files" in said  # three files, one source; the tokens exempt
    # The plants take the shapes the file's own lines have: a declaration in a rule, a fallback inside `var(...)`, an rgba.
    for planted in (
        ".btn { background: #123456; }",
        ".btn { color: var(--text-primary, #654321); }",
        ".btn { box-shadow: 0 0 0 1px rgba(12, 34, 56, 0.4); }",
    ):
        _tree(design, {"primitives.css": real + "\n" + planted + "\n"})
        code, said = _run_the_check(tmp_path, monkeypatch, capsys)
        assert code == 1 and "packages/design/primitives.css:" in said, (
            f"{planted!r} was not flagged: {said}"
        )
    for neighbour in ("scale.css", "panelType.css"):
        _tree(design, {"primitives.css": real, neighbour: ".x { color: #123456; }\n"})
        code, said = _run_the_check(tmp_path, monkeypatch, capsys)
        assert code == 1 and f"packages/design/{neighbour}:1:" in said, (
            f"{neighbour} was not held to the palette"
        )


def test_a_move_of_the_three_files_does_not_lower_the_count(tmp_path: Path) -> None:
    """The same files before and after the move count the same: the three are scanned in both places."""
    before, after = tmp_path / "before", tmp_path / "after"
    files = {"a.tsx": "x", "b.css": "y", "c.test.ts": "z"}
    css = {name: "p" for name in NAMES}
    _tree(before / "src", {**files, **{f"design/{name}": text for name, text in css.items()}})
    _tree(after / "src", files)
    _tree(after / "design", css)
    count_before = len(colour_drift_check.scanned_files(before / "src", frozenset()))
    count_after = len(colour_drift_check.scanned_files(after / "src", frozenset())) + len(
        colour_drift_check.scanned_files(after / "design", frozenset({"tokens.css"}))
    )
    assert count_before == count_after == 5


def test_a_walk_that_forgets_the_new_folder_lowers_the_count(tmp_path: Path) -> None:
    """The regression the count guards: the files leave the folder the check walks, and nothing walks the new one."""
    _tree(tmp_path / "src", {"a.tsx": "x"})
    _tree(tmp_path / "design", {name: "p" for name in NAMES})
    both = ((tmp_path / "src", frozenset()), (tmp_path / "design", frozenset({"tokens.css"})))
    assert colour_drift_check.scanned_count(both) == 4
    assert colour_drift_check.scanned_count(both[:1]) == 1, (
        "dropping the new folder from the walk must lower the count"
    )


def test_an_exception_that_no_longer_names_an_old_path_is_stale(tmp_path: Path) -> None:
    """Red for `test_every_named_exception_still_has_its_reason` (rule 15): the citation allowlist as it is, with its
    entries for the old paths, and with them removed."""
    rel = "OspreyFlow_Build/tests/fixtures/citation_allowlist.txt"
    _tree(tmp_path, {rel: "# Moved by PL4 slice B2.\napps/workspace/src/design/primitives.css\n"})
    assert old_path_mentions(tmp_path, [rel]), "the allowlist naming an old path keeps its reason"
    _tree(tmp_path, {rel: "# Nothing moved here.\nscripts/launch.py\n"})
    assert old_path_mentions(tmp_path, [rel]) == [], "without one, its exception is stale"
    assert rel in NAMED
