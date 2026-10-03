"""The launcher signs a person in first and shows only what their roles allow
(`06_DECISIONS.md` ADR-051, decisions 1 and 2; friction log, 29 September 2026, third item).

**The owner's words:** "the user is asked to login first and depending on the role of the user they
should be shown the interfaces that are available to them". The rulings: the Glass for any signed-in
account; Ingest Studio for an account holding any Studio role; the Admin console for `osprey-admin`.

**What this is and is not.** Hiding a tile is a courtesy to the person at the screen and is *not* an
access control (ADR-050: the Conduit enforces; the Admin console enforces `osprey-admin` itself, see
`test_webapp_sign_in.py`). The one thing here that is a control is starting the Admin console, which
needs an `osprey-admin` session, and the tests say so.

Real HTTP against the real launcher server, a real loopback identity provider that can refuse
(`tests/harness/fake_idp.py`) and a fixture `deployment.env` that carries both demo passwords, so
that "never shown" is tested against the shape that really holds them (rule 15). The launcher is
open until a deployment has been rendered (a `realm.json` exists), because before that there is
nothing to sign in to; `test_launch.py` covers that mode and is unchanged.
"""

from __future__ import annotations

import http.client
import json
import re
import threading
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from harness.realm import (
    ADMIN_ROLE,
    LAUNCHER_CLIENT_ID,
    LAUNCHER_PORT,
    LAUNCHER_REDIRECT_URI,
)
from scripts import launch

from schemas.ingest import StudioRole
from tests.harness.fake_idp import FakeIdentityProvider
from tests.test_launch import (
    CLIENT_SECRET,
    FakeProber,
    FakeSpawner,
    _page_css,
    _tile,
    _visible_text,
)
from tools.layout import REPO as _REPO

DEMO_ANALYST_PASSWORD = "analyst-pw-2c81e6"
DEMO_ADMIN_PASSWORD = "admin-pw-91b7d4"
ENV = f"""\
OSPREY_PROFILE=local-lite
OSPREY_WORKSPACE_PORT=8080
OSPREY_OIDC_CLIENT_SECRET={CLIENT_SECRET}
OSPREY_DEMO_ANALYST_PASSWORD={DEMO_ANALYST_PASSWORD}
OSPREY_DEMO_ADMIN_PASSWORD={DEMO_ADMIN_PASSWORD}
"""

USERS = {
    "ada": [ADMIN_ROLE, "analyst", *(r.value for r in StudioRole)],  # everything
    "demo-analyst": ["analyst", *(r.value for r in StudioRole)],
    "admin-only": [ADMIN_ROLE],  # a real administrator: no analysis or Studio role
    "plain": ["analyst"],
    "nobody": [],
}
GLASS, STUDIO, ADMIN = launch.GLASS, launch.INGEST, launch.ADMIN


@pytest.fixture
def idp() -> Iterator[FakeIdentityProvider]:
    provider = FakeIdentityProvider(
        client_id=LAUNCHER_CLIENT_ID, redirect_uri=LAUNCHER_REDIRECT_URI, users=dict(USERS)
    )
    try:
        yield provider
    finally:
        try:
            provider.stop()
        except Exception:  # already stopped by the test
            pass


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    out = tmp_path / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "deployment.env").write_text(ENV, encoding="utf-8")
    (out / "compose.yaml").write_text("name: osprey-local-lite\nservices: {}\n", encoding="utf-8")
    (out / "realm.json").write_text("{}", encoding="utf-8")  # a rendered realm: sign-in enforced
    tokens = tmp_path / "apps" / "workspace" / "src" / "design" / "tokens.css"
    tokens.parent.mkdir(parents=True)
    tokens.write_text(":root { --brass: #c08a34; }\n", encoding="utf-8")
    return tmp_path


@dataclass
class Rig:
    launcher: launch.Launcher
    prober: FakeProber
    spawner: FakeSpawner
    port: int
    now: list[float] = field(default_factory=lambda: [0.0])

    def browser(self) -> Browser:
        return Browser(self)


@dataclass
class Browser:
    """One person's browser: keeps cookies, sets the Host header a real browser would."""

    rig: Rig
    cookies: dict[str, str] = field(default_factory=dict)

    def request(
        self,
        method: str,
        path: str,
        *,
        host: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], str]:
        conn = http.client.HTTPConnection("127.0.0.1", self.rig.port, timeout=5)
        sent = {"Host": host or f"localhost:{self.rig.port}", **(headers or {})}
        if self.cookies:
            sent["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        conn.request(method, path, headers=sent)
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        for name, value in response.getheaders():
            if name.lower() == "set-cookie":
                pair = value.split(";", 1)[0]
                key, _, val = pair.partition("=")
                if "Max-Age=0" in value or not val:
                    self.cookies.pop(key, None)
                else:
                    self.cookies[key] = val
        out = {k.lower(): v for k, v in response.getheaders()}
        out["set-cookie-all"] = "\n".join(
            v for k, v in response.getheaders() if k.lower() == "set-cookie"
        )
        conn.close()
        return response.status, out, body

    def get(self, path: str, **kw: object) -> tuple[int, dict[str, str], str]:
        return self.request("GET", path, **kw)  # type: ignore[arg-type]

    def post(self, path: str, *, token: bool = True) -> tuple[int, dict[str, str], str]:
        return self.request(
            "POST", path, headers={"X-Launch-Token": self.rig.launcher.token if token else "x"}
        )

    def sign_in(self, idp: FakeIdentityProvider, username: str) -> int:
        status, headers, _ = self.get("/login")
        assert status == 303, headers
        callback = idp.authorise(headers["location"], username=username)
        query = urllib.parse.urlparse(callback).query
        status, _, _ = self.get(f"/callback?{query}")
        return status


@pytest.fixture
def rig(repo: Path, idp: FakeIdentityProvider) -> Iterator[Rig]:
    prober, spawner = FakeProber(), FakeSpawner()
    now = [0.0]
    launcher = launch.Launcher(
        repo_root=repo,
        prober=prober,
        spawner=spawner,
        frontend_built=True,
        clock=lambda: now[0],
        oidc_issuer=idp.issuer,
    )
    server = launch.make_server(launcher, port=0)
    port = server.server_address[1]
    launcher.bound_port = port
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield Rig(launcher, prober, spawner, port, now)
    finally:
        server.shutdown()
        server.server_close()


def _stack_up(rig: Rig) -> None:
    rig.prober.answers[f"{rig.launcher.workspace_url()}healthz"] = 200


def _tile_names(fragment: str) -> list[str]:
    return re.findall(r'<section class="tile"[^>]*data-name="([^"]+)"', fragment)


# --- the launcher is open until there is something to sign in to ---


def test_with_no_rendered_realm_the_launcher_is_open_and_has_no_sign_in_routes(
    tmp_path: Path,
) -> None:
    """Otherwise a first-time operator could not reach even the Admin console that renders it."""
    (tmp_path / "deploy" / "generated" / "local-lite").mkdir(parents=True)
    launcher = launch.Launcher(
        repo_root=tmp_path, prober=FakeProber(), spawner=FakeSpawner(), frontend_built=True
    )
    assert launcher.enforced is False
    assert _tile_names(launcher.render_tiles()) == [GLASS, STUDIO, ADMIN]


def test_with_a_rendered_realm_the_launcher_requires_sign_in(rig: Rig) -> None:
    assert rig.launcher.enforced is True


# --- before sign-in: nothing but the way in ---


def test_before_sign_in_no_interface_is_named_or_addressed(rig: Rig) -> None:
    """Catches a signed-out page that still lists the tiles, or leaks their addresses."""
    status, _, page = rig.browser().get("/")
    assert status == 200
    assert _tile_names(page) == ["OspreyFlow"]
    for name in (GLASS, STUDIO, ADMIN):
        assert f'data-name="{name}"' not in page
    assert "localhost:8080" not in page
    assert f"localhost:{launch.HARNESS_PORT}" not in page


def test_before_sign_in_the_status_and_the_tiles_reveal_only_the_sign_in_tile(rig: Rig) -> None:
    person = rig.browser()
    status, _, _ = person.get("/status")
    assert status == 401
    _, headers, fragment = person.get("/tiles")
    assert _tile_names(fragment) == ["OspreyFlow"]
    assert headers["x-launcher-mode"] == "signed-out"


def test_before_sign_in_a_stack_that_is_not_running_offers_start_and_not_sign_in(rig: Rig) -> None:
    """The identity provider is part of the stack, so without it nobody can sign in: starting it
    must be possible before signing in."""
    _, _, fragment = rig.browser().get("/tiles")
    tile = _tile(fragment, "OspreyFlow")
    assert 'data-target="stack"' in tile
    assert "Start OspreyFlow" in tile
    assert 'href="/login"' not in tile


def test_before_sign_in_a_running_stack_offers_sign_in(rig: Rig) -> None:
    _stack_up(rig)
    _, _, fragment = rig.browser().get("/tiles")
    tile = _tile(fragment, "OspreyFlow")
    assert 'href="/login"' in tile
    assert "Sign in" in tile
    assert "data-target" not in tile


def test_before_sign_in_a_starting_stack_shows_a_disabled_button(rig: Rig) -> None:
    rig.launcher.start_in_background("stack")
    rig.launcher.wait_idle()
    _, _, fragment = rig.browser().get("/tiles")
    assert "disabled" in _tile(fragment, "OspreyFlow")


def test_before_sign_in_the_page_names_the_demo_accounts_and_where_their_passwords_are(
    rig: Rig,
) -> None:
    _, _, page = rig.browser().get("/")
    text = _visible_text(page)
    assert "osprey-demo-analyst" in text
    assert "osprey-demo-admin" in text
    assert "deployment.env" in text
    assert "OSPREY_DEMO_ANALYST_PASSWORD" in text
    assert "OSPREY_DEMO_ADMIN_PASSWORD" in text


def test_no_password_or_secret_reaches_any_page_or_fragment_in_any_state(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    _stack_up(rig)
    person = rig.browser()
    seen = [person.get(p)[2] for p in ("/", "/tiles")]
    assert person.sign_in(idp, "ada") == 303
    seen += [person.get(p)[2] for p in ("/", "/tiles", "/status")]
    everything = "\n".join(seen)
    for secret in (DEMO_ANALYST_PASSWORD, DEMO_ADMIN_PASSWORD, CLIENT_SECRET):
        assert secret not in everything


# --- starting things before and after sign-in ---


def test_the_stack_can_be_started_before_signing_in(rig: Rig) -> None:
    status, _, _ = rig.browser().post("/start/stack")
    rig.launcher.wait_idle()
    assert status == 202
    assert any("up" in call for call in rig.spawner.calls)


def test_the_admin_console_cannot_be_started_without_an_admin_session(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    """The one control on this page: starting the Admin console runs a process. Catches a start
    route that trusts the page having hidden the button."""
    signed_out = rig.browser()
    assert signed_out.post("/start/admin")[0] == 403

    analyst = rig.browser()
    assert analyst.sign_in(idp, "demo-analyst") == 303
    assert analyst.post("/start/admin")[0] == 403

    rig.launcher.wait_idle()
    assert not any("harness" in " ".join(call) for call in rig.spawner.calls)


def test_an_admin_session_can_start_the_admin_console(rig: Rig, idp: FakeIdentityProvider) -> None:
    admin = rig.browser()
    assert admin.sign_in(idp, "admin-only") == 303
    assert admin.post("/start/admin")[0] == 202
    rig.launcher.wait_idle()
    assert any(call[-2:] == ["-m", "harness"] for call in rig.spawner.calls)


def test_a_start_request_still_needs_the_page_token_when_signed_in(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    admin = rig.browser()
    assert admin.sign_in(idp, "ada") == 303
    assert admin.post("/start/admin", token=False)[0] == 403
    assert not rig.spawner.calls


# --- after sign-in: the tiles the roles allow, decided on the server ---


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        ("ada", [GLASS, STUDIO, ADMIN]),
        ("demo-analyst", [GLASS, STUDIO]),
        ("admin-only", [GLASS, ADMIN]),
        ("plain", [GLASS]),  # an analyst with no Studio role: no Ingest Studio
        ("nobody", [GLASS]),  # the Glass is open to any signed-in account
    ],
)
def test_the_tiles_shown_are_exactly_those_the_roles_allow(
    rig: Rig, idp: FakeIdentityProvider, user: str, expected: list[str]
) -> None:
    person = rig.browser()
    assert person.sign_in(idp, user) == 303

    _, headers, page = person.get("/")
    _, _, fragment = person.get("/tiles")
    _, _, status = person.get("/status")

    assert _tile_names(page) == expected
    assert _tile_names(fragment) == expected
    assert sorted(json.loads(status)) == sorted(expected)
    assert headers["x-launcher-mode"] == "signed-in"
    if ADMIN not in expected:
        assert f"localhost:{launch.HARNESS_PORT}" not in page, "the console's address is shown"


@pytest.mark.parametrize("role", [r.value for r in StudioRole])
def test_any_one_studio_role_is_enough_for_the_ingest_studio(
    rig: Rig, idp: FakeIdentityProvider, role: str
) -> None:
    idp.users["one-role"] = [role]
    person = rig.browser()
    assert person.sign_in(idp, "one-role") == 303
    assert STUDIO in _tile_names(person.get("/tiles")[2])


def test_the_studio_roles_are_the_ones_the_ingest_studio_defines() -> None:
    """Catches a role added to (or renamed in) the Ingest Studio that the launcher does not know."""
    assert launch.STUDIO_ROLES == frozenset(r.value for r in StudioRole)


def test_the_page_says_who_is_signed_in_and_offers_to_sign_out(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    person = rig.browser()
    assert person.sign_in(idp, "ada") == 303
    text = _visible_text(person.get("/")[2])
    assert "Signed in as ada" in text
    assert 'href="/logout"' in person.get("/")[2]


def test_the_admin_tile_says_to_sign_in_there_with_an_admin_account(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    person = rig.browser()
    assert person.sign_in(idp, "ada") == 303
    hint = _tile(person.get("/tiles")[2], ADMIN)
    assert "osprey-admin" in hint
    assert "without a sign-in" not in hint, "that was true only before the console required one"


# --- the round trip and its refusals ---


def test_signing_in_binds_the_state_to_the_browser_that_started_it(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    starter = rig.browser()
    _, headers, _ = starter.get("/login")
    location = urllib.parse.urlparse(headers["location"])
    query = urllib.parse.parse_qs(location.query)
    assert query["client_id"] == [LAUNCHER_CLIENT_ID]
    assert query["redirect_uri"] == [LAUNCHER_REDIRECT_URI]
    assert query["code_challenge_method"] == ["S256"]
    assert "HttpOnly" in headers["set-cookie-all"]

    callback = idp.authorise(headers["location"], username="ada")
    stranger = rig.browser()  # a different browser: no login cookie
    status, _, _ = stranger.get(f"/callback?{urllib.parse.urlparse(callback).query}")
    assert status == 400
    assert _tile_names(stranger.get("/tiles")[2]) == ["OspreyFlow"]


def test_the_session_cookie_is_http_only_lax_host_only_and_not_in_the_address(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    person = rig.browser()
    _, headers, _ = person.get("/login")
    callback = idp.authorise(headers["location"], username="ada")
    status, headers, _ = person.get(f"/callback?{urllib.parse.urlparse(callback).query}")

    assert status == 303
    session = next(
        c for c in headers["set-cookie-all"].split("\n") if c.startswith(launch.SESSION_COOKIE)
    )
    assert "HttpOnly" in session and "SameSite=Lax" in session and "Path=/" in session
    assert "Domain" not in session
    assert session.split("=", 1)[1].split(";", 1)[0] not in headers["location"]
    assert headers["location"] == "/"


def test_when_the_provider_is_not_running_sign_in_says_so_and_nobody_is_signed_in(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    person = rig.browser()
    idp.stop()
    status, _, body = person.get("/login")
    assert status == 503
    assert "not running" in body.lower()
    assert "refused" not in body.lower()
    assert _tile_names(person.get("/tiles")[2]) == ["OspreyFlow"]


def test_when_the_provider_stops_between_login_and_callback_it_is_still_not_running_not_refused(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    person = rig.browser()
    _, headers, _ = person.get("/login")
    callback = idp.authorise(headers["location"], username="ada")
    idp.stop()

    status, _, body = person.get(f"/callback?{urllib.parse.urlparse(callback).query}")

    assert status == 503
    assert "not running" in body.lower()
    assert person.get("/status")[0] == 401


def test_a_provider_that_refuses_the_code_is_a_refusal_not_unreachable(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    person = rig.browser()
    _, headers, _ = person.get("/login")
    callback = idp.authorise(headers["location"], username="ada")
    idp.token_status = 400
    status, _, body = person.get(f"/callback?{urllib.parse.urlparse(callback).query}")
    assert status == 403
    assert "not running" not in body.lower()


def test_a_token_minted_for_another_client_does_not_sign_in(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    idp.claim_overrides = {"aud": "osprey-glass"}
    person = rig.browser()
    assert person.sign_in(idp, "ada") == 403
    assert _tile_names(person.get("/tiles")[2]) == ["OspreyFlow"]


def test_a_made_up_session_cookie_is_not_a_session(rig: Rig) -> None:
    person = rig.browser()
    person.cookies[launch.SESSION_COOKIE] = "a" * 43
    assert person.get("/status")[0] == 401


def test_a_session_ends_at_its_absolute_expiry(rig: Rig, idp: FakeIdentityProvider) -> None:
    person = rig.browser()
    assert person.sign_in(idp, "ada") == 303
    rig.now[0] = 8 * 3600 - 1
    assert person.get("/status")[0] == 200
    rig.now[0] = 8 * 3600 + 1
    assert person.get("/status")[0] == 401


def test_signing_out_ends_the_session_here_and_at_the_provider(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    person = rig.browser()
    assert person.sign_in(idp, "ada") == 303
    stolen = dict(person.cookies)

    status, headers, _ = person.get("/logout")

    assert status == 303
    assert headers["location"].startswith(idp.issuer + "/protocol/openid-connect/logout")
    assert person.get("/status")[0] == 401
    replay = rig.browser()
    replay.cookies.update(stolen)
    assert replay.get("/status")[0] == 401, "the token must die on the server too"


# --- the browser's own attacks ---


def test_a_request_addressed_to_another_host_name_is_refused(rig: Rig) -> None:
    status, _, _ = rig.browser().get("/", host="evil.example:7070")
    assert status == 403


def test_the_address_127_0_0_1_is_sent_to_localhost_so_the_cookie_and_redirect_agree(
    rig: Rig,
) -> None:
    status, headers, _ = rig.browser().get("/?x=1", host=f"127.0.0.1:{rig.port}")
    assert status in (301, 302, 303, 307, 308)
    assert headers["location"] == f"http://localhost:{rig.port}/?x=1"


def test_a_start_request_from_another_origin_is_refused_even_with_the_token(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    person = rig.browser()
    assert person.sign_in(idp, "ada") == 303
    status, _, _ = person.request(
        "POST",
        "/start/admin",
        headers={"X-Launch-Token": rig.launcher.token, "Origin": "http://evil.example"},
    )
    assert status == 403
    assert not rig.spawner.calls


# --- the design system and plain language still hold on the new pages ---


def _pages(rig: Rig, idp: FakeIdentityProvider) -> dict[str, str]:
    signed_out = rig.browser().get("/")[2]
    person = rig.browser()
    person.sign_in(idp, "ada")
    return {"signed-out": signed_out, "signed-in": person.get("/")[2]}


def test_the_new_pages_define_no_colour_and_use_only_tokens_that_exist(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    real = (
        _REPO / "apps" / "workspace" / "src" / "design" / "tokens.css"
    ).read_text(encoding="utf-8")
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", real))
    for label, page in _pages(rig, idp).items():
        css = _page_css(page)
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\b(rgb|hsl|color)a?\(", css), label
        assert "style=" not in page, label
        assert set(re.findall(r"var\((--[a-z0-9-]+)", css)) <= defined, label


def test_the_new_pages_speak_the_products_words_not_the_machinerys(
    rig: Rig, idp: FakeIdentityProvider
) -> None:
    for label, page in _pages(rig, idp).items():
        text = _visible_text(page).lower()
        for word in ("harness", "conduit", "docker", "compose", "proxy", "keycloak", "oidc", "jwt"):
            assert word not in text, f"{label}: {word!r}"


def test_the_launcher_will_only_start_on_the_port_the_realm_registers() -> None:
    """The sign-in redirect is one exact address, so another port could never complete it."""
    assert launch.port_problem(LAUNCHER_PORT, enforced=True) is None
    assert launch.port_problem(9999, enforced=False) is None
    problem = launch.port_problem(9999, enforced=True)
    assert problem and str(LAUNCHER_PORT) in problem


def test_the_launchers_message_pages_follow_the_light_and_dark_choice_too(rig: Rig) -> None:
    """ADR-072. The sign-in refusals and "not running" pages are separate small pages; left alone they
    stay dark when everything else is light. An invalid sign-in link is the quickest one to reach."""
    status, _, body = rig.browser().get("/callback?state=not-a-real-attempt&code=x")
    assert status == 400
    script = (Path(launch.__file__).resolve().parents[1] / "harness" / "theme_cookie.js").read_text(
        encoding="utf-8"
    )
    assert script.strip() in body
