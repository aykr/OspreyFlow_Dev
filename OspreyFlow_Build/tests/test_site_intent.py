"""DC1b: the platform's stated intent on the two websites (`marketing_site/sites/`, built only by `build.py`).

The owner's rules for the wording (20 November 2026, `Claude outputs/ospreyflow_intent_2026-11-20/PROMPT_ORCHESTRATOR.md`,
DC1a's table in `process/lanes/v062/slices/DOC1A_REPORT.md`):

- the intent paragraph is one constant in `build.py`, pinned here by its SHA-256 (the owner's file is git-ignored and is
  not in a worktree), and it is on ospreyflow.org's Home as its own section directly under the opening statement and on
  ospreyflow.net's Home lower down, **character for character**: no edit, no reflow, no change of punctuation;
- the five constraints are named, in the owner's order, with one or two plain sentences and a link each, on ospreyflow.org's
  Home, and the Governance page's "Principles the project holds to" names the five;
- every sentence DC1a found stronger than the product is true is gone from both sites (`OVERSTATED`, each shown to be
  flagged when planted back in the shape the pages carry it, and the shapes behind them);
- outside the paragraph neither site says "guarantee";
- a hosted engine is described as an opt-in; the licence statement says what it covers and what is outside it; the
  attribution of model calls and sign-in events, and the fix for Superset's usage image, are said as coming, the fix as in the next release (the pages name no version but the latest);
- the older six-page site (`marketing_site/deploy`) does not carry the paragraph.

Every check is a function of one folder, run on the committed pages and then on a copy with one violation planted in the
shape `build.py` writes it (rule 15). The paragraph's plants are one character changed in a built page, the paragraph
reflowed, the constant used on one page only, and the constant itself changed and the sites rebuilt from it.

**Folders this test walks** (for the line's scan map): `OspreyFlow_Build/marketing_site/sites/org` and
`OspreyFlow_Build/marketing_site/sites/net` (every built page, read), `OspreyFlow_Build/marketing_site/deploy` (the older
site's pages, read), and `OspreyFlow_Build/marketing_site/sites/build.py` with `overview.py` and `govanim.py` (imported and
run into a temporary folder, which reads `OspreyFlow_Core/CHANGELOG.md`). It imports `tests/test_sites.py`, itself a walker.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import re
import shutil
from pathlib import Path
from types import ModuleType

import pytest

from tests.test_sites import DOMAINS, MARKETING, SITES, _plant, pages
from tests.test_website_wording import page_text

DEPLOY = MARKETING / "deploy"

#: The owner's paragraph, as a hash: the owner's file is not in a worktree, and the text is held once, in `build.py`.
INTENT_SHA256 = "725bbd47f56f64339dcd3e11108f8e66dff2abf2d1110d3c92222f2d58919ba9"
INTENT_LENGTH = 1033

#: The five constraints, by the owner's names and in the owner's order.
FIVE = ["Software sovereignty", "Data sovereignty", "Privacy control", "Security management", "Analytical accountability"]
WHY = "Why OspreyFlow exists"
CONSTRAINTS = "The five constraints"
PRINCIPLES = "Principles the project holds to"
#: Where a constraint's link may lead: the pages that already show it.
SHOWN_ON = {"features.html", "governance.html", "public-sector.html"}


def _load_build() -> ModuleType:
    """`build.py` as a module under a name of its own (a bare `build` is another package's)."""
    spec = importlib.util.spec_from_file_location("ospreyflow_sites_build_under_test", SITES / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = _load_build()


def _intent() -> str:
    intent = getattr(BUILD, "INTENT", None)
    assert isinstance(intent, str), "build.py holds the intent paragraph in no constant named INTENT"
    return intent


def _main(page: Path) -> str:
    source = page.read_text(encoding="utf-8")
    return source.split('<main id="main">', 1)[1].split("</main>", 1)[0]


def _strip(fragment: str) -> str:
    """Tags removed and nothing else (no whitespace folded), then the entities read."""
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def _flat(text: str) -> str:
    """For finding a sentence: entities read, quotes straightened, case and spacing folded."""
    return re.sub(r"\s+", " ", html.unescape(text).replace("’", "'")).strip().lower()


@pytest.fixture
def sites(tmp_path: Path) -> Path:
    copy = tmp_path / "sites"
    for site in DOMAINS:
        shutil.copytree(SITES / site, copy / site)
    return copy


# ---------------------------------------------------------------- the paragraph, character for character

HOMES = {"org": "org/index.html", "net": "net/index.html"}
INTENT_P = re.compile(r'<p class="intent">(.*?)</p>', re.DOTALL)


def constant_violations(module: ModuleType = BUILD) -> list[str]:
    """`build.py`'s constant is the owner's paragraph: the hash of its bytes, and its length."""
    intent = getattr(module, "INTENT", None)
    if not isinstance(intent, str):
        return ["build.py holds the intent paragraph in no constant named INTENT"]
    found = []
    if len(intent) != INTENT_LENGTH:
        found.append(f"the constant is {len(intent)} characters, the owner's paragraph {INTENT_LENGTH}")
    if hashlib.sha256(intent.encode("utf-8")).hexdigest() != INTENT_SHA256:
        found.append("the constant is not the owner's paragraph (its SHA-256 differs)")
    return found


def intent_violations(root: Path, intent: str | None = None) -> list[str]:
    """Each Home carries the paragraph once, as the constant: read from the built page with its tags stripped and nothing
    else done to it, compared whole. A reflow, a changed mark or a single letter is a difference."""
    intent = _intent() if intent is None else intent
    found = []
    for site, name in HOMES.items():
        page = root / name
        carried = [_strip(m) for m in INTENT_P.findall(_main(page))]
        if len(carried) != 1:
            found.append(f"{name}: carries the paragraph {len(carried)} times, not once")
            continue
        if carried[0] != intent:
            first = next((i for i, (a, b) in enumerate(zip(carried[0], intent)) if a != b), min(len(carried[0]), len(intent)))
            found.append(f"{name}: differs from the constant at character {first}: …{carried[0][max(0, first - 20):first + 20]!r}…")
        elif intent not in _strip(_main(page)):
            found.append(f"{name}: the paragraph is not whole in the page's text")
    return found


def headings(page: Path) -> list[str]:
    return [_strip(h) for h in re.findall(r"<h2>(.*?)</h2>", _main(page), flags=re.DOTALL)]


def placement_violations(root: Path) -> list[str]:
    """ospreyflow.org: its own section, the first under the opening statement (the hero), followed by the five. ospreyflow.net:
    lower down, after the panels it sits beside ("Why organisations choose it") and before "Where it applies"."""
    found = []
    org = _main(root / HOMES["org"])
    sections = re.findall(r'<section class="([^"]*)"(?: id="([^"]*)")?>', org)
    if not sections or not sections[0][0].startswith("hero"):
        found.append("org/index.html: the opening statement is not the first section")
    elif len(sections) < 2 or sections[1][1] != "why":
        found.append("org/index.html: the paragraph's section does not follow the opening statement directly")
    org_h2 = headings(root / HOMES["org"])
    if org_h2[:2] != [WHY, CONSTRAINTS]:
        found.append(f"org/index.html: the first two sections are {org_h2[:2]}, not {[WHY, CONSTRAINTS]}")
    net_h2 = headings(root / HOMES["net"])
    if WHY not in net_h2 or "Why organisations choose it" not in net_h2 or "Where it applies" not in net_h2:
        found.append(f"net/index.html: headings {net_h2} lack the paragraph's section or its neighbours")
    elif not net_h2.index("Why organisations choose it") < net_h2.index(WHY) < net_h2.index("Where it applies"):
        found.append("net/index.html: the paragraph is not between 'Why organisations choose it' and 'Where it applies'")
    return found


def _section(page: Path, heading: str) -> str:
    chunks = _main(page).split("<section ")[1:]
    for chunk in chunks:
        if f"<h2>{heading}</h2>" in chunk:
            return chunk
    return ""


def constraint_violations(root: Path) -> list[str]:
    """ospreyflow.org's Home names the five in order, each with one or two plain sentences and one link to a page that already
    shows it; the Governance page's principles name the five in order."""
    found = []
    home = root / HOMES["org"]
    section = _section(home, CONSTRAINTS)
    articles = re.findall(r"<article class=\"card\">(.*?)</article>", section, flags=re.DOTALL)
    names = [_strip(m.group(1)) for a in articles for m in [re.search(r"<h3>(.*?)</h3>", a, flags=re.DOTALL)] if m]
    if names != FIVE:
        found.append(f"org/index.html: the constraints are {names}, not {FIVE}")
    for a in articles:
        name = _strip(re.search(r"<h3>(.*?)</h3>", a, flags=re.DOTALL).group(1)) if "<h3>" in a else "?"
        body = _strip(" ".join(re.findall(r"<p>(.*?)</p>", a, flags=re.DOTALL)))
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", body.strip()) if s]
        if not 1 <= len(sentences) <= 2:
            found.append(f"org/index.html: {name} has {len(sentences)} sentences, not one or two")
        links = re.findall(r'<a href="([^"#]+)(?:#[^"]*)?"', a)
        if len(links) != 1 or links[0] not in SHOWN_ON:
            found.append(f"org/index.html: {name} links to {links}, not one of {sorted(SHOWN_ON)}")
    principles = _strip(_section(root / "org" / "governance.html", PRINCIPLES))
    at = [principles.find(n) for n in FIVE]
    if -1 in at or at != sorted(at):
        found.append(f"org/governance.html: '{PRINCIPLES}' does not name the five in order")
    return found


def _constraint(root: Path, name: str) -> str:
    section = _section(root / HOMES["org"], CONSTRAINTS)
    for a in re.findall(r"<article class=\"card\">(.*?)</article>", section, flags=re.DOTALL):
        if f"<h3>{name}</h3>" in a:
            return _flat(_strip(a))
    return ""


# ---------------------------------------------------------------- the sentences DC1a found too strong

#: Each sentence the sites carried that stated one of the five more strongly than DC1a found true (page and line in
#: `DOC1A_REPORT.md`, "Where introductory and positioning text is"; the list with the reasons and the replacements is
#: `DC1B_SENTENCES.md`). Lower case; compared with the page's text folded the same way.
OVERSTATED = [
    "Nothing leaves unless an administrator enables it for a dataset",
    "It never leaves your environment",
    "The deployment's own model answers by default and nothing leaves",
    "because the deployment never calls out",
    "The deployment does not call out on its own",
    "so a hidden record leaves no trace in a count, a path or a chart",
    "so a record someone may not see leaves no trace in a count, a path or a chart",
    "and reads filtered in the store, so a hidden record leaves no trace in a count",
    "so a record someone may not see leaves no trace in a count or a path",
    "every change to what may leave the deployment",
    "Every export and approval is in the audit",
    "Every answer names the engine and model that produced it",
    "and every read that was refused",
    "Open-source components throughout, each listed with its licence",
    "Nothing you may not see is shown or counted",
    "The log is append-only",
    "a full audit trail",
]
#: The shapes behind them, so a reworded return is found too.
OVERSTATED_SHAPES = {
    "nothing leaves": re.compile(r"\bnothing (?:ever )?leaves\b", re.IGNORECASE),
    "never leaves": re.compile(r"\bnever (?:leaves|calls out)\b", re.IGNORECASE),
    "leaves no trace": re.compile(r"\bleaves? no trace\b", re.IGNORECASE),
    "append-only": re.compile(r"\bappend-only\b", re.IGNORECASE),
    "every read": re.compile(r"\bevery read\b", re.IGNORECASE),
}


def overstated(root: Path) -> list[str]:
    found = []
    for page in pages(root):
        text = _flat(page_text(page))
        found += [f"{page.parent.name}/{page.name}: {s!r}" for s in OVERSTATED if _flat(s) in text]
        found += [f"{page.parent.name}/{page.name}: shape {n!r}: {m.group(0)!r}" for n, rx in OVERSTATED_SHAPES.items()
                  for m in rx.finditer(text)]  # fmt: skip
    return found


def guarantees(root: Path) -> list[str]:
    """Outside the paragraph, no 'guarantee' (the paragraph is removed whole, by its exact text, before the page is read)."""
    intent = _intent()
    found = []
    for page in pages(root):
        text = page_text(page).replace(intent, " ")
        found += [f"{page.parent.name}/{page.name}: …{text[max(0, m.start() - 40):m.end() + 40]}…"
                  for m in re.finditer(r"guarantee", text, re.IGNORECASE)]  # fmt: skip
    return found


HOSTED = re.compile(r"\bhosted (?:model |AI )?(?:engine|model)s?\b", re.IGNORECASE)


def hosted_without_opt_in(root: Path) -> list[str]:
    """A page that speaks of a hosted engine says it is an opt-in."""
    return [f"{p.parent.name}/{p.name}" for p in pages(root) if HOSTED.search(page_text(p)) and "opt-in" not in page_text(p).lower()]


def wording_violations(root: Path) -> list[str]:
    """What DC1a says the licence statement, the attribution and the Superset fix may claim."""
    found = []
    one = _constraint(root, FIVE[0])
    found += [f"software sovereignty lacks {w!r}" for w in ("model weights", "map data", "fonts", "base images", "outside", "coming") if w not in one]
    two = _constraint(root, FIVE[1])
    found += [f"data sovereignty lacks {w!r}" for w in ("opt-in", "next release", "no route out by default") if w not in two]
    four = _constraint(root, FIVE[3])
    found += [f"security management lacks {w!r}" for w in ("coming", "model call", "sign-in", "type list", "map tiles") if w not in four]
    public = _flat(page_text(root / "org" / "public-sector.html"))
    found += [f"the licence statement on org/public-sector.html lacks {w!r}" for w in ("model weights", "map data", "fonts", "base images", "coming") if w not in public]
    return found


def deploy_carries_the_paragraph(root: Path = DEPLOY) -> list[str]:
    """The older site is not edited and does not carry the paragraph: its first sentence is the test of it."""
    lead = _flat(_intent()[:110])
    return [p.name for p in sorted(root.glob("*.html")) if lead in _flat(page_text(p))]


# ---------------------------------------------------------------- the sites as committed


def test_the_constant_is_the_owners_paragraph() -> None:
    assert constant_violations() == []


def test_both_homes_carry_the_paragraph_character_for_character() -> None:
    assert intent_violations(SITES) == []


def test_the_paragraph_sits_where_the_owner_put_it() -> None:
    assert placement_violations(SITES) == []


def test_the_five_constraints_are_named_with_a_link_each_and_on_the_governance_page() -> None:
    assert constraint_violations(SITES) == []


def test_no_sentence_dc1a_found_too_strong_remains() -> None:
    assert overstated(SITES) == []


def test_no_guarantee_outside_the_paragraph() -> None:
    assert guarantees(SITES) == []


def test_a_hosted_engine_is_described_as_an_opt_in() -> None:
    assert hosted_without_opt_in(SITES) == []


def test_the_licence_attribution_and_tracking_statements_say_what_dc1a_found() -> None:
    assert wording_violations(SITES) == []


def test_the_older_site_does_not_carry_the_paragraph() -> None:
    assert deploy_carries_the_paragraph() == []


def test_the_pages_the_test_reads_are_there() -> None:
    """Guards every check above against reading nothing."""
    assert len(pages(SITES)) == 12
    assert len(list(DEPLOY.glob("*.html"))) >= 4
    assert (SITES / "build.py").is_file()


# ---------------------------------------------------------------- each check shown red, in build.py's shapes


#: One character each, found by the words round it: a capital, a letter dropped, a letter changed, a mark changed, the full stop dropped.
ONE_CHARACTER = {
    "a-capital": ("Intelligence mapping", "intelligence mapping"),
    "a-letter-dropped": ("guarantees", "guarantee"),
    "a-letter-changed": ("necessary but", "necessarx but"),
    "a-mark": ("licence; the platform", "licence, the platform"),
    "the-full-stop": ("during design.", "during design"),
}
#: The paragraph reflowed: a line break after a comma, a space doubled, a space made a non-breaking one.
REFLOWED = {
    "a-line-break": (", yet the", ",\nyet the"),
    "a-doubled-space": ("at the centre of", "at the  centre of"),
    "a-non-breaking-space": ("at the centre of", "at the\u00a0centre of"),
}


def _plant_in_paragraph(page: Path, old: str, new: str) -> None:
    intent = _intent()
    source = page.read_text(encoding="utf-8")
    assert intent in source, "the page does not carry the constant verbatim, so there is nothing to change"
    assert intent.count(old) == 1, old
    page.write_text(source.replace(intent, intent.replace(old, new, 1), 1), encoding="utf-8")


@pytest.mark.parametrize("home", sorted(HOMES.values()))
@pytest.mark.parametrize("old, new", ONE_CHARACTER.values(), ids=list(ONE_CHARACTER))
def test_one_character_changed_in_a_built_page_is_flagged(sites: Path, home: str, old: str, new: str) -> None:
    _plant_in_paragraph(sites / home, old, new)
    found = intent_violations(sites)
    assert len(found) == 1 and found[0].startswith(home) and "differs from the constant" in found[0], found


@pytest.mark.parametrize("home", sorted(HOMES.values()))
@pytest.mark.parametrize("old, new", REFLOWED.values(), ids=list(REFLOWED))
def test_the_paragraph_reflowed_is_flagged(sites: Path, home: str, old: str, new: str) -> None:
    _plant_in_paragraph(sites / home, old, new)
    found = intent_violations(sites)
    assert len(found) == 1 and found[0].startswith(home) and "differs from the constant" in found[0], found


@pytest.mark.parametrize("home", sorted(HOMES.values()))
def test_the_constant_on_one_page_only_is_flagged(sites: Path, home: str) -> None:
    page = sites / home
    source = page.read_text(encoding="utf-8")
    page.write_text(INTENT_P.sub("", source), encoding="utf-8")
    assert intent_violations(sites) == [f"{home}: carries the paragraph 0 times, not once"]


def test_the_paragraph_twice_on_a_page_is_flagged(sites: Path) -> None:
    page = sites / HOMES["net"]
    source = page.read_text(encoding="utf-8")
    block = INTENT_P.search(source)
    assert block is not None
    page.write_text(source.replace(block.group(0), block.group(0) * 2, 1), encoding="utf-8")
    assert intent_violations(sites) == [f"{HOMES['net']}: carries the paragraph 2 times, not once"]


def test_a_paragraph_moved_off_the_opening_is_flagged(sites: Path) -> None:
    page = sites / HOMES["org"]
    source = page.read_text(encoding="utf-8")
    page.write_text(source.replace(' id="why"', ' id="elsewhere"', 1), encoding="utf-8")
    assert any("does not follow the opening statement" in v for v in placement_violations(sites))


def test_the_constant_changed_and_the_sites_rebuilt_is_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The constant's own use: the pages follow whatever the constant says, so the pages agree with it and only the
    owner's text, held here by its hash, can say the constant is wrong."""
    intent = _intent()
    variant = intent.replace("Open source is necessary but not sufficient", "Open source is necessary and sufficient", 1)
    assert variant != intent
    monkeypatch.setattr(BUILD, "INTENT", variant)
    BUILD.build(tmp_path)
    assert intent_violations(tmp_path, variant) == []
    assert constant_violations(BUILD) and any("SHA-256" in v for v in constant_violations(BUILD))
    assert intent_violations(tmp_path, intent), "the rebuilt pages should differ from the owner's paragraph"


def test_a_wrong_order_or_a_missing_name_of_the_five_is_flagged(sites: Path) -> None:
    page = sites / HOMES["org"]
    source = page.read_text(encoding="utf-8")
    swapped = source.replace("<h3>Privacy control</h3>", "<h3>TMP</h3>", 1).replace("<h3>Data sovereignty</h3>", "<h3>Privacy control</h3>", 1)
    page.write_text(swapped.replace("<h3>TMP</h3>", "<h3>Data sovereignty</h3>", 1), encoding="utf-8")
    assert any("the constraints are" in v for v in constraint_violations(sites))


def test_the_governance_page_without_a_name_is_flagged(sites: Path) -> None:
    page = sites / "org" / "governance.html"
    source = page.read_text(encoding="utf-8")
    assert "Security management" in source
    page.write_text(source.replace("Security management", "Security", 1), encoding="utf-8")
    assert any("org/governance.html" in v for v in constraint_violations(sites))


def test_a_constraint_with_three_sentences_or_no_link_is_flagged(sites: Path) -> None:
    page = sites / HOMES["org"]
    source = page.read_text(encoding="utf-8")
    page.write_text(source.replace("<h3>Privacy control</h3><p>", "<h3>Privacy control</h3><p>One. Two. Three. ", 1), encoding="utf-8")
    assert any(re.search(r"Privacy control has [3-9] sentences", v) for v in constraint_violations(sites))
    page.write_text(re.sub(r'(<h3>Analytical accountability</h3>.*?)<a href="[^"]*">', r'\1<a href="https://example.test/">', page.read_text(encoding="utf-8"), count=1, flags=re.DOTALL), encoding="utf-8")
    assert any("Analytical accountability links to" in v for v in constraint_violations(sites))


@pytest.mark.parametrize("sentence", OVERSTATED)
def test_each_overstated_sentence_is_flagged_when_planted_back(sites: Path, sentence: str) -> None:
    """In the shape the pages carry it: escaped as `build.py` escapes the overview's lines, in a paragraph of a page."""
    _plant(sites / "net" / "services.html", f"<p>{html.escape(sentence.capitalize(), quote=True)}.</p>")
    found = overstated(sites)
    assert any(repr(sentence) in v for v in found), found


@pytest.mark.parametrize("shape", sorted(OVERSTATED_SHAPES))
def test_each_overstated_shape_is_flagged(sites: Path, shape: str) -> None:
    example = {"nothing leaves": "Nothing leaves the site.", "never leaves": "The data never leaves.", "leaves no trace": "A row leaves no trace.",
               "append-only": "The table is append-only.", "every read": "Every read is kept."}[shape]
    _plant(sites / "org" / "features.html", f"<p>{example}</p>")
    assert any(f"shape {shape!r}" in v for v in overstated(sites))


def test_an_overstated_sentence_in_the_overview_is_flagged(sites: Path) -> None:
    """The overview's lines are escaped into the page as `html.escape` writes them, an apostrophe included."""
    page = sites / "org" / "index.html"
    source = page.read_text(encoding="utf-8")
    page.write_text(source.replace("</main>", f'<h3 class="ov-line">{html.escape("Who did what, and every read that was refused")}</h3></main>', 1), encoding="utf-8")
    assert any("every read that was refused" in v for v in overstated(sites))


@pytest.mark.parametrize("word", ["guarantee", "Guarantees", "guaranteed"])
def test_a_guarantee_outside_the_paragraph_is_flagged(sites: Path, word: str) -> None:
    _plant(sites / "net" / "contact.html", f"<p>We {word} that no one can see a record.</p>")
    found = guarantees(sites)
    assert len(found) == 1 and found[0].startswith("net/contact.html"), found


def test_the_paragraphs_own_guarantee_is_not_flagged_and_a_changed_paragraph_is_flagged_by_the_other_check(sites: Path) -> None:
    assert "guarantees" in _intent() and guarantees(sites) == []
    page = sites / HOMES["org"]
    page.write_text(page.read_text(encoding="utf-8").replace("software guarantees this", "software guarantees this, always", 1), encoding="utf-8")
    assert intent_violations(sites) and guarantees(sites)


def test_a_hosted_engine_without_the_words_opt_in_is_flagged(sites: Path) -> None:
    for p in pages(sites):
        p.write_text(re.sub(r"opt-in", "optional", p.read_text(encoding="utf-8"), flags=re.IGNORECASE), encoding="utf-8")
    assert "net/contact.html" not in hosted_without_opt_in(sites)
    _plant(sites / "net" / "contact.html", "<p>A hosted engine answers when asked.</p>")
    assert "net/contact.html" in hosted_without_opt_in(sites)


@pytest.mark.parametrize(
    "page, out, fault",
    [
        ("org/index.html", "base images", "software sovereignty lacks 'base images'"),
        ("org/index.html", "next release", "data sovereignty lacks 'next release'"),
        ("org/index.html", "sign-in", "security management lacks 'sign-in'"),
        ("org/public-sector.html", "map data", "the licence statement on org/public-sector.html lacks 'map data'"),
    ],
)
def test_the_licence_attribution_and_tracking_checks_are_red_when_a_claim_is_dropped(sites: Path, page: str, out: str, fault: str) -> None:
    path = sites / page
    path.write_text(path.read_text(encoding="utf-8").replace(out, "xxxx"), encoding="utf-8")
    assert fault in wording_violations(sites)


def test_the_older_site_carrying_the_paragraph_is_flagged(tmp_path: Path) -> None:
    copy = tmp_path / "deploy"
    shutil.copytree(DEPLOY, copy)
    page = copy / "public-sector.html"
    source = page.read_text(encoding="utf-8")
    page.write_text(source.replace("</body>", f"<p>{_intent()}</p></body>", 1), encoding="utf-8")
    assert deploy_carries_the_paragraph(copy) == ["public-sector.html"]
