"""The ArcadeDB adapter's own batched read of the documents a drawn element cites (ADR-143
Amendment 8 items 2 to 4; slice GG4b, a security part; rules 3 and 4), without a store: what the
adapter sends for it, with whose access step, how many times, and what it keeps. What the store
returns for a hidden or an absent document is the conformance suite's to prove against ArcadeDB
(`tests/conformance/graph_port/test_drawn_documents.py`).

The client stands in for ArcadeDB and refuses what its access step refuses (rule 15): a record is
returned by a Gremlin read only when the query's own classification list holds the record's.

What fails if the adapter is wrong: a document asked with another's principal, or without the
access step; kept when the read does not find it, or when it is not a Document; one read for each
element; a read made for an answer that cites nothing; or a document read skipped when the cited id
resolves to no record, which would make an absent document cost less than a hidden one.
"""

from __future__ import annotations

import re
from typing import Any, cast

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from ontology.handling import load_uk_le_scheme, sources_in_full
from schemas.domain import Node, Principal

NOW = "2026-11-01T00:00:00+00:00"
BOARD_LOCATOR = "a drawing board of the case"
D, MEMO = "doc-sealed-statement", "doc-open-memo"


def _reader(who: str, clearance: str) -> Principal:
    return Principal(id=who, clearance=clearance, org_unit="unit-1", datasets=["layer"])


B = _reader("acct-b", "OFFICIAL")
C = _reader("acct-c", "SECRET")


def _record(identifier: str, kind: str, marking: str, drawn: str | None = None) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "state": "asserted",
        "sources": [
            {"document_id": drawn or "files/r.csv", "locator": BOARD_LOCATOR, "excerpt_hash": ""}
        ]
        if drawn
        else [{"document_id": "files/r.csv", "locator": "row 1", "excerpt_hash": ""}],
        "first_seen": NOW,
    }
    if drawn:
        provenance["drawn"] = {
            "item_id": f"item-{identifier}",
            "asserted_by": "acct-a",
            "board_id": "board-a",
            "case_id": "case-k",
            "label": "Unknown male",
            "grading": {"source": "B", "intelligence": "2", "handling": "1"},
            "source_note": "Seen from the quay",
            "source_document": drawn,
        }
    return {
        "id": identifier,
        "label": f"mx_{kind}",
        "provenance": provenance,
        "handling": {
            "classification": marking,
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        "audit": {"created_at": NOW, "created_by": "acct-a"},
        "datasets": ["layer"],
    }


class _Store:
    """ArcadeDB, as far as `get_nodes` asks it."""

    def __init__(self, *records: dict[str, Any]) -> None:
        self.records = {r["id"]: r for r in records}
        self.rids = {identifier: f"#1:{n}" for n, identifier in enumerate(self.records)}
        #: The record-id lookups, as (type, ids), and each Gremlin read.
        self.lookups: list[tuple[str, list[str]]] = []
        self.gremlin_sent: list[str] = []

    async def sql(self, command: str, *, params: Any = None, **_: Any) -> list[dict[str, Any]]:
        if command == "SELECT name, type, indexes FROM schema:types":
            unique = [{"name": "T[id]", "typeName": "T", "unique": True, "properties": ["id"]}]
            return [
                {"name": name, "type": "vertex", "indexes": unique}
                for name in ("mx_Person", "mx_Document")
            ]
        named = re.search(r"mx_\w+", command)
        assert named is not None, command
        asked = list((params or {}).get("ids", []))
        self.lookups.append((named.group(0), asked))
        return [
            {"rid": self.rids[i]}
            for i in asked
            if i in self.records and self.records[i]["label"] == named.group(0)
        ]

    async def gremlin(self, query: str, **_: Any) -> list[dict[str, Any]]:
        self.gremlin_sent.append(query)
        allowed = re.search(r'has\("handling_classification",within\(\[?([^)\]]*)', query)
        assert allowed is not None, f"a read with no access step: {query}"
        classifications = set(re.findall(r"'([^']*)'", allowed.group(1)))
        asked = set(re.findall(r"'(#\d+:\d+)'", query.split("hasNot")[0].split(".has(")[0]))
        return [
            record
            for identifier, record in self.records.items()
            if self.rids[identifier] in asked
            and record["handling"]["classification"] in classifications
        ]


def _adapter(store: _Store) -> GraphArcadeDBAdapter:
    return GraphArcadeDBAdapter(cast(Any, store), load_uk_le_scheme())


def _held(*extra: dict[str, Any]) -> _Store:
    people = [_record(f"p-{n}", "Person", "OFFICIAL", D if n % 2 else MEMO) for n in range(6)]
    return _Store(
        *people,
        _record(D, "Document", "SECRET"),
        _record(MEMO, "Document", "OFFICIAL"),
        *extra,
    )


def _cited(nodes: list[Node]) -> list[str | None]:
    return [n.provenance.drawn.source_document for n in nodes if n.provenance.drawn is not None]


IDS = [f"p-{n}" for n in range(6)]


async def test_one_read_of_the_cited_documents_with_the_readers_own_access_step() -> None:
    for reader, expected in ((B, [MEMO, None]), (C, [MEMO, D])):
        store = _held()
        nodes = await _adapter(store).get_nodes(IDS, reader)

        assert _cited(nodes) == expected * 3, reader.id
        # One read for the answer's items, then one for the documents they cite: not one each.
        assert len(store.gremlin_sent) == 2, store.gremlin_sent
        document_lookups = [ids for kind, ids in store.lookups if ids == sorted([D, MEMO])]
        assert document_lookups == [sorted([D, MEMO])], "asked of the Document type alone, once"
        assert [k for k, ids in store.lookups if ids == sorted([D, MEMO])] == ["mx_Document"]
        for node in nodes:
            if node.provenance.drawn is not None and node.provenance.drawn.source_document is None:
                assert D not in node.model_dump_json()


async def test_a_cited_id_costs_the_same_hidden_or_absent() -> None:
    """Item 3: the document read is sent even when no cited id resolves to a record."""
    hidden, absent = _held(), _held()
    del absent.records[D]

    await _adapter(hidden).get_nodes(["p-1"], B)
    await _adapter(absent).get_nodes(["p-1"], B)

    assert len(hidden.gremlin_sent) == len(absent.gremlin_sent) == 2


async def test_an_id_that_is_not_a_document_is_not_kept() -> None:
    other = "p-not-a-document"
    store = _Store(
        _record("p-1", "Person", "OFFICIAL", other), _record(other, "Person", "OFFICIAL")
    )

    (node,) = await _adapter(store).get_nodes(["p-1"], C)

    assert _cited([node]) == [None] and other not in node.model_dump_json()


async def test_an_answer_that_cites_nothing_makes_no_read() -> None:
    store = _Store(_record("p-loaded", "Person", "OFFICIAL"))

    await _adapter(store).get_nodes(["p-loaded"], B)

    assert len(store.gremlin_sent) == 1


async def test_a_read_written_back_makes_no_read_and_keeps_the_document() -> None:
    store = _held()
    with sources_in_full():
        (node,) = await _adapter(store).get_nodes(["p-1"], B)

    assert _cited([node]) == [D] and len(store.gremlin_sent) == 1


async def test_a_failed_document_read_keeps_nothing() -> None:
    class Failing(_Store):
        async def gremlin(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
            if self.gremlin_sent:
                self.gremlin_sent.append(query)
                raise ConnectionError("the store went away")
            return await super().gremlin(query, **kwargs)

    failing = Failing(*_held().records.values())

    nodes = await _adapter(failing).get_nodes(IDS, C)

    assert len(nodes) == 6 and _cited(nodes) == [None] * 6
