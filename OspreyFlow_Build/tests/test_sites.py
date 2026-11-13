"""The two new websites, ospreyflow.org and ospreyflow.net (`marketing_site/sites/`), held to the current site's rules
and the owner's decisions of 12 November 2026. Every check has a case that plants a violation in the shape
`build.py` writes it, and asserts the check reports it (rule 15).

- the product's statement on every page, and "Solirius Reply";
- "designed to meet the GDS Service Standard", never a status only an assessment panel gives, and the three checks
  named as planned wherever the Standard is (the current site's own checks, `test_website_wording`);
- no client named (by hash, from the owner's local, gitignored file: `client_hashes.py`; a synthetic name in a file of
  the test's own shows the check red), no competitor named, i2 not until its ADR is accepted, and
  Laurium not named (the owner's decision 4);
- no local path, no credential, no placeholder left, and only the one address the owner gave (decision 2);
- no script but the site's own (`assets/site.js`, and the one inline script in `<head>` that sets the theme before the
  page paints, allowed by its hash in the page's content security policy and by nothing wider: the orchestrator's
  ruling of 13 November 2026), and no request outside the site; every internal link and anchor resolves, across the
  two sites too;
- the committed pages are `build.py`'s output, byte for byte.
"""

from __future__ import annotations

import base64
import hashlib
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
#: The drafts' highlighted gaps (`class="fill"`), build.py's own placeholder card (`class="person placeholder"`), and
#: a gap written in words.
PLACEHOLDER = re.compile(r'class="[^"]*\b(?:fill|placeholder)\b|\bto (?:be )?add(?:ed)?\b', re.IGNORECASE)
#: Planted in the client check's cases: synthetic, hashed into a file in the test's own temporary folder.
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


def _readable(page: Path) -> str:
    """What the page shows, and every attribute's value too (an address, a file name, an email address)."""
    source = page.read_text(encoding="utf-8")
    values = re.findall(r'\b[a-z-]+="([^"]*)"', source, flags=re.IGNORECASE)
    return page_text(page) + " . " + " . ".join(html.unescape(v) for v in values)


def clients(root: Path, hashes: Path) -> list[str] | str:
    """Each page carrying a name held in `hashes`, by its hash alone, so a failure names no client; or, where the file
    is absent, the words saying the pages were not checked (never an empty list, which would read as a pass)."""
    held = client_hashes.known(hashes)
    if held is None:
        return client_hashes.ABSENT
    return [f"{_id(p)}: {h[:12]}…" for p in pages(root) for h in sorted(client_hashes.named(_readable(p), held))]


@pytest.fixture
def synthetic_hashes(tmp_path: Path) -> Path:
    path = tmp_path / "client_names.local.sha256"
    path.write_text(f"# synthetic\n{client_hashes.digest(SYNTHETIC_CLIENT)}\n")
    return path


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


#: In a style sheet, a page's `<style>` or a `style="…"`: a fetch from another host, or an import.
OUTSIDE_IN_CSS = re.compile(r"url\(\s*['\"]?\s*(?:[a-z][a-z0-9+.-]*:)?//[^)]*\)|@import", re.IGNORECASE)


def _elsewhere(value: str) -> bool:
    """An address on another host: with a scheme (`https://…`) or protocol-relative (`//…`)."""
    parts = urlsplit(value.strip())
    return bool(parts.scheme or parts.netloc)


#: The only script a page may load from a file: the site's own.
SITE_SCRIPT = '<script src="assets/site.js"></script>'
CSP = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">')


def _inline_hash(script: str) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()


def scripts(page: Path) -> list[str]:
    """Each script on the page that is not the site's own: any other `<script>`, an inline one whose hash the page's
    policy does not name, a policy that allows more than its own file and that hash, or a handler in an attribute."""
    source = page.read_text(encoding="utf-8")
    found = []
    policy = CSP.search(source)
    directives = dict((d.strip().split(" ", 1) + [""])[:2] for d in policy.group(1).split(";") if d.strip()) if policy else {}
    allowed = directives.get("script-src", "").split()
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", source, flags=re.DOTALL | re.IGNORECASE):
        if m.group(0) == SITE_SCRIPT:
            continue
        if m.group(1).strip() or f"'{_inline_hash(m.group(2))}'" not in allowed:
            found.append(f"{_id(page)}: <script{m.group(1)}> not the site's own")
    if not policy:
        found.append(f"{_id(page)}: no content security policy")
    elif [a for a in allowed if a != "'self'" and not a.startswith("'sha256-")] or directives.get("default-src") != "'self'":
        found.append(f"{_id(page)}: the policy allows more than the site's own script: {policy.group(1)!r}")
    found += [f"{_id(page)}: {m.group(0)!r}" for m in re.finditer(r"\bon[a-z]+\s*=|javascript:", source, re.IGNORECASE)]
    return found


def requests_outside(root: Path) -> list[str]:
    """No script but the site's own, and nothing the browser fetches by itself (a style sheet, an image, a font, a
    script) from elsewhere."""
    found = [v for p in pages(root) for v in scripts(p)]
    for p in pages(root):
        source = p.read_text(encoding="utf-8")
        for tag, attribute, value in _parse(p).links:
            if tag != "a" and _elsewhere(value):
                found.append(f"{_id(p)}: <{tag} {attribute}={value!r}>")
        for srcset in re.findall(r'\bsrcset="([^"]*)"', source, flags=re.IGNORECASE):
            found += [f"{_id(p)}: srcset {c!r}" for c in (part.split()[0] for part in srcset.split(",") if part.strip())
                      if _elsewhere(c)]  # fmt: skip
        inline = re.findall(r"<style\b[^>]*>(.*?)</style>", source, flags=re.DOTALL | re.IGNORECASE)
        inline += [html.unescape(v) for v in re.findall(r'\bstyle="([^"]*)"', source, flags=re.IGNORECASE)]
        found += [f"{_id(p)}: {m}" for css in inline for m in OUTSIDE_IN_CSS.findall(css)]
    for site in DOMAINS:
        css = (root / site / "assets" / "site.css").read_text(encoding="utf-8")
        found += [f"{site}/assets/site.css: {m}" for m in OUTSIDE_IN_CSS.findall(css)]
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
                if not target.is_relative_to(page.parent.resolve()):
                    # Published alone, a site holds nothing above its own folder.
                    found.append(f"{_id(page)}: <{tag}> {value!r} leaves the site's folder")
                    continue
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
        # The screenshots are made only with --images; every other file, Solirius Reply's photographs included, by a plain build.
        held = sorted(p.relative_to(SITES / site) for p in (SITES / site).rglob("*")
                      if p.is_file() and (p.suffix != ".jpg" or p.name.startswith("solirius-")))  # fmt: skip
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


def test_no_page_names_the_synthetic_client(synthetic_hashes: Path) -> None:
    assert clients(SITES, synthetic_hashes) == []


def test_no_page_names_a_client_held_on_this_machine() -> None:
    """Against the owner's own file where it is present. Where it is absent this is skipped in words, never passed."""
    found = clients(SITES, client_hashes.HASHES)
    if isinstance(found, str):
        pytest.skip(found)
    assert found == []


def test_an_absent_hash_file_is_said_in_words_never_an_empty_pass(tmp_path: Path) -> None:
    assert clients(SITES, tmp_path / "client_names.local.sha256") == client_hashes.ABSENT


def test_the_hash_file_is_local_and_never_tracked() -> None:
    assert client_hashes.HASHES.name == "client_names.local.sha256"
    assert not (MARKETING / "client_names.sha256").exists()
    ignored = subprocess.run(["git", "check-ignore", "-q", str(client_hashes.HASHES)], cwd=MARKETING)
    assert ignored.returncode == 0, "client_names.local.sha256 is not gitignored"


def _client_red(root: Path, hashes: Path) -> list[str]:
    found = clients(root, hashes)
    assert isinstance(found, list) and found, "the client check did not report its planted name"
    return found


def test_the_client_check_flags_the_synthetic_name_by_its_hash_alone(sites: Path, synthetic_hashes: Path) -> None:
    _plant(sites / "net" / "sectors.html", f"<p class=\"who\">For the {SYNTHETIC_CLIENT}&#x27;s analysts.</p>")
    found = _client_red(sites, synthetic_hashes)
    assert found == [f"net/sectors.html: {client_hashes.digest(SYNTHETIC_CLIENT)[:12]}…"]
    assert all(SYNTHETIC_CLIENT.lower() not in v.lower() for v in found)


def test_the_client_check_reads_a_name_split_by_markup_and_marks(sites: Path, synthetic_hashes: Path) -> None:
    _plant(sites / "net" / "index.html", "<p><strong>EXAMPLE</strong> shire-constabulary</p>")
    assert _client_red(sites, synthetic_hashes)


@pytest.mark.parametrize(
    "fragment",
    [
        "<p>E.X.A.M.P.L.E. Shire Constabulary</p>",
        "<p>Ex\u00e1mple Shire Constabulary</p>",
        "<p>Ex&shy;ample Shire Con&#x200b;stabulary</p>",
        '<p><a href="https://example-shire-constabulary.example/">A link</a></p>',
    ],
)
def test_the_client_check_reads_dots_accents_invisible_characters_and_addresses(
    sites: Path, synthetic_hashes: Path, fragment: str
) -> None:
    _plant(sites / "net" / "index.html", fragment)
    assert _client_red(sites, synthetic_hashes)


def test_the_local_path_check_flags_one_in_an_address(sites: Path) -> None:
    _plant(sites / "org" / "get-started.html", '<p><a href="file:///Users/someone/guide.pdf">The guide</a></p>')
    assert _red("local path", sites)


@pytest.mark.parametrize(
    "secret", ["AKIA" + "ABCDEFGHIJKLMNOP", "ghp_" + "a" * 36, "sk-" + "b" * 32, "password: hunter2example"]
)
def test_the_credential_check_flags_each_shape(sites: Path, secret: str) -> None:
    _plant(sites / "org" / "get-started.html", f"<pre><code>{secret}</code></pre>")
    assert _red("credential", sites)


def test_the_placeholder_check_flags_build_pys_placeholder_card(sites: Path) -> None:
    _plant(sites / "org" / "team.html",
           '<article class="person placeholder"><div class="avatar" aria-hidden="true"></div><div><h3>Maintainer</h3>'
           '<p class="role">Maintainer</p></div></article>')  # fmt: skip
    assert _red("placeholder", sites)


def test_the_placeholder_check_flags_the_drafts_highlight(sites: Path) -> None:
    _plant(sites / "net" / "contact.html", '<p><span class="fill">Contact email to add</span></p>')
    assert _red("placeholder", sites)


def test_the_address_check_flags_any_other_address(sites: Path) -> None:
    _plant(sites / "org" / "contribute.html", '<p><a href="mailto:someone@example.org">someone@example.org</a></p>')
    assert _red("address", sites)


@pytest.mark.parametrize(
    "fragment",
    [
        '<script src="https://cdn.example/a.js"></script>',
        "<script>document.title='x'</script>",
        '<button type="button" onclick="go()">Go</button>',
        '<a href="javascript:void(0)">Go</a>',
    ],
)
def test_the_script_check_flags_any_script_not_the_sites_own(sites: Path, fragment: str) -> None:
    _plant(sites / "org" / "features.html", fragment)
    assert _red("request outside", sites)


def test_the_script_check_flags_the_head_script_changed_from_its_hash(sites: Path) -> None:
    page = sites / "net" / "index.html"
    page.write_text(page.read_text().replace("classList.add('theme-dark')", "classList.add('theme-light')", 1))
    assert _red("request outside", sites) == ["net/index.html: <script> not the site's own"]


@pytest.mark.parametrize("widened", ["'self' 'unsafe-inline'", "'self' https://cdn.example"])
def test_the_script_check_flags_a_policy_wider_than_the_sites_own(sites: Path, widened: str) -> None:
    page = sites / "org" / "team.html"
    page.write_text(re.sub(r"script-src 'self'", f"script-src {widened}", page.read_text(), count=1))
    assert any("allows more" in v for v in _red("request outside", sites))


def test_the_request_check_flags_a_script_and_a_font_from_elsewhere(sites: Path) -> None:
    _plant(sites / "org" / "index.html", '<script src="assets/a.js"></script>')
    (sites / "net" / "assets" / "site.css").write_text("@font-face{src:url(https://fonts.example/a.woff2)}")
    found = _red("request outside", sites)
    assert any('<script src="assets/a.js">' in v for v in found) and any("site.css" in v for v in found)


@pytest.mark.parametrize(
    "fragment",
    [
        '<link rel="stylesheet" href="//fonts.example/a.css">',
        '<img src="//images.example/a.jpg" alt="">',
        '<img src="assets/communities.jpg" srcset="assets/communities.jpg 1x, https://images.example/a.jpg 2x" alt="">',
        '<div style="background:url(https://images.example/a.jpg)"></div>',
        '<style>.hero{background:url(//images.example/a.jpg)}</style>',
    ],
)
def test_the_request_check_flags_each_other_way_out(sites: Path, fragment: str) -> None:
    _plant(sites / "net" / "services.html", fragment)
    assert _red("request outside", sites)


def test_the_request_check_flags_an_image_from_elsewhere(sites: Path) -> None:
    _plant(sites / "org" / "team.html", '<img src="https://images.example/a.jpg" alt="">')
    assert _red("request outside", sites)


def test_the_link_check_flags_a_missing_page_and_a_missing_anchor(sites: Path) -> None:
    _plant(sites / "org" / "index.html", '<a href="pricing.html">Pricing</a><a href="features.html#ports">Ports</a>')
    found = _red("broken link", sites)
    assert any("pricing.html" in v for v in found) and any("#ports" in v for v in found)


@pytest.mark.parametrize("href", ["../build.py", "../net/contact.html", "../../README.md"])
def test_the_link_check_flags_a_link_out_of_the_sites_folder(sites: Path, href: str) -> None:
    (sites / "build.py").write_text("")
    (sites.parent / "README.md").write_text("")
    _plant(sites / "org" / "index.html", f'<a href="{href}">Out</a>')
    assert any("leaves the site's folder" in v for v in _red("broken link", sites))


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
    assert not (tmp_path / "client_names.sha256").exists()
    held = (tmp_path / "client_names.local.sha256").read_text().split()
    assert held == [client_hashes.digest("Example Shire Constabulary"), client_hashes.digest("Example Unit")]
    again = subprocess.run([sys.executable, str(script)], input="Example Unit\n", capture_output=True, text=True)
    assert again.stdout == "0 added, 2 held.\n"


