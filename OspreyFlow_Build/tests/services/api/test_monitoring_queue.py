"""The one alert queue (`spec/06_DECISIONS.md` ADR-133 decision 5 and stage (a)): typology, hotlist
and monitor alerts in one queue, with severity, team and assignment.

**Who sees what is decided in the query** (`CLAUDE.md` rule 3): the case's members see its typology
alerts; a hotlist or monitor alert reaches its owner, and also the owner's team (their
organisational unit) when it is shared — a monitor's always, a hotlist's only when its audience is
`team`; a `notify` stub reaches its owner alone. The tests read the store as each principal and
check the SQL's answer, with no graph in the way. The referents are then read once, in one batch,
as the reader (`services/api/alert_queue.py::monitoring_queue`), all-or-nothing per alert.

The ADR's own queue tests are `test_the_queue_shows_a_typology_a_hotlist_and_a_monitor_alert_to_a_
team_member` and `test_an_only_me_hotlist_alert_reaches_its_owner_alone`; closing without a reason
is `test_closing_without_a_reason_is_refused`. Real Postgres (`make dev-up`, or a throwaway one);
the graph is a fake that answers as the adapter does — a hidden id is left out of `get_nodes`, never
an error (`ports/graph.py::GraphPort.get_nodes`) — and counts its reads.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from services.api import alert_queue
from services.api.alerts import (
    AlertNotFoundError,
    AlertStore,
    AlertTriageConflict,
    default_severity,
)
from services.api.config import PostgresConfig
from services.api.hotlists import HotlistStore

from conduit_common.identity import new_id
from schemas.domain import (
    Alert,
    AlertDispositionInput,
    AlertMode,
    AuditStub,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


#: Each test's own two units, so one test's shared alerts are not another's (the database is
#: shared across the run, and a team sees its alerts in every case reading the dataset).
_UNITS: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _fresh_units() -> None:
    _UNITS.update({"unit-a": f"unit-a-{new_id()}", "unit-b": f"unit-b-{new_id()}"})


def _person(unit: str = "unit-a", **update: object) -> Principal:
    return Principal(
        id=f"analyst-{new_id()}", clearance="OFFICIAL", org_unit=_UNITS[unit], datasets=["ds-1"]
    ).model_copy(update=update)


def _node(node_id: str, name: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={"name": name},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="row 1", excerpt_hash="a" * 64)],
            first_seen=NOW,
        ),
        handling={  # type: ignore[arg-type]
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-a",
            "owning_unit": "unit-a",
        },
        audit=AuditStub(created_at=NOW, created_by="loader-1"),
    )


class _Graph:
    """Answers `get_nodes` as the adapter does: an id hidden from the reader is simply absent.
    Counts every read, so a test can show the number of reads does not depend on a hidden alert."""

    def __init__(self, names: dict[str, str], hidden: set[str] | None = None) -> None:
        self.names = names
        self.hidden = hidden or set()
        self.reads = 0

    async def get_nodes(self, node_ids: Any, principal: Principal) -> list[Node]:
        self.reads += 1
        return [
            _node(i, self.names[i])
            for i in sorted(set(node_ids))
            if i in self.names and i not in self.hidden
        ]

    async def get_node(self, node_id: str, principal: Principal, **_: object) -> Node | None:
        self.reads += 1
        if node_id in self.names and node_id not in self.hidden:
            return _node(node_id, self.names[node_id])
        return None


@pytest.fixture
async def stores():  # type: ignore[no-untyped-def]
    dsn = PostgresConfig.from_env().dsn
    hotlists = await HotlistStore.connect(dsn)
    alerts = await AlertStore.connect(dsn)
    yield hotlists, alerts
    await alerts.close()
    await hotlists.close()


def _alert(rule_id: str, owner: Principal, **fields: object) -> Alert:
    values: dict[str, Any] = {
        "id": new_id(),
        "rule_id": rule_id,
        "owner_id": owner.id,
        "mode": AlertMode.FULL,
        "referent_node_ids": [],
        "created_at": NOW,
        "dataset_id": "ds-1",
    }
    values.update(fields)
    return Alert(**values)


async def _hotlist(hotlists: HotlistStore, owner: Principal, audience: str) -> str:
    made = await hotlists.create(
        owner, identifier="+447700900310", review_date=date(2027, 1, 1), audience=audience
    )
    return made.id


async def _three_kinds(
    hotlists: HotlistStore, alerts: AlertStore, owner: Principal, case: str
) -> dict[str, Alert]:
    """A typology alert of the case, a team hotlist's alert and a monitor's, all by `owner`."""
    hotlist_id = await _hotlist(hotlists, owner, "team")
    made = {
        "typology": _alert(
            "typology:r1", owner, investigation_id=case, typology="structuring",
            words="4 movements under the threshold", referent_node_ids=["n-1"],
            created_at=NOW - timedelta(hours=3),
        ),
        "hotlist": _alert(
            f"hotlist:{hotlist_id}", owner, team=owner.org_unit, referent_node_ids=["n-2"],
            created_at=NOW - timedelta(hours=2),
        ),
        "monitor": _alert(
            f"monitor:{new_id()}", owner, team=owner.org_unit, referent_node_ids=["n-3"],
            created_at=NOW - timedelta(hours=1),
        ),
    }  # fmt: skip
    for alert in made.values():
        await alerts.save(alert)
    return made


GRAPH_NAMES = {"n-1": "Acme Ltd", "n-2": "07700 900310", "n-3": "OKAFOR, Callum"}


async def _queued_ids(
    alerts: AlertStore, case: str, reader: Principal, **filters: Any
) -> list[str]:
    rows = await alert_queue.monitoring_queue(alerts, _Graph(GRAPH_NAMES), case, reader, **filters)
    return [row.alert.id for row in rows]


# --- the ADR's own queue tests -------------------------------------------------------------------


async def test_the_queue_shows_a_typology_a_hotlist_and_a_monitor_alert_to_a_team_member(
    stores: Any,
) -> None:
    hotlists, alerts = stores
    owner, member = _person(), _person()
    case = new_id()
    made = await _three_kinds(hotlists, alerts, owner, case)

    rows = await alert_queue.monitoring_queue(alerts, _Graph(GRAPH_NAMES), case, member)

    by_kind = {row.kind: row for row in rows}
    assert set(by_kind) == {"typology", "hotlist", "monitor"}
    assert {k: r.alert.id for k, r in by_kind.items()} == {k: a.id for k, a in made.items()}
    assert by_kind["typology"].audience == "case"
    assert by_kind["hotlist"].audience == "team" and by_kind["hotlist"].team == owner.org_unit
    assert by_kind["monitor"].audience == "team"
    # Each names what it found as the reader reads it, never by id.
    assert "07700 900310" in by_kind["hotlist"].summary
    assert "OKAFOR, Callum" in by_kind["monitor"].summary


async def test_an_only_me_hotlist_alert_reaches_its_owner_alone(stores: Any) -> None:
    hotlists, alerts = stores
    owner, member = _person(), _person()
    case = new_id()
    hotlist_id = await _hotlist(hotlists, owner, "only_me")
    alert = _alert(f"hotlist:{hotlist_id}", owner, team=owner.org_unit, referent_node_ids=["n-2"])
    await alerts.save(alert)

    assert await _queued_ids(alerts, case, owner) == [alert.id]
    assert await _queued_ids(alerts, case, member) == []
    with pytest.raises(AlertNotFoundError):
        await alerts.get_queue_alert(alert.id, case, member)


# --- the team, and what it is not ----------------------------------------------------------------


async def test_a_shared_alert_reaches_the_owners_unit_and_no_other(stores: Any) -> None:
    hotlists, alerts = stores
    owner, elsewhere = _person("unit-a"), _person("unit-b")
    case = new_id()
    await _three_kinds(hotlists, alerts, owner, case)

    # Another unit's member of the same case sees the case's typology alert, and nothing shared
    # with a team that is not theirs.
    rows = await alert_queue.monitoring_queue(alerts, _Graph(GRAPH_NAMES), case, elsewhere)
    assert [row.kind for row in rows] == ["typology"]


async def test_an_alert_raised_before_teams_existed_reaches_its_owner_alone(stores: Any) -> None:
    _, alerts = stores
    owner, member = _person(), _person()
    alert = _alert(f"monitor:{new_id()}", owner, referent_node_ids=["n-3"])  # team: None
    await alerts.save(alert)

    assert await _queued_ids(alerts, "any-case", owner) == [alert.id]
    assert await _queued_ids(alerts, "any-case", member) == []


async def test_a_notify_stub_reaches_its_owner_alone_on_a_team_hotlist(stores: Any) -> None:
    hotlists, alerts = stores
    owner, member = _person(), _person()
    hotlist_id = await _hotlist(hotlists, owner, "team")
    # A stub carries no referent and is written with no team (ADR-038); even a team stamped on one
    # by mistake would not share it.
    stub = _alert(f"hotlist:{hotlist_id}", owner, mode=AlertMode.NOTIFY_STUB, team=owner.org_unit)
    await alerts.save(stub)

    rows = await alert_queue.monitoring_queue(alerts, _Graph({}), "c", owner)
    assert [r.alert.id for r in rows] == [stub.id] and rows[0].audience == "owner"
    assert "cannot see" in rows[0].summary
    assert await _queued_ids(alerts, "c", member) == []


async def test_a_hotlist_turned_back_to_only_me_withdraws_its_alerts_from_the_team(
    stores: Any,
) -> None:
    hotlists, alerts = stores
    owner, member = _person(), _person()
    hotlist_id = await _hotlist(hotlists, owner, "team")
    alert = _alert(f"hotlist:{hotlist_id}", owner, team=owner.org_unit, referent_node_ids=["n-2"])
    await alerts.save(alert)
    assert await _queued_ids(alerts, "c", member) == [alert.id]

    await hotlists.set_audience(hotlist_id, owner, "only_me")

    assert await _queued_ids(alerts, "c", member) == []
    assert await _queued_ids(alerts, "c", owner) == [alert.id]


async def test_another_cases_typology_alert_is_not_in_this_queue(stores: Any) -> None:
    _, alerts = stores
    owner = _person()
    other = _alert("typology:r", owner, investigation_id="case-other", typology="structuring",
                   referent_node_ids=["n-1"])  # fmt: skip
    await alerts.save(other)
    assert other.id not in await _queued_ids(alerts, "case-this", owner)


async def test_an_alert_of_a_dataset_the_case_does_not_read_is_not_queued(stores: Any) -> None:
    _, alerts = stores
    owner = _person()
    alert = _alert(f"monitor:{new_id()}", owner, team=owner.org_unit, referent_node_ids=["n-3"],
                   dataset_id="ds-other")  # fmt: skip
    await alerts.save(alert)
    assert await _queued_ids(alerts, "c", owner) == []


async def test_a_scheduled_runs_notice_is_never_queued(stores: Any) -> None:
    _, alerts = stores
    owner = _person()
    notice = _alert("schedule:recipe-1", owner, words="The scheduled run was refused")
    await alerts.save(notice)
    assert await _queued_ids(alerts, "c", owner) == []


# --- severity, and the filters -----------------------------------------------------------------


def test_each_kind_has_a_default_severity() -> None:
    assert default_severity("hotlist", None) == "high"
    assert default_severity("monitor", None) == "medium"
    assert default_severity("typology", "kyc_screening") == "high"
    assert default_severity("typology", "structuring") == "medium"
    assert default_severity("typology", "shared_attributes") == "low"


async def test_severity_defaults_by_kind_and_the_filters_are_applied_in_the_query(
    stores: Any,
) -> None:
    hotlists, alerts = stores
    owner = _person()
    case = new_id()
    made = await _three_kinds(hotlists, alerts, owner, case)
    stated = _alert("typology:r2", owner, investigation_id=case, typology="structuring",
                    severity="low", referent_node_ids=["n-1"])  # fmt: skip
    await alerts.save(stated)

    rows = await alert_queue.monitoring_queue(alerts, _Graph(GRAPH_NAMES), case, owner)
    severity = {row.alert.id: row.severity for row in rows}
    assert severity == {
        made["typology"].id: "medium", made["hotlist"].id: "high",
        made["monitor"].id: "medium", stated.id: "low",
    }  # fmt: skip
    # High first, then the newest.
    assert [r.alert.id for r in rows] == [
        made["hotlist"].id, made["monitor"].id, made["typology"].id, stated.id,
    ]  # fmt: skip

    assert await _queued_ids(alerts, case, owner, kinds=["hotlist"]) == [made["hotlist"].id]
    assert await _queued_ids(alerts, case, owner, severities=["low"]) == [stated.id]
    await alerts.set_queue_triage(
        made["monitor"].id, case, owner, expect_status=["open"], status="closed",
        assignee=owner.id, disposition="false_positive", disposition_reason="noise",
        decided_by=owner.id,
    )  # fmt: skip
    assert made["monitor"].id not in await _queued_ids(
        alerts, case, owner, statuses=["open", "claimed"]
    )
    assert await _queued_ids(alerts, case, owner, statuses=["closed"]) == [made["monitor"].id]


# --- rule 3: a hidden alert says nothing ---------------------------------------------------------


async def test_a_hidden_alert_reveals_nothing_through_count_order_or_reads(stores: Any) -> None:
    """An alert whose referent the reader may not read is left out whole, and the queue it is left
    out of is the queue it would be without it: the same rows, in the same order, after the same
    number of graph reads (one batch), so neither the count, the ordering nor the work done says it
    exists (rule 3's "path length, degree count or histogram bucket")."""
    hotlists, alerts = stores
    owner, member = _person(), _person()
    case_with, case_without = new_id(), new_id()
    for case in (case_with, case_without):
        await _three_kinds(hotlists, alerts, owner, case)
    hidden = _alert("typology:r3", owner, investigation_id=case_with, typology="kyc_screening",
                    referent_node_ids=["n-secret"], created_at=NOW)  # fmt: skip
    await alerts.save(hidden)

    names = {**GRAPH_NAMES, "n-secret": "Hidden person"}
    with_graph, without_graph = _Graph(names, hidden={"n-secret"}), _Graph(names)
    shown_with = await alert_queue.monitoring_queue(alerts, with_graph, case_with, member)
    shown_without = await alert_queue.monitoring_queue(alerts, without_graph, case_without, member)

    def shape(rows: list[Any]) -> list[tuple[str, str, str]]:
        return [(r.kind, r.severity, r.summary) for r in rows]

    assert hidden.id not in [r.alert.id for r in shown_with]
    assert shape(shown_with) == shape(shown_without)
    assert with_graph.reads == without_graph.reads == 1
    with pytest.raises(AlertNotFoundError):
        await alert_queue.explain(alerts, with_graph, None, case_with, hidden.id, member)  # type: ignore[arg-type]


# --- triage ---------------------------------------------------------------------------------------


async def test_a_team_member_claims_and_closes_a_hotlist_alert_and_a_stranger_cannot(
    stores: Any,
) -> None:
    hotlists, alerts = stores
    owner, member, stranger = _person(), _person(), _person("unit-b")
    case = new_id()
    made = await _three_kinds(hotlists, alerts, owner, case)
    graph = _Graph(GRAPH_NAMES)
    target = made["hotlist"].id

    with pytest.raises(AlertNotFoundError):
        await alert_queue.claim(alerts, graph, case, target, stranger)
    claimed = await alert_queue.claim(alerts, graph, case, target, member)
    assert claimed.status == "claimed" and claimed.assignee == member.id
    with pytest.raises(AlertTriageConflict):
        await alert_queue.claim(alerts, graph, case, target, owner)
    # A hotlist alert is high severity and shared with the team: closing it is proposed, and a
    # second member approves (ADR-133 decision 7, stage (d)); `test_alert_close_approval.py`.
    proposed = await alert_queue.dispose(
        alerts, graph, case, target, member, disposition="false_positive", reason="a known number"
    )
    assert (proposed.status, proposed.close_proposed_by) == ("closing", member.id)
    with pytest.raises(AlertNotFoundError):
        await alert_queue.approve_close(alerts, graph, case, target, stranger)
    closed = await alert_queue.approve_close(alerts, graph, case, target, owner)
    assert closed.status == "closed" and closed.disposition_reason == "a known number"
    assert (closed.decided_by, closed.close_proposed_by) == (owner.id, member.id)


async def test_a_case_alert_is_given_to_a_member_and_a_shared_one_only_to_be_claimed(
    stores: Any,
) -> None:
    hotlists, alerts = stores
    owner, member = _person(), _person()
    case = new_id()
    made = await _three_kinds(hotlists, alerts, owner, case)
    graph = _Graph(GRAPH_NAMES)

    given = await alert_queue.assign(alerts, graph, case, made["typology"].id, owner,
                                     assignee=member.id, allowed={member.id, owner.id})  # fmt: skip
    assert given.status == "claimed" and given.assignee == member.id
    with pytest.raises(alert_queue.AssignmentRefused, match="not a member"):
        await alert_queue.assign(alerts, graph, case, made["typology"].id, owner,
                                 assignee="someone-else", allowed={member.id})  # fmt: skip
    # Someone outside the owner's team may be a member of the case: an alert shared with a team is
    # never given to them, as they might not be able to read it. Claiming it is the way.
    with pytest.raises(alert_queue.AssignmentRefused, match="claimed"):
        await alert_queue.assign(alerts, graph, case, made["hotlist"].id, owner,
                                 assignee=member.id, allowed={member.id})  # fmt: skip


def test_closing_without_a_reason_is_refused() -> None:
    for reason in ("", "   "):
        with pytest.raises(ValidationError):
            AlertDispositionInput(disposition="false_positive", reason=reason)
    assert AlertDispositionInput(disposition="true_positive", reason=" seen ").reason == "seen"


async def test_the_queue_reads_on_a_fresh_database_with_the_alert_store_alone() -> None:
    """The queue's scope reads a hotlist's audience, so the alert store makes sure that table exists
    — a caller that connects no hotlist store (a typology rule's tests, a script) still triages.
    Run in a schema of its own, which holds neither table at first."""
    import asyncpg

    schema = f"fresh_{new_id().lower()}"
    dsn = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f"CREATE SCHEMA {schema}")
        store = await AlertStore.connect(f"{dsn}?search_path={schema}")
        try:
            owner = _person()
            alert = _alert("typology:r", owner, investigation_id="c", typology="structuring")
            await store.save(alert)
            assert [r.alert.id for r in await store.list_queue("c", owner)] == [alert.id]
        finally:
            await store.close()
    finally:
        await conn.execute(f"DROP SCHEMA {schema} CASCADE")
        await conn.close()
