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
import re
from pathlib import Path
from typing import Any

from harness.cloud_platform.settings import PlatformSettings
from schemas.deployment import OspreyConfig

#: The databases' names when the render's environment names none: the Conduit's own defaults
#: (`ArcadeDBConfig.from_env`'s callers and `services.api.analytics_store.CLICKHOUSE_DATABASE`).
DEFAULT_DATABASE = "ospreyflow"
#: ArcadeDB's restore step, run by the restore Job in ArcadeDB's own image, and its check: given
#: to the Job from the deployment's files (`ospreyflow-files`), mounted at `RESTORE_GRAPH_DIR`.
RESTORE_GRAPH_SOURCES = Path(__file__).resolve().parents[1] / "deploy" / "backups"
RESTORE_GRAPH_FILES = {
    "restore-graph.sh": "restore-graph.sh",
    "restore-graph-check.java": "CheckDatabase.java",
}
RESTORE_GRAPH_DIR = "/restore-graph"

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
#: ClickHouse's backup user, used by the runner alone. Its password is **a Secret of its own**
#: (backups.tf), never a key of the shared Secret, which the Conduit, the workers, the report sync
#: and the workspace load whole (`envFrom`): ClickHouse and the backup's own pods alone name it (the
#: lane-reviewer's round-2 blocker). CLICKHOUSE_BACKUP_PASSWORD: the variable ClickHouse reads.
CLICKHOUSE_BACKUP_USER = "backup"
CLICKHOUSE_BACKUP_PASSWORD = "OSPREY_CLICKHOUSE_BACKUP_PASSWORD"
BACKUP_SECRET = "ospreyflow-clickhouse-backup"
BACKUP_SECRET_KEY = "password"
CLICKHOUSE_USERS_FILE = "clickhouse-backup-users.xml"
#: Daily at 02:15 UTC. **The retention is the total** (the orchestrator's ruling): a set's objects
#: expire by the bucket's lifecycle rule EXPIRE_DAYS after they were written; an object overwritten
#: keeps its previous version for NONCURRENT_DAYS more, a window to recover an overwrite, not a
#: second retention; expired delete markers are removed. Thirty-four days: a month of failed runs
#: before the last good set goes, for the alert (P9b) to be heard. The client's retention is to be
#: agreed; a proposal, not a measurement.
#:
#: RDS keeps point in time for POINT_IN_TIME_DAYS (35, AWS's maximum), and the sets expire a day
#: sooner (ADR-148 Amendment 13 point 5; MORNING item 5, (a)): RDS's earliest restorable point lags
#: its retention by up to a day, and S3's expiry rounds up to midnight UTC, so a set kept as long as
#: RDS's window could fall outside it in its last day. A day sooner, every set still kept can be
#: restored with its database.
SCHEDULE = "15 2 * * *"
POINT_IN_TIME_DAYS = 35
EXPIRE_DAYS = POINT_IN_TIME_DAYS - 1
NONCURRENT_DAYS = 7
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
#: The key's administrators' actions (the account's): its alias, its rotation, its tags, reading it
#: and its policy (kms:PutKeyPolicy, which the Terraform applies). Not its use, and not
#: kms:CreateGrant (a grant is use), so no routine path uses the key but the two roles'. An
#: administrator can still rewrite this policy (kms:PutKeyPolicy): the Deny below guards against
#: accident, not against them.
KEY_ADMIN_ACTIONS = [
    "kms:CreateAlias", "kms:DeleteAlias", "kms:UpdateAlias", "kms:Describe*", "kms:Enable*",
    "kms:List*", "kms:PutKeyPolicy", "kms:Update*", "kms:Revoke*", "kms:Disable*", "kms:Get*",
    "kms:TagResource", "kms:UntagResource", "kms:CancelKeyDeletion",
]  # fmt: skip
#: Every object action the bucket's policy refuses to all but the two roles: reading, writing and
#: removing an object or any version of it. Not s3:ListBucket, which HeadBucket needs (the
#: Terraform's read of the bucket, the decommission's step 8): a listing names sets, holds none.
OBJECT_DENIED = [
    "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:PutObjectAcl",
    "s3:PutObjectVersionAcl", "s3:DeleteObject", "s3:DeleteObjectVersion", "s3:RestoreObject",
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
            # Every object and version the backup roles' alone: the Conduit's role, which holds
            # every other bucket, and any principal of the account are refused them. The bucket's
            # own settings stay the Terraform's (the account's administrators') to change.
            {"Sid": "BackupRolesOnly", "Effect": "Deny", "Principal": "*", "Action": OBJECT_DENIED,
             "Resource": [f"{bucket_arn}/*"],
             "Condition": {"ArnNotEquals": {"aws:PrincipalArn": role_arns}}},
        ],
    }  # fmt: skip


def key_policy(account_root: str, role_arns: list[str], region: str) -> dict[str, Any]:
    """The backups key's own policy (the orchestrator's ruling 7): the account's administrators
    administer it (KEY_ADMIN_ACTIONS: no use of it, no grant); the backup roles use it, through S3
    in the region alone; its deletion is denied to all, against accident (an administrator who
    rewrites the policy can lift that; the decommission's section 9 does, the client's decision)."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "Administer", "Effect": "Allow", "Principal": {"AWS": [account_root]},
             "Action": KEY_ADMIN_ACTIONS, "Resource": ["*"]},
            {"Sid": "UseThroughS3", "Effect": "Allow", "Principal": {"AWS": role_arns},
             "Action": [*KMS_ACTIONS, "kms:DescribeKey"], "Resource": ["*"],
             "Condition": _via_s3(region)},
            # Against accident: an administrator who rewrites this policy can remove it, and the
            # decommission's section 9 does so, the client's decision when the retention ends.
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


def clickhouse_users(deployment_user: str, database: str = DEFAULT_DATABASE) -> str:
    """ClickHouse's users file: `backup` (the runner's: BACKUP, the S3 source, ON CLUSTER, and
    every right on `ospreyflow*`, a prefix grant, since the restore makes `ospreyflow_restoring_*`
    and swaps it with `ospreyflow_before_*`: refused on kind with `ospreyflow.*` alone, measured
    both ways in gates/p9_grants_probe3.log), and the deployment's own user refused the S3 and URL
    sources and BACKUP, so none of its queries reaches the bucket through ClickHouse's role
    (measured on kind: before this, `osprey` read and overwrote sets), but for RESTORE, which no
    privilege gates (Amendment 7, point 4). Each grant measured on ClickHouse 25.8.33.6."""
    return f"""<clickhouse>
  <users>
    <{deployment_user}>
      <grants>
        <query>GRANT ALL ON *.*</query>
        <query>REVOKE ACCESS MANAGEMENT, NAMED COLLECTION ADMIN ON *.*</query>
        <query>REVOKE S3, URL, BACKUP ON *.*</query>
      </grants>
    </{deployment_user}>
    <{CLICKHOUSE_BACKUP_USER}>
      <password from_env="{CLICKHOUSE_BACKUP_PASSWORD}"/>
      <profile>default</profile>
      <quota>default</quota>
      <networks><ip>::/0</ip></networks>
      <grants>
        <query>GRANT ALL ON {database}*.*</query>
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
    # Its Kubernetes token not mounted: ClickHouse calls no Kubernetes API, and EKS's IRSA webhook
    # projects the role's web identity token by the account alone (cp-policy-check's `token` rule).
    # Set here, not left to where the render's own token step runs (P7b, Amendment 5 point 24).
    clickhouse["automountToken"] = False
    names = {"AWS_REGION", "AWS_DEFAULT_REGION", CLICKHOUSE_BACKUP_PASSWORD}
    clickhouse["env"] = [e for e in clickhouse.get("env", []) if e["name"] not in names] + [
        {"name": "AWS_REGION", "value": region},
        {"name": "AWS_DEFAULT_REGION", "value": region},
        {
            "name": CLICKHOUSE_BACKUP_PASSWORD,
            "secretKeyRef": {"name": BACKUP_SECRET, "key": BACKUP_SECRET_KEY},
        },
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


def database_names(environment: dict[str, Any]) -> tuple[str, str]:
    """ArcadeDB's and ClickHouse's databases as the Conduit reads them: `ARCADEDB_DATABASE` and
    `CLICKHOUSE_DATABASE` in the render's environment, else the Conduit's default. Refused unless
    plain, since each is written into a path, a grant and a statement."""
    names = tuple(
        str(environment.get(variable) or DEFAULT_DATABASE)
        for variable in ("ARCADEDB_DATABASE", "CLICKHOUSE_DATABASE")
    )
    for name in names:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name):
            raise ValueError(f"the database {name!r} is not a plain name the backups can use")
    return names[0], names[1]


#: The stores the restore replaces with their pods stopped (ArcadeDB, from its claim); ClickHouse
#: and its Keeper run through their restore (RESTORE, then a RENAME swap).
#: The ADR-148 audit's ruling 3 (v0.5.2): the shared claim's folders the deployment cannot make
#: again, each a part of the set's claims part: the published pipelines (the recipes repository,
#: under the Conduit's data folder), the model settings, and the map settings with the map key file
#: (ADR-147). The rest of the shared claim (the tiles, the uploads' scratch) is made again or is
#: the Ingest's.
SHARED_PARTS = (
    {"name": "shared-recipes", "subPath": "data/recipes"},
    {"name": "shared-model-settings", "subPath": "model-settings"},
    {"name": "shared-map-settings", "subPath": "map-settings"},
)
STOPPED_STORES = ("arcadedb",)
RUNNING_STORES = ("clickhouse", "clickhouse-keeper")
#: P9's own runs, which a restore must not run beside: a backup reads what is being replaced.
OWN_RUNS = ("backup", "backup-claims")


def _holds_a_shared_part(sub_path: str) -> bool:
    """A mount of the shared claim that holds a part of the set (the folder, or one above it)."""
    if not sub_path:
        return False
    return any(
        part["subPath"] == sub_path or part["subPath"].startswith(sub_path.rstrip("/") + "/")
        for part in SHARED_PARTS
    )


def writers(
    workloads: list[dict[str, Any]], paths: dict[str, list[str]] | None = None
) -> list[str]:
    """Every pod a restore refuses to run beside, from the render (rule 12: a workload added
    later is caught by the same rule): the store replaced stopped (ArcadeDB); every workload or
    Job (`values["jobs"]`) that mounts one of the set's claims (`storage.claims`, a `shared` mount
    naming its `claim`, in a container or an init container); every one that calls a store or a
    writer, by
    profile.yaml's `egress.paths` (the rows its egress is rendered from), so one that writes
    through the Conduit (the report sync, the Glass) is a writer too; and the backups' own runs.
    ClickHouse and its Keeper run through their restore and are not."""
    if paths is None:
        from harness.cloud_platform.settings import load_profile

        paths = load_profile().egress.paths
    names = {str(w["name"]) for w in workloads}
    found = set(STOPPED_STORES) & names
    for workload in workloads:
        mounts = [*(workload.get("shared") or [])]
        for init in workload.get("initContainers", []):
            mounts += init.get("shared") or []
        if any(m.get("claim") or _holds_a_shared_part(str(m.get("subPath", ""))) for m in mounts):
            found.add(str(workload["name"]))
    targets = found | {"clickhouse"}
    while True:
        more = {n for n in names - found - set(RUNNING_STORES) if targets & set(paths.get(n, []))}
        if not more:
            break
        found |= more
        targets |= more
    return sorted(found | set(OWN_RUNS))


def backups_values(
    config: OspreyConfig,
    platform: PlatformSettings,
    workloads: list[dict[str, Any]],
    environment: dict[str, Any],
    jobs: list[dict[str, Any]] | None = None,
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
    graph_db, analytics_db = database_names(environment)
    # Every container's: the region, the bucket and its key, which the runner needs to start.
    env: list[dict[str, Any]] = [
        {"name": "AWS_REGION", "value": platform.aws_region},
        {"name": "OSPREY_BACKUP_BUCKET",
         "secretKeyRef": {"name": OUTPUT_SECRET, "key": OUTPUT_KEYS["bucket"]}},
        {"name": "OSPREY_BACKUP_KMS_KEY",
         "secretKeyRef": {"name": OUTPUT_SECRET, "key": OUTPUT_KEYS["kms_key"]}},
    ]  # fmt: skip
    # ArcadeDB's, to the container that calls it alone, the backup's: the pod whose claim the
    # CronJob mounts, by name (the Service would hand the request to whichever copy answered, and
    # its zip would be on another claim); its password, a key of our Secret (P7b's default-deny on
    # our Secret's keys); the database the Conduit reads. The restore's ArcadeDB step calls nothing.
    arcadedb_env: list[dict[str, Any]] = [
        {"name": "OSPREY_BACKUP_ARCADEDB_HOST", "value": "arcadedb-0.arcadedb-headless"},
        {"name": "ARCADEDB_ROOT_PASSWORD", "secret": "ARCADEDB_ROOT_PASSWORD"},
        {"name": "ARCADEDB_DATABASE", "value": graph_db},
    ]
    # ClickHouse's, to the containers that call it alone, the backup's and restore-analytics':
    # its address, and its backup user (the runner's alone; the deployment's own is refused BACKUP).
    clickhouse_env: list[dict[str, Any]] = [
        *_env_from(environment, ["CLICKHOUSE_HOST", "CLICKHOUSE_HTTP_PORT", "CLICKHOUSE_CLUSTER"]),
        {"name": "CLICKHOUSE_USER", "value": CLICKHOUSE_BACKUP_USER},
        {"name": "CLICKHOUSE_PASSWORD",
         "secretKeyRef": {"name": BACKUP_SECRET, "key": BACKUP_SECRET_KEY}},
        {"name": "CLICKHOUSE_DATABASE", "value": analytics_db},
    ]  # fmt: skip
    return {
        "schedule": SCHEDULE,
        "image": api["image"],
        "serviceAccountName": SERVICE_ACCOUNT,
        "deadlineSeconds": DEADLINE_SECONDS,
        "resources": copy.deepcopy(api.get("resources") or {}),
        "env": env,
        # The audit's ruling 3: the shared claim's parts, beside the claims of their own.
        "shared": [dict(part) for part in SHARED_PARTS],
        "clickhouse": {"env": clickhouse_env},
        # The pods a restore refuses to run beside (the orchestrator's ruling 4), from the render.
        "writers": writers([*workloads, *(jobs or [])]),
        # The restore is proven for one copy of each store (Amendment 7); beyond it the render
        # refuses the restore's Jobs, in words naming P9b (the orchestrator's round 2, item 13).
        "restorable": int(arcadedb.get("replicas", 1)) == 1
        and int(clickhouse.get("replicas", 1)) == 1,
        "arcadedb": {
            "pod": "arcadedb-0",
            "backupsClaim": f"{claim['name']}-arcadedb-0",
            "databasesClaim": "databases-arcadedb-0",
            "database": graph_db,
            "image": arcadedb["image"],
            "resources": copy.deepcopy(arcadedb.get("resources") or {}),
            "env": arcadedb_env,
        },
    }


def add_backups(
    config: OspreyConfig, platform: PlatformSettings, values: dict[str, Any]
) -> dict[str, str]:
    """**The hook** (`render_cloud_platform` calls it once, with the values it is about to write):
    the backups added to `values` (the chart's `backups`, ArcadeDB's claim, ClickHouse's role, users
    file and backup user's password); returns the Terraform files it adds, `terraform/backups.tf`.
    A render without ArcadeDB and ClickHouse is returned unchanged."""
    found = backups_values(
        config, platform, values["workloads"], values["environment"], values.get("jobs") or []
    )
    if found is None:
        return {}
    irsa = platform.secrets.irsa
    if taken := {irsa.service_account, irsa.gateway_service_account} & {
        SERVICE_ACCOUNT,
        CLICKHOUSE_SERVICE_ACCOUNT,
    }:
        # Each pod under its own account (P7b's rule): the backups' accounts never the namespace's
        # IRSA account or the gateway's, or one name would be trusted by two roles.
        raise ValueError(
            f"secrets.irsa names {min(str(n) for n in taken)!r}, the backups' own account: "
            "name another"
        )
    values["backups"] = found
    deployment_user = str(values["environment"].get("CLICKHOUSE_USER", "default"))
    values["files"][CLICKHOUSE_USERS_FILE] = clickhouse_users(
        deployment_user, database_names(values["environment"])[1]
    )
    for key, source in RESTORE_GRAPH_FILES.items():
        values["files"][key] = (RESTORE_GRAPH_SOURCES / source).read_text(encoding="utf-8")
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
                    ("noncurrent_version_expiration", [("noncurrent_days", str(NONCURRENT_DAYS))]),
                ]),
                ("rule", [
                    ("id", _q("remove-expired-markers")),
                    ("status", _q("Enabled")),
                    ("filter", [("prefix", _q("sets/"))]),
                    ("expiration", [("expired_object_delete_marker", "true")]),
                ]),
            ]),
            ('data "aws_iam_policy_document" "backups_bucket"',
             policy_document(bucket_policy(bucket_arn, key_arn, role_arns))),
            ('resource "aws_s3_bucket_policy" "backups"', [
                ("bucket", "aws_s3_bucket.backups.id"),
                ("policy", "data.aws_iam_policy_document.backups_bucket.json"),
            ]),
            *roles,
            # The backup user's password, a Secret of its own (never the shared one, loaded whole by
            # the Conduit and the workers): ClickHouse and the backup's pods alone name it.
            ('resource "random_password" "clickhouse_backup"',
             [("length", "32"), ("special", "false")]),
            _secret(BACKUP_SECRET,
                    # Its key bare, as platform's Terraform writes its own (and its reader takes).
                    {BACKUP_SECRET_KEY: "random_password.clickhouse_backup.result"}),
            _secret(OUTPUT_SECRET, {
                OUTPUT_KEYS["bucket"]: "aws_s3_bucket.backups.bucket",
                OUTPUT_KEYS["kms_key"]: "aws_kms_key.backups.arn",
            }),
        ],
    )  # fmt: skip
