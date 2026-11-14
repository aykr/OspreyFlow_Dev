"""v052-r1's dashboards check, offline (`process/lanes/platform-b/v052/dashboards_check.py`,
`superset_pod.py`): the browser's sign-in to Superset through the Entra stand-in, followed by hand.

Superset and Entra are stand-ins here that answer, and refuse, as the real ones do on these paths
(rule 15): Superset sends `/login/entra` to Entra's `/authorize` with the redirect its proxy headers
make, answers `/oauth-authorized/entra` by signing in only with a code Entra gave for that person, and
answers `/api/v1/me/` 401 to anyone not signed in (Flask-AppBuilder's refused sign-in sends the browser
back to its login page); Entra signs in the person `login_hint` names and shows AADSTS50034 on its own
page for one it does not know, never redirecting. The live run is the leased v052-r1 run.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
import pytest

POD = Path(__file__).resolve().parents[1] / "process/lanes/platform-b/v052/superset_pod.py"
CHECK = Path(__file__).resolve().parents[1] / "process/lanes/platform-b/v052/dashboards_check.py"
GLASS = "ospreyflow.r1.test"
TENANT = "00000000-1111-4222-8333-444444444444"
ROLES = {"reader@r1.test": "Gamma", "builder@r1.test": "Alpha"}  # nobody@r1.test: refused by Superset


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pod(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    module = _load(POD, "superset_pod_under_test")
    codes: dict[str, str] = {}
    sessions: dict[str, str] = {}
    fake = {"honours_forwarding": True}

    def entra(request: httpx.Request) -> httpx.Response:
        q = dict(urllib.parse.parse_qsl(request.url.query.decode()))
        if request.url.path != f"/{TENANT}/oauth2/v2.0/authorize":
            return httpx.Response(404)
        hint = q.get("login_hint", "admin@r1.test")
        if hint not in (*ROLES, "nobody@r1.test", "admin@r1.test"):
            # As the stand-in refuses it (r1_kind_servers.py `_page`): 400, Entra's own page, never the redirect.
            return httpx.Response(400, headers={"content-type": "text/html; charset=utf-8"},
                                  text=f"<html><body><h1>Sign in</h1><p>AADSTS50034: The user account {hint} does not "
                                       f"exist in the {TENANT} directory.</p></body></html>")
        if q.get("redirect_uri") != f"https://bi.{GLASS}/oauth-authorized/entra":
            return httpx.Response(200, text="AADSTS50011: The redirect URI does not match")
        code = f"code-{len(codes)}"
        codes[code] = hint
        return httpx.Response(302, headers={"location": f"{q['redirect_uri']}?code={code}&state={q['state']}"})

    def superset(request: httpx.Request) -> httpx.Response:
        # Superset answers any host, building its redirect from the forwarded scheme and host it is sent
        # (ENABLE_PROXY_FIX), or its own when none is forwarded.
        path = request.url.path
        if fake["honours_forwarding"]:
            host = request.headers.get("x-forwarded-host") or request.headers.get("host")
            scheme = request.headers.get("x-forwarded-proto", "http")
        else:  # a proxy setting lost: its own Service's name and scheme
            host, scheme = request.url.netloc.decode(), request.url.scheme
        if path == "/login/entra":
            redirect = f"{scheme}://{host}/oauth-authorized/entra"
            query = urllib.parse.urlencode({"response_type": "code", "client_id": "superset", "redirect_uri": redirect,
                                            "scope": "openid profile api://x/access_as_user", "state": "s1"})  # fmt: skip
            return httpx.Response(302, headers={"location": f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize?{query}"})
        if path == "/oauth-authorized/entra":
            hint = codes.pop(dict(urllib.parse.parse_qsl(request.url.query.decode())).get("code", ""), None)
            if hint is None or hint == "nobody@r1.test":  # an unknown code, or no reports right: refused
                return httpx.Response(302, headers={"location": "/login/"})
            sessions[f"s-{hint}"] = hint
            return httpx.Response(302, headers={"location": "/", "set-cookie": f"session=s-{hint}; Path=/"})
        cookie = request.headers.get("cookie", "")
        who = sessions.get(cookie.removeprefix("session=")) if cookie.startswith("session=") else None
        if path == "/api/v1/me/":
            return httpx.Response(200, json={"result": {"username": who}}) if who else httpx.Response(401)
        if path == "/api/v1/me/roles/":
            return httpx.Response(200, json={"result": {"roles": {{**ROLES, "admin@r1.test": "Admin"}[who]: []}}}) if who else httpx.Response(401)
        return httpx.Response(404)

    real_client = httpx.Client

    def client(*args: Any, **kwargs: Any) -> httpx.Client:
        return real_client(*args, transport=httpx.MockTransport(superset), **kwargs)

    monkeypatch.setattr(module.httpx, "Client", client)
    monkeypatch.setattr(module.httpx, "get", lambda url, **kw: real_client(transport=httpx.MockTransport(entra)).get(url, **kw))
    monkeypatch.setattr(module, "_jar", lambda hint: tmp_path / f"{hint}.json")
    module.fake = fake
    return module


def test_the_login_hint_is_added_and_one_already_there_replaced(pod: Any) -> None:
    url = pod.with_login_hint("https://login.microsoftonline.com/t/oauth2/v2.0/authorize?state=s&login_hint=x", "reader@r1.test")
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert query == {"state": "s", "login_hint": "reader@r1.test"}


@pytest.mark.parametrize(("hint", "role"), list(ROLES.items()))
def test_a_person_signs_in_and_superset_names_their_role(pod: Any, hint: str, role: str) -> None:
    assert pod.signin(GLASS, hint) == {"signed_in": True, "username": hint, "roles": [role]}


def test_a_person_superset_refuses_is_not_signed_in(pod: Any) -> None:
    answer = pod.signin(GLASS, "nobody@r1.test")
    assert answer["signed_in"] is False and answer["stage"] == "superset" and answer["me"] == 401


def test_a_person_entra_does_not_know_stops_at_entra_s_own_page(pod: Any) -> None:
    answer = pod.signin(GLASS, "stranger@r1.test")
    assert answer["signed_in"] is False and answer["stage"] == "entra" and "AADSTS50034" in answer["said"]


def test_a_superset_that_ignores_the_door_s_name_is_caught_before_entra(pod: Any) -> None:
    """Checked before Entra is asked, so a redirect other than the registered one is said as the
    script's own finding, not as Entra's refusal of it."""
    pod.fake["honours_forwarding"] = False
    answer = pod.signin(GLASS, "reader@r1.test")
    assert answer["signed_in"] is False and answer["stage"] == "the redirect Superset names"


def test_the_check_s_plan_and_its_people() -> None:
    check = _load(CHECK, "dashboards_check_under_test")
    assert len(check.PLAN) == 11
    assert set(check.SUPERSET_ROLE) | {"nobody@r1.test"} == set(check.PEOPLE)
    assert check.ROLES["builder@r1.test"] == ["reports_viewer", "right:manage_dashboards"]
    assert json.dumps(check.SUPERSET_ROLE) == json.dumps(
        {"admin@r1.test": ["Admin"], "builder@r1.test": ["Alpha"], "reader@r1.test": ["Gamma"]})
