"""The S3 and Athena sources a cloud-platform deployment declares (ADR-140 Amendment 21; L1.9 part 2):
`cloud_platform.connector_sources`, rendered into the Conduit's own egress rows on 443, its allow-list,
what Admin › Connections is told the render made, and the namespace role's read-only statements.

What a mistake would do, and the case that catches it (rule 12):
- a declared host reached by every pod that reaches connector hosts (the worker too), or by none —
  `test_each_declared_source_is_the_conduit_s_own_egress_row_on_443`;
- the Conduit's allow-list and the egress disagreeing on a host —
  `test_the_conduit_s_allow_list_and_what_admin_is_told_are_the_declaration`;
- a row to the results or a table's bucket, which the reader never reaches (the orchestrator's Q2,
  Q3) — `test_no_results_or_table_location_is_an_egress_host`;
- a connector host still given to the worker, which reads none (the orchestrator's addition a) —
  `test_the_worker_reaches_no_connector_host`;
- a `*` resource, or a write anywhere but the results location, in the role's statements —
  `test_the_role_s_statements_are_read_only_and_scoped`, and the render's own refusal of both,
  `test_a_wide_statement_is_refused_by_the_render` (planted at the call site);
- statements, rows or settings rendered with nothing declared —
  `test_nothing_is_rendered_with_no_source_declared`.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
import yaml
from harness.cloud_platform import CloudPlatformNotRenderable, terraform
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig

BUCKET_HOST = "synthetic-exports.s3.eu-west-2.amazonaws.com"
ATHENA_HOST = "athena.eu-west-2.amazonaws.com"


def _raw(name: str = "development-sources") -> dict[str, Any]:
    return yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))


def _artefacts(raw: dict[str, Any]) -> dict[str, str]:
    return render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts


def _values(raw: dict[str, Any]) -> dict[str, Any]:
    return yaml.safe_load(_artefacts(raw)["values.yaml"])


def _rows(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["name"]: row for row in values["egress"]["workloads"]}


def test_each_declared_source_is_the_conduit_s_own_egress_row_on_443() -> None:
    values = _values(_raw())
    rows = _rows(values)
    assert {BUCKET_HOST, ATHENA_HOST} <= set(rows["api"]["hosts"])
    holding = sorted(n for n, r in rows.items() if {BUCKET_HOST, ATHENA_HOST} & set(r.get("hosts", [])))
    assert holding == ["api"]
    ports = {h["host"]: h["ports"] for h in values["egress"]["hosts"]}
    assert ports[BUCKET_HOST] == [443] and ports[ATHENA_HOST] == [443]


def test_the_conduit_s_allow_list_and_what_admin_is_told_are_the_declaration() -> None:
    raw = _raw()
    environment = _values(raw)["environment"]
    assert environment["OSPREY_CONNECTOR_EGRESS"].split(",") == sorted([ATHENA_HOST, BUCKET_HOST])
    made = json.loads(environment["OSPREY_CONNECTOR_SOURCES"])
    assert made == OspreyConfig.model_validate(raw).cloud_platform.connector_sources.model_dump(
        mode="json"
    )
    assert "OSPREY_CONNECTOR_SOURCES" not in _values(raw)["secrets"]["keys"]


def test_a_declared_source_s_host_needs_its_networks() -> None:
    raw = _raw()
    del raw["cloud_platform"]["egress_nets"][BUCKET_HOST]
    with pytest.raises(CloudPlatformNotRenderable, match=re.escape(BUCKET_HOST)):
        _artefacts(raw)


def test_no_results_or_table_location_is_an_egress_host() -> None:
    """Athena reads the tables' objects and writes its results itself, as the role: the Conduit
    reaches Athena's host alone (`only_to` refuses any other), so neither bucket is a row."""
    values = _values(_raw())
    hosts = {h["host"] for h in values["egress"]["hosts"]}
    reached = {h for r in values["egress"]["workloads"] for h in r.get("hosts", [])}
    for bucket in ("synthetic-athena-results", "synthetic-lake"):
        assert not [h for h in hosts | reached if bucket in h], bucket
    assert not [h for h in values["environment"]["OSPREY_CONNECTOR_EGRESS"].split(",")
                if "synthetic-athena-results" in h or "synthetic-lake" in h]  # fmt: skip


def test_the_worker_reaches_no_connector_host() -> None:
    """Only the Conduit reads a connection (`read_into_file` and `check_connection` are called from
    `services/api/app.py` alone; the worker's jobs are supersede and resolve)."""
    raw = _raw()
    raw["cloud_platform"]["connector_hosts"] = ["db.example.org:5432"]
    raw["cloud_platform"]["egress_nets"]["db.example.org"] = ["198.51.100.81/32"]
    rows = _rows(_values(raw))
    assert "db.example.org" in rows["api"]["hosts"]
    for name in ("worker", "report-sync"):
        given = set(rows.get(name, {}).get("hosts", []))
        assert not given & {"db.example.org", BUCKET_HOST, ATHENA_HOST}, name


def _statements() -> list[dict[str, Any]]:
    config = OspreyConfig.model_validate(_raw())
    return terraform.connector_source_statements(config)


#: The only actions the role is given for a declared source: reads, and the results' writes.
READS = {"s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject", "athena:StartQueryExecution",
         "athena:GetQueryExecution", "athena:GetQueryResults", "athena:StopQueryExecution",
         "athena:GetNamedQuery", "athena:GetWorkGroup", "glue:GetDatabase", "glue:GetTable",
         "glue:GetTables", "glue:GetPartition", "glue:GetPartitions",
         "s3:ListMultipartUploadParts"}  # fmt: skip
WRITES = {"s3:PutObject", "s3:AbortMultipartUpload"}


def test_the_role_s_statements_are_read_only_and_scoped() -> None:
    statements = _statements()
    for statement in statements:
        assert set(statement["actions"]) <= READS | WRITES, statement
        for resource in statement["resources"]:
            assert resource != "*" and not resource.startswith(("arn:aws:s3:::*", "*")), resource
        if set(statement["actions"]) & WRITES:
            assert statement["resources"] == ["arn:aws:s3:::synthetic-athena-results/out/*"]
    by_resource = {r: s for s in statements for r in s["resources"]}
    # The bucket listed under its prefix alone; its objects read under it alone.
    listing = by_resource["arn:aws:s3:::synthetic-exports"]
    assert listing["actions"] == ["s3:ListBucket"]
    assert listing["condition"] == {
        "test": "StringLike", "variable": "s3:prefix", "values": ["client-a/", "client-a/*"]
    }  # fmt: skip
    assert by_resource["arn:aws:s3:::synthetic-exports/client-a/*"]["actions"] == ["s3:GetObject"]
    assert by_resource["arn:aws:s3:::synthetic-lake/visits/*"]["actions"] == ["s3:GetObject"]
    workgroup = next(r for r in by_resource if r.endswith(":workgroup/analysts"))
    assert workgroup.startswith("arn:aws:athena:eu-west-2:")
    assert any(r.endswith(":database/visits") for r in by_resource)
    assert any(r.endswith(":table/visits/*") for r in by_resource)
    tf = _artefacts(_raw())["terraform/connector_sources.tf"]
    assert '"*"' not in tf
    assert "aws_iam_role.service.name" in tf  # the account the Conduit already has (P7b's IRSA)


@pytest.mark.parametrize(
    "planted",
    [
        {"sid": "Planted", "actions": ["s3:GetObject"], "resources": ["*"]},
        {"sid": "Planted", "actions": ["s3:GetObject"], "resources": ["arn:aws:s3:::*"]},
        {"sid": "Planted", "actions": ["s3:PutObject"],
         "resources": ["arn:aws:s3:::synthetic-exports/client-a/*"]},
        {"sid": "Planted", "actions": ["s3:DeleteObject"],
         "resources": ["arn:aws:s3:::synthetic-athena-results/out/*"]},
    ],
)  # fmt: skip
def test_a_wide_statement_is_refused_by_the_render(
    planted: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Planted where the render takes the statements (`connector_source_statements`), in the shape
    it returns them: a `*` resource, every bucket, a write on a source, a delete on the results."""
    made = terraform.connector_source_statements

    def wider(config: OspreyConfig) -> list[dict[str, Any]]:
        return [*made(config), planted]

    monkeypatch.setattr(terraform, "connector_source_statements", wider)
    with pytest.raises(CloudPlatformNotRenderable, match="connector_sources"):
        _artefacts(_raw())


def test_nothing_is_rendered_with_no_source_declared() -> None:
    artefacts = _artefacts(_raw("development"))
    values = yaml.safe_load(artefacts["values.yaml"])
    assert "terraform/connector_sources.tf" not in artefacts
    assert "OSPREY_CONNECTOR_SOURCES" not in values["environment"]
    assert terraform.connector_source_statements(
        OspreyConfig.model_validate(_raw("development"))
    ) == []
