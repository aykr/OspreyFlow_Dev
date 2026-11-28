"""The ArcadeDB adapter's own batched read of the documents a drawn element cites (ADR-143
Amendment 8 items 2 to 4; slice GG4b, a security part; rules 3 and 4), without a store: what the
adapter sends for it, with whose access step, how many times, and what it keeps. What the store
returns for a hidden or an absent document is the conformance suite's to prove against ArcadeDB
(`tests/conformance/graph_port/test_drawn_documents.py`).

The client stands in for ArcadeDB and refuses what its access step refuses (rule 15), on both
axes "may read" has here (item 2: its handling and the case's datasets): a record is returned by a
Gremlin read only when the query's own classification list holds the record's and, where the query
carries the dataset step, one of the datasets it names is the record's. A query with no dataset step
reads every dataset, as the store would (the Conduit's own unlimited work, `datasets` None). A link
is returned only when both its ends pass too.

What fails if the adapter is wrong: a document asked with another's principal, with the reader's
datasets dropped or widened, or without the access step; kept when the read does not find it, or
when it is not a Document; one read for each element; a read made for an answer that cites nothing;
or a document read skipped when the cited id resolves to no record, which would make an absent
document cost less than a hidden one.
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
#: A dataset of D's own, which a case may read or stop reading apart from everything else.
STATEMENTS = "statements"
LINK = "e-drawn"


def _reader(who: str, clearance: str) -> Principal:
    return Principal(id=who, clearance=clearance, org_unit="unit-1", datasets=["layer"])


B = _reader("acct-b", "OFFICIAL")
C = _reader("acct-c", "SECRET")


def _record(
    identifier: str,
    kind: str,
    marking: str,
    drawn: str | None = None,
    dataset: str = "layer",
) -> dict[str, Any]:
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
        "datasets": [dataset],
    }


def _link(source: str, target: str, drawn: str) -> dict[str, Any]:
    """A drawn link citing `drawn`, as the store returns one."""
    record = _record(LINK, "ASSOCIATE_OF", "OFFICIAL", drawn)
    return {**record, "source": source, "target": target}


class _Store:
    """ArcadeDB, as far as `get_nodes` and `get_edges` ask it."""

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
                {"name": name, "type": kind, "indexes": unique}
                for name, kind in (
                    ("mx_Person", "vertex"),
                    ("mx_Document", "vertex"),
                    ("mx_ASSOCIATE_OF", "edge"),
                )
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
        # The dataset step (`AccessFilter.gremlin_dataset_step`): none where the query has none,
        # and an empty list reads nothing.
        step = re.search(
            r'filter\(values\("datasets"\)\.unfold\(\)\.is\(within\(\[([^\]]*)\]', query
        )
        read_set = None if step is None else set(re.findall(r"'([^']*)'", step.group(1)))
        asked = set(re.findall(r"'(#\d+:\d+)'", query.split("hasNot")[0].split(".has(")[0]))

        def passes(record: dict[str, Any]) -> bool:
            return record["handling"]["classification"] in classifications and (
                read_set is None or bool(read_set & set(record["datasets"]))
            )

        return [
            record
            for identifier, record in self.records.items()
            if self.rids[identifier] in asked
            and passes(record)
            and all(passes(self.records[record[e]]) for e in ("source", "target") if e in record)
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


# --- the other half of "may read": the case's datasets (item 2) -------------------------------


def _in_statements() -> _Store:
    """A drawn person and a drawn link, in the case's layer, both citing D, which sits in a
    dataset of its own."""
    return _Store(
        _record("p-1", "Person", "OFFICIAL", D),
        _record("p-2", "Person", "OFFICIAL"),
        _link("p-1", "p-2", D),
        _record(D, "Document", "SECRET", dataset=STATEMENTS),
    )


def _reading(reader: Principal, *datasets: str) -> Principal:
    """`reader` as the Conduit scopes them to a case that reads `datasets` (`scope_to_case`)."""
    return reader.model_copy(update={"datasets": list(datasets)})


async def test_a_document_is_kept_only_while_the_readers_case_reads_its_dataset() -> None:
    """C is cleared for D throughout. While C's case reads D's dataset, C is sent D on the drawn
    node and the drawn link; once the case no longer reads it, C is sent each of them with D in
    neither place. Nothing else about C changes. The author, A, is judged the same way."""
    author = _reader("acct-a", "SECRET")
    for reader in (C, author):
        for datasets, expected in ((("layer", STATEMENTS), D), (("layer",), None)):
            adapter = _adapter(_in_statements())
            scoped = _reading(reader, *datasets)

            (node,) = await adapter.get_nodes(["p-1"], scoped)
            (link,) = await adapter.get_edges([LINK], scoped)

            for element in (node, link):
                assert element.provenance.drawn is not None, "the drawn element is still sent"
                assert element.provenance.drawn.source_document == expected, (reader.id, datasets)
                assert (D in element.model_dump_json()) is (expected == D), (reader.id, datasets)
                assert element.provenance.sources_withheld is False


async def test_each_read_asks_with_the_datasets_of_the_person_it_is_sent_to() -> None:
    """One adapter, one store: the author's case reads D's dataset and another reader's does not.
    The author's read first, so that nothing of it can be carried into the other's."""
    adapter = _adapter(_in_statements())
    author = _reading(_reader("acct-a", "SECRET"), "layer", STATEMENTS)
    other = _reading(C, "layer")

    (for_author,) = await adapter.get_nodes(["p-1"], author)
    (for_other,) = await adapter.get_nodes(["p-1"], other)

    assert _cited([for_author]) == [D]
    assert _cited([for_other]) == [None] and D not in for_other.model_dump_json()
