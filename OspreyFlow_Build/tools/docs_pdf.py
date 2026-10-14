"""The install package's guides as PDFs (`06_DECISIONS.md` ADR-114 Amendment 15 point 2): the
Markdown in Core's `docs/` is the source; each guide is rendered by `tools.simple_markdown` into a
page styled from the design tokens (`apps/workspace/src/design/tokens.css`, light theme — no colour
of its own), printed to `docs/pdf/<guide>.pdf` by a headless Chromium, and recorded in
`docs/pdf/manifest.json` with the SHA-256 of its Markdown, of every image it shows, and of the PDF
made from them.

`check()` recomputes those and names each guide that is out of step — its Markdown or an image
changed since its PDF was made, its PDF replaced or missing — and every image a guide shows that is
not there, and every screenshot in `docs/images/` no guide shows. `tests/test_docs_pdf.py` runs it,
so a guide changed without its PDF being made again fails the build. Printing needs a browser and
so is a person's step, never CI's:

    python -m tools.docs_pdf --write [--chrome PATH]   # make every PDF and the manifest
    python -m tools.docs_pdf                           # check only (what the test does)

The browser is `--chrome`, else `OSPREY_CHROME`, else the newest headless Chromium in Playwright's
own cache (`npx playwright install chromium-headless-shell` puts one there). A PDF's own bytes
differ from one printing to the next (the browser stamps the time in it), which is why the manifest
records the PDF's hash rather than expecting a reproducible one. The tokens' fonts are named first;
where they are not installed the system's own sans-serif and monospace are used.
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
from pathlib import Path

from tools.layout import CORE
from tools.simple_markdown import render_markdown

DOCS = CORE / "docs"
TOKENS = CORE / "apps" / "workspace" / "src" / "design" / "tokens.css"
#: Each guide, in the order its reader meets them.
GUIDES: tuple[tuple[str, str], ...] = (
    ("administration-guide.md", "OspreyFlow — Installation and Administration Guide"),
    ("user-guide.md", "OspreyFlow — User Guide"),
    ("developer-guide.md", "OspreyFlow — Developer Guide"),
)
_IMAGE = re.compile(r"^!\[[^\]]*\]\(([^)\s]+)\)\s*$", re.MULTILINE)
_GUIDE_LINK = re.compile(r'<a href="([a-z0-9-]+)\.md(?:#[^"]*)?">([^<]*)</a>')
#: A local address in a printed PDF — the printing machine's own folders.
_LOCAL_ADDRESS = re.compile(rb"file://(/[^/\s)]+/[^/\s)]+/)?")

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
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def images_of(markdown: str) -> list[str]:
    """The images a guide shows, as written (relative to `docs/`)."""
    return _IMAGE.findall(markdown)


def page(markdown: str, title: str, base: Path) -> str:
    """The whole printable page for one guide. A link to another guide is printed as its words and
    the guide's file — never as a link, since the browser would print it as an absolute
    `file:///…` address naming the printing machine's home folder (the publish refused that)."""
    body = render_markdown(markdown)
    body = _GUIDE_LINK.sub(r"\2 (\1.pdf)", body)
    tokens = TOKENS.read_text(encoding="utf-8")
    return (
        '<!doctype html>\n<html lang="en-GB" data-theme="light"><head><meta charset="utf-8">'
        f'<base href="{base.as_uri()}/"><title>{html.escape(title)}</title>'
        f"<style>{tokens}\n{DOC_CSS}</style></head><body><main>{body}</main></body></html>\n"
    )


def find_chrome(given: str | None = None) -> Path:
    if given or os.environ.get("OSPREY_CHROME"):
        return Path(given or os.environ["OSPREY_CHROME"])
    caches = [Path.home() / "Library" / "Caches" / "ms-playwright", Path.home() / ".cache" / "ms-playwright"]
    names = ("chrome-headless-shell", "headless_shell")
    found = sorted(
        (p for cache in caches if cache.is_dir() for p in cache.rglob("*") if p.name in names
         and p.is_file() and os.access(p, os.X_OK)),
        key=lambda p: str(p),
    )  # fmt: skip
    if not found:
        raise SystemExit(
            "No headless Chromium found: pass --chrome, set OSPREY_CHROME, or run "
            "`npx playwright install chromium-headless-shell`."
        )
    return found[-1]


def write(docs: Path = DOCS, chrome: Path | None = None) -> dict[str, dict[str, object]]:
    browser = chrome or find_chrome()
    out = docs / "pdf"
    out.mkdir(exist_ok=True)
    manifest: dict[str, dict[str, object]] = {}
    with tempfile.TemporaryDirectory() as scratch:
        for name, title in GUIDES:
            source = docs / name
            markdown = source.read_text(encoding="utf-8")
            shell = Path(scratch) / f"{source.stem}.html"
            shell.write_text(page(markdown, title, docs), encoding="utf-8")
            pdf = out / f"{source.stem}.pdf"
            subprocess.run(
                [str(browser), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                 "--allow-file-access-from-files", f"--print-to-pdf={pdf}", shell.as_uri()],
                check=True, capture_output=True,
            )  # fmt: skip
            manifest[name] = {
                "source": _sha(source),
                "images": {image: _sha(docs / image) for image in images_of(markdown)},
                "pdf": _sha(pdf),
            }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8")  # fmt: skip
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
    for image in sorted((docs / "images").rglob("*.png")):
        relative = image.relative_to(docs).as_posix()
        if relative not in shown:
            problems.append(f"{relative} is in docs/images but no guide shows it")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.docs_pdf", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    parser.add_argument("--write", action="store_true", help="make every PDF and the manifest")
    parser.add_argument("--chrome", help="the headless Chromium to print with")
    args = parser.parse_args(argv)
    if args.write:
        write(chrome=find_chrome(args.chrome))
    problems = check()
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
