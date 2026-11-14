"""Superset as a browser reaches it, run inside the deployment's api pod (v052-r1's dashboards check,
`dashboards_check.py`; ADR-148 Amendments 9 and 11). The standard library and the api image's httpx only.

Inside the pod, the cluster's DNS sends `login.microsoftonline.com` to the Entra stand-in and the stand-in CA
is trusted (R1's webhook), as for every pod of the namespace. Superset is reached on its Service with the
`bi.` door's name and scheme forwarded (Superset trusts its proxy's headers, ENABLE_PROXY_FIX), so the
redirect it builds is the registered `https://bi.<host>/oauth-authorized/entra`; the browser's leg to
`/authorize` and back is followed by hand, the person picked by `login_hint` (the stand-in's `users`).

    python -I superset_pod.py <glass host> signin <login_hint>
    python -I superset_pod.py <glass host> build <login_hint> <title> [<slug>]
    python -I superset_pod.py <glass host> embedded <superset dashboard id> @secret
    python -I superset_pod.py <glass host> chart <login_hint> <superset dashboard id>
    python -I superset_pod.py <glass host> chartdata session <login_hint> <board id> <dataset id> <chart id>
    python -I superset_pod.py <glass host> chartdata guest <board id> <dataset id> <chart id> @secret

`@secret` is the guest token, which never travels as an argument (it would sit on kubectl's command line): the
check prepends it to this script's text on stdin as `R1_SECRET`, and `@secret` reads it from there.

Each prints one JSON line, never a token. A person's Superset session is kept in /tmp between calls of one
run. `build` with a slug already taken by that board answers it as existing (200), so a rerun does not stop.
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
    # The redirect Superset names, decoded and compared whole: Entra matches a registered redirect exactly.
    named = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(authorize).query)).get("redirect_uri")
    if named != f"https://bi.{glass}/oauth-authorized/entra":
        return {"signed_in": False, "stage": "the redirect Superset names", "redirect_uri": named}
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
    if made.status_code == 422 and slug:
        # A rerun (rows 4 to 9 again after a fix): the slug is taken, by this board if it is there.
        there = client.get(f"/api/v1/dashboard/{slug}")
        if there.status_code == 200:
            return {"status": 200, "existing": True, "id": there.json().get("result", {}).get("id")}
    return {"status": made.status_code, "id": result.get("id"), "said": made.text[:200]}


def embedded(glass: str, dashboard_id: str, guest_token: str) -> dict[str, Any]:
    """The board the Glass frames, read with the guest token the Conduit gave (and, for the control,
    without it): what the embedded SDK asks first."""
    client = _client(glass)
    path = f"/api/v1/dashboard/{dashboard_id}"
    with_token = client.get(path, headers={"X-GuestToken": guest_token})
    without = client.get(path)
    return {"with_token": with_token.status_code, "without": without.status_code}


#: The mart Superset reads (deploy/superset/osprey_setup.py: its one data source), the table the report sync
#: fills, and the chart the check reads it through.
MART_DATABASE, MART_SCHEMA, MART_TABLE = "OspreyFlow reports", "osprey_reports", "figures"
CHART = "R1 figures by dashboard"


def _csrf(client: httpx.Client, headers: dict[str, str] | None = None) -> str | None:
    got = client.get("/api/v1/security/csrf_token/", headers=headers or {})
    return got.json().get("result") if got.status_code == 200 else None


def chart(glass: str, hint: str, board_id: str) -> dict[str, Any]:
    """With an administrator's session: the mart's `figures` as a dataset, and a table chart on it grouped by
    the `dashboard` column (the one the guest token's row-level security names), on the board. Each found
    again on a rerun, never made twice."""
    client = _client(glass, hint)
    token = _csrf(client)
    if token is None:
        return {"status": 401, "stage": "csrf"}
    write = {"X-CSRFToken": token, "Referer": f"https://bi.{glass}/"}
    dbs = client.get("/api/v1/database/", params={"q": f"(filters:!((col:database_name,opr:eq,value:'{MART_DATABASE}')))"})
    found = (dbs.json().get("result") or []) if dbs.status_code == 200 else []
    if not found:
        return {"status": dbs.status_code, "stage": "the mart's database", "said": dbs.text[:200]}
    db = found[0]["id"]
    sets = client.get("/api/v1/dataset/", params={"q": f"(filters:!((col:table_name,opr:eq,value:{MART_TABLE})))"})
    listed = [d for d in (sets.json().get("result") or []) if d.get("schema") == MART_SCHEMA] if sets.status_code == 200 else []
    if listed:
        dataset = listed[0]["id"]
    else:
        made = client.post("/api/v1/dataset/", headers=write,
                           json={"database": db, "schema": MART_SCHEMA, "table_name": MART_TABLE})  # fmt: skip
        if made.status_code != 201:
            return {"status": made.status_code, "stage": "the dataset", "said": made.text[:200]}
        dataset = made.json()["id"]
    charts = client.get("/api/v1/chart/", params={"q": f"(filters:!((col:slice_name,opr:eq,value:'{CHART}')))"})
    named = (charts.json().get("result") or []) if charts.status_code == 200 else []
    if named:
        return {"status": 200, "dataset": dataset, "chart": named[0]["id"], "existing": True}
    params = {"viz_type": "table", "groupby": ["dashboard"], "metrics": ["count"], "row_limit": 1000}
    made = client.post("/api/v1/chart/", headers=write, json={
        "slice_name": CHART, "viz_type": "table", "datasource_id": dataset, "datasource_type": "table",
        "dashboards": [int(board_id)], "params": json.dumps(params)})  # fmt: skip
    if made.status_code != 201:
        return {"status": made.status_code, "stage": "the chart", "said": made.text[:200]}
    return {"status": 201, "dataset": dataset, "chart": made.json()["id"]}


def chartdata(glass: str, how: str, who: str, board_id: str, dataset: str, chart_id: str) -> dict[str, Any]:
    """The chart's rows as the embedded board asks for them: grouped by `dashboard`, read with the Conduit's
    guest token (`how` guest, `who` the token) or a person's own session (`how` session, `who` their hint).
    Answers the status and the `dashboard` values seen, never a row's figures."""
    client = _client(glass, who if how == "session" else None)
    headers = {"X-GuestToken": who} if how == "guest" else {}
    token = _csrf(client, headers)
    body = {"datasource": {"id": int(dataset), "type": "table"}, "force": True,
            "queries": [{"columns": ["dashboard"], "metrics": ["count"], "row_limit": 1000}],
            "form_data": {"slice_id": int(chart_id), "dashboardId": int(board_id), "viz_type": "table"},
            "result_format": "json", "result_type": "full"}  # fmt: skip
    asked = client.post("/api/v1/chart/data", json=body,
                        headers={**headers, **({"X-CSRFToken": token} if token else {}), "Referer": f"https://bi.{glass}/"})  # fmt: skip
    if asked.status_code != 200:
        return {"status": asked.status_code}
    rows = [r for q in asked.json().get("result", []) for r in q.get("data", [])]
    return {"status": 200, "dashboards": sorted({str(r.get("dashboard")) for r in rows})}


def _secret(arg: str) -> str:
    """`@secret`: the value the check prepended to this script on stdin, never an argument."""
    import os

    return os.environ.get("R1_SECRET", "") if arg == "@secret" else arg


def main(argv: list[str]) -> int:
    glass, action, *rest = argv
    if action == "signin":
        answer = signin(glass, rest[0])
    elif action == "build":
        answer = build(glass, rest[0], rest[1], rest[2] if len(rest) > 2 else None)
    elif action == "embedded":
        answer = embedded(glass, rest[0], _secret(rest[1]))
    elif action == "chart":
        answer = chart(glass, rest[0], rest[1])
    elif action == "chartdata" and rest[0] == "guest":
        answer = chartdata(glass, "guest", _secret(rest[4]), rest[1], rest[2], rest[3])
    elif action == "chartdata":
        answer = chartdata(glass, "session", rest[1], rest[2], rest[3], rest[4])
    else:
        answer = {"error": f"unknown action {action!r}"}
    print(json.dumps(answer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
