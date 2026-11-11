"""The `cloud-platform` profile's backups, as the render writes them (`spec/06_DECISIONS.md` ADR-148
decision 13, as built in Amendment 7, P9): the chart's `backups` values, ArcadeDB's backups claim,
ClickHouse's backup user and role, and the namespace's `backups.tf`.

**One hook** (the platform lane's condition, ADR-148 Amendment 7): `harness.cloud_platform.
render_cloud_platform` calls `add_backups` once, with the values it is about to write; this module
adds to those values and returns the Terraform file it adds. It changes nothing else of the render.
So this module is the backups' one place: the chart's template (`templates/backups.yaml`) renders
what it adds, the runner (`services/api/platform_backup.py`) reads what its `env` names, and **every
policy is written once** (`role_policies`, `trust_policy`, `bucket_policy`, `key_policy`), for the
Terraform with its references and for the S3 stand-in's tests and kind run with the ARNs they stand
for, so a policy the stand-in refuses is the policy the platform would be given.

**Two roles, each to its own prefix** (the orchestrator's ruling of 11 November 2026, after `osprey`
read and overwrote sets through ClickHouse's `s3()` on kind):
- the runner's (`<namespace>-backup`, service account `ospreyflow-backup`): ArcadeDB's zip, the
  claims part and the manifest;
- ClickHouse's (`<namespace>-backup-clickhouse`, its pod's service account): `sets/*/clickhouse/*`,
  and the one delete of its own lock.

ClickHouse's own SQL users are split too: `backup` holds BACKUP, RESTORE and the S3 source, and is
used by the runner alone; the deployment's own user (`osprey`) is refused the S3 and URL sources and
BACKUP, so no query of the Conduit's or a worker's reaches the bucket through ClickHouse's role.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from harness.cloud_platform.settings import PlatformSettings
from schemas.deployment import OspreyConfig

#: The runner's service account (IRSA), apart from the Conduit's: the Conduit's role is never given
#: the backups and the runner's is never given the Conduit's buckets.
SERVICE_ACCOUNT = "ospreyflow-backup"
#: ClickHouse's own (its pod's), for its `sets/*/clickhouse/*` alone.
CLICKHOUSE_SERVICE_ACCOUNT = "ospreyflow-backup-clickhouse"
#: The roles' names after the namespace's (`<namespace>-backup`, `<namespace>-backup-clickhouse`).
ROLE_SUFFIX = {SERVICE_ACCOUNT: "backup", CLICKHOUSE_SERVICE_ACCOUNT: "backup-clickhouse"}
#: The secret the namespace's Terraform writes the bucket's name and the key's ARN into.
OUTPUT_SECRET = "ospreyflow-backup-output"
OUTPUT_KEYS = {"bucket": "bucket", "kms_key": "kms_key_arn"}
#: ClickHouse's backup user, used by the runner alone, and its password's key in our Secret.
CLICKHOUSE_BACKUP_USER = "backup"
CLICKHOUSE_BACKUP_PASSWORD = "OSPREY_CLICKHOUSE_BACKUP_PASSWORD"
CLICKHOUSE_USERS_FILE = "clickhouse-backup-users.xml"
#: Daily at 02:15 UTC; each set expires by the bucket's lifecycle rule after EXPIRE_DAYS, and an
#: object overwritten keeps its previous version for as long (the bucket is versioned), never by
#: a role, which can erase no set. Thirty-five days: a month of failed runs before the last good
#: set goes, for the alert (P9b) to be heard. The client's retention is to be agreed; a proposal,
#: not a measurement.
SCHEDULE = "15 2 * * *"
EXPIRE_DAYS = 35
#: The backups bucket's name after the deployment's prefix (`<prefix>backups`).
BUCKET_SUFFIX = "backups"
#: What a decommission keeps (the orchestrator's ruling of 11 November 2026): the bucket, its
#: settings and its key, so no decommission makes a retained set unreadable. The roles, their
#: service accounts and the Secret go, and are named ours, so the check still fails if they stay.
KEPT_AT_DECOMMISSION = (
    "aws_kms_key.backups",
    "aws_kms_alias.backups",
    "aws_s3_bucket.backups",
    "aws_s3_bucket_versioning.backups",
    "aws_s3_bucket_public_access_block.backups",
    "aws_s3_bucket_server_side_encryption_configuration.backups",
    "aws_s3_bucket_lifecycle_configuration.backups",
    "aws_s3_bucket_policy.backups",
)
#: ArcadeDB's `BACKUP DATABASE` folder, given a claim of its own on this profile so the CronJob's
#: pod can read the zip (as a scratch folder, no other pod could).
ARCADEDB_BACKUPS = "/home/arcadedb/backups"
#: A run's deadline: long enough for the largest backup proposed, short enough that a hung one
#: does not hold the next night's (`concurrencyPolicy: Forbid`).
DEADLINE_SECONDS = 6 * 3600

#: Each role's objects. No delete of a set by either: overwrites keep their previous version.
RUNNER_OBJECTS = ("sets/*/arcadedb/*", "sets/*/claims/*", "sets/*/manifest.json")
CLICKHOUSE_OBJECTS = ("sets/*/clickhouse/*",)
OBJECT_ACTIONS = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"]
#: The one object ClickHouse's role may delete: its own lock. ClickHouse 25.8's BACKUP removes it at
#: its end and fails without (measured on osprey-p9; the orchestrator's grant of 11 November).
CLICKHOUSE_LOCK = "sets/*/clickhouse/.lock"
BUCKET_ACTIONS = ["s3:ListBucket", "s3:GetBucketLocation"]
KMS_ACTIONS = ["kms:GenerateDataKey", "kms:Decrypt"]
#: The key's administrators' actions (the account's): never its use, never its deletion.
KEY_ADMIN_ACTIONS = [
    "kms:Create*", "kms:Describe*", "kms:Enable*", "kms:List*", "kms:Put*", "kms:Update*",
    "kms:Revoke*", "kms:Disable*", "kms:Get*", "kms:TagResource", "kms:UntagResource",
    "kms:CancelKeyDeletion",
]  # fmt: skip


def _via_s3(region: str) -> dict[str, Any]:
    return {"StringEquals": {"kms:ViaService": f"s3.{region}.amazonaws.com"}}


def role_policies(bucket_arn: str, key_arn: str, region: str) -> dict[str, dict[str, Any]]:
    """Each role's own policy, by its service account: the backups bucket's own prefix and the key,
    the key only through S3 in the region."""

    def policy(objects: tuple[str, ...], extra: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": BUCKET_ACTIONS, "Resource": [bucket_arn]},
                {"Effect": "Allow", "Action": OBJECT_ACTIONS,
                 "Resource": [f"{bucket_arn}/{o}" for o in objects]},
                {"Effect": "Allow", "Action": KMS_ACTIONS, "Resource": [key_arn],
                 "Condition": _via_s3(region)},
                *extra,
            ],
        }  # fmt: skip

    return {
        SERVICE_ACCOUNT: policy(RUNNER_OBJECTS, []),
        CLICKHOUSE_SERVICE_ACCOUNT: policy(
            CLICKHOUSE_OBJECTS,
            [{"Effect": "Allow", "Action": ["s3:DeleteObject"],
              "Resource": [f"{bucket_arn}/{CLICKHOUSE_LOCK}"]}],
        ),
    }  # fmt: skip


def trust_policy(provider_arn: str, issuer: str, subject: str) -> dict[str, Any]:
    """A role's trust: the cluster's OIDC provider, for one service account's token issued for STS
    alone (its `sub` and its `aud`)."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Principal": {"Federated": provider_arn},
             "Action": ["sts:AssumeRoleWithWebIdentity"],
             "Condition": {"StringEquals": {f"{issuer}:sub": subject,
                                            f"{issuer}:aud": "sts.amazonaws.com"}}},
        ],
    }  # fmt: skip


def bucket_policy(bucket_arn: str, key_arn: str, role_arns: list[str]) -> dict[str, Any]:
    """The backups bucket's policy. **No encryption header is the bucket's default** (its key, which
    ClickHouse relies on): IAM reads `StringNotEqualsIfExists` on an absent header as true, so a
    deny by it would refuse every upload without one; `Null: false` denies only a header present
    and wrong (found by the stand-in, 11 November 2026). `aws:kms` named **without a key** is S3's
    own key (`aws/s3`), not this one, and is refused (`NoKeyNamed`, the lane-reviewer's finding)."""
    every = [bucket_arn, f"{bucket_arn}/*"]
    sse = "s3:x-amz-server-side-encryption"
    key_header = "s3:x-amz-server-side-encryption-aws-kms-key-id"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "TLSOnly", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
             "Resource": every, "Condition": {"Bool": {"aws:SecureTransport": "false"}}},
            {"Sid": "KMSOnly", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": [f"{bucket_arn}/*"],
             "Condition": {"StringNotEquals": {sse: "aws:kms"}, "Null": {sse: "false"}}},
            {"Sid": "ItsOwnKey", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": [f"{bucket_arn}/*"],
             "Condition": {"StringNotEquals": {key_header: key_arn},
                           "Null": {key_header: "false"}}},
            {"Sid": "NoKeyNamed", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": [f"{bucket_arn}/*"],
             "Condition": {"StringEquals": {sse: "aws:kms"}, "Null": {key_header: "true"}}},
            # The objects the backup roles' alone: the Conduit's role, which holds every other
            # bucket, is refused here. The bucket's own settings stay the Terraform's to change.
            {"Sid": "BackupRolesOnly", "Effect": "Deny", "Principal": "*",
             "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
             "Resource": every, "Condition": {"ArnNotEquals": {"aws:PrincipalArn": role_arns}}},
        ],
    }  # fmt: skip


def key_policy(account_root: str, role_arns: list[str], region: str) -> dict[str, Any]:
    """The backups key's own policy (the orchestrator's ruling 7): the account's administrators
    administer it, never use it; the backup roles use it, through S3 in the region alone; **nobody
    schedules its deletion** (the decommission's section 9 replaces this policy first, the client's
    decision when the retention ends)."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "Administer", "Effect": "Allow", "Principal": {"AWS": [account_root]},
             "Action": KEY_ADMIN_ACTIONS, "Resource": ["*"]},
            {"Sid": "UseThroughS3", "Effect": "Allow", "Principal": {"AWS": role_arns},
             "Action": [*KMS_ACTIONS, "kms:DescribeKey"], "Resource": ["*"],
             "Condition": _via_s3(region)},
            {"Sid": "NeverScheduledForDeletion", "Effect": "Deny", "Principal": "*",
             "Action": ["kms:ScheduleKeyDeletion"], "Resource": ["*"]},
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


def clickhouse_users(deployment_user: str) -> str:
    """ClickHouse's users file: `backup` (the runner's: BACKUP, the S3 source, the database's own
    rights for RESTORE, ON CLUSTER), and the deployment's own user refused the S3 and URL sources
    and BACKUP, so none of its queries reaches the bucket through ClickHouse's role (measured on
    kind: before this, `osprey` read and overwrote sets). Each grant's grammar measured on
    ClickHouse 25.8.33.6."""
    return f"""<clickhouse>
  <users>
    <{deployment_user}>
      <grants>
        <query>GRANT ALL ON *.*</query>
        <query>REVOKE S3, URL, BACKUP ON *.*</query>
      </grants>
    </{deployment_user}>
    <{CLICKHOUSE_BACKUP_USER}>
      <password from_env="{CLICKHOUSE_BACKUP_PASSWORD}"/>
      <profile>default</profile>
      <quota>default</quota>
      <networks><ip>::/0</ip></networks>
      <grants>
        <query>GRANT ALL ON ospreyflow.*</query>
        <query>GRANT BACKUP, CLUSTER, S3 ON *.*</query>
      </grants>
    </{CLICKHOUSE_BACKUP_USER}>
  </users>
</clickhouse>
"""


def clickhouse_writes_as_its_backup_role(clickhouse: dict[str, Any], region: str) -> None:
    """ClickHouse's pod runs as its backup role's service account (IRSA): ClickHouse 25.8 takes no
    session token in `BACKUP … TO S3()`, so it writes as the role by its own web identity; its
    STS client asks the region AWS_DEFAULT_REGION names (us-east-1 without it). Its users file and
    its backup user's password. Amendment 7."""
    clickhouse["serviceAccountName"] = CLICKHOUSE_SERVICE_ACCOUNT
    names = {"AWS_REGION", "AWS_DEFAULT_REGION", CLICKHOUSE_BACKUP_PASSWORD}
    clickhouse["env"] = [e for e in clickhouse.get("env", []) if e["name"] not in names] + [
        {"name": "AWS_REGION", "value": region},
        {"name": "AWS_DEFAULT_REGION", "value": region},
        {"name": CLICKHOUSE_BACKUP_PASSWORD, "secret": CLICKHOUSE_BACKUP_PASSWORD},
    ]
    clickhouse["files"] = [
        *clickhouse.get("files", []),
        {
            "key": CLICKHOUSE_USERS_FILE,
            "mountPath": "/etc/clickhouse-server/users.d/backup-users.xml",
        },
    ]


def _env_from(environment: dict[str, Any], names: list[str]) -> list[dict[str, Any]]:
    return [{"name": n, "config": n} for n in names if n in environment]


def backups_values(
    config: OspreyConfig,
    platform: PlatformSettings,
    workloads: list[dict[str, Any]],
    environment: dict[str, Any],
) -> dict[str, Any] | None:
    """The chart's `backups` (and ArcadeDB's claim and ClickHouse's role, given in `workloads`), or
    `None` when the deployment runs neither ArcadeDB nor ClickHouse. A deployment with one store and
    not the other is refused: the set is both, and half a set restores half a deployment."""
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
    clickhouse_writes_as_its_backup_role(clickhouse, platform.aws_region)
    env: list[dict[str, Any]] = [
        {"name": "AWS_REGION", "value": platform.aws_region},
        {"name": "OSPREY_BACKUP_BUCKET",
         "secretKeyRef": {"name": OUTPUT_SECRET, "key": OUTPUT_KEYS["bucket"]}},
        {"name": "OSPREY_BACKUP_KMS_KEY",
         "secretKeyRef": {"name": OUTPUT_SECRET, "key": OUTPUT_KEYS["kms_key"]}},
        # The pod whose claim the CronJob mounts, by name: the Service would hand the request to
        # whichever copy answered, and its zip would be on another claim.
        {"name": "OSPREY_BACKUP_ARCADEDB_HOST", "value": "arcadedb-0.arcadedb-headless"},
        {"name": "ARCADEDB_ROOT_PASSWORD", "secret": "ARCADEDB_ROOT_PASSWORD"},
        *_env_from(environment, ["CLICKHOUSE_HOST", "CLICKHOUSE_HTTP_PORT", "CLICKHOUSE_CLUSTER"]),
        # ClickHouse's backup user, the runner's alone (the deployment's own is refused BACKUP).
        {"name": "CLICKHOUSE_USER", "value": CLICKHOUSE_BACKUP_USER},
        {"name": "CLICKHOUSE_PASSWORD", "secret": CLICKHOUSE_BACKUP_PASSWORD},
    ]  # fmt: skip
    return {
        "schedule": SCHEDULE,
        "image": api["image"],
        "serviceAccountName": SERVICE_ACCOUNT,
        "deadlineSeconds": DEADLINE_SECONDS,
        "resources": copy.deepcopy(api.get("resources") or {}),
        "env": env,
        # The pods a restore refuses to run beside (the orchestrator's ruling 4): every writer.
        "writers": ["arcadedb", "api", "worker", "report-sync"],
        "arcadedb": {
            "pod": "arcadedb-0",
            "backupsClaim": f"{claim['name']}-arcadedb-0",
            "databasesClaim": "databases-arcadedb-0",
            "database": "ospreyflow",
            "image": arcadedb["image"],
            "resources": copy.deepcopy(arcadedb.get("resources") or {}),
        },
    }


def add_backups(
    config: OspreyConfig, platform: PlatformSettings, values: dict[str, Any]
) -> dict[str, str]:
    """**The hook** (`render_cloud_platform` calls it once, with the values it is about to write):
    the backups added to `values` (the chart's `backups`, ArcadeDB's claim, ClickHouse's role, users
    file and backup user's password); returns the Terraform files it adds, `terraform/backups.tf`.
    A render without ArcadeDB and ClickHouse is returned unchanged."""
    found = backups_values(config, platform, values["workloads"], values["environment"])
    if found is None:
        return {}
    values["backups"] = found
    deployment_user = str(values["environment"].get("CLICKHOUSE_USER", "default"))
    values["files"][CLICKHOUSE_USERS_FILE] = clickhouse_users(deployment_user)
    secrets = values["secrets"]
    secrets["keys"] = sorted({*secrets["keys"], CLICKHOUSE_BACKUP_PASSWORD})
    return {"terraform/backups.tf": backups_terraform(config, platform)}


def _list(values: Any) -> str:
    return json.dumps(values if isinstance(values, list) else [values])


def policy_document(document: dict[str, Any]) -> list[Any]:
    """A policy document's statements as an `aws_iam_policy_document`'s blocks, in the shape
    `tofu fmt` leaves alone. Each condition key is a block of its own (IAM ANDs them, as the
    document's one block does); `Principal: "*"` is `type = "*"`, `identifiers = ["*"]`, and a
    principal map (`{"AWS": […]}`, `{"Federated": …}`) a block of its type."""
    blocks: list[Any] = []
    for statement in document["Statement"]:
        body: list[Any] = []
        if "Sid" in statement:
            body.append(("sid", json.dumps(statement["Sid"])))
        body.append(("effect", json.dumps(statement["Effect"])))
        body.append(("actions", _list(statement["Action"])))
        if "Resource" in statement:
            body.append(("resources", _list(statement["Resource"])))
        principal = statement.get("Principal")
        if principal == "*":
            body.append(("principals", [("type", '"*"'), ("identifiers", '["*"]')]))
        elif isinstance(principal, dict):
            for kind, who in principal.items():
                body.append(
                    ("principals", [("type", json.dumps(kind)), ("identifiers", _list(who))])
                )
        for operator, keys in statement.get("Condition", {}).items():
            for key, value in keys.items():
                body.append(("condition", [("test", json.dumps(operator)),
                                           ("variable", json.dumps(key)),
                                           ("values", _list(value))]))  # fmt: skip
        blocks.append(("statement", body))
    return blocks


def _role_ref(account: str) -> str:
    return f"aws_iam_role.{ROLE_SUFFIX[account].replace('-', '_')}"


def backups_terraform(config: OspreyConfig, platform: PlatformSettings) -> str:
    """`terraform/backups.tf`: the key and its policy, the bucket (versioned) and its policy, the
    two roles, their service accounts and the secret the runner reads. Uses `s3.tf`'s
    `local.prefix` and `irsa.tf`'s variables."""
    from harness.cloud_platform.terraform import _file, _q, _secret

    region = platform.aws_region
    bucket_arn = "${aws_s3_bucket.backups.arn}"
    key_arn = "${aws_kms_key.backups.arn}"
    role_arns = [f"${{{_role_ref(a)}.arn}}" for a in ROLE_SUFFIX]
    root = "arn:aws:iam::${data.aws_caller_identity.backups.account_id}:root"
    policies = role_policies(bucket_arn, key_arn, region)
    roles: list[Any] = []
    for account, suffix in ROLE_SUFFIX.items():
        ref = _role_ref(account).split(".", 1)[1]
        subject = f"system:serviceaccount:${{var.namespace}}:{account}"
        roles += [
            (f'data "aws_iam_policy_document" "{ref}_trust"',
             policy_document(trust_policy("${var.eks_oidc_provider_arn}",
                                          "${var.eks_oidc_issuer}", subject))),
            (f'resource "aws_iam_role" "{ref}"', [
                ("name", f'"${{var.namespace}}-{suffix}"'),
                ("assume_role_policy", f"data.aws_iam_policy_document.{ref}_trust.json"),
            ]),
            (f'data "aws_iam_policy_document" "{ref}_policy"', policy_document(policies[account])),
            (f'resource "aws_iam_role_policy" "{ref}"', [
                ("name", f'"${{var.namespace}}-{suffix}"'),
                ("role", f"aws_iam_role.{ref}.id"),
                ("policy", f"data.aws_iam_policy_document.{ref}_policy.json"),
            ]),
            (f'resource "kubernetes_service_account" "{ref}"', [
                ("metadata", [
                    ("name", _q(account)),
                    ("namespace", "var.namespace"),
                    ("annotations", {_q("eks.amazonaws.com/role-arn"): f"aws_iam_role.{ref}.arn"}),
                ]),
            ]),
        ]  # fmt: skip
    return _file(
        "Decision 13 (ADR-148 Amendment 7): the backups' bucket, versioned and encrypted by a key\n"
        "of its own; two roles, each trusted for its own service account and given its own prefix\n"
        "and this key through S3, nothing else; neither can erase a set.",
        [
            ('data "aws_caller_identity" "backups"', []),
            ('data "aws_iam_policy_document" "backups_key"',
             policy_document(key_policy(root, role_arns, region))),
            ('resource "aws_kms_key" "backups"', [
                ("description", '"${var.namespace} backups"'),
                ("enable_key_rotation", "true"),
                ("deletion_window_in_days", "30"),
                ("policy", "data.aws_iam_policy_document.backups_key.json"),
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
                ("bucket", f'"${{local.prefix}}{BUCKET_SUFFIX}"'),
                ("lifecycle", [("prevent_destroy", "true")]),
            ]),
            # An object overwritten keeps its previous version until the lifecycle rule expires it:
            # an overwrite is never an erasure, and no role holds DeleteObjectVersion.
            ('resource "aws_s3_bucket_versioning" "backups"', [
                ("bucket", "aws_s3_bucket.backups.id"),
                ("versioning_configuration", [("status", _q("Enabled"))]),
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
                ("depends_on", "[aws_s3_bucket_versioning.backups]"),
                ("rule", [
                    ("id", _q("abort-unfinished-uploads")),
                    ("status", _q("Enabled")),
                    ("filter", [("prefix", '""')]),
                    ("abort_incomplete_multipart_upload", [("days_after_initiation", "7")]),
                ]),
                ("rule", [
                    ("id", _q("expire-sets")),
                    ("status", _q("Enabled")),
                    ("filter", [("prefix", _q("sets/"))]),
                    ("expiration", [("days", str(EXPIRE_DAYS))]),
                    ("noncurrent_version_expiration", [("noncurrent_days", str(EXPIRE_DAYS))]),
                ]),
            ]),
            ('data "aws_iam_policy_document" "backups_bucket"',
             policy_document(bucket_policy(bucket_arn, key_arn, role_arns))),
            ('resource "aws_s3_bucket_policy" "backups"', [
                ("bucket", "aws_s3_bucket.backups.id"),
                ("policy", "data.aws_iam_policy_document.backups_bucket.json"),
            ]),
            *roles,
            _secret(OUTPUT_SECRET, {
                OUTPUT_KEYS["bucket"]: "aws_s3_bucket.backups.bucket",
                OUTPUT_KEYS["kms_key"]: "aws_kms_key.backups.arn",
            }),
        ],
    )  # fmt: skip
