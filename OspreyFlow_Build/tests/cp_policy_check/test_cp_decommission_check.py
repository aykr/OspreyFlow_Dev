"""The decommission check (`harness/cloud_platform/decommission_check.py`, ADR-148 Amendment 5):
after the rendered `DECOMMISSION.md` has run, nothing the deployment made is left in its namespace,
in the cluster's volumes, in the namespace's Terraform state or among the account's buckets.

Each leftover is planted in the shape its source prints it (`kubectl get … -o json`'s `List`,
`tofu state list`'s addresses, one bucket name a line), and each is named by the check alone
(rule 15). The things `helm uninstall` leaves on purpose are among them: a StatefulSet's claims and
the claims the chart keeps (`helm.sh/resource-policy: keep`), which hold the deployment's data.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.cloud_platform.decommission_check import Leftovers, check, main
from tools.cp_policy_check import FIXTURES, render_values

NAMESPACE = "ospreyflow-poc"
PREFIX = "ospreyflow-poc-1a2b3c4d-"


@pytest.fixture(scope="module")
def values() -> dict[str, Any]:
    rendered, _ = render_values(FIXTURES / "poc.yaml")
    return yaml.safe_load(rendered)


def _list(*items: dict[str, Any]) -> dict[str, Any]:
    return {"apiVersion": "v1", "kind": "List", "items": list(items), "metadata": {}}


def _object(kind: str, name: str, labels: dict[str, str] | None = None, **extra: Any) -> dict:
    return {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels or {}, **extra},
    }


#: What a namespace on the platform holds before the deployment and after it: the platform's own.
THE_PLATFORM_S = _list(
    _object("ServiceAccount", "default"),
    _object("ConfigMap", "kube-root-ca.crt"),
    _object("Secret", "platform-team-registry-pull", {"owner": "platform-team"}),
)


def _clean() -> dict[str, Any]:
    return {
        "objects": copy.deepcopy(THE_PLATFORM_S),
        "volumes": _list(),
        "state": "",
        "buckets": "someone-elses-bucket\nospreyflow-dev-9f9f9f9f-media\n",
    }


def _check(values: dict[str, Any], given: dict[str, Any]) -> Leftovers:
    return check(
        values,
        objects=given["objects"],
        volumes=given["volumes"],
        state=given["state"],
        buckets=given["buckets"],
        bucket_prefix=PREFIX,
    )


def test_a_namespace_holding_only_the_platform_s_own_passes(values: dict[str, Any]) -> None:
    found = _check(values, _clean())
    assert found.items == []
    # What is not the deployment's is said to be left alone, not passed over in silence.
    assert sorted(found.not_ours) == [
        "ConfigMap/kube-root-ca.crt", "Secret/platform-team-registry-pull", "ServiceAccount/default"
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("plant", "named"),
    [
        # A StatefulSet's claim, which `helm uninstall` never removes; its labels are the
        # StatefulSet's selector's, as the controller gives them, not the chart's.
        (
            _object(
                "PersistentVolumeClaim",
                "data-clickhouse-0",
                {
                    "app.kubernetes.io/name": "clickhouse",
                    "app.kubernetes.io/instance": "ospreyflow",
                },
            ),
            "PersistentVolumeClaim/data-clickhouse-0",
        ),
        # The claims the chart keeps on uninstall.
        (
            _object(
                "PersistentVolumeClaim",
                "ospreyflow-shared",
                {"app.kubernetes.io/part-of": "ospreyflow"},
                annotations={"helm.sh/resource-policy": "keep"},
            ),
            "PersistentVolumeClaim/ospreyflow-shared",
        ),
        (
            _object(
                "PersistentVolumeClaim",
                "ospreyflow-ingest",
                {"app.kubernetes.io/part-of": "ospreyflow"},
                annotations={"helm.sh/resource-policy": "keep"},
            ),
            "PersistentVolumeClaim/ospreyflow-ingest",
        ),
        # Our Secret, which the install makes outside the chart and so carries no chart label.
        (_object("Secret", "ospreyflow-secrets"), "Secret/ospreyflow-secrets"),
        # Anything else labelled ours.
        (
            _object("ConfigMap", "ospreyflow-env", {"app.kubernetes.io/part-of": "ospreyflow"}),
            "ConfigMap/ospreyflow-env",
        ),
    ],
    ids=["statefulset-claim", "kept-shared-claim", "kept-ingest-claim", "our-secret", "labelled"],
)
def test_a_leftover_in_the_namespace_is_named(
    values: dict[str, Any], plant: dict[str, Any], named: str
) -> None:
    given = _clean()
    given["objects"]["items"].append(plant)
    assert [item.what for item in _check(values, given).items] == [named]


def test_a_volume_kept_after_its_claim_is_named(values: dict[str, Any]) -> None:
    """A released volume whose claim was ours: its disk (an EBS volume) is still billed and still
    holds the data, whatever the class's reclaim policy said."""
    given = _clean()
    given["volumes"]["items"].append({
        "apiVersion": "v1", "kind": "PersistentVolume",
        "metadata": {"name": "pvc-0a1b2c3d"},
        "spec": {"claimRef": {"namespace": NAMESPACE, "name": "databases-arcadedb-0"},
                 "persistentVolumeReclaimPolicy": "Retain"},
        "status": {"phase": "Released"},
    })  # fmt: skip
    given["volumes"]["items"].append({
        "apiVersion": "v1", "kind": "PersistentVolume",
        "metadata": {"name": "pvc-another-tenant"},
        "spec": {"claimRef": {"namespace": "another-tenant", "name": "data"}},
    })  # fmt: skip
    assert [item.what for item in _check(values, given).items] == ["PersistentVolume/pvc-0a1b2c3d"]


@pytest.mark.parametrize(
    "address",
    [
        "aws_iam_role.service",
        "aws_iam_policy.buckets",
        "aws_iam_role_policy_attachment.buckets",
        "aws_kms_alias.store",
        'aws_s3_bucket.store["media"]',
        "aws_db_instance.postgres",
        "module.namespace.kubernetes_service_account.service",
    ],
)
def test_anything_left_in_the_terraform_state_is_named(
    values: dict[str, Any], address: str
) -> None:
    """`tofu state list` prints one address a line; after `tofu destroy` it prints none. An IAM role
    or policy and a KMS key alias are named as such, since each outlives the namespace."""
    given = _clean()
    given["state"] = f"{address}\n"
    [item] = _check(values, given).items
    assert item.what == f"terraform/{address}"
    if "aws_iam" in address:
        assert "IAM" in item.why
    if "aws_kms_alias" in address:
        assert "KMS key alias" in item.why


def test_a_bucket_of_this_deployment_s_is_named(values: dict[str, Any]) -> None:
    given = _clean()
    given["buckets"] += f"{PREFIX}media\n"
    assert [item.what for item in _check(values, given).items] == [f"bucket/{PREFIX}media"]


def test_main_exits_1_on_a_leftover_and_0_on_none(tmp_path: Path, values: dict[str, Any]) -> None:
    files = {}
    given = _clean()
    for key in ("objects", "volumes"):
        files[key] = tmp_path / f"{key}.json"
        files[key].write_text(json.dumps(given[key]), encoding="utf-8")
    for key in ("state", "buckets"):
        files[key] = tmp_path / f"{key}.txt"
        files[key].write_text(given[key], encoding="utf-8")
    values_file = tmp_path / "values.yaml"
    values_file.write_text(yaml.safe_dump(values), encoding="utf-8")
    argv = ["--values", str(values_file), "--bucket-prefix", PREFIX,
            *(f"--{k}={v}" for k, v in files.items())]  # fmt: skip
    assert main(argv) == 0
    files["state"].write_text("aws_iam_role.service\n", encoding="utf-8")
    assert main(argv) == 1
