"""The backup runner (`services/api/platform_backup.py`, ADR-148 Amendment 7) against the S3
stand-in, which refuses what S3, STS and KMS refuse: a set is written only when every step was
granted, and every refusal is reported in words naming the store, the step and S3's own code.

ArcadeDB and ClickHouse are fakes here, at their HTTP call sites: ArcadeDB's writes its zip into
the mounted folder as the server does; ClickHouse's **writes to S3 itself with the credentials the
statement hands it**, so a refusal the stand-in gives ClickHouse is the one the real ClickHouse
meets (its own error quoting the statement back, as ClickHouse's errors do). The real servers are
`test_platform_backup_live.py`'s.
"""

from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import botocore.session
import pytest

from services.api import platform_backup as pb
from tests.cloud_platform_backup.conftest import (
    BUCKET,
    KEY_ARN,
    PATH_STYLE,
    REGION,
    ROLE_ARN,
    Running,
    role_policy,
)
from tests.fixtures.cloud_platform.s3_standin import Role

ZIP = b"PK\x03\x04 an ArcadeDB backup" * 1000


class FakeStores:
    """ArcadeDB's and ClickHouse's HTTP, as `Stores.http` calls them."""

    def __init__(self, aws: Running, folder: Path) -> None:
        self.aws, self.folder = aws, folder
        self.statements: list[str] = []
        self.arcadedb_answer: bytes | None = None

    def __call__(self, request: urllib.request.Request, timeout: float) -> bytes:
        url = request.full_url
        body = (request.data or b"").decode()  # type: ignore[union-attr]
        if "/api/v1/command/" in url:
            assert json.loads(body) == {"language": "sql", "command": "BACKUP DATABASE"}
            if self.arcadedb_answer is not None:
                return self.arcadedb_answer
            database = url.rsplit("/", 1)[1]
            name = f"{database}-backup-20261111-020000.zip"
            (self.folder / database).mkdir(parents=True, exist_ok=True)
            (self.folder / database / name).write_bytes(ZIP)
            return json.dumps({"result": [{"operation": "backup database", "backupFile": name}]}).encode()
        self.statements.append(body)
        if body.startswith("DROP DATABASE"):
            return b""
        match = re.search(r"S3\('([^']*)', '([^']*)', '([^']*)'(?:, '([^']*)')?\)", body)
        assert match, body
        prefix_url, key, secret, token = match.groups()
        s3 = botocore.session.get_session().create_client(
            "s3", region_name=REGION, endpoint_url=self.aws.endpoint, config=PATH_STYLE,
            aws_access_key_id=key, aws_secret_access_key=secret, aws_session_token=token)  # fmt: skip
        bucket_and_prefix = prefix_url.split(self.aws.endpoint + "/", 1)[1]
        bucket, _, prefix = bucket_and_prefix.partition("/")
        try:
            if body.startswith("BACKUP"):
                # ClickHouse sends no encryption header: the bucket's default (its key) applies.
                s3.put_object(Bucket=bucket, Key=prefix + ".backup", Body=b"<config/>")
                s3.put_object(Bucket=bucket, Key=prefix + "data/ospreyflow/events/all_1_1_0/data.bin", Body=b"rows")
                return b"0b1d-backup-id\tBACKUP_CREATED\n"
            s3.get_object(Bucket=bucket, Key=prefix + ".backup")["Body"].read()
            return b"0b1d-restore-id\tRESTORED\n"
        except Exception as error:  # what ClickHouse says: its code, S3's words, the query
            said = getattr(error, "response", {}).get("Error", {})
            text = (f"Code: 499. DB::Exception: {said.get('Code')}: {said.get('Message')}. "
                    f"(S3_ERROR) (query: {body})").encode()  # fmt: skip
            raise urllib.error.HTTPError(request.full_url, 500, "error", Message(), io.BytesIO(text)) from None


@pytest.fixture
def run(aws: Running, tmp_path: Path) -> tuple[pb.Settings, pb.Bucket, pb.Stores, FakeStores]:
    folder = tmp_path / "arcadedb-backups"
    folder.mkdir()
    settings = pb.Settings.from_env({
        "OSPREY_BACKUP_BUCKET": BUCKET, "OSPREY_BACKUP_KMS_KEY": KEY_ARN, "AWS_REGION": REGION,
        "AWS_ENDPOINT_URL_S3": aws.endpoint, "OSPREY_BACKUP_ARCADEDB_FOLDER": str(folder),
        "OSPREY_BACKUP_ARCADEDB_HOST": "arcadedb-0.arcadedb-headless",
        "ARCADEDB_ROOT_PASSWORD": "pw", "CLICKHOUSE_USER": "osprey", "CLICKHOUSE_PASSWORD": "pw",
        "OSPREY_BACKUP_KEEP": "2",
    })  # fmt: skip
    aws.session()  # the pod's IRSA environment
    fake = FakeStores(aws, folder)
    return settings, pb.Bucket(settings), pb.Stores(settings, http=fake), fake


def _objects(aws: Running) -> list[str]:
    return [m["key"] for m in aws.stand_in.listing(BUCKET)]


def _deny_kms(aws: Running, *kept: str) -> None:
    role = aws.stand_in.roles[ROLE_ARN]
    aws.stand_in.roles[ROLE_ARN] = Role(arn=role.arn, policies=[role_policy(kms_actions=kept)],
                                        issuer_secret=role.issuer_secret, subject=role.subject)  # fmt: skip
    aws.stand_in.sessions.clear()


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
    assert fake.statements[0].startswith(f"BACKUP DATABASE ospreyflow TO S3('{aws.endpoint}/{BUCKET}/{prefix}clickhouse/'")
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
    """ArcadeDB's upload names its key (granted); ClickHouse relies on the bucket's default, and
    the same missing permission refuses it there."""
    settings, bucket, stores, _ = run
    original = bucket.put_file

    def then_deny(key: str, path: Path) -> tuple[int, str]:
        done = original(key, path)
        _deny_kms(aws, "kms:Decrypt")
        return done

    bucket.put_file = then_deny  # type: ignore[method-assign]
    bucket_session = pb.Bucket(settings)
    bucket.session = bucket_session.session
    with pytest.raises(pb.BackupRefused) as refused:
        pb.take(settings, bucket, stores)
    assert refused.value.store == "clickhouse"
    assert "kms:GenerateDataKey" in refused.value.reason
    assert [s.complete for s in pb.sets(bucket_session)] == [False]


def test_an_expired_role_refuses_clickhouses_backup_and_the_secret_is_never_said(aws: Running, run: Any) -> None:
    settings, bucket, stores, _ = run
    secret = bucket.credentials()[1]
    original = stores.clickhouse_backup

    def after_an_hour(url: str, credentials: tuple[str, str, str | None]) -> str:
        aws.stand_in.expire()
        return original(url, credentials)

    stores.clickhouse_backup = after_an_hour  # type: ignore[method-assign]
    with pytest.raises(pb.BackupRefused) as refused:
        pb.take(settings, bucket, stores)
    assert refused.value.store == "clickhouse"
    assert "ExpiredToken" in refused.value.reason
    assert secret not in str(refused.value)
    assert "[the role's secret]" in str(refused.value)


def test_a_bucket_policy_refusing_the_role_refuses_the_backup(aws: Running, run: Any) -> None:
    """A bucket policy that names another role (a wrong one in the Terraform) refuses every write."""
    settings, bucket, stores, _ = run
    policy = aws.stand_in.buckets[BUCKET].policy
    assert policy is not None
    policy["Statement"][-1]["Condition"]["ArnNotEquals"]["aws:PrincipalArn"] = ROLE_ARN + "-other"
    with pytest.raises(pb.BackupRefused) as refused:
        pb.take(settings, bucket, stores)
    assert refused.value.store == "arcadedb"
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


def test_pruning_keeps_the_newest_finished_sets_and_never_the_last(aws: Running, run: Any) -> None:
    _, bucket, _, _ = run
    for set_id, finished in [("20261101T020000Z", True), ("20261102T020000Z", False),
                             ("20261103T020000Z", True), ("20261104T020000Z", True),
                             ("20261105T020000Z", False)]:  # fmt: skip
        bucket.put_bytes(f"sets/{set_id}/arcadedb/ospreyflow.zip", b"z")
        if finished:
            bucket.put_bytes(f"sets/{set_id}/manifest.json", b"{}")
    assert pb.prune(bucket, keep=2) == ["20261101T020000Z", "20261102T020000Z"]
    # The one still running (unfinished, newest) is never removed.
    assert [s.set_id for s in pb.sets(bucket)] == ["20261103T020000Z", "20261104T020000Z", "20261105T020000Z"]
    assert pb.prune(bucket, keep=0) == ["20261103T020000Z"]
    assert pb.latest(bucket) == "20261104T020000Z"


def test_a_restore_fetches_the_zip_checked_and_restores_clickhouse_from_the_set(aws: Running, run: Any, tmp_path: Path) -> None:
    settings, bucket, stores, fake = run
    manifest = pb.take(settings, bucket, stores)
    path = pb.fetch_graph(bucket, pb.latest(bucket), tmp_path / "restore")
    assert path.read_bytes() == ZIP
    pb.restore_analytics(settings, bucket, stores, manifest["set"])
    assert fake.statements[-2] == "DROP DATABASE IF EXISTS ospreyflow SYNC"
    assert fake.statements[-1].startswith(
        f"RESTORE DATABASE ospreyflow FROM S3('{aws.endpoint}/{BUCKET}/sets/{manifest['set']}/clickhouse/'")


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
