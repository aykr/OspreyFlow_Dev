"""*Neighbourhood risk* (`spec/06_DECISIONS.md` ADR-109 phase E, ruling 9's D4 defaults) — written
before the read it tests, as the ADR asks (rule 1's spirit). Against live Postgres (the case's
alerts) and ArcadeDB (the neighbourhood), read as each principal.

What a mistake would do, and the case that catches it:

- a score summed over an alerted neighbour the reader cannot see would disclose it (rule 3): the
  reader's score must equal the score of the same neighbourhood without it
  (`test_a_hidden_alerted_neighbour_leaves_the_score_as_if_it_were_absent`), and a path through a
  hidden node must carry nothing (`test_risk_never_travels_through_a_node_the_reader_cannot_see`);
- an alert counted forever, or one a person closed as a false positive, would inflate it
  (`test_an_alert_past_its_ninety_days_or_closed_false_counts_nothing`);
- a neighbourhood too large to read whole, scored on a part (rule 2)
  (`test_a_neighbourhood_too_large_is_refused_not_scored_in_part`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.risk import NeighbourhoodTooLarge, neighbourhood_risk

from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import (
    Alert,
    AlertMode,
    EdgeWrite,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
OFFICIAL = Principal(id="risk-reader", clearance="OFFICIAL", org_unit="u")
SECRET = Principal(id="risk-cleared", clearance="SECRET", org_unit="u")
NOW = datetime.now(UTC)
PROV = Provenance(state=ProvenanceState.ASSERTED, first_seen=NOW,
                  sources=[SourceRef(document_id="t", locator="r", excerpt_hash="")])  # fmt: skip


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(classification=classification, handling_code="P", originator="u", owning_unit="u")


def _person(name: str, classification: str = "OFFICIAL") -> NodeWrite:
    return NodeWrite(id=new_node_id(), type="Person", properties={"family_name": name}, provenance=PROV,
                     handling=_handling(classification), created_by="t", created_at=NOW)  # fmt: skip


def _knows(a: NodeWrite, b: NodeWrite, classification: str = "OFFICIAL") -> EdgeWrite:
    return EdgeWrite(id=new_edge_id(), type="ASSOCIATE_OF", source=a.id, target=b.id, provenance=PROV,
                     handling=_handling(classification), created_by="t", created_at=NOW)  # fmt: skip


async def _write(graph, nodes: list[NodeWrite], edges: list[EdgeWrite]) -> None:  # type: ignore[no-untyped-def]
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(nodes, tx)
    await graph.upsert_edges(edges, tx)
    await graph.commit_transaction(tx)


@pytest.fixture
async def alerts() -> AsyncIterator[AlertStore]:
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    yield store
    await store.close()


async def _alert(store: AlertStore, case: str, on: NodeWrite, *, age_days: int = 1,
                 status: str = "open", disposition: str | None = None) -> None:  # fmt: skip
    await store.save(Alert(
        id=new_id(), rule_id="typology:r", owner_id="deployer", mode=AlertMode.FULL,
        referent_node_ids=[on.id], investigation_id=case, created_at=NOW - timedelta(days=age_days),
        typology="structuring", words=f"finding on {on.id}", status=status, disposition=disposition,  # type: ignore[arg-type]
    ))  # fmt: skip


async def _risk(graph, alerts: AlertStore, case: str, target: NodeWrite, reader: Principal):  # type: ignore[no-untyped-def]
    return await neighbourhood_risk(graph, ComputeRustworkxAdapter(), alerts, case, target.id, reader, today=NOW.date())


async def test_a_hidden_alerted_neighbour_leaves_the_score_as_if_it_were_absent(alerts: AlertStore) -> None:
    case, bare = f"case-{new_id()}", f"case-{new_id()}"
    target, seen, hidden = _person("Target"), _person("Seen"), _person("Hidden", "SECRET")
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _write(graph, [target, seen, hidden], [_knows(target, seen), _knows(target, hidden)])
        await _alert(alerts, case, seen)
        await _alert(alerts, case, hidden)
        official = await _risk(graph, alerts, case, target, OFFICIAL)
        cleared = await _risk(graph, alerts, case, target, SECRET)

    target2, seen2 = _person("Target"), _person("Seen")
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _write(graph, [target2, seen2], [_knows(target2, seen2)])
        await _alert(alerts, bare, seen2)
        without = await _risk(graph, alerts, bare, target2, OFFICIAL)

    assert official.score == without.score == 0.5
    assert [(c.hops, c.contribution) for c in official.contributions] == [
        (c.hops, c.contribution) for c in without.contributions
    ]
    assert cleared.score == 1.0, "a reader who sees both is told of both"


async def test_risk_never_travels_through_a_node_the_reader_cannot_see(alerts: AlertStore) -> None:
    case = f"case-{new_id()}"
    target, middle, far = _person("Target"), _person("Middle", "SECRET"), _person("Far")
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _write(graph, [target, middle, far], [_knows(target, middle), _knows(middle, far)])
        await _alert(alerts, case, far)
        assert (await _risk(graph, alerts, case, target, OFFICIAL)).score == 0.0
        assert (await _risk(graph, alerts, case, target, SECRET)).score == 0.25


async def test_an_alert_past_its_ninety_days_or_closed_false_counts_nothing(alerts: AlertStore) -> None:
    case = f"case-{new_id()}"
    target, old, cleared, live = _person("Target"), _person("Old"), _person("Cleared"), _person("Live")
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _write(graph, [target, old, cleared, live],
                     [_knows(target, old), _knows(target, cleared), _knows(target, live)])  # fmt: skip
        await _alert(alerts, case, old, age_days=91)
        await _alert(alerts, case, cleared, status="closed", disposition="false_positive")
        await _alert(alerts, case, live, age_days=89)
        risk = await _risk(graph, alerts, case, target, OFFICIAL)
        assert risk.score == 0.5
        assert [c.node_id for c in risk.contributions] == [live.id]


async def test_a_neighbourhood_too_large_is_refused_not_scored_in_part(
    alerts: AlertStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import services.api.risk as risk_module

    monkeypatch.setattr(risk_module, "MAX_NEIGHBOURHOOD", 2)
    case = f"case-{new_id()}"
    target, a, b, c = _person("Target"), _person("A"), _person("B"), _person("C")
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _write(graph, [target, a, b, c], [_knows(target, a), _knows(target, b), _knows(target, c)])
        with pytest.raises(NeighbourhoodTooLarge):
            await _risk(graph, alerts, case, target, OFFICIAL)
