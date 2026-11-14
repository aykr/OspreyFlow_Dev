"""Studio's leak test extended to Ask's sources (`06_DECISIONS.md` ADR-098 Amendment 9, ADR-149
Amendment 1; the brief's D(iii)): **what *Whole case* reads, counts and cites is the same whether
the records an asker may not see are in the index or not.**

The worlds are `test_search_leak_live.py`'s own: one index holding every record (hidden ones made
to look as much like visible ones as possible, and stale ones the outbox names), and for each
reader a second index holding only what they may see now. Each question is asked through the
routes' own call site, `app.case_search_with` (the asker's access filter built there), into
`QuestionsService._gather_case`, the step every *Whole case* question and *will read* takes. What
it would send the model (the sources' text and the Documents read whole), the read summary and the
records each `[S-n]` stands for must be identical from both indexes.

Every Document is off the canvas here (the reader opens none), so each is read as the passage the
search matched: the passage is in what is compared.

Shown red first (rule 15), at the real call site: the access filter that `case_search_with` builds
replaced by match-all (`test_the_ask_leak_check_finds_the_access_filter_dropped`).

Needs a lease: the leased stack's OpenSearch, its port pinned (`stack_lease.sh remote`).
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api import app as app_module
from services.api import search_access
from services.api import search_service as s
from services.api.questions import NothingToReadError, QuestionsService
from services.api.review import DocumentNotFoundError
from services.search_index.pending import PendingIds

from schemas.domain import Principal

from .test_search_leak_live import (
    CASE_NAMES,
    ONTOLOGY,
    PENDING,
    READERS,
    SCHEME,
    SEARCHES,
    TAU,
    _Unfiltered,
    _worlds,
)

pytestmark = pytest.mark.store

#: Studio's own queries, asked as questions (each within the search's 200 characters).
QUESTIONS = sorted({request.query for request in SEARCHES})


class _NothingOnTheCanvas:
    """The document reader with nothing in the working set: it opens no Document, so every one
    the search finds is read as its passage."""

    async def read(self, investigation_id: str, document_id: str, principal: Principal) -> Any:
        raise DocumentNotFoundError(document_id)


def _service() -> QuestionsService:
    """Only what `_gather_case` reads is real: the reader. Nothing else is reached."""
    return QuestionsService(
        None,  # type: ignore[arg-type]
        _NothingOnTheCanvas(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        ONTOLOGY,
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        default_model="unused",
        analytics=None,  # type: ignore[arg-type]
        datasets=None,  # type: ignore[arg-type]
        investigations=None,
    )


async def _read(client: Any, index: str, principal: Principal) -> list[Any]:
    setup = s.SearchIndexSetup(
        searcher=s.opensearch_searcher(client, index), schema=ONTOLOGY, scheme=SCHEME
    )

    async def pending_of() -> PendingIds:
        return PendingIds(ids=frozenset(PENDING), complete=True)

    async def names_of(asker: Principal) -> dict[str, str]:
        return {d: n for d, n in CASE_NAMES.items() if d in (asker.datasets or ())}

    async def tau_of(investigation_id: str) -> float | None:
        return TAU

    search = app_module.case_search_with(
        _Unfiltered(),  # type: ignore[arg-type]
        setup,
        pending_of=pending_of,
        names_of=names_of,
        tau_of=tau_of,
    )
    service = _service()
    out: list[Any] = []
    for question in QUESTIONS:
        try:
            material = await service._gather_case("case-1", principal, question, None, search)
        except NothingToReadError as refused:
            out.append((question, "nothing", refused.words))
            continue
        out.append(
            (
                question,
                material.sources_text,
                [(d, title, text) for d, title, text, _ in material.documents],
                material.read.model_dump(),
                [list(source.node_ids) for source in material.sources],
            )
        )
    return out


async def _compare(reader: str) -> tuple[list[Any], list[Any]]:
    principal = READERS[reader]
    async with _worlds(principal) as (client, present, absent):
        with_hidden = await _read(client, present, principal)
        without = await _read(client, absent, principal)
    return with_hidden, without


def _differences(present: list[Any], absent: list[Any]) -> list[Any]:
    return [(p, a) for p, a in zip(present, absent, strict=True) if p != a]


@pytest.mark.parametrize("reader", list(READERS))
async def test_whole_case_reads_the_same_with_hidden_records_present_or_absent(reader: str) -> None:
    with_hidden, without = await _compare(reader)
    assert _differences(with_hidden, without) == []
    sourced = sum(len(row[4]) for row in with_hidden if row[1] != "nothing")
    if reader == "empty-case":
        assert sourced == 0
    else:
        assert sourced > 0, "the test must not pass by finding nothing"


async def test_the_ask_leak_check_finds_the_access_filter_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15: with the filter `case_search_with` builds replaced by match-all, the reader cleared
    for R reads hidden records' sources from the full index, and the comparison says so."""
    match_all: dict[str, Any] = {"bool": {}}
    monkeypatch.setattr(search_access, "index_access_filter", lambda scheme, principal: match_all)
    with_hidden, without = await _compare("cleared-for-R")
    assert _differences(with_hidden, without)
