"""The search service's request and response (ADR-149;
`process/lanes/studio/SEARCH_RESPONSE_SHAPE.md`, frozen at ee7a16d):
`POST /v1/investigations/{id}/search`. TypeScript types are generated from these
(`generate_ts.py`); the results page (the case lane's step 3e′) is built against them."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from .domain import Node

#: Rule 2: a longer query is refused, not cut. It also bounds the one variable band (some words of
#: a mention, a point a word) below the band above it (ADR-149 decision 3).
MAX_QUERY_CHARS = 200


class SearchFilters(BaseModel):
    #: Only the case's own datasets; another is refused (422).
    datasets: list[str] | None = Field(default=None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None


class SearchPageRequest(BaseModel):
    """Today's request (`query`, `limit`), with the results page's fields beside it."""

    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    #: Today's field: the page's size when `page_size` is not given.
    limit: int = Field(default=20, ge=1, le=100)
    #: `None` is All; an entity type's name; or `"mentions"`.
    group: str | None = Field(default=None, max_length=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    page: int = Field(default=1, ge=1)
    page_size: int | None = Field(default=None, ge=1, le=50)


class PassagePart(BaseModel):
    text: str
    match: bool


class SearchMatch(BaseModel):
    band: Literal[
        "identifier",
        "name_exact",
        "name_words",
        "name_sounds",
        "name_typo",
        "mention_phrase",
        "mention_words",
        "mention_some",
    ]
    #: The Conduit's words, ready to show.
    why: str
    #: The property it matched, by its name; `None` for a mention, or where no one property did.
    field: str | None = None


class SearchResult(BaseModel):
    #: Every visible record this result stands for (a merged entity's visible members).
    node_ids: list[str]
    type: str
    match: SearchMatch
    #: A document's text match only; otherwise empty.
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


class SearchPageResponse(BaseModel):
    """Today's response (`nodes`, the Node records), with the results page's fields."""

    nodes: list[Node]
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


ALL_MODELS: list[type[BaseModel]] = [
    SearchFilters,
    SearchPageRequest,
    PassagePart,
    SearchMatch,
    SearchResult,
    SearchGroup,
    DatasetFilter,
    DateSpan,
    OfferedFilters,
    SearchPageResponse,
]
