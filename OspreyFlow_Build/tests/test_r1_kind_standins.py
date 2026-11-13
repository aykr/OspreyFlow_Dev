"""R1's managed-store stand-ins (`process/lanes/platform/gates/r1_kind_standins.yaml`) are what the
client's platform is, not a figure of their own: the RDS stand-in's `max_connections` is the one the
Terraform renders into the parameter group (`harness.cloud_platform.connections`, ADR-114 Amendment
46), read at apply, so the poc manifest's `managed.rds` holds on kind as it would on AWS (case-b's
v052-r1 verifier, 13 November 2026)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

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
    sends to the S3/STS stand-in (where the domain is checked), and the stand-ins'
    certificate names it."""
    r1_kind = _r1_kind()
    host = r1_kind.SEARCH_HOST
    assert re.fullmatch(
        rf"vpc-{r1_kind.NS}-search-[a-z0-9]+\.{r1_kind.REGION}\.es\.amazonaws\.com", host
    )
    assert r1_kind.NAMES[host] == "s3-standin"


def test_the_terraform_stand_in_answers_the_domains_url(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Every expression the rendered poc Terraform's Secrets read has the apply's answer; the
    search secret's is the domain's endpoint over HTTPS (never a missing value the install
    stops on)."""
    from tests.harness.test_cloud_platform_render import _artefacts, _config

    r1_kind = _r1_kind()
    monkeypatch.setattr(r1_kind, "STATE", tmp_path)
    roles = {
        "ospreyflow": "arn:s",
        "ospreyflow-backup": "arn:b",
        "ospreyflow-backup-clickhouse": "arn:c",
    }
    values = r1_kind._terraform_values("ospreyflow-poc-x-", roles)
    tf = _artefacts(_config("poc"))["terraform/opensearch.tf"]
    expressions = [
        e.strip() for e in re.findall(r"^\s+\w+\s*=\s*(.+)$", tf.split("data = {", 1)[1], re.M)
    ]
    assert expressions == ['"https://${aws_opensearch_domain.search.endpoint}"']
    assert values[expressions[0]] == f"https://{r1_kind.SEARCH_HOST}"


def test_the_domain_admits_the_namespaces_role_alone_and_proxies_to_its_opensearch(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    """The stand-in's domain admits what the Terraform's access policy admits,
    `aws_iam_role.service` (the `ospreyflow` service account's role), never a backup role,
    and sends what it admits to the OpenSearch pod in the platform's namespace."""
    r1_kind = _r1_kind()
    jwks = '{"keys": []}'
    discovery = '{"issuer": "https://kubernetes.default.svc.cluster.local"}'
    monkeypatch.setattr(
        r1_kind, "kubectl", lambda *a, **k: jwks if a[-1] == "/openid/v1/jwks" else discovery
    )
    account = f"arn:aws:iam::{r1_kind.ACCOUNT}"
    roles = {
        "ospreyflow": f"{account}:role/ospreyflow-poc-service",
        "ospreyflow-backup": f"{account}:role/ospreyflow-poc-backup",
        "ospreyflow-backup-clickhouse": f"{account}:role/ospreyflow-poc-backup-clickhouse",
    }
    config = r1_kind.s3_config("ospreyflow-poc-x-", roles)
    assert config["domains"] == [
        {
            "host": r1_kind.SEARCH_HOST,
            "roles": [roles["ospreyflow"]],
            "upstream": f"http://opensearch.{r1_kind.MANAGED}.svc.cluster.local:9200",
        }
    ]


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
