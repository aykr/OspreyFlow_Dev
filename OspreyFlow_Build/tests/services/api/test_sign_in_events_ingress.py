"""SE8c, round 8: the session-events route is the page service's own and nobody else's, and a
session whose only authenticated use is a socket opened with a bearer header is still seen (rule 12; rules 3
and 4; `RULINGS.md` SE8: an audit row anyone can forge is a fault).

**The fault.** `POST /v1/session-events` writes a `sign_in` or `sign_out` row for the person of the
token it is given. It was called "internal" and was not: the workspace's own `/v1/` proxy
(`apps/workspace/nginx.conf.template`) and the front proxy's door to the Conduit carry it from a
browser, which holds a workspace token, and the route took a token issued to any client. A person
could write `sign_out` rows while still signed in. Round 7 shut the page service's own
browser-facing forwarder only. **Closed at the route, not at each way in:** the route accepts a token only when it
was issued to the page service's own client, and every other token is refused with one status
and one body, whatever the reason, with nothing written.

**The claim check, and why it is this one.** The Conduit already tells clients apart by the token's
own client claim: `azp` (`appid` on Entra ID v1.0), as `PrincipalResolver` does for the Glass's,
Superset's and the page service's registrations on Entra ID (`ClaimMapping.pages_client_id`, CO2),
and as `ServiceIdentityVerifier` does for an orchestrator. The page service's client is, on Entra
ID, that same `pages_client_id`; on Keycloak, where the resolver names no client, the page service's
own `OSPREY_PAGES_CLIENT_ID` (default `osprey-pages`, `harness/realm.py`). The claim must name that
client and no other: every `azp`/`appid` present, equal to it. Where the client cannot be known (an
Entra mapping with no `pages_client_id`) every token is refused.

**Rule 15: the plants take the shape the code really sees.** Tokens are signed by the real key over
the real JWKS and accepted by the real `PrincipalResolver`, so each refused token is one the
resolver admits as a person: the refusal comes from the route's own check and from nothing earlier.
The ingress case runs the route as every ingress delivers it (the same request, whichever door).

**Folders walked:** none. `app.py` is read as one named file, as the acceptance test does.
"""

# ruff: noqa: F811 - the rig's fixtures are imported by name, as pytest finds them
from __future__ import annotations

import ast
import asyncio
import json
import secrets
import time
from typing import Any

import pytest
from services.api.app import app

from tests.conftest import default_claims, sign_token
from tests.services.api import test_sign_in_events as base
from tests.services.api.test_sign_in_events import (  # noqa: F401 - fixtures, found by name
    CLIENT,
    CORE,
    Rig,
    mod,
    rig,
)

#: The deployment's own clients that a person's browser holds a token of (`harness/realm.py`).
WORKSPACE = "osprey-glass"
SUPERSET = "osprey-superset"
THIRD = "osprey-other"

#: What every token that is not the page service's is told, whatever the reason.
REFUSED = (403, {"detail": "this route is not open to this sign-in"})


def token_for(rig_: Rig, client: Any, *, person: str = "analyst-1", **claims: Any) -> str:
    """A person's token issued to `client` (None: names no client), signed by the real key."""
    body = default_claims(
        sub=person,
        sid=claims.pop("sid", secrets.token_hex(16)),
        jti=secrets.token_hex(16),
        iss=rig_.provider,
        **claims,
    )
    if client is not None:
        body["azp"] = client
    return sign_token(rig_.private, {k: v for k, v in body.items() if v is not None})


def event_rows(rig_: Rig) -> list[dict[str, Any]]:
    return base.events(rig_)


def written_by_the_route(rig_: Rig) -> list[str]:
    """Every key the route's own write leaves in Valkey: the report's mark and the rate window."""
    return [
        k
        for k in rig_.valkey.data
        if k.startswith(
            ("sign-in-events:sign_in:", "sign-in-events:sign_out:", "sign-in-events:rate:")
        )
    ]


# --- the route accepts the page service's client and no other ------------------------------------


def test_the_page_services_own_client_still_records_a_sign_in_and_a_sign_out(rig: Rig) -> None:
    token = token_for(rig, CLIENT)
    assert rig.event(token, "sign_in").json() == {"recorded": True}
    assert rig.event(token, "sign_out").json() == {"recorded": True}
    assert [r["action"] for r in event_rows(rig)] == ["sign_in", "sign_out"]
    assert {base.detail(r)["channel"] for r in event_rows(rig)} == {CLIENT}


@pytest.mark.parametrize("client", [WORKSPACE, SUPERSET, THIRD], ids=lambda c: str(c))
@pytest.mark.parametrize("kind", ["sign_in", "sign_out"])
def test_a_token_of_another_client_calls_the_route_directly_and_is_refused_with_no_row(
    rig: Rig, client: str, kind: str
) -> None:
    """A browser holding a workspace token, posting to the Conduit's route through the workspace's
    own proxy or the front proxy's door: the Conduit is what refuses."""
    token = token_for(rig, client)
    # The session was already seen (the person has used the Glass): the refusal adds no row at all.
    assert rig.me(token).status_code == 200
    rows, keys = list(rig.pool.rows), set(rig.valkey.data)
    answer = rig.event(token, kind)
    assert (answer.status_code, answer.json()) == REFUSED, answer.text
    assert rig.pool.rows == rows, "a refused call wrote a row"
    assert set(rig.valkey.data) == keys, "a refused call left something in Valkey"
    assert event_rows(rig) == []


def test_a_first_call_with_another_clients_token_writes_only_the_first_sight_never_an_event(
    rig: Rig,
) -> None:
    """The Conduit sees a session the first time it is used, by any route (item 1): that row is the
    session's, true whichever route was asked, and is not an event the caller chose."""
    answer = rig.event(token_for(rig, WORKSPACE), "sign_out")
    assert (answer.status_code, answer.json()) == REFUSED
    assert [r["action"] for r in rig.pool.rows] == ["sign_in_seen"]
    assert written_by_the_route(rig) == []


def refusal_cases(rig_: Rig) -> dict[str, str]:
    """Every shape of token the resolver admits as a person that is not the page service's."""
    return {
        "the workspace's client": token_for(rig_, WORKSPACE),
        "Superset's client": token_for(rig_, SUPERSET),
        "a third client": token_for(rig_, THIRD),
        "a token that names no client": token_for(rig_, None),
        "the page service's name in another case": token_for(rig_, CLIENT.upper()),
        "the page service's name with a suffix": token_for(rig_, CLIENT + "-2"),
        "the page service's name as a prefix of another": token_for(rig_, CLIENT[:-1]),
        "a list holding the page service's client": token_for(rig_, [CLIENT]),
        "a number": token_for(rig_, 7),
        "an empty client": token_for(rig_, ""),
        "the page service's azp and another appid": token_for(rig_, CLIENT, appid=WORKSPACE),
        "another azp and the page service's appid": token_for(rig_, WORKSPACE, appid=CLIENT),
        "an appid of another client alone": token_for(rig_, None, appid=WORKSPACE),
    }


def test_every_other_token_is_refused_with_the_same_status_and_the_same_words(rig: Rig) -> None:
    """No detail tells a person which check failed: the answers are identical byte for byte."""
    answers = {}
    for name, token in refusal_cases(rig).items():
        answer = rig.event(token, "sign_in")
        answers[name] = (
            answer.status_code,
            answer.content,
            dict(answer.headers).get("www-authenticate"),
        )
        assert event_rows(rig) == [], name
        assert written_by_the_route(rig) == [], name
    assert len(set(answers.values())) == 1, answers
    status, content, _ = next(iter(answers.values()))
    assert (status, json.loads(content)) == REFUSED


def test_the_words_of_the_refusal_name_no_claim_no_client_and_no_check(rig: Rig) -> None:
    text = rig.event(token_for(rig, WORKSPACE), "sign_in").text.lower()
    for word in (WORKSPACE, CLIENT, "azp", "appid", "client", "page", "workspace", "token"):
        assert word not in text, word


def test_the_refusal_comes_before_the_body_is_read_and_before_the_rate_limit(
    rig: Rig, mod: Any
) -> None:
    """A refused caller learns nothing of the body's shape (a body the route would refuse with 422
    is the same 403) and spends no one's rate window: the page service's own token, of the same
    person, still records after more refused calls than the window allows."""
    other = token_for(rig, WORKSPACE)
    answer = rig.http.post(
        base.ROUTE, json={"kind": "not-a-kind"}, headers={"Authorization": f"Bearer {other}"}
    )
    assert (answer.status_code, answer.json()) == REFUSED, answer.text
    for _ in range(mod.RATE_LIMIT_PER_MINUTE + 5):
        assert rig.event(other, "sign_in").status_code == 403
    assert written_by_the_route(rig) == []
    assert rig.event(token_for(rig, CLIENT), "sign_in").json() == {"recorded": True}


def test_a_person_the_resolver_refuses_is_refused_as_before_whatever_the_client(rig: Rig) -> None:
    """The client check comes after the resolver: an unknown or expired token is the 401 it always
    was, so the new check is no oracle for a token's validity."""
    expired = token_for(rig, WORKSPACE, iat=int(time.time()) - 3600, exp=int(time.time()) - 1800)
    assert rig.event(expired).status_code == 401
    assert rig.event(None).status_code == 401
    assert rig.event("not.a.token").status_code == 401
    assert rig.pool.rows == []


# --- where the page service's client is read from -----------------------------------------------


def test_the_page_services_client_is_the_named_setting_else_its_own_default(mod: Any) -> None:
    from principal_auth import ClaimMapping

    assert mod.pages_client_for(ClaimMapping(), {}) == "osprey-pages"
    assert mod.pages_client_for(ClaimMapping(), {"OSPREY_PAGES_CLIENT_ID": "osprey-pages-x"}) == (
        "osprey-pages-x"
    )
    assert mod.pages_client_for(ClaimMapping(), {"OSPREY_PAGES_CLIENT_ID": "  "}) == "osprey-pages"


def test_on_entra_the_page_services_client_is_the_mappings_and_nothing_else(mod: Any) -> None:
    """Never the environment's: on Entra ID the registration is an application id the resolver
    already admits (CO2), and one that is not set is no client at all."""
    from principal_auth import ClaimMapping

    tenant = "11111111-aaaa-4bbb-8ccc-dddddddddddd"
    glass = "22222222-aaaa-4bbb-8ccc-dddddddddddd"
    pages = "77777777-aaaa-4bbb-8ccc-dddddddddddd"
    entra = ClaimMapping(tenant_id=tenant, client_id=glass, pages_client_id=pages)
    assert mod.pages_client_for(entra, {"OSPREY_PAGES_CLIENT_ID": "osprey-pages"}) == pages
    unset = ClaimMapping(tenant_id=tenant, client_id=glass)
    assert mod.pages_client_for(unset, {"OSPREY_PAGES_CLIENT_ID": "osprey-pages"}) is None
    assert mod.from_page_service({"azp": glass}, pages) is False
    assert mod.from_page_service({"azp": pages}, pages) is True
    assert mod.from_page_service({"appid": pages}, pages) is True
    assert mod.from_page_service({"azp": pages}, None) is False


def test_where_the_page_services_client_cannot_be_known_every_token_is_refused(
    rig: Rig, mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "pages_client_for", lambda mapping, environ=None: None)
    token = token_for(rig, CLIENT)
    answer = rig.event(token, "sign_in")
    assert (answer.status_code, answer.json()) == REFUSED
    assert event_rows(rig) == []


# --- every way in -------------------------------------------------------------------------------


def test_every_ingress_the_route_has_delivers_it_to_the_one_handler_that_refuses() -> None:
    """The ingresses found (searched for in `apps/`, `harness/`, `deploy/` and the cluster chart):

    1. the page service's `/v1` forwarder: refuses the path itself (`forward.ts`, DENIED; its own
       test in `forward.test.ts`);
    2. the workspace's nginx `location /v1/`: carries every `/v1` path, the bearer included, to the
       Conduit;
    3. the front proxy (`harness/site.py`): a `reverse_proxy` for each name, no path filter, and
       the Conduit's own door (`network.expose_conduit`, port 8000) straight to it;
    4. the Conduit's own port inside the deployment's network.

    Numbers 2 to 4 carry the route, so what refuses is the handler: one route, registered once, on
    the one method, whose claim check comes before everything it does.
    """
    tree = ast.parse((CORE / "services/api/app.py").read_text())
    handlers = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef)
        and any(base.ROUTE in ast.unparse(d) for d in n.decorator_list)
    ]
    assert len(handlers) == 1
    body = ast.unparse(handlers[0])
    assert "page_service_only" in body, "the claim check is a dependency of the route itself"
    # Nothing else in the Conduit writes these rows.
    source = (CORE / "services/api/app.py").read_text()
    assert source.count("record_event(") == 1


def test_the_forwarder_still_refuses_the_route_as_a_second_door() -> None:
    """Defence in depth, not the defence: the page service's forwarder names the path in its own
    denied list (its test walks every spelling)."""
    forward = (CORE / "apps/pages/server/forward.ts").read_text()
    assert "session-events" in forward


# --- the socket's header bearer: a session whose only use is a socket is seen ---------------


class _NoAccess:
    """The case store, refusing: the socket records `access_denied` and closes, so the test ends
    where a real unreadable case would, after the authentication that is being looked at."""

    async def get_authorized(self, *args: Any, **kwargs: Any) -> None:
        from services.api.investigations import InsufficientAccessError

        raise InsufficientAccessError("no")


def open_socket(rig_: Rig, token: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr(app.state, "investigations", _NoAccess(), raising=False)
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    try:
        with rig_.http.websocket_connect(
            "/v1/investigations/case-1/stream", headers=headers
        ) as socket:
            socket.receive_text()
    except WebSocketDisconnect:
        pass


def test_a_session_whose_only_use_is_a_socket_with_a_bearer_header_is_seen(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    s = rig.session()
    token = s.token()
    open_socket(rig, token, monkeypatch)
    seen = rig.pool.of("sign_in_seen")
    assert len(seen) == 1, rig.pool.rows
    assert seen[0]["principal_id"] == "analyst-1"
    # The same session on an HTTP route is the same session: still one row.
    assert rig.me(token).status_code == 200
    assert len(rig.pool.of("sign_in_seen")) == 1
    assert base.leaks(rig, caplog, base.forbidden(token, rig, s, {})) == []


def test_a_socket_whose_token_the_resolver_refuses_writes_nothing(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    for token in (
        token_for(rig, CLIENT, iat=int(time.time()) - 3600, exp=int(time.time()) - 1800),
        "not.a.token",
        None,
    ):
        open_socket(rig, token, monkeypatch)
    assert rig.pool.of("sign_in_seen") == []


def test_every_function_that_accepts_a_token_from_the_resolver_notes_the_session() -> None:
    """Read as a syntax tree: each function of `app.py` that calls `resolve_principal` also notes
    the session, so a new way in that skips it fails here (the first gate test read `get_principal`
    alone and so could not see the socket's)."""
    tree = ast.parse((CORE / "services/api/app.py").read_text())
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef)]
    accepting = [
        f.name
        for f in functions
        if any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "resolve_principal"
            for c in ast.walk(f)
        )
    ]
    assert sorted(accepting) == ["_authenticate_websocket", "get_principal"], accepting
    for f in functions:
        if f.name in accepting:
            calls = {
                c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", "")
                for c in ast.walk(f)
                if isinstance(c, ast.Call)
            }
            assert calls & {"note_seen", "note_session_seen"}, f.name


# --- a write that fails in any way leaves nothing marked (round 7's second fault) ---------


def _plant(monkeypatch: pytest.MonkeyPatch, make: Any) -> dict[str, bool]:
    state = {"on": True}
    real = base._Conn.execute

    async def execute(self: Any, sql: str, *args: Any) -> None:
        if state["on"]:
            raise make()
        await real(self, sql, *args)

    monkeypatch.setattr(base._Conn, "execute", execute)
    return state


def _interface_error() -> BaseException:
    import asyncpg

    return asyncpg.InterfaceError("pool is closing")


def _runtime_error() -> BaseException:
    return RuntimeError("something nobody wrapped")


def _timeout() -> BaseException:
    return TimeoutError("the write took too long")


PLANTS = pytest.mark.parametrize(
    "make",
    [_interface_error, _runtime_error, _timeout],
    ids=["InterfaceError", "RuntimeError", "TimeoutError"],
)


@PLANTS
def test_whatever_fails_the_first_sight_write_the_next_request_writes_the_row(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, make: Any
) -> None:
    token = rig.session().token()
    state = _plant(monkeypatch, make)
    assert rig.me(token).status_code == 200
    assert rig.pool.rows == []
    assert [k for k in rig.valkey.data if k.startswith("sign-in-events:seen:")] == []
    state["on"] = False
    rig.use(rig.replica())
    assert rig.me(token).status_code == 200
    assert rig.me(token).status_code == 200
    assert len(rig.pool.of("sign_in_seen")) == 1


@PLANTS
def test_whatever_fails_the_report_write_the_retry_records_it_once(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, make: Any
) -> None:
    token = token_for(rig, CLIENT)
    state = _plant(monkeypatch, make)
    answer = rig.event(token, "sign_out")
    assert answer.status_code == 503 and answer.json()["error"] == "audit_unavailable"
    assert [k for k in rig.valkey.data if k.startswith("sign-in-events:sign_out:")] == []
    state["on"] = False
    assert rig.event(token, "sign_out").json() == {"recorded": True}
    assert rig.event(token, "sign_out").json() == {"recorded": False}
    assert len(rig.pool.of("sign_out")) == 1


def test_a_failure_in_the_store_call_itself_leaves_nothing_marked(rig: Rig, mod: Any) -> None:
    """The write is the whole of what follows the mark: `note_seen` is wrapped as one."""
    from schemas.domain import Principal

    token = rig.session().token()
    principal = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")

    async def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("an audit double that fails in a way nobody wrapped")

    rig.audit.record = fail  # type: ignore[method-assign]
    asyncio.run(rig.watch.note_seen(token, principal))
    assert [k for k in rig.valkey.data if k.startswith("sign-in-events:seen:")] == []
    assert rig.watch.misses == 1
