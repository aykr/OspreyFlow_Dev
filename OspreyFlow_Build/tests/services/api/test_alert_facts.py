"""Alerts kept for alert trends (`spec/06_DECISIONS.md` ADR-134 decision 3): every alert the alert
store writes — raised, triaged, closed by a revert — is kept in the analytics store as it now is,
with every handling it rests on, and a hotlist's alerts are kept again when its owner changes its
audience. Real Postgres (a throwaway one) and the real DuckDB adapter, in memory; the graph is a fake
that answers as the adapter does (a hidden id is absent), reading the scheme's own rule.

What a mistake would do, and the case that catches it:
- an alert raised but never kept, or kept twice after a triage, so a trend is short or doubled —
  `test_a_raised_alert_is_kept_and_its_triage_replaces_it`;
- a hotlist taken back to "only me" still counted in the team's trends —
  `test_an_audience_change_reaches_the_trend_at_once`;
- an alert whose handlings were never recorded counted as if they were viewable —
  `test_an_alert_saved_without_its_handlings_is_counted_for_no_one`;
- a hotlist match kept without the handling of the node it matched, so a reader below it counts it
  — `test_a_hotlist_match_rests_on_the_node_it_matched`;
- a failing analytics store failing the alert itself — `test_a_failing_analytics_store_does_not_lose_the_alert`;
- an analytics store that missed writes never catching up — `test_every_alert_is_kept_again_at_start`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import duckdb
import pytest
from services.api.alerts import AlertStore, record_match
from services.api.config import PostgresConfig
from services.api.hotlists import HotlistStore

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme, principal_may_view
from schemas.analytics import AlertFact, AlertTrendRequest
from schemas.domain import (
    Alert,
    AlertMode,
    AuditStub,
    Handling,
    Interval,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

SCHEME = load_uk_le_scheme()
NOW = datetime.now(UTC)
WINDOW = Interval(valid_from=NOW - timedelta(days=30), valid_to=NOW + timedelta(days=1))


def _h(classification: str = "OFFICIAL") -> Handling:
    return Handling(classification=classification, handling_code="P", owning_unit="u", originator="u")


@pytest.fixture
def unit() -> str:
    return f"unit-{new_id()}"


@pytest.fixture
async def stores() -> AsyncIterator[tuple[AlertStore, HotlistStore, AnalyticsDuckDBAdapter]]:
    dsn = PostgresConfig.from_env().dsn
    hotlists = await HotlistStore.connect(dsn)
    alerts = await AlertStore.connect(dsn)
    con = duckdb.connect(":memory:")
    create_events_table(con)
    analytics = AnalyticsDuckDBAdapter(con, SCHEME)
    alerts.fact_sink = analytics.load_alert_facts
    yield alerts, hotlists, analytics
    await alerts.close()
    await hotlists.close()
    con.close()


def _person(unit: str, clearance: str = "OFFICIAL") -> Principal:
    return Principal(id=f"p-{new_id()}", clearance=clearance, org_unit=unit)


def _alert(owner: Principal, case: str, **fields: Any) -> Alert:
    values: dict[str, Any] = dict(
        id=new_id(), rule_id=f"typology:{new_id()}", owner_id=owner.id, mode=AlertMode.FULL,
        referent_node_ids=["n1"], investigation_id=case, created_at=NOW, typology="structuring",
        words="w",
    )  # fmt: skip
    values.update(fields)
    return Alert(**values)


async def _count(analytics: AnalyticsDuckDBAdapter, case: str, reader: Principal, **kw: Any) -> dict[str | None, float]:
    result = await analytics.alert_trend(
        AlertTrendRequest(investigation_scope=case, window=WINDOW, **kw), reader)
    totals: dict[str | None, float] = {}
    for p in result.points:
        totals[p.series] = totals.get(p.series, 0.0) + p.value
    return totals


async def test_a_raised_alert_is_kept_and_its_triage_replaces_it(stores: Any, unit: str) -> None:
    alerts, _, analytics = stores
    reader, case = _person(unit), f"case-{new_id()}"
    alert = _alert(reader, case)
    await alerts.save(alert, handlings=[_h()])
    assert await _count(analytics, case, reader, group_by="outcome") == {"open": 1.0}
    await alerts.set_triage(alert.id, case, expect_status=["open"], status="closed", assignee=reader.id,
                            disposition="true_positive", disposition_reason="r", decided_by=reader.id)  # fmt: skip
    assert await _count(analytics, case, reader, group_by="outcome") == {"true_positive": 1.0}, (
        "the triage replaced the kept alert: counted once, as it now is")
    await alerts.close_by_ids([alert.id], closed_by="x", at=NOW, reason="r")  # already closed: no change
    await alerts.close_for_elements(["n1"], [], closed_by="x", at=NOW, reason="r")
    assert await _count(analytics, case, reader, group_by="outcome") == {"true_positive": 1.0}


async def test_an_alert_closed_by_a_revert_is_kept_closed(stores: Any, unit: str) -> None:
    alerts, _, analytics = stores
    reader, case = _person(unit), f"case-{new_id()}"
    node = f"n-{new_id()}"
    alert = _alert(reader, case, referent_node_ids=[node])
    await alerts.save(alert, handlings=[_h()])
    await alerts.close_for_elements([node], [], closed_by="revert", at=NOW, reason="taken back")
    assert await _count(analytics, case, reader, group_by="outcome") == {"closed": 1.0}


async def test_an_audience_change_reaches_the_trend_at_once(stores: Any, unit: str) -> None:
    """ADR-133 ruling 3 through ADR-134 decision 2: shared with the team, a hotlist's alert is in a
    colleague's trend; taken back to "only me", it is in its owner's alone — at once."""
    alerts, hotlists, analytics = stores
    owner, colleague, case = _person(unit), _person(unit, "SECRET"), f"case-{new_id()}"
    hotlist = await hotlists.create(owner, identifier="+447700900111", review_date=date(2027, 1, 1),
                                    audience="only_me")  # fmt: skip
    alert = _alert(owner, None, rule_id=f"hotlist:{hotlist.id}", typology=None, words=None, team=unit)  # type: ignore[arg-type]
    await alerts.save(alert, handlings=[_h()])
    assert (await _count(analytics, case, owner), await _count(analytics, case, colleague)) == ({None: 1.0}, {})
    await hotlists.set_audience(hotlist.id, owner, "team")
    await alerts.publish_rule_facts(f"hotlist:{hotlist.id}")
    assert await _count(analytics, case, colleague, group_by="rule") == {"hotlists": 1.0}
    await hotlists.set_audience(hotlist.id, owner, "only_me")
    await alerts.publish_rule_facts(f"hotlist:{hotlist.id}")
    assert await _count(analytics, case, colleague) == {}


async def test_an_alert_saved_without_its_handlings_is_counted_for_no_one(stores: Any, unit: str) -> None:
    alerts, _, analytics = stores
    owner, case = _person(unit, "SECRET"), f"case-{new_id()}"
    await alerts.save(_alert(owner, case))
    assert await _count(analytics, case, owner) == {}


async def test_an_alert_on_a_secret_handling_is_not_counted_below_it(stores: Any, unit: str) -> None:
    alerts, _, analytics = stores
    low, high, case = _person(unit), _person(unit, "SECRET"), f"case-{new_id()}"
    await alerts.save(_alert(low, case), handlings=[_h(), _h("SECRET")])
    assert (await _count(analytics, case, low), await _count(analytics, case, high)) == ({}, {None: 1.0})


class _Graph:
    def __init__(self, nodes: dict[str, Handling]) -> None:
        self.nodes = nodes

    async def get_node(self, node_id: str, principal: Principal, **_: object) -> Node | None:
        handling = self.nodes.get(node_id)
        if handling is None or not principal_may_view(handling, principal, SCHEME):
            return None
        return Node(id=node_id, type="Phone", properties={}, handling=handling,
                    provenance=Provenance(state=ProvenanceState.ASSERTED, first_seen=NOW,
                                          sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")]),
                    audit=AuditStub(created_at=NOW, created_by="t"))  # fmt: skip


class _Audit:
    async def record(self, **_: object) -> None:
        return None


async def test_a_hotlist_match_rests_on_the_node_it_matched(stores: Any, unit: str) -> None:
    """`record_match` reads the matched node as the hotlist's owner, so it knows the node's handling:
    a SECRET-cleared owner's match on a SECRET node is not counted for an OFFICIAL colleague of the
    team it is shared with."""
    alerts, hotlists, analytics = stores
    owner, colleague, case = _person(unit, "SECRET"), _person(unit), f"case-{new_id()}"
    hotlist = await hotlists.create(owner, identifier="+447700900222", review_date=date(2027, 1, 1),
                                    audience="team")  # fmt: skip
    graph = _Graph({"phone": _h("SECRET")})
    await record_match(graph=graph, alert_store=alerts, audit=_Audit(), recipient=owner,  # type: ignore[arg-type]
                       rule_id=f"hotlist:{hotlist.id}", matched_identifier="+447700900222",
                       triggering_node_ids=["phone"], policy="strict", team=unit)  # fmt: skip
    assert await _count(analytics, case, owner) == {None: 1.0}
    assert await _count(analytics, case, colleague) == {}


async def test_a_failing_analytics_store_does_not_lose_the_alert(stores: Any, unit: str) -> None:
    alerts, _, _ = stores
    owner, case = _person(unit), f"case-{new_id()}"

    async def refuse(facts: list[AlertFact]) -> None:
        raise RuntimeError("analytics store away")

    alerts.fact_sink = refuse
    alert = _alert(owner, case)
    await alerts.save(alert, handlings=[_h()])
    assert (await alerts.get_case_alert(alert.id, case, owner)).id == alert.id


async def test_every_alert_is_kept_again_at_start(stores: Any, unit: str) -> None:
    alerts, _, analytics = stores
    owner, case = _person(unit), f"case-{new_id()}"
    alerts.fact_sink = None
    await alerts.save(_alert(owner, case), handlings=[_h()])
    assert await _count(analytics, case, owner) == {}
    alerts.fact_sink = analytics.load_alert_facts
    assert await alerts.publish_all_facts() >= 1
    assert await _count(analytics, case, owner) == {None: 1.0}
