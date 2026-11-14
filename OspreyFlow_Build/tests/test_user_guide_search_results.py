"""The user guide's §5.5, the search results page, held to the page and the Conduit as v0.5.2's step 3e′ built them
(ADR-145 Amendment 15 Part A; spec 02 §2.0c). The page's own words, *Show on graph* and *Open*, 20 a page, the
over-long query's refusal naming its limit, and the fallback's one line are each read from the code that says them,
so the guide's sentence turns red when the screen's words or the Conduit's change (rule 12).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
GUIDE = (CORE / "docs" / "user-guide.md").read_text(encoding="utf-8")
SRC = CORE / "apps" / "workspace" / "src"
PAGE = (SRC / "search" / "SearchResults.tsx").read_text(encoding="utf-8")
APP = (SRC / "App.tsx").read_text(encoding="utf-8")


def results_text(guide: str = GUIDE) -> str:
    """§5.5's two paragraphs on the results page, whitespace folded."""
    m = re.search(r"^\*\*The results page\.\*\*.*?\n\n.*?\n\n", guide, re.MULTILINE | re.DOTALL)
    assert m, "§5.5's results page"
    assert m.start() > guide.index("### 5.5 Search") and m.end() < guide.index("### 5.6"), "in §5.5"
    return re.sub(r"\s+", " ", m.group(0))


def _template(words: str) -> str:
    """A screen template literal (`…${x}…`) with each placeholder written as the guide writes it, '…'."""
    return re.sub(r"\$\{[^}]+\}", "…", words)


def _module_constants(path: Path) -> dict[str, object]:
    """A module's top-level constants, read without importing it (the search service imports the index's client)."""
    found: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0] if isinstance(node, ast.Assign) else None
        if isinstance(target, ast.Name) and node.value is not None:
            try:
                found[target.id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return found


def test_section_5_5_quotes_the_page_s_heading_empty_line_and_ask_line_as_the_page_words_them() -> None:
    text = results_text()
    for shape in (r"`(Search results for '\$\{query\}')`", r"`(No records match '\$\{query\}')", r"`(Ask a question about '\$\{query\}' instead)`"):
        m = re.search(shape, PAGE)
        assert m, f"the page's words: {shape}"
        assert f'"{_template(m.group(1))}' in text
    assert '" (counts may be incomplete)"' in PAGE and '"(counts may be incomplete)"' in text


def test_section_5_5_says_the_ask_line_is_only_for_someone_offered_ask_and_chat() -> None:
    """App gives the page `onAsk` only where the rail offers Ask & Chat; the page draws no line without it."""
    assert re.search(r'onAsk=\{railEntries\(rights\)\.includes\("questions"\) \? \(words\) => \{', APP)
    assert "const askLine = onAsk && (" in PAGE
    assert "Where Ask & Chat is offered to you, a last line" in results_text()


def test_section_5_5_names_the_page_s_controls_as_the_page_labels_them() -> None:
    text = results_text()
    labels = {
        "Back to ‹view›": "{`Back to ${backLabel}`}",
        "All": 'label: "All"',
        "Datasets": ">Datasets</legend>",
        "Dates": ">Dates</legend>",
        "Clear filters": "      Clear filters\n",
        "Next page": "          Next page\n",
        "Previous page": "          Previous page\n",
        "Show on graph": "          Show on graph\n",
        "Open": "            Open\n",
    }
    assert [label for label, code in labels.items() if code not in PAGE] == []
    assert [label for label in labels if f"**{label}**" not in text] == []


def test_section_5_5_gives_the_page_size_the_page_asks_for() -> None:
    m = re.search(r"^export const RESULTS_PAGE_SIZE = (\d+);$", PAGE, re.MULTILINE)
    assert m and "page_size: RESULTS_PAGE_SIZE" in PAGE
    assert f"Results come {m.group(1)} a page" in results_text()


def test_section_5_5_says_show_on_graph_takes_you_to_the_graph_and_open_is_for_a_document() -> None:
    show = re.search(r"onShow=\{\(nodes\) => \{(.*?)\n          \}\}", APP, re.DOTALL)
    assert show and "seedToCanvas(nodes" in show.group(1) and 'setView("graph")' in show.group(1)
    assert "{result.is_document && first && (" in PAGE
    text = results_text()
    assert "**Show on graph** puts every record the result stands for on the graph and takes you there" in text
    assert "**Open**, for a document," in text


def test_section_5_5_gives_the_search_s_limit_and_its_refusal_as_the_conduit_and_page_do() -> None:
    """A query over `MAX_QUERY_CHARS` is refused by the request's own schema, and the page names the limit and the
    query's length from FastAPI's list, keeping the words as typed (rule 2)."""
    from schemas.search import MAX_QUERY_CHARS, SearchPageRequest

    assert [getattr(m, "max_length", None) for m in SearchPageRequest.model_fields["query"].metadata].count(MAX_QUERY_CHARS) == 1
    refusal = re.search(r"return `(The search could not be done: a search can be at most \$\{entry\.ctx\.max_length\} characters, and this one has \$\{[^}]+\}\. Shorten it and press Enter again\.)`;", PAGE)
    assert refusal, "the page's refusal, naming the limit and the query's length"
    text = results_text()
    assert f"A search can be at most {MAX_QUERY_CHARS} characters." in text
    assert "saying the limit and how many characters yours has, and is never cut short: shorten it and press Enter again" in text


def test_section_5_5_quotes_the_fallback_s_line_as_the_conduit_words_it() -> None:
    consts = _module_constants(CORE / "services" / "api" / "search_service.py")
    LIMITED_REASONS, DATES_NOT_APPLIED = consts["LIMITED_REASONS"], consts["DATES_NOT_APPLIED"]
    text = results_text()
    assert f'"{LIMITED_REASONS["no_index"]}"' in text
    assert f'"{DATES_NOT_APPLIED.strip()}"' in text
    # The page shows the Conduit's line where it gives one.
    assert "{shown.limited_reason ?? " in PAGE

