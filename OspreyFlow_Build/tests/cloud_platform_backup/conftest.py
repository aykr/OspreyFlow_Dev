"""The backups' AWS side as P9's Terraform makes it (ADR-148 Amendment 7), on the S3 stand-in
(`tests/fixtures/cloud_platform/s3_standin.py`), which refuses what S3, STS and KMS refuse.

`backup_policies` is the role's policy and the bucket's, in the shape the rendered `backups.tf`
writes them (`P9_render.diff`'s `test_the_backup_policies_are_the_stand_ins` holds the two to one
another), so a refusal here is the refusal the platform would give for the same request.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import botocore.session
import pytest
from botocore.config import Config

from tests.fixtures.cloud_platform.s3_standin import Server, StandIn, mint_token, serve

ACCOUNT = "123456789012"
REGION = "eu-west-2"
BUCKET = "ospreyflow-dev-0a1b2c3d-backups"
KEY_ARN = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/1234abcd-12ab-34cd-56ef-1234567890ab"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-backup"
CONDUIT_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-service"
SUBJECT = "system:serviceaccount:ospreyflow-dev:ospreyflow-backup"
ISSUER_SECRET = "the-cluster-oidc-issuer"


def role_policy(*, kms_actions: tuple[str, ...] = ("kms:GenerateDataKey", "kms:Decrypt")) -> dict[str, Any]:
    """The backup role's own policy: the backups bucket and its key, nothing else."""
    statements: list[dict[str, Any]] = [
        {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
         "Resource": [f"arn:aws:s3:::{BUCKET}"]},
        {"Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"],
         "Resource": [f"arn:aws:s3:::{BUCKET}/*"]},
    ]  # fmt: skip
    if kms_actions:
        statements.append({"Effect": "Allow", "Action": list(kms_actions), "Resource": [KEY_ARN]})
    return {"Version": "2012-10-17", "Statement": statements}


def bucket_policy() -> dict[str, Any]:
    """The backups bucket's policy: TLS only, SSE-KMS by its own key only, and its objects the
    backup role's alone (the Conduit's role, which holds every other bucket, is refused here)."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "TLSOnly", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
             "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"],
             "Condition": {"Bool": {"aws:SecureTransport": "false"}}},
            {"Sid": "KMSOnly", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": [f"arn:aws:s3:::{BUCKET}/*"],
             # A header that names another encryption. No header is the bucket's default (its
             # key): `StringNotEqualsIfExists` would deny that too, as IAM reads it, so `Null`.
             "Condition": {"StringNotEquals": {"s3:x-amz-server-side-encryption": "aws:kms"},
                           "Null": {"s3:x-amz-server-side-encryption": "false"}}},
            {"Sid": "ItsOwnKey", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": [f"arn:aws:s3:::{BUCKET}/*"],
             "Condition": {"StringNotEquals": {"s3:x-amz-server-side-encryption-aws-kms-key-id": KEY_ARN},
                           "Null": {"s3:x-amz-server-side-encryption-aws-kms-key-id": "false"}}},
            {"Sid": "BackupRoleOnly", "Effect": "Deny", "Principal": "*",
             "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
             "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"],
             "Condition": {"ArnNotEquals": {"aws:PrincipalArn": ROLE_ARN}}},
        ],
    }  # fmt: skip


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
