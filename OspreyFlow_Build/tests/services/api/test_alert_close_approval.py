"""Closing a high-severity alert needs a second person (`spec/06_DECISIONS.md` ADR-133 decision 7,
stage (d)): the close is proposed, the alert waits as `closing`, and a second member with the right
approves it — never the person who proposed it. A medium or low alert closes at once, as before.

Routes on the app with its lifespan replaced, as `test_monitoring_routes.py` runs them: the alert
store is real Postgres (a throwaway one), the graph answers as the adapter does. Rule 4: the new
routes are refused without sign-in, without the right, outside the case, and to a Viewer.

What a mistake would do, and the case that catches it:
- a high-severity alert closed by one person — `test_closing_a_high_severity_alert_needs_a_second_person`;
- the closer approving their own close — `test_the_person_who_proposed_the_close_cannot_approve_it`;
- a close sent back losing who proposed it, or leaving the alert unworkable —
  `test_a_proposed_close_sent_back_returns_the_alert_to_its_proposer`;
- an owner-only alert that no second person could ever read, stuck waiting for one —
  `test_an_alert_its_owner_alone_may_read_closes_without_a_second_person`;
- a medium alert held up — `test_a_medium_alert_closes_at_once`;
- the waiting close naming its proposer by an identity-provider id (step 9d finding 1), or the
  directory asked for a person on a read the reader may not make (ADR-106 decision 3) —
  `test_a_waiting_close_names_its_proposer_and_asks_for_no_one_else`.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from services.api.app import app, get_principal, get_principal_names

from conduit_common.identity import new_id
from tests.services.api.test_monitoring_routes import (  # noqa: F401 - `world` is a fixture
    Q,
    _alert,
    _save,
    _World,
    world,
)


def _paths(w: _World, alert_id: str) -> dict[str, str]:
    base = f"{Q.format(case=w.case)}/{alert_id}"
    return {"close": f"{base}/disposition", "approve": f"{base}/approve-close",
            "send_back": f"{base}/send-back"}  # fmt: skip


def _high(w: _World) -> Any:
    return _alert(w, "typology:r-high", investigation_id=w.case, typology="structuring",
                  severity="high", words="4 movements")  # fmt: skip


def test_closing_a_high_severity_alert_needs_a_second_person(world: tuple[_World, TestClient]) -> None:
    w, client = world
    alert = _high(w)
    _save(client, w, alert)
    paths = _paths(w, alert.id)
    w.as_ = w.member
    proposed = client.post(paths["close"], json={"disposition": "false_positive", "reason": "a known supplier"})
    assert proposed.status_code == 200, proposed.text
    body = proposed.json()
    assert (body["status"], body["close_proposed_by"], body["decided_by"]) == ("closing", w.member.id, None)
    queued = {r["alert"]["id"]: r["alert"]["status"] for r in client.get(Q.format(case=w.case)).json()}
    assert queued[alert.id] == "closing"  # still in the active queue, waiting
    w.as_ = w.owner
    approved = client.post(paths["approve"])
    assert approved.status_code == 200, approved.text
    done = approved.json()
    assert (done["status"], done["disposition"], done["disposition_reason"]) == (
        "closed", "false_positive", "a known supplier")  # fmt: skip
    assert (done["decided_by"], done["close_proposed_by"]) == (w.owner.id, w.member.id)
    actions = [r["action"] for r in w.audit.records if r["action"].startswith("alert_")]
    assert actions[-2:] == ["alert_close_proposed", "alert_close_approved"]


def test_the_person_who_proposed_the_close_cannot_approve_it(world: tuple[_World, TestClient]) -> None:
    w, client = world
    alert = _high(w)
    _save(client, w, alert)
    paths = _paths(w, alert.id)
    w.as_ = w.member
    client.post(paths["close"], json={"disposition": "true_positive", "reason": "confirmed"})
    refused = client.post(paths["approve"])
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["error"] == "own_change"
    assert "second person" in refused.json()["detail"]["message"]
    still = {r["alert"]["id"]: r["alert"]["status"] for r in client.get(Q.format(case=w.case)).json()}
    assert still[alert.id] == "closing"


def test_a_proposed_close_sent_back_returns_the_alert_to_its_proposer(world: tuple[_World, TestClient]) -> None:
    w, client = world
    alert = _high(w)
    _save(client, w, alert)
    paths = _paths(w, alert.id)
    w.as_ = w.member
    client.post(paths["close"], json={"disposition": "false_positive", "reason": "known"})
    w.as_ = w.owner
    back = client.post(paths["send_back"], json={"reason": "look at the second transfer first"})
    assert back.status_code == 200, back.text
    body = back.json()
    assert (body["status"], body["assignee"], body["disposition"], body["close_proposed_by"]) == (
        "claimed", w.member.id, None, None)  # fmt: skip
    assert w.audit.records[-1]["action"] == "alert_close_sent_back"
    assert w.audit.records[-1]["resolved_query"]["reason"] == "look at the second transfer first"


def test_an_alert_its_owner_alone_may_read_closes_without_a_second_person(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    alert = _alert(w, f"monitor:{new_id()}", severity="high")  # no team: its owner's alone
    _save(client, w, alert)
    w.as_ = w.owner
    closed = client.post(_paths(w, alert.id)["close"], json={"disposition": "false_positive", "reason": "mine"})
    assert closed.status_code == 200 and closed.json()["status"] == "closed"


def test_a_medium_alert_closes_at_once(world: tuple[_World, TestClient]) -> None:
    w, client = world
    alert = _alert(w, "typology:r-med", investigation_id=w.case, typology="structuring")
    _save(client, w, alert)
    w.as_ = w.member
    closed = client.post(_paths(w, alert.id)["close"], json={"disposition": "false_positive", "reason": "known"})
    assert closed.status_code == 200 and closed.json()["status"] == "closed"


def test_the_approval_routes_need_sign_in_the_right_the_case_and_an_editor(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    alert = _high(w)
    _save(client, w, alert)
    paths = _paths(w, alert.id)
    w.as_ = w.member
    client.post(paths["close"], json={"disposition": "false_positive", "reason": "known"})
    for key, body in (("approve", None), ("send_back", {"reason": "no"})):
        w.as_ = w.no_right
        refused = client.post(paths[key], json=body)
        assert refused.status_code == 403 and refused.json()["detail"]["error"] == "right_required", key
        w.as_ = w.outsider
        assert client.post(paths[key], json=body).status_code == 404, key
        w.as_ = w.viewer
        assert client.post(paths[key], json=body).status_code == 403, key
    saved = app.dependency_overrides.pop(get_principal)
    try:
        for key in ("approve", "send_back"):
            assert client.post(paths[key], json={"reason": "x"}).status_code in (401, 403), key
    finally:
        app.dependency_overrides[get_principal] = saved


class _Directory:
    """`PrincipalNameDirectory` as a read sees it: a name for an account it knows, none for an id it
    does not (the identity provider's 404), and a record of every id it was asked for."""

    def __init__(self, known: dict[str, str]) -> None:
        self.known = known
        self.asked: list[str] = []

    async def display_names(self, ids: Any) -> dict[str, str]:
        wanted = list(ids)
        self.asked += wanted
        return {i: self.known[i] for i in wanted if i in self.known}


def test_a_waiting_close_names_its_proposer_and_asks_for_no_one_else(
    world: tuple[_World, TestClient],
) -> None:
    """Step 9d finding 1: the approval screen said who proposed the close by their identity-provider
    id. The alert's detail serves the proposer's name beside the id, resolved for that one id."""
    w, client = world
    alert = _high(w)
    _save(client, w, alert)
    paths = _paths(w, alert.id)
    w.as_ = w.member
    client.post(paths["close"], json={"disposition": "referred", "reason": "to the regional unit"})
    directory = _Directory({w.member.id: "Priya Shah", w.owner.id: "Owner Name"})
    app.dependency_overrides[get_principal_names] = lambda: directory
    w.as_ = w.owner
    detail = client.get(f"{Q.format(case=w.case)}/{alert.id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert (body["alert"]["close_proposed_by"], body["close_proposed_by_name"]) == (w.member.id, "Priya Shah")
    assert directory.asked == [w.member.id]
    # Rule 3 and ADR-106 decision 3: a reader refused the alert never has its proposer looked up.
    directory.asked.clear()
    w.as_ = w.outsider
    assert client.get(f"{Q.format(case=w.case)}/{alert.id}").status_code in (403, 404)
    assert directory.asked == []
    # An alert no one has proposed closing names no proposer, and asks for no one.
    other = _high(w)
    _save(client, w, other)
    w.as_ = w.owner
    plain = client.get(f"{Q.format(case=w.case)}/{other.id}").json()
    assert plain["close_proposed_by_name"] is None and directory.asked == []
