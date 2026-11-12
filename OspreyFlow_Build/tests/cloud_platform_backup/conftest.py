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
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
from harness import cloud_platform_backups as backups
from services.api import platform_backup as pb

from tests.fixtures.cloud_platform.s3_standin import TEST_ISSUER, Role, Server, StandIn, mint_token, serve

ACCOUNT = "123456789012"
REGION = "eu-west-2"
BUCKET = "ospreyflow-dev-0a1b2c3d-backups"
KEY_ARN = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/1234abcd-12ab-34cd-56ef-1234567890ab"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-backup"
CLICKHOUSE_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-backup-clickhouse"
CONDUIT_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-service"
SUBJECT = f"system:serviceaccount:ospreyflow-dev:{backups.SERVICE_ACCOUNT}"
CLICKHOUSE_SUBJECT = f"system:serviceaccount:ospreyflow-dev:{backups.CLICKHOUSE_SERVICE_ACCOUNT}"
ISSUER_SECRET = "the-cluster-oidc-issuer"
#: The cluster's OIDC issuer as IAM names it (no scheme), and its provider.
ISSUER = TEST_ISSUER.removeprefix("https://")
PROVIDER = f"arn:aws:iam::{ACCOUNT}:oidc-provider/{ISSUER}"
BUCKET_ARN = f"arn:aws:s3:::{BUCKET}"


def role_policy(
    account: str = backups.SERVICE_ACCOUNT, *, kms_actions: tuple[str, ...] = tuple(backups.KMS_ACTIONS)
) -> dict[str, Any]:
    """A backup role's own policy as `backups.tf` writes it, its KMS actions narrowed for a case
    that takes one away (the condition kept)."""
    policy = backups.role_policies(BUCKET_ARN, KEY_ARN, REGION)[account]
    statements = [s for s in policy["Statement"] if not s["Action"][0].startswith("kms:")]
    if kms_actions:
        kms = next(s for s in policy["Statement"] if s["Action"][0].startswith("kms:"))
        statements.append({**kms, "Action": list(kms_actions)})
    return {**policy, "Statement": statements}


def bucket_policy() -> dict[str, Any]:
    """The backups bucket's policy as `backups.tf` writes it (TLS only; SSE-KMS by its own key
    only; its objects the backup roles' alone)."""
    return backups.bucket_policy(BUCKET_ARN, KEY_ARN, [ROLE_ARN, CLICKHOUSE_ROLE_ARN])


def standin_config(
    *, role: dict[str, Any] | None = None, bucket: dict[str, Any] | None = None,
    clickhouse_role: dict[str, Any] | None = None, key_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The stand-in as the namespace's Terraform makes the AWS side: each role trusted by its own
    trust document as rendered (`backups.trust_policy`), given its own policy."""
    def trusted(subject: str) -> dict[str, Any]:
        return backups.trust_policy(PROVIDER, ISSUER, subject)

    return {
        "region": REGION,
        "roles": [
            {"arn": ROLE_ARN, "issuer_secret": ISSUER_SECRET, "subject": SUBJECT, "trust": trusted(SUBJECT),
             "policies": [role or role_policy()]},
            {"arn": CLICKHOUSE_ROLE_ARN, "issuer_secret": ISSUER_SECRET, "subject": CLICKHOUSE_SUBJECT,
             "trust": trusted(CLICKHOUSE_SUBJECT),
             "policies": [clickhouse_role or role_policy(backups.CLICKHOUSE_SERVICE_ACCOUNT)]},
            # The Conduit's role holds S3 in general, and still not this bucket (its policy).
            {"arn": CONDUIT_ROLE_ARN, "issuer_secret": ISSUER_SECRET,
             "subject": "system:serviceaccount:ospreyflow-dev:ospreyflow",
             "policies": [{"Statement": [{"Effect": "Allow", "Action": ["s3:*", "kms:*"], "Resource": "*"}]}]},
        ],
        "buckets": [{"name": BUCKET, "kms_key": KEY_ARN, "policy": bucket or bucket_policy()}],
        # The key's own policy as backups.tf writes it.
        "keys": [{"arn": KEY_ARN, "policy": key_policy or backups.key_policy(
            f"arn:aws:iam::{ACCOUNT}:root", [ROLE_ARN, CLICKHOUSE_ROLE_ARN], REGION)}],
    }  # fmt: skip


@dataclass
class Running:
    stand_in: StandIn
    server: Server
    endpoint: str
    token_file: Path
    env: pytest.MonkeyPatch
    #: A token a refusal case plants in place of the one the role's service account would hold.
    token: str | None = None

    def s3(self, role: str = ROLE_ARN) -> Any:
        """A botocore S3 client as a pod with IRSA builds one: the web identity token file and the
        role, no key, every call to the stand-in."""
        return self.session(role).create_client(
            "s3", region_name=REGION, endpoint_url=self.endpoint, config=PATH_STYLE
        )

    def session(self, role: str = ROLE_ARN) -> botocore.session.Session:
        """The pod's IRSA environment for `role`: its service account's own token."""
        subject = {ROLE_ARN: SUBJECT, CLICKHOUSE_ROLE_ARN: CLICKHOUSE_SUBJECT}.get(role, SUBJECT)
        token_file = self.token_file.with_name(f"token-{subject.rsplit(':', 1)[1]}")
        token_file.write_text(self.token or mint_token(ISSUER_SECRET, sub=subject))
        self.env.setenv("AWS_ROLE_ARN", role)
        self.env.setenv("AWS_WEB_IDENTITY_TOKEN_FILE", str(token_file))
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


def _backup_user_grants() -> list[str]:
    """The database patterns `GRANT ALL ON <pattern>.*` gives `backup` in the users file the render
    writes (cloud_platform_backups.clickhouse_users), so the fake refuses what ClickHouse would."""
    user = backups.CLICKHOUSE_BACKUP_USER
    block = backups.clickhouse_users("osprey").split(f"<{user}>", 1)[1].split(f"</{user}>", 1)[0]
    return re.findall(r"GRANT ALL ON ([\w*]+)\.\*", block)


def _backup_user_may(database: str) -> bool:
    # ClickHouse's wildcard grant (`db*`) is a prefix; anything else names one database.
    return any(
        database.startswith(p[:-1]) if p.endswith("*") else database == p for p in _backup_user_grants()
    )


def _databases_named(statement: str) -> list[str]:
    """The databases a restore's statement creates, drops, renames or restores into."""
    found = re.findall(
        r"(?:DROP DATABASE(?: IF EXISTS)?|CREATE DATABASE(?: IF NOT EXISTS)?|RENAME DATABASE|\bTO|\bAS)\s+(\w+)",
        statement,
    )
    return [d for d in found if d not in ("S3",)]


class FakeStores:
    """ArcadeDB's and ClickHouse's HTTP, as `Stores.http` calls them."""

    def __init__(self, aws: Running, folder: Path) -> None:
        self.aws, self.folder = aws, folder
        self.statements: list[str] = []
        self.arcadedb_answer: bytes | None = None
        self.client: Any = None
        self.access_key: str | None = None
        #: ClickHouse's databases, as its DDL changes them (round 3 on kind: a RENAME of a database
        #: that is not there is refused, Code 81, which a fake answering every DDL with "" hid).
        self.databases: set[str] = {"ospreyflow"}
        #: A Replicated database's Keeper path, which a RENAME keeps (kind, round 4: the restored
        #: database renamed into the live one's place kept `…_restoring_<set>`'s path, and the same
        #: set's next restore was refused making it again, Code 253).
        self.keeper: dict[str, str] = {}

    def _s3(self) -> Any:
        """ClickHouse's S3 client as **its own** role, by its pod's web identity (never the process's
        environment, which is the runner's). As ClickHouse 25.8 does, measured on osprey-p9: an STS
        refusal leaves it no credentials, and it writes anonymously (refused); a session kept is
        renewed when S3 says it expired (`_renewing`)."""
        if self.client is None:
            sts = botocore.session.get_session().create_client(
                "sts", region_name=REGION, endpoint_url=self.aws.endpoint,
                config=Config(signature_version=UNSIGNED, retries={"max_attempts": 1}))  # fmt: skip
            try:
                found = sts.assume_role_with_web_identity(
                    RoleArn=CLICKHOUSE_ROLE_ARN, RoleSessionName="clickhouse",
                    WebIdentityToken=mint_token(ISSUER_SECRET, sub=CLICKHOUSE_SUBJECT),
                )["Credentials"]  # fmt: skip
                self.access_key = found["AccessKeyId"]
                self.client = botocore.session.get_session().create_client(
                    "s3", region_name=REGION, endpoint_url=self.aws.endpoint, config=PATH_STYLE,
                    aws_access_key_id=found["AccessKeyId"], aws_secret_access_key=found["SecretAccessKey"],
                    aws_session_token=found["SessionToken"])  # fmt: skip
            except ClientError:
                self.access_key = None
                self.client = botocore.session.get_session().create_client(
                    "s3", region_name=REGION, endpoint_url=self.aws.endpoint,
                    config=Config(signature_version=UNSIGNED, s3={"addressing_style": "path"},
                                  retries={"max_attempts": 1}))  # fmt: skip
        return self.client

    def _renewing(self, act: Any) -> Any:
        try:
            return act(self._s3())
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ExpiredToken":
                raise
            self.client = None  # renewed, as ClickHouse renews an expired session
            return act(self._s3())

    def _ddl(self, request: urllib.request.Request, body: str) -> bytes:
        """ClickHouse 25.8's own refusals, word for word (kind, round 3): a database that is not
        there (Code 81, HTTP 404), or one that already is (Code 82)."""

        def refuse(code: int, status: int, words: str) -> None:
            text = f"Code: {code}. DB::Exception: {words}. (version 25.8.33.6 (official build))".encode()
            raise urllib.error.HTTPError(request.full_url, status, "error", Message(), io.BytesIO(text))

        names = _databases_named(body)
        if body.startswith("DROP DATABASE"):
            if names[0] not in self.databases and " IF EXISTS " not in body:
                refuse(81, 404, f"Database {names[0]} does not exist. (UNKNOWN_DATABASE)")
            self.databases.discard(names[0])
            self.keeper.pop(names[0], None)
        elif body.startswith("CREATE DATABASE"):
            if names[0] in self.databases:
                refuse(82, 500, f"Database {names[0]} already exists. (DATABASE_ALREADY_EXISTS)")
            if path := re.search(r"Replicated\('([^']+)'", body):
                if path.group(1) in self.keeper.values():
                    refuse(253, 500, f"Replica clickhouse-0 of shard 01 of replicated database at {path.group(1)} "
                                     "already exists. (REPLICA_ALREADY_EXISTS)")  # fmt: skip
                self.keeper[names[0]] = path.group(1)
            self.databases.add(names[0])
        else:
            source, target = names[:2]
            if source not in self.databases:
                refuse(81, 404, f"Database {source} does not exist. (UNKNOWN_DATABASE)")
            if target in self.databases:
                refuse(82, 500, f"Database {target} already exists. (DATABASE_ALREADY_EXISTS)")
            self.databases.discard(source)
            self.databases.add(target)
            if source in self.keeper:
                self.keeper[target] = self.keeper.pop(source)
        return b""

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
        user = request.get_header("X-clickhouse-user")
        if body.startswith(("BACKUP", "RESTORE")) and user != "backup":
            # ClickHouse 25.8's own refusal to the deployment's user, which holds no BACKUP (and no
            # S3 source), measured in p9_grants_probe.log.
            text = (f"Code: 497. DB::Exception: {user}: Not enough privileges. To execute this query, "
                    "it's necessary to have the grant BACKUP ON ospreyflow.*. (ACCESS_DENIED)").encode()  # fmt: skip
            raise urllib.error.HTTPError(request.full_url, 500, "error", Message(), io.BytesIO(text))
        for database in _databases_named(body):
            if not _backup_user_may(database):
                # ClickHouse 25.8's own refusal (kind, round 3: the restore's temporary database
                # outside `ospreyflow.*`), judged by the grants the real users file gives `backup`.
                text = (f"Code: 497. DB::Exception: backup: Not enough privileges. To execute this query, "
                        f"it's necessary to have the grant DROP DATABASE ON {database}.*. (ACCESS_DENIED)").encode()  # fmt: skip
                raise urllib.error.HTTPError(request.full_url, 500, "error", Message(), io.BytesIO(text))
        if body.startswith("EXISTS DATABASE"):
            return b"1\n" if body.split()[2] in self.databases else b"0\n"
        if body.startswith(("DROP DATABASE", "CREATE DATABASE", "RENAME DATABASE")):
            return self._ddl(request, body)
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

        def backup(s3: Any) -> bytes:
            # ClickHouse sends no encryption header: the bucket's default (its key) applies.
            # As ClickHouse 25.8 does: its lock first, removed at the end (refused without
            # s3:DeleteObject on it, measured on osprey-p9), then the backup's own files.
            s3.put_object(Bucket=bucket, Key=prefix + ".lock", Body=b"")
            s3.put_object(Bucket=bucket, Key=prefix + "data/ospreyflow/events/all_1_1_0/data.bin", Body=b"rows")
            s3.put_object(Bucket=bucket, Key=prefix + ".backup", Body=b"<config/>")  # last, as ClickHouse
            s3.delete_object(Bucket=bucket, Key=prefix + ".lock")
            return b"0b1d-backup-id\tBACKUP_CREATED\n"

        def restore(s3: Any) -> bytes:
            s3.get_object(Bucket=bucket, Key=prefix + ".backup")["Body"].read()
            return b"0b1d-restore-id\tRESTORED\n"

        try:
            return bytes(self._renewing(backup if body.startswith("BACKUP") else restore))
        except Exception as error:  # what ClickHouse says: its code, S3's words, the query
            said = getattr(error, "response", {}).get("Error", {})
            text = (f"Code: 499. DB::Exception: {said.get('Code')}: {said.get('Message')}. "
                    f"(S3_ERROR) (query: {body})").encode()  # fmt: skip
            raise urllib.error.HTTPError(request.full_url, 500, "error", Message(), io.BytesIO(text)) from None


@pytest.fixture
def run(aws: Running, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[pb.Settings, pb.Bucket, pb.Stores, FakeStores]:
    folder = tmp_path / "arcadedb-backups"
    folder.mkdir()
    settings = pb.Settings.from_env({
        "OSPREY_BACKUP_BUCKET": BUCKET, "OSPREY_BACKUP_KMS_KEY": KEY_ARN, "AWS_REGION": REGION,
        "AWS_ENDPOINT_URL_S3": aws.endpoint, "OSPREY_BACKUP_ARCADEDB_FOLDER": str(folder),
        "OSPREY_BACKUP_ARCADEDB_HOST": "arcadedb-0.arcadedb-headless",
        "ARCADEDB_ROOT_PASSWORD": "pw", "CLICKHOUSE_USER": "backup", "CLICKHOUSE_PASSWORD": "pw",
        # The restore's writers, as the chart names them; the pods listed as none running (a case
        # that wants one running gives its own listing).
        "OSPREY_BACKUP_WRITERS": "arcadedb,api,worker,report-sync",
    })  # fmt: skip
    aws.session()  # the pod's IRSA environment
    monkeypatch.setattr(pb, "_pods", lambda _: [])
    fake = FakeStores(aws, folder)
    return settings, pb.Bucket(settings), pb.Stores(settings, http=fake), fake


def _objects(aws: Running) -> list[str]:
    return [m["key"] for m in aws.stand_in.listing(BUCKET)]


def _deny_kms(aws: Running, *kept: str, role: str = ROLE_ARN) -> None:
    """`role`'s KMS actions narrowed to `kept`, in the key's own policy (which grants the roles the key
    directly, so a role's IAM policy alone never decides) and in its IAM policy alike; its sessions
    already running meet the new policies, as on AWS."""
    account = {ROLE_ARN: backups.SERVICE_ACCOUNT, CLICKHOUSE_ROLE_ARN: backups.CLICKHOUSE_SERVICE_ACCOUNT}[role]
    found = aws.stand_in.roles[role]
    found.policies = [role_policy(account, kms_actions=kept)]
    for session in aws.stand_in.sessions.values():
        if session.arn.startswith(role.replace(":role/", ":assumed-role/").replace("iam::", "sts::") + "/"):
            session.policies = found.policies
    policy = backups.key_policy(f"arn:aws:iam::{ACCOUNT}:root", [r for r in (ROLE_ARN, CLICKHOUSE_ROLE_ARN) if r != role], REGION)
    use = next(s for s in policy["Statement"] if s["Sid"] == "UseThroughS3")
    if kept:
        policy["Statement"].append({**use, "Sid": "UseThroughS3Narrowed", "Principal": {"AWS": [role]},
                                    "Action": list(kept)})  # fmt: skip
    aws.stand_in.keys[KEY_ARN] = policy


