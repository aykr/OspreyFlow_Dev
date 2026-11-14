"""User guide §5.13, *Saved views*, held to the code that draws them (ADR-145 Amendment 17, ADR-144 Amendment 6; rule
12): the strip's way back and its words in their order (`ViewLensBanner.tsx`), the panel's *The whole case* row and a
default-named view's second line (`ViewsPanel.tsx`), the canvas's notice in a saved view (`GlassCanvas.tsx`), and the
case line's button (`ContextBanner.tsx`). Each claim is read from the code's own strings, never its comments.
"""

from __future__ import annotations

import re

from tests.test_guides_cloud_platform import CORE, USER, section

SRC = CORE / "apps/workspace/src"


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def screen(path: str) -> str:
    """A source file's code without its comments, whitespace folded."""
    source = (SRC / path).read_text(encoding="utf-8")
    source = re.sub(r"\{/\*.*?\*/\}|/\*.*?\*/", " ", source, flags=re.DOTALL)
    return fold(re.sub(r"(?m)^\s*//.*$", " ", source))


def saved_views() -> str:
    return fold(section(USER, "### 5.13"))


def strip_order(strip: str) -> list[str]:
    """The strip's own parts, in the order it draws them."""
    parts = ["Back to the whole case", "Saved view: <span", '{shared ? "Shared" : "Private"}', "{note &&",
             "Nothing in a saved view changes the case."]  # fmt: skip
    return sorted(parts, key=lambda p: strip.find(p) if p in strip else 10**9)


def test_the_strip_starts_with_the_way_back_and_says_what_the_guide_says_in_its_order() -> None:
    strip = screen("views/ViewLensBanner.tsx")
    assert strip_order(strip) == ["Back to the whole case", "Saved view: <span", '{shared ? "Shared" : "Private"}',
                                  "{note &&", "Nothing in a saved view changes the case."]  # fmt: skip
    assert '"govuk-back-link view-lens-banner__whole"' in strip, "under GOV.UK, GOV.UK's back link"
    assert "useEffect(() => strip.current?.focus(), []);" in strip, "focus comes to the strip"
    assert "You are looking at the whole case." in strip
    text = saved_views()
    assert ("The strip above the graph starts with **Back to the whole case** (the GOV.UK back link in that look), then "
            '"Saved view: ‹name›", its *Private* or *Shared* tag, how many of its items could not be shown when any '
            'could not, and "Nothing in a saved view changes the case."') in text  # fmt: skip
    assert 'With no saved view open the strip says "You are looking at the whole case."' in text
    assert ("Focus moves to the strip, **Back to the whole case** is the next Tab, and it returns focus to **Saved views "
            "(n)**.") in text  # fmt: skip


def test_a_strip_drawn_in_another_order_is_flagged() -> None:
    """Main's strip before Amendment 17: the name first, the way back last."""
    planted = ('View: <span>{name}</span> {shared ? "Shared" : "Private"} {note && <span/>} '
               "<span>Nothing in a saved view changes the case.</span> <button>Back to the whole case</button>")
    assert strip_order(planted)[0] != "Back to the whole case"


def test_the_list_starts_with_the_whole_case_and_tells_default_named_views_apart() -> None:
    panel = screen("views/ViewsPanel.tsx")
    assert "The whole case</dt>" in panel and "The whole case</span>" in panel, "both looks"
    assert panel.count("Open now") >= 4, "the whole case's and the open view's, in both looks"
    assert 'aria-label="Open the whole case"' in panel
    assert "const DEFAULT_NAME = /^Selection of [\\d,]+ nodes?$/;" in panel
    assert 'day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"' in panel
    assert "return view.first_item ? `${view.first_item} · saved ${when}` : `Saved ${when}`;" in panel
    assert "Delete this view? Nothing on the case is deleted with it." in panel
    text = saved_views()
    assert ("Its list starts with **The whole case**, marked *Open now* when no saved view is open, and offering **Open "
            "the whole case** while one is") in text  # fmt: skip
    assert ('("‹first item› · saved 14 Nov 2026, 12:01"), or when it was saved alone ("Saved 14 Nov 2026, 12:01")') in text
    assert "The one open now is marked *Open now* and offers no **Open**" in text


def test_the_canvas_notice_and_the_one_way_to_saved_views() -> None:
    canvas = screen("canvas/GlassCanvas.tsx")
    m = re.search(r'const LENS_NOTICE = "([^"]+)";', canvas)
    assert m and f'"{m.group(1)}"' in saved_views()
    assert not (SRC / "views/ViewsMenu.tsx").exists() or not re.search(r"<ViewsMenu\b", canvas)
    banner = screen("shell/ContextBanner.tsx")
    assert 'return typeof count === "number" ? `Saved views (${count.toLocaleString("en-GB")})` : "Saved views";' in banner
    assert "› Saved view: {openView}" in banner
    assert "**Saved views (n)**, on the case line, opens the **Saved views** panel; it is the one way to them." in saved_views()
