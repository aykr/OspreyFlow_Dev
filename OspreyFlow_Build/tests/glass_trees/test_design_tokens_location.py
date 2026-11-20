"""`tokens.css` lives in `packages/design`, and nothing names the place it came from (ADR-152 decision 6;
slice PL4b, the second of the PL4 slices; the owner's rulings of 20 November 2026).

The file `OspreyFlow_Core/apps/workspace/src/design/tokens.css` moved to `OspreyFlow_Core/packages/design/tokens.css`,
its bytes unchanged, and every file that named the old place followed it: the 80 or so imports, the Vitest and Python
readers, the two Dockerfiles, the install-page stamp, the colour-drift check and the guides. This file is the proof that
none was left behind, and that each guard of the move can fail.

Which test fails if the invariant is broken (rule 12):

* the file is not where it should be, or the old one is back: `test_the_tokens_are_in_packages_design_and_not_in_the_workspace`;
* a file of any kind still names the old path, in any of the forms the repository writes it in (a path to open, import,
  copy or cite; `/`-joined, `, `-joined or Python `/`-joined): `test_no_tracked_file_names_the_old_path`, which walks
  `git ls-files` over the **whole repository**: `OspreyFlow_Core`, `OspreyFlow_Build` (spec, tests, tools, scripts,
  guides) and the repository root's own files. Only the places below may keep the old path (`HISTORY` and `NAMED`);
* an import that does not reach the one file: `test_every_import_of_a_tokens_file_reaches_the_one_file`;
* an image that cannot see the file: `test_the_two_images_copy_packages_design`;
* the install-page stamp that goes on counting the old place: `test_both_stamp_lists_name_packages_design`, and that the
  move changed no stamped byte but the paths: `test_the_move_changed_no_stamped_byte_but_the_paths`;
* the colour-drift check that stops looking at the Glass when the file leaves it:
  `test_the_colour_drift_check_scans_no_fewer_files_than_before`.

Each guard is shown red on a planted regression in the shape the real code writes it (rule 15): the planted lines below
are the lines that were in the tree on the day before the move, one case per shape, and each is placed at the path of the
file that held it. A plant that some other rule would also have caught proves nothing, so each case first shows the
same file with the new path clean.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pytest
from tools import colour_drift_check
from tools.layout import CORE, ROOT

NEW_REL = "OspreyFlow_Core/packages/design/tokens.css"
OLD_REL = "OspreyFlow_Core/apps/workspace/src/design/tokens.css"

#: The places that may name the old path because they are a record of the past (the decision log, and the build record
#: under `process/`, which holds the lanes' briefs, the build plan and the handovers). They are not rewritten.
HISTORY = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/process/")
#: One file and one reason each. A name is removed from here when its reason is gone.
NAMED = {
    # The rules file the owner changes: its table row still says "until ADR-152's move lands: <old path>". The
    # owner applies the conductor's one-line diff (`PL4B_RULES_ROW.diff`); this exception goes with it.
    "OspreyFlow_Build/process/CLAUDE.md": "a rules file, changed by the owner and not by a builder",
    # The citation check's allowlist: the decision log and the records name the old path, and the allowlist says why
    # that is not a dead citation. It must name the path to do so.
    "OspreyFlow_Build/tests/fixtures/citation_allowlist.txt": "the allowlist for the records that name the old path",
    # This file: it spells out the old path to look for it.
    "OspreyFlow_Build/tests/glass_trees/test_design_tokens_location.py": "this test",
}

# ---------------------------------------------------------------------------------------------- the old path, found

#: `design/tokens.css`, as a path that is written out: not `spec/design/tokens.css` (a still older place that no file has
#: had since round 14a, and which is not this move's), and not `packages/design/tokens.css` (the new one).
_TEXT_FORM = re.compile(r"(?<!spec/)(?<!packages/)design/tokens\.css")
#: The segments of it written apart: Python's `/ "design" / "tokens.css"`, TypeScript's `join(here, "..", "design", "tokens.css")`
#: (the gap may be a line break inside the brackets).
_SEGMENT_FORM = re.compile(r"""["']design["']\s*[,/]\s*["']tokens\.css["']""")
_PACKAGES_SEGMENT = re.compile(r"""["']packages["']\)?\s*[,/]\s*$""")
_DESIGN_SEGMENT = re.compile(r"""["']design["']\s*[,/]\s*$""")
#: Inside the old folder itself, the file was named bare: `join(__dirname, "tokens.css")`, `"./tokens.css"`.
_BARE_FORM = re.compile(r"""["'](?:\./)?tokens\.css["']""")
_OLD_FOLDER = "OspreyFlow_Core/apps/workspace/src/design/"


def old_path_mentions(root: Path, rels: Iterable[str]) -> list[tuple[str, int, str]]:
    """`(file, line, text)` for each place under `root` that names the old path. `rels` are repository-relative."""
    found: list[tuple[str, int, str]] = []
    for rel in rels:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # gone from the working tree, or not text
        forms = [_TEXT_FORM, _SEGMENT_FORM]
        if rel.startswith(_OLD_FOLDER):
            forms.append(_BARE_FORM)
        for form in forms:
            for hit in form.finditer(text):
                if form is _SEGMENT_FORM and _PACKAGES_SEGMENT.search(text[: hit.start()]):
                    continue  # `"packages", "design", "tokens.css"` is the new place written apart
                if form is _BARE_FORM and _DESIGN_SEGMENT.search(text[: hit.start()]):
                    continue  # `"design", "tokens.css"` is a path written apart, not the bare name
                line = text.count("\n", 0, hit.start()) + 1
                found.append((rel, line, text.splitlines()[line - 1].strip()))
    return sorted(set(found))


def tracked(root: Path = ROOT) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True).stdout
    return sorted(name for name in out.decode("utf-8").split("\0") if name)


def _kept_out(rel: str) -> bool:
    """History and the named exceptions are not looked at. The rules file is under `process/` but is no record: it is
    kept out by its name alone, so it is looked at again the day it leaves `NAMED`."""
    if rel in NAMED:
        return True
    if rel == "OspreyFlow_Build/process/CLAUDE.md":
        return False
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in HISTORY)


# ----------------------------------------------------------------------------------------------------- the imports

_IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|@import\s+(?:url\()?\s*)["']([^"']*tokens\.css[^"']*)["']""")
_SOURCE_SUFFIXES = {".ts", ".tsx", ".mts", ".mjs", ".js", ".jsx", ".css"}


def imports_not_reaching(root: Path, rels: Iterable[str]) -> tuple[list[str], int]:
    """The imports of a `tokens.css` that do not resolve to `root`'s `NEW_REL`, and how many imports were looked at."""
    one = (root / NEW_REL).resolve()
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
            if target != one:
                bad.append(f"{rel}: {hit.group(1)}")
    return bad, seen


# ---------------------------------------------------------------------------------------------------- the images

_COPY_DESIGN = re.compile(r"^COPY\s+packages/design(?:/\S*)?\s+\S+\s*$", re.M)


def stage_of(dockerfile: str, name: str | None) -> str:
    """The text of the stage called `name` (`FROM … AS name`), or all of the file when `name` is None."""
    if name is None:
        return dockerfile
    return dockerfile.split(f"AS {name}", 1)[1].split("\nFROM ", 1)[0]


def copies_design(dockerfile: str, stage: str | None = None) -> bool:
    return bool(_COPY_DESIGN.search(stage_of(dockerfile, stage)))


WORKSPACE_DOCKERFILE = "OspreyFlow_Core/apps/workspace/Dockerfile"
HARNESS_DOCKERFILE = "OspreyFlow_Core/harness/Dockerfile"

# --------------------------------------------------------------------------------------------- the real tree: cases


def test_the_tokens_are_in_packages_design_and_not_in_the_workspace() -> None:
    assert (ROOT / NEW_REL).is_file(), "the tokens file is not in packages/design"
    assert not (ROOT / OLD_REL).exists(), "the old file is still where it was"
    assert NEW_REL in tracked() and OLD_REL not in tracked()


def test_no_tracked_file_names_the_old_path() -> None:
    rels = [rel for rel in tracked() if not _kept_out(rel)]
    assert len(rels) > 1000, "the walk found too few files: git ls-files is not listing the repository"
    found = old_path_mentions(ROOT, rels)
    shown = "\n".join(f"  {rel}:{line}: {text[:140]}" for rel, line, text in found[:40])
    assert found == [], f"{len(found)} place(s) still name the old path; the file is now {NEW_REL}:\n{shown}"


def test_every_import_of_a_tokens_file_reaches_the_one_file() -> None:
    bad, seen = imports_not_reaching(ROOT, tracked())
    assert seen >= 2, "the walk found no import of a tokens file: the pattern no longer matches the sources"
    assert bad == [], f"{len(bad)} import(s) do not reach {NEW_REL}: {bad[:10]}"
    # The two entrances of the two front ends are among those looked at, whatever the count.
    for entrance in ("OspreyFlow_Core/apps/workspace/src/main.tsx", "OspreyFlow_Core/apps/harness/src/main.tsx"):
        assert imports_not_reaching(ROOT, [entrance])[1] == 1, f"{entrance} does not import the tokens once"


def test_the_two_images_copy_packages_design() -> None:
    workspace = (ROOT / WORKSPACE_DOCKERFILE).read_text(encoding="utf-8")
    harness = (ROOT / HARNESS_DOCKERFILE).read_text(encoding="utf-8")
    assert copies_design(workspace), "apps/workspace/Dockerfile does not COPY packages/design"
    assert copies_design(harness, "frontend-builder"), "harness/Dockerfile's frontend-builder does not COPY packages/design"


# The install-page stamp (`apps/harness/scripts/stamp.mjs` and `harness/install_page_build.py` list the same folders; the
# hash holds each file's path and its byte hash, so a move changes the stamp even when no byte moved).


def _node_sources() -> list[str]:
    text = (CORE / "apps" / "harness" / "scripts" / "stamp.mjs").read_text(encoding="utf-8")
    block = text.split("export const SOURCES = [", 1)[1].split("];", 1)[0]
    return re.findall(r'"([^"]+)"', block)


def test_both_stamp_lists_name_packages_design() -> None:
    from harness import install_page_build

    assert "packages/design" in _node_sources(), "stamp.mjs does not stamp packages/design"
    assert "packages/design" in install_page_build.SOURCES, "install_page_build.py does not stamp packages/design"
    assert sorted(_node_sources()) == sorted(install_page_build.SOURCES), "the two stamp lists differ"


_PRODUCT = "OspreyFlow_Core/"
_OLD_SOURCES = ("apps/harness/src", "apps/harness/index.html", "apps/harness/package.json",
                "apps/workspace/src/design", "apps/workspace/src/theme")  # fmt: skip
_NEW_SOURCES = (*_OLD_SOURCES, "packages/design")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout


def _stamped(commit: str, sources: tuple[str, ...]) -> dict[str, str]:
    """The stamped files of `commit` as `{path: blob id}`; a blob id is a hash of the file's bytes."""
    found: dict[str, str] = {}
    for source in sources:
        for line in _git("ls-tree", "-r", commit, "--", _PRODUCT + source).splitlines():
            meta, path = line.split("\t", 1)
            parts = path[len(_PRODUCT):].split("/")
            if any(p.startswith(".") or p in {"node_modules", "Icon\r"} for p in parts):
                continue
            found[path[len(_PRODUCT):]] = meta.split()[2]
    return found


def _move_commit() -> str | None:
    out = _git("log", "--follow", "-M100%", "--diff-filter=R", "--format=%H", "-1", "--", NEW_REL).strip()
    return out or None


def test_the_move_changed_no_stamped_byte_but_the_paths() -> None:
    """The stamp hashes each stamped file's path and its bytes. The owner accepts the new stamp on one condition: that
    the files stamped before the move and after it hold the same bytes, and only their paths differ. This lists both by
    byte hash at the commit that moved the file and the one before it. (A shallow clone has no history to read: skipped,
    and the commit's own run on a full clone is the proof.)"""
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        pytest.skip("a shallow clone has no history: the move commit cannot be read")
    commit = _move_commit()
    assert commit, "no commit in history moved tokens.css to packages/design as a pure rename (the file bytes unchanged)"
    before, after = _stamped(f"{commit}^", _OLD_SOURCES), _stamped(commit, _NEW_SOURCES)
    old_in_stamp, new_in_stamp = "apps/workspace/src/design/tokens.css", "packages/design/tokens.css"
    assert old_in_stamp in before and new_in_stamp in after
    assert before[old_in_stamp] == after[new_in_stamp], "the tokens file's bytes changed in the move"
    gone, came = Counter(before.values()) - Counter(after.values()), Counter(after.values()) - Counter(before.values())
    differing = sorted({p for p, blob in before.items() if gone[blob]} | {p for p, blob in after.items() if came[blob]})
    # The one stamped file whose bytes had to change is the harness entrance, by the one line that imports the tokens.
    assert differing == ["apps/harness/src/main.tsx"], f"stamped files other than the entrance changed: {differing}"
    was = _git("show", f"{commit}^:{_PRODUCT}apps/harness/src/main.tsx")
    now = _git("show", f"{commit}:{_PRODUCT}apps/harness/src/main.tsx")
    assert was.replace("../../../apps/workspace/src/design/tokens.css", "../../../packages/design/tokens.css") == now
    assert Counter(p for p in after if p not in before) == Counter({new_in_stamp: 1}), "a stamped file other than the tokens appeared"


# The colour-drift check walked `apps/workspace/src` and left `design/tokens.css` out by name. With the file gone from
# there, the name excuses nothing and a walk of the new folder is what keeps the tokens' neighbours looked at.

#: Scanned on the day before the move (482). It does not fall without someone deciding it should: a file that leaves the
#: Glass's folders for another folder the check does not walk lowers the count, and this fails (slices B2, C and D rely on it).
SCANNED_BEFORE_THE_MOVE = 482


def test_the_colour_drift_check_scans_no_fewer_files_than_before(capsys: pytest.CaptureFixture[str]) -> None:
    assert colour_drift_check.scanned_count() >= SCANNED_BEFORE_THE_MOVE
    colour_drift_check.main()
    said = re.search(r"scanned (\d+) files", capsys.readouterr().out)
    assert said, "the check does not say how many files it scanned"
    assert int(said.group(1)) == colour_drift_check.scanned_count()


# ------------------------------------------------------------------------------- planted regressions (red, rule 15)
# Each plant is a line as the tree held it before the move, put at the path of the file that held it.


def _tree(tmp_path: Path, files: dict[str, str]) -> list[str]:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return sorted(files)


#: (id, file, the old line, the same line at the new place)
READERS = [
    ("vitest-join-from-dirname", "OspreyFlow_Core/apps/workspace/src/brand/govuk/GovukHeader.test.tsx",
     'const tokens = readFileSync(join(__dirname, "../../design/tokens.css"), "utf-8");',
     'const tokens = readFileSync(join(__dirname, "../../../../../packages/design/tokens.css"), "utf-8");'),
    ("vitest-url", "OspreyFlow_Core/apps/workspace/src/color/tokens.test.ts",
     'const TOKENS_CSS_PATH = new URL("../design/tokens.css", import.meta.url).pathname;',
     'const TOKENS_CSS_PATH = new URL("../../../../packages/design/tokens.css", import.meta.url).pathname;'),
    ("vitest-segments", "OspreyFlow_Core/apps/workspace/src/home/homeKey.test.ts",
     'const tokens = strip(readFileSync(join(here, "..", "design", "tokens.css"), "utf8"));',
     'const tokens = strip(readFileSync(join(here, "..", "..", "..", "..", "packages", "design", "tokens.css"), "utf8"));'),
    ("vitest-bare-name-in-the-old-folder", "OspreyFlow_Core/apps/workspace/src/design/fonts.test.ts",
     'const TOKENS = readFileSync(join(__dirname, "tokens.css"), "utf-8");',
     'const TOKENS = readFileSync(join(__dirname, "../../../../packages/design/tokens.css"), "utf-8");'),
    ("python-segments", "OspreyFlow_Build/tests/test_superset_theme.py",
     'TOKENS = (CORE / "apps" / "workspace" / "src" / "design" / "tokens.css").read_text(encoding="utf-8")',
     'TOKENS = (CORE / "packages" / "design" / "tokens.css").read_text(encoding="utf-8")'),
    ("python-path-constructor", "OspreyFlow_Core/harness/keycloak_theme.py",
     'TOKENS_RELATIVE_PATH = Path("apps") / "workspace" / "src" / "design" / "tokens.css"',
     'TOKENS_RELATIVE_PATH = Path("packages") / "design" / "tokens.css"'),
    ("python-slashed-string", "OspreyFlow_Build/tests/test_refresh_search_rebuild.py",
     '    (repo / "apps/workspace/src/design/tokens.css").write_text(":root {}\\n", encoding="utf-8")',
     '    (repo / "packages/design/tokens.css").write_text(":root {}\\n", encoding="utf-8")'),
    ("guide-prose", "OspreyFlow_Build/spec/05_DEPLOYMENT.md",
     "the same tokens (`apps/workspace/src/design/tokens.css`) so the journey does not change",
     "the same tokens (`packages/design/tokens.css`) so the journey does not change"),
]


@pytest.mark.parametrize(("name", "rel", "old", "new"), READERS, ids=[r[0] for r in READERS])
def test_a_reader_that_names_the_old_path_is_found(tmp_path: Path, name: str, rel: str, old: str, new: str) -> None:
    clean = _tree(tmp_path, {rel: f"{new}\n"})
    assert old_path_mentions(tmp_path, clean) == [], f"the new-path form of {name} must be clean"
    _tree(tmp_path, {rel: f"// before\n{old}\n"})
    assert [(r, n) for r, n, _ in old_path_mentions(tmp_path, [rel])] == [(rel, 2)], f"{name} was not found"


def test_the_old_path_is_found_when_a_python_path_breaks_across_lines(tmp_path: Path) -> None:
    rel = "OspreyFlow_Build/tests/harness/test_keycloak_theme.py"
    old = 'TOKENS = (\n    REPO_ROOT\n    / "apps"\n    / "src"\n    / "design"\n    / "tokens.css"\n).read_text()\n'
    _tree(tmp_path, {rel: old})
    assert old_path_mentions(tmp_path, [rel]), "a path broken across lines was not found"


def test_the_bare_name_is_only_the_old_path_inside_the_old_folder(tmp_path: Path) -> None:
    """`"tokens.css"` is the old path only beside the folder it left; elsewhere it is just a file's name."""
    elsewhere = "OspreyFlow_Core/packages/design/other.test.ts"
    _tree(tmp_path, {elsewhere: 'join(__dirname, "tokens.css")\n'})
    assert old_path_mentions(tmp_path, [elsewhere]) == []


def test_a_still_older_spelling_is_not_this_moves_to_chase(tmp_path: Path) -> None:
    rels = _tree(tmp_path, {"OspreyFlow_Core/x.ts": "// `spec/design/tokens.css` and packages/design/tokens.css\n"})
    assert old_path_mentions(tmp_path, rels) == []


IMPORTS = [
    ("the workspace entrance", "OspreyFlow_Core/apps/workspace/src/main.tsx", 'import "./design/tokens.css";',
     'import "../../../packages/design/tokens.css";'),
    ("a showcase", "OspreyFlow_Core/apps/workspace/a11y/showcase.tsx", 'import "../src/design/tokens.css";',
     'import "../../../packages/design/tokens.css";'),
    ("the harness entrance", "OspreyFlow_Core/apps/harness/src/main.tsx",
     'import "../../../apps/workspace/src/design/tokens.css";', 'import "../../../packages/design/tokens.css";'),
    ("a harness spec's page", "OspreyFlow_Core/apps/harness/keyboard/setup-harness.tsx",
     'import "../../../apps/workspace/src/design/tokens.css";', 'import "../../../packages/design/tokens.css";'),
]


@pytest.mark.parametrize(("name", "rel", "old", "new"), IMPORTS, ids=[i[0] for i in IMPORTS])
def test_an_import_that_does_not_reach_the_one_file_is_found(tmp_path: Path, name: str, rel: str, old: str, new: str) -> None:
    _tree(tmp_path, {NEW_REL: ":root{}\n", rel: f"{new}\n"})
    # `new` is written for a file three folders below the product; place it so that it resolves from `rel`.
    depth = len(Path(rel).parts) - 2  # below OspreyFlow_Core
    fitted = new.replace("../../../", "../" * depth)
    _tree(tmp_path, {rel: f"{fitted}\n"})
    assert imports_not_reaching(tmp_path, [rel]) == ([], 1), f"the new-path form of {name} must resolve"
    _tree(tmp_path, {rel: f"import React from 'react';\n{old}\n"})
    bad, seen = imports_not_reaching(tmp_path, [rel])
    assert seen == 1 and len(bad) == 1, f"{name}: the old import was not found"


def test_an_import_of_some_other_tokens_file_is_found(tmp_path: Path) -> None:
    """A second `tokens.css` beside the first is as wrong as the old place: all resolve to the one."""
    rel = "OspreyFlow_Core/apps/workspace/src/main.tsx"
    _tree(tmp_path, {NEW_REL: ":root{}\n", "OspreyFlow_Core/apps/workspace/src/theme/tokens.css": ":root{}\n",
                     rel: 'import "./theme/tokens.css";\n'})  # fmt: skip
    assert imports_not_reaching(tmp_path, [rel])[1] == 1
    assert len(imports_not_reaching(tmp_path, [rel])[0]) == 1


def _real(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_the_workspace_image_planted_without_its_copy_is_found() -> None:
    """The line out of `apps/workspace/Dockerfile`, with the comment as it was when the file came with `COPY apps/workspace`."""
    real = _real(WORKSPACE_DOCKERFILE)
    assert copies_design(real)
    planted = _COPY_DESIGN.sub("# `apps/workspace/src/design/tokens.css`, inside the `COPY apps/workspace` line below.", real)
    assert planted != real and not copies_design(planted)


def test_the_harness_image_planted_with_the_old_copy_is_found() -> None:
    """The line out of the harness image's `frontend-builder`, put back as the old `COPY` of the workspace's design folder."""
    real = _real(HARNESS_DOCKERFILE)
    assert copies_design(real, "frontend-builder")
    planted = _COPY_DESIGN.sub("COPY apps/workspace/src/design ./apps/workspace/src/design", real, count=1)
    assert planted != real and not copies_design(planted, "frontend-builder")


def test_a_copy_of_packages_design_in_another_stage_does_not_count_for_the_frontend() -> None:
    real = _real(HARNESS_DOCKERFILE)
    moved = _COPY_DESIGN.sub("", real, count=1) + "\nFROM x AS elsewhere\nCOPY packages/design ./packages/design\n"
    assert not copies_design(moved, "frontend-builder")


# The colour-drift check, on a tree in the new layout (its real shape: `apps/workspace/src` and `packages/design`).


def test_the_drift_check_walks_the_new_folder_and_still_flags_a_colour_outside_the_tokens(tmp_path: Path) -> None:
    palette = colour_drift_check.palette_from("`#c08a34`")
    src = tmp_path / "src"
    design = tmp_path / "design"
    _tree(src, {"a/Map.tsx": 'const X = "#c08a34";\n'})
    _tree(design, {"tokens.css": ":root { --stray: #123456; }\n", "primitives.css": ".x { color: #654321; }\n"})
    flagged = colour_drift_check.find_drift(design, palette, mirrors=frozenset({"tokens.css"}), allowed=set())
    assert [(p, lit) for p, _, lit in flagged] == [("primitives.css", "#654321")], "tokens.css exempt, a neighbour not"
    unexempt = colour_drift_check.find_drift(design, palette, mirrors=frozenset(), allowed=set())
    assert {p for p, _, _ in unexempt} == {"tokens.css", "primitives.css"}, "the exemption is what excuses the tokens"
    assert colour_drift_check.scanned_files(design, frozenset({"tokens.css"})) == [design / "primitives.css"]


def test_a_move_of_the_tokens_does_not_lower_the_count(tmp_path: Path) -> None:
    """The same files before and after the move count the same: the tokens are exempt in both places."""
    before, after = tmp_path / "before", tmp_path / "after"
    files = {"a.tsx": "x", "b.css": "y", "c.test.ts": "z"}
    _tree(before / "src", {**files, "design/tokens.css": ":root{}", "design/primitives.css": "p"})
    _tree(after / "src", {**files, "design/primitives.css": "p"})
    _tree(after / "design", {"tokens.css": ":root{}"})
    count_before = len(colour_drift_check.scanned_files(before / "src", frozenset({"design/tokens.css"})))
    count_after = len(colour_drift_check.scanned_files(after / "src", frozenset())) + len(
        colour_drift_check.scanned_files(after / "design", frozenset({"tokens.css"}))
    )
    assert count_before == count_after == 3


def test_a_walk_that_forgets_the_new_folder_lowers_the_count(tmp_path: Path) -> None:
    """The regression the count guards: the file leaves the folder the check walks, and nothing walks the new one."""
    _tree(tmp_path / "src", {"a.tsx": "x", "design/primitives.css": "p"})
    _tree(tmp_path / "design", {"tokens.css": ":root{}", "scale.css": "s"})
    both = ((tmp_path / "src", frozenset()), (tmp_path / "design", frozenset({"tokens.css"})))
    assert colour_drift_check.scanned_count(both) == 3
    assert colour_drift_check.scanned_count(both[:1]) == 2, "dropping the new folder from the walk must lower the count"
