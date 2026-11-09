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
from typing import Any

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
    "100.64.1.1",
    "nat64.example",
    "sixtofour.example",
    "shared.example",
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
        "nat64.example": ["64:ff9b::7f00:1"],
        "sixtofour.example": ["2002:a00:1::1"],
        "shared.example": ["100.64.0.9"],
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
    monkeypatch.setenv("OSPREY_CONNECTOR_SECRETS", "X")  # declared (Amendment 15)
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


# --- the orchestrator's second review: hidden files, and caps that stop reading ------------------


def test_a_json_pattern_never_reads_a_hidden_file(tmp_path: __import__("pathlib").Path) -> None:
    """`*` matches a dotfile in `fnmatch`, so a half-written `.read-*.tmp` beside the source's file
    would have been read. Every dot-name is left out."""
    from services.api.connector_reads import _json_files

    folder = tmp_path / "uploaded" / "ds-a"
    folder.mkdir(parents=True)
    (folder / "bookings.json").write_text('{"records": [{"id": 1}]}')
    (folder / ".read-1234.tmp").write_text("half written")
    (folder / ".hidden.json").write_text('{"records": [{"id": 2}]}')
    assert [name for name, _ in _json_files("ds-a", "*", tmp_path)] == ["bookings.json"]


def test_an_api_body_over_the_cap_is_stopped_not_read_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.ingest.connectors import reads

    monkeypatch.setattr(reads, "MAX_BYTES", 100)
    sent: list[int] = []

    async def body():  # type: ignore[no-untyped-def]
        yield b'{"items": ['
        for n in range(1000):
            sent.append(n)
            yield b'{"n": "' + b"x" * 40 + b'"},'
        yield b'{"n": "end"}]}'

    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=body()))
    settings = ApiConnectionSettings(base_url="https://telco.example")
    with pytest.raises(ConnectorRefused, match="bytes"):
        asyncio.run(reads.read_api(settings, ApiRead(path="/v1/n", records_at="items"),
                                   secret=None, allowed_hosts=["telco.example"],
                                   transport=transport))  # fmt: skip
    assert len(sent) < 10, f"{len(sent)} chunks were read past the cap"


def test_json_files_over_the_cap_are_never_opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: __import__("pathlib").Path
) -> None:
    from pathlib import Path

    from services.api.connector_reads import _json_files
    from services.ingest.connectors import reads

    monkeypatch.setattr(reads, "MAX_BYTES", 100)
    folder = tmp_path / "ds-a"
    folder.mkdir()
    (folder / "big.json").write_text('{"r": [' + '"y",' * 200 + '"z"]}')
    from services.api import connector_reads

    opened: list[str] = []
    real = connector_reads._no_follow

    def spy(path: str, flags: int) -> int:
        opened.append(Path(path).name)
        return real(path, flags)

    monkeypatch.setattr(connector_reads, "_no_follow", spy)
    with pytest.raises(ConnectorRefused, match="bytes"):
        _json_files("ds-a", "*.json", tmp_path)
    assert opened == []
    (folder / "big.json").write_text('{"r": []}')
    assert _json_files("ds-a", "*.json", tmp_path) and opened == ["big.json"]


def test_a_json_file_that_grows_after_it_was_sized_is_stopped_while_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: __import__("pathlib").Path
) -> None:
    """The orchestrator's review of Amendment 15, item 10: the cap holds while reading, not only
    before, so a file written to between the size check and the read is never read whole."""
    from pathlib import Path

    from services.api import connector_reads
    from services.api.connector_reads import _json_files
    from services.ingest.connectors import reads

    monkeypatch.setattr(reads, "MAX_BYTES", 100)
    folder = tmp_path / "ds-a"
    folder.mkdir()
    (folder / "growing.json").write_text('{"r": []}')
    real = connector_reads._no_follow

    def grows_first(path: str, flags: int) -> int:
        with open(path, "a") as handle:
            handle.write(" " * 500)
        return real(path, flags)

    asked: list[int] = []

    class _Counting:
        """The real file, with each read's size kept: never more than the room the cap leaves."""

        def __init__(self, handle: Any) -> None:
            self.handle = handle

        def __enter__(self) -> _Counting:
            return self

        def __exit__(self, *exc: object) -> None:
            self.handle.close()

        def read(self, size: int = -1) -> bytes:
            asked.append(size)
            return self.handle.read(size)

    def counting_open(*args: Any, **kwargs: Any) -> _Counting:
        return _Counting(open(*args, **kwargs))

    monkeypatch.setattr(connector_reads, "_no_follow", grows_first)
    monkeypatch.setattr(connector_reads, "open", counting_open, raising=False)
    with pytest.raises(ConnectorRefused, match="bytes"):
        _json_files("ds-a", "*.json", tmp_path)
    assert Path(folder / "growing.json").stat().st_size > 100
    assert asked and all(0 <= size <= 101 for size in asked), asked


def test_a_json_pattern_never_follows_a_link(tmp_path: __import__("pathlib").Path) -> None:
    """A link named like a source's file, to a dot-file beside it or to a file in another folder,
    is never read; nor a folder that is itself a link (item 10)."""
    from services.api.connector_reads import _json_files

    folder = tmp_path / "uploaded" / "ds-a"
    folder.mkdir(parents=True)
    (folder / "bookings.json").write_text('{"records": [{"id": 1}]}')
    (folder / ".secret.json").write_text('{"records": [{"id": "hidden"}]}')
    elsewhere = tmp_path / "uploaded" / "ds-b"
    elsewhere.mkdir()
    (elsewhere / "theirs.json").write_text('{"records": [{"id": "theirs"}]}')
    (folder / "a.json").symlink_to(folder / ".secret.json")
    (folder / "b.json").symlink_to(elsewhere / "theirs.json")
    found = _json_files("ds-a", "*.json", tmp_path)
    assert [name for name, _ in found] == ["bookings.json"]
    assert all(b"hidden" not in body and b"theirs" not in body for _, body in found)
    (tmp_path / "ds-c").symlink_to(folder)
    with pytest.raises(ConnectorRefused, match="no file"):
        _json_files("ds-c", "*.json", tmp_path)


def test_a_watermark_is_a_column_name_and_a_quoted_name_holds() -> None:
    from services.ingest.connectors.sql_connector import _quoted, read_sql

    from schemas.sources import SqlRead

    async def connect(**kw: object) -> object:
        raise AssertionError("never reached")

    settings = SqlConnectionSettings(host="db.client.example", database="nomis", user="r",
                                     secret="X")  # fmt: skip
    with pytest.raises(ConnectorRefused, match="plain column name"):
        asyncio.run(read_sql(settings, SqlRead(table="public.t"), secret="pw",
                             watermark='id" > 0 OR "1', connect=connect))  # fmt: skip
    assert _quoted('public.we"ird') == '"public"."we""ird"'


def test_an_api_request_goes_to_the_address_that_was_checked(dns: dict[str, list[str]]) -> None:
    """The orchestrator's second review (item 6): the request is sent to the address looked up and
    checked, the name kept for its Host header and TLS, so a rebinding between the check and the
    connection cannot redirect it."""
    seen: list[httpx.Request] = []

    def telco(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": [{"n": "1"}]})

    connection = Connection(
        id="c", kind="api", name="Telco", created_by="adm", created_at=datetime.now(UTC),
        settings=ApiConnectionSettings(base_url="https://telco.example"),
    )  # fmt: skip
    readers = Readers(http_transport=httpx.MockTransport(telco), allowed_hosts=["telco.example"])
    source = type("S", (), {"read": ApiRead(path="/v1/n", records_at="items"), "refresh": None})()
    asyncio.run(read_rows(source, connection, dataset_id="ds-a", cursor=None, readers=readers,
                          root=__import__("pathlib").Path("/nonexistent")))  # fmt: skip
    assert seen[0].url.host == "93.184.215.14"
    assert seen[0].headers["host"] == "telco.example"
    assert seen[0].extensions["sni_hostname"] == "telco.example"
    dns["telco.example"] = []
    with pytest.raises(ConnectorRefused, match="does not resolve"):
        asyncio.run(read_rows(source, connection, dataset_id="ds-a", cursor=None,
                              readers=readers, root=__import__("pathlib").Path("/x")))  # fmt: skip
