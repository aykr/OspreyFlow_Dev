"""The decommission check (`harness/cloud_platform/decommission_check.py`, ADR-148 Amendment 5):
after the rendered `DECOMMISSION.md` has run, nothing the deployment made is left in its namespace,
on the platform's disks, in the namespace's Terraform state or among the account's buckets, while
what is the platform's own is left alone.

Each leftover is planted in the shape its source prints it (`kubectl get <kind> -o json`'s `List`,
`aws ec2 describe-volumes`'s `Volumes`, `tofu state list`'s addresses, one bucket name a line), and
each is named by the branch under test alone (rule 15). The things `helm uninstall` leaves on
purpose are among them: a StatefulSet's claims and the claims the chart keeps
(`helm.sh/resource-policy: keep`), which hold the deployment's data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.cloud_platform.decommission_check import (
    DISK_NAMESPACE_TAG,
    Leftovers,
    ListingRefused,
    check,
    declared_resources,
    main,
)
from harness.cloud_platform_backups import BUCKET_SUFFIX, KEPT_AT_DECOMMISSION
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig

NAMESPACE = "ospreyflow-poc"
PREFIX = "ospreyflow-poc-1a2b3c4d-"
#: The cluster's account (synthetic), which holds its disks; the client platform's region.
ACCOUNT, REGION = "210987654321", "eu-west-2"


@pytest.fixture(scope="module")
def rendered() -> dict[str, str]:
    config = OspreyConfig.model_validate(
        yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    )
    return render(config, resolver=_resolver).artefacts


@pytest.fixture(scope="module")
def values(rendered: dict[str, str]) -> dict[str, Any]:
    return yaml.safe_load(rendered["values.yaml"])


@pytest.fixture(scope="module")
def terraform(rendered: dict[str, str]) -> dict[str, str]:
    return {
        k.removeprefix("terraform/"): v for k, v in rendered.items() if k.startswith("terraform/")
    }


def _list(*items: dict[str, Any]) -> dict[str, Any]:
    return {"apiVersion": "v1", "kind": "List", "items": list(items), "metadata": {}}


def _object(kind: str, name: str, labels: dict[str, str] | None = None, **extra: Any) -> dict:
    return {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels or {}, **extra},
    }


def _disk(volume: str, namespace: str, claim: str) -> dict[str, Any]:
    return {"VolumeId": volume, "State": "available", "Tags": [
        {"Key": DISK_NAMESPACE_TAG, "Value": namespace},
        {"Key": "kubernetes.io/created-for/pvc/name", "Value": claim},
        {"Key": "ebs.csi.aws.com/cluster", "Value": "true"},
    ]}  # fmt: skip


def _clean() -> dict[str, Any]:
    """What the namespace holds before the deployment and after it: the platform's own, one
    listing a kind as the runbook takes them; its Terraform folder's own resources; another
    tenant's disk."""
    return {
        "objects": [
            _list(_object("ServiceAccount", "default")),
            _list(_object("ConfigMap", "kube-root-ca.crt")),
            _list(_object("Secret", "platform-team-registry-pull", {"owner": "platform-team"})),
        ],
        "disks": {
            "Account": ACCOUNT,
            "Region": REGION,
            "Volumes": [
                _disk("vol-0another", "another-tenant", "data-db-0"),
                # The namespace's own disk of a claim that is not the deployment's (the platform's).
                _disk("vol-0platform", NAMESPACE, "platform-team-scratch"),
            ],
        },
        # The platform's own resources in the same folder: in a module of its own, and at the
        # folder's root beside ours, of a type and name the render does not declare.
        "state": "module.namespace.aws_eks_access_entry.team\nmodule.namespace.aws_iam_role.team\n"
        "aws_iam_role.platform_team_reader\n",
        "buckets": "someone-elses-bucket\nospreyflow-dev-9f9f9f9f-media\n",
    }


def _check(values: dict[str, Any], terraform: dict[str, str], given: dict[str, Any]) -> Leftovers:
    return check(
        values,
        objects=given["objects"],
        state=given["state"],
        terraform=terraform,
        buckets=given["buckets"],
        bucket_prefix=PREFIX,
        disks=given["disks"],
        disks_account=ACCOUNT,
        volumes=given.get("volumes"),
        module=given.get("module"),
    )


def test_a_namespace_holding_only_the_platform_s_own_passes(
    values: dict[str, Any], terraform: dict[str, str]
) -> None:
    found = _check(values, terraform, _clean())
    assert found.items == []
    # What is not the deployment's is said to be left alone, not passed over in silence: the
    # namespace's own objects and the platform's own resources in the same Terraform folder.
    assert sorted(found.not_ours) == [
        "ConfigMap/kube-root-ca.crt", "Secret/platform-team-registry-pull",
        "ServiceAccount/default",
        "terraform/aws_iam_role.platform_team_reader",
        "terraform/module.namespace.aws_eks_access_entry.team",
        "terraform/module.namespace.aws_iam_role.team",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("plant", "named"),
    [
        # A StatefulSet's claim, which `helm uninstall` never removes; its labels are the
        # StatefulSet's selector's, as the controller gives them, not the chart's.
        (
            _object("PersistentVolumeClaim", "data-clickhouse-0",
                    {"app.kubernetes.io/name": "clickhouse",
                     "app.kubernetes.io/instance": "ospreyflow"}),
            "PersistentVolumeClaim/data-clickhouse-0",
        ),
        # The claims the chart keeps on uninstall, known by name alone (no chart label).
        (
            _object("PersistentVolumeClaim", "ospreyflow-shared",
                    annotations={"helm.sh/resource-policy": "keep"}),
            "PersistentVolumeClaim/ospreyflow-shared",
        ),
        (
            _object("PersistentVolumeClaim", "ospreyflow-ingest",
                    annotations={"helm.sh/resource-policy": "keep"}),
            "PersistentVolumeClaim/ospreyflow-ingest",
        ),
        # Our Secret, which the install makes outside the chart and so carries no chart label.
        (_object("Secret", "ospreyflow-secrets"), "Secret/ospreyflow-secrets"),
        # Labelled ours by the chart.
        (
            _object("ConfigMap", "ospreyflow-env", {"app.kubernetes.io/part-of": "ospreyflow"}),
            "ConfigMap/ospreyflow-env",
        ),
        # What the namespace's Terraform writes, which carries no label of the chart's: the
        # managed stores' Secrets (the database's password among them) and the bucket role's
        # service account.
        (_object("Secret", "rds-postgresql-instance-output"),
         "Secret/rds-postgresql-instance-output"),
        (_object("Secret", "elasticache-redis"), "Secret/elasticache-redis"),
        (_object("Secret", "s3-bucket-output"), "Secret/s3-bucket-output"),
        (_object("ServiceAccount", "ospreyflow"), "ServiceAccount/ospreyflow"),
        # Helm's record of the release, kept by `helm uninstall --keep-history`.
        (_object("Secret", "sh.helm.release.v1.ospreyflow.v3", {"owner": "helm"}),
         "Secret/sh.helm.release.v1.ospreyflow.v3"),
        # Annotated as the release's by Helm, with no label of ours.
        (
            _object("ServiceAccount", "ospreyflow-extra",
                    annotations={"meta.helm.sh/release-name": "ospreyflow"}),
            "ServiceAccount/ospreyflow-extra",
        ),
    ],
    ids=["statefulset-claim", "kept-shared-claim", "kept-ingest-claim", "our-secret", "labelled",
         "rds-secret", "redis-secret", "s3-secret", "bucket-role-account", "helm-release",
         "helm-annotated"],
)  # fmt: skip
def test_a_leftover_in_the_namespace_is_named(
    values: dict[str, Any], terraform: dict[str, str], plant: dict[str, Any], named: str
) -> None:
    given = _clean()
    given["objects"].append(_list(plant))
    assert [item.what for item in _check(values, terraform, given).items] == [named]


def test_a_disk_kept_after_its_claim_is_named(
    values: dict[str, Any], terraform: dict[str, str]
) -> None:
    """A disk the EBS CSI driver made for one of the namespace's claims, still there once its claim
    and its volume object are gone (a Retain class, or a delete that did not finish): still billed,
    still holding the data. Another tenant's disk is not the deployment's."""
    given = _clean()
    given["disks"]["Volumes"].append(_disk("vol-0abc", NAMESPACE, "databases-arcadedb-0"))
    [item] = _check(values, terraform, given).items
    assert item.what == "disk/vol-0abc"
    assert "aws ec2 delete-volume --region eu-west-2 --volume-id vol-0abc" in item.why


def test_a_volume_object_kept_after_its_claim_is_named_where_it_may_be_listed(
    values: dict[str, Any], terraform: dict[str, str]
) -> None:
    given = _clean()
    given["volumes"] = _list(
        {"apiVersion": "v1", "kind": "PersistentVolume", "metadata": {"name": "pvc-0a1b2c3d"},
         "spec": {"claimRef": {"namespace": NAMESPACE, "name": "databases-arcadedb-0"},
                  "persistentVolumeReclaimPolicy": "Retain"},
         "status": {"phase": "Released"}},
        {"apiVersion": "v1", "kind": "PersistentVolume", "metadata": {"name": "pvc-another"},
         "spec": {"claimRef": {"namespace": "another-tenant", "name": "data"}}},
    )  # fmt: skip
    found = _check(values, terraform, given)
    assert [i.what for i in found.items] == ["PersistentVolume/pvc-0a1b2c3d"]


@pytest.mark.parametrize(
    "address",
    [
        "aws_iam_role.service",
        "aws_iam_policy.buckets",
        "aws_iam_role_policy_attachment.buckets",
        'aws_s3_bucket.store["media"]',
        "aws_db_instance.postgres",
        "kubernetes_service_account.service",
    ],
)
def test_a_resource_the_render_declares_left_in_the_state_is_named(
    values: dict[str, Any], terraform: dict[str, str], address: str
) -> None:
    """`tofu state list` prints one address a line, the platform's own resources among them; only
    those the rendered Terraform declares are the deployment's. An IAM role or policy is named as
    such, since it outlives the namespace."""
    given = _clean()
    given["state"] += f"{address}\n"
    [item] = _check(values, terraform, given).items
    assert item.what == f"terraform/{address}"
    if "aws_iam" in address:
        assert "IAM" in item.why


def test_a_kms_key_alias_is_named_as_such_when_the_render_makes_one(
    values: dict[str, Any], terraform: dict[str, str]
) -> None:
    """The render makes no KMS key today, so an alias in the state is the platform's; were it to
    make one, a leftover alias is named, as one that outlives the namespace."""
    given = _clean()
    given["state"] += "aws_kms_alias.store\n"
    assert _check(values, terraform, given).items == []
    with_alias = {**terraform, "kms.tf": 'resource "aws_kms_alias" "store" {\n}\n'}
    [item] = _check(values, with_alias, given).items
    assert item.what == "terraform/aws_kms_alias.store" and "KMS key alias" in item.why


def test_the_render_s_declared_resources_are_read_from_its_files(terraform: dict[str, str]) -> None:
    declared = declared_resources(terraform)
    assert {"aws_iam_role.service", "aws_iam_policy.buckets", "aws_s3_bucket.store",
            "kubernetes_service_account.service"} <= declared  # fmt: skip
    assert not [r for r in declared if r.startswith("aws_opensearch")]  # no domain in poc


def test_a_bucket_of_this_deployment_s_is_named(
    values: dict[str, Any], terraform: dict[str, str]
) -> None:
    given = _clean()
    given["buckets"] += f"{PREFIX}media\n"
    found = _check(values, terraform, given)
    assert [item.what for item in found.items] == [f"bucket/{PREFIX}media"]


def test_main_exits_1_on_a_leftover_and_0_on_none(tmp_path: Path, rendered: dict[str, str]) -> None:
    given = _clean()
    folder = tmp_path / "terraform"
    folder.mkdir()
    for name, text in rendered.items():
        if name.startswith("terraform/"):
            (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "values.yaml").write_text(rendered["values.yaml"], encoding="utf-8")
    objects = []
    for n, listing in enumerate(given["objects"]):
        objects += ["--objects", str(tmp_path / f"objects-{n}.json")]
        (tmp_path / f"objects-{n}.json").write_text(json.dumps(listing), encoding="utf-8")
    (tmp_path / "disks.json").write_text(json.dumps(given["disks"]), encoding="utf-8")
    (tmp_path / "state.txt").write_text(given["state"], encoding="utf-8")
    (tmp_path / "buckets.txt").write_text(given["buckets"], encoding="utf-8")
    argv = ["--values", str(tmp_path / "values.yaml"), *objects,
            "--disks", str(tmp_path / "disks.json"), "--disks-account", ACCOUNT,
            "--state", str(tmp_path / "state.txt"),
            "--terraform", str(folder), "--buckets", str(tmp_path / "buckets.txt"),
            "--bucket-prefix", PREFIX]  # fmt: skip
    assert main(argv) == 0
    (tmp_path / "state.txt").write_text("aws_iam_role.service\n", encoding="utf-8")
    assert main(argv) == 1
    (tmp_path / "disks.json").write_text(json.dumps({"Volumes": []}), encoding="utf-8")
    assert main(argv) == 2


def test_a_calico_policy_s_removal_names_its_api_group(
    values: dict[str, Any], terraform: dict[str, str]
) -> None:
    given = _clean()
    policy = _object("NetworkPolicy", "default.ospreyflow-allow-egress",
                     {"app.kubernetes.io/part-of": "ospreyflow"})  # fmt: skip
    policy["apiVersion"] = "projectcalico.org/v3"
    given["objects"].append(_list(policy))
    [item] = _check(values, terraform, given).items
    assert item.why == (
        f"kubectl -n {NAMESPACE} delete networkpolicy.projectcalico.org "
        "default.ospreyflow-allow-egress"
    )


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (lambda d: d.pop("Volumes"), "holds no Volumes"),
        (lambda d: d.update(Region="eu-west-1"), "not the platform's 'eu-west-2'"),
        (lambda d: d.update(Account="111111111111"), "not the cluster's"),
        (lambda d: d.pop("Account"), "not the cluster's"),
    ],
    ids=["no-volumes", "other-region", "other-account", "no-account"],
)
def test_a_disks_listing_it_cannot_vouch_for_is_refused(
    values: dict[str, Any], terraform: dict[str, str], change: Any, said: str
) -> None:
    """`describe-volumes` answers `[]` for an account or region that holds none of the cluster's
    disks, and a listing with no answer at all must not read as nothing left either."""
    given = _clean()
    change(given["disks"])
    with pytest.raises(ListingRefused, match=said):
        _check(values, terraform, given)


@pytest.mark.parametrize(
    ("address", "module", "ours"),
    [
        ("aws_iam_role.service", None, True),
        ("module.ospreyflow.aws_iam_role.service", None, False),
        ("module.ospreyflow.aws_iam_role.service", "ospreyflow", True),
        ("aws_iam_role.service", "ospreyflow", False),
        # The platform's own resource of the same type and name, in a module of its own.
        ("module.namespace.aws_iam_role.service", "ospreyflow", False),
        ("module.ospreyflow.module.inner.aws_iam_role.service", "ospreyflow", False),
    ],
)
def test_only_the_deployment_s_place_in_the_state_is_its_own(
    values: dict[str, Any], terraform: dict[str, str], address: str, module: str | None,
    ours: bool,
) -> None:  # fmt: skip
    given = _clean()
    given["state"] += f"{address}\n"
    given["module"] = module
    found = _check(values, terraform, given)
    assert [i.what for i in found.items] == ([f"terraform/{address}"] if ours else [])


def test_a_left_bucket_s_removal_names_its_region_and_step_6(
    values: dict[str, Any], terraform: dict[str, str]
) -> None:
    """`rb --force` cannot empty a versioned bucket; the removal points back to step 6."""
    given = _clean()
    given["buckets"] += f"{PREFIX}media\n"
    [item] = _check(values, terraform, given).items
    assert "step 6" in item.why
    assert f"aws s3api delete-bucket --region {REGION} --bucket {PREFIX}media" in item.why


@pytest.mark.parametrize("address", list(KEPT_AT_DECOMMISSION))
def test_the_backups_bucket_and_its_key_are_kept_never_left_behind(
    values: dict[str, Any], terraform: dict[str, str], address: str
) -> None:
    """ADR-148 Amendment 7: the decommission's one named exception. Each, in the state or among the
    buckets, is reported as kept and the check still passes; anything else of ours still fails it."""
    with_backups = {**terraform, "backups.tf": _backups_tf()}
    given = _clean()
    given["state"] += f"{address}\n"
    given["buckets"] += f"{PREFIX}{BUCKET_SUFFIX}\n"
    found = _check(values, with_backups, given)
    assert found.items == []
    assert f"terraform/{address}" in found.kept and f"bucket/{PREFIX}{BUCKET_SUFFIX}" in found.kept
    given["state"] += "aws_iam_role.backup\naws_iam_role.backup_clickhouse\n"
    given["buckets"] += f"{PREFIX}media\n"
    found = _check(values, with_backups, given)
    assert [i.what for i in found.items] == ["terraform/aws_iam_role.backup",
                                             "terraform/aws_iam_role.backup_clickhouse", f"bucket/{PREFIX}media"]


def test_the_runbook_keeps_the_backups_and_says_how_to_remove_them(rendered: dict[str, str]) -> None:
    text = rendered["DECOMMISSION.md"] if "DECOMMISSION.md" in rendered else next(
        v for k, v in rendered.items() if k.endswith("DECOMMISSION.md"))
    # `${PREFIX}`, fenced: bash reads `$PREFIXbackups` as an empty variable of that name (R1).
    assert f"s3://${{PREFIX}}{BUCKET_SUFFIX}/sets/" in text and "$PREFIXbackups" not in text
    for kept in KEPT_AT_DECOMMISSION:
        assert kept in text
    removal = text.split("## 9.", 1)[1].split("## 10.", 1)[0]
    order = ["delete-bucket-policy", "delete-objects", "delete-bucket ", "describe-key", "put-key-policy",
             "schedule-key-deletion"]  # fmt: skip
    assert [removal.index(step) for step in order] == sorted(removal.index(step) for step in order)
    # The key by its ARN, never the alias, where KMS takes only an ID or ARN.
    assert '--key-id "$KEY"' in removal and "put-key-policy --region \"$REGION\" --key-id \"alias/" not in removal
    step7 = text.split("## 7.", 1)[1].split("## 8.", 1)[0]
    assert 'tofu state rm "$M$kept"' in step7 and 'test "$removed" -gt 0' in step7, "module-aware, and a guard"
    assert '"NoncurrentDays": 7' in step7 and "ExpiredObjectDeleteMarker" in step7
    retention = text.split("## 7.", 1)[1].split("## 8.", 1)[0]
    assert retention.index("put-bucket-lifecycle-configuration") < retention.index("tofu state rm")
    assert "## 10. Restoring a kept set" in text and "BackupRolesOnly" in text and "tofu import" in text


def _backups_tf() -> str:
    """backups.tf as `harness.cloud_platform_backups.backups_terraform` writes it for the poc fixture,
    so a resource it gains is checked here too."""
    from harness.cloud_platform.settings import load_platform
    from harness.cloud_platform_backups import backups_terraform

    config = OspreyConfig.model_validate(yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8")))
    assert config.cloud_platform is not None
    return backups_terraform(config, load_platform(config.cloud_platform.platform))
