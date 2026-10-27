"""The Conduit's FastAPI app — `spec/03_CONDUIT_MIDDLEWARE.md` §1/§3.

**Stateless.** Every `app.state` attribute below is a client for an
external store (ArcadeDB, Valkey, Postgres); none of it is session or
working-set state, which lives entirely in Valkey via `working_set/
store.py`. Two instances of this app, started independently, serve any
request for any investigation identically — `tests/services/api/
test_statelessness.py` is the proof this phase's exit criterion asks for
("kill the instance serving a session mid-investigation and the analyst
notices nothing").

**Every route audits before it discloses or before it returns success.**
`spec/00_ARCHITECTURE.md` §5 / `03_CONDUIT_MIDDLEWARE.md` §8: "an
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
import csv
import functools
import io
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, Final, Literal, cast

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator, model_validator
from scripts.build_local_basemap import GEOFABRIK_REGIONS, BasemapBuildResult, build_local_basemap
from scripts.verify_map import verify_map
from services.extract.writer import (
    NodeNotFoundError,
    ProvenanceTransitionError,
    confirm_node,
    retract_node,
)
from services.ingest.connectors.geo.site_grid import site_grid_rows
from services.ingest.engine import RowKeyDefinitionChanged, RowKeyRunInProgress, run_recipe
from services.ingest.pipeline import (
    pipeline_from_recipe,
    pipeline_rule_violations,
    pipeline_run_violations,
)
from services.ingest.recipe_loader import load_recipe
from services.ingest.recipe_rules import (
    RecipeRuleError,
    check_recipe_rules,
    deduplicate_problems,
    handling_bindings,
    template_elements,
)
from services.ingest.staging import ObjectStorageConfig
from services.ingest.transforms import STRUCTURED_PARTS
from services.resolve.trigger import (
    JOB_TYPE_RESOLVE_ENTITY_TYPE,
    run_resolve_entity_type_job,
    service_principal,
)
from valkey.asyncio import Valkey

from adapters.model_litellm.adapter import ModelLiteLLMAdapter
from adapters.model_litellm.client import LiteLLMClient, LiteLLMConfig
from adapters.model_litellm.errors import ExtractionFailedError, ModelUnavailableError
from conduit_common.identity import new_edge_id, new_id, now_utc
from geo.bilinear import ControlPoint
from geo.image_dimensions import (
    UnsupportedImageFormatError,
    image_content_type,
    image_dimensions,
)
from geo.wkb import polygon_wkb
from knowledge_adapters import ARITY, REGISTRY
from ontology.errors import OntologyError
from ontology.handling import HandlingScheme, principal_may_view
from ontology.packs import pack_catalogue
from ontology.pattern_where import PatternConditionRefused, check_pattern_conditions
from ontology.yardstick import Yardstick, load_phia_yardstick
from ports.analytics import AnalyticsPort, TrendLimitExceeded
from ports.compute import ComputePort
from ports.graph import GraphPort
from ports.media import MediaStore
from ports.model import ModelPort
from ports.recognise import RecogniserRefusedError, RecogniserUnavailableError
from schemas.admin import (
    AccessInput,
    AdminSchedule,
    ChangeScheduleInput,
    ComponentHealth,
    DashboardGuestToken,
    DashboardIdentity,
    DashboardInput,
    DataFeed,
    DemoPackStatus,
    EmbeddedDashboard,
    InviteInput,
    PauseScheduleInput,
    PersonAccount,
    RegisteredDashboard,
    RolesInput,
    ScheduleRunView,
    SignInDelivery,
    SystemStatus,
)
from schemas.analytics import (
    CaseEventHolder,
    CaseEvents,
    CrossFilterRequest,
    EventFilter,
    EventListRequest,
    FirstSeenRequest,
    FirstSeenResult,
    GeoBin,
    GeoBinRequest,
    GeocodeRequest,
    GeometryKind,
    GeometryRecord,
    Histogram,
    HistogramRequest,
    Sighting,
    SightingRequest,
)
from schemas.compute import OwnershipTooComplex, OwnershipView
from schemas.domain import (
    Alert,
    AlertDispositionInput,
    AlertExplanation,
    Assumption,
    Connections,
    ConnectionsRequest,
    DomainPack,
    Edge,
    EdgeWrite,
    ExpandRequest,
    Handling,
    HeldRow,
    HeldRowDecision,
    Hotlist,
    IntelligenceGap,
    Interval,
    Judgement,
    KycStatus,
    LinkNote,
    Monitor,
    NeighbourhoodRisk,
    Node,
    NodeId,
    NodeWrite,
    OntologySchema,
    PathRequest,
    PatternQuery,
    Principal,
    Provenance,
    ProvenanceState,
    QueuedAlert,
    ReportFigures,
    RuleAuditPage,
    SavedPattern,
    SourceRef,
    TypologyRule,
    TypologyRuleInput,
)

# `Path` is already `pathlib.Path` in this module — `GraphPath` is the same alias
# `adapters/compute_graphology_tier1/adapter.py` already uses for the identical collision.
from schemas.domain import Path as GraphPath
from schemas.explore import (
    BusiestDays,
    Groups,
    RankedLinks,
    RankedNodes,
    SharedContacts,
    StarterQuestions,
    TypeCounts,
    WhatsNew,
)
from schemas.ingest import (
    CONNECTOR_CATALOGUE,
    ConnectDraftInput,
    ConnectorCatalogueEntry,
    DeduplicateConfig,
    DomainPackEntry,
    LoadReportView,
    MapHandlingPreviewRequest,
    MapHandlingPreviewResult,
    MapSampleRow,
    PipelineGraph,
    PipelineRunReportView,
    PublishRecipeInput,
    RowTemplateUpdateInput,
    RunRecipeInput,
    SchedulePreview,
    SchedulePreviewInput,
    ScheduleUpdateInput,
    StudioRecipeDraft,
    StudioRecipeStatus,
    StudioRole,
    TransformDescriptor,
    VerifyReport,
)
from schemas.mapconfig import MapConfig, PublicMapConfig
from schemas.packs import (
    AddPackItem,
    PackDraft,
    PackExport,
    PackExportRequest,
    PackHistory,
    PackInput,
    PackItem,
    PackOrder,
    PackVersionSummary,
    PackWithdrawal,
    PackWithheldBody,
    PublishedPack,
    PublishedPackSummary,
    ReportPack,
)
from schemas.profile import SourceProfile
from schemas.rights import Right, RightsResponse, rights_for
from schemas.trends import (
    TrendDefinition,
    TrendDefinitionInput,
    TrendFigures,
    TrendLimitExceededBody,
    TrendOptions,
)

from . import alert_queue
from . import compute_routes as compute_routes_module
from . import connections as connections_module
from . import dossier as dossier_module
from . import kyc as kyc_module
from . import ownership as ownership_module
from . import readiness as readiness_module
from . import reports as reports_module
from . import resolution as resolution_module
from . import resolution_trigger as resolution_trigger_module
from . import review as review_module
from . import risk as risk_module
from . import search as search_module
from .add_by_identifiers import (
    MAX_IDENTIFIERS,
    AddByIdentifiersRequest,
    AddByIdentifiersResponse,
    TooManyIdentifiersError,
    resolve_identifiers,
)
from .alerts import AlertNotFoundError, AlertStore, AlertTriageConflict
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
from .case_brief import (
    AttachmentKind,
    BriefAttachmentBody,
    BriefStatusBody,
    BriefTextBody,
    CaseBrief,
    CaseBriefError,
    CaseBriefService,
    CaseBriefStore,
)
from .case_brief_resolvers import title_resolvers
from .compute_routes import (
    JOB_TYPE_COMPUTE_METRIC,
    ComputeMetricAccepted,
    ComputeMetricName,
    ComputeMetricRequest,
    run_compute_metric_job,
)
from .config import ApiConfig, DeploymentModels
from .dataset_scope import (
    UnknownDatasetError,
    made_in,
    outside_any_case,
    scope_to_case,
)
from .datasets import (
    CaseDatasetsRequest,
    CreateDatasetRequest,
    Dataset,
    DatasetRefusedError,
    DatasetStore,
    InMemoryDatasetStore,
)
from .document_content import (
    UPLOAD_CONTENT_EXTENSIONS,
    DocumentAcceptResult,
    DocumentBulkAcceptResult,
    DocumentContentService,
    DocumentExtractionResult,
    DocumentUploadResult,
    HolderNotFoundError,
    UploadRefusedError,
)
from .document_reader import (
    Designation,
    DesignationRefusedError,
    DesignationResult,
    DocumentReaderService,
    DocumentReaderView,
)
from .dossier import DocumentView
from .email_extraction import (
    EmailAcceptResult,
    EmailDocumentsResult,
    EmailExtractionResult,
    EmailExtractionService,
    EmailNotFoundError,
    ExtractEmailRequest,
    NotDocumentsError,
)
from .entity_pictures import (
    PICTURE_TYPES,
    EntityPicture,
    EntityPictureService,
    PictureNotFoundError,
    PictureSetResponse,
)
from .event_scope import visible_ancestors, with_inherited
from .explore import (
    ExploreService,
    StarterNotOffered,
    TooManyMatches,
)
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
from .folder_watch import WatchedFile, describe_watch, validate_watch, waiting_files
from .held_rows import HeldRowNotFoundError, HeldRowStore
from .history import (
    HistoryStep,
    HistoryStepNotFoundError,
    HistoryStepSummary,
    InvestigationHistoryStore,
)
from .history_labels import (
    ALERT_CANVAS,
    BRANCHED,
    BRIEF_EDITED,
    EXPANDED,
    LINKS_AMONG,
    NOT_RESTORABLE,
    OPENED_FROM_ALERT,
    OWNERSHIP,
    REMOVED,
    SEEDED,
    SHARED_CONTACTS,
    STARTER_QUESTION,
)
from .hotlists import HotlistNotFoundError, HotlistStore
from .identity_admin import (
    DashboardExistsError,
    IdentityAdmin,
    IdentityAdminRefused,
    PersonExistsError,
    UnknownRoleError,
)
from .ingest_sources import (
    IngestSourceFile,
    IngestSourceListing,
    UploadRefused,
    ingest_root,
    list_source_files,
    max_upload_bytes,
    save_upload,
    validate_upload_name,
)
from .investigations import (
    AccessHistoryEntry,
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
    InvestigationStore,
)
from .jobs import JobQueue
from .kyc import KycNotApplicable
from .kyc_expiries import KycExpiryStore
from .kyc_sweep import SweepReport
from .kyc_sweep import run_daily as run_daily_kyc_sweep
from .kyc_sweep import sweep as kyc_sweep
from .link_changes import (
    ChangeNotMadeError,
    InvalidChangeError,
    LinkChangeRequest,
    LinkChangeResponse,
    LinkChangeService,
    LinkChangeStore,
    LinkHistoryResponse,
    LoweringNeedsAuthorError,
    LoweringNotConfirmedError,
    ResolutionLinkError,
)
from .link_events import LinkEventListResponse, LinkEventsService
from .link_notes import (
    InvalidNoteError,
    LinkNoteBody,
    LinkNoteListResponse,
    LinkNoteService,
    LinkNoteStore,
    LinkNotFoundError,
    NoteNotFoundError,
    NoteNotYoursError,
)
from .link_type_store import LinkTypeProposalStore
from .link_types import (
    CaseLinkTypesResponse,
    LinkTypeDecisionRequest,
    LinkTypeOption,
    LinkTypeProposal,
    LinkTypeProposalList,
    LinkTypeService,
    PromoteLinkTypeRequest,
    ProposalNotFoundError,
    ProposalRefusedError,
    ProposeLinkTypeRequest,
    RetireLinkTypeRequest,
    public_ontology,
)
from .load_records import LedgerSink, may_see_counts, released_from_of, report_view
from .mapconfig_loader import load_map_config, public_view
from .model_routing import ModelEgressRefused, RoutedModel, model_status, routes_from_env
from .monitors import MonitorNotFoundError, MonitorStore
from .notify import notify_channel, publish_delta
from .packs import (
    PackExportRefused,
    PackHasWithheldItems,
    PackItemRefused,
    PackStore,
    StoredPackItem,
    assessment_item,
    entity_item,
    export_pack,
    highest_marking,
    note_item,
    readable,
    reorder_visible,
    trend_item,
)
from .pattern_ask import (
    AskToSearchRequest,
    CouldNotExpress,
    PatternAskService,
    PatternProposal,
)
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
from .pipeline_run import (
    OnlineGeocode,
    RecogniserFor,
)
from .principal_names import PrincipalNameDirectory
from .questions import (
    AskRequest,
    NoDocumentsError,
    PostgresQuestionStore,
    QuestionAccepted,
    QuestionAnswer,
    QuestionsService,
    QuestionsTooLargeError,
)
from .recipe_run import (
    RecipeRunDeps,
    _evaluate_watches_best_effort,
    _owner_resolver,
    _rule_gate,
    run_recipe_as,
)
from .recipe_runs import RecipeRun, RecipeRunStore
from .release_notice import read_update_notice
from .report_freshness import ReportFreshness
from .reports import ReportLimitExceededError
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
from .risk import NeighbourhoodTooLarge
from .rule_evaluation import RULE_AUDIT_ACTIONS, RuleGate
from .rule_holds import ReleaseRefused, readable_rule_audit, release_held_rows
from .run_resources import RECIPES_REPO_ROOT, build_run_resources
from .scheduler import (
    DEFAULT_TIMEZONE,
    ScheduleExecutor,
    ScheduleRefused,
    ScheduleRunRefused,
    describe,
    next_slot,
    next_slots,
    run_every_minute,
    schedule_notice,
    validate_schedule,
)
from .screening import ScreeningListStore
from .search import SearchRequest, SearchResponse, SuggestRequest, SuggestResponse
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
    draft_handling_columns,
    draft_units,
    get_sample_row,
    preview_element_handling,
    resolve_source_handling,
    source_column_names,
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
    load_published_recipe,
    pack_versions_for,
    write_and_commit_recipe,
)
from .studio_recipes import (
    SourceDeclarationsInvalidError,
    StudioRecipeCannotVersionError,
    StudioRecipeNotADraftError,
    StudioRecipeNotFoundError,
    StudioRecipeNotVerifiedError,
    StudioRecipeStore,
    recipe_reader,
    reconcile_recipe_pins,
)
from .studio_verify import RowTemplateMissingError, run_verify
from .supersede import JOB_TYPE_SUPERSEDE_NODE, run_supersede_node_job
from .superset_embed import (
    EmbeddableDashboard,
    SupersetEmbedder,
    SupersetRefused,
    SupersetSettings,
    identity_for,
    identity_principal,
    may_open,
)
from .suppression import NodeNotVisibleError, SuppressionMark, SuppressionMarkStore
from .tile_cache import (
    cache_key_for,
    read_cached_tile,
    tile_cache_storage_config,
    write_cached_tile,
)
from .tile_proxy import build_upstream_url, fetch_tile
from .trends import (
    TrendDefinitionRefused,
    TrendStore,
    check_in_case_domains,
    highest,
    mark_outside_case_domains,
    name_series,
    to_request,
    trend_options,
    validate_definition,
)
from .typology_rules import TypologyRuleNotFoundError, TypologyRuleStore
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
    MAX_NODES,
    BranchFilter,
    CardinalityPreview,
    ClusterExplanation,
    ClusterNotFoundError,
    DeltaAdd,
    DeltaReplaceEdgeSent,
    DeltaSnapshot,
    DeltaViewOverCap,
    ExpansionOutcome,
    LimitExceededError,
    LinksAmongOutcome,
    LinksAmongRequest,
    NodeNotInWorkingSetError,
    NothingToBranchError,
    ResolutionOutcome,
    SameNodeAssertionError,
    WorkingSetDeltaSent,
    decode_delta,
    lacks_record,
)
from .working_set.service import WorkingSetService
from .working_set.store import DELTA_STREAM_MAXLEN, ValkeyWorkingSetStore
from .ws_ticket import WsTicketResponse, mint_ws_ticket, redeem_ws_ticket

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = ApiConfig.from_env()

    # ADR-127 Amendment 23: what a recipe run is built from (the stamping graph and its hooks, the
    # stores a run writes, analytics, media, jobs, the principal resolver) is built by the one
    # function the seed calls too, never a copy of it here.
    resources = await build_run_resources(config)
    handling_scheme = resources.handling_scheme
    ontology = resources.ontology
    graph = resources.graph
    valkey = resources.valkey
    audit = resources.audit
    patterns_store = resources.patterns_store
    hotlists_store = resources.hotlists_store
    monitors_store = resources.monitors_store
    alerts_store = resources.alerts_store
    typology_rules = resources.typology_rules
    held_rows = resources.held_rows
    screening_lists = resources.screening_lists
    kyc_expiries = resources.kyc_expiries
    recipe_runs = resources.recipe_runs
    extraction_candidates = resources.extraction_candidates
    datasets_store = resources.datasets_store
    analytics = resources.analytics
    media = resources.media
    recogniser = resources.recogniser
    compute = resources.compute
    jobs = resources.jobs
    yardstick = load_phia_yardstick()
    investigations = await InvestigationStore.connect(config.postgres.dsn)
    history = await InvestigationHistoryStore.connect(config.postgres.dsn)
    sites = await SiteStore.connect(config.postgres.dsn)
    judgements_store = await JudgementStore.connect(config.postgres.dsn)
    link_notes_store = await LinkNoteStore.connect(config.postgres.dsn)
    # ADR-128 decision 3: each case's brief (its information requirements).
    case_brief_store = await CaseBriefStore.connect(config.postgres.dsn)
    link_changes_store = await LinkChangeStore.connect(config.postgres.dsn)
    link_type_store = await LinkTypeProposalStore.connect(config.postgres.dsn)
    suppression_marks = await SuppressionMarkStore.connect(config.postgres.dsn)
    gaps_store = await IntelligenceGapStore.connect(config.postgres.dsn)
    assumptions_store = await AssumptionStore.connect(config.postgres.dsn)
    export_ledger = await ExportLedgerStore.connect(config.postgres.dsn)
    # ADR-111 Amendment 2: read-only, for the Admin area's Dashboards screen.
    report_freshness = await ReportFreshness.connect(config.postgres.dsn)
    # ADR-113: the saved trend definitions of each case.
    trend_store = await TrendStore.connect(config.postgres.dsn)
    pack_store = await PackStore.connect(config.postgres.dsn)
    studio_recipes = await StudioRecipeStore.connect(config.postgres.dsn)
    questions_store = await PostgresQuestionStore.connect(config.postgres.dsn)
    app.state.datasets = datasets_store
    litellm_client = LiteLLMClient(LiteLLMConfig.from_env())
    # `embed_model` is the only model this adapter needs fixed at construction — `extract()`'s own
    # model is caller-supplied per call (`ExtractionRequest.model`, ADR-005), never this adapter's
    # own opinion (`services/api/review.py`'s own docstring on `RunExtractionRequest.model`).
    # ADR-095: the deployment's own models, never the conformance suite's.
    models = DeploymentModels.from_env()
    # ADR-114 Amendment 6: every model call goes through the routes, so a client's own provider
    # sees only material whose handling code the deployment declared sendable.
    routes, sendable = routes_from_env(models, os.environ)
    model: ModelPort = RoutedModel(
        ModelLiteLLMAdapter(litellm_client, embed_model=models.embedding),
        routes=routes,
        sendable_handling_codes=sendable,
    )
    # `spec/09_INGEST_STUDIO.md` §6's reverse index: "an ontology edit flags
    # every recipe that depends on the changed version". This deployment's
    # only "ontology reload" trigger today is a process restart after a new
    # `packages/ontology/default.yaml` ships — there is no live-reload admin
    # action yet (Phase 8's own territory) — so this is that routine, run
    # once, right after the ontology this process will serve is known. ADR-120 Amendment 1,
    # decision 6: it also stamps the pack pins of a recipe published before pinning (read from its
    # committed file under the recipe repository root a publish writes to), and flags a recipe
    # whose pinned packs are no longer the ones this process composes.
    flagged_at_start = await reconcile_recipe_pins(
        studio_recipes, ontology, recipe_reader(resources.recipe_repo_root)
    )
    if flagged_at_start:
        logger.warning(
            "start-up flagged %d published recipe(s) as stale: %s",
            len(flagged_at_start),
            ", ".join(flagged_at_start),
        )

    app.state.config = config
    app.state.graph = graph
    app.state.ontology = ontology
    app.state.valkey = valkey
    # ADR-100 Amendment 3: the Explore panel's figures, kept per access class, cleared on a write
    # (the hook is on the graph, in `build_run_resources`).
    app.state.explore_cache = resources.explore_cache
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
    app.state.typology_rules = typology_rules
    app.state.held_rows = held_rows
    app.state.screening_lists = screening_lists
    app.state.kyc_expiries = kyc_expiries
    app.state.recipe_runs = recipe_runs
    app.state.judgements_store = judgements_store
    app.state.link_notes = LinkNoteService(link_notes_store, app.state.working_set)
    # ADR-128 decision 3, rule 3: an attachment is shown to a reader only with the title its own
    # store gives that reader (`case_brief_resolvers.py`); each kind keeps its own access rule.
    app.state.case_brief = CaseBriefService(
        case_brief_store,
        title_resolvers(
            trends=trend_store,
            patterns=patterns_store,
            judgements=judgements_store,
            graph=graph,
            investigations=investigations,
        ),
    )
    # ADR-090: the ontology in force is `default.yaml` plus every proposal, composed here and after
    # each proposal and decision, in place, so every service holding `ontology` sees it.
    app.state.link_types = LinkTypeService(
        link_type_store, ontology, graph, app.state.working_set, investigations
    )
    await app.state.link_types.refresh()
    app.state.link_changes = LinkChangeService(
        link_changes_store,
        app.state.working_set,
        graph,
        ontology,
        link_notes_store,
        app.state.link_types,
        scheme=handling_scheme,
    )
    app.state.link_events = LinkEventsService(app.state.working_set, analytics, investigations)
    # ADR-108 phase C: the pipeline runner's recogniser lookup and the online geocoding
    # allow-list (`OSPREY_ONLINE_GEOCODER`), both deployment-level wiring, not per-request.
    app.state.pipeline_recogniser_for = resources.recogniser_for
    app.state.online_geocode = resources.online_geocode
    app.state.media = media
    app.state.document_reader = DocumentReaderService(
        app.state.working_set, analytics, graph, extraction_candidates, investigations, media
    )
    app.state.document_content = DocumentContentService(
        app.state.working_set,
        graph,
        media,
        model,
        ontology,
        extraction_candidates,
        text_model=models.extraction,
        vision_model=models.vision,
        transcribe_model=models.transcription,
        scheme=handling_scheme,
        recogniser=recogniser,
    )
    app.state.entity_pictures = EntityPictureService(
        app.state.working_set, graph, media, ontology, scheme=handling_scheme, audit=app.state.audit
    )
    app.state.email_extraction = EmailExtractionService(
        app.state.working_set,
        analytics,
        graph,
        ontology,
        extraction_candidates,
        model,
        models.extraction,
        investigations=investigations,
        recogniser=recogniser,
    )
    # ADR-098 decision 4: questions to the model about a case's documents.
    app.state.questions = QuestionsService(
        app.state.working_set,
        app.state.document_reader,
        graph,
        model,
        ontology,
        extraction_candidates,
        questions_store,
        default_model=models.extraction,
        analytics=analytics,
        datasets=datasets_store,
        investigations=investigations,
    )
    # ADR-129 decision 2: ask to search, a question turned into a pattern that nothing runs.
    app.state.pattern_ask = PatternAskService(
        app.state.working_set, graph, model, default_model=models.extraction
    )
    app.state.suppression_marks = suppression_marks
    app.state.gaps_store = gaps_store
    app.state.assumptions_store = assumptions_store
    app.state.export_ledger = export_ledger
    app.state.report_freshness = report_freshness
    app.state.trend_store = trend_store
    app.state.pack_store = pack_store
    app.state.studio_recipes = studio_recipes
    app.state.extraction_candidates = extraction_candidates
    app.state.model = model
    app.state.recipes_repo_root = resources.recipe_repo_root
    app.state.handling_scheme = handling_scheme
    app.state.yardstick = yardstick
    app.state.site_image_storage = site_image_storage_config()
    app.state.tile_cache_storage = tile_cache_storage_config()
    app.state.analytics = analytics
    # `06_DECISIONS.md` ADR-029/Phase 7 Stage 3: Tier 2 only (built in `build_run_resources`) —
    # Tier 1 (`graphology`, a Node harness, conformance-only) and Tier 3 (Phase 8a's `cluster`
    # profile, ADR-028) have no Conduit-side adapter to construct yet.
    app.state.compute = compute
    app.state.jobs = jobs
    # `06_DECISIONS.md` ADR-025: this system's first job-queue worker,
    # generalised by `job_type` rather than resolution-specific — closes
    # `services/api/supersede.py`'s own long-disclosed "no worker attached
    # yet" gap in the same stroke. Constructed and its handlers registered
    # here so a standalone worker process (`services/api/worker_main.py`)
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
    app.state.principal_resolver = resources.principal_resolver
    # ADR-106: display names for principal ids, resolved when a read is served.
    app.state.principal_names = PrincipalNameDirectory(config)
    # ADR-112: the Admin area's people and dashboards, through the Conduit's own account.
    # ADR-114 Amendment 5: invitations by the identity provider's own email when the deployment has
    # a mail server (rendered from the install answers), else by a one-time code.
    app.state.identity_admin = IdentityAdmin(
        config, by_email=os.environ.get("OSPREY_SIGN_IN_EMAIL", "").lower() == "true"
    )
    # ADR-111 Amendment 3: Superset dashboards inside the Glass; None when not configured.
    superset_settings = SupersetSettings.from_env()
    app.state.superset_embedder = SupersetEmbedder(superset_settings) if superset_settings else None
    app.state.map_config = load_map_config(config.osprey_config_path)

    # ADR-109 phase F, ruling 7: the daily sweep for verifying documents that lapse — the clock
    # passing is never a write the change stream could carry. One replica a day (a Valkey claim).
    sweeper = service_principal(handling_scheme)

    async def _sweep_day(day: date) -> SweepReport:
        return await kyc_sweep(
            day=day,
            expiries=kyc_expiries,
            rules=typology_rules,
            graph=graph,
            scheme=handling_scheme,
            alert_store=alerts_store,
            audit=audit,
            valkey=valkey,
            principal_for_owner=app.state.principal_resolver.resolve_for_owner,
            sweeper=sweeper,
        )

    sweep_task = asyncio.create_task(run_daily_kyc_sweep(valkey, _sweep_day))

    # ADR-110 decision 2: scheduled pipeline runs, ticking each minute on every replica, each slot
    # run by the one that claims it, as the schedule's owner through the one run path.
    app.state.schedule_executor = _schedule_executor(app)
    schedule_task = asyncio.create_task(run_every_minute(app.state.schedule_executor))

    try:
        yield
    finally:
        sweep_task.cancel()
        schedule_task.cancel()
        await investigations.close()
        await history.close()
        await sites.close()
        await judgements_store.close()
        await link_notes_store.close()
        await case_brief_store.close()
        await link_changes_store.close()
        await link_type_store.close()
        await gaps_store.close()
        await assumptions_store.close()
        await export_ledger.close()
        await report_freshness.close()
        await trend_store.close()
        await pack_store.close()
        await studio_recipes.close()
        await questions_store.close()
        await app.state.principal_names.aclose()
        await app.state.identity_admin.aclose()
        if app.state.superset_embedder is not None:
            await app.state.superset_embedder.aclose()
        # A closed store must not outlive the app that held it (a test app is started again).
        app.state.datasets = None
        await litellm_client.aclose()
        await resources.close()


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
        # **Empty by default, not `http://localhost:5173`** (round 13b). The old default meant a
        # deployment that forgot to set this — which every rendered deployment did, until round
        # 13b made `harness/render.py` write it — silently accepted cross-origin requests from a
        # developer's Vite server. A Conduit that has not been told its origin should allow none,
        # not guess one.
        #
        # There is deliberately no "is this a dev build" switch: round 13b's brief expected one
        # ("the dev token fence already distinguishes builds"), and checking the tree found none
        # — `mint_dev_token`'s own fence is file presence, not a runtime flag. So the dev path is
        # explicit instead: `DEMO_GUIDE.md` §3.2/§3.5 now set `CORS_ALLOWED_ORIGINS` on the
        # command that starts a Conduit for a Vite-served Glass. Explicit beats inferred here —
        # a deployment inheriting a development default is precisely the fault being fixed.
        for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
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


def get_datasets(request: Request) -> DatasetStore:
    """ADR-099. The lifespan always sets the Postgres store; a test app with no lifespan gets an
    empty in-memory one, so a case made there reads no dataset rather than every one."""
    store = getattr(request.app.state, "datasets", None)
    if store is None:
        store = InMemoryDatasetStore()
        request.app.state.datasets = store
    return store


DatasetsDep = Annotated[DatasetStore, Depends(get_datasets)]


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


def get_typology_rules(request: Request) -> TypologyRuleStore:
    return request.app.state.typology_rules  # type: ignore[no-any-return]


def get_held_rows(request: Request) -> HeldRowStore:
    return request.app.state.held_rows  # type: ignore[no-any-return]


def get_screening_lists(request: Request) -> ScreeningListStore:
    return request.app.state.screening_lists  # type: ignore[no-any-return]


def get_kyc_expiries(request: Request) -> KycExpiryStore:
    return request.app.state.kyc_expiries  # type: ignore[no-any-return]


def get_judgements_store(request: Request) -> JudgementStore:
    return request.app.state.judgements_store  # type: ignore[no-any-return]


def get_identity_admin(request: Request) -> IdentityAdmin:
    return request.app.state.identity_admin  # type: ignore[no-any-return]


def get_principal_names(request: Request) -> PrincipalNameDirectory:
    return request.app.state.principal_names  # type: ignore[no-any-return]


def get_gaps_store(request: Request) -> IntelligenceGapStore:
    return request.app.state.gaps_store  # type: ignore[no-any-return]


def get_assumptions_store(request: Request) -> AssumptionStore:
    return request.app.state.assumptions_store  # type: ignore[no-any-return]


def get_export_ledger(request: Request) -> ExportLedgerStore:
    return request.app.state.export_ledger  # type: ignore[no-any-return]


def get_report_freshness(request: Request) -> ReportFreshness:
    return request.app.state.report_freshness  # type: ignore[no-any-return]


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
    """Who is asking, and (ADR-099) what they may read: the datasets of the case the path names,
    or none outside a case. Every principal a route is given comes through here, the Studio's
    role checks included, so no request reads unlimited (`dataset_scope.py`)."""
    resolver: PrincipalResolver = request.app.state.principal_resolver
    try:
        identity = resolver.resolve(credentials.credentials)
    except PrincipalResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    investigation_id = request.path_params.get("investigation_id")
    if investigation_id is None:
        return outside_any_case(identity)
    return await scope_to_case(identity, investigation_id, get_datasets(request))


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


def get_link_notes(request: Request) -> LinkNoteService:
    return request.app.state.link_notes  # type: ignore[no-any-return]


def get_case_brief(request: Request) -> CaseBriefService:
    return request.app.state.case_brief  # type: ignore[no-any-return]


PrincipalDep = Annotated[Principal, Depends(get_principal)]
PrincipalResolverDep = Annotated[PrincipalResolver, Depends(get_principal_resolver)]
SitesDep = Annotated[SiteStore, Depends(get_sites)]
PatternsStoreDep = Annotated[PatternStore, Depends(get_patterns_store)]
ConfigDep = Annotated[ApiConfig, Depends(get_config)]
HotlistsStoreDep = Annotated[HotlistStore, Depends(get_hotlists_store)]
MonitorsStoreDep = Annotated[MonitorStore, Depends(get_monitors_store)]
AlertsStoreDep = Annotated[AlertStore, Depends(get_alerts_store)]
TypologyRulesDep = Annotated[TypologyRuleStore, Depends(get_typology_rules)]
HeldRowsDep = Annotated[HeldRowStore, Depends(get_held_rows)]
ScreeningListsDep = Annotated[ScreeningListStore, Depends(get_screening_lists)]
KycExpiriesDep = Annotated[KycExpiryStore, Depends(get_kyc_expiries)]


def get_recipe_runs(request: Request) -> RecipeRunStore:
    return request.app.state.recipe_runs  # type: ignore[no-any-return]


RecipeRunsDep = Annotated[RecipeRunStore, Depends(get_recipe_runs)]
JudgementsStoreDep = Annotated[JudgementStore, Depends(get_judgements_store)]
PrincipalNamesDep = Annotated[PrincipalNameDirectory, Depends(get_principal_names)]
IdentityAdminDep = Annotated[IdentityAdmin, Depends(get_identity_admin)]


def get_superset_embedder(request: Request) -> SupersetEmbedder | None:
    return getattr(request.app.state, "superset_embedder", None)


SupersetEmbedderDep = Annotated[SupersetEmbedder | None, Depends(get_superset_embedder)]
LinkNotesDep = Annotated[LinkNoteService, Depends(get_link_notes)]
CaseBriefDep = Annotated[CaseBriefService, Depends(get_case_brief)]


def get_document_content(request: Request) -> DocumentContentService:
    return request.app.state.document_content  # type: ignore[no-any-return]


DocumentContentDep = Annotated[DocumentContentService, Depends(get_document_content)]


def get_entity_pictures(request: Request) -> EntityPictureService:
    return request.app.state.entity_pictures  # type: ignore[no-any-return]


EntityPicturesDep = Annotated[EntityPictureService, Depends(get_entity_pictures)]


def get_media(request: Request) -> MediaStore:
    return request.app.state.media  # type: ignore[no-any-return]


MediaDep = Annotated[MediaStore, Depends(get_media)]


def get_document_reader(request: Request) -> DocumentReaderService:
    return request.app.state.document_reader  # type: ignore[no-any-return]


DocumentReaderDep = Annotated[DocumentReaderService, Depends(get_document_reader)]


def get_link_events(request: Request) -> LinkEventsService:
    return request.app.state.link_events  # type: ignore[no-any-return]


LinkEventsDep = Annotated[LinkEventsService, Depends(get_link_events)]


def get_email_extraction(request: Request) -> EmailExtractionService:
    return request.app.state.email_extraction  # type: ignore[no-any-return]


EmailExtractionDep = Annotated[EmailExtractionService, Depends(get_email_extraction)]


def get_questions(request: Request) -> QuestionsService:
    return request.app.state.questions  # type: ignore[no-any-return]


QuestionsDep = Annotated[QuestionsService, Depends(get_questions)]


def get_pattern_ask(request: Request) -> PatternAskService:
    return request.app.state.pattern_ask  # type: ignore[no-any-return]


PatternAskDep = Annotated[PatternAskService, Depends(get_pattern_ask)]


def get_link_changes(request: Request) -> LinkChangeService:
    return request.app.state.link_changes  # type: ignore[no-any-return]


LinkChangesDep = Annotated[LinkChangeService, Depends(get_link_changes)]


def get_link_types(request: Request) -> LinkTypeService:
    return request.app.state.link_types  # type: ignore[no-any-return]


LinkTypesDep = Annotated[LinkTypeService, Depends(get_link_types)]


def get_suppression_marks(request: Request) -> SuppressionMarkStore:
    return request.app.state.suppression_marks  # type: ignore[no-any-return]


SuppressionMarksDep = Annotated[SuppressionMarkStore, Depends(get_suppression_marks)]
GapsStoreDep = Annotated[IntelligenceGapStore, Depends(get_gaps_store)]
AssumptionsStoreDep = Annotated[AssumptionStore, Depends(get_assumptions_store)]
ExportLedgerDep = Annotated[ExportLedgerStore, Depends(get_export_ledger)]
ReportFreshnessDep = Annotated[ReportFreshness, Depends(get_report_freshness)]


def get_trend_store(request: Request) -> TrendStore:
    return request.app.state.trend_store  # type: ignore[no-any-return]


TrendStoreDep = Annotated[TrendStore, Depends(get_trend_store)]


def get_pack_store(request: Request) -> PackStore:
    return request.app.state.pack_store  # type: ignore[no-any-return]


PackStoreDep = Annotated[PackStore, Depends(get_pack_store)]
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


def get_pipeline_recogniser_for(request: Request) -> RecogniserFor:
    return cast(RecogniserFor, request.app.state.pipeline_recogniser_for)


def get_online_geocode(request: Request) -> OnlineGeocode | None:
    return cast("OnlineGeocode | None", request.app.state.online_geocode)


PipelineRecognisersDep = Annotated[RecogniserFor, Depends(get_pipeline_recogniser_for)]
OnlineGeocodeDep = Annotated[OnlineGeocode | None, Depends(get_online_geocode)]


def require_right(right: Right) -> Any:
    """`06_DECISIONS.md` ADR-112: the right a route needs, declared in its decorator
    (`dependencies=[Depends(require_right(Right.X))]`) and checked before anything else the route
    does. A right is an action, never a licence to see: what the person then sees is still their
    clearance and the case's datasets (rule 3), and a case route still needs its case level.
    `required_right` is what `test_route_rights.py` reads to prove every route names one."""

    async def _dependency(principal: PrincipalDep) -> Principal:
        if right not in rights_for(principal.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "right_required", "right": right.value},
            )
        return principal

    _dependency.required_right = right  # type: ignore[attr-defined]
    return _dependency


#: ADR-112: a Studio role's check, read as the right it always meant, so `data_engineer` — which
#: holds the rights and not the old role names — passes where `source_author` once did.
_STUDIO_ROLE_RIGHT: dict[StudioRole, Right] = {
    StudioRole.SOURCE_AUTHOR: Right.EDIT_PIPELINES,
    StudioRole.SOURCE_APPROVER: Right.PUBLISH_PIPELINES,
    StudioRole.LOADER: Right.RUN_PIPELINES,
}


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
        if _STUDIO_ROLE_RIGHT[role] not in rights_for(principal.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"principal lacks required studio role: {role.value}",
            )
        return principal

    return _dependency


#: Round 09 — the two Geospatial-screen actions `harness/geospatial.py` cannot perform inside the
#: harness image at all (its own docstring has the confirmed-by-import reason: `scripts.
#: build_local_basemap`/`scripts.verify_map` pull in `services.ingest`/`adapters.graph_arcadedb`/
#: `services.api`, none of which `harness/Dockerfile` copies in, and the former needs a live
#: `GraphPort` transaction besides). Resolved as: these two routes, here, in the one process that
#: already has all of it — never by vendoring `services`/`adapters` into the harness image. Same
#: role name R2 already uses for the harness's own `/admin` ("the same audience check the Conduit
#: uses" — the identical bearer token authenticates both surfaces); a different mechanism from
#: `require_studio_role` above only because there is no `AdminRole` enum to parametrise — one
#: fixed role, one name, matching `harness/webapp_auth.py`'s own `ADMIN_ROLE` constant exactly.
ADMIN_ROLE = "osprey-admin"


async def require_admin_role(principal: PrincipalDep) -> Principal:
    if ADMIN_ROLE not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"principal lacks required role: {ADMIN_ROLE}",
        )
    return principal


def _authorized_at(
    level: AccessLevel, *, admin_safety_net: bool = False
) -> Callable[..., Awaitable[Investigation]]:
    """The one gate every investigation-scoped route depends on, at the level the route needs
    (ADR-052 §8). `required_level` is what the route-level test reads to prove that no route is
    left without one. "No level at all" and "wrong unit" and "no such case" are the same 404
    (ADR-041's existence-leak rule); a level too low is a 403, since the account can already see
    the case exists. Either denial is audited before it propagates.

    `admin_safety_net` is for the access routes only (ADR-052 §4): an `osprey-admin` in the case's
    own unit may manage its access when they hold no level, so a case whose Authors have left is
    not stranded. That confers no level: every other route still needs one."""

    async def dependency(
        investigation_id: str,
        principal: PrincipalDep,
        investigations: InvestigationsDep,
        audit: AuditDep,
    ) -> Investigation:
        return await _authorize(
            investigation_id, principal, investigations, audit, level, admin_safety_net
        )

    dependency.required_level = level  # type: ignore[attr-defined]
    return dependency


async def _authorize(
    investigation_id: str,
    principal: Principal,
    investigations: InvestigationStore,
    audit: AuditWriter,
    level: AccessLevel,
    admin_safety_net: bool = False,
) -> Investigation:
    """`_authorized_at`'s gate, callable by a route whose case is in its body, not its path."""
    denial: Exception
    try:
        return await investigations.get_authorized(investigation_id, principal, need=level)
    except (InvestigationNotFoundError, InsufficientAccessError) as error:
        denial = error

    if admin_safety_net and ADMIN_ROLE in principal.roles:
        try:
            case = await investigations.get_for_access_admin(investigation_id, principal)
        except InvestigationNotFoundError:
            await _audit_denied(audit, principal, investigation_id, {})
            raise
        await audit.record(
            principal=principal,
            action="access_admin_override",
            investigation_id=investigation_id,
            resolved_query={},
            result_cardinality=1,
        )
        return case

    if isinstance(denial, InsufficientAccessError):
        await _audit_denied(audit, principal, investigation_id, {"needed": level.value})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(denial)) from denial
    await _audit_denied(audit, principal, investigation_id, {})
    raise denial


async def _audit_denied(
    audit: AuditWriter, principal: Principal, investigation_id: str, detail: dict[str, str]
) -> None:
    await audit.record(
        principal=principal,
        action="access_denied",
        investigation_id=investigation_id,
        resolved_query=detail,
        result_cardinality=0,
    )


InvestigationViewerDep = Annotated[Investigation, Depends(_authorized_at(AccessLevel.VIEWER))]
InvestigationEditorDep = Annotated[Investigation, Depends(_authorized_at(AccessLevel.EDITOR))]
InvestigationAuthorDep = Annotated[Investigation, Depends(_authorized_at(AccessLevel.AUTHOR))]
#: Access management: an Author, or the administrator's safety net (ADR-052 §4).
InvestigationAccessManagerDep = Annotated[
    Investigation, Depends(_authorized_at(AccessLevel.AUTHOR, admin_safety_net=True))
]


def _authorized_site_at(level: AccessLevel) -> Callable[..., Awaitable[Site]]:
    """Mirrors `_authorized_at` for the site routes. The case is checked first, at `level`, so a
    Viewer cannot change a site and an account with no level cannot tell a site exists;
    `SiteStore.get_authorized` then collapses "no such site" and "wrong owning_unit" into the same
    `SiteNotFoundError`, and the site must belong to the investigation named in the URL, not just
    to the same org unit — a real site id under a *different* investigation is "not found" here
    too."""

    async def dependency(
        investigation_id: str,
        site_id: str,
        principal: PrincipalDep,
        investigations: InvestigationsDep,
        sites: SitesDep,
        audit: AuditDep,
    ) -> Site:
        try:
            await investigations.get_authorized(investigation_id, principal, need=level)
        except InvestigationNotFoundError:
            await _audit_denied(audit, principal, investigation_id, {"site_id": site_id})
            raise
        except InsufficientAccessError as error:
            await _audit_denied(
                audit, principal, investigation_id, {"site_id": site_id, "needed": level.value}
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
        try:
            site = await sites.get_authorized(site_id, principal)
            if site.investigation_id != investigation_id:
                raise SiteNotFoundError(site_id)
            return site
        except SiteNotFoundError:
            await _audit_denied(audit, principal, investigation_id, {"site_id": site_id})
            raise

    dependency.required_level = level  # type: ignore[attr-defined]
    return dependency


SiteViewerDep = Annotated[Site, Depends(_authorized_site_at(AccessLevel.VIEWER))]
SiteEditorDep = Annotated[Site, Depends(_authorized_site_at(AccessLevel.EDITOR))]


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


class SourceAboveClearanceError(Exception):
    """A loader asked to run a recipe whose source marking is above their clearance."""


async def get_runnable_studio_recipe(
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.LOADER))],
    scheme: HandlingSchemeDep,
) -> StudioRecipeDraft:
    """§8: a loader runs a published recipe "against a file at or below their own clearance".
    Refused before anything is read or written: a run's `on_match: reference` lookups go through
    the graph at the loader's clearance, so a loader who cannot see the source's elements cannot
    find the ones an earlier load made and writes them again. Found 9 October 2026, when an
    OFFICIAL loader ran an OFFICIAL-SENSITIVE recipe twice and every number was made twice."""
    if not principal_may_view(resolve_source_handling(recipe), principal, scheme):
        raise SourceAboveClearanceError(recipe.recipe_id)
    return recipe


RunnableStudioRecipeDep = Annotated[StudioRecipeDraft, Depends(get_runnable_studio_recipe)]


# --- exception handling ----------------------------------------------------


@app.exception_handler(LimitExceededError)
async def _limit_exceeded_handler(request: Request, exc: LimitExceededError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=exc.detail.model_dump())


@app.exception_handler(TooManyIdentifiersError)
async def _too_many_identifiers_handler(
    request: Request, exc: TooManyIdentifiersError
) -> JSONResponse:
    """ADR-128 decision 1: more than 5,000 identifiers is refused by name, with the figure, never
    cut to the first 5,000 (rule 2)."""
    return JSONResponse(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        content={
            "error": "too_many_identifiers",
            "cap": MAX_IDENTIFIERS,
            "received": exc.received,
            "message": (
                f"{exc.received:,} identifiers were given; one request reads at most "
                f"{MAX_IDENTIFIERS:,}. Nothing was added. Split the list and add it in parts."
            ),
        },
    )


@app.exception_handler(NothingToBranchError)
async def _nothing_to_branch_handler(request: Request, exc: NothingToBranchError) -> JSONResponse:
    """One answer whether the chosen nodes are hidden from the caller or do not exist (ADR-084)."""
    return JSONResponse(status_code=422, content={"error": "nothing_to_branch"})


@app.exception_handler(TypologyRuleNotFoundError)
async def _typology_rule_not_found_handler(
    request: Request, exc: TypologyRuleNotFoundError
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "rule_not_found"})


@app.exception_handler(HeldRowNotFoundError)
async def _held_row_not_found_handler(request: Request, exc: HeldRowNotFoundError) -> JSONResponse:
    """One answer whether a held row does not exist, is another case's, or is above the reader."""
    return JSONResponse(status_code=404, content={"error": "held_row_not_found"})


@app.exception_handler(ReleaseRefused)
async def _release_refused_handler(request: Request, exc: ReleaseRefused) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "release_refused", "detail": str(exc)})


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
async def _pattern_not_found_handler(request: Request, exc: PatternNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "pattern_not_found"}
    )


@app.exception_handler(HotlistNotFoundError)
async def _hotlist_not_found_handler(request: Request, exc: HotlistNotFoundError) -> JSONResponse:
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


@app.exception_handler(HolderNotFoundError)
async def _holder_not_found_handler(request: Request, exc: HolderNotFoundError) -> JSONResponse:
    """A holder not in the view and one the caller may not see give this one answer (ADR-094)."""
    return JSONResponse(status_code=404, content={"error": "holder_not_found"})


@app.exception_handler(PictureNotFoundError)
async def _picture_not_found_handler(request: Request, exc: PictureNotFoundError) -> JSONResponse:
    """No picture and one the caller may not see give this one answer (ADR-105)."""
    return JSONResponse(status_code=404, content={"error": "picture_not_found"})


@app.exception_handler(UploadRefusedError)
async def _upload_refused_handler(request: Request, exc: UploadRefusedError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "upload_refused", "detail": str(exc)})


@app.exception_handler(RecipeRuleError)
async def _recipe_rule_handler(request: Request, exc: RecipeRuleError) -> JSONResponse:
    """A recipe declares what the ingest rules refuse (ADR-081 step D); each problem is named."""
    return JSONResponse(status_code=422, content={"error": "recipe_rule", "problems": exc.problems})


@app.exception_handler(RowKeyDefinitionChanged)
async def _row_key_definition_changed_handler(
    request: Request, exc: RowKeyDefinitionChanged
) -> JSONResponse:
    """ADR-127 decision 5: the recipe's `deduplicate` is not the one this case's kept keys were made
    under. The cause is in words, with how many loads to revert and never which."""
    return JSONResponse(
        status_code=409,
        content={"error": "deduplicate_changed", "loads": exc.loads, "message": str(exc)},
    )


@app.exception_handler(RowKeyRunInProgress)
async def _row_key_run_in_progress_handler(
    request: Request, exc: RowKeyRunInProgress
) -> JSONResponse:
    """ADR-127 decision 5: another run of this recipe into this case is still loading."""
    return JSONResponse(
        status_code=409, content={"error": "run_in_progress", "message": str(exc)}
    )


@app.exception_handler(NotDocumentsError)
async def _not_documents_handler(request: Request, exc: NotDocumentsError) -> JSONResponse:
    """ADR-092 Amendment 1: the events on this link carry no text, so none is a document."""
    return JSONResponse(status_code=422, content={"error": "not_documents"})


@app.exception_handler(EmailNotFoundError)
async def _email_not_found_handler(request: Request, exc: EmailNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "email_not_found", "detail": str(exc)})


@app.exception_handler(LinkNotFoundError)
async def _link_not_found_handler(request: Request, exc: LinkNotFoundError) -> JSONResponse:
    """A link that is not in the working set and a link this principal may not see give this one
    answer (`services/api/link_notes.py`)."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "link_not_found"})


@app.exception_handler(ModelUnavailableError)
async def _model_unavailable_handler(request: Request, exc: ModelUnavailableError) -> JSONResponse:
    """The deployment's model cannot answer yet (ADR-095): said in words, not as a server fault.
    Seen while the chosen extraction model was still downloading."""
    return JSONResponse(
        status_code=503,
        content={
            "error": "model_unavailable",
            "detail": f"{exc} If the model was chosen recently it may still be downloading; "
            "try again once it is in.",
        },
    )


@app.exception_handler(ExtractionFailedError)
async def _extraction_failed_handler(request: Request, exc: ExtractionFailedError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": "extraction_failed",
            "detail": "The model answered, but not in the shape asked for. Nothing was recorded; "
            "try again.",
        },
    )


@app.exception_handler(ProposalNotFoundError)
async def _proposal_not_found_handler(request: Request, exc: ProposalNotFoundError) -> JSONResponse:
    """No such proposal and one of another unit give this one answer (ADR-090)."""
    return JSONResponse(status_code=404, content={"error": "proposal_not_found"})


@app.exception_handler(ProposalRefusedError)
async def _proposal_refused_handler(request: Request, exc: ProposalRefusedError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "proposal_refused", "detail": str(exc)})


@app.exception_handler(LoweringNeedsAuthorError)
async def _lowering_needs_author_handler(
    request: Request, exc: LoweringNeedsAuthorError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "lowering_needs_author", "detail": str(exc)},
    )


@app.exception_handler(LoweringNotConfirmedError)
async def _lowering_not_confirmed_handler(
    request: Request, exc: LoweringNotConfirmedError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "confirm_lower_handling", "detail": str(exc)},
    )


@app.exception_handler(InvalidChangeError)
async def _invalid_change_handler(request: Request, exc: InvalidChangeError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "invalid_link_change", "detail": str(exc)},
    )


@app.exception_handler(ChangeNotMadeError)
async def _change_not_made_handler(request: Request, exc: ChangeNotMadeError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "nothing_changed", "detail": str(exc)},
    )


@app.exception_handler(ResolutionLinkError)
async def _resolution_link_handler(request: Request, exc: ResolutionLinkError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "resolution_link", "detail": str(exc)},
    )


@app.exception_handler(CaseBriefError)
async def _case_brief_error_handler(request: Request, exc: CaseBriefError) -> JSONResponse:
    """ADR-128 decision 3: each refusal of the brief carries its own status and code and a sentence
    the Glass shows as given. An attachment that does not exist and one the person may not read are
    one refusal, in one body (`AttachmentNotFoundError`)."""
    return JSONResponse(
        status_code=exc.status_code, content={"error": exc.error, "detail": str(exc)}
    )


@app.exception_handler(NoteNotFoundError)
async def _note_not_found_handler(request: Request, exc: NoteNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "note_not_found"})


@app.exception_handler(NoteNotYoursError)
async def _note_not_yours_handler(request: Request, exc: NoteNotYoursError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "note_not_yours",
            "detail": "Only the person who wrote a note can change or remove it.",
        },
    )


@app.exception_handler(InvalidNoteError)
async def _invalid_note_handler(request: Request, exc: InvalidNoteError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "invalid_note", "detail": str(exc)},
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
async def _monitor_not_found_handler(request: Request, exc: MonitorNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "monitor_not_found"}
    )


@app.exception_handler(AlertNotFoundError)
async def _alert_not_found_handler(request: Request, exc: AlertNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "alert_not_found"})


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


@app.exception_handler(UnknownDatasetError)
async def _unknown_dataset_handler(request: Request, exc: UnknownDatasetError) -> JSONResponse:
    """A write named a dataset nobody registered (ADR-099 Amendment 6): nothing was written."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "dataset_unknown",
            "detail": f"No dataset {', '.join(exc.dataset_ids)} is registered; "
            "nothing was written.",
        },
    )


@app.exception_handler(DatasetRefusedError)
async def _dataset_refused_handler(request: Request, exc: DatasetRefusedError) -> JSONResponse:
    """ADR-099: no dataset, or one not of the caller's unit; one answer for both."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"error": "dataset_refused"}
    )


@app.exception_handler(NoDocumentsError)
async def _no_documents_handler(request: Request, exc: NoDocumentsError) -> JSONResponse:
    """ADR-098 decision 4: the case holds no Document the analyst can see to ask about."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"error": "no_documents"}
    )


@app.exception_handler(CouldNotExpress)
async def _could_not_express_handler(request: Request, exc: CouldNotExpress) -> JSONResponse:
    """ADR-129 decision 2: a question, or the model's answer to it, that cannot be drawn as a
    pattern in the case's vocabulary. The panel says it could not express the question."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=exc.body().model_dump()
    )


@app.exception_handler(QuestionsTooLargeError)
async def _questions_too_large_handler(
    request: Request, exc: QuestionsTooLargeError
) -> JSONResponse:
    """Rule 2 (ADR-129 decision 1): the documents and the evidence brief, together longer than the
    model reads at once, are refused with the typed `limit_exceeded` and its three options, never
    cut. It was a 413 `documents_too_large` without the options."""
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=exc.body().model_dump())


@app.exception_handler(RecogniserUnavailableError)
async def _recogniser_unavailable_handler(
    request: Request, exc: RecogniserUnavailableError
) -> JSONResponse:
    """ADR-098: the fast recogniser is not running; the reader offers the model instead."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "recogniser_unavailable",
            "detail": "The fast recogniser is not running. Use Ask the model to extract instead.",
        },
    )


@app.exception_handler(RecogniserRefusedError)
async def _recogniser_refused_handler(
    request: Request, exc: RecogniserRefusedError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "recogniser_refused", "detail": "The text is too long to recognise."},
    )


@app.exception_handler(DesignationRefusedError)
async def _designation_refused_handler(
    request: Request, exc: DesignationRefusedError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "designation_refused", "detail": str(exc)},
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


@app.exception_handler(ModelEgressRefused)
async def _model_egress_refused_handler(request: Request, exc: ModelEgressRefused) -> JSONResponse:
    """ADR-114 Amendment 6: material that may not leave, for a role with no local model."""
    return JSONResponse(
        status_code=409, content={"error": "model_egress_refused", "detail": str(exc)}
    )


@app.exception_handler(ScheduleRefused)
async def _schedule_refused_handler(request: Request, exc: ScheduleRefused) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "schedule_refused", "detail": str(exc)},
    )


@app.exception_handler(SourceAboveClearanceError)
async def _source_above_clearance_handler(
    request: Request, exc: SourceAboveClearanceError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "source_above_clearance",
            "detail": "This source is marked above your clearance, so you cannot load it. A loader "
            "cleared for its marking must run it.",
        },
    )


@app.exception_handler(StudioRecipeNotFoundError)
async def _studio_recipe_not_found_handler(
    request: Request, exc: StudioRecipeNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "studio_recipe_not_found"}
    )


@app.exception_handler(SourceDeclarationsInvalidError)
async def _source_declarations_invalid_handler(
    request: Request, exc: SourceDeclarationsInvalidError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "source_declarations_invalid", "detail": str(exc)},
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


@app.exception_handler(PatternConditionRefused)
async def _pattern_condition_refused_handler(
    request: Request, exc: PatternConditionRefused
) -> JSONResponse:
    """ADR-121: a condition on a pattern node the ontology does not allow (an unindexed or
    `sensitivity: high` property, one the type does not declare) is refused by name, typed, before
    anything is counted, run or saved; never a bare 500 and never quietly dropped."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "pattern_condition_refused",
            "detail": exc.detail,
            "var": exc.var,
            "property": exc.property_name,
            "reason": exc.reason,
        },
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


DEFAULT_CASE_NAME = "Untitled case"


class CreateInvestigationInput(BaseModel):
    name: str | None = None
    #: ADR-099: the datasets the case reads, all of the creator's unit. Left out, the case gets a
    #: new dataset of its own, named after it, for the data that will be added to it.
    dataset_ids: list[str] | None = None
    #: ADR-126: the domain packs the case carries. Left out, the column stays NULL, "never chosen",
    #: which reads as the POLE core model; a list, empty included, is a choice. An unknown pack is a
    #: 422.
    domains: list[DomainPack] | None = None


@app.post(
    "/v1/investigations",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.CREATE_CASE))],
)
async def create_investigation(
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    datasets: DatasetsDep,
    audit: AuditDep,
    body: CreateInvestigationInput | None = None,
) -> Investigation:
    """Needs no grant: whoever creates a case is its first Author (ADR-052 §4). The name is
    optional here only until the Glass proposes one (stage 3), after which it is required.
    ADR-099: the datasets named are checked before the case exists, so a refusal leaves none."""
    name = (body.name if body is not None else None) or DEFAULT_CASE_NAME
    named = body.dataset_ids if body is not None else None
    if named:
        own = {d.id for d in await datasets.list_for_unit(principal.org_unit)}
        if not set(named) <= own:
            raise DatasetRefusedError("not every dataset is one of this unit's")
    investigation = await investigations.create(
        principal, name=name, domains=body.domains if body is not None else None
    )
    if not named:
        named = [(await datasets.create(principal, investigation.name, suffix_if_taken=True)).id]
    await datasets.set_for_case(investigation.id, named, principal)
    await audit.record(
        principal=principal,
        action="create_investigation",
        investigation_id=investigation.id,
        resolved_query={"dataset_ids": list(named)},
        result_cardinality=1,
    )
    return investigation


@app.get("/v1/datasets")
async def list_datasets_route(principal: PrincipalDep, datasets: DatasetsDep) -> list[Dataset]:
    """The datasets of the caller's unit, for a new case to name (ADR-099)."""
    return await datasets.list_for_unit(principal.org_unit)


@app.post(
    "/v1/datasets",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.CREATE_CASE))],
)
async def create_dataset_route(
    body: CreateDatasetRequest, principal: PrincipalDep, datasets: DatasetsDep, audit: AuditDep
) -> Dataset:
    """A new, empty dataset of the caller's unit (ADR-099)."""
    dataset = await datasets.create(principal, body.name)
    await audit.record(
        principal=principal,
        action="create_dataset",
        resolved_query={"dataset_id": dataset.id},
        result_cardinality=1,
    )
    return dataset


@app.get("/v1/investigations/{investigation_id}/datasets")
async def case_datasets_route(
    investigation: InvestigationViewerDep, datasets: DatasetsDep
) -> list[Dataset]:
    """The datasets this case reads (ADR-099)."""
    return await datasets.of_case(investigation.id)


@app.put(
    "/v1/investigations/{investigation_id}/datasets",
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def set_case_datasets_route(
    investigation: InvestigationAuthorDep,
    body: CaseDatasetsRequest,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    audit: AuditDep,
) -> list[Dataset]:
    """Changes what the case reads: its Author's, audited, every dataset of the Author's unit
    (ADR-099). Nothing else widens a case's datasets."""
    before = await datasets.ids_of_case(investigation.id)
    changed = await datasets.set_for_case(investigation.id, body.dataset_ids, principal)
    await audit.record(
        principal=principal,
        action="set_case_datasets",
        investigation_id=investigation.id,
        resolved_query={"before": before, "after": [d.id for d in changed]},
        result_cardinality=len(changed),
    )
    return changed


class InvestigationListing(BaseModel):
    """One row of the case picker (ADR-052 §7): what the account may see of a case it holds a level
    on. Counts are not here yet: they need the working set read under the caller's own handling
    filter, and are added with the Glass picker (stage 3)."""

    id: str
    name: str
    level: AccessLevel
    created_at: datetime
    created_by: str
    branched_from: str | None = None
    #: ADR-126: the case's domain packs, which every reader of the case may see: it says what kind
    #: of case it is, never what it holds.
    domains: list[DomainPack] = Field(default_factory=list)
    #: ADR-084: this account has closed the case's tab. A flag per account, so it says nothing about
    #: anyone else's view of the same case.
    tab_hidden: bool = False
    #: ADR-099: the names of the datasets the case reads, in order, for the picker to show.
    datasets: list[str] = Field(default_factory=list)
    #: Their ids, in the same order, so the picker shows each name with its id (Amendment 6).
    dataset_ids: list[str] = Field(default_factory=list)


@app.get("/v1/investigations")
async def list_investigations(
    principal: PrincipalDep, investigations: InvestigationsDep, datasets: DatasetsDep
) -> list[InvestigationListing]:
    hidden = await investigations.hidden_tab_ids(principal)
    return [
        InvestigationListing(
            id=case.id,
            name=case.name,
            level=level,
            created_at=case.created_at,
            created_by=case.created_by,
            branched_from=case.branched_from,
            domains=case.domains,
            tab_hidden=case.id in hidden,
            datasets=[d.name for d in reads],
            dataset_ids=[d.id for d in reads],
        )
        for case, level in await investigations.list_for(principal)
        for reads in [await datasets.of_case(case.id)]
    ]


class TabStateInput(BaseModel):
    hidden: bool


@app.put("/v1/investigations/{investigation_id}/tab", status_code=status.HTTP_204_NO_CONTENT)
async def set_tab_state(
    investigation: InvestigationViewerDep,
    body: TabStateInput,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> None:
    """Open or close this case's tab for the caller only (ADR-084). Any account that can see the
    case may set it: it changes nothing about the case, only the caller's own strip of tabs, and
    the dependency has already answered 404 for a case the caller cannot see."""
    await investigations.set_tab_hidden(principal, investigation.id, body.hidden)
    await audit.record(
        principal=principal,
        action="set_tab_state",
        investigation_id=investigation.id,
        resolved_query={"hidden": body.hidden},
        result_cardinality=1,
    )


class CaseChangeInput(BaseModel):
    """What an Author changes on a case: its name, its domain packs, or both, at least one given
    (ADR-126 decision 1; it replaces `RenameInput`). An empty `domains` is a change, the POLE core
    model; a field left out, or null, is left alone."""

    name: str | None = None
    domains: list[DomainPack] | None = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("a case needs a name")
        return value.strip()

    @model_validator(mode="after")
    def _something_to_change(self) -> CaseChangeInput:
        if self.name is None and self.domains is None:
            raise ValueError("give a new name, new domain packs, or both")
        return self


@app.patch(
    "/v1/investigations/{investigation_id}", dependencies=[Depends(require_right(Right.SHARE_CASE))]
)
async def rename_investigation(
    investigation: InvestigationAuthorDep,
    body: CaseChangeInput,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> Investigation:
    """Change the case: its name, its domain packs, or both. The handler keeps the name it had when
    a rename was all it did, which `test_route_rights.py`'s table is keyed by. Each change is
    audited on its own: a rename as `rename_investigation`, a change of packs as
    `set_case_domains` with the packs before and after. The response carries the case's name and
    packs as they now stand."""
    # One store call, one transaction: a case removed between two separate writes would leave a
    # rename committed and audited beside packs that were refused.
    after = None if body.domains is None else sorted(set(body.domains))
    await investigations.change(investigation.id, name=body.name, domains=after, by=principal)
    changed = investigation
    if body.name is not None:
        await audit.record(
            principal=principal,
            action="rename_investigation",
            investigation_id=investigation.id,
            resolved_query={"name": body.name},
            result_cardinality=1,
        )
        changed = changed.model_copy(update={"name": body.name})
    if after is not None:
        await audit.record(
            principal=principal,
            action="set_case_domains",
            investigation_id=investigation.id,
            # The stored value, so a never-chosen case (None) is not reported as a choice of POLE.
            resolved_query={"before": investigation.domains_to_inherit(), "after": after},
            result_cardinality=1,
        )
        changed = changed.model_copy(update={"domains": after, "domains_chosen": True})
    return changed


@app.delete(
    "/v1/investigations/{investigation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_right(Right.REMOVE_CASE))],
)
async def remove_investigation(
    investigation: InvestigationAccessManagerDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> None:
    """A soft remove (ADR-052 Amendment 7). An Author, or the administrator of the case's own unit
    through the safety net (a case no Author is left to remove); neither gains any read access."""
    await investigations.remove(investigation.id, by=principal)
    await audit.record(
        principal=principal,
        action="remove_investigation",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=1,
    )


class AccessView(BaseModel):
    """What `GET .../access` shows. Everyone sees their own level; only an Author sees who else
    holds one, so a Viewer cannot learn the case's other participants."""

    your_level: AccessLevel | None
    unit_level: AccessLevel | None
    grants: dict[str, AccessLevel] | None
    #: Display names for the accounts in `grants` (ADR-106: only ids this response already
    #: carries); an account with no name to give is absent, and the Glass shows its id.
    names: dict[str, str] | None = None


@app.get(
    "/v1/investigations/{investigation_id}/access",
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def get_investigation_access(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    principal_names: PrincipalNamesDep,
) -> AccessView:
    level = await investigations.effective_level(investigation.id, principal)
    if level is not AccessLevel.AUTHOR:
        return AccessView(your_level=level, unit_level=None, grants=None)
    grants = await investigations.list_grants(investigation.id)
    return AccessView(
        your_level=level,
        unit_level=await investigations.unit_level(investigation.id),
        grants=grants,
        names=await principal_names.display_names(grants),
    )


class UnitLevelInput(BaseModel):
    """`author` is deliberately not accepted: the unit-wide level is none, Viewer or Editor
    (ADR-052 §5). Authority over a case is always named."""

    unit_level: Literal["viewer", "editor"] | None


@app.put(
    "/v1/investigations/{investigation_id}/access",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def set_investigation_unit_level(
    investigation: InvestigationAccessManagerDep,
    body: UnitLevelInput,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> None:
    level = None if body.unit_level is None else AccessLevel(body.unit_level)
    await investigations.set_unit_level(investigation.id, level, by=principal)
    await audit.record(
        principal=principal,
        action="set_unit_level",
        investigation_id=investigation.id,
        resolved_query={"unit_level": body.unit_level},
        result_cardinality=1,
    )


class GrantInput(BaseModel):
    level: AccessLevel


def _grantee(account_id: str) -> str:
    """The account name the identity provider knows the person by (ADR-052 P3, confirmed). A
    mistyped name grants nothing to anyone, so the only check is that it is a plain, sensible
    string."""
    name = account_id.strip()
    if not name or len(name) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="an account name is 1 to 200 characters",
        )
    return name


@app.put(
    "/v1/investigations/{investigation_id}/access/grants/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def set_investigation_grant(
    investigation: InvestigationAccessManagerDep,
    account_id: str,
    body: GrantInput,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> None:
    grantee = _grantee(account_id)
    await investigations.set_grant(investigation.id, grantee, body.level, by=principal)
    await audit.record(
        principal=principal,
        action="grant_access",
        investigation_id=investigation.id,
        resolved_query={"account": grantee, "level": body.level.value},
        result_cardinality=1,
    )


@app.delete(
    "/v1/investigations/{investigation_id}/access/grants/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def remove_investigation_grant(
    investigation: InvestigationAccessManagerDep,
    account_id: str,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> None:
    grantee = _grantee(account_id)
    await investigations.remove_grant(investigation.id, grantee, by=principal)
    await audit.record(
        principal=principal,
        action="revoke_access",
        investigation_id=investigation.id,
        resolved_query={"account": grantee},
        result_cardinality=1,
    )


@app.get(
    "/v1/investigations/{investigation_id}/access/history",
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def get_investigation_access_history(
    investigation: InvestigationAccessManagerDep, investigations: InvestigationsDep
) -> list[AccessHistoryEntry]:
    return await investigations.access_history(investigation.id)


@app.get("/v1/investigations/{investigation_id}")
async def get_investigation(
    investigation: InvestigationViewerDep,
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


def _narrowed(parent: Interval | None, asked: Interval | None) -> Interval | None:
    """The window a new branch records: the one asked for, held inside the parent branch's own
    (both ends included; an end of `None` runs on without end). Neither: none."""
    if parent is None or asked is None:
        return parent if asked is None else asked
    ends = [t for t in (parent.valid_to, asked.valid_to) if t is not None]
    return Interval(
        valid_from=max(parent.valid_from, asked.valid_from),
        valid_to=min(ends) if ends else None,
    )


class BranchRequest(BaseModel):
    """ADR-084. `node_ids` absent: fork the whole working set, as the cap breach's "branch" option
    always did. Present: fork only those nodes and the links between them (an empty list is a
    choice of nothing, and is refused). `name` is the new case's name; blank means a default."""

    node_ids: list[NodeId] | None = Field(default=None, max_length=50_000)
    name: str | None = None
    #: ADR-128 decision 2 (B3, select what is lit): the brushed window, both ends inside it. With
    #: it, the branch holds only the links with an event in the window and the nodes they touch,
    #: derived here on the server and kept only where `node_ids` names a node. It needs a choice of
    #: nodes: the Glass sends the window with the lit selection, never alone.
    window: Interval | None = None

    @model_validator(mode="after")
    def _a_window_comes_with_a_choice_and_runs_forwards(self) -> BranchRequest:
        if self.window is None:
            return self
        if self.node_ids is None:
            raise ValueError("a window is sent with the nodes chosen, not alone")
        if self.window.valid_to is not None and self.window.valid_from > self.window.valid_to:
            raise ValueError("the window ends before it starts")
        return self


@app.post(
    "/v1/investigations/{investigation_id}/branch",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.BRANCH_CASE))],
)
async def branch_investigation(
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
    datasets: DatasetsDep,
    analytics: AnalyticsDep,
    body: BranchRequest | None = None,
) -> Investigation:
    # `03_CONDUIT_MIDDLEWARE.md` §3.1: "fork the working set into a new
    # investigation" — one of the cap breach's three options, made real.
    # `AuthorizedInvestigationDep` has already checked the branching
    # principal against the *source* investigation's `owning_unit`; the
    # new investigation gets its own, from this principal, not inherited.
    node_ids = body.node_ids if body is not None else None
    window = body.window if body is not None else None
    source_name = investigation.name or DEFAULT_CASE_NAME
    # ADR-097 (design review item 3): a branch is named for what it is, not for a selection.
    name = f"Branch of {source_name}"
    lit_nodes: list[Node] = []
    lit_links: list[Edge] = []
    if window is not None:
        # ADR-128 decision 2: what is lit is derived here, never taken from the request. The links
        # with an event in the window come from the analytics port in its own access-filtered query
        # for this principal, and the working set's own projection decides which of them, and which
        # of the named nodes, this principal may see. Asked first, and before the case exists, so
        # that an empty slice (`NothingToBranchError`) or one past the cap (`LimitExceededError`)
        # leaves no case behind.
        assert node_ids is not None  # `BranchRequest` refuses a window without a choice
        lit = await analytics.first_seen(
            FirstSeenRequest(
                filter=await _case_event_filter(
                    EventFilter(investigation_scope=investigation.id, window=window),
                    principal,
                    investigations,
                    audit,
                    working_set,
                )
            ),
            principal,
        )
        lit_nodes, lit_links = await working_set.branch_lit_contents(
            investigation.id, principal, node_ids, lit.edges.keys()
        )
        name = (
            f"Branch of {source_name} ({len(lit_nodes)} lit "
            f"{'node' if len(lit_nodes) == 1 else 'nodes'})"
        )
    elif node_ids is not None:
        # Asked first, and before the case exists, so that a choice with nothing visible in it
        # (`NothingToBranchError`, a 422) leaves no empty case behind.
        chosen, _, _ = await working_set.branch_contents(investigation.id, principal, node_ids)
        name = f"Branch of {source_name} ({len(chosen)} {'node' if len(chosen) == 1 else 'nodes'})"
    if body is not None and body.name is not None and body.name.strip():
        name = body.name.strip()
    # ADR-128 decision 2: a branch made from what is lit records its window, so its timeline holds
    # only the events inside it; a branch of a windowed case keeps that window (intersected with its
    # own, if it has one), so it does not widen again. A branch of an ordinary case records none.
    held_window = _narrowed(investigation.branch_window, window)
    new_investigation = await investigations.create(
        principal,
        name=name,
        branched_from=investigation.id,
        domains=investigation.domains_to_inherit(),
        **({"branch_window": held_window} if held_window is not None else {}),
    )
    # ADR-099: a branch reads what its parent reads.
    await datasets.copy_case(investigation.id, new_investigation.id)
    if window is not None:
        outcome = await working_set.branch_add(
            new_investigation.id, lit_nodes, lit_links, principal
        )
    else:
        outcome = await working_set.branch(
            investigation.id, new_investigation.id, principal, node_ids=node_ids
        )
    await publish_delta(valkey, new_investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        new_investigation.id,
        seq=outcome.delta.seq,
        label=BRANCHED,
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="branch",
        investigation_id=investigation.id,
        resolved_query={
            "new_investigation_id": new_investigation.id,
            **({"node_ids": list(node_ids)} if node_ids is not None else {}),
            **({"window": window.model_dump(mode="json")} if window is not None else {}),
        },
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return new_investigation


class BranchByFilterRequest(BranchFilter):
    """ADR-124 decision 2, "open a filtered branch": the reader's own view, narrowed to entity
    types, a date window, or both (`BranchFilter` has the rules). `name` is the new case's name;
    blank means the default a branch has."""

    name: str | None = None


@app.post(
    "/v1/investigations/{investigation_id}/branch-by-filter",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.BRANCH_CASE))],
)
async def branch_investigation_by_filter(
    investigation: InvestigationEditorDep,
    body: BranchByFilterRequest,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
    datasets: DatasetsDep,
) -> Investigation:
    """Builds, on the server, a new case from the reader's own projected view narrowed by the filter
    (ADR-124 decision 2), for a reader whose view a colleague's work has pushed past the cap. It is
    created as `branch` creates one: the reader owns it, it records its origin, it takes its
    parent's domain packs and datasets, and it records a history step. What it holds is asked first,
    and before the case exists, so that an empty choice (`NothingToBranchError`, a 422, the same
    answer for a type only hidden material holds as for one that does not exist) or a result still
    past the cap (`limit_exceeded`, with the filtered figures, the reader's own) leaves no case
    behind."""
    nodes, edges = await working_set.branch_filtered_contents(investigation.id, principal, body)
    name = f"Branch of {investigation.name or DEFAULT_CASE_NAME}"
    if body.name is not None and body.name.strip():
        name = body.name.strip()
    new_investigation = await investigations.create(
        principal,
        name=name,
        branched_from=investigation.id,
        domains=investigation.domains_to_inherit(),
    )
    await datasets.copy_case(investigation.id, new_investigation.id)
    outcome = await working_set.branch_add(new_investigation.id, nodes, edges, principal)
    await publish_delta(valkey, new_investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        new_investigation.id,
        seq=outcome.delta.seq,
        label=BRANCHED,
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="branch_by_filter",
        investigation_id=investigation.id,
        resolved_query={
            "new_investigation_id": new_investigation.id,
            "filter": body.model_dump(mode="json", exclude={"name"}),
        },
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return new_investigation


async def _record_history_step(
    working_set: WorkingSetService | None,
    history: InvestigationHistoryStore,
    investigation_id: str,
    *,
    seq: int,
    label: str,
    principal: Principal,
    snapshot: bool = True,
) -> HistoryStep:
    """Called after every mutation that changes working-set membership
    (the "named-step history with restore" capability) — full
    current membership, not just the mutation's own delta, so the step is
    independently restorable (`history.py`'s module docstring).

    `snapshot=False` is for a step that is not a state of the canvas (ADR-128: an edit to the case
    brief): no working set is read, the step holds no nodes or links, and its label is in
    `NOT_RESTORABLE`, so it is listed and never restored."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    if snapshot:
        assert working_set is not None
        nodes, edges = await working_set.current_membership(investigation_id)
    return await history.record_step(
        investigation_id, seq=seq, label=label, created_by=principal.id, nodes=nodes, edges=edges
    )


async def _record_brief_edit(
    history: InvestigationHistoryStore, investigation_id: str, principal: Principal
) -> None:
    """One History step for an edit to the case brief (ADR-128 decision 3): fixed text, no snapshot.
    It takes the case's latest sequence number rather than a new one, so the change stream's own
    count, which its clients hold, is not moved by something that is not a canvas change."""
    await _record_history_step(
        None,
        history,
        investigation_id,
        seq=await history.last_seq(investigation_id),
        label=BRIEF_EDITED,
        principal=principal,
        snapshot=False,
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


@app.post(
    "/v1/investigations/{investigation_id}/seed",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def seed(
    investigation: InvestigationEditorDep,
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
        label=SEEDED,
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


@app.post(
    "/v1/investigations/{investigation_id}/expand",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def expand(
    investigation: InvestigationEditorDep,
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
        label=EXPANDED,
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


@app.post(
    "/v1/investigations/{investigation_id}/links-among",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def links_among_route(
    investigation: InvestigationEditorDep,
    body: LinksAmongRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> LinksAmongOutcome:
    """The links among nodes already in the view (ADR-098 decision 1), which an expansion leaves
    out: all of them, or none and `limit_exceeded` past the cap (rule 2). Access-filtered in the
    adapter for this analyst (rule 3); Editor, since it adds to the case's working set."""
    outcome = await working_set.links_among(
        investigation.id, principal, node_ids=body.node_ids, degree=body.degree
    )
    await publish_delta(valkey, investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=outcome.delta.seq,
        label=LINKS_AMONG,
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="links_among",
        investigation_id=investigation.id,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=outcome.added,
    )
    return outcome


@app.post(
    "/v1/investigations/{investigation_id}/expand/preview",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def expand_preview(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/working-set/add-by-identifiers",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def add_by_identifiers_route(
    investigation: InvestigationEditorDep,
    body: AddByIdentifiersRequest,
    principal: PrincipalDep,
    graph: GraphDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> AddByIdentifiersResponse:
    """ADR-128 decision 1 (B2): a pasted or uploaded list of identifiers, counted (`confirm: false`)
    or added (`true`). Each is read by shape, normalised by its Knowledge Adapter and found through
    the access-filtered `find_node`; the count is read, found, matched nothing you can see,
    repeated. An identifier that does not exist and one the analyst may not see are one figure, one
    lookup and one audit entry (counts only), so the route is not a membership test (rule 3). The
    add goes through the working set's own `seed`, so past the cap it is the typed
    `limit_exceeded` and nothing is added. More than 5,000 identifiers is refused by name, never
    truncated. Editor, since it adds to the case's working set."""
    try:
        resolution = await resolve_identifiers(graph, body.identifiers, principal)
    except TooManyIdentifiersError as exc:
        await audit.record(
            principal=principal,
            action="add_by_identifiers",
            investigation_id=investigation.id,
            resolved_query={
                "read": exc.received,
                "refused": True,
                "cap": MAX_IDENTIFIERS,
                "confirm": body.confirm,
                "with_links": body.with_links,
            },
            result_cardinality=0,
        )
        raise
    counts = resolution.counts
    outcome = None
    if body.confirm:
        outcome = await working_set.add_by_identifiers(
            investigation.id, resolution.nodes, principal, with_links=body.with_links
        )
        await publish_delta(valkey, investigation.id, outcome.delta)
        await _record_history_step(
            working_set,
            history,
            investigation.id,
            seq=outcome.delta.seq,
            label=SEEDED,
            principal=principal,
        )
    await audit.record(
        principal=principal,
        action="add_by_identifiers",
        investigation_id=investigation.id,
        resolved_query={
            **counts.model_dump(),
            "confirm": body.confirm,
            "with_links": body.with_links,
        },
        result_cardinality=len(resolution.nodes),
    )
    return AddByIdentifiersResponse(counts=counts, added=outcome)


@app.delete(
    "/v1/investigations/{investigation_id}/nodes",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def remove_nodes(
    investigation: InvestigationEditorDep,
    body: RemoveNodesRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> dict[str, int]:
    delta = await working_set.remove(investigation.id, body.node_ids, principal)
    seq = delta.seq
    await publish_delta(valkey, investigation.id, delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=seq,
        label=REMOVED,
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


@app.get(
    "/v1/investigations/{investigation_id}/resolution/threshold",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def get_resolution_threshold_route(
    investigation: InvestigationViewerDep,
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


@app.put(
    "/v1/investigations/{investigation_id}/resolution/threshold",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def set_resolution_threshold_route(
    investigation: InvestigationEditorDep,
    body: SetThresholdRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> ResolutionOutcome:
    outcome = await resolution_module.set_threshold(working_set, investigation.id, body, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
    await audit.record(
        principal=principal,
        action="set_resolution_threshold",
        investigation_id=investigation.id,
        resolved_query={"threshold": body.threshold},
        result_cardinality=outcome.affected,
    )
    return outcome


def _clean_reason(reason: str | None) -> str | None:
    """A reason as the audit stream records it: trimmed, and `None` when blank."""
    text = (reason or "").strip()
    return text or None


@app.post(
    "/v1/investigations/{investigation_id}/resolution/link",
    dependencies=[Depends(require_right(Right.RESOLVE_ENTITIES))],
)
async def link_resolution_route(
    investigation: InvestigationEditorDep,
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
) -> ResolutionOutcome:
    """Phase 7 Stage 6c: a manual link is a `SAME_AS` write that can grow a saved pattern's own
    match set (`06_DECISIONS.md` ADR-037's own change-stream amendment names manual assertion as
    one of its three producers) — evaluated synchronously here, the identical shape and the
    identical `run_studio_recipe`'s own docstring reasoning for why only this principal's own
    hotlists/monitors can fire from it. `split_resolution_route` below does not call evaluation at
    all — a `NOT_SAME_AS` write can only shrink a match set, never grow one."""
    outcome, entry = await resolution_module.link(working_set, investigation.id, body, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
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
        result_cardinality=outcome.affected,
        justification=_clean_reason(body.reason),
    )
    return outcome


@app.post(
    "/v1/investigations/{investigation_id}/resolution/split",
    dependencies=[Depends(require_right(Right.RESOLVE_ENTITIES))],
)
async def split_resolution_route(
    investigation: InvestigationEditorDep,
    body: ManualAssertionRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> ResolutionOutcome:
    outcome, _entry = await resolution_module.split(working_set, investigation.id, body, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
    await audit.record(
        principal=principal,
        action="manual_split",
        investigation_id=investigation.id,
        resolved_query={"node_a": body.node_a, "node_b": body.node_b},
        result_cardinality=outcome.affected,
        justification=_clean_reason(body.reason),
    )
    return outcome


@app.get(
    "/v1/investigations/{investigation_id}/resolution/explain/{cluster_id}",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def explain_resolution_route(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/compute/{metric}",
    dependencies=[Depends(require_right(Right.RUN_ANALYSIS))],
)
async def compute_metric_route(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/ingest/extract",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def run_extraction_route(
    investigation: InvestigationEditorDep,
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


@app.get(
    "/v1/investigations/{investigation_id}/ingest/candidates",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def list_extraction_candidates_route(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/ingest/candidates/{candidate_id}/accept",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def accept_extraction_candidate_route(
    investigation: InvestigationEditorDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/ingest/candidates/{candidate_id}/reject",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def reject_extraction_candidate_route(
    investigation: InvestigationEditorDep,
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


@app.get(
    "/v1/investigations/{investigation_id}/dossier/documents/{document_id}",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def get_dossier_document_route(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/nodes/{node_id}/confirm",
    dependencies=[Depends(require_right(Right.CONFIRM_INFERRED))],
)
async def confirm_node_route(
    investigation: InvestigationEditorDep,
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


class SuppressionMarkInput(BaseModel):
    investigation_id: str
    #: Why this node is proposed for suppression. Required and non-empty: an unexplained
    #: mark is a puzzle for whoever finds it, and step two has to cite something.
    reason: str


@app.post(
    "/v1/investigations/{investigation_id}/nodes/{node_id}/suppression-mark",
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def mark_node_for_suppression(
    investigation: InvestigationEditorDep,
    node_id: str,
    body: SuppressionMarkInput,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
    marks: SuppressionMarksDep,
) -> SuppressionMark:
    """**Step one of two — owner ruling R7 (TENTATIVE, 27 September 2026).** An analyst proposes
    a suppression; nothing is suppressed yet. The node keeps its place in every read, its
    revision does not move, and the mark is reversible — `services/api/suppression.py`'s own
    docstring has why a mark is deliberately not a graph write.

    The suppression itself takes effect only when its evidence arrives through the Ingest Studio
    (R7's step two), so that no record is ever suppressed on the strength of a click alone.

    Access control is inside the store, checked against this principal before anything is
    written (`CLAUDE.md` rule 2), and a node this principal cannot see is refused identically to
    one that does not exist."""
    mark = await marks.mark(node_id, body.investigation_id, principal, graph, reason=body.reason)
    await audit.record(
        principal=principal,
        action="mark_node_for_suppression",
        investigation_id=body.investigation_id,
        resolved_query={"node_id": node_id},
        result_cardinality=1,
    )
    return mark


@app.delete(
    "/v1/investigations/{investigation_id}/nodes/{node_id}/suppression-mark",
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def unmark_node_for_suppression(
    investigation: InvestigationEditorDep,
    node_id: str,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
    marks: SuppressionMarksDep,
) -> dict[str, bool]:
    """R7's own word is "reversible"."""
    removed = await marks.unmark(node_id, principal, graph)
    await audit.record(
        principal=principal,
        action="unmark_node_for_suppression",
        resolved_query={"node_id": node_id},
        result_cardinality=1 if removed else 0,
    )
    return {"removed": removed}


@app.exception_handler(NodeNotVisibleError)
async def _node_not_visible_handler(request: Request, exc: NodeNotVisibleError) -> JSONResponse:
    """404, not 403 — a principal who cannot see a node must not learn that it exists, the same
    existence-leak collapse `get_authorized_investigation` already makes."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "node_not_found"})


@app.post(
    "/v1/investigations/{investigation_id}/nodes/{node_id}/retract",
    dependencies=[Depends(require_right(Right.CONFIRM_INFERRED))],
)
async def retract_node_route(
    investigation: InvestigationEditorDep,
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


@app.get(
    "/v1/investigations/{investigation_id}/history",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def get_investigation_history(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/history/{step_id}",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def restore_history_step(
    investigation: InvestigationEditorDep,
    step_id: str,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> DeltaSnapshot:
    step = await history.get_step(investigation.id, step_id)
    if step.label in NOT_RESTORABLE:
        # ADR-128: a brief edit holds no canvas snapshot; restoring it would empty the canvas.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"error": "step_not_restorable"}
        )
    # `WorkingSetService.restore` re-projects `step`'s stored (unfiltered)
    # bodies against `principal` fresh — never the visibility `step` was
    # recorded with (`history.py`'s module docstring).
    restored = await working_set.restore(investigation.id, step.nodes, step.edges, principal)
    snapshot = restored.response
    await publish_delta(valkey, investigation.id, restored.published)
    await audit.record(
        principal=principal,
        action="restore_history_step",
        investigation_id=investigation.id,
        resolved_query={"step_id": step_id},
        result_cardinality=len(snapshot.nodes) + len(snapshot.edges),
    )
    return snapshot


# --- search -------------------------------------------------------------------


@app.post(
    "/v1/investigations/{investigation_id}/search",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def search_route(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/suggest",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def suggest_route(
    investigation: InvestigationViewerDep,
    body: SuggestRequest,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
) -> SuggestResponse:
    result = await search_module.suggest(graph, body, principal)
    await audit.record(
        principal=principal,
        action="suggest",
        resolved_query={
            "query": body.query,
            "mode": body.mode,
            "ignore_case": body.ignore_case,
            "types": body.types,
        },
        result_cardinality=len(result.nodes),
    )
    return result


# --- the Explore panel (06_DECISIONS.md ADR-100) -----------------------------
#
# What the case's data holds and its most connected nodes, for an analyst who does not yet know
# what to search for. Each figure is computed in the store with the principal `get_principal`
# builds for this case, so it is of the case's datasets and the analyst's clearance only (rule 3);
# a ranking carries its total and offset, so a page never passes for the whole (rule 2).

#: The largest ranking page one request may ask for.
EXPLORE_MAX_PAGE = 50


def get_explore(request: Request, graph: GraphDep) -> ExploreService:
    return ExploreService(graph, getattr(request.app.state, "explore_cache", None))


ExploreDep = Annotated[ExploreService, Depends(get_explore)]


@app.get(
    "/v1/investigations/{investigation_id}/explore/counts",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def explore_counts_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    explore: ExploreDep,
    audit: AuditDep,
) -> TypeCounts:
    counts = await explore.counts(principal)
    await audit.record(
        principal=principal,
        action="explore_counts",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=sum(counts.nodes.values()),
    )
    return counts


@app.get(
    "/v1/investigations/{investigation_id}/explore/most-connected",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def explore_most_connected_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    explore: ExploreDep,
    audit: AuditDep,
    entity_type: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=EXPLORE_MAX_PAGE)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RankedNodes:
    ranked = await explore.most_connected(
        principal, entity_type=entity_type, limit=limit, offset=offset
    )
    await audit.record(
        principal=principal,
        action="explore_most_connected",
        investigation_id=investigation.id,
        resolved_query={"entity_type": entity_type, "limit": limit, "offset": offset},
        result_cardinality=len(ranked.nodes),
    )
    return ranked


@app.get(
    "/v1/investigations/{investigation_id}/explore/busiest-links",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def explore_busiest_links_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    explore: ExploreDep,
    audit: AuditDep,
    edge_type: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=EXPLORE_MAX_PAGE)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    node_id: Annotated[str | None, Query(max_length=200)] = None,
) -> RankedLinks:
    """ADR-100 decision 5: the links that stand for the most records, within the case's datasets.
    With `node_id` (Amendment 8), one node's own links — how a dense node is brought to the canvas
    with its N busiest rather than all or nothing."""
    ranked = await explore.busiest_links(
        principal, edge_type=edge_type, limit=limit, offset=offset, node_id=node_id
    )
    await audit.record(
        principal=principal,
        action="explore_busiest_links",
        investigation_id=investigation.id,
        resolved_query={
            "edge_type": edge_type,
            "limit": limit,
            "offset": offset,
            "node_id": node_id,
        },
        result_cardinality=len(ranked.links),
    )
    return ranked


@app.get(
    "/v1/investigations/{investigation_id}/explore/busiest-days",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def explore_busiest_days_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    explore: ExploreDep,
    analytics: AnalyticsDep,
    audit: AuditDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    limit: Annotated[int, Query(ge=1, le=EXPLORE_MAX_PAGE)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BusiestDays:
    """ADR-100 decision 5: the case's days with the most events, read through the same case filter
    as the timeline (a branch reads its parents' events on the links it holds)."""
    case_events = await _case_event_filter(
        EventFilter(investigation_scope=investigation.id),
        principal,
        investigations,
        audit,
        working_set,
    )
    days = await explore.busiest_days(principal, analytics, case_events, limit=limit, offset=offset)
    await audit.record(
        principal=principal,
        action="explore_busiest_days",
        investigation_id=investigation.id,
        resolved_query={"limit": limit, "offset": offset},
        result_cardinality=len(days.days),
    )
    return days


@app.get(
    "/v1/investigations/{investigation_id}/explore/groups",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def explore_groups_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    explore: ExploreDep,
    compute: ComputeDep,
    audit: AuditDep,
) -> Groups:
    """ADR-100 decision 6: the case's largest groups and the nodes bridging them, within its
    datasets; a case over the working set's caps is `limit_exceeded`, never a sample."""
    found = await explore.groups(principal, compute)
    await audit.record(
        principal=principal,
        action="explore_groups",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=found.total_groups,
    )
    return found


@app.get(
    "/v1/investigations/{investigation_id}/explore/whats-new",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def explore_whats_new_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    explore: ExploreDep,
    marks: SuppressionMarksDep,
    audit: AuditDep,
) -> WhatsNew:
    """ADR-100 decision 7 (Amendment 6): the latest loads into the case's datasets, and the nodes
    colleagues confirmed or marked for suppression in them, each named only where the reader can
    see it."""
    news = await explore.whats_new(principal, marks)
    await audit.record(
        principal=principal,
        action="explore_whats_new",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=news.loads_total + news.confirmed_total + news.marked_total,
    )
    return news


@app.get(
    "/v1/investigations/{investigation_id}/explore/starter-questions",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def explore_starter_questions_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    explore: ExploreDep,
    ontology: OntologyDep,
    audit: AuditDep,
) -> StarterQuestions:
    """ADR-100 decision 8 (Amendment 7): query-builder patterns that suit the types the case's
    datasets hold, as this reader sees them."""
    offered = await explore.starter_questions(principal, public_ontology(ontology))
    await audit.record(
        principal=principal,
        action="explore_starter_questions",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=offered.total,
    )
    return offered


class StarterRunOutcome(BaseModel):
    """What a starter question put on the canvas (ADR-100 Amendment 7)."""

    delta: DeltaAdd
    added_nodes: int
    added_links: int


@app.post(
    "/v1/investigations/{investigation_id}/explore/starter-questions/{question_id}/run",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def explore_starter_run_route(
    investigation: InvestigationEditorDep,
    question_id: str,
    principal: PrincipalDep,
    explore: ExploreDep,
    ontology: OntologyDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> StarterRunOutcome:
    """ADR-100 Amendment 7: runs a question offered for this case and puts what it matched, and
    the links among it, on the canvas: all of it or, past the working set's cap, none
    (`limit_exceeded`). Counted first: at the query builder's limit, nothing is matched and the
    answer is `too_many_matches` with how many at least (rule 2). Editor, since it adds to the
    case's working set."""
    nodes, edges = await explore.run_starter(principal, public_ontology(ontology), question_id)
    outcome = await working_set.seed(investigation.id, nodes, edges, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=outcome.delta.seq,
        label=STARTER_QUESTION,
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="explore_starter_run",
        investigation_id=investigation.id,
        resolved_query={"question_id": question_id},
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return StarterRunOutcome(
        delta=outcome.delta,
        added_nodes=len(outcome.delta.nodes),
        added_links=len(outcome.delta.edges),
    )


def _shared_link_type(ontology: OntologySchema, edge_type: str) -> str:
    """A link type a node's contacts can be shared by: one of the ontology's own, not a system
    type such as `SAME_AS`."""
    known = {e.name for e in public_ontology(ontology).edge_types if not e.system}
    if edge_type not in known:
        raise HTTPException(status_code=422, detail="edge_type is not a link type of the ontology")
    return edge_type


@app.get(
    "/v1/investigations/{investigation_id}/nodes/{node_id}/shared-contacts",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def shared_contacts_route(
    investigation: InvestigationViewerDep,
    node_id: str,
    edge_type: str,
    principal: PrincipalDep,
    graph: GraphDep,
    ontology: OntologyDep,
    audit: AuditDep,
    limit: int = Query(default=10, ge=1, le=EXPLORE_MAX_PAGE),
) -> SharedContacts:
    """ADR-100 Amendment 7 decision 4: who shares at least two contacts with this node by the
    link type, most first, counted in the store as the reader (rule 3). A node the reader cannot
    see shares with nobody."""
    found = await graph.shared_contacts(
        node_id, principal, edge_type=_shared_link_type(ontology, edge_type), limit=limit
    )
    await audit.record(
        principal=principal,
        action="shared_contacts",
        investigation_id=investigation.id,
        resolved_query={"node_id": node_id, "edge_type": edge_type},
        result_cardinality=found.total,
    )
    return found


@app.post(
    "/v1/investigations/{investigation_id}/nodes/{node_id}/shared-contacts/{other_id}/canvas",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def shared_pair_canvas_route(
    investigation: InvestigationEditorDep,
    node_id: str,
    other_id: str,
    edge_type: str,
    principal: PrincipalDep,
    explore: ExploreDep,
    ontology: OntologyDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> StarterRunOutcome:
    """ADR-100 Amendment 7 decision 4: the two nodes, the contacts they share and the links among
    them onto the canvas, all or, past the cap, none. Editor, since it adds to the working set."""
    nodes, edges = await explore.shared_pair(
        principal, node_id, other_id, edge_type=_shared_link_type(ontology, edge_type)
    )
    outcome = await working_set.seed(investigation.id, nodes, edges, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=outcome.delta.seq,
        label=SHARED_CONTACTS,
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="shared_pair_canvas",
        investigation_id=investigation.id,
        resolved_query={"node_id": node_id, "other_id": other_id, "edge_type": edge_type},
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return StarterRunOutcome(
        delta=outcome.delta,
        added_nodes=len(outcome.delta.nodes),
        added_links=len(outcome.delta.edges),
    )


@app.exception_handler(StarterNotOffered)
async def _starter_not_offered_handler(request: Request, exc: StarterNotOffered) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "not_offered"})


@app.exception_handler(TooManyMatches)
async def _too_many_matches_handler(request: Request, exc: TooManyMatches) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "too_many_matches", "at_least": exc.at_least},
    )


# --- the visual query builder (Phase 7 Stage 4, 06_DECISIONS.md ADR-030) ------
#
# Not investigation-scoped — `patterns.py`'s own module docstring has the full reasoning, the
# same one `/v1/search` above already gives for its own lack of an `owning_unit` check.


@app.post(
    "/v1/investigations/{investigation_id}/patterns/preview",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def patterns_preview_route(
    investigation: InvestigationViewerDep,
    pattern: PatternQuery,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
    ontology: OntologyDep,
) -> PatternPreview:
    check_pattern_conditions(pattern, ontology)
    preview = await preview_pattern(pattern, graph=graph, principal=principal)
    await audit.record(
        principal=principal,
        action="patterns_preview",
        resolved_query=pattern.model_dump(mode="json"),
        result_cardinality=preview.estimated_count,
    )
    return preview


@app.post(
    "/v1/investigations/{investigation_id}/patterns/run",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def patterns_run_route(
    investigation: InvestigationViewerDep,
    pattern: PatternQuery,
    principal: PrincipalDep,
    graph: GraphDep,
    jobs: JobsDep,
    audit: AuditDep,
    ontology: OntologyDep,
) -> PatternRunAccepted:
    check_pattern_conditions(pattern, ontology)
    accepted = await run_pattern(pattern, graph=graph, principal=principal, jobs=jobs)
    await audit.record(
        principal=principal,
        action="patterns_run",
        resolved_query=pattern.model_dump(mode="json"),
        result_cardinality=accepted.matched_count or 0,
    )
    return accepted


@app.post(
    "/v1/investigations/{investigation_id}/patterns/ask",
    dependencies=[Depends(require_right(Right.ASK_MODEL))],
)
async def ask_to_search_route(
    investigation: InvestigationViewerDep,
    body: AskToSearchRequest,
    principal: PrincipalDep,
    pattern_ask: PatternAskDep,
    audit: AuditDep,
    ontology: OntologyDep,
) -> PatternProposal:
    """ADR-129 decision 2: the model is given the case's vocabulary and the question and proposes a
    pattern, validated against the ontology and ADR-121; the response is the pattern, a one-line
    explanation and the preview's own count. Viewer, as the preview is: it writes nothing, and
    running the pattern is the existing run route's, counted first (rules 3 and 4)."""
    try:
        proposal = await pattern_ask.ask(investigation.id, body, principal, ontology)
    except CouldNotExpress as refused:
        await audit.record(
            principal=principal,
            action="patterns_ask",
            investigation_id=investigation.id,
            resolved_query={"refused": refused.reason},
            result_cardinality=0,
        )
        raise
    await audit.record(
        principal=principal,
        action="patterns_ask",
        investigation_id=investigation.id,
        resolved_query=proposal.pattern.model_dump(mode="json"),
        result_cardinality=proposal.estimated_count,
    )
    return proposal


# --- saved patterns (Phase 7 Stage 4, 06_DECISIONS.md ADR-032/036/040) --------
#
# Owner-only, not investigation-scoped — `pattern_store.py`'s own module docstring has the full
# reasoning. No share route exists: ADR-040 (pattern sharing) is Proposed, not accepted, so there
# is nothing here for a share endpoint to do yet.


@app.post(
    "/v1/investigations/{investigation_id}/patterns/save",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def patterns_save_route(
    investigation: InvestigationEditorDep,
    body: SavePatternRequest,
    principal: PrincipalDep,
    patterns_store: PatternsStoreDep,
    audit: AuditDep,
    ontology: OntologyDep,
) -> SavedPattern:
    """A condition the ontology refuses is refused here, before it is stored (ADR-121): a rule that
    replays the saved pattern later must not hold what no route would run.

    A `pattern_id` the caller does not own raises `PatternStore`'s own `PatternNotFoundError`
    (mapped to 404 by `_pattern_not_found_handler`) — the same existence-leak collapse
    `get_authorized_investigation` already uses, here inside `PatternStore.save` itself rather
    than a separate route-level gate, since save and the ownership check are one operation."""
    check_pattern_conditions(body.definition, ontology)
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


@app.get(
    "/v1/investigations/{investigation_id}/patterns",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def patterns_list_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    patterns_store: PatternsStoreDep,
) -> SavedPatternList:
    """Never another principal's patterns — `PatternStore.list_authorized` filters by owner in
    the query itself, not after fetching everything."""
    return SavedPatternList(patterns=await patterns_store.list_authorized(principal))


@app.get(
    "/v1/investigations/{investigation_id}/patterns/{pattern_id}",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def patterns_load_route(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/hotlists",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.KEEP_WATCHES))],
)
async def create_hotlist_route(
    investigation: InvestigationEditorDep,
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


@app.get(
    "/v1/investigations/{investigation_id}/hotlists",
    dependencies=[Depends(require_right(Right.KEEP_WATCHES))],
)
async def list_hotlists_route(
    investigation: InvestigationViewerDep, principal: PrincipalDep, hotlists_store: HotlistsStoreDep
) -> HotlistList:
    return HotlistList(hotlists=await hotlists_store.list_authorized(principal))


@app.post(
    "/v1/investigations/{investigation_id}/judgements",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def save_judgement_route(
    investigation: InvestigationEditorDep,
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


@app.get(
    "/v1/investigations/{investigation_id}/judgements",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def list_judgements_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    judgements_store: JudgementsStoreDep,
    graph: GraphDep,
    principal_names: PrincipalNamesDep,
) -> JudgementListResponse:
    """`list_visible_judgements`, not `list_for_investigation` — ADR-046's own hide-in-full rule
    and the lazy `contradicting`-unreadable flag both apply here, not only the ownership check."""
    judgements = await list_visible_judgements(judgements_store, investigation.id, principal, graph)
    # ADR-106: names only for the authors of judgements actually served — after the visibility
    # filter, never before it.
    names = await principal_names.display_names(j.author for j in judgements)
    return JudgementListResponse(
        judgements=[j.model_copy(update={"author_name": names.get(j.author)}) for j in judgements]
    )


@app.post(
    "/v1/investigations/{investigation_id}/links/{edge_id}/change",
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def change_link_route(
    investigation: InvestigationEditorDep,
    edge_id: str,
    principal: PrincipalDep,
    body: LinkChangeRequest,
    link_changes: LinkChangesDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> LinkChangeResponse:
    """Change a link's type or details (ADR-080): a supersede, with a required reason, kept in the
    link's history and in the audit stream with the old and new values. The old link is kept in
    the store and replaced in the working set; its notes move to the new one.

    ADR-102: the handling may be raised by an Editor; lowering any part of it is an Author's
    change and needs `confirm_lower`, else 403 or 409 and nothing is written."""
    try:
        await investigations.get_authorized(investigation.id, principal, need=AccessLevel.AUTHOR)
        is_author = True
    except (InvestigationNotFoundError, InsufficientAccessError):
        is_author = False
    result = await link_changes.change(
        investigation.id, edge_id, principal, body, is_author=is_author
    )
    await publish_delta(valkey, investigation.id, result.delta)
    await audit.record(
        principal=principal,
        action="link_change",
        investigation_id=investigation.id,
        resolved_query={
            "edge_id": edge_id,
            "new_edge_id": result.edge.id,
            "before": result.change.before,
            "after": result.change.after,
        },
        result_cardinality=1,
        justification=result.change.reason,
    )
    return result.to_response()


# --- relationship types proposed by analysts (ADR-090) ------------------------------------


@app.get(
    "/v1/investigations/{investigation_id}/link-types",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def case_link_types_route(
    investigation: InvestigationViewerDep, principal: PrincipalDep, link_types: LinkTypesDep
) -> CaseLinkTypesResponse:
    """The types a link in this case may take: the ontology's, and those proposed in the case,
    the cases it was branched from, or for a link the caller can see in it. Not audited, like the
    ontology itself."""
    offered = await link_types.case_types(investigation.id, principal)
    return CaseLinkTypesResponse(
        types=[
            LinkTypeOption(definition=t.definition, proposal_id=t.proposal_id)
            for t in offered.values()
        ]
    )


@app.post(
    "/v1/investigations/{investigation_id}/link-types",
    dependencies=[Depends(require_right(Right.PROPOSE_LINK_TYPE))],
)
async def propose_link_type_route(
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    body: ProposeLinkTypeRequest,
    link_types: LinkTypesDep,
    audit: AuditDep,
) -> LinkTypeProposal:
    """Propose a type when none fits (ADR-090): usable at once in this case, probabilistic, until an
    administrator of the unit decides."""
    proposal = await link_types.propose(
        investigation.id,
        principal,
        name=body.name,
        from_types=body.from_types,
        to_types=body.to_types,
        directed=body.directed,
        colour=body.colour,
        thickness=body.thickness,
        label=body.label,
        reason=body.reason,
    )
    await audit.record(
        principal=principal,
        action="link_type_propose",
        investigation_id=investigation.id,
        resolved_query={"proposal_id": proposal.id, "name": proposal.name},
        result_cardinality=1,
        justification=proposal.reason,
    )
    return proposal


@app.post(
    "/v1/investigations/{investigation_id}/link-types/{proposal_id}/withdraw",
    dependencies=[Depends(require_right(Right.PROPOSE_LINK_TYPE))],
)
async def withdraw_link_type_route(
    investigation: InvestigationEditorDep,
    proposal_id: str,
    principal: PrincipalDep,
    body: LinkTypeDecisionRequest,
    investigations: InvestigationsDep,
    link_types: LinkTypesDep,
    audit: AuditDep,
) -> LinkTypeProposal:
    """Its proposer, or an Author of the case, withdraws a pending proposal of this case."""
    try:
        await investigations.get_authorized(investigation.id, principal, need=AccessLevel.AUTHOR)
        is_author = True
    except (InvestigationNotFoundError, InsufficientAccessError):
        is_author = False
    proposal = await link_types.withdraw(
        investigation.id, proposal_id, principal, reason=body.reason, is_author=is_author
    )
    await audit.record(
        principal=principal,
        action="link_type_withdraw",
        investigation_id=investigation.id,
        resolved_query={"proposal_id": proposal.id, "name": proposal.name},
        result_cardinality=1,
        justification=body.reason,
    )
    return proposal


@app.get("/v1/admin/link-types", dependencies=[Depends(require_right(Right.MANAGE_ONTOLOGY))])
async def list_link_type_proposals_route(
    principal: Annotated[Principal, Depends(require_admin_role)], link_types: LinkTypesDep
) -> LinkTypeProposalList:
    """The administrator's list: every proposal of their own unit, newest first."""
    return LinkTypeProposalList(proposals=await link_types.proposals(principal))


@app.post(
    "/v1/admin/link-types/{proposal_id}/promote",
    dependencies=[Depends(require_right(Right.MANAGE_ONTOLOGY))],
)
async def promote_link_type_route(
    proposal_id: str,
    principal: Annotated[Principal, Depends(require_admin_role)],
    body: PromoteLinkTypeRequest,
    link_types: LinkTypesDep,
    audit: AuditDep,
) -> LinkTypeProposal:
    proposal = await link_types.promote(
        proposal_id, principal, basis=body.basis, reason=body.reason, rename_to=body.rename_to
    )
    await audit.record(
        principal=principal,
        action="link_type_promote",
        investigation_id=proposal.investigation_id,
        resolved_query={
            "proposal_id": proposal.id,
            "name": proposal.reads_as,
            "status": proposal.status.value,
            "basis": body.basis,
        },
        result_cardinality=1,
        justification=body.reason,
    )
    return proposal


@app.post(
    "/v1/admin/link-types/{proposal_id}/reject",
    dependencies=[Depends(require_right(Right.MANAGE_ONTOLOGY))],
)
async def reject_link_type_route(
    proposal_id: str,
    principal: Annotated[Principal, Depends(require_admin_role)],
    body: LinkTypeDecisionRequest,
    link_types: LinkTypesDep,
    audit: AuditDep,
) -> LinkTypeProposal:
    proposal = await link_types.reject(proposal_id, principal, reason=body.reason)
    await audit.record(
        principal=principal,
        action="link_type_reject",
        investigation_id=proposal.investigation_id,
        resolved_query={"proposal_id": proposal.id, "name": proposal.name},
        result_cardinality=1,
        justification=body.reason,
    )
    return proposal


@app.post(
    "/v1/admin/link-types/retire", dependencies=[Depends(require_right(Right.MANAGE_ONTOLOGY))]
)
async def retire_link_type_route(
    principal: Annotated[Principal, Depends(require_admin_role)],
    body: RetireLinkTypeRequest,
    link_types: LinkTypesDep,
    audit: AuditDep,
) -> LinkTypeProposalList:
    """A promoted type no longer offered anywhere; its links stay and read as it."""
    retired = await link_types.retire(body.name, principal, reason=body.reason)
    await audit.record(
        principal=principal,
        action="link_type_retire",
        resolved_query={"name": body.name, "proposal_ids": [p.id for p in retired]},
        result_cardinality=len(retired),
        justification=body.reason,
    )
    return LinkTypeProposalList(proposals=retired)


@app.get(
    "/v1/investigations/{investigation_id}/links/{edge_id}/history",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def link_history_route(
    investigation: InvestigationViewerDep,
    edge_id: str,
    principal: PrincipalDep,
    link_changes: LinkChangesDep,
) -> LinkHistoryResponse:
    """Every change that led to this link, newest first — only to someone who can see the link,
    and a link they cannot see answers as one that does not exist. Not audited, like the other
    case reads here."""
    return await link_changes.history(investigation.id, edge_id, principal)


@app.get(
    "/v1/investigations/{investigation_id}/links/{edge_id}/events",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def list_link_events_route(
    investigation: InvestigationViewerDep,
    edge_id: str,
    principal: PrincipalDep,
    link_events: LinkEventsDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> LinkEventListResponse:
    """The events behind one link (the emails between two addresses, ADR-089), newest first, a
    page at a time with the total — only to someone who can see the link, and a link they cannot
    see answers as one that does not exist. Not audited, like the other case reads here."""
    return await link_events.list(investigation.id, edge_id, principal, offset=offset, limit=limit)


@app.post(
    "/v1/investigations/{investigation_id}/links/{edge_id}/events/{event_id}/extract",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def extract_email_route(
    investigation: InvestigationEditorDep,
    edge_id: str,
    event_id: str,
    body: ExtractEmailRequest,
    principal: PrincipalDep,
    email_extraction: EmailExtractionDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> EmailExtractionResult:
    """Entities from one email behind a link (ADR-089 step 3): the email becomes a Document node
    linked to both addresses, both go into the working set, and the model's findings are stored
    pending for a person to accept. Only to someone who can see the link; Editor, since it
    writes."""
    result = await email_extraction.extract(
        investigation.id, edge_id, event_id, principal, model=body.model, using=body.using
    )
    await publish_delta(valkey, investigation.id, result.delta)
    await audit.record(
        principal=principal,
        action="extract_email",
        investigation_id=investigation.id,
        resolved_query={
            "edge_id": edge_id,
            "event_id": event_id,
            "using": body.using,
            "model": body.model,
        },
        result_cardinality=len(result.candidates),
    )
    return result


@app.get(
    "/v1/investigations/{investigation_id}/documents/{document_id}/reader",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def read_document_route(
    investigation: InvestigationViewerDep,
    document_id: str,
    principal: PrincipalDep,
    document_reader: DocumentReaderDep,
    audit: AuditDep,
) -> DocumentReaderView:
    """A Document's full text to read, with the entities accepted from it marked (ADR-092): only
    to someone who can see the Document in the case; one that cannot be seen answers as one that
    does not exist. Audited, as the Dossier's document read is."""
    view = await document_reader.read(investigation.id, document_id, principal)
    await audit.record(
        principal=principal,
        action="read_document",
        investigation_id=investigation.id,
        resolved_query={"document_id": document_id},
        result_cardinality=len(view.spans),
    )
    return view


@app.post(
    "/v1/investigations/{investigation_id}/documents/{document_id}/designations",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def designate_in_document_route(
    investigation: InvestigationEditorDep,
    document_id: str,
    body: Designation,
    principal: PrincipalDep,
    document_reader: DocumentReaderDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> DesignationResult:
    """Words in a Document marked as an entity by the analyst (ADR-098 decision 5): an asserted
    node of theirs, linked to the Document, onto the canvas. Only on a Document they can read here;
    words not at that place in its text are refused. Editor, since it writes."""
    result = await document_reader.designate(investigation.id, document_id, body, principal)
    await publish_delta(valkey, investigation.id, result.delta)
    await audit.record(
        principal=principal,
        action="designate_in_document",
        investigation_id=investigation.id,
        resolved_query={"document_id": document_id, "entity_type": body.entity_type},
        result_cardinality=1,
    )
    return result


@app.post(
    "/v1/investigations/{investigation_id}/documents",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def upload_document_route(
    investigation: InvestigationEditorDep,
    request: Request,
    principal: PrincipalDep,
    document_content: DocumentContentDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
    name: str = Query(min_length=1),
    classification: str = Query(min_length=1),
    legal_basis: str = Query(min_length=1),
    handling_code: str = Query(default="P", min_length=1),
    holder: str | None = Query(default=None),
) -> DocumentUploadResult:
    """A file added straight to the case (ADR-094 step 3, spec 09 §7): an image, a video or a text
    file, kept in the media store as a Document, held by `holder` if one is named. Like every
    source, it needs a handling marking and a legal basis (spec 09 §2); the marking must be one the
    uploader could read. Audited with the name, size, marking and legal basis, never the
    contents."""
    limit = max_upload_bytes()
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail="That file is larger than the upload limit.")
    try:
        filename = validate_upload_name(name, UPLOAD_CONTENT_EXTENSIONS)
    except UploadRefused as refusal:
        raise HTTPException(
            status_code=_UPLOAD_REFUSAL_STATUS[refusal.code], detail=refusal.message
        ) from refusal
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(
                status_code=413, detail="That file is larger than the upload limit."
            )
    handling = Handling(
        classification=classification,
        handling_code=handling_code,
        originator=principal.org_unit,
        owning_unit=principal.org_unit,
    )
    result = await document_content.upload(
        investigation.id,
        principal,
        name=filename,
        data=bytes(data),
        holder_id=holder,
        handling=handling,
    )
    await publish_delta(valkey, investigation.id, result.delta)
    await audit.record(
        principal=principal,
        action="upload_document",
        investigation_id=investigation.id,
        resolved_query={
            "name": filename,
            "size": len(data),
            "holder": holder,
            "classification": classification,
            "legal_basis": legal_basis,
        },
        result_cardinality=1,
    )
    return result


@app.get(
    "/v1/investigations/{investigation_id}/documents/{document_id}/file",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def document_file_route(
    investigation: InvestigationViewerDep,
    document_id: str,
    principal: PrincipalDep,
    document_content: DocumentContentDep,
    audit: AuditDep,
) -> Response:
    """A held Document's file (an image, a video, kept text), for the reader (ADR-094): only to
    someone who can see the Document in the case; one that cannot be seen answers as missing."""
    data, content_type = await document_content.file(investigation.id, document_id, principal)
    await audit.record(
        principal=principal,
        action="read_document_file",
        investigation_id=investigation.id,
        resolved_query={"document_id": document_id},
        result_cardinality=1,
    )
    return Response(content=data, media_type=content_type)


#: The extensions a picture's name may carry (ADR-105), for the shared name check.
PICTURE_EXTENSIONS = frozenset(f".{ext}" for ext in PICTURE_TYPES)


class PicturesRequest(BaseModel):
    node_ids: list[str] = Field(max_length=MAX_NODES)


@app.put(
    "/v1/investigations/{investigation_id}/nodes/{node_id}/picture",
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def set_entity_picture_route(
    investigation: InvestigationEditorDep,
    node_id: str,
    request: Request,
    principal: PrincipalDep,
    pictures: EntityPicturesDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
    name: str = Query(min_length=1),
    classification: str = Query(min_length=1),
    legal_basis: str = Query(min_length=1),
    handling_code: str = Query(default="P", min_length=1),
) -> PictureSetResponse:
    """One entity's own picture (ADR-105): an image Document that `DEPICTS` it, added as any file
    is (a marking the person could read and a legal basis), replacing the picture they could see
    before, which is kept. Audited with the name, size, marking and legal basis."""
    limit = max_upload_bytes()
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail="That file is larger than the upload limit.")
    try:
        filename = validate_upload_name(name, PICTURE_EXTENSIONS)
    except UploadRefused as refusal:
        raise HTTPException(
            status_code=_UPLOAD_REFUSAL_STATUS[refusal.code], detail=refusal.message
        ) from refusal
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(
                status_code=413, detail="That file is larger than the upload limit."
            )
    handling = Handling(
        classification=classification,
        handling_code=handling_code,
        originator=principal.org_unit,
        owning_unit=principal.org_unit,
    )
    # The service audits `set_entity_picture` itself (ADR-127 Amendment 23), so the seed's path
    # writes the same entry.
    result = await pictures.set(
        investigation.id,
        node_id,
        principal,
        name=filename,
        data=bytes(data),
        handling=handling,
        legal_basis=legal_basis,
    )
    for delta in result.deltas:
        await publish_delta(valkey, investigation.id, delta)
    response = result.to_response()
    return response


@app.delete(
    "/v1/investigations/{investigation_id}/nodes/{node_id}/picture",
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def remove_entity_picture_route(
    investigation: InvestigationEditorDep,
    node_id: str,
    principal: PrincipalDep,
    pictures: EntityPicturesDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> DeltaReplaceEdgeSent:
    """The entity goes back to its type's picture (ADR-105); its own is kept, no longer shown."""
    delta = await pictures.remove(investigation.id, node_id, principal)
    await publish_delta(valkey, investigation.id, delta)
    await audit.record(
        principal=principal,
        action="remove_entity_picture",
        investigation_id=investigation.id,
        resolved_query={"node_id": node_id},
        result_cardinality=1,
    )
    return delta.to_sent()


@app.post(
    "/v1/investigations/{investigation_id}/pictures",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def entity_pictures_route(
    investigation: InvestigationViewerDep,
    body: PicturesRequest,
    principal: PrincipalDep,
    pictures: EntityPicturesDep,
    audit: AuditDep,
) -> list[EntityPicture]:
    """Which of these entities have a picture of their own the caller can see (ADR-105)."""
    found = await pictures.pictures(investigation.id, body.node_ids, principal)
    await audit.record(
        principal=principal,
        action="read_entity_pictures",
        investigation_id=investigation.id,
        resolved_query={"node_ids": len(body.node_ids)},
        result_cardinality=len(found),
    )
    return found


@app.get(
    "/v1/investigations/{investigation_id}/nodes/{node_id}/picture",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def entity_picture_file_route(
    investigation: InvestigationViewerDep,
    node_id: str,
    principal: PrincipalDep,
    pictures: EntityPicturesDep,
    audit: AuditDep,
) -> Response:
    """The entity's picture's file, to someone who can see it; one they cannot answers as none."""
    data, content_type = await pictures.file(investigation.id, node_id, principal)
    await audit.record(
        principal=principal,
        action="read_entity_picture",
        investigation_id=investigation.id,
        resolved_query={"node_id": node_id},
        result_cardinality=1,
    )
    return Response(content=data, media_type=content_type)


class ExtractDocumentRequest(BaseModel):
    """ADR-098: the fast recogniser, the default, or the language model on request."""

    using: Literal["recogniser", "model"] = "recogniser"


@app.post(
    "/v1/investigations/{investigation_id}/documents/{document_id}/extract",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def extract_document_route(
    investigation: InvestigationEditorDep,
    document_id: str,
    principal: PrincipalDep,
    document_content: DocumentContentDep,
    audit: AuditDep,
    body: ExtractDocumentRequest | None = None,
) -> DocumentExtractionResult:
    """Entities from a held Document by its kind (ADR-094): kept text as it is, an image described
    and its text read, a video transcribed. Findings are pending until a person accepts one."""
    using = body.using if body is not None else "recogniser"
    result = await document_content.extract(investigation.id, document_id, principal, using=using)
    await audit.record(
        principal=principal,
        action="extract_document",
        investigation_id=investigation.id,
        resolved_query={"document_id": document_id},
        result_cardinality=len(result.candidates),
    )
    return result


@app.post(
    "/v1/investigations/{investigation_id}/documents/{document_id}/candidates/{candidate_id}/accept",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def accept_document_candidate_route(
    investigation: InvestigationEditorDep,
    document_id: str,
    candidate_id: str,
    principal: PrincipalDep,
    document_content: DocumentContentDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> DocumentAcceptResult:
    """Accepts one finding from a held Document: an inferred node linked to it (ADR-094)."""
    result = await document_content.accept(investigation.id, document_id, candidate_id, principal)
    await publish_delta(valkey, investigation.id, result.delta)
    await audit.record(
        principal=principal,
        action="accept_document_candidate",
        investigation_id=investigation.id,
        resolved_query={"document_id": document_id, "candidate_id": candidate_id},
        result_cardinality=1,
    )
    return result


@app.post(
    "/v1/investigations/{investigation_id}/documents/{document_id}/candidates/accept",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def accept_document_candidates_route(
    investigation: InvestigationEditorDep,
    document_id: str,
    body: review_module.BulkAcceptRequest,
    principal: PrincipalDep,
    document_content: DocumentContentDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> DocumentBulkAcceptResult:
    """ADR-108 ruling Q1's bulk accept: the enumerated findings a person reviewed, accepted as one
    decision — each written `inferred` (rule 5), each refusal reported per item in words, and
    never a filter or a confidence threshold."""
    result = await document_content.accept_all(
        investigation.id, document_id, body.candidate_ids, principal
    )
    for outcome in result.accepted:
        await publish_delta(valkey, investigation.id, outcome.delta)
    await audit.record(
        principal=principal,
        action="accept_document_candidates",
        investigation_id=investigation.id,
        resolved_query={
            "document_id": document_id,
            "candidate_ids": body.candidate_ids,
            "refused": [r.candidate_id for r in result.refusals],
        },
        result_cardinality=len(result.accepted),
    )
    return result


@app.post(
    "/v1/investigations/{investigation_id}/documents/{document_id}/candidates/{candidate_id}/reject",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def reject_document_candidate_route(
    investigation: InvestigationEditorDep,
    document_id: str,
    candidate_id: str,
    principal: PrincipalDep,
    document_content: DocumentContentDep,
    audit: AuditDep,
) -> RejectedResponse:
    """Rejects one finding from a held Document (owner, 6 October 2026): nothing is written."""
    await document_content.reject(investigation.id, document_id, candidate_id, principal)
    await audit.record(
        principal=principal,
        action="reject_document_candidate",
        investigation_id=investigation.id,
        resolved_query={"document_id": document_id, "candidate_id": candidate_id},
        result_cardinality=1,
    )
    return RejectedResponse()


@app.post(
    "/v1/investigations/{investigation_id}/questions",
    dependencies=[Depends(require_right(Right.ASK_MODEL))],
)
async def ask_question_route(
    investigation: InvestigationEditorDep,
    body: AskRequest,
    principal: PrincipalDep,
    questions: QuestionsDep,
    audit: AuditDep,
) -> QuestionAnswer:
    """Asks the model about the case's Documents and graph facts the analyst can see (ADR-098
    decision 4, ADR-129 decision 1): the selection and one link around it, or the whole view. What
    it proposes is pending until a person accepts it."""
    answer = await questions.ask(
        investigation.id,
        body.question,
        principal,
        selected_node_ids=body.selected_node_ids,
        selected_link_ids=body.selected_link_ids,
        window=body.window,
    )
    await audit.record(
        principal=principal,
        action="ask_question",
        investigation_id=investigation.id,
        resolved_query={"question_id": answer.id},
        result_cardinality=len(answer.candidates),
    )
    return answer


@app.get(
    "/v1/investigations/{investigation_id}/questions",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def list_questions_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    questions: QuestionsDep,
    principal_names: PrincipalNamesDep,
) -> list[QuestionAnswer]:
    """The case's questions and answers, as this reader may see them (ADR-098 decision 4)."""
    history = await questions.history(investigation.id, principal)
    names = await principal_names.display_names(q.author for q in history)
    return [q.model_copy(update={"author_name": names.get(q.author)}) for q in history]


@app.post(
    "/v1/investigations/{investigation_id}/questions/candidates/{candidate_id}/accept",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def accept_question_candidate_route(
    investigation: InvestigationEditorDep,
    candidate_id: str,
    principal: PrincipalDep,
    questions: QuestionsDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> QuestionAccepted:
    """Accepts one of the model's proposals: an inferred node linked to its Document."""
    result = await questions.accept(investigation.id, candidate_id, principal)
    await publish_delta(valkey, investigation.id, result.delta)
    await audit.record(
        principal=principal,
        action="accept_question_candidate",
        investigation_id=investigation.id,
        resolved_query={"candidate_id": candidate_id},
        result_cardinality=1,
    )
    return result


@app.post(
    "/v1/investigations/{investigation_id}/questions/candidates/{candidate_id}/reject",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def reject_question_candidate_route(
    investigation: InvestigationEditorDep,
    candidate_id: str,
    principal: PrincipalDep,
    questions: QuestionsDep,
    audit: AuditDep,
) -> RejectedResponse:
    """Rejects one of the model's proposals: nothing is written."""
    await questions.reject(investigation.id, candidate_id, principal)
    await audit.record(
        principal=principal,
        action="reject_question_candidate",
        investigation_id=investigation.id,
        resolved_query={"candidate_id": candidate_id},
        result_cardinality=1,
    )
    return RejectedResponse()


class EmailDocumentsRequest(BaseModel):
    """The timeline's brushed window (ADR-092); left out, every email on the link."""

    window: Interval | None = None


@app.post(
    "/v1/investigations/{investigation_id}/links/{edge_id}/events/documents",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def show_emails_as_documents_route(
    investigation: InvestigationEditorDep,
    edge_id: str,
    body: EmailDocumentsRequest,
    principal: PrincipalDep,
    email_extraction: EmailExtractionDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> EmailDocumentsResult:
    """The emails behind a link onto the canvas (ADR-092): each one inside the window written as a
    Document linked to both addresses, all into the working set, or none and `limit_exceeded` past
    the cap. Only to someone who can see the link; Editor, since it writes."""
    result = await email_extraction.show_as_documents(
        investigation.id, edge_id, principal, window=body.window
    )
    await publish_delta(valkey, investigation.id, result.delta)
    await audit.record(
        principal=principal,
        action="show_emails_as_documents",
        investigation_id=investigation.id,
        resolved_query={"edge_id": edge_id, "window": body.model_dump(mode="json")["window"]},
        result_cardinality=result.written,
    )
    return result


@app.post(
    "/v1/investigations/{investigation_id}/links/{edge_id}/events/{event_id}/candidates/{candidate_id}/accept",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def accept_email_candidate_route(
    investigation: InvestigationEditorDep,
    edge_id: str,
    event_id: str,
    candidate_id: str,
    principal: PrincipalDep,
    email_extraction: EmailExtractionDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> EmailAcceptResult:
    """Accepts one of an email's candidates (ADR-089 step 3): an inferred node and its
    MENTIONED_IN link to the email's Document, both into the working set. One candidate per call,
    as the review queue has it."""
    result = await email_extraction.accept(
        investigation.id, edge_id, event_id, candidate_id, principal
    )
    await publish_delta(valkey, investigation.id, result.delta)
    await audit.record(
        principal=principal,
        action="accept_email_candidate",
        investigation_id=investigation.id,
        resolved_query={"edge_id": edge_id, "event_id": event_id, "candidate_id": candidate_id},
        result_cardinality=1,
    )
    return result


@app.post(
    "/v1/investigations/{investigation_id}/links/{edge_id}/events/{event_id}/candidates/{candidate_id}/reject",
    dependencies=[Depends(require_right(Right.EXTRACT_FILES))],
)
async def reject_email_candidate_route(
    investigation: InvestigationEditorDep,
    edge_id: str,
    event_id: str,
    candidate_id: str,
    principal: PrincipalDep,
    email_extraction: EmailExtractionDep,
    audit: AuditDep,
) -> RejectedResponse:
    """Rejects one of an email's findings (owner, 6 October 2026): marked rejected, nothing is
    written. Only through the email it was found in, by someone who can see the link."""
    await email_extraction.reject(investigation.id, edge_id, event_id, candidate_id, principal)
    await audit.record(
        principal=principal,
        action="reject_email_candidate",
        investigation_id=investigation.id,
        resolved_query={"edge_id": edge_id, "event_id": event_id, "candidate_id": candidate_id},
        result_cardinality=1,
    )
    return RejectedResponse()


# --- the case brief (ADR-128 decision 3) --------------------------------------------------------
#
# Read at Viewer, every edit at Author (the case's own level, and the `share_case` right the Author
# role holds, as the case's datasets and domain models are). The service's own docstring has the
# rules: rule 3 (an attachment the reader may not read is not there at all), rule 5 (only
# `set_brief_requirement_status_route` sets a status), rule 2 (a limit is refused by name).
# Each edit is audited by id, never by text, and is a History step except an attach or a detach: a
# step is shown to every reader, and one for an attachment they may not read would be a trace of it.


@app.get(
    "/v1/investigations/{investigation_id}/brief",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def get_case_brief_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    case_brief: CaseBriefDep,
) -> CaseBrief:
    """The brief as this reader may read it. Not audited, like the other case reads here."""
    return await case_brief.read(investigation.id, principal)


@app.put(
    "/v1/investigations/{investigation_id}/brief/priority",
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def set_brief_priority_route(
    investigation: InvestigationAuthorDep,
    body: BriefTextBody,
    principal: PrincipalDep,
    case_brief: CaseBriefDep,
    history: HistoryDep,
    audit: AuditDep,
) -> CaseBrief:
    brief = await case_brief.set_priority(investigation.id, principal, body.text)
    await audit.record(
        principal=principal,
        action="case_brief_set_priority",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=1,
    )
    await _record_brief_edit(history, investigation.id, principal)
    return brief


@app.post(
    "/v1/investigations/{investigation_id}/brief/requirements",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def add_brief_requirement_route(
    investigation: InvestigationAuthorDep,
    body: BriefTextBody,
    principal: PrincipalDep,
    case_brief: CaseBriefDep,
    history: HistoryDep,
    audit: AuditDep,
) -> CaseBrief:
    brief = await case_brief.add_requirement(investigation.id, principal, body.text)
    await audit.record(
        principal=principal,
        action="case_brief_add_requirement",
        investigation_id=investigation.id,
        resolved_query={"requirement_id": brief.requirements[-1].id},
        result_cardinality=1,
    )
    await _record_brief_edit(history, investigation.id, principal)
    return brief


@app.put(
    "/v1/investigations/{investigation_id}/brief/requirements/{requirement_id}",
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def edit_brief_requirement_route(
    investigation: InvestigationAuthorDep,
    requirement_id: str,
    body: BriefTextBody,
    principal: PrincipalDep,
    case_brief: CaseBriefDep,
    history: HistoryDep,
    audit: AuditDep,
) -> CaseBrief:
    brief = await case_brief.edit_requirement(
        investigation.id, requirement_id, principal, body.text
    )
    await audit.record(
        principal=principal,
        action="case_brief_edit_requirement",
        investigation_id=investigation.id,
        resolved_query={"requirement_id": requirement_id},
        result_cardinality=1,
    )
    await _record_brief_edit(history, investigation.id, principal)
    return brief


@app.delete(
    "/v1/investigations/{investigation_id}/brief/requirements/{requirement_id}",
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def remove_brief_requirement_route(
    investigation: InvestigationAuthorDep,
    requirement_id: str,
    principal: PrincipalDep,
    case_brief: CaseBriefDep,
    history: HistoryDep,
    audit: AuditDep,
) -> CaseBrief:
    brief = await case_brief.remove_requirement(investigation.id, requirement_id, principal)
    await audit.record(
        principal=principal,
        action="case_brief_remove_requirement",
        investigation_id=investigation.id,
        resolved_query={"requirement_id": requirement_id},
        result_cardinality=1,
    )
    await _record_brief_edit(history, investigation.id, principal)
    return brief


@app.put(
    "/v1/investigations/{investigation_id}/brief/requirements/{requirement_id}/status",
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def set_brief_requirement_status_route(
    investigation: InvestigationAuthorDep,
    requirement_id: str,
    body: BriefStatusBody,
    principal: PrincipalDep,
    case_brief: CaseBriefDep,
    history: HistoryDep,
    audit: AuditDep,
) -> CaseBrief:
    """Rule 5: the one route that marks a requirement answered, and it is a person's request. No
    model path reaches it or the transition under it (`test_case_brief_status.py`)."""
    brief = await case_brief.set_status(investigation.id, requirement_id, principal, body.status)
    await audit.record(
        principal=principal,
        action="case_brief_set_status",
        investigation_id=investigation.id,
        resolved_query={"requirement_id": requirement_id, "status": body.status},
        result_cardinality=1,
    )
    await _record_brief_edit(history, investigation.id, principal)
    return brief


@app.post(
    "/v1/investigations/{investigation_id}/brief/requirements/{requirement_id}/attachments",
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def attach_to_brief_requirement_route(
    investigation: InvestigationAuthorDep,
    requirement_id: str,
    body: BriefAttachmentBody,
    principal: PrincipalDep,
    case_brief: CaseBriefDep,
    audit: AuditDep,
) -> CaseBrief:
    """No History step (see above): the audit records it, which no reader sees."""
    brief = await case_brief.attach(investigation.id, requirement_id, principal, body.kind, body.id)
    await audit.record(
        principal=principal,
        action="case_brief_attach",
        investigation_id=investigation.id,
        resolved_query={"requirement_id": requirement_id, "kind": body.kind, "id": body.id},
        result_cardinality=1,
    )
    return brief


@app.delete(
    "/v1/investigations/{investigation_id}/brief/requirements/{requirement_id}"
    "/attachments/{kind}/{attachment_id}",
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def detach_from_brief_requirement_route(
    investigation: InvestigationAuthorDep,
    requirement_id: str,
    kind: AttachmentKind,
    attachment_id: str,
    principal: PrincipalDep,
    case_brief: CaseBriefDep,
    audit: AuditDep,
) -> CaseBrief:
    brief = await case_brief.detach(
        investigation.id, requirement_id, principal, kind, attachment_id
    )
    await audit.record(
        principal=principal,
        action="case_brief_detach",
        investigation_id=investigation.id,
        resolved_query={"requirement_id": requirement_id, "kind": kind, "id": attachment_id},
        result_cardinality=1,
    )
    return brief


@app.get(
    "/v1/investigations/{investigation_id}/links/{edge_id}/notes",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def list_link_notes_route(
    investigation: InvestigationViewerDep,
    edge_id: str,
    principal: PrincipalDep,
    link_notes: LinkNotesDep,
    principal_names: PrincipalNamesDep,
) -> LinkNoteListResponse:
    """Notes on one link, newest first — only to someone who can see the link
    (`link_notes.py`'s module docstring). Not audited, like the other case reads here."""
    notes = await link_notes.list(investigation.id, edge_id, principal)
    names = await principal_names.display_names(n.author for n in notes)
    return LinkNoteListResponse(
        notes=[n.model_copy(update={"author_name": names.get(n.author)}) for n in notes]
    )


@app.post(
    "/v1/investigations/{investigation_id}/links/{edge_id}/notes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def add_link_note_route(
    investigation: InvestigationEditorDep,
    edge_id: str,
    principal: PrincipalDep,
    body: LinkNoteBody,
    link_notes: LinkNotesDep,
    audit: AuditDep,
) -> LinkNote:
    note = await link_notes.add(investigation.id, edge_id, principal, body.body)
    await audit.record(
        principal=principal,
        action="link_note_add",
        investigation_id=investigation.id,
        resolved_query={"edge_id": edge_id, "note_id": note.id},
        result_cardinality=1,
    )
    return note


@app.put(
    "/v1/investigations/{investigation_id}/links/{edge_id}/notes/{note_id}",
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def edit_link_note_route(
    investigation: InvestigationEditorDep,
    edge_id: str,
    note_id: str,
    principal: PrincipalDep,
    body: LinkNoteBody,
    link_notes: LinkNotesDep,
    audit: AuditDep,
) -> LinkNote:
    note = await link_notes.edit(investigation.id, edge_id, note_id, principal, body.body)
    await audit.record(
        principal=principal,
        action="link_note_edit",
        investigation_id=investigation.id,
        resolved_query={"edge_id": edge_id, "note_id": note.id},
        result_cardinality=1,
    )
    return note


@app.delete(
    "/v1/investigations/{investigation_id}/links/{edge_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def remove_link_note_route(
    investigation: InvestigationEditorDep,
    edge_id: str,
    note_id: str,
    principal: PrincipalDep,
    link_notes: LinkNotesDep,
    audit: AuditDep,
) -> Response:
    await link_notes.remove(investigation.id, edge_id, note_id, principal)
    await audit.record(
        principal=principal,
        action="link_note_remove",
        investigation_id=investigation.id,
        resolved_query={"edge_id": edge_id, "note_id": note_id},
        result_cardinality=1,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/v1/investigations/{investigation_id}/gaps",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def save_gap_route(
    investigation: InvestigationEditorDep,
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


@app.get(
    "/v1/investigations/{investigation_id}/gaps",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def list_gaps_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    gaps_store: GapsStoreDep,
    principal_names: PrincipalNamesDep,
) -> IntelligenceGapListResponse:
    gaps = await gaps_store.list_for_investigation(investigation.id, principal)
    names = await principal_names.display_names(g.raised_by for g in gaps)
    return IntelligenceGapListResponse(
        gaps=[g.model_copy(update={"raised_by_name": names.get(g.raised_by)}) for g in gaps]
    )


@app.post(
    "/v1/investigations/{investigation_id}/assumptions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def save_assumption_route(
    investigation: InvestigationEditorDep,
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


@app.get(
    "/v1/investigations/{investigation_id}/assumptions",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def list_assumptions_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    assumptions_store: AssumptionsStoreDep,
) -> AssumptionListResponse:
    return AssumptionListResponse(
        assumptions=await assumptions_store.list_for_investigation(investigation.id, principal)
    )


@app.post(
    "/v1/investigations/{investigation_id}/export",
    dependencies=[Depends(require_right(Right.EXPORT))],
)
async def submit_export_route(
    investigation: InvestigationEditorDep,
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
    (`services/api/export.py::submit_export`'s own docstring). `body` carries no `withheld`
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


@app.get("/v1/exports", dependencies=[Depends(require_right(Right.READ_EXPORT_LEDGER))])
async def list_exports_route(
    principal: PrincipalDep, export_ledger: ExportLedgerDep
) -> ExportLedgerListResponse:
    """`06_DECISIONS.md` ADR-047's own Gap 2 — the compliance-facing export ledger's own read
    path. `ExportLedgerStore.list_all` itself raises `ComplianceRoleRequiredError` for a principal
    without the role; deliberately no `AuthorizedInvestigationDep` here at all, since this route's
    entire point is a listing that needs no per-investigation access."""
    return ExportLedgerListResponse(entries=await export_ledger.list_all(principal))


@app.post(
    "/v1/investigations/{investigation_id}/monitors",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.KEEP_WATCHES))],
)
async def create_monitor_route(
    investigation: InvestigationEditorDep,
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
    saved = await patterns_store.get_authorized(body.pattern_id, principal)
    # ADR-099 Amendment 3: the monitor watches its pattern's dataset (the case may read several).
    owner = (
        principal.model_copy(update={"datasets": [saved.dataset_id]})
        if saved.dataset_id is not None
        else principal
    )
    monitor = await monitors_store.create(owner, pattern_id=body.pattern_id)
    await audit.record(
        principal=principal,
        action="monitors_create",
        resolved_query={"monitor_id": monitor.id},
        result_cardinality=1,
    )
    return monitor


@app.get(
    "/v1/investigations/{investigation_id}/monitors",
    dependencies=[Depends(require_right(Right.KEEP_WATCHES))],
)
async def list_monitors_route(
    investigation: InvestigationViewerDep, principal: PrincipalDep, monitors_store: MonitorsStoreDep
) -> MonitorList:
    return MonitorList(monitors=await monitors_store.list_authorized(principal))


@app.get(
    "/v1/investigations/{investigation_id}/alerts",
    dependencies=[Depends(require_right(Right.KEEP_WATCHES))],
)
async def list_alerts_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    alerts_store: AlertsStoreDep,
    graph: GraphDep,
) -> AlertList:
    """ADR-099 Amendment 3: the alerts of the case's datasets, read as the case reads."""
    rows = await alerts_store.list_authorized(principal)
    return AlertList(alerts=[await alert_to_view(a, principal, graph) for a in rows])


@app.get(
    "/v1/investigations/{investigation_id}/alerts/{alert_id}",
    dependencies=[Depends(require_right(Right.KEEP_WATCHES))],
)
async def get_alert_route(
    investigation: InvestigationViewerDep,
    alert_id: str,
    principal: PrincipalDep,
    alerts_store: AlertsStoreDep,
    graph: GraphDep,
) -> AlertView:
    alert = await alerts_store.get_authorized(alert_id, principal)
    return await alert_to_view(alert, principal, graph)


@app.post(
    "/v1/investigations/{investigation_id}/alerts/{alert_id}/jump",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.KEEP_WATCHES))],
)
async def jump_alert_route(
    investigation: InvestigationEditorDep,
    alert_id: str,
    principal: PrincipalDep,
    alerts_store: AlertsStoreDep,
    graph: GraphDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: ValkeyDep,
    datasets: DatasetsDep,
) -> AlertJumpResult:
    """`08_ACCEPTANCE_SCENARIOS.md` B14: "The new working set contains the alert's entities and a
    link to the originating investigation." The link is `branch.branched_from` — the identical
    mechanism `branch_investigation` already uses (`investigations.create(principal,
    branched_from=...)`), not new investigation-linking infrastructure. `alert.investigation_id`
    may be `None` (the resolution trigger's own producer carries no single investigation) — the
    branch still succeeds, simply unlinked, disclosed via `Investigation.branched_from` being
    `None` rather than silently pointed at a wrong investigation."""
    alert = await alerts_store.get_authorized(alert_id, principal)
    # ADR-126: the packs are those of the route's own authorised case, never of
    # `alert.investigation_id`, which the jumper is not authorised against and which may be None.
    branch = await investigations.create(
        principal,
        name=f"Opened from alert {alert.id}",
        branched_from=alert.investigation_id,
        domains=investigation.domains_to_inherit(),
    )
    # ADR-099: the new case reads the alert's dataset; with none, what the alert's case reads; with
    # neither, a dataset of its own.
    if alert.dataset_id is not None:
        await datasets.set_for_case(branch.id, [alert.dataset_id], principal)
    elif alert.investigation_id is not None:
        await datasets.copy_case(alert.investigation_id, branch.id)
    if not await datasets.ids_of_case(branch.id):
        own = await datasets.create(principal, branch.name, suffix_if_taken=True)
        await datasets.set_for_case(branch.id, [own.id], principal)
    principal = await scope_to_case(principal, branch.id, datasets)
    nodes = await fetch_jumpable_referents(alert, principal=principal, graph=graph)
    outcome = await working_set.seed(branch.id, nodes, [], principal)
    await publish_delta(valkey, branch.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        branch.id,
        seq=outcome.delta.seq,
        label=OPENED_FROM_ALERT,
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="alerts_jump",
        investigation_id=branch.id,
        resolved_query={"alert_id": alert.id, "from_investigation_id": alert.investigation_id},
        result_cardinality=len(nodes),
    )
    return AlertJumpResult(investigation=branch, seeded_count=len(nodes))


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


@app.post(
    "/v1/investigations/{investigation_id}/paths",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def paths_route(
    investigation: InvestigationViewerDep,
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


# --- Find connections (ADR-116) ----------------------------------------------
#
# Under the case, as the pathfinder is: the case's datasets bound what is walked (ADR-099), and the
# graph store filters each step for the reader (rule 3). No preview: at most ten routes come back
# for a degree, and more than that is said, not hidden (rule 2).


@app.post(
    "/v1/investigations/{investigation_id}/connections",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def connections_route(
    investigation: InvestigationViewerDep,
    req: ConnectionsRequest,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
) -> Connections:
    found = await connections_module.find_connections(graph, req, principal)
    await audit.record(
        principal=principal,
        action="connections",
        investigation_id=investigation.id,
        resolved_query=req.model_dump(mode="json"),
        result_cardinality=len(found.paths),
    )
    return found


# --- the corpus-wide resolution trigger (06_DECISIONS.md ADR-025) -------------


@app.post(
    "/v1/resolution/{entity_type}/run",
    dependencies=[Depends(require_right(Right.RESOLVE_ENTITIES))],
)
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


#: The liveness body, as a module constant rather than a literal in the handler, so the test that
#: compares the anonymous and authenticated responses byte for byte has one thing to compare
#: against and a future edit cannot change one caller's answer without changing the other's.
LIVENESS_BODY: Final[dict[str, str]] = {"status": "ok"}


@app.get("/v1/readiness")
async def readiness_route(principal: PrincipalDep) -> readiness_module.Readiness:
    """Whether the deployment's models are present (ADR-095 Amendment 2): any signed-in principal,
    no case, no store. The deployment does not wait for its models at start; this says when they
    have arrived."""
    del principal
    return await readiness_module.deployment_readiness()


@app.get("/healthz")
async def liveness_route() -> dict[str, str]:
    """Is this process up — `03_CONDUIT_MIDDLEWARE.md` §3.0, the owner's decision of 24 September
    2026.

    **Unauthenticated, and outside `/v1` because it is not part of the API surface a client uses.**
    It exists so an orchestrator can tell a started process from a healthy one: `docker compose up
    --wait` has nothing to wait on without it, which is what stopped the scripted deploy reaching
    its own exit criterion (`06_DECISIONS.md` ADR-049 Stage 2 §3).

    **No principal, and deliberately no `PrincipalDep`.** Every other route on this app takes one;
    this is the single exception, and it is the exception because requiring a token to answer "is
    the process alive" makes liveness depend on the identity provider being reachable — which
    inverts the whole point, since an unreachable IdP is one of the conditions an operator most
    needs liveness to survive.

    **It touches no store and says nothing else.** No version, no uptime, no component status, no
    counts. §6's own reasoning applies in full: an unauthenticated endpoint reporting which stores
    are reachable discloses the deployment's internal topology to an unauthenticated caller, and one
    reporting counts is a count leak wearing a friendly name. Touching no store also means the
    answer stays true when every store is down — exactly when an orchestrator needs to tell "the
    process is up, its dependencies are not" from "the process is gone".

    **Readiness is a different question and stays authenticated.** Nothing here should grow into it.
    """
    return LIVENESS_BODY


@app.get("/v1/ontology")
async def get_ontology_route(principal: PrincipalDep, ontology: OntologyDep) -> OntologySchema:
    """The Glass's channel/shape mapping (`spec/02_GLASS_FRONTEND.md` §4:
    "Hue is entity type; shape is entity type too") comes from here, not a
    hardcoded copy of `packages/ontology/default.yaml` in the frontend —
    the ontology already carries `EntityTypeDef.channel`/`.shape` per type,
    and duplicating that mapping client-side would drift the moment a
    deployment's ontology changes. Authenticated like every other route,
    but not investigation-scoped and not audited: this is deployment-wide
    schema *metadata* (entity/edge type names, channels, shapes,
    identifiers) — never a node, a property value or a count — the same
    category of thing `principal_may_view` was never meant to gate.

    The types proposed and promoted by analysts are in it once promoted (ADR-090); the labels a
    proposal's links are stored under, and their aliases, are not (`public_ontology`)."""
    return public_ontology(ontology)


@app.get("/v1/map/providers")
async def get_map_providers_route(
    principal: PrincipalDep, map_config: MapConfigDep
) -> PublicMapConfig:
    """The Glass's layer control (`spec/02_GLASS_FRONTEND.md` §3.5: "Layer
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


@app.get("/v1/map/local-source/{provider_id}")
async def get_map_local_source_route(
    provider_id: str,
    principal: PrincipalDep,
    map_config: MapConfigDep,
) -> Response:
    """Serves a tier-1/2 provider's local `file://` PMTiles source over HTTP —
    Stage 3a's own rehearsal finding, 23 September 2026: a browser cannot fetch a `file://` URI
    at all, so `mapconfig_loader.public_view()` now rewrites that source to this route rather
    than handing the on-disk path straight to the Glass. `spec/02_GLASS_FRONTEND.md` and
    `spec/05_DEPLOYMENT.md` do not name which tier serves tier-1/2 tiles over HTTP (checked
    directly, not assumed silent) — this route is the smallest correct option, since the Conduit
    is already the one exposed service (`05_DEPLOYMENT.md` §2.4's guard table) serving
    `/v1/map/providers` and the tier-3/4 tile proxy right above; recorded as a proposal in
    `02_GLASS_FRONTEND.md`, not settled spec.

    `FileResponse` answers a byte-`Range` request itself (Starlette's own `accept-ranges: bytes`
    handling) — required, not a nicety: the `pmtiles` JS protocol handler reads its own directory
    and tile blocks via ranged fetches against this single file, never downloading it whole.

    A missing file gets a 404 naming the gap rather than a stack trace or a silent empty
    response — `apps/workspace/src/map/basemapAvailability.ts`'s own preflight check depends on
    this exact status code and `detail` shape to render "basemap not built" instead of a blank
    map (the rehearsal's other finding for this same defect)."""
    provider = next((p for p in map_config.providers if p.id == provider_id), None)
    if provider is None or provider.source is None or not provider.source.startswith("file://"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown local source provider"
        )
    path = Path(provider.source.removeprefix("file://"))
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"basemap not built — {path} does not exist yet; see scripts/build_local_basemap.py"
            ),
        )
    return FileResponse(path, media_type="application/vnd.pmtiles")


# --- geospatial admin actions (round 09) ----------------------------------
#
# `harness/geospatial.py`'s own docstring has the full account of why these live here rather
# than in the harness image: `build_local_basemap` needs a live `GraphPort` transaction, and
# both it and `verify_map` import `services`/`adapters` modules the harness image deliberately
# does not carry. Admin-role-gated (`require_admin_role`, same role name and audience check R2's
# own harness `/admin` already uses) — never reachable from the setup-mode Geospatial screen,
# only from the post-Launch admin console, which authenticates against this same Conduit.


class BuildBasemapRequest(BaseModel):
    region: str
    output_dir: str
    planetiler_jar_path: str


class BuildBasemapResult(BaseModel):
    pmtiles_path: str
    nodes_created: int
    nodes_referenced: int
    rejections: int


@app.post(
    "/v1/admin/geospatial/build-basemap",
    dependencies=[Depends(require_right(Right.MANAGE_GEOSPATIAL))],
)
async def build_basemap_route(
    body: BuildBasemapRequest,
    principal: Annotated[Principal, Depends(require_admin_role)],
    graph: GraphDep,
    ontology: OntologyDep,
    config: ConfigDep,
    audit: AuditDep,
) -> StreamingResponse:
    """Streamed the same way Launch is (`harness/webapp.py`'s own `_launch_events`) — one line of
    real progress at a time, `build_local_basemap`'s own `progress` callback bridged into an SSE
    generator via a queue, since the work itself is an in-process async call here, never a
    subprocess (the Conduit already holds the one live `GraphPort` connection this needs)."""
    if body.region not in GEOFABRIK_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{body.region!r} is not a known Geofabrik region: {sorted(GEOFABRIK_REGIONS)}",
        )

    async def _events() -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue()

        def _progress(line: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, line)

        async def _run_build() -> tuple[BasemapBuildResult | None, BaseException | None]:
            tx = await graph.begin_transaction()
            try:
                result = await build_local_basemap(
                    region=body.region,
                    output_dir=Path(body.output_dir),
                    planetiler_jar_path=Path(body.planetiler_jar_path),
                    osprey_config_path=Path(config.osprey_config_path),
                    graph=graph,
                    ontology=ontology,
                    tx=tx,
                    principal=principal,
                    progress=_progress,
                )
            except BaseException as exc:  # noqa: BLE001 - reported to the caller, not swallowed
                await graph.rollback_transaction(tx)
                return None, exc
            await graph.commit_transaction(tx)
            return result, None

        task = asyncio.ensure_future(_run_build())
        while True:
            get_line = asyncio.ensure_future(queue.get())
            done, _pending = await asyncio.wait(
                {task, get_line}, return_when=asyncio.FIRST_COMPLETED
            )
            if get_line in done:
                yield f"data: {json.dumps({'line': get_line.result()})}\n\n".encode()
                continue
            get_line.cancel()
            break
        # Drain whatever progress arrived after the build task itself finished but before this
        # loop's own last `queue.get()` was scheduled — a real race the `asyncio.wait` above
        # cannot close on its own, found writing this route's own first test.
        while not queue.empty():
            yield f"data: {json.dumps({'line': queue.get_nowait()})}\n\n".encode()

        result, error = task.result()
        if error is not None:
            await audit.record(
                principal=principal,
                action="geospatial_build_basemap",
                resolved_query={"region": body.region},
                result_cardinality=0,
            )
            yield (
                f"event: complete\ndata: {json.dumps({'returncode': 1, 'error': str(error)})}\n\n"
            ).encode()
            return
        assert result is not None
        await audit.record(
            principal=principal,
            action="geospatial_build_basemap",
            resolved_query={"region": body.region},
            result_cardinality=1,
        )
        payload = BuildBasemapResult(
            pmtiles_path=str(result.pmtiles_path),
            nodes_created=result.gazetteer_report.nodes_created,
            nodes_referenced=result.gazetteer_report.nodes_referenced,
            rejections=len(result.gazetteer_report.rejections),
        )
        yield (
            f"event: complete\ndata: "
            f"{json.dumps({'returncode': 0, 'result': payload.model_dump()})}\n\n"
        ).encode()

    return StreamingResponse(_events(), media_type="text/event-stream")


class VerifyMapIssue(BaseModel):
    provider_id: str
    check: str
    detail: str


class VerifyMapResult(BaseModel):
    passed: bool
    issues: list[VerifyMapIssue]


@app.post(
    "/v1/admin/geospatial/verify", dependencies=[Depends(require_right(Right.MANAGE_GEOSPATIAL))]
)
async def verify_map_route(
    principal: Annotated[Principal, Depends(require_admin_role)],
    map_config: MapConfigDep,
    audit: AuditDep,
) -> VerifyMapResult:
    """Fast — a handful of in-memory/attribution checks and, for a tier-4 provider only, one live
    capability probe (`check_crs_and_zoom`) — no progress stream needed, unlike the basemap build
    above."""
    report = await verify_map(map_config)
    await audit.record(
        principal=principal,
        action="geospatial_verify_map",
        resolved_query={"provider_count": len(map_config.providers)},
        result_cardinality=len(report.issues),
    )
    return VerifyMapResult(
        passed=report.passed,
        issues=[
            VerifyMapIssue(provider_id=i.provider_id, check=i.check, detail=i.detail)
            for i in report.issues
        ],
    )


# --- analytics -----------------------------------------------------------
#
# Global routes, `EventFilter.investigation_scope` carried in the request
# body rather than the URL path — mirroring `/v1/search`'s own existing
# precedent (also global, also investigation data scoped via the body, not
# nested under `/v1/investigations/{id}/...` the way `/expand`/`/sites` are).
# Audited like `/v1/search`, since these read investigation event data —
# not deployment-wide metadata the way `/v1/ontology`/`/v1/map/providers`
# are.


async def _case_event_filter(
    event_filter: EventFilter,
    principal: Principal,
    investigations: InvestigationStore,
    audit: AuditWriter,
    working_set: WorkingSetService,
) -> EventFilter:
    """The filter a body-scoped analytics read runs with (ADR-084 Amendment 2). The case in the
    body is gated at Viewer exactly as a case in a path is, so a case the account cannot see
    answers 404 and reads nothing. Whatever `inherited` the caller sent is discarded; on a branch it
    is set to the visible parents' events on the links the branch holds."""
    case = await _authorize(
        event_filter.investigation_scope, principal, investigations, audit, AccessLevel.VIEWER
    )
    ancestors = await visible_ancestors(investigations, case, principal)
    if not ancestors:
        return with_inherited(event_filter, [], [], window=None)
    _nodes, edges = await working_set.current_membership(case.id)
    return with_inherited(
        event_filter, ancestors, [e.id for e in edges], window=case.branch_window
    )


class GeometriesRequest(BaseModel):
    geometry_refs: list[str]


@app.post("/v1/analytics/histogram", dependencies=[Depends(require_right(Right.INVESTIGATE))])
async def histogram_route(
    body: HistogramRequest,
    principal: PrincipalDep,
    analytics: AnalyticsDep,
    audit: AuditDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
) -> Histogram:
    body = body.model_copy(
        update={
            "filter": await _case_event_filter(
                body.filter, principal, investigations, audit, working_set
            )
        }
    )
    result = await analytics.histogram(body, principal)
    await audit.record(
        principal=principal,
        action="analytics_histogram",
        investigation_id=body.filter.investigation_scope,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=result.total,
    )
    return result


@app.post("/v1/analytics/cross-filter", dependencies=[Depends(require_right(Right.INVESTIGATE))])
async def cross_filter_route(
    body: CrossFilterRequest,
    principal: PrincipalDep,
    analytics: AnalyticsDep,
    audit: AuditDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
) -> dict[str, Histogram]:
    body = body.model_copy(
        update={
            "filter": await _case_event_filter(
                body.filter, principal, investigations, audit, working_set
            )
        }
    )
    result = await analytics.cross_filter(body, principal)
    await audit.record(
        principal=principal,
        action="analytics_cross_filter",
        investigation_id=body.filter.investigation_scope,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=sum(h.total for h in result.values()),
    )
    return result


@app.post("/v1/analytics/first-seen", dependencies=[Depends(require_right(Right.INVESTIGATE))])
async def first_seen_route(
    body: FirstSeenRequest,
    principal: PrincipalDep,
    analytics: AnalyticsDep,
    audit: AuditDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
) -> FirstSeenResult:
    """When each node and link first appears in the brush window (ADR-087), for the timeline's
    playback. Access control is the adapter's, in the query, as for every analytics read."""
    body = body.model_copy(
        update={
            "filter": await _case_event_filter(
                body.filter, principal, investigations, audit, working_set
            )
        }
    )
    result = await analytics.first_seen(body, principal)
    await audit.record(
        principal=principal,
        action="analytics_first_seen",
        investigation_id=body.filter.investigation_scope,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=len(result.nodes) + len(result.edges),
    )
    return result


@app.post("/v1/analytics/geobins", dependencies=[Depends(require_right(Right.INVESTIGATE))])
async def geo_bins_route(
    body: GeoBinRequest,
    principal: PrincipalDep,
    analytics: AnalyticsDep,
    audit: AuditDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
) -> list[GeoBin]:
    body = body.model_copy(
        update={
            "filter": await _case_event_filter(
                body.filter, principal, investigations, audit, working_set
            )
        }
    )
    result = await analytics.geo_bins(body, principal)
    await audit.record(
        principal=principal,
        action="analytics_geo_bins",
        investigation_id=body.filter.investigation_scope,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=sum(b.count for b in result),
    )
    return result


@app.post("/v1/analytics/sightings", dependencies=[Depends(require_right(Right.INVESTIGATE))])
async def sightings_route(
    body: SightingRequest,
    principal: PrincipalDep,
    analytics: AnalyticsDep,
    audit: AuditDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
) -> list[Sighting]:
    """Phase 8 Stage 4f, B18's own snail trail — `packages/ports/analytics.py::AnalyticsPort.
    list_sightings`'s own docstring has the full record of why this route is new."""
    body = body.model_copy(
        update={
            "filter": await _case_event_filter(
                body.filter, principal, investigations, audit, working_set
            )
        }
    )
    result = await analytics.list_sightings(body, principal)
    await audit.record(
        principal=principal,
        action="analytics_sightings",
        investigation_id=body.filter.investigation_scope,
        resolved_query=body.model_dump(mode="json"),
        result_cardinality=len(result),
    )
    return result


@app.post("/v1/analytics/geometries", dependencies=[Depends(require_right(Right.INVESTIGATE))])
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
# `spec/00_ARCHITECTURE.md` §1.2's "Geospatial reference data as entities"
# table (site plans row), `spec/02_GLASS_FRONTEND.md` §3.5,
# `08_ACCEPTANCE_SCENARIOS.md` A1. A `Site` is investigation-scoped analyst
# data (`services/api/sites.py`'s own docstring), not deployment config —
# nothing here touches `osprey.yaml`/the `MapProvider` registry.
#
# Loaded from the fixtures path even in this live route, mirroring
# `scripts/build_local_basemap.py`'s own precedent for
# `osm_gazetteer_recipe.yaml` — where a shipped, non-test copy of either
# recipe should live is still an open item, recorded once already in
# `osm_gazetteer_recipe.yaml`'s own comment.
#: **A product recipe, in the image — moved out of `tests/` in round 13cdc.**
#:
#: This pointed at a path under `tests/scenarios/fixtures/`, and the Conduit's image
#: deliberately does not carry `tests/` (`.dockerignore`; `harness/apply.py`'s seed step mounts
#: the test tree precisely because the image has none of it). So `POST …/sites/{id}/grid` — A1's
#: own route — returned a bare 500 in **every rendered deployment**, `FileNotFoundError` on a
#: path under a directory that is not shipped. Measured over the wire, not reasoned about.
#:
#: A route the product serves cannot depend on a test fixture. The recipe is product data — it is
#: what turns grid cells into `Location` entities — so it lives beside `connectors/`, which round
#: 13bf put in the image for exactly this class of failure, and is COPYed the same way.
#: `tests/test_connectors_are_carried_into_the_image.py` is what fails if it is dropped again.
_SITE_GRID_RECIPE_PATH = Path(__file__).resolve().parents[2] / "recipes" / "site_grid.yaml"

#: **The geometry partition version a site grid's own cells are loaded at — round 13cde.**
#: The partition is versioned as a whole so a gazetteer refresh can load a new version without
#: overwriting the one an investigation already resolved against (`GeometryRecord`'s docstring).
#: Nothing in this product has ever written to it, so this route is its first writer and there is
#: no earlier version to be consistent with. What a later gazetteer refresh should do with
#: site-specific geometry — carry it forward, or leave a site's cells unresolvable at the new
#: version — has no answer in the spec and is raised in `05_DEPLOYMENT.md`, not decided here.
_SITE_GRID_GEOMETRY_VERSION = 1

#: Publish's own git-repository root (§6: recipes commit to `recipes/<id>.
#: yaml` at the repository root). An `app.state` value, not a bare module
#: constant `studio_publish.py` reaches for on its own, so a route test can
#: point it at a throwaway git repo (`app.dependency_overrides
#: [get_recipes_repo_root]`) instead of committing into this checkout.
#:
#: **Round 13bf: taken from `studio_publish`, not recomputed here.** This was its own
#: `.parents[2]` — a third independent copy of one fact, beside `studio_publish._REPO_ROOT` and
#: the renderer's `OSPREY_RECIPE_REPO_ROOT`, and the one the route actually used. Setting the
#: environment variable moved the other two and left this one pointing at `/app`, so the first
#: fix looked applied, returned 200, and still wrote the record into the image's own code
#: directory where the next rebuild discards it. Exactly the defect this round exists to remove,
#: found one layer further in than the grep that started it.
_RECIPES_REPO_ROOT = RECIPES_REPO_ROOT


class ControlPointsRequest(BaseModel):
    #: Exactly 4, TL/TR/BR/BL winding order — `packages/geo/bilinear.py`.
    control_points: ControlPointQuad


class GridRequest(BaseModel):
    #: `08_ACCEPTANCE_SCENARIOS.md` A1's "draw a 10x10 grid".
    rows: int = 10
    cols: int = 10


@app.post(
    "/v1/investigations/{investigation_id}/sites",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def create_site(
    investigation: InvestigationEditorDep,
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


@app.get(
    "/v1/investigations/{investigation_id}/sites/{site_id}",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def get_site(site: SiteViewerDep, principal: PrincipalDep, audit: AuditDep) -> Site:
    await audit.record(
        principal=principal,
        action="get_site",
        investigation_id=site.investigation_id,
        resolved_query={"site_id": site.id},
        result_cardinality=1,
    )
    return site


@app.get(
    "/v1/investigations/{investigation_id}/sites/{site_id}/image",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def get_site_image(site: SiteViewerDep, storage: SiteImageStorageDep) -> Response:
    """The browser never talks to the object store directly — the same
    reasoning as the tile proxy (`00_ARCHITECTURE.md` §1.2 "The tile
    proxy"): credentials stay server-side and every read is a request this
    process can see, not a signed URL handed out to whoever asks."""
    data = read_site_image(storage=storage, object_key=site.image_object_key)
    return Response(content=data, media_type=image_content_type(data))


@app.patch(
    "/v1/investigations/{investigation_id}/sites/{site_id}/control-points",
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def set_site_control_points(
    site: SiteEditorDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/sites/{site_id}/grid",
    dependencies=[Depends(require_right(Right.EDIT_GRAPH))],
)
async def set_site_grid(
    site: SiteEditorDep,
    principal: PrincipalDep,
    sites: SitesDep,
    graph: GraphDep,
    ontology: OntologyDep,
    analytics: AnalyticsDep,
    audit: AuditDep,
    body: GridRequest,
) -> Site:
    """Runs the site-grid connector + the existing recipe engine
    synchronously against this request — the same call shape
    `packages/demo_fixtures/hmp_graph.py`'s fixture code already uses,
    just triggered by an HTTP request instead of a test
    (`spec/00_ARCHITECTURE.md` §1.2: "Reference geodata is ingested
    through the ordinary connector framework"). `on_match: reference` in
    `site_grid_recipe.yaml` makes redrawing the grid idempotent rather
    than creating duplicate `Location`s.

    **That gap is closed — round 13cde.** This route now loads a `GeometryRecord` per cell, so a
    cell's `geometry_ref` resolves through `POST /v1/analytics/geometries` instead of pointing at
    nothing. The docstring here used to say the Conduit "has no `AnalyticsPort` wired in yet",
    which had stopped being true: `AnalyticsDep` backs the histogram, cross-filter, geo-bin and
    geometry routes. The gap outlived its own reason by being written down.

    **Three things about how it is loaded, each a choice rather than an accident:**

    - **The ref comes from the same Knowledge Adapter the recipe uses**, through the same
      `REGISTRY`, rather than being recomputed here. A second implementation of
      `geometry_reference`'s hash would be one more of the "two copies that drift" defects this
      phase keeps finding, and it would fail silently: the `Location` would carry one ref and the
      geometry partition another, with nothing to notice.
    - **Handling is read off the recipe's own `defaults`**, not restated, for the same reason.
    - **Version 1, deliberately.** The partition is versioned as a whole for gazetteer refreshes
      (`GeometryRecord`'s docstring), and nothing in this product has ever written to it — this
      route is its first writer, so there is no other version to be consistent with. What a
      *later* gazetteer refresh should do with site-specific geometry is a real question with no
      answer in the spec, and it is raised in `05_DEPLOYMENT.md` rather than decided here.

    Re-drawing the grid re-loads nothing: `(geometry_ref, version)` is the partition's primary
    key, so a blind second insert would not duplicate — it would **fail**, taking the whole route
    down with it. Existing refs are read back and skipped, which is what keeps
    `test_a1_redrawing_the_grid_does_not_duplicate_its_cells` true of geometries too.

    **Round 13cf, owner rulings R9 and R10:** a cell is now a `POLYGON` whose ref its `Location`
    carries, and the route geocodes the investigation's incidents into the cells it draws. The
    comments below have the detail, and `08_ACCEPTANCE_SCENARIOS.md`'s A1 note has the contract.
    The paragraphs above describe the point-shaped cells of 13cde and are kept as history."""
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

    # **Each cell is a polygon, and its `geometry_ref` names it — owner ruling R9 (a)/(b), round
    # 13cf.** Every value comes from where the recipe got it: the connector's own corner fields,
    # the shared adapter `REGISTRY`, and the recipe's `defaults`. So the ref on the `Location` and
    # the ref on the partition row are computed once each, by the same function.
    source_crs = recipe.connector.source_crs or "EPSG:4326"
    to_polygon_ref = REGISTRY["polygon_ref"]
    to_lon, to_lat = REGISTRY["coordinate_lon"], REGISTRY["coordinate_lat"]
    cell_handling = Handling(**recipe.defaults.handling)
    corner_fields = [f"c{i}_{axis}" for i in range(4) for axis in ("lon", "lat")]
    polygon_by_site_ref: dict[str, GeometryRecord] = {}
    for row in rows:
        raw = tuple(row[f] for f in corner_fields)
        ring = [
            (
                to_lon((raw[i], raw[i + 1]), source_crs=source_crs),
                to_lat((raw[i], raw[i + 1]), source_crs=source_crs),
            )
            for i in range(0, 8, 2)
        ]
        polygon_by_site_ref[row["site_ref"]] = GeometryRecord(
            geometry_ref=to_polygon_ref(raw, source_crs=source_crs),
            version=_SITE_GRID_GEOMETRY_VERSION,
            kind=GeometryKind.POLYGON,
            source_crs=source_crs,
            geometry_wkb=polygon_wkb(ring),
            handling=cell_handling,
        )

    # **A cell drawn before R9 keeps its identity; its ref moves (R9 (b)).** `on_match:
    # reference` reuses an existing `Location` without touching its properties, so a grid drawn
    # with the point-shaped ref would otherwise keep it forever. The same node id is re-written
    # with the polygon's ref. That is an ordinary upsert: a new revision of the same node, with
    # provenance merged, never a second node. The old point row stays in the partition at its
    # version, unreferenced: the partition is insert-only by design, and nothing reads a ref no
    # `Location` carries.
    cell_node_by_ref: dict[str, NodeId] = {}
    moved: list[NodeWrite] = []
    now = now_utc()
    for site_ref, polygon in polygon_by_site_ref.items():
        node = await graph.find_node("Location", "site_ref", site_ref, principal)
        if node is None:
            continue  # rejected rows already failed the route above; nothing to point at
        cell_node_by_ref[polygon.geometry_ref] = node.id
        if node.properties.get("geometry_ref") != polygon.geometry_ref:
            moved.append(
                NodeWrite(
                    id=node.id,
                    type=node.type,
                    properties={**node.properties, "geometry_ref": polygon.geometry_ref},
                    provenance=Provenance(
                        state=ProvenanceState.ASSERTED,
                        sources=[
                            SourceRef(
                                document_id=f"site:{updated.id}",
                                locator=f"grid-redraw:{site_ref}",
                                excerpt_hash="",
                            )
                        ],
                        first_seen=now,
                    ),
                    handling=node.handling,
                    created_by=principal.id,
                    created_at=now,
                    load_id=f"site-grid-{updated.id}",
                    recipe_id=recipe.id,
                    recipe_version=recipe.version,
                )
            )

    polygons = list(polygon_by_site_ref.values())
    already_loaded = {
        record.geometry_ref
        for record in await analytics.get_geometries(
            [record.geometry_ref for record in polygons],
            principal,
            version=_SITE_GRID_GEOMETRY_VERSION,
        )
    }
    await analytics.load_geometries(
        [record for record in polygons if record.geometry_ref not in already_loaded]
    )

    # **Incidents geocode into cells, at draw time — R9 (c), R10.** One containment call over
    # the investigation's events with a point. Each covered event records its cell (the event
    # half), and each `PRESENT_AT` incident whose cell changed gets an edge from its subject to the
    # cell `Location` (the graph half). "Changed" is what keeps a redraw from adding a second
    # occurrence to every edge, since `upsert_edges` sums occurrences on a same-pair write.
    # Incidents arriving after the draw are geocoded by the next redraw, not on ingest (R10).
    geocoded = await analytics.geocode_events(
        GeocodeRequest(
            filter=EventFilter(investigation_scope=updated.investigation_id),
            cells={ref: node_id for ref, node_id in cell_node_by_ref.items()},
        ),
        principal,
    )
    edges = [
        EdgeWrite(
            id=new_edge_id(),
            type="PRESENT_AT",
            source=event.source_id,
            target=event.value,
            interval=Interval(valid_from=event.occurred_at, valid_to=event.occurred_at),
            provenance=Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[
                    SourceRef(
                        document_id=f"site:{updated.id}",
                        locator=f"geocode:{event.event_id}",
                        excerpt_hash="",
                    )
                ],
                first_seen=now,
            ),
            handling=event.handling,
            created_by=principal.id,
            created_at=now,
            load_id=f"site-grid-{updated.id}",
        )
        for event in geocoded
        if event.edge_type == "PRESENT_AT" and event.previous_value != event.value
    ]
    if moved or edges:
        tx = await graph.begin_transaction()
        try:
            if moved:
                await graph.upsert_nodes(moved, tx)
            if edges:
                await graph.upsert_edges(edges, tx)
        except Exception:
            await graph.rollback_transaction(tx)
            raise
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


@app.get("/v1/ingest/packs")
async def list_domain_packs(principal: PrincipalDep) -> list[DomainPackEntry]:
    """ADR-108 phase D: the domain-model catalogue — deployment metadata, the same justification
    as the connector catalogue above: authenticated, not case-scoped, not audited."""
    return pack_catalogue()


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


@app.get(
    "/v1/investigations/{investigation_id}/ingest/source-files",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))],
)
async def list_ingest_source_files(
    investigation: InvestigationViewerDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    audit: AuditDep,
) -> IngestSourceListing:
    """**Owner ruling R6, 27 September 2026** — what the Studio's Connect stage offers an analyst
    to pick from. Round 13b's over-the-wire exit test found a rendered deployment gave an analyst
    no route by which to supply a source file at all; this is that route, and
    `services/api/ingest_sources.py`'s own docstring has the refusals it enforces and why each is
    there.

    **`SOURCE_AUTHOR`, the same role that already gates `POST /v1/ingest/recipes`** — listing the
    files you are about to point a draft at is that same action one step earlier, and a principal
    who cannot create the draft has no use for the list. Checked as a route dependency, never
    filtered afterwards (`CLAUDE.md` rule 2).

    Audited like every other read: the cardinality is the number of files offered, which is also
    the only thing about the mount's contents this route ever records."""
    # ADR-099 Amendment 3: the files of the case's datasets, and those placed before it.
    listing = list_source_files(datasets=principal.datasets)
    await audit.record(
        principal=principal,
        action="list_ingest_source_files",
        resolved_query={"root": listing.root},
        result_cardinality=len(listing.files),
    )
    return listing


_UPLOAD_REFUSAL_STATUS = {
    "bad_name": status.HTTP_400_BAD_REQUEST,
    "empty": status.HTTP_400_BAD_REQUEST,
    "type_not_allowed": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "exists": status.HTTP_409_CONFLICT,
    "too_large": 413,
    "not_writable": status.HTTP_503_SERVICE_UNAVAILABLE,
}


@app.post(
    "/v1/investigations/{investigation_id}/ingest/source-files",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))],
)
async def upload_ingest_source_file(
    investigation: InvestigationEditorDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    audit: AuditDep,
    request: Request,
    name: str,
) -> IngestSourceFile:
    """**ADR-067 (amends ruling R6)** — the Connect stage's "Choose file…": the analyst's own file,
    sent as the raw request body with its name in the query, lands in the `uploaded` folder under
    the ingest root and is then offered in the picker like any other file.

    **`SOURCE_AUTHOR`, the same role as the listing and the draft route**, checked as a route
    dependency before a byte is read. The name, the type, the size and the no-overwrite rule are
    enforced in `services/api/ingest_sources.py` (see `save_upload`), where the tests prove each.
    The declared size is checked first so an honest oversized upload is refused without reading it;
    the streamed count is what actually stops a dishonest one.

    Audited with the name and the size only, never the contents. A refused upload is not a write
    and so is not audited as one; it is returned as a 4xx the Glass shows as a sentence."""
    limit = max_upload_bytes()
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(
            status_code=413,
            detail="That file is larger than the upload limit.",
        )
    try:
        saved = await save_upload(
            ingest_root(),
            name,
            request.stream(),
            max_bytes=limit,
            dataset_id=made_in(principal),
        )
    except UploadRefused as refusal:
        raise HTTPException(
            status_code=_UPLOAD_REFUSAL_STATUS[refusal.code], detail=refusal.message
        ) from refusal
    await audit.record(
        principal=principal,
        action="upload_ingest_source_file",
        resolved_query={"name": saved.name, "size_bytes": saved.size_bytes},
        result_cardinality=1,
    )
    return saved


def _with_default_classification(
    handling: dict[str, Any], scheme: HandlingScheme
) -> dict[str, Any]:
    """**ADR-068.** Connect's classification is optional: left blank it is recorded as the scheme's
    lowest level, which for the UK scheme is `PUBLIC`. Done here, not in the Glass, so a draft never
    carries an empty marking whichever client wrote it; an analyst's own choice is never
    replaced."""
    chosen = handling.get("classification")
    if isinstance(chosen, str) and chosen.strip():
        return handling
    lowest = "PUBLIC" if "PUBLIC" in scheme.classification else scheme.classification[0]
    return {**handling, "classification": lowest}


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def create_studio_recipe_draft(
    investigation: InvestigationEditorDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    scheme: HandlingSchemeDep,
    body: ConnectDraftInput,
) -> StudioRecipeDraft:
    """§8: "Source author: create and edit draft recipes." A fresh draft —
    Connect's "pick a connector, point at the data" plus the three
    mandatory gate answers, which may still be incomplete
    (`StudioRecipeDraft.ready_for_profile` reports that, §2)."""
    # ADR-127 decision 5: judged by shape at creation (no draft to read the source through yet).
    _check_deduplicate(body.deduplicate, None)
    draft = await studio_recipes.create_draft(
        principal,
        label=body.label,
        connector_profile=body.connector_profile,
        source_location=body.source_location,
        handling=_with_default_classification(body.handling, scheme),
        legal_basis=body.legal_basis,
        deduplicate=body.deduplicate,
    )
    await audit.record(
        principal=principal,
        action="create_studio_recipe_draft",
        resolved_query={"recipe_id": draft.recipe_id},
        result_cardinality=1,
    )
    return draft


def _check_deduplicate(config: DeduplicateConfig | None, columns: list[str] | None) -> None:
    """A `deduplicate` the source cannot support is refused at save, in words (422): see
    `recipe_rules.deduplicate_problems`. An absent one, and one with an empty `key` (which clears
    it), need no judging."""
    if config is None or not config.key:
        return
    problems = deduplicate_problems(config, columns)
    if problems:
        raise RecipeRuleError(problems)


@app.patch(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def update_studio_recipe_draft(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    scheme: HandlingSchemeDep,
    body: ConnectDraftInput,
) -> StudioRecipeDraft:
    """Edits Connect's own fields on a draft still in progress — changing
    connector, source location, handling marking or legal basis before
    moving on. Rejects (409, via `StudioRecipeNotADraftError`) once the
    recipe has left `draft` status.

    `deduplicate` (ADR-127 decision 5) is judged against the columns of the source it will be read
    from (the body's location, else the draft's): each key names a source column, as a run reads
    it. Absent leaves the draft's own; an empty `key` clears it."""
    if body.deduplicate is not None and body.deduplicate.key:
        location = body.source_location or recipe.source_location
        _check_deduplicate(
            body.deduplicate,
            source_column_names(
                recipe.model_copy(
                    update={
                        "source_location": location,
                        "connector_profile": body.connector_profile,
                    }
                )
            )
            if location
            else None,
        )
    updated = await studio_recipes.update_draft(
        recipe.recipe_id,
        principal,
        label=body.label,
        connector_profile=body.connector_profile,
        source_location=body.source_location,
        handling=_with_default_classification(body.handling, scheme),
        legal_basis=body.legal_basis,
        deduplicate=body.deduplicate,
    )
    await audit.record(
        principal=principal,
        action="update_studio_recipe_draft",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )
    return updated


@app.put(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/pipeline",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def update_studio_recipe_pipeline(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    body: PipelineGraph,
) -> StudioRecipeDraft:
    """ADR-108 phase B: the pipeline's own save. The graph half of the save gate runs here —
    a violation answers 422 `pipeline_invalid` with every problem in words, and nothing is
    stored; the row-template half stays Map's own, unchanged."""
    problems = pipeline_rule_violations(body)
    if problems:
        return JSONResponse(  # type: ignore[return-value]
            status_code=422,
            content={"error": "pipeline_invalid", "problems": problems},
        )
    updated = await studio_recipes.update_pipeline(recipe.recipe_id, principal, pipeline=body)
    await audit.record(
        principal=principal,
        action="update_studio_recipe_pipeline",
        resolved_query={"recipe_id": recipe.recipe_id, "nodes": len(body.nodes)},
        result_cardinality=1,
    )
    return updated


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def get_studio_recipe_draft(
    investigation: InvestigationViewerDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> StudioRecipeDraft:
    await audit.record(
        principal=principal,
        action="get_studio_recipe_draft",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )
    names = await principal_names.display_names(
        [recipe.created_by, *([recipe.published_by] if recipe.published_by else [])]
    )
    return recipe.model_copy(
        update={
            "created_by_name": names.get(recipe.created_by),
            "published_by_name": names.get(recipe.published_by or ""),
            # ADR-108 phase A: a v1 recipe reads as its canonical chain — derived here, never
            # stored back, the same read-time discipline the display names above follow.
            "pipeline": pipeline_from_recipe(recipe),
        }
    )


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipes",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def list_studio_recipe_drafts(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> list[StudioRecipeDraft]:
    """Connect's "resume a draft" list — the author's own unit's drafts
    only (`StudioRecipeStore.list_drafts`' own `owning_unit` scoping)."""
    listed = await studio_recipes.list_drafts(principal)
    names = await principal_names.display_names(
        [d.created_by for d in listed] + [d.published_by for d in listed if d.published_by]
    )
    drafts = [
        d.model_copy(
            update={
                "created_by_name": names.get(d.created_by),
                "published_by_name": names.get(d.published_by or ""),
            }
        )
        for d in listed
    ]
    await audit.record(
        principal=principal,
        action="list_studio_recipe_drafts",
        resolved_query={},
        result_cardinality=len(drafts),
    )
    return drafts


# --- ingest studio: profile (09_INGEST_STUDIO.md §3) -------------------------


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/profile",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def get_studio_recipe_profile(
    investigation: InvestigationViewerDep,
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
    return [
        TransformDescriptor(
            name=name, arity=ARITY.get(name, 1), parts=list(STRUCTURED_PARTS.get(name, ()))
        )
        for name in REGISTRY
    ]


@app.put(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/row-template",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def update_studio_recipe_row_template(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
    body: RowTemplateUpdateInput,
    ontology: OntologyDep,
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
    # ADR-081 step D: refused at save, naming each problem; refused again when it runs.
    # ADR-127 decision 3: a marking bound to a column names a column the source has, and a bound
    # unit needs the source's declared units.
    binds_handling = any(
        handling_bindings(e.handling) for e in template_elements(body.row_template)
    )
    check_recipe_rules(
        body.row_template,
        ontology,
        source_columns=(
            source_column_names(recipe)
            if binds_handling or draft_handling_columns(recipe)
            else None
        ),
        units=draft_units(recipe),
        defaults_handling=baseline.model_dump(exclude_none=True),
        scheme=scheme,
        handling_columns=draft_handling_columns(recipe),
        declared_columns=draft_handling_columns(recipe),
    )
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


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/map/sample-rows/{row_index}",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def get_studio_recipe_sample_row(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/map/handling-preview",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def preview_studio_recipe_element_handling(
    investigation: InvestigationViewerDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/verify",
    dependencies=[Depends(require_right(Right.VERIFY_PIPELINES))],
)
async def verify_studio_recipe(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    scheme: HandlingSchemeDep,
    graph: GraphDep,
    ontology: OntologyDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    recipe_runs: RecipeRunsDep,
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
    # ADR-127 decision 5: the dry run counts the rows the case already kept as the run would count
    # them, by the draft's own `deduplicate`, asking the store of loaded rows (this case's keys
    # only) and writing nothing.
    report = await run_verify(
        recipe,
        principal,
        scheme,
        graph,
        ontology,
        row_keys=recipe_runs,
        investigation_id=investigation.id,
    )
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


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipe-registry",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def list_studio_recipe_registry(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/publish",
    dependencies=[Depends(require_right(Right.PUBLISH_PIPELINES))],
)
async def publish_studio_recipe(
    investigation: InvestigationEditorDep,
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
    # ADR-108 phase B: what the runner cannot run yet is refused in words, never published and
    # silently part-run (rule 2). Phase C's pipeline runner empties this gate.
    if recipe.pipeline is not None:
        unrunnable = pipeline_run_violations(recipe.pipeline)
        if unrunnable:
            return JSONResponse(  # type: ignore[return-value]
                status_code=422,
                content={"error": "pipeline_not_runnable", "problems": unrunnable},
            )
    # ADR-120 D10, Amendment 1: the pins come from the live ontology, for the packs the recipe
    # names and the packs whose types it writes.
    assert recipe.row_template is not None
    try:
        pins = pack_versions_for(recipe.pipeline, recipe.row_template, ontology)
    except ValueError as error:
        return JSONResponse(  # type: ignore[return-value]
            status_code=422, content={"error": "pack_not_composed", "message": str(error)}
        )
    built = build_recipe(
        recipe,
        ontology_version=ontology.version,
        pack_versions=pins,
        schedule_cron=body.schedule_cron,
        schedule_watch=body.schedule_watch,
    )
    if body.schedule_cron is not None:
        validate_schedule(body.schedule_cron, body.schedule_timezone or DEFAULT_TIMEZONE)
    if body.schedule_watch is not None:
        validate_watch(body.schedule_watch, recipe)
    git_path = await write_and_commit_recipe(built, repo_root=repo_root)
    updated = await studio_recipes.publish(
        recipe.recipe_id,
        principal,
        ontology_version=ontology.version,
        pack_versions=pins,
        git_path=git_path,
        schedule_cron=body.schedule_cron,
        schedule_watch=body.schedule_watch,
        now=datetime.now(UTC),
        schedule_timezone=body.schedule_timezone,
        schedule_case=investigation.id,
    )
    await audit.record(
        principal=principal,
        action="publish_studio_recipe",
        resolved_query={"recipe_id": recipe.recipe_id, "git_path": git_path},
        result_cardinality=1,
    )
    return updated


@app.patch(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/schedule",
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES))],
)
async def update_studio_recipe_schedule(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_APPROVER))],
    studio_recipes: StudioRecipesDep,
    repo_root: RecipesRepoRootDep,
    audit: AuditDep,
    body: ScheduleUpdateInput,
) -> StudioRecipeDraft:
    """§8: "schedule it" — a source-approver action distinct from
    `publish`. Re-commits the recipe YAML with the new schedule (the
    repository stays the record for the schedule too, not only the
    mapping) at the same `git_path`, without bumping `version` — the
    mapping itself is unchanged.

    ADR-110 decision 7: a schedule it could not keep is refused in words before anything is saved,
    and whoever sets it becomes its owner (decision 3). ADR-120 Amendment 2, decision 2: the
    re-commit carries the row's pins as stored, none included, and a mapped row with no core
    version is saved without one, as the administrator's route does."""
    if body.schedule_cron is not None:
        validate_schedule(body.schedule_cron, body.schedule_timezone or DEFAULT_TIMEZONE)
    if body.schedule_watch is not None:
        validate_watch(body.schedule_watch, recipe)
    updated = await studio_recipes.update_schedule(
        recipe.recipe_id,
        principal,
        schedule_cron=body.schedule_cron,
        schedule_watch=body.schedule_watch,
        schedule_timezone=body.schedule_timezone,
        schedule_case=investigation.id,
    )
    await _commit_schedule(updated, repo_root)
    await audit.record(
        principal=principal,
        action="update_studio_recipe_schedule",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )
    return updated


@app.post(
    "/v1/ingest/schedule-preview",
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES))],
)
async def schedule_preview_route(body: SchedulePreviewInput) -> SchedulePreview:
    """ADR-110 decision 7: a schedule in words and its next five runs, before it is saved — the
    executor's own arithmetic, so the editor never promises what the executor would not keep. A
    schedule it could not keep is refused in words (rule 2)."""
    zone = body.timezone or DEFAULT_TIMEZONE
    validate_schedule(body.cron, zone)
    after = body.after or datetime.now(UTC)
    return SchedulePreview(
        words=describe(body.cron, zone), next_runs=next_slots(body.cron, zone, after=after)
    )


async def _set_recipe_schedule_paused(
    recipe: StudioRecipeDraft,
    principal: Principal,
    studio_recipes: StudioRecipeStore,
    audit: AuditWriter,
    *,
    paused: bool,
) -> StudioRecipeDraft:
    await studio_recipes.set_paused(
        recipe.recipe_id, paused=paused, reason=f"paused by {principal.id}" if paused else None
    )
    await audit.record(principal=principal,
                       action="pause_recipe_schedule" if paused else "resume_recipe_schedule",
                       resolved_query={"recipe_id": recipe.recipe_id},
                       result_cardinality=1)  # fmt: skip
    return await studio_recipes.get(recipe.recipe_id)


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/schedule/pause",
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES))],
)
async def pause_recipe_schedule(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_APPROVER))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
) -> StudioRecipeDraft:
    """ADR-110 decision 7: *Pause* in the Studio, by the source approver; *Resume* below."""
    return await _set_recipe_schedule_paused(recipe, principal, studio_recipes, audit, paused=True)


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/schedule/resume",
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES))],
)
async def resume_recipe_schedule(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_APPROVER))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
) -> StudioRecipeDraft:
    return await _set_recipe_schedule_paused(recipe, principal, studio_recipes, audit, paused=False)


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/runs",
    dependencies=[Depends(require_right(Right.READ_DATA_FEEDS))],
)
async def recipe_runs_route(
    investigation: InvestigationViewerDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    recipe_runs: RecipeRunsDep,
    handling_scheme: HandlingSchemeDep,
) -> list[ScheduleRunView]:
    """ADR-110 decisions 6 and 7: the recipe's runs beneath its schedule, newest first — counts
    withheld where the reader may not view the source (rule 3)."""
    return [
        _schedule_run_view(run, principal, handling_scheme)
        for run in await recipe_runs.for_recipe(recipe.recipe_id)
    ]


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/versions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def create_studio_recipe_version(
    investigation: InvestigationEditorDep,
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


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/run",
    dependencies=[Depends(require_right(Right.RUN_PIPELINES))],
)
async def run_studio_recipe(
    investigation: InvestigationEditorDep,
    recipe: RunnableStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.LOADER))],
    graph: GraphDep,
    ontology: OntologyDep,
    analytics: AnalyticsDep,
    media: MediaDep,
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
    extraction_candidates: ExtractionCandidatesDep,
    recogniser_for: PipelineRecognisersDep,
    online_geocode: OnlineGeocodeDep,
    typology_rules: TypologyRulesDep,
    held_rows: HeldRowsDep,
    screening_lists: ScreeningListsDep,
    compute: ComputeDep,
    kyc_expiries: KycExpiriesDep,
    recipe_runs: RecipeRunsDep,
) -> LoadReportView | PipelineRunReportView:
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
    report = await run_recipe_as(
        RecipeRunDeps(
            graph=graph,
            ontology=ontology,
            analytics=analytics,
            media=media,
            recipe_repo_root=repo_root,
            audit=audit,
            jobs=jobs,
            valkey=valkey,
            handling_scheme=handling_scheme,
            config=config,
            hotlists_store=hotlists_store,
            monitors_store=monitors_store,
            patterns_store=patterns_store,
            alerts_store=alerts_store,
            principal_resolver=principal_resolver,
            extraction_candidates=extraction_candidates,
            recogniser_for=recogniser_for,
            online_geocode=online_geocode,
            typology_rules=typology_rules,
            held_rows=held_rows,
            screening_lists=screening_lists,
            compute=compute,
            kyc_expiries=kyc_expiries,
            recipe_runs=recipe_runs,
        ),
        principal=principal,
        recipe=recipe,
        investigation_id=investigation.id,
        source_location=body.source_location,
        trigger="manual",
    )
    # Rules 3 and 7: counts and words, never the load's id lists, and no count at all where the
    # loader may not view every marking the rows were written at (`report_view`).
    return report_view(report, principal, handling_scheme)


def _schedule_executor(application: FastAPI) -> ScheduleExecutor:
    """The executor over the running Conduit's own stores (ADR-110 decisions 2 and 3)."""
    state = application.state

    async def check_case(owner: Principal, case: str) -> Principal:
        await state.investigations.get_authorized(case, owner, need=AccessLevel.EDITOR)
        return await scope_to_case(owner, case, state.datasets)

    async def run(
        owner: Principal,
        recipe: StudioRecipeDraft,
        case: str,
        slot: datetime | None,
        source_file: WatchedFile | None = None,
    ) -> Any:
        return await run_recipe_as(
            RecipeRunDeps.from_state(state),
            principal=owner,
            recipe=recipe,
            investigation_id=case,
            source_location=source_file.location if source_file else None,
            trigger="watch" if source_file else "schedule" if slot else "manual",
            slot=slot,
            source_file=source_file.identity if source_file else None,
        )

    async def watch_files(recipe: StudioRecipeDraft, now: datetime) -> list[WatchedFile]:
        # A folder listing and a stat per file: off the event loop.
        return await asyncio.to_thread(waiting_files, recipe, now=now)

    async def notify(owner_id: str, recipe: StudioRecipeDraft, words: str) -> None:
        await state.alerts_store.save(schedule_notice(owner_id, recipe, words, datetime.now(UTC)))

    return ScheduleExecutor(
        recipes=state.studio_recipes,
        runs=state.recipe_runs,
        valkey=state.valkey,
        scheme=state.handling_scheme,
        resolve_owner=state.principal_resolver.resolve_for_owner_detailed,
        check_case=check_case,
        run=run,
        notify=notify,
        watch_files=watch_files,
    )


# --- ultimate beneficial ownership (ADR-109 phase C) ------------------------------


@app.get(
    "/v1/investigations/{investigation_id}/ownership/{node_id}",
    dependencies=[Depends(require_right(Right.TRACE_OWNERSHIP))],
)
async def trace_ownership_route(
    node_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    compute: ComputeDep,
    audit: AuditDep,
    threshold: Annotated[float, Query(gt=0, le=100)] = 25.0,
) -> OwnershipView:
    """Who ultimately owns or controls the entity, with cumulative shares, as the reader reads
    the structure (rule 3); refused in words when too deep or too large (rule 2). A view: nothing
    it concludes is written (ruling 9)."""
    view = await ownership_module.trace_for(graph, compute, node_id, principal, threshold=threshold)
    await audit.record(
        principal=principal,
        action="trace_ownership",
        investigation_id=investigation.id,
        resolved_query={"node_id": node_id, "threshold": threshold},
        result_cardinality=len(view.trace.owners),
    )
    return view


@app.post(
    "/v1/investigations/{investigation_id}/ownership/{node_id}/canvas",
    dependencies=[Depends(require_right(Right.TRACE_OWNERSHIP))],
)
async def ownership_canvas(
    node_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> StarterRunOutcome:
    """The entity's ownership structure onto the canvas, all or (past the cap) none."""
    nodes, edges = await ownership_module.read_structure(graph, node_id, principal, max_depth=10)
    outcome = await working_set.seed(
        investigation.id, list(nodes.values()), list(edges.values()), principal
    )
    await publish_delta(valkey, investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=outcome.delta.seq,
        label=OWNERSHIP,
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="ownership_canvas",
        investigation_id=investigation.id,
        resolved_query={"node_id": node_id},
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return StarterRunOutcome(
        delta=outcome.delta,
        added_nodes=len(outcome.delta.nodes),
        added_links=len(outcome.delta.edges),
    )


@app.get(
    "/v1/investigations/{investigation_id}/kyc/{node_id}",
    dependencies=[Depends(require_right(Right.TRACE_OWNERSHIP))],
)
async def kyc_status_route(
    node_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    compute: ComputeDep,
    audit: AuditDep,
) -> KycStatus:
    """A customer's KYC status and baseline risk, computed now, as the reader reads the graph,
    never stored (ADR-109 rulings 7 and 10)."""
    status = await kyc_module.assess(
        graph, compute, node_id, principal, today=datetime.now(UTC).date()
    )
    await audit.record(
        principal=principal,
        action="kyc_status",
        investigation_id=investigation.id,
        resolved_query={"node_id": node_id},
        result_cardinality=len(status.factors),
    )
    return status


@app.get(
    "/v1/investigations/{investigation_id}/risk/{node_id}",
    dependencies=[Depends(require_right(Right.TRACE_OWNERSHIP))],
)
async def neighbourhood_risk_route(
    node_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    compute: ComputeDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
) -> NeighbourhoodRisk:
    """*Neighbourhood risk* (ADR-109 phase E): the case's alerts within two hops, halved per hop,
    counted for ninety days — read as the reader, never stored."""
    risk = await risk_module.neighbourhood_risk(
        graph,
        compute,
        alerts_store,
        investigation.id,
        node_id,
        principal,
        today=datetime.now(UTC).date(),
    )
    await audit.record(
        principal=principal,
        action="neighbourhood_risk",
        investigation_id=investigation.id,
        resolved_query={"node_id": node_id},
        result_cardinality=len(risk.contributions),
    )
    return risk


@app.exception_handler(NeighbourhoodTooLarge)
async def _neighbourhood_too_large_handler(
    request: Request, exc: NeighbourhoodTooLarge
) -> JSONResponse:
    return JSONResponse(
        status_code=409, content={"error": "neighbourhood_too_large", "detail": str(exc)}
    )


@app.exception_handler(KycNotApplicable)
async def _kyc_not_applicable_handler(request: Request, exc: KycNotApplicable) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "kyc_not_applicable", "detail": f"KYC is not about a {exc}"},
    )


@app.exception_handler(OwnershipTooComplex)
async def _ownership_too_complex_handler(
    request: Request, exc: OwnershipTooComplex
) -> JSONResponse:
    return JSONResponse(
        status_code=409, content={"error": "ownership_too_complex", "detail": str(exc)}
    )


# --- the case team's alert queue (ADR-109 phase B) ----------------------------


async def _case_report(
    investigation: Investigation,
    principal: Principal,
    *,
    investigations: InvestigationStore,
    graph: GraphPort,
    alerts_store: AlertStore,
    held_rows: HeldRowStore,
    compute: ComputePort,
    explore: ExploreService,
    ontology: OntologySchema,
    period_weeks: int,
) -> ReportFigures:
    level = await investigations.effective_level(investigation.id, principal)
    return await reports_module.case_report(
        alerts=alerts_store,
        graph=graph,
        held=held_rows,
        compute=compute,
        explore=explore,
        ontology=ontology,
        domains=investigation.domains,
        investigation_id=investigation.id,
        reader=principal,
        today=datetime.now(UTC).date(),
        period_weeks=period_weeks,
        show_held=level is not None and level.rank >= AccessLevel.EDITOR.rank,
    )


@app.get(
    "/v1/investigations/{investigation_id}/reports",
    dependencies=[Depends(require_right(Right.READ_REPORTS))],
)
async def read_case_report(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    held_rows: HeldRowsDep,
    compute: ComputeDep,
    explore: ExploreDep,
    ontology: OntologyDep,
    audit: AuditDep,
    weeks: Annotated[int, Query(ge=1, le=52)] = 12,
) -> ReportFigures:
    """The Reports view (ADR-111): the case's figures, every one counted as the reader (rule 3);
    held rows only for Editors and above; past its bound, `limit_exceeded` (rule 2)."""
    figures = await _case_report(
        investigation, principal, investigations=investigations, graph=graph,
        alerts_store=alerts_store, held_rows=held_rows, compute=compute, explore=explore,
        ontology=ontology, period_weeks=weeks,
    )  # fmt: skip
    await audit.record(
        principal=principal,
        action="read_case_report",
        investigation_id=investigation.id,
        resolved_query={"weeks": weeks},
        result_cardinality=figures.alerts_total,
    )
    return figures


@app.get(
    "/v1/investigations/{investigation_id}/reports/feed",
    response_model=None,
    dependencies=[Depends(require_right(Right.READ_REPORT_FEED))],
)
async def read_report_feed(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    held_rows: HeldRowsDep,
    compute: ComputeDep,
    explore: ExploreDep,
    ontology: OntologyDep,
    audit: AuditDep,
    export_ledger: ExportLedgerDep,
    weeks: Annotated[int, Query(ge=1, le=52)] = 12,
    feed_format: Annotated[Literal["json", "csv"], Query(alias="format")] = "json",
) -> ReportFigures | Response:
    """The reporting feed a dashboard pulls (ADR-111 decisions 6 to 8): the same figures as the
    Reports view, as JSON or CSV — figures only. Every read is audited and written to the export
    ledger as metadata (who, which case, when), since the figures leave the Glass."""
    figures = await _case_report(
        investigation, principal, investigations=investigations, graph=graph,
        alerts_store=alerts_store, held_rows=held_rows, compute=compute, explore=explore,
        ontology=ontology, period_weeks=weeks,
    )  # fmt: skip
    rows = reports_module.feed_rows(figures)
    await export_ledger.record(
        ExportLedgerEntry(
            id=new_id(),
            investigation_id=investigation.id,
            principal_id=principal.id,
            artefact_kind="report_feed",
            handling_level=principal.clearance,
            exported_at=datetime.now(UTC),
            item_count=len(rows),
            withheld=False,
            manifest_policy="omit",
        )
    )
    await audit.record(
        principal=principal,
        action="read_report_feed",
        investigation_id=investigation.id,
        resolved_query={"weeks": weeks, "format": feed_format},
        result_cardinality=len(rows),
    )
    if feed_format == "json":
        return figures
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["section", "label", "typology", "week_start", "value"])
    writer.writerows(rows)
    return Response(content=buffer.getvalue(), media_type="text/csv; charset=utf-8")


@app.exception_handler(ReportLimitExceededError)
async def _report_limit_handler(request: Request, exc: ReportLimitExceededError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=exc.detail.model_dump())


@app.get(
    "/v1/investigations/{investigation_id}/alert-queue",
    dependencies=[Depends(require_right(Right.READ_ALERT_QUEUE))],
)
async def read_alert_queue(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    status_filter: Annotated[
        Literal["open", "claimed", "closed", "active", "all"], Query(alias="status")
    ] = "active",
) -> list[QueuedAlert]:
    """The case's rule-raised alerts, the case team's (ruling 3). `active` is open and claimed.
    An alert any of whose entities the reader cannot see is left out, and not counted (rule 3)."""
    statuses = {
        "active": ["open", "claimed"],
        "all": None,
    }.get(status_filter, [status_filter])
    rows = await alert_queue.queue(
        alerts_store, graph, investigation.id, principal, statuses=statuses
    )
    await audit.record(
        principal=principal,
        action="read_alert_queue",
        investigation_id=investigation.id,
        resolved_query={"status": status_filter},
        result_cardinality=len(rows),
    )
    return rows


@app.get(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}",
    dependencies=[Depends(require_right(Right.READ_ALERT_QUEUE))],
)
async def explain_alert(
    alert_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    analytics: AnalyticsDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
) -> AlertExplanation:
    """What fired the alert: its entities and node, the links and each transaction it cites."""
    explanation = await alert_queue.explain(
        alerts_store, graph, analytics, investigation.id, alert_id, principal
    )
    await audit.record(
        principal=principal,
        action="explain_alert",
        investigation_id=investigation.id,
        resolved_query={"alert_id": alert_id},
        result_cardinality=len(explanation.nodes),
    )
    return explanation


async def _triage_audit(
    audit: AuditWriter, principal: Principal, investigation_id: str, action: str, alert: Alert
) -> None:
    await audit.record(
        principal=principal,
        action=action,
        investigation_id=investigation_id,
        resolved_query={
            "alert_id": alert.id,
            "status": alert.status,
            "disposition": alert.disposition,
            "node_ids": alert.referent_node_ids,
        },
        result_cardinality=1,
    )


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/claim",
    dependencies=[Depends(require_right(Right.TRIAGE_ALERTS))],
)
async def claim_alert(
    alert_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
) -> Alert:
    alert = await alert_queue.claim(alerts_store, graph, investigation.id, alert_id, principal)
    await _triage_audit(audit, principal, investigation.id, "alert_claimed", alert)
    return alert


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/release",
    dependencies=[Depends(require_right(Right.TRIAGE_ALERTS))],
)
async def release_alert(
    alert_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
) -> Alert:
    alert = await alert_queue.release(alerts_store, graph, investigation.id, alert_id, principal)
    await _triage_audit(audit, principal, investigation.id, "alert_released", alert)
    return alert


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/disposition",
    dependencies=[Depends(require_right(Right.TRIAGE_ALERTS))],
)
async def dispose_alert(
    alert_id: str,
    body: AlertDispositionInput,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
) -> Alert:
    """Closes the alert with its disposition and reason. A true positive confirms its node
    (rule 5's human confirmation); a false positive leaves it `inferred`."""
    alert = await alert_queue.dispose(
        alerts_store,
        graph,
        investigation.id,
        alert_id,
        principal,
        disposition=body.disposition,
        reason=body.reason,
    )
    await _triage_audit(audit, principal, investigation.id, "alert_disposed", alert)
    return alert


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/canvas",
    dependencies=[Depends(require_right(Right.TRIAGE_ALERTS))],
)
async def alert_canvas(
    alert_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> StarterRunOutcome:
    """The alert's node, its entities and the links it cites onto the canvas — all, or past the
    working set's cap, none (`limit_exceeded`, rule 2). Editor, as it adds to the working set."""
    alert, nodes, edges = await alert_queue.canvas_elements(
        alerts_store, graph, investigation.id, alert_id, principal
    )
    outcome = await working_set.seed(investigation.id, nodes, edges, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=outcome.delta.seq,
        label=ALERT_CANVAS,
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="alert_canvas",
        investigation_id=investigation.id,
        resolved_query={"alert_id": alert_id},
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return StarterRunOutcome(
        delta=outcome.delta,
        added_nodes=len(outcome.delta.nodes),
        added_links=len(outcome.delta.edges),
    )


@app.exception_handler(AlertTriageConflict)
async def _alert_triage_conflict_handler(
    request: Request, exc: AlertTriageConflict
) -> JSONResponse:
    """Someone else claimed or closed it first: the Glass reloads the queue."""
    return JSONResponse(status_code=409, content={"error": "alert_moved_on"})


# --- typology rules, their audit, and held rows (ADR-109 phase A) -------------


@app.get(
    "/v1/investigations/{investigation_id}/rules",
    dependencies=[Depends(require_right(Right.READ_ALERT_QUEUE))],
)
async def list_typology_rules(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
) -> list[TypologyRule]:
    """The case's rules, retired ones included — what watches this case's loads is the case
    team's to know (ruling 3)."""
    return await typology_rules.list_for_case(investigation.id, principal)


@app.post(
    "/v1/investigations/{investigation_id}/rules",
    status_code=201,
    dependencies=[Depends(require_right(Right.DEPLOY_RULES))],
)
async def deploy_typology_rule(
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    patterns_store: PatternsStoreDep,
    audit: AuditDep,
    body: TypologyRuleInput,
) -> TypologyRule:
    """A case Author deploys, with no second approver (ADR-109 ruling 4); audited. A drawn
    pattern (phase D) must be one the Author saved: it is read as theirs at every evaluation."""
    if body.params.typology == "pattern":
        try:
            await patterns_store.get_authorized(body.params.pattern_id, principal)
        except PatternNotFoundError:
            raise ReleaseRefused("only a pattern you saved can be deployed as a rule") from None
    rule = await typology_rules.create(principal, investigation.id, body)
    await audit.record(
        principal=principal,
        action="rule_deployed",
        investigation_id=investigation.id,
        resolved_query={"rule_id": rule.id, "rule": body.model_dump(mode="json")},
        result_cardinality=1,
    )
    return rule


@app.post(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/retire",
    dependencies=[Depends(require_right(Right.DEPLOY_RULES))],
)
async def retire_typology_rule(
    rule_id: str,
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    audit: AuditDep,
) -> TypologyRule:
    rule = await typology_rules.retire(rule_id, investigation.id, principal)
    await audit.record(
        principal=principal,
        action="rule_retired",
        investigation_id=investigation.id,
        resolved_query={"rule_id": rule.id},
        result_cardinality=1,
    )
    return rule


@app.get(
    "/v1/investigations/{investigation_id}/rules/audit",
    dependencies=[Depends(require_right(Right.READ_RULE_AUDIT))],
)
async def read_rule_audit(
    investigation: InvestigationAccessManagerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> RuleAuditPage:
    """The rule audit inspection read (ruling 1): the case's Authors, and the deployment admin
    through ADR-052 §4's safety net. An entry naming a node the reader cannot see is withheld whole,
    from the page and the total (rule 3)."""
    page = await readable_rule_audit(
        audit, graph, investigation.id, principal, offset=offset, limit=limit
    )
    # Who acted, by name — only for the entries this reader is served (ADR-106 decision 3).
    names = await principal_names.display_names(e.principal_id for e in page.entries)
    page = page.model_copy(
        update={
            "entries": [
                e.model_copy(update={"principal_name": names.get(e.principal_id)})
                for e in page.entries
            ]
        }
    )
    await audit.record(
        principal=principal,
        action="read_rule_audit",
        investigation_id=investigation.id,
        resolved_query={"offset": offset, "limit": limit, "actions": list(RULE_AUDIT_ACTIONS)},
        result_cardinality=len(page.entries),
    )
    return page


@app.get(
    "/v1/investigations/{investigation_id}/held-rows",
    dependencies=[Depends(require_right(Right.READ_HELD_ROWS))],
)
async def list_held_rows(
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    held_rows: HeldRowsDep,
    audit: AuditDep,
) -> list[HeldRow]:
    """Rows held by a failing pre-commit rule, waiting for review — only those whose marking
    the reader may read, filtered in the store's own query (rule 3)."""
    rows = await held_rows.list_authorized(investigation.id, principal)
    await audit.record(
        principal=principal,
        action="list_held_rows",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=len(rows),
    )
    return rows


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/held-rows/release",
    dependencies=[Depends(require_right(Right.DECIDE_HELD_ROWS))],
)
async def release_held_rows_route(
    investigation: InvestigationAuthorDep,
    recipe: RunnableStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.LOADER))],
    body: HeldRowDecision,
    graph: GraphDep,
    ontology: OntologyDep,
    analytics: AnalyticsDep,
    media: MediaDep,
    repo_root: RecipesRepoRootDep,
    audit: AuditDep,
    valkey: ValkeyDep,
    handling_scheme: HandlingSchemeDep,
    alerts_store: AlertsStoreDep,
    principal_resolver: PrincipalResolverDep,
    typology_rules: TypologyRulesDep,
    held_rows: HeldRowsDep,
    screening_lists: ScreeningListsDep,
    compute: ComputeDep,
    kyc_expiries: KycExpiriesDep,
    patterns_store: PatternsStoreDep,
    recipe_runs: RecipeRunsDep,
) -> LoadReportView:
    """A reviewer releases named held rows of one load: they are loaded now, under a new load
    id, with their provenance as it would have been. The case's rules judge them again, but a
    failing rule no longer holds them (ruling 1: the release is the human judgement)."""
    held = [
        await held_rows.get_authorized(held_id, investigation.id, principal)
        for held_id in dict.fromkeys(body.ids)
    ]
    if any(h.status != "held" for h in held):
        raise ReleaseRefused("a named row was already released or rejected")
    rules = await _rule_gate(
        investigation.id,
        loader=principal,
        graph=graph,
        analytics=analytics,
        scheme=handling_scheme,
        typology_rules=typology_rules,
        held_rows=held_rows,
        alerts_store=alerts_store,
        audit=audit,
        valkey=valkey,
        principal_resolver=principal_resolver,
        fail_closed=False,
        screening=screening_lists,
        compute=compute,
        expiries=kyc_expiries,
        patterns=patterns_store,
    ) or RuleGate(
        rules=[],
        investigation_id=investigation.id,
        graph=graph,
        analytics=analytics,
        scheme=handling_scheme,
        alert_store=alerts_store,
        audit=audit,
        valkey=valkey,
        principal_for_owner=_owner_resolver(principal, principal_resolver),
        loader=principal,
        held_store=held_rows,
        fail_closed=False,
    )
    assert recipe.git_path is not None
    load_id = new_id()
    # ADR-127 decision 6 and Amendment 5: a release is a load of its own. Its ledger run starts
    # before the release, as any run does, and its record is written when the release's graph
    # transaction commits, kept with the load its rows were held by so that reverting that load can
    # revert this one first.
    released_from = released_from_of(held)
    released_at = datetime.now(UTC)
    run_id = await recipe_runs.start(
        recipe_id=recipe.recipe_id,
        recipe_version=recipe.version,
        investigation_id=investigation.id,
        trigger="release",
        slot=None,
        run_as=principal.id,
        source=resolve_source_handling(recipe),
        now=released_at,
    )
    sink = LedgerSink(
        recipe_runs,
        run_id,
        created_by=principal.id,
        investigation_id=investigation.id,
        started_at=released_at,
        released_from=released_from,
    )
    try:
        report = await release_held_rows(
            held,
            load_published_recipe(recipe, repo_root),
            principal,
            graph=graph,
            ontology=ontology,
            analytics=analytics,
            media=media,
            rules=rules,
            load_id=load_id,
            sink=sink,
        )
    except Exception as error:
        await recipe_runs.fail(
            run_id,
            failure=f"{type(error).__name__}: {error}"[:1000],
            now=datetime.now(UTC),
            markings=sink.markings,
        )
        raise
    await recipe_runs.finish(run_id, report=report, now=datetime.now(UTC))
    decided = await held_rows.decide_for_reader(
        [h.id for h in held], investigation.id, principal, status="released", reason=body.reason
    )
    await audit.record(
        principal=principal,
        action="rows_released",
        investigation_id=investigation.id,
        resolved_query={
            "load_id": load_id,
            "held_ids": [h.id for h in decided],
            "rows": [h.row_index for h in decided],
            "reason": body.reason,
        },
        result_cardinality=len(decided),
    )
    return report_view(report, principal, handling_scheme)


@app.post(
    "/v1/investigations/{investigation_id}/held-rows/reject",
    dependencies=[Depends(require_right(Right.DECIDE_HELD_ROWS))],
)
async def reject_held_rows(
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    body: HeldRowDecision,
    held_rows: HeldRowsDep,
    audit: AuditDep,
) -> list[HeldRow]:
    """Named held rows are rejected: never loaded, kept as the record of what was refused. A
    rejection says why."""
    if not (body.reason and body.reason.strip()):
        raise ReleaseRefused("a rejection needs its reason")
    decided = await held_rows.decide_for_reader(
        body.ids, investigation.id, principal, status="rejected", reason=body.reason
    )
    await audit.record(
        principal=principal,
        action="rows_rejected",
        investigation_id=investigation.id,
        resolved_query={
            "held_ids": [h.id for h in decided],
            "rows": [h.row_index for h in decided],
            "reason": body.reason,
        },
        result_cardinality=len(decided),
    )
    return decided


# --- the delta stream --------------------------------------------------------


# --- the Admin area: people and dashboards (ADR-110 Amendment 1, ADR-112) ------------------------


@app.get("/v1/admin/people", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))])
async def list_people_route(
    principal: PrincipalDep, identity_admin: IdentityAdminDep, audit: AuditDep
) -> list[PersonAccount]:
    """Every person in the realm with their roles, clearance and unit — never a service account."""
    people = await identity_admin.list_people()
    await audit.record(principal=principal, action="list_people", resolved_query={},
                       result_cardinality=len(people))  # fmt: skip
    return people


@app.put(
    "/v1/admin/people/{user_id}/roles", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))]
)
async def set_person_roles_route(
    user_id: str,
    body: RolesInput,
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    audit: AuditDep,
) -> PersonAccount:
    """A person's roles, set whole — the four roles, `right:<name>` grants and the old role names;
    anything else is refused before the identity provider is asked (ADR-112 Amendment 1)."""
    person = await identity_admin.set_roles(user_id, body.roles)
    await audit.record(principal=principal, action="set_person_roles",
                       resolved_query={"user_id": user_id, "roles": person.roles},
                       result_cardinality=1)  # fmt: skip
    return person


def _within_your_reach(
    principal: Principal, access: AccessInput, handling_scheme: HandlingScheme
) -> None:
    """Nobody is given more than the administrator holds (ADR-114 Amendment 5) — the dashboard rule
    (rule 3) for people: a clearance above one's own, or a handling code one cannot receive, would
    be a way to read above them. Checked before the identity provider is asked."""
    order = list(handling_scheme.classification)
    if access.clearance not in order:
        raise UnknownRoleError(f"{access.clearance} is not a classification of this deployment")
    codes = access.receivable_handling_codes
    unknown = [c for c in codes if c not in handling_scheme.handling_codes]
    if unknown:
        raise UnknownRoleError(f"not a handling code of this deployment: {', '.join(unknown)}")
    if principal.clearance not in order or order.index(access.clearance) > order.index(
        principal.clearance
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "above_your_clearance", "clearance": access.clearance},
        )
    beyond = sorted(set(codes) - set(principal.receivable_handling_codes))
    if beyond:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "handling_code_you_do_not_hold", "codes": beyond},
        )


@app.post(
    "/v1/admin/people",
    status_code=201,
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def invite_person_route(
    body: InviteInput,
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> SignInDelivery:
    """A new person (ADR-114 Amendment 5). The one-time code, when there is one, is in this answer
    only — never in the audit record, never stored."""
    _within_your_reach(principal, body, handling_scheme)
    made = await identity_admin.invite(body)
    await audit.record(principal=principal, action="invite_person",
                       resolved_query={"user_id": made.person.id, "username": made.person.username,
                                       "roles": made.person.roles, "clearance": body.clearance,
                                       "org_unit": body.org_unit, "delivery": made.delivery},
                       result_cardinality=1)  # fmt: skip
    return made


@app.put(
    "/v1/admin/people/{user_id}/access", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))]
)
async def set_person_access_route(
    user_id: str,
    body: AccessInput,
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> PersonAccount:
    """A person's clearance, unit and receivable handling codes — none above the administrator's."""
    _within_your_reach(principal, body, handling_scheme)
    person = await identity_admin.set_access(user_id, body)
    await audit.record(principal=principal, action="set_person_access",
                       resolved_query={"user_id": user_id, "clearance": body.clearance,
                                       "org_unit": body.org_unit,
                                       "receivable_handling_codes": body.receivable_handling_codes},
                       result_cardinality=1)  # fmt: skip
    return person


@app.post(
    "/v1/admin/people/{user_id}/disable",
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def disable_person_route(
    user_id: str, principal: PrincipalDep, identity_admin: IdentityAdminDep, audit: AuditDep
) -> PersonAccount:
    """Disabled at once: open sessions end too. Never one's own account — an administrator who did
    that by mistake would have no way back in."""
    if user_id == principal.id:
        raise HTTPException(status_code=409, detail={"error": "cannot_disable_yourself"})
    person = await identity_admin.set_enabled(user_id, False)
    await audit.record(principal=principal, action="disable_person",
                       resolved_query={"user_id": user_id}, result_cardinality=1)  # fmt: skip
    return person


@app.post(
    "/v1/admin/people/{user_id}/enable",
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def enable_person_route(
    user_id: str, principal: PrincipalDep, identity_admin: IdentityAdminDep, audit: AuditDep
) -> PersonAccount:
    person = await identity_admin.set_enabled(user_id, True)
    await audit.record(principal=principal, action="enable_person",
                       resolved_query={"user_id": user_id}, result_cardinality=1)  # fmt: skip
    return person


@app.post(
    "/v1/admin/people/{user_id}/reset-sign-in",
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def reset_person_sign_in_route(
    user_id: str, principal: PrincipalDep, identity_admin: IdentityAdminDep, audit: AuditDep
) -> SignInDelivery:
    """A new way in for someone locked out: their sessions end, and they choose a new password at
    next sign-in — through an emailed link, or the one-time code in this answer only."""
    reset = await identity_admin.reset_sign_in(user_id)
    await audit.record(principal=principal, action="reset_person_sign_in",
                       resolved_query={"user_id": user_id, "delivery": reset.delivery},
                       result_cardinality=1)  # fmt: skip
    return reset


@app.get("/v1/admin/demo-packs", dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))])
async def list_demo_packs_route(
    principal: PrincipalDep, investigations: InvestigationsDep, audit: AuditDep
) -> list[DemoPackStatus]:
    """The demo packs (ADR-114 Amendment 5, the owner's "Show and explain"): each shipped pack and
    the command that adds it on the host — the Conduit has no control of Docker and runs nothing.
    "Loaded" is said only for a case this administrator can open: naming one they cannot would
    disclose that it exists."""
    from scripts.demo_packs import packs

    opened = {case.name: case.id for case, _ in await investigations.list_for(principal)}
    listed: list[DemoPackStatus] = []
    for each in packs():
        command = f"ospreyflow demo add {each.id}"
        if each.download is not None:
            command += f" --file <the downloaded {each.download.filename}>"
        listed.append(DemoPackStatus(
            id=each.id, title=each.title, shows=each.shows,
            delivery="download" if each.download is not None else "seed",
            licence=each.licence, attribution=each.attribution, case_name=each.case_name,
            loaded_case_id=opened.get(each.case_name), command=command,
            source_page=each.download.source_page if each.download else None,
            size_bytes=each.download.size_bytes if each.download else None,
            real_data=each.real_data,
        ))  # fmt: skip
    await audit.record(principal=principal, action="list_demo_packs", resolved_query={},
                       result_cardinality=len(listed))  # fmt: skip
    return listed


@app.get("/v1/admin/dashboards", dependencies=[Depends(require_right(Right.MANAGE_DASHBOARDS))])
async def list_dashboards_route(
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    freshness: ReportFreshnessDep,
    audit: AuditDep,
) -> list[DashboardIdentity]:
    """Each dashboard identity, with how fresh its figures are in the reporting mart (aggregates
    only: never which cases it reads)."""
    pulled = await freshness.by_dashboard()
    dashboards = [
        d.model_copy(update=pulled[d.client_id].model_dump()) if d.client_id in pulled else d
        for d in await identity_admin.list_dashboards()
    ]
    await audit.record(principal=principal, action="list_dashboards", resolved_query={},
                       result_cardinality=len(dashboards))  # fmt: skip
    return dashboards


@app.post(
    "/v1/admin/dashboards",
    status_code=201,
    dependencies=[Depends(require_right(Right.MANAGE_DASHBOARDS))],
)
async def register_dashboard_route(
    body: DashboardInput,
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> RegisteredDashboard:
    """A dashboard identity (ADR-111 decision 7). Its clearance may not exceed the registering
    administrator's own — otherwise registering a dashboard would be a way to read above one's
    clearance (rule 3). The secret is in this answer only."""
    order = list(handling_scheme.classification)
    if body.clearance not in order:
        raise UnknownRoleError(f"{body.clearance} is not a classification of this deployment")
    if principal.clearance not in order or order.index(body.clearance) > order.index(
        principal.clearance
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "dashboard_above_your_clearance", "clearance": body.clearance},
        )
    made = await identity_admin.create_dashboard(
        body.name, clearance=body.clearance, org_unit=body.org_unit
    )
    await audit.record(principal=principal, action="register_dashboard",
                       resolved_query={"client_id": made.dashboard.client_id,
                                       "clearance": body.clearance, "org_unit": body.org_unit},
                       result_cardinality=1)  # fmt: skip
    return made


@app.delete(
    "/v1/admin/dashboards/{client_id}",
    status_code=204,
    dependencies=[Depends(require_right(Right.MANAGE_DASHBOARDS))],
)
async def remove_dashboard_route(
    client_id: str, principal: PrincipalDep, identity_admin: IdentityAdminDep, audit: AuditDep
) -> Response:
    await identity_admin.delete_dashboard(client_id)
    await audit.record(principal=principal, action="remove_dashboard",
                       resolved_query={"client_id": client_id}, result_cardinality=1)  # fmt: skip
    return Response(status_code=204)


# --- Schedules and runs (ADR-110 decision 8, Amendment 2) -----------------------------------------


def _schedule_run_view(
    run: RecipeRun, reader: Principal, scheme: HandlingScheme
) -> ScheduleRunView:
    """A ledger row for `reader`: a run's counts, and the words of a load's failure, only where the
    reader may view the source (rule 3) — the scheduler's own words for a slot it did not run are
    its own, not the source's, and are always shown."""
    view = ScheduleRunView(
        run_id=run.run_id,
        trigger=run.trigger,
        slot=run.slot,
        started_at=run.started_at,
        finished_at=run.finished_at,
        outcome=run.outcome,
        run_as=run.run_as,
        failure=run.failure if run.outcome not in ("failed", "succeeded", "running") else None,
    )
    # Rule 3, ADR-127 Amendment 23: the counts include every row the run wrote, at every marking it
    # recorded, so each is judged beside the source's own (a run written before the column records
    # the source alone).
    if not may_see_counts([run.source, *run.markings], reader, scheme):
        return view.model_copy(update={"withheld": True})
    return view.model_copy(
        update={
            "rows_read": run.rows_read,
            "nodes_created": run.nodes_created,
            "nodes_referenced": run.nodes_referenced,
            "edges_created": run.edges_created,
            "rows_rejected": run.rows_rejected,
            "rows_held": run.rows_held,
            "load_id": run.load_id,
            "failure": run.failure,
            "file": run.source_file.rsplit("|", 2)[0] if run.source_file else None,
        }
    )


async def _admin_schedule(
    recipe: StudioRecipeDraft, runs: RecipeRunStore, reader: Principal, scheme: HandlingScheme
) -> AdminSchedule:
    zone = recipe.schedule_timezone or DEFAULT_TIMEZONE
    latest = await runs.for_recipe(recipe.recipe_id, limit=1)
    return AdminSchedule(
        recipe_id=recipe.recipe_id,
        label=recipe.label,
        case_id=recipe.schedule_case,
        cron=recipe.schedule_cron,
        watch=recipe.schedule_watch,
        timezone=zone,
        schedule=_schedule_in_words(recipe) or "",
        owner=recipe.schedule_owner,
        next_run=None
        if recipe.schedule_paused or recipe.schedule_cron is None
        else next_slot(recipe.schedule_cron, zone, after=datetime.now(UTC)),
        paused=recipe.schedule_paused,
        paused_reason=recipe.schedule_paused_reason,
        flagged=recipe.status is StudioRecipeStatus.FLAGGED,
        last_run=_schedule_run_view(latest[0], reader, scheme) if latest else None,
    )


def _schedule_in_words(recipe: StudioRecipeDraft) -> str | None:
    """A recipe's schedule and folder watch in words (ADR-110 decision 7, Amendment 4); `None`
    for a recipe run only by hand."""
    zone = recipe.schedule_timezone or DEFAULT_TIMEZONE
    parts = [describe(recipe.schedule_cron, zone)] if recipe.schedule_cron else []
    if recipe.schedule_watch and recipe.dataset_id:
        parts.append(describe_watch(recipe.schedule_watch, recipe.dataset_id))
    return "; and ".join(parts) or None


async def _scheduled_recipe(studio_recipes: StudioRecipeStore, recipe_id: str) -> StudioRecipeDraft:
    for recipe in await studio_recipes.scheduled():
        if recipe.recipe_id == recipe_id:
            return recipe
    raise HTTPException(status_code=404, detail={"error": "schedule_not_found"})


@app.get(
    "/v1/investigations/{investigation_id}/data-feeds",
    dependencies=[Depends(require_right(Right.READ_DATA_FEEDS))],
)
async def data_feeds_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    recipe_runs: RecipeRunsDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> list[DataFeed]:
    """The pipelines feeding the case's datasets (ADR-110 decision 9), read-only: each schedule in
    words, its next run and last outcome — a run's counts only where the reader may view the source
    (rule 3). Viewer level: how fresh a case's data is is for everyone who reads the case."""
    feeds: list[DataFeed] = []
    for recipe in await studio_recipes.feeding(principal.datasets or []):
        zone = recipe.schedule_timezone or DEFAULT_TIMEZONE
        latest = await recipe_runs.for_recipe(recipe.recipe_id, limit=1)
        scheduled = recipe.schedule_cron is not None or recipe.schedule_watch is not None
        feeds.append(
            DataFeed(
                recipe_id=recipe.recipe_id,
                label=recipe.label,
                schedule=_schedule_in_words(recipe),
                next_run=next_slot(recipe.schedule_cron, zone, after=datetime.now(UTC))
                if recipe.schedule_cron and not recipe.schedule_paused
                else None,
                paused=scheduled and recipe.schedule_paused,
                flagged=recipe.status is StudioRecipeStatus.FLAGGED,
                last_run=_schedule_run_view(latest[0], principal, handling_scheme)
                if latest
                else None,
            )
        )
    await audit.record(principal=principal, action="list_data_feeds",
                       investigation_id=investigation.id, resolved_query={},
                       result_cardinality=len(feeds))  # fmt: skip
    return feeds


@app.get("/v1/admin/schedules", dependencies=[Depends(require_right(Right.OPERATE_SCHEDULES))])
async def list_schedules_route(
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    recipe_runs: RecipeRunsDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> list[AdminSchedule]:
    """Every scheduled recipe across the deployment (ADR-110 decision 8): its metadata and last
    outcome for every recipe; a run's counts only where the administrator may view the source."""
    listed = [
        await _admin_schedule(recipe, recipe_runs, principal, handling_scheme)
        for recipe in await studio_recipes.scheduled()
    ]
    await audit.record(principal=principal, action="list_schedules", resolved_query={},
                       result_cardinality=len(listed))  # fmt: skip
    return listed


@app.get(
    "/v1/admin/schedules/{recipe_id}/runs",
    dependencies=[Depends(require_right(Right.OPERATE_SCHEDULES))],
)
async def schedule_runs_route(
    recipe_id: str,
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    recipe_runs: RecipeRunsDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> list[ScheduleRunView]:
    await _scheduled_recipe(studio_recipes, recipe_id)
    history = [
        _schedule_run_view(run, principal, handling_scheme)
        for run in await recipe_runs.for_recipe(recipe_id)
    ]
    await audit.record(principal=principal, action="list_schedule_runs",
                       resolved_query={"recipe_id": recipe_id},
                       result_cardinality=len(history))  # fmt: skip
    return history


@app.post(
    "/v1/admin/schedules/{recipe_id}/pause",
    dependencies=[Depends(require_right(Right.OPERATE_SCHEDULES))],
)
async def pause_schedule_route(
    recipe_id: str,
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    recipe_runs: RecipeRunsDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
    body: PauseScheduleInput | None = None,
) -> AdminSchedule:
    await _scheduled_recipe(studio_recipes, recipe_id)
    reason = body.reason.strip() if body and body.reason and body.reason.strip() else None
    words = f"paused by {principal.id}" + (f": {reason}" if reason else "")
    await studio_recipes.set_paused(recipe_id, paused=True, reason=words)
    await audit.record(principal=principal, action="pause_schedule",
                       resolved_query={"recipe_id": recipe_id, "reason": reason},
                       result_cardinality=1)  # fmt: skip
    recipe = await _scheduled_recipe(studio_recipes, recipe_id)
    return await _admin_schedule(recipe, recipe_runs, principal, handling_scheme)


def get_schedule_executor(request: Request) -> ScheduleExecutor:
    return request.app.state.schedule_executor  # type: ignore[no-any-return]


ScheduleExecutorDep = Annotated[ScheduleExecutor, Depends(get_schedule_executor)]


@app.exception_handler(ScheduleRunRefused)
async def _schedule_run_refused_handler(request: Request, exc: ScheduleRunRefused) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "run_refused", "detail": str(exc)})


@app.post(
    "/v1/admin/schedules/{recipe_id}/run",
    dependencies=[Depends(require_right(Right.OPERATE_SCHEDULES))],
)
async def run_schedule_now_route(
    recipe_id: str,
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    recipe_runs: RecipeRunsDep,
    handling_scheme: HandlingSchemeDep,
    executor: ScheduleExecutorDep,
    audit: AuditDep,
) -> AdminSchedule:
    """*Run now* (ADR-110 Amendment 3, point 2): at once, **as the schedule's owner**, with every
    check a scheduled slot gets — refused in words (409) if the owner may not run it. The
    administrator is named in the audit as who asked; the run itself is the owner's."""
    recipe = await _scheduled_recipe(studio_recipes, recipe_id)
    await audit.record(principal=principal, action="run_schedule_now",
                       resolved_query={"recipe_id": recipe_id, "run_as": recipe.schedule_owner},
                       result_cardinality=1)  # fmt: skip
    await executor.run_now(recipe)
    return await _admin_schedule(recipe, recipe_runs, principal, handling_scheme)


async def _commit_schedule(recipe: StudioRecipeDraft, repo_root: Path) -> None:
    """The recipe repository stays the record of a schedule too (`update_studio_recipe_schedule`):
    the recipe's YAML re-committed at its own path, the mapping and version unchanged, and the pins
    the row holds exactly as stored, none included (ADR-120 Amendment 2, decision 2)."""
    if recipe.row_template is None or recipe.ontology_version is None:
        return
    built = build_recipe(
        recipe,
        ontology_version=recipe.ontology_version,
        pack_versions=recipe.pack_versions,
        schedule_cron=recipe.schedule_cron,
        schedule_watch=recipe.schedule_watch,
    )
    await write_and_commit_recipe(built, repo_root=repo_root)


@app.put(
    "/v1/admin/schedules/{recipe_id}",
    dependencies=[Depends(require_right(Right.OPERATE_SCHEDULES))],
)
async def change_schedule_route(
    recipe_id: str,
    body: ChangeScheduleInput,
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    recipe_runs: RecipeRunsDep,
    handling_scheme: HandlingSchemeDep,
    repo_root: RecipesRepoRootDep,
    audit: AuditDep,
) -> AdminSchedule:
    """*Change schedule* (ADR-110 Amendment 3, point 2): a new time, refused in words if it could
    not be kept; **the owner is kept**, and the administrator named in the audit."""
    await _scheduled_recipe(studio_recipes, recipe_id)
    zone = body.timezone or DEFAULT_TIMEZONE
    validate_schedule(body.cron, zone)
    await studio_recipes.retime(recipe_id, cron=body.cron, timezone=zone, now=datetime.now(UTC))
    recipe = await _scheduled_recipe(studio_recipes, recipe_id)
    await _commit_schedule(recipe, repo_root)
    await audit.record(principal=principal, action="change_schedule",
                       resolved_query={"recipe_id": recipe_id, "cron": body.cron, "timezone": zone,
                                       "owner": recipe.schedule_owner},
                       result_cardinality=1)  # fmt: skip
    return await _admin_schedule(recipe, recipe_runs, principal, handling_scheme)


@app.post(
    "/v1/admin/schedules/{recipe_id}/resume",
    dependencies=[Depends(require_right(Right.OPERATE_SCHEDULES))],
)
async def resume_schedule_route(
    recipe_id: str,
    principal: PrincipalDep,
    studio_recipes: StudioRecipesDep,
    recipe_runs: RecipeRunsDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> AdminSchedule:
    await _scheduled_recipe(studio_recipes, recipe_id)
    await studio_recipes.set_paused(recipe_id, paused=False, reason=None)
    await audit.record(principal=principal, action="resume_schedule",
                       resolved_query={"recipe_id": recipe_id}, result_cardinality=1)  # fmt: skip
    recipe = await _scheduled_recipe(studio_recipes, recipe_id)
    return await _admin_schedule(recipe, recipe_runs, principal, handling_scheme)


@app.get("/v1/admin/system", dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))])
async def system_status_route(
    principal: PrincipalDep,
    graph: GraphDep,
    investigations: InvestigationsDep,
    valkey: ValkeyDep,
    identity_admin: IdentityAdminDep,
) -> SystemStatus:
    """Each component of the running deployment, asked now (ADR-110 Amendment 1, the *System*
    screen). The graph is asked as a principal of no datasets, so the check reads nothing."""

    async def check(name: str, probe: Callable[[], Awaitable[object]]) -> ComponentHealth:
        started = time.monotonic()
        try:
            await asyncio.wait_for(probe(), timeout=5.0)
            ok, detail = True, None
        except Exception as e:  # noqa: BLE001 - a component's failure is the answer, in words
            ok, detail = False, (str(e) or type(e).__name__)[:200]
        return ComponentHealth(name=name, ok=ok, millis=int((time.monotonic() - started) * 1000),
                               detail=detail)  # fmt: skip

    async def models() -> None:
        found = await readiness_module.deployment_readiness()
        if not found.ready:
            raise RuntimeError(found.problem or "a model is not yet present")

    nobody = principal.model_copy(update={"datasets": []})
    components = [
        await check("Graph store", lambda: graph.type_counts(nobody)),
        await check("Case and rule stores (Postgres)", lambda: investigations.list_for(principal)),
        await check("Working-set cache (Valkey)", lambda: valkey.ping()),
        await check("Model server", models),
        await check("Identity provider", identity_admin.reachable),
    ]
    # ADR-114 decision 11: each role's model and where it runs, from names only — never a key.
    statuses, notice = model_status(*routes_from_env(DeploymentModels.from_env(), os.environ))
    return SystemStatus(
        # ADR-114 Amendment 8: the version the deployment was rendered with, and the last check.
        version=os.environ.get("OSPREY_RELEASE_VERSION") or os.environ.get("OSPREY_VERSION"),
        components=components,
        models=statuses,
        model_notice=notice,
        update=read_update_notice(),
    )


# --- Trend reports (ADR-113 decisions 1 and 2) ---------------------------------------------


@app.get(
    "/v1/investigations/{investigation_id}/events/holders",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def case_event_holders_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    analytics: AnalyticsDep,
    audit: AuditDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    datasets: DatasetsDep,
) -> CaseEvents:
    """Whether this case holds events the reader may count and, when it holds none, which cases
    the reader can open read one of its datasets and do (ADR-099 Amendment 9). Each is counted as
    the reader, through the case's own event filter, so a hidden event makes no holder (rule 3); a
    case the reader holds no level on is never listed, so never named (ADR-052)."""

    async def holds(case_id: str) -> bool:
        scoped = await _case_event_filter(
            EventFilter(investigation_scope=case_id), principal, investigations, audit, working_set
        )
        found = await analytics.list_events(EventListRequest(filter=scoped, limit=1), principal)
        return found.total > 0

    if await holds(investigation.id):
        return CaseEvents(has_events=True)
    reads = set(await datasets.ids_of_case(investigation.id))
    held_by: list[CaseEventHolder] = []
    for case, _level in await investigations.list_for(principal):
        if case.id == investigation.id or not reads & set(await datasets.ids_of_case(case.id)):
            continue
        if await holds(case.id):
            held_by.append(CaseEventHolder(investigation_id=case.id, name=case.name))
    return CaseEvents(has_events=False, held_by=held_by)


@app.get(
    "/v1/investigations/{investigation_id}/trends/options",
    dependencies=[Depends(require_right(Right.RUN_ANALYSIS))],
)
async def trend_options_route(
    investigation: InvestigationViewerDep, ontology: OntologyDep
) -> TrendOptions:
    """The event types and properties a trend may use: this deployment's ontology, narrowed to
    the core types and the case's own domain packs (ADR-126 decision 6)."""
    return trend_options(ontology, investigation.domains)


async def _trend_figures(
    defn: TrendDefinitionInput,
    case: Investigation,
    principal: Principal,
    ontology: OntologySchema,
    analytics: AnalyticsPort,
    investigations: InvestigationStore,
    audit: AuditWriter,
    working_set: WorkingSetService,
    handling_scheme: HandlingScheme,
) -> TrendFigures:
    """The trend counted for this reader now (rule 3): the case's own events, a branch's inherited
    ones with them, nothing the reader may not see."""
    validate_definition(defn, ontology)
    now = datetime.now(UTC)
    request, start = to_request(defn, ontology, case.id, now)
    scoped = await _case_event_filter(request.filter, principal, investigations, audit, working_set)
    result = await analytics.trend(request.model_copy(update={"filter": scoped}), principal)
    result = name_series(result, defn, ontology)
    return TrendFigures(
        definition=TrendDefinitionInput.model_validate(
            defn.model_dump(include=set(TrendDefinitionInput.model_fields))
        ),
        result=result,
        as_of=now,
        window_start=start,
        marking=highest(result.classifications, list(handling_scheme.classification)),
    )


@app.post(
    "/v1/investigations/{investigation_id}/trends/preview",
    dependencies=[Depends(require_right(Right.RUN_ANALYSIS))],
)
async def preview_trend(
    body: TrendDefinitionInput,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    ontology: OntologyDep,
    analytics: AnalyticsDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
    working_set: WorkingSetDep,
    handling_scheme: HandlingSchemeDep,
) -> TrendFigures:
    check_in_case_domains(body, ontology, investigation.domains)
    figures = await _trend_figures(body, investigation, principal, ontology, analytics,
                                   investigations, audit, working_set, handling_scheme)  # fmt: skip
    await audit.record(principal=principal, action="preview_trend",
                       investigation_id=investigation.id,
                       resolved_query=body.model_dump(mode="json"),
                       result_cardinality=figures.result.events)  # fmt: skip
    return figures


@app.post(
    "/v1/investigations/{investigation_id}/trends",
    status_code=201,
    dependencies=[Depends(require_right(Right.RUN_ANALYSIS))],
)
async def save_trend(
    body: TrendDefinitionInput,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    ontology: OntologyDep,
    trends: TrendStoreDep,
    audit: AuditDep,
) -> TrendDefinition:
    """Saving writes to the case, so it needs Editor; the definition is checked first."""
    validate_definition(body, ontology)
    check_in_case_domains(body, ontology, investigation.domains)
    saved = await trends.create(investigation.id, body, principal)
    await audit.record(principal=principal, action="save_trend", investigation_id=investigation.id,
                       resolved_query={"trend": saved.id, "title": saved.title},
                       result_cardinality=1)  # fmt: skip
    return saved


@app.get(
    "/v1/investigations/{investigation_id}/trends",
    dependencies=[Depends(require_right(Right.RUN_ANALYSIS))],
)
async def list_trends(
    investigation: InvestigationViewerDep, trends: TrendStoreDep, ontology: OntologyDep
) -> list[TrendDefinition]:
    """The case's trends, each marked when it uses a link type outside the case's domain packs as
    they stand now (ADR-126 decision 6)."""
    return [
        mark_outside_case_domains(t, ontology, investigation.domains)
        for t in await trends.list_for_case(investigation.id)
    ]


@app.get(
    "/v1/investigations/{investigation_id}/trends/{trend_id}/figures",
    dependencies=[Depends(require_right(Right.RUN_ANALYSIS))],
)
async def trend_figures(
    trend_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    ontology: OntologyDep,
    analytics: AnalyticsDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
    working_set: WorkingSetDep,
    handling_scheme: HandlingSchemeDep,
    trends: TrendStoreDep,
) -> TrendFigures:
    saved = await trends.get(investigation.id, trend_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="no such trend in this case")
    figures = await _trend_figures(saved, investigation, principal, ontology, analytics,
                                   investigations, audit, working_set, handling_scheme)  # fmt: skip
    await audit.record(principal=principal, action="read_trend", investigation_id=investigation.id,
                       resolved_query={"trend": trend_id},
                       result_cardinality=figures.result.events)  # fmt: skip
    return figures


@app.delete(
    "/v1/investigations/{investigation_id}/trends/{trend_id}",
    status_code=204,
    dependencies=[Depends(require_right(Right.RUN_ANALYSIS))],
)
async def delete_trend(
    trend_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    trends: TrendStoreDep,
    audit: AuditDep,
) -> None:
    if not await trends.delete(investigation.id, trend_id):
        raise HTTPException(status_code=404, detail="no such trend in this case")
    await audit.record(principal=principal, action="delete_trend",
                       investigation_id=investigation.id,
                       resolved_query={"trend": trend_id}, result_cardinality=1)  # fmt: skip


@app.exception_handler(TrendDefinitionRefused)
async def _trend_refused(request: Request, exc: TrendDefinitionRefused) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "trend_refused", "detail": str(exc)})


@app.exception_handler(TrendLimitExceeded)
async def _trend_limit(request: Request, exc: TrendLimitExceeded) -> JSONResponse:
    body = TrendLimitExceededBody(cap_kind=exc.cap_kind, cap=exc.cap, would_be=exc.would_be)  # type: ignore[arg-type]
    return JSONResponse(status_code=409, content=body.model_dump())


# --- Case report packs (ADR-113 decisions 3 to 5 and 7, Amendment 1) -------------------------


async def _pack_or_404(packs: PackStore, case_id: str, pack_id: str) -> ReportPack:
    pack = await packs.get(case_id, pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="no such pack in this case")
    return pack


def _named_version(v: PackVersionSummary, names: dict[str, str]) -> PackVersionSummary:
    return v.model_copy(update={
        "published_by_name": names.get(v.published_by),
        "withdrawn_by_name": names.get(v.withdrawn_by) if v.withdrawn_by else None,
    })  # fmt: skip


async def _named_packs(
    found: list[ReportPack], principal_names: PrincipalNameDirectory
) -> list[ReportPack]:
    """ADR-106: each version's publisher and withdrawer named — only the people these versions,
    which the response carries, already show."""
    names = await principal_names.display_names(
        who for p in found for v in p.versions for who in (v.published_by, v.withdrawn_by) if who
    )
    return [
        p.model_copy(update={"versions": [_named_version(v, names) for v in p.versions]})
        for p in found
    ]


async def _readable_draft(
    packs: PackStore,
    pack_id: str,
    reader: Principal,
    scheme: HandlingScheme,
    graph: GraphPort,
    case_id: str,
) -> tuple[list[StoredPackItem], list[StoredPackItem], int]:
    """The draft's items in order, those this reader may see, and how many they may not."""
    items = await packs.items(pack_id)
    shown, withheld = await readable(items, reader, scheme, graph, case_id)
    return items, shown, withheld


@app.post(
    "/v1/investigations/{investigation_id}/packs",
    status_code=201,
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def create_pack(
    body: PackInput,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    audit: AuditDep,
) -> ReportPack:
    pack = await packs.create(investigation.id, body.title, principal)
    await audit.record(
        principal=principal,
        action="create_pack",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id, "title": pack.title},
        result_cardinality=1,
    )
    return pack


@app.get(
    "/v1/investigations/{investigation_id}/packs",
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def list_packs(
    investigation: InvestigationViewerDep, packs: PackStoreDep, principal_names: PrincipalNamesDep
) -> list[ReportPack]:
    return await _named_packs(await packs.list_for_case(investigation.id), principal_names)


@app.get(
    "/v1/investigations/{investigation_id}/packs/{pack_id}",
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def read_pack(
    pack_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> PackDraft:
    """The draft as this reader may see it: the items withheld from them are counted, not named."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    _, shown, withheld = await _readable_draft(
        packs, pack.id, principal, scheme, graph, investigation.id
    )
    served = [i.served() for i in shown]
    await audit.record(
        principal=principal,
        action="read_pack",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id},
        result_cardinality=len(served),
    )
    (named,) = await _named_packs([pack], principal_names)
    return PackDraft(
        pack=named, items=served, withheld=withheld > 0, marking=highest_marking(served, scheme)
    )


@app.post(
    "/v1/investigations/{investigation_id}/packs/{pack_id}/items",
    status_code=201,
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def add_pack_item(
    pack_id: str,
    body: AddPackItem,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    judgements_store: JudgementsStoreDep,
    trends: TrendStoreDep,
    ontology: OntologyDep,
    analytics: AnalyticsDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
) -> PackItem:
    """The content is read and frozen here, as the adder — never taken from the request, except a
    caption and a note's own words."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    item = await _build_pack_item(
        body,
        investigation,
        principal,
        graph,
        scheme,
        judgements_store,
        trends,
        ontology,
        analytics,
        investigations,
        audit,
        working_set,
    )
    await packs.add_item(pack.id, item)
    await audit.record(
        principal=principal,
        action="add_pack_item",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id, "item": item.id, "kind": item.kind},
        result_cardinality=1,
    )
    return item.served()


async def _build_pack_item(
    body: AddPackItem,
    case: Investigation,
    principal: Principal,
    graph: GraphPort,
    scheme: HandlingScheme,
    judgements_store: JudgementStore,
    trends: TrendStore,
    ontology: OntologySchema,
    analytics: AnalyticsPort,
    investigations: InvestigationStore,
    audit: AuditWriter,
    working_set: WorkingSetService,
) -> StoredPackItem:
    if body.kind == "trend":
        saved = await trends.get(case.id, body.trend_id) if body.trend_id else None
        if saved is None:
            raise HTTPException(status_code=404, detail="no such trend in this case")
        figures = await _trend_figures(
            saved, case, principal, ontology, analytics, investigations, audit, working_set, scheme
        )
        return trend_item(saved.id, figures, principal, scheme)
    if body.kind == "assessment":
        try:
            judgement = await judgements_store.get_authorized(body.judgement_id or "", principal)
        except JudgementNotFoundError:
            judgement = None
        built = (
            await assessment_item(judgement, principal, scheme, graph)
            if judgement is not None and judgement.investigation_id == case.id
            else None
        )
        if built is None:
            raise HTTPException(status_code=404, detail="no such assessment in this case")
        return built
    if body.kind == "entity":
        node = await graph.get_node(body.node_id, principal) if body.node_id else None
        if node is None:
            raise HTTPException(status_code=404, detail="no such entity")
        return entity_item(node, body.caption or "", principal, scheme)
    if not body.text:
        raise PackItemRefused("a note needs its words")
    return note_item(body.text, body.classification, body.handling_code, principal, scheme)


@app.delete(
    "/v1/investigations/{investigation_id}/packs/{pack_id}/items/{item_id}",
    status_code=204,
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def remove_pack_item(
    pack_id: str,
    item_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> None:
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    _, shown, _ = await _readable_draft(packs, pack.id, principal, scheme, graph, investigation.id)
    if item_id not in {i.id for i in shown} or not await packs.remove_item(pack.id, item_id):
        raise HTTPException(status_code=404, detail="no such item in this pack")
    await audit.record(
        principal=principal,
        action="remove_pack_item",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id, "item": item_id},
        result_cardinality=1,
    )


@app.put(
    "/v1/investigations/{investigation_id}/packs/{pack_id}/order",
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def reorder_pack(
    pack_id: str,
    body: PackOrder,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> PackDraft:
    """Only the reader's own items move; each item withheld from them keeps its place."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    items, shown, withheld = await _readable_draft(
        packs, pack.id, principal, scheme, graph, investigation.id
    )
    try:
        order = reorder_visible([i.id for i in items], {i.id for i in shown}, body.item_ids)
    except ValueError as exc:
        raise PackItemRefused(str(exc)) from exc
    await packs.set_order(pack.id, order)
    await audit.record(
        principal=principal,
        action="reorder_pack",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id},
        result_cardinality=len(order),
    )
    by_id = {i.id: i for i in shown}
    served = [by_id[i].served() for i in body.item_ids]
    (named,) = await _named_packs(
        [await _pack_or_404(packs, investigation.id, pack_id)], principal_names
    )
    return PackDraft(
        pack=named,
        items=served,
        withheld=withheld > 0,
        marking=highest_marking(served, scheme),
    )


@app.post(
    "/v1/investigations/{investigation_id}/packs/{pack_id}/items/{item_id}/refresh",
    status_code=201,
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def refresh_pack_item(
    pack_id: str,
    item_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    judgements_store: JudgementsStoreDep,
    trends: TrendStoreDep,
    ontology: OntologyDep,
    analytics: AnalyticsDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
) -> PackItem:
    """A trend snapshot counted again, now, as the refresher; the earlier one stays in the
    history (decision 4)."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    _, shown, _ = await _readable_draft(packs, pack.id, principal, scheme, graph, investigation.id)
    old = next((i for i in shown if i.id == item_id), None)
    if old is None:
        raise HTTPException(status_code=404, detail="no such item in this pack")
    if old.kind != "trend" or old.trend_id is None:
        raise PackItemRefused("only a trend snapshot is refreshed")
    new = await _build_pack_item(
        AddPackItem(kind="trend", trend_id=old.trend_id),
        investigation,
        principal,
        graph,
        scheme,
        judgements_store,
        trends,
        ontology,
        analytics,
        investigations,
        audit,
        working_set,
    )
    if not await packs.replace_item(pack.id, old.id, new):
        raise HTTPException(status_code=404, detail="no such item in this pack")
    await audit.record(
        principal=principal,
        action="refresh_pack_item",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id, "item": old.id, "replaced_by": new.id},
        result_cardinality=1,
    )
    return new.served()


@app.get(
    "/v1/investigations/{investigation_id}/packs/{pack_id}/history",
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def pack_history(
    pack_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    principal_names: PrincipalNamesDep,
) -> PackHistory:
    (pack,) = await _named_packs(
        [await _pack_or_404(packs, investigation.id, pack_id)], principal_names
    )
    earlier = await packs.earlier_snapshots(pack.id)
    shown, withheld = await readable(earlier, principal, scheme, graph, investigation.id)
    return PackHistory(
        earlier_snapshots=[i.served() for i in shown], withheld=withheld > 0, versions=pack.versions
    )


@app.post(
    "/v1/investigations/{investigation_id}/packs/{pack_id}/publish",
    status_code=201,
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def publish_pack(
    pack_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> PublishedPack:
    """A new immutable version. Refused while the draft holds an item the publisher may not see:
    nobody publishes what they cannot read (Amendment 1)."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    items, _, withheld = await _readable_draft(
        packs, pack.id, principal, scheme, graph, investigation.id
    )
    if not items:
        raise PackItemRefused("an empty pack has nothing to publish")
    if withheld:
        raise PackHasWithheldItems()
    version = await packs.publish(pack.id, principal)
    await audit.record(
        principal=principal,
        action="publish_pack",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id, "version": version.version},
        result_cardinality=len(version.items),
    )
    served = [i.served() for i in version.items]
    return PublishedPack(
        pack_id=pack.id,
        investigation_id=investigation.id,
        title=pack.title,
        version=version.version,
        published_at=version.published_at,
        published_by=version.published_by,
        published_by_name=(await principal_names.display_names([version.published_by])).get(
            version.published_by
        ),
        items=served,
        withheld=False,
        marking=highest_marking(served, scheme),
    )


@app.post(
    "/v1/investigations/{investigation_id}/packs/{pack_id}/versions/{version}/withdraw",
    dependencies=[Depends(require_right(Right.RECORD_ASSESSMENT))],
)
async def withdraw_pack_version(
    pack_id: str,
    version: int,
    body: PackWithdrawal,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> ReportPack:
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    if not await packs.withdraw(pack.id, version, principal, body.reason):
        raise HTTPException(status_code=404, detail="no such published version")
    await audit.record(
        principal=principal,
        action="withdraw_pack",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id, "version": version, "reason": body.reason},
        result_cardinality=1,
    )
    (named,) = await _named_packs(
        [await _pack_or_404(packs, investigation.id, pack_id)], principal_names
    )
    return named


@app.get(
    "/v1/investigations/{investigation_id}/published",
    dependencies=[Depends(require_right(Right.READ_REPORTS))],
)
async def list_published_packs(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> list[PublishedPackSummary]:
    """*Reports → Published*: each pack's newest version not withdrawn."""
    found = await packs.published_for_case(investigation.id)
    await audit.record(
        principal=principal,
        action="list_published_packs",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=len(found),
    )
    names = await principal_names.display_names(v.published_by for _, v in found)
    return [
        PublishedPackSummary(
            pack_id=p.id,
            title=p.title,
            version=v.version,
            published_at=v.published_at,
            published_by=v.published_by,
            published_by_name=names.get(v.published_by),
        )
        for p, v in found
    ]


@app.get(
    "/v1/investigations/{investigation_id}/packs/{pack_id}/published",
    dependencies=[Depends(require_right(Right.READ_REPORTS))],
)
async def read_published_pack(
    pack_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> PublishedPack:
    """The newest published version as this reader may see it (decision 5): every read audited."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    version = await packs.latest_published(pack.id)
    if version is None:
        raise HTTPException(status_code=404, detail="this pack has no publication")
    shown, withheld = await readable(version.items, principal, scheme, graph, investigation.id)
    served = [i.served() for i in shown]
    await audit.record(
        principal=principal,
        action="read_published_pack",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id, "version": version.version},
        result_cardinality=len(served),
    )
    return PublishedPack(
        pack_id=pack.id,
        investigation_id=investigation.id,
        title=pack.title,
        version=version.version,
        published_at=version.published_at,
        published_by=version.published_by,
        published_by_name=(await principal_names.display_names([version.published_by])).get(
            version.published_by
        ),
        items=served,
        withheld=withheld > 0,
        marking=highest_marking(served, scheme),
    )


@app.post(
    "/v1/investigations/{investigation_id}/packs/{pack_id}/export",
    dependencies=[Depends(require_right(Right.EXPORT))],
)
async def export_pack_route(
    pack_id: str,
    body: PackExportRequest,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    packs: PackStoreDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    export_ledger: ExportLedgerDep,
    config: ConfigDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> PackExport:
    """The newest live publication through the export gate (ADR-113 decision 6, ADR-045/047): the
    approved manifest, from which the Glass renders the PDF. Editor and `export`, as every
    export."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    version = await packs.latest_published(pack.id)
    if version is None:
        raise HTTPException(status_code=404, detail="this pack has no publication to export")
    result = await export_pack(
        pack=pack,
        version=version,
        request=body,
        exporter=principal,
        scheme=scheme,
        graph=graph,
        ledger=export_ledger,
        policy=config.export_manifest_policy,
    )
    await audit.record(
        principal=principal,
        action="export_pack",
        investigation_id=investigation.id,
        resolved_query={
            "pack": pack.id,
            "version": version.version,
            "ledger_entry": result.ledger_entry_id,
        },
        result_cardinality=len(result.items),
        justification=body.justification,
    )
    # ADR-106: the two people the manifest prints, named; nobody else is looked up.
    names = await principal_names.display_names([result.published_by, result.mark.exported_by])
    return result.model_copy(update={
        "published_by_name": names.get(result.published_by),
        "mark": result.mark.model_copy(
            update={"exported_by_name": names.get(result.mark.exported_by)}
        ),
    })  # fmt: skip


@app.exception_handler(PackExportRefused)
async def _pack_export_refused(request: Request, exc: PackExportRefused) -> JSONResponse:
    return JSONResponse(status_code=403, content={"error": "export_refused", "detail": str(exc)})


@app.exception_handler(PackHasWithheldItems)
async def _pack_withheld(request: Request, exc: PackHasWithheldItems) -> JSONResponse:
    return JSONResponse(status_code=409, content=PackWithheldBody().model_dump())


@app.exception_handler(PackItemRefused)
async def _pack_refused(request: Request, exc: PackItemRefused) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "pack_refused", "detail": str(exc)})


async def _openable_dashboards(
    principal: Principal,
    embedder: SupersetEmbedder | None,
    identity_admin: IdentityAdmin,
    investigations: InvestigationStore,
    handling_scheme: HandlingScheme,
) -> list[EmbeddableDashboard]:
    """The Superset dashboards this person could open: each counted for an identity whose every
    figure they could compute themselves (ADR-111 Amendment 3, decision 2)."""
    if embedder is None:
        return []
    identities = await identity_admin.list_dashboards()
    boards = await embedder.embeddable(identities)
    if not boards:
        return []
    viewer_cases = {case.id for case, _ in await investigations.list_for(principal)}
    classification = list(handling_scheme.classification)
    openable = []
    for board in boards:
        identity = identity_for(board.slug, identities)
        if identity is None:
            continue
        identity_cases = {
            c.id for c, _ in await investigations.list_for(identity_principal(identity))
        }
        if may_open(principal, identity, classification=classification,
                    viewer_cases=viewer_cases, identity_cases=identity_cases):  # fmt: skip
            openable.append(board)
    return openable


@app.get("/v1/reports/dashboards", dependencies=[Depends(require_right(Right.READ_REPORTS))])
async def list_embedded_dashboards(
    principal: PrincipalDep,
    embedder: SupersetEmbedderDep,
    identity_admin: IdentityAdminDep,
    investigations: InvestigationsDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> list[EmbeddedDashboard]:
    """The Superset dashboards this person may open inside the Glass — nothing they could not count
    themselves (ADR-111 Amendment 3)."""
    boards = await _openable_dashboards(
        principal, embedder, identity_admin, investigations, handling_scheme
    )
    await audit.record(principal=principal, action="list_embedded_dashboards", resolved_query={},
                       result_cardinality=len(boards))  # fmt: skip
    return [EmbeddedDashboard(slug=b.slug, title=b.title) for b in boards]


@app.post(
    "/v1/reports/dashboards/{slug}/guest-token",
    dependencies=[Depends(require_right(Right.READ_REPORTS))],
)
async def embedded_dashboard_guest_token(
    slug: str,
    principal: PrincipalDep,
    embedder: SupersetEmbedderDep,
    identity_admin: IdentityAdminDep,
    investigations: InvestigationsDep,
    handling_scheme: HandlingSchemeDep,
    principal_names: PrincipalNamesDep,
    audit: AuditDep,
) -> DashboardGuestToken:
    """A five-minute, read-only guest token for one dashboard, its rows limited to the identity it
    was counted for. A dashboard this person may not open is the same 404 as one that does not
    exist."""
    boards = await _openable_dashboards(
        principal, embedder, identity_admin, investigations, handling_scheme
    )
    board = next((b for b in boards if b.slug == slug), None)
    if board is None or embedder is None:
        raise HTTPException(status_code=404, detail="no such dashboard")
    name = (await principal_names.display_names([principal.id])).get(principal.id, "")
    token, uuid = await embedder.guest_token(board, principal, name)
    await audit.record(principal=principal, action="embedded_dashboard_guest_token",
                       resolved_query={"dashboard": slug, "identity": board.client_id},
                       result_cardinality=1)  # fmt: skip
    return DashboardGuestToken(
        token=token, uuid=uuid, superset_origin=embedder.settings.public_origin
    )


@app.exception_handler(SupersetRefused)
async def _superset_refused(request: Request, exc: SupersetRefused) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "superset_refused", "detail": str(exc)})


@app.exception_handler(IdentityAdminRefused)
async def _identity_admin_refused(request: Request, exc: IdentityAdminRefused) -> JSONResponse:
    return JSONResponse(
        status_code=502, content={"error": "identity_provider_refused", "detail": str(exc)}
    )


@app.exception_handler(UnknownRoleError)
async def _unknown_role(request: Request, exc: UnknownRoleError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "not_allowed", "detail": str(exc)})


@app.exception_handler(PersonExistsError)
async def _person_exists(request: Request, exc: PersonExistsError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "person_exists",
                 "detail": "that sign-in name or email address is already held"},
    )  # fmt: skip


@app.exception_handler(DashboardExistsError)
async def _dashboard_exists(request: Request, exc: DashboardExistsError) -> JSONResponse:
    return JSONResponse(
        status_code=409, content={"error": "dashboard_exists", "client_id": str(exc)}
    )


@app.get("/v1/me/rights")
async def my_rights_route(principal: PrincipalDep) -> RightsResponse:
    """ADR-112: what the signed-in person may do, so the Glass and the Studio leave out what they
    would only refuse. Not a gate — every route still checks its own right."""
    return RightsResponse(rights=sorted(rights_for(principal.roles)))


@app.post("/v1/ws-ticket", response_model=WsTicketResponse)
async def issue_ws_ticket(principal: PrincipalDep, valkey: ValkeyDep) -> WsTicketResponse:
    """`06_DECISIONS.md` ADR-050 objection 8. Authenticated the ordinary way — the same bearer
    token every other `/v1` route already requires — this mints a short-lived, single-use ticket
    bound to the calling principal and returns it; the caller opens the delta WebSocket with
    `?ticket=<this>` instead of putting its own bearer token in that URL. See
    `services.api.ws_ticket`'s own module docstring for why a ticket, why Valkey, and why 30
    seconds."""
    ticket = await mint_ws_ticket(valkey, principal)
    return WsTicketResponse(ticket=ticket)


async def _authenticate_websocket(websocket: WebSocket) -> Principal:
    """`WebSocket` connections carry no `Authorization` header dependency
    injection the way an HTTP route does — the bearer token is read from
    the same header manually, once, before `accept()`.

    **A browser's native `WebSocket` cannot set that header at all.** Checkpoint 2's own fix —
    the long-lived bearer JWT as a `?token=` query parameter — closed the connectivity gap and
    opened a logging one: measured during ADR-050's own same-origin verification, the full access
    token appeared in the workspace's nginx access log, and `05_DEPLOYMENT.md` §7's own
    TLS-terminating reverse proxy logs it again. **ADR-050 objection 8, built:** `?ticket=`, a
    short-lived, single-use opaque value minted by `POST /v1/ws-ticket` and redeemed here via
    `services.api.ws_ticket.redeem_ws_ticket`'s atomic Valkey `GETDEL` — never the bearer token
    itself, so a ticket appearing anywhere it should not (a proxy log, this is not expected to
    happen, but the whole point of a ticket over a bearer token is that it stays true even if it
    does) is worthless the moment it is used once, and worthless anyway 30 seconds later. **A
    bearer token in the URL is refused outright, not merely no longer preferred** — the query
    parameter `_authenticate_websocket` reads is `ticket`, not `token`, and nothing here falls
    back to accepting the older shape. The `Authorization` header is still tried first, for a
    non-browser client (this phase's own `ws`-based integration test) that *can* set it.
    """
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[len("bearer ") :]
        resolver: PrincipalResolver = websocket.app.state.principal_resolver
        return resolver.resolve(token)

    ticket = websocket.query_params.get("ticket", "")
    if not ticket:
        raise PrincipalResolutionError("missing bearer token or ws-ticket")
    valkey: Valkey = websocket.app.state.valkey
    principal = await redeem_ws_ticket(valkey, ticket)
    if principal is None:
        raise PrincipalResolutionError("ws-ticket is missing, expired, or already redeemed")
    return principal


@dataclass
class _SocketState:
    """What one connected socket remembers, in memory and for as long as it is open (ADR-124
    decision 2): whether its reader has been sent `DeltaViewOverCap` and so is sent nothing more
    until a resync with no last sequence runs the full-snapshot path again. The server keeps no
    state for a stuck reader beyond this; a new connection starts clear.

    **During a try-again only**, the forward does not drop what it is holding back: `buffering` is
    set from the moment the resync starts until it has sent its answer, and the raw messages go to
    `buffer`, at most `DELTA_STREAM_MAXLEN` of them. Past that `overflowed` is set and the buffer is
    emptied; the resync then falls back to a fresh catch-up. In the ordinary stuck period nothing is
    buffered: a try-again snapshot covers it, and a reader who stays stuck holds no memory."""

    stuck: bool = False
    buffering: bool = False
    buffer: list[str] = field(default_factory=list)
    overflowed: bool = False


async def _send_all(
    websocket: WebSocket, state: _SocketState, deltas: Sequence[WorkingSetDeltaSent]
) -> None:
    """Sends `deltas`, and marks the socket stuck if one of them is `DeltaViewOverCap`."""
    for delta in deltas:
        await websocket.send_text(delta.model_dump_json())
        if isinstance(delta, DeltaViewOverCap):
            state.stuck = True


async def _forward_one(
    data: bytes | str,
    websocket: WebSocket,
    working_set: WorkingSetService,
    investigation_id: str,
    principal: Principal,
    state: _SocketState,
) -> bool:
    """Projects one published message for this socket's reader and sends it, as the live forward
    does. True if what was sent was `DeltaViewOverCap`."""
    raw = decode_delta(json.loads(data.decode() if isinstance(data, bytes) else data))
    if lacks_record(raw):
        # A removal or replacement from before it carried the record of what it removed: nothing
        # can be projected from it, and an empty step would leave this canvas unlike a snapshot's.
        # The reader is sent their own full view, as a reconnect with none is.
        sent = await working_set.sync(investigation_id, principal, last_acknowledged_seq=None)
        await _send_all(websocket, state, sent)
        return any(isinstance(delta, DeltaViewOverCap) for delta in sent)
    delta = await working_set.project_live(investigation_id, raw, principal)
    over = await working_set.over_cap_after(investigation_id, delta, principal)
    await _send_all(websocket, state, [over or delta])
    return over is not None


async def _forward_notifications(
    pubsub: Any,
    websocket: WebSocket,
    working_set: WorkingSetService,
    investigation_id: str,
    principal: Principal,
    state: _SocketState | None = None,
) -> None:
    """Relays a live mutation from `notify.py`'s Pub/Sub channel to this
    one connected principal — re-projected via `WorkingSetService.
    project_delta` first, since the delta was recorded by whichever
    principal caused the mutation, who may not be this socket's principal
    (`03_CONDUIT_MIDDLEWARE.md` §4's read-time handling filter applies to
    the live push exactly as much as to reconnect replay)."""
    state = state or _SocketState()
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        if state.stuck:
            # The reader was told their view is over the cap and is sent nothing more until a
            # resync with no last sequence (ADR-124 decision 2). During that try-again, and only
            # then, what arrives is kept (bounded) for the resync to replay after its answer.
            if state.buffering and not state.overflowed:
                if len(state.buffer) >= DELTA_STREAM_MAXLEN:
                    state.overflowed = True
                    state.buffer.clear()
                else:
                    state.buffer.append(message["data"])
            continue
        await _forward_one(
            message["data"], websocket, working_set, investigation_id, principal, state
        )


def _last_seq(deltas: Sequence[WorkingSetDeltaSent], so_far: int) -> int:
    return max([so_far, *(d.seq for d in deltas if not isinstance(d, DeltaViewOverCap))])


async def _try_again(
    websocket: WebSocket,
    working_set: WorkingSetService,
    investigation_id: str,
    principal: Principal,
    state: _SocketState,
) -> None:
    """A resync with no last sequence ("try again"), in this order:

    1. the socket is held stuck and the forward starts buffering what it would send;
    2. the full-snapshot path runs (it checks the cap);
    3. if that gave a snapshot, the catch-up from the snapshot's own sequence runs (it checks the
       cap too);
    4. the snapshot and the catch-up are sent;
    5. if either was `DeltaViewOverCap` the socket stays stuck and the buffer is discarded;
       otherwise the buffered messages whose sequence is above the last one sent are replayed in
       order, each projected and recounted as the forward does it, until the buffer is empty (what
       arrives during the replay is replayed too), and an overflow is answered by a fresh catch-up
       from the last sequence sent instead;
    6. only with the buffer empty, in the same step, the socket is freed.

    Nothing the forward would send overtakes the snapshot, and nothing published during the window
    is lost; a duplicate of what the snapshot already holds is skipped by sequence or harmless."""
    state.stuck = True
    state.buffering = True
    state.overflowed = False
    state.buffer.clear()
    deltas = await working_set.sync(investigation_id, principal, last_acknowledged_seq=None)
    snapshot = deltas[0] if deltas else None
    if isinstance(snapshot, DeltaSnapshot):
        caught_up = await working_set.sync(
            investigation_id, principal, last_acknowledged_seq=snapshot.seq
        )
        deltas = [*deltas, *caught_up]
    await _send_all(websocket, state, deltas)
    if any(isinstance(delta, DeltaViewOverCap) for delta in deltas):
        state.buffer.clear()
        state.buffering = False
        state.overflowed = False
        return
    sent_seq = _last_seq(deltas, -1)
    while True:
        if state.overflowed:
            state.overflowed = False
            state.buffer.clear()
            fresh = await working_set.sync(
                investigation_id, principal, last_acknowledged_seq=sent_seq
            )
            await _send_all(websocket, state, fresh)
            if any(isinstance(delta, DeltaViewOverCap) for delta in fresh):
                state.buffer.clear()
                state.buffering = False
                return
            sent_seq = _last_seq(fresh, sent_seq)
            continue
        if not state.buffer:
            break
        data = state.buffer.pop(0)
        seq = json.loads(data.decode() if isinstance(data, bytes) else data).get("seq", -1)
        if seq <= sent_seq:
            continue
        if await _forward_one(data, websocket, working_set, investigation_id, principal, state):
            state.buffer.clear()
            state.buffering = False
            return
        sent_seq = max(sent_seq, seq)
    state.stuck = False
    state.buffering = False


async def _handle_resync_requests(
    websocket: WebSocket,
    working_set: WorkingSetService,
    investigation_id: str,
    principal: Principal,
    state: _SocketState | None = None,
) -> None:
    state = state or _SocketState()
    while True:
        payload = await websocket.receive_json()
        last_ack = payload.get("last_acknowledged_seq")
        if last_ack is None:
            await _try_again(websocket, working_set, investigation_id, principal, state)
            continue
        if state.stuck:
            continue
        deltas = await working_set.sync(investigation_id, principal, last_acknowledged_seq=last_ack)
        await _send_all(websocket, state, deltas)


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
        await investigations.get_authorized(investigation_id, principal, need=AccessLevel.VIEWER)
    except (InvestigationNotFoundError, InsufficientAccessError):
        await audit.record(
            principal=principal,
            action="access_denied",
            investigation_id=investigation_id,
            resolved_query={},
            result_cardinality=0,
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # ADR-099 decision 4, as `get_principal` does for every HTTP route: the stream reads what its
    # case reads. The ticket's principal was minted outside any case and reads no dataset; the
    # header's was never scoped and reads every one. The snapshot, a resync and each live push all
    # use the principal from here on.
    principal = await scope_to_case(principal, investigation_id, get_datasets(websocket))  # type: ignore[arg-type]
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
    initial_deltas: list[WorkingSetDeltaSent] = await working_set.sync(
        investigation_id, principal, last_acknowledged_seq=init.get("last_acknowledged_seq")
    )
    state = _SocketState()
    await _send_all(websocket, state, initial_deltas)

    pubsub = valkey.pubsub()
    channel = notify_channel(investigation_id)
    await pubsub.subscribe(channel)
    try:
        forward_task = asyncio.create_task(
            _forward_notifications(
                pubsub, websocket, working_set, investigation_id, principal, state
            )
        )
        resync_task = asyncio.create_task(
            _handle_resync_requests(websocket, working_set, investigation_id, principal, state)
        )
        try:
            await asyncio.wait({forward_task, resync_task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (forward_task, resync_task):
                task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]
