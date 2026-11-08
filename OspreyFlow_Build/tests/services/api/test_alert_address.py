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
            if mine and (reach is None or a.dataset_id in reach):
                kind = "typology" if a.typology else "hotlist"
                return QueueRow(a, kind, "medium", "case" if a.typology else "owner")
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
         who: Principal = ANALYST) -> tuple[list[tuple[int, str]], Cases, Audit]:  # fmt: skip
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
    cases = Cases(CASE, levels)
    audit = Audit()
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.dependency_overrides.update({
        get_principal: lambda: who, get_investigations: lambda: cases, get_graph: lambda: graph,
        get_analytics: lambda: analytics, get_alerts_store: lambda: AddressStore(alerts),
        get_audit: lambda: audit, get_principal_names: Names, get_datasets: Datasets,
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
