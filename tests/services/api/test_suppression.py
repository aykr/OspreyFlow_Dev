"""Suppression marks — owner ruling R7 (TENTATIVE), 27 September 2026.

Per `CLAUDE.md` rule 4 the access-control case is here rather than deferred, and per rule 15 each
planted violation takes the shape the real mistake takes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.suppression import NodeNotVisibleError, SuppressionMarkStore

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OTHER_ANALYST = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")


def _node_write(*, owning_unit: str = "unit-1", classification: str = "OFFICIAL") -> NodeWrite:
    return NodeWrite(
        id=new_id(),
        type="Endpoint",
        properties={"value_normalised": f"+4479{new_id()[:8]}", "endpoint_kind": "msisdn"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="row:1", excerpt_hash="")],
            first_seen=datetime.now(UTC),
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by=ANALYST.id,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
async def store():
    s = await SuppressionMarkStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_a_mark_is_recorded_and_is_reversible(store) -> None:
    """R7's own word is "reversible" — an analyst proposing a suppression and then thinking
    better of it must leave nothing behind, which is also why marks are not graph writes: an
    append-only store would keep a revision for every change of mind."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write()], tx)
        await graph.commit_transaction(tx)

        investigation_id = new_id()
        mark = await store.mark(
            node_id, investigation_id, ANALYST, graph, reason="duplicate of the seizure record"
        )
        assert mark.marked_by == ANALYST.id
        assert mark.reason == "duplicate of the seizure record"
        assert (await store.marked_among([node_id]))[node_id].node_id == node_id

        assert await store.unmark(node_id, ANALYST, graph) is True
        assert await store.marked_among([node_id]) == {}


async def test_marking_does_not_touch_the_graph(store) -> None:
    """**The point of the whole design.** A mark is an intent, not a correction, so the node's own
    revision must not move — otherwise the supersession history that `01_DOMAIN_MODEL.md` §2.4
    keeps honest would fill with records of analysts changing their minds, and `superseded_by`
    would stop meaning "this was corrected"."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write()], tx)
        await graph.commit_transaction(tx)
        before = await graph.get_node(node_id, ANALYST)

        await store.mark(node_id, new_id(), ANALYST, graph, reason="proposed")
        await store.unmark(node_id, ANALYST, graph)

        after = await graph.get_node(node_id, ANALYST)
        assert after is not None, "marking removed the node from ordinary reads — it must not"
        assert after.audit.revision == before.audit.revision, (
            "marking minted a revision; a mark is an intent, not a correction"
        )
        assert after.audit.superseded_by is None, (
            "marking superseded the node — that is step two's job, and only once its evidence has "
            "arrived through the Studio"
        )


async def test_a_principal_who_cannot_see_the_node_cannot_mark_it(store) -> None:
    """Rule 4. The refusal must also not disclose whether the node exists: `ANALYST` (OFFICIAL)
    gets the same error for a real SECRET node as for an id that was never written."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (secret_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit="unit-9", classification="SECRET")], tx
        )
        await graph.commit_transaction(tx)

        with pytest.raises(NodeNotVisibleError) as refused_real:
            await store.mark(secret_id, new_id(), ANALYST, graph, reason="should not happen")
        invented = new_id()
        with pytest.raises(NodeNotVisibleError) as refused_invented:
            await store.mark(invented, new_id(), ANALYST, graph, reason="should not happen")

        assert str(refused_real.value).replace(secret_id, "X") == str(
            refused_invented.value
        ).replace(invented, "X"), (
            "a real-but-invisible node and an invented id produce different refusals, so the "
            "route leaks whether the node exists"
        )
        assert await store.marked_among([secret_id]) == {}, "the mark was written anyway"


async def test_unmark_also_refuses_a_principal_who_cannot_see_the_node(store) -> None:
    """Otherwise an invisible node could be probed for a mark by watching `True`/`False`."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (secret_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit="unit-9", classification="SECRET")], tx
        )
        await graph.commit_transaction(tx)
        with pytest.raises(NodeNotVisibleError):
            await store.unmark(secret_id, ANALYST, graph)


async def test_a_second_analyst_marking_the_same_node_records_who_holds_it_now(store) -> None:
    """Not an error: a colleague re-proposing a suppression with their own reason is a real thing
    that happens, and the useful record is who holds it *now* rather than a conflict."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write()], tx)
        await graph.commit_transaction(tx)

        investigation_id = new_id()
        await store.mark(node_id, investigation_id, ANALYST, graph, reason="first")
        await store.mark(node_id, investigation_id, OTHER_ANALYST, graph, reason="second")

        held = (await store.marked_among([node_id]))[node_id]
        assert held.marked_by == OTHER_ANALYST.id
        assert held.reason == "second"
