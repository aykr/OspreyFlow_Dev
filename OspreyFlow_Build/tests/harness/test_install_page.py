"""The guided install page (ADR-114 Amendment 3, stage B2c): `harness/install_page.py`.

What a mistake would do, and the case that catches it:
- the page reachable by anything that did not get the link ospreyflow printed —
  `test_a_request_without_the_token_is_refused_in_words` (every route, from the real route table),
  `test_a_wrong_token_is_refused`, `test_the_token_may_come_as_a_header`;
- the token compared in a way that leaks it — `test_the_token_is_compared_in_constant_time`;
- the screens editing the product's own `osprey.yaml` rather than the draft —
  `test_the_draft_is_what_config_edits`;
- answers that cannot be installed saved anyway — `test_answers_naming_an_unknown_pack_are_refused_in_words`,
  `test_cloud_answers_on_lite_are_refused`;
- Small or Enterprise pretending to install — `test_small_and_enterprise_do_not_install`;
- a password on the page, or the page outliving the install —
  `test_lite_streams_the_install_hides_a_password_and_closes_the_page`;
- a sign-in wall in front of an install that has no identity provider yet —
  `test_sign_in_stays_off_with_a_rendered_realm_when_not_required`;
- the page reachable from the network — `test_main_binds_loopback_only`.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from harness import install_page, webapp
from harness.install_page import create_install_app

TOKEN = "t0ken-for-the-test"
PACKS = [
    {"id": "hmp", "title": "HMP", "shows": "A prison.", "delivery": "generated", "licence": "Own"},
    {"id": "paysim", "title": "PaySim", "shows": "Payments.", "delivery": "download",
     "licence": "CC BY-SA 4.0"},
]  # fmt: skip
INSTALL_SCRIPT = (
    "print('building the images'); print('password = hunter2'); print('the stack is up')"
)


def _python(script: str, code: int = 0) -> list[str]:
    return [sys.executable, "-c", f"{script}\nimport sys; sys.exit({code})"]


class Rig:
    def __init__(self, tmp: Path) -> None:
        self.product = tmp / "product"
        self.product.mkdir()
        self.own = self.product / "osprey.yaml"
        self.own.write_text("profile: local-lite\n", encoding="utf-8")
        self.draft = tmp / "draft" / "osprey.draft.yaml"
        self.draft.parent.mkdir()
        self.draft.write_text(self.own.read_text(encoding="utf-8"), encoding="utf-8")
        self.answers = tmp / "draft" / "install.yaml"
        self.shut: list[bool] = []
        self.install_args: list[Path] = []
        self.script = INSTALL_SCRIPT
        self.code = 0

    def app(self, **extra: Any) -> Any:
        def install_command(answers: Path) -> list[str]:
            self.install_args.append(answers)
            return _python(self.script, self.code)

        return create_install_app(
            product=self.product,
            token=TOKEN,
            draft_config=self.draft,
            answers_path=self.answers,
            install_command=install_command,
            doctor_command=_python("print('Docker is installed.')"),
            packs=PACKS,
            shutdown=lambda: self.shut.append(True),
            **extra,
        )

    def client(self, **extra: Any) -> TestClient:
        return TestClient(self.app(**extra), client=("127.0.0.1", 51000), follow_redirects=False)

    def signed(self, **extra: Any) -> TestClient:
        client = self.client(**extra)
        reply = client.get(f"/?token={TOKEN}")
        assert reply.status_code in (302, 303, 307)
        return client


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_a_request_without_the_token_is_refused_in_words(rig: Rig) -> None:
    client = rig.client()
    for path in ("/", "/api/install/state", "/api/config"):
        reply = client.get(path)
        assert reply.status_code == 403, path
        assert "opens only from the link ospreyflow printed" in reply.text
    assert client.put("/api/install/answers", json={"mode": "lite"}).status_code == 403
    assert client.post("/api/install/run").status_code == 403
    assert rig.shut == []


def test_every_route_is_behind_the_token(rig: Rig) -> None:
    """Built from the real route table, so a route added tomorrow is covered the day it lands."""
    client = rig.client()
    app = client.app
    routes = [r for r in app.routes if isinstance(r, APIRoute)]  # type: ignore[attr-defined]
    assert any(r.path == "/api/install/state" for r in routes)
    for route in routes:
        for method in route.methods - {"HEAD", "OPTIONS"}:
            path = route.path.replace("{profile}", "local-lite").replace("{name}", "x")
            path = path.replace("{dataset}", "x")
            reply = client.request(method, path)
            assert reply.status_code == 403, f"{method} {route.path} answered {reply.status_code}"


def test_the_right_token_sets_the_cookie_and_redirects(rig: Rig) -> None:
    client = rig.client()
    reply = client.get(f"/?token={TOKEN}")
    assert reply.status_code in (302, 303, 307)
    assert reply.headers["location"] == "/"
    cookie = reply.headers["set-cookie"].lower()
    assert "osprey_install=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert TOKEN not in reply.headers["location"]
    assert client.get("/api/install/state").status_code == 200


def test_a_wrong_token_is_refused(rig: Rig) -> None:
    client = rig.client()
    reply = client.get("/?token=not-the-token")
    assert reply.status_code == 403
    assert "set-cookie" not in reply.headers
    assert client.get("/api/install/state").status_code == 403


def test_a_wrong_cookie_is_refused(rig: Rig) -> None:
    client = rig.client()
    client.cookies.set("osprey_install", "forged")
    assert client.get("/api/install/state").status_code == 403


def test_the_token_may_come_as_a_header(rig: Rig) -> None:
    client = rig.client()
    assert client.get("/api/install/state", headers={"X-Install-Token": TOKEN}).status_code == 200
    assert client.get("/api/install/state", headers={"X-Install-Token": "no"}).status_code == 403


def test_the_token_is_compared_in_constant_time(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Any, Any]] = []
    real = install_page.hmac.compare_digest

    def spy(a: Any, b: Any) -> bool:
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(install_page.hmac, "compare_digest", spy)
    rig.client().get("/api/install/state", headers={"X-Install-Token": "guess"})
    assert seen, "the token was compared with == rather than hmac.compare_digest"


def test_state_names_the_modes_and_the_packs(rig: Rig) -> None:
    state = rig.signed().get("/api/install/state").json()
    assert state["mode"] == "lite"
    assert state["answers"] == {} or "config" not in state["answers"]
    assert [p["id"] for p in state["packs"]] == ["hmp", "paysim"]
    assert set(state["packs"][0]) == {"id", "title", "shows", "delivery", "licence"}
    assert state["home"] == str(Path.home())  # where the Folders screen suggests folders
    assert state["modes"]["lite"] == {"available": True}
    assert state["modes"]["small"] == {
        "available": False,
        "says": install_page.MODE_SAYS["small"],
    }
    assert state["modes"]["enterprise"]["says"] == install_page.MODE_SAYS["enterprise"]
    assert "--mode enterprise --cloud aws" in state["modes"]["enterprise"]["says"]
    assert state["modes"]["enterprise"]["available"] is False


def test_the_draft_is_what_config_edits(rig: Rig) -> None:
    client = rig.signed()
    reply = client.put("/api/config", json={"components": {"storage": {"ingest": "/srv/in"}}})
    assert reply.status_code == 200
    assert (
        yaml.safe_load(rig.draft.read_text(encoding="utf-8"))["components"]["storage"]["ingest"]
        == "/srv/in"
    )
    assert rig.own.read_text(encoding="utf-8") == "profile: local-lite\n"
    assert client.get("/api/config").json()["components"]["storage"]["ingest"] == "/srv/in"


def test_answers_are_saved_and_read_back_without_the_config_path(rig: Rig) -> None:
    client = rig.signed()
    reply = client.put(
        "/api/install/answers",
        json={"mode": "lite", "demo_packs": ["hmp", "paysim"], "paysim_file": "/tmp/ps.csv"},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["answers"] == {
        "mode": "lite",
        "demo_packs": ["hmp", "paysim"],
        "paysim_file": "/tmp/ps.csv",
    }
    written = yaml.safe_load(rig.answers.read_text(encoding="utf-8"))
    assert written["config"] == str(rig.draft)  # the draft is used as it is
    assert written["mode"] == "lite" and written["demo_packs"] == ["hmp", "paysim"]
    assert client.get("/api/install/state").json()["answers"]["demo_packs"] == ["hmp", "paysim"]


def test_small_answers_carry_the_cloud_and_are_saved(rig: Rig) -> None:
    client = rig.signed()
    cloud = {"provider": "aws", "region": "eu-west-2", "domain": "osprey.example.org",
             "size": "medium"}  # fmt: skip
    reply = client.put("/api/install/answers", json={"mode": "small", "cloud": cloud})
    assert reply.status_code == 200, reply.text
    assert reply.json()["mode"] == "small"
    assert reply.json()["answers"]["cloud"] == cloud


def test_answers_naming_an_unknown_pack_are_refused_in_words(rig: Rig) -> None:
    reply = rig.signed().put(
        "/api/install/answers", json={"mode": "lite", "demo_packs": ["secret-pack"]}
    )
    assert reply.status_code == 422
    assert "no demo pack called 'secret-pack'" in reply.json()["error"]
    assert not rig.answers.exists()


def test_cloud_answers_on_lite_are_refused(rig: Rig) -> None:
    reply = rig.signed().put(
        "/api/install/answers",
        json={"mode": "lite", "cloud": {"provider": "aws", "region": "x", "domain": "y"}},
    )
    assert reply.status_code == 422
    assert "cloud settings are for the small and enterprise modes" in reply.json()["error"]
    assert not rig.answers.exists()


def test_an_unknown_mode_is_refused(rig: Rig) -> None:
    reply = rig.signed().put("/api/install/answers", json={"mode": "huge"})
    assert reply.status_code == 422 and "mode is one of" in reply.json()["error"]


def test_the_doctor_runs_for_the_chosen_mode(rig: Rig) -> None:
    client = rig.signed()
    client.put("/api/install/answers", json={"mode": "lite"})
    reply = client.get("/api/install/doctor")
    assert reply.status_code == 200
    body = reply.json()
    assert body["returncode"] == 0 and "Docker is installed." in body["lines"]


def test_a_failing_doctor_reports_its_code(rig: Rig) -> None:
    app = create_install_app(
        product=rig.product, token=TOKEN, draft_config=rig.draft, answers_path=rig.answers,
        install_command=lambda a: _python("pass"),
        doctor_command=_python("print('Git is not installed.')", 1),
        packs=PACKS, shutdown=lambda: None,
    )  # fmt: skip
    client = TestClient(app, client=("127.0.0.1", 51000))
    client.get(f"/?token={TOKEN}")
    body = client.get("/api/install/doctor").json()
    assert body["returncode"] == 1 and body["lines"] == ["Git is not installed."]


@pytest.mark.parametrize(
    "mode,said",
    [("small", "--mode small --cloud aws"), ("enterprise", "--mode enterprise --cloud aws")],
)
def test_small_and_enterprise_do_not_install(rig: Rig, mode: str, said: str) -> None:
    """The page never builds in a cloud: Small and Enterprise are built from a terminal (ADR-114
    Amendments 10 and 19)."""
    client = rig.signed()
    client.put("/api/install/answers", json={"mode": mode})
    reply = client.post("/api/install/run")
    assert reply.status_code == 409
    assert said in reply.json()["error"]
    assert rig.install_args == [] and rig.shut == []


def _events(client: TestClient) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    with client.stream("POST", "/api/install/run") as reply:
        assert reply.status_code == 200
        body = "".join(reply.iter_text())
    for block in body.strip().split("\n\n"):
        name = "message"
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        out.append((name, json.loads(data)))
    return out


def test_lite_streams_the_install_hides_a_password_and_closes_the_page(rig: Rig) -> None:
    client = rig.signed()
    client.put("/api/install/answers", json={"mode": "lite"})
    events = _events(client)
    lines = [d["line"] for n, d in events if n == "message"]
    assert lines[0] == "building the images" and lines[-1] == "the stack is up"
    assert not any("hunter2" in line for line in lines)
    assert any("hidden" in line for line in lines)
    assert events[-1] == ("complete", {"returncode": 0})
    assert rig.install_args == [rig.answers]
    assert rig.shut == [True]


def test_a_failed_install_reports_its_code_and_still_closes_the_page(rig: Rig) -> None:
    rig.code = 3
    client = rig.signed()
    client.put("/api/install/answers", json={"mode": "lite"})
    assert _events(client)[-1] == ("complete", {"returncode": 3})
    assert rig.shut == [True]


def test_running_without_saved_answers_is_refused(rig: Rig) -> None:
    reply = rig.signed().post("/api/install/run")
    assert reply.status_code == 409
    assert "answers" in reply.json()["error"].lower()
    assert rig.install_args == []


def test_sign_in_stays_off_with_a_rendered_realm_when_not_required(
    rig: Rig, tmp_path: Path
) -> None:
    out_root = tmp_path / "generated"
    (out_root / "local-lite").mkdir(parents=True)
    (out_root / "local-lite" / "realm.json").write_text("{}", encoding="utf-8")
    assert webapp.rendered_realm_exists(out_root)
    # The default would turn the sign-in on ...
    on = webapp.create_app(config_path=rig.draft, out_root=out_root)
    assert on.state.sign_in is not None
    # ... and `require_sign_in=False` keeps it off whatever is rendered.
    off = webapp.create_app(config_path=rig.draft, out_root=out_root, require_sign_in=False)
    assert off.state.sign_in is None
    client = TestClient(off, client=("127.0.0.1", 51000))
    assert client.get("/api/config").status_code == 200


def test_the_install_page_never_asks_for_a_sign_in(rig: Rig) -> None:
    assert rig.app().state.sign_in is None


def test_main_binds_loopback_only(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    started: dict[str, Any] = {}

    class FakeServer:
        def __init__(self, config: Any) -> None:
            started["host"] = config.host
            started["port"] = config.port
            self.should_exit = False

        def run(self) -> None:
            started["ran"] = True

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setattr(install_page, "_pack_rows", lambda: PACKS)
    code = install_page.main(
        ["--product", str(rig.product), "--token", TOKEN, "--port", "49555",
         "--draft", str(rig.draft), "--answers", str(rig.answers)]
    )  # fmt: skip
    assert code == 0
    assert started == {"host": "127.0.0.1", "port": 49555, "ran": True}


def test_main_refuses_a_host_argument(rig: Rig) -> None:
    with pytest.raises(SystemExit):
        install_page.main(["--host", "0.0.0.0"])  # noqa: S104


def test_the_install_command_is_the_products_own_with_the_answers_file(rig: Rig) -> None:
    argv = install_page.install_argv(rig.product, rig.answers)
    assert argv[-9:] == ["-m", "ospreyflow", "install", "--mode", "lite", "--config",
                         str(rig.answers), "--yes", "--force"]  # fmt: skip
    assert install_page.doctor_argv(rig.product)[-3:] == ["-m", "ospreyflow", "doctor"]


def test_idle_time_ends_the_page(rig: Rig) -> None:
    app = rig.app()
    app.state.last_seen = 1000.0
    clock = [1000.0]
    check: Callable[[], bool] = install_page.idle_check(app, minutes=30, now=lambda: clock[0])
    assert check() is False
    clock[0] += 29 * 60
    assert check() is False
    clock[0] += 2 * 60
    assert check() is True
    # any request, even a refused one, is use
    TestClient(app, client=("127.0.0.1", 51000)).get("/api/install/state")
    assert install_page.idle_check(app, minutes=30)() is False
