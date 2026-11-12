"""The site's personal-identifier rule (publish_pages.sh): a page may name the company, never a person or a
path on this machine. One exception, the owner's decision of 12 November 2026: ospreyflow.org's Team page
(`team.html`) names the six people in `TEAM_NAMES`, each once, in its person cards, and nobody else.

    python3 identifier_check.py <site folder>     # exit 1, naming each file and why, on a violation
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

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


def violations(folder: Path) -> list[str]:
    names = team_names()
    found: list[str] = []
    for page in sorted(folder.rglob("*.html")):
        text = page.read_text(encoding="utf-8", errors="replace")
        where = page.relative_to(folder).as_posix()
        if LOCAL_PATH.search(text):
            found.append(f"{where}: a path on this machine")
        if where == TEAM_PAGE:
            cards = _Cards()
            cards.feed(text)
            if sorted(n.strip() for n in cards.names) != sorted(names):
                found.append(f"{where}: its person cards name someone other than TEAM_NAMES' six, or not each once")
            # The six names in their own cards are allowed; anything of the owner's beyond them is not.
            for name in names:
                text = text.replace(f"<h3>{name}</h3>", "", 1)
            if OWNER.search(text):
                found.append(f"{where}: a personal identifier outside the person cards")
            if any(name in text for name in names):
                found.append(f"{where}: a team member named outside their own card")
            continue
        if OWNER.search(text) or any(name in text for name in names):
            found.append(f"{where}: a personal identifier (people are named on {TEAM_PAGE} alone)")
    return found


def main(argv: list[str]) -> int:
    found = violations(Path(argv[1]))
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
