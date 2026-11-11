"""The backups' AWS side as P9's Terraform makes it (ADR-148 Amendment 7), on the S3 stand-in
(`tests/fixtures/cloud_platform/s3_standin.py`), which refuses what S3, STS and KMS refuse.

The role's policy and the bucket's are `harness.cloud_platform_backups`' own, the one source the
rendered `backups.tf` is written from, so a refusal here is the refusal the platform would give for
the same request.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any

import botocore.session
import pytest
from botocore.config import Config
from harness import cloud_platform_backups as backups
from services.api import platform_backup as pb

from tests.fixtures.cloud_platform.s3_standin import Role, Server, StandIn, mint_token, serve

ACCOUNT = "123456789012"
REGION = "eu-west-2"
BUCKET = "ospreyflow-dev-0a1b2c3d-backups"
KEY_ARN = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/1234abcd-12ab-34cd-56ef-1234567890ab"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-backup"
CONDUIT_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-service"
SUBJECT = "system:serviceaccount:ospreyflow-dev:ospreyflow-backup"
ISSUER_SECRET = "the-cluster-oidc-issuer"


def role_policy(*, kms_actions: tuple[str, ...] = tuple(backups.KMS_ACTIONS)) -> dict[str, Any]:
    """The backup role's own policy as `backups.tf` writes it, its KMS actions narrowed for a
    case that takes one away."""
    policy = backups.role_policy(f"arn:aws:s3:::{BUCKET}", KEY_ARN)
    statements = [s for s in policy["Statement"] if not s["Action"][0].startswith("kms:")]
    if kms_actions:
        statements.append({"Effect": "Allow", "Action": list(kms_actions), "Resource": [KEY_ARN]})
    return {**policy, "Statement": statements}


def bucket_policy() -> dict[str, Any]:
    """The backups bucket's policy as `backups.tf` writes it (TLS only; SSE-KMS by its own key
    only; its objects the backup role's alone)."""
    return backups.bucket_policy(f"arn:aws:s3:::{BUCKET}", KEY_ARN, ROLE_ARN)


def standin_config(
    *, role: dict[str, Any] | None = None, bucket: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "region": REGION,
        "roles": [
            {"arn": ROLE_ARN, "issuer_secret": ISSUER_SECRET, "subject": SUBJECT,
             "policies": [role or role_policy()]},
            # The Conduit's role holds S3 in general, and still not this bucket (its policy).
            {"arn": CONDUIT_ROLE_ARN, "issuer_secret": ISSUER_SECRET,
             "subject": "system:serviceaccount:ospreyflow-dev:ospreyflow",
             "policies": [{"Statement": [{"Effect": "Allow", "Action": ["s3:*", "kms:*"], "Resource": "*"}]}]},
        ],
        "buckets": [{"name": BUCKET, "kms_key": KEY_ARN, "policy": bucket or bucket_policy()}],
    }  # fmt: skip


@dataclass
class Running:
    stand_in: StandIn
    server: Server
    endpoint: str
    token_file: Path
    env: pytest.MonkeyPatch

    def s3(self, role: str = ROLE_ARN) -> Any:
        """A botocore S3 client as a pod with IRSA builds one: the web identity token file and the
        role, no key, every call to the stand-in."""
        return self.session(role).create_client(
            "s3", region_name=REGION, endpoint_url=self.endpoint, config=PATH_STYLE
        )

    def session(self, role: str = ROLE_ARN) -> botocore.session.Session:
        self.env.setenv("AWS_ROLE_ARN", role)
        self.env.setenv("AWS_WEB_IDENTITY_TOKEN_FILE", str(self.token_file))
        self.env.setenv("AWS_ENDPOINT_URL_STS", self.endpoint)
        return botocore.session.get_session()


PATH_STYLE = Config(s3={"addressing_style": "path"}, retries={"max_attempts": 1})


@pytest.fixture
def aws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Running]:
    """The stand-in, given the backup role and bucket, its TLS taken as the platform's
    (`secure`; the TLS-only refusal is its own case), and a token the role trusts."""
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE",
                 "AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3", "AWS_CONFIG_FILE",
                 "AWS_SHARED_CREDENTIALS_FILE"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    stand_in = StandIn.from_config(standin_config(), tmp_path / "objects")
    stand_in.secure = True
    server = serve(stand_in)
    token_file = tmp_path / "token"
    token_file.write_text(mint_token(ISSUER_SECRET, sub=SUBJECT))
    try:
        yield Running(
            stand_in, server, f"http://127.0.0.1:{server.server_address[1]}", token_file, monkeypatch
        )
    finally:
        server.shutdown()
        server.server_close()


def later(stand_in: StandIn, seconds: int) -> None:
    """The stand-in's clock moved on by `seconds`."""
    start = stand_in.clock()
    stand_in.clock = lambda: start + dt.timedelta(seconds=seconds)


# ---------------------------------------------------------------------------------------------
# The stores' fakes and the runner as the CronJob's pod builds it (test_platform_backup*.py)
# ---------------------------------------------------------------------------------------------

ZIP = b"PK\x03\x04 an ArcadeDB backup" * 1000
#: The address ClickHouse reaches S3 by on the platform: the region's own, path style.
REGIONAL = f"https://s3.{REGION}.amazonaws.com"


class FakeStores:
    """ArcadeDB's and ClickHouse's HTTP, as `Stores.http` calls them."""

    def __init__(self, aws: Running, folder: Path) -> None:
        self.aws, self.folder = aws, folder
        self.statements: list[str] = []
        self.arcadedb_answer: bytes | None = None
        self.client: Any = None
        self.access_key: str | None = None

    def _s3(self) -> Any:
        """ClickHouse's S3 client as the role, by its pod's web identity, its credentials kept
        until they expire (as ClickHouse keeps them)."""
        if self.client is None:
            frozen = self.aws.session().get_credentials().get_frozen_credentials()
            self.access_key = frozen.access_key
            self.client = botocore.session.get_session().create_client(
                "s3", region_name=REGION, endpoint_url=self.aws.endpoint, config=PATH_STYLE,
                aws_access_key_id=frozen.access_key, aws_secret_access_key=frozen.secret_key,
                aws_session_token=frozen.token)  # fmt: skip
        return self.client

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
        match = re.search(r"S3\((.*)\)", body)
        assert match, body
        arguments = re.findall(r"'((?:[^'\\]|\\.)*)'", match.group(1))
        if len(arguments) not in (1, 3):  # ClickHouse 25.8's own refusal, word for word
            text = (b"Code: 42. DB::Exception: Backup S3 requires 1 or 3 arguments: url, "
                    b"[access_key_id, secret_access_key]. (NUMBER_OF_ARGUMENTS_DOESNT_MATCH)")  # fmt: skip
            raise urllib.error.HTTPError(request.full_url, 500, "error", Message(), io.BytesIO(text))
        assert len(arguments) == 1, "the runner never hands ClickHouse a key"
        assert arguments[0].startswith(REGIONAL + "/"), arguments[0]
        bucket, _, prefix = arguments[0].removeprefix(REGIONAL + "/").partition("/")
        s3 = self._s3()
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


