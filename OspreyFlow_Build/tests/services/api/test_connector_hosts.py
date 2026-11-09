"""Where a SQL or API connection may reach (`06_DECISIONS.md` ADR-140 Amendment 13, as ADR-147
decision 2a refuses for a map provider): never this machine, the deployment's own services or a
cloud's metadata service, in any form an address can be written or resolve to; checked when an
administrator names the connection and again before every read, since DNS can change in between
(the orchestrator's review of L1.6).

What a mistake would do, and the case that catches it:
- an API connection to `localhost`, a loopback, link-local or private address in any form (`127.1`,
  `0x7f.1`, `2130706433`, `[::ffff:127.0.0.1]`, `169.254.169.254`), a dotless name (`postgres`,
  `keycloak`) or a name resolving to one, reaching inside the deployment —
  `test_an_api_connection_never_reaches_inside_the_deployment`;
- a SQL connection to this machine, the deployment's own database (`postgres`), the metadata
  service or any private address, in any form or by resolution; or a host off the operator's
  allow-list — `test_a_sql_connection_never_reaches_inside_the_deployment`;
- a name that resolved outside when named and inside at the read —
  `test_the_host_is_looked_up_again_before_every_read`;
- a connection named with such a host stored —
  `test_an_administrator_cannot_name_such_a_connection`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from services.api import connector_reads
from services.api.connector_reads import (
    Readers,
    read_rows,
    refuse_host,
)
from services.ingest.connectors.reads import ConnectorRefused

from schemas.sources import (
    ApiConnectionSettings,
    ApiRead,
    Connection,
    SqlConnectionSettings,
)

INSIDE_FORMS = [
    "localhost",
    "db.localhost",
    "127.0.0.1",
    "127.1",
    "0x7f.1",
    "2130706433",
    "[::1]",
    "[::ffff:127.0.0.1]",
    "169.254.169.254",
    "10.0.0.5",
    "192.168.1.9",
    "0.0.0.0",
    "postgres",
    "keycloak.",
]


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """What each name resolves to, by the test: no lookup leaves the machine."""
    answers: dict[str, list[str]] = {
        "telco.example": ["93.184.215.14"],
        "sneaky.example": ["127.0.0.1"],
        "nomis.client.example": ["10.20.30.40"],
        "db.client.example": ["93.184.215.15"],
    }
    monkeypatch.setattr(connector_reads, "resolve_host", lambda host: answers.get(host, []))
    return answers


@pytest.mark.parametrize("host", [*INSIDE_FORMS, "sneaky.example"])
def test_an_api_connection_never_reaches_inside_the_deployment(host: str) -> None:
    with pytest.raises(ConnectorRefused):
        refuse_host("api", host, allowed_hosts=[host.strip("[]"), host])
    refuse_host("api", "telco.example", allowed_hosts=["telco.example"])


@pytest.mark.parametrize("host", [*INSIDE_FORMS, "sneaky.example", "nomis.client.example"])
def test_a_sql_connection_never_reaches_inside_the_deployment(host: str) -> None:
    with pytest.raises(ConnectorRefused):
        refuse_host("sql", host, allowed_hosts=[host.strip("[]"), host])
    refuse_host("sql", "db.client.example", allowed_hosts=["db.client.example"])
    with pytest.raises(ConnectorRefused, match="egress allow-list"):
        refuse_host("sql", "db.client.example", allowed_hosts=[])


def test_the_host_is_looked_up_again_before_every_read(dns: dict[str, list[str]]) -> None:
    connection = Connection(
        id="c",
        kind="api",
        name="Telco",
        created_by="adm",
        created_at=datetime.now(UTC),
        settings=ApiConnectionSettings(base_url="https://telco.example", pagination="page"),
    )
    pages: list[str] = []

    def telco(request: httpx.Request) -> httpx.Response:
        pages.append(str(request.url))
        dns["telco.example"] = ["127.0.0.1"]  # rebound between the first page and the next
        return httpx.Response(200, json={"items": [{"n": "1"}]})

    readers = Readers(http_transport=httpx.MockTransport(telco), allowed_hosts=["telco.example"])
    source = type("S", (), {"read": ApiRead(path="/v1/n", records_at="items"), "refresh": None})()
    with pytest.raises(ConnectorRefused, match="inside this deployment"):
        asyncio.run(
            read_rows(
                source,
                connection,
                dataset_id="ds-a",
                cursor=None,
                readers=readers,
                root=__import__("pathlib").Path("/nonexistent"),
            )
        )
    assert len(pages) == 1, "the second page's address resolved inside and was never asked"


def test_a_sql_read_refuses_its_host_before_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    # The secret is set, so nothing but the host check stands between the read and the connect.
    monkeypatch.setenv("OSPREY_CONNECTION_SECRET_X", "pw")
    connected: list[object] = []

    async def connect(**kw: object) -> object:
        connected.append(kw)
        raise AssertionError("never reached")

    connection = Connection(
        id="c",
        kind="sql",
        name="Own database",
        created_by="adm",
        created_at=datetime.now(UTC),
        settings=SqlConnectionSettings(
            host="sneaky.example", database="ospreyflow", user="osprey", secret="X"
        ),
    )
    source = type(
        "S",
        (),
        {
            "read": __import__("schemas.sources", fromlist=["SqlRead"]).SqlRead(
                table="public.ingest_sources"
            ),
            "refresh": None,
        },
    )()
    readers = Readers(sql_connect=connect, allowed_hosts=["sneaky.example"])
    with pytest.raises(ConnectorRefused, match="resolves inside"):
        asyncio.run(
            read_rows(
                source,
                connection,
                dataset_id="ds-a",
                cursor=None,
                readers=readers,
                root=__import__("pathlib").Path("/nonexistent"),
            )
        )
    assert connected == []


async def test_an_administrator_cannot_name_such_a_connection() -> None:
    """At save: a name resolving inside is refused before it is stored (the schema refuses the
    written forms; `test_connector_schemas.py`)."""
    from services.api.connector_reads import refuse_connection_hosts

    sneaky = Connection(
        id="c",
        kind="api",
        name="Sneaky",
        created_by="adm",
        created_at=datetime.now(UTC),
        settings=ApiConnectionSettings(base_url="https://sneaky.example/v1"),
    )
    with pytest.raises(ConnectorRefused, match="resolves inside"):
        refuse_connection_hosts(sneaky.settings)
    refuse_connection_hosts(ApiConnectionSettings(base_url="https://telco.example"))


def test_a_sql_read_of_a_table_outside_its_connections_schemas_is_refused() -> None:
    from schemas.sources import SqlRead

    connection = Connection(
        id="c",
        kind="sql",
        name="NOMIS",
        created_by="adm",
        created_at=datetime.now(UTC),
        settings=SqlConnectionSettings(
            host="db.client.example", database="nomis", user="r", secret="X", schemas=["nomis"]
        ),
    )

    async def connect(**kw: object) -> object:
        raise AssertionError("never reached")

    source = type("S", (), {"read": SqlRead(table="public.users"), "refresh": None})()
    readers = Readers(sql_connect=connect, allowed_hosts=["db.client.example"])
    with pytest.raises(ConnectorRefused, match="not in a schema"):
        asyncio.run(
            read_rows(
                source,
                connection,
                dataset_id="ds-a",
                cursor=None,
                readers=readers,
                root=__import__("pathlib").Path("/nonexistent"),
            )
        )


def test_every_sql_session_is_bounded_and_read_only_from_its_first_statement() -> None:
    from services.ingest.connectors.sql_connector import read_sql

    from schemas.sources import SqlRead

    asked: dict[str, object] = {}

    async def connect(**kw: object) -> object:
        asked.update(kw)
        raise OSError("stop here")

    settings = SqlConnectionSettings(
        host="db.client.example", database="nomis", user="r", secret="X"
    )
    with pytest.raises(ConnectorRefused):
        asyncio.run(read_sql(settings, SqlRead(table="public.t"), secret="pw", connect=connect))
    assert asked["server_settings"] == {
        "statement_timeout": "60000",
        "default_transaction_read_only": "on",
    }
    assert asked["ssl"] != "require", "verify-full by default: the server's certificate is checked"


def test_a_read_past_the_byte_cap_is_refused_whole(
    monkeypatch: pytest.MonkeyPatch, tmp_path: __import__("pathlib").Path
) -> None:
    from services.ingest.connectors import reads

    monkeypatch.setattr(reads, "MAX_BYTES", 50)
    settings = ApiConnectionSettings(base_url="https://telco.example", pagination="none")
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"items": [{"n": "x" * 80}]})
    )
    with pytest.raises(ConnectorRefused, match="bytes"):
        asyncio.run(
            reads.read_api(
                settings,
                ApiRead(path="/v1/n", records_at="items"),
                secret=None,
                allowed_hosts=["telco.example"],
                transport=transport,
            )
        )
    with pytest.raises(ConnectorRefused, match="bytes"):
        reads.read_json(
            [("a.json", b'{"r": [' + b'"y",' * 30 + b'"z"]}')],
            __import__("schemas.sources", fromlist=["JsonRead"]).JsonRead(pattern="a*"),
        )
    rows = reads.ReadRows(columns=["n"], rows=[{"n": "x" * 80}])
    with pytest.raises(ConnectorRefused, match="bytes"):
        reads.write_snapshot(rows, tmp_path, "big")
