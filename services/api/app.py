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
import functools
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
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
from services.extract.writer import (
    NodeNotFoundError,
    ProvenanceTransitionError,
    confirm_node,
    retract_node,
)
from services.ingest.connectors.geo.site_grid import site_grid_rows
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe
from services.ingest.staging import ObjectStorageConfig
from services.resolve.trigger import JOB_TYPE_RESOLVE_ENTITY_TYPE, run_resolve_entity_type_job
from valkey.asyncio import Valkey

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.model_litellm import CONFORMANCE_EMBED_MODEL
from adapters.model_litellm.adapter import ModelLiteLLMAdapter
from adapters.model_litellm.client import LiteLLMClient, LiteLLMConfig
from conduit_common.identity import new_id
from geo.bilinear import ControlPoint
from geo.image_dimensions import (
    UnsupportedImageFormatError,
    image_content_type,
    image_dimensions,
)
from knowledge_adapters import ARITY, REGISTRY
from ontology.errors import OntologyError
from ontology.handling import HandlingScheme, load_uk_le_scheme
from ontology.loader import load_default_ontology
from ontology.yardstick import Yardstick, load_phia_yardstick
from ports.analytics import AnalyticsPort
from ports.compute import ComputePort
from ports.graph import GraphPort
from ports.model import ModelPort
from schemas.analytics import (
    CrossFilterRequest,
    GeoBin,
    GeoBinRequest,
    GeometryRecord,
    Histogram,
    HistogramRequest,
    Sighting,
    SightingRequest,
)
from schemas.domain import (
    Assumption,
    Edge,
    ExpandRequest,
    Hotlist,
    IntelligenceGap,
    Judgement,
    Monitor,
    Node,
    NodeId,
    OntologySchema,
    PathRequest,
    PatternQuery,
    Principal,
    SavedPattern,
)

# `Path` is already `pathlib.Path` in this module — `GraphPath` is the same alias
# `adapters/compute_graphology_tier1/adapter.py` already uses for the identical collision.
from schemas.domain import Path as GraphPath
from schemas.ingest import (
    CONNECTOR_CATALOGUE,
    ConnectDraftInput,
    ConnectorCatalogueEntry,
    LoadReport,
    MapHandlingPreviewRequest,
    MapHandlingPreviewResult,
    MapSampleRow,
    PublishRecipeInput,
    RowTemplateUpdateInput,
    RunRecipeInput,
    ScheduleUpdateInput,
    StudioRecipeDraft,
    StudioRole,
    TransformDescriptor,
    VerifyReport,
)
from schemas.mapconfig import MapConfig, PublicMapConfig
from schemas.profile import SourceProfile

from . import compute_routes as compute_routes_module
from . import dossier as dossier_module
from . import resolution as resolution_module
from . import resolution_trigger as resolution_trigger_module
from . import review as review_module
from . import search as search_module
from .alerts import AlertNotFoundError, AlertStore
from .assessments import (
    AssumptionListResponse,
    AssumptionNotFoundError,
    AssumptionStore,
    GapNotFoundError,
    IntelligenceGapListResponse,
    IntelligenceGapStore,
    JudgementListResponse,
    JudgementNotFoundError,
    JudgementStore,
    NoSupportingReferenceError,
    SaveAssumptionRequest,
    SaveGapRequest,
    SaveJudgementRequest,
    UnverifiableCitationError,
    flag_judgements_citing_superseded_node,
    list_visible_judgements,
    new_assumption,
    new_gap,
    new_judgement,
)
from .audit import AuditWriteError, AuditWriter
from .auth import PrincipalResolutionError, PrincipalResolver, bearer_scheme
from .change_stream import ChangeStreamEntry, ChangeStreamWriter
from .compute_routes import (
    JOB_TYPE_COMPUTE_METRIC,
    ComputeMetricAccepted,
    ComputeMetricName,
    ComputeMetricRequest,
    run_compute_metric_job,
)
from .config import ApiConfig
from .dossier import DocumentView
from .evaluation import evaluate_hotlists_for_entry, evaluate_monitors_for_entry
from .export import (
    ComplianceRoleRequiredError,
    ExportBlockedError,
    ExportLedgerEntry,
    ExportLedgerStore,
    ExportRequest,
    ExportResult,
    OverrideRequiredError,
    submit_export,
)
from .history import (
    HistoryStep,
    HistoryStepNotFoundError,
    HistoryStepSummary,
    InvestigationHistoryStore,
)
from .hotlists import HotlistNotFoundError, HotlistStore
from .investigations import Investigation, InvestigationNotFoundError, InvestigationStore
from .jobs import JobQueue
from .mapconfig_loader import load_map_config, public_view
from .monitors import MonitorNotFoundError, MonitorStore
from .notify import notify_channel, publish_delta
from .pattern_store import PatternNotFoundError, PatternStore
from .patterns import (
    JOB_TYPE_PATTERN_MATCH,
    PatternPreview,
    PatternRunAccepted,
    SavedPatternList,
    SavePatternRequest,
    preview_pattern,
    run_pattern,
    run_pattern_match_job,
)
from .resolution import ManualAssertionRequest, SetThresholdRequest, ThresholdResponse
from .resolution_trigger import ResolveNowAccepted
from .review import (
    AcceptCandidateRequest,
    CandidateNotPendingError,
    DocumentNotFoundError,
    ExtractionCandidateNotFoundError,
    ExtractionCandidateRecord,
    ExtractionCandidateStore,
    NodeIdResponse,
    RejectedResponse,
    RunExtractionRequest,
)
from .search import SearchRequest, SearchResponse
from .site_images import (
    object_key_for,
    read_site_image,
    site_image_storage_config,
    write_site_image,
)
from .sites import ControlPointQuad, Site, SiteNotFoundError, SiteStore
from .studio_map import (
    HandlingLoosenedError,
    RowIndexOutOfRangeError,
    get_sample_row,
    preview_element_handling,
    resolve_source_handling,
    validate_handling_tightens,
)
from .studio_profile import (
    ConnectorNotAvailableError,
    RecipeNotReadyForProfileError,
    SourceHandlingIncompleteError,
    SourceUnreadableError,
    profile_recipe_source,
)
from .studio_publish import (
    GitCommitError,
    RecipeNotRunnableError,
    build_recipe,
    run_published_recipe,
    write_and_commit_recipe,
)
from .studio_recipes import (
    StudioRecipeCannotVersionError,
    StudioRecipeNotADraftError,
    StudioRecipeNotFoundError,
    StudioRecipeNotVerifiedError,
    StudioRecipeStore,
)
from .studio_verify import RowTemplateMissingError, run_verify
from .supersede import JOB_TYPE_SUPERSEDE_NODE, run_supersede_node_job
from .tile_cache import (
    cache_key_for,
    read_cached_tile,
    tile_cache_storage_config,
    write_cached_tile,
)
from .tile_proxy import build_upstream_url, fetch_tile
from .watch_routes import (
    AlertJumpResult,
    AlertList,
    AlertView,
    CreateHotlistRequest,
    CreateMonitorRequest,
    HotlistList,
    MonitorList,
    alert_to_view,
    fetch_jumpable_referents,
)
from .worker import JobWorker
from .working_set.models import (
    CardinalityPreview,
    ClusterExplanation,
    ClusterNotFoundError,
    DeltaNotice,
    DeltaRemove,
    DeltaReproject,
    DeltaSnapshot,
    ExpansionOutcome,
    LimitExceededError,
    NodeNotInWorkingSetError,
    SameNodeAssertionError,
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
    yardstick = load_phia_yardstick()
    ontology = load_default_ontology()
    graph: GraphPort = GraphArcadeDBAdapter(arcadedb_client, handling_scheme)
    await graph.apply_schema(ontology)

    valkey = Valkey(host=config.valkey.host, port=config.valkey.port, db=config.valkey.db)
    audit = await AuditWriter.connect(config.postgres.dsn)
    investigations = await InvestigationStore.connect(config.postgres.dsn)
    history = await InvestigationHistoryStore.connect(config.postgres.dsn)
    sites = await SiteStore.connect(config.postgres.dsn)
    patterns_store = await PatternStore.connect(config.postgres.dsn)
    hotlists_store = await HotlistStore.connect(config.postgres.dsn)
    monitors_store = await MonitorStore.connect(config.postgres.dsn)
    alerts_store = await AlertStore.connect(config.postgres.dsn)
    judgements_store = await JudgementStore.connect(config.postgres.dsn)
    gaps_store = await IntelligenceGapStore.connect(config.postgres.dsn)
    assumptions_store = await AssumptionStore.connect(config.postgres.dsn)
    export_ledger = await ExportLedgerStore.connect(config.postgres.dsn)
    studio_recipes = await StudioRecipeStore.connect(config.postgres.dsn)
    extraction_candidates = await ExtractionCandidateStore.connect(config.postgres.dsn)
    litellm_client = LiteLLMClient(LiteLLMConfig.from_env())
    # `embed_model` is the only model this adapter needs fixed at construction — `extract()`'s own
    # model is caller-supplied per call (`ExtractionRequest.model`, ADR-005), never this adapter's
    # own opinion (`services/api/review.py`'s own docstring on `RunExtractionRequest.model`).
    model: ModelPort = ModelLiteLLMAdapter(litellm_client, embed_model=CONFORMANCE_EMBED_MODEL)
    # `docs/09_INGEST_STUDIO.md` §6's reverse index: "an ontology edit flags
    # every recipe that depends on the changed version". This deployment's
    # only "ontology reload" trigger today is a process restart after a new
    # `packages/ontology/default.yaml` ships — there is no live-reload admin
    # action yet (Phase 8's own territory) — so this is that routine, run
    # once, right after the ontology this process will serve is known.
    await studio_recipes.flag_stale(ontology.version)

    # A persistent (not `:memory:`) DuckDB file — first production wiring of
    # `AnalyticsPort` anywhere in the Conduit yet; `analytics_duckdb/testing.py`'s own
    # docstring records why
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
    app.state.working_set = WorkingSetService(
        graph, ValkeyWorkingSetStore(valkey), handling_scheme, valkey=valkey
    )
    app.state.audit = audit
    app.state.investigations = investigations
    app.state.history = history
    app.state.sites = sites
    app.state.patterns_store = patterns_store
    app.state.hotlists_store = hotlists_store
    app.state.monitors_store = monitors_store
    app.state.alerts_store = alerts_store
    app.state.judgements_store = judgements_store
    app.state.gaps_store = gaps_store
    app.state.assumptions_store = assumptions_store
    app.state.export_ledger = export_ledger
    app.state.studio_recipes = studio_recipes
    app.state.extraction_candidates = extraction_candidates
    app.state.model = model
    app.state.recipes_repo_root = _RECIPES_REPO_ROOT
    app.state.handling_scheme = handling_scheme
    app.state.yardstick = yardstick
    app.state.site_image_storage = site_image_storage_config()
    app.state.tile_cache_storage = tile_cache_storage_config()
    app.state.analytics = analytics
    # `06_DECISIONS.md` ADR-029/Phase 7 Stage 3: Tier 2 only, registered here — Tier 1
    # (`graphology`, a Node harness, conformance-only) and Tier 3 (Phase 8a's `cluster` profile,
    # ADR-028) have no Conduit-side adapter to construct yet. Stateless,
    # same shape as `ComputeRustworkxAdapter`'s
    # own `tests/conformance/registry.py` factory — no client, no lifecycle to close.
    compute: ComputePort = ComputeRustworkxAdapter()
    app.state.compute = compute
    jobs = JobQueue(valkey)
    app.state.jobs = jobs
    # `06_DECISIONS.md` ADR-025: this system's first job-queue worker,
    # generalised by `job_type` rather than resolution-specific — closes
    # `services/api/supersede.py`'s own long-disclosed "no worker attached
    # yet" gap in the same stroke. Constructed and its handlers registered
    # here so a standalone worker process (`services/api/run_worker.py`)
    # has something real to import and drive in a loop; this app process
    # itself does not spin up that loop — running the worker is deployment
    # wiring (its own process/container), not additional Conduit logic.
    job_worker = JobWorker(valkey, jobs, graph)
    job_worker.register(
        JOB_TYPE_SUPERSEDE_NODE,
        functools.partial(run_supersede_node_job, judgement_store=judgements_store),
    )
    job_worker.register(
        JOB_TYPE_RESOLVE_ENTITY_TYPE,
        functools.partial(
            run_resolve_entity_type_job, ontology=ontology, scheme=handling_scheme, valkey=valkey
        ),
    )
    job_worker.register(
        JOB_TYPE_COMPUTE_METRIC, functools.partial(run_compute_metric_job, compute=compute)
    )
    job_worker.register(JOB_TYPE_PATTERN_MATCH, run_pattern_match_job)
    app.state.job_worker = job_worker
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
        await patterns_store.close()
        await hotlists_store.close()
        await monitors_store.close()
        await alerts_store.close()
        await judgements_store.close()
        await gaps_store.close()
        await assumptions_store.close()
        await export_ledger.close()
        await studio_recipes.close()
        await extraction_candidates.close()
        await litellm_client.aclose()
        await app.state.principal_resolver.aclose()
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


def get_jobs(request: Request) -> JobQueue:
    return request.app.state.jobs  # type: ignore[no-any-return]


def get_sites(request: Request) -> SiteStore:
    return request.app.state.sites  # type: ignore[no-any-return]


def get_patterns_store(request: Request) -> PatternStore:
    return request.app.state.patterns_store  # type: ignore[no-any-return]


def get_config(request: Request) -> ApiConfig:
    return request.app.state.config  # type: ignore[no-any-return]


def get_hotlists_store(request: Request) -> HotlistStore:
    return request.app.state.hotlists_store  # type: ignore[no-any-return]


def get_monitors_store(request: Request) -> MonitorStore:
    return request.app.state.monitors_store  # type: ignore[no-any-return]


def get_alerts_store(request: Request) -> AlertStore:
    return request.app.state.alerts_store  # type: ignore[no-any-return]


def get_judgements_store(request: Request) -> JudgementStore:
    return request.app.state.judgements_store  # type: ignore[no-any-return]


def get_gaps_store(request: Request) -> IntelligenceGapStore:
    return request.app.state.gaps_store  # type: ignore[no-any-return]


def get_assumptions_store(request: Request) -> AssumptionStore:
    return request.app.state.assumptions_store  # type: ignore[no-any-return]


def get_export_ledger(request: Request) -> ExportLedgerStore:
    return request.app.state.export_ledger  # type: ignore[no-any-return]


def get_studio_recipes(request: Request) -> StudioRecipeStore:
    return request.app.state.studio_recipes  # type: ignore[no-any-return]


def get_extraction_candidates(request: Request) -> ExtractionCandidateStore:
    return request.app.state.extraction_candidates  # type: ignore[no-any-return]


def get_model(request: Request) -> ModelPort:
    return request.app.state.model  # type: ignore[no-any-return]


def get_recipes_repo_root(request: Request) -> Path:
    return request.app.state.recipes_repo_root  # type: ignore[no-any-return]


def get_handling_scheme(request: Request) -> HandlingScheme:
    return request.app.state.handling_scheme  # type: ignore[no-any-return]


def get_yardstick(request: Request) -> Yardstick:
    return request.app.state.yardstick  # type: ignore[no-any-return]


def get_site_image_storage(request: Request) -> ObjectStorageConfig:
    return request.app.state.site_image_storage  # type: ignore[no-any-return]


def get_tile_cache_storage(request: Request) -> ObjectStorageConfig:
    return request.app.state.tile_cache_storage  # type: ignore[no-any-return]


def get_analytics(request: Request) -> AnalyticsPort:
    return request.app.state.analytics  # type: ignore[no-any-return]


def get_compute(request: Request) -> ComputePort:
    return request.app.state.compute  # type: ignore[no-any-return]


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Principal:
    resolver: PrincipalResolver = request.app.state.principal_resolver
    try:
        return resolver.resolve(credentials.credentials)
    except PrincipalResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def get_principal_resolver(request: Request) -> PrincipalResolver:
    """`06_DECISIONS.md` ADR-043 — the same process-lifetime resolver `get_principal` above
    already uses, exposed as its own dependency so `_evaluate_watches_best_effort`'s own
    `principal_for_owner` can reach `resolve_for_owner` without a second resolver being built."""
    return request.app.state.principal_resolver  # type: ignore[no-any-return]


WorkingSetDep = Annotated[WorkingSetService, Depends(get_working_set)]
AuditDep = Annotated[AuditWriter, Depends(get_audit)]
InvestigationsDep = Annotated[InvestigationStore, Depends(get_investigations)]
HistoryDep = Annotated[InvestigationHistoryStore, Depends(get_history)]
GraphDep = Annotated[GraphPort, Depends(get_graph)]
OntologyDep = Annotated[OntologySchema, Depends(get_ontology)]
MapConfigDep = Annotated[MapConfig, Depends(get_map_config)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]
PrincipalResolverDep = Annotated[PrincipalResolver, Depends(get_principal_resolver)]
SitesDep = Annotated[SiteStore, Depends(get_sites)]
PatternsStoreDep = Annotated[PatternStore, Depends(get_patterns_store)]
ConfigDep = Annotated[ApiConfig, Depends(get_config)]
HotlistsStoreDep = Annotated[HotlistStore, Depends(get_hotlists_store)]
MonitorsStoreDep = Annotated[MonitorStore, Depends(get_monitors_store)]
AlertsStoreDep = Annotated[AlertStore, Depends(get_alerts_store)]
JudgementsStoreDep = Annotated[JudgementStore, Depends(get_judgements_store)]
GapsStoreDep = Annotated[IntelligenceGapStore, Depends(get_gaps_store)]
AssumptionsStoreDep = Annotated[AssumptionStore, Depends(get_assumptions_store)]
ExportLedgerDep = Annotated[ExportLedgerStore, Depends(get_export_ledger)]
StudioRecipesDep = Annotated[StudioRecipeStore, Depends(get_studio_recipes)]
ExtractionCandidatesDep = Annotated[ExtractionCandidateStore, Depends(get_extraction_candidates)]
ModelDep = Annotated[ModelPort, Depends(get_model)]
ComputeDep = Annotated[ComputePort, Depends(get_compute)]
RecipesRepoRootDep = Annotated[Path, Depends(get_recipes_repo_root)]
HandlingSchemeDep = Annotated[HandlingScheme, Depends(get_handling_scheme)]
YardstickDep = Annotated[Yardstick, Depends(get_yardstick)]
JobsDep = Annotated[JobQueue, Depends(get_jobs)]
ValkeyDep = Annotated[Valkey, Depends(get_valkey)]
SiteImageStorageDep = Annotated[ObjectStorageConfig, Depends(get_site_image_storage)]
TileCacheStorageDep = Annotated[ObjectStorageConfig, Depends(get_tile_cache_storage)]
AnalyticsDep = Annotated[AnalyticsPort, Depends(get_analytics)]


def require_studio_role(role: StudioRole) -> Any:
    """Ingest Studio action authorisation (`09_INGEST_STUDIO.md` §8) — a
    dependency factory rather than a bare dependency, since which role a
    route needs varies per route (publish/schedule need `SOURCE_APPROVER`,
    a load needs `LOADER`). Shaped like `get_authorized_investigation`
    below: takes the resolved `Principal`, denies with an `HTTPException`
    rather than filtering silently, and is meant to be wrapped the same
    way (`Depends(require_studio_role(StudioRole.SOURCE_APPROVER))`) once
    a studio route exists to attach it to. A different axis entirely from
    `AccessFilter`'s per-record clearance/handling gate — holding a role
    permits an action, never grants visibility into material."""

    async def _dependency(principal: PrincipalDep) -> Principal:
        if role.value not in principal.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"principal lacks required studio role: {role.value}",
            )
        return principal

    return _dependency


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


async def get_authorized_studio_recipe(
    recipe_id: str,
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
) -> StudioRecipeDraft:
    """Mirrors `get_authorized_site`. `StudioRecipeStore.get_authorized`
    already collapses "no such recipe" and "wrong owning_unit" into the
    same `StudioRecipeNotFoundError`; this wrapper adds the audit record on
    denial. Org-unit scoping, not a `StudioRole` check — §8 does not name a
    role gate for reading your own unit's draft, only for the actions
    (create/edit/publish/schedule) the routes below gate separately."""
    try:
        return await studio_recipes.get_authorized(recipe_id, principal)
    except StudioRecipeNotFoundError:
        await audit.record(
            principal=principal,
            action="access_denied",
            resolved_query={"recipe_id": recipe_id},
            result_cardinality=0,
        )
        raise


AuthorizedStudioRecipeDep = Annotated[StudioRecipeDraft, Depends(get_authorized_studio_recipe)]


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


@app.exception_handler(PatternNotFoundError)
async def _pattern_not_found_handler(
    request: Request, exc: PatternNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "pattern_not_found"}
    )


@app.exception_handler(HotlistNotFoundError)
async def _hotlist_not_found_handler(
    request: Request, exc: HotlistNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "hotlist_not_found"}
    )


@app.exception_handler(JudgementNotFoundError)
async def _judgement_not_found_handler(
    request: Request, exc: JudgementNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "judgement_not_found"}
    )


@app.exception_handler(GapNotFoundError)
async def _gap_not_found_handler(request: Request, exc: GapNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "gap_not_found"})


@app.exception_handler(AssumptionNotFoundError)
async def _assumption_not_found_handler(
    request: Request, exc: AssumptionNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "assumption_not_found"}
    )


@app.exception_handler(NoSupportingReferenceError)
async def _no_supporting_reference_handler(
    request: Request, exc: NoSupportingReferenceError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "no_supporting_reference",
            "detail": "a judgement cannot be saved without at least one supporting reference",
        },
    )


@app.exception_handler(UnverifiableCitationError)
async def _unverifiable_citation_handler(
    request: Request, exc: UnverifiableCitationError
) -> JSONResponse:
    """A `save` refusal, named per-citation, per the invisible-judgement defect's own fix
    (`services/api/assessments.py::UnverifiableCitationError`'s own docstring) — the Glass's own
    error surfacing (`02_GLASS_FRONTEND.md` §4.1) reads `citation_ids` to name the offending
    reference directly, not just `str(exc)`."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "unverifiable_citation",
            "detail": str(exc),
            "citation_ids": exc.citation_ids,
        },
    )


@app.exception_handler(OverrideRequiredError)
async def _override_required_handler(request: Request, exc: OverrideRequiredError) -> JSONResponse:
    """Registered ahead of `ExportBlockedError` below (Starlette resolves the exact exception
    type first) — `OverrideRequiredError` is a subclass carrying the same named blocked items, but
    the copy tells the analyst what to *do*, not only what is wrong (`02_GLASS_FRONTEND.md` §7's
    own "Errors say what happened and what to do")."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "override_required",
            "detail": "a justification and an originator reference are both required to export "
            "past this block",
            "blocked": [b.model_dump(mode="json") for b in exc.blocked],
        },
    )


@app.exception_handler(ExportBlockedError)
async def _export_blocked_handler(request: Request, exc: ExportBlockedError) -> JSONResponse:
    """A15's own literal assertion: a blocking item is named. `exc.blocked` carries every named
    item and its own reason — `access_denied`/`citation_unverifiable` (never overridable) and
    `consult_originator` (overridable, but this handler only fires when `submit_export` itself
    decided not to proceed — e.g. an access-denied item sits alongside an overridable one, and the
    harder block wins)."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "export_blocked",
            "detail": str(exc),
            "blocked": [b.model_dump(mode="json") for b in exc.blocked],
        },
    )


@app.exception_handler(ComplianceRoleRequiredError)
async def _compliance_role_required_handler(
    request: Request, exc: ComplianceRoleRequiredError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "compliance_role_required",
            "detail": "the export ledger's own cross-investigation listing requires the "
            "compliance role",
        },
    )


@app.exception_handler(MonitorNotFoundError)
async def _monitor_not_found_handler(
    request: Request, exc: MonitorNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "monitor_not_found"}
    )


@app.exception_handler(AlertNotFoundError)
async def _alert_not_found_handler(request: Request, exc: AlertNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "alert_not_found"}
    )


@app.exception_handler(NodeNotInWorkingSetError)
async def _node_not_in_working_set_handler(
    request: Request, exc: NodeNotInWorkingSetError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "node_not_in_working_set"}
    )


@app.exception_handler(SameNodeAssertionError)
async def _same_node_assertion_handler(
    request: Request, exc: SameNodeAssertionError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "same_node_assertion"},
    )


@app.exception_handler(ClusterNotFoundError)
async def _cluster_not_found_handler(request: Request, exc: ClusterNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "cluster_not_found"}
    )


@app.exception_handler(ExtractionCandidateNotFoundError)
async def _extraction_candidate_not_found_handler(
    request: Request, exc: ExtractionCandidateNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "extraction_candidate_not_found"}
    )


@app.exception_handler(DocumentNotFoundError)
async def _document_not_found_handler(request: Request, exc: DocumentNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "document_not_found"}
    )


@app.exception_handler(CandidateNotPendingError)
async def _candidate_not_pending_handler(
    request: Request, exc: CandidateNotPendingError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"error": "candidate_not_pending"}
    )


@app.exception_handler(NodeNotFoundError)
async def _node_not_found_handler(request: Request, exc: NodeNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "node_not_found"})


@app.exception_handler(ProvenanceTransitionError)
async def _provenance_transition_handler(
    request: Request, exc: ProvenanceTransitionError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"error": "provenance_transition_invalid"}
    )


@app.exception_handler(StudioRecipeNotFoundError)
async def _studio_recipe_not_found_handler(
    request: Request, exc: StudioRecipeNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "studio_recipe_not_found"}
    )


@app.exception_handler(StudioRecipeNotADraftError)
async def _studio_recipe_not_a_draft_handler(
    request: Request, exc: StudioRecipeNotADraftError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"error": "studio_recipe_not_a_draft"}
    )


@app.exception_handler(RecipeNotReadyForProfileError)
async def _recipe_not_ready_for_profile_handler(
    request: Request, exc: RecipeNotReadyForProfileError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"error": "recipe_not_ready_for_profile"}
    )


@app.exception_handler(RowTemplateMissingError)
async def _row_template_missing_handler(
    request: Request, exc: RowTemplateMissingError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"error": "row_template_missing"}
    )


@app.exception_handler(StudioRecipeNotVerifiedError)
async def _studio_recipe_not_verified_handler(
    request: Request, exc: StudioRecipeNotVerifiedError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"error": "studio_recipe_not_verified"}
    )


@app.exception_handler(StudioRecipeCannotVersionError)
async def _studio_recipe_cannot_version_handler(
    request: Request, exc: StudioRecipeCannotVersionError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"error": "studio_recipe_cannot_version"}
    )


@app.exception_handler(RecipeNotRunnableError)
async def _recipe_not_runnable_handler(
    request: Request, exc: RecipeNotRunnableError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "recipe_not_runnable", "detail": str(exc)},
    )


@app.exception_handler(GitCommitError)
async def _git_commit_error_handler(request: Request, exc: GitCommitError) -> JSONResponse:
    # A real infrastructure failure, not a client input problem — §6's
    # "the repository is the record" only holds if a failed commit never
    # gets a `published` row alongside it, so this is a 500, not a 409.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "git_commit_failed", "detail": str(exc)},
    )


@app.exception_handler(OntologyError)
async def _ontology_error_handler(request: Request, exc: OntologyError) -> JSONResponse:
    """Verify's own recipe-vs-ontology check (`services/ingest/engine.py`'s
    `_dry_run_entity`/`_dry_run_edge`) — a structurally invalid recipe
    (an undeclared type, a missing required property, an illegal edge
    endpoint) fails here the same way it would, uncaught, at real load
    time; never a bare 500, matching every other studio error."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "ontology_violation", "detail": str(exc)},
    )


@app.exception_handler(ConnectorNotAvailableError)
async def _connector_not_available_handler(
    request: Request, exc: ConnectorNotAvailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "connector_not_available", "detail": str(exc)},
    )


@app.exception_handler(SourceUnreadableError)
async def _source_unreadable_handler(request: Request, exc: SourceUnreadableError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "source_unreadable", "detail": str(exc)},
    )


@app.exception_handler(SourceHandlingIncompleteError)
async def _source_handling_incomplete_handler(
    request: Request, exc: SourceHandlingIncompleteError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "source_handling_incomplete", "detail": str(exc)},
    )


@app.exception_handler(RowIndexOutOfRangeError)
async def _row_index_out_of_range_handler(
    request: Request, exc: RowIndexOutOfRangeError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "row_index_out_of_range", "detail": str(exc)},
    )


@app.exception_handler(HandlingLoosenedError)
async def _handling_loosened_handler(request: Request, exc: HandlingLoosenedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "handling_loosened", "detail": str(exc)},
    )


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
    (the "named-step history with restore" capability) — full
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


# --- resolution ---------------------------------------------------------------


@app.get("/v1/investigations/{investigation_id}/resolution/threshold")
async def get_resolution_threshold_route(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
) -> ThresholdResponse:
    result = await resolution_module.get_threshold(working_set, investigation.id)
    await audit.record(
        principal=principal,
        action="get_resolution_threshold",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=1,
    )
    return result


@app.put("/v1/investigations/{investigation_id}/resolution/threshold")
async def set_resolution_threshold_route(
    investigation: AuthorizedInvestigationDep,
    body: SetThresholdRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> DeltaReproject:
    delta = await resolution_module.set_threshold(working_set, investigation.id, body, principal)
    await publish_delta(valkey, investigation.id, delta)
    await audit.record(
        principal=principal,
        action="set_resolution_threshold",
        investigation_id=investigation.id,
        resolved_query={"threshold": body.threshold},
        result_cardinality=delta.affected,
    )
    return delta


@app.post("/v1/investigations/{investigation_id}/resolution/link")
async def link_resolution_route(
    investigation: AuthorizedInvestigationDep,
    body: ManualAssertionRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
    handling_scheme: HandlingSchemeDep,
    config: ConfigDep,
    graph: GraphDep,
    hotlists_store: HotlistsStoreDep,
    monitors_store: MonitorsStoreDep,
    patterns_store: PatternsStoreDep,
    alerts_store: AlertsStoreDep,
    principal_resolver: PrincipalResolverDep,
) -> DeltaReproject:
    """Phase 7 Stage 6c: a manual link is a `SAME_AS` write that can grow a saved pattern's own
    match set (`06_DECISIONS.md` ADR-037's own change-stream amendment names manual assertion as
    one of its three producers) — evaluated synchronously here, the identical shape and the
    identical `run_studio_recipe`'s own docstring reasoning for why only this principal's own
    hotlists/monitors can fire from it. `split_resolution_route` below does not call evaluation at
    all — a `NOT_SAME_AS` write can only shrink a match set, never grow one."""
    delta, entry = await resolution_module.link(working_set, investigation.id, body, principal)
    await publish_delta(valkey, investigation.id, delta)
    if entry is not None:
        await _evaluate_watches_best_effort(
            entry,
            principal=principal,
            graph=graph,
            handling_scheme=handling_scheme,
            config=config,
            hotlists_store=hotlists_store,
            monitors_store=monitors_store,
            patterns_store=patterns_store,
            alerts_store=alerts_store,
            audit=audit,
            valkey=valkey,
            investigation_id=investigation.id,
            action_on_failure="watch_evaluation_failed",
            principal_resolver=principal_resolver,
        )
    await audit.record(
        principal=principal,
        action="manual_link",
        investigation_id=investigation.id,
        resolved_query={"node_a": body.node_a, "node_b": body.node_b},
        result_cardinality=delta.affected,
    )
    return delta


@app.post("/v1/investigations/{investigation_id}/resolution/split")
async def split_resolution_route(
    investigation: AuthorizedInvestigationDep,
    body: ManualAssertionRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> DeltaReproject:
    delta, _entry = await resolution_module.split(working_set, investigation.id, body, principal)
    await publish_delta(valkey, investigation.id, delta)
    await audit.record(
        principal=principal,
        action="manual_split",
        investigation_id=investigation.id,
        resolved_query={"node_a": body.node_a, "node_b": body.node_b},
        result_cardinality=delta.affected,
    )
    return delta


@app.get("/v1/investigations/{investigation_id}/resolution/explain/{cluster_id}")
async def explain_resolution_route(
    investigation: AuthorizedInvestigationDep,
    cluster_id: str,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
) -> ClusterExplanation:
    result = await resolution_module.explain(working_set, investigation.id, cluster_id, principal)
    await audit.record(
        principal=principal,
        action="explain_resolution_cluster",
        investigation_id=investigation.id,
        resolved_query={"cluster_id": cluster_id},
        result_cardinality=len(result.pairs),
    )
    return result


# --- ComputePort: the metrics panel (Phase 7 Stage 3, 06_DECISIONS.md ADR-029) ----------------


@app.post("/v1/investigations/{investigation_id}/compute/{metric}")
async def compute_metric_route(
    investigation: AuthorizedInvestigationDep,
    metric: ComputeMetricName,
    body: ComputeMetricRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    graph: GraphDep,
    compute: ComputeDep,
    jobs: JobsDep,
    audit: AuditDep,
) -> ComputeMetricAccepted:
    accepted = await compute_routes_module.submit_compute_metric(
        metric,
        investigation.id,
        body,
        working_set=working_set,
        graph=graph,
        principal=principal,
        compute=compute,
        jobs=jobs,
    )
    await audit.record(
        principal=principal,
        action=f"compute_{metric}",
        investigation_id=investigation.id,
        resolved_query={"metric": metric, "mode": accepted.mode},
        result_cardinality=len(accepted.values or accepted.communities or {}),
    )
    return accepted


# --- extraction and the review queue -----------------------------------------
#
# Nested under investigations for audit-context consistency with
# `run_studio_recipe` (`09_INGEST_STUDIO.md` §6's own precedent: `investigation_id` is not an
# access-control scope for the produced elements, which join the shared graph/Postgres registry
# like any other write — it is only what the audit row is attributed against). `09_INGEST_STUDIO.md`
# §8's role table has no role for reviewing unstructured extraction candidates at all — it is
# entirely about the structured Connect/Map/Publish/Load workflow — so these routes are gated by
# `AuthorizedInvestigationDep` alone, the same boundary `/seed`/`/expand` already use, not a
# `require_studio_role` this table never names for this path.


@app.post("/v1/investigations/{investigation_id}/ingest/extract")
async def run_extraction_route(
    investigation: AuthorizedInvestigationDep,
    body: RunExtractionRequest,
    principal: PrincipalDep,
    model: ModelDep,
    ontology: OntologyDep,
    extraction_candidates: ExtractionCandidatesDep,
    audit: AuditDep,
) -> list[ExtractionCandidateRecord]:
    records = await review_module.run_extraction(
        model,
        ontology,
        extraction_candidates,
        document_id=body.document_id,
        text=body.text,
        profile=body.profile.to_profile(),
        handling=body.handling,
        principal=principal,
        extraction_model=body.model,
    )
    await audit.record(
        principal=principal,
        action="run_extraction",
        investigation_id=investigation.id,
        resolved_query={"document_id": body.document_id, "entity_types": body.profile.entity_types},
        result_cardinality=len(records),
    )
    return records


@app.get("/v1/investigations/{investigation_id}/ingest/candidates")
async def list_extraction_candidates_route(
    investigation: AuthorizedInvestigationDep,
    document_id: str,
    principal: PrincipalDep,
    extraction_candidates: ExtractionCandidatesDep,
    audit: AuditDep,
) -> list[ExtractionCandidateRecord]:
    records = await extraction_candidates.list_for_document(document_id, principal)
    await audit.record(
        principal=principal,
        action="list_extraction_candidates",
        investigation_id=investigation.id,
        resolved_query={"document_id": document_id},
        result_cardinality=len(records),
    )
    return records


@app.post("/v1/investigations/{investigation_id}/ingest/candidates/{candidate_id}/accept")
async def accept_extraction_candidate_route(
    investigation: AuthorizedInvestigationDep,
    candidate_id: str,
    body: AcceptCandidateRequest,
    principal: PrincipalDep,
    graph: GraphDep,
    extraction_candidates: ExtractionCandidatesDep,
    audit: AuditDep,
) -> NodeIdResponse:
    """`09_INGEST_STUDIO.md` §7: exactly one `candidate_id` per call, no list, no filter, no
    threshold — "no bulk accept" (`services/api/review.py`'s own module docstring) is structural
    here, not a checked rule."""
    node_id = await review_module.accept_candidate(
        extraction_candidates,
        graph,
        candidate_id,
        principal,
        properties_override=body.properties_override,
    )
    await audit.record(
        principal=principal,
        action="accept_extraction_candidate",
        investigation_id=investigation.id,
        resolved_query={"candidate_id": candidate_id},
        result_cardinality=1,
    )
    return NodeIdResponse(node_id=node_id)


@app.post("/v1/investigations/{investigation_id}/ingest/candidates/{candidate_id}/reject")
async def reject_extraction_candidate_route(
    investigation: AuthorizedInvestigationDep,
    candidate_id: str,
    principal: PrincipalDep,
    extraction_candidates: ExtractionCandidatesDep,
    audit: AuditDep,
) -> RejectedResponse:
    await review_module.reject_candidate(extraction_candidates, candidate_id, principal)
    await audit.record(
        principal=principal,
        action="reject_extraction_candidate",
        investigation_id=investigation.id,
        resolved_query={"candidate_id": candidate_id},
        result_cardinality=1,
    )
    return RejectedResponse()


# --- the Dossier (B6, Phase 6a Stage 4) ---------------------------------------
#
# Nested under investigations for the same audit-context reason the extraction/review routes
# above are — `investigation_id` is not this route's own access-control scope (`owning_unit`,
# via `principal`, already is), only what the audit row is attributed against.


@app.get("/v1/investigations/{investigation_id}/dossier/documents/{document_id}")
async def get_dossier_document_route(
    investigation: AuthorizedInvestigationDep,
    document_id: str,
    principal: PrincipalDep,
    graph: GraphDep,
    extraction_candidates: ExtractionCandidatesDep,
    audit: AuditDep,
) -> DocumentView:
    view = await dossier_module.get_document_view(
        extraction_candidates, graph, document_id, principal
    )
    await audit.record(
        principal=principal,
        action="get_dossier_document",
        investigation_id=investigation.id,
        resolved_query={"document_id": document_id},
        result_cardinality=len(view.spans),
    )
    return view


# --- confirm/retract ----------------------------------------------------------
#
# Bare, not nested under an investigation: `provenance.state` is a fact about the node/edge
# itself in the shared Vault, not a per-investigation-session concept the way τ or the working set
# are (`services/extract/writer.py`'s own module docstring). Access control is `GraphPort.get_node`
# alone, exactly the same principal-scoped read every other node lookup in this app already uses
# — there is no second, investigation-shaped gate to add.


@app.post("/v1/nodes/{node_id}/confirm")
async def confirm_node_route(
    node_id: str,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
    judgements: JudgementsStoreDep,
) -> NodeIdResponse:
    tx = await graph.begin_transaction()
    try:
        new_node_id = await confirm_node(graph, node_id, principal, tx=tx)
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    await graph.commit_transaction(tx)
    # `01_DOMAIN_MODEL.md` §5's own review-flag loop: a confirmation is a content change to the
    # node a judgement may cite as `supporting` evidence (`GraphPort.supersede_node`'s own
    # docstring already names this route as one of its two intended callers), so it flags the same
    # way a correction or a retraction does — within the same session, per `08_ACCEPTANCE_
    # SCENARIOS.md`'s own "retraction propagates" assertion, generalised here to every supersede
    # this route performs, not only a retraction specifically.
    flagged = await flag_judgements_citing_superseded_node(judgements, node_id)
    await audit.record(
        principal=principal,
        action="confirm_node",
        resolved_query={"node_id": node_id, "judgements_flagged": flagged},
        result_cardinality=1,
    )
    return NodeIdResponse(node_id=new_node_id)


@app.post("/v1/nodes/{node_id}/retract")
async def retract_node_route(
    node_id: str,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
    judgements: JudgementsStoreDep,
) -> NodeIdResponse:
    tx = await graph.begin_transaction()
    try:
        new_node_id = await retract_node(graph, node_id, principal, tx=tx)
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    await graph.commit_transaction(tx)
    # See `confirm_node_route`'s own comment — the identical review-flag loop, for the case
    # `08_ACCEPTANCE_SCENARIOS.md`'s own "retraction propagates" assertion names directly.
    flagged = await flag_judgements_citing_superseded_node(judgements, node_id)
    await audit.record(
        principal=principal,
        action="retract_node",
        resolved_query={"node_id": node_id, "judgements_flagged": flagged},
        result_cardinality=1,
    )
    return NodeIdResponse(node_id=new_node_id)


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


# --- the visual query builder (Phase 7 Stage 4, 06_DECISIONS.md ADR-030) ------
#
# Not investigation-scoped — `patterns.py`'s own module docstring has the full reasoning, the
# same one `/v1/search` above already gives for its own lack of an `owning_unit` check.


@app.post("/v1/patterns/preview")
async def patterns_preview_route(
    pattern: PatternQuery,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
) -> PatternPreview:
    preview = await preview_pattern(pattern, graph=graph, principal=principal)
    await audit.record(
        principal=principal,
        action="patterns_preview",
        resolved_query=pattern.model_dump(mode="json"),
        result_cardinality=preview.estimated_count,
    )
    return preview


@app.post("/v1/patterns/run")
async def patterns_run_route(
    pattern: PatternQuery,
    principal: PrincipalDep,
    graph: GraphDep,
    jobs: JobsDep,
    audit: AuditDep,
) -> PatternRunAccepted:
    accepted = await run_pattern(pattern, graph=graph, principal=principal, jobs=jobs)
    await audit.record(
        principal=principal,
        action="patterns_run",
        resolved_query=pattern.model_dump(mode="json"),
        result_cardinality=accepted.matched_count or 0,
    )
    return accepted


# --- saved patterns (Phase 7 Stage 4, 06_DECISIONS.md ADR-032/036/040) --------
#
# Owner-only, not investigation-scoped — `pattern_store.py`'s own module docstring has the full
# reasoning. No share route exists: ADR-040 (pattern sharing) is Proposed, not accepted, so there
# is nothing here for a share endpoint to do yet.


@app.post("/v1/patterns/save", status_code=status.HTTP_201_CREATED)
async def patterns_save_route(
    body: SavePatternRequest,
    principal: PrincipalDep,
    patterns_store: PatternsStoreDep,
    audit: AuditDep,
) -> SavedPattern:
    """A `pattern_id` the caller does not own raises `PatternStore`'s own `PatternNotFoundError`
    (mapped to 404 by `_pattern_not_found_handler`) — the same existence-leak collapse
    `get_authorized_investigation` already uses, here inside `PatternStore.save` itself rather
    than a separate route-level gate, since save and the ownership check are one operation."""
    saved = await patterns_store.save(
        principal,
        pattern_id=body.pattern_id,
        name=body.name,
        definition=body.definition,
    )
    await audit.record(
        principal=principal,
        action="patterns_save",
        resolved_query={"pattern_id": saved.pattern_id, "version": saved.version},
        result_cardinality=1,
    )
    return saved


@app.get("/v1/patterns")
async def patterns_list_route(
    principal: PrincipalDep,
    patterns_store: PatternsStoreDep,
) -> SavedPatternList:
    """Never another principal's patterns — `PatternStore.list_authorized` filters by owner in
    the query itself, not after fetching everything."""
    return SavedPatternList(patterns=await patterns_store.list_authorized(principal))


@app.get("/v1/patterns/{pattern_id}")
async def patterns_load_route(
    pattern_id: str,
    principal: PrincipalDep,
    patterns_store: PatternsStoreDep,
    version: int | None = None,
) -> SavedPattern:
    return await patterns_store.get_authorized(pattern_id, principal, version=version)


# --- hotlists, monitors, the alert inbox (Phase 7 Stage 6c) -------------------
#
# Owner-only, not investigation-scoped — the same reasoning `/v1/patterns/*` already gives.
# `Alert.investigation_id` (the triggering event's own investigation, not the hotlist/monitor's
# own creation context — `schemas.domain.Alert`'s own docstring has the full reasoning) is what
# `POST /v1/alerts/{alert_id}/jump` branches a new investigation from.


@app.post("/v1/hotlists", status_code=status.HTTP_201_CREATED)
async def create_hotlist_route(
    body: CreateHotlistRequest,
    principal: PrincipalDep,
    hotlists_store: HotlistsStoreDep,
    audit: AuditDep,
) -> Hotlist:
    hotlist = await hotlists_store.create(
        principal, identifier=body.identifier, review_date=body.review_date
    )
    await audit.record(
        principal=principal,
        action="hotlists_create",
        resolved_query={"hotlist_id": hotlist.id},
        result_cardinality=1,
    )
    return hotlist


@app.get("/v1/hotlists")
async def list_hotlists_route(
    principal: PrincipalDep, hotlists_store: HotlistsStoreDep
) -> HotlistList:
    return HotlistList(hotlists=await hotlists_store.list_authorized(principal))


@app.post(
    "/v1/investigations/{investigation_id}/judgements", status_code=status.HTTP_201_CREATED
)
async def save_judgement_route(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    body: SaveJudgementRequest,
    judgements_store: JudgementsStoreDep,
    graph: GraphDep,
    audit: AuditDep,
) -> Judgement:
    """`investigation.id` (path, `AuthorizedInvestigationDep`-verified), never `body.
    investigation_id` — `SaveJudgementRequest`'s own docstring states this is deliberate, the same
    "path wins over body" rule `create_site` already follows. `NoSupportingReferenceError`/
    `UnverifiableCitationError` propagate to their own handlers above; a raised exception here
    means nothing was written (`JudgementStore.save`'s own docstring)."""
    judgement = new_judgement(
        investigation_id=investigation.id,
        statement=body.statement,
        probability_band=body.probability_band,
        supporting=body.supporting,
        contradicting=body.contradicting,
        author=principal.id,
    )
    saved = await judgements_store.save(judgement, principal, graph)
    await audit.record(
        principal=principal,
        action="judgement_save",
        investigation_id=investigation.id,
        resolved_query={"judgement_id": saved.id},
        result_cardinality=1,
    )
    return saved


@app.get("/v1/investigations/{investigation_id}/judgements")
async def list_judgements_route(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    judgements_store: JudgementsStoreDep,
    graph: GraphDep,
) -> JudgementListResponse:
    """`list_visible_judgements`, not `list_for_investigation` — ADR-046's own hide-in-full rule
    and the lazy `contradicting`-unreadable flag both apply here, not only the ownership check."""
    return JudgementListResponse(
        judgements=await list_visible_judgements(
            judgements_store, investigation.id, principal, graph
        )
    )


@app.post("/v1/investigations/{investigation_id}/gaps", status_code=status.HTTP_201_CREATED)
async def save_gap_route(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    body: SaveGapRequest,
    gaps_store: GapsStoreDep,
    audit: AuditDep,
) -> IntelligenceGap:
    gap = new_gap(
        investigation_id=investigation.id,
        question=body.question,
        raised_by=principal.id,
        linked_entities=body.linked_entities,
        status=body.status,
    )
    saved = await gaps_store.save(gap, principal)
    await audit.record(
        principal=principal,
        action="gap_save",
        investigation_id=investigation.id,
        resolved_query={"gap_id": saved.id},
        result_cardinality=1,
    )
    return saved


@app.get("/v1/investigations/{investigation_id}/gaps")
async def list_gaps_route(
    investigation: AuthorizedInvestigationDep, principal: PrincipalDep, gaps_store: GapsStoreDep
) -> IntelligenceGapListResponse:
    return IntelligenceGapListResponse(
        gaps=await gaps_store.list_for_investigation(investigation.id, principal)
    )


@app.post(
    "/v1/investigations/{investigation_id}/assumptions", status_code=status.HTTP_201_CREATED
)
async def save_assumption_route(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    body: SaveAssumptionRequest,
    assumptions_store: AssumptionsStoreDep,
    audit: AuditDep,
) -> Assumption:
    assumption = new_assumption(
        investigation_id=investigation.id,
        statement=body.statement,
        if_false_impact=body.if_false_impact,
        linked_judgements=body.linked_judgements,
    )
    saved = await assumptions_store.save(assumption, principal)
    await audit.record(
        principal=principal,
        action="assumption_save",
        investigation_id=investigation.id,
        resolved_query={"assumption_id": saved.id},
        result_cardinality=1,
    )
    return saved


@app.get("/v1/investigations/{investigation_id}/assumptions")
async def list_assumptions_route(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    assumptions_store: AssumptionsStoreDep,
) -> AssumptionListResponse:
    return AssumptionListResponse(
        assumptions=await assumptions_store.list_for_investigation(investigation.id, principal)
    )


@app.post("/v1/investigations/{investigation_id}/export")
async def submit_export_route(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    body: ExportRequest,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    judgements_store: JudgementsStoreDep,
    export_ledger: ExportLedgerDep,
    working_set: WorkingSetDep,
    config: ConfigDep,
    audit: AuditDep,
) -> ExportResult:
    """`03_CONDUIT_MIDDLEWARE.md` §6, `06_DECISIONS.md` ADR-045/046/047 — the export gate,
    Phase 8 Stage 4d. `ExportBlockedError`/`OverrideRequiredError`/`ComplianceRoleRequiredError`
    propagate to their own handlers above; a raised exception here means nothing was written to
    the ledger and no `ExportResult` — with its required `mark` — was ever constructed
    (`services/api/export.py::submit_export`'s own docstring). `body` carries no `withheld_count`
    field at all — `submit_export` obtains it from `working_set` itself, never from the client."""
    result = await submit_export(
        investigation_id=investigation.id,
        request=body,
        principal=principal,
        graph=graph,
        scheme=scheme,
        judgements=judgements_store,
        ledger=export_ledger,
        working_set=working_set,
        manifest_policy=config.export_manifest_policy,
    )
    await audit.record(
        principal=principal,
        action="export",
        investigation_id=investigation.id,
        resolved_query={"artefact_kind": body.artefact_kind, "item_count": len(body.items)},
        result_cardinality=len(body.items),
        justification=body.justification,
    )
    return result


class ExportLedgerListResponse(BaseModel):
    entries: list[ExportLedgerEntry]


@app.get("/v1/exports")
async def list_exports_route(
    principal: PrincipalDep, export_ledger: ExportLedgerDep
) -> ExportLedgerListResponse:
    """`06_DECISIONS.md` ADR-047's own Gap 2 — the compliance-facing export ledger's own read
    path. `ExportLedgerStore.list_all` itself raises `ComplianceRoleRequiredError` for a principal
    without the role; deliberately no `AuthorizedInvestigationDep` here at all, since this route's
    entire point is a listing that needs no per-investigation access."""
    return ExportLedgerListResponse(entries=await export_ledger.list_all(principal))


@app.post("/v1/monitors", status_code=status.HTTP_201_CREATED)
async def create_monitor_route(
    body: CreateMonitorRequest,
    principal: PrincipalDep,
    monitors_store: MonitorsStoreDep,
    patterns_store: PatternsStoreDep,
    audit: AuditDep,
) -> Monitor:
    """`pattern_id` ownership proven via `PatternStore.get_authorized` first, the same
    `PatternNotFoundError`-collapse existence-leak discipline every other route in this file
    already uses — `MonitorStore.create`'s own docstring is explicit this is the caller's job, not
    re-derived inside the store from a second, independent ownership check."""
    await patterns_store.get_authorized(body.pattern_id, principal)
    monitor = await monitors_store.create(principal, pattern_id=body.pattern_id)
    await audit.record(
        principal=principal,
        action="monitors_create",
        resolved_query={"monitor_id": monitor.id},
        result_cardinality=1,
    )
    return monitor


@app.get("/v1/monitors")
async def list_monitors_route(
    principal: PrincipalDep, monitors_store: MonitorsStoreDep
) -> MonitorList:
    return MonitorList(monitors=await monitors_store.list_authorized(principal))


@app.get("/v1/alerts")
async def list_alerts_route(
    principal: PrincipalDep, alerts_store: AlertsStoreDep, graph: GraphDep
) -> AlertList:
    rows = await alerts_store.list_authorized(principal)
    return AlertList(alerts=[await alert_to_view(a, principal, graph) for a in rows])


@app.get("/v1/alerts/{alert_id}")
async def get_alert_route(
    alert_id: str, principal: PrincipalDep, alerts_store: AlertsStoreDep, graph: GraphDep
) -> AlertView:
    alert = await alerts_store.get_authorized(alert_id, principal)
    return await alert_to_view(alert, principal, graph)


@app.post("/v1/alerts/{alert_id}/jump", status_code=status.HTTP_201_CREATED)
async def jump_alert_route(
    alert_id: str,
    principal: PrincipalDep,
    alerts_store: AlertsStoreDep,
    graph: GraphDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: ValkeyDep,
) -> AlertJumpResult:
    """`08_ACCEPTANCE_SCENARIOS.md` B14: "The new working set contains the alert's entities and a
    link to the originating investigation." The link is `branch.branched_from` — the identical
    mechanism `branch_investigation` already uses (`investigations.create(principal,
    branched_from=...)`), not new investigation-linking infrastructure. `alert.investigation_id`
    may be `None` (the resolution trigger's own producer carries no single investigation) — the
    branch still succeeds, simply unlinked, disclosed via `Investigation.branched_from` being
    `None` rather than silently pointed at a wrong investigation."""
    alert = await alerts_store.get_authorized(alert_id, principal)
    branch = await investigations.create(principal, branched_from=alert.investigation_id)
    nodes, unreadable = await fetch_jumpable_referents(alert, principal=principal, graph=graph)
    outcome = await working_set.seed(branch.id, nodes, [], principal)
    await publish_delta(valkey, branch.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        branch.id,
        seq=outcome.delta.seq,
        label=f"Opened from alert {alert.id}",
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="alerts_jump",
        investigation_id=branch.id,
        resolved_query={"alert_id": alert.id, "from_investigation_id": alert.investigation_id},
        result_cardinality=len(nodes),
    )
    return AlertJumpResult(
        investigation=branch, seeded_count=len(nodes), unreadable_count=unreadable
    )


# --- the pathfinder (Phase 7 Stage 5) -----------------------------------------
#
# Not investigation-scoped — the same reasoning `/v1/search` and `/v1/patterns/*` already give:
# a path search is a query over the whole, principal-filtered corpus, not a property of any one
# working set (`01_DOMAIN_MODEL.md` §6.3, `06_DECISIONS.md` ADR-033's own "FIRST" reasoning — the
# working set is what an analyst has already chosen to look at; the pathfinder exists to find a
# route through nodes not yet on it, which scoping to the working set would defeat).
#
# No preview, no job hand-off, unlike `/v1/patterns/*`: `PathRequest.k` bounds the result size by
# construction (`.limit(k)` in the compiled query, not a display cap racing a larger true
# population), so there is no undisclosed larger number a preview would need to surface — ADR
# -033's own "THIRD" reasoning has the full argument. `GraphPort.paths` is called directly, never
# `ComputePort.shortest_paths` (unclaimed, `ports/compute.py`'s own disclosed stub).


@app.post("/v1/paths")
async def paths_route(
    req: PathRequest,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
) -> list[GraphPath]:
    found = await graph.paths(req, principal)
    await audit.record(
        principal=principal,
        action="paths",
        resolved_query=req.model_dump(mode="json"),
        result_cardinality=len(found),
    )
    return found


# --- the corpus-wide resolution trigger (06_DECISIONS.md ADR-025) -------------


@app.post("/v1/resolution/{entity_type}/run")
async def resolve_now_route(
    entity_type: str,
    principal: PrincipalDep,
    ontology: OntologyDep,
    jobs: JobsDep,
    audit: AuditDep,
) -> ResolveNowAccepted:
    """Not investigation-scoped — `resolution_trigger.py`'s own docstring has the full reasoning,
    the same one `/v1/search` already gives for its own lack of an `owning_unit` check."""
    accepted = await resolution_trigger_module.resolve_now(
        entity_type, ontology=ontology, jobs=jobs
    )
    await audit.record(
        principal=principal,
        action="resolve_now",
        resolved_query={"entity_type": entity_type},
        result_cardinality=1,
    )
    return accepted


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


# --- analytics -----------------------------------------------------------
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


@app.post("/v1/analytics/sightings")
async def sightings_route(
    body: SightingRequest, principal: PrincipalDep, analytics: AnalyticsDep, audit: AuditDep
) -> list[Sighting]:
    """Phase 8 Stage 4f, B18's own snail trail — `packages/ports/analytics.py::AnalyticsPort.
    list_sightings`'s own docstring has the full record of why this route is new."""
    result = await analytics.list_sightings(body, principal)
    await audit.record(
        principal=principal,
        action="analytics_sightings",
        investigation_id=body.filter.investigation_scope,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=len(result),
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

#: Publish's own git-repository root (§6: recipes commit to `recipes/<id>.
#: yaml` at the repository root) — the same `.parents[2]` computation as
#: `_SITE_GRID_RECIPE_PATH` above. An `app.state` value, not a bare module
#: constant `studio_publish.py` reaches for on its own, so a route test can
#: point it at a throwaway git repo (`app.dependency_overrides
#: [get_recipes_repo_root]`) instead of committing into this checkout.
_RECIPES_REPO_ROOT = Path(__file__).resolve().parents[2]


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
    has no `AnalyticsPort` wired in yet. Every `Location` gets a real, deterministic
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


# --- ingest studio: connect (09_INGEST_STUDIO.md §2) -------------------------


@app.get("/v1/ingest/connectors")
async def list_connectors(principal: PrincipalDep) -> list[ConnectorCatalogueEntry]:
    """§2's structured/unstructured connector catalogue. Deployment
    metadata, not material — same justification `get_ontology_route` gives
    itself: authenticated so the route isn't open to the world, but not
    investigation-scoped and not audited, since nothing here is a node, a
    property value or a count."""
    return list(CONNECTOR_CATALOGUE)


@app.get("/v1/handling-scheme")
async def get_handling_scheme_route(
    principal: PrincipalDep, scheme: HandlingSchemeDep
) -> HandlingScheme:
    """The active deployment's classification/handling-code vocabulary —
    what Connect's handling-marking gate question offers as choices. Same
    treatment as `GET /v1/ontology`: schema metadata, not a disclosure of
    any record's own handling."""
    return scheme


@app.get("/v1/yardstick")
async def get_yardstick_route(principal: PrincipalDep, yardstick: YardstickDep) -> Yardstick:
    """The active deployment's probability yardstick (`01_DOMAIN_MODEL.md` §5) — what the
    Judgements tab's own band `Select` populates from (`02_GLASS_FRONTEND.md` §9.3: "generated
    from the loaded yardstick file, not hardcoded"). Same treatment as `GET /v1/handling-scheme`:
    schema/config metadata, not a disclosure of any record's own content."""
    return yardstick


@app.post("/v1/ingest/recipes", status_code=status.HTTP_201_CREATED)
async def create_studio_recipe_draft(
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    body: ConnectDraftInput,
) -> StudioRecipeDraft:
    """§8: "Source author: create and edit draft recipes." A fresh draft —
    Connect's "pick a connector, point at the data" plus the three
    mandatory gate answers, which may still be incomplete
    (`StudioRecipeDraft.ready_for_profile` reports that, §2)."""
    draft = await studio_recipes.create_draft(
        principal,
        label=body.label,
        connector_profile=body.connector_profile,
        source_location=body.source_location,
        handling=body.handling,
        legal_basis=body.legal_basis,
    )
    await audit.record(
        principal=principal,
        action="create_studio_recipe_draft",
        resolved_query={"recipe_id": draft.recipe_id},
        result_cardinality=1,
    )
    return draft


@app.patch("/v1/ingest/recipes/{recipe_id}")
async def update_studio_recipe_draft(
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    body: ConnectDraftInput,
) -> StudioRecipeDraft:
    """Edits Connect's own fields on a draft still in progress — changing
    connector, source location, handling marking or legal basis before
    moving on. Rejects (409, via `StudioRecipeNotADraftError`) once the
    recipe has left `draft` status."""
    updated = await studio_recipes.update_draft(
        recipe.recipe_id,
        principal,
        label=body.label,
        connector_profile=body.connector_profile,
        source_location=body.source_location,
        handling=body.handling,
        legal_basis=body.legal_basis,
    )
    await audit.record(
        principal=principal,
        action="update_studio_recipe_draft",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )
    return updated


@app.get("/v1/ingest/recipes/{recipe_id}")
async def get_studio_recipe_draft(
    recipe: AuthorizedStudioRecipeDep, principal: PrincipalDep, audit: AuditDep
) -> StudioRecipeDraft:
    await audit.record(
        principal=principal,
        action="get_studio_recipe_draft",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )
    return recipe


@app.get("/v1/ingest/recipes")
async def list_studio_recipe_drafts(
    principal: PrincipalDep, studio_recipes: StudioRecipesDep, audit: AuditDep
) -> list[StudioRecipeDraft]:
    """Connect's "resume a draft" list — the author's own unit's drafts
    only (`StudioRecipeStore.list_drafts`' own `owning_unit` scoping)."""
    drafts = await studio_recipes.list_drafts(principal)
    await audit.record(
        principal=principal,
        action="list_studio_recipe_drafts",
        resolved_query={},
        result_cardinality=len(drafts),
    )
    return drafts


# --- ingest studio: profile (09_INGEST_STUDIO.md §3) -------------------------


@app.get("/v1/ingest/recipes/{recipe_id}/profile")
async def get_studio_recipe_profile(
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> SourceProfile:
    """§3: automatic, and the studio does not let you map until it has run.
    Reads the sample itself (`services/api/studio_profile.py` dispatches to
    the one available connector) and calls the Phase 2 profiler
    (`services/ingest/profiler.profile_source`) under this principal's own
    clearance, so shape-masking (§3's independent-minimums rule) is exactly
    as strict here as it is for any other read of this source."""
    profile = await profile_recipe_source(recipe, principal, scheme)
    await audit.record(
        principal=principal,
        action="get_studio_recipe_profile",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=len(profile.columns),
    )
    return profile


# --- ingest studio: map (09_INGEST_STUDIO.md §4) ------------------------------


@app.get("/v1/ingest/transforms")
async def list_transforms(principal: PrincipalDep) -> list[TransformDescriptor]:
    """The Knowledge Adapter catalogue Map's transform picker and arity
    check read from — `knowledge_adapters.REGISTRY`/`ARITY`, never
    hand-duplicated in the Glass. Deployment metadata, same treatment as
    `list_connectors`. An adapter absent from `ARITY` takes a single
    `field`, never a `fields` list (that module's own docstring)."""
    return [TransformDescriptor(name=name, arity=ARITY.get(name, 1)) for name in REGISTRY]


@app.put("/v1/ingest/recipes/{recipe_id}/row-template")
async def update_studio_recipe_row_template(
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
    body: RowTemplateUpdateInput,
) -> StudioRecipeDraft:
    """Map's save (§4). Every element's own `handling` override is checked
    against the draft's source-level marking before anything is written —
    §3's independent-minimums rule: an override may tighten, never loosen,
    what Connect already set (`validate_handling_tightens`,
    `services/api/studio_map.py`). Gated on `ready_for_profile` the same
    way Profile is (§3: "the studio does not let you map until it has
    run") — `resolve_source_handling` is Profile's own defense-in-depth
    check reused, not a second implementation of it."""
    if not recipe.ready_for_profile:
        raise RecipeNotReadyForProfileError(recipe.recipe_id)
    baseline = resolve_source_handling(recipe)
    for entity in body.row_template.entities:
        validate_handling_tightens(baseline, entity.handling, scheme)
    for edge in body.row_template.edges:
        validate_handling_tightens(baseline, edge.handling, scheme)
    updated = await studio_recipes.update_row_template(
        recipe.recipe_id,
        principal,
        row_template=body.row_template,
        unmapped_fields=body.unmapped_fields,
    )
    await audit.record(
        principal=principal,
        action="update_studio_recipe_row_template",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )
    return updated


@app.get("/v1/ingest/recipes/{recipe_id}/map/sample-rows/{row_index}")
async def get_studio_recipe_sample_row(
    recipe: AuthorizedStudioRecipeDep,
    row_index: int,
    principal: PrincipalDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> MapSampleRow:
    """§4: "the template is always shown bound to a real row, and the
    analyst can page through." Reads the same bounded sample Profile does,
    masked exactly like `GET .../profile` when the principal isn't cleared
    for the source's own marking."""
    row = await get_sample_row(recipe, principal, scheme, row_index)
    await audit.record(
        principal=principal,
        action="get_studio_recipe_sample_row",
        resolved_query={"recipe_id": recipe.recipe_id, "row_index": row_index},
        result_cardinality=1,
    )
    return row


@app.post("/v1/ingest/recipes/{recipe_id}/map/handling-preview")
async def preview_studio_recipe_element_handling(
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    audit: AuditDep,
    body: MapHandlingPreviewRequest,
) -> MapHandlingPreviewResult:
    """§4: what an in-progress element's handling/provenance override would
    resolve to, via `preview_handling_and_provenance()`
    (`services/ingest/engine.py`) — the same function Verify's dry run
    calls, so Map and Verify never disagree about this. Gated on
    `ready_for_profile`, same reason as the row-template save above: an
    incomplete `handling` has no baseline to preview an override against."""
    if not recipe.ready_for_profile:
        raise RecipeNotReadyForProfileError(recipe.recipe_id)
    handling, provenance = await preview_element_handling(recipe, body)
    await audit.record(
        principal=principal,
        action="preview_studio_recipe_element_handling",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )
    return MapHandlingPreviewResult(handling=handling, provenance=provenance)


# --- ingest studio: verify (09_INGEST_STUDIO.md §5) ---------------------------


@app.post("/v1/ingest/recipes/{recipe_id}/verify")
async def verify_studio_recipe(
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    scheme: HandlingSchemeDep,
    graph: GraphDep,
    ontology: OntologyDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
) -> VerifyReport:
    """§5: the dry run. No persistent write of any kind happens here — no
    Parquet staging, no `GraphPort` write, no transaction — but an
    `on_match: reference` element's lookup against the *existing* graph
    goes through the ordinary `GraphPort.find_node` under this principal's
    own clearance (`services/ingest/engine.py`'s `dry_run_recipe`), which is
    the actual mechanism behind §5's "an author cannot use a dry run to see
    material they could not otherwise see": an access-filtered miss reads
    as `None`, exactly like any other read, so it shows as "would create"
    rather than leaking that a higher-classification match exists."""
    report = await run_verify(recipe, principal, scheme, graph, ontology)
    # §5: "Verify must pass before publish" — recorded here, against a
    # *completed* run (rejections included, per §5's own "a run with
    # rejections can be published"), so `publish` below can gate on this
    # flag alone rather than re-running the dry run itself.
    await studio_recipes.mark_verified(recipe.recipe_id, recipe.version, now=datetime.now(UTC))
    await audit.record(
        principal=principal,
        action="verify_studio_recipe",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=len(report.nodes) + len(report.edges),
    )
    return report


# --- ingest studio: publish (09_INGEST_STUDIO.md §6) --------------------------


@app.get("/v1/ingest/recipe-registry")
async def list_studio_recipe_registry(
    principal: PrincipalDep, studio_recipes: StudioRecipesDep, audit: AuditDep
) -> list[StudioRecipeDraft]:
    """Publish's own listing — every recipe the principal's own unit owns
    at whatever status (draft/published/flagged/superseded), not only
    drafts (`GET /v1/ingest/recipes`, Connect's narrower "resume a draft"
    list). A distinct path rather than a query parameter on the existing
    route, since `GET /v1/ingest/recipes/{recipe_id}` is already registered
    and a literal suffix here would collide with that path parameter."""
    recipes = await studio_recipes.list_all(principal)
    await audit.record(
        principal=principal,
        action="list_studio_recipe_registry",
        resolved_query={},
        result_cardinality=len(recipes),
    )
    return recipes


@app.post("/v1/ingest/recipes/{recipe_id}/publish")
async def publish_studio_recipe(
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_APPROVER))],
    studio_recipes: StudioRecipesDep,
    ontology: OntologyDep,
    repo_root: RecipesRepoRootDep,
    audit: AuditDep,
    body: PublishRecipeInput,
) -> StudioRecipeDraft:
    """§6/§8: draft → published, source-approver only — this same gate is
    what §8's "approve a mapping that changes an existing recipe's
    semantics" means for a recipe reopened by `POST .../versions` below:
    there is no separate "approve" action, publishing the new version *is*
    the sign-off. Writes the YAML and commits it before flipping the
    registry row (`StudioRecipeStore.publish` itself enforces "Verify must
    pass" via `verified_at`), so a `published` row never exists without a
    matching commit — the reverse of that (a commit with no `published`
    row, if the registry write somehow failed) is the safer order given
    §6's own "the repository is the record"."""
    built = build_recipe(
        recipe,
        ontology_version=ontology.version,
        schedule_cron=body.schedule_cron,
        schedule_watch=body.schedule_watch,
    )
    git_path = await write_and_commit_recipe(built, repo_root=repo_root)
    updated = await studio_recipes.publish(
        recipe.recipe_id,
        principal,
        ontology_version=ontology.version,
        git_path=git_path,
        schedule_cron=body.schedule_cron,
        schedule_watch=body.schedule_watch,
        now=datetime.now(UTC),
    )
    await audit.record(
        principal=principal,
        action="publish_studio_recipe",
        resolved_query={"recipe_id": recipe.recipe_id, "git_path": git_path},
        result_cardinality=1,
    )
    return updated


@app.patch("/v1/ingest/recipes/{recipe_id}/schedule")
async def update_studio_recipe_schedule(
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_APPROVER))],
    studio_recipes: StudioRecipesDep,
    ontology: OntologyDep,
    repo_root: RecipesRepoRootDep,
    audit: AuditDep,
    body: ScheduleUpdateInput,
) -> StudioRecipeDraft:
    """§8: "schedule it" — a source-approver action distinct from
    `publish`. Re-commits the recipe YAML with the new schedule (the
    repository stays the record for the schedule too, not only the
    mapping) at the same `git_path`, without bumping `version` — the
    mapping itself is unchanged."""
    updated = await studio_recipes.update_schedule(
        recipe.recipe_id,
        principal,
        schedule_cron=body.schedule_cron,
        schedule_watch=body.schedule_watch,
    )
    assert updated.row_template is not None and updated.ontology_version is not None
    built = build_recipe(
        updated,
        ontology_version=updated.ontology_version,
        schedule_cron=body.schedule_cron,
        schedule_watch=body.schedule_watch,
    )
    await write_and_commit_recipe(built, repo_root=repo_root)
    await audit.record(
        principal=principal,
        action="update_studio_recipe_schedule",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )
    return updated


@app.post("/v1/ingest/recipes/{recipe_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_studio_recipe_version(
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
) -> StudioRecipeDraft:
    """Reopens a published/flagged recipe for further editing — a fresh
    `status='draft'` row one version ahead, so Map's existing row-template
    routes (draft-only) work on it unchanged. Author-gated: opening a
    mapping for edit is authoring; publishing the result is what needs
    approval (the `publish` route above)."""
    updated = await studio_recipes.create_new_version(
        recipe.recipe_id, principal, now=datetime.now(UTC)
    )
    await audit.record(
        principal=principal,
        action="create_studio_recipe_version",
        resolved_query={"recipe_id": recipe.recipe_id, "version": updated.version},
        result_cardinality=1,
    )
    return updated


@app.post("/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/run")
async def run_studio_recipe(
    investigation: AuthorizedInvestigationDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.LOADER))],
    graph: GraphDep,
    ontology: OntologyDep,
    repo_root: RecipesRepoRootDep,
    audit: AuditDep,
    jobs: JobsDep,
    valkey: ValkeyDep,
    body: RunRecipeInput,
    handling_scheme: HandlingSchemeDep,
    config: ConfigDep,
    hotlists_store: HotlistsStoreDep,
    monitors_store: MonitorsStoreDep,
    patterns_store: PatternsStoreDep,
    alerts_store: AlertsStoreDep,
    principal_resolver: PrincipalResolverDep,
) -> LoadReport:
    """§8: "Loader: run a published recipe against a file at or below
    their own clearance" — `body.source_location`, when given, is that
    file; omitted, this repeats against the recipe's own recorded location
    (§6: "re-runnable... the deduplication key makes a re-run idempotent").
    `investigation_id` is carried onto the produced `EventRecord`s'
    `investigation_scope` for analytics filtering (`schemas.analytics.
    EventRecord`) — it is not an access-control scope for the loaded
    elements themselves, which join the shared graph like any other load.

    Also the post-ingest half of `06_DECISIONS.md` ADR-025's corpus-wide
    resolution trigger: a load that actually creates something submits a
    resolution job per resolvable entity type the recipe declares
    (`resolution_trigger.submit_post_ingest_resolution_jobs`) — this is the
    only route through which an ingest can ever raise a hotlist/
    saved-pattern alert against a live deployment, not fixture data
    assembled by a test harness.

    Also ingest's own producer onto the corpus-wide change stream (`06_DECISIONS.md` ADR-037's
    amendment, Phase 7 Stage 6a — `services/api/change_stream.py`'s own docstring).

    **Phase 7 Stage 6c: the change-stream entry, once published, is also evaluated synchronously,
    in this same request.** `06_DECISIONS.md` ADR-036's own amendment recorded why the
    cross-analyst case did not fire before Phase 8 Stage 1 (no principal directory existed to
    resolve any other owner's principal from); **ADR-043 (Phase 8 Stage 1) closes that** — a
    hotlist/monitor owned by an analyst other than this route's own requester can now fire too,
    via `PrincipalResolver.resolve_for_owner`'s own OAuth2 Token Exchange, not only this same
    principal's own. Ingest and manual-assertion (`link_resolution_route`) are both wired to
    synchronous evaluation; corpus-wide resolution still is not — a separate, structural
    job/worker-boundary gap ADR-043 does not touch (see that ADR's own amendment). B13/B20, the
    rows Stage 6 exists for, are both about ingest specifically. Bounded per-hotlist/monitor by
    `evaluation.py`'s own overlap lock and
    `MAX_TOUCHED_NODES_PER_EVALUATION`; **not** bounded in aggregate — this request now blocks on
    evaluating every active hotlist and monitor this principal owns, not a fixed number of them,
    a disclosed cost rather than one silently absorbed into ingest latency. A
    failure in this best-effort side evaluation is caught and audited, never allowed to fail the
    ingest response itself — the load already happened; a failure to also check watches against it
    is a narrower, disclosed problem, not a reason to tell the caller their load failed when it
    didn't."""
    load_id = new_id()
    report = await run_published_recipe(
        recipe,
        principal,
        graph=graph,
        ontology=ontology,
        load_id=load_id,
        investigation_scope=investigation.id,
        source_location=body.source_location,
        repo_root=repo_root,
    )
    await resolution_trigger_module.submit_post_ingest_resolution_jobs(
        report, recipe.row_template, ontology=ontology, jobs=jobs
    )
    entry = await ChangeStreamWriter(valkey).publish(
        "ingest",
        node_ids=report.created_node_ids,
        edge_ids=report.touched_edge_ids,
        investigation_id=investigation.id,
    )
    if entry is not None:
        await _evaluate_watches_best_effort(
            entry,
            principal=principal,
            graph=graph,
            handling_scheme=handling_scheme,
            config=config,
            hotlists_store=hotlists_store,
            monitors_store=monitors_store,
            patterns_store=patterns_store,
            alerts_store=alerts_store,
            audit=audit,
            valkey=valkey,
            investigation_id=investigation.id,
            action_on_failure="watch_evaluation_failed",
            error_context={"load_id": load_id},
            principal_resolver=principal_resolver,
        )
    await audit.record(
        principal=principal,
        action="run_studio_recipe",
        investigation_id=investigation.id,
        resolved_query={"recipe_id": recipe.recipe_id, "load_id": load_id},
        result_cardinality=report.nodes_created + report.edges_created,
    )
    return report


async def _evaluate_watches_best_effort(
    entry: ChangeStreamEntry,
    *,
    principal: Principal,
    graph: GraphPort,
    handling_scheme: HandlingScheme,
    config: ApiConfig,
    hotlists_store: HotlistStore,
    monitors_store: MonitorStore,
    patterns_store: PatternStore,
    alerts_store: AlertStore,
    audit: AuditWriter,
    valkey: Valkey,
    investigation_id: str,
    action_on_failure: str,
    principal_resolver: PrincipalResolver,
    error_context: dict[str, Any] | None = None,
) -> None:
    """Shared by every producer route wired to synchronous evaluation this stage
    (`run_studio_recipe`, `link_resolution_route`) — the identical `principal_for_owner` and the
    identical best-effort failure containment, factored out rather than duplicated a second time
    verbatim. A failure here is caught and audited, never allowed to fail the caller's own
    already-succeeded primary operation.

    **`principal_for_owner`, `06_DECISIONS.md` ADR-043 (Phase 8 Stage 1).** The requester's own id
    resolves instantly, with no network call — no exchange is needed to learn what this route
    already knows. Any other owner goes through `principal_resolver.resolve_for_owner` (OAuth2
    Token Exchange) — a real, live, per-call resolution, never cached (ADR-036's own "resolved
    fresh" requirement, ADR-043's own freshness argument): a revoked or otherwise-unreachable
    owner resolves to `None` on this call and the next, with nothing here holding onto whatever a
    prior call once returned."""

    async def _principal_for_owner(owner_id: str) -> Principal | None:
        if owner_id == principal.id:
            return principal
        return await principal_resolver.resolve_for_owner(owner_id)

    try:
        await evaluate_hotlists_for_entry(
            entry,
            graph=graph,
            scheme=handling_scheme,
            hotlist_store=hotlists_store,
            alert_store=alerts_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for_owner,
            policy=config.hotlist_alert_policy,
        )
        await evaluate_monitors_for_entry(
            entry,
            graph=graph,
            monitor_store=monitors_store,
            pattern_store=patterns_store,
            alert_store=alerts_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=_principal_for_owner,
        )
    except Exception as exc:  # noqa: BLE001 - a best-effort side channel, see this function's
        # own docstring: must never fail the caller's own already-succeeded primary operation.
        # Audited, not silently swallowed.
        await audit.record(
            principal=principal,
            action=action_on_failure,
            investigation_id=investigation_id,
            resolved_query={**(error_context or {}), "error": str(exc)},
            result_cardinality=0,
        )


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
