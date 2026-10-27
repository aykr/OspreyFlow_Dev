"""Request/response shapes for `POST /v1/hotlists`, `POST /v1/monitors`, `GET /v1/alerts` and
`POST /v1/alerts/{alert_id}/jump` (Phase 7 Stage 6c, `06_DECISIONS.md` ADR-036/037/038/039) — the
same "route module owns its own request/response models, `app.py` owns wiring" split
`services/api/patterns.py` already establishes.

**`AlertView` redacts server-side, not left for the frontend to reconstruct.** `alerts.py`'s own
`evidence_available` re-check (ADR-039) is only half the discipline the bare `Alert` model can
enforce on its own: a `FULL` alert whose evidence has since become unavailable still carries its
original, real `referent_node_ids` on the stored row (ADR-039's own Addition 2 — the row stays,
marked unavailable, not purged). Returning that row as-is and *also* a separate `evidence_
available: bool` would hand the frontend two facts and trust it to combine them correctly on every
render path — exactly the shape a future component could get wrong by rendering the id and
skipping the flag, "a component that helpfully falls back to an id" reintroducing the leak past a
green API test. `_to_view` below does the redaction once, here, so `referent_node_ids` in the wire
response is authoritatively `[]` whenever `evidence_available` is `False`, and a renderer has
nothing left to get wrong.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Protocol

from pydantic import BaseModel

from ports.graph import GraphPort
from schemas.domain import Alert, AlertMode, Hotlist, Monitor, Node, Principal

from .alerts import evidence_available
from .evidence_brief import display_name
from .hotlists import HotlistNotFoundError
from .investigations import Investigation

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


class HotlistList(BaseModel):
    hotlists: list[Hotlist]


class CreateMonitorRequest(BaseModel):
    """`POST /v1/monitors`'s body. `pattern_id` must already be owned by the caller —
    `MonitorStore.create`'s own docstring: proven via `PatternStore.get_authorized` by the route,
    not re-derived inside the store from a second, independent ownership check."""

    pattern_id: str


class MonitorList(BaseModel):
    monitors: list[Monitor]


class AlertHotlist(BaseModel):
    """ADR-130 decision 1: the hotlist a `hotlist:` alert came from, read at display time and only
    for the hotlist's owner. The identifier is as typed (else as stored)."""

    identifier: str
    kept_as_written: bool
    review_date: date


class FiredFile(BaseModel):
    """One source file of a matched node: its name (the final path segment of the document id),
    and either the single `row` cited or, when there is more than one, how many `rows`."""

    name: str
    row: int | None = None
    rows: int | None = None


class FiredOn(BaseModel):
    """ADR-130 decision 1: what a matched node is, and where it was read from. `files` are in the
    order of first appearance, at most five; `more_files` counts the rest."""

    type: str
    label: str
    files: list[FiredFile]
    more_files: int


class AlertView(BaseModel):
    """The wire shape for an alert — see this module's own docstring for why `referent_node_ids`
    is redacted here rather than left alongside a separate `evidence_available` flag."""

    id: str
    rule_id: str
    owner_id: str
    mode: AlertMode
    referent_node_ids: list[str]
    evidence_available: bool
    investigation_id: str | None
    created_at: datetime
    #: ADR-110 Amendment 3: what the alert says in words — a scheduled run's notice is nothing
    #: but its words (a typology finding has them too); `None` for a hotlist or monitor match.
    words: str | None = None
    #: ADR-130 decision 1: present for a `hotlist:` rule, only to the hotlist's owner.
    hotlist: AlertHotlist | None = None
    #: ADR-130 decision 1: present only when the evidence is available to the reader (rule 3).
    fired_on: list[FiredOn] | None = None


class AlertList(BaseModel):
    alerts: list[AlertView]


class AlertJumpResult(BaseModel):
    """`POST /v1/alerts/{alert_id}/jump`'s response — `08_ACCEPTANCE_SCENARIOS.md` B14: "The new
    working set contains the alert's entities and a link to the originating investigation."
    `seeded_count` is how many referents the jumper could read and so seeded. There is no count
    of the rest (ADR-124 decision 1): a referent that became unreadable between the alert firing
    and the jump is left out of the new case, and how many were left out is a figure that points at
    what the jumper may not read."""

    investigation: Investigation
    seeded_count: int


class HotlistReader(Protocol):
    """The one read of `HotlistStore` the view needs, owner-checked by the store."""

    async def get_authorized(self, hotlist_id: str, principal: Principal) -> Hotlist: ...


def _file_name(document_id: str) -> str:
    return document_id.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or document_id


def _fired_on(node: Node) -> FiredOn:
    """Group the node's sources by file, in the order each file first appears. A file with one
    distinct locator that reads as `row N` says that row; otherwise it says how many rows."""
    locators: dict[str, list[str]] = {}
    for source in node.provenance.sources:
        seen = locators.setdefault(_file_name(source.document_id), [])
        if source.locator not in seen:
            seen.append(source.locator)
    files: list[FiredFile] = []
    for name, rows in locators.items():
        match = _ROW_LOCATOR.match(rows[0]) if len(rows) == 1 else None
        if match:
            files.append(FiredFile(name=name, row=int(match.group(1))))
        else:
            files.append(FiredFile(name=name, rows=len(rows)))
    return FiredOn(
        type=node.type,
        label=display_name(node),
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


async def alert_to_view(
    alert: Alert,
    principal: Principal,
    graph: GraphPort,
    hotlists_store: HotlistReader | None = None,
) -> AlertView:
    available = await evidence_available(alert, principal, graph)
    fired_on: list[FiredOn] | None = None
    if available and alert.mode is AlertMode.FULL and alert.referent_node_ids:
        nodes = [await graph.get_node(node_id, principal) for node_id in alert.referent_node_ids]
        # `evidence_available` read these a moment ago; one that has gone since is withdrawn whole.
        if all(node is not None for node in nodes):
            fired_on = [_fired_on(node) for node in nodes if node is not None]
    return AlertView(
        id=alert.id,
        rule_id=alert.rule_id,
        owner_id=alert.owner_id,
        mode=alert.mode,
        referent_node_ids=alert.referent_node_ids if available else [],
        evidence_available=available,
        investigation_id=alert.investigation_id,
        created_at=alert.created_at,
        words=alert.words,
        hotlist=await _alert_hotlist(alert, principal, hotlists_store),
        fired_on=fired_on,
    )


async def fetch_jumpable_referents(
    alert: Alert, *, principal: Principal, graph: GraphPort
) -> list[Node]:
    """The node-fetch half of the jump — `app.py`'s own route does the investigation-branch and
    working-set-seed calls, since both are already-established app.py-local orchestration
    (`branch_investigation`'s own `investigations.create`/`working_set.seed`/`publish_delta`/
    `_record_history_step` sequence, reused exactly, not reinvented here). This function is only
    the part specific to an alert: re-fetching each referent fresh, as `principal` — the viewer at
    jump time, never trusted from whatever `evidence_available` found true when the alert was
    listed moments earlier, the same "re-verify from the authoritative source" discipline every
    other read in this codebase already follows. A referent that no longer resolves is not an
    error: the jump proceeds with whatever is readable, and says nothing of how many were not
    (ADR-124 decision 1)."""
    readable: list[Node] = []
    for node_id in alert.referent_node_ids:
        node = await graph.get_node(node_id, principal)
        if node is not None:
            readable.append(node)
    return readable


__all__ = [
    "AlertHotlist",
    "AlertJumpResult",
    "AlertList",
    "AlertView",
    "CreateHotlistRequest",
    "CreateMonitorRequest",
    "FiredFile",
    "FiredOn",
    "HotlistList",
    "MonitorList",
    "alert_to_view",
    "fetch_jumpable_referents",
]
