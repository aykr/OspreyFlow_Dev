"""The Conduit's FastAPI app — `docs/03_CONDUIT_MIDDLEWARE.md` §1/§3.

**Stateless.** Every `app.state` attribute below is a client for an
external store (ArcadeDB, Valkey, Postgres); none of it is session or
working-set state, which lives entirely in Valkey via `working_set/
store.py`. Two instances of this app, started independently, serve any
request for any investigation identically — `tests/services/api/
test_statelessness.py` is the proof this phase's exit criterion asks for
("kill the instance serving a session mid-investigation and the analyst
notices nothing").

**Every route audits before it discloses or before it returns success.**
`docs/00_ARCHITECTURE.md` §5 / `03_CONDUIT_MIDDLEWARE.md` §8: "an
unaudited read is worse than a refused one... Reject reads. This is the
one case where the platform fails closed." Each handler below performs
its `GraphPort`/`WorkingSetService` action first (a read's result
cardinality is only known once it has run), writes the audit row, and
only then returns — an `AuditWriteError` propagates as a 503 with nothing
disclosed to the caller, never a result returned alongside a swallowed
audit failure.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import duckdb
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from services.ingest.connectors.geo.site_grid import site_grid_rows
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe
from services.ingest.staging import ObjectStorageConfig
from valkey.asyncio import Valkey

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_id
from geo.bilinear import ControlPoint
from geo.image_dimensions import (
    UnsupportedImageFormatError,
    image_content_type,
    image_dimensions,
)
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.analytics import (
    CrossFilterRequest,
    GeoBin,
    GeoBinRequest,
    GeometryRecord,
    Histogram,
    HistogramRequest,
)
from schemas.domain import Edge, ExpandRequest, Node, NodeId, OntologySchema, Principal
from schemas.mapconfig import MapConfig, PublicMapConfig

from . import search as search_module
from .audit import AuditWriteError, AuditWriter
from .auth import PrincipalResolutionError, PrincipalResolver, bearer_scheme
from .config import ApiConfig
from .history import (
    HistoryStep,
    HistoryStepNotFoundError,
    HistoryStepSummary,
    InvestigationHistoryStore,
)
from .investigations import Investigation, InvestigationNotFoundError, InvestigationStore
from .jobs import JobQueue
from .mapconfig_loader import load_map_config, public_view
from .notify import notify_channel, publish_delta
from .search import SearchRequest, SearchResponse
from .site_images import (
    object_key_for,
    read_site_image,
    site_image_storage_config,
    write_site_image,
)
from .sites import ControlPointQuad, Site, SiteNotFoundError, SiteStore
from .tile_cache import (
    cache_key_for,
    read_cached_tile,
    tile_cache_storage_config,
    write_cached_tile,
)
from .tile_proxy import build_upstream_url, fetch_tile
from .working_set.models import (
    CardinalityPreview,
    DeltaNotice,
    DeltaRemove,
    DeltaSnapshot,
    ExpansionOutcome,
    LimitExceededError,
    WorkingSetDelta,
    decode_delta,
)
from .working_set.service import WorkingSetService
from .working_set.store import ValkeyWorkingSetStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = ApiConfig.from_env()

    arcadedb_client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await arcadedb_client.create_database_if_absent()
    handling_scheme = load_uk_le_scheme()
    ontology = load_default_ontology()
    graph: GraphPort = GraphArcadeDBAdapter(arcadedb_client, handling_scheme)
    await graph.apply_schema(ontology)

    valkey = Valkey(host=config.valkey.host, port=config.valkey.port, db=config.valkey.db)
    audit = await AuditWriter.connect(config.postgres.dsn)
    investigations = await InvestigationStore.connect(config.postgres.dsn)
    history = await InvestigationHistoryStore.connect(config.postgres.dsn)
    sites = await SiteStore.connect(config.postgres.dsn)

    # A persistent (not `:memory:`) DuckDB file — first production wiring of
    # `AnalyticsPort` anywhere in the Conduit (`07_BUILD_PLAN.md` Phase 5
    # Checkpoint 2; `analytics_duckdb/testing.py`'s own docstring records why
    # this isn't yet the Parquet-in-object-storage store that module names
    # as the longer-term design — a stated, deliberate deferral, not this
    # checkpoint's job). `IF NOT EXISTS` in `schema.py` makes re-running this
    # DDL against the same file on every restart safe.
    Path(config.analytics_db_path).parent.mkdir(parents=True, exist_ok=True)
    analytics_con = duckdb.connect(config.analytics_db_path)
    create_events_table(analytics_con)
    create_geometries_table(analytics_con)
    analytics: AnalyticsPort = AnalyticsDuckDBAdapter(analytics_con, handling_scheme)

    app.state.config = config
    app.state.graph = graph
    app.state.ontology = ontology
    app.state.valkey = valkey
    app.state.working_set = WorkingSetService(graph, ValkeyWorkingSetStore(valkey), handling_scheme)
    app.state.audit = audit
    app.state.investigations = investigations
    app.state.history = history
    app.state.sites = sites
    app.state.site_image_storage = site_image_storage_config()
    app.state.tile_cache_storage = tile_cache_storage_config()
    app.state.analytics = analytics
    app.state.jobs = JobQueue(valkey)
    app.state.principal_resolver = PrincipalResolver(config)
    app.state.map_config = load_map_config(config.osprey_config_path)

    try:
        yield
    finally:
        await arcadedb_client.aclose()
        await valkey.aclose()
        await audit.close()
        await investigations.close()
        await history.close()
        await sites.close()
        analytics_con.close()


app = FastAPI(title="OspreyFlow Conduit", lifespan=lifespan)

# The Glass is served from its own origin (`apps/workspace`'s Vite dev
# server locally; a separately-hosted static build in a real deployment)
# and calls this API cross-origin — discovered as a real gap, not a
# pre-empted one, the first time Checkpoint 2's canvas actually tried to
# call `/v1/ontology` from a browser and every request failed preflight.
# Read directly from the environment rather than through `ApiConfig`:
# that dataclass requires `OIDC_JWKS_URL` to be set (`config.py`'s own
# `from_env`), which many tests importing this module never set, since
# `app.dependency_overrides` bypasses `PrincipalResolver` entirely for
# them — middleware, unlike a dependency, must be registered before the
# app is used at all, not deferred into `lifespan`.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(
        o.strip()
        for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ),
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- dependencies ---------------------------------------------------------


def get_working_set(request: Request) -> WorkingSetService:
    return request.app.state.working_set  # type: ignore[no-any-return]


def get_audit(request: Request) -> AuditWriter:
    return request.app.state.audit  # type: ignore[no-any-return]


def get_investigations(request: Request) -> InvestigationStore:
    return request.app.state.investigations  # type: ignore[no-any-return]


def get_history(request: Request) -> InvestigationHistoryStore:
    return request.app.state.history  # type: ignore[no-any-return]


def get_graph(request: Request) -> GraphPort:
    return request.app.state.graph  # type: ignore[no-any-return]


def get_ontology(request: Request) -> OntologySchema:
    return request.app.state.ontology  # type: ignore[no-any-return]


def get_map_config(request: Request) -> MapConfig:
    return request.app.state.map_config  # type: ignore[no-any-return]


def get_valkey(request: Request) -> Valkey:
    return request.app.state.valkey  # type: ignore[no-any-return]


def get_sites(request: Request) -> SiteStore:
    return request.app.state.sites  # type: ignore[no-any-return]


def get_site_image_storage(request: Request) -> ObjectStorageConfig:
    return request.app.state.site_image_storage  # type: ignore[no-any-return]


def get_tile_cache_storage(request: Request) -> ObjectStorageConfig:
    return request.app.state.tile_cache_storage  # type: ignore[no-any-return]


def get_analytics(request: Request) -> AnalyticsPort:
    return request.app.state.analytics  # type: ignore[no-any-return]


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Principal:
    resolver: PrincipalResolver = request.app.state.principal_resolver
    try:
        return resolver.resolve(credentials.credentials)
    except PrincipalResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


WorkingSetDep = Annotated[WorkingSetService, Depends(get_working_set)]
AuditDep = Annotated[AuditWriter, Depends(get_audit)]
InvestigationsDep = Annotated[InvestigationStore, Depends(get_investigations)]
HistoryDep = Annotated[InvestigationHistoryStore, Depends(get_history)]
GraphDep = Annotated[GraphPort, Depends(get_graph)]
OntologyDep = Annotated[OntologySchema, Depends(get_ontology)]
MapConfigDep = Annotated[MapConfig, Depends(get_map_config)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]
SitesDep = Annotated[SiteStore, Depends(get_sites)]
SiteImageStorageDep = Annotated[ObjectStorageConfig, Depends(get_site_image_storage)]
TileCacheStorageDep = Annotated[ObjectStorageConfig, Depends(get_tile_cache_storage)]
AnalyticsDep = Annotated[AnalyticsPort, Depends(get_analytics)]


async def get_authorized_investigation(
    investigation_id: str,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> Investigation:
    """The one gate every investigation-scoped route depends on instead of
    a bare `investigation_id` path param — divergence-review fix #1.
    `InvestigationStore.get_authorized` already collapses "no such
    investigation" and "wrong `owning_unit`" into the same exception,
    mapped to the same 404 by `_investigation_not_found_handler`; this
    wrapper's only addition is recording the denial in the audit stream
    before it propagates, same as every other action here."""
    try:
        return await investigations.get_authorized(investigation_id, principal)
    except InvestigationNotFoundError:
        await audit.record(
            principal=principal,
            action="access_denied",
            investigation_id=investigation_id,
            resolved_query={},
            result_cardinality=0,
        )
        raise


AuthorizedInvestigationDep = Annotated[Investigation, Depends(get_authorized_investigation)]


async def get_authorized_site(
    investigation_id: str,
    site_id: str,
    principal: PrincipalDep,
    sites: SitesDep,
    audit: AuditDep,
) -> Site:
    """Mirrors `get_authorized_investigation` — `SiteStore.get_authorized`
    already collapses "no such site" and "wrong owning_unit" into the same
    `SiteNotFoundError`; this wrapper adds the audit record on denial, plus
    the check that the site actually belongs to the investigation named in
    the URL, not just to the same org unit — a real site id under a
    *different* investigation is "not found" here too, not a cross-
    investigation peek."""
    try:
        site = await sites.get_authorized(site_id, principal)
        if site.investigation_id != investigation_id:
            raise SiteNotFoundError(site_id)
        return site
    except SiteNotFoundError:
        await audit.record(
            principal=principal,
            action="access_denied",
            investigation_id=investigation_id,
            resolved_query={"site_id": site_id},
            result_cardinality=0,
        )
        raise


AuthorizedSiteDep = Annotated[Site, Depends(get_authorized_site)]


# --- exception handling ----------------------------------------------------


@app.exception_handler(LimitExceededError)
async def _limit_exceeded_handler(request: Request, exc: LimitExceededError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=exc.detail.model_dump())


@app.exception_handler(AuditWriteError)
async def _audit_write_error_handler(request: Request, exc: AuditWriteError) -> JSONResponse:
    # `03_CONDUIT_MIDDLEWARE.md` §8: "The audit stream is unavailable.
    # Reject reads. This is the one case where the platform fails
    # closed." 503, not 500: this is a named, expected failure mode with
    # its own documented behaviour, not an unhandled server error.
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "audit_unavailable", "detail": str(exc)},
    )


@app.exception_handler(InvestigationNotFoundError)
async def _investigation_not_found_handler(
    request: Request, exc: InvestigationNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "investigation_not_found"}
    )


@app.exception_handler(HistoryStepNotFoundError)
async def _history_step_not_found_handler(
    request: Request, exc: HistoryStepNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "history_step_not_found"}
    )


@app.exception_handler(SiteNotFoundError)
async def _site_not_found_handler(request: Request, exc: SiteNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "site_not_found"})


@app.exception_handler(UnsupportedImageFormatError)
async def _unsupported_image_format_handler(
    request: Request, exc: UnsupportedImageFormatError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "unsupported_image_format", "detail": str(exc)},
    )


# --- investigations ---------------------------------------------------------


@app.post("/v1/investigations", status_code=status.HTTP_201_CREATED)
async def create_investigation(
    principal: PrincipalDep, investigations: InvestigationsDep, audit: AuditDep
) -> Investigation:
    investigation = await investigations.create(principal)
    await audit.record(
        principal=principal,
        action="create_investigation",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=1,
    )
    return investigation


@app.get("/v1/investigations/{investigation_id}")
async def get_investigation(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    audit: AuditDep,
) -> Investigation:
    await audit.record(
        principal=principal,
        action="get_investigation",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=1,
    )
    return investigation


@app.post("/v1/investigations/{investigation_id}/branch", status_code=status.HTTP_201_CREATED)
async def branch_investigation(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> Investigation:
    # `03_CONDUIT_MIDDLEWARE.md` §3.1: "fork the working set into a new
    # investigation" — one of the cap breach's three options, made real.
    # `AuthorizedInvestigationDep` has already checked the branching
    # principal against the *source* investigation's `owning_unit`; the
    # new investigation gets its own, from this principal, not inherited.
    new_investigation = await investigations.create(principal, branched_from=investigation.id)
    outcome = await working_set.branch(investigation.id, new_investigation.id, principal)
    await publish_delta(valkey, new_investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        new_investigation.id,
        seq=outcome.delta.seq,
        label=f"Branched from {investigation.id}",
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="branch",
        investigation_id=investigation.id,
        resolved_query={"new_investigation_id": new_investigation.id},
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return new_investigation


async def _record_history_step(
    working_set: WorkingSetService,
    history: InvestigationHistoryStore,
    investigation_id: str,
    *,
    seq: int,
    label: str,
    principal: Principal,
) -> HistoryStep:
    """Called after every mutation that changes working-set membership
    (`07_BUILD_PLAN.md` Phase 4's "Named-step history with restore") — full
    current membership, not just the mutation's own delta, so the step is
    independently restorable (`history.py`'s module docstring)."""
    nodes, edges = await working_set.current_membership(investigation_id)
    return await history.record_step(
        investigation_id, seq=seq, label=label, created_by=principal.id, nodes=nodes, edges=edges
    )


# --- working set ------------------------------------------------------------


class SeedRequest(BaseModel):
    nodes: list[Node]
    edges: list[Edge] = []


class ExpandBody(BaseModel):
    request: ExpandRequest
    justification: str | None = None


class RemoveNodesRequest(BaseModel):
    node_ids: list[NodeId]


@app.post("/v1/investigations/{investigation_id}/seed")
async def seed(
    investigation: AuthorizedInvestigationDep,
    body: SeedRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> ExpansionOutcome:
    outcome = await working_set.seed(investigation.id, body.nodes, body.edges, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=outcome.delta.seq,
        label=f"Seeded {len(outcome.delta.nodes)} node(s)",
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="seed",
        investigation_id=investigation.id,
        resolved_query={"node_count": len(body.nodes), "edge_count": len(body.edges)},
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return outcome


@app.post("/v1/investigations/{investigation_id}/expand")
async def expand(
    investigation: AuthorizedInvestigationDep,
    body: ExpandBody,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> ExpansionOutcome:
    outcome = await working_set.expand(investigation.id, body.request, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=outcome.delta.seq,
        label=(
            f"Expanded {len(outcome.delta.nodes)} node(s) from "
            f"{len(body.request.node_ids)} seed(s)"
        ),
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="expand",
        investigation_id=investigation.id,
        resolved_query=body.request.model_dump(mode="json"),
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
        justification=body.justification,
    )
    return outcome


@app.post("/v1/investigations/{investigation_id}/expand/preview")
async def expand_preview(
    investigation: AuthorizedInvestigationDep,
    body: ExpandBody,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
) -> CardinalityPreview:
    preview = await working_set.expand_preview(investigation.id, body.request, principal)
    await audit.record(
        principal=principal,
        action="expand_preview",
        investigation_id=investigation.id,
        resolved_query=body.request.model_dump(mode="json"),
        result_cardinality=preview.candidate_node_count + preview.candidate_edge_count,
    )
    return preview


@app.delete("/v1/investigations/{investigation_id}/nodes")
async def remove_nodes(
    investigation: AuthorizedInvestigationDep,
    body: RemoveNodesRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> dict[str, int]:
    seq = await working_set.remove(investigation.id, body.node_ids)
    await publish_delta(
        valkey, investigation.id, DeltaRemove(seq=seq, node_ids=list(body.node_ids))
    )
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=seq,
        label=f"Removed {len(body.node_ids)} node(s)",
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="remove_nodes",
        investigation_id=investigation.id,
        resolved_query={"node_ids": body.node_ids},
        result_cardinality=len(body.node_ids),
    )
    return {"seq": seq}


# --- named-step history -----------------------------------------------------


@app.get("/v1/investigations/{investigation_id}/history")
async def get_investigation_history(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    history: HistoryDep,
    audit: AuditDep,
) -> list[HistoryStepSummary]:
    steps = await history.list_steps(investigation.id)
    await audit.record(
        principal=principal,
        action="get_history",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=len(steps),
    )
    return steps


@app.post("/v1/investigations/{investigation_id}/history/{step_id}")
async def restore_history_step(
    investigation: AuthorizedInvestigationDep,
    step_id: str,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> DeltaSnapshot:
    step = await history.get_step(investigation.id, step_id)
    # `WorkingSetService.restore` re-projects `step`'s stored (unfiltered)
    # bodies against `principal` fresh — never the visibility `step` was
    # recorded with (`history.py`'s module docstring).
    snapshot = await working_set.restore(investigation.id, step.nodes, step.edges, principal)
    await publish_delta(valkey, investigation.id, snapshot)
    await audit.record(
        principal=principal,
        action="restore_history_step",
        investigation_id=investigation.id,
        resolved_query={"step_id": step_id},
        result_cardinality=len(snapshot.nodes) + len(snapshot.edges),
    )
    return snapshot


# --- search -------------------------------------------------------------------


@app.post("/v1/search")
async def search_route(
    body: SearchRequest,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
) -> SearchResponse:
    result = await search_module.search(graph, body, principal)
    await audit.record(
        principal=principal,
        action="search",
        resolved_query={"query": body.query},
        result_cardinality=len(result.nodes),
    )
    return result


# --- ontology -----------------------------------------------------------------


@app.get("/v1/ontology")
async def get_ontology_route(principal: PrincipalDep, ontology: OntologyDep) -> OntologySchema:
    """The Glass's channel/shape mapping (`docs/02_GLASS_FRONTEND.md` §4:
    "Hue is entity type; shape is entity type too") comes from here, not a
    hardcoded copy of `packages/ontology/default.yaml` in the frontend —
    the ontology already carries `EntityTypeDef.channel`/`.shape` per type,
    and duplicating that mapping client-side would drift the moment a
    deployment's ontology changes. Authenticated like every other route,
    but not investigation-scoped and not audited: this is deployment-wide
    schema *metadata* (entity/edge type names, channels, shapes,
    identifiers) — never a node, a property value or a count — the same
    category of thing `principal_may_view` was never meant to gate."""
    return ontology


@app.get("/v1/map/providers")
async def get_map_providers_route(
    principal: PrincipalDep, map_config: MapConfigDep
) -> PublicMapConfig:
    """The Glass's layer control (`docs/02_GLASS_FRONTEND.md` §3.5: "Layer
    control listing every provider declared in `osprey.yaml`") reads this,
    not a hardcoded copy of the registry — the same reasoning as
    `get_ontology_route` just above. Not in `03_CONDUIT_MIDDLEWARE.md`
    §3.3's API surface list; that is a real spec silence (the doc requires
    the capability in `02_GLASS_FRONTEND.md` but never names an endpoint
    for it), not an oversight here — flagged for the end-of-checkpoint
    audit rather than filled in silently. Deployment-wide configuration
    metadata like `/v1/ontology`, so the same category applies: not
    investigation-scoped, not audited, authenticated only so an
    unauthenticated caller learns nothing about this deployment's
    providers or credentials. Carries `default` too, not just the
    provider list (`PublicMapConfig`'s own docstring) — a bare list has
    nowhere to say which entry the map should start on."""
    return PublicMapConfig(
        default=map_config.default,
        providers=[public_view(p) for p in map_config.providers],
    )


@app.get("/v1/map/tiles/{provider_id}/{z}/{x}/{y}")
async def get_map_tile_route(
    provider_id: str,
    z: int,
    x: int,
    y: int,
    principal: PrincipalDep,
    map_config: MapConfigDep,
    tile_cache_storage: TileCacheStorageDep,
) -> Response:
    """`00_ARCHITECTURE.md` §1.2's tile proxy — resolves a `credential:
    env:VAR` reference server-side (`tile_proxy.build_upstream_url`) and
    caches the fetched tile to object storage (`tile_cache.py`) per the
    provider's own `PrefetchCache.ttl_days`, so the browser never holds a
    tier-3/4 credential or talks to a hosted provider directly — this is
    the one named, auditable exception to default-deny egress the section
    describes. Not itself audited (deployment-wide infrastructure, the
    same category `/v1/map/providers` already is, not investigation data);
    the same section's own caution about tile-request patterns over a
    sensitive AOI is mitigated by preferring tier 1/2 local providers, not
    by auditing this route's traffic."""
    provider = next((p for p in map_config.providers if p.id == provider_id), None)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown provider")
    if provider.proxy == "none":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="provider is not proxied — use its own source directly",
        )

    cache_key = cache_key_for(provider_id, z, x, y)
    if provider.cache is not None:
        cached = read_cached_tile(
            storage=tile_cache_storage, object_key=cache_key, ttl_days=provider.cache.ttl_days
        )
        if cached is not None:
            return Response(content=cached, media_type=image_content_type(cached))

    url = build_upstream_url(provider, z, x, y)
    tile_bytes = await fetch_tile(url)
    if provider.cache is not None:
        write_cached_tile(tile_bytes, storage=tile_cache_storage, object_key=cache_key)
    return Response(content=tile_bytes, media_type=image_content_type(tile_bytes))


# --- analytics (07_BUILD_PLAN.md Phase 5 Checkpoint 2) -----------------------
#
# Global routes, `EventFilter.investigation_scope` carried in the request
# body rather than the URL path — mirroring `/v1/search`'s own existing
# precedent (also global, also investigation data scoped via the body, not
# nested under `/v1/investigations/{id}/...` the way `/expand`/`/sites` are).
# Audited like `/v1/search`, since these read investigation event data —
# not deployment-wide metadata the way `/v1/ontology`/`/v1/map/providers`
# are.


class GeometriesRequest(BaseModel):
    geometry_refs: list[str]


@app.post("/v1/analytics/histogram")
async def histogram_route(
    body: HistogramRequest, principal: PrincipalDep, analytics: AnalyticsDep, audit: AuditDep
) -> Histogram:
    result = await analytics.histogram(body, principal)
    await audit.record(
        principal=principal,
        action="analytics_histogram",
        investigation_id=body.filter.investigation_scope,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=result.total,
    )
    return result


@app.post("/v1/analytics/cross-filter")
async def cross_filter_route(
    body: CrossFilterRequest, principal: PrincipalDep, analytics: AnalyticsDep, audit: AuditDep
) -> dict[str, Histogram]:
    result = await analytics.cross_filter(body, principal)
    await audit.record(
        principal=principal,
        action="analytics_cross_filter",
        investigation_id=body.filter.investigation_scope,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=sum(h.total for h in result.values()),
    )
    return result


@app.post("/v1/analytics/geobins")
async def geo_bins_route(
    body: GeoBinRequest, principal: PrincipalDep, analytics: AnalyticsDep, audit: AuditDep
) -> list[GeoBin]:
    result = await analytics.geo_bins(body, principal)
    await audit.record(
        principal=principal,
        action="analytics_geo_bins",
        investigation_id=body.filter.investigation_scope,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=sum(b.count for b in result),
    )
    return result


@app.post("/v1/analytics/geometries")
async def geometries_route(
    body: GeometriesRequest, principal: PrincipalDep, analytics: AnalyticsDep, audit: AuditDep
) -> list[GeometryRecord]:
    """`MapView.tsx`'s `nodeCoordinates` — a `Location`'s `geometry_ref`
    resolved to a WGS84 point, batched so plotting a whole working set is
    one round trip rather than one request per node. Not investigation-
    scoped (the geometry partition never is, `GeometryRecord`'s own
    docstring) — audited on `result_cardinality` alone rather than a
    resolved `investigation_id`, matching `/v1/ontology`'s reasoning for
    deployment-wide reference data, except this genuinely is per-request
    caller input, so it stays audited rather than exempt."""
    result = await analytics.get_geometries(body.geometry_refs, principal)
    await audit.record(
        principal=principal,
        action="analytics_geometries",
        resolved_query={"geometry_refs": body.geometry_refs},
        result_cardinality=len(result),
    )
    return result


# --- sites ---------------------------------------------------------------
#
# `docs/00_ARCHITECTURE.md` §1.2's "Geospatial reference data as entities"
# table (site plans row), `docs/02_GLASS_FRONTEND.md` §3.5,
# `08_ACCEPTANCE_SCENARIOS.md` A1. A `Site` is investigation-scoped analyst
# data (`services/api/sites.py`'s own docstring), not deployment config —
# nothing here touches `osprey.yaml`/the `MapProvider` registry.
#
# Loaded from the fixtures path even in this live route, mirroring
# `scripts/build_local_basemap.py`'s own precedent for
# `osm_gazetteer_recipe.yaml` — where a shipped, non-test copy of either
# recipe should live is still an open item, recorded once already in
# `osm_gazetteer_recipe.yaml`'s own comment.
_SITE_GRID_RECIPE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "scenarios"
    / "fixtures"
    / "site_grid_recipe.yaml"
)


class ControlPointsRequest(BaseModel):
    #: Exactly 4, TL/TR/BR/BL winding order — `packages/geo/bilinear.py`.
    control_points: ControlPointQuad


class GridRequest(BaseModel):
    #: `08_ACCEPTANCE_SCENARIOS.md` A1's "draw a 10x10 grid".
    rows: int = 10
    cols: int = 10


@app.post("/v1/investigations/{investigation_id}/sites", status_code=status.HTTP_201_CREATED)
async def create_site(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    sites: SitesDep,
    audit: AuditDep,
    storage: SiteImageStorageDep,
    label: Annotated[str, Form()],
    image: Annotated[UploadFile, File()],
) -> Site:
    """First `UploadFile` route in the Conduit
    (`services/api/site_images.py`'s own docstring). `image_dimensions`
    raising `UnsupportedImageFormatError` (-> 422, the handler above) is
    what actually validates the upload; nothing here inspects the
    browser-supplied content-type header, which is never trustworthy."""
    data = await image.read()
    width, height = image_dimensions(data)
    site_id = new_id()
    write_site_image(data, storage=storage, object_key=object_key_for(site_id))
    site = await sites.create(
        principal,
        investigation_id=investigation.id,
        label=label,
        image_object_key=object_key_for(site_id),
        image_width_px=width,
        image_height_px=height,
        site_id=site_id,
    )
    await audit.record(
        principal=principal,
        action="create_site",
        investigation_id=investigation.id,
        resolved_query={"site_id": site.id},
        result_cardinality=1,
    )
    return site


@app.get("/v1/investigations/{investigation_id}/sites/{site_id}")
async def get_site(site: AuthorizedSiteDep, principal: PrincipalDep, audit: AuditDep) -> Site:
    await audit.record(
        principal=principal,
        action="get_site",
        investigation_id=site.investigation_id,
        resolved_query={"site_id": site.id},
        result_cardinality=1,
    )
    return site


@app.get("/v1/investigations/{investigation_id}/sites/{site_id}/image")
async def get_site_image(site: AuthorizedSiteDep, storage: SiteImageStorageDep) -> Response:
    """The browser never talks to the object store directly — the same
    reasoning as the tile proxy (`00_ARCHITECTURE.md` §1.2 "The tile
    proxy"): credentials stay server-side and every read is a request this
    process can see, not a signed URL handed out to whoever asks."""
    data = read_site_image(storage=storage, object_key=site.image_object_key)
    return Response(content=data, media_type=image_content_type(data))


@app.patch("/v1/investigations/{investigation_id}/sites/{site_id}/control-points")
async def set_site_control_points(
    site: AuthorizedSiteDep,
    principal: PrincipalDep,
    sites: SitesDep,
    audit: AuditDep,
    body: ControlPointsRequest,
) -> Site:
    updated = await sites.set_control_points(site.id, principal, body.control_points)
    await audit.record(
        principal=principal,
        action="set_site_control_points",
        investigation_id=site.investigation_id,
        resolved_query={"site_id": site.id},
        result_cardinality=1,
    )
    return updated


@app.post("/v1/investigations/{investigation_id}/sites/{site_id}/grid")
async def set_site_grid(
    site: AuthorizedSiteDep,
    principal: PrincipalDep,
    sites: SitesDep,
    graph: GraphDep,
    ontology: OntologyDep,
    audit: AuditDep,
    body: GridRequest,
) -> Site:
    """Runs the site-grid connector + the existing recipe engine
    synchronously against this request — the same call shape
    `tests/scenarios/fixtures/hmp_graph.py`'s fixture code already uses,
    just triggered by an HTTP request instead of a test
    (`docs/00_ARCHITECTURE.md` §1.2: "Reference geodata is ingested
    through the ordinary connector framework"). `on_match: reference` in
    `site_grid_recipe.yaml` makes redrawing the grid idempotent rather
    than creating duplicate `Location`s.

    **A stated gap, not a silent one**: this does not call
    `AnalyticsPort.load_geometries` for the cells it creates — the Conduit
    has no `AnalyticsPort` wired in yet (`07_BUILD_PLAN.md` Phase 5
    Checkpoint 2's job). Every `Location` gets a real, deterministic
    `geometry_ref`, but that reference does not resolve to a point until
    Checkpoint 2 wires geometry loading through — exactly the same
    already-documented gap `test_osm_gazetteer_recipe_end_to_end.py`'s own
    docstring records for the OSM gazetteer connector, not a new one this
    route introduces."""
    if site.control_points is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="the site needs 4 control points before a grid can be drawn",
        )
    updated = await sites.set_grid(site.id, principal, rows=body.rows, cols=body.cols)

    assert updated.control_points is not None  # checked above; narrows the type for mypy
    cp1, cp2, cp3, cp4 = updated.control_points
    control_points = (
        ControlPoint(px=cp1.px, py=cp1.py, lon=cp1.lon, lat=cp1.lat),
        ControlPoint(px=cp2.px, py=cp2.py, lon=cp2.lon, lat=cp2.lat),
        ControlPoint(px=cp3.px, py=cp3.py, lon=cp3.lon, lat=cp3.lat),
        ControlPoint(px=cp4.px, py=cp4.py, lon=cp4.lon, lat=cp4.lat),
    )
    rows = list(
        site_grid_rows(
            site_id=updated.id, control_points=control_points, rows=body.rows, cols=body.cols
        )
    )
    recipe = load_recipe(_SITE_GRID_RECIPE_PATH)
    tx = await graph.begin_transaction()
    try:
        report, _events = await run_recipe(
            recipe,
            rows,
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=principal,
            load_id=f"site-grid-{updated.id}",
            investigation_scope=updated.investigation_id,
            source=f"site:{updated.id}",
        )
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    if report.rejections:
        await graph.rollback_transaction(tx)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="grid cells were rejected by the recipe engine",
        )
    await graph.commit_transaction(tx)

    await audit.record(
        principal=principal,
        action="set_site_grid",
        investigation_id=site.investigation_id,
        resolved_query={"site_id": site.id, "rows": body.rows, "cols": body.cols},
        result_cardinality=report.nodes_created,
    )
    return updated


# --- the delta stream --------------------------------------------------------


async def _authenticate_websocket(websocket: WebSocket) -> Principal:
    """`WebSocket` connections carry no `Authorization` header dependency
    injection the way an HTTP route does — the bearer token is read from
    the same header manually, once, before `accept()`.

    **A browser's native `WebSocket` cannot set that header at all** — a
    real gap Checkpoint 2 hit the first time the Glass tried to open this
    connection from an actual browser, not a pre-empted one. The `?token=`
    query parameter is this phase's resolution: the same long-lived JWT a
    browser client already holds and already sends as a Bearer header on
    every ordinary HTTP call, so this does not mint or expose a new
    credential — the marginal risk is a token appearing in this server's
    own access/proxy logs, which a Bearer header avoids. A short-lived,
    single-use "ticket" (minted by an authenticated HTTP call, exchanged
    here instead of the JWT itself) closes that gap properly and is named
    here as the production hardening this phase does not implement, not
    left silent. The `Authorization` header is still tried first, for a
    non-browser client (this phase's own `ws`-based integration test) that
    *can* set it.
    """
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[len("bearer ") :]
    else:
        token = websocket.query_params.get("token", "")
        if not token:
            raise PrincipalResolutionError("missing bearer token")
    resolver: PrincipalResolver = websocket.app.state.principal_resolver
    return resolver.resolve(token)


async def _forward_notifications(
    pubsub: Any, websocket: WebSocket, working_set: WorkingSetService, principal: Principal
) -> None:
    """Relays a live mutation from `notify.py`'s Pub/Sub channel to this
    one connected principal — re-projected via `WorkingSetService.
    project_delta` first, since the delta was recorded by whichever
    principal caused the mutation, who may not be this socket's principal
    (`03_CONDUIT_MIDDLEWARE.md` §4's read-time handling filter applies to
    the live push exactly as much as to reconnect replay)."""
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        data = message["data"]
        raw = decode_delta(json.loads(data.decode() if isinstance(data, bytes) else data))
        delta, hidden = working_set.project_delta(raw, principal)
        await websocket.send_text(delta.model_dump_json())
        if hidden > 0:
            notice = DeltaNotice(
                seq=delta.seq,
                message=f"{hidden} item(s) withheld by handling policy",
                count=hidden,
            )
            await websocket.send_text(notice.model_dump_json())


async def _handle_resync_requests(
    websocket: WebSocket,
    working_set: WorkingSetService,
    investigation_id: str,
    principal: Principal,
) -> None:
    while True:
        payload = await websocket.receive_json()
        last_ack = payload.get("last_acknowledged_seq")
        deltas = await working_set.sync(
            investigation_id, principal, last_acknowledged_seq=last_ack
        )
        for delta in deltas:
            await websocket.send_text(delta.model_dump_json())


@app.websocket("/v1/investigations/{investigation_id}/stream")
async def stream(websocket: WebSocket, investigation_id: str) -> None:
    """`03_CONDUIT_MIDDLEWARE.md` §3.2: "bidirectional delta channel".
    On connect, and on any later `{"last_acknowledged_seq": ...}` message
    from the client, replies with exactly what `WorkingSetService.sync`
    decides — the missed deltas, or a full snapshot when the gap can't be
    proven closed (never a silent patch attempt either way), both already
    filtered for this connection's own principal. Between those moments,
    deltas from *any* Conduit instance's mutation on this investigation
    arrive via `notify.py`'s Valkey Pub/Sub channel, so a seed/expand
    handled by a different instance than the one holding this socket
    still reaches the client live — also filtered per-connection."""
    try:
        principal = await _authenticate_websocket(websocket)
    except PrincipalResolutionError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    investigations: InvestigationStore = websocket.app.state.investigations
    audit: AuditWriter = websocket.app.state.audit
    try:
        await investigations.get_authorized(investigation_id, principal)
    except InvestigationNotFoundError:
        await audit.record(
            principal=principal,
            action="access_denied",
            investigation_id=investigation_id,
            resolved_query={},
            result_cardinality=0,
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await audit.record(
        principal=principal,
        action="stream_connect",
        investigation_id=investigation_id,
        resolved_query={},
        result_cardinality=0,
    )
    working_set: WorkingSetService = websocket.app.state.working_set
    valkey: Valkey = websocket.app.state.valkey

    try:
        init = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    initial_deltas: list[WorkingSetDelta] = await working_set.sync(
        investigation_id, principal, last_acknowledged_seq=init.get("last_acknowledged_seq")
    )
    for delta in initial_deltas:
        await websocket.send_text(delta.model_dump_json())

    pubsub = valkey.pubsub()
    channel = notify_channel(investigation_id)
    await pubsub.subscribe(channel)
    try:
        forward_task = asyncio.create_task(
            _forward_notifications(pubsub, websocket, working_set, principal)
        )
        resync_task = asyncio.create_task(
            _handle_resync_requests(websocket, working_set, investigation_id, principal)
        )
        try:
            await asyncio.wait(
                {forward_task, resync_task}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for task in (forward_task, resync_task):
                task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]
