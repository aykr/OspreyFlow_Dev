"""The fonts are listed once, in `packages/design/fonts.json`, and a test fails if either front end loads a font the
list does not name (ADR-152 decision 6, "tokens.css, primitives.css, fonts; read by the React workspace and tree-default
alike"; slice PL4b3, the fourth of the PL4 slices; the owner's ruling of 20 November 2026 on "the rest of the design
folder", item 3: `fonts.ts` may stay in the workspace because it is tied to the Vite bundle, but which families and
weights are used is stated once in `packages/design`, and both front ends load from that list, each its own way).

The list states what the code ships, and no weight in the code changed with it: Atkinson Hyperlegible Next 400, 600 and
700 and IBM Plex Mono 400 and 600 (SIL OFL 1.1, from `@fontsource`), and GDS Transport (from `govuk-frontend`,
self-hosted under `/assets/govuk/`), which carries its two conditions as fields of its own entry: shown only when the
GOV.UK identity switch is on (`appearance.govuk_identity`), and only on a gov.uk address.

Which test fails if the invariant is broken (rule 12):

* the list is malformed, has a field it should not (`subsets`), lacks a licence, or GDS Transport's conditions are
  missing or are on any other entry: `test_the_list_is_well_formed`, `test_gds_transport_carries_both_conditions_and_is_the_only_entry_with_them`
  and `test_the_list_names_only_faces_tokens_css_names`;
* the workspace (`apps/workspace`) or the keyboard and set-up harnesses (`apps/harness`) load a family or a weight the
  list does not name, or a listed `@fontsource` weight is imported by nothing, or a listed package is not declared:
  `test_the_workspace_and_the_harness_load_only_what_the_list_names`;
* any of those loads a font from outside the repository (a `<link>` to Google Fonts, as the design handoff files write
  it, an `@import`, a stylesheet from any other host, an external font file), or an `@font-face` of a listed name points
  `src` at a file the list does not own or at a URL: the same test (fonts are self-hosted; spec 00 section 6);
* the generated GOV.UK stylesheet, or a file in `public/assets/govuk/fonts/`, names a family the list does not (when the
  generated files exist; and always for the stylesheet the installed `govuk-frontend` ships, which the generator copies):
  `test_the_workspace_and_the_harness_load_only_what_the_list_names` and
  `test_the_installed_govuk_stylesheet_names_only_listed_families`;
* `apps/pages` (sources, views, static files and built output) loads a family or a font file the list does not name, or
  names GDS Transport at all (the font half of ADR-152 I9): `test_pages_loads_no_font_the_list_does_not_name_and_no_gds_transport`;
* `fonts.test.ts` restates the list instead of reading it: `test_fonts_test_ts_reads_the_list_and_does_not_restate_it`.

`apps/pages` loads no font today, so its scan has nothing to find on the real tree. Each rule is shown red on a planted
fault in the shape the real tree writes it (rule 15): the planted lines are taken from, or written as, the lines the real
call sites hold (`fonts.ts`'s own imports, the workspace's `package.json` line, `layout.njk`'s `</head>`, the two real
`@font-face` rules of `govuk-frontend`), each placed at the path of the file that would hold it. A plant that some other
rule would also have caught proves nothing, so each case first shows the same tree clean, and then asserts that exactly
one violation was found, and that it is the one the case is about. A plant of GDS Transport is written as a *listed*
family, so the list's own rule passes it and only the GDS Transport rule can catch it.

**The folders this test walks** (the conductor's scan-map row): under `OspreyFlow_Core`, `apps/workspace`,
`apps/harness`, `apps/pages` and `packages/design`; it reads only the text and font files in them, and never
`node_modules`, `dist` (except `apps/pages/dist`, the built output), `coverage`, `test-results`, `playwright-report` or,
for `apps/pages`, its own `test/` folder (a test of the pages may name GDS Transport in order to forbid it). The GDS
Transport rule leaves out `.yaml` records (`FUNCTIONS.yaml` names `/assets/govuk/*` in prose); a test file is held to the
`@fontsource` rule but not to the `@font-face` rule (it may hold a fixture). It also reads
`OspreyFlow_Core/node_modules/govuk-frontend/dist/govuk/govuk-frontend.min.css` when it is installed, and
`packages/design/fonts.json`.
"""

# The planted lines are the real call-site shapes, kept on one line as the tree writes them (rule 15), and the prose
# beside them names whole paths: neither is wrapped. `OspreyFlow_Build` is not under ruff's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import copy
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tools.layout import CORE

LIST_REL = "packages/design/fonts.json"
LIST = CORE / LIST_REL
FONTS_TS_REL = "apps/workspace/src/design/fonts.ts"
FONTS_TEST_TS = CORE / "apps/workspace/src/design/fonts.test.ts"
TOKENS = CORE / "packages/design/tokens.css"
INSTALLED_GOVUK_CSS = CORE / "node_modules/govuk-frontend/dist/govuk/govuk-frontend.min.css"

#: Walked under `OspreyFlow_Core`. The pages are walked on their own: their rule is stricter (no GDS Transport at all).
FRONT_END_WALK = ("apps/workspace", "apps/harness", "packages/design")
PAGES_WALK = ("apps/pages",)
#: Never read: dependencies and build or test output. `apps/pages/dist` is the one built output that is read.
SKIP_DIRS = frozenset({"node_modules", "dist", "coverage", "test-results", "playwright-report", "__pycache__", ".vite"})
#: A test of the pages may name GDS Transport in order to forbid it; it is not what the default tree serves.
PAGES_SKIPPED = ("apps/pages/test",)
TEXT_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".mjs", ".cjs", ".css", ".scss", ".html", ".njk", ".json", ".yaml", ".yml"})
FONT_SUFFIXES = frozenset({".woff", ".woff2", ".ttf", ".otf", ".eot"})

ROLES = frozenset({"ui", "mono", "govuk"})
BASE_KEYS = frozenset({"family", "role", "source", "weights", "licence"})
GOVUK_KEYS = BASE_KEYS | {"only_when", "only_on", "self_hosted_under", "file_stems"}
#: The fields only GDS Transport carries: its two conditions.
CONDITION_KEYS = frozenset({"only_when", "only_on"})

# ------------------------------------------------------------------------------------------------- reading the list


def load_list(path: Path = LIST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def entries(data: dict) -> list[dict]:
    return data["fonts"]


def by_family(data: dict) -> dict[str, dict]:
    return {e["family"].lower(): e for e in entries(data)}


def fontsource_entries(data: dict) -> list[dict]:
    return [e for e in entries(data) if e["source"].startswith("@fontsource/")]


def govuk_entries(data: dict) -> list[dict]:
    return [e for e in entries(data) if e["role"] == "govuk"]


def list_violations(data: dict) -> list[str]:
    """What is wrong with the list itself: its shape, its licences, and where GDS Transport's conditions are."""
    if not isinstance(data, dict) or set(data) != {"fonts"} or not isinstance(data["fonts"], list) or not data["fonts"]:
        return ["the list is not an object with one non-empty `fonts` array"]
    out: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(data["fonts"]):
        name = entry.get("family", f"entry {index}") if isinstance(entry, dict) else f"entry {index}"
        if not isinstance(entry, dict):
            out.append(f"{name}: not an object")
            continue
        govuk = entry.get("role") == "govuk"
        allowed = GOVUK_KEYS if govuk else BASE_KEYS
        for key in sorted(set(entry) - allowed):
            out.append(f"{name}: has the field `{key}`, which the list does not define" + (" (no subsets: narrowing the imports would change the built bytes)" if key == "subsets" else ""))
        for key in sorted(allowed - set(entry)):
            out.append(f"{name}: lacks the field `{key}`")
        if set(entry) < allowed:
            continue
        if entry["role"] not in ROLES:
            out.append(f"{name}: role {entry['role']!r} is not one of ui, mono, govuk")
        if entry["family"].lower() in seen:
            out.append(f"{name}: listed twice")
        seen.add(entry["family"].lower())
        weights = entry["weights"]
        if not weights or weights != sorted(set(weights)) or any(not isinstance(w, int) or w % 100 or not 100 <= w <= 900 for w in weights):
            out.append(f"{name}: weights {weights!r} are not a sorted list of distinct hundreds from 100 to 900")
        if not isinstance(entry["licence"], str) or not entry["licence"].strip():
            out.append(f"{name}: no licence")
        if govuk:
            out += _gds_violations(name, entry)
        else:
            if not re.fullmatch(r"@fontsource/[a-z0-9-]+", entry["source"]):
                out.append(f"{name}: source {entry['source']!r} is not `@fontsource/<package>`")
            if entry["licence"] != "OFL-1.1":
                out.append(f"{name}: licence {entry['licence']!r} is not OFL-1.1")
    roles = [e.get("role") for e in data["fonts"] if isinstance(e, dict)]
    for role in sorted(ROLES):
        if roles.count(role) != 1:
            out.append(f"the list names {roles.count(role)} faces for the role {role}, not one")
    return out


def _gds_violations(name: str, entry: dict) -> list[str]:
    out: list[str] = []
    if entry["source"] != "govuk-frontend":
        out.append(f"{name}: source {entry['source']!r} is not `govuk-frontend`")
    if entry["only_when"] != "appearance.govuk_identity":
        out.append(f"{name}: not conditioned on the identity switch `appearance.govuk_identity` (only_when is {entry['only_when']!r})")
    if entry["only_on"] != "gov.uk":
        out.append(f"{name}: not conditioned on a gov.uk address (only_on is {entry['only_on']!r})")
    if entry["self_hosted_under"] != "/assets/govuk/":
        out.append(f"{name}: not self-hosted under /assets/govuk/")
    if "GOV.UK" not in entry["licence"] or re.search(r"OFL-\d", entry["licence"]):
        out.append(f"{name}: its licence must say it is restricted to services on GOV.UK domains, and is not OFL")
    stems = entry["file_stems"]
    if not isinstance(stems, list) or not stems or not all(isinstance(s, str) and re.fullmatch(r"[a-z]+", s) for s in stems):
        out.append(f"{name}: file_stems must be a list of the stems its files in fonts/ begin with")
    return out


# ---------------------------------------------------------------------------------------------------- the scanners


@dataclass
class Scan:
    violations: list[str] = field(default_factory=list)
    #: Files read, relative to the core folder: a scan with nothing to find must still show it looked.
    read: list[str] = field(default_factory=list)
    #: `(source, weight)` imported from the workspace's own `src`.
    imported: set[tuple[str, int]] = field(default_factory=set)
    #: Sources declared in the workspace's `package.json`.
    declared: set[str] = field(default_factory=set)


def walk_files(core: Path, folders: tuple[str, ...], skipped: tuple[str, ...] = ()) -> list[Path]:
    found: list[Path] = []
    for folder in folders:
        top = core / folder
        if not top.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            here = Path(dirpath).relative_to(core).as_posix()
            dirnames[:] = sorted(
                d
                for d in dirnames
                # `dist` is a skipped name everywhere but under the pages, whose built output is scanned.
                if (d not in SKIP_DIRS or (d == "dist" and here == "apps/pages")) and f"{here}/{d}" not in skipped
            )
            found += [Path(dirpath) / n for n in sorted(filenames) if Path(n).suffix in TEXT_SUFFIXES | FONT_SUFFIXES]
    return found


FONTSOURCE_SPEC = re.compile(r"""["'`](@fontsource(?:-variable)?/[^"'`\s]+)["'`]""")
FONT_FACE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)
FONT_REF = re.compile(r"[\w@./\-]+\.(?:woff2?|ttf|otf|eot)\b")
#: A URL that leaves the repository: with a scheme anywhere, or protocol-relative straight after a quote, a bracket or `=`
#: (a bare `//` is a comment in the languages scanned).
EXTERNAL_URL = re.compile(r"""https?://[^\s"'()<>\\]+|(?<=["'(=])//[^\s"'()<>\\/][^\s"'()<>\\]*""", re.I)
#: The hosts that serve fonts or font stylesheets: a `<link>` to one is how the design handoff's own files load a face.
FONT_HOSTS = re.compile(r"(?:fonts\.googleapis\.com|fonts\.gstatic\.com|use\.typekit\.net|fonts\.bunny\.net|fast\.fonts\.net|fonts\.adobe\.com|cloud\.typography\.com|use\.fontawesome\.com|kit\.fontawesome\.com)", re.I)
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I | re.S)
IMPORT_URL = re.compile(r"""@import\s+(?:url\(\s*)?["']?([^\s"')]+)""", re.I)
FACE_URL = re.compile(r"""url\(\s*["']?([^"')]+?)["']?\s*\)""", re.I)


def _is_external(ref: str) -> bool:
    return bool(re.match(r"(?:https?:)?//", ref.strip(), re.I))


def _stylesheet_urls(text: str) -> set[str]:
    """What the text pulls in as a stylesheet: a `<link rel=stylesheet href=...>`, or an `@import`."""
    found = {m.group(1) for m in IMPORT_URL.finditer(text)}
    for tag in LINK_TAG.findall(text):
        if re.search(r"""\brel\s*=\s*["']?[^"'>]*\bstylesheet\b""", tag, re.I):
            found.update(re.findall(r"""\bhref\s*=\s*["']?([^\s"'>]+)""", tag, re.I))
    return found


def is_test_file(path: Path) -> bool:
    return bool(re.search(r"\.(?:test|spec)\.[cm]?[jt]sx?$", path.name))


def _weight(file: str | None) -> int | None:
    """The weight a `@fontsource/<package>/<file>` import loads: `400.css` is 400; the bare package is its default, 400."""
    if file is None or file == "index.css":
        return 400
    found = re.fullmatch(r"(\d{3})\.css", file)
    return int(found.group(1)) if found else None


def _face_weights(declared: str) -> list[int | None]:
    names = {"normal": 400, "bold": 700}
    return [int(t) if t.isdigit() else names.get(t.lower()) for t in declared.split()]


def _gds_names(data: dict) -> list[str]:
    return [e["family"] for e in govuk_entries(data)]


#: How @fontsource names a file: `<package>-<subset>-<weight>-<style>.<ext>`, as `ibm-plex-mono-latin-400-normal.woff2`.
FONTSOURCE_FILE = r"{package}-[a-z0-9]+(?:-[a-z0-9]+)*?-(?P<weight>\d{{3}})-(?P<style>normal|italic)\.[a-z0-9]+"
UNOWNED = "no listed family owns it"


def _font_file_fault(ref: str, data: dict) -> str | None:
    """Why a font file (or a URL to one) is not the list's, or None when it is. A file is the list's when it belongs to a
    listed `@fontsource` package *at a weight and a style the list names* (the file name carries both), or is one of the
    stems the GDS Transport entry names under its own folder. UNOWNED is the answer for a file no listed family owns."""
    name = ref.replace("\\", "/")
    base = name.rsplit("/", 1)[-1].split("?")[0].split("#")[0]
    for entry in fontsource_entries(data):
        package = entry["source"].removeprefix("@fontsource/")
        if package not in name:
            continue
        parsed = re.fullmatch(FONTSOURCE_FILE.format(package=re.escape(package)), base, re.I)
        if parsed is None:
            return f"a file of {entry['family']} whose weight and style the list cannot be read against"
        if parsed.group("style").lower() != "normal":
            return f"the {parsed.group('style').lower()} style of {entry['family']}, which the list does not name"
        if int(parsed.group("weight")) not in entry["weights"]:
            return f"weight {int(parsed.group('weight'))} of {entry['family']}, which the list does not name"
        return None
    for entry in govuk_entries(data):
        folder = entry["self_hosted_under"].strip("/") + "/fonts/"
        if folder in name and any(base.startswith(stem + "-") for stem in entry["file_stems"]):
            return None
    return UNOWNED


def scan(core: Path, data: dict, folders: tuple[str, ...], skipped: tuple[str, ...] = (), *, no_gds: bool = False) -> Scan:
    """Every family, weight and font file the folders load, against the list. `no_gds` is the pages' rule: GDS Transport
    is not on a page of the default tree, whatever the list says of it."""
    result = Scan()
    families = by_family(data)
    sources = {e["source"]: e for e in fontsource_entries(data)}
    gds = [re.compile(r"[\s_-]*".join(map(re.escape, name.lower().split())), re.I) for name in _gds_names(data)]
    # Its stylesheet and files, self-hosted under the folder the entry names, are how a page would load it.
    gds += [re.compile(re.escape(e["self_hosted_under"].strip("/") + "/"), re.I) for e in govuk_entries(data)]
    for path in walk_files(core, folders, skipped):
        rel = path.relative_to(core).as_posix()
        if path.suffix in FONT_SUFFIXES:
            result.read.append(rel)
            if (fault := _font_file_fault(rel, data)) == UNOWNED:
                result.violations.append(f"{rel}: a font file that no listed family owns")
            elif fault:
                result.violations.append(f"{rel}: a font file, {fault}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        result.read.append(rel)
        # The `@fontsource` packages: imported, or declared in a package.json.
        for spec in FONTSOURCE_SPEC.findall(text):
            parts = spec.split("/")
            source, file = "/".join(parts[:2]), "/".join(parts[2:]) or None
            entry = sources.get(source)
            if entry is None:
                result.violations.append(f"{rel}: loads {spec}, a family the list does not name")
            elif path.name == "package.json":
                if rel == "apps/workspace/package.json":
                    result.declared.add(source)
            elif (weight := _weight(file)) is None:
                result.violations.append(f"{rel}: loads {spec}, whose weight the list cannot be read against")
            elif weight not in entry["weights"]:
                result.violations.append(f"{rel}: loads {spec}, weight {weight}, which the list does not name for {entry['family']}")
            elif rel.startswith("apps/workspace/src/"):
                result.imported.add((source, weight))
        if is_test_file(path):
            continue  # a fixture about fonts is not a load: nothing serves a test file
        # `@font-face` rules: the family, and the weight it is declared for.
        for block in FONT_FACE.findall(text):
            family_m = re.search(r"font-family\s*:\s*([^;}]+)", block)
            family = family_m.group(1).strip().strip("'\"").strip() if family_m else ""
            entry = families.get(family.lower())
            if entry is None:
                result.violations.append(f"{rel}: an @font-face for {family or '(no family)'!r}, which the list does not name")
                continue
            weight_m = re.search(r"font-weight\s*:\s*([^;}]+)", block)
            for weight in _face_weights(weight_m.group(1)) if weight_m else []:
                if weight not in entry["weights"]:
                    result.violations.append(f"{rel}: an @font-face for {entry['family']} at weight {weight}, which the list does not name")
        # The files an `@font-face` points at are held to the list too: a listed name over an unlisted file loads an
        # unlisted font, and one over a URL outside the repository is not self-hosted.
        for block in FONT_FACE.findall(text):
            family_m = re.search(r"font-family\s*:\s*([^;}]+)", block)
            if (family_m.group(1).strip().strip("'\"").strip().lower() if family_m else "") not in families:
                continue  # an unlisted family is reported above, once, for the family
            for ref in FACE_URL.findall(block):
                if _is_external(ref):
                    result.violations.append(f"{rel}: an @font-face loads {ref}, from outside the repository: fonts are self-hosted")
                elif (fault := _font_file_fault(ref, data)) == UNOWNED:
                    result.violations.append(f"{rel}: an @font-face loads {ref}, which no listed family owns")
                elif fault:
                    result.violations.append(f"{rel}: an @font-face loads {ref}, {fault}")
        rest = FONT_FACE.sub("", text)
        # A font file named outside an `@font-face` (a preload, a `url(...)`); an external one is reported below.
        for ref in FONT_REF.findall(rest):
            if ref.startswith("//"):
                continue
            if (fault := _font_file_fault(ref, data)) == UNOWNED:
                result.violations.append(f"{rel}: names the font file {ref}, which no listed family owns")
            elif fault:
                result.violations.append(f"{rel}: names the font file {ref}, {fault}")
        # What leaves the repository: a font host, an external font file, or an external stylesheet (a `<link>` or an
        # `@import`, which can load any family at any weight). Each URL is reported once, however it was found.
        sheets = _stylesheet_urls(rest)
        for url in dict.fromkeys(EXTERNAL_URL.findall(rest) + [u for u in sheets if _is_external(u)]):
            if FONT_HOSTS.search(url):
                result.violations.append(f"{rel}: loads {url}, from a font host: fonts are self-hosted from the list")
            elif re.search(r"\.(?:woff2?|ttf|otf|eot)(?:[?#]|$)", url, re.I):
                result.violations.append(f"{rel}: names the font file {url}, from outside the repository")
            elif url in sheets:
                result.violations.append(f"{rel}: pulls in the stylesheet {url} from outside the repository, which can load a font the list does not name")
        # The records beside the service (`FUNCTIONS.yaml` names `/assets/govuk/*` in prose) are not served.
        if no_gds and path.suffix not in {".yaml", ".yml"} and any(pattern.search(text) for pattern in gds):
            result.violations.append(f"{rel}: names GDS Transport (or its self-hosted assets), which the default tree does not serve (ADR-152 I9)")
    return result


def front_end_violations(core: Path, data: dict) -> Scan:
    """The workspace and the harnesses, against the list; and every listed `@fontsource` weight imported."""
    result = scan(core, data, FRONT_END_WALK)
    for entry in fontsource_entries(data):
        if entry["source"] not in result.declared:
            result.violations.append(f"apps/workspace/package.json: does not declare {entry['source']}, which the list names")
        for weight in entry["weights"]:
            if (entry["source"], weight) not in result.imported:
                result.violations.append(f"apps/workspace/src: {entry['family']} {weight} is on the list and nothing imports it")
    return result


def pages_violations(core: Path, data: dict) -> Scan:
    return scan(core, data, PAGES_WALK, PAGES_SKIPPED, no_gds=True)


# ----------------------------------------------------------------------------------------------------- the real tree


def test_the_list_is_well_formed() -> None:
    """One entry per family, the fields the list defines and no others (no `subsets`), a licence on each, the roles
    ui, mono and govuk once each: and the weights are those the code ships, which the next tests hold the code to."""
    data = load_list()
    assert list_violations(data) == []
    assert [(e["family"], e["role"], e["source"]) for e in entries(data)] == [
        ("Atkinson Hyperlegible Next", "ui", "@fontsource/atkinson-hyperlegible-next"),
        ("IBM Plex Mono", "mono", "@fontsource/ibm-plex-mono"),
        ("GDS Transport", "govuk", "govuk-frontend"),
    ]


def test_gds_transport_carries_both_conditions_and_is_the_only_entry_with_them() -> None:
    data = load_list()
    (gds,) = govuk_entries(data)
    assert gds["only_when"] == "appearance.govuk_identity"
    assert gds["only_on"] == "gov.uk"
    assert gds["self_hosted_under"] == "/assets/govuk/"
    assert "GOV.UK" in gds["licence"]
    others = [e for e in entries(data) if e is not gds]
    assert others
    assert all(not (CONDITION_KEYS & set(e)) for e in others)


def test_the_list_names_only_faces_tokens_css_names() -> None:
    """`tokens.css` is where a face is drawn from; a listed family it never names is a font nothing uses."""
    css = TOKENS.read_text(encoding="utf-8")
    for entry in entries(load_list()):
        assert re.search(rf"""["']{re.escape(entry['family'])}["']""", css), f"tokens.css does not name {entry['family']}"


def test_the_workspace_and_the_harness_load_only_what_the_list_names() -> None:
    result = front_end_violations(CORE, load_list())
    assert result.violations == []
    # The scan is not empty: it read the one file that holds the imports, and the workspace's package.json.
    assert FONTS_TS_REL in result.read
    assert "apps/workspace/package.json" in result.read
    assert "apps/harness/src/main.tsx" in result.read
    assert result.imported == {
        (e["source"], w) for e in fontsource_entries(load_list()) for w in e["weights"]
    }


def test_pages_loads_no_font_the_list_does_not_name_and_no_gds_transport() -> None:
    """Nothing to find today, and shown to have looked: it read the service's own sources and views."""
    result = pages_violations(CORE, load_list())
    assert result.violations == []
    assert "apps/pages/server/views/layout.njk" in result.read
    assert "apps/pages/package.json" in result.read


def test_the_installed_govuk_stylesheet_names_only_listed_families() -> None:
    """The stylesheet `sync_govuk_assets.mjs` copies: its `@font-face` rules are what the generated copy carries."""
    if not INSTALLED_GOVUK_CSS.is_file():
        pytest.skip("govuk-frontend is not installed in this checkout")
    data = load_list()
    text = INSTALLED_GOVUK_CSS.read_text(encoding="utf-8")
    faces = FONT_FACE.findall(text)
    assert faces, "the package's stylesheet carries no @font-face: the scan below would find nothing"
    for block in faces:
        family = re.search(r"font-family\s*:\s*([^;}]+)", block).group(1).strip().strip("'\"")  # type: ignore[union-attr]
        entry = by_family(data).get(family.lower())
        assert entry is not None, f"govuk-frontend ships a face the list does not name: {family}"
        weight = re.search(r"font-weight\s*:\s*(\d+)", block)
        assert weight is not None and int(weight.group(1)) in entry["weights"]
    stems = {m.group(1).rsplit("/", 1)[-1].split("-")[0] for m in re.finditer(r"url\((/assets/fonts/[^)]+)\)", text)}
    (gds,) = govuk_entries(data)
    assert stems == set(gds["file_stems"])


def test_fonts_test_ts_reads_the_list_and_does_not_restate_it() -> None:
    text = FONTS_TEST_TS.read_text(encoding="utf-8")
    assert fonts_test_restates_the_list(text) == []


def fonts_test_restates_the_list(text: str) -> list[str]:
    out: list[str] = []
    if "fonts.json" not in text:
        out.append("fonts.test.ts does not read fonts.json")
    for literal in re.findall(r"""["'`]@fontsource(?:-variable)?/[^"'`/][^"'`]*["'`]""", text):
        out.append(f"fonts.test.ts restates {literal}")
    return out


# ----------------------------------------------------------------------------------------- each rule, shown red


def _real(rel: str) -> str:
    return (CORE / rel).read_text(encoding="utf-8")


#: The two `@font-face` rules `govuk-frontend` 6.6.0 ships for GDS Transport, as the generator rewrites them.
REAL_GDS_FACES = (
    "@font-face{font-family:GDS Transport;font-style:normal;font-weight:400;font-display:fallback;src:url(/assets/govuk/fonts/light-94a07e06a1-v2.woff2) format(\"woff2\"),url(/assets/govuk/fonts/light-f591b13f7d-v2.woff) format(\"woff\")}\n"
    "@font-face{font-family:GDS Transport;font-style:normal;font-weight:700;font-display:fallback;src:url(/assets/govuk/fonts/bold-b542beb274-v2.woff2) format(\"woff2\"),url(/assets/govuk/fonts/bold-affa96571d-v2.woff) format(\"woff\")}\n"
)
#: What `@fontsource/atkinson-hyperlegible-next/400.css` writes for its face, to the shape.
REAL_FONTSOURCE_FACE = (
    "@font-face {\n  font-family: 'Atkinson Hyperlegible Next';\n  font-style: normal;\n  font-display: swap;\n  font-weight: 400;\n"
    "  src: url(./files/atkinson-hyperlegible-next-latin-400-normal.woff2) format('woff2');\n}\n"
)


def build_tree(root: Path) -> Path:
    """A small core folder holding the real text of the files the rules read, at their real paths."""
    files = {
        FONTS_TS_REL: _real(FONTS_TS_REL),
        "apps/workspace/package.json": _real("apps/workspace/package.json"),
        "apps/harness/src/main.tsx": _real("apps/harness/src/main.tsx"),
        "apps/workspace/index.html": _real("apps/workspace/index.html"),
        "apps/harness/index.html": _real("apps/harness/index.html"),
        "apps/pages/server/views/layout.njk": _real("apps/pages/server/views/layout.njk"),
        "apps/pages/package.json": _real("apps/pages/package.json"),
        "apps/workspace/public/assets/govuk/govuk-frontend.css": "/* GENERATED */\n" + REAL_GDS_FACES,
        "apps/workspace/public/assets/govuk/fonts/light-94a07e06a1-v2.woff2": "",
        "apps/workspace/public/assets/govuk/fonts/bold-b542beb274-v2.woff2": "",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def _front(core: Path, data: dict | None = None) -> list[str]:
    return front_end_violations(core, data or load_list()).violations


def _pages(core: Path, data: dict | None = None) -> list[str]:
    return pages_violations(core, data or load_list()).violations


def _edit(core: Path, rel: str, change: Callable[[str], str]) -> None:
    path = core / rel
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    after = change(before)
    assert after != before, f"the plant changed nothing in {rel}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(after, encoding="utf-8")


def _append(line: str) -> Callable[[str], str]:
    return lambda text: text + ("" if text.endswith("\n") or not text else "\n") + line + "\n"


def _after(anchor: str, line: str) -> Callable[[str], str]:
    def change(text: str) -> str:
        assert anchor in text, f"the real file no longer holds {anchor!r}: the plant's shape is stale"
        return text.replace(anchor, anchor + line, 1)

    return change


def _before(anchor: str, line: str) -> Callable[[str], str]:
    def change(text: str) -> str:
        assert anchor in text, f"the real file no longer holds {anchor!r}: the plant's shape is stale"
        return text.replace(anchor, line + anchor, 1)

    return change


def _without(line: str) -> Callable[[str], str]:
    def change(text: str) -> str:
        assert line in text, f"the real file no longer holds {line!r}: the plant's shape is stale"
        return text.replace(line, "", 1)

    return change


def test_the_tree_the_plants_are_made_in_is_clean(tmp_path: Path) -> None:
    core = build_tree(tmp_path)
    assert _front(core) == []
    assert _pages(core) == []


FRONT_PLANTS: list[tuple[str, str, Callable[[str], str], str]] = [
    # An unlisted `@fontsource` import in `fonts.ts`, as `fonts.ts` writes one.
    ("an unlisted family imported in fonts.ts", FONTS_TS_REL, _append('import "@fontsource/roboto/400.css";'), "loads @fontsource/roboto/400.css, a family the list does not name"),
    # A listed family at a weight the list does not name for it.
    ("a listed family at an unlisted weight", FONTS_TS_REL, _append('import "@fontsource/ibm-plex-mono/700.css";'), "weight 700, which the list does not name for IBM Plex Mono"),
    # The bare package (its default weight, 400) of an unlisted family.
    ("an unlisted family imported bare", "apps/harness/src/main.tsx", _after('import "../../../packages/design/primitives.css";', '\nimport "@fontsource/inter";'), "loads @fontsource/inter, a family the list does not name"),
    # A variable face from the other scope.
    ("an unlisted variable family declared", "apps/workspace/package.json", _after('"@fontsource/ibm-plex-mono": "5.3.0",', '\n    "@fontsource-variable/inter": "5.2.0",'), "loads @fontsource-variable/inter, a family the list does not name"),
    # A listed weight nothing imports any more (the line `fonts.ts` holds).
    ("a listed weight no longer imported", FONTS_TS_REL, _without('import "@fontsource/ibm-plex-mono/600.css";\n'), "IBM Plex Mono 600 is on the list and nothing imports it"),
    # A listed package the workspace stopped declaring.
    ("a listed package no longer declared", "apps/workspace/package.json", _without('    "@fontsource/ibm-plex-mono": "5.3.0",\n'), "does not declare @fontsource/ibm-plex-mono"),
    # An `@font-face` of an unlisted family, as @fontsource writes its rule, in a workspace stylesheet.
    ("an unlisted @font-face in the workspace", "apps/workspace/src/design/extra.css", _append(REAL_FONTSOURCE_FACE.replace("Atkinson Hyperlegible Next", "Comic Neue")), "an @font-face for 'Comic Neue', which the list does not name"),
    # The generated GOV.UK stylesheet gains a face the list does not name.
    ("an unlisted face in the generated GOV.UK stylesheet", "apps/workspace/public/assets/govuk/govuk-frontend.css", _append(REAL_GDS_FACES.splitlines()[0].replace("GDS Transport", "Comic Neue")), "an @font-face for 'Comic Neue'"),
    # GDS Transport at a weight the list does not name for it.
    ("GDS Transport at an unlisted weight", "apps/workspace/public/assets/govuk/govuk-frontend.css", _append(REAL_GDS_FACES.splitlines()[0].replace("font-weight:400", "font-weight:600")), "an @font-face for GDS Transport at weight 600"),
    # A file in the generated fonts folder that is not one of GDS Transport's.
    ("an unlisted file in the generated fonts folder", "apps/workspace/public/assets/govuk/fonts/comic-neue-1a2b3c-v2.woff2", _append("x"), "a font file that no listed family owns"),
    # A hosted font stylesheet, as the repository's own design handoff files load their faces (a `<link>` in the head),
    # with the weight (500) and the span (200..800) the list does not name: in the workspace's page, and in a harness's.
    ("a hosted Google Fonts stylesheet linked from the workspace page", "apps/workspace/index.html", _before("</head>", '<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@200..800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">'), "loads https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next"),
    ("a hosted Google Fonts stylesheet linked from a harness page", "apps/harness/index.html", _before("</head>", '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500&display=swap">'), "loads https://fonts.googleapis.com/css2?family=IBM+Plex+Mono"),
    # The same stylesheet pulled in from a workspace stylesheet, and a protocol-relative one.
    ("a hosted font stylesheet imported by a workspace stylesheet", "apps/workspace/src/design/extra.css", _append('@import url("https://fonts.googleapis.com/css2?family=Roboto:wght@400&display=swap");'), "loads https://fonts.googleapis.com/css2?family=Roboto"),
    ("a protocol-relative hosted font stylesheet", "apps/workspace/index.html", _before("</head>", '<link rel="stylesheet" href="//fonts.bunny.net/css?family=roboto:400">'), "loads //fonts.bunny.net/css?family=roboto:400"),
    # A stylesheet from any other host: it can load any family, so the list cannot name what it loads.
    ("an external stylesheet that is not a font host", "apps/workspace/index.html", _before("</head>", '<link rel="stylesheet" href="https://cdn.example.test/site.css">'), "pulls in the stylesheet https://cdn.example.test/site.css from outside the repository"),
    ("an external stylesheet imported by a harness stylesheet", "apps/harness/src/extra.css", _append('@import "https://cdn.example.test/site.css";'), "pulls in the stylesheet https://cdn.example.test/site.css"),
    # A font file on another host, named outside an `@font-face`.
    ("an external font file named in a stylesheet", "apps/workspace/src/design/extra.css", _append("a{background:url(https://fonts.example.test/roboto-400.woff2)}"), "names the font file https://fonts.example.test/roboto-400.woff2, from outside the repository"),
    # A listed name over a file the list does not name: the `src` of the rule is held to the list, not only its family.
    ("a listed family whose @font-face points at a hosted file", "apps/workspace/src/design/extra.css", _append("@font-face{font-family:'IBM Plex Mono';font-weight:400;src:url(https://fonts.gstatic.com/s/roboto/v30/x.woff2)}"), "an @font-face loads https://fonts.gstatic.com/s/roboto/v30/x.woff2, from outside the repository"),
    ("a listed family whose @font-face points at an unlisted local file", "apps/workspace/src/design/extra.css", _append(REAL_FONTSOURCE_FACE.replace("atkinson-hyperlegible-next-latin-400-normal.woff2", "roboto-latin-400-normal.woff2")), "an @font-face loads ./files/roboto-latin-400-normal.woff2, which no listed family owns"),
    # A listed family's own file at a weight or a style the list does not name: the declared weight (400) passes, the file is 500.
    ("a listed family whose @font-face declares 400 and serves the 500 file", "apps/workspace/src/design/extra.css", _append("@font-face{font-family:'IBM Plex Mono';font-weight:400;src:url(./files/ibm-plex-mono-latin-500-normal.woff2) format('woff2')}"), "an @font-face loads ./files/ibm-plex-mono-latin-500-normal.woff2, weight 500 of IBM Plex Mono, which the list does not name"),
    ("a listed family whose @font-face serves its italic file", "apps/workspace/src/design/extra.css", _append(REAL_FONTSOURCE_FACE.replace("latin-400-normal", "latin-400-italic")), "the italic style of Atkinson Hyperlegible Next, which the list does not name"),
    ("a listed family's file at an unlisted weight in the generated fonts folder", "apps/workspace/public/assets/govuk/fonts/ibm-plex-mono-latin-500-normal.woff2", _append("x"), "a font file, weight 500 of IBM Plex Mono, which the list does not name"),
    ("a listed family whose @font-face points at a file with no font extension", "apps/workspace/src/design/extra.css", _append("@font-face{font-family:'IBM Plex Mono';font-weight:400;src:url(https://fonts.gstatic.com/l/font?kit=abc)}"), "an @font-face loads https://fonts.gstatic.com/l/font?kit=abc, from outside the repository"),
]


@pytest.mark.parametrize(("case", "rel", "change", "expected"), FRONT_PLANTS, ids=[p[0] for p in FRONT_PLANTS])
def test_the_workspace_scan_is_red_for_each_planted_fault(tmp_path: Path, case: str, rel: str, change: Callable[[str], str], expected: str) -> None:
    core = build_tree(tmp_path)
    assert _front(core) == [], "the tree must be clean before the plant"
    _edit(core, rel, change)
    found = _front(core)
    assert len(found) == 1 and expected in found[0], found


LAYOUT_HEAD = "</head>"
PAGES_PLANTS: list[tuple[str, str, Callable[[str], str], str]] = [
    # An unlisted `@font-face` in a pages view, written into the layout's head.
    ("an unlisted @font-face in a pages view", "apps/pages/server/views/layout.njk", (lambda t: t.replace(LAYOUT_HEAD, "<style>" + REAL_FONTSOURCE_FACE.replace("Atkinson Hyperlegible Next", "Comic Neue").replace("\n", "") + "</style>" + LAYOUT_HEAD, 1)), "an @font-face for 'Comic Neue', which the list does not name"),
    # The same fault in the built output, which the image carries.
    ("an unlisted @font-face in the built output", "apps/pages/dist/server/views/layout.njk", _append("<style>" + REAL_FONTSOURCE_FACE.replace("Atkinson Hyperlegible Next", "Comic Neue").replace("\n", "") + "</style>"), "an @font-face for 'Comic Neue'"),
    # An unlisted `@fontsource` import, in a pages source, and the package declared by the service's package.json.
    ("an unlisted @fontsource import in a pages source", "apps/pages/server/app.ts", _append('import "@fontsource/roboto/400.css";'), "loads @fontsource/roboto/400.css, a family the list does not name"),
    ("an unlisted @fontsource package in the pages' package.json", "apps/pages/package.json", _after('"express-session": "1.19.0",', '\n    "@fontsource/roboto": "5.3.0",'), "loads @fontsource/roboto, a family the list does not name"),
    # A font file the list does not own, in a static folder.
    ("an unlisted font file among the pages' static files", "apps/pages/server/static/fonts/comic-neue-latin-400-normal.woff2", _append("x"), "a font file that no listed family owns"),
    # A listed family's own file at a weight the list does not name, in a static folder and as a preload.
    ("a listed family's file at an unlisted weight among the pages' static files", "apps/pages/server/static/fonts/ibm-plex-mono-latin-500-normal.woff2", _append("x"), "a font file, weight 500 of IBM Plex Mono, which the list does not name"),
    ("a listed family's file at an unlisted weight preloaded by a view", "apps/pages/server/views/layout.njk", lambda t: t.replace(LAYOUT_HEAD, '<link rel="preload" href="/fonts/ibm-plex-mono-latin-500-normal.woff2" as="font" crossorigin>' + LAYOUT_HEAD, 1), "names the font file /fonts/ibm-plex-mono-latin-500-normal.woff2, weight 500 of IBM Plex Mono"),
    # A bare font URL, as a preload `<link>` in a view writes it.
    ("an unlisted font preloaded by a view", "apps/pages/server/views/layout.njk", lambda t: t.replace(LAYOUT_HEAD, '<link rel="preload" href="/fonts/comic-neue-latin-400-normal.woff2" as="font" crossorigin>' + LAYOUT_HEAD, 1), "names the font file /fonts/comic-neue-latin-400-normal.woff2"),
    # GDS Transport in a pages stylesheet, as the GOV.UK brand's own token writes it: a *listed* family, so the list passes it.
    ("GDS Transport in a pages stylesheet", "apps/pages/server/static/app.css", _append('body{font-family:"GDS Transport",arial,sans-serif}'), "names GDS Transport"),
    # GDS Transport as a listed `@font-face` (the list passes it; only the GDS rule can catch it), as the generator writes it.
    ("a GDS Transport @font-face in the built output", "apps/pages/dist/server/static/govuk.css", _append(REAL_GDS_FACES.splitlines()[0]), "names GDS Transport"),
    # A hosted font stylesheet linked from the layout's head (the pages' CSP and page.test.ts also refuse it; this names the font).
    ("a hosted Google Fonts stylesheet linked from a pages view", "apps/pages/server/views/layout.njk", lambda t: t.replace(LAYOUT_HEAD, '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">' + LAYOUT_HEAD, 1), "loads https://fonts.googleapis.com/css2?family=IBM+Plex+Mono"),
    # The font folder of the GOV.UK assets named from a view.
    ("the GOV.UK fonts folder named from a view", "apps/pages/server/views/layout.njk", lambda t: t.replace(LAYOUT_HEAD, '<link rel="stylesheet" href="/assets/govuk/govuk-frontend.css">' + LAYOUT_HEAD, 1), "names GDS Transport"),
]


@pytest.mark.parametrize(("case", "rel", "change", "expected"), PAGES_PLANTS, ids=[p[0] for p in PAGES_PLANTS])
def test_the_pages_scan_is_red_for_each_planted_fault(tmp_path: Path, case: str, rel: str, change: Callable[[str], str], expected: str) -> None:
    core = build_tree(tmp_path)
    assert _pages(core) == [], "the tree must be clean before the plant"
    _edit(core, rel, change)
    found = _pages(core)
    assert len(found) == 1 and expected in found[0], found


def test_a_listed_face_in_the_pages_is_not_a_fault(tmp_path: Path) -> None:
    """The scan names what is not the list's; a family the list names, loaded from its own package's file, passes. (The
    page build that first loads a font, PL7, adds `@fontsource` to the pages' package.json and loads a listed face.)"""
    core = build_tree(tmp_path)
    _edit(core, "apps/pages/server/static/fonts.css", _append(REAL_FONTSOURCE_FACE))
    _edit(core, "apps/pages/server/static/fonts/atkinson-hyperlegible-next-latin-400-normal.woff2", _append("x"))
    assert _pages(core) == []


def test_a_test_file_of_the_workspace_may_hold_a_font_face_fixture_but_not_import_a_font(tmp_path: Path) -> None:
    """`syncGovukAssets.test.ts` holds an `@font-face{src:url(/assets/fonts/a.woff2)}` string to test the URL rewrite: it
    loads nothing. An `@fontsource` import in a test file is still a load (a harness imports what it draws with)."""
    core = build_tree(tmp_path)
    fixture = '  const css = "@font-face{src:url(/assets/fonts/a.woff2)}";\n'
    _edit(core, "apps/workspace/src/brand/govuk/syncGovukAssets.test.ts", _append(fixture))
    assert _front(core) == []
    _edit(core, "apps/workspace/src/brand/govuk/syncGovukAssets.test.ts", _append('import "@fontsource/roboto/400.css";'))
    found = _front(core)
    assert len(found) == 1 and "loads @fontsource/roboto/400.css" in found[0]
    # The same fixture in a file that is not a test is a fault.
    _edit(core, "apps/workspace/src/brand/govuk/sync.ts", _append(fixture))
    assert any("sync.ts: an @font-face for '(no family)'" in line for line in _front(core))


def test_a_yaml_record_beside_the_pages_may_name_the_govuk_assets_but_a_view_may_not(tmp_path: Path) -> None:
    core = build_tree(tmp_path)
    _edit(core, "apps/pages/FUNCTIONS.yaml", _append("  # the proxy sends /assets/govuk/* to the workspace"))
    assert _pages(core) == []
    _edit(core, "apps/pages/server/views/home.njk", _append('<link rel="stylesheet" href="/assets/govuk/govuk-frontend.css">'))
    assert len(_pages(core)) == 1


def test_a_test_of_the_pages_may_name_gds_transport_in_order_to_forbid_it(tmp_path: Path) -> None:
    core = build_tree(tmp_path)
    _edit(core, "apps/pages/test/server/fonts.test.ts", _append('expect(html).not.toContain("GDS Transport");'))
    assert _pages(core) == []


def test_the_pages_scan_is_red_when_the_list_names_nothing_of_the_face(tmp_path: Path) -> None:
    """Remove Atkinson from the list: the same tree's own face, which was clean, is now unlisted."""
    core = build_tree(tmp_path)
    _edit(core, "apps/pages/server/static/fonts.css", _append(REAL_FONTSOURCE_FACE))
    data = load_list()
    assert _pages(core, data) == []
    data = copy.deepcopy(data)
    data["fonts"] = [e for e in data["fonts"] if e["family"] != "Atkinson Hyperlegible Next"]
    found = _pages(core, data)
    assert len(found) == 1 and "an @font-face for 'Atkinson Hyperlegible Next', which the list does not name" in found[0]


LIST_PLANTS: list[tuple[str, Callable[[dict], None], str]] = [
    ("a subsets field on a family", lambda d: d["fonts"][0].update(subsets=["latin"]), "has the field `subsets`"),
    ("a family with no licence", lambda d: d["fonts"][1].pop("licence"), "IBM Plex Mono: lacks the field `licence`"),
    ("a licence that is not OFL on a fontsource family", lambda d: d["fonts"][0].update(licence="MIT"), "licence 'MIT' is not OFL-1.1"),
    ("GDS Transport without the identity switch", lambda d: d["fonts"][2].pop("only_when"), "GDS Transport: lacks the field `only_when`"),
    ("GDS Transport without the gov.uk address", lambda d: d["fonts"][2].pop("only_on"), "GDS Transport: lacks the field `only_on`"),
    ("GDS Transport on the wrong switch", lambda d: d["fonts"][2].update(only_when="appearance.brand"), "not conditioned on the identity switch"),
    ("GDS Transport for any address", lambda d: d["fonts"][2].update(only_on="*"), "not conditioned on a gov.uk address"),
    ("GDS Transport with an OFL licence", lambda d: d["fonts"][2].update(licence="OFL-1.1"), "licence must say it is restricted"),
    ("a condition on another entry", lambda d: d["fonts"][0].update(only_when="appearance.govuk_identity"), "Atkinson Hyperlegible Next: has the field `only_when`"),
    ("a weight list that is not sorted and distinct", lambda d: d["fonts"][0].update(weights=[700, 400, 400]), "weights [700, 400, 400] are not a sorted list"),
    ("a family listed twice", lambda d: d["fonts"].append(copy.deepcopy(d["fonts"][1]) | {"role": "mono"}), "listed twice"),
    ("a second face for a role", lambda d: d["fonts"].append(copy.deepcopy(d["fonts"][1]) | {"family": "Other Mono", "source": "@fontsource/other-mono"}), "the list names 2 faces for the role mono"),
]


@pytest.mark.parametrize(("case", "plant", "expected"), LIST_PLANTS, ids=[p[0] for p in LIST_PLANTS])
def test_the_list_check_is_red_for_each_planted_fault(case: str, plant: Callable[[dict], None], expected: str) -> None:
    data = load_list()
    assert list_violations(data) == []
    planted = copy.deepcopy(data)
    plant(planted)
    found = list_violations(planted)
    assert any(expected in line for line in found), found


def test_fonts_test_ts_restating_the_list_is_red() -> None:
    """The line the old file held, put back, and the file that stopped reading the list."""
    text = FONTS_TEST_TS.read_text(encoding="utf-8")
    assert fonts_test_restates_the_list(text) == []
    restated = text + '\nconst OLD = [\n  "@fontsource/ibm-plex-mono/600.css",\n];\n'
    assert fonts_test_restates_the_list(restated) == ['fonts.test.ts restates "@fontsource/ibm-plex-mono/600.css"']
    assert fonts_test_restates_the_list(text.replace("fonts.json", "fonts.txt")) == ["fonts.test.ts does not read fonts.json"]
