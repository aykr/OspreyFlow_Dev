"""The backups' AWS side as P9's Terraform makes it (ADR-148 Amendment 7), on the S3 stand-in
(`tests/fixtures/cloud_platform/s3_standin.py`), which refuses what S3, STS and KMS refuse.

The role's policy and the bucket's are `harness.cloud_platform_backups`' own, the one source the
rendered `backups.tf` is written from, so a refusal here is the refusal the platform would give for
the same request.
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

from harness import cloud_platform_backups as backups
from tests.fixtures.cloud_platform.s3_standin import Server, StandIn, mint_token, serve

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
