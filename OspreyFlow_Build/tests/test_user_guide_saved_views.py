"""User guide §5.13, *Saved views*, held to the code that draws them (ADR-145 Amendment 19, which withdrew Amendment
17's strip; ADR-144 Amendment 6; rule 12): the case line's saved view, its parts in their order and its *Details*
(`views/SavedViewOnTheLine.tsx`, drawn by `shell/ContextBanner.tsx` from App's `caseState`), the panel's *The whole
case* row and a default-named view's second line (`ViewsPanel.tsx`), the canvas's notice in a saved view
(`GlassCanvas.tsx`), and the case line's button (`ContextBanner.tsx`). Each claim is read from the code's own strings,
never its comments.
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


def line_order(line: str) -> list[str]:
    """The case line's saved-view parts, in the order it draws them: a part it no longer draws is left out, so the list
    is short."""
    parts = ['Saved view: <span className="context-banner__view-name">', '{state.shared ? "Shared" : "Private"}',
             "Details <span", "{state.from.backLabel}", "Back to the whole case"]  # fmt: skip
    return sorted((p for p in parts if p in line), key=line.find)


def items(code: str) -> str:
    """`CaseStateItems`, the parts the state adds to the line."""
    return code[code.index("export function CaseStateItems(") : code.index("export function SavedViewDetails(")]


def details(code: str) -> str:
    """`SavedViewDetails`, the panel *Details* opens."""
    return code[code.index("export function SavedViewDetails(") :]


def test_the_case_line_says_what_is_open_in_the_guides_order() -> None:
    code = screen("views/SavedViewOnTheLine.tsx")
    line = items(code)
    assert line_order(line) == ['Saved view: <span className="context-banner__view-name">', '{state.shared ? "Shared" : "Private"}',
                                "Details <span", "{state.from.backLabel}", "Back to the whole case"]  # fmt: skip
    assert '"govuk-back-link context-banner__whole"' in line, "under GOV.UK, GOV.UK's back link"
    assert "if (id !== null) named.current?.focus();" in line, "focus comes to the saved view's name"
    assert '<span className="context-banner__state">Whole case</span>' in line
    assert "aria-expanded={detailsOpen} aria-controls={DETAILS_ID}" in line
    panel = details(code)
    assert '{note && <p className="case-line-details__line">{note}</p>}' in panel
    assert 'export const NOTHING_CHANGES = "Nothing in a saved view changes the case.";' in code and "{NOTHING_CHANGES}" in panel
    assert "{state.from.label}" in panel and "{state.from.backLabel}" in panel
    assert "Notes from the drawing ({annotations.length})" in panel
    # Esc is the line's own, closing *Details* wherever focus is on the line or in it.
    assert 'if (event.key !== "Escape" || !detailsOpen) return;' in screen("shell/ContextBanner.tsx")
    text = saved_views()
    assert ('The case line says so: "Saved view: ‹name›", its *Private* or *Shared* tag, **Details ▾** and **Back to the '
            "whole case** (the GOV.UK back link in that look).") in text  # fmt: skip
    assert ("**Details** opens over the graph and says how many of its items could not be shown when any could not, "
            '"Nothing in a saved view changes the case.", and, for a saved view opened from an alert, "From alert '
            '‹title›" with **← Back to the alert**; for a merged drawing it offers **Notes from the drawing (n)**. Esc '
            "closes it.") in text  # fmt: skip
    assert 'With no saved view open the case line ends "Whole case".' in text
    assert ("Focus moves to the saved view's name on the case line; **Details** is the next Tab, then **Back to the "
            "whole case**, which returns focus to **Saved views (n)**.") in text  # fmt: skip


def test_a_line_drawn_in_another_order_is_flagged() -> None:
    """The real line with its way back moved before the name, and *Details* dropped."""
    line = items(screen("views/SavedViewOnTheLine.tsx"))
    back = line.index("Back to the whole case")
    moved = line[:back] + line[back + len("Back to the whole case") :]
    moved = moved.replace("Saved view: <span", "Back to the whole case Saved view: <span", 1)
    assert line_order(moved)[0] == "Back to the whole case"
    assert "Details <span" not in line_order(line.replace("Details <span", "More <span"))


def test_the_app_draws_the_state_the_panel_and_the_way_back_as_the_guide_says() -> None:
    app = screen("App.tsx")
    assert 'title={casesOpen === "views" ? "Saved views" : "Cases"}' in app, "the drawer's title from the case line"
    # The whole case's Open is the back link's own handler, so it does what Back to the whole case does.
    assert "onOpenWholeCase={backToTheWholeCase}" in app
    # No strip: the state is the case line's, from App's caseState.
    assert "WholeCaseStrip" not in app and "ViewLensBanner" not in app
    assert not (SRC / "views/ViewLensBanner.tsx").exists()
    assert "caseState={caseState}" in app and "onBack: backToTheWholeCase," in app
    back = app[app.index("const backToTheWholeCase = (): void => {") :]
    assert "requestAnimationFrame(() => focusSavedViewsButton());" in back[: back.index("};")]
    assert "label: `From alert ${lensFromAlert.title}`," in app and 'backLabel: "← Back to the alert",' in app
    # The Cases panel lists each case's saved views too: its list opens one.
    cases = app[app.index("<CaseList") :]
    assert "onOpenView={(caseId, chosen: CaseView) => {" in cases[:2000]
    banner = screen("shell/ContextBanner.tsx")
    assert "<CaseStateItems" in banner and "<SavedViewDetails" in banner
    text = saved_views()
    assert ("**Saved views (n)**, on the case line, opens the **Saved views** panel: on the case's own screen it is the "
            "one route to them, and the **Cases** panel, from **All cases**, still lists each case's saved views.") in text  # fmt: skip
    # The decision's own words for it (ADR-144 Amendment 6, as case corrected it after this lane's review).
    decisions = fold((CORE.parent / "OspreyFlow_Build" / "spec" / "06_DECISIONS.md").read_text(encoding="utf-8"))
    amendment = decisions[decisions.index("### ADR-144, Amendment 6 (14 November 2026)") :][:3000]
    assert ("The case line's **Saved views (n)** is the one route on the case's own screen to its saved views; "
            "*All cases* still lists each case's saved views") in amendment  # fmt: skip
    assert "A saved view opened from an alert also offers **← Back to the alert** on the case line itself." in text


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
