"""The Admin console enforces `osprey-admin` itself (`06_DECISIONS.md` ADR-051, decision 4).

Standing rule 4: every read path gets an access-control test. So the route-by-route cases below are
built **from the real app's route table**, not from a list someone remembers to extend: a route
added to `harness/webapp.py` tomorrow is covered the day it lands, and a route that is skipped
fails the coverage assertion rather than passing by omission.

Rule 15: real requests through the real app against a real loopback provider that can refuse
(`tests/harness/fake_idp.py`); the planted violations in the commit message are the real call-site
shape (a middleware that lets one method through, a cookie that is not checked, and so on).

Enforcement is decided when the console starts: a rendered realm under `out_root` means sign-in is
required; none means the bootstrap console, which stays open (there is nothing to sign in to).
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from harness.oidc import LoginAttempts, SessionStore
from harness.realm import ADMIN_ROLE, HARNESS_CLIENT_ID, HARNESS_PORT, HARNESS_REDIRECT_URI
from harness.webapp import create_app
from starlette.routing import Mount

from harness import webapp_signin
from tests.harness.fake_idp import AuthorisationRefused, FakeIdentityProvider

BASE = f"http://localhost:{HARNESS_PORT}"
PUBLIC_PATHS = {"/login", "/callback", "/logout"}
USERS = {"ada": [ADMIN_ROLE], "grace": ["analyst", "source_author"], "nobody": []}


@pytest.fixture
def idp() -> Iterator[FakeIdentityProvider]:
    provider = FakeIdentityProvider(
        client_id=HARNESS_CLIENT_ID, redirect_uri=HARNESS_REDIRECT_URI, users=dict(USERS)
    )
    try:
        yield provider
    finally:
        try:
            provider.stop()
        except Exception:  # already stopped by the test
            pass


def _out_root(tmp_path: Path, *, with_realm: bool) -> Path:
    root = tmp_path / "generated"
    (root / "local-lite").mkdir(parents=True, exist_ok=True)
    if with_realm:
        (root / "local-lite" / "realm.json").write_text("{}", encoding="utf-8")
    return root


def _app(tmp_path: Path, idp: FakeIdentityProvider | None, *, with_realm: bool = True, **kw: Any):
    return create_app(
        config_path=tmp_path / "osprey.yaml",
        out_root=_out_root(tmp_path, with_realm=with_realm),
        oidc_issuer=idp.issuer if idp else None,
        **kw,
    )


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url=BASE, client=("127.0.0.1", 51000), follow_redirects=False)


def _sign_in(client: TestClient, idp: FakeIdentityProvider, username: str = "ada") -> Any:
    """The browser's whole round trip. Returns the callback response."""
    login = client.get("/login")
    assert login.status_code == 303, login.text
    callback = idp.authorise(login.headers["location"], username=username)
    query = urllib.parse.urlparse(callback).query
    return client.get(f"/callback?{query}")


def _signed_in(tmp_path: Path, idp: FakeIdentityProvider, **kw: Any) -> tuple[Any, TestClient]:
    app = _app(tmp_path, idp, **kw)
    client = _client(app)
    response = _sign_in(client, idp)
    assert response.status_code == 303, response.text
    return app, client


# --- the bootstrap console stays open, and says nothing about sign-in ---


def test_with_no_rendered_realm_the_console_is_open_because_there_is_nothing_to_sign_in_to(
    tmp_path: Path,
) -> None:
    """Otherwise a first-time operator could never reach the wizard that creates the realm."""
    client = _client(_app(tmp_path, None, with_realm=False))
    assert client.get("/api/config").status_code == 200
    for path in PUBLIC_PATHS:
        assert client.get(path).status_code == 404, f"{path} exists although nothing is enforced"


def test_the_console_starts_enforced_when_a_realm_has_been_rendered(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    assert _app(tmp_path / "with", idp).state.sign_in is not None
    assert _app(tmp_path / "without", idp, with_realm=False).state.sign_in is None


def test_a_deployment_folder_that_cannot_be_read_is_treated_as_rendered_not_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When it cannot be told whether a realm exists, the safe answer is to require sign-in, never
    to open the console because a listing failed."""

    def unreadable(self: Path, pattern: str) -> Any:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "glob", unreadable)
    assert webapp_signin.rendered_realm_exists(tmp_path) is True


# --- rule 4: every route, from the real route table ---


def _every_route(app: Any) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            path = route.path
            for token in [t for t in path.split("/") if t.startswith("{")]:
                path = path.replace(token, "x")
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                found.append((method, path))
        elif isinstance(route, Mount):
            found.append(("GET", route.path or "/"))
        elif getattr(route, "path", None):  # /docs, /openapi.json, /redoc
            for method in sorted(getattr(route, "methods", None) or {"GET"}):
                if method not in {"HEAD", "OPTIONS"}:
                    found.append((method, route.path))
    return found


def test_every_route_of_the_real_app_refuses_a_request_with_no_session(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    app = _app(tmp_path, idp)
    client = _client(app)
    routes = [(m, p) for m, p in _every_route(app) if p not in PUBLIC_PATHS]

    assert len(routes) >= 15, f"the route table looks wrong: {routes}"
    assert ("POST", "/api/launch/stream") in routes
    assert ("PUT", "/api/config") in routes
    assert ("DELETE", "/api/real-data-exceptions/x") in routes
    assert ("GET", "/admin") in routes
    for method, path in routes:
        response = client.request(method, path)
        assert response.status_code in (401, 303), f"{method} {path}: {response.status_code}"
        if path.startswith("/api/"):
            assert response.status_code == 401, f"{method} {path}"
        else:
            assert response.headers["location"] == "/login", f"{method} {path}"


def test_the_front_end_itself_is_not_served_to_a_person_who_is_not_signed_in(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    """Catches enforcement that covers `/api/` but leaves the pages, and the screens' own code,
    open."""
    client = _client(_app(tmp_path, idp))
    for path in ("/", "/index.html", "/assets/app.js", "/anything/else"):
        response = client.get(path)
        assert response.status_code == 303, path
        assert response.headers["location"] == "/login"


def test_a_signed_in_administrator_reaches_the_routes(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    _, client = _signed_in(tmp_path, idp)
    assert client.get("/api/config").status_code == 200
    assert client.get("/api/profile-options/local-lite").status_code == 200


# --- the sign-in round trip ---


def test_login_sends_the_browser_to_the_provider_with_pkce_and_binds_the_state_to_a_cookie(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    response = _client(_app(tmp_path, idp)).get("/login")

    location = urllib.parse.urlparse(response.headers["location"])
    query = urllib.parse.parse_qs(location.query)
    assert response.headers["location"].startswith(idp.issuer)
    assert query["client_id"] == [HARNESS_CLIENT_ID]
    assert query["redirect_uri"] == [HARNESS_REDIRECT_URI]
    assert query["code_challenge_method"] == ["S256"]
    cookie = response.headers["set-cookie"]
    assert query["state"][0] in cookie
    assert "HttpOnly" in cookie


def test_the_session_cookie_is_http_only_lax_and_host_only_and_never_appears_in_an_address(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    app = _app(tmp_path, idp)
    client = _client(app)
    response = _sign_in(client, idp)

    cookies = response.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith(webapp_signin.SESSION_COOKIE))
    assert "HttpOnly" in session
    assert "SameSite=lax" in session
    assert "Path=/" in session
    assert "Domain" not in session, "a host-only cookie is not sent to sibling hosts"
    token = session.split("=", 1)[1].split(";", 1)[0]
    assert token not in response.headers["location"]
    assert response.headers["location"] == "/"


def test_an_account_without_the_admin_role_is_told_so_and_gets_no_session(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    """The realm authenticated them; the console still refuses. Catches a callback that creates a
    session for any valid sign-in."""
    client = _client(_app(tmp_path, idp))
    response = _sign_in(client, idp, "grace")

    assert response.status_code == 403
    assert "not an administrator" in response.text
    assert "grace" in response.text
    assert "/logout" in response.text, "signing in again would silently re-use the same account"
    assert webapp_signin.SESSION_COOKIE not in response.headers.get("set-cookie", "")
    assert client.get("/api/config").status_code == 401


def test_an_account_with_no_roles_at_all_gets_no_session(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    client = _client(_app(tmp_path, idp))
    assert _sign_in(client, idp, "nobody").status_code == 403
    assert client.get("/api/config").status_code == 401


def test_a_callback_from_a_different_browser_is_refused(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    """Login CSRF: someone else's code and state, arriving in a browser that did not start the
    sign-in, must not sign that browser in as them."""
    app = _app(tmp_path, idp)
    starter = _client(app)
    login = starter.get("/login")
    callback = idp.authorise(login.headers["location"], username="ada")

    other = _client(app)  # a different browser: no login cookie
    response = other.get(f"/callback?{urllib.parse.urlparse(callback).query}")

    assert response.status_code == 400
    assert other.get("/api/config").status_code == 401


def test_a_callback_with_an_unknown_or_replayed_state_is_refused(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    client = _client(_app(tmp_path, idp))
    login = client.get("/login")
    callback = idp.authorise(login.headers["location"], username="ada")
    query = urllib.parse.urlparse(callback).query

    assert client.get(f"/callback?{query}").status_code == 303
    client.cookies.set(webapp_signin.LOGIN_COOKIE, urllib.parse.parse_qs(query)["state"][0])
    assert client.get(f"/callback?{query}").status_code == 400, "a state is single-use"
    assert client.get("/callback?code=x&state=never-issued").status_code == 400
    assert client.get("/callback").status_code == 400


def test_the_provider_reporting_an_error_is_shown_as_not_completed_and_signs_nobody_in(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    client = _client(_app(tmp_path, idp))
    client.get("/login")
    response = client.get("/callback?error=access_denied")
    assert response.status_code in (400, 403)
    assert client.get("/api/config").status_code == 401


# --- unreachable is not refused (ADR-044) ---


def test_when_the_provider_is_not_running_the_person_is_told_to_start_it_not_to_try_another_account(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    client = _client(_app(tmp_path, idp))
    idp.stop()

    response = client.get("/login")

    assert response.status_code == 503
    assert "not running" in response.text.lower()
    assert "make launch" in response.text
    assert "refused" not in response.text.lower()
    assert client.get("/api/config").status_code == 401, "fails closed, never open"


def test_when_the_provider_dies_between_login_and_callback_it_is_still_unreachable_not_refused(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    client = _client(_app(tmp_path, idp))
    login = client.get("/login")
    callback = idp.authorise(login.headers["location"], username="ada")
    idp.stop()

    response = client.get(f"/callback?{urllib.parse.urlparse(callback).query}")

    assert response.status_code == 503
    assert client.get("/api/config").status_code == 401


def test_a_provider_that_refuses_the_code_is_a_refusal_not_unreachable(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    client = _client(_app(tmp_path, idp))
    login = client.get("/login")
    callback = idp.authorise(login.headers["location"], username="ada")
    idp.token_status = 400

    response = client.get(f"/callback?{urllib.parse.urlparse(callback).query}")

    assert response.status_code == 403
    assert "not running" not in response.text.lower()


def test_a_token_minted_for_another_client_does_not_sign_in(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    """The realm's own Glass token (audience `osprey-glass`) must not open the console."""
    idp.claim_overrides = {"aud": "osprey-glass"}
    client = _client(_app(tmp_path, idp))
    assert _sign_in(client, idp).status_code == 403
    assert client.get("/api/config").status_code == 401


# --- sessions ---


def test_a_made_up_session_cookie_is_not_a_session(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    client = _client(_app(tmp_path, idp))
    client.cookies.set(webapp_signin.SESSION_COOKIE, "a" * 43)
    assert client.get("/api/config").status_code == 401


def test_a_session_from_before_a_restart_is_not_valid_afterwards(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    _, client = _signed_in(tmp_path, idp)
    restarted = _client(_app(tmp_path, idp))
    restarted.cookies.update(client.cookies)
    assert restarted.get("/api/config").status_code == 401


def test_a_session_ends_at_its_absolute_expiry(tmp_path: Path, idp: FakeIdentityProvider) -> None:
    now = [0.0]
    settings = webapp_signin.make_settings(idp.issuer)
    settings.sessions = SessionStore(ttl_seconds=60.0, clock=lambda: now[0])
    settings.attempts = LoginAttempts(clock=lambda: now[0])
    app = _app(tmp_path, idp, sign_in=settings)
    client = _client(app)
    assert _sign_in(client, idp).status_code == 303
    now[0] = 59.0
    assert client.get("/api/config").status_code == 200
    now[0] = 61.0
    assert client.get("/api/config").status_code == 401


def test_signing_out_ends_the_session_here_and_at_the_provider(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    """If it only cleared the cookie, the provider's own cookie would sign the person straight
    back in and 'sign out' would do nothing visible."""
    _, client = _signed_in(tmp_path, idp)
    stolen = dict(client.cookies)

    response = client.get("/logout")

    assert response.status_code == 303
    assert response.headers["location"].startswith(idp.issuer + "/protocol/openid-connect/logout")
    assert client.get("/api/config").status_code == 401
    replay = _client(client.app)
    replay.cookies.update(stolen)
    assert replay.get("/api/config").status_code == 401, "the token must die on the server too"


def test_a_bearer_token_does_not_stand_in_for_a_session(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    """One way in, so there is one thing to get right."""
    client = _client(_app(tmp_path, idp))
    response = client.get("/api/config", headers={"Authorization": "Bearer anything.at.all"})
    assert response.status_code == 401


# --- the browser's own attacks ---


def test_a_state_changing_request_from_another_origin_is_refused_even_with_a_valid_session(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    """Cross-site request forgery: another page in the same browser posting to localhost."""
    _, client = _signed_in(tmp_path, idp)

    forged = client.put("/api/config", json={}, headers={"Origin": "http://evil.example"})
    assert forged.status_code == 403

    same = client.put("/api/config", json={}, headers={"Origin": BASE})
    assert same.status_code != 403, "a same-origin request must not be refused as forged"
    plain = client.put("/api/config", json={})
    assert plain.status_code != 403, "no Origin (a script, not a browser) is not refused as forged"


def test_a_request_addressed_to_another_host_name_is_refused_even_with_a_valid_session(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    """DNS rebinding: a site whose name points at this machine reaches the console, but cannot
    borrow the session, and is refused outright."""
    _, client = _signed_in(tmp_path, idp)
    response = client.get("/api/config", headers={"Host": f"evil.example:{HARNESS_PORT}"})
    assert response.status_code == 403


def test_the_address_127_0_0_1_is_sent_to_localhost_so_the_cookie_and_redirect_agree(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    client = _client(_app(tmp_path, idp))
    response = client.get("/login?x=1", headers={"Host": f"127.0.0.1:{HARNESS_PORT}"})
    assert response.status_code in (301, 302, 303, 307, 308)
    assert response.headers["location"] == f"{BASE}/login?x=1"


# --- other modes and starting up ---


def test_console_mode_is_unchanged_by_a_rendered_realm(
    tmp_path: Path, idp: FakeIdentityProvider
) -> None:
    """`/admin` in console mode stays bearer-only and answers 404, never a redirect to a sign-in
    page (R2: existence must not be inferable)."""
    app = _app(tmp_path, idp, mode="console")
    assert app.state.sign_in is None
    assert _client(app).get("/admin").status_code == 404


def test_the_client_registered_in_the_realm_only_allows_the_harness_port(
    idp: FakeIdentityProvider,
) -> None:
    """Sign-in redirects to a fixed address. A console served on another port would fail at the
    provider with an error page, so start-up refuses that rather than leaving the operator to
    discover it."""
    assert webapp_signin.port_problem(HARNESS_PORT, enforced=True) is None
    assert webapp_signin.port_problem(7001, enforced=False) is None
    problem = webapp_signin.port_problem(7001, enforced=True)
    assert problem and str(HARNESS_PORT) in problem


def test_the_authorisation_helper_really_refuses_an_unregistered_redirect(
    idp: FakeIdentityProvider,
) -> None:
    """Guards the fixture itself: if it accepted anything, the tests above would prove nothing
    about the redirect the realm registers."""
    with pytest.raises(AuthorisationRefused):
        idp.authorise(
            f"{idp.issuer}/protocol/openid-connect/auth?"
            + urllib.parse.urlencode(
                {
                    "response_type": "code",
                    "client_id": HARNESS_CLIENT_ID,
                    "redirect_uri": "http://localhost:7000/elsewhere",
                    "code_challenge": "x",
                    "code_challenge_method": "S256",
                    "state": "s",
                }
            ),
            username="ada",
        )
