"""What the `cloud-platform` render writes for the backups (ADR-148 Amendment 7), held to what the
runner reads and what the Terraform makes, so the three never disagree (rule 12: each invariant
named by the test that fails without it)."""

from __future__ import annotations

import json
import re

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
            assert ref["name"] == backups.OUTPUT_SECRET
            block = re.search(r'resource "kubernetes_secret" "ospreyflow_backup_output" \{(.*?)\n\}', text, re.S)
            assert block and re.search(rf"\b{ref['key']}\s*=", block.group(1)), ref


def test_the_backup_pod_is_given_no_other_secret() -> None:
    """Not the whole Secret (`envFrom`): the two passwords it uses, by name (Amendment 1 item 3)."""
    values = rendered.values()
    secret_items = [e for e in values["backups"]["env"] if "secret" in e]
    assert sorted(e["secret"] for e in secret_items) == ["ARCADEDB_ROOT_PASSWORD", "CLICKHOUSE_PASSWORD"]


def test_the_backup_runs_in_the_conduits_image_from_the_profiles_registry() -> None:
    values = rendered.values()
    api = next(w for w in values["workloads"] if w["name"] == "api")
    assert values["backups"]["image"] == api["image"]
    assert values["backups"]["serviceAccountName"] == backups.SERVICE_ACCOUNT != api["serviceAccountName"]


def test_the_backup_role_trusts_its_own_service_account_for_sts_alone() -> None:
    text = rendered.terraform()
    trust = re.search(r'data "aws_iam_policy_document" "backup_trust" \{(.*?)\n\}', text, re.S)
    assert trust is not None
    assert f"system:serviceaccount:${{var.namespace}}:{backups.SERVICE_ACCOUNT}" in trust.group(1)
    assert '"sts.amazonaws.com"' in trust.group(1)
    assert "AssumeRoleWithWebIdentity" in trust.group(1)


def test_the_terraform_writes_the_policies_the_stand_in_holds() -> None:
    """Each statement of the two policies is a statement block of its document, actions,
    resources and every condition, so the stand-in's refusals are the platform's."""
    text = rendered.terraform()
    for document, policy in (
        ("backups_bucket", backups.bucket_policy("${aws_s3_bucket.backups.arn}", "${aws_kms_key.backups.arn}",
                                                 "${aws_iam_role.backup.arn}")),
        ("backup_role", backups.role_policy("${aws_s3_bucket.backups.arn}", "${aws_kms_key.backups.arn}")),
    ):  # fmt: skip
        block = re.search(rf'data "aws_iam_policy_document" "{document}" \{{(.*?)\n\}}', text, re.S)
        assert block is not None, document
        statements = block.group(1).count("statement {")
        assert statements == len(policy["Statement"]), document
        for statement in policy["Statement"]:
            actions = statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
            assert json.dumps(actions) in block.group(1), (document, actions)
            for operator, keys in statement.get("Condition", {}).items():
                for key in keys:
                    assert f'"{operator}"' in block.group(1) and f'"{key}"' in block.group(1)


def test_the_bucket_is_encrypted_by_its_own_key() -> None:
    text = rendered.terraform()
    assert re.search(r"kms_master_key_id\s*=\s*aws_kms_key\.backups\.arn", text)
    assert re.search(r"enable_key_rotation\s*=\s*true", text)
    assert re.search(r'bucket\s*=\s*"\$\{local\.prefix\}backups"', text)


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
