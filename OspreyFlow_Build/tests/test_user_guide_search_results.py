"""The user guide's §5.5, the search results page, held to the page and the Conduit as v0.5.2's step 3e′ built them
(ADR-145 Amendment 15 Part A; spec 02 §2.0c). Each sentence is read beside the code that does what it says: Enter in
the box, the page's words and counts, *Show on graph* and *Open*, 20 a page, the over-long query's refusal naming its
limit, the Conduit's other refusals, and the fallback's one line and what it cannot do. The guide's sentence turns red
when the screen or the Conduit changes (rule 12). Code is matched with its whitespace folded, so a reflow of the
source is not a change of what it does.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
GUIDE = (CORE / "docs" / "user-guide.md").read_text(encoding="utf-8")
SRC = CORE / "apps" / "workspace" / "src"
API = CORE / "services" / "api"


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _read(path: Path) -> str:
    return fold(path.read_text(encoding="utf-8"))


PAGE = _read(SRC / "search" / "SearchResults.tsx")
APP = _read(SRC / "App.tsx")
OVERLAY = _read(SRC / "search" / "useSearchResultsOverlay.ts")
COMBOBOX = _read(SRC / "design" / "primitives" / "Combobox.tsx")
BOX = _read(SRC / "search" / "GlobalSearch.tsx")
PANEL = _read(SRC / "questions" / "QuestionsPanel.tsx")
SERVICE = (API / "search_service.py").read_text(encoding="utf-8")
ROUTES = (API / "app.py").read_text(encoding="utf-8")


def results_text(guide: str = GUIDE) -> str:
    """§5.5's paragraphs on the results page, from their bold lead to *Add many from a list*, whitespace folded."""
    start, end = guide.index("**The results page.**"), guide.index("**Add many from a list.**")
    assert guide.index("### 5.5 Search") < start < end < guide.index("### 5.6"), "the results page, in §5.5"
    return fold(guide[start:end])


def _constants(source: str) -> dict[str, object]:
    """A module's top-level constants, read without importing it (the search service imports the index's client)."""
    found: dict[str, object] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign):
            target = node.target
        elif isinstance(node, ast.Assign):
            target = node.targets[0]
        else:
            continue
        if isinstance(target, ast.Name) and node.value is not None:
            try:
                found[target.id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return found


def _function(source: str, name: str) -> str:
    """One function's source, whitespace folded."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return fold(ast.get_source_segment(source, node) or "")
    raise AssertionError(f"no function {name}")


def _template(words: str) -> str:
    """A screen template literal's text with each placeholder written as the guide writes it, '…'."""
    return re.sub(r"\$\{[^}]+\}", "…", words)


SERVICE_CONSTANTS = _constants(SERVICE)


# ---------------------------------------------------------------- opening it


def test_section_5_5_says_enter_on_the_typed_words_opens_the_page_and_a_suggestion_is_still_chosen() -> None:
    """Combobox's Enter submits the words only when no option is highlighted; the box's submit opens the results."""
    assert 'if (onSubmit && e.key === "Enter" && !(open && highlighted >= 0 && filtered[highlighted])) {' in COMBOBOX
    assert "const none = onSubmit ? -1 : 0;" in COMBOBOX, "nothing highlighted until the arrows move to an option"
    chosen = '} else if (e.key === "Enter") { e.preventDefault(); const option = filtered[Math.min(highlighted, filtered.length - 1)]; if (option) select(option);'
    assert chosen in COMBOBOX, "Enter on a suggestion moved to chooses it"
    assert "onSubmit={onSearch}" in BOX
    assert "onSearch={(query) => results.open(query," in APP
    text = results_text()
    assert "Press Enter on the words you typed, with no suggestion moved to, and the results fill the main area" in text
    assert "a suggestion moved to with the arrow keys is still chosen by Enter" in text
    row = "| The top bar's search box | Enter | The search results page for the words typed; with a suggestion moved to by the arrows, that suggestion |"
    assert row in GUIDE[GUIDE.index("## 12. Keys") :]


def test_section_5_5_says_the_view_waits_beneath_out_of_reach_and_back_returns_to_it() -> None:
    assert "viewInert: searching !== null && !reading," in OVERLAY
    assert 'inert={app === "glass" && results.viewInert ? true : undefined}' in APP
    assert "back: () => { focusBox.current = true; setSearching(null); }," in OVERLAY
    assert "onBack={results.back}" in APP and "{`Back to ${backLabel}`}" in PAGE
    text = results_text()
    assert "over the view you were on, which waits beneath them as it was and cannot be reached until you leave them" in text
    assert "**Back to ‹view›** returns to the view as you left it." in text


# ---------------------------------------------------------------- the page's words and counts


def test_section_5_5_quotes_the_heading_the_empty_lines_and_the_ask_line_as_the_page_words_them() -> None:
    text = results_text()
    heading = re.search(r"\{`(Search results for '\$\{query\}')`\}", PAGE)
    assert heading and f'headed "{_template(heading.group(1))}"' in text
    empty = "{`No records match '${query}'${group === null ? \"\" : \" in this group\"}.`}"
    assert empty in PAGE, "the empty line, its group suffix and its full stop"
    assert "\"No records match '…'.\", or \"No records match '…' in this group.\" once a group is chosen" in text
    assert "{shown && shown.results.length === 0 && shown.page === 1 && (" in PAGE
    ask = re.search(r"\{`(Ask a question about '\$\{query\}' instead)`\}", PAGE)
    assert ask and f'a last line, "{_template(ask.group(1))}"' in text


def test_section_5_5_gives_the_count_under_the_heading_as_the_page_chooses_it() -> None:
    """The total, or the chosen group's own count; marked incomplete only when the Conduit says the counts are not exact."""
    assert "const groupCount = counts && group !== null ? counts.groups.find((g) => g.key === group)?.count : undefined;" in PAGE
    assert '`${records(groupCount ?? counts.total)}${counts.counts_exact ? "" : " (counts may be incomplete)"}`' in PAGE
    text = results_text()
    assert "the total, or a group's own count once you choose one, and \"(counts may be incomplete)\" when the Conduit cannot be sure" in text


def test_section_5_5_names_the_groups_filters_and_pages_as_the_page_labels_them() -> None:
    labels = {
        "All": '{ key: null, label: "All", count: counts.total }',
        "Datasets": ">Datasets</legend>",
        "Dates": ">Dates</legend>",
        "Clear filters": "> Clear filters </button>",
        "Next page": "> Next page </button>",
        "Previous page": "> Previous page </button>",
    }
    assert [label for label, code in labels.items() if code not in PAGE] == []
    # The filters are what the answer offers: drawn only where it offers datasets or dates.
    for offered in ("{counts && (counts.filters.datasets.length > 0 || counts.filters.dates) && (", "{counts.filters.datasets.length > 0 && (", "{counts.filters.dates && ("):
        assert offered in PAGE, offered
    assert "**Datasets** and **Dates** narrow it again to what the search offers" in results_text()
    text = results_text()
    assert [label for label in labels if f"**{label}**" not in text] == []
    # Clear filters is drawn only where a filter is on, beside the filters and in the empty state.
    assert PAGE.count("{filtered && clear}") == 2
    assert 'const filtered = filters.datasets.length > 0 || filters.dateFrom !== "" || filters.dateTo !== "";' in PAGE
    assert "with **Clear filters** where a filter is on" in text


def test_section_5_5_says_the_box_s_filters_shape_suggestions_alone_and_the_page_starts_unfiltered() -> None:
    assert "const [group, setGroup] = useState<string | null>(null);" in PAGE
    assert "const [filters, setFilters] = useState<Filters>(NO_FILTERS);" in PAGE
    assert 'const NO_FILTERS: Filters = { datasets: [], dateFrom: "", dateTo: "" };' in PAGE
    # Nothing of the box's own filters reaches the page: it takes none, and App gives it only the words.
    props = re.search(r"export interface SearchResultsProps \{(.*?)\} interface Filters", PAGE)
    assert props and not re.search(r"\b(filters|group|types|entityTypes)\??:", props.group(1)), "the page takes no filter"
    element = APP[APP.index("<SearchResults") : APP.index("onShow={(nodes)")]
    assert "query={searching.query}" in element and "filters=" not in element and "group=" not in element
    assert "The search box's **Filters** shape its suggestions alone: the page starts at **All** with no filter." in results_text()


def test_section_5_5_gives_the_page_size_the_page_asks_for() -> None:
    m = re.search(r"export const RESULTS_PAGE_SIZE = (\d+);", PAGE)
    assert m and "page, page_size: RESULTS_PAGE_SIZE })" in PAGE
    assert f"Results come {m.group(1)} a page" in results_text()


def test_section_5_5_lists_what_each_result_shows_as_the_page_draws_it() -> None:
    assert "const name = first ? nodeLabel(first) : result.type;" in PAGE
    for part in ("<span>{result.type}</span>", "<span>{result.match.why}</span>", "<span>{result.date}</span>"):
        assert part in PAGE, part
    assert "part.match ? <mark key={i}>{part.text}</mark>" in PAGE
    assert (
        "Each gives its name as the canvas names it, its type, why it matched and its date, and for a document the "
        "passage with the matched words marked." in results_text()
    )


# ---------------------------------------------------------------- the actions


def test_section_5_5_says_show_on_graph_draws_the_records_read_says_the_rest_and_goes_to_the_graph() -> None:
    assert "nodes={result.node_ids.map((id) => byId.get(id)).filter((n): n is Node => n !== undefined)}" in PAGE
    assert "disabled={nodes.length === 0} onClick={() => onShow(nodes)}> Show on graph </button>" in PAGE
    unread = re.search(r"\{`(\$\{unread\} of its \$\{result\.node_ids\.length\} records could not be read\.)`\}", PAGE)
    assert unread and "const unread = result.node_ids.length - nodes.length;" in PAGE
    show = re.search(r"onShow=\{\(nodes\) => \{(.*?)\}\} onOpenDocument=", APP)
    assert show, "App's Show on graph"
    for step in ("void seedToCanvas(nodes, []);", "setSelectedNode(nodes[0] ?? null);", "results.leave();", 'setView("graph");'):
        assert step in show.group(1), step
    text = results_text()
    assert "**Show on graph** puts the records the result stands for on the graph, selects the first and takes you there" in text
    example = re.search(r'a record the result names that could not be read is said, as in "((\d+) of its (\d+) records could not be read\.)"', text)
    assert example and int(example.group(2)) < int(example.group(3))
    shape = re.escape(unread.group(1)).replace(re.escape("${unread}"), r"\d+").replace(re.escape("${result.node_ids.length}"), r"\d+")
    assert re.fullmatch(shape, example.group(1))


def test_section_5_5_says_open_sets_the_results_aside_and_reads_the_document_over_the_view() -> None:
    assert "{result.is_document && first && ( <button" in PAGE
    assert "aria-label={`Open ${name}`} onClick={() => onOpenDocument(first.id)}> Open </button>" in PAGE
    assert "hidden={results.resultsHidden}" in APP and "resultsHidden: reading," in OVERLAY
    assert "if (was && !reading && searching !== null) document.querySelector<HTMLElement>(RESULTS_HEADING)?.focus();" in OVERLAY
    text = results_text()
    assert "**Open**, for a document, sets the results aside and reads it over the view; they come back when you close it." in text
    assert "reads it over the results" not in text


def test_section_5_5_says_the_ask_line_is_for_someone_offered_ask_and_chat_and_sends_nothing() -> None:
    m = re.search(r'onAsk=\{railEntries\(rights\)\.includes\("questions"\) \? \(words\) => \{(.*?)\} : undefined\}', APP)
    assert m, "App gives the page onAsk only where the rail offers Ask & Chat"
    assert m.group(1).strip() == "setQuestionDraft({ text: words, at: Date.now() }); setQuestionsOpen(true);", "and it sends nothing"
    # Ask & Chat puts the words in its box and focuses it; asking stays the person's, by Ask.
    assert "useEffect(() => { if (!draft) return; setQuestion(draft.text); questionBox.current?.focus(); }, [draft]);" in PANEL
    assert "const askLine = onAsk && (" in PAGE
    assert "Where Ask & Chat is offered to you, a last line" in results_text()
    assert "in the question box, sending nothing until you press **Ask**." in results_text()


# ---------------------------------------------------------------- refusals


def test_section_5_5_gives_the_search_s_limit_and_its_refusal_as_the_schema_and_page_do() -> None:
    """A query over `MAX_QUERY_CHARS` is refused by the request's own schema; the page names the limit and the query's
    length from FastAPI's list for that field, and sends the words whole: no maxLength cuts them in the box (rule 2)."""
    from schemas.search import MAX_QUERY_CHARS, SearchPageRequest

    limits = [getattr(m, "max_length", None) for m in SearchPageRequest.model_fields["query"].metadata]
    assert limits.count(MAX_QUERY_CHARS) == 1
    assert 'd.type === "string_too_long" && Array.isArray(d.loc) && d.loc.at(-1) === "query"' in PAGE
    refusal = "a search can be at most ${entry.ctx.max_length} characters, and this one has ${[...query].length}. Shorten it and press Enter again."
    assert refusal in PAGE
    assert "body: JSON.stringify({ query, group," in PAGE and "maxLength" not in COMBOBOX and "maxLength" not in BOX
    text = results_text()
    assert f"A search can be at most {MAX_QUERY_CHARS} characters." in text
    assert "saying the limit and how many characters yours has, and is never cut short: shorten it and press Enter again" in text


def test_section_5_5_quotes_the_conduit_s_other_refusals_in_its_words() -> None:
    check = _function(SERVICE, "_check")
    assert 'raise ValueError("the date filter ends before it starts")' in check
    assert 'f"results are listed {q.MAX_DEPTH} deep at most; narrow the search to see further"' in check
    route = _function(ROUTES, "search_route")
    assert "except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc" in route, "the words reach the page as the detail"
    depth = _constants((API / "search_index_query.py").read_text(encoding="utf-8"))["MAX_DEPTH"]
    assert 'const detail = typeof body?.detail === "string" ? body.detail : tooLong(body?.detail, query);' in PAGE
    text = results_text()
    assert '("the date filter ends before it starts")' in text
    assert f'("results are listed {depth} deep at most; narrow the search to see further")' in text


# ---------------------------------------------------------------- the fallback


def test_section_5_5_quotes_the_fallback_s_line_and_says_what_it_cannot_do() -> None:
    reasons, dates_line = SERVICE_CONSTANTS["LIMITED_REASONS"], SERVICE_CONSTANTS["DATES_NOT_APPLIED"]
    depth = SERVICE_CONSTANTS["FALLBACK_DEPTH"]
    fallback = _function(SERVICE, "_from_graph")
    for code in (
        "SearchRequest(query=request.query, limit=FALLBACK_DEPTH)",
        "limited=True,",
        "counts_exact=False,",
        "DatasetFilter(id=d, name=n, count=None)",
        "dates=None,",
        "if request.filters.date_from or request.filters.date_to: reason += DATES_NOT_APPLIED",
    ):
        assert code in fallback, code
    assert "{shown?.limited && ( <p" in PAGE and "{shown.limited_reason ?? " in PAGE, "the page shows the Conduit's line where it gives one"
    text = results_text()
    assert f'the page says so in one line, such as "{reasons["no_index"]}"' in text
    assert f"looks no further than the first {depth} exact matches" in text
    assert "Its counts are of those, and always marked incomplete; the datasets are offered without counts, and there are no dates to filter by." in text
    assert f'A date filter already set is not applied, and the line then adds "{dates_line.strip()}"' in text


def test_section_5_5_says_the_fallback_pages_only_while_records_remain_and_where_its_depth_ends_the_list() -> None:
    """Studio's paging fix: `more` only when a further page holds records, and the depth's line on the page that ends
    a list the fallback's depth cut short; the page offers *Next page* only on `more`."""
    depth, line = SERVICE_CONSTANTS["FALLBACK_DEPTH"], SERVICE_CONSTANTS["DEPTH_REACHED"]
    fallback = _function(SERVICE, "_from_graph")
    for code in (
        "reached = len(found) >= FALLBACK_DEPTH",
        "more = len(found) > start + size",
        "if reached and not more: reason += DEPTH_REACHED.format(depth=FALLBACK_DEPTH)",
        "more=more,",
    ):
        assert code in fallback, code
    assert "{shown && (shown.page > 1 || shown.more) && (" in PAGE and "{more && (" in PAGE
    text = results_text()
    assert "**Next page** is offered only while a further page holds records" in text
    assert f"where the {depth} end the list, its last page's line adds \"{line.format(depth=depth).strip()}\"" in text
