"""The search service (ADR-149; v0.5.2 step 3d): one search, asked of the index when there is one
and an access filter to ask it with, and of today's graph search otherwise, in the response shape
the results page is built against (`schemas.search`;
`process/lanes/studio/SEARCH_RESPONSE_SHAPE.md`).

- **The graph stays the source of truth** (the owner's requirement b). The index names hits by
  node id, and the nodes are read from the graph through its own access step. A hit the graph does
  not return is never listed, and the counts are then not shown as exact.
- **The fallback says so** (requirement c). With no index, or an index that cannot answer, today's
  exact search answers with `limited` set, and the screen says results are limited. Any other index
  failure is this code's defect and is raised, never hidden behind "limited".
- **What it never sends:** the index's scores, an index name, or a dataset outside the reader's
  case, even one an index count names.

The access filter is an argument here: the route builds it from the reader's own principal
(`search_access.index_access_filter`).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import opensearchpy
from services.api.case_views import _collapsed
from services.search_index.document import searchable_fields

from ontology.handling import HandlingScheme
from ports.graph import GraphPort
from schemas.domain import Node, OntologySchema, Principal
from schemas.search import (
    DatasetFilter,
    DateSpan,
    OfferedFilters,
    PassagePart,
    SearchGroup,
    SearchMatch,
    SearchPageRequest,
    SearchPageResponse,
    SearchResult,
)

from . import search_index_query as q
from .identifier_reading import search_alternative
from .search import SearchRequest, SuggestRequest, SuggestResponse, search, suggest

log = logging.getLogger(__name__)

#: The words the screen shows when the fallback answers, by why it answered.
FallbackWhy = Literal["no_index", "unreachable", "catching_up"]
LIMITED_REASONS: dict[FallbackWhy, str] = {
    "no_index": "Search is limited to exact identifiers: this deployment has no search index.",
    "unreachable": (
        "Search is limited to exact identifiers just now: the search index cannot be reached."
    ),
    "catching_up": (
        "Search is limited to exact identifiers just now: the search index is catching up "
        "with recent changes."
    ),
}
#: How many rows of each outbox are read for the pending nodes. More than this, and the set is not
#: known to be whole, so search falls back (the orchestrator's ruling on page A: pending nodes are
#: left out of every query, and a set not known to be whole cannot be).
PENDING_LIMIT = 10_000
#: Added when the fallback cannot apply the date filter: today's search knows no dates.
DATES_NOT_APPLIED = " The date filter is not applied."
#: Added on the page where the fallback's list stops because more matched than today's search's
#: depth, and on any page past it: the list ends there because of the fallback, not because nothing
#: else matches (rule 2). It sends the reader to nothing the page cannot do: the dataset and group
#: filters apply to the listed matches alone, so they cannot reach one past the cut, and today's
#: search is an exact match, so a different query is no narrowing of it. `{depth}` is
#: `FALLBACK_DEPTH`.
DEPTH_REACHED = " Only the first {depth} matches are listed, and the filters apply to those alone."

#: Today's search returns at most this many, so the fallback lists no deeper, and says when it
#: reached it.
FALLBACK_DEPTH = 100

#: How long a request waits for the index before falling back, in seconds. Short: suggestions are
#: asked at each keystroke, and a silent drop must not hold the box (requirement c).
SEARCH_TIMEOUT = 5.0
SUGGEST_TIMEOUT = 2.0

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
    """The index cannot be reached. Raised by the searcher, and the one failure that falls back
    (the owner's requirement c: "if OpenSearch is unreachable")."""


Searcher = Callable[[dict[str, Any], float], Awaitable[dict[str, Any]]]


class _SearchClient(Protocol):
    async def search(self, *, index: str, body: dict[str, Any], request_timeout: float) -> Any: ...


def opensearch_searcher(client: _SearchClient, alias: str) -> Searcher:
    """A `Searcher` over the shared client (rules' `search_client`), asking the deployment's alias
    and never a concrete index, with a short timeout per request.

    Only an index that cannot be reached falls back (the owner's requirement c): a refused or
    timed-out connection becomes `IndexUnavailable`. Everything else is raised and logged, never
    hidden behind "limited": a TLS failure, an alias that does not exist, a refusal of our
    identity (401, 403), an overload (429), a query it refuses (400), a server error."""

    async def ask(body: dict[str, Any], timeout: float) -> dict[str, Any]:
        try:
            reply = await client.search(index=alias, body=body, request_timeout=timeout)
        except opensearchpy.SSLError:
            log.exception("the search index's TLS failed")
            raise
        except opensearchpy.ConnectionError as exc:  # a refused or timed-out connection
            raise IndexUnavailable("the search index cannot be reached") from exc
        except opensearchpy.TransportError as exc:
            log.error("the search index answered %s", exc.status_code)
            raise
        return dict(reply)

    return ask


@dataclass(frozen=True)
class SearchIndexSetup:
    """What the routes need to ask the index: the searcher, every entity type the ontology has
    (for the by-type counts and to refuse an unknown one) and the handling scheme (for the reader's
    access filter)."""

    searcher: Searcher
    schema: OntologySchema
    scheme: HandlingScheme

    @property
    def types(self) -> list[str]:
        return [t.name for t in self.schema.entity_types]


def _page_size(request: SearchPageRequest) -> int:
    return request.page_size if request.page_size is not None else request.limit


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _searchable(node: Node, schema: OntologySchema | None) -> list[str] | None:
    """The properties the index searches for this node's type: its identifiers and names
    (ADR-150's `searchable_fields`), never another or a sensitive one. `None` with no schema."""
    if schema is None:
        return None
    identifiers, names, _ = searchable_fields(schema, node.type)
    return [*identifiers, *names]


def display_name(key: str) -> str:
    """A property's name as the screen says it: `family_name` is "Family name"."""
    return key.replace("_", " ").strip().capitalize()


def group_label(type_name: str) -> str:
    """A group's heading (the frozen shape: "People", "Documents")."""
    if type_name == "Person":
        return "People"
    if type_name.endswith("y") and type_name[-2:-1] not in "aeiou":
        return type_name[:-1] + "ies"
    if type_name.endswith(("s", "x", "ch", "sh")):
        return type_name + "es"
    return type_name + "s"


def _matched_field(
    node: Node,
    band: str,
    query: str,
    phonetic_codes: q.PhoneticCodes,
    schema: OntologySchema | None = None,
) -> str | None:
    """The property the hit matched, by its display name: the first searchable one whose value (or
    one of whose values) meets the band's rule. `None` for a mention, for a typo (graded over
    trigrams of every name), and where no one property does."""
    words = query.casefold().split()
    canonical = search_alternative(query)

    def meets(value: str) -> bool:
        if band == "identifier":
            return value in (query, canonical)
        if band == "name_exact":
            return value.casefold() == query.casefold()
        if band == "name_words":
            held = value.casefold().split()
            return all(w in held for w in words)
        if band == "name_sounds":
            return bool(set(phonetic_codes(value)) & set(phonetic_codes(query)))
        return False

    allowed = _searchable(node, schema)
    for key, value in node.properties.items():
        if allowed is not None and key not in allowed:
            continue
        if any(meets(v) for v in _strings(value)):
            return display_name(key)
    return None


def _result(
    node: Node,
    band: str,
    query: str,
    principal: Principal,
    phonetic_codes: q.PhoneticCodes,
    schema: OntologySchema | None,
    **extra: Any,
) -> SearchResult:
    case = set(principal.datasets or ())
    return SearchResult(
        node_ids=[node.id],
        type=node.type,
        match=SearchMatch(
            band=band,  # type: ignore[arg-type]  # one of the bands, by `q._band`
            why=_WHY[band].format(query=query),
            field=_matched_field(node, band, query, phonetic_codes, schema),
        ),
        datasets=[d for d in node.datasets if d in case],
        is_document=node.type == "Document",
        **extra,
    )


def _date(value: str | None) -> str | None:
    """The day of `value` in UTC (a date with an offset is moved to UTC first)."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value[:10]
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return moment.date().isoformat()


def _check(request: SearchPageRequest, principal: Principal) -> None:
    """A caller's mistake, refused before either path is asked (422)."""
    case = set(principal.datasets or ())
    outside = sorted(set(request.filters.datasets or ()) - case)
    if outside:
        raise ValueError(f"not a dataset of this case: {', '.join(outside)}")
    if request.page * _page_size(request) > q.MAX_DEPTH:
        raise ValueError(
            f"results are listed {q.MAX_DEPTH} deep at most; narrow the search to see further"
        )
    dates = request.filters
    if dates.date_from and dates.date_to and dates.date_from > dates.date_to:
        raise ValueError("the date filter ends before it starts")


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
    tau: float | None = None,
    pending: Sequence[str] = (),
    pending_complete: bool = True,
    schema: OntologySchema | None = None,
) -> SearchPageResponse:
    """`case_datasets` maps each of the case's datasets to its name, `tau` is the case's resolution
    threshold (`None`: nothing is merged), and `pending` the nodes the index has not yet caught up
    with (`pending_complete` false: the set is not known to be whole, and the graph answers). A
    `ValueError` is the caller's mistake (a dataset outside the case, a page too deep) and becomes
    a 422."""
    _check(request, principal)
    why: FallbackWhy = "no_index"
    if searcher is not None and access_filter is not None and not pending_complete:
        why = "catching_up"
    elif searcher is not None and access_filter is not None:
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
                tau,
                pending,
                schema,
            )
        except IndexUnavailable:
            why = "unreachable"
    return await _from_graph(
        request, principal, graph, case_datasets, tau, phonetic_codes, schema, why
    )


async def _merged(
    graph: GraphPort,
    results: list[SearchResult],
    nodes: Mapping[str, Node],
    principal: Principal,
    tau: float | None,
) -> list[SearchResult]:
    """Page A §2, as ruled: the visible hits on this page that the case reads as one entity at
    `tau` become one result, in the place of its best member. The clustering is case views' own
    (`case_views._collapsed`): links only among the nodes shown, through the adapter's filter, so a
    member the reader may not see joins nothing and adds nothing."""
    if tau is None or len(results) < 2:
        return results
    shown = await _collapsed(graph, [nodes[r.node_ids[0]] for r in results], principal, tau)
    cluster = {n.id: n.resolution.cluster_id or n.id for n in shown}
    first: dict[str, SearchResult] = {}
    for result in results:
        key = cluster[result.node_ids[0]]
        lead = first.get(key)
        if lead is None:
            first[key] = result.model_copy(deep=True)
            continue
        lead.node_ids.append(result.node_ids[0])
        lead.datasets = sorted(set(lead.datasets) | set(result.datasets))
    return list(first.values())


async def _from_index(
    request: SearchPageRequest,
    principal: Principal,
    graph: GraphPort,
    searcher: Searcher,
    access_filter: dict[str, Any],
    phonetic_codes: q.PhoneticCodes,
    types: Sequence[str],
    case_datasets: Mapping[str, str],
    tau: float | None,
    pending: Sequence[str],
    schema: OntologySchema | None,
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
        pending=pending,
    )
    found = q.read_search_response(await searcher(body, SEARCH_TIMEOUT), page_size=size)
    ids = [hit.node_id for hit in found.hits]
    visible = {node.id: node for node in await graph.get_nodes(ids, principal)} if ids else {}
    results = [
        _result(
            visible[hit.node_id],
            hit.band,
            request.query,
            principal,
            phonetic_codes,
            schema,
            passage=[PassagePart(text=p.text, match=p.match) for p in hit.snippet]
            if hit.band.startswith("mention")
            else [],
            date=_date(hit.date),
        )
        for hit in found.hits
        if hit.node_id in visible
    ]
    shown = len(results)
    results = await _merged(graph, results, visible, principal, tau)
    groups = [
        SearchGroup(key=k, label=group_label(k), count=c)
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
        # Not exact when the graph withheld a hit, or when nodes the index has not caught up with
        # were left out (they may belong in a count).
        counts_exact=found.counts_exact and shown == len(found.hits) and not pending,
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
        nodes=[visible[i] for r in results for i in r.node_ids],
    )


async def _from_graph(
    request: SearchPageRequest,
    principal: Principal,
    graph: GraphPort,
    case_datasets: Mapping[str, str],
    tau: float | None,
    phonetic_codes: q.PhoneticCodes,
    schema: OntologySchema | None,
    why: FallbackWhy,
) -> SearchPageResponse:
    """Today's exact search, at most `FALLBACK_DEPTH`, then narrowed by the dataset filter and the
    group, and paged. It cannot apply a date filter (today's search knows no dates) and says so;
    its counts are never shown as exact. `more` is true only when a further page holds records;
    where its depth stops the list, the line says so (`DEPTH_REACHED`)."""
    size = _page_size(request)
    start = (request.page - 1) * size
    one_past = SearchRequest.model_construct(query=request.query, limit=FALLBACK_DEPTH + 1)
    found = (await search(graph, one_past, principal)).nodes
    # Asked one past the depth, so a cut is known: exactly `FALLBACK_DEPTH` matches is a whole list.
    # `model_construct`: the request's own bound (100) is the box's, not this internal read's.
    reached = len(found) > FALLBACK_DEPTH
    found = found[:FALLBACK_DEPTH]
    wanted = set(request.filters.datasets or ())
    if wanted:
        found = [n for n in found if wanted.intersection(n.datasets)]
    counts: dict[str, int] = {}
    for node in found:
        counts[node.type] = counts.get(node.type, 0) + 1
    if request.group is not None:
        found = [n for n in found if n.type == request.group]
    page = found[start : start + size]
    more = len(found) > start + size
    reason = LIMITED_REASONS[why]
    if request.filters.date_from or request.filters.date_to:
        reason += DATES_NOT_APPLIED
    if reached and not more:
        reason += DEPTH_REACHED.format(depth=FALLBACK_DEPTH)
    return SearchPageResponse(
        query=request.query,
        source="fallback",
        limited=True,
        limited_reason=reason,
        total=sum(counts.values()),
        counts_exact=False,
        groups=[
            SearchGroup(key=k, label=group_label(k), count=c)
            for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        filters=OfferedFilters(
            datasets=[DatasetFilter(id=d, name=n, count=None) for d, n in case_datasets.items()],
            dates=None,
        ),
        page=request.page,
        page_size=size,
        more=more,
        results=await _merged(
            graph,
            [
                _result(n, "identifier", request.query, principal, phonetic_codes, schema)
                for n in page
            ],
            {n.id: n for n in page},
            principal,
            tau,
        ),
        nodes=page,
    )


#: A case-sensitive suggestion asks the index this many times its page, at most `_WIDEST`, so the
#: page still fills once the matches in another case are left out; and pages on, at most `_PAGES`
#: times, until its page is full or the matches run out. Past that, the graph's prefix read answers.
_WIDER = 4
_WIDEST = 100
_PAGES = 5


async def suggest_page(
    request: SuggestRequest,
    principal: Principal,
    graph: GraphPort,
    *,
    searcher: Searcher | None,
    access_filter: dict[str, Any] | None,
    schema: OntologySchema | None = None,
    pending: Sequence[str] = (),
    pending_complete: bool = True,
) -> SuggestResponse:
    """Suggestions as the analyst types (ADR-059 Amendment 1): the index answers a "starts with"
    suggestion when there is one and an access filter to ask it with; "contains" and "exact", no
    index, or an index that cannot answer go to the graph's prefix read, as before. A "starts with"
    suggestion the graph answered says it is `limited`, so the box can say so (requirement c).

    The index's stored prefixes ignore case. A case-sensitive request (the box's default) keeps
    only the nodes holding a value that starts with the prefix as typed, read from the graph, and
    says `more` whenever the index had more than it was asked (rule 2). A `ValueError` (a prefix
    too long, an entity type the ontology does not have) is the caller's mistake: a 422."""
    if request.types and schema is not None:
        unknown = sorted(set(request.types) - {t.name for t in schema.entity_types})
        if unknown:
            raise ValueError(f"not an entity type: {', '.join(unknown)}")
    why: FallbackWhy = "no_index"
    if searcher is not None and access_filter is not None and not pending_complete:
        why = "catching_up"
    elif searcher is not None and access_filter is not None and request.mode == "starts_with":
        try:
            answered_by_index = await _suggest_from_index(
                request, principal, graph, searcher, access_filter, pending, schema
            )
        except IndexUnavailable:
            why = "unreachable"
        else:
            if answered_by_index is not None:
                return answered_by_index
            # The index could not fill a case-sensitive page within its bound: the graph's own
            # prefix read answers, exactly, and nothing is limited about it.
            exact = await suggest(graph, request, principal)
            return exact.model_copy(update={"source": "graph", "limited": False})
    answered = await suggest(graph, request, principal)
    limited = request.mode == "starts_with"
    return answered.model_copy(
        update={"source": "graph", "limited": limited, "limited_why": why if limited else None}
    )


def _starts_with(node: Node, prefix: str, schema: OntologySchema | None) -> bool:
    """Whether one of the values the index matched (the type's identifiers and names, never
    another or a sensitive property) starts with `prefix` as typed."""
    allowed = _searchable(node, schema)
    return any(
        v.startswith(prefix)
        for key, value in node.properties.items()
        if allowed is None or key in allowed
        for v in _strings(value)
    )


async def _suggest_from_index(
    request: SuggestRequest,
    principal: Principal,
    graph: GraphPort,
    searcher: Searcher,
    access_filter: dict[str, Any],
    pending: Sequence[str],
    schema: OntologySchema | None,
) -> SuggestResponse | None:
    """The index's suggestions, or `None` where a case-sensitive page cannot be filled within
    `_PAGES` pages while the index still holds more: then the caller asks the graph, which answers
    case-sensitively and exactly, so the box never shows an empty list with "more match"."""
    asked = request.limit if request.ignore_case else min(_WIDEST, request.limit * _WIDER)
    pages = 1 if request.ignore_case else _PAGES
    prefixes = [request.query]
    alternative = search_alternative(request.query)
    if alternative is not None and alternative != request.query:
        prefixes.append(alternative)  # ADR-128 decision 1, as today's suggestion
    seen: set[str] = set()
    kept: list[Node] = []
    unfinished = False  # some prefix still had matches when its scan stopped
    for prefix in prefixes:
        start = 0
        had_more = False
        for _ in range(pages):
            body = q.build_suggest_body(
                prefix,
                access_filter=access_filter,
                limit=asked,
                types=request.types,
                pending=pending,
                start=start,
            )
            found, had_more = q.read_suggest_response(
                await searcher(body, SUGGEST_TIMEOUT), limit=asked
            )
            fresh = [i for i in found if i not in seen]
            seen.update(fresh)
            read = {n.id: n for n in await graph.get_nodes(fresh, principal)} if fresh else {}
            nodes = [read[i] for i in fresh if i in read]
            if not request.ignore_case:
                nodes = [n for n in nodes if any(_starts_with(n, p, schema) for p in prefixes)]
            kept += nodes
            start += asked
            if not had_more or len(kept) > request.limit:
                break
        unfinished = unfinished or had_more
        if len(kept) > request.limit:
            break
    if len(kept) <= request.limit and unfinished and not request.ignore_case:
        return None
    return SuggestResponse(
        nodes=kept[: request.limit],
        more=len(kept) > request.limit or (unfinished and request.ignore_case),
        source="index",
        limited=False,
    )
