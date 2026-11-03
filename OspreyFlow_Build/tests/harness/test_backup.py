"""`ospreyflow backup` on Small on a server of your own (ADR-114 Amendment 33 decision 5; drop 2,
unit 6): where the set is written, and what is never in it.

The stores' own dumps need the running deployment and are proved by the live exit test
(`test_restore_exit_test.py`); these cases are about the two things this mode adds — the folder
`server.backups` names, and the organisation's certificate key, which lives outside the deployment
and must never be copied into a set.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness import backup, site

from schemas.deployment import OspreyConfig

from .tls_fixtures import write_set


def _own_server(folder: Path, backups: str | None = "/srv/ospreyflow/backups") -> OspreyConfig:
    files = write_set(folder / "tls")
    raw: dict[str, object] = {
        "profile": "small",
        "network": {"public_origin": "https://osprey.example.internal",
                    "tls": {"certificate": str(files.certificate), "key": str(files.key),
                            "ca": str(files.ca)}},
    }  # fmt: skip
    if backups:
        raw["components"] = {"storage": {"backups": backups}}
    return OspreyConfig.model_validate(raw)


@pytest.fixture
def no_resolver_changes(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """`answer_the_deployment_here` reached, recorded, without changing this process's resolver
    or trust store for the tests after it."""
    seen: dict[str, list[str]] = {"trusted": []}
    monkeypatch.setattr(site, "_HERE", {})
    monkeypatch.setattr(site, "_answer_here", lambda: None)
    monkeypatch.setattr(site, "_trust", lambda files: seen["trusted"].extend(files))
    return seen


def test_a_self_contained_small_backs_up_to_its_configured_folder(tmp_path: Path) -> None:
    """Decision 5: `ospreyflow backup` writes to `server.backups` (`components.storage.backups`)
    by default on this mode; elsewhere it writes where it always has."""
    assert backup.default_out_root(_own_server(tmp_path)) == Path("/srv/ospreyflow/backups")
    lite = OspreyConfig.model_validate({})
    assert backup.default_out_root(lite) == backup.DEFAULT_BACKUP_ROOT


def test_backup_main_writes_to_the_configured_folder_reaching_the_servers_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_resolver_changes: dict[str, list[str]]
) -> None:
    config = _own_server(tmp_path, backups=str(tmp_path / "backups"))
    path = tmp_path / "osprey.yaml"
    path.write_text(yaml.safe_dump(config.model_dump(mode="json", exclude_defaults=True)))
    (tmp_path / "generated" / "small").mkdir(parents=True)
    (tmp_path / "generated" / "small" / "compose.yaml").write_text("services: {}\n")
    seen: dict[str, object] = {}

    def run_backup(**kwargs: object) -> Path:
        seen.update(kwargs)
        # What the identity export reaches: the deployment's own identity name, here.
        seen["id"] = site._HERE.get("id.osprey.example.internal")
        raise backup.BackupFailed("graph", "stopped by the test")

    monkeypatch.setattr(backup, "run_backup", run_backup)
    assert backup.main(["--config", str(path), "--generated-root", str(tmp_path / "generated")]) == 1
    assert seen["out_root"] == tmp_path / "backups"
    assert seen["id"] == "127.0.0.1"
    assert str(config.network.tls.certificate) in no_resolver_changes["trusted"]  # type: ignore[union-attr]


def test_a_backup_never_carries_the_tls_key(tmp_path: Path) -> None:
    """Decision 5 and §6.1: the set's configuration is the deployment's settings and rendered
    files — never the organisation's certificate key (mounted from where it is, never copied), and
    never `deployment.env`'s secrets."""
    config = _own_server(tmp_path)
    assert config.network.tls is not None
    key = Path(config.network.tls.key).read_bytes()
    deployment = tmp_path / "generated" / "small"
    deployment.mkdir(parents=True)
    (deployment / "compose.yaml").write_text(
        yaml.safe_dump({"services": {"proxy": {"volumes": [
            f"{config.network.tls.certificate}:/certs/cert.pem:ro",
            f"{config.network.tls.key}:/certs/key.pem:ro"]}}})
    )  # fmt: skip
    (deployment / "realm.json").write_text("{}\n")
    (deployment / "tls-fingerprint").write_text("ab:cd\n")
    (deployment / "deployment.env").write_text("OSPREY_ORG_SIGN_IN_SECRET=never-in-a-backup\n")
    target = tmp_path / "set"
    written = backup.backup_configuration(deployment / "compose.yaml", target)
    assert {item for item, _path in written} == {"configuration"}
    names = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    assert "config/compose.yaml" in names and "config/realm.json" in names
    for file in target.rglob("*"):
        if file.is_file():
            body = file.read_bytes()
            assert key not in body and b"PRIVATE KEY" not in body, file
            assert b"never-in-a-backup" not in body, file


def test_a_backup_set_is_readable_by_its_owner_only(tmp_path: Path) -> None:
    """A set holds the case data and the people's identities with the dashboards' client secrets;
    on a server it sits in a folder of its own (`server.backups`), so it is made owner-only."""
    target = backup.new_set_folder(tmp_path / "backups", "small")
    assert target.parent == tmp_path / "backups"
    assert target.stat().st_mode & 0o777 == 0o700
