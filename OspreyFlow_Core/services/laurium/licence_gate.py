"""The licence register (`00_ARCHITECTURE.md` §7) for Laurium's image's own packages, which
`make licence-check` cannot see (it reads the Conduit's environment; `06_DECISIONS.md` ADR-135
Amendment 6). Run at image build: fails, naming each package, on any licence that mentions the GPL
or that matches nothing on the allowlist (an unreadable licence fails too: default-deny). The same
rule as `tools/licence_check.find_offenders`, copied from the recogniser's gate
(`services/ner/licence_gate.py`), since the image cannot reach the Build folder, with two additions:

- **the recorded licence evidence** (decision 7): `laurium` 0.6.0, `arrow-pd-parser` 2.2.0 and
  `tiktoken` 0.14.0 are MIT on their licence files' evidence, which their metadata does not state in
  a form this gate reads; each entry admits that package at that version and nothing else;
- **the `encoder` extra refused** (decision 2; the owner's ruling 4): torch, transformers, setfit,
  sentence-transformers and the NVIDIA wheels fail by their presence, whatever licence they state.

`tests/services/laurium/test_licence_gate.py` fails if the copies' lists part, or if they judge any
planted row differently.
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

#: `00_ARCHITECTURE.md` §7's recorded licence evidence: (normalised name, version) -> the evidence.
RECORDED_LICENCE_EVIDENCE: dict[tuple[str, str], str] = {
    ("laurium", "0.6.0"): "MIT, 'Copyright (c) 2025 Ministry of Justice', in its LICENSE file and "
    "the wheel's License-File; no licence in its metadata (P12's licence check, 11 November 2026)",
    ("arrow-pd-parser", "2.2.0"): "MIT, Ministry of Justice, in LICENCE.md inside the wheel; no "
    "licence in its metadata (P12's licence check, 11 November 2026)",
    ("tiktoken", "0.14.0"): "MIT, its full text in the License field, which this gate's expression "
    "parser refuses (P12's licence check, 11 November 2026)",
}

#: Laurium's `encoder` extra and what it brings: never in this image (the owner's ruling 4).
_ENCODER = re.compile(r"^(torch|transformers|setfit|sentence-transformers|nvidia-.*)$")

#: The gate's own tool, and what it depends on: not shipped, removed after the check.
TOOLING = {"pip-licenses", "prettytable", "wcwidth"}


def _normalised(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


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


def recorded(package: dict[str, str]) -> bool:
    key = (_normalised(package["Name"]), package["Version"])
    return key in RECORDED_LICENCE_EVIDENCE and not _GPL.search(package["License"].lower())


def encoder(package: dict[str, str]) -> bool:
    return bool(_ENCODER.match(_normalised(package["Name"])))


def offenders(packages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        p
        for p in packages
        if p["Name"].lower() not in TOOLING
        and (encoder(p) or not (is_allowed(p["License"], package=p["Name"]) or recorded(p)))
    ]


def main() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    packages = json.loads(out.stdout)
    bad = offenders(packages)
    for p in bad:
        why = "Laurium's encoder extra, never installed" if encoder(p) else "not on the allowlist"
        print(f"licence-gate: {p['Name']} {p['Version']} is {p['License'][:80]!r}: {why}")
    for p in packages:
        if recorded(p) and not is_allowed(p["License"], package=p["Name"]):
            key = (_normalised(p["Name"]), p["Version"])
            print(f"licence-gate: {p['Name']} {p['Version']} admitted by recorded evidence: "
                  f"{RECORDED_LICENCE_EVIDENCE[key]}")  # fmt: skip
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
