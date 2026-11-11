"""The `cloud-platform` profile's backups, as the render writes them (`spec/06_DECISIONS.md` ADR-148
decision 13, as built in Amendment 7, P9): the chart's `backups` values, ArcadeDB's backups claim,
and the namespace's `backups.tf`.

Called from `harness.cloud_platform.render_cloud_platform` and `harness.cloud_platform.terraform.
render_terraform` (two lines, the platform lane's, ADR-142 Amendment 8 decision 3), so this module
is the backups' one place: the chart's template (`templates/backups.yaml`) renders what
`backups_values` returns, the runner (`services/api/platform_backup.py`) reads what its `env`
names, and **the IAM policies are written once** (`bucket_policy`, `role_policy`), for the
Terraform with its references and for the S3 stand-in's tests with the ARNs they stand for, so a
policy the stand-in refuses is the policy the platform would be given.

What a backup needs from the AWS side, all made here: a bucket of its own (`<prefix>backups`),
encrypted by a KMS key of its own, its policy refusing plain HTTP, another encryption, another
key and every principal but the backup role; that role, trusted for one service account
(`ospreyflow-backup`) and given that bucket and that key alone; the secret the runner reads the
bucket's name and the key's ARN from.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from harness.cloud_platform.settings import PlatformSettings
from schemas.deployment import OspreyConfig

#: The backup's own service account (IRSA), apart from the Conduit's, so the Conduit's role is
#: never given the backups and the backup's is never given the Conduit's buckets.
SERVICE_ACCOUNT = "ospreyflow-backup"
#: The secret the namespace's Terraform writes the bucket's name and the key's ARN into.
OUTPUT_SECRET = "ospreyflow-backup-output"
OUTPUT_KEYS = {"bucket": "bucket", "kms_key": "kms_key_arn"}
#: Daily at 02:15 UTC; the sets kept (ADR-148 Amendment 7: the client's retention is to be
#: agreed, so a proposal, not a measurement).
SCHEDULE = "15 2 * * *"
KEEP = 14
#: ArcadeDB's `BACKUP DATABASE` folder, given a claim of its own on this profile so the CronJob's
#: pod can read the zip (as a scratch folder, no other pod could).
ARCADEDB_BACKUPS = "/home/arcadedb/backups"
#: A run's deadline: long enough for the largest backup proposed, short enough that a hung one
#: does not hold the next night's (`concurrencyPolicy: Forbid`).
DEADLINE_SECONDS = 6 * 3600

OBJECT_ACTIONS = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
BUCKET_ACTIONS = ["s3:ListBucket", "s3:GetBucketLocation"]
KMS_ACTIONS = ["kms:GenerateDataKey", "kms:Decrypt"]


def role_policy(bucket_arn: str, key_arn: str) -> dict[str, Any]:
    """The backup role's own policy: the backups bucket and its key, nothing else."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": BUCKET_ACTIONS, "Resource": [bucket_arn]},
            {"Effect": "Allow", "Action": OBJECT_ACTIONS, "Resource": [f"{bucket_arn}/*"]},
            {"Effect": "Allow", "Action": KMS_ACTIONS, "Resource": [key_arn]},
        ],
    }


def bucket_policy(bucket_arn: str, key_arn: str, role_arn: str) -> dict[str, Any]:
    """The backups bucket's policy. **No header is the bucket's default** (its key, which
    ClickHouse relies on): IAM reads `StringNotEqualsIfExists` on an absent header as true, so a
    deny by it would refuse every upload without one; `Null: false` denies only a header present
    and wrong (found by the stand-in, 11 November 2026)."""
    every = [bucket_arn, f"{bucket_arn}/*"]
    key_header = "s3:x-amz-server-side-encryption-aws-kms-key-id"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "TLSOnly", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
             "Resource": every, "Condition": {"Bool": {"aws:SecureTransport": "false"}}},
            {"Sid": "KMSOnly", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": [f"{bucket_arn}/*"],
             "Condition": {"StringNotEquals": {"s3:x-amz-server-side-encryption": "aws:kms"},
                           "Null": {"s3:x-amz-server-side-encryption": "false"}}},
            {"Sid": "ItsOwnKey", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": [f"{bucket_arn}/*"],
             "Condition": {"StringNotEquals": {key_header: key_arn},
                           "Null": {key_header: "false"}}},
            # The objects the backup role's alone: the Conduit's role, which holds every other
            # bucket, is refused here. The bucket's own settings stay the Terraform's to change.
            {"Sid": "BackupRoleOnly", "Effect": "Deny", "Principal": "*",
             "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
             "Resource": every, "Condition": {"ArnNotEquals": {"aws:PrincipalArn": role_arn}}},
        ],
    }  # fmt: skip


def _workload(workloads: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((w for w in workloads if w["name"] == name), None)


def give_arcadedb_its_backups_claim(arcadedb: dict[str, Any]) -> dict[str, Any]:
    """ArcadeDB's backups folder as a claim (`backups`, the databases claim's size: a backup is
    never larger than the database), no longer a scratch folder. Returns the claim."""
    arcadedb["scratch"] = [
        s for s in arcadedb.get("scratch", []) if s["mountPath"] != ARCADEDB_BACKUPS
    ]
    if not arcadedb["scratch"]:
        arcadedb.pop("scratch")
    databases = next(c for c in arcadedb["claims"] if c["mountPath"] == "/home/arcadedb/databases")
    claim = {"name": "backups", "mountPath": ARCADEDB_BACKUPS, "size": databases["size"]}
    arcadedb["claims"] = [*arcadedb["claims"], claim]
    return claim


def clickhouse_writes_as_the_backup_role(clickhouse: dict[str, Any], region: str) -> None:
    """ClickHouse's pod runs as the backup role's service account (IRSA): ClickHouse 25.8 takes no
    session token in `BACKUP … TO S3()`, so it writes as the role by its own web identity; its
    STS client asks the region AWS_DEFAULT_REGION names (us-east-1 without it). Amendment 7."""
    clickhouse["serviceAccountName"] = SERVICE_ACCOUNT
    names = {"AWS_REGION", "AWS_DEFAULT_REGION"}
    clickhouse["env"] = [e for e in clickhouse.get("env", []) if e["name"] not in names] + [
        {"name": "AWS_REGION", "value": region},
        {"name": "AWS_DEFAULT_REGION", "value": region},
    ]


def _env_from(environment: dict[str, Any], names: list[str]) -> list[dict[str, Any]]:
    return [{"name": n, "config": n} for n in names if n in environment]


def backups_values(
    config: OspreyConfig,
    platform: PlatformSettings,
    workloads: list[dict[str, Any]],
    environment: dict[str, Any],
) -> dict[str, Any] | None:
    """The chart's `backups` (and ArcadeDB's claim, given in `workloads`), or `None` when the
    deployment runs neither ArcadeDB nor ClickHouse. A deployment with one store and not the
    other is refused: the set is both, and half a set restores half a deployment."""
    arcadedb = _workload(workloads, "arcadedb")
    clickhouse = _workload(workloads, "clickhouse")
    api = _workload(workloads, "api")
    if arcadedb is None and clickhouse is None:
        return None
    if arcadedb is None or clickhouse is None or api is None:
        missing = [
            n
            for n, w in (("arcadedb", arcadedb), ("clickhouse", clickhouse), ("api", api))
            if w is None
        ]
        raise ValueError(
            "the backups (ADR-148 decision 13) take ArcadeDB and ClickHouse together, in the "
            f"Conduit's image; this render has no {', '.join(missing)}"
        )
    claim = give_arcadedb_its_backups_claim(arcadedb)
    clickhouse_writes_as_the_backup_role(clickhouse, platform.aws_region)
    env: list[dict[str, Any]] = [
        {"name": "AWS_REGION", "value": platform.aws_region},
        {"name": "OSPREY_BACKUP_BUCKET",
         "secretKeyRef": {"name": OUTPUT_SECRET, "key": OUTPUT_KEYS["bucket"]}},
        {"name": "OSPREY_BACKUP_KMS_KEY",
         "secretKeyRef": {"name": OUTPUT_SECRET, "key": OUTPUT_KEYS["kms_key"]}},
        {"name": "OSPREY_BACKUP_KEEP", "value": str(KEEP)},
        # The pod whose claim the CronJob mounts, by name: the Service would hand the request to
        # whichever copy answered, and its zip would be on another claim.
        {"name": "OSPREY_BACKUP_ARCADEDB_HOST", "value": "arcadedb-0.arcadedb-headless"},
        {"name": "ARCADEDB_ROOT_PASSWORD", "secret": "ARCADEDB_ROOT_PASSWORD"},
        *_env_from(environment, ["CLICKHOUSE_HOST", "CLICKHOUSE_HTTP_PORT", "CLICKHOUSE_USER",
                                 "CLICKHOUSE_CLUSTER"]),
        {"name": "CLICKHOUSE_PASSWORD", "secret": "CLICKHOUSE_PASSWORD"},
    ]  # fmt: skip
    return {
        "schedule": SCHEDULE,
        "image": api["image"],
        "serviceAccountName": SERVICE_ACCOUNT,
        "deadlineSeconds": DEADLINE_SECONDS,
        "resources": copy.deepcopy(api.get("resources") or {}),
        "env": env,
        "arcadedb": {
            "pod": "arcadedb-0",
            "backupsClaim": f"{claim['name']}-arcadedb-0",
            "databasesClaim": "databases-arcadedb-0",
            "database": "ospreyflow",
            "image": arcadedb["image"],
            "resources": copy.deepcopy(arcadedb.get("resources") or {}),
        },
    }


def _list(values: Any) -> str:
    return json.dumps(values if isinstance(values, list) else [values])


def policy_document(document: dict[str, Any]) -> list[Any]:
    """A policy document's statements as an `aws_iam_policy_document`'s blocks, in the shape
    `tofu fmt` leaves alone. Each condition key is a block of its own (IAM ANDs them, as the
    document's one block does); `Principal: "*"` is `type = "*"`, `identifiers = ["*"]`."""
    blocks: list[Any] = []
    for statement in document["Statement"]:
        body: list[Any] = []
        if "Sid" in statement:
            body.append(("sid", json.dumps(statement["Sid"])))
        body.append(("effect", json.dumps(statement["Effect"])))
        body.append(("actions", _list(statement["Action"])))
        body.append(("resources", _list(statement["Resource"])))
        if statement.get("Principal") == "*":
            body.append(("principals", [("type", '"*"'), ("identifiers", '["*"]')]))
        for operator, keys in statement.get("Condition", {}).items():
            for key, value in keys.items():
                body.append(("condition", [("test", json.dumps(operator)),
                                           ("variable", json.dumps(key)),
                                           ("values", _list(value))]))  # fmt: skip
        blocks.append(("statement", body))
    return blocks


def backups_terraform(config: OspreyConfig, platform: PlatformSettings) -> str:
    """`terraform/backups.tf`: the key, the bucket, its policy, the role, its service account and
    the secret the runner reads. Uses `s3.tf`'s `local.prefix` and `irsa.tf`'s variables."""
    from harness.cloud_platform.terraform import _file, _q, _secret

    bucket_arn = "${aws_s3_bucket.backups.arn}"
    key_arn = "${aws_kms_key.backups.arn}"
    role_arn = "${aws_iam_role.backup.arn}"
    subject = f"system:serviceaccount:${{var.namespace}}:{SERVICE_ACCOUNT}"
    return _file(
        "Decision 13 (ADR-148 Amendment 7): the backups' bucket, encrypted by a key of its own,\n"
        "its objects the backup role's alone; that role, trusted for the backup's service account\n"
        "and given this bucket and this key, nothing else.",
        [
            ('resource "aws_kms_key" "backups"', [
                ("description", '"${var.namespace} backups"'),
                ("enable_key_rotation", "true"),
                ("deletion_window_in_days", "30"),
                # spec/05 §6.1: a set must never become data nobody can read. A destroy of the
                # namespace would schedule this key's deletion while the bucket (not empty, so not
                # deleted) still held its sets; it is kept from a destroy, and so is the bucket.
                ("lifecycle", [("prevent_destroy", "true")]),
            ]),
            ('resource "aws_kms_alias" "backups"', [
                ("name", '"alias/${var.namespace}-backups"'),
                ("target_key_id", "aws_kms_key.backups.key_id"),
            ]),
            ('resource "aws_s3_bucket" "backups"', [
                ("bucket", '"${local.prefix}backups"'),
                ("lifecycle", [("prevent_destroy", "true")]),
            ]),
            ('resource "aws_s3_bucket_public_access_block" "backups"', [
                ("bucket", "aws_s3_bucket.backups.id"),
                ("block_public_acls", "true"),
                ("block_public_policy", "true"),
                ("ignore_public_acls", "true"),
                ("restrict_public_buckets", "true"),
            ]),
            ('resource "aws_s3_bucket_server_side_encryption_configuration" "backups"', [
                ("bucket", "aws_s3_bucket.backups.id"),
                ("rule", [
                    ("apply_server_side_encryption_by_default", [
                        ("sse_algorithm", _q("aws:kms")),
                        ("kms_master_key_id", "aws_kms_key.backups.arn"),
                    ]),
                    ("bucket_key_enabled", "true"),
                ]),
            ]),
            ('resource "aws_s3_bucket_lifecycle_configuration" "backups"', [
                ("bucket", "aws_s3_bucket.backups.id"),
                ("rule", [
                    ("id", _q("abort-unfinished-uploads")),
                    ("status", _q("Enabled")),
                    ("filter", [("prefix", '""')]),
                    ("abort_incomplete_multipart_upload", [("days_after_initiation", "7")]),
                ]),
            ]),
            ('data "aws_iam_policy_document" "backups_bucket"',
             policy_document(bucket_policy(bucket_arn, key_arn, role_arn))),
            ('resource "aws_s3_bucket_policy" "backups"', [
                ("bucket", "aws_s3_bucket.backups.id"),
                ("policy", "data.aws_iam_policy_document.backups_bucket.json"),
            ]),
            ('data "aws_iam_policy_document" "backup_trust"', [
                ("statement", [
                    ("actions", '["sts:AssumeRoleWithWebIdentity"]'),
                    ("principals", [("type", _q("Federated")),
                                    ("identifiers", "[var.eks_oidc_provider_arn]")]),
                    ("condition", [
                        ("test", _q("StringEquals")),
                        ("variable", '"${var.eks_oidc_issuer}:sub"'),
                        ("values", f'["{subject}"]'),
                    ]),
                    ("condition", [
                        ("test", _q("StringEquals")),
                        ("variable", '"${var.eks_oidc_issuer}:aud"'),
                        ("values", '["sts.amazonaws.com"]'),
                    ]),
                ]),
            ]),
            ('resource "aws_iam_role" "backup"', [
                ("name", '"${var.namespace}-backup"'),
                ("assume_role_policy", "data.aws_iam_policy_document.backup_trust.json"),
            ]),
            ('data "aws_iam_policy_document" "backup_role"',
             policy_document(role_policy(bucket_arn, key_arn))),
            ('resource "aws_iam_role_policy" "backup"', [
                ("name", '"${var.namespace}-backups"'),
                ("role", "aws_iam_role.backup.id"),
                ("policy", "data.aws_iam_policy_document.backup_role.json"),
            ]),
            ('resource "kubernetes_service_account" "backup"', [
                ("metadata", [
                    ("name", _q(SERVICE_ACCOUNT)),
                    ("namespace", "var.namespace"),
                    ("annotations", {_q("eks.amazonaws.com/role-arn"): "aws_iam_role.backup.arn"}),
                ]),
            ]),
            _secret(OUTPUT_SECRET, {
                OUTPUT_KEYS["bucket"]: "aws_s3_bucket.backups.bucket",
                OUTPUT_KEYS["kms_key"]: "aws_kms_key.backups.arn",
            }),
        ],
    )  # fmt: skip
