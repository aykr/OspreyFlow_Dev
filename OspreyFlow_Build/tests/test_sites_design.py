"""The two websites in the design the owner approved on 13 November 2026 (`process/lanes/docs/BRIEF_sites2.md`), held
to the rules the new parts bring with them. `test_sites.py` holds the rules every page already kept; this file holds
the design's own:

- the fonts are the site's own files, with their licences, and the headings are set in Atkinson Hyperlegible Next;
- every text pairing in both palettes (the page's, the overview's and the GOV.UK drawing's) reaches 4.5:1;
- the release named anywhere on either site is the CHANGELOG's latest release, read at build time, never typed;
- the word is "pipeline", as the screens say, never "recipe" (the owner, 13 November);
- the animations are there, eleven chapters and four steps, synthetic and saying so, the GOV.UK one on ospreyflow.org's
  UK public sector page alone, drawn without the crown, the GOV.UK logotype or GDS Transport, with the line saying so;
- the datasets chapter versions the model, the pipeline and every load, never the dataset (the orchestrator's answer);
- the Solirius Reply images are the current site's own, byte for byte;
- one quiet line on every ospreyflow.org page leads to ospreyflow.net, and ospreyflow.net's UK public sector page leads
  to ospreyflow.org's rather than repeating it.

The browser's part (the theme switch, the player, reduced motion, off screen, keyboard and accessibility scans in both
themes) is in `marketing_site/check/`. Every check here has a case that plants a violation in the shape `build.py`
writes, and asserts the check reports it (rule 15).
"""

from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

import pytest

import subprocess
import sys

from tests.test_sites import CHECKS as PAGE_CHECKS
from tests.test_sites import DOMAINS, SITES, SYNTHETIC_CLIENT, _id, _plant, clients, page_text, pages
from tests.test_sites import sites, synthetic_hashes  # noqa: F401  (fixtures)

MARKETING = SITES.parent
CHANGELOG = MARKETING.parents[1] / "OspreyFlow_Core" / "CHANGELOG.md"
#: The current six-page site's home page: a bundle holding its images as base64 blobs.
CURRENT_HOME = MARKETING / "deploy" / "index.html"
FONT_FAMILIES = ("Atkinson Hyperlegible Next", "IBM Plex Mono")
SEATS = {"Analyst": 4, "Developer": 3, "Administrator": 4}
INVENTED = "every name is invented"
#: The datasets chapter, as the owner accepted it on 13 November 2026.
DATASETS_SUB = ("Every load is recorded with the pipeline version that made it, and can be reverted. The dataset's model "
                "is versioned: one live, one draft, and every earlier version can be restored.")
GOVUK_NOTE = "not a gov.uk"


def css(root: Path, site: str) -> str:
    return (root / site / "assets" / "site.css").read_text(encoding="utf-8")


def source(page: Path) -> str:
    return page.read_text(encoding="utf-8")


# ---------------------------------------------------------------- fonts and headings


def fonts(root: Path) -> list[str]:
    """Each family declared by `@font-face` from a file the site holds, beside its licence; nothing else named."""
    found = []
    for site in DOMAINS:
        sheet = css(root, site)
        faces = re.findall(r"@font-face\s*\{([^}]*)\}", sheet)
        for family in FONT_FAMILIES:
            if not any(family in face for face in faces):
                found.append(f"{site}: no @font-face for {family}")
        for face in faces:
            for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", face):
                if not (root / site / "assets" / url).is_file():
                    found.append(f"{site}: {url} is not held")
        held = root / site / "assets" / "fonts"
        for family in FONT_FAMILIES:
            licence = held / f"{family.replace(' ', '')}-OFL.txt"
            if not licence.is_file() or "SIL OPEN FONT LICENSE" not in licence.read_text(encoding="utf-8").upper():
                found.append(f"{site}: no licence for {family} at assets/fonts/{licence.name}")
    return found


def headings(root: Path) -> list[str]:
    """The owner, 13 November: page headings in Atkinson Hyperlegible Next, not serif."""
    found = []
    for site in DOMAINS:
        rule = re.search(r"(?:^|\})\s*h1\s*,\s*h2\s*,\s*h3\b[^{]*\{([^}]*)\}", css(root, site))
        family = re.search(r"font-family\s*:\s*([^;]+)", rule.group(1)) if rule else None
        if family is None or not family.group(1).strip().startswith('"Atkinson Hyperlegible Next"'):
            found.append(f"{site}: headings set in {family.group(1) if family else 'nothing declared'}")
    return found


# ---------------------------------------------------------------- contrast


def _block(sheet: str, selector: str) -> dict[str, str]:
    m = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", sheet)
    return dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})", m.group(1))) if m else {}


def _luminance(colour: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


#: Text on its ground, as the style sheet and the drawings set them: (palette's selectors, foreground, background).
PAGE_PAIRS = [("ink", "ground"), ("ink-2", "ground"), ("ink-2", "ground-2"), ("ink", "ground-2"), ("ink", "surface"),
              ("ink-2", "surface"), ("accent", "ground"), ("accent", "ground-2"), ("accent", "surface"),
              ("second", "ground"), ("second", "ground-2"), ("second", "surface"), ("on-dark", "dark"),
              ("on-dark-2", "dark"), ("accent-2", "dark"), ("dark", "accent-2"), ("on-accent", "accent"),
              ("ground", "ink")]  # fmt: skip
OVERVIEW_PAIRS = [(fg, bg) for fg in ("t1", "t2", "t3", "brass", "warn", "err", "ok") for bg in ("app", "panel", "raised")]
OVERVIEW_PAIRS += [("brassInk", "brass")]
GOVUK_PAIRS = [("ink", "white"), ("sec", "white"), ("blue", "white"), ("ink", "light"), ("sec", "light"), ("blue", "light"),
               ("white", "blue"), ("tagink", "tagbg"), ("white", "green"), ("ink", "yellow"), ("termink", "term"),
               ("termdim", "term")]  # fmt: skip
PALETTES = [(":root", ".theme-dark", PAGE_PAIRS), (".ov", ".theme-dark .ov", OVERVIEW_PAIRS), (".gv", None, GOVUK_PAIRS)]


def contrast(root: Path) -> list[str]:
    found = []
    for site in DOMAINS:
        sheet = css(root, site)
        for light, dark, pairs in PALETTES:
            for selector in filter(None, (light, dark)):
                palette = {**_block(sheet, light), **_block(sheet, selector)}
                if not palette:
                    found.append(f"{site}: no palette at {selector}")
                    continue
                for fg, bg in pairs:
                    prefix = {":root": "", ".theme-dark": ""}.get(selector, "k-" if "ov" in selector else "g-")
                    a, b = palette.get(prefix + fg), palette.get(prefix + bg)
                    if a is None or b is None:
                        found.append(f"{site} {selector}: {prefix + fg} or {prefix + bg} not defined")
                    elif ratio(a, b) < 4.5:
                        found.append(f"{site} {selector}: {fg} {a} on {bg} {b} is {ratio(a, b):.2f}:1")
    return found


# ---------------------------------------------------------------- the release


def latest_release(changelog: Path = CHANGELOG) -> str:
    m = re.search(r"^## (v\d+\.\d+\.\d+) — \d{4}-\d{2}-\d{2}$", changelog.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, "no released version in the CHANGELOG"
    return m.group(1)


def release_named(root: Path, release: str | None = None) -> list[str]:
    """Every version a page names is the latest release, and every page carries the badge saying which."""
    release = release or latest_release()
    found = [f"{_id(p)}: {v}" for p in pages(root) for v in re.findall(r"\bv\d+\.\d+\.\d+\b", page_text(p)) if v != release]
    found += [f"{_id(p)}: no release badge" for p in pages(root)
              if not re.search(r'class="release"[^>]*>Release ' + re.escape(release) + "<", source(p))]  # fmt: skip
    return found


# ---------------------------------------------------------------- words


def recipe(root: Path) -> list[str]:
    """The owner, 13 November: "pipeline", the word the screens show; "recipe" is the code's word."""
    return [f"{_id(p)}: {m.group(0)!r}" for p in pages(root) for m in re.finditer(r"\brecipes?\b", page_text(p), re.I)]


# ---------------------------------------------------------------- the animations


def _scenes(text: str, cls: str) -> list[str]:
    return re.findall(rf'<div class="{cls}-scene" data-seat="(\d)" data-step="(\d)"', text)


def animations(root: Path) -> list[str]:
    found = []
    for site in DOMAINS:
        home = source(root / site / "index.html")
        seats = re.findall(r'<button type="button" class="ov-tab[^"]*"[^>]*>([^<]+)</button>', home)
        if seats != list(SEATS):
            found.append(f"{site}/index.html: the seats are {seats}")
        counts = [sum(1 for p, _ in _scenes(home, "ov") if int(p) == i) for i in range(len(SEATS))]
        if counts != list(SEATS.values()):
            found.append(f"{site}/index.html: chapters per seat {counts}")
    org = source(root / "org" / "public-sector.html")
    if len(_scenes(org, "gv")) != 4:
        found.append(f"org/public-sector.html: {len(_scenes(org, 'gv'))} GOV.UK steps")
    for p in pages(root):
        if p != root / "org" / "public-sector.html" and 'class="gv' in source(p):
            found.append(f"{_id(p)}: the GOV.UK animation, which is ospreyflow.org's UK public sector page's alone")
    return found


def synthetic(root: Path) -> list[str]:
    """Each animation's section says its names are invented, and every case it draws says it is synthetic."""
    found = []
    for p in pages(root):
        text = source(p)
        for cls, ident in (("ov", "overview"), ("gv", "govuk-theme")):
            if f'class="{cls}"' not in text:
                continue
            section = re.search(rf'<section class="band[^"]*" id="{ident}">(.*?)</section>', text, re.S)
            if section is None or INVENTED not in page_text_of(section.group(1)):
                found.append(f"{_id(p)}: the {ident} section does not say {INVENTED!r}")
        for m in re.finditer(r"\b(?:Operation [A-Z][a-z]+|HMP [A-Za-z ]+?)\b(?! \(synthetic)", page_text(p)):
            found.append(f"{_id(p)}: {m.group(0)!r} without '(synthetic'")
    return found


def page_text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment)))


def govuk_drawing(root: Path) -> list[str]:
    """ADR-132's rule for a site that is not on gov.uk: no crown, no GOV.UK logotype and no GDS Transport, with a line
    under the drawing saying it is the website's own drawing, not the product's screen."""
    found = []
    for site in DOMAINS:
        if "GDS Transport" in css(root, site):
            found.append(f"{site}/assets/site.css: GDS Transport")
        gv = re.search(r"(?:^|\})\s*\.gv\s*\{([^}]*)\}", css(root, site))
        if gv is None or not re.search(r"font-family\s*:\s*Arial", gv.group(1)):
            found.append(f"{site}/assets/site.css: the GOV.UK drawing is not set in Arial")
    for p in pages(root):
        text = source(p)
        if "GDS Transport" in text:
            found.append(f"{_id(p)}: GDS Transport")
        for m in re.finditer(r"crown|logotype", "".join(re.findall(r'<div class="gv".*?<p class="gv-note">', text, re.S)), re.I):
            found.append(f"{_id(p)}: {m.group(0)!r} in the GOV.UK drawing")
        if 'class="gv"' in text:
            note = re.search(r'<p class="gv-note">(.*?)</p>', text, re.S)
            if note is None or GOVUK_NOTE not in note.group(1):
                found.append(f"{_id(p)}: the line under the GOV.UK drawing does not say it is the website's own")
    return found


def datasets_chapter(root: Path) -> list[str]:
    """The orchestrator's answer of 13 November: a dataset has no version of its own; its model, each pipeline and
    every load do."""
    found = []
    for site in DOMAINS:
        home = source(root / site / "index.html")
        chapter = re.search(r'data-seat="2" data-step="2".*?(?=<div class="ov-scene"|<div class="ov-steps")', home, re.S)
        text = page_text_of(chapter.group(0)) if chapter else ""
        for want in (DATASETS_SUB, "pipeline v3", "Model v14 · live", "v15 · draft", "Reverted"):
            if want not in text:
                found.append(f"{site}/index.html: the datasets chapter lacks {want!r}")
        for m in re.finditer(r"[Dd]ataset v\d+|[Rr]ecipe v\d+|Pipeline v\d+ ·", text):
            found.append(f"{site}/index.html: {m.group(0)!r} in the datasets chapter")
    return found


# ---------------------------------------------------------------- Solirius Reply, and the way between the sites


def _blobs(bundle: Path = CURRENT_HOME) -> set[str]:
    import base64

    found = set()
    for m in re.finditer(r'"(?:data|content)"\s*:\s*"([A-Za-z0-9+/=]{200,})"', bundle.read_text(encoding="utf-8")):
        found.add(hashlib.sha256(base64.b64decode(m.group(1))).hexdigest())
    return found


def solirius(root: Path) -> list[str]:
    """The two logos and two photographs are the current site's own (its home page bundle), used at the owner's
    instruction, and the "Developed by Solirius Reply" section is on both home pages."""
    found, blobs = [], _blobs()
    for site in DOMAINS:
        held = sorted((root / site / "assets").glob("solirius-*"))
        if len(held) != 4:
            found.append(f"{site}: {len(held)} Solirius Reply images, not 4")
        found += [f"{site}/assets/{p.name} is not the current site's" for p in held
                  if hashlib.sha256(p.read_bytes()).hexdigest() not in blobs]  # fmt: skip
        if 'id="solirius"' not in source(root / site / "index.html"):
            found.append(f"{site}/index.html: no 'Developed by Solirius Reply' section")
    return found


def between_sites(root: Path) -> list[str]:
    found = []
    for p in sorted((root / "org").glob("*.html")):
        lines = re.findall(r'<p class="to-net">.*?href="https://ospreyflow\.net/?".*?</p>', source(p), re.S)
        if len(lines) != 1:
            found.append(f"{_id(p)}: {len(lines)} quiet lines to ospreyflow.net")
    net = source(root / "net" / "public-sector.html")
    if 'href="https://ospreyflow.org/public-sector.html"' not in net:
        found.append("net/public-sector.html: no link to ospreyflow.org's UK public sector page")
    if "<table" in net or "Starters" in net:
        found.append("net/public-sector.html: repeats ospreyflow.org's page rather than leading to it")
    return found


CHECKS = {
    "fonts": fonts,
    "headings": headings,
    "contrast": contrast,
    "release": release_named,
    "recipe": recipe,
    "animations": animations,
    "synthetic": synthetic,
    "govuk drawing": govuk_drawing,
    "datasets chapter": datasets_chapter,
    "solirius": solirius,
    "between sites": between_sites,
}


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_the_sites_pass(check: str) -> None:
    assert CHECKS[check](SITES) == []


# ---------------------------------------------------------------- each check shown red, in build.py's shapes


def _red(check: str, root: Path) -> list[str]:
    found = CHECKS[check](root)
    assert found, f"the {check} check did not report its planted violation"
    return found


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {path.name}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_the_font_check_flags_a_missing_file_and_licence(sites: Path) -> None:
    next((sites / "org" / "assets" / "fonts").glob("ibm-plex-mono-*.woff2")).unlink()
    (sites / "net" / "assets" / "fonts" / "AtkinsonHyperlegibleNext-OFL.txt").unlink()
    found = _red("fonts", sites)
    assert any("org: fonts/ibm-plex-mono" in v for v in found) and any("net: no licence" in v for v in found)


def test_the_font_check_flags_a_family_with_no_face(sites: Path) -> None:
    sheet = sites / "org" / "assets" / "site.css"
    sheet.write_text(re.sub(r"@font-face\s*\{[^}]*IBM Plex Mono[^}]*\}", "", sheet.read_text()))
    assert "org: no @font-face for IBM Plex Mono" in _red("fonts", sites)


def test_the_heading_check_flags_the_drafts_serif(sites: Path) -> None:
    sheet = sites / "net" / "assets" / "site.css"
    sheet.write_text(re.sub(r'(h1,h2,h3\{font-family:)"Atkinson Hyperlegible Next"[^;]*',
                            r'\1"Iowan Old Style","Palatino Linotype",Georgia,serif', sheet.read_text(), count=1))
    assert _red("headings", sites) == ['net: headings set in "Iowan Old Style","Palatino Linotype",Georgia,serif']


@pytest.mark.parametrize(
    ("selector", "token", "colour"),
    [(".theme-dark", "ink-2", "#5f6263"), (".ov", "k-t3", "#a2a5a6"), (".theme-dark .ov", "k-brass", "#6b4d12"),
     (".gv", "g-sec", "#b1b4b6"), (":root", "accent", "#C08A34")],
)  # fmt: skip
def test_the_contrast_check_flags_a_pairing_below_four_and_a_half(sites: Path, selector: str, token: str, colour: str) -> None:
    sheet = sites / "org" / "assets" / "site.css"
    text = sheet.read_text()
    m = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", text)
    assert m, selector
    block = re.sub(rf"(--{re.escape(token)}\s*:\s*)#[0-9A-Fa-f]{{6}}", rf"\g<1>{colour}", m.group(1))
    sheet.write_text(text[: m.start(1)] + block + text[m.end(1) :])
    assert any(v.startswith(f"org {selector}:") for v in _red("contrast", sites))


def test_the_release_check_flags_the_drafts_typed_badge(sites: Path) -> None:
    _plant(sites / "org" / "index.html", '<p class="kicker">Version v2.6.0</p>')
    assert _red("release", sites) == ["org/index.html: v2.6.0"]


def test_the_release_check_flags_a_badge_behind_the_changelog(sites: Path) -> None:
    """A CHANGELOG that has moved on (here to v9.9.9) and pages built before it: every badge is flagged."""
    found = release_named(sites, "v9.9.9")
    assert {v for v in found if v.endswith("no release badge")} == {f"{_id(p)}: no release badge" for p in pages(sites)}


def test_the_recipe_check_flags_the_codes_word(sites: Path) -> None:
    _plant(sites / "org" / "contribute.html", "<p>A recipe maps a source to a domain model.</p>")
    assert _red("recipe", sites) == ["org/contribute.html: 'recipe'"]


def test_the_animation_check_flags_a_chapter_missing_and_the_govuk_animation_on_net(sites: Path) -> None:
    home = sites / "net" / "index.html"
    text = home.read_text()
    home.write_text(re.sub(r'<div class="ov-scene" data-seat="1" data-step="2".*?(?=<div class="ov-scene")', "", text,
                           count=1, flags=re.S))  # fmt: skip
    gv = re.search(r'<div class="gv".*?<p class="gv-note">.*?</p></div>', (sites / "org" / "public-sector.html").read_text(), re.S)
    assert gv
    _plant(sites / "net" / "public-sector.html", gv.group(0))
    found = _red("animations", sites)
    assert "net/index.html: chapters per seat [4, 2, 4]" in found and any("net/public-sector.html" in v for v in found)


def test_the_synthetic_check_flags_a_section_that_does_not_say_so(sites: Path) -> None:
    _edit(sites / "org" / "index.html", INVENTED, "every name is ours")
    assert any("overview" in v for v in _red("synthetic", sites))


def test_the_synthetic_check_flags_a_case_not_marked_synthetic(sites: Path) -> None:
    _plant(sites / "net" / "index.html", "<svg><text>The Glass · Case · Operation Harbour</text></svg>")
    assert any("Operation Harbour" in v for v in _red("synthetic", sites))


@pytest.mark.parametrize(
    "plant",
    ["font-family:\"GDS Transport\",arial,sans-serif", '<path class="govuk-logotype-crown" d="M0 0"></path>', "no note"],
)
def test_the_govuk_check_flags_the_crown_the_typeface_and_a_missing_note(sites: Path, plant: str) -> None:
    page = sites / "org" / "public-sector.html"
    if plant.startswith("font-family"):
        sheet = sites / "org" / "assets" / "site.css"
        sheet.write_text(sheet.read_text().replace(".gv{", ".gv{" + plant + ";", 1))
    elif plant.startswith("<path"):
        _edit(page, '<div class="gv-stage">', '<div class="gv-stage">' + plant)
    else:
        text = page.read_text()
        page.write_text(re.sub(r'<p class="gv-note">.*?</p>', '<p class="gv-note">The GOV.UK theme.</p>', text, flags=re.S))
    assert _red("govuk drawing", sites)


@pytest.mark.parametrize(
    ("old", "new"),
    [("pipeline v3", "recipe v3"), ("Model v14 · live", "Dataset v14 · live"), ("pipeline version that made it", "load")],
)
def test_the_datasets_check_flags_a_dataset_version_and_the_codes_word(sites: Path, old: str, new: str) -> None:
    _edit(sites / "org" / "index.html", old, new)
    assert any(v.startswith("org/index.html") for v in _red("datasets chapter", sites))


def test_the_solirius_check_flags_an_image_not_the_current_sites(sites: Path) -> None:
    (sites / "net" / "assets" / "solirius-desk.jpg").write_bytes(b"\xff\xd8\xff\xe0 not the current site's photograph")
    assert _red("solirius", sites) == ["net/assets/solirius-desk.jpg is not the current site's"]


def test_the_between_sites_check_flags_a_missing_line_and_a_repeated_page(sites: Path) -> None:
    page = sites / "org" / "team.html"
    page.write_text(re.sub(r'<p class="to-net">.*?</p>', "", page.read_text(), flags=re.S))
    _plant(sites / "net" / "public-sector.html", "<table><caption>The ten starters</caption></table>")
    found = _red("between sites", sites)
    assert "org/team.html: 0 quiet lines to ospreyflow.net" in found and any("repeats" in v for v in found)


def test_the_changelog_is_read_not_typed() -> None:
    assert re.fullmatch(r"v\d+\.\d+\.\d+", latest_release())


# ---------------------------------------------------------------- the page rules reach inside the animations


def _into_a_chapter(page: Path, svg_fragment: str) -> None:
    """Into the drawing of a chapter that is not shown first, where a reader meets it only once the player moves on."""
    _edit(page, '<div class="ov-scene" data-seat="2" data-step="3" hidden><div class="ov-head">',
          '<div class="ov-scene" data-seat="2" data-step="3" hidden><div class="ov-head">' + svg_fragment)


@pytest.mark.parametrize(
    ("check", "fragment"),
    [("standard", '<svg viewBox="0 0 10 10"><text x="0" y="0">OspreyFlow is GDS compliant.</text></svg>'),
     ("competitor", '<svg viewBox="0 0 10 10" role="img" aria-label="A chart imported from Palantir"></svg>'),
     ("laurium", '<svg viewBox="0 0 10 10"><text x="0" y="0">Extraction: Laurium</text></svg>')],
)  # fmt: skip
def test_the_page_rules_flag_a_violation_inside_an_animation(sites: Path, check: str, fragment: str) -> None:
    _into_a_chapter(sites / "net" / "index.html", fragment)
    found = PAGE_CHECKS[check](sites)
    assert any(v.startswith("net/index.html") for v in found), f"the {check} check missed a violation in a chapter"


def test_the_client_check_flags_a_name_inside_an_animation(sites: Path, synthetic_hashes: Path) -> None:
    _into_a_chapter(sites / "org" / "index.html", f'<svg viewBox="0 0 10 10"><text x="0" y="0">{SYNTHETIC_CLIENT}</text></svg>')
    assert clients(sites, synthetic_hashes) == [f"org/index.html: {__import__('client_hashes').digest(SYNTHETIC_CLIENT)[:12]}…"]


def test_the_build_refuses_a_release_its_pages_were_not_checked_against(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## Unreleased\n\n## v0.5.1 — 2026-11-14\n\n## v0.5.0 — 2026-11-10\n", encoding="utf-8")
    run = subprocess.run([sys.executable, str(SITES / "build.py"), "--out", str(tmp_path / "out"), "--changelog", str(changelog)],
                         capture_output=True, text=True)  # fmt: skip
    assert run.returncode != 0
    assert "latest release is v0.5.1, and the pages were checked against v0.5.0" in run.stderr
