"""`tools.client_name_check` (slice BL6; the owner's rulings of 18 November 2026, "the client's name and Laurium"),
shown red before it is wired into `make ci` (rule 15). Each planted name is in the shape a real caller produces: a
git-tracked file in a repository, found by `git ls-files`, the name hashed into a list in the test's own temporary
folder, and written the ways the tree writes one (a docstring, a comment, a wrapped sentence, a path, a file that is
not UTF-8).

- a tracked file naming the client is flagged, in each shape: `test_a_tracked_file_naming_the_client_is_flagged`;
  an untracked one is not read: `test_an_untracked_file_is_not_read`;
- each of the four keep-files is not flagged, and only by its exact path:
  `test_each_keep_file_may_name_the_client`, `test_a_keep_files_name_elsewhere_is_flagged`;
- Laurium in each file the publish copies is flagged, and not elsewhere, the two READMEs included:
  `test_laurium_in_a_published_file_is_flagged`, `test_laurium_elsewhere_is_not_flagged`;
- the list absent: the words of `client_hashes.ABSENT`, exit 0; present and empty: not a pass:
  `test_an_absent_list_says_so_and_exits_zero`, `test_an_empty_list_is_not_a_pass`;
- a hit prints no name, no hash and no line: `test_a_hit_never_prints_the_name_or_its_hash`;
- the real tree with the real list: `test_the_real_tree_names_no_client` (red until the reword; where the list is
  absent it says so, in words, that it did not run).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

MARKETING = Path(__file__).resolve().parents[1] / "marketing_site"
sys.path.insert(0, str(MARKETING))
import client_hashes  # noqa: E402
from tools import client_name_check  # noqa: E402

#: Synthetic, hashed into a list of the test's own; never the real client's.
SYNTHETIC_CLIENT = "Example Shire Constabulary"
SYNTHETIC_ABBREVIATION = "ESC"
#: Where the real caller keeps each of the four files the owner keeps the client's name in.
KEEP_FILES = [
    "OspreyFlow_Core/NOTICE",
    "OspreyFlow_Core/services/laurium/NOTICE",
    "OspreyFlow_Build/tools/licence_check.py",
    "OspreyFlow_Core/services/laurium/licence_gate.py",
]
#: What `publish_pages.sh` copies for the current site, and the two new sites whole.
PUBLISHED = [
    "OspreyFlow_Build/marketing_site/deploy/index.html",
    "OspreyFlow_Build/marketing_site/deploy/intro-video.html",
    "OspreyFlow_Build/marketing_site/deploy/public-sector.html",
    "OspreyFlow_Build/marketing_site/deploy/monitoring.html",
    "OspreyFlow_Build/marketing_site/deploy/assets/note.svg",
    "OspreyFlow_Build/marketing_site/sites/org/features.html",
    "OspreyFlow_Build/marketing_site/sites/org/assets/site.js",
    "OspreyFlow_Build/marketing_site/sites/net/services.html",
    "OspreyFlow_Build/marketing_site/sites/net/assets/site.css",
]
#: Where Laurium's name may stay: the product, its records, and the two READMEs the publish never copies.
LAURIUM_ALLOWED = [
    "OspreyFlow_Build/marketing_site/sites/README.md",
    "OspreyFlow_Build/marketing_site/deploy/README.md",
    "OspreyFlow_Build/marketing_site/deploy/three-places.html",
    "OspreyFlow_Build/marketing_site/sites/build.py",
    "OspreyFlow_Core/services/laurium/server.py",
    "OspreyFlow_Build/spec/06_DECISIONS.md",
]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, files: dict[str, str | bytes], untracked: dict[str, str] | None = None) -> Path:
    """A repository of its own, the files tracked as `git ls-files` lists them."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    for name, content in {**files, **{n: c for n, c in (untracked or {}).items()}}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    _git(root, "add", *files)
    return root


def _list(tmp_path: Path, names: tuple[str, ...] = (SYNTHETIC_CLIENT, SYNTHETIC_ABBREVIATION)) -> Path:
    path = tmp_path / "client_names.local.sha256"
    path.write_text("# synthetic\n" + "".join(f"{client_hashes.digest(n)}  # a name\n" for n in names))
    return path


def _run(root: Path, hashes: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = client_name_check.main(["--root", str(root), "--hashes", str(hashes)])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


#: The ways the tree writes the client: each is `(path, content, the line it is on)`.
SHAPES = {
    "a docstring": ("OspreyFlow_Build/tests/test_x.py", f'"""A case.\n\nRead as {SYNTHETIC_CLIENT} reads it.\n"""\n', 3),
    "a comment": ("OspreyFlow_Core/services/api/x.py", f"x = 1\n# the {SYNTHETIC_ABBREVIATION} view\n", 2),
    "markdown": ("OspreyFlow_Build/spec/x.md", f"# Title\n\nA table for **{SYNTHETIC_CLIENT.upper()}**.\n", 3),
    "a wrapped sentence": ("OspreyFlow_Build/process/x.md", "A line.\nSent to Example Shire\nConstabulary, who read it.\n", 2),
    "a quoted path": ("OspreyFlow_Build/spec/06_DECISIONS.md", f"see `tests/{SYNTHETIC_ABBREVIATION}_notes.md`\n", 1),
    "markup split by tags": ("OspreyFlow_Core/apps/x.html", "<p>Example <b>Shire</b> Constabulary</p>\n", 1),
    "a file that is not UTF-8": (
        "OspreyFlow_Core/data/x.bin",
        b"\xff\xfe\x00\x01 junk\n\x80\x81 " + SYNTHETIC_CLIENT.encode() + b" \x90\x91 more\n",
        None,
    ),
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_tracked_file_naming_the_client_is_flagged(shape: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path, content, line = SHAPES[shape]
    root = _repo(tmp_path, {"README.md": "Nothing here.\n", path: content})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    assert f"{path}:" in out, out
    if line is not None:
        assert f"{path}:{line}:" in out, out
    assert "README.md" not in out
    assert "1 " in out.splitlines()[-1], out  # the count, on the last line


def test_a_clean_tree_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, {"README.md": "Example Shire is a place.\n", "a.py": "# a constable\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 0, out
    assert "0" in out


def test_an_untracked_file_is_not_read(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Scope is `git ls-files`: a scratch file, or the gitignored list itself, is not the repository's."""
    root = _repo(tmp_path, {"README.md": "Nothing.\n"}, untracked={"scratch.md": f"{SYNTHETIC_CLIENT}\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 0, out


@pytest.mark.parametrize("keep", KEEP_FILES)
def test_each_keep_file_may_name_the_client(keep: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, {keep: f"# Supplied for {SYNTHETIC_CLIENT} ({SYNTHETIC_ABBREVIATION}).\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 0, out


@pytest.mark.parametrize("keep", KEEP_FILES)
def test_a_keep_files_name_elsewhere_is_flagged(keep: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The exemption is the four exact paths: a file of the same name in another folder is not exempt."""
    lookalike = "OspreyFlow_Build/tests/fixtures/" + keep
    root = _repo(tmp_path, {keep: f"{SYNTHETIC_CLIENT}\n", lookalike: f"{SYNTHETIC_CLIENT}\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    assert f"{lookalike}:1:" in out, out
    assert f"{keep}:" not in out.replace(lookalike, ""), out


@pytest.mark.parametrize("path", PUBLISHED)
@pytest.mark.parametrize("written", ["Laurium", "LAURIUM", "<b>Lau</b>rium"])
def test_laurium_in_a_published_file_is_flagged(
    path: str, written: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {path: f"first line\n<p>Credit to {written} for the library.</p>\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    assert f"{path}:2:" in out, out


@pytest.mark.parametrize("path", LAURIUM_ALLOWED)
def test_laurium_elsewhere_is_not_flagged(path: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, {path: "Laurium is the library's publisher.\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 0, out


def test_laurium_is_not_the_clients_name_in_a_published_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The two names are two rules: a published file naming the client is flagged for the client, by path and line."""
    path = PUBLISHED[0]
    root = _repo(tmp_path, {path: f"<p>{SYNTHETIC_CLIENT}</p>\n"})
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1, out
    assert f"{path}:1:" in out


def test_an_absent_list_says_so_and_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, {"a.md": f"{SYNTHETIC_CLIENT}\n"})
    code, out = _run(root, tmp_path / "no-such-list.sha256", capsys)
    assert code == 0
    assert client_hashes.ABSENT in out


def test_an_empty_list_is_not_a_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A present list with no names checks nothing; it must not read as a pass (as `identifier_check.EMPTY`)."""
    root = _repo(tmp_path, {"a.md": "Nothing.\n"})
    empty = tmp_path / "empty.sha256"
    empty.write_text("# no names yet\n")
    code, out = _run(root, empty, capsys)
    assert code == 1, out
    assert "holds no names" in out


def test_a_hit_never_prints_the_name_or_its_hash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(
        tmp_path,
        {
            "OspreyFlow_Build/spec/a.md": f"Quote: {SYNTHETIC_CLIENT} said so; {SYNTHETIC_ABBREVIATION}.\n",
            "OspreyFlow_Build/spec/b.md": "Example Shire\nConstabulary\n",
            "OspreyFlow_Build/marketing_site/deploy/index.html": "<p>Laurium</p>\n",
        },
    )
    code, out = _run(root, _list(tmp_path), capsys)
    assert code == 1
    assert "a.md:1:" in out and "b.md:1:" in out
    lowered = out.lower()
    for name in (SYNTHETIC_CLIENT, "example shire", "constabulary", "said so"):
        assert name.lower() not in lowered, name
    for name in (SYNTHETIC_CLIENT, SYNTHETIC_ABBREVIATION):
        digest = client_hashes.digest(name)
        assert digest not in out and digest[:12] not in out and digest[:8] not in out
    # The abbreviation is a word of its own: it would show only if the line were printed.
    assert SYNTHETIC_ABBREVIATION not in out.replace("OspreyFlow", "")


def test_the_check_is_wired_into_make_ci() -> None:
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text()
    ci = next(line for line in makefile.splitlines() if line.startswith("ci:"))
    assert "client-name-check" in ci.split()
    assert "client-name-check:" in makefile
    assert "tools.client_name_check" in makefile


def test_the_real_tree_names_no_client(capsys: pytest.CaptureFixture[str]) -> None:
    """The real tree, with the owner's real list. Red until the reword; where the list is absent it says so, in words,
    that it did not run (never a silent pass)."""
    held = client_hashes.known()
    if held is None:
        pytest.skip(client_hashes.ABSENT)
    assert held, "client_names.local.sha256 holds no names"
    code = client_name_check.main([])
    out = capsys.readouterr()
    assert code == 0, out.out + out.err
