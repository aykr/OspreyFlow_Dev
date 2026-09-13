"""Test-only database lifecycle for the `GraphPort` conformance suite.

Not used by production code — the Conduit is configured with one long-lived
database. Every conformance test gets its own uniquely-named ArcadeDB
database, schema-applied and dropped on exit, so tests never interfere with
each other regardless of ordering or parallelism.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ontology.handling import HandlingScheme
from schemas.domain import OntologySchema

from .adapter import GraphArcadeDBAdapter
from .client import ArcadeDBClient, ArcadeDBConfig


@asynccontextmanager
async def arcadedb_adapter(
    ontology: OntologySchema, handling_scheme: HandlingScheme
) -> AsyncIterator[GraphArcadeDBAdapter]:
    database = f"conformance_{uuid.uuid4().hex[:12]}"
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    try:
        await client.create_database_if_absent()
        adapter = GraphArcadeDBAdapter(client, handling_scheme)
        await adapter.apply_schema(ontology)
        yield adapter
    finally:
        await client.drop_database()
        await client.aclose()
