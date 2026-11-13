"""The search service (ADR-149, reserved; v0.5.2 step 3d): an index reply into the response shape
the results page is built against (`process/lanes/studio/SEARCH_RESPONSE_SHAPE.md`), and the
fallback to today's search. What a mistake would do, and the case that catches it:

- the index asked with no access filter, or with no index at all, instead of falling back and
  saying so (`test_with_no_access_filter_the_index_is_never_asked`,
  `test_with_no_index_the_fallback_answers_and_says_results_are_limited`);
- an unreachable index shown as an error, or a broken query hidden as "limited"
  (`test_an_unreachable_index_falls_back`, `test_any_other_index_failure_is_not_hidden`);
- a hit the graph does not show (drift, or a record the reader may not see) listed or counted as
  exact (`test_a_hit_the_graph_does_not_return_is_dropped_and_counts_are_not_exact`);
- a dataset outside the reader's case offered as a filter, naming its id
  (`test_a_dataset_outside_the_case_is_never_offered`), or asked for
  (`test_a_filter_on_a_dataset_outside_the_case_is_refused`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest
from services.api import search_index_query as q
from services.api import search_service as s

from schemas.domain import Node, Principal
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
B = q.BAND_SCORES


def _typed(node_id: str, type_: str = "Person", **props: Any) -> Node:
    node = _node(node_id)
    return node.model_copy(update={"type": type_, "properties": props, "datasets": ["ds-1"]})


class _Graph:
    def __init__(self, nodes: Sequence[Node] = (), exact: Sequence[Node] = ()) -> None:
        self.nodes = {n.id: n for n in nodes}
        self.exact = list(exact)
        self.asked: list[list[str]] = []

    async def get_nodes(self, node_ids: Sequence[str], principal: Principal) -> list[Node]:
        self.asked.append(list(node_ids))
        return [self.nodes[i] for i in node_ids if i in self.nodes]

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        return self.exact[:limit]


class _Index:
    def __init__(self, reply: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.bodies: list[dict[str, Any]] = []

    async def __call__(self, body: dict[str, Any]) -> dict[str, Any]:
        self.bodies.append(body)
        if self.error is not None:
            raise self.error
        assert self.reply is not None
        return self.reply


def _hit(node_id: str, score: float, kind: str = "node", date: str | None = None) -> dict[str, Any]:
    return {
        "_id": node_id if kind == "node" else f"text:{node_id}",
        "_score": score,
        "_source": {"node_id": node_id, "kind": kind, **({"date": date} if date else {})},
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
    request: s.SearchPageRequest,
    graph: _Graph,
    index: _Index | None,
    access: dict[str, Any] | None = ACCESS,
) -> s.SearchPageResponse:
    return asyncio.run(
        s.search_page(
            request,
            ANALYST,
            graph,  # type: ignore[arg-type]
            searcher=index,
            access_filter=access,
            phonetic_codes=lambda w: [],
            types=TYPES,
            case_datasets=CASE,
        )
    )


# --- the index path -------------------------------------------------------------------------------


def test_an_index_reply_becomes_the_response_shape() -> None:
    graph = _Graph([_typed("p1", family_name="Smyth"), _typed("d1", "Document", title="Memo")])
    index = _Index(
        _reply([_hit("p1", B["name_sounds"], date="2026-01-02"), _hit("d1", 1500, "text")])
    )
    out = _ask(s.SearchPageRequest(query="Smith"), graph, index)

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
    assert first.match.why == "Sounds like 'Smith'"
    assert (second.type, second.match.band, second.is_document) == (
        "Document",
        "mention_phrase",
        True,
    )
    assert [(g.key, g.count) for g in out.groups] == [("Person", 2), ("mentions", 1)]
    assert out.total == 3
    assert out.counts_exact is True
    assert [(d.id, d.name, d.count) for d in out.filters.datasets] == [("ds-1", "Fixture Corp", 3)]
    assert out.filters.dates is not None
    assert (out.filters.dates.earliest, out.filters.dates.latest) == ("2025-03-02", "2026-10-30")
    assert graph.asked == [["p1", "d1"]]


def test_the_request_reaches_the_body_whole() -> None:
    index = _Index(_reply([]))
    request = s.SearchPageRequest(
        query="Smyth",
        group="Person",
        filters=s.SearchFilters(datasets=["ds-2"], date_from="2026-01-01", date_to="2026-02-01"),
        page=2,
        page_size=10,
    )
    _ask(request, _Graph(), index)
    (body,) = index.bodies
    assert body["query"]["bool"]["filter"][0] == ACCESS
    assert {"terms": {"datasets": ["ds-2"]}} in body["query"]["bool"]["filter"]
    assert {"range": {"date": {"gte": "2026-01-01", "lte": "2026-02-01"}}} in body["query"]["bool"][
        "filter"
    ]
    assert (body["from"], body["size"]) == (10, 11)
    assert body["post_filter"]["bool"]["filter"][1] == {"term": {"type": "Person"}}


def test_a_hit_the_graph_does_not_return_is_dropped_and_counts_are_not_exact() -> None:
    """The graph stays the source of truth (the owner's requirement b): a hit it does not show the
    reader is never listed, and the counts beside it are then not shown as exact (rule 2)."""
    graph = _Graph([_typed("p1")])
    out = _ask(
        s.SearchPageRequest(query="x"),
        graph,
        _Index(_reply([_hit("p1", 3000), _hit("gone", 2900)])),
    )
    assert [r.node_ids for r in out.results] == [["p1"]]
    assert out.counts_exact is False


def test_a_dataset_outside_the_case_is_never_offered() -> None:
    """A node in the case's dataset and another: the other's id is in the index's `datasets`, so its
    bucket comes back; it is not the reader's to see named."""
    out = _ask(
        s.SearchPageRequest(query="x"),
        _Graph(),
        _Index(_reply([], datasets={"ds-1": 3, "ds-elsewhere": 3})),
    )
    assert [d.id for d in out.filters.datasets] == ["ds-1"]


def test_a_filter_on_a_dataset_outside_the_case_is_refused() -> None:
    request = s.SearchPageRequest(query="x", filters=s.SearchFilters(datasets=["ds-elsewhere"]))
    with pytest.raises(ValueError, match="ds-elsewhere"):
        _ask(request, _Graph(), _Index(_reply([])))


def test_the_page_size_wins_over_the_old_limit() -> None:
    index = _Index(_reply([]))
    _ask(s.SearchPageRequest(query="x", limit=50, page_size=5), _Graph(), index)
    _ask(s.SearchPageRequest(query="x", limit=7), _Graph(), index)
    assert [b["size"] for b in index.bodies] == [6, 8]


# --- the fallback ---------------------------------------------------------------------------------


def test_with_no_access_filter_the_index_is_never_asked() -> None:
    index = _Index(_reply([]))
    out = _ask(
        s.SearchPageRequest(query="AB123456C"), _Graph(exact=[_typed("p1")]), index, access=None
    )
    assert index.bodies == []
    assert (out.source, out.limited) == ("fallback", True)


def test_with_no_index_the_fallback_answers_and_says_results_are_limited() -> None:
    out = _ask(s.SearchPageRequest(query="AB123456C"), _Graph(exact=[_typed("p1")]), None)
    assert (out.source, out.limited, out.limited_reason) == ("fallback", True, s.LIMITED_REASON)
    assert [r.node_ids for r in out.results] == [["p1"]]
    assert [n.id for n in out.nodes] == ["p1"]
    assert out.results[0].match.band == "identifier"
    assert out.counts_exact is False
    assert [(g.key, g.count) for g in out.groups] == [("Person", 1)]
    assert [(d.id, d.count) for d in out.filters.datasets] == [("ds-1", None), ("ds-2", None)]
    assert out.filters.dates is None


def test_an_unreachable_index_falls_back() -> None:
    out = _ask(
        s.SearchPageRequest(query="AB123456C"),
        _Graph(exact=[_typed("p1")]),
        _Index(error=s.IndexUnavailable("connection refused")),
    )
    assert (out.source, out.limited) == ("fallback", True)


def test_any_other_index_failure_is_not_hidden() -> None:
    """A query the index refuses is this code's defect, not an outage: it is raised, never shown as
    'results limited'."""
    with pytest.raises(RuntimeError, match="parsing_exception"):
        _ask(
            s.SearchPageRequest(query="x"),
            _Graph(),
            _Index(error=RuntimeError("parsing_exception")),
        )


def test_the_fallback_pages_today_s_results() -> None:
    graph = _Graph(exact=[_typed(f"p{i}") for i in range(5)])
    out = _ask(s.SearchPageRequest(query="x", page=2, page_size=2), graph, None)
    assert [r.node_ids for r in out.results] == [["p2"], ["p3"]]
    assert out.more is True
