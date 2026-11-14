"""R1's decommission step 7 on kind, both choices modelled (the orchestrator's review of
platform-b's step-6 run sheet, 14 November 2026). Before this, `BACKUPS=destroy` was refused as
"not modelled", and R1's driver gave `BACKUPS=keep` whenever the choice was unset, which hid the
product's own "there is no default" refusal.

What a mistake would do, and the case that catches it (rule 12):
- destroy leaving the sets or the key usable, or removing what is not the deployment's:
  `test_destroy_removes_the_backups_and_schedules_the_key_and_nothing_else`;
- keep losing the sets: `test_keep_leaves_the_backups_bucket_and_its_key`;
- a destroy run twice, or over a key already pending deletion, going ahead where AWS refuses:
  `test_destroy_refuses_what_aws_refuses`;
- a full bucket deleted: `test_the_terraform_s_buckets_are_refused_while_they_hold_anything`;
- R1's keep hiding the product's refusal: `test_a_run_may_ask_for_no_choice`.

Step 7's stand-in runs over a folder standing in for the stand-in pod's `/data` (its own code, run
here), and the kubectl calls and the configuration it gives the S3 stand-in are recorded.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

GATES = Path(__file__).parents[1] / "process/lanes/platform/gates"
PREFIX = "ospreyflow-poc-1a2b3c4d-"
STEP = "7. The namespace's resources (the platform team's pull request)"


def _r1_kind():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(GATES))
    try:
        import r1_kind
    finally:
        sys.path.remove(str(GATES))
    return r1_kind


class Cluster:
    """The kind cluster as step 7 meets it: the stand-in's configuration and its disk, the calls."""

    def __init__(self, r1_kind: Any, tmp_path: Path) -> None:
        from harness.cloud_platform.terraform import BUCKETS

        self.data = tmp_path / "data"
        self.backups = f"{PREFIX}backups"
        self.buckets = [f"{PREFIX}{b}" for b in BUCKETS]
        for name in self.buckets:
            (self.data / name).mkdir(parents=True)  # step 6 emptied them
        (self.data / self.backups / "sets/20261114T0300Z").mkdir(parents=True)
        (self.data / self.backups / "sets/20261114T0300Z/arcadedb.zip").write_bytes(b"zip")
        (self.data / self.backups / "sets/20261114T0300Z/done").write_text("{}")
        (self.data / "platform-own-logs").mkdir()  # the platform's, no deployment prefix
        (self.data / "platform-own-logs/today.log").write_text("kept")
        self.config: dict[str, Any] = {
            "region": r1_kind.REGION,
            "roles": [{"arn": "arn:aws:iam::123456789012:role/ospreyflow-poc-service"}],
            "buckets": [{"name": n} for n in self.buckets]
            + [{"name": self.backups, "kms_key": r1_kind.KEY_ARN}],
            "keys": [{"arn": r1_kind.KEY_ARN, "policy": {"Statement": ["the deployment's"]}}],
            "domains": [{"host": r1_kind.SEARCH_HOST}],
        }
        self.calls: list[tuple[str, ...]] = []
        self.given: list[dict[str, Any]] = []

    def kubectl(self, *args: str, **_: Any) -> str:
        if "configmap" in args and "get" in args:
            return json.dumps(self.config)
        self.calls.append(args)
        return ""

    def s3_exec(self, code: str) -> str:
        done = subprocess.run(
            [sys.executable, "-I", "-c", code.replace("/data", str(self.data))],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
        if done.returncode:
            raise SystemExit(done.stderr.strip() or done.stdout.strip())
        return done.stdout

    def on_disk(self) -> set[str]:
        return {p.name for p in self.data.iterdir()}


@pytest.fixture
def cluster(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    r1_kind = _r1_kind()
    monkeypatch.setattr(r1_kind, "STATE", tmp_path / "state")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.delenv("WORK", raising=False)
    made = ["kubernetes_secret ospreyflow-secrets (secrets.tf)",
            "kubernetes_service_account ospreyflow (irsa.tf)"]  # fmt: skip
    r1_kind.save(prefix=PREFIX, terraform_made=made)
    c = Cluster(r1_kind, tmp_path)
    monkeypatch.setattr(r1_kind, "kubectl", c.kubectl)
    monkeypatch.setattr(r1_kind, "s3_exec", c.s3_exec)
    monkeypatch.setattr(r1_kind, "s3_standin", c.given.append)
    monkeypatch.setattr(r1_kind, "coredns", lambda names=None: None)
    c.r1 = r1_kind  # type: ignore[attr-defined]
    c.work = tmp_path / f"ospreyflow-{r1_kind.NS}"  # type: ignore[attr-defined]
    return c


def _shared_removals(r1_kind: Any) -> set[tuple[str, ...]]:
    """What the Terraform's removal deletes in the cluster, either way."""
    ns, managed = r1_kind.NS, r1_kind.MANAGED
    return {
        ("-n", ns, "delete", "secret", "ospreyflow-secrets", "--ignore-not-found"),
        ("-n", ns, "delete", "serviceaccount", "ospreyflow", "--ignore-not-found"),
        ("-n", managed, "delete", "statefulset", "opensearch", "--ignore-not-found"),
        ("-n", managed, "delete", "service", "opensearch", "--ignore-not-found"),
        ("-n", managed, "delete", "pvc", "-l", "app=opensearch", "--ignore-not-found"),
        ("delete", "mutatingwebhookconfiguration", "r1-irsa-standin", "--ignore-not-found"),
    }


def test_destroy_removes_the_backups_and_schedules_the_key_and_nothing_else(  # type: ignore[no-untyped-def]
    cluster,
) -> None:
    r1 = cluster.r1
    r1.decommission_resources("destroy", "")
    assert (cluster.work / "backups").read_text() == "destroy\n"
    # The backups bucket with every object, and the Terraform's buckets: gone. The platform's: kept.
    assert cluster.on_disk() == {"platform-own-logs"}
    assert (cluster.data / "platform-own-logs/today.log").read_text() == "kept"
    [config] = cluster.given
    assert config["buckets"] == [] and config["roles"] == [] and config["domains"] == []
    [key] = config["keys"]
    assert key["state"] == "PendingDeletion" and key["deletion_date"]
    root = "arn:aws:iam::123456789012:root"
    assert key["policy"]["Statement"] == [{
        "Sid": "Administer", "Effect": "Allow", "Principal": {"AWS": root},
        "Action": "kms:*", "Resource": "*"}]  # fmt: skip
    assert set(cluster.calls) == _shared_removals(r1)


def test_keep_leaves_the_backups_bucket_and_its_key(cluster) -> None:  # type: ignore[no-untyped-def]
    r1 = cluster.r1
    r1.decommission_resources("keep", "30")
    assert (cluster.work / "backups").read_text() == "keep\n"
    assert cluster.on_disk() == {cluster.backups, "platform-own-logs"}
    kept = cluster.data / cluster.backups / "sets/20261114T0300Z/arcadedb.zip"
    assert kept.read_bytes() == b"zip"
    [config] = cluster.given
    assert [b["name"] for b in config["buckets"]] == [cluster.backups]
    [key] = config["keys"]
    assert "state" not in key and key["policy"] == {"Statement": ["the deployment's"]}
    assert set(cluster.calls) == _shared_removals(r1)


@pytest.mark.parametrize(
    ("before", "says"),
    [
        ("bucket gone", "NoSuchBucket"),  # a destroy run twice
        ("key pending", "KMSInvalidStateException"),
        ("no key", "NotFoundException"),
    ],
)
def test_destroy_refuses_what_aws_refuses(  # type: ignore[no-untyped-def]
    cluster, before: str, says: str
) -> None:
    """Each refused before anything is touched: no file removed, nothing deleted, no choice
    recorded."""
    if before == "bucket gone":
        buckets = cluster.config["buckets"]
        cluster.config["buckets"] = [b for b in buckets if b["name"] != cluster.backups]
    elif before == "key pending":
        cluster.config["keys"][0]["state"] = "PendingDeletion"
    else:
        cluster.config["keys"] = []
    on_disk = cluster.on_disk()
    with pytest.raises(SystemExit, match=says):
        cluster.r1.decommission_resources("destroy", "")
    assert cluster.on_disk() == on_disk and cluster.calls == [] and cluster.given == []
    assert not (cluster.work / "backups").exists()


@pytest.mark.parametrize("choice", ["keep", "destroy"])
def test_the_terraform_s_buckets_are_refused_while_they_hold_anything(  # type: ignore[no-untyped-def]
    cluster, choice: str
) -> None:
    """`aws_s3_bucket` without force_destroy: BucketNotEmpty, so step 6's emptying is what lets the
    Terraform's buckets go. The stand-in's configuration is not changed."""
    (cluster.data / cluster.buckets[0] / "left.bin").write_bytes(b"x")
    with pytest.raises(SystemExit, match="BucketNotEmpty"):
        cluster.r1.decommission_resources(choice, "30")
    assert cluster.given == []
    assert (cluster.data / cluster.buckets[0] / "left.bin").exists()


def test_the_stand_in_step_runs_the_model_by_the_operator_s_choice(  # type: ignore[no-untyped-def]
    cluster, monkeypatch
) -> None:
    monkeypatch.setenv("BACKUPS", "destroy")
    monkeypatch.delenv("BACKUP_RETENTION_DAYS", raising=False)
    cluster.r1.stand_in("DECOMMISSION", STEP)
    assert cluster.on_disk() == {"platform-own-logs"}


def test_a_run_may_ask_for_no_choice(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`R1_BACKUPS=unset`: no choice given, so the run meets the product's "no default" refusal
    (step 7's block, and its stand-in, refuse an unset BACKUPS); with BACKUPS also set, refused."""
    r1 = _r1_kind()
    monkeypatch.delenv("BACKUPS", raising=False)
    monkeypatch.setenv("R1_BACKUPS", "unset")
    assert r1.operator_choices("DECOMMISSION") == {}
    with pytest.raises(SystemExit, match="no default"):
        r1.stand_in("DECOMMISSION", STEP)
    monkeypatch.setenv("BACKUPS", "keep")
    with pytest.raises(SystemExit, match="R1_BACKUPS=unset"):
        r1.operator_choices("DECOMMISSION")
    monkeypatch.delenv("R1_BACKUPS")
    assert r1.operator_choices("DECOMMISSION") == {}  # never over a choice already given
    monkeypatch.delenv("BACKUPS")
    assert r1.operator_choices("DECOMMISSION")["BACKUPS"] == "keep"  # R1's own, otherwise
