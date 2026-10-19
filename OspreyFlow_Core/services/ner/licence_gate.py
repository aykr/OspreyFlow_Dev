"""The licence register (`00_ARCHITECTURE.md` §7) for the recogniser image's own packages, which
`make licence-check` cannot see (it reads the Conduit's environment). Run at image build: fails,
naming each package, on any licence that mentions the GPL or that matches nothing on the allowlist
(an unreadable licence fails too: default-deny). The same rule as `tools/licence_check.is_allowed` —
a copy, since the image cannot reach the Build folder: a licence is read as an expression, and LGPL
passes only for a recorded exception. `tests/test_ner_licence_gate.py` fails if the copies' lists
part or if they answer any planted licence differently.

Found building it (6 October 2026): Stanza 1.11 and later require udtools (GPL-2.0-or-later) and
udapi (GPL-3.0-or-later), and pip-licenses 5.0.0 reports both as UNKNOWN, which a fail-on list
of GPL names lets through; 5.5.5 reads their `License-Expression`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

ALLOWED_MARKERS = (
    "mit",
    "apache",
    "bsd",
    "isc",
    "mozilla public license",
    "mpl-2.0",
    "sil open font",
    "open font license",
    "psf-2.0",
    "python software foundation",
    "unlicense",
    "cc0",
    "cc-by-3.0",
    "cc-by-4.0",
    # Added 19 October 2026, the owner's choice (§7): permissive, transitive only.
    "0bsd",
    "zlib",
    "cnri-python",
    "bsl-1.0",
    "boost software license",
)

#: `00_ARCHITECTURE.md` §7's recorded LGPL exceptions: package name -> where it was assessed. An
#: exception admits the package's LGPL and nothing else it declares.
RECORDED_LGPL_EXCEPTIONS: dict[str, str] = {
    "deepparse": "ADR-108, 10 October 2026: imported unmodified as a separate installed package",
    "psycopg2-binary": "ADR-111 Amendment 2, 11 October 2026: Superset's driver, its image only",
    # deepparse's own dependencies, under its exception on the same terms (the owner, 19 October).
    "gensim": "deepparse's dependency, under its exception (19 October 2026)",
    "poutyne": "deepparse's dependency, under its exception (19 October 2026)",
}

#: The gate's own tool, and what it depends on: not shipped, removed after the check.
TOOLING = {"pip-licenses", "prettytable", "wcwidth"}


_OPERATOR = re.compile(r"(\(|\)|;|,|\band\b|\bor\b)")
_LGPL = re.compile(r"(?<![a-z])lgpl|lesser general public|library general public")
_GPL = re.compile(r"(?<![a-z])a?gpl|general public licen[cs]e|affero")


def _word(marker: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])" + re.escape(marker) + r"(?![a-z0-9])")


_MARKERS = tuple(_word(m) for m in ALLOWED_MARKERS)


def _term_allowed(term: str, package: str | None) -> bool:
    if _LGPL.search(term):
        return package is not None and package.lower() in RECORDED_LGPL_EXCEPTIONS
    if _GPL.search(term):
        return False
    return any(marker.search(term) for marker in _MARKERS)


def _tokens(text: str) -> list[str]:
    text = text.lower().replace("library or lesser", "lesser")
    # A parenthesised aside with no operator in it ("(LGPLv3)", "(MPL 2.0)") is part of the
    # licence's name, not a group.
    text = re.sub(
        r"\(([^()]*)\)",
        lambda m: m.group(0) if _OPERATOR.search(m.group(1)) else f" {m.group(1)} ",
        text,
    )
    return [t.strip() for t in _OPERATOR.split(text) if t.strip()]


def is_allowed(license_text: str, package: str | None = None) -> bool:
    """The whole expression allowed (module docstring); `package` names the LGPL exception, if
    any. Anything that does not parse is refused."""
    tokens = _tokens(license_text)
    position = 0

    def peek() -> str | None:
        return tokens[position] if position < len(tokens) else None

    def take() -> str:
        nonlocal position
        position += 1
        return tokens[position - 1]

    def either() -> bool:
        result = both()
        while peek() == "or":
            take()
            result = both() or result
        return result

    def both() -> bool:
        result = atom()
        while peek() in ("and", ";", ","):
            take()
            result = atom() and result
        return result

    def atom() -> bool:
        token = peek()
        if token is None or token in ("and", "or", ";", ",", ")"):
            raise ValueError("expected a licence")
        take()
        if token == "(":
            result = either()
            if peek() != ")":
                raise ValueError("unbalanced parenthesis")
            take()
            return result
        return _term_allowed(token, package)

    try:
        result = either()
    except ValueError:
        return False
    return result and position == len(tokens)


def offenders(packages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        p
        for p in packages
        if p["Name"].lower() not in TOOLING and not is_allowed(p["License"], package=p["Name"])
    ]


def main() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    bad = offenders(json.loads(out.stdout))
    for p in bad:
        print(f"licence-gate: {p['Name']} {p['Version']} is {p['License']!r}, not on the allowlist")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
