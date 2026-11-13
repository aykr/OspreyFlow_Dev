"""What the indexer, the rebuild and the drift check open: the graph adapter itself (the
`IndexFeedSource`, never the stamping wrapper a route is given), the texts' store, the deployment's
ontology and the client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from opensearchpy import AsyncOpenSearch
from services.api.config import PostgresConfig
from services.api.review import ExtractionCandidateStore

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import OntologySchema

from .client import SearchIndexConfig, search_client


@dataclass
class FeedResources:
    source: GraphArcadeDBAdapter
    texts: ExtractionCandidateStore
    client: AsyncOpenSearch
    alias: str
    schema: OntologySchema


@asynccontextmanager
async def feed_resources(*, database: str = "ospreyflow") -> AsyncIterator[FeedResources]:
    config = SearchIndexConfig.from_env()
    arcadedb = ArcadeDBClient(ArcadeDBConfig.from_env(database=database))
    schema = load_deployment_ontology()
    source = GraphArcadeDBAdapter(arcadedb, load_uk_le_scheme())
    await source.apply_schema(schema)
    texts = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    client = search_client(config)
    try:
        yield FeedResources(source, texts, client, config.alias, schema)
    finally:
        await client.close()
        await texts.close()
        await source.aclose()
