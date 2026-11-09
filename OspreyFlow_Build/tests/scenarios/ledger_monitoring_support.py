"""What Operation Ledger's monitoring-week tests share (`spec/06_DECISIONS.md` ADR-108 Amendment 5): the
case's September, built by the seed's own `build_ledger_graph`, and the week's export loaded the way
the run route loads it. Not a test module.

**September is the seed's.** `ledger.build_ledger_graph` runs the KYC, companies and transactions
recipes through the engine and makes the seed's direct writes, behind the real `DatasetStampingGraph`,
so every element is stamped `ledger` as the seed's are. Its money-movement events go into a real
DuckDB (the adapter's `load_events`), scoped to the scene's case, so a rule reads September around
the week as it would in the deployment.

**The week, as `run_published_recipe` runs it.** The committed `ledger_transactions_recipe.yaml`
through `studio_publish.load_with_rules` with the case's rules; the run's events into the analytics
store; the rules after commit (`post_commit_notes`, the `RuleGate`'s own); then the change stream's
touched nodes to every active hotlist (`evaluation.evaluate_hotlists_for_entry`).

**The graph answers as the adapter does (rule 15).** `LedgerGraph` is ADR-127 Amendment 41's
`AccessGraph` (every read judged as the reader by the scheme's own predicate and the reader's
datasets; a hidden node absent, never an error), with the two reads a re-screening makes:
`list_nodes`, paged to a cursor over only what the reader sees, and `find_node`, a whole node the
reader may see or nothing. What it does not model: the store's indexes and its timing.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from services.api.change_stream import ChangeStreamEntry, touched_node_ids
from services.api.dataset_scope import DatasetStampingGraph
from services.api.evaluation import evaluate_hotlists_for_entry
from services.api.rule_evaluation import RuleGate
from services.api.studio_publish import load_with_rules, post_commit_notes
from services.ingest.recipe_loader import load_recipe
from tests.ingest.test_row_keys import KeyStore, Sink
from tests.scenarios.pid_monitoring_support import AccessGraph, Audit, SignatureSet

from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from demo_fixtures import ledger, ledger_monitoring
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.analytics import EventRecord
from schemas.domain import ListNodesPage, Node, Principal

DATASET = "ledger"
ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
#: The seed's worker (`scripts.seed_ledger_fixture`: OFFICIAL, the demo unit), scoped to the dataset.
SEEDER = Principal(id="ledger-seed-worker", clearance="OFFICIAL", org_unit="verify",
                   datasets=[DATASET])  # fmt: skip
#: The demo data engineer, who loads the week through the Studio.
ENGINEER = Principal(id="osprey-demo-engineer", clearance="OFFICIAL", org_unit="verify",
                     roles=["data_engineer"], datasets=[DATASET])  # fmt: skip
RECIPE = load_recipe(ledger.FIXTURES / ledger_monitoring.RECIPE)


class LedgerGraph(AccessGraph):
    """See the module docstring."""

    async def find_node(self, entity_type: str, field: str, value: str, principal: Any) -> Any:
        for node in self._visible_nodes(principal).values():
            if node.type == entity_type and str(node.properties.get(field)) == value:
                return self._node(node)
        # A write still open in the transaction (the engine finding what it has just made).
        for node in self.open_nodes:
            if node.type == entity_type and str(node.properties.get(field)) == value:
                return self._node(node)
        return None

    async def list_nodes(self, entity_type: str, principal: Principal, *, cursor: str | None = None,
                         limit: int = 500) -> ListNodesPage:  # fmt: skip
        seen = self._visible_nodes(principal)
        ids = sorted(i for i, n in seen.items() if n.type == entity_type and (cursor is None or i > cursor))
        page = [self._node(seen[i]) for i in ids[:limit]]
        more = len(ids) > limit
        return ListNodesPage(nodes=page, next_cursor=page[-1].id if more and page else None)

    def account(self, number: str) -> Node:
        (found,) = [n for n in self._live_nodes().values()
                    if n.type == "Account" and n.properties.get("account_number") == number]  # fmt: skip
        return self._node(found)

    def person(self, family_name: str) -> Node:
        """The customer of that family name, not a listed party a screening match wrote."""
        (found,) = [n for n in self._live_nodes().values()
                    if n.type == "Person" and n.properties.get("family_name") == family_name
                    and not n.properties.get("listing")]  # fmt: skip
        return self._node(found)


@dataclass
class World:
    """One case's graph, the row keys it keeps, and September's events."""

    graph: LedgerGraph
    keys: KeyStore
    events: list[EventRecord]
    loads: list[str] = field(default_factory=list)

    def copy(self) -> World:
        return copy.deepcopy(self)



async def _owner_reaches(owner: object, dataset_id: str) -> bool:
    """The hotlist's owner still reaches its dataset (ADR-146 Amendment 4 point 7): the storyline's
    owner is the case's own member throughout; the reach itself is proven in
    `test_evaluation_touched_nodes.py` and `test_team_lead_and_watches.py`."""
    return True


async def base_world() -> World:
    """The case as the seed leaves it: September's people, accounts, money and direct writes."""
    graph = LedgerGraph(ONTOLOGY)
    result = await ledger.build_ledger_graph(
        graph=DatasetStampingGraph(graph, dataset=DATASET),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        principal=SEEDER,
        investigation_scope="ledger-base",
    )
    assert result.transactions_loaded == len(ledger.transaction_rows())
    return World(graph, KeyStore(), list(result.events))


def september_for(world: World, case: str) -> list[EventRecord]:
    """September's events in the scene's own case, as the seed loads them into the analytics store."""
    return [e.model_copy(update={"investigation_scope": case}) for e in world.events]


@dataclass
class Stores:
    """The real stores a run writes to, and the stand-ins beside them."""

    hotlists: Any
    alerts: Any
    analytics: Any
    valkey: SignatureSet
    audit: Audit
    principals: dict[str, Principal]

    async def principal_for_owner(self, owner_id: str) -> Principal | None:
        """As `PrincipalResolver.resolve_for_owner` answers: the owner outside any case, reading
        every dataset — the evaluation and the rule gate narrow it to the hotlist's or rule's own."""
        found = self.principals.get(owner_id)
        return found.model_copy(update={"datasets": None}) if found is not None else None


@dataclass
class Loaded:
    report: Any
    rule_notes: list[str]
    hotlist_alerts: list[Any]


async def load_week(
    world: World,
    stores: Stores,
    *,
    case: str,
    rules: Sequence[Any] = (),
    rows: Sequence[dict[str, str]] | None = None,
) -> Loaded:
    """The week's export, as `_execute_recipe_run` runs a published recipe."""
    graph = DatasetStampingGraph(world.graph, dataset=DATASET)
    gate = (
        RuleGate(
            rules=list(rules),
            investigation_id=case,
            graph=graph,  # type: ignore[arg-type]
            analytics=stores.analytics,
            scheme=SCHEME,
            alert_store=stores.alerts,
            audit=stores.audit,  # type: ignore[arg-type]
            valkey=stores.valkey,  # type: ignore[arg-type]
            principal_for_owner=stores.principal_for_owner,
            loader=ENGINEER,
            ontology=ONTOLOGY,
        )
        if rules
        else None
    )
    load_id = f"load-week2-{new_id()}"
    report, events, _held = await load_with_rules(
        RECIPE,
        list(rows if rows is not None else ledger_monitoring.week_rows()),
        ENGINEER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope=case,
        source=ledger_monitoring.WEEK_2,
        media=InMemoryMediaStore(),
        rules=gate,
        scheme=SCHEME,
        sink=Sink(world.keys, case),  # type: ignore[arg-type]
    )
    assert report.rejections == [], report.rejections[:3]
    if events:
        await stores.analytics.load_events(events)
    notes = await post_commit_notes(gate, events, load_id=load_id, sink=None) if gate else []
    entry = ChangeStreamEntry(
        entry_id=new_id(),
        source="ingest",
        node_ids=touched_node_ids(report),
        edge_ids=report.touched_edge_ids,
        investigation_id=case,
        recorded_at=datetime.now(UTC),
    )
    found = await evaluate_hotlists_for_entry(
        entry,
        graph=graph,  # type: ignore[arg-type]
        scheme=SCHEME,
        hotlist_store=stores.hotlists,
        alert_store=stores.alerts,
        audit=stores.audit,  # type: ignore[arg-type]
        valkey=stores.valkey,  # type: ignore[arg-type]
        principal_for_owner=stores.principal_for_owner,
        policy="strict",
        reaches_dataset=_owner_reaches,
    )
    world.loads.append(load_id)
    return Loaded(report, notes, found)
