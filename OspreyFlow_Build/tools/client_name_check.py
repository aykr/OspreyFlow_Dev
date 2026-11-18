"""The client's name, and Laurium's, kept out of the tree (the owner's rulings of 18 November 2026, "the client's name
and Laurium"; slice BL6).

    cd OspreyFlow_Core
    PYTHONPATH=../OspreyFlow_Build python -m tools.client_name_check [--root <repository>] [--hashes <list>]

**The client.** The client's name (full and abbreviated) stays only in the four files in `KEEP_FILES`; everywhere else
it is "UK public sector client", and where text credits Laurium, "the library's publisher". The names are never
written down: the check holds them as the owner's hashes (`marketing_site/client_hashes.py`, a gitignored list
on the machine that publishes) and prints a file, a line and a count, never a name, a hash or the line's text.

**Scope.** Every git-tracked file (`git ls-files`); a file that is not UTF-8 is read for its runs of printable
characters, as `identifier_check._read` does (with `BINARY_MINIMUM`'s limit). A name is found as the list's other readers find it (case, accents,
marks, spacing and an abbreviation's full stops folded), on a line or wrapped across several; a page's tags and
attribute values are read as `identifier_check.readable` reads them. A hit on a wrapped name is reported on the line it
starts.

**Laurium.** Its name may stay in the product and its records, but never in a file the publish copies
(`marketing_site/publish_pages.sh`: `PUBLISHED` below), the two READMEs never.

**Where the list is absent** the check says so in the words of `client_hashes.ABSENT` and exits 0, as the publish check
does: on GitHub (which runs no `make ci`) and in a worktree without the list. The Mac's merge gate refuses a merge
without it, so there the check always runs. A present list holding no names is not a pass: exit 1.

Exit 0 when nothing is found; 1, naming each file and line, when something is.
`tests/test_client_name_check.py` plants each shape and shows it flagged.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import re
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from tools.layout import ROOT

MARKETING = Path(__file__).resolve().parents[1] / "marketing_site"
sys.path.insert(0, str(MARKETING))
import client_hashes  # noqa: E402
import identifier_check  # noqa: E402

#: The only four files that may name the client, by exact path from the repository's root.
KEEP_FILES = frozenset(
    {
        "OspreyFlow_Core/NOTICE",
        "OspreyFlow_Core/services/laurium/NOTICE",
        "OspreyFlow_Build/tools/licence_check.py",
        "OspreyFlow_Core/services/laurium/licence_gate.py",
    }
)
_SITE = "OspreyFlow_Build/marketing_site"
#: What `publish_pages.sh` copies: the current site's four pages and its `assets/`, and the two new sites whole. The
#: READMEs, and the pages in `deploy/` the publish does not copy, are not here.
PUBLISHED_FILES = frozenset(f"{_SITE}/deploy/{name}" for name in ("index.html", "intro-video.html", "public-sector.html", "monitoring.html"))
PUBLISHED_FOLDERS = tuple(f"{_SITE}/{folder}/" for folder in ("deploy/assets", "sites/org", "sites/net"))
#: The pattern `tests/test_sites.py` holds (`LAURIUM`), the owner's decision 4 of 12 November 2026.
LAURIUM = re.compile(r"laurium", re.IGNORECASE)
#: A tree of this many files or more is scanned on every core.
PARALLEL_FROM = 200
#: In a file that is not text (a video, an image, a PDF) the printable runs are noise as much as metadata: a three-letter
#: abbreviation turns up in 30 megabytes of video by chance (the intro video, a screenshot and a PDF each held one, all
#: compressed data), and no reword can remove it. A run of fewer than this many characters is not read as a
#: name there; a full name in an image's metadata still is. The owner's call to change (`tests/test_client_name_check_binary.py`).
BINARY_MINIMUM = 5
_MARKUP = frozenset({".html", ".htm", ".svg"})
EMPTY = "client_names.local.sha256 holds no names, so the tree was not checked against the client's names; run client_hashes.py to add them"


def tracked(root: Path) -> list[str]:
    """The repository's files, by `git ls-files`, relative to `root` (NUL-separated, so no name is misread)."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True
    ).stdout.decode("utf-8")
    return sorted(name for name in out.split("\0") if name)


def published(path: str) -> bool:
    return path in PUBLISHED_FILES or path.startswith(PUBLISHED_FOLDERS)


def _seen(text: str, path: str) -> str:
    return identifier_check.readable(text) if Path(path).suffix.lower() in _MARKUP else text


@functools.lru_cache(maxsize=200_000)
def _words(line: str, markup: bool) -> tuple[str, ...]:
    """A line's words, normalised as a name is; a page's tags and attribute values read as `readable` reads them.
    Cached: a log repeats a line thousands of times."""
    return tuple(client_hashes.normalise(identifier_check.readable(line) if markup else line).split())


def client_lines(text: str, path: str, held: frozenset[str] | set[str], is_text: bool = True) -> list[int]:
    """The 1-based lines a name in `held` starts on. The file's words are read as one stream, each tagged with its line,
    so a name wrapped across lines is found as it is written (a docstring's, a comment's, a paragraph's). In a file
    that is not text, a run shorter than `BINARY_MINIMUM` characters is not a name (see there)."""
    markup = Path(path).suffix.lower() in _MARKUP
    words: list[str] = []
    where: list[int] = []
    for number, line in enumerate(text.splitlines(), 1):
        got = _words(line, markup)
        words += got
        where += [number] * len(got)
    found: set[int] = set()
    memo: dict[str, bool] = {}
    for start in range(len(words)):
        if where[start] in found:
            continue
        for end in range(start + 1, min(start + client_hashes.LONGEST, len(words)) + 1):
            run = " ".join(words[start:end])
            if not is_text and len(run) < BINARY_MINIMUM:
                continue
            hit = memo.get(run)
            if hit is None:
                hit = memo[run] = hashlib.sha256(run.encode("utf-8")).hexdigest() in held
            if hit:
                found.add(where[start])
                break
        if len(memo) > 2_000_000:
            memo.clear()
    return sorted(found)


def laurium_lines(text: str) -> Iterator[int]:
    """A published file is read as a page is whatever its suffix: a script or a style sheet can carry a page's markup in
    a string ("Lau<b>rium</b>")."""
    for number, line in enumerate(text.splitlines(), 1):
        if LAURIUM.search(identifier_check.readable(line)):
            yield number


_HELD: frozenset[str] = frozenset()
_ROOT = ROOT


def _start(root: Path, held: frozenset[str]) -> None:
    global _HELD, _ROOT
    _HELD, _ROOT = held, root


def scan_file(path: str) -> list[str]:
    """One tracked file's hits, as `path:line: why`; the file is read once."""
    file = _ROOT / path
    if not file.is_file():  # a tracked file deleted from the working tree, or a link to nothing
        return []
    text, is_text = identifier_check._read(file)
    hits: list[str] = []
    if path not in KEEP_FILES:
        hits += [f"{path}:{n}: the client's name" for n in client_lines(text, path, _HELD, is_text)]
    if published(path):
        hits += [f"{path}:{n}: Laurium in a published file" for n in laurium_lines(text)]
    return hits


def scan(root: Path, held: set[str]) -> list[str]:
    """Every hit, in path order. The tree is 5,000 files and 30 million words, each word the start of up to six hashed
    runs, so a large tree is shared across the machine's cores; a small one (a test's) is read in this process."""
    files = tracked(root)
    frozen = frozenset(held)
    if len(files) < PARALLEL_FROM:
        _start(root, frozen)
        return [hit for path in files for hit in scan_file(path)]
    with ProcessPoolExecutor(initializer=_start, initargs=(root, frozen)) as pool:
        return [hit for hits in pool.map(scan_file, files, chunksize=16) for hit in hits]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="the repository (default: this one)")
    parser.add_argument("--hashes", type=Path, default=client_hashes.HASHES, help="the owner's list of hashed names")
    args = parser.parse_args(argv)
    held = client_hashes.known(args.hashes)
    if held is None:
        print(client_hashes.ABSENT)
        return 0
    if not held:
        print(EMPTY)
        return 1
    hits = scan(args.root, held)
    for hit in hits:
        print(hit)
    files = len({h.split(":")[0] for h in hits})
    print(f"client-name-check: {len(hits)} hit(s) in {files} file(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
