"""`06_DECISIONS.md` ADR-049's Stage 2 §5b, the documentation-site Proposed sub-item — built
against `tools/doc_site.py`. Exit tests, each a planted violation: "no file the two gates
classify private is rendered — plant one, the build goes red; every internal link on the site
resolves — plant a broken one, the build goes red; the Preflight reference page is generated from
`harness/preflight/*`'s own check strings, not hand-copied — change one of those strings, the
generated page changes with it."
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools import doc_site
from tools.layout import REPO as REPO_ROOT
from tools.route_coverage_check import APACHE_DOC_PATHS


@pytest.fixture
def site(tmp_path: Path) -> Path:
    out = tmp_path / "site"
    doc_site.render_doc_site(out)
    return out


def test_renders_every_apache_scoped_doc_and_nothing_else_by_hand(site: Path) -> None:
    """Inclusion is `APACHE_DOC_PATHS` itself, not a second, hand-kept list — every one of the ten
    real Apache-scoped docs gets its own page."""
    for doc_path in APACHE_DOC_PATHS:
        assert (site / f"{doc_path.stem}.html").is_file()


def test_the_three_landing_pages_exist(site: Path) -> None:
    assert (site / "index.html").is_file()
    assert (site / "operator-guide.html").is_file()
    assert (site / "analyst-guide.html").is_file()


def test_the_analyst_guide_is_a_placeholder_not_a_written_guide(site: Path) -> None:
    """07_BUILD_PLAN.md Stage 3c: the analyst guide is Proposed, post-milestone — this page must
    say so plainly rather than pretend to be the guide itself."""
    text = (site / "analyst-guide.html").read_text(encoding="utf-8")
    assert "not yet written" in text


# --- "no file the two gates classify private is rendered — plant one, the build goes red" -------


def test_a_private_tree_filename_in_the_render_output_fails_the_build() -> None:
    """`07_BUILD_PLAN.md`, not `06_DECISIONS.md` — round 14a (Trigger A) moved the ADR log to
    `spec/` (product), so it is the one numbered file no longer private; `07_BUILD_PLAN.md` moved
    to `process/` and is now the example."""
    violations = doc_site.assert_no_private_tree_names(["07_BUILD_PLAN.html", "index.html"])
    assert violations == ["07_BUILD_PLAN.html"]


def test_render_doc_site_itself_refuses_if_a_private_page_were_ever_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plants the violation the real render path would produce if `APACHE_DOC_PATHS` were ever
    (wrongly) extended to include a private-tree file, proving `render_doc_site` itself checks its
    own output rather than only exposing a checker function nothing calls."""

    poisoned = (*APACHE_DOC_PATHS, REPO_ROOT / "process" / "07_BUILD_PLAN.md")
    monkeypatch.setattr(doc_site, "APACHE_DOC_PATHS", poisoned)

    with pytest.raises(RuntimeError, match="private-tree"):
        doc_site.render_doc_site(tmp_path / "site")


def test_a_process_classified_id_is_flagged_by_the_defensive_check() -> None:
    """The safety mechanism named in this module's own docstring: if the site is ever extended to
    render ADR content by number, a PROCESS-classified id must never pass. Real ADR content is not
    rendered today (`06_DECISIONS.md` moved to `spec/` at Trigger A, round 14a, but was
    deliberately kept out of `APACHE_DOC_PATHS`) — this proves the mechanism itself works against a
    fabricated id list, honestly disclosed as not yet wired to a real caller."""
    from tools.decision_log_publication_check import PROCESS_ADR_NUMBERS

    a_process_adr = next(iter(PROCESS_ADR_NUMBERS))
    violations = doc_site.assert_no_process_content(["001", a_process_adr, "003"])
    assert violations == [a_process_adr]


# --- "every internal link on the site resolves — plant a broken one, the build goes red" --------


_HREF_PATTERN = re.compile(r'href="([^"]+)"')


def _internal_links(html: str) -> list[str]:
    return [href for href in _HREF_PATTERN.findall(html) if not href.startswith(("http://", "https://"))]


def test_every_internal_link_on_the_real_site_resolves(site: Path) -> None:
    written = {p.name for p in site.iterdir()}
    for page in site.iterdir():
        for href in _internal_links(page.read_text(encoding="utf-8")):
            assert href in written, f"{page.name} links to {href!r}, which was never rendered"


def test_a_broken_internal_link_fails_this_same_check(site: Path) -> None:
    """The planted violation, the real shape: hand-edit a rendered page to link to a file that
    was never written, and confirm the check above catches it — proof it is not vacuous."""
    (site / "index.html").write_text('<a href="does-not-exist.html">gone</a>', encoding="utf-8")
    written = {p.name for p in site.iterdir()}

    broken = [
        href
        for href in _internal_links((site / "index.html").read_text(encoding="utf-8"))
        if href not in written
    ]
    assert broken == ["does-not-exist.html"]


# --- "the Preflight reference page is generated from harness/preflight/*'s own check strings" ----


def test_the_preflight_reference_names_every_registered_check(site: Path) -> None:
    text = (site / "preflight-reference.html").read_text(encoding="utf-8")
    for name in ("memory", "disk", "gpu", "ports", "oidc-audience"):
        assert f"<code>{name}</code>" in text


def test_changing_a_preflight_checks_own_docstring_changes_the_generated_page(
    tmp_path: Path,
) -> None:
    """The exit test named directly: edit one check module's own string, the generated reference
    changes with it — proving the page is generated from the real source, not hand-copied prose
    that could silently drift."""
    fixture_preflight_dir = tmp_path / "preflight"
    fixture_preflight_dir.mkdir()
    (fixture_preflight_dir / "__init__.py").write_text(
        "from harness.preflight import memory_fixture\nALL_CHECKS = (memory_fixture,)\n"
    )
    (fixture_preflight_dir / "memory_fixture.py").write_text(
        '"""Original docstring text."""\nNAME = "memory-fixture"\n'
    )

    import importlib

    original_dir = doc_site.PREFLIGHT_DIR
    doc_site.PREFLIGHT_DIR = fixture_preflight_dir
    try:
        before = doc_site._preflight_reference_page()
        (fixture_preflight_dir / "memory_fixture.py").write_text(
            '"""Changed docstring text."""\nNAME = "memory-fixture"\n'
        )
        after = doc_site._preflight_reference_page()
    finally:
        doc_site.PREFLIGHT_DIR = original_dir
        importlib.invalidate_caches()

    assert "Original docstring text" in before
    assert "Changed docstring text" in after
    assert before != after
