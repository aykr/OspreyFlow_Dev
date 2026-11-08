"""The gateway's database and the models file in a backup set, and the restore that refuses to lose
model keys silently (`06_DECISIONS.md` ADR-135 Amendment 2 decision 9). Measured on the pinned
LiteLLM: restarted under another encryption key, every stored engine and credential is dropped with
only a warning in its log, so a restore onto another deployment must say so before it happens.

Each case runs the real code path (`backup_postgres_all`, `run_restore`) with Docker answered by a
stand-in runner; nothing reaches a deployment.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from harness import backup, restore
from harness.backup import gateway_key_check, schema_versions

SALT_HERE = "salt-of-this-deployment-0123456789"
SALT_THERE = "salt-of-another-deployment-987654"


def _env(folder: Path, salt: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    env = folder / "deployment.env"
    env.write_text(
        f"POSTGRES_USER=osprey\nPOSTGRES_DB=ospreyflow\nOSPREY_LITELLM_SALT_SECRET={salt}\n"
    )
    (folder / "compose.yaml").write_text("services: {}\n")
    return folder / "compose.yaml"


def test_backup_dumps_the_gateway_s_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose = _env(tmp_path / "dep", SALT_HERE)

    def run(command: list[str], **_kw: object) -> str:
        if "--roles-only" in command:
            return "CREATE ROLE litellm;\n"
        if "-Atc" in command:
            return "keycloak\nlitellm\nospreyflow\n"
        return f"-- dump of {command[-1]}\nCREATE TABLE t (i int);\n"

    monkeypatch.setattr(backup, "_run", run)
    written = backup.backup_postgres_all(compose, tmp_path / "set" / "postgres")
    names = sorted(p.name for _, p in written)
    assert "litellm.sql" in names and "keycloak.sql" not in names


def test_the_check_value_tells_encryption_keys_apart_and_never_holds_one(tmp_path: Path) -> None:
    here = gateway_key_check(_env(tmp_path / "a", SALT_HERE).parent / "deployment.env")
    again = gateway_key_check(_env(tmp_path / "b", SALT_HERE).parent / "deployment.env")
    there = gateway_key_check(_env(tmp_path / "c", SALT_THERE).parent / "deployment.env")
    assert here == again and here != there
    assert here is not None and SALT_HERE not in here


def _set(tmp_path: Path, *, sealed_under: str, keys: list[str]) -> Path:
    directory = tmp_path / "set"
    (directory / "config").mkdir(parents=True)
    (directory / "config" / "models.yaml").write_text(
        "providers: []\ndefaults: {}\nkeys:\n"
        + "".join(f"  {k}: {{set_at: '2026-11-08T00:00:00Z', set_by: a}}\n" for k in keys)
    )
    check = gateway_key_check(_env(tmp_path / "source", sealed_under).parent / "deployment.env")
    manifest = {
        "format": 1,
        "schema_versions": schema_versions(include_weights=False),
        "gateway_key_check": check,
        "files": [],
        "empty": [],
        "quiesced": True,
        "audit_disposition": backup.AUDIT_DISPOSITION,
        "taken_at": "2026-11-08T00:00:00+00:00",
        "profile": "local-lite",
        "database": "ospreyflow",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


def _dry_run(directory: Path, compose: Path, *, lost_ok: bool = False) -> object:
    return restore.run_restore(
        directory=directory,
        compose_file=compose,
        database="ospreyflow",
        analytics_container_path="/data/analytics.duckdb",
        acknowledged=False,
        keys_will_be_lost=lost_ok,
    )


def test_a_set_sealed_under_another_key_is_refused_naming_each_key_lost(tmp_path: Path) -> None:
    directory = _set(tmp_path, sealed_under=SALT_THERE, keys=["gemini", "openai"])
    compose = _env(tmp_path / "here", SALT_HERE)
    with pytest.raises(restore.RestoreRefused) as refused:
        _dry_run(directory, compose)
    assert "the keys of gemini, openai would be lost" in refused.value.reason
    assert "--model-keys-will-be-lost" in refused.value.remedy
    assert SALT_HERE not in str(refused.value) and SALT_THERE not in str(refused.value)


def test_the_override_restores_knowing_the_keys_are_lost(tmp_path: Path) -> None:
    directory = _set(tmp_path, sealed_under=SALT_THERE, keys=["gemini"])
    _dry_run(directory, _env(tmp_path / "here", SALT_HERE), lost_ok=True)


def test_a_set_restored_where_it_was_taken_is_not_refused(tmp_path: Path) -> None:
    directory = _set(tmp_path, sealed_under=SALT_HERE, keys=["gemini"])
    _dry_run(directory, _env(tmp_path / "here", SALT_HERE))


def test_a_set_with_no_key_set_loses_nothing_and_is_not_refused(tmp_path: Path) -> None:
    directory = _set(tmp_path, sealed_under=SALT_THERE, keys=[])
    _dry_run(directory, _env(tmp_path / "here", SALT_HERE))
