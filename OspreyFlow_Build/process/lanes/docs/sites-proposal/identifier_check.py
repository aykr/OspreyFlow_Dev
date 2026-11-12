"""The site's personal-identifier rule (publish_pages.sh): a page may name the company, never a person or a
path on this machine. One exception, the owner's decision of 12 November 2026: ospreyflow.org's Team page
(`team.html`) names the six people in `TEAM_NAMES`, each once, in its person cards, and nobody else. No page names
a client: each is checked against the owner's local `client_names.local.sha256` (`client_hashes.py`), and without
that file nothing is published (the owner's ruling, 12 November 2026).

    python3 identifier_check.py <site folder>     # exit 1, naming each file and why, on a violation
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
LOCAL_PATH = re.compile(r"/Users/|/home/")
TEAM_PAGE = "team.html"
TEAM_NAMES = Path(__file__).with_name("TEAM_NAMES")


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


def _flat(text: str) -> str:
    """Entities read, every run of space one, lower case: "Will&nbsp;Forbes" and "WILL\nFORBES" are one name."""
    return " ".join(html.unescape(text).split()).casefold()


def _readable(text: str) -> str:
    """What a page shows, tags read as spaces, and every attribute's value (an address, a file name)."""
    values = re.findall(r'\b[a-z-]+="([^"]*)"', text, flags=re.IGNORECASE)
    return html.unescape(re.sub(r"<[^>]+>", " ", text)) + " . " + " . ".join(html.unescape(v) for v in values)


def violations(folder: Path, hashes: Path = client_hashes.HASHES) -> list[str]:
    names = team_names()
    found: list[str] = []
    held = client_hashes.known(hashes)
    if held is None:
        found.append(client_hashes.ABSENT + "; nothing is published without it")
    for page in sorted(folder.rglob("*.html")):
        text = page.read_text(encoding="utf-8", errors="replace")
        where = page.relative_to(folder).as_posix()
        if held and client_hashes.named(_readable(text), held):
            found.append(f"{where}: a client's name (by its hash; the name is not printed)")
        if LOCAL_PATH.search(text):
            found.append(f"{where}: a path on this machine")
        if where == TEAM_PAGE:
            cards = _Cards()
            cards.feed(text)
            if sorted(" ".join(n.split()) for n in cards.names) != sorted(names):
                found.append(f"{where}: its person cards name someone other than TEAM_NAMES' six, or not each once")
            # The six names in their own cards are allowed; anything of the owner's beyond them is not.
            for name in names:
                text = text.replace(f"<h3>{name}</h3>", "", 1)
            if OWNER.search(text):
                found.append(f"{where}: a personal identifier outside the person cards")
            if any(_flat(name) in _flat(text) for name in names):
                found.append(f"{where}: a team member named outside their own card")
            continue
        if OWNER.search(text) or any(_flat(name) in _flat(text) for name in names):
            found.append(f"{where}: a personal identifier (people are named on {TEAM_PAGE} alone)")
    return found


def main(argv: list[str]) -> int:
    found = violations(Path(argv[1]))
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
