"""`scripts/simple_markdown.py` — a dependency-free renderer scoped to what the Apache-scoped docs
actually use, not full CommonMark. Each test proves one construct in isolation; a separate
integration check (`test_renders_the_real_architecture_doc_without_crashing`) proves it survives a
real document, not only hand-written fixtures.
"""

from __future__ import annotations

from pathlib import Path

from scripts.simple_markdown import render_inline, render_markdown

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_headers_render_at_every_level() -> None:
    assert render_markdown("# One") == "<h1>One</h1>"
    assert render_markdown("### Three") == "<h3>Three</h3>"


def test_bold_italic_and_inline_code() -> None:
    html = render_inline("**bold** and *italic* and `code`")
    assert html == "<strong>bold</strong> and <em>italic</em> and <code>code</code>"


def test_bold_marker_inside_inline_code_is_not_misread() -> None:
    html = render_inline("`**not bold**`")
    assert html == "<code>**not bold**</code>"


def test_html_is_escaped_before_markup_is_applied() -> None:
    html = render_inline("<script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_a_fenced_code_block_with_a_language_tag() -> None:
    text = "```yaml\nmap:\n  default: osm-local\n```"
    html = render_markdown(text)
    assert html == '<pre><code class="language-yaml">map:\n  default: osm-local</code></pre>'


def test_a_fenced_code_block_with_no_language_tag() -> None:
    html = render_markdown("```\nplain\n```")
    assert html == "<pre><code>plain</code></pre>"


def test_a_pipe_table() -> None:
    text = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    html = render_markdown(text)
    assert html == (
        "<table><thead><tr><th>A</th><th>B</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    )


def test_an_unordered_list() -> None:
    html = render_markdown("- one\n- two")
    assert html == "<ul><li>one</li><li>two</li></ul>"


def test_an_ordered_list() -> None:
    html = render_markdown("1. one\n2. two")
    assert html == "<ol><li>one</li><li>two</li></ol>"


def test_a_blockquote() -> None:
    assert render_markdown("> quoted") == "<blockquote><p>quoted</p></blockquote>"


def test_a_horizontal_rule() -> None:
    assert render_markdown("---") == "<hr>"


def test_adjacent_lines_join_into_one_paragraph() -> None:
    html = render_markdown("line one\nline two")
    assert html == "<p>line one line two</p>"


def test_a_blank_line_separates_paragraphs() -> None:
    html = render_markdown("first\n\nsecond")
    assert html == "<p>first</p>\n<p>second</p>"


def test_renders_the_real_architecture_doc_without_crashing() -> None:
    """The integration check: every real construct `00_ARCHITECTURE.md` actually uses (headers,
    tables, fenced code, bold, inline code) survives a real document, not only the hand-written
    fixtures above."""
    text = (REPO_ROOT / "docs" / "00_ARCHITECTURE.md").read_text(encoding="utf-8")

    html = render_markdown(text)

    assert "<h2>" in html or "<h1>" in html
    assert "<table>" in html
    assert "<pre><code" in html
    assert "<strong>" in html
    assert "<script" not in html.lower()
