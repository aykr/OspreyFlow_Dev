"""What `GremlinBulkTransport` sends: constant script text, every value as a parameter (ADR-058).

Why it matters: ArcadeDB compiles each distinct Groovy script. A script with an address or an id
spliced into its text is a new script every time, which is the leading (still unmeasured) suspect
for the 0.15 s per link of the upsert path (ADR-056 Amendments 23 and 24). The bulk path's whole
design is that its script text does not change from chunk to chunk. This checks the text, not the
speed: whether the shapes run on a real ArcadeDB is for `scripts/spike_bulk_transport.py`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from adapters.graph_arcadedb.bulk import GremlinBulkTransport

LABEL = "mx_TRANSACTED"


class _RecordingClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    async def gremlin(
        self, command: str, *, params: Any = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        self.sent.append((command, dict(params or {})))
        return []


def _rows(prefix: str) -> list[dict[str, Any]]:
    return [{"s": f"{prefix}-a", "t": f"{prefix}-b", "p": {"id": f"{prefix}-e", "valid_from": 1}}]


def test_the_write_script_is_the_same_text_for_every_chunk() -> None:
    """Catches a row value reaching the script text, which would make every chunk a new script."""
    client = _RecordingClient()
    transport = GremlinBulkTransport(client)  # type: ignore[arg-type]
    asyncio.run(transport.write_chunk(LABEL, _rows("first"), "tx"))
    asyncio.run(transport.write_chunk(LABEL, _rows("second"), "tx"))
    (script_one, params_one), (script_two, params_two) = client.sent
    assert script_one == script_two
    assert "first" not in script_one and "second" not in script_two
    assert params_one["rows"][0]["s"] == "first-a" and params_two["rows"][0]["s"] == "second-a"
    assert LABEL in script_one  # the one identifier spliced in, already validated upstream


def test_every_lookup_passes_its_ids_as_parameters() -> None:
    client = _RecordingClient()
    transport = GremlinBulkTransport(client)  # type: ignore[arg-type]

    async def run() -> None:
        await transport.vertex_labels(["id-1", "id-2"])
        await transport.stored_pairs(LABEL, [("id-1", "id-2")], directed=True)
        await transport.degrees(LABEL, ["id-1", "id-2"])

    asyncio.run(run())
    assert len(client.sent) == 3
    for script, params in client.sent:
        assert "id-1" not in script and "id-2" not in script
        assert params, script


def test_an_undirected_type_is_looked_for_from_either_end() -> None:
    """Catches `outE` being used for an undirected type, which would miss an edge stored the other
    way round (`upsert_edges` uses `bothE` for the same reason)."""
    client = _RecordingClient()
    transport = GremlinBulkTransport(client)  # type: ignore[arg-type]

    async def run() -> None:
        await transport.stored_pairs(LABEL, [("a", "b")], directed=False)
        await transport.stored_pairs(LABEL, [("a", "b")], directed=True)

    asyncio.run(run())
    (undirected, _), (directed, _) = client.sent
    assert "bothE" in undirected and "otherV" in undirected
    assert "outE" in directed and "bothE" not in directed
