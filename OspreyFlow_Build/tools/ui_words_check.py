"""`python -m tools.ui_words_check` — no "target model" in the Glass's user-facing copy.

ADR-140 Amendment 9 decision 1: every dataset has one model, and the screens, guides and help call it
the **domain model**; the code and spec 01 keep `TargetModel`. So the phrase "target model" (any case;
its words apart by any run of whitespace, so JSX text wrapped across lines is caught, by a hyphen, or by
JSX's `{" "}`) must not appear in the Glass's source outside comments: in a string, a template literal
(nested ones too), JSX text, an attribute or a JSON copy file. Identifiers (`TargetModel`) and right ids
(`edit_target_model`) never match.

**What this gate cannot see, and what holds it instead.** Words computed at run time from an id: a
right's name is `help/roles.ts`'s `rightName`, held to the rule by `help/rightNames.test.ts`, which also
holds Admin › Roles' `rightWords` to `rightName` (until rules-b's `admin-tips.patch` lands, Admin builds
its own, and says "Edit target model": the lane review of L1.8). Words the Conduit sends to the screen
(none says it today) and `apps/harness` are outside the Glass's `src` and not scanned.

Tests (`*.test.*`, `*.spec.*`) and generated types are not on screen and are skipped.

Limits, recorded: comments are found by a small lexer, not a TypeScript parser. A quoted string never
runs past its line (as in TS), so an apostrophe in JSX text cannot hide the next line; a `//` inside
JSX text (a bare URL in prose) is read as a comment for the rest of that line; a stray backtick in JSX
text is read as a template to the end of the file, which can only add findings, never hide one.

Non-vacuous: `tests/test_ui_words_check.py` plants the phrase in the shapes the Glass's strings took
before L1.8 (a section's `aria-label`, a heading's JSX text, a words table's constant, a panel's
`words` attribute, a template literal, wrapped JSX text, a JSON copy file) and the shapes the lane
review of L1.8 named (a hyphen, `{" "}`, a template nested in another, a comment inside a template's
expression), and asserts each is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from tools.layout import CORE

GLASS_SRC = CORE / "apps" / "workspace" / "src"

#: The banned phrase, its words apart by whitespace, a hyphen, or JSX's `{" "}`. The words in its place
#: are "domain model".
BANNED = re.compile(r"\btarget(?:\s|-|\{\s*[\"'`]\s+[\"'`]\s*\})+model", re.IGNORECASE)

SUFFIXES = frozenset({".ts", ".tsx", ".json", ".html", ".md"})


def strip_comments(text: str) -> str:
    """`text` with every `//` and `/* */` comment blanked to spaces, newlines kept (so line numbers
    hold), strings and template literals left as they are. A template literal's `${...}` is read as
    code, so a template nested inside one, or a comment inside its expression, is read as such."""
    out: list[str] = []
    n = len(text)

    def code(i: int, closing: bool) -> int:
        """Code from `i`; with `closing`, up to the `}` that ends a template's `${`."""
        depth = 0
        while i < n:
            c, two = text[i], text[i : i + 2]
            if closing and c == "}" and depth == 0:
                return i
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
            elif c in "\"'":
                j = i + 1
                while j < n and text[j] != c:
                    if text[j] == "\\":
                        j += 1
                    elif text[j] == "\n":
                        break  # a quoted string never spans a line: an apostrophe in JSX text
                    j += 1
                j = min(j + 1, n) if j < n and text[j] == c else j
                out.append(text[i:j])
                i = j
            elif c == "`":
                out.append(c)
                i = template(i + 1)
            else:
                depth += {"{": 1, "}": -1}.get(c, 0) if closing else 0
                out.append(c)
                i += 1
        return i

    def template(i: int) -> int:
        """A template literal's text from `i`, its `${...}` read as code; returns past its closing `."""
        while i < n:
            c = text[i]
            if c == "\\":
                out.append(text[i : i + 2])
                i += 2
            elif c == "`":
                out.append(c)
                return i + 1
            elif text[i : i + 2] == "${":
                out.append("${")
                i = code(i + 2, closing=True)
                if i < n:
                    out.append("}")
                    i += 1
            else:
                out.append(c)
                i += 1
        return i

    code(0, closing=False)
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
