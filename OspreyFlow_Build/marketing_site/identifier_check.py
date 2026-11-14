"""The site's personal-identifier rule (publish_pages.sh): a page may name the company, never a person or a
path on this machine. One exception, the owner's decision of 12 November 2026: ospreyflow.org's Team page
(`team.html`) names the six people in `TEAM_NAMES`, each once, in its person cards, and nobody else. No page names
a client: each is checked against the owner's local `client_names.local.sha256` (`client_hashes.py`), and without
that file, or with one that holds no names, nothing is published (the owner's ruling, 12 November 2026).

Every file the publish copies is read, not only the pages: a script, a style sheet, a licence, an image's metadata.
A file that is not UTF-8 text (an image, a font) is read for its runs of printable characters, the way metadata sits
in one, so a name or a path in an image's metadata is still found. This module is the one place the local-path rule and a page's readable text are defined;
`tests/test_sites.py` imports both.

    python3 identifier_check.py <site folder> [<hash file>]     # exit 1, naming each file and why, on a violation

**Its limit.** People are recognised by TEAM_NAMES' six: each full name, and each surname on its own, in any case,
spacing or markup. A person who is not among the six, written in running prose, is not detected.
"""

from __future__ import annotations

import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import client_hashes

#: The owner's identifiers, as publish_pages.sh has always refused them.
OWNER = re.compile(r"ayan[\s._-]?(d[._-])?kar|ayankarsolirius", re.IGNORECASE)
#: A path on a computer, in any of the shapes a page or a file can carry one (tests/test_sites.py reads it from here).
#: `file://` counts with a path after it: the current site's script names the scheme in a comment ("a file:// download").
LOCAL_PATH = re.compile(r"/Users/|/home/|[A-Za-z]:\\\\?Users|file://[^\s'\"<>]", re.IGNORECASE)
TEAM_PAGE = "team.html"
TEAM_NAMES = Path(__file__).with_name("TEAM_NAMES")
#: Said where the local file is present and holds no names: an empty list must never read as a pass.
EMPTY = (
    "client_names.local.sha256 holds no names, so the pages were not checked against the client's names; "
    "run client_hashes.py to add them"
)


def team_names() -> list[str]:
    return [n.strip() for n in TEAM_NAMES.read_text().splitlines() if n.strip() and not n.startswith("#")]


class _Cards(HTMLParser):
    """Each person card's name: the first `<h3>` inside an `<article class="person …">`."""

    def __init__(self) -> None:
        super().__init__()
        self.names: list[str] = []
        self._depth = 0  # nesting inside a person card; 0 outside one
        self._in_h3 = False
        self._took = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "article" and "person" in classes and self._depth == 0:
            self._depth, self._took = 1, False
        elif self._depth and tag == "article":
            self._depth += 1
        elif self._depth and tag == "h3" and not self._took:
            self._in_h3, self._took = True, True
            self.names.append("")

    def handle_endtag(self, tag: str) -> None:
        if self._depth and tag == "article":
            self._depth -= 1
        elif tag == "h3":
            self._in_h3 = False

    def handle_data(self, data: str) -> None:
        if self._in_h3:
            self.names[-1] += data


#: An attribute's value, in each of the three ways HTML writes one: double-quoted, single-quoted and bare.
_ATTRIBUTE = re.compile(r"""\b[a-z][a-z0-9:_-]*\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""", re.IGNORECASE)


def readable(source: str) -> str:
    """What a page shows, read twice: with its tags as spaces ("Will</span> <span>Forbes") and with its tags taken
    out, as a browser joins the letters of one word around them ("Forb<span>es</span>"); and also what it carries
    unseen: each comment's text and every attribute's value (an address, a file name, alternative text), however the
    value is quoted."""
    comments = re.findall(r"<!--(.*?)-->", source, flags=re.DOTALL)
    values = [next(v for v in m.groups() if v is not None) for m in _ATTRIBUTE.finditer(source)]
    shown = re.sub(r"<!--.*?-->", " ", source, flags=re.DOTALL)
    spaced, joined = re.sub(r"<[^>]+>", " ", shown), re.sub(r"<[^>]+>", "", shown)
    return " . ".join(html.unescape(part) for part in [spaced, joined, *comments, *values])


def _words(text: str) -> str:
    """Normalised as a client's name is (case, accents, invisible characters, marks and spacing folded), padded so a
    whole-word match is a substring match."""
    return f" {client_hashes.normalise(text)} "


def _names_in(text: str, people: list[str]) -> bool:
    """Whether `text` names any of `people`, whole words, the text normalised once."""
    words = _words(text)
    return any(_words(person) in words for person in people)


def _surnames(names: list[str]) -> list[str]:
    return [name.split()[-1] for name in names]


#: A run of printable characters in a file that is not text: where an image's metadata (a comment, an author, a
#: path) sits. Four characters or more, as `strings` reads one.
_PRINTABLE = re.compile(rb"[\x20-\x7e]{4,}")


def _read(path: Path) -> tuple[str, bool]:
    """A file's text, and whether it is text: UTF-8 if it decodes, otherwise its runs of printable characters, one
    a line."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8"), True
    except UnicodeDecodeError:
        return "\n".join(run.decode("ascii") for run in _PRINTABLE.findall(data)), False


def violations(folder: Path, hashes: Path = client_hashes.HASHES) -> list[str]:
    names = team_names()
    found: list[str] = []
    held = client_hashes.known(hashes)
    if held is None:
        found.append(client_hashes.ABSENT + "; nothing is published without it")
    elif not held:
        found.append(EMPTY + "; nothing is published without them")
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        text, is_text = _read(path)
        where = path.relative_to(folder).as_posix()
        seen = readable(text) if path.suffix.lower() in {".html", ".htm", ".svg"} else text
        if held and client_hashes.named(seen, held):
            found.append(f"{where}: a client's name (by its hash; the name is not printed)")
        if LOCAL_PATH.search(text):
            found.append(f"{where}: a path on this machine")
        if where == TEAM_PAGE:
            cards = _Cards()
            cards.feed(text)
            if sorted(" ".join(n.split()) for n in cards.names) != sorted(names):
                found.append(f"{where}: its person cards name someone other than TEAM_NAMES' six, or not each once")
            # The six names in their own cards are allowed; anything of the owner's, or of the six, beyond them is not.
            for name in names:
                text = text.replace(f"<h3>{name}</h3>", "", 1)
            seen = readable(text)
            if OWNER.search(text) or OWNER.search(seen):
                found.append(f"{where}: a personal identifier outside the person cards")
            if _names_in(seen, [*names, *_surnames(names)]):
                found.append(f"{where}: a team member named outside their own card")
            continue
        people = [*names, *_surnames(names)] if is_text else names
        if OWNER.search(text) or OWNER.search(seen) or _names_in(seen, people):
            found.append(f"{where}: a personal identifier (people are named on {TEAM_PAGE} alone)")
    return found


def main(argv: list[str]) -> int:
    found = violations(Path(argv[1]), Path(argv[2])) if len(argv) > 2 else violations(Path(argv[1]))
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
