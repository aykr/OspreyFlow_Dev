"""`seed_support.clear_seeded_links` against a real ArcadeDB: the Enron seed's `--replace-links`
deletes only its own email links, so the address nodes stay and so does every other link to them.

Seen planning the repair of the owner's tripled emails: `--replace-graph` deletes the address
vertices, and deleting a vertex deletes every link touching it, including the `MENTIONED_IN` links
from the analyst's own email Documents and the entities they marked. Rewriting only the
`COMMUNICATED_WITH` links (the ones whose counts were inflated) is the repair that keeps them."""

from __future__ import annotations

from datetime import UTC, datetime

from scripts.seed_support import clear_seeded_links

from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.testing import arcadedb_adapter
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

NOW = datetime(2026, 10, 1, tzinfo=UTC)
HANDLING = Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")
EVERYONE = Principal(id="r", clearance="SECRET", org_unit="u")
PROVENANCE = Provenance(
    state=ProvenanceState.ASSERTED,
    sources=[SourceRef(document_id="enron-corpus", locator="m", excerpt_hash="")],
    first_seen=NOW,
)


def _node(node_id: str, node_type: str, **properties: object) -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type=node_type,
        properties=properties,
        provenance=PROVENANCE,
        handling=HANDLING,
        created_by="seed",
        created_at=NOW,
        datasets=["enron"],
    )


def _link(link_id: str, link_type: str, source: str, target: str) -> EdgeWrite:
    return EdgeWrite(
        id=link_id,
        type=link_type,
        source=source,
        target=target,
        provenance=PROVENANCE,
        handling=HANDLING,
        created_by="seed",
        created_at=NOW,
        datasets=["enron"],
    )


async def test_only_the_seeds_email_links_go_and_everything_attached_to_the_addresses_stays() -> (
    None
):
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as graph:
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(
            [
                _node("enron-ep-a", "Endpoint", value_normalised="a@enron.com"),
                _node("enron-ep-b", "Endpoint", value_normalised="b@enron.com"),
                _node("email:enron-ev-1", "Document", title="Re: plant"),
            ],
            tx,
        )
        await graph.upsert_edges(
            [
                _link("enron-comm-1", "COMMUNICATED_WITH", "enron-ep-a", "enron-ep-b"),
                _link(
                    "email:enron-ev-1:mentions:a", "MENTIONED_IN", "enron-ep-a", "email:enron-ev-1"
                ),
            ],
            tx,
        )
        await graph.commit_transaction(tx)

        removed = await clear_seeded_links(
            graph._client,  # noqa: SLF001 - the seed's own client, on the test database
            edge_type=groovy_identifier(physical_type_name("COMMUNICATED_WITH")),
            edge_prefix="enron-comm-",
        )

        assert removed == 1
        assert await graph.get_node("enron-ep-a", EVERYONE) is not None
        assert await graph.get_node("email:enron-ev-1", EVERYONE) is not None
        left = await graph.edges_among(["enron-ep-a", "enron-ep-b", "email:enron-ev-1"], EVERYONE)
        assert [e.id for e in left] == ["email:enron-ev-1:mentions:a"]
