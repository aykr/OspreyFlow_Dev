"""Phase 9's connection kinds and the screening-list connector's shapes (`06_DECISIONS.md` ADR-140
Amendment 13; Amendment 9 decision 3).

What a mistake would do, and the case that catches it:
- a secret's value carried on a connection, where every reader of the connections list sees it —
  `test_a_connection_names_its_secret_and_never_holds_it`;
- an expression where a name is asked for (rule 8): a SQL table that is a sub-select, a records path
  that is a JSONPath filter, an API path that climbs out of its base URL —
  `test_a_read_names_things_and_never_holds_an_expression`;
- a plain-HTTP API, or a files connection given settings — `test_settings_must_be_their_kinds`;
- a blank list with no mapping, or a format's template overridden —
  `test_only_the_blank_template_takes_a_mapping`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.list_connector import BlankListMapping, DeploymentListInput
from schemas.sources import (
    ApiConnectionSettings,
    ApiRead,
    ConnectionInput,
    JsonRead,
    RegisterSourceInput,
    SqlConnectionSettings,
    SqlRead,
)

SQL = {"kind": "sql", "host": "db.internal", "database": "nomis", "user": "reader",
       "secret": "NOMIS_READER"}  # fmt: skip


def test_a_connection_names_its_secret_and_never_holds_it() -> None:
    made = ConnectionInput(kind="sql", name="NOMIS replica", settings=SQL, datasets=["nomis"])  # type: ignore[arg-type]
    assert "password" not in made.model_dump_json()
    with pytest.raises(ValidationError):
        SqlConnectionSettings(**{**SQL, "password": "s3cret"})  # type: ignore[arg-type]
    with pytest.raises(ValidationError):  # a value, not a name
        SqlConnectionSettings(**{**SQL, "secret": "hunter2!"})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "build",
    [
        lambda: SqlRead(table="(select * from users)"),
        lambda: SqlRead(table="bookings; drop table bookings"),
        lambda: SqlRead(table="bookings", columns=["id, pg_sleep(10)"]),
        lambda: ApiRead(path="/v1/../admin"),
        lambda: ApiRead(path="/v1/bookings?limit=1"),
        lambda: ApiRead(path="/v1", records_at="$.data[?(@.x)]"),
        lambda: JsonRead(pattern="*.json", records_at="data[0]"),
        lambda: JsonRead(pattern="../*.json"),
    ],
)
def test_a_read_names_things_and_never_holds_an_expression(build) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        build()


def test_the_reads_that_name_things_are_accepted() -> None:
    assert SqlRead(table="public.visit_bookings", columns=["booking_id"]).table
    assert ApiRead(path="/v1/numbers", records_at="data.items").records_at == "data.items"
    assert JsonRead(pattern="bookings-*.json", records_at="records").pattern


def test_settings_must_be_their_kinds() -> None:
    with pytest.raises(ValidationError):
        ApiConnectionSettings(base_url="http://telco.example/api")
    with pytest.raises(ValidationError):
        ApiConnectionSettings(base_url="https://telco.example", auth="bearer")
    with pytest.raises(ValidationError):
        ConnectionInput(kind="files", name="x", settings=SQL)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ConnectionInput(kind="sql", name="x")
    with pytest.raises(ValidationError):
        ConnectionInput(kind="api", name="x", settings=SQL)  # type: ignore[arg-type]


def test_a_source_carries_its_read() -> None:
    body = RegisterSourceInput(connection_id="c", name="Visit bookings", location="visit_bookings",
                               read={"kind": "sql", "table": "public.visit_bookings"})  # type: ignore[arg-type]  # fmt: skip
    assert isinstance(body.read, SqlRead)


def test_only_the_blank_template_takes_a_mapping() -> None:
    mapping = BlankListMapping(ref="id", primary_name="name")
    with pytest.raises(ValidationError):
        DeploymentListInput(name="Client list", template="blank", location="l.csv")
    with pytest.raises(ValidationError):
        DeploymentListInput(name="OFAC", template="ofac_sdn", location="SDN.CSV", mapping=mapping)
    assert DeploymentListInput(name="Client list", template="blank", location="l.csv",
                               mapping=mapping).mapping == mapping  # fmt: skip


def test_a_blank_mapping_says_one_way_to_tell_a_person_from_an_organisation() -> None:
    with pytest.raises(ValidationError):
        BlankListMapping(ref="id", primary_name="name", entity_type=None)
    with pytest.raises(ValidationError):
        BlankListMapping(ref="id", primary_name="name", entity_type_column="type")
    assert BlankListMapping(ref="id", primary_name="name", entity_type=None,
                            entity_type_column="type").entity_type_column == "type"  # fmt: skip


# --- the orchestrator's review of L1.6 (items 4, 6, 7, 8 and 9) ---------------------------------

INSIDE = ["localhost", "db.localhost", "127.0.0.1", "127.1", "0x7f.1", "2130706433", "::1",
          "169.254.169.254", "10.0.0.5", "192.168.1.9", "0.0.0.0", "postgres",
          "keycloak."]  # fmt: skip


@pytest.mark.parametrize("host", INSIDE)
def test_a_connection_naming_a_host_inside_the_deployment_is_refused(host: str) -> None:
    with pytest.raises(ValidationError):
        SqlConnectionSettings(**{**SQL, "host": host})  # type: ignore[arg-type]
    shown = f"[{host}]" if ":" in host else host
    with pytest.raises(ValidationError):
        ApiConnectionSettings(base_url=f"https://{shown}/v1")


def test_a_sql_connection_verifies_its_server_by_default_and_names_its_schemas() -> None:
    made = SqlConnectionSettings(**SQL)  # type: ignore[arg-type]
    assert made.tls == "verify-full"
    assert made.schemas == ["public"]
    with pytest.raises(ValidationError):
        SqlConnectionSettings(**{**SQL, "schemas": ["pg_catalog"]})  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SqlConnectionSettings(**{**SQL, "schemas": []})  # type: ignore[arg-type]


def test_a_sql_read_names_its_schema() -> None:
    assert SqlRead(table="nomis.visit_bookings").table == "nomis.visit_bookings"
    for table in ("visit_bookings", "pg_catalog.pg_authid", "information_schema.tables"):
        with pytest.raises(ValidationError):
            SqlRead(table=table)


@pytest.mark.parametrize("pattern", ["..", "..*", "a..json", ".hidden*"])
def test_a_json_pattern_never_climbs_or_reaches_hidden_files(pattern: str) -> None:
    with pytest.raises(ValidationError):
        JsonRead(pattern=pattern)


def test_a_connection_names_the_datasets_that_may_read_through_it() -> None:
    """The orchestrator's ruling on L1.6 (rule 3): a SQL, API or JSON connection is bound to the
    datasets an administrator names; a files connection to none (its sources keep to their own)."""
    with pytest.raises(ValidationError):
        ConnectionInput(kind="sql", name="x", settings=SQL)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ConnectionInput(kind="files", name="x", datasets=["ds-a"])
    with pytest.raises(ValidationError):
        ConnectionInput(kind="sql", name="x", settings=SQL, datasets=["../ds"])  # type: ignore[arg-type]
