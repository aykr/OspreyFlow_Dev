"""The Glass's navigation as the administration, developer and architecture guides and both websites name it, held to
`railLayout.ts` and Admin's `sections.json` (ADR-145 Amendments 12 and 15; the docs lane's step 5 sweep, part 3). The
user guide's own navigation is held by `test_user_guide_navigation.py`; these are the other places that name it,
which nothing held, so the 1.54 rewrite left them behind (rule 12):

- a view is never said to be on the rail: only `ON_THE_RAIL`'s panel openers are, and a guide naming a view (Reports,
  Ownership, Connection strength, Matrix, Figures) puts it where `VIEW_SWITCH` or `MORE_VIEWS` does;
- the questions panel is called by its label (`RAIL_LABELS.questions`, *Ask & Chat*), never by a name it had before
  Amendment 12 ("Questions", "Ask the case");
- an Admin section is named as `sections.json` labels it ("Admin → Operations", never "Schedules and runs").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
DOCS = CORE / "docs"
SRC = CORE / "apps" / "workspace" / "src"
LAYOUT = (SRC / "shell" / "railLayout.ts").read_text(encoding="utf-8")
SITES_BUILD = Path(__file__).resolve().parents[1] / "marketing_site" / "sites" / "build.py"
#: Every place held here, by name.
GUIDES = {name: DOCS / f"{name}-guide.md" for name in ("administration", "developer", "architecture")}
#: The names the questions panel had before Amendment 12 renamed it (ADR-145 Amendment 12: "Questions renamed").
OLD_QUESTIONS_NAMES = ("Ask the case", "Questions panel", "Questions and Ask", "<strong>Questions.</strong>")


def _list(name: str) -> list[str]:
    m = re.search(rf"export const {name}(?:: [^=]+)? = \[([^\]]*)\]", LAYOUT)
    assert m, f"railLayout.ts's {name}"
    return re.findall(r'"([a-z]+)"', m.group(1))


def _labels(name: str) -> dict[str, str]:
    m = re.search(rf"export const {name}: Record<[^>]+> = \{{(.*?)\}};", LAYOUT, re.DOTALL)
    assert m, f"railLayout.ts's {name}"
    return dict(re.findall(r'^\s*([a-z]+): "([^"]+)",$', m.group(1), re.MULTILINE))


ON_THE_RAIL = _list("ON_THE_RAIL")
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


def test_each_admin_section_is_named_as_admin_labels_it() -> None:
    assert admin_sections_misnamed(read_all()) == []


def test_the_views_the_guides_name_are_where_the_layout_puts_them() -> None:
    """The two places the administration guide names a view say where it is, in the layout's words."""
    text = prose(read_all()["administration"])
    assert ("dashboards" in VIEW_SWITCH) and f"the **{VIEW_LABELS['dashboards']}** view (the top bar's view switch)" in text
    assert ("strength" in MORE_VIEWS) and (
        f"**{VIEW_LABELS['strength']}** view (the top bar's view switch, under **More views**)" in text
    )


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
