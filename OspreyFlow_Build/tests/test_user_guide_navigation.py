"""The user guide's navigation of the Glass, held to the code that lays it out (ADR-145 Amendment 15, the
owner's navigation decision of 13 November 2026; ADR-078 Amendment 1, the selection's actions). The guide
described the rail, banner and view switch Amendment 15 replaced, and no test noticed: each case here
reads the lists the Glass draws from, so a change to the rail, the switch, the case line or the selection's
words turns the guide red (rule 12):

- the rail's entries, in order, by their names (`ON_THE_RAIL`, `RAIL_LABELS`), and nothing said to be on
  the rail that is not;
- the view switch and its More views, in order, by their names (`VIEW_SWITCH`, `MORE_VIEWS`, `VIEW_LABELS`);
- the case line's parts and its cross-link (`ContextBanner.tsx`);
- the selection bar's words in order (`SELECTION_WORDS`), the node menu's heading and the keys that open it
  (`GlassCanvas.tsx`).
"""

from __future__ import annotations

import re

from tests.test_guides_cloud_platform import CORE, USER, section

SRC = CORE / "apps/workspace/src"
RAIL = (SRC / "shell/railLayout.ts").read_text(encoding="utf-8")
BANNER = (SRC / "shell/ContextBanner.tsx").read_text(encoding="utf-8")
WORDS = (SRC / "canvas/selectionActions.ts").read_text(encoding="utf-8")
CANVAS = (SRC / "canvas/GlassCanvas.tsx").read_text(encoding="utf-8")


def _list(source: str, name: str) -> list[str]:
    m = re.search(rf"export const {name}(?:: [^=]+)? = \[([^\]]*)\]", source)
    assert m, f"{name} where this test reads it"
    return re.findall(r'"([a-z]+)"', m.group(1))


def _labels(source: str, name: str) -> dict[str, str]:
    m = re.search(rf"export const {name}[^=]*= \{{(.*?)\}}", source, re.DOTALL)
    assert m, f"{name} where this test reads it"
    return dict(re.findall(r'(\w+): "([^"]+)"', m.group(1)))


def _row(part: str, guide: str = USER) -> str:
    line = next((ln for ln in guide.splitlines() if ln.startswith(f"| **{part}** |")), "")
    assert line, f"§5's row for the {part}"
    return line


def _bold_in_order(text: str) -> list[str]:
    return re.findall(r"\*\*([^*]+)\*\*", text)


def rail_names() -> list[str]:
    labels = _labels(RAIL, "RAIL_LABELS")
    return [labels[e] for e in _list(RAIL, "ON_THE_RAIL")]


def view_names() -> tuple[list[str], list[str]]:
    labels = _labels(RAIL, "VIEW_LABELS")
    return [labels[v] for v in _list(RAIL, "VIEW_SWITCH")], [labels[v] for v in _list(RAIL, "MORE_VIEWS")]


def off_the_rail_said_on_it(guide: str) -> list[str]:
    """Each of the Glass's names that is not on the rail, where the guide puts it on the rail."""
    on = set(rail_names())
    names = {*_labels(RAIL, "RAIL_LABELS").values(), *_labels(RAIL, "VIEW_LABELS").values(), "Cases"} - on
    # The guide's text, not its history: the document control's rows record the rail each version had.
    body = re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", "", guide, flags=re.DOTALL)
    flat = re.sub(r"\s+", " ", body)
    found = []
    for name in sorted(names):
        said = [rf"rail's \*\*{re.escape(name)}\*\*", rf"\*\*{re.escape(name)}\*\*,? \(?on the rail",
                rf"{re.escape(name)}\*\* \(on the rail\)", rf"\*\*{re.escape(name)}\*\* is in the Glass's rail"]  # fmt: skip
        if any(re.search(p, flat) for p in said):
            found.append(name)
    if re.search(r"in the Glass's rail|Explore Details", flat):
        found.append("the rail's menu")
    return found


def test_section_5_names_the_rail_s_entries_in_order() -> None:
    row = _row("Left rail")
    named = _bold_in_order(row.split("|")[2])
    assert named[: len(rail_names())] == rail_names()
    assert "**Help** (**?**)" in row
    assert ("**Show names**" in row) is ('"Show names"' in (SRC / "shell/LeftRail.tsx").read_text(encoding="utf-8"))


def test_no_guide_passage_puts_on_the_rail_what_is_not_there() -> None:
    assert off_the_rail_said_on_it(USER) == []


def test_the_rail_check_flags_a_view_said_to_be_on_the_rail() -> None:
    planted = USER.replace("**Ownership**, under **More views** in the Glass,", "The rail's **Ownership**")
    assert off_the_rail_said_on_it(planted) == ["Ownership"]


def test_section_5_names_the_view_switch_and_more_views_in_order() -> None:
    switch, more = view_names()
    row = _row("Top bar")
    m = re.search(r"the view switch \((.*?) under \*\*More views\*\*", row)
    assert m, "the top bar's view switch"
    named = _bold_in_order(m.group(1))
    assert named == switch + more


def test_sections_3_and_5_give_the_case_line_as_the_banner_draws_it() -> None:
    three = re.sub(r"\s+", " ", section(USER, "## 3"))
    assert "Views in this case" in BANNER and "**Views in this case**" in three
    assert '"reads no dataset"' in BANNER and '"reads no dataset"' in three
    assert "Case</span>" in BANNER and '"You are in the Glass · Case ‹name› ▾ · Views in this case · reads ‹dataset›"' in three
    cross = re.search(r'label: "(Open this case[^"]+)"', BANNER)
    assert cross and f"**{cross.group(1)}**" in three
    assert "mode toggle" not in three and "Graph: the case's data" not in three
    assert ("**All cases**, opens the **Cases** panel" in three) is ("All cases" in (SRC / "App.tsx").read_text(encoding="utf-8"))
    assert "the case switcher, **Views in this case** and the dataset the case reads" in _row("Context banner")


def test_section_5_2_gives_the_selection_bar_in_its_words_and_order() -> None:
    words = _labels(WORDS, "SELECTION_WORDS")
    order = ["expand", "linksAmong", "ask", "saveView", "remove", "clear", "undoLit"]
    assert set(order) == set(words), "a selection word the guide does not place"
    m = re.search(r"The selection bar then offers (.*?)\. Past one degree", re.sub(r"\s+", " ", section(USER, "### 5.2")))
    assert m, "§5.2's sentence on the selection bar"
    assert _bold_in_order(m.group(1)) == [words[k] for k in order]


def test_section_5_2_gives_the_node_menu_s_heading_and_keys() -> None:
    two = re.sub(r"\s+", " ", section(USER, "### 5.2"))
    heading = re.search(r'const EXPAND_BY_LINK_TYPE = "([^"]+)"', CANVAS)
    assert heading and f"**{heading.group(1)}** lists each kind of relationship" in two
    keys = re.search(r"function opensMenu.*?\n\}", CANVAS, re.DOTALL)
    assert keys
    menu_key = '"ContextMenu"' in keys.group(0)
    shift_f10 = '"F10" && e.shiftKey' in keys.group(0)
    assert ("Right-click (or `\\`, the menu key, or Shift+F10)" in two) is (menu_key and shift_f10)
    row = next(ln for ln in USER.splitlines() if ln.startswith("| Canvas | `\\`"))
    assert ("the menu key, Shift+F10" in row) is (menu_key and shift_f10)
    assert "types with no links" in CANVAS and '("7 types with no links")' in two


def test_the_old_navigation_s_screenshots_are_marked_for_a_new_capture() -> None:
    marked = re.findall(r"<!-- needs a new capture[^>]*-->\n!\[[^\]]*\]\((images/user/[^)]+)\)", USER)
    assert sorted(m.split("/")[-1][:2] for m in marked) == ["04", "05", "06", "12", "16"]
