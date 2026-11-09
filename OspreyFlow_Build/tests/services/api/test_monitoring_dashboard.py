"""The monitoring dashboard's figures (`spec/06_DECISIONS.md` ADR-134 decision 2): beside `raised`,
`open_by_age` and `outcome`, the feed gains alerts raised per week by rule (each typology, hotlists
together, monitors together), closed per week by outcome, time to close, and hotlist matches per
week — every kind the one queue holds, counted as the reader, per case, through the same report the
Reports view reads and the same sync and mart.

Real Postgres (the alert and hotlist stores, a throwaway database); the graph is
`test_monitoring_queue.py`'s fake, which leaves a hidden id out of its answer as the adapter does.
`test_reports.py` holds the rest of the report against a live ArcadeDB.

What a mistake would do, and the case that catches it (ADR-134's two dashboard tests are the first
two):
- a hidden alert moving a dashboard figure — `test_a_hidden_alert_changes_no_dashboard_figure`;
- a hotlist kept "only me" counted beyond its owner —
  `test_an_only_me_hotlists_matches_are_in_its_owners_figures_and_no_one_elses`;
- the Alerts panel's or the team view's figures reaching beyond each alert's audience (another
  member of the team, another unit, another case's reader on the same dataset) —
  `test_the_panel_and_the_team_view_reach_only_each_alert_s_audience`;
- the sections counting the wrong thing — `test_the_sections_count_by_rule_outcome_time_and_match`;
- the feed leaving out a section, or carrying an alert's words — `test_the_feed_carries_the_new_sections_as_figures_only`;
- the typology figures the Reports view already showed widened to every kind by mistake —
  `test_the_typology_figures_still_count_typology_alerts_only`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from services.api import reports

from conduit_common.identity import new_id
from schemas.domain import ReportFigures
from tests.services.api.no_transactions import NO_TRANSACTIONS
from tests.services.api.test_monitoring_queue import (  # noqa: F401 — `stores`, `_fresh_units` are fixtures
    _alert,
    _fresh_units,
    _Graph,
    _hotlist,
    _person,
    stores,
)

NOW = datetime.now(UTC)
TODAY = NOW.date()
NAMES = {"n-a": "Alpha Ltd", "n-b": "Bravo Ltd", "n-secret": "Hidden"}


def _monday(moment: datetime) -> str:
    day = moment.date()
    return (day - timedelta(days=day.weekday())).isoformat()


async def _figures(alerts: Any, graph: _Graph, case: str, reader: Any) -> ReportFigures:
    return await reports.alert_report(
        alerts, graph, NO_TRANSACTIONS, case, reader, today=TODAY, period_weeks=12
    )


def _monitoring(figures: ReportFigures) -> dict[str, Any]:
    return figures.monitoring.model_dump(mode="json")


async def _three_kinds(
    hotlists: Any, alerts: Any, owner: Any, case: str, *, audience: str = "team"
) -> None:
    hotlist = await _hotlist(hotlists, owner, audience)
    raised = NOW - timedelta(days=2)
    for alert in (
        _alert("typology:r1", owner, investigation_id=case, typology="structuring", referent_node_ids=["n-a"],
               created_at=raised),
        _alert("typology:r2", owner, investigation_id=case, typology="rapid_movement", referent_node_ids=["n-b"],
               created_at=raised, status="closed", disposition="true_positive", decided_by=owner.id,
               decided_at=raised + timedelta(hours=3)),
        _alert(f"hotlist:{hotlist}", owner, referent_node_ids=["n-a"], team=owner.org_unit, created_at=raised),
        _alert("monitor:m1", owner, referent_node_ids=["n-b"], team=owner.org_unit, created_at=raised,
               status="closed", disposition="false_positive", decided_by=owner.id,
               decided_at=raised + timedelta(days=3)),
    ):  # fmt: skip
        await alerts.save(alert)


async def test_a_hidden_alert_changes_no_dashboard_figure(stores: Any) -> None:
    """ADR-134's test, as `test_a_hidden_alert_changes_no_figure` does for typology alerts: two
    cases identical but for alerts — one of each kind — naming a node the reader cannot see."""
    hotlists, alerts = stores
    owner = _person()
    seen, hidden_case = new_id(), new_id()
    for case in (seen, hidden_case):
        await _three_kinds(hotlists, alerts, owner, case)
    hotlist = await _hotlist(hotlists, owner, "team")
    for hidden in (
        _alert("typology:r3", owner, investigation_id=hidden_case, typology="structuring",
               referent_node_ids=["n-a", "n-secret"], created_at=NOW),
        _alert(f"hotlist:{hotlist}", owner, investigation_id=hidden_case, referent_node_ids=["n-secret"],
               team=owner.org_unit, created_at=NOW, status="closed", disposition="true_positive",
               decided_by=owner.id, decided_at=NOW),
    ):  # fmt: skip
        await alerts.save(hidden)
    # The hotlist alert of `hidden_case` names no case, so the reader reads it in either case: the
    # two must still agree, since it is hidden from them in both.
    graph = _Graph(NAMES, hidden={"n-secret"})
    with_hidden = await _figures(alerts, graph, hidden_case, owner)
    without = await _figures(alerts, _Graph(NAMES, hidden={"n-secret"}), seen, owner)
    assert _monitoring(with_hidden) == _monitoring(without)
    assert with_hidden.alerts_total == without.alerts_total


async def test_an_only_me_hotlists_matches_are_in_its_owners_figures_and_no_one_elses(
    stores: Any,
) -> None:
    hotlists, alerts = stores
    owner = _person()
    colleague, other_unit = _person(), _person("unit-b")
    case = new_id()
    mine = await _hotlist(hotlists, owner, "only_me")
    await alerts.save(_alert(f"hotlist:{mine}", owner, referent_node_ids=["n-a"], team=owner.org_unit,
                             created_at=NOW))  # fmt: skip
    graph = _Graph(NAMES)
    owners = (await _figures(alerts, graph, case, owner)).monitoring
    colleagues = (await _figures(alerts, graph, case, colleague)).monitoring
    assert sum(w.count for w in owners.hotlist_matches) == 1
    assert colleagues.hotlist_matches == [] and colleagues.raised_by_rule == []
    shared = await _hotlist(hotlists, owner, "team")
    await alerts.save(_alert(f"hotlist:{shared}", owner, referent_node_ids=["n-a"], team=owner.org_unit,
                             created_at=NOW))  # fmt: skip
    assert (
        sum(
            w.count
            for w in (await _figures(alerts, graph, case, colleague)).monitoring.hotlist_matches
        )
        == 1
    )
    assert (await _figures(alerts, graph, case, other_unit)).monitoring.hotlist_matches == []
    # The Alerts panel's and the team view's sections read the same queue (ADR-146 decision 9;
    # ADR-145 Amendment 4 decision 9): the shared hotlist's alert is the colleague's too, the "only
    # me" one never, and the other unit's reader has neither.
    colleagues = (await _figures(alerts, graph, case, colleague)).monitoring
    assert _opened(colleagues) == [("hotlists", "", "under a day", 1)]
    assert _team(colleagues) == [("hotlists", "", 1, 0, 0, 0, 0)]
    others = (await _figures(alerts, graph, case, other_unit)).monitoring
    assert _opened(others) == [] and _team(others) == []


def _opened(m: Any) -> list[tuple[str, str, str, int]]:
    return sorted((c.label, c.typology, c.age, c.count) for c in m.open_by_source if c.count)


def _team(m: Any) -> list[tuple[str, str, int, int, int, int, int]]:
    return sorted((t.label, t.typology, t.unassigned, t.mine, t.older_than_week, t.closed, t.not_of_interest)
                  for t in m.team)  # fmt: skip


async def test_the_panel_and_the_team_view_reach_only_each_alert_s_audience(stores: Any) -> None:
    """Rule 3 for the two L2.12 sections, by audience: the owner, a colleague of their team, a reader
    of another unit, and a reader of another case on the same dataset. An "only me" hotlist alert,
    claimed by its owner, is in the owner's panel and team view (as *mine*) and in no one else's; a
    case's typology alerts are in that case's figures alone."""
    hotlists, alerts = stores
    owner, colleague, other_unit, other_case = _person(), _person(), _person("unit-b"), _person()
    case, case_b = new_id(), new_id()
    await _three_kinds(hotlists, alerts, owner, case)
    only_me = await _hotlist(hotlists, owner, "only_me")
    await alerts.save(_alert(f"hotlist:{only_me}", owner, referent_node_ids=["n-b"], team=owner.org_unit,
                             created_at=NOW, status="claimed", assignee=owner.id))  # fmt: skip
    graph = _Graph(NAMES)
    typology = [
        ("typology", "rapid_movement", 0, 0, 0, 1, 0),
        ("typology", "structuring", 1, 0, 0, 0, 0),
    ]
    monitors = ("monitors", "", 0, 0, 0, 1, 1)

    owners = (await _figures(alerts, graph, case, owner)).monitoring
    assert _opened(owners) == [("hotlists", "", "1 to 7 days", 1), ("hotlists", "", "under a day", 1),
                               ("typology", "structuring", "1 to 7 days", 1)]  # fmt: skip
    assert _team(owners) == [("hotlists", "", 1, 1, 0, 0, 0), monitors, *typology]

    colleagues = (await _figures(alerts, graph, case, colleague)).monitoring
    assert _opened(colleagues) == [
        ("hotlists", "", "1 to 7 days", 1),
        ("typology", "structuring", "1 to 7 days", 1),
    ]
    assert _team(colleagues) == [("hotlists", "", 1, 0, 0, 0, 0), monitors, *typology]

    others = (await _figures(alerts, graph, case, other_unit)).monitoring
    # The other unit's reader of the same case: the case's typology alerts, all of them, and
    # nothing of the owner's team: pinned whole, not a subset (the orchestrator's review of
    # 211a6dc).
    assert _opened(others) == [("typology", "structuring", "1 to 7 days", 1)]
    assert _team(others) == typology

    # Another case's reader on the same dataset, in the same unit: the team's shared alerts are
    # theirs too; case's typology alerts and the "only me" alert are not.
    elsewhere = (await _figures(alerts, graph, case_b, other_case)).monitoring
    assert _opened(elsewhere) == [("hotlists", "", "1 to 7 days", 1)]
    assert _team(elsewhere) == [("hotlists", "", 1, 0, 0, 0, 0), monitors]


async def test_the_sections_count_by_rule_outcome_time_and_match(stores: Any) -> None:
    hotlists, alerts = stores
    owner = _person()
    case = new_id()
    await _three_kinds(hotlists, alerts, owner, case)
    m = (await _figures(alerts, _Graph(NAMES), case, owner)).monitoring
    week = _monday(NOW - timedelta(days=2))
    assert sorted((w.label, w.typology, w.week_start.isoformat(), w.count) for w in m.raised_by_rule) == [
        ("hotlists", "", week, 1), ("monitors", "", week, 1),
        ("typology", "rapid_movement", week, 1), ("typology", "structuring", week, 1)]  # fmt: skip
    closed = sorted((w.label, w.count) for w in m.closed_by_outcome)
    assert closed == [("false_positive", 1), ("true_positive", 1)]
    assert {c.label: c.value for c in m.time_to_close} == {
        "under a day": 1, "1 to 7 days": 1, "7 to 30 days": 0, "over 30 days": 0}  # fmt: skip
    assert [(w.label, w.count) for w in m.hotlist_matches] == [("hotlists", 1)]


async def test_the_typology_figures_still_count_typology_alerts_only(stores: Any) -> None:
    hotlists, alerts = stores
    owner = _person()
    case = new_id()
    await _three_kinds(hotlists, alerts, owner, case)
    figures = await _figures(alerts, _Graph(NAMES), case, owner)
    assert figures.alerts_total == 2
    assert {o.typology for o in figures.outcomes} == {"structuring", "rapid_movement"}


async def test_the_feed_carries_the_new_sections_as_figures_only(stores: Any) -> None:
    hotlists, alerts = stores
    owner = _person()
    case = new_id()
    await _three_kinds(hotlists, alerts, owner, case)
    figures = await _figures(alerts, _Graph(NAMES), case, owner)
    rows = reports.feed_rows(figures)
    sections = {r[0] for r in rows}
    assert {"raised", "open_by_age", "outcome", "raised_by_rule", "closed", "time_to_close",
            "hotlist_matches"} <= sections  # fmt: skip
    text = repr(rows)
    assert "Alpha" not in text and "Bravo" not in text and owner.id not in text, "figures only"
    assert ("hotlist_matches", "hotlists", "", _monday(NOW - timedelta(days=2)), 1) in rows
    assert isinstance(date.fromisoformat(next(r for r in rows if r[0] == "closed")[3]), date)
