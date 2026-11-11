"""The install runbook's sign-in step (`harness/cloud_platform/identity.py`, ADR-148 Amendment 5):
it reads our Secret, hands the cluster's identity step the deployment's settings and the Secret
together, as the cluster's own install does (`harness.cluster_install`, step 5: the realm's sign-in
reads ConfigMap settings, the dashboards' address among them, and our Secret alone has none of
them), then makes the first administrator, as the cluster's install's step 6 does."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.cloud_platform import identity
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig


class Kube:
    """kubectl as the namespace's tenant sees it: our Secret, and Keycloak's admin tool."""

    def __init__(self, made: tuple[int, str, str] = (0, "", "")) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.made = made

    def run(self, argv: list[str], *, stdin: str | None = None) -> tuple[int, str, str]:
        self.calls.append((argv, stdin))
        if argv[3:6] == ["get", "secret", "ospreyflow-secrets"]:
            data = {"OSPREY_OIDC_CLIENT_SECRET": base64.b64encode(b"s3cret").decode()}
            return 0, json.dumps(data), ""
        return self.made


@pytest.fixture
def values_file(tmp_path: Path) -> Path:
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    path = tmp_path / "values.yaml"
    config = OspreyConfig.model_validate(raw)
    path.write_text(render(config, resolver=_resolver).artefacts["values.yaml"], encoding="utf-8")
    return path


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    given: dict[str, Any] = {}

    def configure(_kube: Any, namespace: str, cfg: OspreyConfig, held: dict[str, str]) -> list[str]:
        given.update(namespace=namespace, held=dict(held), cfg=cfg)
        return ["configured"]

    monkeypatch.setattr("harness.cluster_install._configure_identity", configure)
    return given


def test_identity_is_given_the_settings_and_our_secret_together(
    values_file: Path, configured: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    kube = Kube()
    assert identity.main([str(values_file)], kube=kube) == 0
    environment = yaml.safe_load(values_file.read_text(encoding="utf-8"))["environment"]
    assert configured["namespace"] == "ospreyflow-poc"
    assert configured["held"]["OSPREY_OIDC_CLIENT_SECRET"] == "s3cret"
    # Every ConfigMap setting the cluster's install would give it, not our Secret's alone.
    assert {k: configured["held"][k] for k in environment} == environment
    assert kube.calls[0][0] == ["kubectl", "-n", "ospreyflow-poc", "get", "secret",
                                "ospreyflow-secrets", "-o", "jsonpath={.data}"]  # fmt: skip
    # The Python step's own kubectl, as the runbook's: the namespace's, never cluster-wide.
    assert all(argv[:3] == ["kubectl", "-n", "ospreyflow-poc"] for argv, _ in kube.calls)


def test_the_first_administrator_is_made_and_its_code_said_once(
    values_file: Path, configured: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    kube = Kube()
    assert identity.main([str(values_file), "--email", "lead@example.org"], kube=kube) == 0
    argv, stdin = kube.calls[-1]
    assert argv[:6] == ["kubectl", "-n", "ospreyflow-poc", "exec", "-i", "keycloak-0"]
    user = json.loads(stdin or "{}")
    assert user["username"] == "admin" and user["email"] == "lead@example.org"
    out = capsys.readouterr().out
    assert "first administrator admin made: sign in once with the code" in out


def test_an_administrator_already_there_is_left_unchanged(
    values_file: Path, configured: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    kube = Kube(made=(1, "", "Conflict detected"))
    assert identity.main([str(values_file)], kube=kube) == 0
    assert "already exists; unchanged" in capsys.readouterr().out


def test_a_refused_administrator_fails_the_step(
    values_file: Path, configured: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    kube = Kube(made=(1, "", "forbidden"))
    assert identity.main([str(values_file)], kube=kube) == 1
    assert "making the first administrator: forbidden" in capsys.readouterr().err


def test_it_says_how_it_is_run_when_given_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    assert identity.main([]) == 2


def test_the_sign_in_step_s_port_forward_is_the_namespace_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identity step reaches Keycloak through the cluster install's own port-forward, which runs
    as the namespace's tenant (`kubectl -n <namespace>`), never cluster-wide."""
    import subprocess

    from harness.cluster_install import SystemKube

    asked: list[list[str]] = []

    class Refused(Exception):
        pass

    def popen(argv: list[str], **_: Any) -> Any:
        asked.append(argv)
        raise Refused

    monkeypatch.setattr(subprocess, "Popen", popen)
    with (
        pytest.raises(Refused),
        SystemKube().port_forward("ospreyflow-poc", "service/keycloak", 8080),
    ):
        pass
    assert asked[0][:4] == ["kubectl", "-n", "ospreyflow-poc", "port-forward"]
