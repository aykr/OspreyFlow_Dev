"""Superset as a browser reaches it, run inside the deployment's api pod (v052-r1's dashboards check,
`dashboards_check.py`; ADR-148 Amendments 9 and 11). The standard library and the api image's httpx only.

Inside the pod, the cluster's DNS sends `login.microsoftonline.com` to the Entra stand-in and the stand-in CA
is trusted (R1's webhook), as for every pod of the namespace. Superset is reached on its Service with the
`bi.` door's name and scheme forwarded (Superset trusts its proxy's headers, ENABLE_PROXY_FIX), so the
redirect it builds is the registered `https://bi.<host>/oauth-authorized/entra`; the browser's leg to
`/authorize` and back is followed by hand, the person picked by `login_hint` (the stand-in's `users`).

    python -I superset_pod.py <glass host> signin <login_hint>
    python -I superset_pod.py <glass host> build <login_hint> <title> [<slug>]
    python -I superset_pod.py <glass host> embedded <superset dashboard id> <guest token>

Each prints one JSON line. A person's Superset session is kept in /tmp between calls of one run.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

SUPERSET = "http://superset:8088"


def with_login_hint(authorize_url: str, hint: str) -> str:
    """The authorisation request Superset made, with the person to sign in named as a browser's
    `login_hint` would; anything Superset put there is kept, a hint of its own replaced."""
    parts = urllib.parse.urlsplit(authorize_url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != "login_hint"]
    query.append(("login_hint", hint))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _jar(hint: str) -> Path:
    return Path("/tmp") / f"r1-superset-{hint.replace('@', '_at_')}.json"


def _client(glass: str, hint: str | None = None) -> httpx.Client:
    forwarded = {"Host": f"bi.{glass}", "X-Forwarded-Proto": "https", "X-Forwarded-Host": f"bi.{glass}",
                 "X-Forwarded-Port": "443"}  # fmt: skip
    client = httpx.Client(base_url=SUPERSET, headers=forwarded, follow_redirects=False, timeout=60)
    if hint and _jar(hint).is_file():
        for name, value in json.loads(_jar(hint).read_text()).items():
            client.cookies.set(name, value)
    return client


def _keep(client: httpx.Client, hint: str) -> None:
    _jar(hint).write_text(json.dumps({c.name: c.value for c in client.cookies.jar}))


def signin(glass: str, hint: str) -> dict[str, Any]:
    """Superset's own sign-in, as a browser: its `/login/entra` sends us to Entra's `/authorize`, which
    signs in `hint` and sends us back with a code, which Superset exchanges and reads the person from
    the Conduit with. Signed in when Superset then answers `/api/v1/me/` as someone; refused when it
    sends us back to its login page instead (Flask-AppBuilder's refused sign-in)."""
    _jar(hint).unlink(missing_ok=True)
    client = _client(glass)
    started = client.get("/login/entra", params={"next": "/"})
    authorize = started.headers.get("location", "")
    if started.status_code != 302 or "/oauth2/v2.0/authorize" not in authorize:
        return {"signed_in": False, "stage": "superset's redirect", "status": started.status_code, "location": authorize}
    if f"redirect_uri={urllib.parse.quote(f'https://bi.{glass}/oauth-authorized/entra', safe='')}" not in authorize:
        return {"signed_in": False, "stage": "the redirect Superset names", "location": authorize}
    answered = httpx.get(with_login_hint(authorize, hint), follow_redirects=False, timeout=60)
    back = answered.headers.get("location", "")
    if answered.status_code != 302 or "/oauth-authorized/entra?" not in back:
        return {"signed_in": False, "stage": "entra", "status": answered.status_code, "said": answered.text[:300]}
    if "code=" not in back:
        return {"signed_in": False, "stage": "entra's answer", "location": back}
    returned = client.get("/oauth-authorized/entra?" + urllib.parse.urlsplit(back).query)
    me = client.get("/api/v1/me/")
    if me.status_code != 200:
        return {"signed_in": False, "stage": "superset", "status": returned.status_code,
                "location": returned.headers.get("location", ""), "me": me.status_code}  # fmt: skip
    roles = client.get("/api/v1/me/roles/")
    _keep(client, hint)
    named = sorted((roles.json().get("result", {}).get("roles") or {}).keys()) if roles.status_code == 200 else []
    return {"signed_in": True, "username": me.json().get("result", {}).get("username"), "roles": named}


def build(glass: str, hint: str, title: str, slug: str | None) -> dict[str, Any]:
    """What a builder does first: save a new dashboard, through Superset's own API with the person's
    session and its CSRF token. 201 is made; Gamma is refused (403)."""
    client = _client(glass, hint)
    csrf = client.get("/api/v1/security/csrf_token/")
    if csrf.status_code != 200:
        return {"status": csrf.status_code, "stage": "csrf", "said": csrf.text[:200]}
    body: dict[str, Any] = {"dashboard_title": title, "published": True, **({"slug": slug} if slug else {})}
    made = client.post("/api/v1/dashboard/", json=body,
                       headers={"X-CSRFToken": csrf.json()["result"], "Referer": f"https://bi.{glass}/"})  # fmt: skip
    _keep(client, hint)
    result = made.json() if made.headers.get("content-type", "").startswith("application/json") else {}
    return {"status": made.status_code, "id": result.get("id"), "said": made.text[:200]}


def embedded(glass: str, dashboard_id: str, guest_token: str) -> dict[str, Any]:
    """The board the Glass frames, read with the guest token the Conduit gave (and, for the control,
    without it): what the embedded SDK asks first."""
    client = _client(glass)
    path = f"/api/v1/dashboard/{dashboard_id}"
    with_token = client.get(path, headers={"X-GuestToken": guest_token})
    without = client.get(path)
    return {"with_token": with_token.status_code, "without": without.status_code}


def main(argv: list[str]) -> int:
    glass, action, *rest = argv
    if action == "signin":
        answer = signin(glass, rest[0])
    elif action == "build":
        answer = build(glass, rest[0], rest[1], rest[2] if len(rest) > 2 else None)
    elif action == "embedded":
        answer = embedded(glass, rest[0], rest[1])
    else:
        answer = {"error": f"unknown action {action!r}"}
    print(json.dumps(answer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
