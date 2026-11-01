"""Monitoring in the Prison Intelligence storyline (`spec/06_DECISIONS.md` ADR-127 Amendment 41;
`process/ALERTING_MONITORING_PLAN.md` P1 to P4): chapter 9 raises exactly three alerts, in order,
and chapters 10 and 11 count, close and pack them — each as the reader may see it (rules 3, 4, 7).

The files are the seed's and the two monitoring batches, loaded through the committed recipes; each
chapter-9 load runs as the run route runs it (`pid_monitoring_support.run_chapter_9_file`): the
case's rules after commit, then the hotlists over the run's touched nodes. Real Postgres (a database
of this module's own, dropped after) holds the hotlists and the alerts; real DuckDB, through the
adapter's `load_alert_facts`, the alert facts; the graph answers as the adapter does (the support
module says how, and what it does not model).

**The storyline** (`story`, run once per scenario): the analyst hotlists 07700 900640 ("only me");
batch 2 loads (H1); the bookings load (H2); the analyst deploys "Calls to a number on a seized
handset" (`pid_monitoring.P1_SENTENCE`); the PIN first contacts load (S1). Then chapter 10's closes:
H2 by its owner as *Referred*; S1 proposed as *Referred* by the analyst and approved by a second
analyst. H1 stays open.

What each case would catch (the amendment names each):
- P1 and P2 together: an alert more or fewer, or out of order —
  `test_chapter_nine_raises_exactly_these_alerts_in_this_order`;
- P2: the bookings not touching the hotlisted number, or raising after the visit —
  `test_the_bookings_raise_one_hotlist_alert_before_the_visit`; a hotlist judging a load it did not
  exist for — `test_a_hotlist_added_after_the_bookings_load_raises_nothing`; a hotlist judging
  another dataset's nodes — `test_a_hotlist_made_in_another_dataset_raises_nothing`; an "only me"
  alert shown to anyone else — `test_another_analyst_does_not_see_the_owners_hotlist_alerts`;
- P1: the rule not firing on the number Pryce's handset called —
  `test_the_new_contacts_raise_one_alert_on_the_number_from_pryces_handset`; a rule judging a load
  made before it — `test_a_rule_deployed_after_the_new_contacts_load_raises_nothing_for_it`; a rule
  judging beyond its author's datasets — `test_a_rule_author_without_the_dataset_raises_nothing`;
  a file loaded twice alerting twice — `test_a_second_run_of_the_new_contacts_raises_nothing`; an
  alert shown outside its dataset — `test_a_reader_without_the_dataset_sees_no_chapter_nine_alert`;
- P3: the alert trend miscounting — `test_the_weekly_alert_trend_counts_chapter_nines_alerts_by_rule`,
  or counting what the reader may not see — `test_the_alert_trend_counts_nothing_for_a_reader_without_the_dataset`,
  `test_a_colleague_counts_only_the_case_alert_in_the_trend`; the pack item losing its open,
  inferred state — `test_chapter_nines_alert_goes_into_the_pack_open_and_inferred`, or shown to a
  reader who may not see the number — `test_the_alert_item_is_withheld_from_a_reader_who_may_not_see_the_number`;
- P4: the monitoring figures miscounting — `test_the_monitoring_figures_count_raised_closed_and_the_open_queue`;
  the proposer approving their own close — `test_the_proposer_cannot_approve_their_own_close`; an
  "only me" hotlist on anyone else's board — `test_the_board_never_counts_the_owners_only_me_hotlist`;
  a reader without the dataset counting anything — `test_a_reader_without_the_dataset_counts_nothing_on_the_board`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import asyncpg
import duckdb
import pytest
import pytest_asyncio
from services.api import alert_queue, packs, reports
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.hotlists import HotlistStore
from services.api.pattern_store import PatternNotFoundError
from services.api.rule_sentences import compile_pattern
from tests.scenarios import pid_monitoring_support as support
from tests.scenarios.pid_monitoring_support import (
    DATASET,
    ONTOLOGY,
    SCHEME,
    Audit,
    SignatureSet,
    Stores,
    World,
    run_chapter_9_file,
)

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table
from conduit_common.identity import new_id
from demo_fixtures import pid_files, pid_monitoring
from schemas.analytics import AlertTrendRequest, TrendInterval
from schemas.domain import Interval, Principal, SavedPattern, TypologyRule
from schemas.sentences import RuleSentence, SentenceRuleParams

pytestmark = [pytest.mark.asyncio(loop_scope="module")]

COORDINATOR_NUMBER = "+447700900640"
UNIDENTIFIED_NUMBER = "+447700900718"
OTHER_DATASET = "another-dataset"
REVIEW = date(2026, 8, 1)


# --- The module's stores -----------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _staged_locally() -> Iterator[None]:
    with support.local_staging():
        yield


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def dsn() -> AsyncIterator[str]:
    """A database of this module's own on the throwaway Postgres: `list_all_active` reads every
    hotlist in a database, so another module's hotlists must not be in it."""
    base = PostgresConfig.from_env()
    name = f"pid_monitoring_{new_id().replace('-', '')[:16]}"
    admin = await asyncpg.connect(base.dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    yield base.dsn.rsplit("/", 1)[0] + f"/{name}"
    admin = await asyncpg.connect(base.dsn)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def base(dsn: str) -> World:
    return await support.base_world()


@dataclass
class Scene:
    """One run of chapter 9 in a case of its own, with its own people."""

    world: World
    stores: Stores
    analytics: AnalyticsDuckDBAdapter
    case: str
    analyst: Principal
    colleague: Principal
    stranger: Principal
    alerts_raised: list[Any] = field(default_factory=list)
    loaded: dict[str, Any] = field(default_factory=dict)
    rule: TypologyRule | None = None
    hotlist: Any = None


def _analyst(unit: str, **update: Any) -> Principal:
    return Principal(
        id=f"analyst-{new_id()}", clearance="OFFICIAL", org_unit=unit, roles=["analyst"],
        datasets=[DATASET],
    ).model_copy(update=update)  # fmt: skip


@pytest_asyncio.fixture(loop_scope="module")
async def scene(base: World, dsn: str) -> AsyncIterator[Scene]:
    hotlists = await HotlistStore.connect(dsn)
    alerts = await AlertStore.connect(dsn)
    con = duckdb.connect(":memory:")
    create_events_table(con)
    analytics = AnalyticsDuckDBAdapter(con, SCHEME)
    alerts.fact_sink = analytics.load_alert_facts
    unit = f"verify-{new_id()}"
    analyst, colleague = _analyst(unit), _analyst(unit)
    stranger = _analyst(unit, datasets=[OTHER_DATASET])
    stores = Stores(
        hotlists=hotlists,
        alerts=alerts,
        valkey=SignatureSet(),
        audit=Audit(),
        principals={p.id: p for p in (analyst, colleague)},
    )
    case = f"pid-case-{new_id()}"
    yield Scene(base.copy(), stores, analytics, case, analyst, colleague, stranger)
    await alerts.close()
    await hotlists.close()
    con.close()


class _Patterns:
    """The rule's drawn pattern, read as its author alone (`PatternStore.get_authorized`'s refusal:
    anyone else is told it is not found)."""

    def __init__(self, rule: TypologyRule) -> None:
        assert isinstance(rule.params, SentenceRuleParams)
        self.rule = rule
        self.pattern = compile_pattern(rule.params.sentence, ONTOLOGY)

    async def get_authorized(self, pattern_id: str, principal: Principal) -> SavedPattern:
        if principal.id != self.rule.owner_id or pattern_id != self.rule.params.pattern_id:  # type: ignore[union-attr]
            raise PatternNotFoundError(pattern_id)
        return SavedPattern(id=f"saved-{pattern_id}", pattern_id=pattern_id, version=1,
                            name=f"Rule: {self.rule.name}", owner_id=self.rule.owner_id,
                            created_at=datetime.now(UTC), definition=self.pattern)  # fmt: skip


def p1_rule(scene: Scene, *, dataset: str = DATASET) -> TypologyRule:
    """The analyst's rule as the sentence builder deploys it (ADR-133 Amendment 2): typology
    `sentence`, its drawn pattern saved as theirs, in the case's dataset."""
    return TypologyRule(
        id=f"rule-{new_id()}",
        investigation_id=scene.case,
        owner_id=scene.analyst.id,
        name=pid_monitoring.P1_RULE_NAME,
        created_at=datetime.now(UTC),
        trigger="post_commit",
        dataset_id=dataset,
        params=SentenceRuleParams(
            pattern_id=f"pattern-{new_id()}",
            sentence=RuleSentence.model_validate(dict(pid_monitoring.P1_SENTENCE)),
        ),
    )


async def load(scene: Scene, file: str, *, rule: TypologyRule | None = None) -> Any:
    loaded = await run_chapter_9_file(
        scene.world, file, scene.stores, case=scene.case,
        rules=[rule] if rule is not None else [],
        patterns=_Patterns(rule) if rule is not None else None,
    )  # fmt: skip
    scene.loaded[file] = loaded
    return loaded


async def hotlist_coordinator(scene: Scene, owner: Principal | None = None) -> Any:
    scene.hotlist = await scene.stores.hotlists.create(
        owner or scene.analyst, identifier="07700 900640", review_date=REVIEW
    )
    return scene.hotlist


async def queue(scene: Scene, reader: Principal) -> list[Any]:
    rows = await alert_queue.monitoring_queue(
        scene.stores.alerts, scene.world.graph, scene.case, reader
    )
    return sorted(rows, key=lambda q: q.alert.created_at)


async def story(scene: Scene, *, close: bool = True) -> Scene:
    """Chapter 9 as the script runs it, then chapter 10's closes."""
    await hotlist_coordinator(scene)
    await load(scene, pid_files.BATCH_2)
    await load(scene, pid_monitoring.VISIT_BOOKINGS)
    scene.rule = p1_rule(scene)
    await load(scene, pid_monitoring.PIN_NEW_CONTACTS, rule=scene.rule)
    if close:
        h2, s1 = (await queue(scene, scene.analyst))[1:3]
        store, graph = scene.stores.alerts, scene.world.graph
        await alert_queue.dispose(
            store, graph, scene.case, h2.alert.id, scene.analyst, disposition="referred",
            reason="To the visits team: the visit goes ahead under closed conditions.",
        )  # fmt: skip
        proposed = await alert_queue.dispose(
            store, graph, scene.case, s1.alert.id, scene.analyst, disposition="referred",
            reason="To the regional intelligence unit for a subscriber check on 07700 900718.",
        )  # fmt: skip
        assert proposed.status == "closing", "a high-severity case alert waits for a second person"
        await alert_queue.approve_close(store, graph, scene.case, s1.alert.id, scene.colleague)
    return scene


def number_of(scene: Scene, queued: Any) -> str:
    (node_id,) = queued.alert.referent_node_ids
    return str(scene.world.graph.nodes[node_id].properties["value_normalised"])


def _kind(queued: Any) -> str:
    return "sentence" if queued.alert.typology == "sentence" else queued.kind


# --- P1 and P2 together: chapter 9's three alerts ----------------------------------------------


async def test_chapter_nine_raises_exactly_these_alerts_in_this_order(scene: Scene) -> None:
    await story(scene, close=False)
    raised = await queue(scene, scene.analyst)
    assert [(_kind(q), number_of(scene, q)) for q in raised] == [
        (e.kind, e.number) for e in pid_monitoring.EXPECTED_ALERTS
    ]
    h1, h2, s1 = raised
    assert h1.alert.rule_id == h2.alert.rule_id == f"hotlist:{scene.hotlist.id}"
    assert (h1.severity, h1.audience) == (h2.severity, h2.audience) == ("high", "owner")
    assert s1.alert.rule_id == f"typology:{scene.rule.id}"  # type: ignore[union-attr]
    assert (s1.severity, s1.audience, s1.alert.dataset_id) == ("high", "case", DATASET)
    # Each load raised exactly its own: batch 2 and the bookings by the hotlist, the new contacts
    # by the rule — and nothing else anywhere in the store.
    hotlisted = [len(scene.loaded[f].hotlist_alerts) for f in
                 (pid_files.BATCH_2, pid_monitoring.VISIT_BOOKINGS, pid_monitoring.PIN_NEW_CONTACTS)]  # fmt: skip
    assert hotlisted == [1, 1, 0]
    assert scene.loaded[pid_monitoring.PIN_NEW_CONTACTS].rule_notes == [
        f"Rule “{pid_monitoring.P1_RULE_NAME}” raised 1 alert(s)."
    ]
    assert len(await scene.stores.alerts.list_authorized(scene.analyst)) == 3


# --- P2: the bookings ----------------------------------------------------------------------------


async def test_the_bookings_raise_one_hotlist_alert_before_the_visit(scene: Scene) -> None:
    await hotlist_coordinator(scene)
    loaded = await load(scene, pid_monitoring.VISIT_BOOKINGS)
    (alert,) = loaded.hotlist_alerts
    graph = scene.world.graph
    number = graph.node_by_value(COORDINATOR_NUMBER)
    assert alert.referent_node_ids == [number.id]
    assert alert.rule_id == f"hotlist:{scene.hotlist.id}" and alert.owner_id == scene.analyst.id
    # The booking is a record the number is mentioned in; no visit is written, since none happened.
    (booking,) = [n for n in graph.live_nodes.values() if n.properties.get("message_id") == "VB-2605-001"]
    mentioned = {e.source for e in graph.committed_edges
                 if e.type == "MENTIONED_IN" and e.target == booking.id}  # fmt: skip
    assert number.id in mentioned and len(mentioned) == 3
    assert booking.properties["title"].endswith("Saturday 9 May 2026 at 14:00")
    assert not [e for e in graph.committed_edges if e.type == "VISITED" and e.load_id == loaded.report.load_id]
    assert alert.created_at is not None  # raised by the load itself


async def test_a_hotlist_added_after_the_bookings_load_raises_nothing(scene: Scene) -> None:
    loaded = await load(scene, pid_monitoring.VISIT_BOOKINGS)
    await hotlist_coordinator(scene)
    assert loaded.hotlist_alerts == []
    assert await queue(scene, scene.analyst) == []


async def test_a_hotlist_made_in_another_dataset_raises_nothing(scene: Scene) -> None:
    elsewhere = scene.analyst.model_copy(update={"datasets": [OTHER_DATASET]})
    scene.stores.principals[elsewhere.id] = elsewhere
    await hotlist_coordinator(scene, owner=elsewhere)
    loaded = await load(scene, pid_monitoring.VISIT_BOOKINGS)
    assert loaded.hotlist_alerts == []


async def test_another_analyst_does_not_see_the_owners_hotlist_alerts(scene: Scene) -> None:
    await story(scene, close=False)
    colleague = [_kind(q) for q in await queue(scene, scene.colleague)]
    assert colleague == ["sentence"], "the hotlist is the owner's alone; the rule's is the case's"
    assert await queue(scene, scene.stranger) == []


# --- P1: the new contacts ------------------------------------------------------------------------


async def test_the_new_contacts_raise_one_alert_on_the_number_from_pryces_handset(scene: Scene) -> None:
    await load(scene, pid_files.BATCH_2)
    await load(scene, pid_monitoring.VISIT_BOOKINGS)
    rule = p1_rule(scene)
    loaded = await load(scene, pid_monitoring.PIN_NEW_CONTACTS, rule=rule)
    (s1,) = await queue(scene, scene.analyst)
    assert number_of(scene, s1) == UNIDENTIFIED_NUMBER
    assert (s1.alert.typology, s1.severity, s1.audience) == ("sentence", "high", "case")
    graph = scene.world.graph
    # A sentence has one subject, the number; the handset it is near is named as the Glass names a
    # node with no name of its own (`node_name`: its type and the tail of its id).
    handset = next(n for n in graph.live_nodes.values() if n.type == "Device"
                   and str(n.properties.get("imei", "")).startswith("00182304241345"))  # fmt: skip
    assert s1.alert.words.startswith(
        f"+447700900718 (Endpoint): within 2 step(s) of Device {handset.id[-6:]}. "
        "When an Endpoint whose endpoint kind is msisdn, is within 2 step(s) of a Device"
    )
    # Its `Alert` node and link are the load's own: the reset's revert takes them back.
    assert s1.alert.alert_node_id is not None
    alert_node = graph.nodes[s1.alert.alert_node_id]
    assert alert_node.provenance.state.value == "inferred"
    assert loaded.report.rows_already_loaded == 0 and loaded.report.edges_created == 11  # 14 calls on 11 new pairs
    darren = graph.node_by_value("PIN-Z2558ZZ")
    number = graph.node_by_value(UNIDENTIFIED_NUMBER)
    assert [e for e in graph.committed_edges if e.type == "COMMUNICATED_WITH"
            and (e.source, e.target) == (darren.id, number.id)], "Darren Ashcombe's account called it"  # fmt: skip


async def test_a_rule_deployed_after_the_new_contacts_load_raises_nothing_for_it(scene: Scene) -> None:
    await load(scene, pid_files.BATCH_2)
    await load(scene, pid_monitoring.VISIT_BOOKINGS)
    loaded = await load(scene, pid_monitoring.PIN_NEW_CONTACTS)
    scene.rule = p1_rule(scene)  # deployed now: it judges later loads, never this one
    assert loaded.rule_notes == [] and await queue(scene, scene.analyst) == []


async def test_a_rule_author_without_the_dataset_raises_nothing(scene: Scene) -> None:
    await load(scene, pid_files.BATCH_2)
    await load(scene, pid_monitoring.VISIT_BOOKINGS)
    rule = p1_rule(scene, dataset=OTHER_DATASET)  # judged as its author, within its own dataset
    loaded = await load(scene, pid_monitoring.PIN_NEW_CONTACTS, rule=rule)
    assert loaded.rule_notes == []
    assert await scene.stores.alerts.list_authorized(scene.analyst) == []


async def test_a_second_run_of_the_new_contacts_raises_nothing(scene: Scene) -> None:
    await load(scene, pid_files.BATCH_2)
    await load(scene, pid_monitoring.VISIT_BOOKINGS)
    rule = p1_rule(scene)
    await load(scene, pid_monitoring.PIN_NEW_CONTACTS, rule=rule)
    again = await load(scene, pid_monitoring.PIN_NEW_CONTACTS, rule=rule)
    assert again.report.rows_already_loaded == 14 and again.rule_notes == []
    assert len(await queue(scene, scene.analyst)) == 1


async def test_a_reader_without_the_dataset_sees_no_chapter_nine_alert(scene: Scene) -> None:
    await story(scene)
    assert await queue(scene, scene.stranger) == []
    assert await scene.stores.alerts.list_authorized(scene.stranger) == []


# --- P3: the alert trend and the pack item -------------------------------------------------------


def _trend_request(scene: Scene) -> AlertTrendRequest:
    now = datetime.now(UTC)
    return AlertTrendRequest(
        investigation_scope=scene.case,
        window=Interval(valid_from=now - timedelta(days=14), valid_to=now + timedelta(days=1)),
        interval=TrendInterval.WEEK,
        group_by="rule",
    )


async def test_the_weekly_alert_trend_counts_chapter_nines_alerts_by_rule(scene: Scene) -> None:
    await story(scene)
    trend = await scene.analytics.alert_trend(_trend_request(scene), scene.analyst)
    series = {p.series: p.value for p in trend.points}
    assert series == {"hotlists": 2.0, f"typology:{scene.rule.id}": 1.0}  # type: ignore[union-attr]
    assert len({p.period_start for p in trend.points}) == 1, "the demo's own week"


async def test_the_alert_trend_counts_nothing_for_a_reader_without_the_dataset(scene: Scene) -> None:
    await story(scene)
    trend = await scene.analytics.alert_trend(_trend_request(scene), scene.stranger)
    assert trend.points == [] and trend.total == 0


async def test_a_colleague_counts_only_the_case_alert_in_the_trend(scene: Scene) -> None:
    await story(scene)
    trend = await scene.analytics.alert_trend(_trend_request(scene), scene.colleague)
    assert {p.series: p.value for p in trend.points} == {f"typology:{scene.rule.id}": 1.0}  # type: ignore[union-attr]


async def _h1_item(scene: Scene) -> Any:
    h1 = (await queue(scene, scene.analyst))[0]
    explained, events = await alert_queue.explain_with_evidence(
        scene.stores.alerts, scene.world.graph, scene.analytics, scene.case, h1.alert.id, scene.analyst
    )
    return packs.alert_item(explained, events, scene.analyst, SCHEME)


async def test_chapter_nines_alert_goes_into_the_pack_open_and_inferred(scene: Scene) -> None:
    await story(scene)
    item = await _h1_item(scene)
    snapshot = item.alert
    assert (snapshot.kind, snapshot.status, snapshot.match, snapshot.outcome) == (
        "hotlist", "open", "inferred", None)  # fmt: skip
    assert [e.name for e in snapshot.entities] == [COORDINATOR_NUMBER]
    assert snapshot.hotlist_entry == COORDINATOR_NUMBER
    number = scene.world.graph.node_by_value(COORDINATOR_NUMBER)
    assert item.handlings == [number.handling]
    shown, withheld = await packs.readable([item], scene.analyst, SCHEME, scene.world.graph, scene.case)
    assert shown == [item] and withheld is False


async def test_the_alert_item_is_withheld_from_a_reader_who_may_not_see_the_number(scene: Scene) -> None:
    await story(scene)
    item = await _h1_item(scene)
    public = scene.colleague.model_copy(update={"clearance": "PUBLIC"})
    for reader in (scene.stranger, public):
        shown, withheld = await packs.readable([item], reader, SCHEME, scene.world.graph, scene.case)
        assert shown == [] and withheld is True  # a yes, never a count or a name


# --- P4: the monitoring figures ------------------------------------------------------------------


async def _figures(scene: Scene, reader: Principal) -> Any:
    return await reports.alert_report(
        scene.stores.alerts, scene.world.graph, scene.case, reader, today=datetime.now(UTC).date()
    )


def _week() -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=today.weekday())


async def test_the_monitoring_figures_count_raised_closed_and_the_open_queue(scene: Scene) -> None:
    await story(scene)
    m = (await _figures(scene, scene.analyst)).monitoring
    week = _week()
    assert sorted((w.label, w.typology, w.week_start, w.count) for w in m.raised_by_rule) == [
        ("hotlists", "", week, 2), ("typology", "sentence", week, 1)]  # fmt: skip
    assert [(w.label, w.week_start, w.count) for w in m.closed_by_outcome] == [("referred", week, 2)]
    assert {c.label: c.value for c in m.time_to_close}["under a day"] == 2
    assert [(w.label, w.count) for w in m.hotlist_matches] == [("hotlists", 2)]
    still_open = [q for q in await queue(scene, scene.analyst) if q.alert.status != "closed"]
    assert [number_of(scene, q) for q in still_open] == [COORDINATOR_NUMBER], "H1 alone"
    closed = {q.alert.id: q.alert for q in await queue(scene, scene.analyst) if q.alert.status == "closed"}
    s1 = next(a for a in closed.values() if a.typology == "sentence")
    assert (s1.disposition, s1.decided_by, s1.close_proposed_by) == (
        "referred", scene.colleague.id, scene.analyst.id)  # fmt: skip


async def test_the_proposer_cannot_approve_their_own_close(scene: Scene) -> None:
    await story(scene, close=False)
    s1 = (await queue(scene, scene.analyst))[2]
    store, graph = scene.stores.alerts, scene.world.graph
    await alert_queue.dispose(store, graph, scene.case, s1.alert.id, scene.analyst,
                              disposition="referred", reason="Subscriber check.")  # fmt: skip
    with pytest.raises(alert_queue.CloseRefused):
        await alert_queue.approve_close(store, graph, scene.case, s1.alert.id, scene.analyst)
    (still,) = [q for q in await queue(scene, scene.analyst) if q.alert.id == s1.alert.id]
    assert still.alert.status == "closing"


async def test_the_board_never_counts_the_owners_only_me_hotlist(scene: Scene) -> None:
    await story(scene)
    m = (await _figures(scene, scene.colleague)).monitoring
    assert [(w.label, w.typology, w.count) for w in m.raised_by_rule] == [("typology", "sentence", 1)]
    assert m.hotlist_matches == []
    assert [(w.label, w.count) for w in m.closed_by_outcome] == [("referred", 1)]


async def test_a_reader_without_the_dataset_counts_nothing_on_the_board(scene: Scene) -> None:
    await story(scene)
    figures = await _figures(scene, scene.stranger)
    m = figures.monitoring
    assert m.raised_by_rule == m.closed_by_outcome == m.hotlist_matches == []
    assert all(c.value == 0 for c in m.time_to_close) and figures.alerts_total == 0
