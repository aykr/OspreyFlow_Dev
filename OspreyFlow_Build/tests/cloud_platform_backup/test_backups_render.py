"""What the `cloud-platform` render writes for the backups (ADR-148 Amendment 7), held to what the
runner reads and what the Terraform makes, so the three never disagree (rule 12: each invariant
named by the test that fails without it)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
import yaml
from harness import cloud_platform_backups as backups
from services.api.platform_backup import Settings

from tests.cloud_platform_backup import rendered


@pytest.mark.parametrize("fixture", rendered.fixtures())
def test_arcadedb_writes_its_backups_onto_a_claim_of_its_own(fixture: str) -> None:
    arcadedb = next(w for w in rendered.values(fixture)["workloads"] if w["name"] == "arcadedb")
    claims = {c["mountPath"]: c for c in arcadedb["claims"]}
    assert claims[backups.ARCADEDB_BACKUPS]["name"] == "backups"
    assert claims[backups.ARCADEDB_BACKUPS]["size"] == claims["/home/arcadedb/databases"]["size"]
    assert backups.ARCADEDB_BACKUPS not in [s["mountPath"] for s in arcadedb.get("scratch", [])]
    assert rendered.values(fixture)["backups"]["arcadedb"]["backupsClaim"] == "backups-arcadedb-0"


@pytest.mark.parametrize("fixture", rendered.fixtures())
def test_every_setting_the_runner_needs_is_rendered(fixture: str) -> None:
    """The runner refuses without its bucket, key and region; each is in the CronJob's env."""
    values = rendered.values(fixture)
    names = {e["name"] for e in values["backups"]["env"]}
    with pytest.raises(Exception, match="not set"):
        Settings.from_env({})
    for needed in ("OSPREY_BACKUP_BUCKET", "OSPREY_BACKUP_KMS_KEY", "AWS_REGION",
                   "OSPREY_BACKUP_ARCADEDB_HOST", "ARCADEDB_ROOT_PASSWORD", "CLICKHOUSE_HOST",
                   "CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD", "CLICKHOUSE_CLUSTER"):  # fmt: skip
        assert needed in names, needed
    # Each `config:` is a key of the ConfigMap; each `secret:` one of our Secret's keys.
    for item in values["backups"]["env"]:
        if "config" in item:
            assert item["config"] in values["environment"], item
        if "secret" in item:
            assert item["secret"] in values["secrets"]["keys"], item


@pytest.mark.parametrize("fixture", rendered.fixtures())
def test_each_secret_the_backup_reads_is_one_the_terraform_writes(fixture: str) -> None:
    text = rendered.terraform(fixture)
    for item in rendered.values(fixture)["backups"]["env"]:
        ref = item.get("secretKeyRef")
        if ref:
            assert ref["name"] in (backups.OUTPUT_SECRET, backups.BACKUP_SECRET), ref
            resource = ref["name"].replace("-", "_")
            block = re.search(rf'resource "kubernetes_secret" "{resource}" \{{(.*?)\n\}}', text, re.S)
            assert block and re.search(rf'\b"?{ref["key"]}"?\s*=', block.group(1)), ref


def test_the_backup_pod_is_given_no_other_secret() -> None:
    """Not the whole Secret (`envFrom`): the two passwords it uses, by name (Amendment 1 item 3):
    ArcadeDB's and ClickHouse's backup user's, never the deployment's own ClickHouse user's."""
    values = rendered.values()
    secret_items = [e for e in values["backups"]["env"] if "secret" in e]
    assert [e["secret"] for e in secret_items] == ["ARCADEDB_ROOT_PASSWORD"]
    own = [e for e in values["backups"]["env"] if (e.get("secretKeyRef") or {}).get("name") == backups.BACKUP_SECRET]
    assert [e["name"] for e in own] == ["CLICKHOUSE_PASSWORD"]
    env = {e["name"]: e.get("value") for e in values["backups"]["env"]}
    assert env["CLICKHOUSE_USER"] == backups.CLICKHOUSE_BACKUP_USER != values["environment"]["CLICKHOUSE_USER"]


def test_the_backup_runs_in_the_conduits_image_from_the_profiles_registry() -> None:
    values = rendered.values()
    api = next(w for w in values["workloads"] if w["name"] == "api")
    assert values["backups"]["image"] == api["image"]
    assert values["backups"]["serviceAccountName"] == backups.SERVICE_ACCOUNT != api["serviceAccountName"]


@pytest.mark.parametrize("account", list(backups.ROLE_SUFFIX))
def test_each_backup_role_trusts_its_own_service_account_for_sts_alone(account: str) -> None:
    text = rendered.terraform()
    ref = backups.ROLE_SUFFIX[account].replace("-", "_")
    trust = re.search(rf'data "aws_iam_policy_document" "{ref}_trust" \{{(.*?)\n\}}', text, re.DOTALL)
    assert trust is not None
    assert f'"system:serviceaccount:${{var.namespace}}:{account}"' in trust.group(1)
    assert '"${var.eks_oidc_issuer}:sub"' in trust.group(1) and '"${var.eks_oidc_issuer}:aud"' in trust.group(1)
    assert '"sts.amazonaws.com"' in trust.group(1) and "AssumeRoleWithWebIdentity" in trust.group(1)
    assert trust.group(1).count('test     = "StringEquals"') == 2


def _documents() -> list[tuple[str, dict[str, Any]]]:
    bucket, key = "${aws_s3_bucket.backups.arn}", "${aws_kms_key.backups.arn}"
    roles = ["${aws_iam_role.backup.arn}", "${aws_iam_role.backup_clickhouse.arn}"]
    policies = backups.role_policies(bucket, key, "eu-west-2")
    return [
        ("backups_bucket", backups.bucket_policy(bucket, key, roles)),
        ("backups_key", backups.key_policy("arn:aws:iam::${data.aws_caller_identity.backups.account_id}:root",
                                           roles, "eu-west-2")),
        ("backup_policy", policies[backups.SERVICE_ACCOUNT]),
        ("backup_clickhouse_policy", policies[backups.CLICKHOUSE_SERVICE_ACCOUNT]),
    ]  # fmt: skip


@pytest.mark.parametrize(("document", "policy"), _documents(), ids=[d for d, _ in _documents()])
def test_the_terraform_writes_the_policies_the_stand_in_holds(document: str, policy: dict[str, Any]) -> None:
    """Each statement of each policy is a statement block of its document, actions, resources and
    every condition, so the stand-in's refusals are the platform's."""
    text = rendered.terraform()
    block = re.search(rf'data "aws_iam_policy_document" "{document}" \{{(.*?)\n\}}', text, re.DOTALL)
    assert block is not None, document
    assert block.group(1).count("statement {") == len(policy["Statement"]), document
    for statement in policy["Statement"]:
        actions = statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
        assert json.dumps(actions) in block.group(1), (document, actions)
        for operator, keys in statement.get("Condition", {}).items():
            for key in keys:
                assert f'"{operator}"' in block.group(1) and f'"{key}"' in block.group(1)


def test_each_role_reaches_its_own_prefix_alone() -> None:
    """The orchestrator's ruling 1(b): ClickHouse's role, `sets/*/clickhouse/*`; the runner's, the
    graph's zip, the claims and the manifest. Neither holds the other's."""
    policies = backups.role_policies("arn:aws:s3:::b", "arn:aws:kms:eu-west-2:1:key/k", "eu-west-2")

    def objects(account: str) -> set[str]:
        return {r for s in policies[account]["Statement"] if "s3:PutObject" in s["Action"] for r in s["Resource"]}

    assert objects(backups.CLICKHOUSE_SERVICE_ACCOUNT) == {"arn:aws:s3:::b/sets/*/clickhouse/*"}
    assert objects(backups.SERVICE_ACCOUNT) == {
        "arn:aws:s3:::b/sets/*/arcadedb/*", "arn:aws:s3:::b/sets/*/claims/*", "arn:aws:s3:::b/sets/*/manifest.json"}
    for account in policies:
        kms = next(s for s in policies[account]["Statement"] if s["Action"][0].startswith("kms:"))
        assert kms["Condition"] == {"StringEquals": {"kms:ViaService": "s3.eu-west-2.amazonaws.com"}}


def test_the_keys_own_policy_lets_the_account_administer_the_roles_use_and_nobody_delete() -> None:
    """The orchestrator's ruling 7: the account's administrators never use the key and nobody
    schedules its deletion (section 9 of the decommission replaces the policy first); the two roles
    use it through S3 in the region alone."""
    roles = ["arn:aws:iam::1:role/r1", "arn:aws:iam::1:role/r2"]
    policy = backups.key_policy("arn:aws:iam::1:root", roles, "eu-west-2")
    by_sid = {s["Sid"]: s for s in policy["Statement"]}
    administer = by_sid["Administer"]
    assert administer["Principal"] == {"AWS": ["arn:aws:iam::1:root"]}
    # By action, not by name: no wildcard that reaches use or a grant (kms:Create* holds CreateGrant).
    use = ("kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:ReEncryptFrom", "kms:CreateGrant",
           "kms:ScheduleKeyDeletion")  # fmt: skip
    import fnmatch

    assert not [a for a in administer["Action"] for u in use if fnmatch.fnmatchcase(u, a.replace("kms:", "kms:"))]
    assert {"kms:CreateAlias", "kms:DeleteAlias", "kms:PutKeyPolicy"} <= set(administer["Action"])
    use = by_sid["UseThroughS3"]
    assert use["Principal"] == {"AWS": roles} and use["Condition"]["StringEquals"]["kms:ViaService"] == "s3.eu-west-2.amazonaws.com"
    deny = by_sid["NeverScheduledForDeletion"]
    assert (deny["Effect"], deny["Principal"], deny["Action"]) == ("Deny", "*", ["kms:ScheduleKeyDeletion"])
    assert re.search(r"policy\s*=\s*data\.aws_iam_policy_document\.backups_key\.json", rendered.terraform())


def test_clickhouses_own_user_is_refused_the_buckets_and_the_backup_user_holds_them() -> None:
    """The orchestrator's ruling 1(a), after `osprey` read and overwrote sets through `s3()` on kind:
    the deployment's own user refused S3, URL and BACKUP; `backup` the runner's alone."""
    values = rendered.values()
    deployment_user = values["environment"]["CLICKHOUSE_USER"]
    users = values["files"][backups.CLICKHOUSE_USERS_FILE]
    own = re.search(rf"<{deployment_user}>(.*?)</{deployment_user}>", users, re.DOTALL)
    assert own is not None and "<query>REVOKE S3, URL, BACKUP ON *.*</query>" in own.group(1)
    backup = re.search(r"<backup>(.*?)</backup>", users, re.DOTALL)
    assert backup is not None and f'from_env="{backups.CLICKHOUSE_BACKUP_PASSWORD}"' in backup.group(1)
    assert "GRANT BACKUP, CLUSTER, S3 ON *.*" in backup.group(1) and "URL" not in backup.group(1)
    clickhouse = next(w for w in values["workloads"] if w["name"] == "clickhouse")
    assert {"key": backups.CLICKHOUSE_USERS_FILE, "mountPath": "/etc/clickhouse-server/users.d/backup-users.xml"} in clickhouse["files"]
    assert backups.CLICKHOUSE_BACKUP_PASSWORD not in values["secrets"]["keys"], "a Secret of its own"


def test_the_bucket_is_encrypted_by_its_own_key() -> None:
    text = rendered.terraform()
    assert re.search(r"kms_master_key_id\s*=\s*aws_kms_key\.backups\.arn", text)
    assert re.search(r"enable_key_rotation\s*=\s*true", text)
    assert re.search(r'bucket\s*=\s*"\$\{local\.prefix\}backups"', text)


def test_the_key_and_the_bucket_outlive_a_destroy_of_the_namespace() -> None:
    """spec/05_DEPLOYMENT.md §6.1: a backup must never become data nobody can read. The sets are
    S3's ciphertext under the backups key, so a `terraform destroy` that scheduled the key's
    deletion while the bucket still held them (S3 refuses to delete a bucket that is not empty)
    would leave every set unreadable thirty days later. Both are kept from a destroy."""
    text = rendered.terraform()
    for resource in ('resource "aws_kms_key" "backups"', 'resource "aws_s3_bucket" "backups"'):
        block = text.split(resource, 1)[1].split("\nresource ", 1)[0]
        assert re.search(r"lifecycle\s*\{\s*prevent_destroy\s*=\s*true\s*\}", block), resource


def test_clickhouse_writes_its_backup_as_the_backup_role_by_its_own_pod() -> None:
    """ClickHouse 25.8 takes no session token in `BACKUP … TO S3()` (Code 42 on osprey-p9), so it
    writes as its own backup role by its own pod's web identity: that role's service account, and the
    region its STS client is built for (without AWS_DEFAULT_REGION it asked sts.us-east-1, which the
    platform's egress does not reach, and wrote anonymously, refused)."""
    found = rendered.values()
    clickhouse = next(w for w in found["workloads"] if w["name"] == "clickhouse")
    assert clickhouse["serviceAccountName"] == backups.CLICKHOUSE_SERVICE_ACCOUNT
    env = {e["name"]: e.get("value") for e in clickhouse["env"]}
    assert env["AWS_DEFAULT_REGION"] == env["AWS_REGION"] == "eu-west-2"
    # No other workload is given either backup role's account.
    others = [w["name"] for w in found["workloads"] if w.get("serviceAccountName") in backups.ROLE_SUFFIX
              and w["name"] != "clickhouse"]  # fmt: skip
    assert others == []


def test_the_backup_roles_only_delete_is_clickhouses_own_lock_file() -> None:
    """The orchestrator's rulings of 11 November 2026: no delete but one. ClickHouse 25.8's BACKUP
    removes its own `.lock` at its end and fails without that (measured on osprey-p9), so ClickHouse's
    role may delete `sets/*/clickhouse/.lock` and nothing else; the runner's role, nothing; neither
    an object version."""
    bucket = "arn:aws:s3:::b"
    policies = backups.role_policies(bucket, "arn:aws:kms:eu-west-2:1:key/k", "eu-west-2")

    def deletes(account: str) -> list[tuple[str, list[str]]]:
        return [(a, s["Resource"]) for s in policies[account]["Statement"] for a in s["Action"]
                if "Delete" in a or a in ("s3:*", "*") or a.endswith(":*")]  # fmt: skip

    assert deletes(backups.CLICKHOUSE_SERVICE_ACCOUNT) == [("s3:DeleteObject", [f"{bucket}/sets/*/clickhouse/.lock"])]
    assert deletes(backups.SERVICE_ACCOUNT) == []
    text = rendered.terraform()
    for document in ("backup_policy", "backup_clickhouse_policy"):
        role = re.search(rf'data "aws_iam_policy_document" "{document}" \{{(.*?)\n\}}', text, re.DOTALL)
        assert role is not None
        assert "DeleteObjectVersion" not in role.group(1)
    assert len(re.findall(r'"s3:DeleteObject"', text.split('data "aws_iam_policy_document" "backups_bucket"')[0])) == 0


def test_the_bucket_is_versioned_so_an_overwrite_erases_nothing() -> None:
    """The orchestrator's ruling 2: every overwrite keeps the previous version until the lifecycle
    rule expires it, and no role holds DeleteObjectVersion; ClickHouse's lock is the one object a role
    may delete, so a delete marker can stand on nothing else."""
    text = rendered.terraform()
    versioning = re.search(r'resource "aws_s3_bucket_versioning" "backups" \{(.*?)\n\}', text, re.DOTALL)
    assert versioning is not None and re.search(r'status\s*=\s*"Enabled"', versioning.group(1))
    for document in ("backup_policy", "backup_clickhouse_policy"):  # the roles': no version is theirs to remove
        role = re.search(rf'data "aws_iam_policy_document" "{document}" \{{(.*?)\n\}}', text, re.DOTALL)
        assert role is not None and "Version" not in role.group(1).replace('"Version"', "")


def test_the_sets_expire_by_the_buckets_lifecycle_rule() -> None:
    text = rendered.terraform()
    rule = re.search(r'id\s*=\s*"expire-sets"(.*?)\n  \}', text, re.DOTALL)
    assert rule is not None, text
    assert re.search(r'prefix\s*=\s*"sets/"', rule.group(1))
    # The current versions' own expiry, not the noncurrent one's `noncurrent_days` (which this once
    # matched alone, so the rule's expiry could go and the test stay green).
    assert re.search(rf"expiration \{{\s*days\s*=\s*{backups.EXPIRE_DAYS}\s*\}}", rule.group(1))
    # The retention is the total (the orchestrator's ruling): an overwritten version is kept a
    # short window to recover it, not a second retention; expired delete markers are removed.
    assert re.search(rf"noncurrent_days\s*=\s*{backups.NONCURRENT_DAYS}\b", rule.group(1))
    assert backups.NONCURRENT_DAYS < backups.EXPIRE_DAYS
    markers = re.search(r'id\s*=\s*"remove-expired-markers"(.*?)\n  \}', text, re.DOTALL)
    assert markers is not None and re.search(r"expired_object_delete_marker\s*=\s*true", markers.group(1))
    assert backups.EXPIRE_DAYS >= 30, "a month of failed runs before the last good set expires"


def test_a_decommission_keeps_the_bucket_and_its_key_and_nothing_else_of_the_backups() -> None:
    """What `decommission_check` reports as kept: each a resource backups.tf declares, the bucket
    and the key among them; the role, its service account and the Secret are not."""
    declared = set(re.findall(r'^resource "([^"]+)" "([^"]+)"', rendered.terraform(), re.MULTILINE))
    declared_names = {f"{kind}.{name}" for kind, name in declared}
    assert set(backups.KEPT_AT_DECOMMISSION) <= declared_names
    assert {"aws_kms_key.backups", "aws_s3_bucket.backups"} <= set(backups.KEPT_AT_DECOMMISSION)
    assert not [k for k in backups.KEPT_AT_DECOMMISSION if k.startswith(("aws_iam", "kubernetes_"))]


@pytest.mark.parametrize("fixture", rendered.fixtures())
def test_no_workload_but_clickhouse_and_the_backups_can_read_the_backup_users_password(fixture: str) -> None:
    """The lane-reviewer's round-2 blocker: the shared Secret is loaded whole (`envFrom`) by the
    Conduit, the workers, the report sync and the workspace, so the backup user's password is never
    one of its keys; it is a Secret of its own, which ClickHouse and the backup's own pods alone name."""
    values = rendered.values(fixture)
    assert backups.CLICKHOUSE_BACKUP_PASSWORD not in values["secrets"]["keys"]
    assert backups.CLICKHOUSE_BACKUP_PASSWORD not in values["secrets"].get("defaults", {})

    def readers(items: list[dict[str, Any]]) -> set[str]:
        return {w["name"] for w in items for e in w.get("env", [])
                if (e.get("secretKeyRef") or {}).get("name") == backups.BACKUP_SECRET
                or e.get("secret") == backups.CLICKHOUSE_BACKUP_PASSWORD}  # fmt: skip

    assert readers(values["workloads"] + values.get("jobs", [])) == {"clickhouse"}
    assert {e["secretKeyRef"]["name"] for e in values["backups"]["env"]
            if e["name"] == "CLICKHOUSE_PASSWORD"} == {backups.BACKUP_SECRET}  # fmt: skip
    text = rendered.terraform(fixture)
    assert f'resource "kubernetes_secret" "{backups.BACKUP_SECRET.replace("-", "_")}"' in text
    assert 'resource "random_password" "clickhouse_backup"' in text


def test_a_render_with_one_store_and_not_the_other_is_refused() -> None:
    values = rendered.values()
    workloads = [w for w in values["workloads"] if w["name"] != "clickhouse"]
    cfg = rendered.config()
    from harness.cloud_platform.settings import load_platform

    assert cfg.cloud_platform is not None
    with pytest.raises(ValueError, match="no clickhouse"):
        backups.backups_values(cfg, load_platform(cfg.cloud_platform.platform), workloads, values["environment"])


@pytest.mark.skipif(not rendered.has_the_diff(), reason="P9_render.diff (the platform lane's) not yet applied")
def test_the_render_carries_the_backups_itself() -> None:
    """Once the diff is applied: the render's own `backups`, ArcadeDB's claim and `backups.tf`."""
    files = rendered.artefacts()
    assert "terraform/backups.tf" in files
    values = yaml.safe_load(files["values.yaml"])
    assert values["backups"]["serviceAccountName"] == backups.SERVICE_ACCOUNT
