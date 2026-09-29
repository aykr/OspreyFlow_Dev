"""A small, dependency-free Markdown-to-HTML renderer, scoped to what `docs/`'s own Apache-scoped
files actually use — checked directly before writing this, not assumed from Markdown's full
surface: `#`-`######` headers, paragraphs, `**bold**`/`*italic*`, `` `inline code` ``, fenced
``` code blocks (with an optional language tag, kept as a `class` for a future syntax highlighter
this module does not itself provide), pipe tables, `-`/`*` bullet lists and `1.` ordered lists,
`>` blockquotes, and `---` horizontal rules. No reference-style or inline `[text](url)` links —
grepped for across every Apache-scoped file before this was written, and none exist there (they do
appear in the private-tree `process/SESSION_HANDOVER.md`, which this renderer never sees). Bare URLs
are left as plain text rather than auto-linked, a deliberate simplification rather than a gap this
module fails to disclose.

**Why hand-rolled rather than a dependency.** No Markdown library is installed today (checked:
`import markdown`/`mistune`/`commonmark` all fail in `.venv`) and `pyproject.toml`'s own
dependency list is small and deliberately reasoned about, package by package, with its own licence
noted at the point of addition — adding a new one for a bundle-time convenience this narrow set of
constructs already covers is a cost this module avoids rather than pays silently. This is not a
general-purpose CommonMark implementation and does not try to be one.

HTML escaping is applied to every text run before any construct markup is added, so the docs'
own frequent backtick-quoted code (file paths, class names, shell commands) can never inject
markup into the rendered page.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_HEADER = re.compile(r"^(#{1,6})\s+(.*)$")
_ORDERED_ITEM = re.compile(r"^(\d+)\.\s+(.*)$")
_UNORDERED_ITEM = re.compile(r"^[-*]\s+(.*)$")
_BLOCKQUOTE = re.compile(r"^>\s?(.*)$")
_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")
_TABLE_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|?$")
_HR = re.compile(r"^(-{3,}|\*{3,})$")
_FENCE = re.compile(r"^```\s*(\S*)\s*$")


def render_inline(text: str) -> str:
    """Escapes the text, then layers `code`/`bold`/`italic` spans on top — in that order, so a
    bold marker inside a code span (e.g. `` `**not bold**` ``) is not misread, since the code
    span's own content is protected from the later passes by being substituted back in after
    they run."""
    escaped = html.escape(text)

    code_spans: list[str] = []

    def _stash_code(match: re.Match[str]) -> str:
        code_spans.append(match.group(1))
        return f"\x00{len(code_spans) - 1}\x00"

    with_code_stashed = _INLINE_CODE.sub(_stash_code, escaped)
    with_bold = _BOLD.sub(r"<strong>\1</strong>", with_code_stashed)
    with_italic = _ITALIC.sub(r"<em>\1</em>", with_bold)

    def _restore_code(match: re.Match[str]) -> str:
        return f"<code>{code_spans[int(match.group(1))]}</code>"

    return re.sub(r"\x00(\d+)\x00", _restore_code, with_italic)


@dataclass
class _ListState:
    ordered: bool
    items: list[str]


def render_markdown(text: str) -> str:
    """Converts a whole document's own Markdown text to an HTML fragment (no `<html>`/`<body>`
    wrapper — the caller supplies the page shell)."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    list_state: _ListState | None = None
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{render_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_state
        if list_state is not None:
            tag = "ol" if list_state.ordered else "ul"
            items_html = "".join(f"<li>{render_inline(item)}</li>" for item in list_state.items)
            out.append(f"<{tag}>{items_html}</{tag}>")
            list_state = None

    while i < len(lines):
        line = lines[i]

        fence_match = _FENCE.match(line)
        if fence_match:
            flush_paragraph()
            flush_list()
            lang = fence_match.group(1)
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not _FENCE.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip the closing fence
            css_class = f' class="language-{html.escape(lang)}"' if lang else ""
            code_text = html.escape("\n".join(code_lines))
            out.append(f"<pre><code{css_class}>{code_text}</code></pre>")
            continue

        if _TABLE_ROW.match(line) and i + 1 < len(lines) and _TABLE_SEPARATOR.match(lines[i + 1]):
            flush_paragraph()
            flush_list()
            header_cells = [c.strip() for c in _TABLE_ROW.match(line).group(1).split("|")]
            i += 2
            body_rows: list[list[str]] = []
            while i < len(lines) and _TABLE_ROW.match(lines[i]):
                body_rows.append(
                    [c.strip() for c in _TABLE_ROW.match(lines[i]).group(1).split("|")]
                )
                i += 1
            thead = "".join(f"<th>{render_inline(c)}</th>" for c in header_cells)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{render_inline(c)}</td>" for c in row) + "</tr>"
                for row in body_rows
            )
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            continue

        header_match = _HEADER.match(line)
        if header_match:
            flush_paragraph()
            flush_list()
            level = len(header_match.group(1))
            out.append(f"<h{level}>{render_inline(header_match.group(2))}</h{level}>")
            i += 1
            continue

        if _HR.match(line.strip()) and line.strip():
            flush_paragraph()
            flush_list()
            out.append("<hr>")
            i += 1
            continue

        ordered_match = _ORDERED_ITEM.match(line)
        unordered_match = _UNORDERED_ITEM.match(line)
        if ordered_match or unordered_match:
            flush_paragraph()
            is_ordered = ordered_match is not None
            item_text = (ordered_match or unordered_match).group(
                2 if ordered_match else 1
            )
            if list_state is None or list_state.ordered != is_ordered:
                flush_list()
                list_state = _ListState(ordered=is_ordered, items=[])
            list_state.items.append(item_text)
            i += 1
            continue

        blockquote_match = _BLOCKQUOTE.match(line)
        if blockquote_match:
            flush_paragraph()
            flush_list()
            out.append(f"<blockquote><p>{render_inline(blockquote_match.group(1))}</p></blockquote>")
            i += 1
            continue

        if not line.strip():
            flush_paragraph()
            flush_list()
            i += 1
            continue

        # A continuation of an in-progress list item (indented text) is out of scope — treated as
        # a new paragraph, the same "covers what these docs use, not full CommonMark" boundary
        # this module's own docstring states.
        flush_list()
        paragraph.append(line.strip())
        i += 1

    flush_paragraph()
    flush_list()
    return "\n".join(out)
