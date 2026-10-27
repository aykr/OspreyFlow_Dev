"""The case team's alert queue and an alert's explanation (`06_DECISIONS.md` ADR-109 phase B).

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
from schemas.analytics import EventFilter, EventListRequest
from schemas.domain import (
    Alert,
    AlertExplanation,
    Edge,
    ExplainedTransaction,
    Node,
    Principal,
    ProvenanceState,
    QueuedAlert,
)

from .alerts import AlertNotFoundError, AlertStore, AlertTriageConflict

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
    """The finding in words, each entity named as the reader sees it, not by its id."""
    words = alert.words or alert.typology or "Alert"
    for node_id, node in nodes.items():
        words = words.replace(node_id, node_name(node))
    return words


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
    shown: list[QueuedAlert] = []
    for alert in await store.list_case_queue(investigation_id, reader):
        if statuses is not None and alert.status not in statuses:
            continue
        nodes = await _visible_nodes(alert, graph, reader)
        if nodes is None:
            continue
        shown.append(QueuedAlert(alert=alert, summary=summary_of(alert, nodes)))
    return shown


async def _visible_alert(
    store: AlertStore, graph: GraphPort, alert_id: str, investigation_id: str, reader: Principal
) -> tuple[Alert, dict[str, Node]]:
    alert = await store.get_case_alert(alert_id, investigation_id, reader)
    nodes = await _visible_nodes(alert, graph, reader)
    if nodes is None:
        raise AlertNotFoundError(alert_id)
    return alert, nodes


async def explain(
    store: AlertStore,
    graph: GraphPort,
    analytics: AnalyticsPort,
    investigation_id: str,
    alert_id: str,
    reader: Principal,
) -> AlertExplanation:
    alert, nodes = await _visible_alert(store, graph, alert_id, investigation_id, reader)
    edges = await _cited_edges(alert, graph, reader, list(nodes))
    if len({e.id for e in edges if e.type != "ALERTED_ON"}) < len(set(alert.edge_ids)):
        raise AlertNotFoundError(alert_id)
    transactions: list[ExplainedTransaction] = []
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
    return AlertExplanation(
        alert=alert,
        summary=summary_of(alert, nodes),
        nodes=list(nodes.values()),
        edges=edges,
        transactions=transactions,
    )


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
    return await store.set_triage(
        alert_id, investigation_id, expect_status=["open"], status="claimed", assignee=member.id
    )


async def release(
    store: AlertStore, graph: GraphPort, investigation_id: str, alert_id: str, member: Principal
) -> Alert:
    alert, _ = await _visible_alert(store, graph, alert_id, investigation_id, member)
    if alert.assignee not in (None, member.id):
        raise AlertTriageConflict(alert_id)
    return await store.set_triage(
        alert_id, investigation_id, expect_status=["claimed"], status="open", assignee=None
    )


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
    alert, nodes = await _visible_alert(store, graph, alert_id, investigation_id, member)
    if alert.status == "closed":
        raise AlertTriageConflict(alert_id)
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
    return await store.set_triage(
        alert_id,
        investigation_id,
        expect_status=["open", "claimed"],
        status="closed",
        assignee=alert.assignee or member.id,
        disposition=disposition,
        disposition_reason=reason,
        decided_by=member.id,
        alert_node_id=confirmed_node,
        edge_ids=cited,
    )


__all__ = ["canvas_elements", "claim", "dispose", "explain", "node_name", "queue", "release"]
