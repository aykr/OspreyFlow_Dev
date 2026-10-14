"""The bundle-time documentation site — `06_DECISIONS.md` ADR-049's Stage 2 §5b, its own
Proposed sub-item, 25 September 2026: "A site rendered from the Apache-scoped `docs/` tree at
bundle time... inclusion decided by the two existing gates already scoping that boundary... rather
than a third notion of what publishes."

**Inclusion, decided by data these two modules already own, not a hand-kept list — the design
call this build made, recorded here rather than left implicit.** The file set rendered is exactly
`tools.route_coverage_check.APACHE_DOC_PATHS` — the same tuple `product_tree_link_check.py`
itself imports rather than redeclaring, so this site can never drift from what that gate already
treats as the Apache-scoped boundary. `decision_log_publication_check.PROCESS_ADR_NUMBERS` is
imported and exercised by `assert_no_process_content` below as a **safety check on the render's
own output**, not as a second, larger content set — this site renders no ADR content from `06_
DECISIONS.md` at all (that file moved to `spec/` at Trigger A, round 14a, but stayed out of
`APACHE_DOC_PATHS` deliberately — `route_coverage_check.py`'s own note has why), so
`PROCESS_ADR_NUMBERS` is exercised defensively today, proven by its own test with a fabricated
would-be-rendered ADR fragment, not because the real site currently calls it with real ADR
content. `assert_no_private_tree_names` below checks the render's *output filenames* against
`process/`'s own real file stems, computed directly rather than restated, so Trigger A's own
marker simplification needed no change there.

**Three landing pages**, per the build brief: `index.html` (Architecture — a short cold-reader
orientation, then links into the rendered spec pack), `operator-guide.html` (`05_DEPLOYMENT.md`,
both RUNBOOKs, and the generated Preflight reference), `analyst-guide.html` (a placeholder stating
plainly that the analyst guide is not yet written, per `07_BUILD_PLAN.md` Stage 3c's own "Proposed,
post-milestone" — the honest thing to say, rather than writing one).

**The Preflight reference** is generated from `harness/preflight/*.py`'s own module docstrings and
`NAME` constants, read via `ast.parse` rather than `import` — deliberately: this keeps the whole
of `doc_site.py` free of any dependency beyond the Python standard library (no `pydantic`, no
`yaml`), which is what lets the Docker build stage that runs this module (`apps/workspace/
Dockerfile`'s own `docs` stage) use a bare `python:3.12-slim` with nothing installed into it.
Changing a check module's own docstring changes the generated reference page — the exit test this
site owes, proven in `tests/test_doc_site.py`.
"""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

from tools.decision_log_publication_check import PROCESS_ADR_NUMBERS
from tools.layout import REPO as REPO_ROOT
from tools.route_coverage_check import APACHE_DOC_PATHS
from tools.simple_markdown import render_markdown

PREFLIGHT_DIR = REPO_ROOT / "harness" / "preflight"
#: The install package's three guides (`06_DECISIONS.md` ADR-114 Amendment 15), each a page of this
#: site with the images it shows copied beside it. Their own Markdown is the source, as the PDFs'.
PACKAGE_DOCS = REPO_ROOT / "docs"
GUIDES: tuple[tuple[str, str], ...] = (
    ("administration-guide", "Installation and Administration Guide"),
    ("user-guide", "User Guide"),
    ("developer-guide", "Developer Guide"),
)
_GUIDE_LINK = re.compile(
    r'href="(?:docs/)?(?:pdf/)?(' + "|".join(g for g, _ in GUIDES) + r')\.(?:md|pdf)"'
)
_IMAGE_SOURCE = re.compile(r'<img src="([^"]+)"')
PROCESS_DIR = REPO_ROOT / "process"

_PAGE_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} — OspreyFlow documentation</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 60rem; margin: 2rem auto;
        padding: 0 1rem; color: #1a1a1a; line-height: 1.5; }}
nav {{ margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #ccc; }}
nav a {{ margin-right: 1rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }}
code {{ background: #f2f2f2; padding: 0.1rem 0.3rem; border-radius: 3px; }}
pre code {{ display: block; padding: 0.8rem; overflow-x: auto; }}
</style>
</head>
<body>
<nav><a href="index.html">Architecture</a> <a href="operator-guide.html">Operator guide</a>
<a href="analyst-guide.html">Analyst guide</a> <a href="developer-guide.html">Developer guide</a></nav>
{body}
</body>
</html>
"""


def _page(title: str, body_html: str) -> str:
    return _PAGE_SHELL.format(title=title, body=body_html)


def _spec_pack_pages() -> dict[str, str]:
    """`{html_filename: rendered_html}` for every Apache-scoped doc — the spec pack the
    Architecture landing page links into."""
    pages = {}
    for doc_path in APACHE_DOC_PATHS:
        html_name = doc_path.stem + ".html"
        body = render_markdown(doc_path.read_text(encoding="utf-8"))
        pages[html_name] = _page(doc_path.name, body)
    return pages


def _architecture_landing_page() -> str:
    links = "".join(
        f'<li><a href="{doc_path.stem}.html">{doc_path.name}</a></li>'
        for doc_path in APACHE_DOC_PATHS
    )
    body = (
        "<h1>OspreyFlow</h1>"
        "<p>Open-source intelligence analysis and network discovery platform. This site is "
        "generated from this deployment's own documentation at bundle time.</p>"
        "<h2>Start here</h2><ul><li><a href=\"administration-guide.html\">Installation and "
        "Administration Guide</a> — install, run, back up and update it.</li>"
        "<li><a href=\"user-guide.html\">User Guide</a> — for analysts, using the workspace day to "
        "day.</li><li><a href=\"developer-guide.html\">Developer Guide</a> — for data engineers, "
        "bringing data in.</li><li><a href=\"operator-guide.html\">Operator guide</a> — the "
        "deployment guide, the RUNBOOKs and the Preflight reference.</li></ul>"
        f"<h2>The full specification</h2><ul>{links}</ul>"
    )
    return _page("Architecture", body)


#: `06_DECISIONS.md` ADR-049 Stage 2 §6's own six named screens, in the order the harness's own
#: nav bar presents them (`apps/harness/src/store.ts`'s own `SCREEN_NAMES`) — kept as a literal
#: tuple here rather than imported, the same "no dependency beyond the standard library" constraint
#: `PREFLIGHT_DIR`'s own `ast.parse` reading already keeps for this module (importing
#: `apps/harness/src/store.ts` at all would need a JS/TS toolchain this bundle-time render never
#: has).
_SETUP_SCREENS: tuple[str, ...] = (
    "Profile",
    "Components",
    "Models",
    "Governance",
    "Geospatial",
    "Preflight",
)


def _operator_guide_landing_page(
    generated_runbook_present: bool, deploy_runbook_present: bool
) -> str:
    deployment_html = next(p.stem for p in APACHE_DOC_PATHS if p.name == "05_DEPLOYMENT.md")
    links = [
        '<li><a href="administration-guide.html">Installation and Administration Guide</a></li>',
        f'<li><a href="{deployment_html}.html">Deployment guide</a></li>',
    ]
    if generated_runbook_present:
        links.append('<li><a href="runbook-generated.html">This deployment\'s own RUNBOOK</a></li>')
    if deploy_runbook_present:
        links.append('<li><a href="runbook.html">Backup/restore RUNBOOK</a></li>')
    links.append('<li><a href="preflight-reference.html">Preflight reference</a></li>')
    screen_items = "".join(f"<li>{name}</li>" for name in _SETUP_SCREENS)
    body = (
        "<h1>Operator guide</h1>"
        "<h2>The setup harness's own path</h2>"
        "<p>One bootstrap command (the deployment guide's own §2) opens a browser application, "
        "not a wizard to read about — six screens, navigable in any order, a persistent summary "
        "rail showing what is decided and what is outstanding:</p>"
        f"<ol>{screen_items}</ol>"
        "<p>Then Launch, from the confirmed generated artefacts — the harness itself becomes the "
        "deployment's own <code>/admin</code> console afterwards, at the same port, not a page the "
        "workspace serves.</p>"
        "<ul>" + "".join(links) + "</ul>"
    )
    return _page("Operator guide", body)


def _analyst_guide_page() -> str:
    """The analyst's way in: the User Guide (`docs/user-guide.md`), and the demo walkthrough."""
    demo_guide_html = next(p.stem for p in APACHE_DOC_PATHS if p.name == "DEMO_GUIDE.md")
    body = (
        "<h1>Analyst guide</h1>"
        '<p>The analyst\'s guide is the <a href="user-guide.html">User Guide</a>: signing in, cases, '
        "the graph, map, timeline and reports, alerts and watches, and how what you see is "
        "decided.</p>"
        f'<p>For a followable walkthrough of the demo cases, see <a href="{demo_guide_html}.html">'
        "the demo guide</a>.</p>"
    )
    return _page("Analyst guide", body)


def _guide_pages() -> tuple[dict[str, str], set[str]]:
    """`{html_filename: rendered_html}` for each of the install package's guides, and the images
    they show (relative to `docs/`)."""
    pages: dict[str, str] = {}
    images: set[str] = set()
    for stem, title in GUIDES:
        body = render_markdown((PACKAGE_DOCS / f"{stem}.md").read_text(encoding="utf-8"))
        images.update(_IMAGE_SOURCE.findall(body))
        pages[f"{stem}.html"] = _page(title, body)
    return pages, images


def _preflight_reference_page() -> str:
    """Reads `harness/preflight/__init__.py`'s own `ALL_CHECKS` tuple, in source order, without
    importing it — a plain `ast.parse` of the assignment's tuple-of-Name elements — then reads
    each named module's own docstring and `NAME` constant the same way."""
    init_source = (PREFLIGHT_DIR / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(init_source)
    check_module_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "ALL_CHECKS" for t in node.targets
        ):
            if isinstance(node.value, ast.Tuple):
                check_module_names = [
                    elt.id for elt in node.value.elts if isinstance(elt, ast.Name)
                ]

    sections = []
    for module_name in check_module_names:
        module_path = PREFLIGHT_DIR / f"{module_name}.py"
        if not module_path.is_file():
            continue
        module_tree = ast.parse(module_path.read_text(encoding="utf-8"))
        docstring = ast.get_docstring(module_tree) or ""
        check_name = module_name
        for node in ast.walk(module_tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "NAME" for t in node.targets
            ):
                if isinstance(node.value, ast.Constant):
                    check_name = str(node.value.value)
        sections.append(
            f"<h2><code>{check_name}</code></h2>{render_markdown(docstring)}"
        )

    body = "<h1>Preflight reference</h1>" + "".join(sections)
    return _page("Preflight reference", body)


def assert_no_process_content(rendered_ids: list[str]) -> list[str]:
    """The defensive safety check this module's own docstring names: if the site is ever extended
    to render ADR-numbered content, every id passed here must not be in `PROCESS_ADR_NUMBERS`.
    Returns violations; empty today because the real render never calls this with real ADR ids."""
    return [rid for rid in rendered_ids if rid in PROCESS_ADR_NUMBERS]


def _private_tree_file_stems() -> frozenset[str]:
    """**Round 14a (Trigger A):** `PRIVATE_TREE_MARKERS` became `process/` as a directory prefix
    plus three root markers (`CLAUDE.md`, `.claude/`, `.graphifyignore`) — right for the link
    check it was built for (a citation carries path context), wrong for this function's own bare
    *rendered filename* check (`"07_BUILD_PLAN.html"` carries no `process/` prefix to match at
    all). Rather than hand-maintain a second, parallel list of individual private filenames that
    would silently drift from the real `process/` tree, this derives the stems directly from what
    is actually there — every real markdown file `process/` currently holds, plus `CLAUDE.md`'s
    own stem for the root stub's sake.

    **Deliberately `process/*.md` (top-level only), not `process/**/*.md`.** A recursive glob
    walks into `process/archive/`, `process/demo/`, `process/prototypes/`, and `process/upstream/`
    — folders that hold their own incidental `README.md`/`SESSION_HANDOVER.md`/`CLAUDE.md` files,
    never rendered or referenced by this module, whose stems are not unique across the repository
    and collide by pure coincidence with real, legitimately-rendered pages (`process/archive/
    README.md`'s stem colliding with the product's own root `README.md` is the case this module's
    own tests found). The files this check actually needs to catch — a numbered or named doc that
    used to live at `docs/`'s top level and could plausibly be reintroduced to `APACHE_DOC_PATHS`
    by mistake — all sit directly under `process/`, so the top-level glob is not a narrowing that
    loses coverage; it is the fix for the collision.
    """
    stems = {p.stem for p in PROCESS_DIR.glob("*.md")}
    stems.add("CLAUDE")
    return frozenset(stems)


def assert_no_private_tree_names(rendered_filenames: list[str]) -> list[str]:
    """The same file-identity check `scripts/packaging_gate.find_private_tree_files` applies to a
    whole artefact, scoped here to just the site's own rendered filenames.

    **Matched by stem, not by exact substring.** This site renders `.html`, not `.md` — a bare
    substring check the way `packaging_gate` uses for a real artefact's own untouched file list
    would never fire here, since `"07_BUILD_PLAN.md" not in "07_BUILD_PLAN.html"`. Found writing
    this module's own test, not assumed: `Path(name).stem` strips the rendered extension before
    comparing, so a marker's own `.md` suffix does not have to match this site's
    differently-suffixed output."""
    return [
        name
        for name in rendered_filenames
        if Path(name).stem in _private_tree_file_stems() or "archive" in name
    ]


def render_doc_site(
    output_dir: Path,
    *,
    generated_runbook_text: str | None = None,
    deploy_runbook_text: str | None = None,
) -> list[str]:
    """Writes the whole site to `output_dir` and returns the list of files written, relative to
    it — the site's own manifest, which `tests/test_doc_site.py` and the bundle's own exit test
    both check against `assert_no_private_tree_names`/`assert_no_process_content`."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pages: dict[str, str] = {}
    pages.update(_spec_pack_pages())
    pages["index.html"] = _architecture_landing_page()
    pages["operator-guide.html"] = _operator_guide_landing_page(
        generated_runbook_text is not None, deploy_runbook_text is not None
    )
    pages["analyst-guide.html"] = _analyst_guide_page()
    guides, images = _guide_pages()
    pages.update(guides)
    # A link to a guide's Markdown or PDF — the README's, or one guide's to another — is to its
    # page here.
    pages = {name: _GUIDE_LINK.sub(r'href="\1.html"', html) for name, html in pages.items()}
    pages["preflight-reference.html"] = _preflight_reference_page()
    if generated_runbook_text is not None:
        pages["runbook-generated.html"] = _page(
            "This deployment's own RUNBOOK", render_markdown(generated_runbook_text)
        )
    if deploy_runbook_text is not None:
        pages["runbook.html"] = _page(
            "Backup/restore RUNBOOK", render_markdown(deploy_runbook_text)
        )

    violations = assert_no_private_tree_names(list(pages))
    if violations:
        raise RuntimeError(f"doc_site: refusing to render private-tree file(s): {violations}")

    for filename, html in pages.items():
        (output_dir / filename).write_text(html, encoding="utf-8")
    for image in sorted(images):
        target = output_dir / image
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PACKAGE_DOCS / image, target)
    return sorted(pages) + sorted(images)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m tools.doc_site")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    generated_runbook_path = REPO_ROOT / "deploy" / "generated" / "local-lite" / "RUNBOOK.md"
    deploy_runbook_path = REPO_ROOT / "deploy" / "RUNBOOK.md"
    written = render_doc_site(
        args.out,
        generated_runbook_text=(
            generated_runbook_path.read_text(encoding="utf-8")
            if generated_runbook_path.is_file()
            else None
        ),
        deploy_runbook_text=(
            deploy_runbook_path.read_text(encoding="utf-8")
            if deploy_runbook_path.is_file()
            else None
        ),
    )
    print(f"doc_site: wrote {len(written)} page(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
