"""`services/api/change_stream.py` — `06_DECISIONS.md` ADR-037's amendment.
Real Valkey, real ArcadeDB for the resolution-producer case: the whole point of this module is
proving a *consumer* sees what a *producer* actually wrote, which a fake on either side cannot
prove.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from services.api.change_stream import ChangeStreamWriter
from services.api.config import ValkeyConfig
from services.resolve.trigger import run_resolution_for_entity_type
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Provenance, ProvenanceState, SourceRef


@pytest.fixture
async def valkey() -> Valkey:
    cfg = ValkeyConfig.from_env()
    client = Valkey(host=cfg.host, port=cfg.port, db=cfg.db)
    yield client
    await client.aclose()


async def test_publish_is_a_no_op_when_nothing_was_touched(valkey: Valkey) -> None:
    writer = ChangeStreamWriter(valkey)
    assert await writer.publish("ingest", node_ids=[], edge_ids=[]) is None


async def test_a_consumer_reads_back_what_a_producer_published(valkey: Valkey) -> None:
    writer = ChangeStreamWriter(valkey)
    edge_id = new_id()
    published = await writer.publish("manual_assertion", edge_ids=[edge_id])
    assert published is not None

    entries = await writer.read_since()
    matching = [e for e in entries if e.entry_id == published.entry_id]
    assert len(matching) == 1
    assert matching[0].source == "manual_assertion"
    assert matching[0].edge_ids == [edge_id]


async def test_change_stream_carries_a_same_as_edge_written_by_resolution_with_no_new_ingest(
    valkey: Valkey,
) -> None:
    """The named test `06_DECISIONS.md` ADR-037's amendment calls for: a `SAME_AS` edge appearing
    between two *already-existing* nodes, written by the resolution trigger alone — no ingest
    call anywhere in this test — must still reach the change stream. This is the exact case the
    amendment exists for: an ingest-only trigger would miss it silently and forever, since
    resolution's own normal output (not an edge case) creates matches with no new ingest."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        # A purely alphabetic marker — `phonetics.soundex` (`duckdb_setup.py`) is only guarded
        # against an empty/falsy value, not against punctuation or digits, and a hyphenated
        # alphanumeric marker was found to crash it (`IndexError: string index out of range`)
        # rather than being a real defect in the resolver itself worth chasing here.
        marker = "".join(chr(ord("a") + int(d)) for d in str(uuid.uuid4().int)[:8])
        await graph.upsert_nodes(
            [
                _person_write(f"Resolveonly{marker}", "Dana", "1980-01-01"),
                _person_write(f"Resolveonly{marker}", "Dana", "1980-01-01"),
            ],
            tx,
        )
        await graph.commit_transaction(tx)

        before = await ChangeStreamWriter(valkey).read_since()
        before_ids = {e.entry_id for e in before}

        tx = await graph.begin_transaction()
        result = await run_resolution_for_entity_type(
            "Person", graph=graph, tx=tx, ontology=ontology, scheme=scheme, valkey=valkey
        )
        await graph.commit_transaction(tx)
        assert result.same_as_written >= 1

        after = await ChangeStreamWriter(valkey).read_since()
        new_entries = [e for e in after if e.entry_id not in before_ids]
        resolution_entries = [e for e in new_entries if e.source == "resolution"]

        assert len(resolution_entries) >= 1, (
            "a consumer reading the change stream after a resolution-only run must see an entry "
            "with source='resolution' — none did"
        )
        assert resolution_entries[-1].edge_ids, "the entry must carry the written SAME_AS edge id"


def _person_write(family_name: str, given_names: str, date_of_birth: str) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={
            "family_name": family_name,
            "given_names": given_names,
            "date_of_birth": date_of_birth,
        },
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        created_by="test",
        created_at=now,
    )
