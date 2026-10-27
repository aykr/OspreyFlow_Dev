"""ADR-130 Amendment 2, "a read that is written back", for a link change, on real ArcadeDB: a reader
whose case reads one of a link's two datasets changes it, and the stored link keeps every source
with the change added; what they are sent back carries none. The hermetic twin is
`test_link_changes_withheld.py`; this is the proof that the adapter's own withholding and the
writer's full read agree.

Needs a live ArcadeDB. Run alone with:
`cd OspreyFlow_Core && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini \
../OspreyFlow_Build/tests/services/api/test_link_changes_withheld_live.py`."""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.link_changes import LinkChangeRequest, LinkChangeService
from services.api.working_set.service import WorkingSetService

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .test_link_changes import InMemoryChanges, MovedNotes
from .working_set.fakes import FakeWorkingSetStore

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
WHEN = datetime(2026, 1, 1, tzinfo=UTC)
TWO = ["Z1001ZZ", "Z1002ZZ"]
SOURCE = SourceRef(document_id="files/calls.csv", locator="row 3", excerpt_hash="d" * 64)
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)
SCOPED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[TWO[0]])
SYSTEM = Principal(id="system", clearance="OFFICIAL", org_unit="unit-1", datasets=None)


def _person(name: str) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type="Person",
        properties={"family_name": name},
        provenance=Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN),
        handling=HANDLING,
        created_by="loader-1",
        created_at=WHEN,
        datasets=TWO,
    )


async def test_a_scoped_reader_changing_a_two_dataset_link_keeps_the_stored_sources() -> None:
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        a, b = _person("Quillfeather"), _person("Marlowe")
        link = EdgeWrite(
            id=new_edge_id(),
            type="ASSOCIATE_OF",
            source=a.id,
            target=b.id,
            provenance=Provenance(
                state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN
            ),
            handling=HANDLING,
            created_by="loader-1",
            created_at=WHEN,
            datasets=TWO,
        )
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([a, b], tx)
        await graph.upsert_edges([link], tx)
        await graph.commit_transaction(tx)

        # The working set is seeded as production seeds it: by the case-scoped principal, so what
        # it stores is already withheld, and the change must read the Vault again in full.
        store = FakeWorkingSetStore()
        stored_nodes = await graph.get_nodes([a.id, b.id], SCOPED)
        stored_edges = await graph.get_edges([link.id], SCOPED)
        assert all(n.provenance.sources_withheld for n in stored_nodes)
        assert all(e.provenance.sources_withheld for e in stored_edges)
        await store.add_nodes("inv-1", stored_nodes)
        await store.add_edges("inv-1", stored_edges)
        service = LinkChangeService(
            InMemoryChanges(),
            WorkingSetService(graph, store, SCHEME),
            graph,
            ONTOLOGY,
            MovedNotes(),
        )

        result = await service.change(
            "inv-1", link.id, SCOPED, LinkChangeRequest(occurrences=7, reason="Seen again")
        )

        stored = (await graph.get_edges([result.edge.id], SYSTEM))[0]
        assert [s.document_id for s in stored.provenance.sources] == [
            "files/calls.csv",
            "manual:change",
        ]
        assert not stored.provenance.sources_withheld
        sent = result.to_response(SCOPED)
        assert sent.edge.provenance.sources == [] and sent.edge.provenance.sources_withheld
        read_back = (await graph.get_edges([result.edge.id], SCOPED))[0]
        assert read_back.provenance.sources_withheld
