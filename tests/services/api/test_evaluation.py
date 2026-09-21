"""`services/api/evaluation.py` — `06_DECISIONS.md` ADR-037/038, Phase 7 Stage 6b. Real Postgres
(hotlist/monitor/alert/audit stores), real ArcadeDB (the match itself, one freshly-created and
dropped database per `arcadedb_adapter` block — `packages/adapters/graph_arcadedb/testing.py`'s
own isolation guarantee, which is what makes the monitor dedup test below safe against whatever
else the wider suite has written) and real Valkey (the overlap guard, the dedup signature) — the
same "own its access-control and bounds proof rather than only through a fake" discipline
`test_alerts.py`/`test_change_stream.py` already establish.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from services.api.alerts import AlertStore
from services.api.audit import AuditWriter
from services.api.change_stream import ChangeStreamEntry
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.evaluation import (
    _HOTLIST_LOCK_PREFIX,
    LOCK_TTL_SECONDS,
    evaluate_hotlists_for_entry,
    evaluate_monitors_for_entry,
)
from services.api.hotlists import HotlistStore
from services.api.monitors import MonitorStore
from services.api.pattern_store import PatternStore
from services.resolve.trigger import service_principal
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.graph import GraphPort
from schemas.domain import (
    EdgeWrite,
    Handling,
    NodeWrite,
    PatternEdge,
    PatternNode,
    PatternQuery,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

OWNER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OTHER_ANALYST = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")


def _principal_for(owner_id: str) -> Principal | None:
    """The caller-supplied stand-in `evaluation.py`'s own docstring calls for — no principal
    directory exists anywhere in this codebase, so a test (like a future scheduled consumer) must
    supply its own resolution."""
    return {OWNER.id: OWNER, OTHER_ANALYST.id: OTHER_ANALYST}.get(owner_id)


def _endpoint_write(
    value_normalised: str, *, owning_unit: str, classification: str = "OFFICIAL"
) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Endpoint",
        properties={"value_normalised": value_normalised},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by="test",
        created_at=now,
    )


def _person_write(
    family_name: str, *, owning_unit: str, classification: str = "OFFICIAL"
) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={
            "family_name": family_name,
            "given_names": "Test",
            "date_of_birth": "1990-01-01",
        },
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by="test",
        created_at=now,
    )


def _uses_edge(
    source: str, target: str, *, owning_unit: str, classification: str = "OFFICIAL"
) -> EdgeWrite:
    now = datetime.now(UTC)
    return EdgeWrite(
        id=new_id(),
        type="USES",
        source=source,
        target=target,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by="test",
        created_at=now,
    )


def _pattern() -> PatternQuery:
    return PatternQuery(
        nodes=[
            PatternNode(var="p", entity_type="Person"),
            PatternNode(var="e", entity_type="Endpoint"),
        ],
        edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
    )


def _entry(node_ids: list[str]) -> ChangeStreamEntry:
    return ChangeStreamEntry(
        entry_id=new_id(),
        source="ingest",
        node_ids=node_ids,
        edge_ids=[],
        recorded_at=datetime.now(UTC),
    )


@pytest.fixture
async def valkey() -> Valkey:
    cfg = ValkeyConfig.from_env()
    client = Valkey(host=cfg.host, port=cfg.port, db=cfg.db)
    yield client
    await client.aclose()


@pytest.fixture
async def alert_store():
    s = await AlertStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


@pytest.fixture
async def audit():
    w = await AuditWriter.connect(PostgresConfig.from_env().dsn)
    yield w
    await w.close()


@pytest.fixture
async def hotlist_store():
    s = await HotlistStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


@pytest.fixture
async def monitor_store():
    s = await MonitorStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


@pytest.fixture
async def pattern_store():
    s = await PatternStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


# --- evaluate_hotlists_for_entry -----------------------------------------------------------


async def test_a_hotlist_match_visible_to_its_owner_writes_a_full_alert(
    hotlist_store, alert_store, audit, valkey
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    identifier = f"+44-hotlist-{uuid.uuid4().hex[:10]}"
    hotlist = await hotlist_store.create(OWNER, identifier=identifier, review_date=date(2027, 1, 1))

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_endpoint_write(identifier, owning_unit=OWNER.org_unit)], tx
        )
        await graph.commit_transaction(tx)

        alerts = await evaluate_hotlists_for_entry(
            _entry([node_id]),
            graph=graph,
            scheme=scheme,
            hotlist_store=hotlist_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for,
            policy="strict",
        )
        matching = [a for a in alerts if a.rule_id == f"hotlist:{hotlist.id}"]
        assert len(matching) == 1
        assert matching[0].mode.value == "full"
        assert matching[0].referent_node_ids == [node_id]


async def test_a_hotlist_match_outside_the_owners_access_leaks_nothing_in_strict_or_notify(
    hotlist_store, alert_store, audit, valkey
) -> None:
    """The named test the Stage 6b task itself calls for. **Renamed from the original
    `..._produces_nothing_in_strict_and_notify`**: that name read as "nothing is produced in
    either mode," which is false and would mislead a future reader into thinking notify mode
    suppresses the alert row the same way strict does — it does not (ADR-038's own point of
    having two modes at all). What this test actually asserts, checked line by line below: under
    `policy="strict"` nothing is produced at all (no alert row, matching `test_alerts.py`'s own
    `test_a_suppressed_strict_match_writes_no_alert_row`); under `policy="notify"` one alert *is*
    produced, but it leaks nothing — `referent_node_ids == []` and neither the node id nor the
    matched identifier appear anywhere in the serialised alert, mirroring `test_alerts.py`'s own
    `test_notify_mode_alert_contains_no_referent_its_recipient_cannot_read`. A hotlist match the
    evaluator's own unscoped `service_principal` read can see, but the hotlist's own owner cannot
    (a different `owning_unit`, a `classification` above `OWNER`'s own clearance) — exercised
    through the evaluator's own hotlist-matching path, not `record_match` directly."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    identifier = f"+44-hotlist-hidden-{uuid.uuid4().hex[:10]}"
    hotlist = await hotlist_store.create(OWNER, identifier=identifier, review_date=date(2027, 1, 1))

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_endpoint_write(identifier, owning_unit="unit-2", classification="SECRET")], tx
        )
        await graph.commit_transaction(tx)

        strict_alerts = await evaluate_hotlists_for_entry(
            _entry([node_id]),
            graph=graph,
            scheme=scheme,
            hotlist_store=hotlist_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for,
            policy="strict",
        )
        assert [a for a in strict_alerts if a.rule_id == f"hotlist:{hotlist.id}"] == []

        notify_alerts = await evaluate_hotlists_for_entry(
            _entry([node_id]),
            graph=graph,
            scheme=scheme,
            hotlist_store=hotlist_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for,
            policy="notify",
        )
        matching = [a for a in notify_alerts if a.rule_id == f"hotlist:{hotlist.id}"]
        assert len(matching) == 1
        serialised = matching[0].model_dump(mode="json")
        assert serialised["referent_node_ids"] == []
        assert node_id not in str(serialised)
        assert identifier not in str(serialised)


async def test_a_hotlist_with_no_resolvable_owner_principal_is_skipped_not_run_as_a_stale_one(
    hotlist_store, alert_store, audit, valkey
) -> None:
    """`06_DECISIONS.md` ADR-036's "the monitor stops" extended to a hotlist owner:
    `principal_for_owner` returning `None` must skip that hotlist's evaluation entirely, not fall
    back to a cached or synthetic principal."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    identifier = f"+44-hotlist-orphan-{uuid.uuid4().hex[:10]}"
    orphan_owner_id = f"no-such-analyst-{uuid.uuid4().hex[:8]}"
    # Build the row directly against a principal not present in `_principal_for`'s own map.
    unresolvable_owner = Principal(id=orphan_owner_id, clearance="OFFICIAL", org_unit="unit-1")
    hotlist = await hotlist_store.create(
        unresolvable_owner, identifier=identifier, review_date=date(2027, 1, 1)
    )

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_endpoint_write(identifier, owning_unit=unresolvable_owner.org_unit)], tx
        )
        await graph.commit_transaction(tx)

        alerts = await evaluate_hotlists_for_entry(
            _entry([node_id]),
            graph=graph,
            scheme=scheme,
            hotlist_store=hotlist_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for,
            policy="strict",
        )
        assert [a for a in alerts if a.rule_id == f"hotlist:{hotlist.id}"] == []


async def test_a_skipped_hotlist_evaluation_is_observable_as_stopped_and_a_later_success_clears_it(
    hotlist_store, alert_store, audit, valkey
) -> None:
    """Stage 6c's own addendum: the test above proves the skip *happens*; this one proves it is
    not silent — `06_DECISIONS.md` ADR-036's own "the monitor stops" requirement, extended to
    hotlists, means the owner (or another reader of the list) must be able to see it, not just
    trust that no alert firing means everything is fine. Written to `hotlist.status`, checked by
    re-reading the row through the store's own `get_authorized`, not inferred from the evaluator's
    return value. The second half proves it is not a one-way trip: the next attempt that *does*
    resolve a principal flips it back to `active`, matching this stage's own synchronous-evaluation
    design, where most reaches for someone else's hotlist are ordinary, expected skips, not a
    terminal failure state."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    identifier = f"+44-hotlist-status-{uuid.uuid4().hex[:10]}"
    hotlist = await hotlist_store.create(OWNER, identifier=identifier, review_date=date(2027, 1, 1))
    assert hotlist.status == "active"

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_endpoint_write(identifier, owning_unit=OWNER.org_unit)], tx
        )
        await graph.commit_transaction(tx)

        await evaluate_hotlists_for_entry(
            _entry([node_id]),
            graph=graph,
            scheme=scheme,
            hotlist_store=hotlist_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=lambda owner_id: None,  # every owner unresolvable, this one too
            policy="strict",
        )
        stopped = await hotlist_store.get_authorized(hotlist.id, OWNER)
        assert stopped.status == "stopped"

        await evaluate_hotlists_for_entry(
            _entry([node_id]),
            graph=graph,
            scheme=scheme,
            hotlist_store=hotlist_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for,  # resolves OWNER again
            policy="strict",
        )
        active_again = await hotlist_store.get_authorized(hotlist.id, OWNER)
        assert active_again.status == "active"


async def test_a_hotlist_evaluation_already_in_progress_is_skipped_not_queued(
    hotlist_store, alert_store, audit, valkey
) -> None:
    """ADR-037's overrun bound: a concurrent trigger for the same hotlist skips rather than
    queues behind one already running. Proven by holding the evaluator's own overlap-guard lock
    externally (the identical key `_with_overlap_guard` computes) before calling the evaluator,
    then releasing it and calling again."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    identifier = f"+44-hotlist-lock-{uuid.uuid4().hex[:10]}"
    hotlist = await hotlist_store.create(OWNER, identifier=identifier, review_date=date(2027, 1, 1))

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_endpoint_write(identifier, owning_unit=OWNER.org_unit)], tx
        )
        await graph.commit_transaction(tx)

        lock = valkey.lock(
            f"{_HOTLIST_LOCK_PREFIX}{hotlist.id}", timeout=LOCK_TTL_SECONDS, blocking=False
        )
        assert await lock.acquire()
        try:
            during = await evaluate_hotlists_for_entry(
                _entry([node_id]),
                graph=graph,
                scheme=scheme,
                hotlist_store=hotlist_store,
                alert_store=alert_store,
                audit=audit,
                valkey=valkey,
                principal_for_owner=_principal_for,
                policy="strict",
            )
            assert [a for a in during if a.rule_id == f"hotlist:{hotlist.id}"] == []
        finally:
            await lock.release()

        after = await evaluate_hotlists_for_entry(
            _entry([node_id]),
            graph=graph,
            scheme=scheme,
            hotlist_store=hotlist_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for,
            policy="strict",
        )
        matching = [a for a in after if a.rule_id == f"hotlist:{hotlist.id}"]
        assert len(matching) == 1


# --- evaluate_monitors_for_entry -----------------------------------------------------------


async def test_a_monitor_alert_is_always_visible_since_the_match_is_already_owner_filtered(
    monitor_store, pattern_store, alert_store, audit, valkey
) -> None:
    """`evaluation.py`'s own claim about monitors — there is no out-of-access case for a monitor
    alert, since `GraphPort.match` is already principal-filtered by the owner's own principal —
    checked directly rather than only asserted in the module docstring."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    saved = await pattern_store.save(
        OWNER, pattern_id=None, name="Evaluator fixture visible", definition=_pattern()
    )
    monitor = await monitor_store.create(OWNER, pattern_id=saved.pattern_id)

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (person_id, endpoint_id) = await graph.upsert_nodes(
            [
                _person_write("Monitorfixture", owning_unit=OWNER.org_unit),
                _endpoint_write(f"+44-{uuid.uuid4().hex[:8]}", owning_unit=OWNER.org_unit),
            ],
            tx,
        )
        await graph.commit_transaction(tx)
        tx = await graph.begin_transaction()
        await graph.upsert_edges(
            [_uses_edge(person_id, endpoint_id, owning_unit=OWNER.org_unit)], tx
        )
        await graph.commit_transaction(tx)

        alerts = await evaluate_monitors_for_entry(
            _entry([]),
            graph=graph,
            monitor_store=monitor_store,
            pattern_store=pattern_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for,
        )
        matching = [a for a in alerts if a.rule_id == f"monitor:{monitor.id}"]
        assert len(matching) == 1
        assert matching[0].mode.value == "full"
        assert set(matching[0].referent_node_ids) >= {person_id, endpoint_id}


class _PrincipalRecordingGraph:
    """Wraps a real `GraphPort` adapter, delegating every call unchanged except `match`, whose
    `principal` argument it records before delegating on. This is the only reliable way to pin
    which principal `evaluate_monitors_for_entry` actually used: asserting on the *alert outcome*
    alone cannot distinguish "never used a broader principal" from "used one, but `alerts.py`'s
    own independent per-referent recheck in `record_match` (`graph.get_node(node_id, recipient)`,
    always against the true recipient) suppressed the leak anyway" — checked directly while
    designing this test, not assumed: substituting a broader principal into the `graph.match` call
    still produced zero alerts, because that second, independent check catches it too. Real
    defense in depth, but it means a leak-outcome-only test would pass unchanged even if this
    function started matching under the wrong principal — silently exercising the "match found
    under a broader principal, then suppressed" path this module's own docstring says does not
    exist for a monitor at all, rather than the "no broader principal, nothing to suppress" path
    it claims to be on. This wrapper observes the actual argument, not a downstream proxy for it."""

    def __init__(self, real: GraphPort) -> None:
        self._real = real
        self.match_principals: list[Principal] = []

    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph:
        self.match_principals.append(principal)
        return await self._real.match(pattern, principal)

    def __getattr__(self, name: str):  # noqa: ANN001, ANN204 - delegating proxy
        return getattr(self._real, name)


async def test_a_monitor_never_evaluates_with_a_principal_broader_than_its_owner(
    monitor_store, pattern_store, alert_store, audit, valkey
) -> None:
    """Pins an invariant of today's code as a test, not left as a property that happens to hold:
    `evaluate_monitors_for_entry`'s own docstring says a monitor alert is always visible because
    `GraphPort.match` is always run as the owner's own principal — that is true only as long as
    nothing inside this function ever substitutes a broader one in. `service_principal` (the same
    corpus-wide, all-seeing identity `evaluate_hotlists_for_entry` deliberately *does* use,
    `06_DECISIONS.md` ADR-038's own addendum) is exactly the "obvious future efficiency" a later
    change might reach for — matching once against the broadest principal rather than once per
    monitor owner. `_PrincipalRecordingGraph` above records exactly which principal reached
    `graph.match`, so this test fails if that principal is ever anything but the monitor's own
    saving analyst — not only if a leak happens to reach the alert, which `record_match`'s own
    independent recheck can mask regardless of what `graph.match` was called with.

    `principal_for_owner` here resolves only `OWNER` — Postgres is shared across the whole test
    run with no per-test reset (`test_pattern_store.py`'s own established discipline), so
    `monitor_store.list_all_active()` also returns every other test's own leftover monitors, some
    owned by ids this function has no reason to recognise. Those are skipped via the already-proven
    "unresolvable owner" behaviour (`test_a_hotlist_with_no_resolvable_owner_principal_is_skipped_
    not_run_as_a_stale_one`), so `graph.match` is only ever reached for the monitor this test
    itself created — not an assumption that the store happens to be empty."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    saved = await pattern_store.save(
        OWNER, pattern_id=None, name="Evaluator fixture principal pin", definition=_pattern()
    )
    monitor = await monitor_store.create(OWNER, pattern_id=saved.pattern_id)

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (person_id, endpoint_id) = await graph.upsert_nodes(
            [
                _person_write("Principalpinfixture", owning_unit=OWNER.org_unit),
                _endpoint_write(f"+44-{uuid.uuid4().hex[:8]}", owning_unit=OWNER.org_unit),
            ],
            tx,
        )
        await graph.commit_transaction(tx)
        tx = await graph.begin_transaction()
        await graph.upsert_edges(
            [_uses_edge(person_id, endpoint_id, owning_unit=OWNER.org_unit)], tx
        )
        await graph.commit_transaction(tx)

        recording_graph = _PrincipalRecordingGraph(graph)
        await evaluate_monitors_for_entry(
            _entry([]),
            graph=recording_graph,
            monitor_store=monitor_store,
            pattern_store=pattern_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=lambda owner_id: OWNER if owner_id == OWNER.id else None,
        )

        assert recording_graph.match_principals, (
            "graph.match was never called — the setup above is wrong, not the invariant"
        )
        broader = service_principal(scheme)
        for used in recording_graph.match_principals:
            assert used.id == OWNER.id, (
                f"monitor {monitor.id} evaluated with principal {used.id!r}, not its own "
                f"owner {OWNER.id!r}"
            )
            assert used.id != broader.id


async def test_a_monitor_alerts_once_per_match_set_and_again_only_when_it_changes(
    monitor_store, pattern_store, alert_store, audit, valkey
) -> None:
    """The coarse whole-subgraph dedup `evaluation.py`'s own docstring discloses: an unchanged
    match set does not re-alert; a match set that grows does. Safe against the rest of the test
    suite's own data because `arcadedb_adapter` gives this test a freshly-created, isolated
    database — `packages/adapters/graph_arcadedb/testing.py`'s own guarantee."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    saved = await pattern_store.save(
        OWNER, pattern_id=None, name="Evaluator fixture dedup", definition=_pattern()
    )
    monitor = await monitor_store.create(OWNER, pattern_id=saved.pattern_id)

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (person_id, endpoint_id) = await graph.upsert_nodes(
            [
                _person_write("Dedupfixtureone", owning_unit=OWNER.org_unit),
                _endpoint_write(f"+44-{uuid.uuid4().hex[:8]}", owning_unit=OWNER.org_unit),
            ],
            tx,
        )
        await graph.commit_transaction(tx)
        tx = await graph.begin_transaction()
        await graph.upsert_edges(
            [_uses_edge(person_id, endpoint_id, owning_unit=OWNER.org_unit)], tx
        )
        await graph.commit_transaction(tx)

        kwargs = dict(
            graph=graph,
            monitor_store=monitor_store,
            pattern_store=pattern_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for,
        )

        first = await evaluate_monitors_for_entry(_entry([]), **kwargs)
        assert len([a for a in first if a.rule_id == f"monitor:{monitor.id}"]) == 1

        second = await evaluate_monitors_for_entry(_entry([]), **kwargs)
        assert [a for a in second if a.rule_id == f"monitor:{monitor.id}"] == [], (
            "an unchanged match set re-alerted — dedup signature did not hold"
        )

        # Grow the match set: a new Person/Endpoint pair joined by USES.
        tx = await graph.begin_transaction()
        (person2_id, endpoint2_id) = await graph.upsert_nodes(
            [
                _person_write("Dedupfixturetwo", owning_unit=OWNER.org_unit),
                _endpoint_write(f"+44-{uuid.uuid4().hex[:8]}", owning_unit=OWNER.org_unit),
            ],
            tx,
        )
        await graph.commit_transaction(tx)
        tx = await graph.begin_transaction()
        await graph.upsert_edges(
            [_uses_edge(person2_id, endpoint2_id, owning_unit=OWNER.org_unit)], tx
        )
        await graph.commit_transaction(tx)

        third = await evaluate_monitors_for_entry(_entry([]), **kwargs)
        matching_third = [a for a in third if a.rule_id == f"monitor:{monitor.id}"]
        assert len(matching_third) == 1, "a grown match set must re-alert once, not stay silent"


async def test_a_monitor_whose_pattern_no_longer_exists_stops_rather_than_errors(
    monitor_store, pattern_store, alert_store, audit, valkey
) -> None:
    """`evaluate_monitors_for_entry`'s own `PatternNotFoundError` handling — ADR-036's "the
    monitor stops" extended from principal validity to pattern validity. There is no delete route
    on `PatternStore` today, so this is proven directly against the store rather than through a
    route that does not exist yet."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    saved = await pattern_store.save(
        OWNER, pattern_id=None, name="Evaluator fixture missing pattern", definition=_pattern()
    )
    await monitor_store.create(OWNER, pattern_id=saved.pattern_id)

    # Simulate "no longer this owner's own pattern" the same way `MonitorNotFoundError`'s own
    # docstring frames it: a monitor referencing a `pattern_id` `get_authorized` no longer
    # resolves for its own `owner_id` — here, a monitor built directly against a pattern id that
    # was never saved under `OWNER` at all.
    orphan_monitor = await monitor_store.create(
        OTHER_ANALYST, pattern_id=f"no-such-pattern-{uuid.uuid4().hex}"
    )

    async with arcadedb_adapter(ontology, scheme) as graph:
        alerts = await evaluate_monitors_for_entry(
            _entry([]),
            graph=graph,
            monitor_store=monitor_store,
            pattern_store=pattern_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for,
        )
        # No exception raised (the whole call must not error), and the orphaned monitor produces
        # no alert. The well-formed monitor above is unaffected by its neighbour's failure.
        assert [a for a in alerts if a.rule_id == f"monitor:{orphan_monitor.id}"] == []


async def test_a_skipped_monitor_evaluation_is_observable_as_stopped_and_a_later_success_clears_it(
    monitor_store, pattern_store, alert_store, audit, valkey
) -> None:
    """`test_a_skipped_hotlist_evaluation_is_observable_as_stopped_and_a_later_success_clears_it`'s
    own twin for monitors — same reasoning, same ADR-036 requirement, this time for the "principal
    unresolvable" skip specifically (not the "pattern gone" skip the test above already covers,
    which also sets `status="stopped"` but is not re-asserted here to keep this one scoped to a
    single named case)."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    saved = await pattern_store.save(
        OWNER, pattern_id=None, name="Evaluator fixture status observability", definition=_pattern()
    )
    monitor = await monitor_store.create(OWNER, pattern_id=saved.pattern_id)
    assert monitor.status == "active"

    async with arcadedb_adapter(ontology, scheme) as graph:
        await evaluate_monitors_for_entry(
            _entry([]),
            graph=graph,
            monitor_store=monitor_store,
            pattern_store=pattern_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=lambda owner_id: None,
        )
        stopped = await monitor_store.get_authorized(monitor.id, OWNER)
        assert stopped.status == "stopped"

        await evaluate_monitors_for_entry(
            _entry([]),
            graph=graph,
            monitor_store=monitor_store,
            pattern_store=pattern_store,
            alert_store=alert_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=lambda owner_id: OWNER if owner_id == OWNER.id else None,
        )
        active_again = await monitor_store.get_authorized(monitor.id, OWNER)
        assert active_again.status == "active"
