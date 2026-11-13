"""ADR-114 Amendment 41, against the real proxy: the Caddyfile `harness.site.render_caddyfile` renders
for a deployment that asks for the shared key, run by Caddy 2.11.4 itself (the version the product
pins, `harness.site.PROXY_IMAGE`), with the key file `harness.access_key` writes and a stand-in behind
each name that records what reaches it. The access-control test of every name (rule 4).

The stand-in is never the judge: every refusal below is Caddy's own. The hash is made by Caddy's own
`hash-password`, as the helper makes it on the server.

Needs a `caddy` 2.11 binary: `OSPREY_TEST_CADDY`, else `caddy` on the PATH; skipped, in words,
without one. `gate/B-proxy-*.raw.txt` has the runs, red and green. The proxy itself is
`access_key_proxy_fixtures.py`'s, shared with admin's refresh tests.
"""

# ruff: noqa: F811  (each test takes the shared `proxy` fixture, imported by name, as its argument)
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest
from harness import access_key

from .access_key_proxy_fixtures import (  # noqa: F401  (proxy: the fixture, by name)
    CADDY,
    HOST,
    KEY,
    NAMES,
    NEEDS_CADDY,
    OPEN_PATHS,
    Proxy,
    free_port,
    hash_key,
    pass_cookie,
    proxy,
    run_again,
    run_caddy,
    stand_in_server,
    write_caddyfile,
)

pytestmark = NEEDS_CADDY


@pytest.mark.parametrize("name", NAMES)
def test_without_the_key_nothing_behind_the_proxy_answers(proxy: Proxy, name: str) -> None:
    status, fields = proxy.ask(name, "/")
    assert status == 401
    assert fields["www-authenticate"][0].startswith("Basic")
    assert fields["x-robots-tag"] == ["noindex, nofollow"]
    assert proxy.stand_in.seen == []


@pytest.mark.parametrize("name", NAMES)
def test_a_wrong_key_or_user_is_refused_and_given_no_pass(proxy: Proxy, name: str) -> None:
    for user, key in (("demo", "not the shared key"), ("someone", KEY), (None, None)):
        status, fields = proxy.ask(name, "/", user=user, key=key)
        assert status == 401
        assert "set-cookie" not in fields
    assert proxy.stand_in.seen == []


@pytest.mark.parametrize("name", NAMES)
def test_a_refusal_says_nothing_more(proxy: Proxy, name: str) -> None:
    """The 401 has no body and a realm that names only the product: the box asks, and nothing of
    the deployment, its services or why is told. (Caddy's own `Server: Caddy` stays: a refusal is
    written by its error path, which a deferred header deletion does not reach.)"""
    status, fields = proxy.ask(name, "/v1/anything", user="demo", key="not the shared key")
    assert status == 401
    assert proxy.body == b""
    assert fields["www-authenticate"] == ['Basic realm="OspreyFlow"']
    assert set(fields) <= {"www-authenticate", "x-robots-tag", "server", "alt-svc", "date",
                           "content-length"}, fields  # fmt: skip


def test_every_attempt_is_logged_and_the_log_holds_no_key_and_no_pass(proxy: Proxy) -> None:
    """Each answer, a refusal included, is in the proxy's own log (`docker compose logs proxy`),
    with Caddy's redaction of `Authorization` and `Cookie`: never the key, nor the pass."""
    assert proxy.folder is not None
    proxy.ask(HOST, "/attempt", user="demo", key="a wrong guess at the key")
    proxy.ask(HOST, "/with-pass", headers=pass_cookie(proxy))
    proxy.ask(HOST, "/with-key", user="demo", key=KEY)
    deadline = time.monotonic() + 5
    log = ""
    while time.monotonic() < deadline and "/with-key" not in log:
        log = (proxy.folder / "caddy.log").read_text(errors="replace")
        time.sleep(0.1)
    attempt = [line for line in log.splitlines() if '"/attempt"' in line]
    assert attempt and '"status":401' in attempt[0]
    for secret in (KEY, "a wrong guess at the key", proxy.token):
        assert secret not in log
    import base64

    assert base64.b64encode(f"demo:{KEY}".encode()).decode() not in log


@pytest.mark.parametrize("name", NAMES)
def test_the_key_lets_a_browser_in_gives_it_the_pass_and_never_reaches_behind(
    proxy: Proxy, name: str
) -> None:
    status, fields = proxy.ask(name, "/", user="demo", key=KEY)
    assert status == 200
    assert fields["x-robots-tag"] == ["noindex, nofollow"]
    (given,) = [c for c in fields["set-cookie"] if c.startswith(f"{access_key.PASS_COOKIE}=")]
    # ADR-114 Amendment 42: for the deployment's own base name, so one answer passes all three
    # names (and nothing outside the base). Eight hours at most.
    assert given == (f"{access_key.PASS_COOKIE}={proxy.token}; Domain={HOST}; Path=/; Max-Age=28800; "
                     "Secure; HttpOnly; SameSite=Lax")  # fmt: skip
    (seen,) = proxy.stand_in.seen
    assert seen.authorization is None, "the key reached the service behind the proxy"


@pytest.mark.parametrize("name", NAMES)
def test_the_pass_lets_in_a_request_with_a_token_of_its_own(proxy: Proxy, name: str) -> None:
    """The Glass's own API calls carry `Authorization: Bearer`, which a browser sends in place of
    the key; the pass lets them in, and their token reaches the service unchanged."""
    status, fields = proxy.ask(
        name, "/v1/x", headers={**pass_cookie(proxy), "Authorization": "Bearer abc"}
    )
    assert status == 200 and fields["x-robots-tag"] == ["noindex, nofollow"]
    (seen,) = proxy.stand_in.seen
    assert seen.authorization == "Bearer abc"


@pytest.mark.parametrize("name", NAMES)
def test_a_forged_pass_is_refused(proxy: Proxy, name: str) -> None:
    forged = [
        f"{access_key.PASS_COOKIE}={'x' * 43}",
        f"{access_key.PASS_COOKIE}=",
        f"{access_key.PASS_COOKIE}={proxy.token[:-1]}",
        f"other={proxy.token}",
    ]
    for cookie in forged:
        assert proxy.ask(name, "/", headers={"Cookie": cookie})[0] == 401, cookie
    assert proxy.stand_in.seen == []


def test_setting_the_key_again_refuses_the_old_pass_and_the_old_key(proxy: Proxy, tmp_path: Path) -> None:
    """The helper and `ospreyflow apply`: a new hash and a new pass, and the proxy restarted with
    them; the browser holding the old pass, or the old key, is asked again."""
    old = proxy.token
    assert proxy.ask(HOST, "/", headers=pass_cookie(proxy))[0] == 200
    access_key.set_key(tmp_path, user="demo", ask=lambda _prompt: KEY + " renewed", hasher=hash_key)
    access_key.carry_into(tmp_path, tmp_path)
    access_key.settle(tmp_path)
    new = access_key.pass_token(tmp_path)
    assert new is not None and new != old
    caddy = run_again(tmp_path, proxy.port)
    try:
        assert proxy.ask(HOST, "/", headers={"Cookie": f"{access_key.PASS_COOKIE}={old}"})[0] == 401
        assert proxy.ask(HOST, "/", user="demo", key=KEY)[0] == 401
        assert proxy.ask(HOST, "/", user="demo", key=KEY + " renewed")[0] == 200
        assert proxy.ask(HOST, "/", headers={"Cookie": f"{access_key.PASS_COOKIE}={new}"})[0] == 200
    finally:
        caddy.kill()
        caddy.wait(timeout=10)


PREFLIGHT = {"Origin": f"https://{HOST}", "Access-Control-Request-Method": "POST"}


@pytest.mark.parametrize("name", NAMES)
def test_a_cors_preflight_is_answered_without_the_key_and_given_no_pass(
    proxy: Proxy, name: str
) -> None:
    status, fields = proxy.ask(name, "/v1/x", method="OPTIONS", headers=PREFLIGHT)
    assert status == 200
    assert "set-cookie" not in fields
    assert fields["x-robots-tag"] == ["noindex, nofollow"]


@pytest.mark.parametrize("name", NAMES)
def test_an_options_that_is_not_a_preflight_asks_for_the_key(proxy: Proxy, name: str) -> None:
    assert proxy.ask(name, "/v1/x", method="OPTIONS")[0] == 401
    assert proxy.stand_in.seen == []


@pytest.mark.parametrize(
    "path",
    [
        "/realms/osprey/protocol/openid-connect/token",
        "/realms/osprey/protocol/openid-connect/certs",
        "/realms/osprey/.well-known/openid-configuration",
    ],
)
def test_the_identity_providers_cross_origin_answers_go_without_the_key(
    proxy: Proxy, path: str
) -> None:
    method = "POST" if path.endswith("/token") else "GET"
    status, fields = proxy.ask(f"id.{HOST}", path, method=method)
    assert status == 200 and fields["x-robots-tag"] == ["noindex, nofollow"]


OPEN = [
    (f"id.{HOST}", "POST", "/realms/osprey/protocol/openid-connect/token"),
    (f"id.{HOST}", "GET", "/realms/osprey/protocol/openid-connect/certs"),
    (f"id.{HOST}", "GET", "/realms/osprey/.well-known/openid-configuration"),
    *((name, "OPTIONS", "/v1/x") for name in NAMES),
]


@pytest.mark.parametrize(("name", "method", "path"), OPEN)
def test_the_open_answers_never_give_the_pass_for_an_unchecked_key(
    proxy: Proxy, name: str, method: str, path: str
) -> None:
    """A request to an answer that goes without the key is not checked, whatever Basic credential it
    carries, so it is never given the pass for one; at the token endpoint the credential reaches
    Keycloak never: no Basic credential, of any client, passes the proxy."""
    headers = PREFLIGHT if method == "OPTIONS" else None
    status, fields = proxy.ask(name, path, method=method, user="demo", key="anything at all",
                               headers=headers)  # fmt: skip
    assert status == 200
    assert "set-cookie" not in fields
    (seen,) = proxy.stand_in.seen
    assert seen.authorization is None, "a Basic credential reached the service behind the proxy"


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("path", ["/", "/realms/osprey/protocol/openid-connect/auth", "/v1/x"])
def test_a_browser_that_has_answered_never_sends_the_key_behind(proxy: Proxy, name: str, path: str) -> None:
    """After the first answer a browser sends the pass and the key together with every request;
    the key is taken off, whatever the scheme's case, on every name and path."""
    import base64

    credential = base64.b64encode(f"demo:{KEY}".encode()).decode()
    for scheme in ("Basic", "basic", "BASIC"):
        headers = {**pass_cookie(proxy), "Authorization": f"{scheme} {credential}"}
        assert proxy.ask(name, path, headers=headers)[0] == 200
    assert [seen.authorization for seen in proxy.stand_in.seen] == [None, None, None]


@pytest.mark.parametrize("name", NAMES)
def test_a_lower_case_scheme_is_checked_and_taken_off_like_any_other(proxy: Proxy, name: str) -> None:
    import base64

    for key, expected in (("not the shared key", 401), (KEY, 200)):
        credential = base64.b64encode(f"demo:{key}".encode()).decode()
        assert proxy.ask(name, "/", headers={"Authorization": f"basic {credential}"})[0] == expected
    assert [seen.authorization for seen in proxy.stand_in.seen] == [None]


@pytest.mark.parametrize(
    "path",
    [
        "/realms/osprey/protocol/openid-connect/auth%2F..%2Ftoken",
        "/realms/osprey/protocol/openid-connect/%2e%2e/openid-connect/auth",
        "/realms/osprey/protocol/openid-connect/token;/../auth",
        "/realms/osprey/protocol/openid-connect/auth%2Ftoken",
        "/REALMS/osprey/protocol/openid-connect/auth",
        "/realms/osprey/protocol/openid-connect/token/../auth",
    ],
)
def test_an_encoded_or_disguised_path_never_reaches_the_sign_in_page_without_the_key(
    proxy: Proxy, path: str
) -> None:
    """Caddy matches the cleaned path; whatever it lets through as an open answer must reach the
    identity provider as that open answer itself, never another page."""
    status, _fields = proxy.ask(f"id.{HOST}", path)
    if status != 401:
        (seen,) = proxy.stand_in.seen
        assert seen.path in OPEN_PATHS, (path, seen.path)


@pytest.mark.parametrize(
    "path",
    [
        "/realms/osprey/protocol/openid-connect/auth",
        "/realms/osprey/protocol/openid-connect/token/../auth",
        "/realms/master/protocol/openid-connect/token",
        "/admin/master/console/",
        "/realms/osprey/account/",
    ],
)
def test_the_sign_in_page_and_everything_else_on_the_identity_provider_asks(
    proxy: Proxy, path: str
) -> None:
    assert proxy.ask(f"id.{HOST}", path)[0] == 401
    assert proxy.stand_in.seen == []


def test_without_its_key_file_the_proxy_does_not_start(tmp_path: Path) -> None:
    """Fails closed: a deployment that asks for the key and has none set answers nothing at all."""
    caddyfile = write_caddyfile(tmp_path, free_port(), free_port(), 9)
    done = subprocess.run([str(CADDY), "validate", "--config", str(caddyfile), "--adapter", "caddyfile"],
                          capture_output=True, text=True)  # fmt: skip
    assert done.returncode != 0
    assert access_key.ACCESS_KEY_FILE in done.stdout + done.stderr


def test_a_deployment_that_does_not_ask_is_answered_as_before(tmp_path: Path) -> None:
    stand_in = stand_in_server()
    port, plain = free_port(), free_port()
    process = run_caddy(write_caddyfile(tmp_path, port, plain, stand_in.server_address[1], ask=False), port)
    try:
        status, fields = Proxy(port, stand_in, "").ask(HOST, "/")
        assert status == 200
        assert "x-robots-tag" not in fields and "set-cookie" not in fields
    finally:
        process.kill()
        process.wait(timeout=10)
        stand_in.shutdown()


# --- ADR-114 Amendment 42: one key prompt for the whole deployment -----------------------------------


@pytest.mark.parametrize("first", NAMES)
def test_one_answer_on_any_name_lets_the_other_two_through(proxy: Proxy, first: str, tmp_path: Path) -> None:
    """The owner's ruling of 13 November 2026: the key answered once, on whichever name a visitor
    reaches first, and the other two go through without asking again."""
    jar = tmp_path / "jar"
    assert proxy.ask(first, "/", user="demo", key=KEY, jar=jar)[0] == 200
    for name in NAMES:
        status, fields = proxy.ask(name, "/after", jar=jar)
        assert status == 200, name
        assert fields["x-robots-tag"] == ["noindex, nofollow"]
    assert all(seen.authorization is None for seen in proxy.stand_in.seen)


@pytest.mark.parametrize("first", NAMES)
def test_a_wrong_or_no_key_still_asks_on_all_three(proxy: Proxy, first: str, tmp_path: Path) -> None:
    jar = tmp_path / "jar"
    assert proxy.ask(first, "/", user="demo", key="not the shared key", jar=jar)[0] == 401
    for name in NAMES:
        status, fields = proxy.ask(name, "/", jar=jar)
        assert status == 401 and fields["x-robots-tag"] == ["noindex, nofollow"], name
    assert proxy.stand_in.seen == []


def _sent_to(set_cookie: str, origin: str, name: str) -> bool:
    """Whether a browser that received `set_cookie` from `origin` sends it to `name`: RFC 6265 §5.3
    step 6 and §5.1.3. With a `Domain` attribute, to that domain and the names under it; without
    one, host-only, to `origin` alone. (`http.cookiejar`'s default policy is not a browser's: it
    sends a host-only cookie to subdomains too.)"""
    attributes = {
        part.split("=", 1)[0].strip().lower(): (part.split("=", 1) + [""])[1].strip()
        for part in set_cookie.split(";")[1:]
    }
    domain = attributes.get("domain", "").lstrip(".").lower()
    if not domain:
        return name == origin
    if not (origin == domain or origin.endswith("." + domain)):
        return False  # a browser refuses to store it at all (§5.3 step 6)
    return name == domain or name.endswith("." + domain)


def test_the_pass_goes_to_the_deployments_names_and_nowhere_else(proxy: Proxy) -> None:
    """Sent by a browser's own rules (RFC 6265 domain matching): to the deployment's base name and
    the names under it, never to the domain above it, a sibling, or a name that merely ends with the
    same letters."""
    status, fields = proxy.ask(HOST, "/", user="demo", key=KEY)
    assert status == 200
    (given,) = [c for c in fields["set-cookie"] if c.startswith(f"{access_key.PASS_COOKIE}=")]
    parent = HOST.split(".", 1)[1]
    expected = {
        HOST: True, f"id.{HOST}": True, f"bi.{HOST}": True, f"deep.id.{HOST}": True,
        parent: False, f"other.{parent}": False, f"x{HOST}": False, f"{HOST}.example.org": False,
    }
    assert {name: _sent_to(given, HOST, name) for name in expected} == expected
