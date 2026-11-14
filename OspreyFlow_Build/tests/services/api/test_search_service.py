"""The search service (ADR-149; v0.5.2 step 3d): an index reply into the response shape the results
page is built against (`schemas.search`), the fallback to today's search, merged entities and the
suggestions from the index. What a mistake would do, and the case that catches it:

- the index asked with no access filter, or a fallback that does not say so, or says the index
  "cannot be reached" when there is none (`test_with_no_access_filter_the_index_is_never_asked`,
  `test_with_no_index_the_fallback_says_there_is_none`);
- anything but an unreachable index hidden behind "limited" (the owner's requirement c)
  (`test_only_an_unreachable_index_falls_back`, `test_any_other_failure_is_raised_not_hidden`);
- a node the index has not caught up with counted under stale facts (the orchestrator's ruling on
  page A) (`test_nodes_the_index_has_not_caught_up_with_are_left_out_and_counts_not_exact`,
  `test_a_pending_set_not_known_to_be_whole_and_the_graph_answers`);
- a hit the graph does not return listed or counted as exact
  (`test_a_hit_the_graph_does_not_return_is_dropped_and_counts_are_not_exact`);
- a dataset outside the reader's case offered or asked
  (`test_a_dataset_outside_the_case_is_never_offered`,
  `test_a_filter_on_a_dataset_outside_the_case_is_refused`);
- a list-valued property crashing a search (`test_a_list_valued_property_never_breaks_a_search`);
- the fallback cutting silently (rule 2) (`test_the_fallback_says_more_at_its_depth`,
  `test_a_page_past_the_depth_is_refused_on_either_path`,
  `test_the_fallback_narrows_by_group_and_dataset_before_it_pages`);
- a merge through a member or a link the reader may not see
  (`test_a_merge_through_a_hidden_member_is_not_made`,
  `test_a_hidden_same_as_between_visible_records_merges_nothing`);
- a suggestion narrowed on a property the index did not match, or a fallback suggestion that does
  not say it is limited (`test_a_case_sensitive_suggestion_looks_only_at_identifiers_and_names`,
  `test_a_suggestion_the_graph_answers_says_it_is_limited`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date
from typing import Any

import opensearchpy
import pytest
from services.api import search_index_query as q
from services.api import search_service as s
from services.api.search import SuggestRequest

from ontology.loader import load_default_ontology
from ports.graph import NodeSuggestions
from schemas.domain import NOT_SAME_AS, SAME_AS, Edge, Node, Principal
from schemas.search import SearchFilters, SearchPageRequest, SearchPageResponse
from tests.services.api.test_search_route import _node

ANALYST = Principal(
    id="analyst-1",
    clearance="OFFICIAL",
    org_unit="unit-1",
    roles=["analyst"],
    datasets=["ds-1", "ds-2"],
)
ACCESS = {"bool": {"filter": [{"terms": {"handling_classification": ["OFFICIAL"]}}]}}
CASE = {"ds-1": "Fixture Corp", "ds-2": "Harbour Street"}
TYPES = ["Person", "Document"]
SCHEMA = load_default_ontology()
B = q.BAND_SCORES


def _typed(
    node_id: str, type_: str = "Person", datasets: Sequence[str] = ("ds-1",), **props: Any
) -> Node:
    node = _node(node_id)
    return node.model_copy(update={"type": type_, "properties": props, "datasets": list(datasets)})


def _link(kind: str, a: str, b: str, score: float = 0.97, link_id: str | None = None) -> Edge:
    base = _node("x")
    return Edge(
        id=link_id or f"{kind}:{a}:{b}",
        type=kind,
        source=a,
        target=b,
        properties={"score": score},
        provenance=base.provenance,
        handling=base.handling,
        audit=base.audit,
    )


class _Graph:
    """The graph as the reader sees it: `nodes` are visible; `hidden_links` are not, and the
    adapter's filter keeps them, and every link to a node not asked for, out of every read."""

    def __init__(
        self,
        nodes: Sequence[Node] = (),
        exact: Sequence[Node] = (),
        links: Sequence[Edge] = (),
        hidden_links: Sequence[str] = (),
    ) -> None:
        self.nodes = {n.id: n for n in nodes}
        self.exact = list(exact)
        self.links = list(links)
        self.hidden_links = set(hidden_links)
        self.asked: list[list[str]] = []
        self.among: list[list[str]] = []
        self.suggested: list[str] = []

    async def get_nodes(self, node_ids: Sequence[str], principal: Principal) -> list[Node]:
        self.asked.append(list(node_ids))
        return [self.nodes[i] for i in node_ids if i in self.nodes]

    async def edges_among(
        self, node_ids: Sequence[str], principal: Principal, *, edge_types: Sequence[str]
    ) -> list[Edge]:
        self.among.append(list(node_ids))
        ids = set(node_ids)
        return [
            e
            for e in self.links
            if e.type in edge_types
            and e.source in ids
            and e.target in ids
            and e.id not in self.hidden_links
        ]

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        return self.exact[:limit]

    async def suggest_nodes(
        self, prefix: str, principal: Principal, *, limit: int = 10, options: Any = None
    ) -> NodeSuggestions:
        self.suggested.append(prefix)
        return NodeSuggestions(nodes=[], more=False)


class _Index:
    def __init__(self, reply: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.bodies: list[dict[str, Any]] = []
        self.timeouts: list[float] = []

    async def __call__(self, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.bodies.append(body)
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        assert self.reply is not None
        return self.reply


def _hit(
    node_id: str, score: float, kind: str = "node", date_: str | None = None
) -> dict[str, Any]:
    return {
        "_id": node_id if kind == "node" else f"text:{node_id}",
        "_score": score,
        "_source": {"node_id": node_id, "kind": kind, **({"date": date_} if date_ else {})},
    }


def _reply(hits: list[dict[str, Any]], datasets: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "hits": {"hits": hits},
        "aggregations": {
            "by_type": {
                "types": {
                    "doc_count_error_upper_bound": 0,
                    "sum_other_doc_count": 0,
                    "buckets": [{"key": "Person", "doc_count": 2}],
                }
            },
            "mentions": {"doc_count": 1},
            "datasets": {
                "doc_count_error_upper_bound": 0,
                "sum_other_doc_count": 0,
                "buckets": [
                    {"key": k, "doc_count": v} for k, v in (datasets or {"ds-1": 3}).items()
                ],
            },
            "earliest": {"value": 1.0, "value_as_string": "2025-03-02T00:00:00.000Z"},
            "latest": {"value": 2.0, "value_as_string": "2026-10-30T00:00:00.000Z"},
        },
    }


def _ask(
    request: SearchPageRequest,
    graph: _Graph,
    index: _Index | None,
    access: dict[str, Any] | None = ACCESS,
    tau: float | None = None,
    pending: Sequence[str] = (),
    pending_complete: bool = True,
) -> SearchPageResponse:
    return asyncio.run(
        s.search_page(
            request,
            ANALYST,
            graph,  # type: ignore[arg-type]
            searcher=index,
            access_filter=access,
            phonetic_codes=lambda w: ["SM0"] if w.lower() in {"smith", "smyth"} else [],
            types=TYPES,
            case_datasets=CASE,
            tau=tau,
            pending=pending,
            pending_complete=pending_complete,
            schema=SCHEMA,
        )
    )


# --- the index path -------------------------------------------------------------------------------


def test_an_index_reply_becomes_the_response_shape() -> None:
    graph = _Graph([_typed("p1", family_name="Smith"), _typed("d1", "Document", title="Memo")])
    reply = _reply([_hit("p1", B["name_sounds"], date_="2026-01-02"), _hit("d1", 1500, "text")])
    index = _Index(reply)
    out = _ask(SearchPageRequest(query="Smyth"), graph, index)

    assert (out.source, out.limited, out.limited_reason) == ("index", False, None)
    assert [r.node_ids for r in out.results] == [["p1"], ["d1"]]
    assert [n.id for n in out.nodes] == ["p1", "d1"]
    first, second = out.results
    assert (first.type, first.match.band, first.date, first.is_document) == (
        "Person",
        "name_sounds",
        "2026-01-02",
        False,
    )
    assert (first.match.why, first.match.field) == ("Sounds like 'Smyth'", "Family name")
    assert (second.type, second.match.band, second.is_document) == (
        "Document",
        "mention_phrase",
        True,
    )
    assert [(g.key, g.label, g.count) for g in out.groups] == [
        ("Person", "People", 2),
        ("mentions", "Mentioned in documents", 1),
    ]
    assert out.total == 3
    assert out.counts_exact is True
    assert [(d.id, d.name, d.count) for d in out.filters.datasets] == [("ds-1", "Fixture Corp", 3)]
    assert out.filters.dates is not None
    assert (out.filters.dates.earliest, out.filters.dates.latest) == ("2025-03-02", "2026-10-30")
    assert graph.asked == [["p1", "d1"]]
    assert index.timeouts == [s.SEARCH_TIMEOUT]


def test_the_request_reaches_the_body_whole() -> None:
    index = _Index(_reply([]))
    request = SearchPageRequest(
        query="Smyth",
        group="Person",
        filters=SearchFilters(
            datasets=["ds-2"], date_from=date(2026, 1, 1), date_to=date(2026, 2, 1)
        ),
        page=2,
        page_size=10,
    )
    _ask(request, _Graph(), index)
    (body,) = index.bodies
    filters = body["query"]["bool"]["filter"]
    assert filters[0] == ACCESS
    assert {"terms": {"datasets": ["ds-2"]}} in filters
    assert {"range": {"date": {"gte": "2026-01-01", "lte": "2026-02-01"}}} in filters
    assert (body["from"], body["size"]) == (10, 11)
    assert body["post_filter"]["bool"]["filter"][1] == {"term": {"type": "Person"}}
    assert body["aggs"]["datasets"]["terms"]["include"] == ["ds-1", "ds-2"]


def test_group_labels_and_the_matched_fields_display_name() -> None:
    assert [s.group_label(t) for t in ("Person", "Document", "Address", "Company", "Day")] == [
        "People",
        "Documents",
        "Addresses",
        "Companies",
        "Days",
    ]
    assert s.display_name("family_name") == "Family name"


def test_a_date_with_an_offset_is_read_in_utc() -> None:
    graph = _Graph([_typed("d1", "Document")])
    reply = _reply([_hit("d1", 1500, "text", date_="2026-01-02T00:30:00+01:00")])
    assert _ask(SearchPageRequest(query="x"), graph, _Index(reply)).results[0].date == "2026-01-01"


def test_a_hit_the_graph_does_not_return_is_dropped_and_counts_are_not_exact() -> None:
    """The graph stays the source of truth (the owner's requirement b): a hit it does not show the
    reader is never listed, and the counts beside it are then not shown as exact (rule 2)."""
    graph = _Graph([_typed("p1")])
    reply = _reply([_hit("p1", 3000), _hit("gone", 2900)])
    out = _ask(SearchPageRequest(query="x"), graph, _Index(reply))
    assert [r.node_ids for r in out.results] == [["p1"]]
    assert out.counts_exact is False


def test_a_dataset_outside_the_case_is_never_offered() -> None:
    out = _ask(
        SearchPageRequest(query="x"),
        _Graph(),
        _Index(_reply([], datasets={"ds-1": 3, "ds-elsewhere": 3})),
    )
    assert [d.id for d in out.filters.datasets] == ["ds-1"]


def test_a_filter_on_a_dataset_outside_the_case_is_refused() -> None:
    request = SearchPageRequest(query="x", filters=SearchFilters(datasets=["ds-elsewhere"]))
    with pytest.raises(ValueError, match="ds-elsewhere"):
        _ask(request, _Graph(), _Index(_reply([])))


def test_a_date_filter_that_ends_before_it_starts_is_refused() -> None:
    request = SearchPageRequest(
        query="x", filters=SearchFilters(date_from=date(2026, 2, 1), date_to=date(2026, 1, 1))
    )
    with pytest.raises(ValueError, match="ends before it starts"):
        _ask(request, _Graph(), _Index(_reply([])))


def test_the_page_size_wins_over_the_old_limit() -> None:
    index = _Index(_reply([]))
    _ask(SearchPageRequest(query="x", limit=50, page_size=5), _Graph(), index)
    _ask(SearchPageRequest(query="x", limit=7), _Graph(), index)
    assert [b["size"] for b in index.bodies] == [6, 8]


def test_a_list_valued_property_never_breaks_a_search() -> None:
    """A `string[]` property (a Person's aliases) beside the identifier the search found, on both
    paths (the lane review of d2b207a found a `TypeError` here)."""
    person = _typed("p1", aliases=["Jon", "Johnny"], given_names=["Jon", "J"], nino="AB123456C")
    on_index = _ask(
        SearchPageRequest(query="AB123456C"), _Graph([person]), _Index(_reply([_hit("p1", 3000)]))
    )
    assert on_index.results[0].match.field == "Nino"
    fallback = _ask(SearchPageRequest(query="AB123456C"), _Graph(exact=[person]), None)
    assert fallback.results[0].match.field == "Nino"
    # A list in a searchable name, matched as one of its values.
    by_name = _ask(
        SearchPageRequest(query="jon"), _Graph([person]), _Index(_reply([_hit("p1", 2900)]))
    )
    assert by_name.results[0].match.field == "Given names"


def test_a_page_past_the_depth_is_refused_on_either_path() -> None:
    deep = SearchPageRequest(query="x", page=q.MAX_DEPTH // 20 + 1, page_size=20)
    for index in (_Index(_reply([])), None):
        with pytest.raises(ValueError, match=str(q.MAX_DEPTH)):
            _ask(deep, _Graph(), index)


# --- the outbox's pending nodes (the orchestrator's ruling on page A) -----------------------------


def test_nodes_the_index_has_not_caught_up_with_are_left_out_and_counts_not_exact() -> None:
    index = _Index(_reply([]))
    out = _ask(SearchPageRequest(query="x"), _Graph(), index, pending=["p9", "p8"])
    (body,) = index.bodies
    assert body["query"]["bool"]["must_not"] == [{"terms": {"node_id": ["p8", "p9"]}}]
    assert body["query"]["bool"]["filter"][0] == ACCESS
    assert out.counts_exact is False


def test_a_pending_set_not_known_to_be_whole_and_the_graph_answers() -> None:
    index = _Index(_reply([]))
    out = _ask(
        SearchPageRequest(query="x"), _Graph(exact=[_typed("a")]), index, pending_complete=False
    )
    assert index.bodies == []
    assert (out.source, out.limited_reason) == ("fallback", s.LIMITED_REASONS["catching_up"])


# --- the fallback ---------------------------------------------------------------------------------


def test_with_no_access_filter_the_index_is_never_asked() -> None:
    index = _Index(_reply([]))
    out = _ask(SearchPageRequest(query="x"), _Graph(exact=[_typed("p1")]), index, access=None)
    assert index.bodies == []
    assert (out.source, out.limited) == ("fallback", True)


def test_with_no_index_the_fallback_says_there_is_none() -> None:
    out = _ask(SearchPageRequest(query="AB123456C"), _Graph(exact=[_typed("p1")]), None)
    assert (out.source, out.limited) == ("fallback", True)
    assert out.limited_reason == s.LIMITED_REASONS["no_index"]
    assert "cannot be reached" not in out.limited_reason
    assert [r.node_ids for r in out.results] == [["p1"]]
    assert [n.id for n in out.nodes] == ["p1"]
    assert out.results[0].match.band == "identifier"
    assert out.counts_exact is False
    assert [(g.key, g.label, g.count) for g in out.groups] == [("Person", "People", 1)]
    assert [(d.id, d.count) for d in out.filters.datasets] == [("ds-1", None), ("ds-2", None)]
    assert out.filters.dates is None


def test_only_an_unreachable_index_falls_back() -> None:
    error = s.IndexUnavailable("refused")
    out = _ask(SearchPageRequest(query="x"), _Graph(exact=[_typed("p1")]), _Index(error=error))
    assert (out.source, out.limited_reason) == ("fallback", s.LIMITED_REASONS["unreachable"])


def test_an_index_that_answers_badly_is_raised() -> None:
    """A query the index refuses, or any failure other than an unreachable index, is this code's
    defect or the deployment's, never shown as "limited" (the orchestrator's review)."""
    error = RuntimeError("parsing_exception")
    with pytest.raises(RuntimeError, match="parsing_exception"):
        _ask(SearchPageRequest(query="x"), _Graph(), _Index(error=error))


def test_the_fallback_says_more_at_its_depth() -> None:
    graph = _Graph(exact=[_typed(f"p{i}") for i in range(s.FALLBACK_DEPTH)])
    out = _ask(SearchPageRequest(query="x", page=5, page_size=20), graph, None)
    assert len(out.results) == 20
    assert out.more is True  # today's search stopped at its depth: there may be more


def test_the_fallback_pages_today_s_results() -> None:
    graph = _Graph(exact=[_typed(f"p{i}") for i in range(5)])
    out = _ask(SearchPageRequest(query="x", page=2, page_size=2), graph, None)
    assert [r.node_ids for r in out.results] == [["p2"], ["p3"]]
    assert out.more is True
    last = _ask(SearchPageRequest(query="x", page=3, page_size=2), graph, None)
    assert [r.node_ids for r in last.results] == [["p4"]] and last.more is False


def test_the_fallback_narrows_by_group_and_dataset_before_it_pages() -> None:
    nodes = [
        _typed("d1", "Document"),
        _typed("p1"),
        _typed("p2", datasets=["ds-2"]),
        _typed("p3"),
    ]
    out = _ask(
        SearchPageRequest(
            query="x", group="Person", filters=SearchFilters(datasets=["ds-1"]), page_size=1
        ),
        _Graph(exact=nodes),
        None,
    )
    assert [r.node_ids for r in out.results] == [["p1"]] and out.more is True
    assert {g.key: g.count for g in out.groups} == {"Document": 1, "Person": 2}


def test_the_fallback_says_it_cannot_apply_a_date_filter() -> None:
    request = SearchPageRequest(query="x", filters=SearchFilters(date_from=date(2026, 1, 1)))
    out = _ask(request, _Graph(exact=[_typed("p1")]), None)
    assert out.limited_reason == s.LIMITED_REASONS["no_index"] + s.DATES_NOT_APPLIED


# --- merged entities (page A §2, as ruled) --------------------------------------------------------


def test_visible_hits_the_case_reads_as_one_are_one_result() -> None:
    graph = _Graph([_typed("a"), _typed("b"), _typed("c")], links=[_link(SAME_AS, "a", "b")])
    reply = _reply([_hit("a", 3000), _hit("c", 2900), _hit("b", 2500)])
    out = _ask(SearchPageRequest(query="x"), graph, _Index(reply), tau=0.95)
    assert [(r.node_ids, r.match.band) for r in out.results] == [
        (["a", "b"], "identifier"),
        (["c"], "name_exact"),
    ]
    assert [n.id for n in out.nodes] == ["a", "b", "c"]


def test_a_merge_below_the_cases_threshold_or_split_is_not_made() -> None:
    reply = _reply([_hit("a", 3000), _hit("b", 2500)])
    below = _Graph([_typed("a"), _typed("b")], links=[_link(SAME_AS, "a", "b", 0.90)])
    assert len(_ask(SearchPageRequest(query="x"), below, _Index(reply), tau=0.95).results) == 2
    split = _Graph(
        [_typed("a"), _typed("b")], links=[_link(SAME_AS, "a", "b"), _link(NOT_SAME_AS, "a", "b")]
    )
    assert len(_ask(SearchPageRequest(query="x"), split, _Index(reply), tau=0.95).results) == 2


def test_a_merge_through_a_hidden_member_is_not_made() -> None:
    """A and B are each the same as H, whom the reader may not see. H is never asked for, so A and
    B stay apart: the reader cannot learn of H from A and B shown as one."""
    graph = _Graph(
        [_typed("a"), _typed("b")], links=[_link(SAME_AS, "a", "h"), _link(SAME_AS, "h", "b")]
    )
    reply = _reply([_hit("a", 3000), _hit("h", 2900), _hit("b", 2500)])
    out = _ask(SearchPageRequest(query="x"), graph, _Index(reply), tau=0.95)
    assert [r.node_ids for r in out.results] == [["a"], ["b"]]
    assert graph.among == [["a", "b"]]


def test_a_hidden_same_as_between_visible_records_merges_nothing() -> None:
    graph = _Graph(
        [_typed("a"), _typed("b")],
        links=[_link(SAME_AS, "a", "b", link_id="secret-link")],
        hidden_links=["secret-link"],
    )
    reply = _reply([_hit("a", 3000), _hit("b", 2500)])
    out = _ask(SearchPageRequest(query="x"), graph, _Index(reply), tau=0.95)
    assert [r.node_ids for r in out.results] == [["a"], ["b"]]


def test_with_no_threshold_nothing_is_merged_and_no_link_is_read() -> None:
    graph = _Graph([_typed("a"), _typed("b")], links=[_link(SAME_AS, "a", "b")])
    reply = _reply([_hit("a", 3000), _hit("b", 3000)])
    out = _ask(SearchPageRequest(query="x"), graph, _Index(reply))
    assert len(out.results) == 2
    assert graph.among == []


def test_the_fallback_merges_the_same_way() -> None:
    nodes = [_typed("a"), _typed("b")]
    graph = _Graph(nodes, exact=nodes, links=[_link(SAME_AS, "a", "b")])
    out = _ask(SearchPageRequest(query="x"), graph, None, tau=0.95)
    assert [r.node_ids for r in out.results] == [["a", "b"]]


# --- the searcher over a real client's errors -----------------------------------------------------


class _Client:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, Any], float]] = []

    async def search(
        self, *, index: str, body: dict[str, Any], request_timeout: float
    ) -> dict[str, Any]:
        self.calls.append((index, body, request_timeout))
        if self.error is not None:
            raise self.error
        return {"hits": {"hits": []}}


async def _run(searcher: s.Searcher, body: dict[str, Any]) -> dict[str, Any]:
    return await searcher(body, 2.0)


def test_the_searcher_asks_the_alias_alone_with_a_short_timeout() -> None:
    client = _Client()
    asyncio.run(_run(s.opensearch_searcher(client, "ospreyflow-default"), {"query": {}}))
    assert client.calls == [("ospreyflow-default", {"query": {}}, 2.0)]


@pytest.mark.parametrize(
    "error",
    [
        opensearchpy.ConnectionError("N/A", "refused", OSError("refused")),
        opensearchpy.ConnectionTimeout("TIMEOUT", "timed out", TimeoutError()),
    ],
)
def test_an_index_that_cannot_be_reached_is_unavailable(error: Exception) -> None:
    with pytest.raises(s.IndexUnavailable):
        asyncio.run(_run(s.opensearch_searcher(_Client(error), "a"), {}))


@pytest.mark.parametrize(
    "error",
    [
        opensearchpy.SSLError("N/A", "certificate verify failed", OSError("tls")),
        opensearchpy.RequestError(400, "parsing_exception", {}),
        opensearchpy.AuthenticationException(401, "unauthorised", {}),
        opensearchpy.AuthorizationException(403, "forbidden", {}),
        opensearchpy.NotFoundError(404, "index_not_found_exception", {}),
        opensearchpy.TransportError(429, "too many requests", {}),
        opensearchpy.TransportError(503, "unavailable", {}),
    ],
)
def test_any_other_failure_is_raised_not_hidden(error: Exception) -> None:
    with pytest.raises(type(error)):
        asyncio.run(_run(s.opensearch_searcher(_Client(error), "a"), {}))


# --- suggestions from the index (ADR-059 Amendment 1) ---------------------------------------------


def _suggest_reply(ids: list[str]) -> dict[str, Any]:
    return {"hits": {"hits": [_hit(i, 2900) for i in ids]}}


def _suggest(
    request: SuggestRequest,
    graph: _Graph,
    index: _Index | None,
    access: dict[str, Any] | None = ACCESS,
    pending: Sequence[str] = (),
    pending_complete: bool = True,
) -> Any:
    return asyncio.run(
        s.suggest_page(
            request,
            ANALYST,
            graph,  # type: ignore[arg-type]
            searcher=index,
            access_filter=access,
            schema=SCHEMA,
            pending=pending,
            pending_complete=pending_complete,
        )
    )


def test_a_suggestion_is_answered_by_the_index_in_its_order() -> None:
    graph = _Graph([_typed("a", family_name="Smythe"), _typed("b", family_name="smyth")])
    index = _Index(_suggest_reply(["b", "a"]))
    out = _suggest(SuggestRequest(query="Smy", ignore_case=True), graph, index, pending=["z"])
    assert [n.id for n in out.nodes] == ["b", "a"] and out.more is False
    assert (out.source, out.limited) == ("index", False)
    assert graph.suggested == []
    (body,) = index.bodies
    assert body["query"]["bool"]["filter"][0] == ACCESS
    assert body["query"]["bool"]["must_not"] == [{"terms": {"node_id": ["z"]}}]
    assert index.timeouts == [s.SUGGEST_TIMEOUT]


def test_a_case_sensitive_suggestion_is_narrowed_and_says_there_may_be_more() -> None:
    graph = _Graph([_typed("a", family_name="Smythe"), _typed("b", family_name="smyth")])
    out = _suggest(SuggestRequest(query="Smy", limit=1), graph, _Index(_suggest_reply(["b", "a"])))
    assert [n.id for n in out.nodes] == ["a"]
    index = _Index({"hits": {"hits": [_hit(f"x{i}", 2900) for i in range(9)]}})
    out = _suggest(SuggestRequest(query="Smy", limit=2), _Graph(), index)
    assert out.nodes == [] and out.more is True  # the index had more than asked; none kept


def test_a_case_sensitive_suggestion_looks_only_at_identifiers_and_names() -> None:
    """The index matched the type's identifiers and names: another property starting with the
    prefix in the typed case (a note, a sensitive one) never keeps a node."""
    graph = _Graph(
        [
            _typed("a", family_name="smythe", notes="Smy note"),
            _typed("b", given_names=["Ann", "Smyla"]),
        ]
    )
    out = _suggest(SuggestRequest(query="Smy"), graph, _Index(_suggest_reply(["a", "b"])))
    assert [n.id for n in out.nodes] == ["b"]


def test_contains_and_exact_stay_on_the_graph() -> None:
    for mode in ("contains", "exact"):
        graph, index = _Graph(), _Index(_suggest_reply([]))
        out = _suggest(SuggestRequest(query="Smy", mode=mode), graph, index)
        assert graph.suggested == ["Smy"] and index.bodies == []
        assert (out.source, out.limited) == ("graph", False)


def test_a_suggestion_the_graph_answers_says_it_is_limited() -> None:
    cases: list[tuple[_Index | None, dict[str, Any] | None, bool]] = [
        (None, ACCESS, True),
        (_Index(_suggest_reply([])), None, True),
        (_Index(error=s.IndexUnavailable("down")), ACCESS, True),
        (_Index(_suggest_reply([])), ACCESS, False),
    ]
    for index, access, complete in cases:
        graph = _Graph()
        out = _suggest(SuggestRequest(query="Smy"), graph, index, access, pending_complete=complete)
        assert graph.suggested == ["Smy"]
        assert (out.source, out.limited) == ("graph", True)


def test_an_unknown_type_is_refused_as_today() -> None:
    with pytest.raises(ValueError, match="Nonsense"):
        _suggest(
            SuggestRequest(query="Smy", types=["Nonsense"]), _Graph(), _Index(_suggest_reply([]))
        )
