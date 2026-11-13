"""The search service (ADR-149, reserved; v0.5.2 step 3d): one search, asked of the index when
there is one and an access filter to ask it with, and of today's graph search otherwise, in the
response shape the results page is built against (`process/lanes/studio/SEARCH_RESPONSE_SHAPE.md`).

- **The graph stays the source of truth** (the owner's requirement b). The index names hits by
  node id, and the nodes are read from the graph through its own access step. A hit the graph does
  not return is never listed, and the counts are then not shown as exact.
- **The fallback says so** (requirement c). With no index, no access filter to ask it with, or an
  index that cannot be reached, today's exact search answers with `limited` set, and the screen
  says results are limited. Any other index failure is this code's defect and is raised, never
  hidden behind "limited".
- **What it never sends:** the index's scores, an index name, or a dataset outside the reader's
  case, even one an index count names.

The access filter is an argument here. It is built by stage 8, after the owner has read page A;
until then the route passes none, so every search takes the fallback.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from ports.graph import GraphPort
from schemas.domain import Node, Principal

from . import search_index_query as q
from .identifier_reading import search_alternative
from .search import SearchRequest, SearchResponse, search

#: The words the screen shows when the fallback answers.
LIMITED_REASON = (
    "Search is limited to exact identifiers just now: the search index cannot be reached."
)

#: Today's search returns at most this many, so the fallback lists no deeper.
FALLBACK_DEPTH = 100

_WHY: dict[str, str] = {
    "identifier": "Exact identifier",
    "name_exact": "Exact name",
    "name_words": "Every word of the name",
    "name_sounds": "Sounds like '{query}'",
    "name_typo": "Spelt like '{query}'",
    "mention_phrase": "Mentions the phrase",
    "mention_words": "Mentions every word",
    "mention_some": "Mentions some of the words",
}


class IndexUnavailable(Exception):
    """The index cannot be reached. Raised by the searcher, and the one failure that falls back."""


Searcher = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class SearchFilters(BaseModel):
    datasets: list[str] | None = Field(default=None, max_length=200)
    date_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class SearchPageRequest(SearchRequest):
    """Today's `SearchRequest` (`query`, `limit`), with the results page's fields beside it."""

    query: str = Field(min_length=1, max_length=q.MAX_QUERY_CHARS)
    group: str | None = Field(default=None, max_length=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    page: int = Field(default=1, ge=1)
    page_size: int | None = Field(default=None, ge=1, le=50)


class PassagePart(BaseModel):
    text: str
    match: bool


class Match(BaseModel):
    band: str
    why: str
    field: str | None = None


class SearchResult(BaseModel):
    node_ids: list[str]
    type: str
    match: Match
    passage: list[PassagePart] = Field(default_factory=list)
    date: str | None = None
    datasets: list[str] = Field(default_factory=list)
    is_document: bool


class SearchGroup(BaseModel):
    key: str
    label: str
    count: int


class DatasetFilter(BaseModel):
    id: str
    name: str
    #: `None` on the fallback, which cannot count beyond what it returned.
    count: int | None


class DateSpan(BaseModel):
    earliest: str | None
    latest: str | None


class OfferedFilters(BaseModel):
    datasets: list[DatasetFilter]
    dates: DateSpan | None


class SearchPageResponse(SearchResponse):
    """Today's `SearchResponse` (`nodes`, the Node records), with the results page's fields."""

    query: str
    source: Literal["index", "fallback"]
    limited: bool
    limited_reason: str | None
    total: int
    counts_exact: bool
    groups: list[SearchGroup]
    filters: OfferedFilters
    page: int
    page_size: int
    more: bool
    results: list[SearchResult]


def _page_size(request: SearchPageRequest) -> int:
    return request.page_size if request.page_size is not None else request.limit


def _matched_field(node: Node, band: str, query: str) -> str | None:
    """The property an exact identifier or exact name matched, by its name; `None` for the rest,
    which match over several properties or the text."""
    if band == "identifier":
        wanted = {query, search_alternative(query)}
    elif band == "name_exact":
        folded = query.casefold()
        return next(
            (
                k
                for k, v in node.properties.items()
                if isinstance(v, str) and v.casefold() == folded
            ),
            None,
        )
    else:
        return None
    return next((k for k, v in node.properties.items() if v in wanted), None)


def _result(node: Node, band: str, query: str, principal: Principal, **extra: Any) -> SearchResult:
    case = set(principal.datasets or ())
    return SearchResult(
        node_ids=[node.id],
        type=node.type,
        match=Match(
            band=band, why=_WHY[band].format(query=query), field=_matched_field(node, band, query)
        ),
        datasets=[d for d in node.datasets if d in case],
        is_document=node.type == "Document",
        **extra,
    )


def _date(value: str | None) -> str | None:
    return value[:10] if value else None


def _check_datasets(request: SearchPageRequest, principal: Principal) -> None:
    case = set(principal.datasets or ())
    outside = sorted(set(request.filters.datasets or ()) - case)
    if outside:
        raise ValueError(f"not a dataset of this case: {', '.join(outside)}")


async def search_page(
    request: SearchPageRequest,
    principal: Principal,
    graph: GraphPort,
    *,
    searcher: Searcher | None,
    access_filter: dict[str, Any] | None,
    phonetic_codes: q.PhoneticCodes,
    types: Sequence[str],
    case_datasets: Mapping[str, str],
) -> SearchPageResponse:
    """`case_datasets` maps each of the case's datasets to its name. A `ValueError` is the caller's
    mistake (a dataset outside the case, a page too deep) and becomes a 422."""
    _check_datasets(request, principal)
    if searcher is not None and access_filter is not None:
        try:
            return await _from_index(
                request,
                principal,
                graph,
                searcher,
                access_filter,
                phonetic_codes,
                types,
                case_datasets,
            )
        except IndexUnavailable:
            pass
    return await _from_graph(request, principal, graph, case_datasets)


async def _from_index(
    request: SearchPageRequest,
    principal: Principal,
    graph: GraphPort,
    searcher: Searcher,
    access_filter: dict[str, Any],
    phonetic_codes: q.PhoneticCodes,
    types: Sequence[str],
    case_datasets: Mapping[str, str],
) -> SearchPageResponse:
    size = _page_size(request)
    body = q.build_search_body(
        request.query,
        access_filter=access_filter,
        phonetic_codes=phonetic_codes,
        types=types,
        page_size=size,
        page=request.page,
        group=request.group,
        case_datasets=list(case_datasets),
        datasets=request.filters.datasets,
        date_from=request.filters.date_from,
        date_to=request.filters.date_to,
    )
    found = q.read_search_response(await searcher(body), page_size=size)
    ids = [hit.node_id for hit in found.hits]
    visible = {node.id: node for node in await graph.get_nodes(ids, principal)} if ids else {}
    results = [
        _result(
            visible[hit.node_id],
            hit.band,
            request.query,
            principal,
            passage=[PassagePart(text=p.text, match=p.match) for p in hit.snippet]
            if hit.band.startswith("mention")
            else [],
            date=_date(hit.date),
        )
        for hit in found.hits
        if hit.node_id in visible
    ]
    groups = [
        SearchGroup(key=k, label=k, count=c)
        for k, c in sorted(found.counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    if found.mentions:
        groups.append(
            SearchGroup(key=q.MENTIONS, label="Mentioned in documents", count=found.mentions)
        )
    return SearchPageResponse(
        query=request.query,
        source="index",
        limited=False,
        limited_reason=None,
        total=sum(g.count for g in groups),
        counts_exact=found.counts_exact and len(results) == len(found.hits),
        groups=groups,
        filters=OfferedFilters(
            datasets=[
                DatasetFilter(id=d, name=name, count=found.dataset_counts[d])
                for d, name in case_datasets.items()
                if found.dataset_counts.get(d)
            ],
            dates=DateSpan(earliest=_date(found.earliest), latest=_date(found.latest)),
        ),
        page=request.page,
        page_size=size,
        more=found.more,
        results=results,
        nodes=[visible[r.node_ids[0]] for r in results],
    )


async def _from_graph(
    request: SearchPageRequest,
    principal: Principal,
    graph: GraphPort,
    case_datasets: Mapping[str, str],
) -> SearchPageResponse:
    """Today's exact search, paged over what it returns (at most `FALLBACK_DEPTH`)."""
    size = _page_size(request)
    start = (request.page - 1) * size
    want = min(FALLBACK_DEPTH, start + size + 1)
    found = (await search(graph, SearchRequest(query=request.query, limit=want), principal)).nodes
    if request.group is not None:
        found = [n for n in found if n.type == request.group]
    page = found[start : start + size]
    counts: dict[str, int] = {}
    for node in found:
        counts[node.type] = counts.get(node.type, 0) + 1
    return SearchPageResponse(
        query=request.query,
        source="fallback",
        limited=True,
        limited_reason=LIMITED_REASON,
        total=len(found),
        counts_exact=False,
        groups=[
            SearchGroup(key=k, label=k, count=c)
            for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        filters=OfferedFilters(
            datasets=[DatasetFilter(id=d, name=n, count=None) for d, n in case_datasets.items()],
            dates=None,
        ),
        page=request.page,
        page_size=size,
        more=len(found) > start + size,
        results=[_result(node, "identifier", request.query, principal) for node in page],
        nodes=page,
    )
