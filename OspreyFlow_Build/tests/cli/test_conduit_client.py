"""`ospreyflow release` and `ospreyflow run` as thin clients (`06_DECISIONS.md` ADR-140
Amendment 9 decision 4; ADR-141 decisions 9–12): each sends what the Studio's buttons send, writes
nothing on a refusal, exits non-zero on a refusal or a met `--fail-on`, and never passes a run whose
counts it could not see.

The identity provider double refuses what Keycloak refuses for the client-credentials grant
(rule 15, second worked example): a wrong secret is `401 invalid_client`, a client not enabled for
service accounts `400 unauthorized_client`. The Conduit double answers in the routes' own shapes.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from cli.ospreyflow.conduit_client import (
    FailOn,
    parse_fail_on,
    release_export,
    release_import,
    run,
    service_token,
)
from cli.ospreyflow.home import CommandRefused

_FILES = {"release.yaml": "apiVersion: ospreyflow.io/v1\n", "model.yaml": "packs: {}\n"}


def _conduit(handler: object) -> httpx.Client:
    return httpx.Client(base_url="http://conduit", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_export_writes_the_bundle_and_says_what_was_left_out(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"files": _FILES, "left_out": 1})

    said: list[str] = []
    out = tmp_path / "bundle"
    code = release_export(
        _conduit(handler), token="tok", dataset="pid", name="r", version="1", out=out,
        say=said.append,
    )  # fmt: skip
    assert code == 0
    assert (out / "release.yaml").read_text() == _FILES["release.yaml"]
    assert seen[0].url.path == "/v1/datasets/pid/release"
    assert seen[0].headers["Authorization"] == "Bearer tok"
    assert any("1 published pipeline(s) are marked above" in s for s in said)


def test_export_never_writes_into_a_folder_holding_files(tmp_path: Path) -> None:
    (tmp_path / "old.txt").write_text("x")
    with pytest.raises(CommandRefused):
        release_export(
            _conduit(lambda r: httpx.Response(200, json={"files": _FILES})),
            token="t", dataset="pid", name="r", version="1", out=tmp_path,
        )  # fmt: skip


def test_export_refuses_a_file_outside_its_folder(tmp_path: Path) -> None:
    files = {"../outside.yaml": "x"}
    with pytest.raises(CommandRefused):
        release_export(
            _conduit(lambda r: httpx.Response(200, json={"files": files})),
            token="t", dataset="pid", name="r", version="1", out=tmp_path / "b",
        )  # fmt: skip
    assert not (tmp_path / "outside.yaml").exists()


def test_import_dry_run_sends_dry_run_and_says_nothing_was_written(tmp_path: Path) -> None:
    for path, text in _FILES.items():
        (tmp_path / path).write_text(text)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = {"role": "pipeline", "name": "Visits", "action": "new_draft"}
        return httpx.Response(200, json={"dry_run": True, "items": [item], "refused": []})

    said: list[str] = []
    code = release_import(
        _conduit(handler), token="t", dataset="pid", folder=tmp_path, dry_run=True, say=said.append
    )
    assert code == 0
    assert seen[0].url.params["dry_run"] == "true"
    assert json.loads(seen[0].content)["files"] == _FILES
    assert said[-1] == "Nothing was written (a dry run)."


def test_a_refused_import_exits_one_and_says_why(tmp_path: Path) -> None:
    (tmp_path / "release.yaml").write_text("x")
    said: list[str] = []
    code = release_import(
        _conduit(lambda r: httpx.Response(422, json={"refused": ["model.yaml is changed"]})),
        token="t", dataset="pid", folder=tmp_path, dry_run=False, say=said.append,
    )  # fmt: skip
    assert code == 1
    assert "Refused: model.yaml is changed" in said and "Nothing was written." in said


def _keycloak(request: httpx.Request) -> httpx.Response:
    form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
    if form.get("grant_type") != "client_credentials":
        return httpx.Response(400, json={"error": "unsupported_grant_type"})
    if form.get("client_id") == "no-service-accounts":
        words = "Client not enabled to retrieve service account"
        return httpx.Response(
            400, json={"error": "unauthorized_client", "error_description": words}
        )
    if form.get("client_secret") != "right-secret":
        return httpx.Response(401, json={"error": "invalid_client"})
    return httpx.Response(200, json={"access_token": "svc-token", "token_type": "Bearer"})


_ENV = {"OSPREY_TOKEN_URL": "http://idp/token", "OSPREY_CLIENT_ID": "airflow"}


def test_the_service_identity_signs_in_by_client_credentials() -> None:
    http = httpx.Client(transport=httpx.MockTransport(_keycloak))
    assert service_token({**_ENV, "OSPREY_CLIENT_SECRET": "right-secret"}, http) == "svc-token"


@pytest.mark.parametrize(
    "env",
    [
        {**_ENV, "OSPREY_CLIENT_SECRET": "wrong"},
        {**_ENV, "OSPREY_CLIENT_ID": "no-service-accounts", "OSPREY_CLIENT_SECRET": "right-secret"},
    ],
)
def test_what_keycloak_refuses_is_refused_in_words_without_the_secret(env: dict[str, str]) -> None:
    http = httpx.Client(transport=httpx.MockTransport(_keycloak))
    with pytest.raises(CommandRefused) as refused:
        service_token(env, http)
    assert "refused the service identity's sign-in" in str(refused.value)
    assert env["OSPREY_CLIENT_SECRET"] not in str(refused.value)


def _runs(*answers: dict[str, object]) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202 if request.method == "POST" else 200, json=queue.pop(0))

    return _conduit(handler), seen


def _status(outcome: str, **extra: object) -> dict[str, object]:
    return {"run_id": "run-1", "pipeline_id": "p", "version": 3, "external_run_id": "dag:1",
            "outcome": outcome, "started_at": "2026-11-10T09:00:00Z", **extra}  # fmt: skip


def _go(http: httpx.Client, fail_on: FailOn = FailOn(), said: list[str] | None = None) -> int:
    return run(
        http, token="svc", dataset="pid", pipeline="p", version="latest",
        external_run_id="dag:1", wait=True, fail_on=fail_on,
        say=(said if said is not None else []).append, sleep=lambda s: None, clock=lambda: 0.0,
    )  # fmt: skip


def test_a_run_waits_and_succeeds() -> None:
    http, seen = _runs(_status("running"), _status("succeeded", rows_read=10, rows_held=0))
    assert _go(http) == 0
    assert json.loads(seen[0].content) == {
        "dataset_id": "pid", "pipeline_id": "p", "version": "latest", "external_run_id": "dag:1",
    }  # fmt: skip
    assert seen[1].url.path == "/v1/runs/run-1"


def test_a_refused_run_exits_one_with_its_words() -> None:
    said: list[str] = []
    http, _ = _runs(_status("refused", words="the quota of 1 run a day is used"))
    assert _go(http, said=said) == 1
    assert "the quota of 1 run a day is used" in said[-1]


def test_fail_on_held_is_met_by_a_held_row() -> None:
    http, _ = _runs(_status("succeeded", rows_read=10, rows_held=2))
    assert _go(http, parse_fail_on("held")) == 2


def test_fail_on_rejections_is_a_share_of_rows_read() -> None:
    http, _ = _runs(_status("succeeded", rows_read=100, rows_rejected=6))
    assert _go(http, parse_fail_on("rejections>5%")) == 2
    http, _ = _runs(_status("succeeded", rows_read=100, rows_rejected=5))
    assert _go(http, parse_fail_on("rejections>5%")) == 0


def test_withheld_counts_never_pass_a_fail_on() -> None:
    http, _ = _runs(_status("succeeded", withheld=True))
    assert _go(http, parse_fail_on("held")) == 2


def test_an_unknown_fail_on_is_refused() -> None:
    with pytest.raises(CommandRefused):
        parse_fail_on("rows>3")


# --- through the command's own entry point ---------------------------------------------------------


def _main(product: Path, home: Path, *argv: str, env: dict[str, str]) -> int:
    from cli.ospreyflow.main import main

    return main(
        list(argv),
        home_env={"OSPREYFLOW_HOME": str(product), "HOME": str(home), **env},
        recorded_home=lambda: None,
        ask=lambda prompt, default="": default,
        ask_secret=lambda prompt: "",
        open_url=lambda url: None,
    )


@pytest.fixture
def conduit(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """The verbs' client, answering as the routes do, at the address the command chose."""
    from cli.ospreyflow import conduit_client

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/release"):
            return httpx.Response(200, json={"files": _FILES, "left_out": 0})
        if request.url.path.endswith("/release/import"):
            return httpx.Response(200, json={"dry_run": True, "items": [], "refused": []})
        return httpx.Response(202, json=_status("succeeded", rows_read=1, rows_held=0))

    monkeypatch.setattr(
        conduit_client,
        "client",
        lambda api: httpx.Client(base_url=api, transport=httpx.MockTransport(handler)),
    )
    return seen


_PERSON = {"OSPREY_TOKEN": "person-token", "OSPREY_API_URL": "http://conduit.test"}


def test_release_export_and_import_through_the_command(
    product: Path, tmp_path: Path, conduit: list[httpx.Request]
) -> None:
    out = tmp_path / "bundle"
    args = ("release", "export", "pid", "--name", "r", "--release-version", "1", "--out", str(out))
    assert _main(product, tmp_path / "home", *args, env=_PERSON) == 0
    assert (out / "release.yaml").is_file()
    args = ("release", "import", str(out), "--dataset", "pid", "--dry-run")
    assert _main(product, tmp_path / "home", *args, env=_PERSON) == 0
    assert [r.url.host for r in conduit] == ["conduit.test", "conduit.test"]
    assert conduit[1].url.params["dry_run"] == "true"
    assert all(r.headers["Authorization"] == "Bearer person-token" for r in conduit)


def test_run_through_the_command_needs_the_service_identity(
    product: Path, tmp_path: Path, conduit: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    args = ("run", "pid", "p", "--external-run-id", "dag:1")
    assert _main(product, tmp_path / "home", *args, env={"OSPREY_API_URL": "http://c"}) == 1
    assert "OSPREY_TOKEN_URL" in capsys.readouterr().err
    assert conduit == []
    env = {"OSPREY_API_URL": "http://c", "OSPREY_TOKEN": "svc-token"}
    assert _main(product, tmp_path / "home", *args, "--wait", "--fail-on", "held", env=env) == 0
    assert conduit[0].url.path == "/v1/runs"


@pytest.mark.parametrize("confirmed", [False, True])
def test_replace_own_draft_is_sent_only_when_given(tmp_path: Path, confirmed: bool) -> None:
    """CARRIES row 90: the confirmation travels as the route's own query, never by default."""
    (tmp_path / "release.yaml").write_text("x")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": [], "refused": []})

    code = release_import(
        _conduit(handler), token="t", dataset="pid", folder=tmp_path, dry_run=False,
        replace_own_draft=confirmed, say=lambda _: None,
    )  # fmt: skip
    assert code == 0
    assert seen[0].url.params["replace_own_draft"] == ("true" if confirmed else "false")


def test_the_parser_takes_replace_own_draft() -> None:
    from cli.ospreyflow.main import _parser

    args = _parser().parse_args(
        ["release", "import", "bundle", "--dataset", "pid", "--replace-own-draft"]
    )
    assert args.replace_own_draft is True
    plain = _parser().parse_args(["release", "import", "bundle", "--dataset", "pid"])
    assert plain.replace_own_draft is False
