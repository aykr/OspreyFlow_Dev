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
#: Superset's username is the Conduit's principal, the Entra object id (deploy/superset/superset_config.py
#: `_entra_user_info`: "its id (the Entra object id) is the username"), never the sign-in name.
OIDS = {"admin@r1.test": "50000000-0000-4000-8000-0000000000a1", "reader@r1.test": "50000000-0000-4000-8000-0000000000b1",
        "builder@r1.test": "50000000-0000-4000-8000-0000000000b2"}
GUEST = "guest-token-of-the-conduit"


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
    fake: dict[str, Any] = {"honours_forwarding": True, "boards": {}, "csrf_checked": True, "redirect_suffix": ""}

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
            redirect = f"{scheme}://{host}/oauth-authorized/entra{fake['redirect_suffix']}"
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
        role = {**ROLES, "admin@r1.test": "Admin"}.get(who or "")
        if path == "/api/v1/me/":
            return httpx.Response(200, json={"result": {"username": OIDS[who]}}) if who else httpx.Response(401)
        if path == "/api/v1/me/roles/":
            return httpx.Response(200, json={"result": {"roles": {role: []}}}) if who else httpx.Response(401)
        if path == "/api/v1/security/csrf_token/":
            return httpx.Response(200, json={"result": f"csrf-{who}"}) if who else httpx.Response(401)
        boards = fake["boards"]
        if path == "/api/v1/dashboard/" and request.method == "POST":
            # Flask-AppBuilder's refusals, in its order: no session, then no CSRF token, then the role, then
            # the slug's uniqueness.
            if not who:
                return httpx.Response(401, json={"msg": "Missing Authorization Header"})
            if fake["csrf_checked"] and request.headers.get("x-csrftoken") != f"csrf-{who}":
                return httpx.Response(400, json={"errors": [{"message": "400 Bad Request: The CSRF token is missing."}]})
            if role == "Gamma":
                return httpx.Response(403, json={"message": "Forbidden"})
            body = json.loads(request.content)
            if body.get("slug") and body["slug"] in boards:
                return httpx.Response(422, json={"message": {"slug": ["Must be unique"]}})
            made = len(boards) + 7
            boards[body.get("slug") or f"#{made}"] = made
            return httpx.Response(201, json={"id": made, "result": body})
        if path.startswith("/api/v1/dashboard/") and request.method == "GET":
            key = path.rsplit("/", 1)[1]
            board = boards.get(key) or (int(key) if key.isdigit() and int(key) in boards.values() else None)
            guest = request.headers.get("x-guesttoken")
            if guest is not None:  # the embedded SDK's read: the Conduit's token alone opens it
                return httpx.Response(200 if guest == GUEST and board else 401)
            if not who:
                return httpx.Response(401)
            return httpx.Response(200, json={"result": {"id": board}}) if board else httpx.Response(404)
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
    assert pod.signin(GLASS, hint) == {"signed_in": True, "username": OIDS[hint], "roles": [role]}


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


def test_a_redirect_that_only_begins_with_the_registered_one_is_caught(pod: Any) -> None:
    """Entra matches a registered redirect exactly: the decoded redirect_uri is compared whole, so one that
    merely starts with the registered address (which a substring of the encoded URL would pass) is caught."""
    pod.fake["redirect_suffix"] = "-elsewhere"
    answer = pod.signin(GLASS, "reader@r1.test")
    assert answer["signed_in"] is False and answer["stage"] == "the redirect Superset names"
    assert answer["redirect_uri"] == f"https://bi.{GLASS}/oauth-authorized/entra-elsewhere"


def test_the_check_s_plan_and_its_people() -> None:
    check = _load(CHECK, "dashboards_check_under_test")
    assert len(check.PLAN) == 12
    assert set(check.SUPERSET_ROLE) | {"nobody@r1.test"} == set(check.PEOPLE)
    assert check.ROLES["builder@r1.test"] == ["reports_viewer", "right:manage_dashboards"]
    assert json.dumps(check.SUPERSET_ROLE) == json.dumps(
        {"admin@r1.test": ["Admin"], "builder@r1.test": ["Alpha"], "reader@r1.test": ["Gamma"]})


def test_the_report_sync_is_given_what_install_s_step_6a_tells_the_client_to_give() -> None:
    """The check writes REPORT_SYNC_DASHBOARDS as the apply would from the runbook's example, so it tests the
    value a client is told to give, not one of its own (a key added here, or one the runbook gains, fails)."""
    import json as _json
    import re

    from harness.cloud_platform import runbooks

    source = Path(runbooks.__file__).read_text(encoding="utf-8")
    example = re.search(r'report_sync_dashboards`, a JSON list, as\\n"\s*"`(\{.*?\})`', source, re.S)
    assert example, "INSTALL.md's step 6a example"
    told = set(re.findall(r'\\"([a-z_]+)\\": ', example.group(1)))
    check = _load(CHECK, "dashboards_check_under_test")
    given = _json.loads(check.report_sync_dashboards("app-id", "not-a-secret"))
    assert told == {"client_id", "secret"} and [set(d) for d in given] == [told]


# ---- building and embedding, against Superset's own refusals (the review of 093c7cb, must 6) --------------


def test_building_is_made_for_alpha_refused_for_gamma_and_needs_a_session_and_its_csrf(pod: Any) -> None:
    pod.signin(GLASS, "builder@r1.test"), pod.signin(GLASS, "reader@r1.test")
    assert pod.build(GLASS, "builder@r1.test", "a board", None)["status"] == 201
    assert pod.build(GLASS, "reader@r1.test", "a board", None)["status"] == 403
    assert pod.build(GLASS, "nobody@r1.test", "a board", None) == {"status": 401, "stage": "csrf", "said": ""}


def test_superset_refuses_a_build_without_its_csrf_token_so_build_is_shown_to_send_it(pod: Any) -> None:
    """The fake refuses a session's POST with no CSRF token, as Superset does (400): the builder's 201 above
    is then only possible because build sends it."""
    pod.signin(GLASS, "builder@r1.test")
    session = pod._client(GLASS, "builder@r1.test")
    refused = session.post("/api/v1/dashboard/", json={"dashboard_title": "no csrf"})
    assert refused.status_code == 400 and "CSRF" in refused.text


def test_a_rerun_finds_the_board_its_slug_names(pod: Any) -> None:
    pod.signin(GLASS, "admin@r1.test")
    first = pod.build(GLASS, "admin@r1.test", "R1 board", "r1-board")
    again = pod.build(GLASS, "admin@r1.test", "R1 board", "r1-board")
    assert first["status"] == 201 and again == {"status": 200, "existing": True, "id": first["id"]}


def test_the_board_opens_with_the_conduit_s_guest_token_alone(pod: Any) -> None:
    pod.signin(GLASS, "admin@r1.test")
    made = pod.build(GLASS, "admin@r1.test", "R1 board", "r1-board")
    assert pod.embedded(GLASS, str(made["id"]), GUEST) == {"with_token": 200, "without": 401}
    assert pod.embedded(GLASS, str(made["id"]), "a-token-the-conduit-never-gave")["with_token"] == 401


# ---- the check itself, against a Conduit whose refusals are the real may_open's ---------------------------

CLASSES = ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"]
NS = "ospreyflow-poc"
SECRET = "report-sync-secret-of-the-run"
#: The fakes misbehaving, each the leak one access assertion exists for (rules 3 and 4, rule 15).
LEAKS = {
    "the report sync never pulls": "pulls the case",
    "the report sync's pull fails": "pulls the case",
    "the builder, with no level on the identity's case, is offered the board": "no level on the identity's case",
    "another unit is offered the board": "another unit",
    "a lower clearance is offered the board": "clearance is below",
    "no reports right is given the listing": "no reports right is refused the listing",
    "no reports right is given a guest token": "no reports right is refused the listing",
    "Superset signs in the person with no reports right": "refused by Superset at sign-in",
    "Superset lets Gamma build": "the Reports Viewer is refused saving one",
    "Superset opens the board without a guest token": "nothing opens without it",
    "Superset names the account by its sign-in name": "the Conduit's principal (the object id)",
    "the person with no reports right is stopped by Entra, never reaching Superset": "refused by Superset at sign-in",
}


class _R1:
    """R1's driver as the check uses it: the door to a Conduit, tokens, kubectl, the run's records."""

    NS = NS
    GLASS = GLASS

    def __init__(self, tmp: Path, conduit: Any) -> None:
        import yaml

        self.CONFIG = tmp / "osprey.yaml"
        entra = yaml.safe_load((Path(__file__).resolve().parents[1] / "process/lanes/platform/gates/r1_kind_entra.yaml").read_text())
        self.CONFIG.write_text(yaml.safe_dump({
            "reporting": {"sync": True, "superset": True},
            "cloud_platform": {"claims": {"first_administrators": [OIDS["admin@r1.test"]], "superset_client_id": entra["superset"]["client_id"],
                                          "clearance": {"claim": "ext_clearance"}, "org_unit": {"claim": "ext_unit"}}},
        }))  # fmt: skip
        self.report_sync = entra["report-sync"]["client_id"]
        self.records, self.calls, self.conduit, self.tmp = tmp / "records", [], conduit, tmp
        self.records.mkdir()

    def record(self, name: str) -> Path:
        return self.records / f"{name}.log"

    def token(self, **claims: Any) -> str:
        return "fake." + json.dumps({"ext_clearance": "OFFICIAL-SENSITIVE", "ext_unit": "unit-1", **claims})

    def door(self) -> httpx.Client:
        return httpx.Client(base_url=f"https://{GLASS}", transport=httpx.MockTransport(self.conduit))

    def entra_clients(self) -> dict[str, str]:
        return {"report-sync": SECRET}

    def kubectl(self, *args: str, stdin: str | None = None, check: bool = True) -> str:
        self.calls.append((args, stdin))
        if "patch" in args:
            self.conduit.patched = json.loads(stdin or "{}")
        return ""


def _conduit(leak: str = "") -> Any:
    """The Conduit's routes the check asks, deciding a board with the real `may_open` over its own state."""
    from schemas.admin import DashboardIdentity
    from schemas.domain import Principal
    from services.api.superset_embed import may_open

    roles: dict[str, list[str]] = {OIDS["admin@r1.test"]: ["osprey-admin"]}
    grants: dict[str, set[str]] = {}
    identities: list[DashboardIdentity] = []

    def principal(request: httpx.Request) -> Principal:
        claims = json.loads(request.headers["authorization"].removeprefix("Bearer fake."))
        return Principal(id=claims["oid"], clearance=claims["ext_clearance"], org_unit=claims["ext_unit"],
                         roles=roles.get(claims["oid"], []), receivable_handling_codes=[])  # fmt: skip

    def openable(who: Principal) -> bool:
        seen = {case for case, people in grants.items() if who.id in people} | ({"case-1"} if "osprey-admin" in who.roles else set())
        leaky = {"the builder, with no level on the identity's case, is offered the board": who.id == OIDS["builder@r1.test"],
                 "another unit is offered the board": who.org_unit != "unit-1",
                 "a lower clearance is offered the board": who.clearance == "PUBLIC"}.get(leak, False)  # fmt: skip
        return leaky or any(
            may_open(who, i, classification=CLASSES, viewer_cases=seen,
                     identity_cases={c for c, p in grants.items() if i.account_id in p})  # fmt: skip
            for i in identities
        )

    def answer(request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        who = principal(request)
        reads = any(r in ("reports_viewer", "osprey-admin") for r in who.roles)
        if path == "/v1/admin/people/by-object-id":
            return httpx.Response(201)
        if path.startswith("/v1/admin/people/") and path.endswith("/roles"):
            roles[path.split("/")[4]] = json.loads(request.content)["roles"]
            return httpx.Response(200, json={})
        if path == "/v1/me":
            return httpx.Response(200, json={"id": who.id, "clearance": who.clearance, "org_unit": who.org_unit})
        if path == "/v1/investigations" and method == "POST":
            return httpx.Response(201, json={"id": "case-1"})
        if path == "/v1/admin/dashboards" and method == "POST":
            body = json.loads(request.content)
            identities.append(DashboardIdentity(client_id=body["application_id"], account_id=body["application_id"], name=body["name"],
                                                clearance=body["clearance"], org_unit=body["org_unit"]))  # fmt: skip
            return httpx.Response(201, json={})
        if path == "/v1/admin/dashboards":
            pulled = bool(answer.patched) and leak != "the report sync never pulls"
            failure = "the Conduit refused the identity's token" if leak == "the report sync's pull fails" else None
            return httpx.Response(200, json=[{"client_id": i.client_id, "last_pulled": "2026-11-25T10:00:00Z" if pulled else None,
                                              "last_failure": failure} for i in identities])  # fmt: skip
        if "/access/grants/" in path:
            grants.setdefault(path.split("/")[3], set()).add(path.rsplit("/", 1)[1])
            return httpx.Response(204)
        if path == "/v1/reports/dashboards":
            if not reads and leak != "no reports right is given the listing":
                return httpx.Response(403, json={"detail": "not_allowed"})
            return httpx.Response(200, json=[{"slug": "r1-board", "title": "R1 board"}] if openable(who) else [])
        if path == "/v1/reports/dashboards/r1-board/guest-token":
            if not reads and leak != "no reports right is given a guest token":
                return httpx.Response(403, json={"detail": "not_allowed"})
            if not reads or openable(who):
                return httpx.Response(200, json={"token": GUEST})
            return httpx.Response(404, json={"detail": "not_found"})
        return httpx.Response(404)

    answer.patched = None
    answer.roles = roles
    return answer


def _superset(conduit: Any, leak: str = "") -> Any:
    """superset_pod's answers as its own tests show them, the roles read from the Conduit's state."""
    def ask(action: str, *args: str) -> dict[str, Any]:
        if action == "signin":
            hint = args[0]
            if hint == "nobody@r1.test" and leak == "the person with no reports right is stopped by Entra, never reaching Superset":
                return {"signed_in": False, "stage": "entra", "status": 400, "said": "AADSTS50034"}
            if hint == "nobody@r1.test" and leak != "Superset signs in the person with no reports right":
                return {"signed_in": False, "stage": "superset", "status": 302, "location": "/login/", "me": 401}
            held = conduit.roles.get(OIDS.get(hint, "x"), [])
            role = "Admin" if "osprey-admin" in held else "Alpha" if "right:manage_dashboards" in held else "Gamma"
            name = hint if leak == "Superset names the account by its sign-in name" else OIDS.get(hint, hint)
            return {"signed_in": True, "username": name, "roles": [role]}
        if action == "build":
            gamma = args[0] == "reader@r1.test"
            return {"status": 201 if not gamma or leak == "Superset lets Gamma build" else 403, "id": 7}
        if action == "embedded":
            return {"with_token": 200 if args[1] == GUEST else 401, "without": 200 if leak == "Superset opens the board without a guest token" else 401}
        raise AssertionError(action)

    return ask


def _run(tmp_path: Path, leak: str = "") -> tuple[Any, _R1]:
    check = _load(CHECK, "dashboards_check_run_under_test")
    conduit = _conduit(leak)
    r1 = _R1(tmp_path, conduit)
    check.run(r1, _superset(conduit, leak), sleep=lambda seconds: None)
    return check, r1


def test_the_check_passes_on_a_deployment_that_refuses_what_it_should(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, r1 = _run(tmp_path)
    record = (r1.records / "dashboards.log").read_text()
    assert "FAIL" not in record and record.count("PASS") >= 20
    printed = capsys.readouterr().out + record
    # Nothing secret or bearer leaves the run: the report sync's secret, a guest token, a person's token.
    assert SECRET not in printed and GUEST not in printed and "fake.{" not in printed
    # Every kubectl call names R1's namespace, and the secret is never on kubectl's command line.
    assert r1.calls and all(args[:2] == ("-n", NS) for args, _ in r1.calls)
    assert all(SECRET not in " ".join(args) for args, _ in r1.calls)
    patch = next(stdin for args, stdin in r1.calls if "patch" in args)
    assert json.loads(json.loads(patch)["stringData"]["REPORT_SYNC_DASHBOARDS"]) == [{"client_id": r1.report_sync, "secret": SECRET}]


@pytest.mark.parametrize(("leak", "stops_at"), list(LEAKS.items()), ids=list(LEAKS))
def test_each_leak_stops_the_check_at_its_own_assertion(tmp_path: Path, leak: str, stops_at: str) -> None:
    """Each access assertion red for its own reason: the fake leaks one thing, and the check stops at the
    line that exists for it, not at an earlier one (rule 15's second paragraph)."""
    with pytest.raises(SystemExit) as stopped:
        _run(tmp_path, leak)
    assert stops_at in str(stopped.value), stopped.value


# ---- the wrapper, held to r1_kind.sh's own environment by running both (must 3) ---------------------------


def _env_seen(script: Path, args: list[str], tmp: Path) -> dict[str, Any]:
    import os
    import subprocess

    core = tmp / "core"
    (core / ".venv" / "bin").mkdir(parents=True)
    stub = core / ".venv" / "bin" / "python"
    stub.write_text('#!/bin/sh\nexec "$(command -v python3)" -c \'import json,os,sys; print(json.dumps({**{k: os.environ.get(k, "") for k in ("PATH", "KUBECONFIG", "OSPREY_PLATFORM_FOLDERS", "PYTHONPATH")}, "ARGV": sys.argv[1:]}))\' "$@"\n')
    stub.chmod(0o755)
    env = {"HOME": str(tmp / "home"), "PATH": os.environ["PATH"]}
    done = subprocess.run(["bash", str(script), *args], cwd=core, env=env, capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


@pytest.mark.parametrize(("which", "args", "script"), [
    ("dashboards", ["run"], "process/lanes/platform-b/v052/dashboards_check.py"),
    ("survival", ["snap"], "process/lanes/platform-b/v052/survival.py"),
    ("spec08", ["run"], "process/lanes/case-b/v052/spec08_poc.py"),
])  # fmt: skip
def test_the_wrapper_gives_each_script_r1_s_own_environment(tmp_path: Path, which: str, args: list[str], script: str) -> None:
    build = Path(__file__).resolve().parents[1]
    ours = _env_seen(build / "process/lanes/platform-b/v052/r1_live.sh", [which, *args], tmp_path / "a")
    r1 = _env_seen(build / "process/lanes/platform/gates/r1_kind.sh", ["py", "x"], tmp_path / "b")
    for key in ("KUBECONFIG", "OSPREY_PLATFORM_FOLDERS"):
        assert ours[key] == r1[key].replace(str(tmp_path / "b"), str(tmp_path / "a")), key
    assert ours["PATH"].split(":")[0] == r1["PATH"].split(":")[0].replace(str(tmp_path / "b"), str(tmp_path / "a"))
    assert Path(ours["ARGV"][0]) == build / script and ours["ARGV"][1:] == args
    assert ours["PYTHONPATH"] == ".:packages:cli"


# ---- v0.5.1's data after the upgrade (must 2) ---------------------------------------------------------------

SURVIVAL = Path(__file__).resolve().parents[1] / "process/lanes/platform-b/v052/survival.py"


def _held_case(lost: str = "") -> Any:
    """A Conduit holding what v0.5.1's check made, in the routes' real shapes, less what `lost` names."""
    def answer(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/investigations/case-1":
            return httpx.Response(200, json={"id": "case-1", "name": "R1 synthetic case"})
        if path.endswith("/search"):
            return httpx.Response(200, json={"nodes": [] if lost == "the load" else [{"id": "n1"}, {"id": "n2"}]})
        if path.endswith("/hotlists"):
            listed = [] if lost == "the hotlist" else [{"id": "h1", "identifier": "+447700900123"}]
            return httpx.Response(200, json={"hotlists": listed, "audience_default": "only_me", "audience_editable": True})
        if path.endswith("/alert-queue"):
            return httpx.Response(200, json=[] if lost == "the alert" else [{"alert": {"rule_id": "hotlist:h1"}}])
        if path.endswith("/ingest/source-files"):
            return httpx.Response(200, json=[] if lost == "the file" else [{"name": "r1-people.csv"}])
        return httpx.Response(404)

    return answer


class _R1State:
    def __init__(self, tmp: Path, lost: str = "") -> None:
        self.STATE, self.lost = tmp, lost
        (tmp / "records").mkdir(exist_ok=True)

    def state(self) -> dict[str, str]:
        return {"case": "case-1"}

    def token(self) -> str:
        return "t"

    def door(self) -> httpx.Client:
        return httpx.Client(base_url=f"https://{GLASS}", transport=httpx.MockTransport(_held_case(self.lost)))

    def record(self, name: str) -> Path:
        return self.STATE / "records" / f"{name}.log"


def test_v051s_data_is_snapped_before_and_found_after(tmp_path: Path) -> None:
    survival = _load(SURVIVAL, "survival_under_test")
    held = survival.snap(_R1State(tmp_path))
    assert held["hotlists"] == ["h1"] and held["found"] == 2 and held["alerts"] == ["hotlist:h1"] and held["files"] == ["r1-people.csv"]
    lines = survival.verify(_R1State(tmp_path))
    assert len(lines) == 5 and all(line.startswith("PASS") for line in lines)


@pytest.mark.parametrize(("lost", "its_line"), [
    ("the load", "search finds the load's"),
    ("the hotlist", "its hotlist on"),
    ("the alert", "the hotlist's alert on the load"),
    ("the file", "the Ingest claim's files"),
])  # fmt: skip
def test_anything_v051_made_and_the_upgrade_lost_fails_on_its_own_line(tmp_path: Path, lost: str, its_line: str) -> None:
    """Each loss is caught by the line that exists for it, not only by another it drags down (a lost hotlist
    also empties its alerts): rule 15's second paragraph."""
    survival = _load(SURVIVAL, "survival_under_test")
    survival.snap(_R1State(tmp_path))
    with pytest.raises(SystemExit, match="did not all survive"):
        survival.verify(_R1State(tmp_path, lost))
    record = next((tmp_path / "records").glob("survival.log")).read_text().splitlines()
    assert any(line.startswith("FAIL") and its_line in line for line in record), record


def test_a_snap_of_a_case_holding_too_little_proves_nothing_and_stops(tmp_path: Path) -> None:
    survival = _load(SURVIVAL, "survival_under_test")
    with pytest.raises(SystemExit, match="left less than it should"):
        survival.snap(_R1State(tmp_path, "the alert"))
