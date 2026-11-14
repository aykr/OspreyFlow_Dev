"""The write path's lookup of ids (ADR-124 Amendment 18), shared by the adapter and the bulk
loader: each id's vertex as (record id, stored type), through every vertex type's unique `id`
index by SQL. Gremlin's `g.V().has("id", …)` scans every vertex, labelled or not (Amendment 2's
measure), so a load that asked it per item grew with the graph's square. Unfiltered by design: an
internal lookup during a trusted write; nothing it returns leaves the adapter."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from typing import Any

from ontology.errors import OntologyError

from .builders import render_record_id_and_id_lookup_sql

RECORD_ID = re.compile(r"^#\d+:\d+$")
CHUNK = 1000


async def unique_id_types(client: Any, kind: str) -> list[str]:
    """The stored types of `kind` (`"vertex"` or `"edge"`) that carry a unique index on `id`
    alone, from the store itself (ADR-124 Amendment 2): a type another process made since is found,
    and a type without the index is never asked, since asking would scan it."""
    types = await client.sql("SELECT name, type, indexes FROM schema:types")
    return [
        str(t["name"])
        for t in types
        if t.get("type") == kind
        and any(
            i.get("unique") is True and i.get("properties") == ["id"]
            for i in t.get("indexes") or []
        )
    ]


class IdInTwoTypes(OntologyError):
    """One id held by vertices of two stored types: the write cannot tell which it means, so it
    stops rather than write onto whichever answered last. An `OntologyError`, as the refusal of a
    write onto another type's id is, so a load reports both the same way: the write refused."""


async def vertex_records(
    client: Any,
    ids: Sequence[str],
    *,
    tx: str | None = None,
    types: Sequence[str] | None = None,
) -> dict[str, tuple[str, str]]:
    """Each id's vertex as (record id, stored type): one query per vertex type asked per 1,000 ids,
    sent together (inside a transaction the client's session sends them one after another), in the
    write's own transaction where one is given, so a vertex written earlier in it is found.

    `types`, the stored types the caller knows its ids are of, narrows the question to those of
    them the store indexes, so a call costs one read of the store's types and one query per type it
    names, not one per type in the store; `None` asks every indexed vertex type."""
    wanted = sorted({str(i) for i in ids})
    found: dict[str, tuple[str, str]] = {}
    if not wanted:
        return found
    indexed = await unique_id_types(client, "vertex")
    asked = indexed if types is None else [t for t in indexed if t in set(types)]
    for start in range(0, len(wanted), CHUNK):
        chunk = wanted[start : start + CHUNK]
        answers = await asyncio.gather(
            *(
                client.sql(
                    render_record_id_and_id_lookup_sql(t), params={"ids": chunk}, session_id=tx
                )
                for t in asked
            )
        )
        for type_name, rows in zip(asked, answers, strict=True):
            for row in rows:
                rid = row.get("rid")
                if not isinstance(rid, str) or not RECORD_ID.match(rid):
                    raise ValueError(f"not an ArcadeDB record id: {rid!r}")
                node_id = str(row["id"])
                if node_id in found and found[node_id][1] != type_name:
                    raise IdInTwoTypes(
                        f"the id {node_id!r} is held by nodes of two types: the write stops rather "
                        "than choose one"
                    )
                found[node_id] = (rid, type_name)
    return found
