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
    """The strip's own parts it draws, in the order it draws them: a part it no longer draws is left out, so the
    list is short."""
    parts = ["Back to the whole case", "Saved view: <span", '{shared ? "Shared" : "Private"}', "{note &&",
             "Nothing in a saved view changes the case."]  # fmt: skip
    return sorted((p for p in parts if p in strip), key=strip.find)


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
    """The real strip with its way back moved after the note, as main's strip had it, and with its note reworded."""
    strip = screen("views/ViewLensBanner.tsx")
    back = strip.index("Back to the whole case")
    moved = strip[:back] + strip[back + len("Back to the whole case") :]
    moved = moved.replace("Nothing in a saved view changes the case.", "Nothing in a saved view changes the case. Back to the whole case")
    assert strip_order(moved)[0] != "Back to the whole case"
    reworded = strip.replace("Nothing in a saved view changes the case.", "Nothing in a view changes the case.")
    assert "Nothing in a saved view changes the case." not in strip_order(reworded)


def test_the_app_draws_the_strip_the_panel_and_the_way_back_as_the_guide_says() -> None:
    app = screen("App.tsx")
    assert 'title={casesOpen === "views" ? "Saved views" : "Cases"}' in app, "the drawer's title from the case line"
    assert "onOpenWholeCase={() => {" in app, "the whole case's Open, wired"
    assert '{view === "graph" && !lens && investigationId && <WholeCaseStrip />}' in app
    back = app[app.index("const backToTheWholeCase = (): void => {") :]
    assert "requestAnimationFrame(() => focusSavedViewsButton());" in back[: back.index("};")]
    assert 'label: "Opened from an alert",' in app and 'backLabel: "← Back to the alert",' in app
    # The Cases panel lists each case's saved views too: its list opens one.
    cases = app[app.index("<CaseList") :]
    assert "onOpenView={(caseId, chosen: CaseView) => {" in cases[:2000]
    strip = screen("views/ViewLensBanner.tsx")
    assert "{from && <span className=\"view-lens-banner__from\">{from.label}</span>}" in strip
    assert strip.index("Back to the whole case") < strip.index("{from.label}") < strip.index("Saved view: <span")
    assert strip.index("Nothing in a saved view changes the case.") < strip.index("{from.backLabel}")
    text = saved_views()
    assert ("the **Cases** panel, from **All cases**, lists each case's saved views too.") in text
    assert ('A saved view opened from an alert says "Opened from an alert" straight after the way back, and offers '
            "**← Back to the alert** after the note.") in text  # fmt: skip


def test_the_list_starts_with_the_whole_case_and_tells_default_named_views_apart() -> None:
    panel = screen("views/ViewsPanel.tsx")
    # The whole case's row, in both looks, marked Open now while no saved view is; the open view's, likewise.
    assert '<dt className="govuk-summary-list__key">The whole case</dt>' in panel
    assert '<span className="case-views__name">The whole case</span>' in panel
    assert panel.count("{openViewId === null && <") == 2 and panel.count("{view.id === openViewId && <") == 2
    assert 'aria-label="Open the whole case" onClick={onOpen}> Open </button>' in panel
    # The open view offers no Open.
    assert "{!isOpen && ( <button type=\"button\" className={action} aria-label={`Open ${view.name}`} onClick={onOpen}> Open </button>" in panel
    assert "const DEFAULT_NAME = /^Selection of [\\d,]+ nodes?$/;" in panel
    canvas = screen("canvas/GlassCanvas.tsx")
    assert 'return `Selection of ${n} node${n === 1 ? "" : "s"}`;' in canvas, "the Glass's default name, as the panel matches it"
    assert 'day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"' in panel
    assert "return view.first_item ? `${view.first_item} · saved ${when}` : `Saved ${when}`;" in panel
    assert "Delete this view? Nothing on the case is deleted with it." in panel
    assert "aria-label={`Share with the case: ${view.name}`}" in panel
    assert "No views yet. Select nodes on the canvas and choose <em>Save as a view</em>." in panel
    form = screen("views/SaveViewForm.tsx")
    assert "View name" in form and "Save view" in form
    text = saved_views()
    assert ("The list starts with **The whole case**, marked *Open now* when no saved view is open, and offering "
            "**Open** (*Open the whole case*, to a screen reader) while one is") in text  # fmt: skip
    assert 'One saved under the name the Glass gives a selection ("Selection of 3 nodes") is told apart' in text
    assert ('("‹first item› · saved 14 Nov 2026, 12:01"), or when it was saved alone ("Saved 14 Nov 2026, 12:01")') in text
    assert "The one open now is marked *Open now* and offers no **Open**" in text
    assert "**Share with the case** and **Delete**" in text and "under **View name** and **Save view**" in text


def test_the_canvas_notice_and_the_toolbar() -> None:
    canvas = screen("canvas/GlassCanvas.tsx")
    m = re.search(r'const LENS_NOTICE = "([^"]+)";', canvas)
    assert m and f'"{m.group(1)}"' in saved_views()
    # ADR-144 Amendment 6: the toolbar's Views menu, its file and its slot, removed.
    assert not (SRC / "views/ViewsMenu.tsx").exists() and "viewsMenu" not in canvas
    actions = screen("canvas/ViewActions.tsx")
    # The toolbar's button, by its word, and its confirmation, by its name.
    assert "onClick={() => setConfirming(true)} > Clear the graph </button>" in actions
    assert 'role="alertdialog" aria-label="Clear the graph"' in actions
    two = fold(section(USER, "### 5.2"))
    assert "**Remove from view** and **Clear the graph** take nodes off" in two
    assert "In a saved view, the menu offers only what changes nothing in the case." in two
