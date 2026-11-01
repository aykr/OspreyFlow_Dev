"""The one alert queue and an alert's explanation (`06_DECISIONS.md` ADR-109 phase B; ADR-133
decision 5 and stage (a)).

**One queue for every kind (ADR-133 stage (a)).** The queue a case's Monitoring place shows holds
its typology alerts (the case team's) and the hotlist and monitor alerts the reader owns or that are
shared with their team (`alerts.queue_scope`, decided in the query, rule 3). Each carries its kind,
its severity and who may see it. `queue` below stays the typology alerts alone: it is what the
Reports view and neighbourhood risk count (ADR-111), which ADR-134 widens, not this stage.

**One queue per case (ruling 3).** Every member of the case reads the rule-raised alerts of the
case; the rule still evaluated as its deployer (ADR-036), only readership widens. **What a reader
cannot see, they are not shown (rule 3, ADR-039's all-or-nothing):** an alert any of whose entities,
links or transactions the reader cannot read is left out of the queue and its count, and opening
it answers as if it did not exist — its words name what it concerns, so a partial alert would
disclose the hidden part. Visibility is always the adapters' own answer, read as the reader.

**Triage.** An open alert is claimed by one member (or released again), and closed with a
disposition and its reason. A *true positive* is the human confirmation rule 5 waits for: the
alert's `Alert` node is confirmed (asserted, `confirmed_by` the member). A *false positive* closes
the alert and leaves the node `inferred` — a suggestion nobody confirmed, which is what it was.
"""

from __future__ import annotations

from collections.abc import Sequence

from services.extract.writer import confirm_edge, confirm_node

from ontology.handling import sources_in_full
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.analytics import EventFilter, EventListRequest, EventRecord
from schemas.domain import (
    Alert,
    AlertExplanation,
    AlertMode,
    Edge,
    ExplainedTransaction,
    Node,
    Principal,
    ProvenanceState,
    QueuedAlert,
)

from .alerts import AlertNotFoundError, AlertStore, AlertTriageConflict, QueueRow

#: The properties that name an entity, most telling first.
_NAME_PROPERTIES = (
    "name",
    "account_number",
    "value_normalised",
    "family_name",
    "title",
    "rule_id",
)


def node_name(node: Node) -> str:
    for key in _NAME_PROPERTIES:
        value = node.properties.get(key)
        if isinstance(value, str) and value.strip():
            if key == "family_name" and node.properties.get("given_names"):
                return f"{node.properties['given_names']} {value}"
            return value
    return f"{node.type} {node.id[-6:]}"


def summary_of(alert: Alert, nodes: dict[str, Node]) -> str:
    """The finding in words, each entity named as the reader sees it, not by its id. A hotlist or
    monitor alert has no words of its own; it is said from what it found."""
    if alert.words is None and alert.typology is None:
        named = ", ".join(node_name(nodes[i]) for i in alert.referent_node_ids if i in nodes)
        if alert.rule_id.startswith("hotlist:"):
            if alert.mode is AlertMode.NOTIFY_STUB:
                return "A hotlisted identifier matched data you cannot see."
            return f"A hotlisted identifier appeared: {named}"
        if alert.rule_id.startswith("monitor:"):
            return f"A watched pattern matched: {named}"
    words = alert.words or alert.typology or "Alert"
    for node_id, node in nodes.items():
        words = words.replace(node_id, node_name(node))
    return words


def _wanted(alert: Alert) -> list[str]:
    return [*alert.referent_node_ids, *([alert.alert_node_id] if alert.alert_node_id else [])]


def _queued(row: QueueRow, summary: str) -> QueuedAlert:
    return QueuedAlert(
        alert=row.alert,
        summary=summary,
        kind=row.kind,
        severity=row.severity,
        audience=row.audience,
        team=row.alert.team if row.audience == "team" else None,
    )


async def monitoring_queue(
    store: AlertStore,
    graph: GraphPort,
    investigation_id: str,
    reader: Principal,
    *,
    kinds: Sequence[str] | None = None,
    severities: Sequence[str] | None = None,
    statuses: Sequence[str] | None = None,
) -> list[QueuedAlert]:
    """ADR-133 decision 5: the one queue, as `reader` may see it. Which rows is the query's answer
    (`AlertStore.list_queue`, rule 3); what each names is then read **once, in one batch**, as the
    reader, through the adapter's own access step (`GraphPort.get_nodes`). An alert any of whose
    entities is missing from that answer is left out whole (ADR-039's all-or-nothing): it is neither
    listed nor counted, the order of the rest is unchanged, and the work done is the same one read
    whether it exists or not — so no count, order or timing says a hidden alert is there."""
    rows = await store.list_queue(
        investigation_id, reader, kinds=kinds, severities=severities, statuses=statuses
    )
    wanted = sorted({node_id for row in rows for node_id in _wanted(row.alert)})
    readable = {n.id: n for n in await graph.get_nodes(wanted, reader)} if wanted else {}
    shown: list[QueuedAlert] = []
    for row in rows:
        ids = _wanted(row.alert)
        if any(node_id not in readable for node_id in ids):
            continue
        shown.append(_queued(row, summary_of(row.alert, {i: readable[i] for i in ids})))
    return shown


async def _visible_nodes(
    alert: Alert, graph: GraphPort, reader: Principal
) -> dict[str, Node] | None:
    """Every entity the alert concerns, and its own node, as the reader reads them — or `None`
    when any of them is hidden from the reader."""
    wanted = [*alert.referent_node_ids, *([alert.alert_node_id] if alert.alert_node_id else [])]
    found: dict[str, Node] = {}
    for node_id in wanted:
        node = await graph.get_node(node_id, reader)
        if node is None:
            return None
        found[node_id] = node
    return found


async def queue(
    store: AlertStore,
    graph: GraphPort,
    investigation_id: str,
    reader: Principal,
    *,
    statuses: Sequence[str] | None = None,
) -> list[QueuedAlert]:
    """The case's typology alerts the reader may see whole, newest first: what the Reports figures
    and neighbourhood risk count. Through `monitoring_queue`, so which rows is the query's answer
    and what they name is one batched read as the reader (ADR-134 decision 4: this read each
    alert's nodes in turn, stopping at a hidden one, so its work grew with the alerts the reader
    may not see; `test_case_queue_reads.py`)."""
    shown = await monitoring_queue(
        store, graph, investigation_id, reader, kinds=["typology"], statuses=statuses
    )
    return sorted(shown, key=lambda q: (q.alert.created_at, q.alert.id), reverse=True)


async def _visible_row(
    store: AlertStore, graph: GraphPort, alert_id: str, investigation_id: str, reader: Principal
) -> tuple[QueueRow, dict[str, Node]]:
    """One alert of the reader's queue, and everything it names as they read it — or not found,
    the same answer as for an alert that does not exist."""
    row = await store.get_queue_alert(alert_id, investigation_id, reader)
    nodes = await _visible_nodes(row.alert, graph, reader)
    if nodes is None:
        raise AlertNotFoundError(alert_id)
    return row, nodes


async def _visible_alert(
    store: AlertStore, graph: GraphPort, alert_id: str, investigation_id: str, reader: Principal
) -> tuple[Alert, dict[str, Node]]:
    row, nodes = await _visible_row(store, graph, alert_id, investigation_id, reader)
    return row.alert, nodes


async def explain(
    store: AlertStore,
    graph: GraphPort,
    analytics: AnalyticsPort,
    investigation_id: str,
    alert_id: str,
    reader: Principal,
) -> AlertExplanation:
    explanation, _ = await explain_with_evidence(
        store, graph, analytics, investigation_id, alert_id, reader
    )
    return explanation


async def explain_with_evidence(
    store: AlertStore,
    graph: GraphPort,
    analytics: AnalyticsPort,
    investigation_id: str,
    alert_id: str,
    reader: Principal,
) -> tuple[AlertExplanation, list[EventRecord]]:
    """`explain`, and the cited transactions as the analytics store holds them — with their
    handlings, which a report pack's alert item rests on (ADR-134 decision 1)."""
    row, nodes = await _visible_row(store, graph, alert_id, investigation_id, reader)
    alert = row.alert
    edges = await _cited_edges(alert, graph, reader, list(nodes))
    if len({e.id for e in edges if e.type != "ALERTED_ON"}) < len(set(alert.edge_ids)):
        raise AlertNotFoundError(alert_id)
    transactions: list[ExplainedTransaction] = []
    cited_events: list[EventRecord] = []
    if alert.event_ids:
        page = await analytics.list_events(
            EventListRequest(
                filter=EventFilter(investigation_scope=investigation_id, event_ids=alert.event_ids),
                limit=200,
            ),
            reader,
        )
        if page.total < len(set(alert.event_ids)):
            # A cited transaction the reader cannot read: the alert is not theirs to see.
            raise AlertNotFoundError(alert_id)
        cited_events = list(page.events)
        transactions = sorted(
            (
                ExplainedTransaction(
                    event_id=e.event_id,
                    edge_id=e.edge_id,
                    source_id=e.source_id,
                    target_id=e.target_id,
                    occurred_at=e.occurred_at,
                    amount=_number(e.properties.get("amount")),
                )
                for e in page.events
            ),
            key=lambda t: t.occurred_at,
        )
    explanation = AlertExplanation(
        alert=alert,
        summary=summary_of(alert, nodes),
        nodes=list(nodes.values()),
        edges=edges,
        transactions=transactions,
        kind=row.kind,
        severity=row.severity,
        audience=row.audience,
        team=alert.team if row.audience == "team" else None,
    )
    return explanation, cited_events


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


async def _cited_edges(
    alert: Alert, graph: GraphPort, reader: Principal, node_ids: list[str]
) -> list[Edge]:
    """The links the alert cites, and its own `ALERTED_ON` links, among its nodes, as the reader
    reads them."""
    cited = set(alert.edge_ids)
    return [
        e
        for e in await graph.edges_among(node_ids, reader)
        if e.id in cited or (e.type == "ALERTED_ON" and e.source == alert.alert_node_id)
    ]


async def canvas_elements(
    store: AlertStore, graph: GraphPort, investigation_id: str, alert_id: str, reader: Principal
) -> tuple[Alert, list[Node], list[Edge]]:
    """What "open on the canvas" puts there: the alert's node, its entities and the links among
    them it cites — all of it visible to the reader, or the alert is not found."""
    alert, nodes = await _visible_alert(store, graph, alert_id, investigation_id, reader)
    return alert, list(nodes.values()), await _cited_edges(alert, graph, reader, list(nodes))


async def claim(
    store: AlertStore, graph: GraphPort, investigation_id: str, alert_id: str, member: Principal
) -> Alert:
    await _visible_alert(store, graph, alert_id, investigation_id, member)
    return await store.set_queue_triage(
        alert_id, investigation_id, member, expect_status=["open"], status="claimed",
        assignee=member.id,
    )  # fmt: skip


async def release(
    store: AlertStore, graph: GraphPort, investigation_id: str, alert_id: str, member: Principal
) -> Alert:
    alert, _ = await _visible_alert(store, graph, alert_id, investigation_id, member)
    if alert.assignee not in (None, member.id):
        raise AlertTriageConflict(alert_id)
    return await store.set_queue_triage(
        alert_id, investigation_id, member, expect_status=["claimed"], status="open",
        assignee=None,
    )  # fmt: skip


class CloseRefused(Exception):
    """ADR-133 decision 7: the person who proposed closing a high-severity alert cannot approve
    it."""


def needs_second_person(row: QueueRow) -> bool:
    """ADR-133 decision 7, stage (d): closing a high-severity alert needs a second person with the
    right — where a second person may read it. An alert its owner alone may read (their "only me"
    hotlist's, their own monitor's) has no second reader to ask: asking would show it to someone it
    is not shared with, so its owner closes it."""
    return row.severity == "high" and row.audience != "owner"


async def dispose(
    store: AlertStore,
    graph: GraphPort,
    investigation_id: str,
    alert_id: str,
    member: Principal,
    *,
    disposition: str,
    reason: str,
) -> Alert:
    """Closes the alert with its disposition and reason — or, for a high-severity alert a second
    person may read, proposes the close: the alert waits as `closing`, its disposition and reason
    kept, until another member approves it (`approve_close`)."""
    row, nodes = await _visible_row(store, graph, alert_id, investigation_id, member)
    alert = row.alert
    if alert.status in ("closed", "closing"):
        raise AlertTriageConflict(alert_id)
    if needs_second_person(row):
        return await store.set_queue_triage(
            alert_id, investigation_id, member, expect_status=["open", "claimed"],
            status="closing", assignee=alert.assignee or member.id, disposition=disposition,
            disposition_reason=reason, close_proposed_by=member.id,
        )  # fmt: skip
    return await _close(
        store, graph, investigation_id, alert, nodes, member, disposition=disposition,
        reason=reason, expect=["open", "claimed"],
    )  # fmt: skip


async def approve_close(
    store: AlertStore, graph: GraphPort, investigation_id: str, alert_id: str, member: Principal
) -> Alert:
    """The second person approves a proposed close: the alert closes with the proposer's
    disposition and reason, decided by `member`, the proposer kept beside it."""
    alert, nodes = await _visible_alert(store, graph, alert_id, investigation_id, member)
    if alert.status != "closing" or alert.disposition is None or alert.close_proposed_by is None:
        raise AlertTriageConflict(alert_id)
    if alert.close_proposed_by == member.id:
        raise CloseRefused(
            "You proposed closing this alert; a second person with the right must approve it."
        )
    return await _close(
        store, graph, investigation_id, alert, nodes, member, disposition=alert.disposition,
        reason=alert.disposition_reason or "", expect=["closing"],
        proposed_by=alert.close_proposed_by,
    )  # fmt: skip


async def send_back(
    store: AlertStore, graph: GraphPort, investigation_id: str, alert_id: str, member: Principal
) -> Alert:
    """A proposed close turned down (or withdrawn by its proposer): the alert goes back to the
    person who proposed it, claimed, its proposed disposition cleared."""
    alert, _ = await _visible_alert(store, graph, alert_id, investigation_id, member)
    if alert.status != "closing":
        raise AlertTriageConflict(alert_id)
    return await store.set_queue_triage(
        alert_id, investigation_id, member, expect_status=["closing"], status="claimed",
        assignee=alert.close_proposed_by or alert.assignee, close_proposed_by=None,
    )  # fmt: skip


async def _close(
    store: AlertStore,
    graph: GraphPort,
    investigation_id: str,
    alert: Alert,
    nodes: dict[str, Node],
    member: Principal,
    *,
    disposition: str,
    reason: str,
    expect: list[str],
    proposed_by: str | None = None,
) -> Alert:
    alert_id = alert.id
    confirmed_node: str | None = None
    cited: list[str] | None = None
    if disposition == "true_positive":
        node = nodes.get(alert.alert_node_id) if alert.alert_node_id is not None else None
        # ADR-109 Amendment 7 (owner ruling, 11 October 2026): a true positive on a screening alert
        # is the analyst's confirmation of the match it found — its inferred `SAME_AS` becomes
        # asserted, and the alert cites the new revision so it still opens.
        # Read in full: `confirm_edge` writes each of these back with its own provenance (ADR-130
        # Amendment 2, "a read that is written back"); they are not sent to the Glass.
        with sources_in_full():
            cited_edges = await _cited_edges(alert, graph, member, list(nodes))
        matches = [
            e for e in cited_edges
            if alert.typology == "kyc_screening" and e.type == "SAME_AS"
            and e.provenance.state is not ProvenanceState.ASSERTED
        ]  # fmt: skip
        if (node is not None and node.provenance.state is not ProvenanceState.ASSERTED) or matches:
            tx = await graph.begin_transaction()
            try:
                if node is not None and node.provenance.state is not ProvenanceState.ASSERTED:
                    confirmed_node = await confirm_node(graph, node.id, member, tx=tx)
                renamed = {e.id: await confirm_edge(graph, e, member, tx=tx) for e in matches}
            except Exception:
                await graph.rollback_transaction(tx)
                raise
            await graph.commit_transaction(tx)
            if renamed:
                cited = [renamed.get(edge_id, edge_id) for edge_id in alert.edge_ids]
    return await store.set_queue_triage(
        alert_id,
        investigation_id,
        member,
        expect_status=expect,
        status="closed",
        assignee=alert.assignee or member.id,
        disposition=disposition,
        disposition_reason=reason,
        decided_by=member.id,
        alert_node_id=confirmed_node,
        edge_ids=cited,
        close_proposed_by=proposed_by,
    )


class AssignmentRefused(Exception):
    """An alert may not be given to that person; the message says why, in words."""


async def assign(
    store: AlertStore,
    graph: GraphPort,
    investigation_id: str,
    alert_id: str,
    member: Principal,
    *,
    assignee: str,
    allowed: set[str],
) -> Alert:
    """ADR-133 stage (a): give an open or claimed alert to one member of the case. `allowed` is the
    route's answer to who may be given work in this case (its Editors and Authors). Only a case
    alert (a typology alert, which every member of the case may read) is given to someone else: an
    alert shared with a team, or its owner's alone, may be read by people the case's member list
    does not show, so it is claimed by a person who can see it, never handed to one who may not."""
    row, _ = await _visible_row(store, graph, alert_id, investigation_id, member)
    if row.alert.status == "closed":
        raise AlertTriageConflict(alert_id)
    if assignee not in allowed:
        raise AssignmentRefused("That person is not a member of this case who can work on alerts.")
    if row.audience != "case" and assignee != member.id:
        raise AssignmentRefused(
            "An alert shared with a team, or its owner's alone, is claimed by someone who can see "
            "it; it cannot be given to another person."
        )
    return await store.set_queue_triage(
        alert_id, investigation_id, member, expect_status=["open", "claimed"], status="claimed",
        assignee=assignee,
    )  # fmt: skip


__all__ = [
    "AssignmentRefused",
    "CloseRefused",
    "approve_close",
    "assign",
    "canvas_elements",
    "claim",
    "dispose",
    "explain",
    "explain_with_evidence",
    "monitoring_queue",
    "node_name",
    "queue",
    "release",
    "send_back",
]
