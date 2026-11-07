"""A screening list's refresh and the re-screening it starts (`spec/06_DECISIONS.md` ADR-133 decision 4,
stage (c)), against the real Postgres store, with the graph a stand-in that reads as the adapters do:
every read through the access predicate and the reader's datasets (rule 3), `list_nodes` paged to a
cursor, and every write recorded through the Conduit's own `DatasetStampingGraph`.

ADR-133's tests, each shown red first:
- a list update adding one entry raises exactly one alert, for the one matching customer, and none
  for an unchanged entry — `test_a_list_update_adding_one_entry_raises_one_alert_for_the_one_matching_customer`;
- the match is written `inferred` — `test_the_match_is_written_inferred_and_belongs_to_the_case`.

And what else a mistake would do:
- a customer the rule's deployer may not read, or outside the case's datasets, alerted on (rules 3
  and 4) — `test_a_customer_the_deployer_may_not_read_is_not_rescreened`;
- a real list loaded without this device's exceptions entry, or a file that only claims to be
  synthetic (rule 9) — `test_a_real_list_without_an_exceptions_entry_is_refused_and_nothing_loads`,
  `test_a_file_that_is_not_one_of_the_repositorys_synthetic_files_is_real`;
- a malformed file replacing the list — `test_a_malformed_file_fails_in_words_and_keeps_the_list`;
- a location outside the ingest folder read — `test_a_location_outside_the_ingest_folder_is_refused`;
- one rule's trouble stopping the others — `test_a_rule_whose_deployer_is_gone_is_said_and_the_rest_run`.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from services.api.alerts import default_severity
from services.api.config import PostgresConfig
from services.api.dataset_scope import DatasetStampingGraph
from services.api.rule_evaluation import handling_readable
from services.api.screening import ScreeningListStore
from services.api.screening_refresh import SYNTHETIC_MANIFEST, Rescreener, refresh, synthetic_digests

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    Alert,
    EdgeWrite,
    Handling,
    KycScreeningParams,
    ListNodesPage,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    TypologyRule,
)
from schemas.screening import ScreeningSubscriptionInput

SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
CASE, DATASET = "case-ledger", "ds-ledger"
OFFICER = Principal(id="kyc-officer", clearance="OFFICIAL", org_unit="verify")
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="verify", roles=["administrator"])
CORE_LISTS = SYNTHETIC_MANIFEST.parent
GOLDEN_LISTS = Path(__file__).resolve().parents[2] / "knowledge_adapters" / "golden" / "screening_lists"


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(classification=classification, handling_code="P", originator="verify", owning_unit="verify")


def _customer(node_id: str, given: str, family: str, *, dob: str = "", marking: str = "OFFICIAL",
              datasets: Sequence[str] = (DATASET,), **props: Any) -> Node:  # fmt: skip
    return Node(
        id=node_id, type="Person",
        properties={"given_names": given, "family_name": family, **({"date_of_birth": dob} if dob else {}), **props},
        provenance=Provenance(state=ProvenanceState.ASSERTED, first_seen=NOW,
                              sources=[SourceRef(document_id="customers.csv", locator="row 1", excerpt_hash="")]),
        handling=_handling(marking), datasets=list(datasets),
        audit={"created_at": NOW, "created_by": "loader", "revision": 1},
    )  # fmt: skip


class _Graph:
    """The reads a re-screening makes, as the ArcadeDB adapter makes them: a node the reader may
    not see, or outside the reader's datasets, is never returned, and never counts toward a page."""

    def __init__(self, nodes: Sequence[Node]) -> None:
        self.nodes = {n.id: n for n in nodes}
        self.written_nodes: list[NodeWrite] = []
        self.written_edges: list[EdgeWrite] = []

    def _sees(self, principal: Principal, node: Node | NodeWrite | EdgeWrite) -> bool:
        reach = principal.datasets
        in_reach = reach is None or bool(set(node.datasets) & set(reach))
        return in_reach and handling_readable(SCHEME, principal, node.handling)

    async def list_nodes(self, entity_type: str, principal: Principal, *, cursor: str | None = None,
                         limit: int = 500) -> ListNodesPage:  # fmt: skip
        ids = sorted(i for i, n in self.nodes.items() if n.type == entity_type and (cursor is None or i > cursor))
        visible = [self.nodes[i] for i in ids if self._sees(principal, self.nodes[i])]
        page = visible[:limit]
        more = len(visible) > limit
        return ListNodesPage(nodes=page, next_cursor=page[-1].id if more and page else None)

    async def find_node(self, entity_type: str, field: str, value: str, principal: Principal) -> Node | None:
        for node in self.nodes.values():
            if node.type == entity_type and node.properties.get(field) == value and self._sees(principal, node):
                return node
        return None

    async def get_node(self, node_id: str, principal: Principal) -> Node | None:
        node = self.nodes.get(node_id)
        return node if node is not None and self._sees(principal, node) else None

    async def get_nodes(self, node_ids: Sequence[str], principal: Principal) -> list[Node]:
        return [n for i in node_ids if (n := await self.get_node(i, principal)) is not None]

    async def get_edges(self, edge_ids: Sequence[str], principal: Principal) -> list[Any]:
        return []

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        return None

    async def rollback_transaction(self, tx: str) -> None:
        return None

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: str) -> list[str]:
        for write in nodes:
            self.written_nodes.append(write)
            self.nodes[write.id] = Node(
                id=write.id, type=write.type, properties=write.properties, provenance=write.provenance,
                handling=write.handling, datasets=write.datasets,
                audit={"created_at": write.created_at, "created_by": write.created_by, "revision": 1},
            )  # fmt: skip
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: str) -> list[str]:
        self.written_edges.extend(edges)
        return [e.id for e in edges]


class _Queue:
    """The alert store, the audit and the signature set: recorders."""

    def __init__(self) -> None:
        self.alerts: list[Alert] = []
        self.audit: list[dict[str, Any]] = []
        self.signatures: set[str] = set()

    async def save(self, alert: Alert, handlings: Any = None) -> None:
        self.alerts.append(alert)

    async def record(self, **entry: Any) -> None:
        self.audit.append(entry)

    async def sismember(self, key: str, value: str) -> int:
        return int(value in self.signatures)

    async def sadd(self, key: str, value: str) -> int:
        self.signatures.add(value)
        return 1


class _Rules:
    def __init__(self, rules: Sequence[TypologyRule]) -> None:
        self.rules = list(rules)

    async def list_active_of_typology(self, typology: str) -> list[TypologyRule]:
        return [r for r in self.rules if r.params.typology == typology and r.status == "active"]


class _Datasets:
    async def ids_of_case(self, investigation_id: str) -> list[str]:
        return [DATASET] if investigation_id == CASE else []

    async def layer_of_case(self, investigation_id: str) -> str | None:
        return None

    async def chosen_of_case(self, investigation_id: str) -> list[object]:
        return []  # a source, never a composite

    async def composites_among(self, dataset_ids: object) -> set[str]:
        return set()


def _rule(rule_id: str = "rule-screen", owner: str = OFFICER.id) -> TypologyRule:
    return TypologyRule(id=rule_id, investigation_id=CASE, owner_id=owner, name="Screening",
                        params=KycScreeningParams(), trigger="post_commit", created_at=NOW)  # fmt: skip


@pytest.fixture
async def store() -> AsyncIterator[ScreeningListStore]:
    dsn = PostgresConfig.from_env().dsn
    made = await ScreeningListStore.connect(dsn)
    conn = await asyncpg.connect(dsn)
    await conn.execute("DELETE FROM screening_list_updates; DELETE FROM screening_lists; "
                       "DELETE FROM screening_entries WHERE list_name LIKE 'Synthetic list%'")  # fmt: skip
    await conn.close()
    yield made
    await made.close()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "ingest"
    (folder / "lists").mkdir(parents=True)
    for name in ("synthetic_opensanctions_v1.ftm.json", "synthetic_opensanctions_v2.ftm.json"):
        shutil.copy(CORE_LISTS / name, folder / "lists" / name)
    return folder


def _rescreener(graph: _Graph, queue: _Queue, rules: Sequence[TypologyRule], *,
                known: Sequence[Principal] = (OFFICER,), page_size: int = 500) -> Rescreener:  # fmt: skip
    people = {p.id: p for p in known}

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return people.get(owner_id)

    return Rescreener(
        rules=_Rules(rules), datasets=_Datasets(), graph=DatasetStampingGraph(graph),  # type: ignore[arg-type]
        scheme=SCHEME, alert_store=queue, audit=queue, valkey=queue,  # type: ignore[arg-type]
        principal_for_owner=principal_for_owner, runner=ADMIN, page_size=page_size,
    )  # fmt: skip


async def _subscribe(store: ScreeningListStore, location: str, **more: Any) -> None:
    await store.subscribe(
        ScreeningSubscriptionInput(list_name="Synthetic list", source="opensanctions", location=location, **more),
        ADMIN.id,
        synthetic=False,
    )


async def _refresh(store: ScreeningListStore, root: Path, rescreen: Any, **more: Any) -> Any:
    return await refresh("Synthetic list", store=store, rescreen=rescreen, root=root, **more)


LEDGER = [
    _customer("p-petrova", "Elena", "Petrova"),
    _customer("p-zelinsky", "Tomas", "Zelinsky", dob="1997-01-30"),
    _customer("p-hale", "Marcus", "Hale", dob="1981-03-07"),
]


# --- ADR-133's own tests ------------------------------------------------------------------------


async def test_a_list_update_adding_one_entry_raises_one_alert_for_the_one_matching_customer(
    store: ScreeningListStore, root: Path
) -> None:
    graph, queue = _Graph(LEDGER), _Queue()
    # Version 1 arrives before any rule screens this case: Elena Petrova is on it and matches a
    # customer, but nothing is watching yet.
    await _subscribe(store, "lists/synthetic_opensanctions_v1.ftm.json")
    first = await _refresh(store, root, _rescreener(graph, queue, []))
    assert (first.outcome, first.added, first.alerts) == ("updated", 10, 0)
    # The case deploys its screening rule; version 2 adds Tomas Zelinsky, changes one entry and
    # removes one. Petrova's entry is unchanged: a re-screening of the whole list would alert on her.
    await _subscribe(store, "lists/synthetic_opensanctions_v2.ftm.json")
    second = await _refresh(store, root, _rescreener(graph, queue, [_rule()]))
    assert (second.outcome, second.added, second.changed, second.delisted) == ("updated", 1, 1, 1)
    (alert,) = queue.alerts
    assert alert.typology == "kyc_screening" and alert.rule_id == "typology:rule-screen"
    assert "p-zelinsky" in alert.referent_node_ids and "p-petrova" not in alert.referent_node_ids
    assert alert.words is not None and "Tomas Zelinsky" in alert.words and "a suggestion to confirm" in alert.words
    assert alert.investigation_id == CASE
    assert default_severity("typology", alert.typology) == "high"  # the queue's screening severity
    assert (second.rescreened, second.alerts) == (3, 1)
    assert second.words.startswith("Version ") and "3 customers re-screened against 2 changed entries; 1 alert raised" in second.words
    (audit,) = [e for e in queue.audit if e["resolved_query"].get("trigger") == "list_update"]
    assert audit["resolved_query"]["findings"] == 1 and audit["principal"] == ADMIN


async def test_the_match_is_written_inferred_and_belongs_to_the_case(
    store: ScreeningListStore, root: Path
) -> None:
    graph, queue = _Graph(LEDGER), _Queue()
    await _subscribe(store, "lists/synthetic_opensanctions_v1.ftm.json")
    await _refresh(store, root, _rescreener(graph, queue, []))
    await _subscribe(store, "lists/synthetic_opensanctions_v2.ftm.json")
    await _refresh(store, root, _rescreener(graph, queue, [_rule()]))
    (same_as,) = [e for e in graph.written_edges if e.type == "SAME_AS"]
    assert same_as.provenance.state is ProvenanceState.INFERRED  # rule 5: a suggestion
    assert same_as.basis == "probabilistic" and same_as.source == "p-zelinsky"
    assert same_as.properties["model_version"] == "screening:Synthetic list"
    listed = next(n for n in graph.written_nodes if n.id == same_as.target)
    assert listed.provenance.state is ProvenanceState.ASSERTED and listed.properties["listing"] == "sanction"
    # Rule 6: nothing merged — the customer is untouched, the listed party a node of its own.
    assert "p-zelinsky" not in {n.id for n in graph.written_nodes}
    # Written outside any request, it still belongs to the case's dataset (ADR-099).
    assert {tuple(w.datasets) for w in [*graph.written_nodes, *graph.written_edges]} == {(DATASET,)}


# --- access control (rules 3 and 4) -------------------------------------------------------------


async def test_a_customer_the_deployer_may_not_read_is_not_rescreened(
    store: ScreeningListStore, root: Path
) -> None:
    hidden = [
        _customer("p-secret", "Tomas", "Zelinsky", dob="1997-01-30", marking="SECRET"),
        _customer("p-elsewhere", "Tomas", "Zelinsky", dob="1997-01-30", datasets=("ds-other",)),
    ]
    graph, queue = _Graph(hidden), _Queue()
    await _subscribe(store, "lists/synthetic_opensanctions_v1.ftm.json")
    await _refresh(store, root, _rescreener(graph, queue, []))
    await _subscribe(store, "lists/synthetic_opensanctions_v2.ftm.json")
    update = await _refresh(store, root, _rescreener(graph, queue, [_rule()]))
    assert queue.alerts == [] and graph.written_edges == []
    # Not even counted: the number re-screened says nothing about who the reader cannot see.
    assert update.rescreened == 0


async def test_every_page_of_customers_is_read(store: ScreeningListStore, root: Path) -> None:
    crowd = [_customer(f"p-{i:03d}", "Someone", f"Else{i}") for i in range(7)]
    graph, queue = _Graph([*crowd, _customer("p-zz", "Tomas", "Zelinsky", dob="1997-01-30")]), _Queue()
    await _subscribe(store, "lists/synthetic_opensanctions_v1.ftm.json")
    await _refresh(store, root, _rescreener(graph, queue, []))
    await _subscribe(store, "lists/synthetic_opensanctions_v2.ftm.json")
    update = await _refresh(store, root, _rescreener(graph, queue, [_rule()], page_size=3))
    assert update.rescreened == 8 and len(queue.alerts) == 1  # the last page's customer too


async def test_a_rule_whose_deployer_is_gone_is_said_and_the_rest_run(
    store: ScreeningListStore, root: Path
) -> None:
    graph, queue = _Graph(LEDGER), _Queue()
    await _subscribe(store, "lists/synthetic_opensanctions_v1.ftm.json")
    await _refresh(store, root, _rescreener(graph, queue, []))
    await _subscribe(store, "lists/synthetic_opensanctions_v2.ftm.json")
    rules = [_rule("rule-orphan", owner="left-the-unit"), _rule()]
    update = await _refresh(store, root, _rescreener(graph, queue, rules))
    assert len(queue.alerts) == 1
    assert "Rule “Screening” could not re-screen: its deployer could not be resolved" in update.words


# --- rule 9 -------------------------------------------------------------------------------------


async def test_a_real_list_without_an_exceptions_entry_is_refused_and_nothing_loads(
    store: ScreeningListStore, root: Path, tmp_path: Path
) -> None:
    real_shaped = root / "lists" / "entities.ftm.json"
    real_shaped.write_text((CORE_LISTS / "synthetic_opensanctions_v1.ftm.json").read_text() + "\n")
    exceptions = tmp_path / "real_data_exceptions.yaml"  # this device admits nothing
    await _subscribe(store, "lists/entities.ftm.json", dataset="opensanctions")
    update = await _refresh(store, root, _rescreener(_Graph(LEDGER), _Queue(), [_rule()]),
                            exceptions_path=exceptions)  # fmt: skip
    assert update.outcome == "refused"
    assert "“opensanctions” is real data and is not in this device's real_data_exceptions.yaml" in update.words
    status = await store.subscription("Synthetic list")
    assert status is not None and status.version is None and status.entries == 0
    assert status.failure == update.words
    assert not [e for e in await store.entries("Person") if e.list_name == "Synthetic list"]
    # With the device's own entry, a real list of a connector whose licence is confirmed loads, as
    # real data. (OpenSanctions' is not: `test_a_real_list_whose_licence_is_not_confirmed_...`.)
    _admit(exceptions, "ofac_sdn")
    for name in ("SDN.CSV", "ALT.CSV", "ADD.CSV"):
        shutil.copy(GOLDEN_LISTS / f"ofac_sdn.{name}", root / "lists" / name)
    await store.subscribe(
        ScreeningSubscriptionInput(list_name="Synthetic list OFAC", source="ofac_sdn",
                                   location="lists/SDN.CSV", dataset="ofac_sdn"),
        ADMIN.id, synthetic=False,
    )  # fmt: skip
    admitted = await refresh("Synthetic list OFAC", store=store, root=root,
                             rescreen=_rescreener(_Graph(LEDGER), _Queue(), []),
                             exceptions_path=exceptions)  # fmt: skip
    status = await store.subscription("Synthetic list OFAC")
    assert admitted.outcome == "updated", admitted.words
    assert status is not None and status.synthetic is False


def _admit(exceptions: Path, dataset: str) -> None:
    exceptions.write_text(
        f"exceptions:\n  - dataset: {dataset}\n    approved_uses: [local_development]\n"
        "    added_by: owner\n    added_date: '2026-11-01'\n    device: test-device\n"
        "    justification: a test of the gate\n    decision_record: ADR-133\n"
    )


async def test_a_real_list_whose_licence_is_not_confirmed_is_refused_even_with_an_exceptions_entry(
    store: ScreeningListStore, root: Path, tmp_path: Path
) -> None:
    """The owner's answer of 1 November 2026 (ADR-133 Amendment 3's licence findings): UN and
    OpenSanctions are synthetic-only until their licences are confirmed. A real OpenSanctions file
    the device's exceptions admit is still refused, in words that say why, and nothing loads."""
    real_shaped = root / "lists" / "entities.ftm.json"
    real_shaped.write_text((CORE_LISTS / "synthetic_opensanctions_v1.ftm.json").read_text() + "\n")
    exceptions = tmp_path / "real_data_exceptions.yaml"
    _admit(exceptions, "opensanctions")
    await _subscribe(store, "lists/entities.ftm.json", dataset="opensanctions")
    update = await _refresh(store, root, _rescreener(_Graph(LEDGER), _Queue(), [_rule()]),
                            exceptions_path=exceptions)  # fmt: skip
    assert update.outcome == "refused", update.words
    assert "licence is not confirmed" in update.words and "commercial" in update.words
    assert "only OspreyFlow's synthetic" in update.words
    status = await store.subscription("Synthetic list")
    assert status is not None and status.entries == 0
    # Its own synthetic list still loads.
    await _subscribe(store, "lists/synthetic_opensanctions_v1.ftm.json")
    synthetic = await _refresh(store, root, _rescreener(_Graph(LEDGER), _Queue(), []),
                               exceptions_path=exceptions)  # fmt: skip
    assert synthetic.outcome == "updated"


async def test_a_file_that_is_not_one_of_the_repositorys_synthetic_files_is_real(
    store: ScreeningListStore, root: Path, tmp_path: Path
) -> None:
    # Says it is synthetic about itself, and names no dataset: not trusted.
    claimed = root / "lists" / "claims_synthetic.ftm.json"
    claimed.write_text('{"id": "x", "schema": "Person", "properties": {"name": ["Anyone"], '
                       '"topics": ["sanction"], "notes": ["synthetic: true"]}}\n')  # fmt: skip
    await _subscribe(store, "lists/claims_synthetic.ftm.json")
    update = await _refresh(store, root, _rescreener(_Graph(LEDGER), _Queue(), []),
                            exceptions_path=tmp_path / "none.yaml")  # fmt: skip
    assert update.outcome == "refused" and "must name its dataset" in update.words


def test_every_synthetic_list_file_is_in_the_manifest_by_its_digest() -> None:
    files = sorted(p for p in CORE_LISTS.iterdir() if p.suffix in (".json", ".xml"))
    assert {p.suffix for p in files} == {".json", ".xml"}
    digests = synthetic_digests()
    for path in files:
        assert hashlib.sha256(path.read_bytes()).hexdigest() in digests, path.name


# --- what a refresh refuses or fails, in words --------------------------------------------------


async def test_a_malformed_file_fails_in_words_and_keeps_the_list(
    store: ScreeningListStore, root: Path, tmp_path: Path
) -> None:
    await _subscribe(store, "lists/synthetic_opensanctions_v1.ftm.json")
    await _refresh(store, root, _rescreener(_Graph(LEDGER), _Queue(), []))
    # The CSV export handed to the JSON connector, as an operator might.
    (root / "lists" / "targets.simple.csv").write_text("id,schema,name\nsyn-001,Person,Elena Petrova\n")
    manifest = tmp_path / "manifest"
    digest = hashlib.sha256((root / "lists" / "targets.simple.csv").read_bytes()).hexdigest()
    manifest.write_text(f"{digest}  targets.simple.csv\n")
    await _subscribe(store, "lists/targets.simple.csv")
    update = await _refresh(store, root, _rescreener(_Graph(LEDGER), _Queue(), []), manifest=manifest)
    assert update.outcome == "failed"
    assert update.words.startswith("The file could not be read as opensanctions: line 1 is not a JSON object")
    status = await store.subscription("Synthetic list")
    assert status is not None and status.entries == 10 and status.failure == update.words


async def test_a_location_outside_the_ingest_folder_is_refused(
    store: ScreeningListStore, root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.ftm.json"
    shutil.copy(CORE_LISTS / "synthetic_opensanctions_v1.ftm.json", outside)
    (root / "lists" / "link.ftm.json").symlink_to(outside)
    for location in ("../outside.ftm.json", "lists/link.ftm.json"):
        await _subscribe(store, location)
        update = await _refresh(store, root, _rescreener(_Graph(LEDGER), _Queue(), []))
        assert (update.outcome, update.words) == (
            "refused", "Refused: the list's location is outside the ingest folder; nothing was read.")


async def test_the_same_version_again_rescreens_no_one(store: ScreeningListStore, root: Path) -> None:
    graph, queue = _Graph(LEDGER), _Queue()
    await _subscribe(store, "lists/synthetic_opensanctions_v1.ftm.json")
    await _refresh(store, root, _rescreener(graph, queue, []))
    again = await _refresh(store, root, _rescreener(graph, queue, [_rule()]))
    assert again.outcome == "unchanged" and again.rescreened == 0 and queue.alerts == []


async def test_a_listed_party_already_in_the_graph_is_not_screened_as_a_customer(
    store: ScreeningListStore, root: Path
) -> None:
    # A listed party a past match wrote carries its listing; it is the list's entry, not a customer.
    listed = _customer("p-listed", "Tomas", "Zelinsky", dob="1997-01-30", listing="sanction",
                       list_name="Synthetic list")  # fmt: skip
    graph, queue = _Graph([listed]), _Queue()
    await _subscribe(store, "lists/synthetic_opensanctions_v1.ftm.json")
    await _refresh(store, root, _rescreener(graph, queue, []))
    await _subscribe(store, "lists/synthetic_opensanctions_v2.ftm.json")
    update = await _refresh(store, root, _rescreener(graph, queue, [_rule()]))
    assert queue.alerts == [] and update.rescreened == 0
