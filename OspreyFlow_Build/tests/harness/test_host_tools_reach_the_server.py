"""Every host tool that reaches a running deployment answers a server's own names on this server
(ADR-114 Amendment 33 decision 2; drop 2, unit 6). Drop 1 gave it to `apply` and `register_sign_in`;
`backup` (its identity export), `restore`, `start --build` (`scripts.refresh`) and the seeds
(`scripts.seed_internal`, through `scripts.refresh`'s deployment finder) reach the deployment's
identity provider too, and on a server with the organisation's certificate the names neither
resolve before the organisation's DNS does nor verify without the organisation's CA.

`answer_the_deployment_here` itself is proved against a real Caddy and a real TLS client in
`test_proxy_tls_caddy.py`; these cases prove each tool calls it, recorded without changing this
process's resolver or trust store.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness import restore, site

from schemas.deployment import OspreyConfig

HOST = "osprey.example.internal"


def _config() -> OspreyConfig:
    return OspreyConfig.model_validate({
        "profile": "small",
        "network": {"public_origin": f"https://{HOST}",
                    "tls": {"certificate": "/etc/ospreyflow/tls/osprey.crt",
                            "key": "/etc/ospreyflow/tls/osprey.key",
                            "ca": "/etc/ospreyflow/tls/org-root.pem"}},
    })  # fmt: skip


@pytest.fixture
def answered(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    here: dict[str, str] = {}
    monkeypatch.setattr(site, "_HERE", here)
    monkeypatch.setattr(site, "_answer_here", lambda: None)
    monkeypatch.setattr(site, "_trust", lambda files: None)
    return here


def _deployment(root: Path) -> Path:
    """A rendered deployment under `root/deploy/generated/small`, with its `osprey.yaml` copy."""
    folder = root / "deploy" / "generated" / "small"
    folder.mkdir(parents=True)
    (folder / "compose.yaml").write_text("services: {}\n")
    text = yaml.safe_dump(_config().model_dump(mode="json", exclude_defaults=True))
    (folder / "osprey.yaml").write_text(text)
    (root / "osprey.yaml").write_text(text)
    return folder


def test_restore_answers_the_servers_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answered: dict[str, str]
) -> None:
    folder = _deployment(tmp_path)
    seen: dict[str, str | None] = {}

    def run_restore(**_kwargs: object) -> object:
        seen["id"] = site._HERE.get(f"id.{HOST}")
        raise restore.RestoreRefused("stopped by the test", "")

    monkeypatch.setattr(restore, "run_restore", run_restore)
    code = restore.main([str(tmp_path / "set"), "--config", str(tmp_path / "osprey.yaml"),
                         "--generated-root", str(folder.parent)])  # fmt: skip
    assert code == 2
    assert seen["id"] == "127.0.0.1"


def test_start_build_and_the_seeds_answer_the_servers_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answered: dict[str, str]
) -> None:
    """`scripts.refresh` finds the deployment for `start --build`, for `update`'s files and for
    every seed (`scripts.seed_internal`); finding it answers its names."""
    from scripts import refresh

    folder = _deployment(tmp_path)
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE, raising=False)
    assert refresh._deployment_dir(tmp_path) == folder
    assert answered == {HOST: "127.0.0.1", f"id.{HOST}": "127.0.0.1", f"bi.{HOST}": "127.0.0.1"}
    answered.clear()
    monkeypatch.setattr(refresh, "refresh", lambda repo_root: None)
    assert refresh.main([], repo_root=tmp_path) == 0
    assert answered.get(f"id.{HOST}") == "127.0.0.1"


def test_a_lite_deployment_is_answered_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answered: dict[str, str]
) -> None:
    from scripts import refresh

    folder = tmp_path / "deploy" / "generated" / "local-lite"
    folder.mkdir(parents=True)
    (folder / "compose.yaml").write_text("services: {}\n")
    (folder / "osprey.yaml").write_text("map: null\n")
    (tmp_path / "osprey.yaml").write_text("map: null\n")
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE, raising=False)
    assert refresh._deployment_dir(tmp_path) == folder
    assert answered == {}
