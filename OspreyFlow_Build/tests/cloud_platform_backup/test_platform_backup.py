"""The backup runner (`services/api/platform_backup.py`, ADR-148 Amendment 7) against the S3
stand-in, which refuses what S3, STS and KMS refuse: a set is written only when every step was
granted, and every refusal is reported in words naming the store, the step and S3's own code.

ArcadeDB and ClickHouse are fakes here, at their HTTP call sites: ArcadeDB's writes its zip into
the mounted folder as the server does; ClickHouse's **writes to S3 itself, as the backup role, by
its own pod's web identity** (IRSA), so a refusal the stand-in gives ClickHouse is the one the real
ClickHouse meets (its own error quoting the statement back, as ClickHouse's errors do).

The fake refuses what ClickHouse 25.8 refuses (rule 15's second example): `S3()` in `BACKUP` takes
one argument or three, never a session token, which the real server answered with Code 42 on
osprey-p9, 11 November 2026, after a fake that took four had passed every case here. The real
servers are the kind run's (`process/lanes/case/gates/p9_kind.sh`).
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from harness import cloud_platform_backups as backups
from services.api import platform_backup as pb

from tests.cloud_platform_backup.conftest import (
    BUCKET,
    CLICKHOUSE_ROLE_ARN,
    ISSUER,
    KEY_ARN,
    PROVIDER,
    REGION,
    REGIONAL,
    ROLE_ARN,
    ZIP,
    Running,
    _deny_kms,
    _objects,
)


def test_a_backup_writes_a_set_encrypted_by_the_deployments_key_its_manifest_last(aws: Running, run: Any) -> None:
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    prefix = f"sets/{manifest['set']}/"
    keys = _objects(aws)
    assert f"{prefix}arcadedb/ospreyflow.zip" in keys
    assert f"{prefix}clickhouse/.backup" in keys
    assert f"{prefix}manifest.json" in keys
    for key in keys:
        assert aws.stand_in.meta(BUCKET, key)["kms_key"] == KEY_ARN, key
    assert manifest["arcadedb"]["bytes"] == len(ZIP)
    assert aws.stand_in.read(BUCKET, f"{prefix}arcadedb/ospreyflow.zip") == ZIP
    # ArcadeDB asked by its pod's own name, never the Service; the zip gone from the claim.
    assert not list((settings.arcadedb_folder / "ospreyflow").iterdir())
    # One argument, the regional address: ClickHouse writes as the role by its own pod's identity,
    # and no key or token is ever in the statement (or ClickHouse's query log).
    assert fake.statements[0] == f"BACKUP DATABASE ospreyflow TO S3('{REGIONAL}/{BUCKET}/{prefix}clickhouse/')"
    assert [s.set_id for s in pb.sets(bucket)] == [manifest["set"]]


def test_without_the_kms_permission_the_backup_is_refused_in_words_and_no_set_is_finished(
    aws: Running, run: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    settings, bucket, stores, _ = run
    _deny_kms(aws, "kms:Decrypt")
    with pytest.raises(pb.BackupRefused) as refused:
        pb.take(settings, pb.Bucket(settings), stores)
    assert refused.value.store == "arcadedb"
    assert "AccessDenied" in refused.value.reason and "kms:GenerateDataKey" in refused.value.reason
    assert KEY_ARN in refused.value.reason
    assert not any(k.endswith("manifest.json") for k in _objects(aws))
    assert not list((settings.arcadedb_folder / "ospreyflow").iterdir()), "the zip is never left on the claim"


def test_clickhouse_refused_by_kms_leaves_the_set_unfinished_and_says_so(aws: Running, run: Any) -> None:
    """ClickHouse writes by its own role and the bucket's default key: its role without
    kms:GenerateDataKey refuses it there, after ArcadeDB's part was written by the runner's."""
    settings, bucket, stores, _ = run
    _deny_kms(aws, "kms:Decrypt", role=CLICKHOUSE_ROLE_ARN)
    with pytest.raises(pb.BackupRefused) as refused:
        pb.take(settings, bucket, stores)
    assert refused.value.store == "clickhouse"
    assert "kms:GenerateDataKey" in refused.value.reason
    assert [s.complete for s in pb.sets(bucket)] == [False]


def test_clickhouse_renews_an_expired_session_and_the_set_is_written(aws: Running, run: Any) -> None:
    """Measured on osprey-p9: with every session ended, ClickHouse takes a new one by its pod's
    identity (as the runner does), and the set is written."""
    settings, bucket, stores, fake = run
    pb.take(settings, bucket, stores, now=dt.datetime(2026, 11, 11, 2, 15, tzinfo=dt.UTC))
    first_key = fake.access_key
    aws.stand_in.expire()
    renewed = pb.Bucket(settings)  # the runner's next pod: a new session of its own
    second = pb.take(settings, renewed, stores, now=dt.datetime(2026, 11, 12, 2, 15, tzinfo=dt.UTC))
    assert fake.access_key not in (None, first_key), "a new session, not the expired one"
    assert [s.set_id for s in pb.sets(renewed) if s.complete][-1] == second["set"]


def test_clickhouse_refused_a_new_session_is_refused_and_never_writes_anonymously(aws: Running, run: Any) -> None:
    """A role that cannot be renewed (its trust another account's): STS refuses ClickHouse, which then
    has no credentials and writes unsigned, refused (as measured on kind), and the set is unfinished."""
    settings, bucket, stores, fake = run
    role = aws.stand_in.roles[CLICKHOUSE_ROLE_ARN]
    role.trust = backups.trust_policy(PROVIDER, ISSUER, "system:serviceaccount:ospreyflow-dev:another-account")
    with pytest.raises(pb.BackupRefused) as refused:
        pb.take(settings, bucket, stores)
    assert refused.value.store == "clickhouse" and "AccessDenied" in refused.value.reason
    assert fake.access_key is None, "no session was granted"
    assert ("AccessDenied", "Not authorized to perform sts:AssumeRoleWithWebIdentity") in aws.stand_in.refusals
    assert not [s for s in pb.sets(bucket) if s.complete]


def test_a_statement_handing_clickhouse_a_session_is_refused_as_clickhouse_refuses_it(run: Any) -> None:
    """The fake's own refusal, red at the shape the code once sent (url, key, secret, token)."""
    settings, _, stores, _ = run
    with pytest.raises(pb.BackupRefused) as refused:
        stores.clickhouse(
            f"BACKUP DATABASE ospreyflow TO S3('{REGIONAL}/{BUCKET}/x/', 'ASIA', 'secret', 'token')",
            "BACKUP … TO S3",
        )
    assert "NUMBER_OF_ARGUMENTS_DOESNT_MATCH" in refused.value.reason


def test_a_bucket_policy_refusing_the_role_refuses_the_backup(aws: Running, run: Any) -> None:
    """A bucket policy that names another role (a wrong one in the Terraform) refuses every write."""
    settings, bucket, stores, _ = run
    policy = aws.stand_in.buckets[BUCKET].policy
    assert policy is not None
    policy["Statement"][-1]["Condition"]["ArnNotEquals"]["aws:PrincipalArn"] = [ROLE_ARN + "-other"]
    with pytest.raises(pb.BackupRefused) as refused:
        pb.take(settings, bucket, stores)
    assert refused.value.store == "arcadedb" and "AccessDenied" in refused.value.reason
    assert "AccessDenied" in refused.value.reason


def test_main_exits_non_zero_and_says_why(aws: Running, run: Any, monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    settings, _, _, fake = run
    _deny_kms(aws, "kms:Decrypt")
    monkeypatch.setattr(pb, "Settings", type("S", (), {"from_env": staticmethod(lambda: settings)}))
    real_stores = pb.Stores
    monkeypatch.setattr(pb, "Stores", lambda s: real_stores(s, http=fake))
    assert pb.main(["backup"]) == 1
    said = capsys.readouterr().err
    assert said.startswith("backup refused: arcadedb: upload to s3://")
    assert "kms:GenerateDataKey" in said


def test_arcadedb_reporting_no_file_is_refused_in_words(run: Any) -> None:
    settings, bucket, stores, fake = run
    fake.arcadedb_answer = b'{"result": []}'
    with pytest.raises(pb.BackupRefused, match="no backup file reported"):
        pb.take(settings, bucket, stores)
    fake.arcadedb_answer = b'{"result": [{"backupFile": "elsewhere.zip"}]}'
    with pytest.raises(pb.BackupRefused, match="is not in the mounted backups folder"):
        pb.take(settings, bucket, stores)
    fake.arcadedb_answer = b'{"result": [{"backupFile": "../../etc/passwd"}]}'
    with pytest.raises(pb.BackupRefused, match="an unexpected backup file name"):
        pb.take(settings, bucket, stores)


def test_the_settings_missing_are_named() -> None:
    with pytest.raises(pb.BackupRefused, match="OSPREY_BACKUP_BUCKET, OSPREY_BACKUP_KMS_KEY"):
        pb.Settings.from_env({"AWS_REGION": REGION})


def test_the_newest_finished_set_is_the_latest_and_an_unfinished_one_never_is(aws: Running, run: Any) -> None:
    _, bucket, _, _ = run
    for set_id, finished in [("20261101T020000Z", True), ("20261102T020000Z", False),
                             ("20261103T020000Z", True), ("20261104T020000Z", False)]:  # fmt: skip
        bucket.put_bytes(f"sets/{set_id}/arcadedb/ospreyflow.zip", b"z")
        if finished:
            bucket.put_bytes(f"sets/{set_id}/manifest.json", b"{}")
    assert [s.complete for s in pb.sets(bucket)] == [True, False, True, False]
    assert pb.latest(bucket) == "20261103T020000Z"


def test_a_restore_fetches_the_zip_checked_and_restores_clickhouse_from_the_set(aws: Running, run: Any, tmp_path: Path) -> None:
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    path = pb.fetch_graph(bucket, pb.latest(bucket), tmp_path / "restore")
    assert path.read_bytes() == ZIP
    sent = len(fake.statements)
    pb.restore_analytics(settings, bucket, stores, manifest["set"])
    stamp = manifest["set"].lower()
    restoring, before = f"ospreyflow_restoring_{stamp}", f"ospreyflow_before_{stamp}"
    # Restored beside the live database, then swapped, and the old dropped only after.
    assert fake.statements[sent:] == [
        f"DROP DATABASE IF EXISTS {restoring} SYNC",
        f"CREATE DATABASE {restoring}",
        f"RESTORE DATABASE ospreyflow AS {restoring} FROM S3('{REGIONAL}/{BUCKET}/sets/{manifest['set']}/clickhouse/') "
        "SETTINGS allow_different_database_def = true",
        f"RENAME DATABASE ospreyflow TO {before}",
        f"RENAME DATABASE {restoring} TO ospreyflow",
        f"DROP DATABASE IF EXISTS {before} SYNC",
    ]


def test_clickhouse_refused_its_restore_leaves_the_live_database_as_it_was(aws: Running, run: Any) -> None:
    """The orchestrator's ruling 5: ClickHouse's role refused the set's key (kms:Decrypt), the live
    database is never renamed or dropped; the half-restored one is removed."""
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    _deny_kms(aws, "kms:GenerateDataKey", role=CLICKHOUSE_ROLE_ARN)
    sent = len(fake.statements)
    with pytest.raises(pb.BackupRefused) as refused:
        pb.restore_analytics(settings, bucket, stores, manifest["set"])
    assert refused.value.step == "RESTORE … FROM S3" and "kms:Decrypt" in refused.value.reason
    after = fake.statements[sent:]
    assert not [s for s in after if s.startswith("RENAME") or s == "DROP DATABASE IF EXISTS ospreyflow SYNC"]
    assert after[-1].startswith("DROP DATABASE IF EXISTS ospreyflow_restoring_"), "the half removed"


def test_a_zip_that_does_not_match_its_manifest_is_never_restored(aws: Running, run: Any, tmp_path: Path) -> None:
    settings, bucket, stores, _ = run
    manifest = pb.take(settings, bucket, stores)
    aws.stand_in.put(BUCKET, manifest["arcadedb"]["key"], b"another zip", KEY_ARN)
    with pytest.raises(pb.BackupRefused, match="the manifest says"):
        pb.fetch_graph(bucket, manifest["set"], tmp_path / "restore")
    assert not (tmp_path / "restore" / "ospreyflow.zip").exists()


def test_an_unfinished_set_is_never_restored(aws: Running, run: Any, tmp_path: Path) -> None:
    _, bucket, _, _ = run
    bucket.put_bytes("sets/20261101T020000Z/arcadedb/ospreyflow.zip", ZIP)
    with pytest.raises(pb.BackupRefused, match="no finished set by that name"):
        pb.fetch_graph(bucket, "20261101T020000Z", tmp_path)
    with pytest.raises(pb.BackupRefused, match="no finished set"):
        pb.latest(bucket)


def test_a_restore_without_kms_decrypt_is_refused_naming_it(aws: Running, run: Any, tmp_path: Path) -> None:
    settings, bucket, stores, _ = run
    manifest = pb.take(settings, bucket, stores)
    _deny_kms(aws, "kms:GenerateDataKey")
    with pytest.raises(pb.BackupRefused) as refused:
        pb.fetch_graph(pb.Bucket(settings), manifest["set"], tmp_path / "restore")
    assert "kms:Decrypt" in refused.value.reason


def test_a_large_zip_goes_up_in_parts(aws: Running, run: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _, bucket, _, _ = run
    monkeypatch.setattr(pb, "PART_SIZE", 5 * 1024 * 1024)
    big = tmp_path / "big.zip"
    big.write_bytes(b"a" * (5 * 1024 * 1024) + b"b" * 7)
    size, _ = bucket.put_file("sets/x/arcadedb/big.zip", big)
    assert size == big.stat().st_size
    assert aws.stand_in.read(BUCKET, "sets/x/arcadedb/big.zip") == big.read_bytes()


def test_a_refused_part_aborts_the_upload(aws: Running, run: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings, _, _, _ = run
    monkeypatch.setattr(pb, "PART_SIZE", 5 * 1024 * 1024)
    big = tmp_path / "big.zip"
    big.write_bytes(b"a" * (5 * 1024 * 1024) + b"b")
    _deny_kms(aws, "kms:GenerateDataKey")  # parts written; completion needs kms:Decrypt
    with pytest.raises(Exception, match="kms:Decrypt"):
        pb.Bucket(settings).put_file("sets/x/arcadedb/big.zip", big)
    assert aws.stand_in.uploads == {}


# ---- the restore verifies before it destroys (the orchestrator's ruling 3) ----------------------


def test_a_missing_clickhouse_part_leaves_arcadedb_and_clickhouse_untouched(
    aws: Running, run: Any, tmp_path: Path
) -> None:
    """Every part is checked before anything is replaced: with ClickHouse's `.backup` gone (expired,
    say), the graph is not fetched, nothing is dropped, and each step says which part and why."""
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    aws.stand_in.delete(BUCKET, f"{manifest['clickhouse']['prefix']}.backup")
    sent = len(fake.statements)
    for step in (lambda: pb.verify_set(bucket, manifest["set"]),
                 lambda: pb.restore_analytics(settings, bucket, stores, manifest["set"])):  # fmt: skip
        with pytest.raises(pb.BackupRefused) as refused:
            step()
        assert "ClickHouse's" in refused.value.reason and ".backup is missing" in refused.value.reason
        assert "nothing was touched" in refused.value.reason
    assert fake.statements[sent:] == [], "no DROP, no RESTORE sent to ClickHouse"
    assert not (tmp_path / "restore").exists()


def test_a_changed_clickhouse_file_is_never_restored(aws: Running, run: Any) -> None:
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    aws.stand_in.put(BUCKET, f"{manifest['clickhouse']['prefix']}.backup", b"<another/>", KEY_ARN)
    sent = len(fake.statements)
    with pytest.raises(pb.BackupRefused, match="is not the file the set wrote"):
        pb.restore_analytics(settings, bucket, stores, manifest["set"])
    assert fake.statements[sent:] == []


def test_the_manifest_records_clickhouses_part_by_file(run: Any) -> None:
    settings, bucket, stores, _ = run
    manifest = pb.take(settings, bucket, stores)
    files = {f["key"].rsplit("/clickhouse/", 1)[1]: f for f in manifest["clickhouse"]["files"]}
    assert set(files) == {".backup", "data/ospreyflow/events/all_1_1_0/data.bin"}, "the lock is gone by then"
    assert all(f["bytes"] > 0 and f["etag"] for f in files.values())


def test_a_finished_slot_is_never_taken_again(run: Any) -> None:
    """A Job of a slot run again (its retry, or by hand) never writes over a finished set."""
    settings, bucket, stores, _ = run
    when = dt.datetime(2026, 11, 11, 2, 15, tzinfo=dt.UTC)
    pb.take(settings, bucket, stores, now=when)
    with pytest.raises(pb.BackupRefused, match="already finished"):
        pb.take(settings, bucket, stores, now=when)


# ---- the restore refuses while writers run (the orchestrator's ruling 4) ------------------------


def _pod(name: str, phase: str) -> dict[str, Any]:
    return {"metadata": {"name": name}, "status": {"phase": phase}}


@pytest.mark.parametrize("phase", ["Running", "Pending"])
def test_a_restore_refuses_while_a_writer_runs_and_touches_nothing(run: Any, phase: str) -> None:
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    guarded = pb.Settings(**{**settings.__dict__, "writers": ("arcadedb", "api", "worker", "report-sync")})
    asked: list[str] = []

    def pods(selector: str) -> list[dict[str, Any]]:
        asked.append(selector)
        return [_pod("api-7d9c-xk2", phase), _pod("arcadedb-0", "Succeeded")]

    sent = len(fake.statements)
    with pytest.raises(pb.BackupRefused) as refused:
        pb.restore_analytics(guarded, bucket, stores, manifest["set"], pods=pods)
    assert "api-7d9c-xk2 still running" in refused.value.reason and "arcadedb-0" not in refused.value.reason
    assert asked == ["app.kubernetes.io/name in (arcadedb,api,worker,report-sync)"]
    assert fake.statements[sent:] == []


def test_a_restore_goes_on_once_the_writers_are_stopped(run: Any) -> None:
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    guarded = pb.Settings(**{**settings.__dict__, "writers": ("arcadedb", "api")})
    pb.restore_analytics(guarded, bucket, stores, manifest["set"], pods=lambda _: [_pod("api-1", "Succeeded")])
    assert any(s.startswith("RESTORE DATABASE") for s in fake.statements)
    assert fake.statements[-1].startswith("DROP DATABASE IF EXISTS ospreyflow_before_")


def test_pods_it_cannot_list_refuse_the_restore(run: Any) -> None:
    settings, bucket, stores, _ = run
    guarded = pb.Settings(**{**settings.__dict__, "writers": ("api",)})

    def refused(_: str) -> list[dict[str, Any]]:
        raise urllib.error.URLError("forbidden")

    with pytest.raises(pb.BackupRefused, match="cannot confirm the writers are stopped") as said:
        pb.writers_stopped(guarded, refused)
    assert "nothing was touched" in said.value.reason


def test_a_restore_whose_writers_cannot_be_seen_touches_nothing(run: Any) -> None:
    """Fails closed (the orchestrator's ruling): the API unreachable, the restore refuses in words and
    sends ClickHouse nothing."""
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    guarded = pb.Settings(**{**settings.__dict__, "writers": ("api",)})

    def unreachable(_: str) -> list[dict[str, Any]]:
        raise urllib.error.URLError("timed out")

    sent = len(fake.statements)
    with pytest.raises(pb.BackupRefused, match="cannot confirm the writers are stopped"):
        pb.restore_analytics(guarded, bucket, stores, manifest["set"], pods=unreachable)
    assert fake.statements[sent:] == []


def test_an_sts_refusal_is_named_as_sts_s() -> None:
    from botocore.exceptions import ClientError

    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "Not authorized"}}, "AssumeRoleWithWebIdentity")
    assert pb._said(error) == "STS refused it (AccessDenied: Not authorized)"
    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "PutObject")
    assert pb._said(error).startswith("S3 refused it")


# ---- round 3: the manifest is its own set's; no writers named refuses; main fails closed --------


def _rewrite_manifest(aws: Running, set_id: str, change: Any) -> None:
    key = f"sets/{set_id}/manifest.json"
    manifest = json.loads(aws.stand_in.read(BUCKET, key))
    change(manifest)
    aws.stand_in.put(BUCKET, key, json.dumps(manifest).encode(), KEY_ARN)


def test_a_manifest_that_is_another_sets_is_refused(aws: Running, run: Any) -> None:
    settings, bucket, stores, _ = run
    manifest = pb.take(settings, bucket, stores)
    _rewrite_manifest(aws, manifest["set"], lambda m: m.update(set="20201231T000000Z"))
    with pytest.raises(pb.BackupRefused, match="its manifest is set '20201231T000000Z'"):
        pb.verify_set(bucket, manifest["set"])


def test_a_manifest_naming_another_sets_objects_is_refused(aws: Running, run: Any) -> None:
    settings, bucket, stores, _ = run
    manifest = pb.take(settings, bucket, stores)
    _rewrite_manifest(aws, manifest["set"],
                      lambda m: m["arcadedb"].update(key="sets/20201231T000000Z/arcadedb/ospreyflow.zip"))  # fmt: skip
    with pytest.raises(pb.BackupRefused, match="outside the set"):
        pb.verify_set(bucket, manifest["set"])


def test_a_set_without_the_deployments_claims_is_refused(run: Any) -> None:
    """The stores' Job refuses a set taken without the claims part the deployment has."""
    settings, bucket, stores, _ = run
    manifest = pb.take(settings, bucket, stores)
    with pytest.raises(pb.BackupRefused, match="no part for the claim ingest"):
        pb.verify_set(bucket, manifest["set"], claims=("ingest",))


def test_no_writers_named_refuses_the_restore(run: Any) -> None:
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    unnamed = pb.Settings(**{**settings.__dict__, "writers": ()})
    sent = len(fake.statements)
    with pytest.raises(pb.BackupRefused, match="cannot confirm the writers are stopped: none are named"):
        pb.restore_analytics(unnamed, bucket, stores, manifest["set"])
    assert fake.statements[sent:] == []


@pytest.mark.parametrize("command", ["verify", "restore-claims"])
def test_mains_restore_steps_fail_closed_when_the_pods_cannot_be_listed(
    aws: Running, run: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    tmp_path: Path, command: str,
) -> None:  # fmt: skip
    """The Jobs' own entry points: `verify` (the stores' and the claims' first step) and
    `restore-claims` refuse in words when the API cannot be asked, before reading anything."""
    settings, bucket, stores, _ = run
    manifest = pb.take(settings, bucket, stores)
    claims = tmp_path / "claims" / "ingest"
    claims.mkdir(parents=True)
    (claims / "kept.txt").write_text("untouched")
    for name, value in {"OSPREY_BACKUP_BUCKET": BUCKET, "OSPREY_BACKUP_KMS_KEY": KEY_ARN, "AWS_REGION": REGION,
                        "AWS_ENDPOINT_URL_S3": aws.endpoint, "OSPREY_BACKUP_WRITERS": "arcadedb,api",
                        "OSPREY_BACKUP_CLAIMS_FOLDER": str(tmp_path / "claims")}.items():  # fmt: skip
        monkeypatch.setenv(name, value)

    def unreachable(_: str) -> list[dict[str, Any]]:
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(pb, "_pods", unreachable)
    assert pb.main([command, "--set", manifest["set"]]) == 1
    assert "cannot confirm the writers are stopped" in capsys.readouterr().err
    assert (claims / "kept.txt").read_text() == "untouched"
