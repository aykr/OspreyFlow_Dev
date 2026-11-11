"""The install runbook's sign-in step (`harness/cloud_platform/identity.py`, ADR-148 Amendment 5):
it reads the deployment's namespace and our Secret's name from the rendered values, decodes the
Secret `kubectl` prints, and hands both to the cluster's own identity step."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.cloud_platform import identity
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig


def test_it_configures_the_namespace_s_identity_from_our_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = OspreyConfig.model_validate(
        yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    )
    values = tmp_path / "values.yaml"
    values.write_text(render(config, resolver=_resolver).artefacts["values.yaml"], encoding="utf-8")
    asked: list[list[str]] = []

    def kubectl(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        asked.append(argv)
        data = {"OSPREY_OIDC_CLIENT_SECRET": base64.b64encode(b"s3cret").decode()}
        return subprocess.CompletedProcess(argv, 0, json.dumps(data), "")

    given: dict[str, Any] = {}

    def configure(_kube: Any, namespace: str, cfg: OspreyConfig, held: dict[str, str]) -> list[str]:
        given.update(namespace=namespace, held=held, cfg=cfg)
        return ["configured"]

    monkeypatch.setattr(subprocess, "run", kubectl)
    monkeypatch.setattr("harness.cluster_install._configure_identity", configure)
    assert identity.main([str(values)]) == 0
    assert asked == [["kubectl", "-n", "ospreyflow-poc", "get", "secret", "ospreyflow-secrets",
                      "-o", "jsonpath={.data}"]]  # fmt: skip
    assert given["namespace"] == "ospreyflow-poc"
    assert given["held"] == {"OSPREY_OIDC_CLIENT_SECRET": "s3cret"}
    assert given["cfg"].cloud_platform.shape == "poc"


def test_it_says_how_it_is_run_when_given_nothing() -> None:
    assert identity.main([]) == 2
