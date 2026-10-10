"""*Neighbourhood risk* — contextual risk propagation (`06_DECISIONS.md` ADR-109 phase E; ruling
9's D4 defaults: 2 hops, ½ decay per hop, an alert counting for 90 days).

**A read, never a stored score** (rule 5 would make a stored propagated score model-derived data;
rule 3 would make it a leak, summed over links some readers cannot see). At each read: the
entity's neighbourhood out to two hops through `GraphPort.expand` as the reader (the access step on
every hop, so a hidden node is neither counted nor travelled through); the case's alerts the reader
may see whole (`alert_queue.queue`, ADR-039's all-or-nothing), less those past ninety days and those
a person closed as false positives; and `ComputePort.propagate` for the arithmetic. The reader's
score is therefore exactly the score of the graph they can see — the property
`tests/ingest/test_risk.py` was written to pin before this module existed.

**Never in part (rule 2):** a neighbourhood of more than `MAX_NEIGHBOURHOOD` nodes is refused in
words. **Disclosed cost:** the case's alerts are read and each checked for visibility at every
read; a case with many thousands of alerts makes this slow before it makes it wrong.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ports.compute import ComputePort
from ports.graph import GraphPort
from schemas.compute import PropagationRequest, StructureEdge, StructureNode
from schemas.domain import ExpandRequest, NeighbourhoodRisk, Principal, RiskContribution

from . import alert_queue
from .alerts import AlertStore
from .suppression import NodeNotVisibleError

MAX_HOPS = 2
DECAY = 0.5
WINDOW_DAYS = 90
#: The most nodes a neighbourhood read scores whole. A guess, disclosed as such.
MAX_NEIGHBOURHOOD = 5000


class NeighbourhoodTooLarge(Exception):
    """More of a neighbourhood than is scored whole: refused, never scored on a part (rule 2)."""


async def neighbourhood_risk(
    graph: GraphPort,
    compute: ComputePort,
    alert_store: AlertStore,
    investigation_id: str,
    node_id: str,
    reader: Principal,
    *,
    today: date,
) -> NeighbourhoodRisk:
    target = await graph.get_node(node_id, reader)
    if target is None:
        raise NodeNotVisibleError(node_id)
    around = await graph.expand(
        ExpandRequest(node_ids=[target.id], depth=MAX_HOPS, direction="both"), reader
    )
    # An alert's own node and links are not part of the entity's neighbourhood: risk travels
    # along what entities are to one another, not along the alerts raised about them.
    nodes = {n.id: n for n in around.nodes if n.type != "Alert"}
    nodes[target.id] = target
    if len(nodes) > MAX_NEIGHBOURHOOD:
        raise NeighbourhoodTooLarge(
            f"more than {MAX_NEIGHBOURHOOD:,} entities lie within {MAX_HOPS} hops; "
            "the neighbourhood is not scored in part"
        )
    edges = [e for e in around.edges if e.source in nodes and e.target in nodes]

    since = today - timedelta(days=WINDOW_DAYS)
    seeds: dict[str, float] = defaultdict(float)
    cited: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for queued in await alert_queue.queue(alert_store, graph, investigation_id, reader):
        alert = queued.alert
        if alert.created_at.date() < since:
            continue
        if alert.status == "closed" and alert.disposition == "false_positive":
            continue
        for ref in set(alert.referent_node_ids) & set(nodes):
            seeds[ref] += 1.0
            cited[ref].append((alert.id, queued.summary))

    result = await compute.propagate(
        PropagationRequest(
            target=target.id,
            nodes=[StructureNode(id=n.id, type=n.type) for n in nodes.values()],
            edges=[StructureEdge(id=e.id, source=e.source, target=e.target) for e in edges],
            seeds=dict(seeds),
            max_hops=MAX_HOPS,
            decay=DECAY,
        )
    )
    return NeighbourhoodRisk(
        node_id=target.id,
        score=result.score,
        max_hops=MAX_HOPS,
        decay=DECAY,
        window_days=WINDOW_DAYS,
        as_of=today,
        contributions=[
            RiskContribution(
                node_id=c.node_id,
                name=alert_queue.node_name(nodes[c.node_id]),
                hops=c.hops,
                alert_ids=[a for a, _ in cited[c.node_id]],
                summaries=[s for _, s in cited[c.node_id]],
                contribution=c.contribution,
            )
            for c in result.contributions
        ],
    )


__all__ = ["DECAY", "MAX_HOPS", "MAX_NEIGHBOURHOOD", "NeighbourhoodTooLarge", "WINDOW_DAYS",
           "neighbourhood_risk"]  # fmt: skip
