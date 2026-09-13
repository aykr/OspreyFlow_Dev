"""`GraphArcadeDBAdapter` — full `GraphPort` over ArcadeDB.

Every read method injects the access filter into the traversal itself
(`access_filter.py`) — never fetches broadly and filters the result — so an
unauthorised principal's query runs the same code path, with the same
predicate, whether or not a hidden record exists.

Every write validates against the ontology before it touches the store
(`ontology/validation.py`) — a property's declared type, a required
property's presence, and an edge's declared endpoint types are all checked
here, on the write path, not left for a caller to have got right.

`Subgraph.filtered_count` is left at its default here. Computing it
accurately needs a full-vs-filtered comparison at the point the Working-Set
Service holds both the requested expansion and the access-filtered result
(`docs/03_CONDUIT_MIDDLEWARE.md`, Phase 3's expansion budget/cardinality
preview) — attempting it here, one `GraphPort.expand` call at a time, risks
adding a second, less-audited channel for exactly the kind of leak this
adapter exists to prevent. Flagged rather than guessed at.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from ulid import ULID

from ontology.errors import OntologyError
from ontology.handling import HandlingScheme
from ontology.validation import validate_edge_endpoints, validate_properties
from schemas.domain import (
    AuditStub,
    EdgeId,
    EdgeWrite,
    ExpandRequest,
    NeighbourhoodStats,
    Node,
    NodeId,
    NodeWrite,
    OntologySchema,
    Path,
    PathRequest,
    PatternQuery,
    Principal,
    SchemaReport,
    Subgraph,
    TxId,
)

from .access_filter import AccessFilter
from .builders import (
    ExpandBuilder,
    GetNodeBuilder,
    MatchBuilder,
    NeighbourhoodStatsBuilder,
    PathBuilder,
)
from .client import ArcadeDBClient
from .gremlin_literals import groovy_identifier, groovy_string_literal
from .naming import logical_type_name, physical_type_name
from .schema import apply_schema as _apply_schema_ddl
from .schema import drop_schema as _drop_schema_ddl
from .serialization import (
    edge_from_element_map,
    edge_write_to_properties,
    node_from_element_map,
    node_write_to_properties,
)


class GraphArcadeDBAdapter:
    """`docs/00_ARCHITECTURE.md` §2.1. `dialects` is `{"gremlin"}` in Phase 1
    (ADR-003's amendment) — a second dialect adds a `render_<dialect>` to
    each builder in `builders.py`, not a change here."""

    dialects: frozenset[str] = frozenset({"gremlin"})

    def __init__(self, client: ArcadeDBClient, handling_scheme: HandlingScheme) -> None:
        self._client = client
        self._access = AccessFilter(handling_scheme)
        self._schema: OntologySchema | None = None
        # In-memory only: a real migration runner persists applied versions
        # to survive a restart. Reverting to a version never applied in
        # this adapter's lifetime is out of scope for Phase 1.
        self._schema_history: dict[int, OntologySchema] = {}

    # --- transactions --------------------------------------------------

    async def begin_transaction(self) -> TxId:
        return await self._client.begin_transaction()

    async def commit_transaction(self, tx: TxId) -> None:
        await self._client.commit_transaction(tx)

    async def rollback_transaction(self, tx: TxId) -> None:
        await self._client.rollback_transaction(tx)

    # --- writes ----------------------------------------------------------

    def _require_schema(self) -> OntologySchema:
        if self._schema is None:
            raise OntologyError("no ontology schema has been applied — call apply_schema first")
        return self._schema

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[NodeId]:
        schema = self._require_schema()
        ids: list[NodeId] = []
        for write in nodes:
            entity_type = schema.entity_type(write.type)
            if entity_type is None:
                raise OntologyError(f"{write.type!r} is not a type in the active ontology")
            validate_properties(entity_type, write.properties)

            node_id = str(ULID())
            audit = AuditStub(created_at=datetime.now(UTC), created_by=write.created_by)
            props = node_write_to_properties(
                write, node_id=node_id, audit=audit, entity_type=entity_type
            )
            type_name = groovy_identifier(physical_type_name(write.type))
            set_clause = ", ".join(f"{key} = :{key}" for key in props)
            await self._client.sql(
                f"INSERT INTO {type_name} SET {set_clause}", params=props, session_id=tx
            )
            ids.append(node_id)
        return ids

    async def _node_type(self, node_id: NodeId, *, session_id: TxId) -> str | None:
        node_lit = groovy_string_literal(node_id)
        results = await self._client.gremlin(
            f'g.V().has("id",{node_lit}).label()', session_id=session_id
        )
        if not results:
            return None
        return logical_type_name(results[0]["result"])

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[EdgeId]:
        schema = self._require_schema()
        ids: list[EdgeId] = []
        for write in edges:
            edge_type = schema.edge_type(write.type)
            if edge_type is None:
                raise OntologyError(f"{write.type!r} is not a type in the active ontology")
            validate_properties(edge_type, write.properties)

            source_type = await self._node_type(write.source, session_id=tx)
            target_type = await self._node_type(write.target, session_id=tx)
            if source_type is None:
                raise OntologyError(f"edge source {write.source!r} does not exist")
            if target_type is None:
                raise OntologyError(f"edge target {write.target!r} does not exist")
            validate_edge_endpoints(edge_type, source_type=source_type, target_type=target_type)

            edge_id = str(ULID())
            audit = AuditStub(created_at=datetime.now(UTC), created_by=write.created_by)
            props = edge_write_to_properties(
                write, edge_id=edge_id, audit=audit, edge_type=edge_type
            )
            type_name = groovy_identifier(physical_type_name(write.type))
            # Bound Gremlin/Groovy variable names are prefixed: TinkerPop
            # statically imports `T.id`/`T.label` as bare `id`/`label` in
            # this scripting context, so a parameter literally named `id`
            # silently resolves to that enum instead of the bound value.
            bound_params = {f"prop_{key}": value for key, value in props.items()}
            _date_keys = {"valid_from", "valid_to"}
            property_steps = "".join(
                f".property({key!r}, new Date(prop_{key}))"
                if key in _date_keys
                else f".property({key!r}, prop_{key})"
                for key in props
            )
            command = (
                f'g.V().has("id", src).as("__src")'
                f'.V().has("id", tgt)'
                f'.addE("{type_name}").from("__src"){property_steps}'
            )
            await self._client.gremlin(
                command,
                params={"src": write.source, "tgt": write.target, **bound_params},
                session_id=tx,
            )
            ids.append(edge_id)
        return ids

    # --- reads -----------------------------------------------------------

    async def get_node(self, node_id: NodeId, principal: Principal) -> Node | None:
        query = GetNodeBuilder(node_id).render_gremlin(self._access, principal)
        results = await self._client.gremlin(query)
        if not results:
            return None
        return node_from_element_map(results[0])

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        builder = ExpandBuilder(req)
        seed_records = await self._client.gremlin(
            builder.render_seed_nodes_gremlin(self._access, principal)
        )
        node_records = await self._client.gremlin(
            builder.render_nodes_gremlin(self._access, principal)
        )
        edge_records = await self._client.gremlin(
            builder.render_edges_gremlin(self._access, principal)
        )
        nodes_by_id = {r["id"]: node_from_element_map(r) for r in (*seed_records, *node_records)}
        return Subgraph(
            nodes=list(nodes_by_id.values()),
            edges=[edge_from_element_map(r) for r in edge_records],
        )

    async def paths(self, req: PathRequest, principal: Principal) -> list[Path]:
        query = PathBuilder(req).render_gremlin(self._access, principal)
        results = await self._client.gremlin(query)
        paths: list[Path] = []
        for record in results:
            steps: list[str] = record["result"]
            node_ids = steps[0::2]
            edge_ids = steps[1::2]
            paths.append(Path(nodes=node_ids, edges=edge_ids, length=len(edge_ids)))
        return paths

    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph:
        query = MatchBuilder(pattern).render_gremlin(self._access, principal)
        results = await self._client.gremlin(query)
        nodes: dict[NodeId, Node] = {}
        for record in results:
            for value in record.values():
                node = node_from_element_map(value)
                nodes[node.id] = node
        return Subgraph(nodes=list(nodes.values()), edges=[])

    async def neighbourhood_stats(
        self, node_id: NodeId, principal: Principal
    ) -> NeighbourhoodStats:
        query = NeighbourhoodStatsBuilder(node_id).render_gremlin(self._access, principal)
        results = await self._client.gremlin(query)
        raw_degree_by_type: dict[str, int] = results[0] if results else {}
        degree_by_type = {
            logical_type_name(label): count for label, count in raw_degree_by_type.items()
        }
        return NeighbourhoodStats(
            node_id=node_id,
            degree=sum(degree_by_type.values()),
            degree_by_type=degree_by_type,
        )

    # --- schema ------------------------------------------------------------

    async def apply_schema(self, schema: OntologySchema) -> SchemaReport:
        report = await _apply_schema_ddl(self._client, schema)
        self._schema = schema
        self._schema_history[schema.version] = schema
        return report

    async def revert_schema(self, to_version: int) -> SchemaReport:
        target = self._schema_history.get(to_version)
        if target is None:
            raise OntologyError(
                f"cannot revert to version {to_version}: no schema at that version has been "
                "applied in this adapter's lifetime"
            )
        current = self._require_schema()
        stale_entities = {e.name for e in current.entity_types} - {
            e.name for e in target.entity_types
        }
        stale_edges = {e.name for e in current.edge_types} - {e.name for e in target.edge_types}
        if stale_entities or stale_edges:
            partial = OntologySchema(
                version=current.version,
                entity_types=[e for e in current.entity_types if e.name in stale_entities],
                edge_types=[e for e in current.edge_types if e.name in stale_edges],
            )
            await _drop_schema_ddl(self._client, partial)

        report = await _apply_schema_ddl(self._client, target)
        self._schema = target
        return report
