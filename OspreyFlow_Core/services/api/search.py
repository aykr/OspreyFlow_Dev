"""`POST /v1/search` — `spec/02_GLASS_FRONTEND.md`'s workspace layout search
box, `spec/03_CONDUIT_MIDDLEWARE.md` §3.3.

**v1, graph-only.** §3.3 specifies `POST /v1/search` as "federated search
across graph, documents, index" — the index leg is OpenSearch, which is not
wired into any deployment profile until later (`05_DEPLOYMENT.md`; document
content itself does not exist as a searchable thing until extraction,
Phase 6). This route is the graph leg only: `GraphPort.search_nodes`, an
exact match against every entity type's declared identifiers, access-filtered
the same way any other read is. It is deliberately scoped so that document
and index federation, when OpenSearch lands, extends this same route rather
than replacing it with a second one.

Not investigation-scoped — a search result is a candidate to seed into a
working set (`POST /seed`), not itself part of one, so there is no
`owning_unit` check here; visibility is governed entirely by
`GraphPort.search_nodes`'s own handling filter, the same as every other
un-investigation-scoped read in this service.
"""

from __future__ import annotations

from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ports.graph import GraphPort, NodeSuggestions, SuggestOptions
from schemas.domain import Node, Principal

from .identifier_reading import search_alternative

#: A prefix shorter than this is not worth a scan of every suggestable type (ADR-059). Two, by the
#: owner's ruling of 3 October 2026 (ADR-074); it had been three.
SUGGEST_MIN_CHARS = 2


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=20, ge=1, le=100)


class SearchResponse(BaseModel):
    nodes: list[Node]


def _merged(first: list[Node], second: list[Node]) -> list[Node]:
    """`first`, then what `second` adds, each node once."""
    seen = {n.id for n in first}
    return [*first, *(n for n in second if n.id not in seen)]


async def search(graph: GraphPort, request: SearchRequest, principal: Principal) -> SearchResponse:
    """The typed text is asked as it always was. ADR-128 decision 1 (B2): a phone number or account
    reference written another way is asked in its canonical form too, so `07700 900640` finds
    `+447700900640`; the typed text first, and nothing else changes for any other text."""
    nodes = await graph.search_nodes(request.query, principal, limit=request.limit)
    alternative = search_alternative(request.query)
    if alternative is not None:
        more = await graph.search_nodes(alternative, principal, limit=request.limit)
        nodes = _merged(nodes, more)[: request.limit]
    return SearchResponse(nodes=nodes)


class SuggestRequest(BaseModel):
    """`mode`, `ignore_case` and `types` are ADR-061's search options; the defaults are exactly
    ADR-059's plain case-sensitive prefix match on every type."""

    query: str = Field(min_length=SUGGEST_MIN_CHARS)
    limit: int = Field(default=10, ge=1, le=25)
    mode: Literal["starts_with", "contains", "exact"] = "starts_with"
    ignore_case: bool = False
    #: Entity type names to look in; `None` is every type. Bounded so a request cannot ask the
    #: store to build an unbounded label list.
    types: list[str] | None = Field(default=None, max_length=50)


class SuggestResponse(BaseModel):
    """`more` is true when another visible node matched beyond `nodes`: the Glass says so and
    never shows a cut-off list as if it were complete (rule 2). It is counted after the access
    filter, so it cannot reveal a hidden node."""

    nodes: list[Node]
    more: bool


async def suggest(
    graph: GraphPort, request: SuggestRequest, principal: Principal
) -> SuggestResponse:
    """`POST /v1/suggest` — the search box as the analyst types (ADR-059). A separate route from
    `search` above, which stays an exact match; same principal, same access filter in the
    adapter, same lack of an `owning_unit` check for the same reason."""
    options = SuggestOptions(
        mode=request.mode,
        ignore_case=request.ignore_case,
        types=tuple(request.types) if request.types is not None else None,
    )
    try:
        found = await graph.suggest_nodes(
            request.query, principal, limit=request.limit, options=options
        )
        alternative = search_alternative(request.query)
        if alternative is not None:
            # ADR-128 decision 1: the canonical form of a number or account reference, as `search`.
            extra = await graph.suggest_nodes(
                alternative, principal, limit=request.limit, options=options
            )
            merged = _merged(found.nodes, extra.nodes)
            found = NodeSuggestions(
                nodes=merged[: request.limit],
                more=found.more or extra.more or len(merged) > request.limit,
            )
    except ValueError as exc:  # an entity type the ontology does not have: the caller's mistake
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SuggestResponse(nodes=found.nodes, more=found.more)
