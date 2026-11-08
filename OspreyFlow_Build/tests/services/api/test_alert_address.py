"""An alert's own address (`06_DECISIONS.md` ADR-146 decision 6 and its test, rule 3):
`GET /v1/alerts/{alert_id}` answers the case an alert is worked in and its explanation, and refuses
**exactly as for an alert that does not exist** a reader who may not see it: one whose evidence is
not whole for them, one who may not open its case, and one whose case is another's. The answer is
the same status and body, and the reads made are the same calls (the case's level check is made for
a missing alert too, on no case), so neither says the alert is there. (The reads after the level check
are not the same: an alert in a case the reader may open is read through the queue's scope and its
evidence before it is refused; what the reader is told is the same.)

**The fakes refuse what the real dependencies refuse (rule 15).** The reader is the principal the real
`get_principal` gives a route with no case in its path (`outside_any_case`: `datasets=[]`, reading no
dataset), so the route must scope it to the alert's case before it reads anything; the graph and the
analytics answer nothing outside the reader's datasets, and the store's queue read admits a hotlist
alert only to its owner, a typology alert only in its case, and any alert only within the reader's
datasets, as `queue_scope` does.

Red records: `process/lanes/rules/l2.9/RED_RECORD.md` (the route's case check and its evidence check
each removed at the real call site).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from schemas.domain import Alert, Principal
from services.api.investigations import AccessLevel
from services.api.alerts import AlertNotFoundError, QueueRow
from tests.services.api.test_alert_evidence_withheld import (
    CASE,
    OVER_LINK,
    OVER_TRANSACTION,
    READER,
    V1,
    Analytics,
    Graph,
    Recorder,
    TriageStore,
)
from tests.services.api.test_monitoring_routes import _Case, _no_lifespan

OTHER_CASE = "case-other"
DATASET = "ds-1"
#: What the real `get_principal` gives a route with no case in its path: no dataset read at all.
ANALYST = READER.model_copy(update={"roles": ["analyst"], "datasets": []})
#: The datasets each case reads.
READS = {CASE: [DATASET], OTHER_CASE: ["ds-2"]}


def _in(alert: Alert, **update: object) -> Alert:
    return alert.model_copy(update={"dataset_id": DATASET, **update})


class Datasets:
    """The dataset store `scope_to_case` reads: each case's datasets, no layers."""

    async def ids_of_case(self, investigation_id: str) -> list[str]:
        return list(READS.get(investigation_id, []))

    async def layer_of_case(self, investigation_id: str) -> None:
        return None

    async def read_only_layer_of(self, investigation_id: str) -> None:
        return None


def _reach(principal: Principal) -> set[str] | None:
    return None if principal.datasets is None else set(principal.datasets)


class ScopedGraph(Graph):
    """The graph port's dataset step: a reader reading no dataset of the alert's is shown nothing."""

    async def get_nodes(self, node_ids: Any, principal: Principal) -> list[Any]:
        reach = _reach(principal)
        found = await super().get_nodes(node_ids, principal)
        return found if reach is None or DATASET in reach else []

    async def get_edges(self, edge_ids: Any, principal: Principal) -> list[Any]:
        reach = _reach(principal)
        found = await super().get_edges(edge_ids, principal)
        return found if reach is None or DATASET in reach else []


class ScopedAnalytics(Analytics):
    async def list_events(self, req: Any, principal: Principal) -> Any:
        reach = _reach(principal)
        if reach is not None and DATASET not in reach:
            self.hidden = self.hidden | set(req.filter.event_ids)
        return await super().list_events(req, principal)


class AddressStore(TriageStore):
    """`AlertStore.case_of` beside the queue's own read: the case an alert was raised in, whoever
    asks (the route checks the reader against it), or `None` for an id that never existed."""

    def __init__(self, alerts: list[Alert]) -> None:
        super().__init__(alerts)
        self.asked: list[str] = []

    async def case_of(self, alert_id: str) -> str | None:
        self.asked.append(alert_id)
        return next((a.investigation_id for a in self.alerts if a.id == alert_id), None)

    async def get_queue_alert(self, alert_id: str, investigation_id: str, reader: Principal) -> QueueRow:
        """`queue_scope`: a typology alert in its case, a hotlist or monitor alert its owner's, and
        either only within the reader's datasets."""
        reach = _reach(reader)
        for a in self.alerts:
            if a.id != alert_id:
                continue
            mine = a.typology is not None and a.investigation_id == investigation_id
            mine = mine or (a.typology is None and a.owner_id == reader.id)
            # Shared with the owner's team (`_SHARED_SQL`): a team set on it, the reader's unit.
            mine = mine or (a.typology is None and a.team is not None and a.team == reader.org_unit)
            if mine and (reach is None or a.dataset_id in reach):
                kind = "typology" if a.typology else "hotlist"
                audience = "case" if a.typology else ("team" if a.team else "owner")
                return QueueRow(a, kind, "medium", audience)
        raise AlertNotFoundError(alert_id)


class Audit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, *, action: str, **_: Any) -> None:
        self.actions.append(action)


class Cases(_Case):
    """`_Case`, recording which case each level check asked about."""

    def __init__(self, case_id: str, levels: dict[str, AccessLevel]) -> None:
        super().__init__(case_id, levels)
        self.checked: list[str] = []

    async def get_authorized(self, investigation_id: str, principal: Principal, *, need: AccessLevel) -> Any:
        self.checked.append(investigation_id)
        return await super().get_authorized(investigation_id, principal, need=need)


class Names:
    async def display_names(self, ids: list[str]) -> dict[str, str]:
        return {}


def _ask(alerts: list[Alert], hidden: set[str], levels: dict[str, AccessLevel], ids: list[str],
         who: Principal = ANALYST, *, cases: Cases | None = None,
         datasets: Any = None) -> tuple[list[tuple[int, str]], Cases, Audit]:  # fmt: skip
    from services.api.app import (
        app,
        get_alerts_store,
        get_analytics,
        get_audit,
        get_datasets,
        get_graph,
        get_investigations,
        get_principal,
        get_principal_names,
    )

    recorder = Recorder()
    graph, analytics = ScopedGraph(recorder, hidden), ScopedAnalytics(recorder, hidden)
    cases = cases if cases is not None else Cases(CASE, levels)
    audit = Audit()
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.dependency_overrides.update({
        get_principal: lambda: who, get_investigations: lambda: cases, get_graph: lambda: graph,
        get_analytics: lambda: analytics, get_alerts_store: lambda: AddressStore(alerts),
        get_audit: lambda: audit, get_principal_names: Names, get_datasets: datasets or Datasets,
    })  # fmt: skip
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            answers = [
                (r.status_code, r.text) for r in (client.get(f"/v1/alerts/{i}") for i in ids)
            ]
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous
    return answers, cases, audit


MEMBER = {ANALYST.id: AccessLevel.VIEWER}


def test_a_readable_alert_is_answered_with_its_case_and_explanation() -> None:
    """Red with the reader left unscoped (`datasets=[]`, as `get_principal` gives it): every node
    is then outside its reach and the alert is refused to everyone."""
    (answer,), cases, audit = _ask([_in(V1)], set(), MEMBER, [V1.id])
    assert answer[0] == 200, answer
    assert f'"investigation_id":"{CASE}"' in answer[1] and f'"id":"{V1.id}"' in answer[1]
    assert cases.checked == [CASE] and audit.actions == ["open_alert_at_address"]


@pytest.mark.parametrize(
    ("why", "alerts", "hidden", "levels"),
    [
        ("a link it cites is hidden", [_in(OVER_LINK)], {"e-secret"}, MEMBER),
        ("a transaction it cites is hidden", [_in(OVER_TRANSACTION)], {"t-secret"}, MEMBER),
        ("a node it names is hidden", [_in(V1)], {"n-a"}, MEMBER),
        ("the reader is no member of its case", [_in(V1)], set(), {}),
        ("its case is another's", [_in(V1, investigation_id=OTHER_CASE)], set(), MEMBER),
        ("its dataset is not one its case reads", [_in(V1, dataset_id="ds-elsewhere")], set(), MEMBER),
        ("it is another member's own hotlist alert in the case",
         [_in(V1, typology=None, rule_id="hotlist:h1", owner_id="someone-else")], set(), MEMBER),
    ],
)  # fmt: skip
def test_an_alert_the_reader_may_not_see_is_answered_as_a_missing_one(
    why: str, alerts: list[Alert], hidden: set[str], levels: dict[str, AccessLevel]
) -> None:
    """ADR-146's test: "`/alerts/<id>` for a reader who may not see the alert is refused exactly as
    a missing alert". Red with the case check skipped (the other case's alert answered) and with the
    evidence check skipped (the alert over a hidden link answered, its words with it)."""
    (refused, missing), cases, audit = _ask(alerts, hidden, levels, [alerts[0].id, "no-such-alert"])
    assert refused == missing, (why, refused, missing)
    assert refused[0] == 404 and '"alert_not_found"' in refused[1], why
    # The same reads: a level check for each, the missing one's on no case of the reader's.
    assert len(cases.checked) == 2, cases.checked
    assert "open_alert_at_address" not in audit.actions


def test_a_reader_rules_and_monitoring_is_not_offered_to_is_refused_at_its_gate() -> None:
    """ADR-146 decision 2: a Data Engineer holds `read_alert_queue` but neither right that opens
    Rules and Monitoring, so the address refuses them before it reads anything."""
    engineer = READER.model_copy(update={"roles": ["data_engineer"]})
    (answer,), cases, _ = _ask([V1], set(), {engineer.id: AccessLevel.AUTHOR}, [V1.id], engineer)
    assert answer[0] == 403 and "place_required" in answer[1], answer
    assert cases.checked == []


def test_the_jump_s_case_of_its_own_is_gone() -> None:
    """ADR-146 Amendment 2 point 7: no route makes a case of its own from an alert any more; the
    alert opens at its address instead."""
    from services.api.app import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any(p.endswith("/jump") for p in paths), sorted(p for p in paths if "jump" in p)
    assert "/v1/alerts/{alert_id}" in paths


# --- the refusal's timing (the orchestrator's independent review of L2.9, blocker 1) ------------


class Clock:
    """A clock the fakes advance as they read, standing in for each read's cost, and the sleep the
    route waits out a refusal with, which advances it too (`rules_place.monotonic`/`sleep`)."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _timed(alerts: list[Alert], hidden: set[str], levels: dict[str, AccessLevel], ids: list[str],
           monkeypatch: pytest.MonkeyPatch) -> list[float]:  # fmt: skip
    """Each id asked for alone, and the clock's reading when its answer was given, from its start."""
    from services.api import rules_place

    clock = Clock()
    monkeypatch.setattr(rules_place, "monotonic", clock.monotonic)
    monkeypatch.setattr(rules_place, "sleep", clock.sleep)
    # Every read the route makes costs time: the case check 2 ms, each graph and analytics read 5 ms.
    for cls, names, cost in ((Cases, ["get_authorized"], 0.002),
                             (ScopedGraph, ["get_nodes", "get_edges"], 0.005),
                             (ScopedAnalytics, ["list_events"], 0.005)):  # fmt: skip
        for name in names:
            original = getattr(cls, name)

            async def costly(self: Any, *a: Any, _o: Any = original, _c: float = cost, **k: Any) -> Any:
                clock.now += _c
                return await _o(self, *a, **k)

            monkeypatch.setattr(cls, name, costly)
    answered = []
    for i in ids:
        start = clock.now
        (answer,), _, _ = _ask(alerts, hidden, levels, [i])
        assert answer[0] == 404, answer
        answered.append(round(clock.now - start, 6))
    return answered


def test_every_refusal_is_answered_on_the_same_quantum(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 3: a member must not tell an alert over evidence hidden from them from no alert at all,
    by when the answer comes. An id that never existed and one in a case the reader may not open
    stop after the level check; an alert over a hidden link is read through the queue's scope and its
    evidence first. Each refusal is answered at the end of the quantum it falls in
    (`rules_place.ADDRESS_REFUSAL_QUANTUM`), so all three are answered at the same instant. Red with
    the wait removed: the hidden alert's answer comes later than the missing one's."""
    from services.api.rules_place import ADDRESS_REFUSAL_QUANTUM

    alerts = [_in(OVER_LINK), _in(V1, id="v-other", investigation_id=OTHER_CASE)]
    answered = _timed(alerts, {"e-secret"}, MEMBER, ["no-such-alert", "v-other", OVER_LINK.id],
                      monkeypatch)  # fmt: skip
    assert answered == [ADDRESS_REFUSAL_QUANTUM] * 3, answered


def test_a_refusal_past_one_quantum_waits_for_the_next() -> None:
    from services.api.rules_place import ADDRESS_REFUSAL_QUANTUM as Q
    from services.api.rules_place import refusal_wait

    assert refusal_wait(10.0, 10.0) == pytest.approx(Q)
    assert refusal_wait(10.0, 10.0 + Q / 4) == pytest.approx(Q * 3 / 4)
    assert refusal_wait(10.0, 10.0 + Q * 1.5) == pytest.approx(Q / 2)


# --- the review's minors: a team-shared alert, and a case's read-only layer ---------------------


def test_another_member_s_alert_shared_with_the_reader_s_team_is_answered() -> None:
    """The queue's scope admits a hotlist alert shared with its owner's team to that team
    (`_SHARED_SQL`): its address answers a member of the team as the queue would. Red with the
    fake's team admission removed: refused as a missing alert."""
    shared = _in(V1, typology=None, rule_id="hotlist:h1", owner_id="someone-else", team=ANALYST.org_unit)
    (answer,), _, audit = _ask([shared], set(), MEMBER, [shared.id])
    assert answer[0] == 200, answer
    assert '"audience":"team"' in answer[1] and audit.actions == ["open_alert_at_address"]


ORIGINAL = "case-original"
LAYER = "layer-of-the-original"


class LayerCases(Cases):
    """Levels on this case and on the case it was made from."""

    def __init__(self, levels: dict[str, dict[str, AccessLevel]]) -> None:
        super().__init__(CASE, levels.get(CASE, {}))
        self.by_case = levels

    async def get_authorized(self, investigation_id: str, principal: Principal, *, need: AccessLevel) -> Any:
        self.checked.append(investigation_id)
        self.case_id, self.levels = investigation_id, self.by_case.get(investigation_id, {})
        return await _Case.get_authorized(self, investigation_id, principal, need=need)


class LayerDatasets(Datasets):
    """A case made from another and not converted: it reads its dataset and the original's layer,
    read-only, which only a reader holding a level on the original reads (`scope_to_case`)."""

    async def ids_of_case(self, investigation_id: str) -> list[str]:
        return [DATASET, LAYER] if investigation_id == CASE else []

    async def read_only_layer_of(self, investigation_id: str) -> str | None:
        return LAYER if investigation_id == CASE else None

    async def case_of_layer(self, layer_id: str) -> str | None:
        return ORIGINAL if layer_id == LAYER else None


@pytest.mark.parametrize("holds_the_original", [True, False])
def test_an_alert_in_the_case_s_read_only_layer_is_answered_only_to_a_reader_of_the_original(
    holds_the_original: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The address reads as the case reads: an alert over the original case's layer is answered to a
    reader holding a level there, and refused exactly as a missing one to a member of this case
    alone (rule 3). Red with the route scoping without `holds_a_level`: the second answered too, or
    the first refused."""
    import tests.services.api.test_alert_address as here

    monkeypatch.setattr(here, "DATASET", LAYER)  # the alert's nodes are the layer's
    alert = _in(V1)
    levels = {CASE: {ANALYST.id: AccessLevel.VIEWER}}
    if holds_the_original:
        levels[ORIGINAL] = {ANALYST.id: AccessLevel.VIEWER}
    (answer, missing), _, _ = _ask([alert], set(), {}, [alert.id, "no-such-alert"],
                                   cases=LayerCases(levels), datasets=LayerDatasets)  # fmt: skip
    if holds_the_original:
        assert answer[0] == 200, answer
    else:
        assert answer == missing and answer[0] == 404, answer
