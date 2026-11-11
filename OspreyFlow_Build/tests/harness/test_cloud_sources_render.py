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
        # A `?` alone, in a declared bucket under its declared folder, with no `*`: only the `?`
        # branch can refuse it (a `?` beside a `*` is refused by the `*` branch either way).
        ({"actions": ["s3:GetObject"], "resources": ["arn:aws:s3:::synthetic-exports/client-a/a?.csv"]},
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
        # The orchestrator's review of part 2, item 2 (a): a condition's values held to the folders.
        ({"actions": ["s3:ListBucket"], "resources": ["arn:aws:s3:::synthetic-exports"],
          "condition": {"test": "StringLike", "variable": "s3:prefix", "values": ["*"]}},
         "lists synthetic-exports under '*', beyond its declared folders"),
        ({"actions": ["s3:ListBucket"], "resources": ["arn:aws:s3:::synthetic-exports"],
          "condition": {"test": "StringNotLike", "variable": "s3:prefix", "values": ["client-a/"]}},
         "lists synthetic-exports under a StringNotLike condition, not StringLike"),
        # (b): a workgroup, or a region, the declaration does not name.
        ({"actions": ["athena:GetQueryResults"],
          "resources": [f"arn:aws:athena:eu-west-2:{terraform._ACCOUNT}:workgroup/primary"]},
         "names the workgroup primary in eu-west-2, which is not declared"),
        ({"actions": ["athena:GetQueryResults"],
          "resources": [f"arn:aws:athena:eu-west-1:{terraform._ACCOUNT}:workgroup/analysts"]},
         "names the workgroup analysts in eu-west-1, which is not declared"),
        ({"actions": ["glue:GetTable"],
          "resources": [f"arn:aws:glue:eu-west-1:{terraform._ACCOUNT}:table/visits/*"]},
         "names Glue in eu-west-1, where no workgroup is declared"),
        # (c): default-deny, a shape not recognised.
        ({"actions": ["s3:GetObject"],
          "resources": ["arn:aws:s3:eu-west-2:000000000000:accesspoint/synthetic-exports"]},
         "names arn:aws:s3:eu-west-2:000000000000:accesspoint/synthetic-exports, a resource of a "
         "shape this check does not recognise"),
        ({"actions": ["s3:GetObject"], "resources": ["arn:aws-cn:s3:::synthetic-exports/client-a/a"]},
         "names arn:aws-cn:s3:::synthetic-exports/client-a/a, a resource of a shape this check "
         "does not recognise"),
        ({"actions": ["s3:GetObject"],
          "resources": [f"arn:aws:dynamodb:eu-west-2:{terraform._ACCOUNT}:table/visits"]},
         f"names arn:aws:dynamodb:eu-west-2:{terraform._ACCOUNT}:table/visits, a resource of a "
         "shape this check does not recognise"),
        # Item 3: a `*` only the `*` branch refuses: in a declared bucket under its declared folder,
        # but not at the end (every other branch admits it).
        ({"actions": ["s3:GetObject"], "resources": ["arn:aws:s3:::synthetic-exports/client-a/*.csv"]},
         "names a wildcard resource"),
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


def test_a_policy_past_iam_s_size_limit_is_refused_at_render() -> None:
    """IAM refuses a managed policy past 6,144 characters (whitespace removed), so the render does
    first, in words, rather than leave the platform team a Terraform that cannot apply (the
    orchestrator's review). The fixture's own policy is well within it."""
    assert terraform.policy_characters(_statements()) < terraform.POLICY_LIMIT
    raw = _raw()
    raw["cloud_platform"]["connector_sources"]["s3"] = [
        {"bucket": f"synthetic-exports-{n:02d}", "region": "eu-west-2", "prefix": "client-a/"}
        for n in range(40)
    ]
    for n in range(40):
        raw["cloud_platform"]["egress_nets"][
            f"synthetic-exports-{n:02d}.s3.eu-west-2.amazonaws.com"] = ["198.18.0.0/24"]
    with pytest.raises(CloudPlatformNotRenderable, match="past IAM's limit of 6,144"):
        _artefacts(raw)


@pytest.fixture
def own_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """The deployment's identity as botocore's chain finds it (synthetic), as `test_cloud_clients`."""
    from ..connectors.athena_fixture import GRANTED_KEY

    for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE",
                 "AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", GRANTED_KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-secret-not-a-real-key")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


@pytest.mark.usefixtures("own_identity")
def test_the_deployment_s_listing_asks_only_within_the_role_s_rendered_grants() -> None:
    """Rule 15, the orchestrator's review of part 2: the recorded S3 is given the role's own
    statements, rendered from the declaration, and refuses what IAM would. The deployment's own
    listing client (`CloudS3Store`) asks within them: Test's one-level listing of the connection's
    folder (`Prefix=client-a/`, which the `s3:prefix` values match) and a read's folder under it.
    A connection at the bucket's top, beyond the declared folder, is refused by S3 itself in words;
    so is a key outside the role's `s3:GetObject` resources."""
    from botocore.exceptions import ClientError
    from services.api.connector_reads import _check_cloud, cloud_s3_store
    from services.api.connector_reads import Readers
    from services.ingest.connectors.reads import ConnectorRefused
    from services.ingest.connectors.s3_connector import list_folder

    from schemas.sources import S3ConnectionSettings

    from ..connectors.s3_fixture import RecordedS3

    keys = [("client-a/visits/a.csv", 10), ("client-b/b.csv", 10)]
    recorded = RecordedS3(buckets={"synthetic-exports": keys}, granted=_statements())
    settings = S3ConnectionSettings(region="eu-west-2", bucket="synthetic-exports",
                                    prefix="client-a/")  # fmt: skip

    def store(s: S3ConnectionSettings) -> Any:
        made = cloud_s3_store(s)
        recorded.attach(made.client)
        return made

    readers = Readers(s3_store=store)
    assert _check_cloud(settings, readers).ok  # Test: Prefix=client-a/
    found = list_folder(store(settings), "synthetic-exports", "synthetic-exports/client-a/visits",
                        recursive=True, limit=10)  # fmt: skip
    assert [f.path for f in found] == ["synthetic-exports/client-a/visits/a.csv"]
    assert {r["query"].get("prefix") for r in recorded.requests} == {"client-a/", "client-a/visits/"}
    top = settings.model_copy(update={"prefix": ""})
    with pytest.raises(ConnectorRefused, match="access denied"):
        _check_cloud(top, readers)  # Prefix="" under a grant conditioned on client-a/
    with pytest.raises(ClientError, match="AccessDenied|403"):
        store(settings).client.head_object(Bucket="synthetic-exports", Key="client-b/b.csv")


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"s3": [{"bucket": "synthetic-exports", "region": "cn-north-1"}]},
         "cn-north-1 is outside AWS's standard partition"),
        ({"s3": [{"bucket": "synthetic-exports", "region": "us-gov-west-1"}]},
         "us-gov-west-1 is outside AWS's standard partition"),
        ({"athena": [{"workgroup": "analysts", "region": "eu-west-2", "databases": ["visits"],
                      "results_location": "s3://synthetic-athena-results/out/",
                      "table_locations": []}]},
         "table_locations names at least one s3://bucket/folder/"),
    ],
)  # fmt: skip
def test_a_declaration_the_role_s_statements_cannot_serve_is_refused_in_words(
    change: dict[str, Any], words: str
) -> None:
    """The statements name `arn:aws:` resources, so a China or GovCloud region is refused (the
    orchestrator's recommendation); an Athena workgroup with no table location could read no
    table, so one is required (the orchestrator's review of part 2)."""
    from pydantic import ValidationError

    raw = _raw()
    raw["cloud_platform"]["connector_sources"] = change
    with pytest.raises(ValidationError, match=re.escape(words)):
        OspreyConfig.model_validate(raw)
