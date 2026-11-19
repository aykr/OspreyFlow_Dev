"""`tools.client_name_check` reads a file's path as well as its contents (slice BL6, round 5; the owner's ruling of
19 November 2026). A path that names the client or, in a published website file, Laurium is a naming; the hit line shows
the path with the matching word replaced, never the word or its hash. Planted as the real caller produces them: a
git-tracked file whose name or folder carries the name, found by `git ls-files`, the name hashed into a list of the
test's own.

- a name in a path alone, in each shape the tree writes a path in, is flagged and never printed:
  `test_a_name_in_a_path_alone_is_flagged_and_never_printed`;
- a name in a path whose contents name it too: `test_a_path_and_its_contents_naming_the_client_print_neither`;
- Laurium in a published file's path is flagged, and not in an unpublished one:
  `test_laurium_in_a_published_path_is_flagged_and_not_printed`, `test_laurium_in_an_unpublished_path_is_not_flagged`;
- the keep-files' paths are exempt as before: `test_a_keep_file_path_is_not_flagged`;
- the count is exact for a tree with several hits across several files, and counts two paths that print alike as two
  files: `test_the_count_is_exact_for_several_hits_in_several_files`, `test_two_paths_that_print_alike_are_two_files`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_client_name_check import (
    KEEP_FILES,
    PUBLISHED,
    SYNTHETIC_ABBREVIATION,
    SYNTHETIC_CLIENT,
    _list,
    _repo,
    _run,
    client_hashes,
)

#: The ways a path can carry the client: `(path, a word that must never be printed)`.
PATHS = {
    "abbreviation in a file name": ("OspreyFlow_Build/process/ESC_notes.md", "esc_notes"),
    "abbreviation in lower case": ("OspreyFlow_Build/process/esc-notes.md", "esc-notes"),
    "abbreviation with full stops": ("OspreyFlow_Build/process/E.S.C.-notes.md", "e.s.c"),
    "full name in a folder": ("OspreyFlow_Build/process/Example Shire Constabulary/plan.md", "example shire"),
    "full name with underscores": ("OspreyFlow_Build/spec/Example_Shire_Constabulary.md", "constabulary"),
    "full name with hyphens": ("OspreyFlow_Build/spec/example-shire-constabulary-brief.md", "shire"),
}


def _assert_no_name(out: str) -> None:
    lowered = out.lower().replace("ospreyflow", "")
    for word in ("example", "shire", "constabulary", "esc", "e.s.c"):
        assert word not in lowered, (word, out)
    for name in (SYNTHETIC_CLIENT, SYNTHETIC_ABBREVIATION):
        digest = client_hashes.digest(name)
        assert digest not in out and digest[:12] not in out and digest[:8] not in out


@pytest.mark.parametrize("shape", sorted(PATHS))
def test_a_name_in_a_path_alone_is_flagged_and_never_printed(
    shape: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, _ = PATHS[shape]
    root = _repo(tmp_path, {"README.md": "Nothing here.\n", path: "Nothing here either.\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    assert "README.md" not in out
    assert out.splitlines()[-1] == "client-name-check: 1 hit(s) in 1 file(s)", out
    # the line says where, by the path with the word replaced
    assert out.splitlines()[0].startswith("OspreyFlow_Build/"), out
    _assert_no_name(out)


@pytest.mark.parametrize("shape", sorted(PATHS))
def test_a_path_and_its_contents_naming_the_client_print_neither(
    shape: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, _ = PATHS[shape]
    root = _repo(tmp_path, {path: f"Line one.\nRead as {SYNTHETIC_CLIENT} reads it.\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    # the contents' hit is still reported by its line, the path's by the path: two hits, one file
    assert out.splitlines()[-1] == "client-name-check: 2 hit(s) in 1 file(s)", out
    assert ":2:" in out, out
    _assert_no_name(out)


def test_a_name_in_a_path_is_not_a_keep_files_exemption(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A file named for the client in a keep-file's folder is flagged: the four exempt paths are exact."""
    path = "OspreyFlow_Core/services/laurium/ESC_notes.md"
    root = _repo(tmp_path, {path: "Nothing.\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    _assert_no_name(out)


@pytest.mark.parametrize("keep", KEEP_FILES)
def test_a_keep_file_path_is_not_flagged(keep: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, {keep: "Nothing.\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 0, out
    assert out.splitlines()[-1] == "client-name-check: 0 hit(s) in 0 file(s)", out


LAURIUM_PATHS = [
    "OspreyFlow_Build/marketing_site/sites/org/assets/laurium.svg",
    "OspreyFlow_Build/marketing_site/sites/net/Laurium-credit.html",
    "OspreyFlow_Build/marketing_site/deploy/assets/LAURIUM/logo.png",
]


@pytest.mark.parametrize("path", LAURIUM_PATHS)
def test_laurium_in_a_published_path_is_flagged_and_not_printed(
    path: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {path: "Nothing here.\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    assert out.splitlines()[-1] == "client-name-check: 1 hit(s) in 1 file(s)", out
    printed_path = out.splitlines()[0].split(": ")[0]  # the message after it says "Laurium"; the path must not
    assert "laurium" not in printed_path.lower(), out
    assert out.splitlines()[0].startswith("OspreyFlow_Build/marketing_site/"), out


@pytest.mark.parametrize(
    "path",
    [
        "OspreyFlow_Core/services/laurium/server.py",
        "OspreyFlow_Build/marketing_site/deploy/laurium-notes.html",  # in deploy/, but not one the publish copies
        "OspreyFlow_Build/marketing_site/sites/laurium-README.md",
    ],
)
def test_laurium_in_an_unpublished_path_is_not_flagged(
    path: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {path: "Nothing here.\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 0, out


def test_the_count_is_exact_for_several_hits_in_several_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Seven hits in four files: a hit counted twice, or the two numbers swapped, is a different last line."""
    index = PUBLISHED[0]
    root = _repo(
        tmp_path,
        {
            "README.md": "Nothing here.\n",
            "OspreyFlow_Build/spec/a.md": f"{SYNTHETIC_CLIENT}\nclean\n{SYNTHETIC_ABBREVIATION}\n",  # 2 hits
            "OspreyFlow_Build/spec/b.md": f"clean\nSent to {SYNTHETIC_CLIENT}.\n",  # 1 hit
            index: f"<p>Laurium</p>\n<p>{SYNTHETIC_ABBREVIATION}</p>\n<p>Laurium again</p>\n",  # 3 hits
            "OspreyFlow_Build/process/ESC_notes.md": "clean\n",  # 1 hit, by its path
        },
    )
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    lines = out.splitlines()
    assert len(lines) == 8, out  # seven hits, then the count
    assert lines[-1] == "client-name-check: 7 hit(s) in 4 file(s)", out


def test_two_paths_that_print_alike_are_two_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The word is replaced in the path printed, so two files that differ only in that word print the same path: they
    are still two files."""
    root = _repo(
        tmp_path,
        {
            "OspreyFlow_Build/process/ESC/plan.md": "clean\n",
            "OspreyFlow_Build/process/Example Shire Constabulary/plan.md": "clean\n",
        },
    )
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    assert out.splitlines()[-1] == "client-name-check: 2 hit(s) in 2 file(s)", out
    _assert_no_name(out)
