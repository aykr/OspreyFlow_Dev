"""ADR-105: one entity's own picture, against a real ArcadeDB (the throwaway one).

Run against the real adapter, not a fake, because what matters most here is the adapter's own
behaviour: a superseded link no longer read, and a link or Document above the reader filtered out
of `expand` (rule 3). What a mistake would do, and the case that catches it:

- a picture set for one car drawn on another, or a replaced picture still the one shown
  (`test_a_new_picture_replaces_the_old_which_is_kept`);
- a removed picture deleted rather than kept as evidence (`test_removing_a_picture_keeps_it`);
- **a picture above the reader shown to them, or its existence given away** (rule 4,
  `test_a_picture_above_the_reader_reads_as_none` and
  `test_a_hidden_picture_does_not_let_the_older_one_show_through`);
- an SVG, a phone number or an entity not in the case given a picture (the refusal cases).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from services.api.document_content import UploadRefusedError
from services.api.entity_pictures import DEPICTS, EntityPictureService, PictureNotFoundError
from services.api.working_set.service import WorkingSetService
from services.extract.writer import NodeNotFoundError

from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    ExpandRequest,
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .working_set.fakes import FakeWorkingSetStore

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 10, 9, tzinfo=UTC)
OFFICIAL_READER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
SECRET_READER = Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1")
PNG_A = b"\x89PNG\r\n\x1a\n" + b"synthetic car"
PNG_B = b"\x89PNG\r\n\x1a\n" + b"synthetic car, other side"


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification, handling_code="P", originator="unit-1", owning_unit="unit-1"
    )


PROVENANCE = Provenance(
    state=ProvenanceState.ASSERTED,
    sources=[SourceRef(document_id="fixture", locator="row 1", excerpt_hash="")],
    first_seen=NOW,
)


def _write(node_id: str, node_type: str, **properties: object) -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type=node_type,
        properties=properties,
        provenance=PROVENANCE,
        handling=_handling(),
        created_by="loader",
        created_at=NOW,
    )


def _node(write: NodeWrite) -> Node:
    return Node(
        id=write.id,
        type=write.type,
        properties=write.properties,
        provenance=write.provenance,
        handling=write.handling,
        audit=AuditStub(created_at=NOW, created_by="loader"),
    )


ENTITIES = [
    _write("car-1", "Vehicle"),
    _write("car-2", "Vehicle"),
    _write(
        "phone-1",
        "Endpoint",
        value_raw="07700900123",
        value_normalised="+447700900123",
        endpoint_kind="msisdn",
    ),
    #: v14's one still-refused case below needs a type `DEPICTS` does not allow.
    _write("meeting-1", "Event"),
]


class _Fixture:
    def __init__(self, service: EntityPictureService, graph: object, media: InMemoryMediaStore):
        self.service = service
        self.graph = graph
        self.media = media


@pytest.fixture
async def fx() -> AsyncIterator[_Fixture]:
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(ENTITIES, tx)
        await graph.commit_transaction(tx)
        store = FakeWorkingSetStore()
        await store.add_nodes("inv-1", [_node(w) for w in ENTITIES])
        media = InMemoryMediaStore()
        service = EntityPictureService(
            WorkingSetService(graph, store, SCHEME), graph, media, ONTOLOGY, scheme=SCHEME
        )
        yield _Fixture(service, graph, media)


async def _set(
    fx: _Fixture,
    node_id: str = "car-1",
    data: bytes = PNG_A,
    *,
    principal: Principal = OFFICIAL_READER,
    classification: str = "OFFICIAL",
    name: str = "car.png",
) -> str:
    result = await fx.service.set(
        "inv-1", node_id, principal, name=name, data=data, handling=_handling(classification)
    )
    return result.document_id


async def _shown(fx: _Fixture, principal: Principal = OFFICIAL_READER) -> dict[str, str]:
    found = await fx.service.pictures("inv-1", ["car-1", "car-2", "phone-1"], principal)
    return {p.node_id: p.document_id for p in found}


async def test_a_picture_is_the_one_entitys_and_its_file_is_served(fx: _Fixture) -> None:
    document_id = await _set(fx)
    assert await _shown(fx) == {"car-1": document_id}
    assert await fx.service.file("inv-1", "car-1", OFFICIAL_READER) == (PNG_A, "image/png")
    with pytest.raises(PictureNotFoundError):
        await fx.service.file("inv-1", "car-2", OFFICIAL_READER)


async def test_a_new_picture_replaces_the_old_which_is_kept(fx: _Fixture) -> None:
    first = await _set(fx)
    second = await _set(fx, data=PNG_B, name="car-side.png")
    assert first != second
    assert await _shown(fx) == {"car-1": second}
    found = await fx.graph.expand(  # type: ignore[attr-defined]
        ExpandRequest(node_ids=["car-1"], edge_types=[DEPICTS], direction="in"), SECRET_READER
    )
    # The first link is superseded, so not read; the first picture itself is still evidence.
    assert [e.source for e in found.edges] == [second]
    assert await fx.graph.get_node(first, SECRET_READER) is not None  # type: ignore[attr-defined]


async def test_removing_a_picture_keeps_it(fx: _Fixture) -> None:
    document_id = await _set(fx)
    await fx.service.remove("inv-1", "car-1", OFFICIAL_READER)
    assert await _shown(fx) == {}
    with pytest.raises(PictureNotFoundError):
        await fx.service.file("inv-1", "car-1", OFFICIAL_READER)
    with pytest.raises(PictureNotFoundError):
        await fx.service.remove("inv-1", "car-1", OFFICIAL_READER)
    assert await fx.graph.get_node(document_id, SECRET_READER) is not None  # type: ignore[attr-defined]


async def test_a_picture_above_the_reader_reads_as_none(fx: _Fixture) -> None:
    document_id = await _set(fx, principal=SECRET_READER, classification="SECRET")
    assert await _shown(fx, SECRET_READER) == {"car-1": document_id}
    assert await _shown(fx, OFFICIAL_READER) == {}
    with pytest.raises(PictureNotFoundError):
        await fx.service.file("inv-1", "car-1", OFFICIAL_READER)
    with pytest.raises(PictureNotFoundError):
        await fx.service.remove("inv-1", "car-1", OFFICIAL_READER)


async def test_a_hidden_picture_does_not_let_the_older_one_show_through(fx: _Fixture) -> None:
    await _set(fx)
    hidden = await _set(fx, data=PNG_B, principal=SECRET_READER, classification="SECRET")
    assert await _shown(fx, SECRET_READER) == {"car-1": hidden}
    assert await _shown(fx, OFFICIAL_READER) == {}


async def test_an_svg_is_not_a_picture(fx: _Fixture) -> None:
    with pytest.raises(UploadRefusedError):
        await _set(fx, data=b"<svg onload='x'/>", name="car.svg")
    assert await _shown(fx, SECRET_READER) == {}


async def test_an_endpoint_takes_a_picture_of_its_own_since_v14(fx: _Fixture) -> None:
    """v13 refused this ("a phone number has no picture of its own"); ontology v14 (ADR-105
    Amendment 2, the owner's choice, 9 October 2026) adds Endpoint to `DEPICTS`'s `to`."""
    document_id = await _set(fx, "phone-1")
    assert (await _shown(fx, SECRET_READER)).get("phone-1") == document_id


async def test_an_event_still_has_no_picture_of_its_own(fx: _Fixture) -> None:
    """The service refuses a type `DEPICTS` does not allow — proven with one v14 still refuses,
    so the refusal path stays exercised now that Endpoint no longer is one."""
    with pytest.raises(UploadRefusedError):
        await _set(fx, "meeting-1")
    assert await _shown(fx, SECRET_READER) == {}


async def test_a_marking_the_uploader_could_not_read_is_refused(fx: _Fixture) -> None:
    with pytest.raises(UploadRefusedError):
        await _set(fx, classification="SECRET")
    assert await _shown(fx, SECRET_READER) == {}


async def test_an_entity_not_in_the_case_is_not_found(fx: _Fixture) -> None:
    with pytest.raises(NodeNotFoundError):
        await _set(fx, "car-9")
    with pytest.raises(NodeNotFoundError):
        await fx.service.file("inv-1", "car-9", OFFICIAL_READER)
    assert await fx.service.pictures("inv-1", ["car-9"], OFFICIAL_READER) == []


async def test_two_live_pictures_show_the_newer(fx: _Fixture) -> None:
    # Someone who cannot see the current picture sets one: it cannot supersede what it cannot
    # see, so two links are live (ADR-105, "Not decided here"), and a reader of both sees the newer.
    await _set(fx, principal=SECRET_READER, classification="SECRET")
    newer = await _set(fx, data=PNG_B)
    assert await _shown(fx, SECRET_READER) == {"car-1": newer}
    assert await _shown(fx, OFFICIAL_READER) == {"car-1": newer}
