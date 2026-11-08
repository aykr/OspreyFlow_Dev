"""An alert's own address against the real stack (`06_DECISIONS.md` ADR-146 decision 6 and Amendment 2
point 6; the orchestrator's independent review of L2.9, blockers 1 and 2).

The route is reached the way the Glass reaches it: the real app with its lifespan, a signed token read
by the real `get_principal` (a path naming no case, so the reader reads no dataset until the route
scopes it), the real `PostgresAlertStore.case_of`, the real hotlist and alert stores, and ArcadeDB.
The hermetic cases are in `test_alert_address.py`; this proves the same through the real dependencies,
which refuse what the fakes stand in for (rule 15).

The refusals are compared byte for byte, and timed: with the wait switched off, a hidden alert costs
more than a missing one (the reads differ); with it, all three are answered on the same quantum.
With `OSPREY_ADDRESS_TIMING_OUT` set, the timings are written there as the run's record.
"""

from __future__ import annotations

import os
import statistics
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from conduit_common.identity import new_id
from schemas.domain import Alert, AlertMode, Handling, NodeWrite, Principal, Provenance
from schemas.domain import ProvenanceState, SourceRef
from tests.conftest import default_claims, sign_token
from tests.services.api.case_dataset import new_case

#: Timed requests per refusal, after three to warm.
N = int(os.environ.get("OSPREY_ADDRESS_TIMING_N", "15"))


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    keys = ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update({"OIDC_JWKS_URL": jwks_url, "OIDC_ALGORITHMS": "RS256", "ARCADEDB_DATABASE": "ospreyflow"})
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _node(dataset: str, classification: str) -> NodeWrite:
    now = datetime.now(UTC)
    unit = "unit-1" if classification == "OFFICIAL" else "unit-2"
    return NodeWrite(
        id=new_id(), type="Endpoint",
        properties={"value_normalised": "+447700900918", "endpoint_kind": "msisdn"},
        provenance=Provenance(state=ProvenanceState.ASSERTED, first_seen=now,
                              sources=[SourceRef(document_id="in/address.csv", locator="row 1", excerpt_hash="")]),
        handling=Handling(classification=classification, handling_code="P", originator=unit, owning_unit=unit),
        created_by="test", created_at=now, datasets=[dataset],
    )  # fmt: skip


async def _seed(app: object, case: str, other_case: str, owner: str) -> dict[str, str]:
    """A readable alert, one over a node hidden from the reader, and one in a case not theirs: each a
    hotlist alert of the reader's own, in its case's dataset, so the queue's scope admits it to them
    in its case. Written through the app's own stores and graph, the ones the route reads."""
    state = app.state  # type: ignore[attr-defined]
    dataset = (await state.datasets.chosen_of_case(case))[0].id
    who = Principal(id=owner, clearance="OFFICIAL", org_unit="unit-1", datasets=[dataset])
    hotlist = await state.hotlists_store.create(who, identifier="07700 900918", review_date=date(2027, 1, 31))
    graph = state.graph
    tx = await graph.begin_transaction()
    seen, hidden = await graph.upsert_nodes([_node(dataset, "OFFICIAL"), _node(dataset, "SECRET")], tx)
    await graph.commit_transaction(tx)
    made = {}
    for name, node, in_case in (("readable", seen, case), ("hidden", hidden, case), ("elsewhere", seen, other_case)):
        alert = Alert(
            id=new_id(), rule_id=f"hotlist:{hotlist.id}", owner_id=owner, mode=AlertMode.FULL,
            referent_node_ids=[node], investigation_id=in_case, dataset_id=dataset,
            created_at=datetime.now(UTC),
        )  # fmt: skip
        await state.alerts_store.save(alert)
        made[name] = alert.id
    return made


def _times(client: TestClient, path: str, headers: dict[str, str]) -> list[float]:
    for _ in range(3):
        client.get(path, headers=headers)
    out = []
    for _ in range(N):
        t = time.perf_counter()
        client.get(path, headers=headers)
        out.append(time.perf_counter() - t)
    return out


def _line(name: str, xs: list[float]) -> str:
    q = statistics.quantiles(xs, n=4)
    return (f"{name}: n={len(xs)} median={statistics.median(xs) * 1000:.1f} ms "
            f"q1={q[0] * 1000:.1f} q3={q[2] * 1000:.1f} max={max(xs) * 1000:.1f}")  # fmt: skip


def test_the_address_answers_through_the_real_stores_and_refuses_alike_on_one_quantum(
    api_env: None, keypair: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.api import rules_place
    from services.api.app import app

    private_key, _ = keypair
    me, them = f"addr-{new_id()}", f"addr-other-{new_id()}"
    reader = {"Authorization": f"Bearer {sign_token(private_key, default_claims(sub=me))}"}
    other = {"Authorization": f"Bearer {sign_token(private_key, default_claims(sub=them))}"}
    with TestClient(app) as client:
        made = [client.post("/v1/investigations", headers=h, json=new_case()) for h in (reader, other)]
        assert [m.status_code for m in made] == [201, 201], [m.text for m in made]
        case, other_case = (m.json()["id"] for m in made)
        ids = client.portal.call(_seed, app, case, other_case, me)  # type: ignore[union-attr]

        # Through the real `get_principal` and `case_of`: the alert, in its own case, with its node.
        opened = client.get(f"/v1/alerts/{ids['readable']}", headers=reader)
        assert opened.status_code == 200, opened.text
        assert opened.json()["investigation_id"] == case
        assert len(opened.json()["explanation"]["nodes"]) == 1, opened.json()

        # Refused alike: the same status and the same bytes.
        missing = client.get(f"/v1/alerts/no-such-alert-{new_id()}", headers=reader)
        answers = {
            "hidden": client.get(f"/v1/alerts/{ids['hidden']}", headers=reader),
            "elsewhere": client.get(f"/v1/alerts/{ids['elsewhere']}", headers=reader),
        }
        assert missing.status_code == 404 and "alert_not_found" in missing.text, missing.text
        for name, refused in answers.items():
            assert (refused.status_code, refused.content) == (404, missing.content), (name, refused.text)

        paths = {"missing": f"/v1/alerts/no-such-alert-{new_id()}", "elsewhere": f"/v1/alerts/{ids['elsewhere']}",
                 "hidden": f"/v1/alerts/{ids['hidden']}"}  # fmt: skip
        # The reads alone, the wait switched off; then as served.
        monkeypatch.setattr(rules_place, "sleep", _no_wait)
        raw = {name: _times(client, path, reader) for name, path in paths.items()}
        monkeypatch.undo()
        held = {name: _times(client, path, reader) for name, path in paths.items()}

    q = rules_place.ADDRESS_REFUSAL_QUANTUM
    lines = [f"quantum {q * 1000:.0f} ms; {N} timed requests each, after 3 to warm"]
    lines += ["without the wait:"] + [f"  {_line(k, v)}" for k, v in raw.items()]
    lines += ["with the wait:"] + [f"  {_line(k, v)}" for k, v in held.items()]
    out = os.environ.get("OSPREY_ADDRESS_TIMING_OUT")
    if out:
        with open(out, "a") as f:
            f.write("\n".join(lines) + "\n")
    # Every refusal's work fits in one quantum, so each is answered on the first.
    assert max(max(v) for v in raw.values()) < q, lines
    for v in held.values():
        assert q <= statistics.median(v) < q + 0.05, lines
    medians = [statistics.median(v) for v in held.values()]
    assert max(medians) - min(medians) < 0.01, lines


async def _no_wait(seconds: float) -> None:
    return None

