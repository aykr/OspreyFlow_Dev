"""The install package's guides as PDFs (`06_DECISIONS.md` ADR-114 Amendment 15 point 2, Amendment
26): the Markdown in Core's `docs/` is the source; each guide is rendered by `tools.simple_markdown`
into a page styled from the design tokens (`apps/workspace/src/design/tokens.css`, light theme — no
colour of its own), printed to `docs/pdf/<guide>.pdf`, and recorded in `docs/pdf/manifest.json` with
the SHA-256 of its Markdown, of every image it shows, and of the PDF made from them.

**Each guide carries its own version record** (Amendment 26): a *Document control* section between
`<!-- document-control:begin -->` and `<!-- document-control:end -->`, giving its version, date, the
OspreyFlow release it describes and its status, above a version history, newest first. The manifest
also records each guide's version and the SHA-256 of everything outside that section; a guide whose
content changed while its version did not is out of step, and `--write` refuses to print it — the
change needs its own row in the history first.

**Each PDF opens with** a cover page, the document control, the contents and the list of figures,
both with page numbers, and every page is numbered in its footer. The browser cannot number a page a
link points to, so the guide is printed once with placeholders, the page each heading and figure
landed on is read back from that PDF (`pypdf`), and it is printed again with the numbers; the second
printing is read back too, and printed once more if a number moved.

`check()` recomputes all of this and names each guide that is out of step — its Markdown or an image
changed since its PDF was made, its content changed without a new version, its version record
malformed, its PDF replaced or missing — and every image a guide shows that is not there, and every
screenshot in `docs/images/` no guide shows. `tests/test_docs_pdf.py` runs it, so a guide changed
without its PDF being made again fails the build. Printing needs a browser and so is a person's
step, never CI's:

    python -m tools.docs_pdf --write [--chrome PATH]   # make every PDF and the manifest
    python -m tools.docs_pdf                           # check only (what the test does)

Printing is Playwright's Chromium, through `tools/print_pdf.mjs` (Core's `@playwright/test`); the
browser is `--chrome`, else `OSPREY_CHROME`, else Playwright's own. A PDF's own bytes differ from
one printing to the next (the browser stamps the time in it), which is why the manifest records the
PDF's hash rather than expecting a reproducible one.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tools.layout import BUILD, CORE
from tools.simple_markdown import render_markdown

DOCS = CORE / "docs"
TOKENS = CORE / "apps" / "workspace" / "src" / "design" / "tokens.css"
PRINTER = BUILD / "tools" / "print_pdf.mjs"
#: Each guide, in the order its reader meets them: its file, its title, and its short name.
GUIDES: tuple[tuple[str, str], ...] = (
    ("administration-guide.md", "OspreyFlow — Installation and Administration Guide"),
    ("user-guide.md", "OspreyFlow — User Guide"),
    ("developer-guide.md", "OspreyFlow — Developer Guide"),
)
_IMAGE = re.compile(r"^!\[[^\]]*\]\(([^)\s]+)\)\s*$", re.MULTILINE)
_GUIDE_LINK = re.compile(r'<a href="([a-z0-9-]+)\.md(?:#[^"]*)?">([^<]*)</a>')
#: A local address in a printed PDF — the printing machine's own folders.
_LOCAL_ADDRESS = re.compile(rb"file://(/[^/\s)]+/[^/\s)]+/)?")

_CONTROL = re.compile(
    r"<!-- document-control:begin -->\n(.*?)<!-- document-control:end -->\n\n?", re.DOTALL
)
_CURRENT = re.compile(
    r"^\*\*Version (\d+\.\d+)\*\* · (\d{4}-\d{2}-\d{2}) · For OspreyFlow "
    r"(v\d+\.\d+\.\d+|unreleased) · (Issued|Draft)$",
    re.MULTILINE,
)
_HISTORY_ROW = re.compile(r"^\| (\d+\.\d+) \| (\d{4}-\d{2}-\d{2}) \| (.+?) \|$", re.MULTILINE)
_HEADING = re.compile(r"<h([23])>(.*?)</h\1>")
_CAPTION = re.compile(r"<figcaption>(.*?)</figcaption>")
_TAG = re.compile(r"<[^>]+>")
#: Front matter printed before a page number is known: the same width as a real one, so the second
#: printing lays out exactly as the first.
_PLACEHOLDER = "000"

#: The page's own rules: sizes and spacing only, every colour a token (CLAUDE.md: no colour outside
#: the tokens). `tests/test_docs_pdf.py` refuses a literal colour here.
DOC_CSS = """
@page { size: A4; margin: 18mm 16mm 20mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { background: var(--surface-app); color: var(--text-primary); font-family: var(--ui);
       font-size: 10.5pt; line-height: 1.45; margin: 0; }
main { max-width: 100%; }
h1 { font-size: 22pt; line-height: 1.2; margin: 0 0 var(--sp-16);
     padding-bottom: var(--sp-8); border-bottom: 2px solid var(--brass); }
h2 { font-size: 15pt; margin: var(--sp-32) 0 var(--sp-8); break-after: avoid; }
h3 { font-size: 12pt; margin: var(--sp-20) 0 var(--sp-6); break-after: avoid; }
h2 + *, h3 + * { break-before: avoid; }
p { margin: 0 0 var(--sp-8); }
p, li { color: var(--text-primary); }
ul, ol { margin: 0 0 var(--sp-8); padding-left: var(--sp-24); }
a { color: var(--brass-press); text-decoration: none; }
code { font-family: var(--mono); font-size: 0.9em; background: var(--surface-raised);
       padding: 0 var(--sp-2); border-radius: var(--r-control); }
pre { background: var(--surface-raised); border: 1px solid var(--border-subtle);
      border-radius: var(--r-panel); padding: var(--sp-8) var(--sp-12); white-space: pre-wrap;
      break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: var(--sp-8) 0 var(--sp-12);
        font-size: 9pt; break-inside: auto; }
th { text-align: left; color: var(--text-secondary); border-bottom: 1px solid var(--border); }
th, td { padding: var(--sp-4) var(--sp-6); vertical-align: top; }
td { border-bottom: 1px solid var(--border-subtle); }
tr { break-inside: avoid; }
blockquote { margin: var(--sp-8) 0; padding-left: var(--sp-12);
             border-left: 3px solid var(--brass); color: var(--text-secondary); }
hr { border: none; border-top: 1px solid var(--border-subtle); margin: var(--sp-24) 0; }
figure { margin: var(--sp-12) 0 var(--sp-16); break-inside: avoid; }
figure img { max-width: 100%; max-height: 120mm; border: 1px solid var(--border-subtle);
             border-radius: var(--r-panel); }
figcaption { font-size: 9pt; color: var(--text-secondary); margin-top: var(--sp-4); }
.cover { height: 240mm; display: flex; flex-direction: column; justify-content: center;
         break-after: page; }
.cover-product { font-size: 13pt; letter-spacing: 0.08em; text-transform: uppercase;
                 color: var(--text-secondary); margin: 0 0 var(--sp-8); }
.cover-title { font-size: 30pt; line-height: 1.15; margin: 0 0 var(--sp-24);
               padding-bottom: var(--sp-16); border-bottom: 3px solid var(--brass); }
.cover-audience { font-size: 11.5pt; color: var(--text-secondary); max-width: 140mm;
                  margin: 0 0 var(--sp-32); }
.cover-facts { display: grid; grid-template-columns: max-content 1fr; gap: var(--sp-4) var(--sp-16);
               font-size: 10.5pt; margin: 0; }
.cover-facts dt { color: var(--text-secondary); }
.cover-facts dd { margin: 0; }
.front { break-after: page; }
.front > h2 { margin-top: 0; }
.leaders { list-style: none; padding: 0; margin: 0; }
.leaders li { display: flex; align-items: baseline; gap: var(--sp-4); margin: 0 0 var(--sp-4); }
.leaders .dots { flex: 1; border-bottom: 1px dotted var(--border); min-width: var(--sp-16); }
.leaders .at { min-width: 2.2em; text-align: right; }
.leaders .level-3 { padding-left: var(--sp-16); font-size: 9.5pt; }
.leaders a { color: var(--text-primary); border-bottom: none; text-decoration: none; }
"""


class DocumentControlError(ValueError):
    """A guide's version record is missing or does not hold together, in words."""


@dataclass(frozen=True)
class Control:
    version: str
    date: str
    release: str
    status: str
    history: tuple[tuple[str, str, str], ...]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _version_key(version: str) -> tuple[int, int]:
    major, minor = version.split(".")
    return int(major), int(minor)


def images_of(markdown: str) -> list[str]:
    """The images a guide shows, as written (relative to `docs/`)."""
    return _IMAGE.findall(markdown)


def control_of(markdown: str) -> Control:
    """The guide's version record, held to its own rules: the current version and date are the
    newest row of the history, and the history runs newest first, every version once."""
    found = _CONTROL.search(markdown)
    if not found:
        raise DocumentControlError("it has no document control section")
    block = found.group(1)
    current = _CURRENT.search(block)
    if not current:
        raise DocumentControlError(
            "its document control has no `**Version X.Y** · YYYY-MM-DD · For OspreyFlow vX.Y.Z · "
            "Issued` line"
        )
    history = tuple(_HISTORY_ROW.findall(block))
    if not history:
        raise DocumentControlError("its version history has no rows")
    version, date, release, status = current.groups()
    if (version, date) != history[0][:2]:
        raise DocumentControlError(
            f"it says version {version} of {date}, but its newest history row is "
            f"{history[0][0]} of {history[0][1]}"
        )
    for newer, older in zip(history, history[1:], strict=False):
        if _version_key(newer[0]) <= _version_key(older[0]) or newer[1] < older[1]:
            raise DocumentControlError(
                f"its version history is not newest first ({newer[0]} above {older[0]})"
            )
    return Control(version, date, release, status, history)


def body_of(markdown: str) -> str:
    """Everything a reader reads except the version record: what a new version must change."""
    return _CONTROL.sub("", markdown, count=1)


def _plain(fragment: str) -> str:
    return html.unescape(_TAG.sub("", fragment)).strip()


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


@dataclass(frozen=True)
class Entry:
    level: int  # 2 or 3 for a heading, 0 for a figure
    anchor: str
    text: str


def _body_html(markdown: str) -> tuple[str, list[Entry], list[Entry]]:
    """The guide's own text as HTML without its title and version record, with an anchor on every
    section and a number on every figure, and the contents and figures that list them."""
    body = body_of(markdown)
    body = re.sub(r"\A# .*\n", "", body, count=1)  # the title is the cover's
    rendered = _GUIDE_LINK.sub(r"\2 (\1.pdf)", render_markdown(body))
    headings: list[Entry] = []
    figures: list[Entry] = []

    def heading(match: re.Match[str]) -> str:
        entry = Entry(int(match.group(1)), f"s{len(headings) + 1}", _plain(match.group(2)))
        headings.append(entry)
        return f'<h{entry.level} id="{entry.anchor}">{match.group(2)}</h{entry.level}>'

    def caption(match: re.Match[str]) -> str:
        entry = Entry(0, f"f{len(figures) + 1}", _plain(match.group(1)))
        figures.append(entry)
        number = len(figures)
        return f'<figcaption id="{entry.anchor}">Figure {number}. {match.group(1)}</figcaption>'

    rendered = _HEADING.sub(heading, rendered)
    rendered = _CAPTION.sub(caption, rendered)
    return rendered, headings, figures


def _audience(markdown: str) -> str:
    """The guide's opening paragraph — who it is for — for the cover."""
    paragraphs = re.split(r"\n\s*\n", re.sub(r"\A# .*\n", "", markdown, count=1).strip())
    return render_markdown(paragraphs[0]) if paragraphs else ""


def _leaders(entries: list[Entry], pages: dict[str, int] | None, figure: bool) -> str:
    items = []
    for number, entry in enumerate(entries, start=1):
        at = str(pages[entry.anchor]) if pages else _PLACEHOLDER
        words = html.escape(entry.text)
        if figure:
            words = f"Figure {number} — {words}"
        level = "" if figure else f' class="level-{entry.level}"'
        items.append(
            f'<li{level}><a href="#{entry.anchor}">{words}</a><span class="dots"></span>'
            f'<span class="at">{at}</span></li>'
        )
    return f'<ol class="leaders">{"".join(items)}</ol>'


def page(markdown: str, title: str, base: Path, pages: dict[str, int] | None = None) -> str:
    """The whole printable page for one guide: the cover, the document control, the contents and
    the figures (with `pages` once they are known, placeholders until then), then the guide.

    A link to another guide is printed as its words and the guide's file — never as a link, since
    the browser would print it as an absolute `file:///…` address naming the printing machine's home
    folder (the publish refused that)."""
    control = control_of(markdown)
    body, headings, figures = _body_html(markdown)
    product, _, name = title.partition(" — ")
    record = _CONTROL.search(markdown)
    assert record is not None  # control_of found it
    control_html = render_markdown(record.group(1))
    released = "not yet released" if control.release == "unreleased" else control.release
    cover = (
        '<section class="cover">'
        f'<p class="cover-product">{html.escape(product)}</p>'
        f'<h1 class="cover-title">{html.escape(name or title)}</h1>'
        f'<div class="cover-audience">{_audience(body_of(markdown))}</div>'
        '<dl class="cover-facts">'
        f"<dt>Version</dt><dd>{control.version}</dd>"
        f"<dt>Date</dt><dd>{control.date}</dd>"
        f"<dt>Describes</dt><dd>OspreyFlow {released}</dd>"
        f"<dt>Status</dt><dd>{control.status}</dd>"
        "</dl></section>"
    )
    front = (
        f'<section class="front">{control_html}</section>'
        '<section class="front"><h2>Contents</h2>'
        f"{_leaders(headings, pages, figure=False)}</section>"
        f'<section class="front"><h2>List of figures</h2>'
        f"{_leaders(figures, pages, figure=True)}</section>"
    )
    tokens = TOKENS.read_text(encoding="utf-8")
    return (
        '<!doctype html>\n<html lang="en-GB" data-theme="light"><head><meta charset="utf-8">'
        f'<base href="{base.as_uri()}/"><title>{html.escape(title)}</title>'
        f"<style>{tokens}\n{DOC_CSS}</style></head><body>{cover}{front}"
        f"<main>{body}</main></body></html>\n"
    )


def locate(page_texts: list[str], markdown: str) -> dict[str, int]:
    """The page (counting from 1) each section and figure of `markdown` landed on, read from the
    printed pages' text. The search starts after the list of figures, so the contents and the list
    themselves are never taken for the thing they name, and moves forward only: each entry is found
    on the page of the one before it or later."""
    _, headings, figures = _body_html(markdown)
    squashed = [_squash(text) for text in page_texts]
    # The page the list *begins* on: the words alone also occur elsewhere (the version history
    # said "a list of figures", and every heading was then found on the contents page).
    marker = _squash("List of figures")
    front = next((i for i, text in enumerate(squashed) if text.startswith(marker)), None)
    if front is None:
        raise DocumentControlError("the printed guide has no list of figures to start after")
    found: dict[str, int] = {}
    at = front + 1
    for entry in headings:
        at = _find(squashed, _squash(entry.text)[:60], at, entry.text)
        found[entry.anchor] = at + 1
    at = front + 1
    for number, entry in enumerate(figures, start=1):
        at = _find(squashed, _squash(f"Figure {number}. {entry.text}")[:60], at, entry.text)
        found[entry.anchor] = at + 1
    return found


def _find(squashed: list[str], needle: str, start: int, words: str) -> int:
    for index in range(start, len(squashed)):
        if needle in squashed[index]:
            return index
    raise DocumentControlError(f"{words!r} is on no page of the printed guide")


def _page_texts(pdf: Path) -> list[str]:
    from pypdf import PdfReader

    return [p.extract_text() or "" for p in PdfReader(str(pdf)).pages]


def _print(html_page: Path, pdf: Path, footer: str, chrome: Path | None) -> None:
    command = ["node", str(PRINTER), str(CORE), str(html_page), str(pdf), footer]
    if chrome is not None:
        command.append(str(chrome))
    subprocess.run(command, check=True, capture_output=True)


def find_chrome(given: str | None = None) -> Path | None:
    """The browser to print with: `--chrome`, else `OSPREY_CHROME`, else Playwright's own."""
    if given or os.environ.get("OSPREY_CHROME"):
        return Path(given or os.environ["OSPREY_CHROME"])
    return None


def _unversioned_changes(docs: Path, manifest: dict[str, dict[str, object]]) -> list[str]:
    problems = []
    for name, _title in GUIDES:
        source = docs / name
        if not source.exists():
            continue
        markdown = source.read_text(encoding="utf-8")
        try:
            control = control_of(markdown)
        except DocumentControlError:
            continue  # named by `check`
        made = manifest.get(name) or {}
        if made.get("version") == control.version and made.get("body") not in (
            None,
            _text_sha(body_of(markdown)),
        ):
            problems.append(
                f"{name} changed since version {control.version} without a new version: add a "
                "row to the top of its version history, and set its version and date to it"
            )
    return problems


def write(docs: Path = DOCS, chrome: Path | None = None) -> dict[str, dict[str, object]]:
    out = docs / "pdf"
    out.mkdir(exist_ok=True)
    listed = out / "manifest.json"
    previous = json.loads(listed.read_text(encoding="utf-8")) if listed.exists() else {}
    refused = _unversioned_changes(docs, previous)
    if refused:
        raise SystemExit("\n".join(refused))
    manifest: dict[str, dict[str, object]] = {}
    with tempfile.TemporaryDirectory() as scratch:
        for name, title in GUIDES:
            source = docs / name
            markdown = source.read_text(encoding="utf-8")
            control = control_of(markdown)
            footer = f"{title.partition(' — ')[2] or title} · version {control.version}"
            shell = Path(scratch) / f"{source.stem}.html"
            pdf = out / f"{source.stem}.pdf"
            pages: dict[str, int] | None = None
            for _attempt in range(4):
                shell.write_text(page(markdown, title, docs, pages), encoding="utf-8")
                _print(shell, pdf, footer, chrome)
                landed = locate(_page_texts(pdf), markdown)
                if landed == pages:
                    break
                pages = landed
            else:
                raise SystemExit(f"{name}: its page numbers did not settle in four printings")
            manifest[name] = {
                "source": _sha(source),
                "images": {image: _sha(docs / image) for image in images_of(markdown)},
                "pdf": _sha(pdf),
                "version": control.version,
                "body": _text_sha(body_of(markdown)),
            }
    listed.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def check(docs: Path = DOCS) -> list[str]:
    """Every way the PDFs are out of step with their sources, in words; empty when none is."""
    problems: list[str] = []
    listed = docs / "pdf" / "manifest.json"
    manifest = json.loads(listed.read_text(encoding="utf-8")) if listed.exists() else {}
    shown: set[str] = set()
    for name, _title in GUIDES:
        source = docs / name
        if not source.exists():
            problems.append(f"{name} is missing")
            continue
        markdown = source.read_text(encoding="utf-8")
        try:
            control_of(markdown)
        except DocumentControlError as wrong:
            problems.append(f"{name}: {wrong}")
        images = images_of(markdown)
        shown.update(images)
        for image in images:
            if not (docs / image).is_file():
                problems.append(f"{name} shows {image}, which is not there")
        made = manifest.get(name)
        pdf = docs / "pdf" / f"{source.stem}.pdf"
        rebuild = "run `python -m tools.docs_pdf --write`"
        if made is None or not pdf.exists():
            problems.append(f"{source.stem}.pdf has not been made from {name}: {rebuild}")
            continue
        if made["source"] != _sha(source):
            problems.append(f"{name} changed since {source.stem}.pdf was made: {rebuild}")
        if made["images"] != {i: _sha(docs / i) for i in images if (docs / i).is_file()}:
            problems.append(f"{name}'s images changed since {source.stem}.pdf was made: {rebuild}")
        if made["pdf"] != _sha(pdf):
            problems.append(f"{source.stem}.pdf is not the one made from {name}: {rebuild}")
        local = _LOCAL_ADDRESS.search(pdf.read_bytes())
        if local:
            where = local.group(1).decode(errors="replace") if local.group(1) else ""
            problems.append(f"{source.stem}.pdf carries a local address (file://{where}…)")
    problems.extend(_unversioned_changes(docs, manifest))
    for image in sorted((docs / "images").rglob("*.png")):
        relative = image.relative_to(docs).as_posix()
        if relative not in shown:
            problems.append(f"{relative} is in docs/images but no guide shows it")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.docs_pdf",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--write", action="store_true", help="make every PDF and the manifest")
    parser.add_argument("--chrome", help="the Chromium to print with (else Playwright's own)")
    args = parser.parse_args(argv)
    if args.write:
        write(chrome=find_chrome(args.chrome))
    problems = check()
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
