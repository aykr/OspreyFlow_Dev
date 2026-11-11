"""The Athena connector against the real Athena, **on the client's platform only** (L1.9; the build
plan's row: "Athena against a recorded fixture, its live test marked for the client's platform").

`athena_fixture.py` answers in the shapes AWS's API reference gives; nobody has run this code
against Athena itself, which is the finding rule 15's second worked example names. This file is
what confirms the fixture's refusals, and is skipped everywhere but a namespace with Athena: set
`OSPREY_ATHENA_LIVE=<region>,<workgroup>,<database>,<table>` there, signed in as the namespace's
own role (no key: ADR-148). It reads a synthetic table the client's team creates for it (rule 9:
never a table holding real data), and asks Athena to refuse a query that does not parse and a table
that does not exist, as the fixture does.
"""

from __future__ import annotations

import os

import pytest
from services.api.connector_reads import cloud_athena_client
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
