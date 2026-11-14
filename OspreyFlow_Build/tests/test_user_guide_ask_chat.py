"""The user guide's §6, Ask & Chat, held to the panel and the Conduit as built (ADR-098 Amendment 7,
Part D of v0.5.2; ADR-144 decision 4). The panel asks what to read from, says before anything is sent
what that is about, what will be read and which engine will answer, and answers from links and events
when there is no document; *Ask the model about these…* saves the selection as a private view and asks
there; asking needs the case's Editor. Each case reads the code that says it, so the guide's sentence
turns red when the screen's words or the route change (rule 12).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
GUIDE = (CORE / "docs" / "user-guide.md").read_text(encoding="utf-8")
SRC = CORE / "apps" / "workspace" / "src"
PANEL = (SRC / "questions" / "QuestionsPanel.tsx").read_text(encoding="utf-8")


def ask_paragraph() -> str:
    """§6's paragraph on Ask & Chat, whitespace folded."""
    m = re.search(r"^## 6\. Ask & Chat.*?^(\*\*Ask & Chat\*\*.*?)(?:\n\n)", GUIDE, re.MULTILINE | re.DOTALL)
    assert m, "§6's Ask & Chat paragraph"
    return re.sub(r"\s+", " ", m.group(1))


def test_section_6_names_each_read_from_choice_as_the_panel_labels_it() -> None:
    labels = re.findall(r'\{ value: "[a-z]+", label: "([^"]+)" \}', PANEL)
    assert labels, "the panel's Read from choices"
    assert ">Read from</legend>" in PANEL
    text = ask_paragraph()
    assert "under **Read from**:" in text
    assert re.findall(r"\*\*(Selected items|Everything on the graph|Whole case|[A-Z][a-z ]+)\*\* \(", text) == labels


def test_section_6_says_whole_case_is_not_available_while_the_panel_says_so() -> None:
    disabled = re.search(r'"Whole case is not available yet:[^"]*"', PANEL)
    text = ask_paragraph()
    assert ("**Whole case** (not available yet, and it says why)" in text) is bool(disabled)


def test_section_6_quotes_about_and_will_read_in_the_panel_s_shape() -> None:
    text = ask_paragraph()
    about = re.search(r'\("(About: [^"]+)"\)', text)
    will = re.search(r'\("(Will read: [^"]+)"\)', text)
    assert about and will, "the guide's two examples"
    # aboutWords: "About: <first selected> and <n> other(s)"; readWords: "<n> document(s), <n> item(s) and <n> link(s)".
    assert "`About: ${read.first_selected} and ${counted(others, \"other\", \"others\")}`" in PANEL
    assert re.fullmatch(r"About: .+ and (1 other|\d+ others)", about.group(1))
    assert "<p style={{ margin: 0 }}>Will read: {readWords(will.read)}</p>" in PANEL
    assert re.fullmatch(r"Will read: (1 document|\d+ documents), (1 item|\d+ items) and (1 link|\d+ links)", will.group(1))
    assert ("which engine will answer" in text) is ("Will be answered by {will.engine_label}" in PANEL)


def test_section_6_says_an_answer_with_no_document_comes_from_links_and_events() -> None:
    said = "No documents will be read: the answer will come from the links and events." in PANEL
    text = ask_paragraph()
    assert ("With no document to read it answers from the links and events, and says so" in text) is said
    assert "at least one document you can see" not in text


def test_section_6_says_ask_the_model_about_these_saves_a_private_view() -> None:
    bar = (SRC / "canvas" / "SelectionBar.tsx").read_text(encoding="utf-8")
    canvas = (SRC / "canvas" / "GlassCanvas.tsx").read_text(encoding="utf-8")
    m = re.search(r"async function askAboutSelected\(\).*?\n    \}\n", canvas, re.DOTALL)
    assert m and "saveSelection(" in m.group(0) and "onAskInView?.(saved.view)" in m.group(0)
    schema = ast.parse((CORE / "packages" / "schemas" / "case_views.py").read_text(encoding="utf-8"))
    view = next(n for n in schema.body if isinstance(n, ast.ClassDef) and n.name == "CaseView")
    shared = next(s for s in view.body if isinstance(s, ast.AnnAssign) and getattr(s.target, "id", "") == "shared")
    private = isinstance(shared.value, ast.Constant) and shared.value.value is False
    text = ask_paragraph()
    assert "Ask the model about these…" in bar
    assert ("**Ask the model about these…** on any selection saves it as a private view and asks there" in text) is private
    assert "starts a case of its own" not in text


def test_section_6_gives_asking_the_case_level_the_route_requires() -> None:
    app = (CORE / "services" / "api" / "app.py").read_text(encoding="utf-8")
    m = re.search(r'@app\.post\(\s*"/v1/investigations/\{investigation_id\}/questions",.*?\)\nasync def ask_question_route\(\s*investigation: (\w+)', app, re.DOTALL)
    assert m, "the ask route"
    level = {"InvestigationEditorDep": "Editor", "InvestigationViewerDep": "Viewer"}[m.group(1)]
    assert f"Asking needs {level}." in ask_paragraph()
