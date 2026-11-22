"""`python -m tools.theme_rule_check` — a theme's CSS rule outside its own folder is found.

ADR-152 Amendment 4 (21 November 2026; the owner's rulings on build id PL12): a theme that is not
the default has one folder, `OspreyFlow_Core/packages/themes/<name>/`, and no rule in the shared
design package names a theme. This is the guard (item 5): it fails if a theme's rule appears outside
its folder, against an allowlist of today's GOV.UK rules outside it
(`tests/fixtures/theme_rule_allowlist.txt`), and the allowlist may only shrink. It reaches zero when
the React GOV.UK look is retired (item 8: one release after the cutover, by a build of its own, on
the owner's word then). Nothing is moved by the build that wrote this; the allowlist is what is
outside the folder today.

**What is a theme rule.** Read as CSS (comments blanked, strings skipped, at-rule blocks and nested
rules followed; not a regex over lines), then one finding per rule or entry:

* kind `rule`: a rule whose selector names a brand (`[data-brand="x"]`, any value) or carries the
  word `govuk` in a class or other name (`.govuk-header`, `.admin-nav--govuk`; not `.ungovukable`);
* kind `custom-property`: a rule that is not a `rule` above but declares or reads a `--…govuk…`
  custom property (or an `@property` that names one);
* kind `font-face`: an `@font-face` naming GDS Transport; kind `font-use`: any other rule whose
  declarations name it; kind `font-entry`: an entry for it in a `fonts*.json` list;
* kind `string-rule`: any of these inside a Python or JavaScript string, in the two sign-in theme
  files named below and in any such file under a theme folder.

A theme's name is the brand's value, or `govuk` for the word and for GDS Transport. A finding under
`packages/themes/<name>/` for its own `<name>` is allowed, anywhere else it is a violation: a rule
of theme A under theme B's folder is one too.

**What is scanned.** Under `OspreyFlow_Core`: `packages/design`, `packages/themes`,
`packages/glass-shared/src`, `apps/workspace/src`, `apps/workspace/scripts`, `apps/pages`,
`apps/harness/src` (the `.css` files, the `<style>` blocks of `.njk` and `.html` files, and
`fonts*.json`); and, as strings, `harness/keycloak_theme.py` and `harness/govuk_chrome.js` by name.
`node_modules`, `dist` and anything under `assets/govuk` (generated output) are never read; nor are
the marketing sites or `OspreyFlow_Build`.

**What it cannot see.** A component's class strings (the 56 React files that branch on the brand are
code, not CSS rules), a theme named only in TypeScript or in a `.mjs` build script, an `@import` of
a GOV.UK stylesheet, a rule in a JavaScript regular expression or a template literal's `${…}`, and
a stylesheet held only in a string outside the two named sign-in files. Python strings are read
through `ast`, so a docstring or a comment is never a rule; JavaScript strings are read by a small
tokeniser (comments skipped; a regular expression literal holding a quote can confuse it).

**The ratchet.** The allowlist's first line is `count: N`. The check fails if the file holds more
entries than it records (one was added), fewer (the count was edited by hand), an entry whose rule
is no longer found (stale: delete it, so the list shrinks), a rule found that no entry excuses, or a
recorded count above `RATCHET_CEILING` below. The ceiling is the same figure kept a second time, in
code, so that raising the count takes a visible edit here as well; it must equal the recorded count,
so a slice that removes a rule lowers both. Nobody raises either without the owner's word.

Not wired into `make ci` (the Makefile is the owner's): the owner applies the diff the slice's
report gives. `tests/glass_trees/test_theme_rules.py` shows it red, and green, for each shape (rule
15)."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from tools.layout import BUILD, CORE

ALLOWLIST_PATH = BUILD / "tests" / "fixtures" / "theme_rule_allowlist.txt"
#: The recorded count, kept a second time (see the module's "The ratchet"). Lower it with the
#: allowlist's first line when a slice removes a rule; never raise it without the owner's word.
RATCHET_CEILING = 70

#: Where themes live, relative to `OspreyFlow_Core` (ADR-152 Amendment 4, item 1).
THEMES_DIR = "packages/themes"
#: Each folder read, relative to `OspreyFlow_Core`.
SCAN_ROOTS = (
    "packages/design",
    THEMES_DIR,
    "packages/glass-shared/src",
    "apps/workspace/src",
    "apps/workspace/scripts",
    "apps/pages",
    "apps/harness/src",
)
#: The sign-in theme's files, read as strings, by name.
SIGN_IN_FILES = ("harness/keycloak_theme.py", "harness/govuk_chrome.js")
#: Folders never entered: installed or generated output.
PRUNED = frozenset({"node_modules", "dist", ".git", "__pycache__"})

_GOVUK_WORD = re.compile(r"(?<![A-Za-z0-9])govuk(?![A-Za-z0-9])", re.IGNORECASE)
_BRAND = re.compile(
    r"""\[\s*data-brand\s*[~|^$*]?=\s*(?:"([^"]*)"|'([^']*)'|([^\s\]"']+))\s*(?:[is]\s*)?\]""",
    re.IGNORECASE,
)
_GDS = re.compile(r"gds[\s_-]*transport", re.IGNORECASE)
_CUSTOM_PROPERTY = re.compile(r"--[\w-]+")
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_GROUPING = re.compile(r"@(media|supports|layer|container|document|scope|starting-style)\b", re.I)
_KEY_LIMIT = 110


class ThemeScanError(Exception):
    """A file the check could not read as what it is (an unclosed block, a bad count line)."""


class RawFinding(NamedTuple):
    """One theme rule in a piece of text: where it is in the file is not part of it."""

    key: str
    kind: str
    themes: tuple[str, ...]


class Finding(NamedTuple):
    path: str  # relative to OspreyFlow_Core, with forward slashes
    key: str
    kind: str
    themes: tuple[str, ...]

    @property
    def entry(self) -> tuple[str, str, str]:
        return (self.path, self.key, self.kind)


# ---------------------------------------------------------------------------------- reading CSS


def _skip_string(text: str, start: int) -> int:
    """The index just past the string that opens at `start`."""
    quote = text[start]
    i = start + 1
    while i < len(text) and text[i] != quote:
        i += 2 if text[i] == "\\" else 1
    return i + 1


def _blank_comments(css: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(css):
        c = css[i]
        if c == "/" and css[i + 1 : i + 2] == "*":
            end = css.find("*/", i + 2)
            i = len(css) if end == -1 else end + 2
            out.append(" ")
        elif c in "\"'":
            end = _skip_string(css, i)
            out.append(css[i:end])
            i = end
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _find(css: str, targets: str, start: int, stop: int) -> int:
    """The first of `targets` at or after `start` and before `stop`, outside a string; or -1."""
    i = start
    while i < stop:
        c = css[i]
        if c in "\"'":
            i = _skip_string(css, i)
        elif c == "\\":
            i += 2
        elif c in targets:
            return i
        else:
            i += 1
    return -1


def _closing(css: str, open_at: int) -> int:
    depth = 0
    i = open_at
    while i < len(css):
        c = css[i]
        if c in "\"'":
            i = _skip_string(css, i)
            continue
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ThemeScanError("a block is opened and never closed")


def _normal(text: str) -> str:
    return re.sub(r"\s*,\s*", ", ", re.sub(r"\s+", " ", text.strip()))


def _blank_strings(text: str) -> str:
    """The text with each string's contents removed (a name inside a string is not a property)."""
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] in "\"'":
            i = _skip_string(text, i)
            out.append('""')
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _key(context: tuple[str, ...], selector: str) -> str:
    key = " :: ".join((*context, selector))
    if len(key) > _KEY_LIMIT:
        # A label for a long key, not a secret.
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]  # noqa: S324
        key = f"{key[: _KEY_LIMIT - 12]}... #{digest}"
    return key


def _selector_themes(selector: str) -> set[str]:
    themes = {
        next(g for g in m.groups() if g is not None).lower() for m in _BRAND.finditer(selector)
    }
    if _GOVUK_WORD.search(selector):
        themes.add("govuk")
    return themes


def _body_theme(body: str) -> tuple[str, set[str]] | None:
    """(`custom-property` or `font-use`, themes) when a rule's declarations name a theme."""
    plain = _blank_strings(body)
    if any(_GOVUK_WORD.search(token) for token in _CUSTOM_PROPERTY.findall(plain)):
        return ("custom-property", {"govuk"})
    if _GDS.search(body):
        return ("font-use", {"govuk"})
    return None


def _walk(css: str, context: tuple[str, ...], out: list[RawFinding]) -> None:
    i = 0
    while i < len(css):
        brace = _find(css, "{", i, len(css))
        semicolon = _find(css, ";", i, len(css) if brace == -1 else brace)
        if brace == -1 or semicolon != -1:
            i = len(css) if semicolon == -1 else semicolon + 1
            continue
        prelude = _normal(css[i:brace])
        end = _closing(css, brace)
        body = css[brace + 1 : end]
        i = end + 1
        if prelude.startswith("@"):
            if _GROUPING.match(prelude):
                _walk(body, (*context, prelude), out)
            elif re.match(r"@font-face\b", prelude, re.IGNORECASE):
                if _GDS.search(body):
                    out.append(
                        RawFinding(
                            _key(context, "@font-face GDS Transport"), "font-face", ("govuk",)
                        )
                    )
            elif re.match(r"@property\b", prelude, re.IGNORECASE) and _GOVUK_WORD.search(prelude):
                out.append(RawFinding(_key(context, prelude), "custom-property", ("govuk",)))
            continue
        themes = _selector_themes(prelude)
        kind = "rule"
        if not themes:
            hit = _body_theme(body)
            if hit is not None:
                kind, themes = hit
        if themes:
            out.append(RawFinding(_key(context, prelude), kind, tuple(sorted(themes))))
        elif "{" in body:
            _walk(body, context, out)


def css_findings(css: str) -> list[RawFinding]:
    """Every theme rule in `css`, in file order; `ThemeScanError` on a block that never closes."""
    found: list[RawFinding] = []
    _walk(_blank_comments(css), (), found)
    return found


# ------------------------------------------------------------------ reading strings in code


def _python_strings(text: str) -> list[str]:
    tree = ast.parse(text)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}


def _javascript_strings(text: str) -> list[str]:
    strings: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "/" and text[i + 1 : i + 2] == "/":
            end = text.find("\n", i)
            i = len(text) if end == -1 else end
        elif c == "/" and text[i + 1 : i + 2] == "*":
            end = text.find("*/", i + 2)
            i = len(text) if end == -1 else end + 2
        elif c in "\"'`":
            end = _skip_string(text, i)
            raw = text[i + 1 : end - 1]
            strings.append(
                re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), raw, flags=re.S)
            )
            i = end
        else:
            i += 1
    return strings


def string_findings(source: str, *, python: bool) -> list[RawFinding]:
    """Every theme rule held in a string of a Python or JavaScript source; kind `string-rule`.

    A string that is not a stylesheet (an unbalanced brace in a message) is skipped, not an error.
    """
    try:
        strings = _python_strings(source) if python else _javascript_strings(source)
    except SyntaxError as error:
        raise ThemeScanError(f"not valid Python: {error}") from error
    found: list[RawFinding] = []
    for text in strings:
        if "{" not in text:
            continue
        try:
            found += [RawFinding(f.key, "string-rule", f.themes) for f in css_findings(text)]
        except ThemeScanError:
            continue
    return found


def _fonts_findings(text: str) -> list[RawFinding]:
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ThemeScanError(f"not valid JSON: {error}") from error
    fonts = data.get("fonts", []) if isinstance(data, dict) else []
    return [
        RawFinding("GDS Transport", "font-entry", ("govuk",))
        for entry in fonts
        if isinstance(entry, dict) and _GDS.search(str(entry.get("family", "")))
    ]


def _html_findings(text: str) -> list[RawFinding]:
    found: list[RawFinding] = []
    for block in _STYLE_BLOCK.findall(text):
        try:
            found += css_findings(block)
        except ThemeScanError:
            continue  # a template's own tags inside a style block are not a stylesheet to refuse
    return found


# ---------------------------------------------------------------------------- reading the tree


def _generated(parts: tuple[str, ...]) -> bool:
    return any(a == "assets" and b == "govuk" for a, b in zip(parts, parts[1:], strict=False))


def scanned_files(core: Path = CORE) -> list[tuple[Path, str]]:
    """`(file, how it is read)` for everything read under `core`: `css`, `html`, `fonts`, or
    `python` / `javascript` (as strings)."""
    files: list[tuple[Path, str]] = []
    for top in SCAN_ROOTS:
        root = core / top
        in_themes = top == THEMES_DIR
        for here, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in PRUNED)
            for name in sorted(names):
                path = Path(here) / name
                if _generated(path.relative_to(core).parts):
                    continue
                suffix = path.suffix
                if suffix == ".css":
                    files.append((path, "css"))
                elif suffix in {".njk", ".html"}:
                    files.append((path, "html"))
                elif suffix == ".json" and name.startswith("fonts"):
                    files.append((path, "fonts"))
                elif in_themes and suffix == ".py":
                    files.append((path, "python"))
                elif in_themes and suffix in {".js", ".mjs", ".ts"}:
                    files.append((path, "javascript"))
    for name in SIGN_IN_FILES:
        path = core / name
        if path.is_file():
            files.append((path, "python" if name.endswith(".py") else "javascript"))
    return files


def _read(path: Path, how: str) -> list[RawFinding]:
    text = path.read_text(encoding="utf-8")
    try:
        if how == "css":
            return css_findings(text)
        if how == "html":
            return _html_findings(text)
        if how == "fonts":
            return _fonts_findings(text)
        return string_findings(text, python=how == "python")
    except ThemeScanError as error:
        raise ThemeScanError(f"{path}: {error}") from error


def _home(relative: str) -> str | None:
    """The theme whose folder holds `relative` (`packages/themes/<name>/…`), or None."""
    parts = relative.split("/")
    prefix = THEMES_DIR.split("/")
    if parts[: len(prefix)] == prefix and len(parts) > len(prefix) + 1:
        return parts[len(prefix)]
    return None


def find_theme_rules(core: Path = CORE) -> list[Finding]:
    """Every theme rule under `core` that is not in its own theme's folder, sorted."""
    found: list[Finding] = []
    for path, how in scanned_files(core):
        relative = path.relative_to(core).as_posix()
        home = _home(relative)
        for raw in _read(path, how):
            if home is not None and set(raw.themes) <= {home}:
                continue  # at home: the move the check exists to allow
            found.append(Finding(relative, raw.key, raw.kind, raw.themes))
    return sorted(found)


# -------------------------------------------------------------------------------- the ratchet


Entry = tuple[str, str, str]


@dataclass
class Allowlist:
    recorded: int
    entries: list[Entry] = field(default_factory=list)


@dataclass
class Judgement:
    new: list[Finding] = field(default_factory=list)
    stale: list[Entry] = field(default_factory=list)
    count_problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.new or self.stale or self.count_problems)


def load_allowlist(path: Path = ALLOWLIST_PATH) -> Allowlist:
    lines = path.read_text(encoding="utf-8").splitlines()
    match = re.fullmatch(r"count:\s*(\d+)\s*", lines[0]) if lines else None
    if match is None:
        raise ThemeScanError(
            f"{path.name}: the first line must be `count: N`, the number of entries"
        )
    entries: list[Entry] = []
    for number, raw in enumerate(lines[1:], start=2):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) != 3 or not all(p.strip() for p in parts):
            raise ThemeScanError(f"{path.name}:{number}: an entry is `path<TAB>key<TAB>kind`")
        entries.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return Allowlist(int(match.group(1)), entries)


def judge(findings: Iterable[Finding], allowlist: Allowlist) -> Judgement:
    """Findings against the allowlist, as a multiset: a rule written twice needs two entries."""
    result = Judgement()
    excuses = Counter(allowlist.entries)
    for finding in findings:
        if excuses[finding.entry] > 0:
            excuses[finding.entry] -= 1
        else:
            result.new.append(finding)
    result.stale = sorted(excuses.elements())
    held, recorded = len(allowlist.entries), allowlist.recorded
    if held > recorded:
        result.count_problems.append(
            f"the allowlist holds {held} entries but records {recorded}: an entry was added; "
            "the list may only shrink, and nobody raises the count without the owner's word"
        )
    elif held < recorded:
        result.count_problems.append(
            f"the allowlist holds {held} entries but records {recorded}: the count is not the "
            "number of entries (it is lowered by deleting an entry's line, and the count with it)"
        )
    if recorded > RATCHET_CEILING:
        result.count_problems.append(
            f"the recorded count {recorded} is above the ceiling {RATCHET_CEILING}: the count "
            "may only fall; raising it needs the owner's word"
        )
    elif recorded < RATCHET_CEILING:
        result.count_problems.append(
            f"the recorded count {recorded} is below the ceiling {RATCHET_CEILING}: "
            f"lower RATCHET_CEILING in tools/theme_rule_check.py to {recorded}"
        )
    return result


def entry_line(finding: Finding) -> str:
    return "\t".join(finding.entry)


def main(
    argv: list[str] | None = None, *, core: Path = CORE, allowlist_path: Path = ALLOWLIST_PATH
) -> int:
    args = argv or []
    try:
        findings = find_theme_rules(core)
        if "--list" in args:
            for finding in findings:
                print(entry_line(finding))
            return 0
        verdict = judge(findings, load_allowlist(allowlist_path))
    except ThemeScanError as error:
        print(f"theme-rule-check: {error}")
        return 1
    for finding in verdict.new:
        themes = " and ".join(finding.themes)
        print(
            f"{finding.path}: {finding.key} [{finding.kind}] is the {themes} theme's and is "
            f"outside {THEMES_DIR}/{finding.themes[0]}/, and not on {allowlist_path.name}"
        )
    for path, key, kind in verdict.stale:
        print(
            f"{allowlist_path.name}: {path}  {key} [{kind}] is no longer found; "
            "delete its line and lower the count"
        )
    for problem in verdict.count_problems:
        print(f"{allowlist_path.name}: {problem}")
    if not verdict.ok:
        print(
            f"theme-rule-check: {len(verdict.new)} theme rule(s) outside their folder and not on "
            f"the allowlist, {len(verdict.stale)} stale entry(ies), "
            f"{len(verdict.count_problems)} count problem(s)",
            file=sys.stderr,
        )
        return 1
    print(
        f"theme-rule-check: scanned {len(scanned_files(core))} files in "
        f"{', '.join(SCAN_ROOTS)} and {', '.join(SIGN_IN_FILES)}; {len(findings)} theme rule(s) "
        "outside a theme folder, all on the allowlist (it only shrinks)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
