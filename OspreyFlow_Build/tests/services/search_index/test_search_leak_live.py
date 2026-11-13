"""The leak test (the owner's requirement a; page A §4, read and ruled on 13 November 2026; ADR-149,
reserved): **an analyst cannot see, count or infer a record they are not cleared for.**

One world of synthetic records is indexed through the real document builder and bulk writer
(rules' `throwaway_index`). Hidden records are made to look as much like visible ones as possible:
the same names, sound-alikes, words in text, identifiers, and same-as links to visible records.
For each reader, a second index holds only what the Conduit's own rule (`principal_may_view`,
`in_case_datasets`, and a text's unit) lets that reader see. **Every search and suggestion the
reader makes must answer identically from both:** results, their order, merged entities, passages,
every group count and total, the filters offered, and `more`.

The graph here deliberately does **not** filter: it returns any node asked for. So a hit the index
leaks reaches the response and shows as a difference, rather than being dropped by the graph's own
filter.

Shown red first (rule 15):
- once per part of the access filter, with that part replaced by match-all
  (`test_the_leak_check_finds_each_filter_part_dropped`);
- once for ranking: OpenSearch's default scoring lets hidden records reorder visible ones
  (`test_default_relevance_would_leak_through_word_rarity`);
- once for expansion: a fuzzy query lets hidden near-names push a visible one out
  (`test_fuzzy_expansion_would_leak_a_visible_record_out`).

A reverted, withdrawn or superseded record is not planted here: the graph returns none for it, so
the indexer deletes it (ADR-150), and rules' `test_feed_live.py` shows each such event leaving the
index. `throwaway_index` takes live nodes only.

Needs a lease: the leased stack's OpenSearch, its port pinned (`stack_lease.sh remote`).
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from opensearchpy import AsyncOpenSearch
from services.api import search_index_query as q
from services.api import search_service as s
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


# --- the world ------------------------------------------------------------------------------------

VISIBLE_LOOKING = [
    _node("p-smythe", "Person", family_name="Smythe", given_names="John", nino="AB123456C"),
    _node("p-mohammed", "Person", family_name="Mohammed", given_names="Ali"),
    _node("o-kestrel", "Organisation", name="Kestrel Holdings", org_ref="ORG-1"),
    _node("d-memo", "Document", title="Harbour memo", sent_at="2026-01-05T09:00:00Z"),
    _node("d-report", "Document", title="Quarterly report", sent_at="2026-02-10T09:00:00Z"),
    _node("d-note", "Document", title="Kestrel note", sent_at="2026-03-01T09:00:00Z"),
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
    # Many hidden documents whose text makes "kestrel" common (the word-rarity leak).
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
    # Many hidden near-names of "smyth", one letter changed (the expansion leak).
    *[
        _node(f"p-near-{i}", "Person", cls="SECRET", family_name=name)
        for i, name in enumerate(
            sorted(
                {
                    "smyth"[:pos] + letter + "smyth"[pos + 1 :]
                    for pos in range(5)
                    for letter in "abcdefghijklmnopqrstuvwxyz"
                }
                - {"smyth"}
            )
        )
    ],
]
NODES = {n.id: n for n in VISIBLE_LOOKING + HIDDEN_LOOKING}
TEXTS = {
    "d-memo": ("Kestrel paid the invoice at Harbour Street", "unit-1"),
    "d-report": ("the invoice and the invoice and the invoice", "unit-1"),
    # The Document is visible; its text is held by another unit.
    "d-note": ("Kestrel invoice for the harbour", "unit-2"),
    "d-public": ("Kestrel invoice notice for the harbour", "unit-2"),
    **{f"d-secret-{i}": ("kestrel kestrel briefing", "unit-1") for i in range(40)},
}
LINKS = [
    Edge(
        id="same-as-1",
        type=SAME_AS,
        source="p-smythe",
        target="p-smyth-secret",
        properties={"score": 0.99},
        provenance=VISIBLE_LOOKING[0].provenance,
        handling=VISIBLE_LOOKING[0].handling,
        audit=VISIBLE_LOOKING[0].audit,
    )
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
    s.SearchPageRequest(query=text, page_size=50)
    for text in [
        "Smythe",
        "Smyth",
        "Smithe",
        "John Smythe",
        "AB123456C",
        "Kestrel Holdings",
        "Kestrel",
        "Kestrel invoice",
        "invoice",
        "Mohammed",
        "Muhammad",
        "harbour",
    ]
] + [
    s.SearchPageRequest(query="Smyth", group="Person", page_size=50),
    s.SearchPageRequest(query="Kestrel", group="mentions", page_size=50),
    s.SearchPageRequest(query="Kestrel", filters=s.SearchFilters(datasets=["ds-1"]), page_size=50),
    s.SearchPageRequest(
        query="invoice",
        filters=s.SearchFilters(date_from="2026-01-01", date_to="2026-01-31"),
        page_size=50,
    ),
    s.SearchPageRequest(query="Smyth", page=1, page_size=1),
]
SUGGESTIONS = ["Sm", "Smy", "Smyth", "Kes", "Mo", "Mu", "AB12", "Ha"]


def _may_see(node: Node, principal: Principal) -> bool:
    if node.handling.handling_code not in SCHEME.handling_codes:
        return False
    return principal_may_view(node.handling, principal, SCHEME) and in_case_datasets(
        node.datasets, principal
    )


def _seen(principal: Principal) -> tuple[list[Node], dict[str, tuple[str, str]]]:
    """What `principal` may see, by the Conduit's own rule: the absent world for them."""
    nodes = [n for n in NODES.values() if _may_see(n, principal)]
    shown = {n.id for n in nodes}
    texts = {k: v for k, v in TEXTS.items() if k in shown and v[1] == principal.org_unit}
    return nodes, texts


class _Unfiltered:
    """A graph that returns every node and link asked for, so the index's filter is the only one."""

    async def get_nodes(self, node_ids: Sequence[str], principal: Principal) -> list[Node]:
        return [NODES[i] for i in node_ids if i in NODES]

    async def edges_among(
        self, node_ids: Sequence[str], principal: Principal, *, edge_types: Sequence[str]
    ) -> list[Edge]:
        ids = set(node_ids)
        return [e for e in LINKS if e.type in edge_types and e.source in ids and e.target in ids]

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        raise AssertionError("the fallback must not answer in the leak test")


async def _answers(
    client: AsyncOpenSearch, index: str, principal: Principal, access: dict[str, Any]
) -> list[Any]:
    searcher = s.opensearch_searcher(client, index)
    out: list[Any] = []
    for request in SEARCHES:
        if not set(request.filters.datasets or ()) <= set(principal.datasets or ()):
            # A filter on a dataset outside the case is refused (422) before the index is asked.
            with pytest.raises(ValueError, match="not a dataset of this case"):
                await s.search_page(
                    request,
                    principal,
                    _Unfiltered(),  # type: ignore[arg-type]
                    searcher=searcher,
                    access_filter=access,
                    phonetic_codes=phonetic_codes,
                    types=TYPES,
                    case_datasets={},
                    tau=TAU,
                )
            out.append((request.model_dump(), "refused"))
            continue
        response = await s.search_page(
            request,
            principal,
            _Unfiltered(),  # type: ignore[arg-type]
            searcher=searcher,
            access_filter=access,
            phonetic_codes=phonetic_codes,
            types=TYPES,
            case_datasets={d: n for d, n in CASE_NAMES.items() if d in (principal.datasets or ())},
            tau=TAU,
        )
        assert response.source == "index", "the leak test must be answered by the index"
        out.append((request.model_dump(), response.model_dump()))
    for prefix in SUGGESTIONS:
        body = q.build_suggest_body(prefix, access_filter=access, limit=10)
        out.append((prefix, q.read_suggest_response(await searcher(body), limit=10)))
    return out


@asynccontextmanager
async def _worlds(principal: Principal) -> AsyncIterator[tuple[AsyncOpenSearch, str, str]]:
    nodes, texts = _seen(principal)
    async with throwaway_index(list(NODES.values()), TEXTS, schema=ONTOLOGY) as (client, present):
        async with throwaway_index(nodes, texts, schema=ONTOLOGY, client=client) as (_, absent):
            yield client, present, absent


def _differences(present: list[Any], absent: list[Any]) -> list[Any]:
    return [(p[0], p[1], a[1]) for p, a in zip(present, absent, strict=True) if p != a]


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
    found = sum(len(r[1]["results"]) for r in with_hidden if isinstance(r[1], dict))
    if reader == "empty-case":
        assert found == 0
    else:
        assert found > 0, "the test must not pass by finding nothing"


async def test_the_world_is_not_vacuous() -> None:
    """The hidden records are really in the present index and really match the queries: an
    unlimited filter finds them."""
    reader = READERS["cleared-for-R"]
    async with _worlds(reader) as (client, present, absent):
        everything: dict[str, Any] = {"bool": {}}
        searcher = s.opensearch_searcher(client, present)
        body = q.build_search_body(
            "Smyth",
            access_filter=everything,
            phonetic_codes=phonetic_codes,
            types=TYPES,
            page_size=50,
        )
        ids = {h["_source"]["node_id"] for h in (await searcher(body))["hits"]["hits"]}
    assert {"p-smyth-secret", "p-smythe-r-other", "p-smythe-undefined"} <= ids


@pytest.mark.parametrize("part", ["classification", "handling_code", "datasets", "text_unit"])
async def test_the_leak_check_finds_each_filter_part_dropped(part: str) -> None:
    """Rule 15: the comparison above, shown red with each part of the real filter replaced by
    match-all, for the reader each part hides something from."""
    reader = READERS["not-for-R" if part == "handling_code" else "cleared-for-R"]
    access = copy.deepcopy(index_access_filter(SCHEME, reader))
    access["bool"]["filter"] = [
        {"bool": {"_name": f"{part} dropped"}} if c["bool"]["_name"] == part else c
        for c in access["bool"]["filter"]
    ]
    async with _worlds(reader) as (client, present, absent):
        with_hidden = await _answers(client, present, reader, access)
        without = await _answers(client, absent, reader, access)
    assert _differences(with_hidden, without)


def _default_relevance(body: Any) -> Any:
    """The mapping as OpenSearch would have it by default: no `similarity: boolean` anywhere."""
    if isinstance(body, dict):
        return {k: _default_relevance(v) for k, v in body.items() if k != "similarity"}
    if isinstance(body, list):
        return [_default_relevance(v) for v in body]
    return body


async def _order(client: AsyncOpenSearch, index: str, body: dict[str, Any]) -> list[str]:
    reply = await client.search(index=index, body=body)
    return [h["_source"]["node_id"] for h in reply["hits"]["hits"]]


async def test_default_relevance_would_leak_through_word_rarity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15 for ranking (page A's first worked example): with OpenSearch's default scoring, 40
    hidden documents mentioning "kestrel" reverse the order of two visible ones; with the built
    query and mapping they do not."""
    reader = READERS["cleared-for-R"]
    access = index_access_filter(SCHEME, reader)
    plain = {
        "query": {"bool": {"filter": [access], "must": [{"match": {"text": "kestrel invoice"}}]}},
        "_source": ["node_id"],
    }
    built = q.build_search_body(
        "Kestrel invoice",
        access_filter=access,
        phonetic_codes=phonetic_codes,
        types=TYPES,
        page_size=50,
    )
    async with _worlds(reader) as (client, present, absent):
        strict = (await _order(client, present, built), await _order(client, absent, built))
    original = index_testing.index_body  # type: ignore[attr-defined]
    monkeypatch.setattr(index_testing, "index_body", lambda: _default_relevance(original()))
    async with _worlds(reader) as (client, present, absent):
        default = (await _order(client, present, plain), await _order(client, absent, plain))
    assert strict[0] == strict[1]
    assert default[0] != default[1], default


async def test_fuzzy_expansion_would_leak_a_visible_record_out() -> None:
    """Rule 15 for expansion (page A's second worked example): a fuzzy query for "smyth" expands to
    at most 50 words, and the hidden near-names can use them up; the built query expands nothing."""
    reader = READERS["cleared-for-R"]
    access = index_access_filter(SCHEME, reader)
    fuzzy = {
        "query": {
            "bool": {
                "filter": [access, {"term": {"kind": "node"}}],
                "must": [
                    {
                        "fuzzy": {
                            "names.words": {"value": "smyth", "fuzziness": 1, "max_expansions": 50}
                        }
                    }
                ],
            }
        },
        "_source": ["node_id"],
        "size": 100,
    }
    built = q.build_search_body(
        "Smyth", access_filter=access, phonetic_codes=phonetic_codes, types=TYPES, page_size=50
    )
    async with _worlds(reader) as (client, present, absent):
        strict = (await _order(client, present, built), await _order(client, absent, built))
        expanded = (await _order(client, present, fuzzy), await _order(client, absent, fuzzy))
    assert strict[0] == strict[1]
    assert "p-smythe" in expanded[1]
    assert expanded[0] != expanded[1], expanded
