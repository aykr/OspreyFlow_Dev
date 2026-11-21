"""The Glass's navigation as the administration, developer and architecture guides and both websites name it, held to
`railLayout.ts` and Admin's `sections.json` (ADR-145 Amendments 12 and 15; the docs lane's step 5 sweep, part 3). The
user guide's own navigation is held by `test_user_guide_navigation.py`; these are the other places that name it,
which nothing held, so the 1.54 rewrite left them behind (rule 12):

- a view is never said to be on the rail: only `ON_THE_RAIL`'s panel openers are, and a guide naming a view (Reports,
  Ownership, Connection strength, Matrix, Figures) puts it where `VIEW_SWITCH` or `MORE_VIEWS` does;
- the questions panel is called by its label (`RAIL_LABELS.questions`, *Ask & Chat*), never by a name it had before
  Amendment 12 ("Questions", "Ask the case");
- an Admin section is named as `sections.json` labels it ("Admin → Operations", never "Schedules and runs");
- "view" means a saved view alone (ADR-145 Amendment 17, ADR-144 Amendment 6): no guide, the user guide among them,
  names *More views*, *Views in this case*, the graph toolbar's withdrawn *Views* menu or *Clear view*, and nor does
  the Glass, held both ways.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
DOCS = CORE / "docs"
SRC = CORE / "apps" / "workspace" / "src"
LAYOUT = (SRC / "shell" / "railLayout.ts").read_text(encoding="utf-8")
USER_GUIDE = DOCS / "user-guide.md"
SITES_BUILD = Path(__file__).resolve().parents[1] / "marketing_site" / "sites" / "build.py"
#: Every place held here, by name.
GUIDES = {name: DOCS / f"{name}-guide.md" for name in ("administration", "developer", "architecture")}
GUIDES["demo"] = CORE / "DEMO_GUIDE.md"
#: The names the questions panel had before Amendment 12 renamed it (ADR-145 Amendment 12: "Questions renamed").
OLD_QUESTIONS_NAMES = ("Ask the case", "Questions panel", "Questions and Ask", "<strong>Questions.</strong>",
                       "Questions: an answer")  # the last, the questions figure's caption and alternative text
#: The names "view" had before ADR-145 Amendment 17 kept it for saved views: the other ways to show the case, the case
#: line's button, the graph toolbar's menu (withdrawn, ADR-144 Amendment 6) and the selection's clearing.
OLD_VIEW_NAMES = ("More views", "Views in this case", "**Views ▾**", "**Views** menu", "Clear view",
                  "Nothing in a view changes the case", "**Back to the case**")
#: The same, as the Glass would draw them: a label or text on screen.
OLD_VIEW_WORDS = ("More views", "Views in this case", "Clear view", "Nothing in a view changes the case")


def _list(name: str) -> list[str]:
    m = re.search(rf"export const {name}(?:: [^=]+)? = \[([^\]]*)\]", LAYOUT)
    assert m, f"railLayout.ts's {name}"
    return re.findall(r'"([a-z]+)"', m.group(1))


def _labels(name: str) -> dict[str, str]:
    m = re.search(rf"export const {name}: Record<[^>]+> = \{{(.*?)\}};", LAYOUT, re.DOTALL)
    assert m, f"railLayout.ts's {name}"
    return dict(re.findall(r'^\s*([a-z]+): "([^"]+)",$', m.group(1), re.MULTILINE))


ON_THE_RAIL = _list("ON_THE_RAIL")
_more = re.search(r'^export const MORE_LABEL = "([^"]+)";$', LAYOUT, re.MULTILINE)
MORE = _more.group(1) if _more else "(railLayout.ts's MORE_LABEL, not found)"
VIEW_SWITCH, MORE_VIEWS = _list("VIEW_SWITCH"), _list("MORE_VIEWS")
RAIL_LABELS, VIEW_LABELS = _labels("RAIL_LABELS"), _labels("VIEW_LABELS")
ADMIN_SECTIONS = [
    item["label"]
    for group in json.loads((SRC / "admin" / "sections.json").read_text(encoding="utf-8"))["groups"]
    for item in group["sections"]
]


def prose(text: str) -> str:
    """A guide without its document-control table (which records what earlier versions said), whitespace folded."""
    text = re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", " ", text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", text)


def sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+(?=[A-Z*])", text)


def places(guides: dict[str, str]) -> dict[str, str]:
    return {name: prose(text) for name, text in guides.items()}


def read_all() -> dict[str, str]:
    found = {name: path.read_text(encoding="utf-8") for name, path in GUIDES.items()}
    found["sites"] = SITES_BUILD.read_text(encoding="utf-8")
    # The pages as generated too, so a page edited by hand or left unbuilt is read as it would be published.
    pages = sorted(p for site in ("org", "net") for p in (SITES_BUILD.parent / site).glob("*.html"))
    found["pages"] = "\n\n".join(p.read_text(encoding="utf-8") for p in pages)
    return found


def views_said_on_the_rail(texts: dict[str, str]) -> list[str]:
    """Each sentence that puts a view on the rail: a view's label, bold, with "rail" in the same sentence. Only the
    panel openers are on the rail."""
    views = {VIEW_LABELS[v] for v in [*VIEW_SWITCH, *MORE_VIEWS]} | {
        RAIL_LABELS[e] for e in RAIL_LABELS if e not in ON_THE_RAIL and e != "cases"
    }
    found = []
    for name, text in places(texts).items():
        for sentence in sentences(text):
            if re.search(r"\brail\b", sentence):
                found += [f"{name}: {label} on the rail" for label in sorted(views) if f"**{label}**" in sentence]
    return found


def old_question_names(texts: dict[str, str]) -> list[str]:
    return [f"{name}: {old!r}" for name, text in places(texts).items() for old in OLD_QUESTIONS_NAMES if old in text]


def old_view_names(texts: dict[str, str]) -> list[str]:
    return [f"{name}: {old!r}" for name, text in places(texts).items() for old in OLD_VIEW_NAMES if old in text]


def _screen_text(source: str) -> str:
    """A source file without its comments: what it can put on screen, not what it says about itself."""
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    source = re.sub(r"\{/\*.*?\*/\}", " ", source, flags=re.DOTALL)
    return re.sub(r"(?m)(^|[^:\"'`])//.*$", r"\1", source)


def old_view_words_on_screen(sources: dict[str, str]) -> list[str]:
    return [f"{name}: {old!r}" for name, source in sources.items() for old in OLD_VIEW_WORDS
            if old in re.sub(r"\s+", " ", _screen_text(source))]  # fmt: skip


#: The Glass's sources: the workspace, and the shared package that holds what moved out of it (ADR-152 decision 6; the
#: PL4d2 clients return headlines and errors a person reads). A file is named by its place under its root.
GLASS_ROOTS = (SRC, CORE / "packages" / "glass-shared" / "src")


def glass_sources(roots: tuple[Path, ...] = GLASS_ROOTS) -> dict[str, str]:
    found = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
             for root in roots for p in sorted(root.rglob("*.ts*"))}  # fmt: skip
    return {name: text for name, text in found.items()
            if ".test." not in name and not name.startswith("test") and "/test" not in name}  # fmt: skip


def admin_sections_misnamed(texts: dict[str, str]) -> list[str]:
    """Each "Admin → X" or "Admin › X" that names no section by its label: what follows the arrow, a name (a capital
    first), must begin with one of `sections.json`'s labels. A mention inside a quotation is the code's own words,
    which a guide quotes exactly, so it is left to the code ("Admin → the Conduit" is a flow, not a screen)."""
    labels = sorted(ADMIN_SECTIONS, key=len, reverse=True)
    found = []
    for name, text in texts.items():
        text = re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", " ", text, flags=re.DOTALL)
        # Appendix A is generated from the schema's own descriptions (tools.admin_guide_options, held by
        # test_admin_guide.py): its words are the schema's, changed there.
        text = re.sub(r"^## Appendix A\b.*?(?=^## |\Z)", " ", text, flags=re.DOTALL | re.MULTILINE)
        for paragraph in (" ".join(p.split()) for p in re.split(r"\n\s*\n", text)):
            for m in re.finditer(r"Admin (?:→|›) \*{0,2}(?=[A-Z])", paragraph):
                if paragraph.count('"', 0, m.start()) % 2:
                    continue
                after = paragraph[m.end() :]
                if not any(after.startswith(label) for label in labels):
                    found.append(f"{name}: Admin → {' '.join(after.split()[:3])}")
    return found


# ---------------------------------------------------------------- the rules, against the guides and sites as they are


def test_the_layout_is_read() -> None:
    assert ON_THE_RAIL and VIEW_SWITCH and MORE_VIEWS and RAIL_LABELS and VIEW_LABELS and "Operations" in ADMIN_SECTIONS
    assert RAIL_LABELS["questions"] == "Ask & Chat"


def test_no_guide_or_site_puts_a_view_on_the_rail() -> None:
    assert views_said_on_the_rail(read_all()) == []


def test_the_questions_panel_is_called_by_its_label() -> None:
    assert old_question_names(read_all()) == []


def test_view_means_a_saved_view_in_every_guide_and_in_the_glass() -> None:
    texts = {**read_all(), "user": USER_GUIDE.read_text(encoding="utf-8")}
    assert old_view_names(texts) == []
    sources = glass_sources()
    assert len(sources) > 100 and "shell/TopBar.tsx" in sources, "the Glass's sources are read"
    assert old_view_words_on_screen(sources) == []
    # The toolbar's Views menu is withdrawn: nothing draws it.
    drawn = [n for n, s in glass_sources().items() if n != "views/ViewsMenu.tsx" and re.search(r"<ViewsMenu\b", s)]
    assert drawn == [], drawn


#: The six clients that moved: a folder, then each file's stem. Never written as a path (the old-path scan in
#: `glass_trees/test_glass_shared_clients.py` reads this file too, and only the package's own place may name them).
_MOVED = {"ingest": ("api",), "ingest/sources": ("api",), "ingest/releases": ("releasesApi",),
          "admin/sections": ("MapsApi", "ModelsApi"), "admin": ("updateNotice",)}  # fmt: skip
MOVED_CLIENTS = tuple(f"{folder}/{stem}.ts" for folder, stems in _MOVED.items() for stem in stems)


def test_the_glass_s_sources_include_the_clients_that_moved_to_the_shared_package() -> None:
    """The six clients left `apps/workspace/src` in PL4d2; this guard once read only that folder (found in review)."""
    sources = glass_sources()
    for client in MOVED_CLIENTS:
        assert client in sources, client
        assert not (SRC / client).exists(), client


def test_an_old_view_word_planted_in_a_moved_client_is_found(tmp_path: Path) -> None:
    """Each moved client, copied; the same copy clean finds nothing, with a word on screen it is found, and in a comment
    (which a person never sees) it is not."""
    for client in MOVED_CLIENTS:
        real = (GLASS_ROOTS[1] / client).read_text(encoding="utf-8")
        copy = tmp_path / "src" / client
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(real, encoding="utf-8")
        assert old_view_words_on_screen(glass_sources((tmp_path / "src",))) == []
        copy.write_text(real + '\nexport const planted = "Clear view";\n', encoding="utf-8")
        assert old_view_words_on_screen(glass_sources((tmp_path / "src",))) == [f"{client}: 'Clear view'"]
        copy.write_text(real + "\n// Clear view, a comment\n", encoding="utf-8")
        assert old_view_words_on_screen(glass_sources((tmp_path / "src",))) == []
        copy.unlink()


def test_each_admin_section_is_named_as_admin_labels_it() -> None:
    assert admin_sections_misnamed(read_all()) == []


def test_the_views_the_guides_name_are_where_the_layout_puts_them() -> None:
    """The two places the administration guide names a view say where it is, in the layout's words."""
    text = prose(read_all()["administration"])
    assert ("dashboards" in VIEW_SWITCH) and f"**{VIEW_LABELS['dashboards']}** (the top bar's view switch)" in text
    assert ("strength" in MORE_VIEWS) and (
        f"**{VIEW_LABELS['strength']}** (the top bar's view switch, under **{MORE}**, or in the switch itself "
        "for someone offered nothing else there, as the built-in Administrator is)" in text
    )
    # splitViews: someone offered none of the switch's views has More's in the switch itself.
    assert "return main.length > 0 ? { main, more } : { main: more, more: [] };" in LAYOUT


# ---------------------------------------------------------------- each check flags what it is for (rule 15)


def test_a_view_said_on_the_rail_is_flagged() -> None:
    """The administration guide's own words before this sweep (§12, §9.6)."""
    planted = {"administration": "**In the Glass**, the rail's **Dashboards** draws an **Alert monitoring** board itself. "
               "**Approving influencers.** In the Glass's rail, **Connection strength**, a version waiting."}  # fmt: skip
    assert views_said_on_the_rail(planted) == [
        "administration: Dashboards on the rail", "administration: Connection strength on the rail"]  # fmt: skip


def test_a_panel_opener_on_the_rail_is_not_flagged() -> None:
    planted = {"administration": f"The rail's **{RAIL_LABELS['questions']}** opens over the view."}
    assert views_said_on_the_rail(planted) == []


def test_an_old_name_for_the_questions_panel_is_flagged() -> None:
    planted = {"administration": "which also answers Ask the case and Ask to search on the local engine"}
    assert old_question_names(planted) == ["administration: 'Ask the case'"]


def test_an_old_name_for_view_is_flagged_in_a_guide() -> None:
    """The user guide's own words before ADR-145 Amendment 17 (§3, §5.2, §5.13)."""
    planted = {"user": "· Views in this case · reads ‹dataset›. **Remove from view** and **Clear view** take nodes off. "
               "**Views ▾** in the graph's toolbar, beside *Clear view*. **Ownership**, under **More views** in the Glass."}  # fmt: skip
    assert old_view_names(planted) == ["user: 'More views'", "user: 'Views in this case'", "user: '**Views ▾**'", "user: 'Clear view'"]


def test_an_old_name_for_view_on_screen_is_flagged_and_a_comment_is_not() -> None:
    """Main's own code before Amendment 17: `TopBar.tsx`'s button and `ViewLensBanner.tsx`'s note."""
    planted = {"shell/TopBar.tsx": '// under More views\n          label={moreOpen ? moreOpen.label : "More views"}',
               "views/ViewLensBanner.tsx": '{/* Views in this case */}<span>Nothing in a view changes the case.</span>',
               "views/ViewsPanel.tsx": "/* *Views in this case* (ADR-144) */ const x = 1;"}  # fmt: skip
    assert old_view_words_on_screen(planted) == [
        "shell/TopBar.tsx: 'More views'", "views/ViewLensBanner.tsx: 'Nothing in a view changes the case'"]  # fmt: skip


def test_an_admin_section_under_an_old_name_is_flagged() -> None:
    planted = {"administration": "Admin → Schedules and runs lists every one. Admin → Operations lists them too."}
    assert admin_sections_misnamed(planted) == ["administration: Admin → Schedules and runs"]


def test_a_short_name_for_a_section_is_flagged_and_a_quotation_is_not() -> None:
    """The administration guide's own shapes before this sweep: the section is *People and roles*; a refusal quoted in
    the code's words is the code's to change."""
    planted = {"administration": "Roles are assigned in *Admin › People*, which keeps them.\n\n"
               'An owner is refused ("is not a person Admin › People holds"). In *Admin › Dashboards* by its id.'}  # fmt: skip
    assert admin_sections_misnamed(planted) == [
        "administration: Admin → People*, which keeps", "administration: Admin → Dashboards* by its"]  # fmt: skip


def test_the_document_control_table_is_not_read() -> None:
    """What an earlier version said is the record of it, not a claim about the screen."""
    planted = {"administration": "<!-- document-control:begin -->| 1.0 | Admin → Schedules and runs |"
               "<!-- document-control:end --> Admin → Operations."}  # fmt: skip
    assert admin_sections_misnamed(planted) == []
