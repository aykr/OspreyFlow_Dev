"""ADR-146 (L2.10) in the Conduit, offline, the cases the lane-reviewer found untested:

- who answers for a dataset, read by the real `alert_routing.answers_for_datasets` (the home case
  and the reader's level there): `test_only_an_author_of_the_home_case_answers_for_its_dataset`;
- the acting lead (`leads_today`): `test_the_cover_leads_through_their_last_day_and_the_lead_after`;
- *Suppress until…* (Amendment 1): only the lead or cover, a reason, a day not past and at most 90
  days ahead; it ends by itself — `test_only_the_lead_suppresses_and_only_within_ninety_days`,
  `test_a_suppression_ends_by_itself_after_its_day`;
- the lead's hand-off: `test_the_lead_gives_a_team_alert_to_a_member_and_no_one_else_gives_it`;
- a dataset alert closed by its home case's Authors alone, failing closed:
  `test_a_dataset_alert_is_closed_by_the_home_cases_authors_alone`;
- a watched pattern on its own schedule (G16), matched as its owner within its dataset, so it alerts
  only on what its maker may see: `test_a_watch_runs_on_its_schedule_as_its_owner_within_its_dataset`,
  `test_a_scheduled_watch_alerts_only_on_what_its_maker_may_see`,
  `test_a_slot_the_identity_provider_could_not_answer_is_tried_again`.
Each red with its check removed at the real call site (`process/lanes/rules/l2.10/RED_RECORD.md`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from services.api import alert_queue
from services.api.alert_routing import answers_for_datasets, leads_today
from services.api.alerts import AlertTriageConflict, QueueRow
from services.api.evaluation import match_monitor
from services.api.investigations import AccessLevel
from services.api.monitor_schedule import MonitorScheduleExecutor

from principal_auth import PrincipalExchangeUnavailable, PrincipalRevoked
from schemas.admin import Team
from schemas.dataset_model import HomeCase
from schemas.domain import Alert, AlertMode, Monitor, Node, PatternQuery, Principal, SavedPattern, Subgraph
from tests.services.api.test_alert_evidence_withheld import CASE, TriageStore, _node, _world

NOW = datetime(2026, 11, 9, 9, tzinfo=UTC)
TODAY = NOW.date()
LEAD = Principal(id="lead", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst", "role:team-7"],
                 datasets=["ds-1"])  # fmt: skip
MEMBER = LEAD.model_copy(update={"id": "member"})


# --- who answers for a dataset ----------------------------------------------------------------


class _Homes:
    async def home_case_of(self, dataset_id: str) -> HomeCase | None:
        homes = {"ds-1": "home-1", "ds-2": "home-2"}
        return None if dataset_id not in homes else HomeCase(
            dataset_id=dataset_id, investigation_id=homes[dataset_id], made_at=NOW, made_by="m")


class _Levels:
    """`InvestigationStore.effective_level` as it answers: the reader's level on a case, or None."""

    def __init__(self, levels: dict[tuple[str, str], AccessLevel]) -> None:
        self.levels = levels

    async def effective_level(self, case: str, principal: Principal) -> AccessLevel | None:
        return self.levels.get((case, principal.id))


async def test_only_an_author_of_the_home_case_answers_for_its_dataset() -> None:
    reader = LEAD.model_copy(update={"datasets": ["ds-1", "ds-2", "ds-3"]})
    levels = _Levels({("home-1", "lead"): AccessLevel.AUTHOR, ("home-2", "lead"): AccessLevel.EDITOR})
    answers = await answers_for_datasets(_Homes(), levels)(reader)
    assert list(answers) == ["ds-1"], "an Editor of a home case, or a dataset with none, answers for nothing"
    assert list(await answers_for_datasets(_Homes(), levels)(reader.model_copy(update={"datasets": ["ds-2"]}))) == []


# --- the lead ---------------------------------------------------------------------------------


class _Teams:
    def __init__(self, team: Team) -> None:
        self._team = team

    async def team(self, role_id: str, today: date) -> Team | None:
        return self._team if role_id == self._team.role_id else None


async def test_the_cover_leads_through_their_last_day_and_the_lead_after() -> None:
    team = Team(role_id="team-7", display_name="Prison intel", mailbox="m@x", lead="lead", cover="member",
                cover_until=TODAY)  # fmt: skip
    assert await leads_today(_Teams(team), MEMBER, TODAY) == {"team-7"}
    assert await leads_today(_Teams(team), LEAD, TODAY) == set()
    assert await leads_today(_Teams(team), LEAD, TODAY + timedelta(days=1)) == {"team-7"}
    outsider = LEAD.model_copy(update={"roles": ["analyst"]})
    assert await leads_today(_Teams(team), outsider, TODAY + timedelta(days=1)) == set(), "a lead outside the role leads nothing"


# --- the lead's tools, through the queue's own checks -----------------------------------------


def _routed(**update: Any) -> Alert:
    return Alert(id="r1", rule_id="typology:r", owner_id="deployer", mode=AlertMode.FULL,
                 referent_node_ids=["n-a"], investigation_id=CASE, created_at=NOW, typology="sentence",
                 words="w", routed_team="team-7").model_copy(update=update)  # fmt: skip


class _TeamStore(TriageStore):
    """The queue's store for a team's alert, its writes recorded."""

    async def get_queue_alert(self, alert_id: str, investigation_id: str, reader: Principal) -> QueueRow:
        row = await super().get_queue_alert(alert_id, investigation_id, reader)
        return QueueRow(row.alert, "typology", "medium", "team")

    async def set_suppression(self, alert_id: str, *_: Any, until: date, reason: str) -> Alert:
        self.writes.append(f"suppress {alert_id} {until} {reason}")
        return next(a for a in self.alerts if a.id == alert_id)


def _team_world(alert: Alert) -> tuple[_TeamStore, Any, Any]:
    _, graph, analytics, _ = _world(set(), [alert])
    return _TeamStore([alert]), graph, analytics


async def test_only_the_lead_suppresses_and_only_within_ninety_days() -> None:
    store, graph, analytics = _team_world(_routed())

    async def suppress(who: Principal, lead_of: set[str], until: date) -> Any:
        return await alert_queue.suppress(store, graph, analytics, CASE, "r1", who, until=until,  # type: ignore[arg-type]
                                          reason="known", lead_of=lead_of, today=TODAY)  # fmt: skip

    await suppress(LEAD, {"team-7"}, TODAY + timedelta(days=90))
    assert store.writes == [f"suppress r1 {TODAY + timedelta(days=90)} known"]
    for who, lead_of, until in ((MEMBER, set(), TODAY + timedelta(days=1)),
                                (LEAD, {"team-7"}, TODAY + timedelta(days=91)),
                                (LEAD, {"team-7"}, TODAY - timedelta(days=1))):  # fmt: skip
        with pytest.raises(alert_queue.SuppressRefused):
            await suppress(who, lead_of, until)
    store2, graph2, analytics2 = _team_world(_routed(routed_team=None))
    with pytest.raises(alert_queue.SuppressRefused):
        await alert_queue.suppress(store2, graph2, analytics2, CASE, "r1", LEAD, until=TODAY,  # type: ignore[arg-type]
                                   reason="x", lead_of={"team-7"}, today=TODAY)  # fmt: skip
    assert len(store.writes) == 1 and store2.writes == []


def test_a_suppression_ends_by_itself_after_its_day() -> None:
    alert = _routed(suppressed_until=TODAY)
    assert alert_queue.suppressed_today(alert, TODAY) is True
    assert alert_queue.suppressed_today(alert, TODAY + timedelta(days=1)) is False


async def test_the_lead_gives_a_team_alert_to_a_member_and_no_one_else_gives_it() -> None:
    store, graph, analytics = _team_world(_routed())

    async def give(who: Principal, to: str, lead_of: set[str]) -> Any:
        return await alert_queue.assign(store, graph, analytics, CASE, "r1", who, assignee=to,  # type: ignore[arg-type]
                                        allowed=set(), lead_of=lead_of,
                                        team_members={"team-7": {"member"}})  # fmt: skip

    await give(LEAD, "member", {"team-7"})
    assert store.writes == ["triage r1"]
    with pytest.raises(alert_queue.AssignmentRefused, match="Only the team's lead"):
        await give(MEMBER, "lead", set())
    with pytest.raises(alert_queue.AssignmentRefused, match="not a member of the team"):
        await give(LEAD, "outsider", {"team-7"})
    await give(MEMBER, "member", set())  # a member claims it for themselves
    assert store.writes == ["triage r1", "triage r1"]


async def test_a_dataset_alert_is_closed_by_the_home_cases_authors_alone() -> None:
    alert = _routed(id="d1", rule_id="analyst:dataset:ds-1", typology=None, routed_team=None,
                    investigation_id=CASE)  # fmt: skip
    store, graph, analytics = _team_world(alert)

    async def close(closer: Any) -> Any:
        return await alert_queue.dispose(store, graph, analytics, CASE, "d1", MEMBER,  # type: ignore[arg-type]
                                         disposition="false_positive", reason="no", closer=closer)  # fmt: skip

    async def no(_: Alert) -> bool:
        return False

    async def yes(_: Alert) -> bool:
        return True

    for closer in (None, no):
        with pytest.raises(alert_queue.CloseRefused):
            await close(closer)
    assert store.writes == []
    await close(yes)
    assert store.writes == ["triage d1"]


# --- a watched pattern on its own schedule (G16) ----------------------------------------------


def _monitor(**update: Any) -> Monitor:
    return Monitor(id="mo-1", pattern_id="pat-1", owner_id="owner", created_at=NOW - timedelta(days=3),
                   dataset_id="ds-1").model_copy(update=update)  # fmt: skip


class _Monitors:
    def __init__(self, monitor: Monitor) -> None:
        self.monitor, self.slots, self.status = monitor, [], []  # type: ignore[var-annotated]

    async def list_all_active(self) -> list[Monitor]:
        return [self.monitor]

    async def last_slot(self, monitor_id: str) -> datetime | None:
        return NOW - timedelta(days=1, hours=4)

    async def record_slot(self, monitor_id: str, slot: datetime) -> None:
        self.slots.append(slot)

    async def set_status(self, monitor_id: str, status: str) -> None:
        self.status.append(status)


class _Valkey:
    def __init__(self) -> None:
        self.claims: set[str] = set()

    async def set(self, key: str, value: Any, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.claims:
            return False
        self.claims.add(key)
        return True

    async def delete(self, key: str) -> int:
        self.claims.discard(key)
        return 1

    async def get(self, key: str) -> None:
        return None


OWNER = Principal(id="owner", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


def _executor(monitors: _Monitors, valkey: _Valkey, resolve: Any) -> tuple[MonitorScheduleExecutor, list[Principal]]:
    matched: list[Principal] = []

    async def match(monitor: Monitor, owner: Principal) -> list[Alert]:
        matched.append(owner)
        return []

    return MonitorScheduleExecutor(monitors=monitors, valkey=valkey, resolve_owner=resolve, match=match), matched  # type: ignore[arg-type]


async def test_a_watch_runs_on_its_schedule_as_its_owner_within_its_dataset() -> None:
    async def resolve(owner_id: str) -> Principal:
        return OWNER

    for dataset, reads in (("ds-1", ["ds-1"]), (None, [])):
        monitors, valkey = _Monitors(_monitor(dataset_id=dataset)), _Valkey()
        executor, matched = _executor(monitors, valkey, resolve)
        await executor.tick(NOW)  # no load: the schedule alone runs it
        (who,) = matched
        assert (who.id, who.datasets) == ("owner", reads)
        assert len(monitors.slots) == 1
        await executor.tick(NOW)
        assert len(matched) == 1, "one run per slot"
    never, _ = _executor(_Monitors(_monitor(every="never")), _Valkey(), resolve)
    await never.tick(NOW)

    async def revoked(owner_id: str) -> Principal:
        raise PrincipalRevoked("gone")

    monitors = _Monitors(_monitor())
    executor, matched = _executor(monitors, _Valkey(), revoked)
    await executor.tick(NOW)
    assert matched == [] and monitors.status == ["stopped"]


async def test_a_slot_the_identity_provider_could_not_answer_is_tried_again() -> None:
    calls: list[int] = []

    async def flaky(owner_id: str) -> Principal:
        calls.append(1)
        if len(calls) == 1:
            raise PrincipalExchangeUnavailable("down")
        return OWNER

    monitors, valkey = _Monitors(_monitor()), _Valkey()
    executor, matched = _executor(monitors, valkey, flaky)
    await executor.tick(NOW)
    assert matched == [] and monitors.slots == []
    await executor.tick(NOW)
    assert [m.id for m in matched] == ["owner"] and len(monitors.slots) == 1


class _ScopedGraph:
    """`GraphPort.match` and `get_node` as the adapter answers them: only what the principal may see
    (its datasets here), a hidden node absent, never an error."""

    def __init__(self, nodes: dict[str, str]) -> None:
        self.nodes = nodes  # id -> dataset

    def _seen(self, principal: Principal) -> list[Node]:
        return [_node(i).model_copy(update={"datasets": [d]}) for i, d in self.nodes.items()
                if principal.datasets is None or d in principal.datasets]  # fmt: skip

    async def match(self, pattern: Any, principal: Principal) -> Subgraph:
        return Subgraph(nodes=self._seen(principal), edges=[])

    async def get_node(self, node_id: str, principal: Principal, **_: Any) -> Node | None:
        return next((n for n in self._seen(principal) if n.id == node_id), None)


class _Saved:
    async def get_authorized(self, pattern_id: str, principal: Principal) -> SavedPattern:
        return SavedPattern(id="s", pattern_id=pattern_id, version=1, name="Common contacts", owner_id=principal.id,
                            created_at=NOW, definition=PatternQuery(nodes=[], edges=[]))  # fmt: skip


class _Saves:
    def __init__(self) -> None:
        self.saved: list[Alert] = []

    async def save(self, alert: Alert, *, handlings: Any = None) -> None:
        self.saved.append(alert)


class _Audit:
    async def record(self, **_: Any) -> None:
        return None


async def test_a_scheduled_watch_alerts_only_on_what_its_maker_may_see() -> None:
    """A watch made from the Glass (*Save as a watch*) is matched as its maker within its dataset:
    what lies in another dataset is never in its alert. Red with the owner not confined to the
    watch's dataset by the executor."""
    graph = _ScopedGraph({"n-mine": "ds-1", "n-elsewhere": "ds-2"})
    saves = _Saves()

    async def resolve(owner_id: str) -> Principal:
        return OWNER  # unconfined as the identity provider gives it

    async def match(monitor: Monitor, owner: Principal) -> list[Alert]:
        return await match_monitor(monitor, owner, graph=graph, monitor_store=_Monitors(monitor),  # type: ignore[arg-type]
                                   pattern_store=_Saved(), alert_store=saves, audit=_Audit(),  # type: ignore[arg-type]
                                   valkey=_Valkey(), investigation_id=None)  # type: ignore[arg-type]  # fmt: skip

    executor = MonitorScheduleExecutor(monitors=_Monitors(_monitor()), valkey=_Valkey(),  # type: ignore[arg-type]
                                       resolve_owner=resolve, match=match)  # fmt: skip
    await executor.tick(NOW)
    (alert,) = saves.saved
    assert alert.referent_node_ids == ["n-mine"] and alert.owner_id == "owner"


async def test_a_suppression_on_a_closed_alert_is_refused() -> None:
    store, graph, analytics = _team_world(_routed(status="closed"))
    with pytest.raises((AlertTriageConflict, alert_queue.SuppressRefused)):
        await alert_queue.suppress(store, graph, analytics, CASE, "r1", LEAD, until=TODAY,  # type: ignore[arg-type]
                                   reason="x", lead_of={"team-7"}, today=TODAY)  # fmt: skip


def test_a_routed_rules_run_counts_are_its_teams_alone() -> None:
    """Rule 7: a scheduled run of a rule routed to a team says how many alerts it raised to the
    team's members, and to anyone else only that it ran. Red with `runs_for_reader` returning the
    runs as stored."""
    from services.api.rule_schedule import runs_for_reader

    from schemas.monitoring import RuleRun
    from schemas.sentences import RuleSentence, SentenceRuleParams
    from schemas.domain import TypologyRule

    sentence = RuleSentence.model_validate({"subject": "Person", "team": "team", "team_id": "team-7"})
    rule = TypologyRule(id="r", investigation_id=CASE, owner_id="author", name="Listed", created_at=NOW,
                        trigger="post_commit", params=SentenceRuleParams(pattern_id="p", sentence=sentence))  # fmt: skip
    run = RuleRun(id="run", rule_id="r", rule_version=1, slot=NOW, ran_at=NOW, run_as="author", outcome="ran",
                  alerts=3, words="Ran as author over the last day: 3 alert(s) raised.")  # fmt: skip
    (inside,) = runs_for_reader(rule, [run], LEAD)
    (outside,) = runs_for_reader(rule, [run], LEAD.model_copy(update={"roles": ["analyst"]}))
    assert inside.alerts == 3
    assert outside.alerts == 0 and "3" not in outside.words
