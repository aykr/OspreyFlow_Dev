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
    check,
    declared_resources,
    main,
)
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig

NAMESPACE = "ospreyflow-poc"
PREFIX = "ospreyflow-poc-1a2b3c4d-"


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
        "disks": {"Volumes": [_disk("vol-0another", "another-tenant", "data-db-0")]},
        "state": "module.namespace.aws_eks_access_entry.team\nmodule.namespace.aws_iam_role.team\n",
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
        volumes=given.get("volumes"),
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
        # Annotated as the release's by Helm, with no label of ours.
        (
            _object("ServiceAccount", "ospreyflow-extra",
                    annotations={"meta.helm.sh/release-name": "ospreyflow"}),
            "ServiceAccount/ospreyflow-extra",
        ),
    ],
    ids=["statefulset-claim", "kept-shared-claim", "kept-ingest-claim", "our-secret", "labelled",
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
    assert "aws ec2 delete-volume --volume-id vol-0abc" in item.why


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
        "module.ospreyflow.kubernetes_service_account.service",
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
            "--disks", str(tmp_path / "disks.json"), "--state", str(tmp_path / "state.txt"),
            "--terraform", str(folder), "--buckets", str(tmp_path / "buckets.txt"),
            "--bucket-prefix", PREFIX]  # fmt: skip
    assert main(argv) == 0
    (tmp_path / "state.txt").write_text("aws_iam_role.service\n", encoding="utf-8")
    assert main(argv) == 1
