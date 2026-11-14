"""Test-only: a throwaway index holding exactly the given nodes, built through the real document
builder and bulk writer (ADR-150), for the query side's leak test (ADR-149): the same query
against an index with hidden records planted and one without them must answer alike. Not used by
production code."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager

from opensearchpy import AsyncOpenSearch

from ontology.loader import load_default_ontology
from schemas.domain import Node, OntologySchema

from .client import search_client
from .indexer import actions_for, write_actions
from .mapping import index_body


@asynccontextmanager
async def throwaway_index(
    nodes: Sequence[Node],
    texts: Mapping[str, tuple[str, str]] | None = None,
    *,
    schema: OntologySchema | None = None,
    client: AsyncOpenSearch | None = None,
) -> AsyncIterator[tuple[AsyncOpenSearch, str]]:
    """Yields `(client, index name)` for a new index holding `nodes` (and, for a Document, its text:
    `texts` maps a node id to `(text, the unit that may read it)`), refreshed so it answers at once,
    and deletes it afterwards. The client is the settings' own (`OPENSEARCH_PORT` of the leased
    stack) unless one is given."""
    own = client is None
    client = client or search_client()
    index = f"throwaway-{uuid.uuid4().hex}"
    try:
        await client.indices.create(index=index, body=index_body())
        body = actions_for(
            index,
            [n.id for n in nodes],
            {n.id: n for n in nodes},
            dict(texts or {}),
            schema or load_default_ontology(),
        )
        refused = await write_actions(client, body)
        if refused:
            # A fixture index is exactly the nodes given, or none: never one quietly short.
            raise AssertionError(f"the fixture index refused {refused}")
        await client.indices.refresh(index=index)
        yield client, index
    finally:
        await client.indices.delete(index=index, ignore_unavailable=True)
        if own:
            await client.close()
