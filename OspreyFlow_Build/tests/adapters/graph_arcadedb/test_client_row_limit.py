"""The client never returns a cut-short result as if it were whole (`CLAUDE.md` rule 2).

Found measuring the Explore panel's group read on the owner's Enron case (8 October 2026): a read of
233,935 links came back with 20,000. ArcadeDB's HTTP command endpoint stops at 20,000 rows unless
the request says otherwise, and says so only in a `truncated` flag beside the result, which the
client did not read; measured on 26.10.1 for Gremlin and SQL alike, and that `"limit": -1` returns
every row. So every read past 20,000 rows had been silently cut, a large expansion's included. The
port's own reads bound themselves (the working set's caps, counted first; paged reads), so the
client asks for every row, and refuses a reply that still says it was cut.

The live case makes more rows than the old default and reads them back; the stand-in cases model
the server's refusal shape (`truncated: true`), which a stand-in that never truncates would hide.
"""

from __future__ import annotations

import json

import httpx
import pytest

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig, ResultTruncatedError
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology


def _client_answering(body: dict) -> tuple[ArcadeDBClient, list[dict]]:  # type: ignore[type-arg]
    sent: list[dict] = []  # type: ignore[type-arg]

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=body)

    client = ArcadeDBClient(
        ArcadeDBConfig(host="arcadedb", http_port=2480, password="x", database="db")
    )
    client._http = httpx.AsyncClient(  # noqa: SLF001
        transport=httpx.MockTransport(handler), base_url="http://arcadedb:2480"
    )
    return client, sent


async def test_every_command_asks_for_every_row() -> None:
    client, sent = _client_answering({"result": [], "truncated": False})
    await client.sql("SELECT 1")
    await client.gremlin("g.V().count()")
    assert [s["limit"] for s in sent] == [-1, -1]


async def test_a_reply_that_says_it_was_cut_is_refused_not_returned() -> None:
    client, _ = _client_answering({"result": [{"n": 1}] * 3, "limit": 3, "truncated": True})
    with pytest.raises(ResultTruncatedError, match="3"):
        await client.sql("SELECT n FROM T")


async def test_more_rows_than_the_old_default_all_come_back() -> None:
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as graph:
        client = graph._client  # noqa: SLF001
        await client.sql("CREATE VERTEX TYPE RowLimitProbe IF NOT EXISTS")
        await client.gremlin(
            '(1..20005).each { g.addV("RowLimitProbe").property("n", it).iterate() }; 1'
        )
        rows = await client.gremlin('g.V().hasLabel("RowLimitProbe").values("n")')
        assert len(rows) == 20005
        rows = await client.sql("SELECT n FROM RowLimitProbe")
        assert len(rows) == 20005
