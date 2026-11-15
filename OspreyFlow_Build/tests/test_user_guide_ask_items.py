"""User guide §6, *An answer's items* (v0.6.0 item 5, the owner's closed list), held to the code that decides each
claim (rule 12): `questions/AnswerActions.tsx` (the two actions, the view's name, when each is offered),
`questions/showAnswer.ts` (what it says when it cannot show everything) and `App.tsx` (a saved view closed first,
the saved message, the case line's count).
"""

from __future__ import annotations

import re

from tests.test_guides_cloud_platform import CORE, USER, section

SRC = CORE / "apps/workspace/src"


def screen(path: str) -> str:
    source = (SRC / path).read_text(encoding="utf-8")
    source = re.sub(r"\{/\*.*?\*/\}|/\*.*?\*/", " ", source, flags=re.DOTALL)
    return re.sub(r"\s+", " ", re.sub(r"(?m)^\s*//.*$", " ", source))


def six() -> str:
    return re.sub(r"\s+", " ", section(USER, "## 6"))


def test_the_two_actions_and_when_each_is_offered() -> None:
    actions = screen("questions/AnswerActions.tsx")
    assert 'role="group" aria-label="This answer\'s items"' in actions
    assert "onClick={() => onShowAll(ids)}> Show all on graph </button>" in actions
    assert "Save as a view </button>" in actions
    # Save is offered only when the answer stands for nodes: links alone offer Show all only.
    assert "const canSave = onSaveAsView !== undefined && ids.nodeIds.length > 0;" in actions
    text = six()
    assert ("Under an answer whose markers stand for items, **Show all on graph** puts every item they stand for on the "
            "case's graph and selects them together, the view moved to the first") in text  # fmt: skip
    assert "An answer whose markers stand for links alone offers only **Show all on graph**." in text


def test_what_show_all_cannot_show_is_a_count_and_past_the_limit_nothing() -> None:
    show = screen("questions/showAnswer.ts")
    assert "now.say(`${added.notShown.toLocaleString(\"en-GB\")} of this answer's items could not be shown.`);" in show
    assert "Nothing was added; Save as a view keeps them all.`" in show and "`Too many for the canvas: " in show
    assert "drawn.highlightNodes(ids.nodeIds);" in show and "if (first) drawn.centreOn(first);" in show
    app = screen("App.tsx")
    body = app[app.index("const showAnswerOnGraph = async") :][:400]
    assert "if (lens) closeLens();" in body, "a saved view open is closed first"
    text = six()
    assert '("3 of this answer\'s items could not be shown."), never which' in text
    assert ('Past the graph\'s limit it adds nothing and says so ("Too many for the canvas: … Nothing was added; Save as '
            'a view keeps them all.")') in text  # fmt: skip
    assert "a saved view that is open is closed first, since the items go on the case" in text


def test_save_as_a_view_names_the_view_as_the_code_does() -> None:
    actions = screen("questions/AnswerActions.tsx")
    assert "words.length > 72 ? `${words.slice(0, 72).replace(/\\s+\\S*$/, \"\")}…` : words;" in actions
    assert 'return cut ? `Answer: ${cut}` : "Answer from Ask & Chat";' in actions
    app = screen("App.tsx")
    save = app[app.index("const saveAnswerAsView = async") :]
    save = save[: save.index("return null; };") + len("return null; };")]
    assert "setToast(`Saved as a view: ${saved.view.name}. Open it from Saved views.`);" in save
    assert "setViewsRead((n) => n + 1);" in save, "the case line's Saved views (n) counts it"
    text = six()
    assert ('named "Answer: " and the question (cut at a word after 72 characters), or "Answer from Ask & Chat" when '
            'there is no question; saving says "Saved as a view: ‹name›. Open it from Saved views."') in text  # fmt: skip
    assert "private to you until shared, and **Saved views (n)** counts it (section 5.13)" in text
