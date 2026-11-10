"""Request/response shapes for `POST /v1/hotlists` and `POST /v1/monitors` (Phase 7 Stage 6c,
`06_DECISIONS.md` ADR-036/037/038/039), and *what fired it* on a watch alert's explanation.

**The inbox is gone (ADR-146 decision 1, one queue).** `GET …/alerts` and `GET …/alerts/{id}`, the
reader's own alerts, were removed in L2.10: every alert of every source is in the one queue
(`/alert-queue`), and what the inbox alone said, ADR-130's *what fired it* (the hotlist's entry,
each matched node's files and rows), is on the queue's explanation (`with_what_fired_it`), which
is served only once the reader may see the whole alert (rule 3).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Protocol

from pydantic import BaseModel

from ontology.handling import sources_within_case
from schemas.domain import (
    Alert,
    AlertExplanation,
    AlertHotlist,
    AlertMode,
    FiredFile,
    FiredOn,
    Hotlist,
    HotlistAudience,
    Monitor,
    Node,
    Principal,
)

from .evidence_brief import display_name
from .hotlists import HotlistNotFoundError

#: ADR-130 decision 1: the most files named for one matched node. The rest are counted, never cut
#: silently (rule 2).
_MAX_FIRED_FILES = 5

_ROW_LOCATOR = re.compile(r"^row (\d+)$")


class CreateHotlistRequest(BaseModel):
    """`POST /v1/hotlists`'s body — `06_DECISIONS.md` ADR-038: "A list of identifiers with an
    owner and a review date." `identifier` is the same normalised `value_normalised` shape
    `Endpoint`'s own identifiers use — deliberately not validated against the graph at all
    (ADR-038's own "before it resolves to anything they can see")."""

    identifier: str
    review_date: date
    #: ADR-133 ruling 3: the owner's choice of whom its alerts reach; when left out, the
    #: deployment's `monitoring.hotlist_audience`. A choice other than that default is refused
    #: when the deployment does not let owners choose (`hotlist_audience_editable: false`).
    audience: HotlistAudience | None = None


class HotlistList(BaseModel):
    """The owner's hotlists, and the deployment's audience setting, so the Glass offers the choice
    only where it may be made (ADR-133 ruling 3)."""

    hotlists: list[Hotlist]
    audience_default: HotlistAudience = "only_me"
    audience_editable: bool = True


class CreateMonitorRequest(BaseModel):
    """`POST /v1/monitors`'s body. `pattern_id` must already be owned by the caller —
    `MonitorStore.create`'s own docstring: proven via `PatternStore.get_authorized` by the route,
    not re-derived inside the store from a second, independent ownership check."""

    pattern_id: str


class MonitorList(BaseModel):
    monitors: list[Monitor]


class HotlistReader(Protocol):
    """The one read of `HotlistStore` the view needs, owner-checked by the store."""

    async def get_authorized(self, hotlist_id: str, principal: Principal) -> Hotlist: ...


def _file_name(document_id: str) -> str:
    return document_id.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or document_id


def _fired_on(node: Node, principal: Principal) -> FiredOn:
    """Group the node's sources by whole document, in the order each first appears. A file with one
    distinct `row N` locator and nothing else says that row; otherwise it says how many `row N`
    rows and how many records of any other locator form."""
    label = display_name(node)
    if not sources_within_case(node.datasets, principal):
        return FiredOn(type=node.type, label=label, files=[], more_files=0, sources_withheld=True)
    locators: dict[str, list[str]] = {}
    for source in node.provenance.sources:
        seen = locators.setdefault(source.document_id, [])
        if source.locator not in seen:
            seen.append(source.locator)
    files: list[FiredFile] = []
    for document_id, cited in locators.items():
        name = _file_name(document_id)
        rows = [m for m in (_ROW_LOCATOR.match(c) for c in cited) if m]
        records = len(cited) - len(rows)
        if len(rows) == 1 and records == 0:
            files.append(FiredFile(name=name, row=int(rows[0].group(1))))
        else:
            files.append(FiredFile(name=name, rows=len(rows) or None, records=records or None))
    return FiredOn(
        type=node.type,
        label=label,
        files=files[:_MAX_FIRED_FILES],
        more_files=max(0, len(files) - _MAX_FIRED_FILES),
    )


async def _alert_hotlist(
    alert: Alert, principal: Principal, hotlists_store: HotlistReader | None
) -> AlertHotlist | None:
    if hotlists_store is None or not alert.rule_id.startswith("hotlist:"):
        return None
    try:
        hotlist_id = alert.rule_id.removeprefix("hotlist:")
        hotlist = await hotlists_store.get_authorized(hotlist_id, principal)
    except HotlistNotFoundError:
        return None
    return AlertHotlist(
        identifier=hotlist.identifier_typed or hotlist.identifier,
        kept_as_written=hotlist.identifier_canonical is False,
        review_date=hotlist.review_date,
    )


async def with_what_fired_it(
    explanation: AlertExplanation,
    principal: Principal,
    hotlists_store: HotlistReader | None,
) -> AlertExplanation:
    """ADR-146 decision 1: *what fired it* on every watch alert, in the one queue's explanation,
    since the inbox that said it is gone: the hotlist's entry (to its owner alone, ADR-130 decision
    1) and each matched node's files and rows. Only ever given an explanation already served to
    the reader whole (`alert_queue.explain`, rule 3), so every node here is one they may read."""
    alert = explanation.alert
    if explanation.kind not in ("hotlist", "monitor") or alert.mode is not AlertMode.FULL:
        return explanation
    nodes = {n.id: n for n in explanation.nodes}
    fired_on = [_fired_on(nodes[i], principal) for i in alert.referent_node_ids if i in nodes]
    return explanation.model_copy(
        update={
            "fired_on": fired_on or None,
            "hotlist": await _alert_hotlist(alert, principal, hotlists_store),
        }
    )


__all__ = [
    "CreateHotlistRequest",
    "CreateMonitorRequest",
    "HotlistList",
    "MonitorList",
    "with_what_fired_it",
]
