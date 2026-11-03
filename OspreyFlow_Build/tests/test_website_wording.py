"""The marketing site's wording on the GDS Service Standard (build order step 12; the owner, 1 November 2026).

The owner's rule: the site says OspreyFlow is "designed to meet the GDS Service Standard", never that it is
GDS-compliant, compliant with the Standard, certified, accredited or assessed, and it lists the independent
accessibility audit, the penetration test and the DPIA as planned. Only a service assessment panel decides
whether a service meets the Standard (`process/gds/gds_compliance_report.md` §8).

Every page in `marketing_site/deploy/` is read. `index.html` and `intro-video.html` are bundles exported
from a design tool: their visible text lives in a JSON-encoded `<script type="__bundler/template">` block,
so the template is decoded before it is read; a check of the raw file alone would read `\\"` and `\\n`
escapes, and a phrase written across one of them would pass.

Rules 12 and 15: each check has a case below that plants a violation in the shape the page really carries
(plain HTML for a hand-written page, a re-encoded template for a bundle) and asserts the check reports it.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "marketing_site" / "deploy"

TEMPLATE_OPEN = '<script type="__bundler/template">'

# Anywhere on a page.
FORBIDDEN_PHRASES = re.compile(
    r"GDS[\s\-‐‑]+compliant|compliant\s+with\s+the\s+GDS|GDS[\s\-]+compliance",
    re.IGNORECASE,
)
# Near "GDS" or "Service Standard": a claim of a status only an assessment panel can give.
STATUS_WORDS = re.compile(r"\b(certified|certification|accredited|compliant|compliance|assessed)\b", re.IGNORECASE)
STANDARD = re.compile(r"\bGDS\b|Service\s+Standard", re.IGNORECASE)
NEAR = 200

# A page that names the Service Standard lists each check as planned, close to its own name.
CHECKS = {
    "accessibility audit": re.compile(r"accessibility\s+audit", re.IGNORECASE),
    "penetration test": re.compile(r"penetration\s+test", re.IGNORECASE),
    "DPIA": re.compile(r"\bDPIA\b|data\s+protection\s+impact\s+assessment", re.IGNORECASE),
}
PLANNED = re.compile(r"\bplanned\b", re.IGNORECASE)
PLANNED_NEAR = 250


def _encode_template(text: str) -> str:
    """The export's own encoding: JSON, non-ASCII kept, `</` written `<\\u002F`. Reproduces it byte for byte."""
    return json.dumps(text, ensure_ascii=False).replace("</", "<\\u002F")


def _template_span(source: str) -> tuple[int, int] | None:
    start = source.find(TEMPLATE_OPEN)
    if start < 0:
        return None
    start += len(TEMPLATE_OPEN)
    return start, source.index("</script>", start)


def page_text(path: Path) -> str:
    """What a reader can see: the decoded template for a bundle, the page itself otherwise, tags removed."""
    source = path.read_text(encoding="utf-8")
    span = _template_span(source)
    if span is not None:
        source = json.loads(source[span[0] : span[1]])
    source = re.sub(r"<style\b.*?</style>", " ", source, flags=re.DOTALL | re.IGNORECASE)
    # Words a reader meets outside the page's body text: alt text, titles, spoken names, the meta description.
    attributes = re.findall(r'\b(?:alt|title|aria-label|content)="([^"]*)"', source, flags=re.IGNORECASE)
    text = html.unescape(re.sub(r"<[^>]+>", " ", source) + " " + " ".join(attributes))
    return re.sub(r"\s+", " ", text)


def wording_violations(text: str) -> list[str]:
    found = [f"forbidden phrase {m.group(0)!r}" for m in FORBIDDEN_PHRASES.finditer(text)]
    anchors = [m.start() for m in STANDARD.finditer(text)]
    for m in STATUS_WORDS.finditer(text):
        if any(abs(m.start() - a) <= NEAR for a in anchors):
            found.append(f"{m.group(0)!r} near the Standard: …{text[max(0, m.start() - 60) : m.end() + 60]}…")
    return found


def missing_planned_checks(text: str) -> list[str]:
    if not re.search(r"Service\s+Standard", text, re.IGNORECASE):
        return []
    planned = [m.start() for m in PLANNED.finditer(text)]
    missing = []
    for name, pattern in CHECKS.items():
        if not any(abs(m.start() - p) <= PLANNED_NEAR for m in pattern.finditer(text) for p in planned):
            missing.append(name)
    return missing


def site_pages(folder: Path = DEPLOY) -> list[Path]:
    return sorted(folder.glob("*.html"))


def test_the_site_has_its_pages() -> None:
    """Guards the checks below against reading nothing: a moved folder would otherwise pass them all."""
    names = {p.name for p in site_pages()}
    assert {"index.html", "intro-video.html", "public-sector.html", "monitoring.html"} <= names


def test_the_bundles_template_is_decoded_and_read() -> None:
    """The index's visible words come out of the template, not out of its escaped JSON."""
    text = page_text(DEPLOY / "index.html")
    assert "designed to meet the GDS Service Standard" in text
    assert "Get started" in text


@pytest.mark.parametrize("page", site_pages(), ids=lambda p: p.name)
def test_no_page_claims_a_status_only_an_assessment_panel_gives(page: Path) -> None:
    assert wording_violations(page_text(page)) == []


@pytest.mark.parametrize("page", site_pages(), ids=lambda p: p.name)
def test_a_page_naming_the_service_standard_lists_the_three_checks_as_planned(page: Path) -> None:
    assert missing_planned_checks(page_text(page)) == []


def test_the_public_sector_page_names_the_standard_and_the_planned_checks() -> None:
    """The page the owner asked for says it; the parametrised check above would pass a page that never names it."""
    text = page_text(DEPLOY / "public-sector.html")
    assert "designed to meet the GDS Service Standard" in text
    assert "for every UK department" in text


# Red-then-green: each check fails for a violation in the shape a real page carries.


@pytest.fixture()
def site_copy(tmp_path: Path) -> Path:
    folder = tmp_path / "deploy"
    folder.mkdir()
    for page in site_pages():
        shutil.copy(page, folder / page.name)
    return folder


def _plant_in_template(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    start, end = _template_span(source)
    raw = source[start:end]
    lead, trail = raw[: len(raw) - len(raw.lstrip())], raw[len(raw.rstrip()) :]
    template = json.loads(raw)
    assert lead + _encode_template(template) + trail == raw
    assert template.count(old) == 1
    path.write_text(source[:start] + lead + _encode_template(template.replace(old, new)) + trail + source[end:], encoding="utf-8")


def test_the_check_flags_gds_compliant_on_a_hand_written_page(site_copy: Path) -> None:
    page = site_copy / "public-sector.html"
    page.write_text(page.read_text(encoding="utf-8").replace("designed to meet the GDS Service Standard", "GDS-compliant", 1), encoding="utf-8")
    assert any("GDS-compliant" in v for v in wording_violations(page_text(page)))


def test_the_check_flags_a_phrase_inside_the_bundles_encoded_template(site_copy: Path) -> None:
    """Written across a line break, the phrase is `GDS-\\ncompliant` in the export: invisible to the raw file."""
    page = site_copy / "index.html"
    _plant_in_template(page, "designed to meet the GDS Service Standard", "GDS-\ncompliant with the Service Standard")
    assert not FORBIDDEN_PHRASES.search(page.read_text(encoding="utf-8"))
    assert any("GDS-" in v for v in wording_violations(page_text(page)))


def test_the_check_flags_certified_inside_the_bundles_template(site_copy: Path) -> None:
    page = site_copy / "index.html"
    _plant_in_template(page, "designed to meet the GDS Service Standard", "certified against the GDS Service Standard")
    assert any("certified" in v for v in wording_violations(page_text(page)))


def test_the_check_flags_compliant_with_the_gds_and_assessed(site_copy: Path) -> None:
    assert wording_violations("OspreyFlow is compliant with the GDS Service Standard.")
    assert wording_violations("OspreyFlow has been assessed against the Service Standard.")
    assert not wording_violations("OspreyFlow is designed to meet the GDS Service Standard; only a service assessment panel decides.")


def test_the_check_flags_a_check_no_longer_listed_as_planned(site_copy: Path) -> None:
    page = site_copy / "public-sector.html"
    text = page_text(page)
    assert missing_planned_checks(text) == []
    stripped = re.sub(r"\bplanned\b", "done", text, flags=re.IGNORECASE)
    assert set(missing_planned_checks(stripped)) == set(CHECKS)


def test_the_check_flags_a_check_missing_from_the_bundle(site_copy: Path) -> None:
    page = site_copy / "index.html"
    _plant_in_template(page, "An independent accessibility audit, a penetration test and a DPIA are planned.", "")
    assert set(missing_planned_checks(page_text(page))) == set(CHECKS)


# The product's home (ADR-114 Amendment 31, which withdrew Amendment 30's move to `Solirius/ospreyflow`):
# the site points at `aykr/OspreyFlow`, and says what the product is in the owner's words (ADR-034 Amendment 1).

PRODUCT_REPOSITORY = "https://github.com/aykr/OspreyFlow"
STATEMENT = (
    "OspreyFlow is an open source intelligence mapping, anti-money-laundering and fraud detection platform, "
    "developed by Solirius Reply and released under the Apache License 2.0."
)
GITHUB_REPOSITORY = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def repository_addresses(path: Path) -> set[str]:
    """Every GitHub repository address on a page: in its decoded template (the `repoUrl` setting's default
    and the script's fallback, which the template carries HTML-escaped and JSON-encoded) and in the page."""
    source = path.read_text(encoding="utf-8")
    span = _template_span(source)
    decoded = html.unescape(json.loads(source[span[0] : span[1]])) if span is not None else ""
    return {m.group(0) for m in GITHUB_REPOSITORY.finditer(html.unescape(source) + "\n" + decoded)}


@pytest.mark.parametrize("page", site_pages(), ids=lambda p: p.name)
def test_every_repository_address_on_the_site_is_the_products_home(page: Path) -> None:
    assert repository_addresses(page) <= {PRODUCT_REPOSITORY}


def test_the_home_page_links_to_the_products_home() -> None:
    """Guards the check above against reading nothing: the home page's `repoUrl` is the one address."""
    assert repository_addresses(DEPLOY / "index.html") == {PRODUCT_REPOSITORY}


def test_the_home_page_gives_the_products_statement() -> None:
    assert STATEMENT in page_text(DEPLOY / "index.html")


def test_the_address_check_flags_the_withdrawn_home_inside_the_bundles_template(site_copy: Path) -> None:
    page = site_copy / "index.html"
    _plant_in_template(page, 'const repoUrl = this.props.repoUrl ?? "https://github.com/aykr/OspreyFlow"',
                       'const repoUrl = this.props.repoUrl ?? "https://github.com/Solirius/ospreyflow"')  # fmt: skip
    assert "https://github.com/Solirius/ospreyflow" in repository_addresses(page)


def test_the_statement_check_flags_a_home_page_without_it(site_copy: Path) -> None:
    page = site_copy / "index.html"
    _plant_in_template(page, STATEMENT, "OspreyFlow is a platform.")
    assert STATEMENT not in page_text(page)
