"""The events behind one link — `06_DECISIONS.md` ADR-089. The service's own rule, against
`FakeWorkingSetStore` and an analytics stand-in that answers the filter it is given.

The rule under test is one sentence: the emails behind a link are readable by exactly the people
who can see the link, newest first and paged, and a link they cannot see answers as one that does
not exist. The analytics store's own refusals (a hidden event neither listed nor counted) are the
conformance suite's to prove (`tests/conformance/analytics_port`), not this file's; the stand-in
here keeps what it is asked, so this file proves the link-level gate and the request shape.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.investigations import AccessLevel, Investigation, InvestigationNotFoundError
from services.api.link_events import LinkEventsService
from services.api.link_notes import LinkNotFoundError
from services.api.working_set.service import WorkingSetService

from schemas.analytics import EventFilter, EventListRequest, EventListResult, EventRecord
from schemas.domain import Handling, Principal, Subgraph

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _event(edge_id: str, hour: int, subject: str, scope: str = "inv-1") -> EventRecord:
    return EventRecord(
        event_id=f"ev-{edge_id}-{hour}",
        edge_id=edge_id,
        edge_type="COMMUNICATED_WITH",
        source_id="a",
        target_id="b",
        occurred_at=datetime(2001, 5, 14, hour, tzinfo=UTC),
        direction="outbound",
        properties={"subject": subject, "excerpt": f"Body of {subject}"},
        investigation_scope=scope,
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
    )


def _in_scope(e: EventRecord, f: EventFilter) -> bool:
    """The conformance suite's rule for `investigation_scope` and `inherited`, restated."""
    if e.investigation_scope == f.investigation_scope:
        return True
    return (
        f.inherited is not None
        and e.investigation_scope in f.inherited.scopes
        and e.edge_id in f.inherited.edge_ids
    )


class RecordingAnalytics:
    """Answers the filter it is given from a fixed list, newest first; keeps the last request."""

    def __init__(self, events: list[EventRecord]) -> None:
        self.events = events
        self.last: EventListRequest | None = None

    async def list_events(self, req: EventListRequest, principal: Principal) -> EventListResult:
        self.last = req
        matching = sorted(
            (
                e
                for e in self.events
                if _in_scope(e, req.filter)
                and (not req.filter.edge_ids or e.edge_id in req.filter.edge_ids)
            ),
            key=lambda e: e.occurred_at,
            reverse=True,
        )
        page = matching[req.offset : req.offset + req.limit]
        return EventListResult(total=len(matching), events=page)


async def _service(
    events: list[EventRecord], investigations: object | None = None
) -> tuple[LinkEventsService, RecordingAnalytics]:
    working = FakeWorkingSetStore()
    await working.add_nodes("inv-1", [node("a"), node("b"), node("c", "SECRET")])
    await working.add_edges(
        "inv-1",
        [
            edge("e1", "a", "b"),
            edge("secret-link", "a", "b", "SECRET"),
            edge("secret-end", "a", "c"),
        ],
    )
    analytics = RecordingAnalytics(events)
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), candidate_count=0)
    service = LinkEventsService(
        WorkingSetService(graph, working, SCHEME),
        analytics,  # type: ignore[arg-type]
        investigations,  # type: ignore[arg-type]
    )
    await working.add_nodes("branch-1", [node("a"), node("b")])
    await working.add_edges("branch-1", [edge("e1", "a", "b")])
    return service, analytics


async def test_the_emails_behind_a_visible_link_come_newest_first_with_a_total() -> None:
    events = [_event("e1", h, f"Subject {h}") for h in range(5)] + [_event("other", 9, "Elsewhere")]
    service, analytics = await _service(events)
    page = await service.list("inv-1", "e1", ANALYST, offset=0, limit=2)
    assert page.total == 5
    assert [e.properties["subject"] for e in page.events] == ["Subject 4", "Subject 3"]
    assert (page.offset, page.limit) == (0, 2)
    # The request names the case and the link, and nothing else, so the store does the narrowing.
    assert analytics.last is not None
    assert analytics.last.filter.investigation_scope == "inv-1"
    assert analytics.last.filter.edge_ids == ["e1"]
    assert analytics.last.filter.node_ids == []
    last = await service.list("inv-1", "e1", ANALYST, offset=4, limit=2)
    assert [e.properties["subject"] for e in last.events] == ["Subject 0"]


async def test_a_link_with_no_events_lists_empty_with_a_total_of_zero() -> None:
    service, _ = await _service([])
    page = await service.list("inv-1", "e1", ANALYST)
    assert page.total == 0 and page.events == []


@pytest.mark.parametrize("edge_id", ["secret-link", "secret-end", "no-such-link"])
async def test_a_hidden_link_and_a_missing_link_refuse_identically(edge_id: str) -> None:
    service, analytics = await _service([_event("secret-link", 9, "Hidden")])
    with pytest.raises(LinkNotFoundError) as refused:
        await service.list("inv-1", edge_id, ANALYST)
    assert str(refused.value) == str(LinkNotFoundError(edge_id))
    # Nothing was asked of the analytics store for a link the person may not see.
    assert analytics.last is None


# --- a branch reads the emails its parent holds on the links it took (ADR-084 Amendment 2) ----


class _Cases:
    """`inv-1` is the original; `branch-1` was branched from it. `visible` says which the
    analyst may see; a case they may not see answers as one that does not exist."""

    def __init__(self, visible: set[str]) -> None:
        self.cases = {
            "inv-1": Investigation(
                id="inv-1",
                name="Enron",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                created_by="alice",
                owning_unit="unit-1",
            ),
            "branch-1": Investigation(
                id="branch-1",
                name="Enron · 2 selected",
                created_at=datetime(2026, 1, 2, tzinfo=UTC),
                created_by="alice",
                owning_unit="unit-1",
                branched_from="inv-1",
            ),
        }
        self.visible = visible

    async def get(self, investigation_id: str) -> Investigation:
        if investigation_id not in self.cases:
            raise InvestigationNotFoundError(investigation_id)
        return self.cases[investigation_id]

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        if investigation_id not in self.visible:
            raise InvestigationNotFoundError(investigation_id)
        return await self.get(investigation_id)


async def test_a_branch_lists_the_emails_its_parent_holds_on_that_link() -> None:
    """The defect the owner hit: on a branch tab, *Show emails (1)* listed nothing, because the
    emails were loaded under the original case and the branch asked only for its own."""
    events = [_event("e1", 9, "From the original", scope="inv-1")]
    service, analytics = await _service(events, _Cases({"inv-1", "branch-1"}))
    page = await service.list("branch-1", "e1", ANALYST)
    assert [e.properties["subject"] for e in page.events] == ["From the original"]
    assert analytics.last is not None and analytics.last.filter.inherited is not None
    assert analytics.last.filter.inherited.scopes == ["inv-1"]
    # Only the link asked about, not every link the branch holds.
    assert analytics.last.filter.inherited.edge_ids == ["e1"]


async def test_a_branch_reads_nothing_from_a_parent_the_analyst_cannot_see() -> None:
    events = [_event("e1", 9, "From the original", scope="inv-1")]
    service, analytics = await _service(events, _Cases({"branch-1"}))
    page = await service.list("branch-1", "e1", ANALYST)
    assert page.total == 0
    assert analytics.last is not None and analytics.last.filter.inherited is None


async def test_a_case_that_is_not_a_branch_reads_its_own_events_only() -> None:
    service, analytics = await _service([_event("e1", 9, "Own")], _Cases({"inv-1", "branch-1"}))
    await service.list("inv-1", "e1", ANALYST)
    assert analytics.last is not None and analytics.last.filter.inherited is None
