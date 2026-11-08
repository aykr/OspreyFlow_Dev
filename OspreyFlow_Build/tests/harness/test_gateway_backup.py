"""The gateway's database and the models file in a backup set, and what a restore says
(`06_DECISIONS.md` ADR-135 Amendment 2, the owner's ruling of 8 November 2026 on `05_DEPLOYMENT.md`
§6.1: "A backup carries no secrets … Nothing in a backup may ever be encrypted with a
deployment-scoped key"). The gateway's tables whose rows hold a key or a sealed value are dumped
without their rows; every restore brings the engines back and names each key to enter again.

Each case runs the real code path (`backup_postgres_all`, `run_restore`) with Docker answered by a
stand-in runner whose `pg_dump` leaves out a table's rows for `--exclude-table-data`, as `pg_dump`
does; nothing reaches a deployment. `test_model_gateway_live.py` checks the same flags against the
real `pg_dump` and the pinned gateway's own tables.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from harness import backup, restore
from harness.backup import schema_versions

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


PLANTED = "sk-PLANTED-backup-key-Q7Z4"
SEALED = "sealed:" + PLANTED[::-1]  # stands for the gateway's encrypted copy of the key


def _pg_dump_honouring_exclusions(tables: dict[str, list[str]]) -> object:
    def dump(command: list[str]) -> str:
        excluded = {a.split("=", 1)[1] for a in command if a.startswith("--exclude-table-data=")}
        out = [f"-- dump of {command[-1]}"]
        for table, rows in tables.items():
            out.append(f'CREATE TABLE public."{table}" (v text);')
            if f'public."{table}"' in excluded:
                continue
            out += [f'COPY public."{table}" (v) FROM stdin;', *rows, "\\."]
        return "\n".join(out) + "\n"

    return dump


def test_a_backup_holds_no_key_and_no_sealed_value_of_the_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose = _env(tmp_path / "dep", SALT_HERE)
    gateway = _pg_dump_honouring_exclusions({
        "LiteLLM_CredentialsTable": [f"osprey-gemini\t{{\"api_key\": \"{SEALED}\"}}"],
        "LiteLLM_ProxyModelTable": [f"osprey-gemini-flash\t{SEALED}"],
        "LiteLLM_Config": [f"general_settings\t{SEALED}"],
        "LiteLLM_SpendLogs": ["2026-11-08\tgemini/gemini-2.5-flash\t1"],
    })  # fmt: skip

    def run(command: list[str], **_kw: object) -> str:
        if "--roles-only" in command:
            return "CREATE ROLE litellm;\n"
        if "-Atc" in command:
            return "litellm\nospreyflow\n"
        if command[-1] == "litellm":
            return gateway(command)  # type: ignore[operator]
        return "-- dump of ospreyflow\nCREATE TABLE t (i int);\n"

    monkeypatch.setattr(backup, "_run", run)
    written = backup.backup_postgres_all(compose, tmp_path / "set" / "postgres")
    assert "litellm.sql" in {p.name for _, p in written}
    everything = b"".join(p.read_bytes() for p in (tmp_path / "set").rglob("*") if p.is_file())
    assert PLANTED.encode() not in everything and SEALED.encode() not in everything
    # The schema is kept, and the gateway's other records (its spend log) too.
    dumped = (tmp_path / "set" / "postgres" / "litellm.sql").read_text()
    assert 'CREATE TABLE public."LiteLLM_CredentialsTable"' in dumped
    assert 'COPY public."LiteLLM_SpendLogs"' in dumped


def test_a_backup_holds_no_engine_key_of_the_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-135 Amendment 3: each engine's own gateway key is a row of `LiteLLM_VerificationToken`
    (its hash, its last four, its spend). Restored elsewhere, that row would keep the old
    deployment's engine key working there, for anyone who holds the old master key; so no backup
    holds those rows, and a restore's first start makes each engine's key afresh. A key deleted (an
    engine removed, or revoked at a reconcile after the master key changed) leaves the same hash,
    its name's last four and its metadata in `LiteLLM_DeletedVerificationToken` (measured in P3, ADR-135
    Amendment 3's "As built in P3"), which a restore has no use for, so its rows are left out too."""
    compose = _env(tmp_path / "dep", SALT_HERE)
    engine_hash = "9aed966cd5732b4d1da7a405e41fee7b74772b0f73edc0ef564ec9814571918f"
    engine_row = f"{engine_hash}\tsk-...ENG4\t12.0"
    gateway = _pg_dump_honouring_exclusions({
        "LiteLLM_VerificationToken": [engine_row],
        "LiteLLM_DeletedVerificationToken": [f"{engine_hash[::-1]}\tsk-...DEL7\t3.0"],
        "LiteLLM_SpendLogs": ["2026-11-08\tgemini/gemini-2.5-flash\t1"],
    })  # fmt: skip

    def run(command: list[str], **_kw: object) -> str:
        if "--roles-only" in command:
            return "CREATE ROLE litellm;\n"
        if "-Atc" in command:
            return "litellm\nospreyflow\n"
        if command[-1] == "litellm":
            return gateway(command)  # type: ignore[operator]
        return "-- dump of ospreyflow\nCREATE TABLE t (i int);\n"

    monkeypatch.setattr(backup, "_run", run)
    backup.backup_postgres_all(compose, tmp_path / "set" / "postgres")
    dumped = (tmp_path / "set" / "postgres" / "litellm.sql").read_text()
    assert "9aed966cd5732b4d" not in dumped and "ENG4" not in dumped
    assert engine_hash[::-1] not in dumped and "DEL7" not in dumped
    assert 'CREATE TABLE public."LiteLLM_VerificationToken"' in dumped
    assert 'CREATE TABLE public."LiteLLM_DeletedVerificationToken"' in dumped


def _set(tmp_path: Path, *, keys: list[str]) -> Path:
    directory = tmp_path / "set"
    (directory / "config").mkdir(parents=True)
    (directory / "config" / "models.yaml").write_text(
        "providers: []\ndefaults: {}\nkeys:\n"
        + "".join(f"  {k}: {{set_at: '2026-11-08T00:00:00Z', set_by: a}}\n" for k in keys)
    )
    manifest = {
        "format": 1,
        "schema_versions": schema_versions(include_weights=False),
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


def _dry_run(directory: Path, compose: Path) -> restore.DryRun:
    return restore.run_restore(
        directory=directory,
        compose_file=compose,
        database="ospreyflow",
        analytics_container_path="/data/analytics.duckdb",
        acknowledged=False,
    )


def test_a_restore_names_each_key_to_enter_again(tmp_path: Path) -> None:
    plan = _dry_run(_set(tmp_path, keys=["gemini", "openai"]), _env(tmp_path / "here", SALT_HERE))
    assert plan.keys_to_enter == ("gemini", "openai")
    said = plan.render()
    assert "enter the key of gemini, openai again" in said and "Admin › Models" in said


def test_a_restore_with_no_key_set_says_nothing_of_keys(tmp_path: Path) -> None:
    plan = _dry_run(_set(tmp_path, keys=[]), _env(tmp_path / "here", SALT_HERE))
    assert plan.keys_to_enter == () and "model keys" not in plan.render()


def test_a_stopped_conduit_s_models_file_is_still_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A quiesced backup stops the Conduit first; the models file is then read through a one-off
    container on the same volume, and a set never silently lacks it."""
    compose = _env(tmp_path / "dep", SALT_HERE)
    ran: list[list[str]] = []

    def run(command: list[str], **_kw: object) -> str:
        ran.append(command)
        if "exec" in command:
            raise backup.BackupFailed("models", "service api is not running")
        return "providers: []\nkeys:\n  gemini: {set_at: '2026-11-08T00:00:00Z', set_by: a}\n"

    monkeypatch.setattr(backup, "_run", run)
    taken = backup.backup_models_file(compose, tmp_path / "set" / "config" / "models.yaml")
    assert taken is not None and "gemini" in taken.read_text()
    assert ["run", "--rm", "--no-deps"] == ran[-1][ran[-1].index("run") : ran[-1].index("run") + 3]


def test_a_models_file_that_cannot_be_read_stops_the_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose = _env(tmp_path / "dep", SALT_HERE)

    def run(command: list[str], **_kw: object) -> str:
        raise backup.BackupFailed("models", "no such service")

    monkeypatch.setattr(backup, "_run", run)
    with pytest.raises(backup.BackupFailed):
        backup.backup_models_file(compose, tmp_path / "set" / "config" / "models.yaml")
