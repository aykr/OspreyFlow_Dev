"""The two new websites, ospreyflow.org and ospreyflow.net (`marketing_site/sites/`), held to the current site's rules
and the owner's decisions of 12 November 2026. Every check has a case that plants a violation in the shape
`build.py` writes it, and asserts the check reports it (rule 15).

- the product's statement on every page, and "Solirius Reply";
- "designed to meet the GDS Service Standard", never a status only an assessment panel gives, and the three checks
  named as planned wherever the Standard is (the current site's own checks, `test_website_wording`);
- no client named (by hash: `client_hashes.py`), no competitor named, i2 not until its ADR is accepted, and
  Laurium not named (the owner's decision 4);
- no local path, no credential, no placeholder left, and only the one address the owner gave (decision 2);
- no script and no request outside the site; every internal link and anchor resolves, across the two sites too;
- the committed pages are `build.py`'s output, byte for byte.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.test_website_wording import (
    PRODUCT_REPOSITORY,
    STATEMENT,
    missing_planned_checks,
    page_text,
    repository_addresses,
    wording_violations,
)

MARKETING = Path(__file__).resolve().parents[1] / "marketing_site"
SITES = MARKETING / "sites"
sys.path.insert(0, str(MARKETING))
import client_hashes  # noqa: E402

DOMAINS = {"org": "ospreyflow.org", "net": "ospreyflow.net"}
PAGES = {
    "org": {"index", "features", "public-sector", "get-started", "team", "contribute", "governance"},
    "net": {"index", "sectors", "public-sector", "services", "contact"},
}

#: Public names, so held in plain text. i2 is named only once an ADR deciding it is accepted (the owner, 7 November
#: 2026); none is.
COMPETITORS = re.compile(
    r"\bi2\b|analyst['’]?s\s+notebook|\bpalantir\b|\bquantexa\b|\blinkurious\b|\bmaltego\b", re.IGNORECASE
)
#: The owner's decision 4 (12 November 2026): neither site names Laurium.
LAURIUM = re.compile(r"laurium", re.IGNORECASE)
LOCAL_PATH = re.compile(r"/Users/|/home/|[A-Za-z]:\\\\?Users|file://", re.IGNORECASE)
CREDENTIAL = re.compile(
    r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|\bgh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|\bsk-[A-Za-z0-9_-]{20,}|\bxox[abpr]-[A-Za-z0-9-]{10,}|\b(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S",
    re.IGNORECASE,
)
#: The owner's decision 2 (12 November 2026, as changed that evening): the one address the sites give, the
#: organisation's shared mailbox, for enquiries on .net and security reports on .org.
ADDRESSES = {"servicecentre@solirius.com"}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PLACEHOLDER = re.compile(r'class="fill"|\bto (?:be )?add(?:ed)?\b', re.IGNORECASE)
#: Planted in the client check's cases: synthetic, its hash the first line of `client_names.sha256`.
SYNTHETIC_CLIENT = "Example Shire Constabulary"


def pages(root: Path = SITES) -> list[Path]:
    return sorted(p for site in DOMAINS for p in (root / site).glob("*.html"))


def _id(page: Path) -> str:
    return f"{page.parent.name}/{page.name}"


@pytest.fixture
def sites(tmp_path: Path) -> Path:
    copy = tmp_path / "sites"
    for site in DOMAINS:
        shutil.copytree(SITES / site, copy / site)
    return copy


def _plant(page: Path, html_fragment: str) -> None:
    """Into the page's main content, where build.py writes every section."""
    text = page.read_text(encoding="utf-8")
    assert "</main>" in text
    page.write_text(text.replace("</main>", html_fragment + "</main>", 1), encoding="utf-8")


# ---------------------------------------------------------------- the checks, each a function of one site folder


def statement_missing(root: Path) -> list[str]:
    return [_id(p) for p in pages(root) if STATEMENT not in page_text(p) or "Solirius Reply" not in page_text(p)]


def standard_wording(root: Path) -> list[str]:
    found = [f"{_id(p)}: {v}" for p in pages(root) for v in wording_violations(page_text(p))]
    found += [f"{_id(p)}: {c} not planned" for p in pages(root) for c in missing_planned_checks(page_text(p))]
    for site in DOMAINS:
        text = page_text(root / site / "public-sector.html")
        if "designed to meet the GDS Service Standard" not in text:
            found.append(f"{site}/public-sector.html: no 'designed to meet the GDS Service Standard'")
    return found


def names(root: Path, pattern: re.Pattern[str]) -> list[str]:
    return [f"{_id(p)}: {m.group(0)!r}" for p in pages(root) for m in pattern.finditer(page_text(p))]


def clients(root: Path) -> list[str]:
    """Each page carrying a name in `client_names.sha256`, by its hash alone, so a failure names no client."""
    held = client_hashes.known()
    return [f"{_id(p)}: {h[:12]}…" for p in pages(root) for h in sorted(client_hashes.named(page_text(p), held))]


def in_source(root: Path, pattern: re.Pattern[str]) -> list[str]:
    """In the page's whole source, attributes and addresses included, not only its visible text."""
    return [f"{_id(p)}: {m.group(0)!r}" for p in pages(root) for m in pattern.finditer(p.read_text(encoding="utf-8"))]


def other_addresses(root: Path) -> list[str]:
    return [f"{_id(p)}: {a}" for p in pages(root)
            for a in EMAIL.findall(html.unescape(p.read_text(encoding="utf-8"))) if a not in ADDRESSES]  # fmt: skip


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[tuple[str, str, str]] = []  # (tag, attribute, value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value:
                self.ids.add(value)
            if name in ("href", "src") and value is not None:
                self.links.append((tag, name, value))


def _parse(page: Path) -> _Links:
    parser = _Links()
    parser.feed(page.read_text(encoding="utf-8"))
    return parser


def requests_outside(root: Path) -> list[str]:
    """No script, and nothing the browser fetches by itself (a style sheet, an image, a font) from elsewhere."""
    found = [f"{_id(p)}: <script>" for p in pages(root) if "<script" in p.read_text(encoding="utf-8").lower()]
    for p in pages(root):
        for tag, attribute, value in _parse(p).links:
            if tag != "a" and urlsplit(value).scheme:
                found.append(f"{_id(p)}: <{tag} {attribute}={value!r}>")
    for site in DOMAINS:
        css = (root / site / "assets" / "site.css").read_text(encoding="utf-8")
        found += [f"{site}/assets/site.css: {m}" for m in re.findall(r"url\(\s*['\"]?(?:https?:)?//[^)]*\)|@import", css)]
    return found


def broken_links(root: Path) -> list[str]:
    """Every link within a site or to the other one resolves to a file, and every `#anchor` to an id in it."""
    found = []
    ids = {p: _parse(p).ids for p in pages(root)}
    for page in pages(root):
        for tag, _, value in _parse(page).links:
            parts = urlsplit(value)
            if parts.scheme in ("mailto",):
                continue
            if parts.scheme or parts.netloc:
                host = parts.netloc.removeprefix("www.")
                site = next((s for s, d in DOMAINS.items() if d == host), None)
                if site is None:
                    continue  # the product's repository, held by its own check
                target = root / site / (parts.path.lstrip("/") or "index.html")
            else:
                target = (page.parent / parts.path).resolve() if parts.path else page
            if not target.is_file():
                found.append(f"{_id(page)}: <{tag}> {value!r} reaches no file")
            elif parts.fragment and parts.fragment not in ids.get(target, _parse(target).ids if target.suffix == ".html" else set()):
                found.append(f"{_id(page)}: {value!r} reaches no id")
    return found


def installs_without_a_mode(root: Path) -> list[str]:
    """Every `ospreyflow install` a page shows names its mode: without `--mode` the install refuses, "Say which mode to
    install" (`cli/ospreyflow/main.py`). The draft's public-sector command left it out."""
    return [f"{_id(p)}: {html.unescape(m.group(0))!r}" for p in pages(root)
            for m in re.finditer(r"ospreyflow install\b[^<\n]*", p.read_text(encoding="utf-8"))
            if "--mode" not in m.group(0)]  # fmt: skip


def foreign_repositories(root: Path) -> list[str]:
    """Every repository address the product's own: `git clone`'s `.git` form is the same address."""
    return [f"{_id(p)}: {a}" for p in pages(root) for a in repository_addresses(p)
            if a.removesuffix(".git") != PRODUCT_REPOSITORY]  # fmt: skip


CHECKS = {
    "statement": statement_missing,
    "standard": standard_wording,
    "competitor": lambda root: names(root, COMPETITORS),
    "laurium": lambda root: names(root, LAURIUM) + in_source(root, LAURIUM),
    "client": clients,
    "local path": lambda root: in_source(root, LOCAL_PATH),
    "credential": lambda root: in_source(root, CREDENTIAL),
    "placeholder": lambda root: in_source(root, PLACEHOLDER),
    "address": other_addresses,
    "request outside": requests_outside,
    "broken link": broken_links,
    "repository": foreign_repositories,
    "install without a mode": installs_without_a_mode,
}


# ---------------------------------------------------------------- the sites as committed


def test_each_site_has_its_pages() -> None:
    for site, expected in PAGES.items():
        assert {p.stem for p in (SITES / site).glob("*.html")} == expected


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_the_sites_pass(check: str) -> None:
    assert CHECKS[check](SITES) == []


def test_the_pages_are_build_pys_output(tmp_path: Path) -> None:
    """Rebuilt into a temporary folder: every page and style sheet byte for byte, and every image it shows held."""
    run = subprocess.run([sys.executable, str(SITES / "build.py"), "--out", str(tmp_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    for site in DOMAINS:
        built = sorted(p.relative_to(tmp_path / site) for p in (tmp_path / site).rglob("*") if p.is_file())
        held = sorted(p.relative_to(SITES / site) for p in (SITES / site).rglob("*") if p.is_file() and p.suffix != ".jpg")
        assert built == held, site
        for relative in built:
            assert (tmp_path / site / relative).read_bytes() == (SITES / site / relative).read_bytes(), relative
        shown = {v for p in (SITES / site).glob("*.html") for t, _, v in _parse(p).links if v.endswith(".jpg")}
        assert {f"assets/{p.name}" for p in (SITES / site / "assets").glob("*.jpg")} == shown, site


# ---------------------------------------------------------------- each check shown red, in build.py's shapes


def _red(check: str, root: Path) -> list[str]:
    found = CHECKS[check](root)
    assert found, f"the {check} check did not report its planted violation"
    return found


def test_the_statement_check_flags_a_page_without_it(sites: Path) -> None:
    page = sites / "net" / "contact.html"
    page.write_text(page.read_text().replace(STATEMENT, "OspreyFlow is a platform."))
    assert _red("statement", sites) == ["net/contact.html"]


def test_the_standard_check_flags_compliant(sites: Path) -> None:
    _plant(sites / "org" / "features.html", '<p class="callout">OspreyFlow is GDS compliant.</p>')
    assert any("org/features.html" in v for v in _red("standard", sites))


def test_the_standard_check_flags_a_check_no_longer_planned(sites: Path) -> None:
    page = sites / "net" / "public-sector.html"
    page.write_text(page.read_text().replace("a penetration test and ", ""))
    assert any("penetration test not planned" in v for v in _red("standard", sites))


@pytest.mark.parametrize("name", ["IBM i2", "Analyst's Notebook", "Palantir", "Quantexa", "Linkurious", "Maltego"])
def test_the_competitor_check_flags_each(sites: Path, name: str) -> None:
    _plant(sites / "org" / "features.html", f"<li><strong>Import.</strong> A chart from {html.escape(name)}.</li>")
    assert _red("competitor", sites)


def test_the_laurium_check_flags_the_drafts_own_words(sites: Path) -> None:
    _plant(sites / "org" / "features.html",
           "<li>A second extraction engine: Laurium, an open-source (MIT) library for extracting structured facts "
           "from documents.</li>")  # fmt: skip
    assert _red("laurium", sites)


def test_the_client_check_flags_the_synthetic_name_by_its_hash_alone(sites: Path) -> None:
    _plant(sites / "net" / "sectors.html", f"<p class=\"who\">For the {SYNTHETIC_CLIENT}&#x27;s analysts.</p>")
    found = _red("client", sites)
    assert found == [f"net/sectors.html: {client_hashes.digest(SYNTHETIC_CLIENT)[:12]}…"]
    assert all(SYNTHETIC_CLIENT.lower() not in v.lower() for v in found)


def test_the_client_check_reads_a_name_split_by_markup_and_marks(sites: Path) -> None:
    _plant(sites / "net" / "index.html", "<p><strong>EXAMPLE</strong> shire-constabulary</p>")
    assert _red("client", sites)


def test_the_local_path_check_flags_one_in_an_address(sites: Path) -> None:
    _plant(sites / "org" / "get-started.html", '<p><a href="file:///Users/someone/guide.pdf">The guide</a></p>')
    assert _red("local path", sites)


@pytest.mark.parametrize(
    "secret", ["AKIA" + "ABCDEFGHIJKLMNOP", "ghp_" + "a" * 36, "sk-" + "b" * 32, "password: hunter2example"]
)
def test_the_credential_check_flags_each_shape(sites: Path, secret: str) -> None:
    _plant(sites / "org" / "get-started.html", f"<pre><code>{secret}</code></pre>")
    assert _red("credential", sites)


def test_the_placeholder_check_flags_the_drafts_highlight(sites: Path) -> None:
    _plant(sites / "net" / "contact.html", '<p><span class="fill">Contact email to add</span></p>')
    assert _red("placeholder", sites)


def test_the_address_check_flags_any_other_address(sites: Path) -> None:
    _plant(sites / "org" / "contribute.html", '<p><a href="mailto:someone@example.org">someone@example.org</a></p>')
    assert _red("address", sites)


def test_the_request_check_flags_a_script_and_a_font_from_elsewhere(sites: Path) -> None:
    _plant(sites / "org" / "index.html", '<script src="assets/a.js"></script>')
    (sites / "net" / "assets" / "site.css").write_text("@font-face{src:url(https://fonts.example/a.woff2)}")
    found = _red("request outside", sites)
    assert any("<script>" in v for v in found) and any("site.css" in v for v in found)


def test_the_request_check_flags_an_image_from_elsewhere(sites: Path) -> None:
    _plant(sites / "org" / "team.html", '<img src="https://images.example/a.jpg" alt="">')
    assert _red("request outside", sites)


def test_the_link_check_flags_a_missing_page_and_a_missing_anchor(sites: Path) -> None:
    _plant(sites / "org" / "index.html", '<a href="pricing.html">Pricing</a><a href="features.html#ports">Ports</a>')
    found = _red("broken link", sites)
    assert any("pricing.html" in v for v in found) and any("#ports" in v for v in found)


def test_the_link_check_follows_a_link_to_the_other_site(sites: Path) -> None:
    _plant(sites / "net" / "index.html", '<a href="https://ospreyflow.org/roadmap.html">Roadmap</a>')
    assert _red("broken link", sites)


def test_the_link_check_flags_an_image_not_held(sites: Path) -> None:
    (sites / "org" / "assets" / "communities.jpg").unlink()
    assert any("communities.jpg" in v for v in _red("broken link", sites))


def test_the_install_check_flags_the_drafts_own_command(sites: Path) -> None:
    _plant(sites / "net" / "public-sector.html",
           '<pre><code>ospreyflow install --starter govuk-crime --service-name &quot;Analyse crime intelligence&quot; '
           '--organisation &quot;Your organisation&quot;</code></pre>')  # fmt: skip
    assert _red("install without a mode", sites) == [
        "net/public-sector.html: 'ospreyflow install --starter govuk-crime --service-name \"Analyse crime intelligence\" "
        "--organisation \"Your organisation\"'"]


def test_the_repository_check_flags_another_home(sites: Path) -> None:
    _plant(sites / "org" / "contribute.html", '<a href="https://github.com/Solirius/ospreyflow">Source</a>')
    assert _red("repository", sites)


# ---------------------------------------------------------------- client_hashes.py


def test_the_script_appends_hashes_and_prints_no_name(tmp_path: Path) -> None:
    script = tmp_path / "client_hashes.py"
    shutil.copy(MARKETING / "client_hashes.py", script)
    names = "Example Shire Constabulary\nEXAMPLE  shire constabulary\nExample Unit\n\n"
    run = subprocess.run([sys.executable, str(script)], input=names, capture_output=True, text=True)
    assert run.returncode == 0
    assert run.stdout == "2 added, 2 held.\n" and "example" not in (run.stdout + run.stderr).lower()
    held = (tmp_path / "client_names.sha256").read_text().split()
    assert held == [client_hashes.digest("Example Shire Constabulary"), client_hashes.digest("Example Unit")]
    again = subprocess.run([sys.executable, str(script)], input="Example Unit\n", capture_output=True, text=True)
    assert again.stdout == "0 added, 2 held.\n"


def test_the_hash_file_holds_the_synthetic_name() -> None:
    assert client_hashes.digest(SYNTHETIC_CLIENT) in client_hashes.known()
