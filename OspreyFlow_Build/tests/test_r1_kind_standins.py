"""R1's managed-store stand-ins (`process/lanes/platform/gates/r1_kind_standins.yaml`) are what the
client's platform is, not a figure of their own: the RDS stand-in's `max_connections` is the one the
Terraform renders into the parameter group (`harness.cloud_platform.connections`, ADR-114 Amendment
46), read at apply, so the poc manifest's `managed.rds` holds on kind as it would on AWS (case-b's
v052-r1 verifier, 13 November 2026)."""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

import pytest
import yaml
from harness.cloud_platform.connections import POSTGRES_MAX_CONNECTIONS

GATES = Path(__file__).parents[1] / "process/lanes/platform/gates"


def test_the_rds_stand_in_allows_what_the_parameter_group_sets() -> None:
    sys.path.insert(0, str(GATES))
    try:
        import r1_kind
    finally:
        sys.path.remove(str(GATES))
    docs = [d for d in yaml.safe_load_all(r1_kind.standins_text("pw")) if d]
    postgres = next(
        d for d in docs if d["kind"] == "StatefulSet" and d["metadata"]["name"] == "postgres"
    )
    args = postgres["spec"]["template"]["spec"]["containers"][0]["args"]
    assert f"max_connections={POSTGRES_MAX_CONNECTIONS}" in args
    raw = (GATES / "r1_kind_standins.yaml").read_text(encoding="utf-8")
    assert "max_connections=${MAX_CONNECTIONS}" in raw  # never a number kept beside the render's


# -- the OpenSearch domain on kind (v0.5.2, v052-searchkind; ADR-148 Amendment 13) -------------


def _r1_kind():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(GATES))
    try:
        import r1_kind
    finally:
        sys.path.remove(str(GATES))
    return r1_kind


def test_the_kind_deployment_searches_with_the_domain_as_the_poc_does() -> None:
    """R1's osprey.yaml is the poc's: since 3a the poc shape searches with its own OpenSearch
    domain, so kind's install renders the domain's Terraform, the search Jobs and
    OPENSEARCH_URL as a client's."""
    config = yaml.safe_load((GATES / "r1_kind_osprey.yaml").read_text(encoding="utf-8"))
    poc = yaml.safe_load(
        (Path(__file__).parent / "fixtures/cloud_platform/poc.yaml").read_text(encoding="utf-8")
    )
    assert config["cloud_platform"]["shape"] == "poc"
    assert config["components"]["search"] == poc["components"]["search"] == "opensearch"


def test_the_domains_host_answers_at_the_stand_in_inside_the_cluster() -> None:
    """The endpoint the Terraform gives the pods is the domain's own VPC name, which CoreDNS
    sends to the S3/STS stand-in (where the domain is checked); the stand-ins' certificate is
    made for every name in `NAMES` (`r1_kind.platform`), so naming it there names it in the
    certificate too."""
    r1_kind = _r1_kind()
    host = r1_kind.SEARCH_HOST
    assert re.fullmatch(
        rf"vpc-{r1_kind.NS}-search-[a-z0-9]+\.{r1_kind.REGION}\.es\.amazonaws\.com", host
    )
    assert r1_kind.NAMES[host] == "s3-standin"


def test_the_opensearch_behind_the_domain_is_the_poc_manifests_engine() -> None:
    """One OpenSearch pod behind the stand-in, of the engine the poc manifest names
    (OpenSearch_2.17), its security plugin off as the domain has no fine-grained access
    control, and nothing else in the cluster reaching it but the stand-in (its port is not
    the domain's 443)."""
    from harness.cloud_platform import manifest

    r1_kind = _r1_kind()
    docs = [d for d in yaml.safe_load_all(r1_kind.standins_text("pw")) if d]
    sts = next(
        d for d in docs if d["kind"] == "StatefulSet" and d["metadata"]["name"] == "opensearch"
    )
    container = sts["spec"]["template"]["spec"]["containers"][0]
    engine = manifest.load()["managed"]["opensearch"]["engine"]  # OpenSearch_2.17
    version = engine.removeprefix("OpenSearch_")
    assert re.fullmatch(
        rf"localhost:5001/opensearchproject/opensearch:{re.escape(version)}\.\d+",
        container["image"],
    )
    assert container["image"].removeprefix("localhost:5001/") in r1_kind.THIRD_PARTY
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["DISABLE_SECURITY_PLUGIN"] == "true" and env["discovery.type"] == "single-node"
    # Its disk carries the label decommission step 7 deletes it by.
    [claim] = sts["spec"]["volumeClaimTemplates"]
    assert claim["metadata"]["labels"] == {"app": "opensearch"}
    service = next(
        d for d in docs if d["kind"] == "Service" and d["metadata"]["name"] == "opensearch"
    )
    assert [p["port"] for p in service["spec"]["ports"]] == [9200]


def test_the_decommissions_terraform_removal_takes_the_domain_with_it(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Decommission step 7's stand-in: the domain goes with the Terraform (ADR-148 Amendment 13,
    no index backup), so the stand-in stops answering as it and the OpenSearch behind it is
    deleted with its disk."""
    r1_kind = _r1_kind()
    monkeypatch.setattr(r1_kind, "STATE", tmp_path)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("BACKUPS", "keep")
    monkeypatch.setenv("BACKUP_RETENTION_DAYS", "30")
    r1_kind.save(prefix="ospreyflow-poc-x-", terraform_made=[])
    calls: list[tuple[str, ...]] = []
    live = {
        "region": "eu-west-2",
        "roles": [{"arn": "r"}],
        "buckets": [{"name": "ospreyflow-poc-x-backups"}],
        "domains": [{"host": r1_kind.SEARCH_HOST, "roles": ["r"], "upstream": "u"}],
    }

    def kubectl(*args: str, **_: object) -> str:
        calls.append(args)
        return json.dumps(live) if "configmap" in args else ""

    given: list[dict] = []
    monkeypatch.setattr(r1_kind, "kubectl", kubectl)
    monkeypatch.setattr(r1_kind, "s3_exec", lambda code: "[]")
    monkeypatch.setattr(r1_kind, "s3_standin", given.append)
    r1_kind.stand_in("DECOMMISSION", "7. Remove what the Terraform made")
    assert given and given[0]["domains"] == [] and given[0]["roles"] == []
    deleted = [c for c in calls if c[:1] == ("-n",) and "delete" in c]
    assert (
        "-n",
        r1_kind.MANAGED,
        "delete",
        "statefulset",
        "opensearch",
        "--ignore-not-found",
    ) in deleted
    assert (
        "-n",
        r1_kind.MANAGED,
        "delete",
        "pvc",
        "-l",
        "app=opensearch",
        "--ignore-not-found",
    ) in deleted


def _step7(r1_kind, tmp_path: Path, monkeypatch) -> list[dict]:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(r1_kind, "STATE", tmp_path / "state")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    r1_kind.save(prefix="ospreyflow-poc-x-", terraform_made=[])
    live = {"region": "eu-west-2", "roles": [], "buckets": [], "domains": []}
    monkeypatch.setattr(
        r1_kind, "kubectl", lambda *a, **k: json.dumps(live) if "configmap" in a else ""
    )
    monkeypatch.setattr(r1_kind, "s3_exec", lambda code: "[]")
    given: list[dict] = []
    monkeypatch.setattr(r1_kind, "s3_standin", given.append)
    return given


def test_decommission_step_7_records_the_backups_choice_step_8_reads(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Step 8's last block refuses without `$WORK/backups`, which only step 7's platform block
    writes (`echo "$BACKUPS" > "$WORK/backups"`): the stand-in for step 7 writes it as that block
    does."""
    r1_kind = _r1_kind()
    _step7(r1_kind, tmp_path, monkeypatch)
    monkeypatch.setenv("BACKUPS", "keep")
    monkeypatch.setenv("BACKUP_RETENTION_DAYS", "30")
    r1_kind.stand_in("DECOMMISSION", "7. Remove what the Terraform made")
    assert (tmp_path / f"ospreyflow-{r1_kind.NS}" / "backups").read_text() == "keep\n"


@pytest.mark.parametrize(
    ("backups", "days", "says"),
    [
        (None, "30", "no default"),
        ("maybe", "30", "no default"),
        ("keep", None, "retention"),
        ("keep", "0", "retention"),
        ("destroy", None, "destroy"),
    ],
)
def test_decommission_step_7_refuses_what_its_block_refuses(
    backups, days, says, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """No choice, an unknown one, or keep without a retention stop step 7 before anything is
    removed, as the block's own `:?` and `case` do; destroy, which the stand-in does not model
    (R1 keeps), is refused by name rather than run as keep."""
    r1_kind = _r1_kind()
    given = _step7(r1_kind, tmp_path, monkeypatch)
    for name, value in (("BACKUPS", backups), ("BACKUP_RETENTION_DAYS", days)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit, match=says):
        r1_kind.stand_in("DECOMMISSION", "7. Remove what the Terraform made")
    assert given == [] and not (tmp_path / f"ospreyflow-{r1_kind.NS}" / "backups").exists()


def test_the_operator_brings_r1s_choice_to_the_decommission(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R1 keeps its backups (the brief: the decommission's leftovers checked, the bucket kept with
    the last set), so the driver gives the decommission BACKUPS=keep and a retention, as an
    operator would export them; never to the install, and never over a choice already in the
    environment."""
    r1_kind = _r1_kind()
    monkeypatch.delenv("BACKUPS", raising=False)
    monkeypatch.delenv("BACKUP_RETENTION_DAYS", raising=False)
    assert r1_kind.operator_choices("DECOMMISSION") == {
        "BACKUPS": "keep",
        "BACKUP_RETENTION_DAYS": "30",
    }
    assert r1_kind.operator_choices("INSTALL") == {}
    monkeypatch.setenv("BACKUPS", "destroy")
    assert r1_kind.operator_choices("DECOMMISSION") == {}


def _kind_render(tmp_path: Path, monkeypatch) -> Path:  # type: ignore[no-untyped-def]
    """R1's own osprey.yaml rendered on the kind platform settings, as `r1_kind.py` renders it."""
    from harness.render import render
    from tools.cp_policy_check import _resolver

    from schemas.deployment import OspreyConfig

    monkeypatch.setenv(
        "OSPREY_PLATFORM_FOLDERS", str(Path(__file__).parent / "fixtures/cloud_platform/platforms")
    )
    raw = yaml.safe_load((GATES / "r1_kind_osprey.yaml").read_text(encoding="utf-8"))
    folder = tmp_path / "render"
    for name, text in render(
        OspreyConfig.model_validate(raw), resolver=_resolver
    ).artefacts.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text)
    return folder


def test_the_terraform_stand_in_makes_the_domains_secret_and_admits_what_its_policy_admits(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Install step 2's stand-in, run over R1's own render: the search Secret the pods read is made
    with the domain's endpoint, and the domain admits exactly the principals the rendered access
    policy names, each mapped to its ARN as the apply would answer it (never a list of its own)."""
    r1_kind = _r1_kind()
    folder = _kind_render(tmp_path, monkeypatch)
    monkeypatch.setattr(r1_kind, "STATE", tmp_path / "state")
    applied: list[dict] = []
    configs: list[dict] = []
    discovery = '{"issuer": "https://kubernetes.default.svc.cluster.local"}'
    monkeypatch.setattr(
        r1_kind,
        "kubectl",
        lambda *a, **k: '{"keys": []}' if a[-1] == "/openid/v1/jwks" else discovery,
    )
    monkeypatch.setattr(r1_kind, "apply", applied.extend)
    monkeypatch.setattr(r1_kind, "s3_standin", configs.append)
    monkeypatch.setattr(r1_kind, "irsa_webhook", lambda roles: None)
    r1_kind.terraform(folder)

    tf = (folder / "terraform/opensearch.tf").read_text()
    secret = re.search(r'resource "kubernetes_secret" "\w+" \{\n(.*?)^\}\n', tf, re.S | re.M).group(
        1
    )  # type: ignore[union-attr]
    name = re.search(r'name\s*=\s*"([^"]+)"', secret).group(1)  # type: ignore[union-attr]
    [made] = [d for d in applied if d["kind"] == "Secret" and d["metadata"]["name"] == name]
    assert {k: base64.b64decode(v).decode() for k, v in made["data"].items()} == {
        "proxy_url": f"https://{r1_kind.SEARCH_HOST}"
    }

    policy = re.search(r'data "aws_iam_policy_document" "search" \{(.*?)\n\}', tf, re.S).group(1)  # type: ignore[union-attr]
    identifiers = re.findall(r"identifiers\s*=\s*\[(.*?)\]", policy)
    roles = r1_kind.state()["roles"]
    values = r1_kind._terraform_values(r1_kind.state()["prefix"], roles)
    admitted = [values[i.strip()] for group in identifiers for i in group.split(",")]
    [config] = configs
    assert [d["roles"] for d in config["domains"]] == [admitted]
    assert admitted == [roles["ospreyflow"]] and roles["ospreyflow-backup"] not in admitted
