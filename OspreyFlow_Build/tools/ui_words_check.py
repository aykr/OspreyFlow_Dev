"""`python -m tools.ui_words_check` — no "target model" in the Glass's user-facing copy.

ADR-140 Amendment 9 decision 1: every dataset has one model, and the screens, guides and help call it
the **domain model**; the code and spec 01 keep `TargetModel`. So the phrase "target model" (any case,
any run of whitespace between the words, so JSX text wrapped across lines is caught) must not appear
in the Glass's source outside comments: in a string, a template literal, JSX text, an attribute or a
JSON copy file. Identifiers (`TargetModel`) and right ids (`edit_target_model`) never match, since
the words must be separated by whitespace; a right id becomes on-screen words only through
`help/roles.ts`'s `rightName`, whose own test (`help/rightNames.test.ts`) holds every right's name to
the same rule.

Tests (`*.test.*`, `*.spec.*`) and generated types are not on screen and are skipped.

Limits, recorded: comments are found by a small lexer, not a TypeScript parser. A quoted string never
runs past its line (as in TS), so an apostrophe in JSX text cannot hide the next line; a `//` inside
JSX text (a bare URL in prose) is read as a comment for the rest of that line.

Non-vacuous: `tests/test_ui_words_check.py` plants the phrase in the shapes the Glass's strings took
before L1.8 (a section's `aria-label`, a heading's JSX text, a words table's constant, a panel's
`words` attribute, a template literal, wrapped JSX text, a JSON copy file) and asserts each is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from tools.layout import CORE

GLASS_SRC = CORE / "apps" / "workspace" / "src"

#: The banned phrase. The words in their place are "domain model".
BANNED = re.compile(r"\btarget\s+model", re.IGNORECASE)

SUFFIXES = frozenset({".ts", ".tsx", ".json", ".html", ".md"})


def strip_comments(text: str) -> str:
    """`text` with every `//` and `/* */` comment blanked to spaces, newlines kept (so line numbers
    hold), strings and template literals left as they are."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        two = text[i : i + 2]
        if two == "//":
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        elif c in "\"'`":
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\\":
                    j += 1
                elif text[j] == "\n" and c != "`":
                    break  # a quoted string never spans a line: an apostrophe in JSX text
                j += 1
            j = min(j + 1, n) if j < n and text[j] == c else j
            out.append(text[i:j])
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _skipped(rel: Path) -> bool:
    name = rel.name
    return ".test." in name or ".spec." in name or "generated" in rel.parts


def find_banned(root: Path) -> list[tuple[str, int, str]]:
    """`(path, line, phrase)` for each "target model" in copy under `root`, sorted."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in SUFFIXES or not path.is_file() or "node_modules" in path.parts:
            continue
        rel = path.relative_to(root)
        if _skipped(rel):
            continue
        text = strip_comments(path.read_text(encoding="utf-8"))
        for match in BANNED.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append((rel.as_posix(), line, " ".join(match.group(0).split())))
    return found


def main() -> int:
    found = find_banned(GLASS_SRC)
    for path, line, phrase in found:
        print(f"{path}:{line}: \"{phrase}\" on screen: the screens say \"domain model\" (ADR-140 Amendment 9)")
    if found:
        print(f"ui-words-check: {len(found)} violation(s)")
        return 1
    print("ui-words-check: no \"target model\" in the Glass's copy (tests/test_ui_words_check.py holds the proof)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
