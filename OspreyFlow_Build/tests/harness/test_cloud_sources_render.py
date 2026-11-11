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
         "glue:GetTables", "glue:GetPartition", "glue:GetPartitions", "glue:BatchGetPartition",
         "s3:ListMultipartUploadParts", "s3:ListBucketMultipartUploads"}  # fmt: skip
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
    # Named for this file: a `current` may already be in the namespace folder (the lane review).
    assert 'data "aws_caller_identity" "osprey_connector_sources"' in tf


def test_a_listing_condition_never_holds_an_action_that_carries_no_prefix() -> None:
    """`s3:prefix` is set only on a listing: a statement giving ListBucket under it gives nothing
    else, and the bucket's location and uploads (which Athena asks of its results' and tables'
    buckets, and which carry no prefix) are given in a statement with no condition (the lane
    review: under the condition, IAM would never have granted them)."""
    statements = _statements()
    for statement in statements:
        if "condition" in statement:
            assert statement["actions"] == ["s3:ListBucket"], statement
    for bucket in ("synthetic-athena-results", "synthetic-lake"):
        located = [s for s in statements if "s3:GetBucketLocation" in s["actions"]
                   and s["resources"] == [f"arn:aws:s3:::{bucket}"]]  # fmt: skip
        assert located and all("condition" not in s for s in located), bucket
    results = next(s for s in statements if s["sid"] == "AthenaResultsBucket0")
    assert results["actions"] == ["s3:GetBucketLocation", "s3:ListBucketMultipartUploads"]
    for sid, folder in (("AthenaResultsList0", "out/"), ("AthenaTablesList0x0", "visits/")):
        listing = next(s for s in statements if s["sid"] == sid)
        assert listing["condition"]["values"] == [folder, f"{folder}*"], sid


@pytest.mark.parametrize(
    ("planted", "why"),
    [
        ({"actions": ["s3:GetObject"], "resources": ["*"]}, "names a wildcard resource"),
        ({"actions": ["s3:GetObject"], "resources": ["arn:aws:s3:::*"]},
         "names a wildcard resource"),
        ({"actions": ["s3:GetObject"], "resources": ["arn:aws:s3:::synthetic-export?/client-a/*"]},
         "names a wildcard resource"),
        ({"actions": ["s3:PutObject"], "resources": ["arn:aws:s3:::synthetic-exports/client-a/*"]},
         "writes outside a declared results_location"),
        ({"actions": ["s3:DeleteObject"],
          "resources": ["arn:aws:s3:::synthetic-athena-results/out/*"]}, "gives s3:DeleteObject"),
        ({"actions": ["s3:GetObject"], "resources": ["arn:aws:s3:::synthetic-other/*"]},
         "names the bucket synthetic-other, which is not declared"),
        ({"actions": ["s3:GetObject"], "resources": ["arn:aws:s3:::synthetic-exports/client-b/*"]},
         "reads synthetic-exports outside its declared folders"),
        ({"actions": ["s3:ListBucket"], "resources": ["arn:aws:s3:::synthetic-exports"]},
         "lists synthetic-exports beyond its declared folders"),
        ({"actions": ["glue:GetTable"],
          "resources": [f"arn:aws:glue:eu-west-2:{terraform._ACCOUNT}:table/payroll/*"]},
         "names the database payroll, which is not declared"),
    ],
)  # fmt: skip
def test_a_wide_statement_is_refused_by_the_render(
    planted: dict[str, Any], why: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Planted where the render takes the statements (`connector_source_statements`), in the shape
    it returns them; each refused by its own branch, named in the words (the lane review: a match on
    the setting's name alone could not tell which branch refused)."""
    made = terraform.connector_source_statements

    def wider(config: OspreyConfig) -> list[dict[str, Any]]:
        return [*made(config), {"sid": "Planted", **planted}]

    monkeypatch.setattr(terraform, "connector_source_statements", wider)
    with pytest.raises(CloudPlatformNotRenderable, match=re.escape(f"statement Planted {why}")):
        _artefacts(_raw())


def test_a_table_location_not_declared_is_athena_s_refusal_in_typed_words() -> None:
    """The orchestrator's Q3: a table whose objects lie outside every declared `table_locations` is
    not in the role's policy, so Athena (reading them as the role) fails the execution. The recorded
    Athena is given the role's own GetObject resources, rendered from the declaration, and refuses a
    table whose location none covers; the reader words it, naming `table_locations`."""
    from services.ingest.connectors import athena_connector

    from ..connectors.athena_fixture import RecordedAthena
    from ..connectors.test_athena_connector import BOOKINGS, COLUMNS, _read

    granted = [r for st in _statements() if st["actions"] == ["s3:GetObject"]
               for r in st["resources"]]  # fmt: skip
    athena = RecordedAthena(
        tables={"visits": {"visit_bookings": (COLUMNS, BOOKINGS)},
                "payroll": {"salaries": (COLUMNS, BOOKINGS)}},
        granted_objects=granted,
    )  # fmt: skip
    from schemas.sources import AthenaConnectionSettings, AthenaRead

    settings = AthenaConnectionSettings(region="eu-west-2", databases=["visits", "payroll"])
    assert _read(athena, AthenaRead(table="visits.visit_bookings"), settings=settings).rows
    with pytest.raises(athena_connector.ConnectorRefused) as refused:
        _read(athena, AthenaRead(table="payroll.salaries"), settings=settings)
    assert str(refused.value) == athena_connector.TABLE_DATA_DENIED


def test_nothing_is_rendered_with_no_source_declared() -> None:
    artefacts = _artefacts(_raw("development"))
    values = yaml.safe_load(artefacts["values.yaml"])
    assert "terraform/connector_sources.tf" not in artefacts
    assert "OSPREY_CONNECTOR_SOURCES" not in values["environment"]
    assert terraform.connector_source_statements(
        OspreyConfig.model_validate(_raw("development"))
    ) == []
