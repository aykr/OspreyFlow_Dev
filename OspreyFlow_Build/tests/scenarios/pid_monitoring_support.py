"""What the monitoring storyline's tests share (`spec/06_DECISIONS.md` ADR-127 Amendment 41): the PID
files the chapter-9 alerts rest on, loaded through the committed recipes, and each chapter-9 load
run the way the run route runs it. Not a test module.

**The loads are the engine's own.** Every file is loaded by `studio_publish.load_with_rules` through
its committed recipe (as the golden tests load them), behind the real `DatasetStampingGraph`, so
every element is stamped `prison-intelligence` as the seed's are. After each chapter-9 load, as
`recipe_run._execute_recipe_run` does: the case's rules after commit (`post_commit_notes`, the
`RuleGate`'s own), then a change-stream entry of the run's touched nodes (`touched_node_ids`) and
the hotlists evaluated over it (`evaluation.evaluate_hotlists_for_entry`, the function the route
calls).

**The graph answers as the adapter does (rule 15).** `AccessGraph` is the golden tests'
`MergingGraph` (the store's own link merge) answering every read with whole `Node`s and `Edge`s,
each judged as the reader by the scheme's own predicate (`rule_evaluation.handling_readable`, the
adapters' access step in Python) and by the reader's datasets (ADR-099: an element outside them is
not in the reader's world). A node the reader may not see is absent from the answer, never an error,
and a link is seen only with both its ends. `expand` walks only what the reader sees. A write a
reader could not have made (an undeclared type, a missing end) is refused by `MergingGraph`'s own
validation. What it does not model: the store's indexes and its timing.

**The rest is real** where it can be: the alert, hotlist and (for P4) close paths run against a
throwaway Postgres; alert facts go to an in-memory DuckDB through the adapter's own
`load_alert_facts`. The Valkey the evaluation locks and the rule gate's signature set use is
`SignatureSet` below: a set and a lock that always acquires (no other evaluation runs), as the
gate's tests use.

**The slice.** The whole call file is 100,000 rows; the stand-in's linear scans would take minutes.
`BASE_STEPS` loads the estate, the prisoners, the visits, the number owners, the first seized-phone
batch whole, and the call file's rows on every account and every number the chapter-9 batches name
(plus the coordinator's and the number nobody owns), whole: every path within two links of any of
those numbers is present, so the P1 rule meets what it would in the whole case.
"""

from __future__ import annotations

import copy
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.api.change_stream import ChangeStreamEntry, touched_node_ids
from services.api.dataset_scope import DatasetStampingGraph
from services.api.evaluation import evaluate_hotlists_for_entry
from services.api.rule_evaluation import RuleGate, handling_readable
from services.api.studio_publish import load_with_rules, post_commit_notes
from services.ingest import staging
from tests.ingest import pid_golden_support as golden
from tests.ingest.recipe_test_support import LocalStore, MergingGraph
from tests.ingest.test_row_keys import KeyStore, Sink

from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from demo_fixtures import pid_files, pid_monitoring
from knowledge_adapters import REGISTRY
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    ExpandRequest,
    Node,
    NodeWrite,
    Principal,
    Subgraph,
)

DATASET = "prison-intelligence"
CASE = golden.CASE
SCHEME = golden.SCHEME
ONTOLOGY = golden.ONTOLOGY
#: The demo data engineer, as the seed scopes him: the dataset's loader.
ENGINEER = golden.LOADER.model_copy(update={"datasets": [DATASET]})


class AccessGraph(MergingGraph):
    """See the module docstring."""

    def _sees(self, principal: Principal, handling: Any, datasets: Sequence[str]) -> bool:
        if not handling_readable(SCHEME, principal, handling):
            return False
        return principal.datasets is None or bool(set(datasets) & set(principal.datasets))

    def _live_nodes(self) -> dict[str, NodeWrite]:
        return {
            i: n for i, n in self.nodes.items() if i not in self.reverted and i not in self.superseded
        }

    def _visible_nodes(self, principal: Principal) -> dict[str, NodeWrite]:
        return {
            i: n for i, n in self._live_nodes().items() if self._sees(principal, n.handling, n.datasets)
        }

    def _visible_edges(self, principal: Principal) -> list[EdgeWrite]:
        seen = self._visible_nodes(principal)
        return [
            e
            for e in self.committed_edges
            if e.id not in self.reverted
            and e.id not in self.superseded
            and e.source in seen
            and e.target in seen
            and self._sees(principal, e.handling, e.datasets)
        ]

    @staticmethod
    def _node(write: NodeWrite) -> Node:
        return Node(
            id=write.id,
            type=write.type,
            properties=write.properties,
            provenance=write.provenance,
            handling=write.handling,
            audit=AuditStub(created_at=write.created_at, created_by=write.created_by, revision=0),
            datasets=write.datasets,
        )

    @staticmethod
    def _edge(write: EdgeWrite) -> Edge:
        return Edge(
            id=write.id,
            type=write.type,
            source=write.source,
            target=write.target,
            properties=write.properties,
            interval=write.interval,
            occurrences=write.occurrences,
            basis=write.basis,
            provenance=write.provenance,
            handling=write.handling,
            audit=AuditStub(created_at=write.created_at, created_by=write.created_by, revision=0),
            datasets=write.datasets,
        )

    async def get_nodes(self, node_ids: Sequence[str], principal: Any) -> list[Any]:
        seen = self._visible_nodes(principal)
        return [self._node(seen[i]) for i in dict.fromkeys(node_ids) if i in seen]

    async def get_node(self, node_id: str, principal: Any, **kwargs: Any) -> Node | None:
        if kwargs.get("include_superseded"):
            return None  # nothing here is superseded by the system
        found = await self.get_nodes([node_id], principal)
        return found[0] if found else None

    async def get_edges(self, edge_ids: Sequence[str], principal: Any) -> list[Any]:
        wanted = set(edge_ids)
        return [self._edge(e) for e in self._visible_edges(principal) if e.id in wanted]

    async def edges_among(self, node_ids: Sequence[str], principal: Any, **_: Any) -> list[Edge]:
        ids = set(node_ids)
        return [
            self._edge(e)
            for e in self._visible_edges(principal)
            if e.source in ids and e.target in ids
        ]

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        seen = self._visible_nodes(principal)
        links = self._visible_edges(principal)
        reached = {i for i in req.node_ids if i in seen}
        frontier, used = set(reached), set()
        for _ in range(req.depth):
            nxt: set[str] = set()
            for edge in links:
                if req.edge_types and edge.type not in req.edge_types:
                    continue
                for a, b in ((edge.source, edge.target), (edge.target, edge.source)):
                    if a in frontier and b not in reached:
                        nxt.add(b)
                        used.add(edge.id)
            reached |= nxt
            frontier = nxt
        return Subgraph(
            nodes=[self._node(seen[i]) for i in sorted(reached)],
            edges=[self._edge(e) for e in links if e.id in used],
        )

    def node_by_value(self, value: str) -> NodeWrite:
        """The one live node holding this `value_normalised` (an outside number, a PIN account)."""
        (found,) = [
            n for n in self._live_nodes().values() if n.properties.get("value_normalised") == value
        ]
        return found


class SignatureSet:
    """The Valkey a run's watches and rules touch: the rule gate's signature set (`sismember`,
    `sadd`) and the evaluation's overlap lock, which always acquires (nothing else evaluates)."""

    def __init__(self) -> None:
        self.members: dict[str, set[str]] = {}

    async def sismember(self, key: str, value: str) -> int:
        return int(value in self.members.get(key, set()))

    async def sadd(self, key: str, value: str) -> int:
        self.members.setdefault(key, set()).add(value)
        return 1

    def lock(self, key: str, **_: Any) -> Any:
        class _Lock:
            async def acquire(self) -> bool:
                return True

            async def release(self) -> None:
                return None

        return _Lock()


class Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **entry: Any) -> None:
        self.entries.append(entry)


@contextmanager
def local_staging() -> Iterator[None]:
    """The engine stages raw rows in the object store; here, in a scratch folder, as the golden
    tests' `local_staging` fixture does (that one is per test; this one spans a module's world)."""
    before = staging.filesystem
    with tempfile.TemporaryDirectory(prefix="pid-monitoring-") as root:
        staging.filesystem = lambda config: LocalStore(Path(root))  # type: ignore[assignment]
        try:
            yield
        finally:
            staging.filesystem = before  # type: ignore[assignment]


def msisdn(raw: str) -> str:
    return str(REGISTRY["msisdn"](raw))


# --- The slice the chapter-9 alerts rest on ----------------------------------------------------


def _named_by_the_batches() -> tuple[set[str], set[str]]:
    """The PIN accounts and the numbers (normalised) the two monitoring batches name, with the
    coordinator's and the unidentified number."""
    plan = golden.PLAN
    accounts = {r["pin_account"] for r in pid_monitoring.new_contact_rows(plan)}
    numbers = {msisdn(r["called_number"]) for r in pid_monitoring.new_contact_rows(plan)}
    numbers |= {msisdn(r["contact_number"]) for r in pid_monitoring.booking_rows(plan)}
    numbers |= {"+447700900640", "+447700900718"}
    return accounts, numbers


def _calls_slice() -> golden.Step:
    accounts, numbers = _named_by_the_batches()
    rows = tuple(
        r
        for r in golden.rows_of(golden.CALLS)
        if r["pin_account"] in accounts or msisdn(r["called_number"]) in numbers
    )
    wanted = {(r["pin_account"], msisdn(r["called_number"])) for r in rows}
    return golden.Step(
        golden.CALLS,
        rows,
        lambda row: (row.values["pin_account"], msisdn(row.values["called_number"])) in wanted,
    )


#: Before chapter 9, in the seed's order (`pid_files.SEED_ORDER`), the files the alerts rest on.
BASE_FILES = (
    "pid_establishment_plan.csv",
    "pid_nomis_prisoners.csv",
    "pid_nomis_visits.csv",
    "pid_number_owners.csv",
)


@dataclass
class World:
    """One case's graph and the row keys it keeps, before or after a chapter-9 load."""

    graph: AccessGraph
    keys: KeyStore
    loads: list[str] = field(default_factory=list)

    def copy(self) -> World:
        return copy.deepcopy(self)


async def _load_base(world: World, file: str, rows: Sequence[dict[str, str]] | None = None) -> None:
    report, _events, _held = await load_with_rules(
        golden.recipe_for(file),
        list(rows if rows is not None else golden.rows_of(file)),
        ENGINEER,
        graph=DatasetStampingGraph(world.graph, dataset=DATASET),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=f"load-{file}",
        investigation_scope=CASE,
        source=file,
        media=InMemoryMediaStore(),
        scheme=SCHEME,
        sink=Sink(world.keys, CASE),  # type: ignore[arg-type]
    )
    assert report.rejections == [], (file, report.rejections[:3])
    world.loads.append(file)


async def base_world() -> World:
    """The case up to the end of the seed's own loads that chapter 9's alerts rest on."""
    world = World(AccessGraph(ONTOLOGY), KeyStore())
    for file in BASE_FILES:
        await _load_base(world, file)
    await _load_base(world, golden.CALLS, _calls_slice().rows)
    await _load_base(world, pid_files.BATCH_1)
    return world


# --- A chapter-9 load, as the run route runs it -----------------------------------------------


@dataclass
class Stores:
    """The real stores a chapter-9 run writes to, and the stand-ins beside them."""

    hotlists: Any
    alerts: Any
    valkey: SignatureSet
    audit: Audit
    principals: dict[str, Principal]

    async def principal_for_owner(self, owner_id: str) -> Principal | None:
        """As `PrincipalResolver.resolve_for_owner` answers (Token Exchange, ADR-043): the owner
        as the identity provider describes them, outside any case, so reading every dataset — the
        evaluation and the rule gate narrow it to the hotlist's or the rule's own."""
        found = self.principals.get(owner_id)
        return found.model_copy(update={"datasets": None}) if found is not None else None


@dataclass
class Loaded:
    file: str
    report: Any
    hotlist_alerts: list[Any]
    rule_notes: list[str]


async def run_chapter_9_file(
    world: World,
    file: str,
    stores: Stores,
    *,
    case: str = CASE,
    rules: Sequence[Any] = (),
    patterns: Any = None,
    load_id: str | None = None,
) -> Loaded:
    """One chapter-9 file, as `_execute_recipe_run` runs it: its recipe through the engine with the
    case's rules, the rules after commit, then the change stream's touched nodes to every active
    hotlist."""
    graph = DatasetStampingGraph(world.graph, dataset=DATASET)
    gate = (
        RuleGate(
            rules=list(rules),
            investigation_id=case,
            graph=graph,  # type: ignore[arg-type]
            analytics=None,
            scheme=SCHEME,
            alert_store=stores.alerts,
            audit=stores.audit,  # type: ignore[arg-type]
            valkey=stores.valkey,  # type: ignore[arg-type]
            principal_for_owner=stores.principal_for_owner,
            loader=ENGINEER,
            patterns=patterns,
            ontology=ONTOLOGY,
        )
        if rules
        else None
    )
    load = load_id or f"load-{file}-{new_id()}"
    report, events, _held = await load_with_rules(
        golden.recipe_for(file),
        list(golden.rows_of(file)),
        ENGINEER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load,
        investigation_scope=case,
        source=file,
        media=InMemoryMediaStore(),
        rules=gate,
        scheme=SCHEME,
        sink=Sink(world.keys, case),  # type: ignore[arg-type]
    )
    assert report.rejections == [], (file, report.rejections[:3])
    notes = await post_commit_notes(gate, events, load_id=load, sink=None) if gate else []
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
    )
    world.loads.append(file)
    return Loaded(file, report, found, notes)
