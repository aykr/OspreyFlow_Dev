"""The Athena connector against the real Athena, **on the client's platform only** (L1.9; the build
plan's row: "Athena against a recorded fixture, its live test marked for the client's platform").

`athena_fixture.py` answers in the shapes AWS's API reference gives; nobody has run this code
against Athena itself, which is the finding rule 15's second worked example names. This file is
what confirms the fixture's refusals, and is skipped everywhere but a namespace with Athena: set
`OSPREY_ATHENA_LIVE=<region>,<workgroup>,<database>,<table>` there, signed in as the namespace's
own role (no key: ADR-148). It reads a synthetic table the client's team creates for it (rule 9:
never a table holding real data), and asks Athena to refuse what the fixture refuses: a query that
does not parse, a table that does not exist, and a catalog that does not exist.

**Unconfirmed until part 2** (the orchestrator's review of L1.9, round 1, item 7): whether Athena
reports a query that does not parse as a FAILED execution (the fixture's model) or refuses it at
`StartQueryExecution` with an `InvalidRequestException`; and the same for a catalog it does not hold.
The reader words both ways, so a read is refused either way; these cases say which one Athena does,
and fail, naming it, if it is not the one modelled.
"""

from __future__ import annotations

import os
import time

import pytest
from botocore.exceptions import ClientError
from services.api.connector_reads import cloud_athena_client
from services.ingest.connectors import athena_connector
from services.ingest.connectors.athena_connector import read_athena
from services.ingest.connectors.reads import ConnectorRefused

from schemas.sources import AthenaConnectionSettings, AthenaRead

LIVE = os.environ.get("OSPREY_ATHENA_LIVE", "")
pytestmark = pytest.mark.skipif(
    LIVE.count(",") != 3, reason="the client's platform only: OSPREY_ATHENA_LIVE is not set"
)


def _settings() -> tuple[AthenaConnectionSettings, str, str]:
    region, workgroup, database, table = LIVE.split(",")
    return AthenaConnectionSettings(region=region, workgroup=workgroup,
                                    databases=[database]), database, table  # fmt: skip


def test_the_synthetic_table_is_read_as_the_namespace_s_role() -> None:
    settings, database, table = _settings()
    rows = read_athena(cloud_athena_client(settings), settings,
                       AthenaRead(table=f"{database}.{table}"))  # fmt: skip
    assert rows.columns


def test_athena_fails_a_table_that_does_not_exist_as_the_fixture_does() -> None:
    settings, database, _table = _settings()
    with pytest.raises(ConnectorRefused, match="Athena could not run the query: TABLE_NOT_FOUND"):
        read_athena(cloud_athena_client(settings), settings,
                    AthenaRead(table=f"{database}.osprey_no_such_table"))  # fmt: skip


def test_athena_fails_a_query_that_does_not_parse_as_the_fixture_does() -> None:
    """The fixture's model: accepted at StartQueryExecution, then FAILED with Athena's reason (a
    dangling WHERE, as `test_athena_connector`'s syntax case). A named query cannot be saved here,
    so the statement is started as the reader starts one, and waited on by the reader's own wait."""
    settings, database, table = _settings()
    client = cloud_athena_client(settings)
    try:
        started = client.start_query_execution(
            QueryString=f'SELECT * FROM "{database}"."{table}" WHERE',
            QueryExecutionContext={"Database": database, "Catalog": settings.catalog},
            WorkGroup=settings.workgroup,
        )
    except ClientError as error:  # the other answer: refused at the request, not as an execution
        pytest.fail(f"Athena refused the query at the request ({error}), not as a FAILED "
                    "execution: correct athena_fixture.py's syntax model")  # fmt: skip
    with pytest.raises(ConnectorRefused, match=r"Athena could not run the query: line 1:\d+"):
        athena_connector._wait(client, started["QueryExecutionId"], sleep=time.sleep,
                               clock=time.monotonic)  # fmt: skip


def test_athena_fails_a_catalog_it_does_not_hold_as_the_fixture_does() -> None:
    settings, database, table = _settings()
    nowhere = settings.model_copy(update={"catalog": "osprey_no_such_catalog"})
    try:
        read_athena(cloud_athena_client(nowhere), nowhere, AthenaRead(table=f"{database}.{table}"))
    except ConnectorRefused as refused:
        assert str(refused).startswith("Athena could not run the query: CATALOG_NOT_FOUND"), (
            f"Athena refused a missing catalog otherwise ({refused}): correct athena_fixture.py"
        )
    else:
        pytest.fail("Athena read through a catalog that does not exist")
