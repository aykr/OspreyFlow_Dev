"""The leak test (the owner's requirement a; page A §4, read and ruled on 13 November 2026; ADR-149
decision 2): **an analyst cannot see, count or infer a record they are not cleared for.**

One world of synthetic records is indexed through the real document builder and bulk writer
(rules' `throwaway_index`). Hidden records are made to look as much like visible ones as possible:
the same names, sound-alikes, words in text, identifiers, and same-as links to visible records.
Some records have changed in the graph since the index last caught up (reverted, withdrawn,
superseded, re-marked), so the index holds them at their older facts while the outbox names them.

For each reader, a second index holds exactly what the Conduit's own rule (`principal_may_view`,
`in_case_datasets`, a text's unit) lets that reader see in the graph as it is now, less the nodes
the index has not caught up with. **Every search and suggestion the reader makes, through the
service itself (`search_page`, `suggest_page`), must answer identically from both:** results, their
order,
merged entities, passages, every group count and total, the filters offered, and `more`.

The graph here does **not** apply access: it returns any node or link asked for, as it stands now
(a reverted or withdrawn node is gone, a re-marked one is at its new marking), so a hit the index
leaks reaches the response as a difference rather than being dropped by the graph's own filter.

Shown red first (rule 15), each at the real comparison with one protection removed:
- each part of the access filter replaced by match-all
  (`test_the_leak_check_finds_each_filter_part_dropped`);
- the outbox's pending nodes not left out (`test_the_leak_check_finds_the_pending_nodes_counted`);
- word rarity: `similarity: boolean` off in the mapping, and the bands' refusal of a score no band
  gives turned off (`test_the_leak_check_finds_word_rarity_when_scoring_is_not_strict`);
- expansion: the typo band asked as a fuzzy query (`test_the_leak_check_finds_fuzzy_expansion`).

Needs a lease: the leased stack's OpenSearch, its port pinned (`stack_lease.sh remote`).
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest
from opensearchpy import AsyncOpenSearch
from services.api import search_index_query as q
from services.api import search_service as s
from services.api.search import SuggestRequest
from services.api.search_access import index_access_filter
from services.search_index import testing as index_testing
from services.search_index.document import phonetic_codes
from services.search_index.testing import throwaway_index

from ontology.handling import in_case_datasets, load_uk_le_scheme, principal_may_view
from ontology.loader import load_default_ontology
from schemas.domain import (
    SAME_AS,
    AuditStub,
    Edge,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.search import SearchFilters, SearchPageRequest, SearchPageResponse

pytestmark = pytest.mark.store

SCHEME = load_uk_le_scheme()
ONTOLOGY = load_default_ontology()
TYPES = [t.name for t in ONTOLOGY.entity_types]
WHEN = datetime(2026, 1, 1, tzinfo=UTC)
TAU = 0.95
CASE_NAMES = {"ds-1": "Fixture Corp", "ds-2": "Harbour Street"}


def _node(
    node_id: str,
    type_: str,
    *,
    cls: str = "OFFICIAL",
    code: str = "P",
    owner: str = "unit-1",
    origin: str = "unit-1",
    datasets: Sequence[str] = ("ds-1",),
    **props: Any,
) -> Node:
    return Node(
        id=node_id,
        type=type_,
        properties=props,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[
                SourceRef(document_id="files/synthetic.csv", locator="row 1", excerpt_hash="f" * 64)
            ],
            first_seen=WHEN,
        ),
        handling=Handling(
            classification=cls, handling_code=code, originator=origin, owning_unit=owner
        ),
        audit=AuditStub(created_at=WHEN, created_by="loader-1"),
        datasets=list(datasets),
    )


def _near(word: str) -> list[str]:
    """Every word one letter different from `word`."""
    return sorted(
        {
            word[:pos] + letter + word[pos + 1 :]
            for pos in range(len(word))
            for letter in "abcdefghijklmnopqrstuvwxyz"
        }
        - {word}
    )


# --- the world ------------------------------------------------------------------------------------

VISIBLE_LOOKING = [
    _node("p-smythe", "Person", family_name="Smythe", given_names="John", nino="AB123456C"),
    _node("p-mohammed", "Person", family_name="Mohammed", given_names="Ali"),
    _node("p-pemberton", "Person", family_name="Pemberton"),
    _node("o-kestrel", "Organisation", name="Kestrel Holdings", org_ref="ORG-1"),
    _node("d-memo", "Document", title="Harbour memo", sent_at="2026-01-05T09:00:00Z"),
    _node("d-report", "Document", title="Quarterly report", sent_at="2026-02-10T09:00:00Z"),
    _node("d-note", "Document", title="Kestrel note", sent_at="2026-03-01T09:00:00Z"),
    # Merged entities: A and B are each the same as H, whom no OFFICIAL reader may see.
    _node("p-ashdown-a", "Person", family_name="Ashdown"),
    _node("p-ashdown-b", "Person", family_name="Ashdown"),
    # PUBLIC, for the reader cleared to PUBLIC alone, in unit-2, reading both datasets.
    _node("p-smythe-public", "Person", cls="PUBLIC", family_name="Smythe", given_names="Jon"),
    _node(
        "o-kestrel-public", "Organisation", cls="PUBLIC", datasets=["ds-2"], name="Kestrel Shipping"
    ),
    _node(
        "p-smyth-r-unit2",
        "Person",
        cls="PUBLIC",
        code="R",
        owner="unit-2",
        origin="unit-2",
        family_name="Smyth",
    ),
    _node(
        "d-public", "Document", cls="PUBLIC", title="Public notice", sent_at="2026-01-20T09:00:00Z"
    ),
    # Visible to a reader who may receive R, in the owning unit: hidden from one who may not.
    _node("p-smith-r", "Person", code="R", family_name="Smith", given_names="John"),
]
HIDDEN_LOOKING = [
    # Above an OFFICIAL clearance: the same name, identifier and a same-as link to a visible one.
    _node(
        "p-smyth-secret",
        "Person",
        cls="SECRET",
        family_name="Smyth",
        given_names="John",
        nino="AB123456C",
    ),
    _node("p-muhammad-secret", "Person", cls="SECRET", family_name="Muhammad"),
    _node("p-ashdown-h", "Person", cls="SECRET", family_name="Ashdown"),
    # Restricted, owned and originated by another unit.
    _node(
        "p-smythe-r-other",
        "Person",
        code="R",
        owner="unit-2",
        origin="unit-2",
        family_name="Smythe",
    ),
    # Another dataset.
    _node(
        "o-kestrel-ds2",
        "Organisation",
        datasets=["ds-2"],
        name="Kestrel Holdings Ltd",
        org_ref="ORG-1",
    ),
    # A code the scheme does not define.
    _node("p-smythe-undefined", "Person", code="UNDEFINED", family_name="Smythe"),
    # Many hidden documents whose text makes "kestrel" and "briefing" common (word rarity).
    *[
        _node(
            f"d-secret-{i}",
            "Document",
            cls="SECRET",
            title=f"Secret file {i}",
            sent_at="2025-06-01T09:00:00Z",
        )
        for i in range(40)
    ],
    # Many hidden near-names, one letter from what is typed (expansion).
    *[
        _node(f"p-near-smyth-{i}", "Person", cls="SECRET", family_name=name)
        for i, name in enumerate(_near("smyth"))
    ],
    *[
        _node(f"p-near-pemb-{i}", "Person", cls="SECRET", family_name=name)
        for i, name in enumerate(n for n in _near("pembertom") if n != "pemberton")
    ],
]

# Changed in the graph since the index caught up: the index holds STALE, the graph holds NOW, and
# the outbox names every one of them (and the superseding revision, not yet indexed at all).
STALE = [
    _node("p-reverted", "Person", family_name="Smythe", given_names="Reverted"),
    _node("p-withdrawn", "Person", family_name="Smyth", given_names="Withdrawn"),
    _node("o-superseded", "Organisation", name="Kestrel Holdings", org_ref="ORG-1"),
    _node("p-remarked", "Person", family_name="Smythe", given_names="Remarked"),
]
NOW = {
    # Reverted and withdrawn: gone from every read. Superseded: its successor reads instead.
    "o-superseded-v2": _node("o-superseded-v2", "Organisation", name="Kestrel Holdings Group"),
    # Re-marked above OFFICIAL.
    "p-remarked": _node("p-remarked", "Person", cls="SECRET", family_name="Smythe"),
}
PENDING = sorted({n.id for n in STALE} | set(NOW))

INDEXED = {n.id: n for n in VISIBLE_LOOKING + HIDDEN_LOOKING + STALE}
GRAPH = {**{n.id: n for n in VISIBLE_LOOKING + HIDDEN_LOOKING}, **NOW}
TEXTS = {
    "d-memo": ("Kestrel paid the invoice at Harbour Street", "unit-1"),
    "d-report": ("the invoice and the invoice and the invoice", "unit-1"),
    # The Document is visible; its text is held by another unit.
    "d-note": ("Kestrel invoice for the harbour", "unit-2"),
    "d-public": ("Kestrel invoice notice for the harbour", "unit-2"),
    **{f"d-secret-{i}": ("kestrel kestrel briefing", "unit-1") for i in range(40)},
}


def _same_as(link_id: str, a: str, b: str) -> Edge:
    base = VISIBLE_LOOKING[0]
    return Edge(
        id=link_id,
        type=SAME_AS,
        source=a,
        target=b,
        properties={"score": 0.99},
        provenance=base.provenance,
        handling=base.handling,
        audit=base.audit,
    )


LINKS = [
    _same_as("same-as-1", "p-smythe", "p-smyth-secret"),
    _same_as("same-as-2", "p-ashdown-a", "p-ashdown-h"),
    _same_as("same-as-3", "p-ashdown-h", "p-ashdown-b"),
]

READERS = {
    "cleared-for-R": Principal(
        id="a",
        clearance="OFFICIAL",
        org_unit="unit-1",
        receivable_handling_codes=["R"],
        datasets=["ds-1"],
    ),
    "not-for-R": Principal(id="b", clearance="OFFICIAL", org_unit="unit-1", datasets=["ds-1"]),
    "public-other-unit": Principal(
        id="c",
        clearance="PUBLIC",
        org_unit="unit-2",
        receivable_handling_codes=["R"],
        datasets=["ds-1", "ds-2"],
    ),
    "empty-case": Principal(
        id="d", clearance="SECRET", org_unit="unit-1", receivable_handling_codes=["R"], datasets=[]
    ),
}

SEARCHES = [
    SearchPageRequest(query=text, page_size=50)
    for text in [
        "Smythe",
        "Smyth",
        "Smithe",
        "John Smythe",
        "AB123456C",
        "Kestrel Holdings",
        "Kestrel",
        "Kestrel invoice",
        "kestrel briefing invoice",
        "invoice",
        "Mohammed",
        "Muhammad",
        "Ashdown",
        "Pembertom",
        "harbour",
    ]
] + [
    SearchPageRequest(query="Smyth", group="Person", page_size=50),
    SearchPageRequest(query="Kestrel", group="mentions", page_size=50),
    SearchPageRequest(query="Kestrel", filters=SearchFilters(datasets=["ds-1"]), page_size=50),
    SearchPageRequest(
        query="invoice",
        filters=SearchFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31)),
        page_size=50,
    ),
    SearchPageRequest(query="Smyth", page=1, page_size=1),
]
SUGGESTIONS = [
    SuggestRequest(query=text, ignore_case=ignore)
    for text in ["Sm", "Smy", "Smyth", "Kes", "Mo", "Mu", "AB12", "Ha", "Ash", "Pem"]
    for ignore in (True, False)
] + [SuggestRequest(query="Smy", types=["Person"], ignore_case=True)]


def _may_see(node: Node, principal: Principal) -> bool:
    if node.handling.handling_code not in SCHEME.handling_codes:
        return False
    return principal_may_view(node.handling, principal, SCHEME) and in_case_datasets(
        node.datasets, principal
    )


def _seen(principal: Principal) -> tuple[list[Node], dict[str, tuple[str, str]]]:
    """What `principal` may see in the graph as it is now, less the nodes the index has not
    caught up with (left out of every query): the absent world for them."""
    nodes = [n for n in GRAPH.values() if n.id not in PENDING and _may_see(n, principal)]
    shown = {n.id for n in nodes}
    texts = {k: v for k, v in TEXTS.items() if k in shown and v[1] == principal.org_unit}
    return nodes, texts


class _Unfiltered:
    """The graph as it is now, with no access applied: every node and link asked for."""

    async def get_nodes(self, node_ids: Sequence[str], principal: Principal) -> list[Node]:
        return [GRAPH[i] for i in node_ids if i in GRAPH]

    async def edges_among(
        self, node_ids: Sequence[str], principal: Principal, *, edge_types: Sequence[str]
    ) -> list[Edge]:
        ids = set(node_ids)
        return [e for e in LINKS if e.type in edge_types and e.source in ids and e.target in ids]

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        raise AssertionError("the fallback must not answer in the leak test")

    async def suggest_nodes(self, prefix: str, principal: Principal, **kwargs: Any) -> Any:
        raise AssertionError("the fallback must not answer in the leak test")


async def _answers(
    client: AsyncOpenSearch, index: str, principal: Principal, access: dict[str, Any]
) -> list[Any]:
    searcher = s.opensearch_searcher(client, index)
    graph: Any = _Unfiltered()
    case = {d: n for d, n in CASE_NAMES.items() if d in (principal.datasets or ())}
    out: list[Any] = []
    for request in SEARCHES:
        try:
            response = await s.search_page(
                request,
                principal,
                graph,
                searcher=searcher,
                access_filter=access,
                phonetic_codes=phonetic_codes,
                types=TYPES,
                case_datasets=case,
                tau=TAU,
                pending=PENDING,
                schema=ONTOLOGY,
            )
        except ValueError as refused:  # a filter on a dataset outside the case: a 422
            out.append((request.model_dump(), "refused", str(refused)))
            continue
        assert response.source == "index", "the leak test must be answered by the index"
        out.append((request.model_dump(), response.model_dump()))
    for suggestion in SUGGESTIONS:
        answered = await s.suggest_page(
            suggestion,
            principal,
            graph,
            searcher=searcher,
            access_filter=access,
            schema=ONTOLOGY,
            pending=PENDING,
        )
        assert answered.source == "index"
        out.append((suggestion.model_dump(), answered.model_dump()))
    return out


@asynccontextmanager
async def _worlds(principal: Principal) -> AsyncIterator[tuple[AsyncOpenSearch, str, str]]:
    nodes, texts = _seen(principal)
    async with throwaway_index(list(INDEXED.values()), TEXTS, schema=ONTOLOGY) as (
        client,
        present,
    ):
        async with throwaway_index(nodes, texts, schema=ONTOLOGY, client=client) as (_, absent):
            yield client, present, absent


def _differences(present: list[Any], absent: list[Any]) -> list[Any]:
    return [(p[0], p[1:], a[1:]) for p, a in zip(present, absent, strict=True) if p != a]


async def _compare(reader: str, access: dict[str, Any] | None = None) -> list[Any]:
    principal = READERS[reader]
    access = access or index_access_filter(SCHEME, principal)
    async with _worlds(principal) as (client, present, absent):
        with_hidden = await _answers(client, present, principal, access)
        without = await _answers(client, absent, principal, access)
    return _differences(with_hidden, without)


# --- the test -------------------------------------------------------------------------------------


@pytest.mark.parametrize("reader", list(READERS))
async def test_a_reader_gets_the_same_answers_with_hidden_records_present_or_absent(
    reader: str,
) -> None:
    principal = READERS[reader]
    access = index_access_filter(SCHEME, principal)
    async with _worlds(principal) as (client, present, absent):
        with_hidden = await _answers(client, present, principal, access)
        without = await _answers(client, absent, principal, access)
    assert _differences(with_hidden, without) == []
    found = sum(
        len(r[1]["results"]) for r in with_hidden if isinstance(r[1], dict) and "results" in r[1]
    )
    if reader == "empty-case":
        assert found == 0
    else:
        assert found > 0, "the test must not pass by finding nothing"


async def test_the_world_is_not_vacuous() -> None:
    """The hidden and stale records are really in the present index and really match the
    queries: an unlimited filter finds them."""
    reader = READERS["cleared-for-R"]
    async with _worlds(reader) as (client, present, absent):
        searcher = s.opensearch_searcher(client, present)
        body = q.build_search_body(
            "Smythe",
            access_filter={"bool": {}},
            phonetic_codes=phonetic_codes,
            types=TYPES,
            page_size=50,
        )
        ids = {h["_source"]["node_id"] for h in (await searcher(body, 5.0))["hits"]["hits"]}
    assert {"p-smyth-secret", "p-smythe-r-other", "p-smythe-undefined"} <= ids
    assert {"p-reverted", "p-remarked"} <= ids


@pytest.mark.parametrize("part", ["classification", "handling_code", "datasets", "text_unit"])
async def test_the_leak_check_finds_each_filter_part_dropped(part: str) -> None:
    """Rule 15: the comparison above, shown red with each part of the real filter replaced by
    match-all, for the reader each part hides something from."""
    reader = "not-for-R" if part == "handling_code" else "cleared-for-R"
    access = copy.deepcopy(index_access_filter(SCHEME, READERS[reader]))
    access["bool"]["filter"] = [
        {"bool": {"_name": f"{part} dropped"}} if c["bool"]["_name"] == part else c
        for c in access["bool"]["filter"]
    ]
    assert await _compare(reader, access)


@pytest.fixture
def no_exclusion(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(q, "_left_out", lambda pending: {})
    yield


async def test_the_leak_check_finds_the_pending_nodes_counted(no_exclusion: None) -> None:
    """The orchestrator's ruling on page A, shown red: without the exclusion, a reverted,
    withdrawn, superseded or re-marked node the index still holds at its older facts is counted."""
    assert await _compare("cleared-for-R")


@pytest.fixture
def not_strict(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """OpenSearch's default scoring: `similarity: boolean` removed from the mapping the throwaway
    indexes are made with, and the bands' refusal of a score no band gives turned off, so word
    rarity reaches the order instead of being refused."""
    original = index_testing.index_body  # type: ignore[attr-defined]

    def default_relevance(body: Any) -> Any:
        if isinstance(body, dict):
            return {k: default_relevance(v) for k, v in body.items() if k != "similarity"}
        if isinstance(body, list):
            return [default_relevance(v) for v in body]
        return body

    monkeypatch.setattr(index_testing, "index_body", lambda: default_relevance(original()))
    real_band = q._band

    def lenient(score: float) -> str:
        try:
            return real_band(score)
        except q.ScoreOutsideBands:
            return "mention_some"

    monkeypatch.setattr(q, "_band", lenient)
    yield


async def test_the_leak_check_finds_word_rarity_when_scoring_is_not_strict(
    not_strict: None,
) -> None:
    """Page A's first worked example, at the real comparison: 40 hidden documents make "kestrel"
    and "briefing" common, and two visible documents change places."""
    assert await _compare("cleared-for-R")


@pytest.fixture
def expanding(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The typo band asked as OpenSearch's fuzzy query (at most 50 words of the index's list)."""
    real = q.build_search_body

    def with_fuzzy(text: str, **kw: Any) -> dict[str, Any]:
        body = real(text, **kw)
        for band in body["query"]["bool"]["must"][0]["dis_max"]["queries"]:
            if band["bool"]["_name"] == "name_typo":
                band["bool"]["must"][0]["constant_score"]["filter"] = {
                    "fuzzy": {
                        "names.words": {
                            "value": text.lower(),
                            "fuzziness": 1,
                            "max_expansions": 50,
                        }
                    }
                }
        return body

    monkeypatch.setattr(q, "build_search_body", with_fuzzy)
    yield


async def test_the_leak_check_finds_fuzzy_expansion(expanding: None) -> None:
    """Page A's second worked example, at the real comparison: hidden near-names of "pembertom"
    use up the fuzzy query's 50 words, and the visible "Pemberton" goes missing."""
    assert await _compare("cleared-for-R")


# --- the bands, as built, against a real index (ADR-149 decisions 3, 5, 6) ------------------------


async def _search(text: str, **kw: Any) -> SearchPageResponse:
    reader = READERS["cleared-for-R"]
    nodes, texts = _seen(reader)
    async with throwaway_index(nodes, texts, schema=ONTOLOGY) as (client, index):
        return await s.search_page(
            SearchPageRequest(query=text, page_size=50, **kw),
            reader,
            _Unfiltered(),  # type: ignore[arg-type]
            searcher=s.opensearch_searcher(client, index),
            access_filter=index_access_filter(SCHEME, reader),
            phonetic_codes=phonetic_codes,
            types=TYPES,
            case_datasets={"ds-1": "Fixture Corp"},
            tau=TAU,
            schema=ONTOLOGY,
        )


def _bands(response: SearchPageResponse) -> list[tuple[str, str]]:
    return [(r.node_ids[0], r.match.band) for r in response.results]


async def test_an_exact_identifier_comes_first() -> None:
    found = await _search("AB123456C")
    assert _bands(found)[0] == ("p-smythe", "identifier")
    assert found.results[0].match.field == "Nino"


async def test_names_exact_every_word_sounds_alike_and_spelt_alike() -> None:
    assert _bands(await _search("Smythe"))[0] == ("p-smythe", "name_exact")
    assert ("p-smythe", "name_words") in _bands(await _search("John Smythe"))
    sounds = _bands(await _search("Smyth"))
    assert ("p-smythe", "name_sounds") in sounds and ("p-smith-r", "name_sounds") in sounds
    assert ("p-mohammed", "name_sounds") in _bands(await _search("Muhammad"))
    # A misspelling that also changes the sound, so the typo band is the best it reaches.
    assert _bands(await _search("Kestrel Holdinsg"))[0] == ("o-kestrel", "name_typo")


async def test_a_typo_needs_most_of_the_querys_trigrams() -> None:
    """The trigram band's 60% (ADR-150's trigram tokenizer): "invoice" shares one trigram with the
    title "Public notice" and finds no name; "Kestrel invoice" makes "Kestrel note" no close
    name."""
    assert not [b for _, b in _bands(await _search("invoice")) if b.startswith("name")]
    assert ("d-note", "name_typo") not in _bands(await _search("Kestrel invoice"))


async def test_a_mention_is_found_in_text_with_its_passage_marked() -> None:
    found = await _search("Kestrel invoice")
    assert _bands(found)[0] == ("d-memo", "mention_words")
    memo = found.results[0]
    assert memo.is_document
    assert [p.text for p in memo.passage if p.match] == ["Kestrel", "invoice"]
    assert "".join(p.text for p in memo.passage) == "Kestrel paid the invoice at Harbour Street"


async def test_names_rank_above_mentions_and_groups_count_records() -> None:
    found = await _search("Kestrel")
    bands = [b for _, b in _bands(found)]
    assert bands == sorted(bands, key=lambda b: -q.BAND_SCORES.get(b, 0))
    assert bands[0].startswith("name")
    groups = {g.key: g.count for g in found.groups}
    assert groups.get("Organisation") == 1 and groups.get("mentions") == 1
    assert [g.label for g in found.groups if g.key == "Organisation"] == ["Organisations"]
    assert found.counts_exact and found.total == sum(groups.values())


async def test_the_date_filter_and_the_offered_span() -> None:
    found = await _search(
        "invoice", filters=SearchFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    )
    assert [n for n, _ in _bands(found)] == ["d-memo"]
    everything = await _search("invoice")
    assert everything.filters.dates is not None
    assert (everything.filters.dates.earliest, everything.filters.dates.latest) == (
        "2026-01-05",
        "2026-02-10",
    )


async def test_suggestions_come_from_stored_prefixes() -> None:
    reader = READERS["cleared-for-R"]
    nodes, texts = _seen(reader)
    async with throwaway_index(nodes, texts, schema=ONTOLOGY) as (client, index):
        searcher = s.opensearch_searcher(client, index)
        access = index_access_filter(SCHEME, reader)
        graph: Any = _Unfiltered()

        async def suggest(request: SuggestRequest) -> Any:
            return await s.suggest_page(
                request, reader, graph, searcher=searcher, access_filter=access, schema=ONTOLOGY
            )

        insensitive = await suggest(SuggestRequest(query="smy", ignore_case=True))
        sensitive = await suggest(SuggestRequest(query="smy"))
        by_id = await suggest(SuggestRequest(query="AB1234", ignore_case=True))
    assert {n.id for n in insensitive.nodes} == {"p-smythe", "p-smythe-public"}
    assert sensitive.nodes == [] and sensitive.source == "index"  # "Smythe", not "smy"
    assert [n.id for n in by_id.nodes] == ["p-smythe"]
