"""L2.8c (ADR-109 Amendment 11) against the real stores: the repoint journal's lock and rename
(the L2.8b review's D9 and D10), and every caller that clones or replaces a link an alert can cite
going through the journal, so an alert citing the link each one replaces stays listed for its
readers. The journal's own cases, from L2.8b, are `test_alert_evidence_withheld_live.py`'s.

Each case was shown red by a plant at the real call site; the outputs are kept with the lane's
record (`process/lanes/rules/l2.8c/`)."""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import pytest
from services.api.alerts import RepointLockBusy
from services.api.config import PostgresConfig

from conduit_common.identity import new_id
from schemas.domain import Alert, AlertMode
from tests.ingest import test_typology_rules as _rules_suite
from tests.ingest.test_typology_rules import ANALYST, ONTOLOGY, SCHEME, T0, arcadedb_adapter
from tests.services.api.repoint_journal_cleanup import remove_repoint_records  # noqa: F401 - autouse teardown

#: The rules suite's own live stores and DuckDB analytics, as fixtures of this file.
stores = _rules_suite.stores
analytics = _rules_suite.analytics

#: Seconds a case may take before it fails rather than stalls the run.
BOUND = 30


def _alert(case: str, *, node: str | None = None, edges: list[str] | None = None) -> Alert:
    return Alert(id=new_id(), rule_id=f"typology:{new_id()}", owner_id=ANALYST.id, mode=AlertMode.FULL,
                 referent_node_ids=[], edge_ids=edges or [], investigation_id=case, created_at=T0,
                 typology="structuring", words="A finding", severity="medium",
                 alert_node_id=node)  # fmt: skip


async def _record(stores: dict[str, Any]) -> str:
    """An empty record, as `AlertStore.repointing` opens one."""
    record = new_id()
    async with stores["alerts"]._pool.acquire() as conn:
        await conn.execute("INSERT INTO alert_repoint_records (id) VALUES ($1)", record)
    return record


# ---- D10: the lock pool's timeout and its own advisory-key space --------------------------------


async def test_a_settle_that_waits_too_long_for_a_lock_connection_refuses_in_words(
    stores: dict[str, Any],
) -> None:
    """D10. Every lock connection is held elsewhere; a settle waits `lock_wait` for one, then
    refuses in words naming the record and the wait, and the record is left for a later read.
    Red with no timeout on the wait: the settle waited for ever (the case's bound fired)."""
    alerts = stores["alerts"]
    alerts.lock_wait = 0.5
    record = await _record(stores)
    held = [await alerts._lock_pool.acquire() for _ in range(alerts._lock_pool.get_max_size())]
    try:
        with pytest.raises(RepointLockBusy, match=rf"repoint record {record} not settled: no lock "
                                                  r"connection came free within 0\.5 seconds"):  # fmt: skip
            await asyncio.wait_for(alerts._settle_record(None, record, writer=True), BOUND)
    finally:
        for conn in held:
            await alerts._lock_pool.release(conn)
    async with alerts._pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM alert_repoint_records WHERE id = $1", record) == 1


async def test_a_records_lock_is_its_own_whatever_another_store_locks_on_the_same_text(
    stores: dict[str, Any],
) -> None:
    """D10. Another store holds a one-key advisory lock on `hashtext` of the record's own id (as
    `strength_influencers` and `studio_recipes` lock their own text). The record's settle is not
    skipped for it: its writer closes it. Red with the record's lock in the one-key space: the
    settle found the key taken and skipped the record (`None`)."""
    record = await _record(stores)
    other = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await other.execute("SELECT pg_advisory_lock(hashtext($1))", record)
        settled = await asyncio.wait_for(stores["alerts"]._settle_record(None, record, writer=True), BOUND)
        assert settled == [], "the writer settled its own empty record, not skipped it"
    finally:
        await other.close()


# ---- D9: the rename under the id-ordered lock ---------------------------------------------------


async def test_a_rename_and_a_repoint_of_the_same_alerts_never_deadlock(stores: dict[str, Any]) -> None:
    """D9. Two alerts, `a` before `b` in id order, each naming a node a record renames. Another
    writer (as `apply_repoints` does) has locked `a` and goes on to lock `b`, id order. The rename,
    asked to rename `b`'s node first, takes the rows in id order too, so it waits for `a` holding
    nothing, and the other writer takes `b` at once. Red with the rename outside the id-ordered
    lock: the rename held `b` while waiting for `a`, and Postgres broke the deadlock by killing
    one of the two (`DeadlockDetectedError`)."""
    case = f"case-{new_id()}"
    node_a, node_b = f"node-a-{new_id()}", f"node-b-{new_id()}"
    first, second = _alert(case, node=node_a), _alert(case, node=node_b)
    assert first.id < second.id
    for alert in (first, second):
        await stores["alerts"].save(alert)
    renamed = {node_b: f"{node_b}-r2", node_a: f"{node_a}-r2"}

    other = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        tx = other.transaction()
        await tx.start()
        await other.execute("SET LOCAL lock_timeout = '10s'")
        await other.execute("SELECT id FROM alerts WHERE id = $1 FOR UPDATE", first.id)
        rename = asyncio.create_task(stores["alerts"].rename_alert_nodes(renamed))
        await asyncio.sleep(1.5)  # the rename reaches its wait for `a`
        try:
            await other.execute("SELECT id FROM alerts WHERE id = $1 FOR UPDATE", second.id)
        finally:
            await tx.commit()
        await asyncio.wait_for(rename, BOUND)
    finally:
        await other.close()
    async with stores["alerts"]._pool.acquire() as conn:
        named = dict(await conn.fetch("SELECT id, alert_node_id FROM alerts WHERE id = ANY($1::text[])",
                                      [first.id, second.id]))  # fmt: skip
    assert named == {first.id: renamed[node_a], second.id: renamed[node_b]}


# ---- every caller that clones or replaces a link an alert can cite ------------------------------
#
# Each case writes a person `p` and a contact `q` joined by a link `L`, and an alert citing `L` and
# naming `q` (never `p`, whose own correction this step does not cover). Then the caller replaces
# `L`: a node's correction clones it onto the new revision of `p`; a split's annotation supersedes
# it. The alert stays listed for the reader who may read `L`, citing `L`'s newest revision. Red with
# that caller's journal entry removed: the alert went on citing `L`, which no read returns, and was
# withheld from every reader for good (ADR-146 decision 10).

from datetime import UTC, datetime  # noqa: E402

from schemas.domain import (  # noqa: E402
    EdgeWrite,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from conduit_common.identity import new_edge_id, new_node_id  # noqa: E402

#: The reader: OFFICIAL in the unit that owns everything here, so it may read `p`, `q` and `L`.
READER = Principal(id="reader-l28c", clearance="OFFICIAL", org_unit="verify")
OFFICIAL = Handling(classification="OFFICIAL", handling_code="P", originator="verify", owning_unit="verify")


def _provenance(state: ProvenanceState) -> Provenance:
    return Provenance(state=state, first_seen=T0, extracted_by=None if state is ProvenanceState.ASSERTED else "t",
                      sources=[SourceRef(document_id="t", locator="r", excerpt_hash="")])  # fmt: skip


def _person(name: str, state: ProvenanceState = ProvenanceState.ASSERTED, node_type: str = "Person",
            **properties: Any) -> NodeWrite:  # fmt: skip
    key = "name" if node_type == "Location" else "family_name"
    return NodeWrite(id=new_node_id(), type=node_type, properties={key: name, **properties},
                     provenance=_provenance(state), handling=OFFICIAL, created_by="t", created_at=T0)  # fmt: skip


async def _cited_link(stores: dict[str, Any], graph: Any, case: str, *, p_state: ProvenanceState,
                      p_type: str = "Person", link_type: str = "ASSOCIATE_OF") -> tuple[str, str, Alert]:  # fmt: skip
    """`p` (in `p_state`), `q`, the link `L` from `p` to `q`, and an alert citing `L` and `q`."""
    tag = new_id()
    p_write = _person(f"P {tag}", p_state, p_type)
    q_write = _person(f"Q {tag}", node_type=p_type)
    tx = await graph.begin_transaction()
    p, q = await graph.upsert_nodes([p_write, q_write], tx)
    (link,) = await graph.upsert_edges([EdgeWrite(
        id=new_edge_id(), type=link_type, source=p, target=q, provenance=_provenance(ProvenanceState.ASSERTED),
        handling=OFFICIAL, created_by="t", created_at=T0)], tx)  # fmt: skip
    await graph.commit_transaction(tx)
    alert = Alert(id=new_id(), rule_id=f"typology:{new_id()}", owner_id=ANALYST.id, mode=AlertMode.FULL,
                  referent_node_ids=[q], edge_ids=[link], investigation_id=case, created_at=T0,
                  typology="structuring", words=f"A finding over {tag}", severity="medium")  # fmt: skip
    await stores["alerts"].save(alert, handlings=[OFFICIAL])
    return p, link, alert


async def _still_listed(stores: dict[str, Any], graph: Any, analytics: Any, case: str, alert: Alert,
                        link: str) -> None:  # fmt: skip
    """The alert is listed for the reader, citing the newest revision of `link` the graph holds."""
    from services.api import alert_queue

    listed = {q.alert.id: q.alert for q in await alert_queue.queue(stores["alerts"], graph, analytics, case, READER)}
    assert alert.id in listed, "the alert citing the replaced link is withheld from its reader"
    (now,) = listed[alert.id].edge_ids
    assert now != link and (await graph.stored_link_states([now]))[now].superseded_by is None
    assert (await graph.stored_link_states([link]))[link].superseded_by is not None


class _Judgements:
    """No judgement cites anything here (`flag_judgements_citing_superseded_node` reads this)."""

    async def list_citing(self, node_id: str) -> list[Any]:
        return []


class _WorkingSets:
    """The routes purge the moved alerts' re-marked nodes; nothing is re-marked here. Shaped as
    `WorkingSetService` answers: the cases changed, and the client they are published on."""

    publisher = None

    def __init__(self) -> None:
        self.removed: list[Any] = []

    async def remove_reverted(self, nodes: Any, links: Any) -> list[Any]:
        self.removed.append((list(nodes), list(links)))
        return []


@pytest.mark.parametrize("route", ["confirm", "retract"])
async def test_an_alert_citing_a_link_a_routes_correction_clones_stays_listed(
    stores: dict[str, Any], analytics: Any, route: str
) -> None:
    """`confirm_node` and `retract_node` through their routes (`app.py`): each supersedes `p`, so
    `L` is cloned onto the new revision. Red with the route's `on_link_cloned` removed."""
    from services.api import app as conduit

    case = f"case-{new_id()}"
    state = ProvenanceState.INFERRED if route == "confirm" else ProvenanceState.ASSERTED
    handler = conduit.confirm_node_route if route == "confirm" else conduit.retract_node_route
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        p, link, alert = await _cited_link(stores, graph, case, p_state=state)
        await handler(investigation=None, node_id=p, principal=READER, graph=graph, audit=stores["audit"],
                      judgements=_Judgements(), alerts_store=stores["alerts"], working_set=_WorkingSets())  # type: ignore[arg-type]  # fmt: skip
        await _still_listed(stores, graph, analytics, case, alert, link)


async def test_an_alert_citing_a_link_the_closes_confirm_clones_stays_listed(
    stores: dict[str, Any], analytics: Any
) -> None:
    """The close's confirm (`alert_queue._close`): a true positive confirms the closed alert's
    inferred node, here `p`, cloning `L`, which a second alert cites. Red with the close's
    `on_link_cloned` removed."""
    from services.api import alert_queue

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        p, link, citing = await _cited_link(stores, graph, case, p_state=ProvenanceState.INFERRED)
        closed = Alert(id=new_id(), rule_id=f"typology:{new_id()}", owner_id=ANALYST.id, mode=AlertMode.FULL,
                       referent_node_ids=[], edge_ids=[], investigation_id=case, created_at=T0,
                       typology="structuring", words="The closed finding", severity="medium",
                       alert_node_id=p)  # fmt: skip
        await stores["alerts"].save(closed, handlings=[OFFICIAL])
        await alert_queue.dispose(stores["alerts"], graph, analytics, case, closed.id, READER,
                                  disposition="true_positive", reason="checked")  # fmt: skip
        await _still_listed(stores, graph, analytics, case, citing, link)


@pytest.mark.parametrize("path", ["submit", "job"])
async def test_an_alert_citing_a_link_supersede_py_clones_stays_listed(
    stores: dict[str, Any], analytics: Any, path: str
) -> None:
    """`supersede.py`'s synchronous path and its worker job: the caller (the worker) commits the
    transaction, and the next read settles the record. Red with that path's journal removed."""
    from services.api.supersede import run_supersede_node_job, submit_supersede_node

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        p, link, alert = await _cited_link(stores, graph, case, p_state=ProvenanceState.INFERRED)
        replacement = _person(f"P corrected {new_id()}")
        tx = await graph.begin_transaction()
        if path == "submit":
            done = await submit_supersede_node(p, replacement, tx, graph=graph, principal=READER, jobs=None,  # type: ignore[arg-type]
                                               degree_threshold=1_000, alerts=stores["alerts"])  # fmt: skip
            assert done.mode == "sync"
        else:
            await run_supersede_node_job({"node_id": p, "replacement": replacement.model_dump(mode="json")},
                                         graph=graph, tx=tx, alerts=stores["alerts"])  # fmt: skip
        await graph.commit_transaction(tx)
        await _still_listed(stores, graph, analytics, case, alert, link)


async def test_an_alert_citing_a_link_the_pipelines_online_point_clones_stays_listed(
    stores: dict[str, Any], analytics: Any
) -> None:
    """`pipeline_run`'s enrich stage: an online geocode supersedes the mention `p` (a Location the
    run's branch created) with its point, cloning `L`. Red with the stage's `on_link_cloned`
    removed from `_persist_online_point`."""
    from services.api.pipeline_run import _run_enrich_stage

    from schemas.ingest import BranchRunReport, LoadReport, PipelineGraph
    from tests.ingest.test_studio_run_geometries import RecordingAnalytics

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        p, link, alert = await _cited_link(stores, graph, case, p_state=ProvenanceState.ASSERTED,
                                           p_type="Location", link_type="ADJOINS")  # fmt: skip
        pipeline = PipelineGraph.model_validate({
            "nodes": [{"id": "src", "kind": "source", "label": "Places"},
                      {"id": "enrich", "kind": "enrich", "label": "Geocode",
                       "config": {"geocoder": "online_allowlist"}}],
            "edges": [{"source": "src", "target": "enrich"}]})  # fmt: skip
        branch = BranchRunReport(source_id="src", source_label="Places",
                                 report=LoadReport(load_id="l", recipe_id="r", recipe_version=1,
                                                   created_node_ids=[p]))  # fmt: skip

        async def provider(name: str) -> tuple[float, float] | None:
            return (-1.8984, 52.4778)

        stage, _ = await _run_enrich_stage(pipeline.nodes[1], pipeline=pipeline, branches=[branch], graph=graph,
                                           principal=READER, scheme=SCHEME, analytics=RecordingAnalytics(),  # type: ignore[arg-type]
                                           online_geocode=provider, alerts=stores["alerts"])  # fmt: skip
        assert stage.matched_online == 1, stage
        await _still_listed(stores, graph, analytics, case, alert, link)


async def test_an_alert_citing_a_split_a_resolution_run_annotates_stays_listed(
    stores: dict[str, Any], analytics: Any
) -> None:
    """`same_as_writer.record_conflicts` through the resolution run (`trigger.py`): two records of
    one person an analyst split (`NOT_SAME_AS`) are matched again, so the split is superseded with
    the conflict noted on it; an alert cites the split. The worker commits; the next read settles.
    Red with the run's `on_link_replaced` removed."""
    from services.resolve.trigger import run_resolution_for_entity_type

    async def no_layers() -> set[str]:
        return set()

    case = f"case-{new_id()}"
    tag = new_id()
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        twins = [NodeWrite(id=new_node_id(), type="Person", provenance=_provenance(ProvenanceState.ASSERTED),
                           properties={"family_name": f"Split{tag}", "given_names": "Dana", "date_of_birth": "1980-01-01"},
                           handling=OFFICIAL, created_by="t", created_at=T0) for _ in range(2)]  # fmt: skip
        tx = await graph.begin_transaction()
        c, d = await graph.upsert_nodes(twins, tx)
        (split,) = await graph.upsert_edges([EdgeWrite(
            id=new_edge_id(), type="NOT_SAME_AS", source=c, target=d, provenance=_provenance(ProvenanceState.ASSERTED),
            handling=OFFICIAL, created_by="t", created_at=datetime.now(UTC))], tx)  # fmt: skip
        await graph.commit_transaction(tx)
        alert = Alert(id=new_id(), rule_id=f"typology:{new_id()}", owner_id=ANALYST.id, mode=AlertMode.FULL,
                      referent_node_ids=[c, d], edge_ids=[split], investigation_id=case, created_at=T0,
                      typology="structuring", words="Over a split", severity="medium")  # fmt: skip
        await stores["alerts"].save(alert, handlings=[OFFICIAL])
        tx = await graph.begin_transaction()
        result = await run_resolution_for_entity_type("Person", graph=graph, tx=tx, ontology=ONTOLOGY, scheme=SCHEME,
                                                      analyst_layers=no_layers, alerts=stores["alerts"])  # fmt: skip
        await graph.commit_transaction(tx)
        assert result.conflicts_recorded >= 1
        await _still_listed(stores, graph, analytics, case, alert, split)


# ---- the purge published to connected canvases (Amendment 10 point 6's second gap) ---------------


async def test_a_purge_of_a_re_marked_alert_node_is_published_to_the_cases_canvases(
    stores: dict[str, Any], analytics: Any
) -> None:
    """An analyst raises a cited link to SECRET through the link change route's service; the alert
    follows it and its node is re-marked, so the OFFICIAL copy leaves the case's working set. The
    removal is published on the case's channel at once (`notify.publish_delta`), naming that node,
    so a connected canvas drops it now rather than at its next resynchronisation. Red with the
    purge's publish removed: nothing reached the channel."""
    import json

    from services.api.link_changes import LinkChangeRequest, LinkChangeService
    from services.api.notify import notify_channel
    from services.api.working_set.service import WorkingSetService

    from tests.ingest.test_typology_rules import SECRET_LOADER, _case_alerts, _raised
    from tests.services.api.test_link_changes import InMemoryChanges, MovedNotes
    from tests.services.api.working_set.fakes import FakeWorkingSetStore

    case = f"case-{new_id()}"
    valkey = stores["valkey"]
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _raised(stores, graph, analytics, case, "PB")
        (alert,) = await _case_alerts(stores, ANALYST, case)
        (link,) = await graph.get_edges(alert.edge_ids, ANALYST)
        working = FakeWorkingSetStore()
        await working.add_nodes(case, await graph.get_nodes(alert.referent_node_ids, ANALYST))
        await working.add_edges(case, [link])
        await working.add_nodes(case, [await graph.get_node(alert.alert_node_id, ANALYST)])  # type: ignore[arg-type, list-item]
        service = LinkChangeService(InMemoryChanges(), WorkingSetService(graph, working, SCHEME, valkey=valkey),
                                    graph, ONTOLOGY, MovedNotes(), scheme=SCHEME, alerts=stores["alerts"])  # fmt: skip
        pubsub = valkey.pubsub()
        await pubsub.subscribe(notify_channel(case))
        try:
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            secret = link.handling.model_copy(update={"classification": "SECRET"})
            await service.change(case, link.id, SECRET_LOADER, LinkChangeRequest(reason="SECRET", handling=secret))
            assert alert.alert_node_id not in await working.node_ids(case), "the copy was purged"
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
        finally:
            await pubsub.unsubscribe(notify_channel(case))
            await pubsub.aclose()
        assert message is not None, "the purge reached no connected canvas"
        delta = json.loads(message["data"])
        assert delta["op"] == "remove" and alert.alert_node_id in delta["node_ids"], delta
