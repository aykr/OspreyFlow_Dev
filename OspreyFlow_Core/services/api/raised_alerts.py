"""*Raise an alert…* (`06_DECISIONS.md` ADR-146 decision 7, R4): an alert raised by hand, from
query results, a question's answer or the selection bar, to the case or to the case's dataset.

**Where it goes.**
- *This case*: its members read it, as any case alert (`rule_id` `analyst:case:<case>`, worked in
  the case).
- *The dataset*: raised into the dataset's home case (`analyst:dataset:<dataset>`, ADR-145
  Amendment 4 decision 2), in the queue of the home case and of every case reading the dataset
  (`alerts.queue_scope`); only the home case's Authors close it.

**Refused at the route, before anything is written (rule 3, rule 4).**
- A raiser who may not write the case (below Editor) is refused by the route's level check.
- A dataset the case does not read, an analyst layer, or one with no home case yet is refused in
  words that name only the dataset the raiser asked for.
- Every item it cites is read as the raiser, through the adapter's access step: one they may not
  read is answered as if it did not exist (404), whichever.
- A dataset alert may cite only the dataset's own items: a drawn item (in the case's layer, which
  only its case can see) is refused (409 `not_the_datasets_own`), so the form offers to promote it
  first or to raise the alert to this case only.

Its evidence is kept by reference (the items and the links), re-read as each reader at every read,
as any alert's (ADR-039); it names who raised it (`owner_id`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from conduit_common.identity import new_id
from ports.graph import GraphPort
from schemas.domain import Alert, AlertMode, Handling, Principal, RaiseAlertInput

from .alerts import AlertStore


class RaiseRefused(Exception):
    """Refused in words (409), naming only what the raiser asked for."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RaisedEvidenceNotFound(Exception):
    """An item the raiser may not read, answered as one that does not exist (404)."""


def dataset_alert_rule(dataset_id: str) -> str:
    return f"analyst:dataset:{dataset_id}"


def is_dataset_alert(alert: Alert) -> bool:
    return alert.rule_id.startswith("analyst:dataset:")


async def raise_alert(
    body: RaiseAlertInput,
    *,
    case_id: str,
    raiser: Principal,
    graph: GraphPort,
    store: AlertStore,
    home_case: str | None = None,
    dataset_is_readable: bool = True,
) -> Alert:
    """The alert raised, once every check has passed. `raiser` is scoped to the case's datasets;
    `home_case` is the dataset's home case for a dataset alert (`None`: it has none);
    `dataset_is_readable` says the case reads the dataset as a source or composite, not a layer."""
    if body.to == "dataset":
        if not dataset_is_readable or body.dataset_id not in (raiser.datasets or []):
            raise RaiseRefused(
                "dataset_not_writable",
                "This case cannot raise an alert to that dataset: it is not one the case reads.",
            )
        if home_case is None:
            raise RaiseRefused(
                "no_home_case",
                "That dataset has no home case yet, so its alerts have nowhere to go: raise this "
                "alert to the case instead.",
            )
    node_ids = sorted(set(body.node_ids))
    nodes = await graph.get_nodes(node_ids, raiser)
    if {n.id for n in nodes} != set(node_ids):
        raise RaisedEvidenceNotFound()
    edge_ids = sorted(set(body.edge_ids))
    edges = await graph.get_edges(edge_ids, raiser) if edge_ids else []
    if {e.id for e in edges} != set(edge_ids):
        raise RaisedEvidenceNotFound()
    if body.to == "dataset":
        if any(body.dataset_id not in (n.datasets or []) for n in nodes) or any(
            body.dataset_id not in (e.datasets or []) for e in edges
        ):
            raise RaiseRefused(
                "not_the_datasets_own",
                "A dataset alert may cite only the dataset's own items. Something selected is "
                "in this case alone (a drawn item): promote it first, or raise the alert to this "
                "case.",
            )
    words = f"{body.title}. {body.reason}"
    if body.found_by:
        words += f" Found by: {body.found_by}"
    alert = Alert(
        id=new_id(),
        rule_id=(
            dataset_alert_rule(body.dataset_id or "")
            if body.to == "dataset"
            else f"analyst:case:{case_id}"
        ),
        owner_id=raiser.id,
        mode=AlertMode.FULL,
        referent_node_ids=node_ids,
        edge_ids=edge_ids,
        investigation_id=home_case if body.to == "dataset" else case_id,
        created_at=datetime.now(UTC),
        dataset_id=body.dataset_id if body.to == "dataset" else None,
        words=words,
        severity=body.severity,
    )
    handlings: Sequence[Handling] = [*(n.handling for n in nodes), *(e.handling for e in edges)]
    await store.save(alert, handlings=handlings)
    return alert


__all__ = [
    "RaiseRefused",
    "RaisedEvidenceNotFound",
    "dataset_alert_rule",
    "is_dataset_alert",
    "raise_alert",
]
