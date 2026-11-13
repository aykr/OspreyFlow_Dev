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
from collections import Counter
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Coroutine,
    Iterable,
    Mapping,
    Sequence,
)
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Final, Literal, cast, get_args
from zoneinfo import ZoneInfo

import httpx
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
from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from scripts.build_local_basemap import GEOFABRIK_REGIONS, load_gazetteer
from scripts.verify_map import verify_map
from services.extract.writer import (
    NodeNotFoundError,
    ProvenanceTransitionError,
    confirm_node,
    retract_node,
)
from services.ingest.ceiling import AboveTheDeploymentCeiling, DeploymentCeiling
from services.ingest.connectors import reads as connector_reads_module
from services.ingest.connectors.geo.site_grid import site_grid_rows
from services.ingest.connectors.reads import ConnectorRefused, ReadOverCap
from services.ingest.engine import RowKeyDefinitionChanged, RowKeyRunInProgress, run_recipe
from services.ingest.pipeline import (
    expert_steps_changed,
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
from services.ingest.release import ReleaseRefused as BundleRefused
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import DEPLOYMENT_WIDE
from services.ingest.transforms import STRUCTURED_PARTS
from services.ingest.watermark import RefreshRead
from services.resolve.trigger import service_principal
from valkey.asyncio import Valkey

from adapters.model_litellm.adapter import ModelLiteLLMAdapter
from adapters.model_litellm.client import LiteLLMClient, LiteLLMConfig
from adapters.model_litellm.errors import (
    ExtractionFailedError,
    ModelLimitReached,
    ModelUnavailableError,
    UsageUnavailableError,
)
from conduit_common.identity import new_edge_id, new_id, now_utc
from conduit_common.valkey_compat import reply
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
from ontology.influencers import StrengthDefaults, as_the_reader_sees, load_strength_defaults
from ontology.packs import pack_catalogue
from ontology.pattern_where import PatternConditionRefused, check_pattern_conditions
from ontology.yardstick import Yardstick, load_phia_yardstick
from ports.analytics import AnalyticsPort, TrendLimitExceeded
from ports.compute import ComputePort
from ports.graph import GraphPort
from ports.media import MediaStore
from ports.model import ModelPort
from ports.recognise import RecogniserRefusedError, RecogniserUnavailableError
from principal_auth import (
    ROLE_LOOKUP_TIMEOUT_SECONDS,
    PrincipalLookupUnavailable,
    PrincipalRevoked,
    SigningKeysUnavailable,
    in_keys_thread,
)
from rule_standards import StoredRuleFiles, rule_files
from schemas.admin import (
    AccessInput,
    AddPersonInput,
    AdminDataset,
    AdminDatasetAuthors,
    AdminDatasetCases,
    AdminLinkedCase,
    AdminPeopleRows,
    AdminSchedule,
    AuditSectionEntry,
    AuditSectionPage,
    BuiltInRole,
    ChangeScheduleInput,
    ComponentHealth,
    ConvertedViews,
    CustomRole,
    CustomRoleInput,
    CustomRoleVersion,
    DashboardGuestToken,
    DashboardIdentity,
    DashboardInput,
    DataFeed,
    DatasetAuthor,
    DatasetEgressInput,
    DatasetPromotionPolicyInput,
    DemoPackStatus,
    DisableInput,
    DisablePlan,
    EmbeddedDashboard,
    InviteInput,
    LayerAction,
    LayerDryRun,
    NeedsYou,
    NeedsYouProposals,
    OperationsAgeing,
    OrganisationArrival,
    OrganisationLinkInput,
    PauseScheduleInput,
    PersonAccount,
    PromotionAlertSetting,
    RegisteredDashboard,
    RolesCatalogue,
    RolesInput,
    ScheduleRunView,
    SignInDelivery,
    SignInKind,
    SystemStatus,
    Team,
    TeamCoverInput,
    TeamInput,
    TeamLeadInput,
    TeamMember,
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
from schemas.boards import (
    Board,
    BoardInput,
    BoardMove,
    BoardOpened,
    BoardPictures,
    DrawingInput,
    DrawnItemEdit,
    DrawnItemInput,
    DrawnItemMade,
    DrawnLinkInput,
    DrawnWatch,
    MatchDecided,
    MatchDecision,
    MatchSuggestions,
    NewDrawing,
    PictureChoice,
    Withdrawn,
)
from schemas.case_views import CaseView, CaseViewInput, CaseViewOpened
from schemas.compute import OwnershipTooComplex, OwnershipView
from schemas.dataset_model import (
    DatasetModelView,
    DatasetOwners,
    DatasetOwnerSetting,
    DrawnDatasetInput,
    HomeCase,
    MadeLive,
    MakeLiveInput,
    ModelImpact,
    ReferenceList,
    RevertModelInput,
    TargetModel,
    TargetModelDraftInput,
)
from schemas.domain import (
    Alert,
    AlertAssignee,
    AlertAssignInput,
    AlertAtAddress,
    AlertDispositionInput,
    AlertExplanation,
    AlertKind,
    AlertQueueCounts,
    AlertSeverity,
    AlertSources,
    AlertSuppressInput,
    AlertTeam,
    Assumption,
    CompiledSentence,
    Connections,
    ConnectionsRequest,
    DomainPack,
    Edge,
    EdgeWrite,
    ExpandRequest,
    Grading,
    GradingSchemeAnswer,
    Handling,
    HeldRow,
    HeldRowDecision,
    Hotlist,
    HotlistAudienceInput,
    IntelligenceGap,
    Interval,
    Judgement,
    KycStatus,
    LinkNote,
    Monitor,
    MonitorScheduleInput,
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
    RaiseAlertInput,
    ReportFigures,
    RuleAuditPage,
    SavedPattern,
    SentenceReadRequest,
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
    PipelineYaml,
    PublishRecipeInput,
    RowTemplateUpdateInput,
    RunRecipeInput,
    SchedulePreview,
    SchedulePreviewInput,
    ScheduleUpdateInput,
    SqlCheck,
    SqlCheckInput,
    StagingPreview,
    StagingPreviewInput,
    StudioRecipeDraft,
    StudioRecipeStatus,
    StudioRole,
    TransformDescriptor,
    VerifyReport,
)
from schemas.list_connector import (
    DatasetOwnListImportInput,
    DatasetSubscriptions,
    DeploymentList,
    DeploymentListInput,
    ListImport,
    ListImports,
    OfferedList,
    SubscribableList,
)
from schemas.map_admin import (
    BuildBasemapInput,
    MapAdminHistory,
    MapDefaultInput,
    MapKeyInput,
    MapProviderInput,
    MapsAdminView,
    PrefetchAreasInput,
    PrefetchRun,
    PrefetchScheduleInput,
)
from schemas.mapconfig import (
    GAZETTEER_DATASET_PREFIX,
    CaseGazetteer,
    CaseGazetteers,
    MapConfig,
    PlaceSearchRequest,
    PlaceSearchResponse,
    PublicMapConfig,
)
from schemas.model import OfferedEngines
from schemas.model_admin import (
    ConnectionTestResult,
    DefaultsInput,
    EngineInput,
    KeyInput,
    LimitsInput,
    ModelAdminHistory,
    ModelsAdminView,
    ModelUsageView,
)
from schemas.monitoring import (
    CheckNotJudged,
    ListScheduleInput,
    LoadChecksInput,
    LoadChecksView,
    RuleChangeRejection,
    RuleScheduleView,
    RuleVersion,
    WouldRaise,
)
from schemas.operations import (
    ExternallyOwnedInput,
    ExternalRunInput,
    ExternalRunStatus,
    OperationsRollup,
    PausedPipeline,
    QuotaAlertView,
    QuotaScope,
    RunQuota,
    RunQuotaInput,
    RunQuotaUse,
)
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
from schemas.person_ownership import PersonOwnership
from schemas.profile import SourceProfile
from schemas.promotions import (
    DrawnMergeDryRun,
    DrawnMergeInput,
    DrawnMergeSheet,
    LayerDeleted,
    LayerMergeInput,
    LayerMergeSheet,
    MergeTargets,
    Promotion,
    PromotionDecision,
    PromotionDetails,
    PromotionInput,
    PromotionSheet,
    RemovedCaseLayer,
    RemovedCaseLayers,
    TypeChoice,
)
from schemas.promotions import Promotions as PromotionsList
from schemas.release import (
    ReleaseBundleInput,
    ReleaseExport,
    ReleaseImportPlan,
    ReleaseMetadata,
)
from schemas.rights import (
    CUSTOM_ROLE_PREFIX,
    ROLE_RIGHTS,
    SUPER_USER_PRESET,
    MeResponse,
    Right,
    RightsResponse,
    rights_for,
)
from schemas.rule_editor import RuleDatasetOffer, RuleTestResult
from schemas.rule_standards import ImportedRule
from schemas.screening import (
    ScreeningLists,
    ScreeningListsOverview,
    ScreeningListStatus,
    ScreeningListUpdate,
    ScreeningSubscriptionInput,
)
from schemas.sentences import (
    RULE_TEST_DAYS,
    RulePreview,
    RulePreviewRequest,
    RuleSentence,
    SentenceRuleInput,
    SentenceRuleParams,
)
from schemas.sources import (
    Connection,
    ConnectionInput,
    ConnectionTest,
    ConnectorRead,
    GovernanceEdited,
    PauseRefreshInput,
    RegisterSourceInput,
    SourceDefaultMarkingInput,
    SourceGovernanceInput,
    SourceLineage,
    SourceRefresh,
    SourceTable,
)
from schemas.strength import (
    ActiveInfluencer,
    CaseInfluencers,
    CaseInfluencersInput,
    ConnectionStrengthRequest,
    ConnectionStrengths,
    InfluencerDecision,
    InfluencerSetHistory,
    InfluencerSetInput,
    InfluencerSetVersion,
    RarityRequest,
    RarityResult,
)
from schemas.trends import (
    TrendDefinition,
    TrendDefinitionInput,
    TrendFigures,
    TrendLimitExceededBody,
    TrendOptions,
)

from . import (
    alert_queue,
    alert_sources,
    case_gazetteers,
    map_places,
    raised_alerts,
    rule_editor,
    sentence_rules,
)
from . import audit_section as audit_section_module
from . import compute_routes as compute_routes_module
from . import connections as connections_module
from . import dossier as dossier_module
from . import drawn_merge as drawn_merge_module
from . import guides as guide_files
from . import kyc as kyc_module
from . import map_admin as map_admin_module
from . import model_admin as model_admin_module
from . import model_usage as model_usage_module
from . import needs_you as needs_you_module
from . import ownership as ownership_module
from . import promotion_ageing as promotion_ageing_module
from . import readiness as readiness_module
from . import reports as reports_module
from . import resolution as resolution_module
from . import resolution_trigger as resolution_trigger_module
from . import review as review_module
from . import risk as risk_module
from . import rules_place as rules_place_clock
from . import search as search_module
from .add_by_identifiers import (
    MAX_IDENTIFIERS,
    AddByIdentifiersRequest,
    AddByIdentifiersResponse,
    TooManyIdentifiersError,
    resolve_identifiers,
)
from .admin_people import OTHER_UNIT, AdminPeopleStore, DisableRefused, recipients
from .alert_routing import answers_for_datasets, leads_today
from .alerts import (
    AlertNotFoundError,
    AlertStore,
    AlertTriageConflict,
    QueueShow,
    purge_remarked_copies,
    raiser_floor,
    supersede_journalled,
)
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
from .board_store import BoardItemStore, InMemoryBoardItemStore, PostgresBoardItemStore
from .boards import BoardNotFound, Boards, DrawingRefused, ItemNotFound, NotTheBoardsCreator
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
from .case_views import (
    CaseViewStore,
    InMemoryCaseViewStore,
    NotTheViewsCreator,
    PostgresCaseViewStore,
    ViewNotFound,
    open_view,
)
from .change_stream import touched_node_ids
from .compute_routes import (
    JOB_TYPE_COMPUTE_METRIC,
    ComputeMetricAccepted,
    ComputeMetricName,
    ComputeMetricRequest,
    run_compute_metric_job,
)
from .config import ApiConfig, DeploymentModels, GradingSettings, MonitoringSettings
from .connection_strength import case_connection_strengths, case_legend, case_rarity
from .connector_reads import (
    Readers,
    check_connection,
    read_into_file,
    refuse_connection_hosts,
    refuse_unbound,
    source_file,
)
from .credentials import MissingCredentialError
from .custom_roles import (
    CustomRoleStore,
    RoleRefused,
    custom_role_ids,
    giver_may_give,
    leaves_no_people_manager,
    role_refusal,
)
from .dataset_scope import (
    CompositeReadOnlyError,
    DrawnOnItsBoard,
    NoAnalystLayerError,
    UnknownDatasetError,
    holds_a_level_in,
    made_in,
    outside_any_case,
    read_in_view,
    refuse_correcting_a_drawn_node,
    refuse_in_a_composite_case,
    refuse_writing_a_node_in_a_composite_case,
    scope_to_case,
    scope_to_dataset,
)
from .datasets import (
    DRAWN,
    MAX_DATASET_NAME,
    CaseDatasetsRequest,
    CreateCompositeRequest,
    CreateDatasetRequest,
    Dataset,
    DatasetRefusedError,
    DatasetStore,
    DrawnNotCopied,
    HomeCaseHeld,
    InMemoryDatasetStore,
    ReadOnlyLayerError,
    UnknownDatasetEgressError,
)
from .datasets import SOURCE as SOURCE_DATASET
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
from .entra_people import STALE_ACCESS_WORDS, EntraPeopleAdmin, access_current
from .event_scope import own_events_only
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
from .external_runs import start_external_run, status_for
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
    BRIEF_EDITED,
    EXPANDED,
    LINKS_AMONG,
    NOT_RESTORABLE,
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
    PeopleDirectory,
    PersonActionRefused,
    PersonExistsError,
    UnknownRoleError,
    allowed_role,
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
    TEAM_GRANT_PREFIX,
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
from .laurium_start import close_laurium, laurium_in_the_conduit, routed_model
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
    AcceptLinkTypeRequest,
    CaseLinkTypesResponse,
    LinkTypeDecisionRequest,
    LinkTypeOption,
    LinkTypeProposal,
    LinkTypeProposalList,
    LinkTypeService,
    ModelProposalList,
    ModelProposalView,
    PromotableRequest,
    PromotableResponse,
    PromotableType,
    PromoteLinkTypeRequest,
    ProposalNotFoundError,
    ProposalRefusedError,
    ProposeLinkTypeRequest,
    RetireLinkTypeRequest,
    may_read_proposal_words,
    public_ontology,
)
from .list_connector import (
    DeploymentListScheduler,
    InMemoryListRows,
    InMemoryListStore,
    ListConnectorRefused,
    ListNotFound,
    ListRows,
    ListStore,
    ParquetListRows,
    check_list_location,
    import_list,
    import_own_list,
    offered_lists,
)
from .list_schedule import ListRefreshExecutor, ListScheduleRefused, check_list_schedule
from .load_checks import READ_ONLY, ChecksRefused, check_choice, checks_view, would_raise
from .load_records import LedgerSink, may_see_counts, released_from_of, report_view
from .mapconfig_loader import load_map_config, public_view
from .model_impact import flag_reason, impact_of, pack_types_of
from .model_routing import (
    EngineRefused,
    ModelEgressRefused,
    ModelRoutes,
    RoutedModel,
    model_status,
    routes_from_env,
)
from .monitor_schedule import MonitorScheduleExecutor, monitor_matcher
from .monitors import MonitorNotFoundError, MonitorStore
from .notify import notify_channel, publish_delta
from .operations_rollup import external_triggers, rollup_rows, scheduler_health
from .packs import (
    PackExportRefused,
    PackHasWithheldItems,
    PackItemRefused,
    PackStore,
    StoredPackItem,
    alert_item,
    assessment_item,
    entity_item,
    export_pack,
    highest_marking,
    note_item,
    readable,
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
from .person_ownership import PostgresOwnershipStore
from .pipeline_run import (
    OnlineGeocode,
    RecogniserFor,
)
from .principal_names import PrincipalNameDirectory
from .promotion_store import (
    InMemoryPromotionStore,
    PostgresPromotionStore,
    PromotionRecord,
    PromotionStore,
    WaitingFromStore,
)
from .promotions import (
    GAZETTEER_TAKES_NOTHING_DRAWN,
    PromotionNotFound,
    PromotionRefused,
    Promotions,
    is_composite,
    is_gazetteer,
)
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
    run_drawn_watches_best_effort,
    run_recipe_as,
)
from .recipe_runs import External, RecipeRun, RecipeRunStore, RunTrigger
from .release_notice import read_update_notice
from .release_version import deployment_version, release_version
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
from .rule_schedule import RuleScheduleExecutor, runs_for_reader, schedule_view
from .rule_sentences import (
    SentenceContext,
    SentenceRefused,
    check_sentence,
    compile_pattern,
    compile_sentence,
    normalised,
    preview_sentence,
    sentence_of,
)
from .rule_standards_routes import export_rule_file, import_rule_files
from .rules_place import PLACE as RULES_PLACE
from .rules_place import opens_rules_place, reads_queue_rows, refusal_wait
from .rules_place import refusal as rules_place_refusal
from .rules_place import rows_refusal as queue_rows_refusal
from .run_quotas import QuotaRefused, QuotaStore, day_start
from .run_resources import RECIPES_REPO_ROOT, build_run_resources
from .run_source import (
    SourceChangedSinceVerifyError,
    changed_since_verify,
    files_a_run_reads,
    identify,
)
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
from .screening import ListClearance, ScreeningListStore
from .screening_refresh import (
    ListNotSubscribed,
    ListRefused,
    Rescreener,
    check_location,
)
from .screening_refresh import refresh as refresh_screening_list
from .search import SearchRequest, SearchResponse, SuggestRequest, SuggestResponse
from .sentence_rules import (
    is_deployment_wide,
    run_on_list_refresh,
    run_scheduled_rule,
    strength_context,
)
from .service_identity import (
    DASHBOARD_IS_NO_SERVICE_IDENTITY,
    DEPLOYMENT_CLIENT_WORDS,
    ServiceIdentityRefused,
    ServiceIdentityVerifier,
    is_deployment_client,
)
from .site_images import (
    object_key_for,
    read_site_image,
    site_image_storage_config,
    write_site_image,
)
from .sites import ControlPointQuad, Site, SiteNotFoundError, SiteStore
from .source_refresh import StoredSourceWatches
from .sources import (
    InMemorySourceStore,
    SecretInUseError,
    SourceAlreadyRegisteredError,
    SourceNotFoundError,
    SourceStore,
    UnknownConnectionError,
    default_marking_problems,
)
from .strength_influencers import (
    InfluencerChangeRefused,
    InfluencerRefused,
    InfluencerStore,
    OwnInfluencerChangeRefused,
    check_influencers,
)
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
    offered_to,
    profile_recipe_source,
)
from .studio_publish import (
    GitCommitError,
    RecipeNotRunnableError,
    build_recipe,
    check_before_publish,
    load_published_recipe,
    pack_versions_for,
    write_and_commit_recipe,
)
from .studio_recipes import (
    SOURCE_GOVERNANCE_CHANGED,
    SourceDeclarationsInvalidError,
    StudioRecipeCannotVersionError,
    StudioRecipeNotADraftError,
    StudioRecipeNotFoundError,
    StudioRecipeNotVerifiedError,
    StudioRecipeStore,
    recipe_reader,
    reconcile_recipe_pins,
)
from .studio_release import (
    DraftHeld,
    apply_import,
    bundle_from_text,
    deployment_secrets,
    export_release,
    plan_import,
    with_default_classification,
)
from .studio_staging import (
    StagedTestInputs,
    dataset_reference_lists,
    declared_markings,
    draft_marked,
    pipeline_from_yaml,
    pipeline_yaml,
    preview_staging,
    sources_not_offered,
    sql_check,
    staging_gate,
)
from .studio_verify import RowTemplateMissingError, run_verify
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
from .target_models import (
    InMemoryTargetModelStore,
    NoModelYet,
    TargetModelRefused,
    TargetModelStore,
    core_types_of,
    packs_of_case,
)
from .tile_cache import (
    cache_key_for,
    read_cached_tile,
    tile_cache_storage_config,
    write_cached_tile,
)
from .tile_proxy import MissingMapKeyError, TileFetchFailed, build_upstream_url, fetch_tile
from .trends import (
    TrendDefinitionRefused,
    TrendStore,
    check_in_case_domains,
    highest,
    mark_outside_case_domains,
    name_alert_series,
    name_series,
    to_alert_request,
    to_request,
    trend_options,
    validate_definition,
)
from .typology_rules import (
    OwnChangeRefused,
    RuleChangeRefused,
    RuleDatasetFixed,
    RuleFiles,
    RuleUntested,
    TypologyRuleNotFoundError,
    TypologyRuleStore,
)
from .watch_reach import DatasetReach, owner_reaches_dataset_in
from .watch_routes import (
    CreateHotlistRequest,
    CreateMonitorRequest,
    HotlistList,
    MonitorList,
    with_what_fired_it,
)
from .worker import JobWorker
from .worker_main import register_all
from .working_set.models import (
    MAX_NODES,
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
    ResolutionOutcome,
    SameNodeAssertionError,
    WorkingSetDeltaSent,
    decode_delta,
    lacks_record,
)
from .working_set.service import WorkingSetService, _cap_breach
from .working_set.store import DELTA_STREAM_MAXLEN, ValkeyWorkingSetStore
from .ws_ticket import WsTicketResponse, mint_ws_ticket, redeem_ws_ticket

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = ApiConfig.from_env()
    # ADR-143 decision 11: `grading.scheme`, read first, so an unknown scheme stops the start
    # before anything is opened or written (a guessed scheme would grade every new drawing wrongly).
    grading_settings = GradingSettings.from_env()
    # ADR-148 decision 10: the deployment's marking ceiling, read at the start for the same reason,
    # so an unknown value stops the Conduit rather than guess the limit every load is judged by.
    deployment_ceiling = DeploymentCeiling.from_env()

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
    # ADR-145 Amendment 5: custom roles and teams, and Admin › People's reads and Disable….
    custom_roles = await CustomRoleStore.connect(config.postgres.dsn)
    admin_people = await AdminPeopleStore.connect(config.postgres.dsn)
    # ADR-145 decisions 9 and 10 (L2.6): Admin › Audit's reads, and Operations' ageing.
    audit_section = await audit_section_module.AuditSectionReader.connect(config.postgres.dsn)
    promotion_ageing = await promotion_ageing_module.PromotionAgeingStore.connect(
        config.postgres.dsn
    )
    # L3.8: what a person owns that the case lane keeps, which Disable… lists (ADR-145 A4).
    person_ownership = await PostgresOwnershipStore.connect(config.postgres.dsn)
    # ADR-141 decision 6: the run quotas every run's start judges (`run_quotas.judge`).
    run_quotas = resources.run_quotas
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
    # ADR-140 Amendment 4: connections and the sources registered on them, opened with the run's
    # resources, which a staged run reads each source's declared default marking through
    # (ADR-140 Amendment 19; one pool).
    source_store = resources.sources
    # ADR-140 Amendment 13: deployment-wide screening lists and each dataset's subscriptions,
    # opened with the run's resources, which a staged run reads them through (one pool).
    list_store = resources.list_store
    # ADR-140 Amendment 12: opened with the run's resources, which a staged run reads it through,
    # so the Conduit holds one pool for it and closes it with them.
    target_model_store = resources.target_models
    questions_store = await PostgresQuestionStore.connect(config.postgres.dsn)
    # ADR-144: the saved views of each case, holding no data.
    case_view_store = await PostgresCaseViewStore.connect(config.postgres.dsn)
    # ADR-143 decisions 4 and 5: what each board holds, by id, and the watches drawing sets.
    board_item_store = await PostgresBoardItemStore.connect(config.postgres.dsn)
    promotion_store = await PostgresPromotionStore.connect(config.postgres.dsn)
    app.state.datasets = datasets_store
    litellm_client = LiteLLMClient(LiteLLMConfig.from_env())
    # `embed_model` is the only model this adapter needs fixed at construction — `extract()`'s own
    # model is caller-supplied per call (`ExtractionRequest.model`, ADR-005), never this adapter's
    # own opinion (`services/api/review.py`'s own docstring on `RunExtractionRequest.model`).
    # ADR-095: the deployment's own models, never the conformance suite's.
    models = DeploymentModels.from_env()
    # ADR-114 Amendment 6, ADR-135, ADR-136: every model call goes through the routes, so a
    # client's provider sees only material whose handling code the deployment declared sendable
    # and whose every dataset allows that provider, and an engine an analyst names is used only
    # when it is enabled and has a key.
    # ADR-135 Amendments 6 and 9 (P12 part 2): `extract` by Laurium's service for the review
    # queue's document extraction when the deployment chose it (`OSPREY_EXTRACTION_ENGINE`),
    # every other call the gateway's; inside the routes, so each keeps its engine's key and the
    # egress rules (`services.api.laurium_start.routed_model`).
    model: ModelPort = routed_model(
        ModelLiteLLMAdapter(litellm_client, embed_model=models.embedding),
        routes=routes_from_env(models, os.environ),
        # ADR-136: and only from datasets whose egress allows the engine.
        egress=datasets_store,
        environ=os.environ,
        master=LiteLLMConfig.from_env().api_key,
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
    # ADR-133 ruling 3: `osprey.yaml`'s `monitoring` section, read once.
    app.state.monitoring = MonitoringSettings.from_env()
    app.state.grading = grading_settings
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
    app.state.custom_roles = custom_roles
    app.state.admin_people = admin_people
    app.state.audit_section = audit_section
    app.state.promotion_ageing = promotion_ageing
    # ADR-145 Amendment 6's seam, answered by L3.4's promotion record (ADR-143 Amendment 5).
    app.state.waiting_promotions = waiting_promotions_seam(
        promotion_store, datasets_store, investigations, custom_roles, handling_scheme
    )
    app.state.ownership = person_ownership
    app.state.history = history
    app.state.sites = sites
    app.state.patterns_store = patterns_store
    app.state.hotlists_store = hotlists_store
    app.state.monitors_store = monitors_store
    app.state.alerts_store = alerts_store
    # ADR-146 decision 8: a routed alert is read by its team and the home case's Authors; the store
    # asks who answers for which dataset on each read of the queue.
    alerts_store.answers_for = answers_for_datasets(datasets_store, investigations)
    # L2.10's carry: a settle on a read path purges the working-set copies it re-marked at once.
    alerts_store.working_set = app.state.working_set
    # ADR-134 decision 3: the analytics store's alert facts brought into line with the alert store
    # at every start, so alert trends recover from any write the analytics store missed.
    await alerts_store.publish_all_facts()
    app.state.typology_rules = typology_rules
    # ADR-139: link-strength influencers (installation-wide by maker–checker, per case by its
    # Author) and the weights file's shipped defaults.
    app.state.strength_influencers = resources.influencers
    app.state.strength_defaults = load_strength_defaults()
    app.state.held_rows = held_rows
    app.state.screening_lists = screening_lists
    app.state.kyc_expiries = kyc_expiries
    app.state.recipe_runs = recipe_runs
    app.state.run_quotas = run_quotas
    # ADR-141 decision 10: a service identity's sign-in, for the run API alone.
    app.state.service_identities = ServiceIdentityVerifier(
        config,
        claim_mapping=resources.principal_resolver.claim_mapping,
        # One set of keys for both paths: the same OIDC_JWKS_URL (ADR-148 Amendment 8).
        # A resolver double without keys of its own leaves the verifier its own set.
        signing_keys=getattr(resources.principal_resolver, "signing_keys", None),
    )
    # The external runs going on in the background, held so none is collected mid-run.
    app.state.external_runs = set()
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
        link_type_store, ontology, graph, app.state.working_set, investigations,
        models=target_model_store,
    )  # fmt: skip
    await app.state.link_types.refresh()
    app.state.link_changes = LinkChangeService(
        link_changes_store,
        app.state.working_set,
        graph,
        ontology,
        link_notes_store,
        app.state.link_types,
        scheme=handling_scheme,
        alerts=alerts_store,
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
        app.state.working_set,
        graph,
        media,
        ontology,
        scheme=handling_scheme,
        audit=app.state.audit,
        alerts=alerts_store,
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
    # ADR-129 decision 2: ask to search, a question turned into a pattern that nothing runs. ADR-135
    # Amendment 1: it carries the case's handling and datasets, so the engine choice applies.
    app.state.pattern_ask = PatternAskService(
        app.state.working_set, graph, model, default_model=models.extraction,
        datasets=datasets_store,
    )  # fmt: skip
    app.state.suppression_marks = suppression_marks
    app.state.gaps_store = gaps_store
    app.state.assumptions_store = assumptions_store
    app.state.export_ledger = export_ledger
    app.state.report_freshness = report_freshness
    app.state.trend_store = trend_store
    app.state.pack_store = pack_store
    app.state.studio_recipes = studio_recipes
    app.state.sources = source_store
    app.state.list_store = list_store
    app.state.list_rows = ParquetListRows(ObjectStorageConfig.from_env())
    app.state.target_models = target_model_store
    app.state.case_views = case_view_store
    app.state.board_items = board_item_store
    app.state.promotions = promotion_store
    app.state.extraction_candidates = extraction_candidates
    app.state.model = model
    # ADR-135 Amendment 2: *Admin › Models*. The engines it holds route the next request, with no
    # restart (`RoutedModel.set_routes`); the gateway's entries are made equal to them at start.
    gateway_config = LiteLLMConfig.from_env()
    gateway_http = httpx.AsyncClient(
        base_url=gateway_config.base_url,
        headers={"Authorization": f"Bearer {gateway_config.api_key}"},
    )
    model_admin_audit = await model_admin_module.PostgresModelAdminAudit.connect(
        config.postgres.dsn
    )
    routed = model if isinstance(model, RoutedModel) else None
    model_admin = model_admin_module.ModelAdmin(
        installed=model_admin_module.Installed.from_env(models, os.environ),
        settings_file=model_admin_module.ModelSettingsFile.from_env(),
        gateway=model_admin_module.GatewayAdmin(gateway_http),
        audit=model_admin_audit,
        on_change=routed.set_routes if routed is not None else (lambda _routes: None),
    )
    await model_admin.start()
    if routed is not None:
        routed.follow(model_admin.routes)
    # ADR-135 Amendment 6 decision 8: Laurium's own key, the deployment's extraction model alone,
    # any older one (a master key since rotated) deleted; tried again in the background until held,
    # never stopping the Conduit, Laurium's calls refused until then (`laurium_start`).
    laurium_key_start = await laurium_in_the_conduit(
        model, gateway_http, gateway_config.api_key, [models.extraction]
    )
    app.state.model_admin = model_admin
    app.state.recipes_repo_root = resources.recipe_repo_root
    app.state.handling_scheme = handling_scheme
    app.state.deployment_ceiling = deployment_ceiling
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
    # The supersede and resolution jobs, bound as the standalone worker binds them, by the one
    # function (`worker_main.register_all`): the alerts' repoint journal on both (ADR-109
    # Amendment 11), a layer's split its own case's (ADR-143 Amendment 1), the review flag here.
    register_all(
        job_worker,
        ontology=ontology,
        scheme=handling_scheme,
        valkey=valkey,
        analyst_layers=datasets_store.layer_ids,
        alerts=alerts_store,
        judgement_store=judgements_store,
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
    # ADR-112 Amendment 3 (b): the organisation's sign-in, whose refused arrivals can be joined.
    # ADR-148 Amendment 8: on Entra ID sign-in, Admin › People writes the deployment's own store,
    # which an open delta socket also asks before each message (`_socket_standing`).
    app.state.people_store = resources.people_store
    app.state.identity_admin = people_directory(resources, config)
    # ADR-111 Amendment 3: Superset dashboards inside the Glass; None when not configured.
    superset_settings = SupersetSettings.from_env()
    app.state.superset_embedder = SupersetEmbedder(superset_settings) if superset_settings else None
    app.state.map_config = load_map_config(config.osprey_config_path)
    # ADR-147: *Admin › Maps*; its maps file replaces `osprey.yaml`'s `map:` once changed there,
    # and its prefetch areas run on their schedule in the Conduit.
    map_admin_audit = await map_admin_module.PostgresMapAdminAudit.connect(config.postgres.dsn)
    # ADR-147 Amendment 2 (the owner's ruling 6): the gazetteers each case added, copied into it.
    app.state.case_gazetteers = await case_gazetteers.CaseGazetteerStore.connect(
        config.postgres.dsn
    )
    app.state.map_admin = map_admin_module.MapAdmin(
        installed=app.state.map_config,
        settings_file=map_admin_module.MapSettingsFile.from_env(),
        key_file=map_admin_module.MapKeyFile.from_env(),
        audit=map_admin_audit,
    )
    prefetch_schedule = map_admin_module.PrefetchScheduler(app.state.map_admin)
    prefetch_schedule.start()

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
            datasets=datasets_store,
        )

    sweep_task = asyncio.create_task(run_daily_kyc_sweep(valkey, _sweep_day))

    # ADR-110 decision 2: scheduled pipeline runs, ticking each minute on every replica, each slot
    # run by the one that claims it, as the schedule's owner through the one run path.
    app.state.schedule_executor = _schedule_executor(app)
    schedule_task = asyncio.create_task(run_every_minute(app.state.schedule_executor))
    # ADR-133 stage (d): scheduled rules, each slot as the rule's author, and screening lists'
    # refresh schedules, each slot as the person who set it — ticking each minute, one replica per
    # slot.
    app.state.monitoring_schedules = _MonitoringSchedules(
        rules=_rule_schedule_executor(app), lists=_list_schedule_executor(app),
        deployment_lists=_deployment_list_scheduler(app),
        monitors=MonitorScheduleExecutor(
            monitors=app.state.monitors_store, valkey=app.state.valkey,
            resolve_owner=_owner_with_custom_roles(
                app, app.state.principal_resolver.resolve_for_owner_detailed
            ),
            match=monitor_matcher(app.state),
            reaches_dataset=owner_reaches_dataset_in(
                lambda: app.state.datasets, lambda: app.state.investigations
            ),
        ),
    )  # fmt: skip
    monitoring_task = asyncio.create_task(run_every_minute(app.state.monitoring_schedules))
    # ADR-145 Amendment 4 decision 11 (R7), admin's own job (Amendment 6): *Promotions overdue*,
    # once each at N days, from whatever source `app.state.waiting_promotions` holds at each tick.
    app.state.promotion_sweep = promotion_ageing_module.PromotionSweep(
        promotion_ageing, promotion_ageing, lambda: app.state.waiting_promotions,
        lambda p: _promotion_recipients(app, p),
    )  # fmt: skip
    promotion_task = asyncio.create_task(
        promotion_ageing_module.run_every(
            app.state.promotion_sweep,
            float(os.environ.get("OSPREY_PROMOTION_SWEEP_SECONDS")
                  or promotion_ageing_module.SWEEP_SECONDS),
        )
    )  # fmt: skip

    try:
        yield
    finally:
        sweep_task.cancel()
        schedule_task.cancel()
        monitoring_task.cancel()
        promotion_task.cancel()
        await investigations.close()
        await custom_roles.close()
        await admin_people.close()
        await audit_section.close()
        await promotion_ageing.close()
        await person_ownership.close()
        app.state.ownership = None
        # A closed store must not outlive the app: a request's custom roles are read through it.
        app.state.custom_roles = None
        await history.close()
        # Closed with the run's resources; a closed store must not outlive the app.
        app.state.sources = None
        # Closed with the run's resources; a closed store must not outlive the app.
        app.state.list_store = None
        await case_view_store.close()
        app.state.case_views = None
        await board_item_store.close()
        app.state.board_items = None
        await promotion_store.close()
        app.state.promotions = None
        # Every case's level check reads it (its packs, ADR-126 Amendment 2): a closed store left
        # on the state would answer a later app (a test's, with no lifespan) "pool is closed".
        app.state.target_models = None
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
        # ADR-139: a route that judges rules reads this store when the app holds one, so a closed
        # one left here would fail them; without it they judge with the weights file's influencers.
        app.state.strength_influencers = None
        await litellm_client.aclose()
        if laurium_key_start is not None:
            await laurium_key_start.stop()
        await close_laurium(model)
        app.state.model_admin = None
        await model_admin.close()
        await model_admin_audit.close()
        await prefetch_schedule.close()
        app.state.map_admin = None
        await map_admin_audit.close()
        await app.state.case_gazetteers.close()
        app.state.case_gazetteers = None
        await gateway_http.aclose()
        await resources.close()


# The OpenAPI document is published at `GET /v1/openapi.json` behind sign-in (the owner's answer of
# 1 November 2026; `03_CONDUIT_MIDDLEWARE.md` §3.0a), versioned with the release. FastAPI's own
# unauthenticated copies (`/openapi.json`, `/docs`, `/redoc`) are switched off.
app = FastAPI(
    title="OspreyFlow Conduit",
    version=release_version(),
    lifespan=lifespan,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)

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


def get_sources(request: Request) -> SourceStore:
    """ADR-140 Amendment 4. The lifespan sets the Postgres store; a test app with no lifespan gets
    an in-memory one holding the built-in Files connection."""
    store = getattr(request.app.state, "sources", None)
    if store is None:
        store = InMemorySourceStore()
        request.app.state.sources = store
    return store


SourcesDep = Annotated[SourceStore, Depends(get_sources)]


def get_list_store(request: Request) -> ListStore:
    """ADR-140 Amendment 13. The lifespan sets the Postgres store; a test app gets the twin."""
    store = getattr(request.app.state, "list_store", None)
    if store is None:
        store = InMemoryListStore()
        request.app.state.list_store = store
    return store


def get_list_rows(request: Request) -> ListRows:
    """Where a list's versions are kept: the object store; a test app gets the twin."""
    rows = getattr(request.app.state, "list_rows", None)
    if rows is None:
        rows = InMemoryListRows()
        request.app.state.list_rows = rows
    return rows


ListStoreDep = Annotated[ListStore, Depends(get_list_store)]
ListRowsDep = Annotated[ListRows, Depends(get_list_rows)]


def _core_types() -> frozenset[str]:
    """The POLE core's entity and link types, from the default ontology (which composes no pack):
    what a dataset's model may not redefine as an extension (ADR-140 decision 4)."""
    from ontology.loader import load_default_ontology

    core = load_default_ontology()
    return core_types_of([e.name for e in core.entity_types], [e.name for e in core.edge_types])


def get_target_models(request: Request) -> TargetModelStore:
    """ADR-140 decision 5. The lifespan sets the Postgres store; a test app with no lifespan gets
    an in-memory one."""
    store = getattr(request.app.state, "target_models", None)
    if store is None:
        store = InMemoryTargetModelStore(core_types=_core_types())
        request.app.state.target_models = store
    return store


TargetModelsDep = Annotated[TargetModelStore, Depends(get_target_models)]


async def _rules_on_list_refresh(state: Any, done: ListImport, owner: str) -> None:
    """ADR-146 decision 3, *When* a screening list refreshes: a new version kept starts every
    running rule that names the list, each as its author, recorded with its runs. A refresh that
    kept nothing new starts none."""
    if done.outcome != "updated":
        return
    schedules = getattr(state, "monitoring_schedules", None)
    executor = getattr(schedules, "rules", None)
    if executor is None:
        return
    try:
        await executor.on_list_refreshed(done.list_id, owner, datetime.now(UTC))
    except Exception:  # noqa: BLE001 - the refresh stands; each rule's run says what became of it
        logger.exception("the rules naming list %s could not be started", done.list_id)


def _rule_lists_of(state: Any) -> rule_editor.RuleListReader:
    """ADR-146 decision 3 (L2.11): how a run reads the Studio list a sentence names, within the
    rule's own dataset, over the running Conduit's stores (each `None` where it has none)."""
    return rule_editor.rule_list_reader(
        datasets=state.datasets if getattr(state, "datasets", None) is not None
        else InMemoryDatasetStore(),
        models=getattr(state, "target_models", None),
        lists=getattr(state, "list_store", None),
        rows_kept=getattr(state, "list_rows", None),
    )  # fmt: skip


def _rule_reach_from(state: Any) -> rule_editor.RuleReach:
    datasets = getattr(state, "datasets", None)
    return rule_editor.rule_reach_of(datasets if datasets is not None else InMemoryDatasetStore())


def get_rule_reach(request: Request) -> rule_editor.RuleReach:
    return _rule_reach_from(request.app.state)


RuleReachDep = Annotated[rule_editor.RuleReach, Depends(get_rule_reach)]


def get_rule_lists(request: Request) -> rule_editor.RuleListReader:
    return _rule_lists_of(request.app.state)


RuleListsDep = Annotated[rule_editor.RuleListReader, Depends(get_rule_lists)]


def get_case_views(request: Request) -> CaseViewStore:
    """ADR-144. The lifespan sets the Postgres store; a test app with no lifespan gets an in-memory
    one."""
    store = getattr(request.app.state, "case_views", None)
    if store is None:
        store = InMemoryCaseViewStore()
        request.app.state.case_views = store
    return store


CaseViewsDep = Annotated[CaseViewStore, Depends(get_case_views)]


def get_board_items(request: Request) -> BoardItemStore:
    """ADR-143 decision 5. The lifespan sets the Postgres store; a test app with no lifespan gets
    an in-memory one."""
    store = getattr(request.app.state, "board_items", None)
    if store is None:
        store = InMemoryBoardItemStore()
        request.app.state.board_items = store
    return store


BoardItemsDep = Annotated[BoardItemStore, Depends(get_board_items)]


def get_promotion_store(request: Request) -> PromotionStore:
    """ADR-143 decision 8 (L3.4). The lifespan sets the Postgres store; a test app with no
    lifespan gets an in-memory one."""
    store = getattr(request.app.state, "promotions", None)
    if store is None:
        store = InMemoryPromotionStore()
        request.app.state.promotions = store
    return store


PromotionStoreDep = Annotated[PromotionStore, Depends(get_promotion_store)]


def get_ontology(request: Request) -> OntologySchema:
    return request.app.state.ontology  # type: ignore[no-any-return]


def get_map_config(request: Request) -> MapConfig:
    """ADR-147: the map as *Admin › Maps* holds it where the app has one (its maps file once changed
    there, else `osprey.yaml`'s), so a change reaches the map with no restart."""
    admin = getattr(request.app.state, "map_admin", None)
    if admin is not None:
        return admin.config()  # type: ignore[no-any-return]
    return request.app.state.map_config  # type: ignore[no-any-return]


def get_case_gazetteers(request: Request) -> Any:
    """ADR-147 Amendment 2: the store of each case's added gazetteers."""
    store = getattr(request.app.state, "case_gazetteers", None)
    if store is None:
        raise HTTPException(status_code=503, detail="the case gazetteers are not running")
    return store


CaseGazetteersDep = Annotated[Any, Depends(get_case_gazetteers)]


def get_map_admin(request: Request) -> map_admin_module.MapAdmin:
    admin = getattr(request.app.state, "map_admin", None)
    if admin is None:
        raise HTTPException(status_code=503, detail="map administration is not running")
    return admin  # type: ignore[no-any-return]


def _map_key(request: Request, provider_id: str) -> str | None:
    admin = getattr(request.app.state, "map_admin", None)
    return admin.key_for(provider_id) if admin is not None else None


def get_valkey(request: Request) -> Valkey:
    return request.app.state.valkey  # type: ignore[no-any-return]


def get_model_routes(request: Request) -> ModelRoutes:
    """ADR-135: the engines as the routing reads them — *Admin › Models*' (ADR-135 Amendment 2)
    where the app holds it, else the Conduit's own environment."""
    admin = getattr(request.app.state, "model_admin", None)
    if admin is not None:
        return admin.routes()  # type: ignore[no-any-return]
    return routes_from_env(DeploymentModels.from_env(), os.environ)


def get_model_admin(request: Request) -> model_admin_module.ModelAdmin:
    admin = getattr(request.app.state, "model_admin", None)
    if admin is None:
        raise HTTPException(status_code=503, detail="model administration is not running")
    return admin  # type: ignore[no-any-return]


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


def get_monitoring_settings(request: Request) -> MonitoringSettings:
    """ADR-133 ruling 3. A test app with no lifespan reads the schema's defaults."""
    return getattr(request.app.state, "monitoring", None) or MonitoringSettings()


def get_monitors_store(request: Request) -> MonitorStore:
    return request.app.state.monitors_store  # type: ignore[no-any-return]


def get_alerts_store(request: Request) -> AlertStore:
    return request.app.state.alerts_store  # type: ignore[no-any-return]


def get_typology_rules(request: Request) -> TypologyRuleStore:
    return request.app.state.typology_rules  # type: ignore[no-any-return]


def get_strength_influencers(request: Request) -> InfluencerStore:
    return request.app.state.strength_influencers  # type: ignore[no-any-return]


def get_optional_strength_influencers(request: Request) -> InfluencerStore | None:
    """For a route that judges rules (a run, Verify, a release, a preview): the store when the
    application holds one; without it, a strength condition judges with the weights file's
    influencers alone (`sentence_rules.strength_context`)."""
    return getattr(request.app.state, "strength_influencers", None)


def get_strength_defaults(request: Request) -> StrengthDefaults:
    return request.app.state.strength_defaults  # type: ignore[no-any-return]


def get_held_rows(request: Request) -> HeldRowStore:
    return request.app.state.held_rows  # type: ignore[no-any-return]


def get_screening_lists(request: Request) -> ScreeningListStore:
    return request.app.state.screening_lists  # type: ignore[no-any-return]


def get_optional_screening_lists(request: Request) -> ScreeningListStore | None:
    """For the rule audit's reads: the store, to read a list's marking as it stands now; an app
    started without it (a test's) reads the marking each entry recorded alone."""
    return getattr(request.app.state, "screening_lists", None)


def get_kyc_expiries(request: Request) -> KycExpiryStore:
    return request.app.state.kyc_expiries  # type: ignore[no-any-return]


def get_judgements_store(request: Request) -> JudgementStore:
    return request.app.state.judgements_store  # type: ignore[no-any-return]


def get_identity_admin(request: Request) -> PeopleDirectory:
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


def get_grading_settings(request: Request) -> GradingSettings:
    """The setting the start read; with none (an app not started through `lifespan`, as in a
    test), read from the environment the same way, refusing an unknown scheme, never a default."""
    held = getattr(request.app.state, "grading", None)
    return held if held is not None else GradingSettings.from_env()


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


def people_directory(resources: Any, config: ApiConfig) -> PeopleDirectory:
    """Admin › People's and Dashboards' directory: the deployment's own store on Entra ID sign-in
    (ADR-148 Amendment 8), told the Glass's and this API's own application ids, which it never
    registers as dashboard identities (Amendment 10); Keycloak's admin API otherwise."""
    if resources.people_store is not None:
        mapping = resources.principal_resolver.claim_mapping
        return EntraPeopleAdmin(
            resources.people_store, own_clients=(mapping.client_id, mapping.api_client_id)
        )
    return IdentityAdmin(
        config,
        by_email=os.environ.get("OSPREY_SIGN_IN_EMAIL", "").lower() == "true",
        organisation=os.environ.get("OSPREY_ORGANISATION_SIGN_IN") or None,
    )


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Principal:
    """Who is asking, and (ADR-099) what they may read: the datasets of the case the path names,
    or none outside a case. Every principal a route is given comes through here, the Studio's
    role checks included, so no request reads unlimited (`dataset_scope.py`)."""
    resolver: PrincipalResolver = request.app.state.principal_resolver
    try:
        identity = await resolver.resolve_principal(credentials.credentials)
    except PrincipalResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except SigningKeysUnavailable as exc:
        # ADR-148 Amendment 8: the identity provider's keys could not be read; said so, never as a
        # rejected token.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "identity_provider_unavailable",
                "message": "sign-in is unavailable: the identity provider could not be reached. "
                "Try again shortly.",
            },
        ) from exc
    except PrincipalLookupUnavailable as exc:
        # ADR-148 Amendment 8: the person's stored roles could not be read; never a principal
        # without them.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "people_store_unavailable",
                "message": "sign-in is unavailable: this deployment could not read your roles. "
                "Try again shortly.",
            },
        ) from exc
    # ADR-148 Amendment 10: a principal admitted to named routes alone (a dashboard identity on
    # Entra ID) is refused every other, before anything is read for it.
    if identity.routes is not None:
        route = request.scope.get("route")
        asked = f"{request.method} {getattr(route, 'path', request.url.path)}"
        if asked not in identity.routes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "route_not_admitted",
                    "message": "this identity is admitted only to "
                    + ", ".join(sorted(identity.routes)),
                },
            )
    # The token's own roles, kept apart for what must read a custom role's rights afresh later
    # (the delta socket's ticket, `issue_ws_ticket`).
    request.state.token_roles = list(identity.roles)
    identity = await with_custom_roles(request.app, identity)
    investigation_id = request.path_params.get("investigation_id")
    dataset_id = request.path_params.get("dataset_id")
    if (
        investigation_id is None
        and dataset_id is not None
        and request.url.path.startswith("/v1/datasets/")
    ):
        # ADR-140 Amendment 4: a Studio route of a dataset reads that dataset alone, and only for
        # someone one of whose cases loads into it; for anyone else it reads none, and
        # `require_studio_dataset` answers 404.
        scoped = await scope_to_dataset(
            identity, dataset_id, get_investigations(request), get_datasets(request)
        )
        return scoped if scoped is not None else outside_any_case(identity)
    if investigation_id is None:
        return outside_any_case(identity)
    return await scope_to_case(
        identity,
        investigation_id,
        get_datasets(request),
        holds_a_level=holds_a_level_in(lambda: get_investigations(request)),
    )


async def with_custom_roles(app_: Any, principal: Principal) -> Principal:
    """ADR-145 Amendment 5 (Q1 (a)): a custom role's current rights, read now from the store and
    added as single grants, so every right check reads them; never kept between requests. Without
    the store (an app with no lifespan, as some tests run it) a custom role confers nothing."""
    store = getattr(app_.state, "custom_roles", None)
    if store is None or not custom_role_ids(principal.roles):
        return principal
    return cast("Principal", await store.expand(principal))


def _owner_with_custom_roles(app_: Any, resolve: Callable[[str], Awaitable[Principal]]) -> Any:
    """A schedule's owner as a request's principal is: with their custom roles' rights."""

    async def resolved(owner_id: str) -> Principal:
        return await with_custom_roles(app_, await resolve(owner_id))

    return resolved


def get_watch_reach(request: Request) -> DatasetReach:
    """`owner_reaches_dataset_in` over this app's stores, for a route whose load runs watches."""
    return owner_reaches_dataset_in(
        lambda: request.app.state.datasets, lambda: get_investigations(request)
    )


WatchReachDep = Annotated[DatasetReach, Depends(get_watch_reach)]


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
MapAdminDep = Annotated[map_admin_module.MapAdmin, Depends(get_map_admin)]


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
MonitoringSettingsDep = Annotated[MonitoringSettings, Depends(get_monitoring_settings)]
MonitorsStoreDep = Annotated[MonitorStore, Depends(get_monitors_store)]
AlertsStoreDep = Annotated[AlertStore, Depends(get_alerts_store)]
TypologyRulesDep = Annotated[TypologyRuleStore, Depends(get_typology_rules)]
StrengthInfluencersDep = Annotated[InfluencerStore, Depends(get_strength_influencers)]
OptionalStrengthInfluencersDep = Annotated[
    InfluencerStore | None, Depends(get_optional_strength_influencers)
]
StrengthDefaultsDep = Annotated[StrengthDefaults, Depends(get_strength_defaults)]
HeldRowsDep = Annotated[HeldRowStore, Depends(get_held_rows)]
ScreeningListsDep = Annotated[ScreeningListStore, Depends(get_screening_lists)]
OptionalScreeningListsDep = Annotated[
    ScreeningListStore | None, Depends(get_optional_screening_lists)
]
KycExpiriesDep = Annotated[KycExpiryStore, Depends(get_kyc_expiries)]


def get_recipe_runs(request: Request) -> RecipeRunStore:
    return request.app.state.recipe_runs  # type: ignore[no-any-return]


def get_run_quotas(request: Request) -> QuotaStore | None:
    return getattr(request.app.state, "run_quotas", None)


RunQuotasDep = Annotated[QuotaStore | None, Depends(get_run_quotas)]


async def get_service_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> str:
    """The run API's caller (ADR-141 decision 10): the client a service identity's token names,
    or 401 in words. Never a `Principal`: a service identity reads nothing as itself. Its keys are
    read in the keys' own threads, bounded in total, as a person's are (ADR-148 Amendment 8; never
    anyio's shared pool, with no bound of its own)."""
    verifier: ServiceIdentityVerifier = request.app.state.service_identities
    try:
        client = await in_keys_thread(verifier.client_of, credentials.credentials)
    except SigningKeysUnavailable as unavailable:
        raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable
    except ServiceIdentityRefused as refused:
        raise HTTPException(status_code=refused.status, detail=str(refused)) from refused
    # ADR-148 Amendment 10: a client Admin › Dashboards registered is a dashboard identity, which
    # reads the report feed and never submits runs, whatever its token holds. The read is bounded as
    # a person's stored roles are; past it, the same 503.
    store = getattr(request.app.state, "people_store", None)
    if store is not None:
        try:
            registered = await asyncio.wait_for(
                store.dashboard(store.tenant_id, client), timeout=ROLE_LOOKUP_TIMEOUT_SECONDS
            )
        except Exception as exc:  # noqa: BLE001 - any failure of the read is the one 503
            raise HTTPException(
                status_code=503, detail="the dashboard identities could not be read"
            ) from exc
        if registered is not None:
            raise HTTPException(status_code=403, detail=DASHBOARD_IS_NO_SERVICE_IDENTITY)
    return client


ServiceIdentityDep = Annotated[str, Depends(get_service_identity)]


RecipeRunsDep = Annotated[RecipeRunStore, Depends(get_recipe_runs)]
JudgementsStoreDep = Annotated[JudgementStore, Depends(get_judgements_store)]
PrincipalNamesDep = Annotated[PrincipalNameDirectory, Depends(get_principal_names)]
IdentityAdminDep = Annotated[PeopleDirectory, Depends(get_identity_admin)]


def get_custom_roles(request: Request) -> CustomRoleStore:
    return request.app.state.custom_roles  # type: ignore[no-any-return]


def get_admin_people(request: Request) -> AdminPeopleStore:
    return request.app.state.admin_people  # type: ignore[no-any-return]


CustomRolesDep = Annotated[CustomRoleStore, Depends(get_custom_roles)]


def get_audit_section(request: Request) -> audit_section_module.AuditSectionReader:
    return request.app.state.audit_section  # type: ignore[no-any-return]


def get_promotion_ageing(request: Request) -> promotion_ageing_module.PromotionAgeingStore:
    return request.app.state.promotion_ageing  # type: ignore[no-any-return]


def get_waiting_promotions(request: Request) -> promotion_ageing_module.WaitingPromotions:
    return request.app.state.waiting_promotions  # type: ignore[no-any-return]


AuditSectionDep = Annotated[audit_section_module.AuditSectionReader, Depends(get_audit_section)]
PromotionAgeingDep = Annotated[
    promotion_ageing_module.PromotionAgeingStore, Depends(get_promotion_ageing)
]
WaitingPromotionsDep = Annotated[
    promotion_ageing_module.WaitingPromotions, Depends(get_waiting_promotions)
]
AdminPeopleDep = Annotated[AdminPeopleStore, Depends(get_admin_people)]


def get_ownership(request: Request) -> PostgresOwnershipStore:
    return request.app.state.ownership  # type: ignore[no-any-return]


OwnershipDep = Annotated[PostgresOwnershipStore, Depends(get_ownership)]


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
GradingSettingsDep = Annotated[GradingSettings, Depends(get_grading_settings)]
JobsDep = Annotated[JobQueue, Depends(get_jobs)]
ValkeyDep = Annotated[Valkey, Depends(get_valkey)]
ModelRoutesDep = Annotated[ModelRoutes, Depends(get_model_routes)]
SiteImageStorageDep = Annotated[ObjectStorageConfig, Depends(get_site_image_storage)]
TileCacheStorageDep = Annotated[ObjectStorageConfig, Depends(get_tile_cache_storage)]
AnalyticsDep = Annotated[AnalyticsPort, Depends(get_analytics)]


def get_staging_storage(request: Request) -> ObjectStorageConfig:
    """ADR-140 Amendment 12: where a staged run's Parquet, its sources' raw rows and a reference
    list's rows are kept, the bucket the engine's own staging names."""
    return ObjectStorageConfig.from_env()


StagingStorageDep = Annotated[ObjectStorageConfig, Depends(get_staging_storage)]


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


async def require_rules_place(principal: PrincipalDep) -> Principal:
    """ADR-146 decision 2: Rules and Monitoring's gate, asked by every route of the place beside the
    right its own action takes (`rules_place.py`), checked after that right (whose refusal names
    it) and before anything the route reads: 403 `place_required`, so a right that only acts in the
    place never opens it."""
    if not opens_rules_place(principal.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=rules_place_refusal())
    return principal


require_rules_place.required_place = RULES_PLACE  # type: ignore[attr-defined]


#: ADR-112: a Studio role's check, read as the right it always meant, so `data_engineer` — which
#: holds the rights and not the old role names — passes where `source_author` once did.
_STUDIO_ROLE_RIGHT: dict[StudioRole, Right] = {
    StudioRole.SOURCE_AUTHOR: Right.EDIT_PIPELINES,
    StudioRole.SOURCE_APPROVER: Right.PUBLISH_PIPELINES,
    StudioRole.LOADER: Right.RUN_PIPELINES,
}


#: The built-in roles as a person reads them (Admin › Roles' catalogue, and the Studio's refusals).
BUILT_IN_ROLE_LABELS = {
    "analyst": "Analyst",
    "data_engineer": "Data Engineer",
    "osprey-admin": "Admin",
    "reports_viewer": "Reports Viewer",
    "rule_author": "Rule author",
}
_STUDIO_ACTION_WORDS: dict[StudioRole, str] = {
    StudioRole.SOURCE_AUTHOR: "edit pipelines",
    StudioRole.SOURCE_APPROVER: "deploy pipelines",
    StudioRole.LOADER: "run pipelines",
}


def studio_role_refusal(role: StudioRole) -> str:
    """A missing studio role in words (CARRIES row 40; ADR-145 Amendment 4 decision 12, the owner's
    ruling (c)): the action, and the roles that hold its right, never the role's id or a person."""
    right = _STUDIO_ROLE_RIGHT[role]
    holders = [BUILT_IN_ROLE_LABELS[r] for r, rights in ROLE_RIGHTS.items() if right in rights]
    if right in rights_for(SUPER_USER_PRESET):
        holders.append("Super user")
    held = " or ".join(holders) if holders else "no built-in role"
    return (
        f"You may not {_STUDIO_ACTION_WORDS[role]} here. It is held by the {held} role, or by a "
        "custom role an administrator gives it to; ask an administrator in Admin › Roles."
    )


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
                detail=studio_role_refusal(role),
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


async def with_derived_packs(
    case: Investigation, datasets: DatasetStore, models: TargetModelStore
) -> Investigation:
    """The case with its packs as ADR-126 Amendment 2 derives them, from its dataset's live domain
    model; as stored while that dataset has no model yet (Amendment 3)."""
    derived = await packs_of_case(case.id, datasets, models)
    return case if derived is None else case.model_copy(update={"domains": derived})


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
        datasets: DatasetsDep,
        models: TargetModelsDep,
    ) -> Investigation:
        case = await _authorize(
            investigation_id, principal, investigations, audit, level, admin_safety_net
        )
        return await with_derived_packs(case, datasets, models)

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


_AT_EDITOR = _authorized_at(AccessLevel.EDITOR)
_AT_AUTHOR = _authorized_at(AccessLevel.AUTHOR)
InvestigationEditorDep = Annotated[Investigation, Depends(_AT_EDITOR)]
InvestigationAuthorDep = Annotated[Investigation, Depends(_AT_AUTHOR)]


async def refuse_loading_in_a_composite_case(
    investigation: InvestigationEditorDep, datasets: DatasetsDep
) -> None:
    """ADR-099 Amendment 15: a case reading a composite loads, runs, schedules, publishes and
    uploads nothing (a composite is read-only for now). After the case's own level check, so a
    caller who may not open the case is still answered as for a missing one. It depends on the
    very check the route's own `InvestigationEditorDep` does, so FastAPI runs it once and the
    route declares one level (`test_investigation_levels.py`). A case reading a drawn dataset
    (its home case) loads nothing either (ADR-143 Amendment 2 decision 5)."""
    await refuse_in_a_composite_case()
    await _refuse_in_a_drawn_case(investigation, datasets, DrawnNotLoaded)


async def refuse_deciding_held_rows_in_a_composite_case(
    investigation: InvestigationAuthorDep, datasets: DatasetsDep
) -> None:
    """The same refusal for the held-rows routes, which need an author."""
    await refuse_in_a_composite_case()
    await _refuse_in_a_drawn_case(investigation, datasets, DrawnNotLoaded)


class NoRuleOnADrawnDataset(Exception):
    """ADR-143 Amendment 2 decision 5: no rule runs on a drawn dataset until it is merged."""


@app.exception_handler(NoRuleOnADrawnDataset)
async def _no_rule_on_a_drawn_dataset_handler(
    request: Request, exc: NoRuleOnADrawnDataset
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": "drawn_not_judged",
            "detail": "no rule runs on a drawn dataset until it is merged into another, so none "
            "is made, changed or made live in its case",
        },
    )


async def _refuse_in_a_drawn_case(
    investigation: Investigation, datasets: DatasetStore, refusal: type[Exception]
) -> None:
    chosen = await datasets.chosen_of_case(investigation.id)
    if chosen and chosen[0].kind == DRAWN:
        raise refusal


async def refuse_rules_in_a_drawn_case_as_author(
    investigation: InvestigationAuthorDep, datasets: DatasetsDep
) -> None:
    await _refuse_in_a_drawn_case(investigation, datasets, NoRuleOnADrawnDataset)


async def refuse_rules_in_a_drawn_case_as_editor(
    investigation: InvestigationEditorDep, datasets: DatasetsDep
) -> None:
    await _refuse_in_a_drawn_case(investigation, datasets, NoRuleOnADrawnDataset)


NoLoadingInACompositeCase = Depends(refuse_loading_in_a_composite_case)
NoHeldRowsInACompositeCase = Depends(refuse_deciding_held_rows_in_a_composite_case)
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


@app.exception_handler(ViewNotFound)
async def _view_not_found_handler(request: Request, exc: ViewNotFound) -> JSONResponse:
    """ADR-144 decision 3: someone else's private view, another case's, and none at all alike."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "view_not_found"})


@app.exception_handler(NotTheViewsCreator)
async def _not_the_views_creator_handler(request: Request, exc: NotTheViewsCreator) -> JSONResponse:
    """ADR-144 decision 3: a shared view is shared or deleted only by the person who saved it."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "not_the_views_creator",
            "detail": "Only the person who saved this view can share or delete it.",
        },
    )


@app.exception_handler(BoardNotFound)
async def _board_not_found_handler(request: Request, exc: BoardNotFound) -> JSONResponse:
    """ADR-143 decision 5: someone else's private board, another case's, and none at all alike."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "board_not_found"})


@app.exception_handler(ItemNotFound)
async def _drawn_item_not_found_handler(request: Request, exc: ItemNotFound) -> JSONResponse:
    """An item of another case, one the reader may not see, and none at all alike (rule 3)."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "item_not_found"})


@app.exception_handler(NotTheBoardsCreator)
async def _not_the_boards_creator_handler(
    request: Request, exc: NotTheBoardsCreator
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "not_the_boards_creator",
            "detail": "Only the person who made this board draws on it. Make a board of your own "
            "from this one's view to draw.",
        },
    )


@app.exception_handler(DrawnOnItsBoard)
async def _drawn_on_its_board_handler(request: Request, exc: DrawnOnItsBoard) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "drawn_on_its_board",
            "detail": "This was drawn on a board: only the person who drew it changes or "
            "withdraws it, there (Edit on board).",
        },
    )


@app.exception_handler(DrawingRefused)
async def _drawing_refused_handler(request: Request, exc: DrawingRefused) -> JSONResponse:
    """A drawing refused in words, before anything was written (ADR-143 Amendment 2 decision 3)."""
    return JSONResponse(status_code=exc.status, content={"error": exc.code, "detail": exc.message})


@app.exception_handler(TypologyRuleNotFoundError)
async def _typology_rule_not_found_handler(
    request: Request, exc: TypologyRuleNotFoundError
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "rule_not_found"})


@app.exception_handler(InfluencerChangeRefused)
async def _influencer_change_refused_handler(
    request: Request, exc: InfluencerChangeRefused
) -> JSONResponse:
    """ADR-139 decision 3: a proposal, approval or sending back that cannot be made, in words."""
    said = str(exc)
    return JSONResponse(
        status_code=409,
        content={"error": "influencer_change_refused", "message": f"{said[0].upper()}{said[1:]}."},
    )


@app.exception_handler(OwnInfluencerChangeRefused)
async def _own_influencer_change_handler(
    request: Request, exc: OwnInfluencerChangeRefused
) -> JSONResponse:
    return JSONResponse(
        status_code=403, content={"detail": {"error": "own_change", "message": str(exc)}}
    )


@app.exception_handler(InfluencerRefused)
async def _influencer_refused_handler(request: Request, exc: InfluencerRefused) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "influencer_refused", "influencer": exc.influencer,
                 "reason": exc.reason},
    )  # fmt: skip


@app.exception_handler(RuleChangeRefused)
async def _rule_change_refused_handler(request: Request, exc: RuleChangeRefused) -> JSONResponse:
    """ADR-133 decision 7: a change, approval or rejection that cannot be made, in words. ADR-146
    decision 3: a rule's dataset changed, or a rule made live untested, each with its own code."""
    said = str(exc)
    error = (
        "rule_dataset_fixed" if isinstance(exc, RuleDatasetFixed)
        else "rule_untested" if isinstance(exc, RuleUntested)
        else "rule_change_refused"
    )  # fmt: skip
    return JSONResponse(
        status_code=409, content={"error": error, "message": f"{said[0].upper()}{said[1:]}."}
    )


@app.exception_handler(rule_editor.ListNotOffered)
async def _rule_list_not_offered_handler(
    request: Request, exc: rule_editor.ListNotOffered
) -> JSONResponse:
    """ADR-146 decision 3: a rule names only a list its dataset may read; any other is refused
    exactly as a list that does not exist (rule 3)."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "list_not_found", "detail": "There is no such list."},
    )


@app.exception_handler(rule_editor.DatasetNotOffered)
async def _rule_dataset_not_offered_handler(
    request: Request, exc: rule_editor.DatasetNotOffered
) -> JSONResponse:
    """ADR-146 decision 3: a rule declared on anything but the case's own source or composite is
    refused exactly as a dataset that does not exist (rule 3)."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "dataset_not_found", "detail": "There is no such dataset."},
    )


@app.exception_handler(alert_queue.CloseRefused)
async def _close_refused_handler(request: Request, exc: alert_queue.CloseRefused) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": {"error": "own_change",
                                                             "message": str(exc)}})  # fmt: skip


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


@app.exception_handler(AboveTheDeploymentCeiling)
async def _above_the_ceiling_handler(
    request: Request, exc: AboveTheDeploymentCeiling
) -> JSONResponse:
    """ADR-148 decision 10: a load or an import marked above the deployment's highest marking is
    refused before anything is written, in words that say the limit, never the content."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "above_the_deployments_highest_marking",
            # `detail` is what the Glass shows a person (`AddFiles.tsx`, `entityPictures.ts`).
            "detail": exc.problems[0],
            "problems": exc.problems,
        },
    )


def refuse_above_the_deployment_ceiling(request: Request, classification: str) -> None:
    """An import that carries its own marking (a document, an entity's picture), judged before its
    body is read: refused when the marking is a classification of the scheme above the deployment's
    highest. One the scheme does not know is left to the route's own marking check."""
    held = getattr(request.app.state, "deployment_ceiling", None)
    ceiling = held if held is not None else DeploymentCeiling.from_env()
    if classification in ceiling.scheme.classification and ceiling.above(classification):
        raise AboveTheDeploymentCeiling(ceiling.marking, "import")


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
    return JSONResponse(status_code=409, content={"error": "run_in_progress", "message": str(exc)})


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


@app.exception_handler(CompositeReadOnlyError)
async def _composite_read_only_handler(
    request: Request, exc: CompositeReadOnlyError
) -> JSONResponse:
    """ADR-099 Amendment 15 (the owner, 7 November 2026): a composite is read-only for now; nothing
    was written."""
    return JSONResponse(
        status_code=409, content={"error": "composite_read_only", "detail": str(exc)}
    )


@app.exception_handler(NoModelYet)
async def _no_model_yet_handler(request: Request, exc: NoModelYet) -> JSONResponse:
    """A dataset with no domain model yet (ADR-126 Amendment 3: seeded with step 3)."""
    return JSONResponse(status_code=409, content={"error": "no_model_yet", "detail": str(exc)})


@app.exception_handler(TargetModelRefused)
async def _model_refused_handler(request: Request, exc: TargetModelRefused) -> JSONResponse:
    """A change to a dataset's domain model refused in words, before anything was written (ADR-140
    decision 5)."""
    return JSONResponse(status_code=409, content={"error": "model_refused", "detail": str(exc)})


@app.exception_handler(ReadOnlyLayerError)
async def _read_only_layer_handler(request: Request, exc: ReadOnlyLayerError) -> JSONResponse:
    """ADR-144 Amendment 1 decision 2: an unconverted case reads its original's layer, writes none;
    refused before anything was written."""
    return JSONResponse(
        status_code=409, content={"error": "original_layer_read_only", "detail": str(exc)}
    )


@app.exception_handler(NoAnalystLayerError)
async def _no_analyst_layer_handler(request: Request, exc: NoAnalystLayerError) -> JSONResponse:
    """ADR-143 Amendment 1 item 3: an analyst's own write with no case's layer to go into (the
    case reads nothing): refused, and nothing was written, rather than written into a source."""
    return JSONResponse(
        status_code=409,
        content={
            "error": "no_analyst_layer",
            "detail": "This case reads no dataset yet, so there is nowhere to keep what you mark "
            "or link; nothing was written.",
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


@app.exception_handler(ModelLimitReached)
async def _model_limit_reached_handler(request: Request, exc: ModelLimitReached) -> JSONResponse:
    """ADR-135 Amendment 3: an engine's limit stopped the call. Said in the Conduit's own words,
    never the gateway's (which name its key's hash or part of it)."""
    headers = {}
    if exc.resets_at is not None:
        wait = max(1, int((exc.resets_at - datetime.now(UTC)).total_seconds()))
        headers["Retry-After"] = str(wait)
    return JSONResponse(
        status_code=429,
        content={"error": "model_limit_reached", "detail": exc.words},
        headers=headers,
    )


@app.exception_handler(EngineRefused)
async def _engine_refused_handler(request: Request, exc: EngineRefused) -> JSONResponse:
    """ADR-135 decision 4: a named engine not enabled, with no key, or with no model for the role.
    Nothing was sent."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "engine_refused", "detail": str(exc)},
    )


@app.exception_handler(QuotaRefused)
async def _quota_refused_handler(request: Request, exc: QuotaRefused) -> JSONResponse:
    """ADR-141 decision 6: a run past a quota, refused in words; the ledger has it *refused*."""
    return JSONResponse(status_code=429, content={"error": "quota_used", "detail": str(exc)})


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


@app.exception_handler(SentenceRefused)
async def _sentence_refused_handler(request: Request, exc: SentenceRefused) -> JSONResponse:
    """ADR-133 decision 1: a sentence naming what the ontology does not declare, or a choice that
    does not fit what it names, is refused at validation by its blank, typed, in words."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=exc.refusal.model_dump()
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


@app.exception_handler(SourceChangedSinceVerifyError)
async def _source_changed_since_verify_handler(
    request: Request, exc: SourceChangedSinceVerifyError
) -> JSONResponse:
    """Build order step 30: a *Run now* whose file is not the one Verify checked, in words."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "source_changed_since_verify", "detail": str(exc)},
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
    #: ADR-099 Amendment 12 item 6 (R16): *Use an existing dataset* names exactly one, a source or a
    #: composite of the creator's unit; *Make a new dataset* names it instead (`new_dataset_name`,
    #: an empty dataset of the creator's unit). One or the other; neither, or both, is refused.
    #: The Conduit no longer makes a case a dataset of its own when it names none.
    dataset_ids: list[str] | None = None
    new_dataset_name: str | None = Field(default=None, max_length=MAX_DATASET_NAME)
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
    models: TargetModelsDep,
    audit: AuditDep,
    body: CreateInvestigationInput | None = None,
) -> Investigation:
    """Needs no grant: whoever creates a case is its first Author (ADR-052 §4). The name is
    optional here only until the Glass proposes one (stage 3), after which it is required.
    ADR-099 Amendment 12: the case reads exactly one dataset, named or made here, checked before
    the case exists, so a refusal leaves none. ADR-143 decision 1: the case's analyst layer is made
    with it (`set_for_case`)."""
    name = (body.name if body is not None else None) or DEFAULT_CASE_NAME
    named = list(dict.fromkeys(body.dataset_ids or [])) if body is not None else []
    new_name = (body.new_dataset_name or "").strip() if body is not None else ""
    if bool(named) == bool(new_name) or len(named) > 1:
        raise DatasetRefusedError("a case reads exactly one dataset: name one, or a new one")
    if named:
        own = {d.id for d in await datasets.list_for(principal)}
        if not set(named) <= own:
            raise DatasetRefusedError("not every dataset is one of this unit's")
    else:
        # Made before the case, so a name already taken refuses the whole request.
        named = [(await datasets.create(principal, new_name)).id]
    # ADR-126 Amendment 2: a case reading a dataset with a live model takes its packs from the
    # model, so packs sent with it are not stored (they would only stand again were the model
    # gone, which it never is). They are kept for a dataset with no model yet (Amendment 3).
    given = body.domains if body is not None else None
    if given is not None and await models.live(named[0]) is not None:
        given = None
    investigation = await investigations.create(principal, name=name, domains=given)
    await datasets.set_for_case(investigation.id, named, principal, case_name=investigation.name)
    await audit.record(
        principal=principal,
        action="create_investigation",
        investigation_id=investigation.id,
        resolved_query={"dataset_ids": list(named)},
        result_cardinality=1,
    )
    return await with_derived_packs(investigation, datasets, models)


@app.get("/v1/datasets")
async def list_datasets_route(principal: PrincipalDep, datasets: DatasetsDep) -> list[Dataset]:
    """The datasets of the caller's unit, for a new case to name (ADR-099); none to a caller holding
    no right (Amendment 11: the store's query answers them nothing)."""
    return await datasets.list_for(principal)


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


@app.post(
    "/v1/datasets/composites",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.CREATE_CASE))],
)
async def create_composite_route(
    body: CreateCompositeRequest, principal: PrincipalDep, datasets: DatasetsDep, audit: AuditDep
) -> Dataset:
    """ADR-099 Amendment 12 item 2: a composite of the caller's unit's source datasets, read at read
    time as its members; nothing is copied. A member of another unit, a missing one, a composite and
    an analyst layer are refused alike (`dataset_refused`)."""
    composite = await datasets.create_composite(principal, body.name, body.member_ids)
    await audit.record(
        principal=principal,
        action="create_composite_dataset",
        resolved_query={"dataset_id": composite.id, "member_ids": composite.members},
        result_cardinality=len(composite.members),
    )
    return composite


@app.get("/v1/investigations/{investigation_id}/datasets")
async def case_datasets_route(
    investigation: InvestigationViewerDep, principal: PrincipalDep, datasets: DatasetsDep
) -> list[Dataset]:
    """The datasets this case reads (ADR-099); none to a caller holding no right (Amendment 11)."""
    return await datasets.of_case(investigation.id, principal)


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
    (ADR-099). Nothing else widens a case's datasets.

    A dataset's home case reads that dataset while it exists (ADR-145 Amendment 4 decision 2;
    L3.H1): choosing anything else for it is refused in words naming nothing beyond the case,
    before anything is written (re-choosing its own dataset changes nothing)."""
    home_of = await datasets.dataset_of_home_case(investigation.id)
    if home_of is not None and list(body.dataset_ids) != [home_of]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "home_case_kept",
                "message": "this is its dataset's home case, which holds the dataset's reports, "
                "alerts and promotion reviews, so it keeps reading its dataset while the dataset "
                "exists",
            },
        )
    before = [d.id for d in await datasets.of_case(investigation.id, principal)]
    changed = await datasets.set_for_case(
        investigation.id, body.dataset_ids, principal, case_name=investigation.name
    )
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
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    datasets: DatasetsDep,
    models: TargetModelsDep,
) -> list[InvestigationListing]:
    hidden = await investigations.hidden_tab_ids(principal)
    listed = [
        (await with_derived_packs(case, datasets, models), level)
        for case, level in await investigations.list_for(principal)
    ]
    return [
        InvestigationListing(
            id=case.id,
            name=case.name,
            level=level,
            created_at=case.created_at,
            created_by=case.created_by,
            domains=case.domains,
            tab_hidden=case.id in hidden,
            datasets=[d.name for d in reads],
            dataset_ids=[d.id for d in reads],
        )
        for case, level in listed
        for reads in [await datasets.of_case(case.id, principal)]
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
    if body.domains is not None:
        # ADR-126 Amendment 2: the packs come from the dataset's domain model, read-only here.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "packs_from_the_model",
                "message": "a case's domain packs come from its dataset's domain model: change "
                "them on the Ingest Studio's Model tab, where they change for every case reading "
                "the dataset",
            },
        )
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
    datasets: DatasetsDep,
    audit: AuditDep,
) -> None:
    """A soft remove (ADR-052 Amendment 7). An Author, or the administrator of the case's own unit
    through the safety net (a case no Author is left to remove); neither gains any read access. A
    dataset's home case is kept while its dataset exists (ADR-145 Amendment 4 decision 2)."""
    if await datasets.dataset_of_home_case(investigation.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "home_case_kept",
                "message": "this is its dataset's home case, which holds the dataset's reports, "
                "alerts and promotion reviews, so it is kept while the dataset exists",
            },
        )
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


async def _may_hold_a_level(
    request: Request, grantee: str, level: AccessLevel, names: PrincipalNameDirectory
) -> None:
    """Who may hold a level in a case (ADR-112 Amendment 5 decisions 3 and 5, reconciled with
    ADR-111 decision 7 by ADR-145 Amendment 5 point 7): a team that exists (`team:<role id>`); an
    enabled person; a dashboard identity as Viewer and no higher. Any other account the directory
    holds that is no person (a service account, or a disabled account), and a dashboard above
    Viewer, is refused in words (409 `service_account`). A deployment with no directory cannot
    tell, and a name it does not hold grants nothing to anyone, as before."""
    if grantee.startswith(TEAM_GRANT_PREFIX):
        store = getattr(request.app.state, "custom_roles", None)
        role_id = grantee[len(TEAM_GRANT_PREFIX) :]
        if store is None or await store.team(role_id, _today()) is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "no_such_team",
                    "message": f"there is no team {role_id} to give a level to",
                },
            )
        return
    people = await names.people([grantee])
    if people is not None and grantee in people:
        return
    # Not a person the directory holds, so its registration is read: on Entra ID the names
    # directory holds no people (`people` is None) and a registered dashboard is still a Viewer
    # and nothing more (ADR-148 Amendment 10). With no directory, an identity provider that
    # cannot answer leaves the grant as before: the deployment cannot tell.
    admin = getattr(request.app.state, "identity_admin", None)
    try:
        dashboards = {d.account_id for d in await admin.list_dashboards()} if admin else set()
    except IdentityAdminRefused:
        if people is None:
            return
        raise
    if grantee in dashboards:
        if level is AccessLevel.VIEWER:
            return
        raise HTTPException(
            status_code=409,
            detail={
                "error": "service_account",
                "message": f"a dashboard identity may be a Viewer of a case and nothing more; "
                f"{grantee} was asked to be {level.value}",
            },
        )
    if people is None:
        return
    raise HTTPException(
        status_code=409,
        detail={
            "error": "service_account",
            "message": f"{grantee} is not an enabled person: a service account owns nothing and "
            "is never a case member, and a disabled account holds no level",
        },
    )


@app.put(
    "/v1/investigations/{investigation_id}/access/grants/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_right(Right.SHARE_CASE))],
)
async def set_investigation_grant(
    request: Request,
    investigation: InvestigationAccessManagerDep,
    account_id: str,
    body: GrantInput,
    principal: PrincipalDep,
    principal_names: PrincipalNamesDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> None:
    grantee = _grantee(account_id)
    await _may_hold_a_level(request, grantee, body.level, principal_names)
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


# --- case views (ADR-144; spec 03 §3.1b) -----------------------------------------------------
#
# A view holds no data: every route stands behind the case's own level check first, so a reader
# with no level on the case is refused each one as for a case that does not exist, and the store
# answers only with views the reader may see (rule 3). Saving, sharing and deleting need
# `investigate`, the Viewer's right to work the case; listing and opening need only the level.


@app.get("/v1/investigations/{investigation_id}/views")
async def list_case_views(
    investigation: InvestigationViewerDep, principal: PrincipalDep, views: CaseViewsDep
) -> list[CaseView]:
    """The case's views this reader may see: their own, and those shared with the case."""
    return [v.wire() for v in await views.visible_in(investigation.id, principal.id)]


@app.post(
    "/v1/investigations/{investigation_id}/views",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def save_case_view(
    investigation: InvestigationViewerDep,
    body: CaseViewInput,
    principal: PrincipalDep,
    views: CaseViewsDep,
    audit: AuditDep,
) -> CaseView:
    """*Save what I see as a view* (ADR-144 decision 4): private to its creator until shared."""
    view = await views.save(investigation.id, body, principal.id)
    await audit.record(
        principal=principal,
        action="save_case_view",
        investigation_id=investigation.id,
        resolved_query={"view_id": view.id},
        result_cardinality=1,
    )
    return view.wire()


@app.get("/v1/investigations/{investigation_id}/views/{view_id}")
async def open_case_view(
    request: Request,
    investigation: InvestigationViewerDep,
    view_id: str,
    principal: PrincipalDep,
    views: CaseViewsDep,
    graph: GraphDep,
    working_set: WorkingSetDep,
    items: BoardItemsDep,
) -> CaseViewOpened:
    """ADR-144 decision 2: the view re-read now, as this reader may see the case; `missing` counts
    the chosen items it could not show and names none."""
    view = await views.get(investigation.id, view_id, principal.id)
    opened = await open_view(
        view, principal, graph=graph, working_set=working_set, cap_breach=_cap_breach
    )
    if view.merged_load is None:
        return opened
    # A merged drawing (ADR-143 Amendment 2 decision 7): what did not become data, as this reader
    # may see it, read through their own principal (rule 3).
    directory = getattr(request.app.state, "principal_names", None)
    noted = await drawn_merge_module.view_annotations(
        view, principal, graph=graph, items=items,
        names=directory.display_names if directory is not None else None,
    )  # fmt: skip
    return opened.model_copy(update={"annotations": noted})


@app.post(
    "/v1/investigations/{investigation_id}/views/{view_id}/share",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def share_case_view(
    investigation: InvestigationViewerDep,
    view_id: str,
    principal: PrincipalDep,
    views: CaseViewsDep,
    audit: AuditDep,
) -> CaseView:
    """*Share with the case* (ADR-144 decision 3): every member then sees it at their own level."""
    view = await views.share(investigation.id, view_id, principal.id)
    await audit.record(
        principal=principal,
        action="share_case_view",
        investigation_id=investigation.id,
        resolved_query={"view_id": view_id},
        result_cardinality=1,
    )
    return view.wire()


@app.delete(
    "/v1/investigations/{investigation_id}/views/{view_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def delete_case_view(
    investigation: InvestigationViewerDep,
    view_id: str,
    principal: PrincipalDep,
    views: CaseViewsDep,
    audit: AuditDep,
) -> None:
    """Only its creator deletes a view, and deleting it deletes nothing else (ADR-144 decision 3):
    what was drawn on it stays in the case's layer and on the case's canvas."""
    await views.delete(investigation.id, view_id, principal.id)
    await audit.record(
        principal=principal,
        action="delete_case_view",
        investigation_id=investigation.id,
        resolved_query={"view_id": view_id},
        result_cardinality=1,
    )


# --- drawing boards (ADR-143 decisions 4 to 7; Amendments 2 and 3; spec 03 §3.1c; L3.3) ---------
#
# A board is a case view with drawing on. Every route stands behind the case's own level check
# first, so a reader with no level on the case is refused as for a case that does not exist; the
# registry and the views store answer only by case, and every element is read through the
# reader's principal, scoped to the case's read set and filtered in the adapter (rule 3). Reading a
# board needs the case's level and `investigate`; drawing needs Editor and `draw_on_boards`.

#: Drawing needs reading too: a role holding `draw_on_boards` without `investigate` would make a
#: board it could not open (the orchestrator's review of L3.3, finding 6).
_DRAWS = [Depends(require_right(Right.DRAW_ON_BOARDS)), Depends(require_right(Right.INVESTIGATE))]
_READS_BOARDS = [Depends(require_right(Right.INVESTIGATE))]


def get_boards(
    request: Request,
    graph: GraphDep,
    views: CaseViewsDep,
    items: BoardItemsDep,
    datasets: DatasetsDep,
    ontology: OntologyDep,
    scheme: HandlingSchemeDep,
    models: TargetModelsDep,
) -> Boards:
    return Boards(
        graph=graph,
        views=views,
        items=items,
        datasets=datasets,
        ontology=ontology,
        scheme=scheme,
        models=models,
        media=getattr(request.app.state, "media", None),
        cap_breach=_cap_breach,
        case_types=getattr(request.app.state, "link_types", None),
    )


BoardsDep = Annotated[Boards, Depends(get_boards)]


async def _audit_board(
    audit: AuditWriter, principal: Principal, action: str, case_id: str, **query: Any
) -> None:
    await audit.record(
        principal=principal,
        action=action,
        investigation_id=case_id,
        resolved_query=query,
        result_cardinality=1,
    )


@app.get("/v1/investigations/{investigation_id}/boards", dependencies=_READS_BOARDS)
async def list_boards(
    investigation: InvestigationViewerDep, principal: PrincipalDep, boards: BoardsDep
) -> list[Board]:
    """The case's boards this reader may see: their own, and those shared with the case."""
    held = await boards.views.boards_in(investigation.id, principal.id)
    return [await boards.wire(b, principal) for b in held]


@app.post(
    "/v1/investigations/{investigation_id}/boards",
    status_code=status.HTTP_201_CREATED,
    dependencies=_DRAWS,
)
async def make_board(
    investigation: InvestigationEditorDep,
    body: BoardInput,
    principal: PrincipalDep,
    boards: BoardsDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
) -> Board:
    """*New drawing board* in this case: blank, from a view, or from a selection (decision 5)."""
    made = await boards.make(investigation.id, body, principal, projection=working_set)
    await _audit_board(audit, principal, "make_board", investigation.id, board_id=made.id,
                       start=body.start)  # fmt: skip
    return await boards.wire(made, principal)


@app.get("/v1/investigations/{investigation_id}/boards/{board_id}", dependencies=_READS_BOARDS)
async def open_board(
    investigation: InvestigationViewerDep,
    board_id: str,
    principal: PrincipalDep,
    boards: BoardsDep,
    grading: GradingSettingsDep,
    investigations: InvestigationsDep,
) -> BoardOpened:
    """The board now, as this reader may see it; `missing` counts what it could not show. It
    offers the deployment's grading scheme (`grading.scheme`, ADR-143 decision 11), and says
    whether this reader may promote from it, asked as the promotion routes ask (CARRIES, docs
    D2a: *Promote…* offered only to those the route admits; the route still refuses the rest)."""
    board = await boards.board(investigation.id, board_id, principal.id)
    opened = await boards.open(board, principal)
    may_draw = opened.may_draw and _may_draw(principal)
    return opened.model_copy(
        update={
            "may_draw": may_draw,
            # Exactly the promotion routes' check (the orchestrator's review, minor 7): the board's
            # own creator (`own_board`), `_PROMOTES`' rights and the case's Author level.
            "may_promote": board.created_by == principal.id
            and await _may_promote(investigation.id, principal, investigations),
            "grading_scheme": grading.scheme,
            "grading_grades": grading.grades,
        }
    )


def _graded_in_the_deployments_scheme(given: Grading | None, grading: GradingSettings) -> None:
    """ADR-143 decision 11: every drawn item is graded in the deployment's one scheme, so the
    change command's mapping covers them all; a grade in another is refused before any write."""
    if given is None:
        return
    try:
        grading.grades.check(given)
    except ValueError as refused:
        raise DrawingRefused(
            "grading_scheme", f"this deployment grades in {grading.scheme}: {refused}", status=422
        ) from None


def _may_draw(principal: Principal) -> bool:
    return Right.DRAW_ON_BOARDS in rights_for(principal.roles)


async def _may_promote(
    investigation_id: str, principal: Principal, investigations: InvestigationStore
) -> bool:
    """`_PROMOTES`' rights and the case's Author level (`InvestigationAuthorDep`), as asked of a
    promotion route."""
    held = rights_for(principal.roles)
    if Right.PROMOTE_TO_DATASET not in held or Right.INVESTIGATE not in held:
        return False
    try:
        await investigations.get_authorized(investigation_id, principal, need=AccessLevel.AUTHOR)
    except (InvestigationNotFoundError, InsufficientAccessError):
        return False
    return True


@app.post("/v1/investigations/{investigation_id}/boards/{board_id}/share", dependencies=_DRAWS)
async def share_board(
    investigation: InvestigationEditorDep,
    board_id: str,
    principal: PrincipalDep,
    boards: BoardsDep,
    audit: AuditDep,
) -> Board:
    """*Share with the case*: every member then sees the board, and what is on it at their level."""
    await boards.own_board(investigation.id, board_id, principal.id)
    shared = await boards.views.share(investigation.id, board_id, principal.id)
    await _audit_board(audit, principal, "share_board", investigation.id, board_id=board_id)
    return await boards.wire(shared, principal)


@app.delete(
    "/v1/investigations/{investigation_id}/boards/{board_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_DRAWS,
)
async def delete_board(
    investigation: InvestigationEditorDep,
    board_id: str,
    principal: PrincipalDep,
    boards: BoardsDep,
    audit: AuditDep,
) -> None:
    """Deleting a board never deletes what was drawn on it: that stays in the case's layer."""
    await boards.own_board(investigation.id, board_id, principal.id)
    await boards.views.delete(investigation.id, board_id, principal.id)
    await _audit_board(audit, principal, "delete_board", investigation.id, board_id=board_id)


@app.post(
    "/v1/investigations/{investigation_id}/boards/{board_id}/items",
    status_code=status.HTTP_201_CREATED,
    dependencies=_DRAWS,
)
async def declare_drawn_item(
    investigation: InvestigationEditorDep,
    board_id: str,
    body: DrawnItemInput,
    principal: PrincipalDep,
    boards: BoardsDep,
    audit: AuditDep,
    grading: GradingSettingsDep,
) -> DrawnItemMade:
    """*Add to board*: a node of the case's model, marked within the case's ceiling, graded and
    sourced (decision 4; Amendment 2 decision 3), with its watch (decision 8)."""
    board = await boards.own_board(investigation.id, board_id, principal.id)
    _graded_in_the_deployments_scheme(body.grading, grading)
    made = await boards.declare(board, body, principal)
    await _audit_board(audit, principal, "draw_item", investigation.id, board_id=board_id,
                       item_id=made.item_id, node_id=made.element_id, type=body.type,
                       classification=body.marking)  # fmt: skip
    return made


@app.post(
    "/v1/investigations/{investigation_id}/boards/{board_id}/links",
    status_code=status.HTTP_201_CREATED,
    dependencies=_DRAWS,
)
async def draw_link(
    investigation: InvestigationEditorDep,
    board_id: str,
    body: DrawnLinkInput,
    principal: PrincipalDep,
    boards: BoardsDep,
    audit: AuditDep,
    grading: GradingSettingsDep,
) -> DrawnItemMade:
    """A link between two items on the board (by the handle, Alt-drag, the menu or the form)."""
    board = await boards.own_board(investigation.id, board_id, principal.id)
    _graded_in_the_deployments_scheme(body.grading, grading)
    made = await boards.link(board, body, principal)
    await _audit_board(audit, principal, "draw_link", investigation.id, board_id=board_id,
                       item_id=made.item_id, edge_id=made.element_id, type=body.type,
                       classification=body.marking)  # fmt: skip
    return made


@app.put(
    "/v1/investigations/{investigation_id}/boards/{board_id}/layout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_DRAWS,
)
async def move_board_items(
    investigation: InvestigationEditorDep,
    board_id: str,
    body: BoardMove,
    principal: PrincipalDep,
    boards: BoardsDep,
) -> None:
    """Moving items is the board's own layout, not data (C7: dragging an item moves it)."""
    board = await boards.own_board(investigation.id, board_id, principal.id)
    await boards.move(board, body.positions, principal)


@app.patch("/v1/investigations/{investigation_id}/board-items/{item_id}", dependencies=_DRAWS)
async def edit_drawn_item(
    investigation: InvestigationEditorDep,
    item_id: str,
    body: DrawnItemEdit,
    principal: PrincipalDep,
    boards: BoardsDep,
    promotion_store: PromotionStoreDep,
    audit: AuditDep,
    grading: GradingSettingsDep,
) -> DrawnItemMade:
    """The author edits their own item; a marking is never lowered (decision 5). An item waiting
    for review raises its promotion's marking with its own (ADR-143 Amendment 5 decision 6a)."""
    _graded_in_the_deployments_scheme(body.grading, grading)
    made = await boards.edit(investigation.id, item_id, body, principal)
    if body.marking is not None:
        # `PromotionsDep` is declared below this route: the store is reached directly, as
        # `Promotions.item_marked` does (FastAPI drops a dependency it cannot resolve here).
        await promotion_store.raise_marking(
            investigation.id, item_id, body.marking, list(boards.scheme.classification)
        )
    await _audit_board(audit, principal, "edit_drawn_item", investigation.id, item_id=item_id,
                       changed=sorted(body.model_dump(exclude_none=True)))  # fmt: skip
    return made


@app.post(
    "/v1/investigations/{investigation_id}/board-items/{item_id}/withdraw", dependencies=_DRAWS
)
async def withdraw_drawn_item(
    investigation: InvestigationEditorDep,
    item_id: str,
    principal: PrincipalDep,
    boards: BoardsDep,
    audit: AuditDep,
) -> Withdrawn:
    """The author withdraws their own item: out of every read, never deleted; its watch ends."""

    async def audited(nodes: list[str], links: list[str]) -> None:
        # Every element withdrawn, seen by the caller or not: the audit is read under its own right.
        await _audit_board(audit, principal, "withdraw_drawn_item", investigation.id,
                           item_id=item_id, nodes=nodes, links=links)  # fmt: skip

    return await boards.withdraw(investigation.id, item_id, principal, before_write=audited)


@app.get(
    "/v1/investigations/{investigation_id}/boards/{board_id}/matches",
    dependencies=_READS_BOARDS,
)
async def board_match_suggestions(
    investigation: InvestigationViewerDep,
    board_id: str,
    principal: PrincipalDep,
    boards: BoardsDep,
) -> MatchSuggestions:
    """*Looks like a loaded item* (decision 6): `inferred` suggestions, which act on nothing."""
    board = await boards.board(investigation.id, board_id, principal.id)
    return await boards.suggestions(board, principal)


@app.post(
    "/v1/investigations/{investigation_id}/boards/{board_id}/matches",
    status_code=status.HTTP_201_CREATED,
    dependencies=_DRAWS,
)
async def decide_board_match(
    investigation: InvestigationEditorDep,
    board_id: str,
    body: MatchDecision,
    principal: PrincipalDep,
    boards: BoardsDep,
    audit: AuditDep,
) -> MatchDecided:
    """*Same* or *Not the same*: one link in the layer; neither item changed (rule 6)."""
    board = await boards.own_board(investigation.id, board_id, principal.id)
    edge_id = await boards.decide(board, body, principal)
    await _audit_board(audit, principal, "decide_board_match", investigation.id,
                       board_id=board_id, drawn=body.drawn, loaded=body.loaded,
                       same=body.same, edge_id=edge_id)  # fmt: skip
    return MatchDecided(edge_id=edge_id)


@app.put(
    "/v1/investigations/{investigation_id}/boards/{board_id}/nodes/{node_id}/picture",
    status_code=status.HTTP_201_CREATED,
    dependencies=_DRAWS,
)
async def upload_drawn_picture(
    investigation: InvestigationEditorDep,
    board_id: str,
    node_id: str,
    request: Request,
    principal: PrincipalDep,
    boards: BoardsDep,
    audit: AuditDep,
    name: str = Query(min_length=1),
    marking: str = Query(min_length=1),
    source_note: str = Query(min_length=1, max_length=2000),
) -> DrawnItemMade:
    """C17 (a): an uploaded picture of a drawn node, held in the layer with its own marking and
    source note; a new one supersedes the one before. Audited after every refusal, before the
    file or the graph is written."""
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
    board = await boards.own_board(investigation.id, board_id, principal.id)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(
                status_code=413, detail="That file is larger than the upload limit."
            )

    async def audited() -> None:
        await _audit_board(audit, principal, "set_drawn_picture", investigation.id,
                           board_id=board_id, node_id=node_id, name=filename, size=len(data),
                           classification=marking)  # fmt: skip

    return await boards.upload_picture(
        board, node_id, principal, name=filename, data=bytes(data), marking=marking,
        source_note=source_note, before_write=audited,
    )  # fmt: skip


@app.post(
    "/v1/investigations/{investigation_id}/boards/{board_id}/nodes/{node_id}/picture",
    status_code=status.HTTP_201_CREATED,
    dependencies=_DRAWS,
)
async def choose_drawn_picture(
    investigation: InvestigationEditorDep,
    board_id: str,
    node_id: str,
    body: PictureChoice,
    principal: PrincipalDep,
    boards: BoardsDep,
    audit: AuditDep,
) -> DrawnItemMade:
    """C17 (b): a picture the case already holds, linked in the layer; the image stays put.
    Audited after every refusal and before the link is written, as the upload is."""
    board = await boards.own_board(investigation.id, board_id, principal.id)

    async def audited(marking: str) -> None:
        await _audit_board(
            audit, principal, "choose_drawn_picture", investigation.id,
            board_id=board_id, node_id=node_id, document_id=body.document_id,
            classification=marking,
        )  # fmt: skip

    return await boards.choose_picture(board, node_id, body, principal, before_write=audited)


@app.get(
    "/v1/investigations/{investigation_id}/boards/{board_id}/pictures",
    dependencies=_READS_BOARDS,
)
async def board_pictures(
    investigation: InvestigationViewerDep,
    board_id: str,
    principal: PrincipalDep,
    boards: BoardsDep,
) -> BoardPictures:
    """Each drawn node's picture on the board that this reader may see."""
    board = await boards.board(investigation.id, board_id, principal.id)
    return BoardPictures(pictures=await boards.pictures(board, principal))


@app.get(
    "/v1/investigations/{investigation_id}/boards/{board_id}/nodes/{node_id}/picture",
    dependencies=_READS_BOARDS,
)
async def board_picture_file(
    investigation: InvestigationViewerDep,
    board_id: str,
    node_id: str,
    principal: PrincipalDep,
    boards: BoardsDep,
) -> Response:
    """The picture's file, to someone who may see it; one they may not answers as none."""
    board = await boards.board(investigation.id, board_id, principal.id)
    data, content_type = await boards.picture_file(board, node_id, principal)
    return Response(content=data, media_type=content_type)


@app.get("/v1/investigations/{investigation_id}/drawn-watches", dependencies=_READS_BOARDS)
async def list_drawn_watches(
    investigation: InvestigationViewerDep, principal: PrincipalDep, boards: BoardsDep
) -> list[DrawnWatch]:
    """The watches drawing set in this case (Amendment 2 decision 8): one withheld whole from a
    reader who may not see its item."""
    return await boards.watches(investigation.id, principal)


# --- promotion (ADR-143 decisions 8 and 10; Amendment 2 decision 1; spec 03 §3.1d; L3.4) --------
#
# Promoting needs the case's Author level and `promote_to_dataset` (ADR-112 Amendment 4, I12), on
# the promoter's own board. The Studio's *Analyst promotions* list is behind the dataset's own gate
# and `review_promotions`; deciding also needs to be one of the dataset's Authors, never the
# proposer. A removed case's layer is merged or deleted by one of the dataset's Authors (ADR-145
# Amendment 4 decision 3: owning, no Studio right), or deleted by an administrator.

_PROMOTES = [
    Depends(require_right(Right.PROMOTE_TO_DATASET)),
    Depends(require_right(Right.INVESTIGATE)),
]
_REVIEWS = [Depends(require_right(Right.REVIEW_PROMOTIONS))]
#: A removed case's layer merged or deleted by one of the dataset's Authors: a write, so it names
#: a right every Author holds and a Reports Viewer does not (ADR-112: a Reports Viewer is refused
#: every write; ADR-146 decision 10), the dataset's gate and Author level asked as before. The
#: owner's ruling of 9 November 2026 (Amendment 5): owning alone does not; ADR-112 stands.
_LAYER_WRITES = [Depends(require_right(Right.INVESTIGATE))]


def get_promotions(
    request: Request,
    boards: BoardsDep,
    store: PromotionStoreDep,
    investigations: InvestigationsDep,
    principal: PrincipalDep,
    audit: AuditDep,
) -> Promotions:
    # The people directory's names; ids where the app holds none (a test app with no lifespan).
    directory = getattr(request.app.state, "principal_names", None)

    async def case_name(case_id: str) -> str | None:
        held = await investigations.admin_states([case_id])
        return held[case_id][0] if case_id in held else None

    async def rejected(record: PromotionRecord, reason: str, check: str | None) -> None:
        # The check's code (marking, types, graded, ends, withdrawn), never an item's label.
        await _audit_promotion(
            audit, principal, "promotion_rejected", record.case_id,
            len(record.node_ids) + len(record.edge_ids), promotion_id=record.id,
            load_id=record.load_id, dataset_id=record.dataset_id, reason=reason, check=check,
        )  # fmt: skip

    return Promotions(
        boards=boards,
        store=store,
        investigations=investigations,
        # A drawn dataset's merge's own writes and decision 7 (L3.9), for every route that may
        # commit one (the merge itself, and an approval in the target's Runs).
        merges=drawn_merge_module.MergeCommit(
            promotions_store=store,
            graph=boards.graph,
            datasets=boards.datasets,
            views=boards.views,
            items=boards.items,
            scheme=boards.scheme,
        ),
        author_level=AccessLevel.AUTHOR,
        # Case-b's `LinkTypeService` (ADR-143 Amendment 4 decision 3), as the app holds it: no
        # quiet fallback for a service without `promotion_refusals` (the independent review of
        # L3.4, item 3). A test app holding none refuses every type outside the dataset's model.
        link_types=getattr(request.app.state, "link_types", None),
        names=directory.display_names if directory is not None else None,
        case_names=case_name,
        on_rejected=rejected,
    )


PromotionsDep = Annotated[Promotions, Depends(get_promotions)]


@app.exception_handler(PromotionRefused)
async def _promotion_refused_handler(request: Request, exc: PromotionRefused) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": exc.code, "detail": exc.message})


@app.exception_handler(PromotionNotFound)
async def _promotion_not_found_handler(request: Request, exc: PromotionNotFound) -> JSONResponse:
    """Another dataset's promotion, and none at all, alike (rule 3)."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "promotion_not_found"}
    )


async def _copies_audited(promotions: Any, record: PromotionRecord) -> list[dict[str, Any]]:
    """A drawn merge's retyped items for its audit entry (ADR-143 Amendment 7): each original, the
    type it goes in as, and what the load wrote for it (none while it waits or once refused)."""
    if record.trigger != "drawn_merge":
        return []
    return [
        {"original": c.original, "kind": c.kind, "type": c.type, "written": c.written_id,
         "same_as": c.same_as_id}
        for c in await promotions.store.copies_of(record.id)
    ]  # fmt: skip


async def _audit_promotion(
    audit: AuditWriter,
    principal: Principal,
    action: str,
    case_id: str | None,
    count: int,
    **query: Any,
) -> None:
    await audit.record(
        principal=principal,
        action=action,
        investigation_id=case_id,
        resolved_query=query,
        result_cardinality=count,
    )


@app.get(
    "/v1/investigations/{investigation_id}/boards/{board_id}/promotion-sheet",
    dependencies=_PROMOTES,
)
async def promotion_sheet(
    investigation: InvestigationAuthorDep,
    board_id: str,
    principal: PrincipalDep,
    boards: BoardsDep,
    promotions: PromotionsDep,
) -> PromotionSheet:
    """*Promote…* (decision 8): the board's drawn items not yet promoted, each with every check it
    fails, the undecided matches as warnings, and how it will be recorded."""
    board = await boards.own_board(investigation.id, board_id, principal.id)
    return await promotions.sheet(board, principal)


@app.post(
    "/v1/investigations/{investigation_id}/boards/{board_id}/promotions",
    status_code=status.HTTP_201_CREATED,
    dependencies=_PROMOTES,
)
async def promote_drawn_items(
    investigation: InvestigationAuthorDep,
    board_id: str,
    body: PromotionInput,
    principal: PrincipalDep,
    boards: BoardsDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> Promotion:
    """*Promote*: every check run again here, then one load, committed at once or sent for review
    under the dataset's policy (ADR-145 decision 8)."""
    board = await boards.own_board(investigation.id, board_id, principal.id)
    record = await promotions.promote(board, body.item_ids, principal)
    await _audit_promotion(
        audit, principal, "promote_drawn_items", investigation.id,
        len(record.node_ids) + len(record.edge_ids), board_id=board_id,
        promotion_id=record.id, load_id=record.load_id, dataset_id=record.dataset_id,
        status=record.status, node_ids=list(record.node_ids), edge_ids=list(record.edge_ids),
    )  # fmt: skip
    return await promotions.view(record, principal, with_board=True, show_case=True)


@app.get(
    "/v1/investigations/{investigation_id}/boards/{board_id}/promotions",
    dependencies=_READS_BOARDS,
)
async def list_board_promotions(
    investigation: InvestigationViewerDep,
    board_id: str,
    principal: PrincipalDep,
    boards: BoardsDep,
    promotions: PromotionsDep,
) -> PromotionsList:
    """*Promotions from this board* (decision 10): the outcome of each, for a reader who may see
    the board."""
    board = await boards.board(investigation.id, board_id, principal.id)
    # Rule 3: a promotion carrying an item above the reader's clearance is not listed to them,
    # in the store's query; each listed with the counts of what this reader is shown.
    held = await promotions.store.of_board(
        investigation.id, board.id, markings=_markings_cleared(promotions, principal)
    )
    counts = await promotions.shown_counts(held, principal)
    return PromotionsList(
        promotions=[
            await promotions.view(
                r, principal, with_board=True, counts=counts[r.id], show_case=True
            )
            for r in held
        ]
    )


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
    watch_reach: WatchReachDep,
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
            watch_reach=watch_reach,
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
    dependencies=[Depends(require_right(Right.EXTRACT_FILES)), NoLoadingInACompositeCase],
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
        # ADR-136: text extracted in a case is of the case's datasets.
        datasets=principal.datasets,
        # ADR-135 Amendment 9: the review queue's extraction, the one call Laurium serves.
        laurium_may_read=True,
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
    alerts_store: AlertsStoreDep,
    working_set: WorkingSetDep,
) -> NodeIdResponse:
    # ADR-099 Amendment 15: a composite is read-only (a node the caller cannot read stays 404).
    await refuse_writing_a_node_in_a_composite_case(graph, node_id, principal)
    # ADR-109 Amendment 11: each link the confirm clones goes through the alerts' repoint journal,
    # so an alert citing one follows it to its clone.
    new_node_id = await supersede_journalled(
        alerts_store,
        graph,
        lambda tx, cloned: confirm_node(graph, node_id, principal, tx=tx, on_link_cloned=cloned),
        working_set=working_set,
        # ADR-109 Amendment 12: an alert naming the node follows it to its new revision.
        superseding=node_id,
    )
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
    alerts_store: AlertsStoreDep,
    working_set: WorkingSetDep,
) -> NodeIdResponse:
    # ADR-099 Amendment 15: a composite is read-only (a node the caller cannot read stays 404).
    await refuse_writing_a_node_in_a_composite_case(graph, node_id, principal)
    # ADR-143 decision 5 (C15): a drawn node is withdrawn on its board, by whoever drew it.
    await refuse_correcting_a_drawn_node(graph, node_id, principal)
    # ADR-109 Amendment 11: each link the retract clones goes through the alerts' repoint journal,
    # so an alert citing one follows it to its clone.
    new_node_id = await supersede_journalled(
        alerts_store,
        graph,
        lambda tx, cloned: retract_node(graph, node_id, principal, tx=tx, on_link_cloned=cloned),
        working_set=working_set,
        # ADR-109 Amendment 12: an alert naming the node follows it to its new revision.
        superseding=node_id,
    )
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
    as the timeline."""
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
# own creation context — `schemas.domain.Alert`'s own docstring has the full reasoning) is the case
# an alert's address, `GET /v1/alerts/{alert_id}`, opens it in (ADR-146 Amendment 2).


@app.post(
    "/v1/investigations/{investigation_id}/hotlists",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_right(Right.KEEP_WATCHES)),
        Depends(require_rules_place),
    ],
)
async def create_hotlist_route(
    investigation: InvestigationEditorDep,
    body: CreateHotlistRequest,
    principal: PrincipalDep,
    hotlists_store: HotlistsStoreDep,
    monitoring: MonitoringSettingsDep,
    audit: AuditDep,
) -> Hotlist:
    """ADR-133 ruling 3: a new hotlist takes the deployment's audience, or its owner's choice where
    the deployment allows one."""
    audience = body.audience or monitoring.hotlist_audience
    if audience != monitoring.hotlist_audience and not monitoring.hotlist_audience_editable:
        raise HotlistAudienceFixed(monitoring.hotlist_audience)
    hotlist = await hotlists_store.create(
        principal, identifier=body.identifier, review_date=body.review_date, audience=audience
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
    dependencies=[
        Depends(require_right(Right.KEEP_WATCHES)),
        Depends(require_rules_place),
    ],
)
async def list_hotlists_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    hotlists_store: HotlistsStoreDep,
    monitoring: MonitoringSettingsDep,
) -> HotlistList:
    return HotlistList(
        hotlists=await hotlists_store.list_authorized(principal),
        audience_default=monitoring.hotlist_audience,
        audience_editable=monitoring.hotlist_audience_editable,
    )


_AUDIENCE_WORDS = {"only_me": "only its owner", "team": "its owner's team"}


class HotlistAudienceFixed(Exception):
    """The deployment does not let a hotlist's owner choose its audience (ADR-133 ruling 3)."""

    def __init__(self, audience: str) -> None:
        super().__init__(audience)
        self.audience = audience


@app.exception_handler(HotlistAudienceFixed)
async def _audience_fixed_handler(request: Request, exc: HotlistAudienceFixed) -> JSONResponse:
    """ADR-133 ruling 3: with editing off, the choice is refused in words."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "hotlist_audience_fixed",
            "detail": (
                "This deployment sends every hotlist's alerts to "
                f"{_AUDIENCE_WORDS[exc.audience]}; the audience cannot be changed here. An "
                "administrator sets it (monitoring.hotlist_audience_editable)."
            ),
        },
    )


@app.put(
    "/v1/investigations/{investigation_id}/hotlists/{hotlist_id}/audience",
    dependencies=[
        Depends(require_right(Right.KEEP_WATCHES)),
        Depends(require_rules_place),
    ],
)
async def set_hotlist_audience_route(
    hotlist_id: str,
    body: HotlistAudienceInput,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    hotlists_store: HotlistsStoreDep,
    monitoring: MonitoringSettingsDep,
    audit: AuditDep,
    alerts_store: AlertsStoreDep,
) -> Hotlist:
    """ADR-133 ruling 3: the owner chooses whom their hotlist's alerts reach — only them, or their
    team too. Another's hotlist is not found (the store's owner check, in the statement). Refused in
    words when the deployment does not let owners choose. Its alerts are kept again for alert
    trends (ADR-134 decision 3), so the team's trends follow the choice at once."""
    if not monitoring.hotlist_audience_editable:
        raise HotlistAudienceFixed(monitoring.hotlist_audience)
    hotlist = await hotlists_store.set_audience(hotlist_id, principal, body.audience)
    await alerts_store.publish_rule_facts(f"hotlist:{hotlist.id}")
    await audit.record(
        principal=principal,
        action="hotlist_audience_changed",
        investigation_id=investigation.id,
        resolved_query={"hotlist_id": hotlist.id, "audience": hotlist.audience},
        result_cardinality=1,
    )
    return hotlist


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
    return result.to_response(principal)


# --- relationship types proposed by analysts (ADR-090) ------------------------------------


@app.get(
    "/v1/investigations/{investigation_id}/link-types",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def case_link_types_route(
    investigation: InvestigationViewerDep, principal: PrincipalDep, link_types: LinkTypesDep
) -> CaseLinkTypesResponse:
    """The types a link in this case may take: the ontology's, those accepted into the model of a
    dataset the case reads once live, and those proposed in this case alone (ADR-143 decision 9).
    Not audited, like the ontology itself."""
    offered = await link_types.case_types(investigation.id, principal)
    return CaseLinkTypesResponse(
        types=[
            LinkTypeOption(definition=t.definition, proposal_id=t.proposal_id)
            for t in offered.values()
        ]
    )


@app.post(
    "/v1/investigations/{investigation_id}/link-types",
    dependencies=[Depends(require_right(Right.PROPOSE_TYPES))],
)
async def propose_link_type_route(
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    body: ProposeLinkTypeRequest,
    link_types: LinkTypesDep,
    audit: AuditDep,
) -> LinkTypeProposal:
    """Propose a type when none fits (ADR-090): usable at once in this case alone, probabilistic,
    until a data engineer of its dataset decides it on the Studio's Model tab (ADR-143 decision
    9)."""
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
    dependencies=[Depends(require_right(Right.PROPOSE_TYPES))],
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


@app.post(
    "/v1/investigations/{investigation_id}/link-types/promotable",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def promotable_link_types_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    body: PromotableRequest,
    link_types: LinkTypesDep,
) -> PromotableResponse:
    """ADR-143 decision 9: whether links of each type can be promoted from this case into its
    source dataset, and why not. A proposed type's cannot until a data engineer has accepted it and
    its model version is live; a declined type's never. L3.4's promotion sheet asks the same
    `promotion_refusals`. Not audited: a read of the case's own types, like the list above."""
    found = await link_types.promotion_refusals(investigation.id, principal, body.types)
    return PromotableResponse(
        types=[
            PromotableType(name=name, promotable=reason is None, reason=reason)
            for name, reason in found.items()
        ]
    )


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
    dependencies=[Depends(require_right(Right.EXTRACT_FILES)), NoLoadingInACompositeCase],
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
    # ADR-148 decision 10: refused before the body is read or anything is stored.
    refuse_above_the_deployment_ceiling(request, classification)
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
    # ADR-148 decision 10: refused before the body is read or anything is stored.
    refuse_above_the_deployment_ceiling(request, classification)
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
    response = result.to_response(principal)
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
    return delta.to_sent(principal)


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
    principal_names: PrincipalNamesDep,
    views: CaseViewsDep,
    working_set: WorkingSetDep,
) -> QuestionAnswer:
    """Asks the model about the case's Documents and graph facts the analyst can see (ADR-098
    decision 4, ADR-129 decision 1): the selection and one link around it, or the whole view. What
    it proposes is pending until a person accepts it. The answer names its author as the case's
    conversation does (ADR-106; build order step 18c: it showed the identity provider's id)."""
    # *Ask the model about these* (ADR-144 decision 4): asked in a view the asker may see (the
    # store's answer; 404 otherwise), reading only what the view holds.
    in_view = (
        await _view_node_ids(views, working_set, investigation.id, body.view_id, principal)
        if body.view_id is not None
        else None
    )
    answer = await questions.ask(
        investigation.id,
        body.question,
        principal,
        selected_node_ids=body.selected_node_ids,
        selected_link_ids=body.selected_link_ids,
        window=body.window,
        engine=body.engine,
        view_id=body.view_id,
        view_node_ids=in_view,
    )
    await audit.record(
        principal=principal,
        action="ask_question",
        investigation_id=investigation.id,
        resolved_query={"question_id": answer.id},
        result_cardinality=len(answer.candidates),
    )
    names = await principal_names.display_names([answer.author])
    return answer.model_copy(update={"author_name": names.get(answer.author)})


async def _view_node_ids(
    views: CaseViewStore,
    working_set: WorkingSetService,
    case_id: str,
    view_id: str,
    principal: Principal,
) -> list[str]:
    """The nodes a view shows, for a reader the store lets see it (`ViewNotFound` otherwise). The
    request may then read what is kept with the view (`read_in_view`)."""
    view = await views.get(case_id, view_id, principal.id)
    read_in_view(view_id)
    if view.node_ids is not None:
        return list(view.node_ids)
    assert view.filter is not None
    nodes, _ = await working_set.filtered_view(case_id, principal, view.filter)
    return [n.id for n in nodes]


@app.get(
    "/v1/investigations/{investigation_id}/questions",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def list_questions_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    questions: QuestionsDep,
    principal_names: PrincipalNamesDep,
    views: CaseViewsDep,
    view_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> list[QuestionAnswer]:
    """The case's questions and answers, as this reader may see them (ADR-098 decision 4): the
    case's own conversation, or, with `view_id`, the conversation kept with that view, only for a
    reader who may see the view (the owner's ruling of 8 November 2026; 404 as for no view)."""
    if view_id is not None:
        await views.get(investigation.id, view_id, principal.id)
        read_in_view(view_id)  # its proposals are read only through it
    history = await questions.history(investigation.id, principal, view_id=view_id)
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
    views: CaseViewsDep,
    view_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> QuestionAccepted:
    """Accepts one of the model's proposals: an inferred node linked to its Document. A proposal
    from a view's conversation is found only with that view named, for a reader who may see it."""
    if view_id is not None:
        await views.get(investigation.id, view_id, principal.id)
        read_in_view(view_id)
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
    views: CaseViewsDep,
    view_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> RejectedResponse:
    """Rejects one of the model's proposals: nothing is written. A proposal from a view's
    conversation is found only with that view named, for a reader who may see it."""
    if view_id is not None:
        await views.get(investigation.id, view_id, principal.id)
        read_in_view(view_id)
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
    # A monitor runs a saved pattern on the case's data, as a rule does: none in a drawing's case
    # until it is merged (ADR-143 Amendment 2 decision 5).
    dependencies=[
        Depends(require_right(Right.KEEP_WATCHES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_editor),
    ],
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
    dependencies=[
        Depends(require_right(Right.KEEP_WATCHES)),
        Depends(require_rules_place),
    ],
)
async def list_monitors_route(
    investigation: InvestigationViewerDep, principal: PrincipalDep, monitors_store: MonitorsStoreDep
) -> MonitorList:
    return MonitorList(monitors=await monitors_store.list_authorized(principal))


@app.put(
    "/v1/investigations/{investigation_id}/monitors/{monitor_id}/schedule",
    dependencies=[
        Depends(require_right(Right.KEEP_WATCHES)),
        Depends(require_rules_place),
    ],
)
async def set_monitor_schedule(
    monitor_id: str,
    body: MonitorScheduleInput,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    monitors_store: MonitorsStoreDep,
    audit: AuditDep,
) -> Monitor:
    """ADR-146 decision 4 (G16): a watched pattern's own schedule, set by its owner alone: every
    day or week at a whole hour, or never (as data loads only). Another's watch answers as
    missing."""
    monitor = await monitors_store.set_schedule(monitor_id, principal, body)
    await audit.record(
        principal=principal,
        action="monitor_schedule_set",
        investigation_id=investigation.id,
        resolved_query={"monitor_id": monitor_id, **body.model_dump()},
        result_cardinality=1,
    )
    return monitor


# ADR-146 decision 1 (L2.10): the Watches inbox, `GET …/alerts` and `GET …/alerts/{id}`, is gone:
# every alert is in the one queue, and what the inbox alone said (*what fired it*) is on the
# queue's explanation (`watch_routes.with_what_fired_it`).


@app.get(
    "/v1/alerts/{alert_id}",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_rules_place),
    ],
)
async def open_alert_at_address(
    alert_id: str,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    analytics: AnalyticsDep,
    alerts_store: AlertsStoreDep,
    principal_names: PrincipalNamesDep,
    audit: AuditDep,
    datasets: DatasetsDep,
) -> AlertAtAddress:
    """An alert's own address, `/alerts/<id>` (ADR-146 decision 6), which Home, the canvas, a board,
    an email and the queue all open: the case it is worked in, and its explanation there, read as
    `explain_alert` reads it. Refused exactly as an alert that does not exist (404
    `alert_not_found`, rule 3; ADR-146's test) when the reader may not open that case, when the
    alert is not in their queue there, or when any of its evidence is hidden from them: the same
    status and body, and answered at the same time. The reads differ (an id that never existed, or
    one in a case the reader may not open, stops after the level check; an alert in a case they may
    open is read through the queue's scope and its evidence first), so every refusal waits to the
    end of the quantum it falls in from the request's start (`rules_place.refusal_wait`; ADR-146
    Amendment 2 point 6). Replaces the jump's case of its own (ADR-144 Amendment 2 decision 2): the
    alert is worked in the case it arose in, and its evidence opened there as a private view."""
    started = rules_place_clock.monotonic()
    try:
        return await _alert_at_address(
            alert_id, principal, investigations, graph, analytics, alerts_store, principal_names,
            audit, datasets,
        )  # fmt: skip
    except AlertNotFoundError:
        await rules_place_clock.sleep(refusal_wait(started, rules_place_clock.monotonic()))
        raise


async def _alert_at_address(
    alert_id: str,
    principal: Principal,
    investigations: InvestigationStore,
    graph: GraphPort,
    analytics: AnalyticsPort,
    alerts_store: AlertStore,
    principal_names: Any,
    audit: Any,
    datasets: DatasetStore,
) -> AlertAtAddress:
    """`open_alert_at_address`'s reads: the case's level check (made for a missing id too, on no
    case), the reader scoped to the alert's case, then the queue's own read of it."""
    case_id = await alerts_store.case_of(alert_id)
    try:
        await investigations.get_authorized(case_id or "", principal, need=AccessLevel.VIEWER)
    except (InvestigationNotFoundError, InsufficientAccessError):
        raise AlertNotFoundError(alert_id) from None
    if case_id is None:
        raise AlertNotFoundError(alert_id)
    # The path names no case, so `get_principal` reads no dataset for this reader
    # (`outside_any_case`): the reader reads the alert's case's datasets, and no others, as every
    # route of a case does (ADR-099).
    principal = await scope_to_case(
        principal, case_id, datasets, holds_a_level=holds_a_level_in(investigations)
    )
    explanation = await alert_queue.explain(
        alerts_store, graph, analytics, case_id, alert_id, principal
    )
    explanation = await _named_explanation(explanation, principal_names)
    await audit.record(
        principal=principal,
        action="open_alert_at_address",
        investigation_id=case_id,
        resolved_query={"alert_id": alert_id},
        result_cardinality=len(explanation.nodes),
    )
    return AlertAtAddress(investigation_id=case_id, explanation=explanation)


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


@app.get("/v1/openapi.json", include_in_schema=False)
async def openapi_document_route(principal: PrincipalDep) -> JSONResponse:
    """The API's OpenAPI document (`03_CONDUIT_MIDDLEWARE.md` §3.0a; the owner's answer of 1
    November 2026; GDS remediation O1). Under `/v1/`, so the workspace's proxy carries it to the
    deployment's address with every other route, and signed in as every other `/v1` route is. Its
    `info.version` is the release the deployment was rendered from (`release_version.py`), read
    when it is asked for, so it always says what Admin → System says."""
    document = dict(app.openapi())
    document["info"] = {**document["info"], "version": release_version()}
    return JSONResponse(document)


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


@app.post(
    "/v1/investigations/{investigation_id}/map/places",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def map_place_search_route(
    investigation: InvestigationViewerDep,
    body: PlaceSearchRequest,
    principal: PrincipalDep,
    graph: GraphDep,
    analytics: AnalyticsDep,
    audit: AuditDep,
    store: CaseGazetteersDep,
) -> PlaceSearchResponse:
    """The map's place search (`02_GLASS_FRONTEND.md` §3.5, ADR-147 Amendment 1): the loaded
    gazetteer's places in the case's datasets (ADR-099, read with the case's principal in the
    store, rule 3), each with its point; never a hosted geocoder (`map_places`). Viewer and
    `investigate`, as the case's other searches are; audited as they are."""
    # ADR-147 Amendment 2, the orchestrator's ruling (d): a removed gazetteer's copies are no longer
    # offered as places (keyed on their mark and the removal record, the same for every copy). The
    # store is a dependency: without it the search answers 503, never offering them again.
    removed = await store.removed_among(list(principal.datasets or []))
    result = await map_places.search_places(graph, analytics, body, principal, removed=removed)
    await audit.record(
        principal=principal,
        action="map_place_search",
        investigation_id=investigation.id,
        resolved_query={"query": body.query, "limit": body.limit},
        result_cardinality=len(result.places),
    )
    return result


async def _own_dataset(investigation_id: str, datasets: DatasetStore) -> Dataset | None:
    """The one source dataset the case reads of its own, where a gazetteer's copies are; `None`
    for a case reading a composite or nothing (ADR-147 Amendment 2)."""
    chosen = await datasets.chosen_of_case(investigation_id)
    if len(chosen) != 1 or chosen[0].kind != SOURCE_DATASET:
        return None
    return chosen[0]


#: ADR-147 Amendment 2, the orchestrator's ruling (d): what a removal says, the same for every
#: removal, whatever rests on any copy (rule 3), and with no count.
REMOVED_WORDS = (
    "The gazetteer is removed: its places stay in this dataset as its own, and the map's place "
    "search no longer offers them. A re-build no longer refreshes them; adding it again does."
)


async def _gazetteers_view(
    dataset: Dataset | None, datasets: DatasetStore, store: Any, *, said: str | None = None
) -> CaseGazetteers:
    """The gazetteers of `dataset`'s unit, and those it holds (ADR-147 Amendment 2: recorded for
    the dataset, so every case reading it sees them added)."""
    if dataset is None:
        return CaseGazetteers(gazetteers=[])
    added = {a.gazetteer for a in await store.of_dataset(dataset.id)}
    offered = {
        d.id: d.name
        for d in await datasets.list_all()
        if d.id.startswith(GAZETTEER_DATASET_PREFIX) and d.owning_unit == dataset.owning_unit
    }
    return CaseGazetteers(
        gazetteers=[
            CaseGazetteer(dataset_id=i, name=offered.get(i, i), added=i in added)
            for i in sorted(set(offered) | added)
        ],
        said=said,
    )


@app.get(
    "/v1/investigations/{investigation_id}/map/gazetteers",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def case_gazetteers_route(
    investigation: InvestigationViewerDep,
    datasets: DatasetsDep,
    store: CaseGazetteersDep,
) -> CaseGazetteers:
    """The gazetteers the case's own dataset may take, and which it holds (ADR-147 Amendment 2, the
    owner's ruling 6): names only, never a count of places (a count would take in places above the
    reader's clearance). Viewer and `investigate`, as the place search is. A case reading a
    composite or nothing is answered with none."""
    return await _gazetteers_view(await _own_dataset(investigation.id, datasets), datasets, store)


#: ADR-147 Amendment 2: the words a refused addition is said in.
_NO_SUCH_GAZETTEER = (
    "There is no gazetteer of that name for this dataset's unit: a dataset takes a gazetteer built "
    "for its own unit, in Admin › Maps."
)


async def _dataset_and_gazetteer(
    dataset_id: str, gazetteer_id: str, datasets: DatasetStore
) -> Dataset:
    """The dataset (a source, its gate passed) and the gazetteer it may take: one of the dataset's
    own unit (the orchestrator's review of P5, item 3), refused in words otherwise."""
    held = await datasets.egress_of([dataset_id, gazetteer_id])
    dataset = held.get(dataset_id)
    if dataset is None or dataset.kind != SOURCE_DATASET:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    gazetteer = held.get(gazetteer_id)
    if gazetteer is None or not gazetteer_id.startswith(GAZETTEER_DATASET_PREFIX):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_SUCH_GAZETTEER)
    if gazetteer.owning_unit != dataset.owning_unit:
        # The same answer as for no gazetteer at all, so it says nothing of which regions another
        # unit has built (the lane's review, item 3).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_SUCH_GAZETTEER)
    return dataset


@app.get("/v1/map/tiles/{provider_id}/{z}/{x}/{y}")
async def get_map_tile_route(
    request: Request,
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

    map_admin = getattr(request.app.state, "map_admin", None)
    if map_admin is not None:
        try:
            await asyncio.to_thread(map_admin.refuse_inside, provider)  # a lookup: off the loop
        except map_admin_module.MapAdminRefused as refused:
            raise HTTPException(status_code=refused.status, detail=refused.words) from None
    # ADR-147: a key set in *Admin › Maps* first, then `osprey.yaml`'s `env:` reference; a provider
    # that needs one and holds neither is said in words, never its address.
    try:
        url = build_upstream_url(provider, z, x, y, key=_map_key(request, provider_id))
    except MissingMapKeyError as missing:
        raise HTTPException(status_code=503, detail=str(missing)) from None
    except MissingCredentialError:
        raise HTTPException(status_code=503, detail=str(MissingMapKeyError(provider_id))) from None
    try:
        tile_bytes = await fetch_tile(url)
    except TileFetchFailed as failed:
        raise HTTPException(
            status_code=502,
            detail=(
                f"The map provider {provider_id!r} refused the tile (HTTP {failed.status}). If it "
                "was refused for its key, set the key again in Admin › Maps."
                if failed.status
                else f"The map provider {provider_id!r} answered with something larger than any "
                "tile, so it was not kept."
                if failed.too_large
                else f"The map provider {provider_id!r} could not be reached."
            ),
        ) from None
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


class BuildBasemapResult(BaseModel):
    pmtiles_file: str
    nodes_created: int
    nodes_referenced: int
    rejections: int


@app.post(
    "/v1/admin/geospatial/build-basemap",
    dependencies=[Depends(require_right(Right.MANAGE_GEOSPATIAL))],
)
async def build_basemap_route(
    request: Request,
    principal: Annotated[Principal, Depends(require_admin_role)],
    graph: GraphDep,
    ontology: OntologyDep,
    audit: AuditDep,
    admin: MapAdminDep,
    datasets: DatasetsDep,
    analytics: AnalyticsDep,
    handling_scheme: HandlingSchemeDep,
    copies: CaseGazetteersDep,
) -> StreamingResponse:
    """ADR-147: a named region only; the tiles folder and the planetiler jar are the deployment's
    own (`map_admin.build_basemap`), never a path typed in the Glass, and the provider is registered
    in the maps file. Streamed the same way Launch is (`harness/webapp.py`'s own `_launch_events`):
    one line of real progress at a time, the build's `progress` callback bridged into an SSE
    generator via a queue. The gazetteer loads in one graph transaction, rolled back if anything
    fails."""
    body = await _map_admin_body(request, BuildBasemapInput)
    if body.region not in GEOFABRIK_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{body.region!r} is not a known Geofabrik region: {sorted(GEOFABRIK_REGIONS)}",
        )
    # ADR-147 Amendment 2 (the owner's ruling 8): the gazetteer's unit is the build's setting, the
    # administrator's own unless named, and refused in words before anything runs.
    gazetteer_unit = body.unit or principal.org_unit
    try:
        map_places.check_unit(
            gazetteer_unit, await map_places.units_held(datasets), own=principal.org_unit,
            built_for=await map_places.built_for(datasets, body.region),
        )  # fmt: skip
    except map_places.UnknownUnit as unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(unknown)
        ) from None

    async def _events() -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue()
        transaction: dict[str, str] = {}
        audited = False

        def _progress(line: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, line)

        async def _load_places(extract: Path) -> tuple[int, int, int]:
            # ADR-147 Amendment 1: into the region's gazetteer dataset, which a case's Author
            # adds to a case for its place search; before P4 the places were in no dataset. The
            # dataset is registered once they are committed (`_settle`), so a failed build leaves
            # none behind.
            tx = await graph.begin_transaction()
            transaction["tx"] = tx
            report = await load_gazetteer(
                extract, graph=graph, ontology=ontology, tx=tx, principal=principal,
                load_id=f"load-osm-gazetteer-{body.region}",
                dataset=map_places.gazetteer_dataset_id(body.region), analytics=analytics,
                unit=gazetteer_unit,
            )  # fmt: skip
            return report.nodes_created, report.nodes_referenced, len(report.rejections)

        async def _settle() -> None:
            # Committed before the provider is registered (`map_admin.build_basemap`).
            await graph.commit_transaction(transaction.pop("tx"))
            await map_places.register_gazetteer_dataset(
                datasets, body.region, by=principal.id, unit=gazetteer_unit
            )
            # ADR-147 Amendment 2: a re-build gives every dataset holding the gazetteer its places
            # again. Never failing the build, whose places are committed: each failure is said.
            try:
                refreshed = await case_gazetteers.refresh_cases(
                    graph, handling_scheme, copies, datasets,
                    map_places.gazetteer_dataset_id(body.region),
                )  # fmt: skip
            except Exception as error:  # noqa: BLE001 - said in words; the build stands
                _progress(case_gazetteers.UNREFRESHED.format(error=type(error).__name__))
            else:
                for words in refreshed.failed:
                    _progress(words)

        async def _run_build() -> tuple[tuple[str, int, int, int] | None, BaseException | None]:
            try:
                result = await map_admin_module.build_basemap(
                    admin, by=principal.id, region=body.region, load_places=_load_places,
                    progress=_progress, tiles_root=admin.tiles_root, settle=_settle,
                )  # fmt: skip
            except BaseException as exc:  # noqa: BLE001 - reported to the caller, not swallowed
                if "tx" in transaction:
                    await graph.rollback_transaction(transaction.pop("tx"))
                return None, exc
            return result, None

        try:
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
            # Drain whatever progress arrived after the build task itself finished but before
            # this loop's own last `queue.get()` was scheduled — a real race the `asyncio.wait`
            # above cannot close on its own, found writing this route's own first test.
            while not queue.empty():
                yield f"data: {json.dumps({'line': queue.get_nowait()})}\n\n".encode()

            result, error = task.result()
            await audit.record(
                principal=principal,
                action="geospatial_build_basemap",
                resolved_query={"region": body.region},
                result_cardinality=0 if error is not None else 1,
            )
            audited = True
            if error is not None:
                # The independent review's minor 8: an error's own words (a path, a provider's
                # answer) are the Conduit's log's; the Glass is told it stopped, and its kind.
                if isinstance(error, map_admin_module.MapAdminRefused):
                    words = error.words
                else:
                    logger.warning("the basemap build stopped: %s", error)
                    words = (
                        f"The build stopped ({type(error).__name__}). The Conduit's log has the "
                        "reason."
                    )
                stopped = json.dumps({"returncode": 1, "error": words})
                yield f"event: complete\ndata: {stopped}\n\n".encode()
                return
            assert result is not None
            name, created, referenced, rejected = result
            payload = BuildBasemapResult(
                pmtiles_file=name, nodes_created=created, nodes_referenced=referenced,
                rejections=rejected,
            )  # fmt: skip
            yield (
                f"event: complete\ndata: "
                f"{json.dumps({'returncode': 0, 'result': payload.model_dump()})}\n\n"
            ).encode()
        finally:
            # A stream the Glass abandoned still leaves its record (the review's minor 8).
            if not audited:
                await audit.record(
                    principal=principal,
                    action="geospatial_build_basemap",
                    resolved_query={"region": body.region},
                    result_cardinality=0,
                )

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
    request: Request,
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
    admin = getattr(request.app.state, "map_admin", None)
    if admin is not None:
        await admin.record_verify(principal.id, len(report.issues))
    return VerifyMapResult(
        passed=report.passed,
        issues=[
            VerifyMapIssue(provider_id=i.provider_id, check=i.check, detail=i.detail)
            for i in report.issues
        ],
    )


# --- Admin › Maps (ADR-147) ------------------------------------------------------------------
# Every route needs `manage_geospatial` (rule 4). None returns, logs or audits a key: each route
# reads its own body, so no validation error can echo what was sent (ADR-135 Amendment 2's rule).

_MANAGE_GEOSPATIAL = [Depends(require_right(Right.MANAGE_GEOSPATIAL))]


async def _map_admin_body[Body: BaseModel](request: Request, shape: type[Body]) -> Body:
    """A Maps route's body, read here rather than by FastAPI, whose 422 carries the input back. The
    refusal names each field and why, never what was sent unless it is shaped like an id."""
    raw = await request.body()
    try:
        return shape.model_validate_json(raw)
    except ValidationError as invalid:
        try:
            sent = map_admin_module.sent_values(json.loads(raw))
        except ValueError:
            sent = {raw.decode("utf-8", "replace")}
        words = map_admin_module.refusal_words(invalid, sent)
        raise HTTPException(
            status_code=422, detail={"error": "map_admin_refused", "detail": words}
        ) from None


def _map_admin_refused(refused: map_admin_module.MapAdminRefused) -> HTTPException:
    return HTTPException(
        status_code=refused.status, detail={"error": "map_admin_refused", "detail": refused.words}
    )


@app.get("/v1/admin/maps", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_view_route(admin: MapAdminDep) -> MapsAdminView:
    return admin.view()


@app.get("/v1/admin/maps/history", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_history_route(admin: MapAdminDep) -> MapAdminHistory:
    return MapAdminHistory(entries=await admin.history())


@app.post("/v1/admin/maps/providers", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_add_provider_route(
    request: Request, principal: PrincipalDep, admin: MapAdminDep
) -> MapsAdminView:
    body = await _map_admin_body(request, MapProviderInput)
    try:
        return await admin.add_provider(principal.id, body.provider)
    except map_admin_module.MapAdminRefused as refused:
        raise _map_admin_refused(refused) from None


@app.put("/v1/admin/maps/providers/{provider_id}", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_edit_provider_route(
    provider_id: str, request: Request, principal: PrincipalDep, admin: MapAdminDep
) -> MapsAdminView:
    body = await _map_admin_body(request, MapProviderInput)
    try:
        return await admin.edit_provider(principal.id, provider_id, body.provider)
    except map_admin_module.MapAdminRefused as refused:
        raise _map_admin_refused(refused) from None


@app.delete("/v1/admin/maps/providers/{provider_id}", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_remove_provider_route(
    provider_id: str, principal: PrincipalDep, admin: MapAdminDep
) -> MapsAdminView:
    try:
        return await admin.remove_provider(principal.id, provider_id)
    except map_admin_module.MapAdminRefused as refused:
        raise _map_admin_refused(refused) from None


@app.put("/v1/admin/maps/providers/{provider_id}/key", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_set_key_route(
    provider_id: str, request: Request, principal: PrincipalDep, admin: MapAdminDep
) -> MapsAdminView:
    """Write-only: the key is in this request's body and goes to the map key file alone."""
    body = await _map_admin_body(request, MapKeyInput)
    try:
        return await admin.set_key(principal.id, provider_id, body.key)
    except map_admin_module.MapAdminRefused as refused:
        raise _map_admin_refused(refused) from None


@app.delete("/v1/admin/maps/providers/{provider_id}/key", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_remove_key_route(
    provider_id: str, principal: PrincipalDep, admin: MapAdminDep
) -> MapsAdminView:
    try:
        return await admin.remove_key(principal.id, provider_id)
    except map_admin_module.MapAdminRefused as refused:
        raise _map_admin_refused(refused) from None


@app.put("/v1/admin/maps/default", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_default_route(
    request: Request, principal: PrincipalDep, admin: MapAdminDep
) -> MapsAdminView:
    body = await _map_admin_body(request, MapDefaultInput)
    try:
        return await admin.set_default(principal.id, body.default)
    except map_admin_module.MapAdminRefused as refused:
        raise _map_admin_refused(refused) from None


@app.put("/v1/admin/maps/areas", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_areas_route(
    request: Request, principal: PrincipalDep, admin: MapAdminDep
) -> MapsAdminView:
    body = await _map_admin_body(request, PrefetchAreasInput)
    try:
        return await admin.set_areas(principal.id, body.areas)
    except map_admin_module.MapAdminRefused as refused:
        raise _map_admin_refused(refused) from None


@app.put("/v1/admin/maps/schedule", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_schedule_route(
    request: Request, principal: PrincipalDep, admin: MapAdminDep
) -> MapsAdminView:
    body = await _map_admin_body(request, PrefetchScheduleInput)
    try:
        return await admin.set_schedule(principal.id, body.schedule)
    except map_admin_module.MapAdminRefused as refused:
        raise _map_admin_refused(refused) from None


@app.post("/v1/admin/maps/prefetch", dependencies=_MANAGE_GEOSPATIAL)
async def maps_admin_prefetch_route(
    principal: PrincipalDep, admin: MapAdminDep
) -> list[PrefetchRun]:
    """Every area now, counts only; a failure is said on its own area in fixed words."""
    try:
        return await admin.run_prefetch(principal.id)
    except map_admin_module.MapAdminRefused as refused:
        raise _map_admin_refused(refused) from None


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
    """The filter a body-scoped analytics read runs with. The case in the body is gated at Viewer
    exactly as a case in a path is, so a case the account cannot see answers 404 and reads
    nothing. It counts the case's own events alone; whatever `inherited` the caller sent is
    discarded (ADR-144 Amendment 1, `event_scope.py`)."""
    await _authorize(
        event_filter.investigation_scope, principal, investigations, audit, AccessLevel.VIEWER
    )
    return own_events_only(event_filter)


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
    # ADR-099 Amendment 15: drawing the grid loads its cells, so not in a case reading a composite;
    # after the site's own check (a site the caller cannot reach is not found), before the grid is
    # stored.
    await refuse_in_a_composite_case()
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


# --- ingest studio: connections and registered sources (ADR-140 Amendment 4) ----------------


def require_studio_dataset(dataset_id: str, principal: PrincipalDep) -> str:
    """A dataset route's own gate: `get_principal` scoped the principal to `dataset_id` only when
    one of their cases loads into it. Anyone else is told 404, the same answer as for a dataset that
    does not exist, so the refusal says nothing of another unit's data (rule 3)."""
    if list(principal.datasets or []) != [dataset_id]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return dataset_id


StudioDatasetDep = Annotated[str, Depends(require_studio_dataset)]
SourceAuthorDep = Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))]


async def _first_name(datasets: DatasetStore, dataset_ids: Sequence[str]) -> str | None:
    """The first of these datasets' names, for a refusal that names a composite to an asker who
    may be told names (ADR-099 Amendment 11); `None` for an id the store does not hold."""
    held = {d.id: d for d in (await datasets.egress_of(dataset_ids)).values()}
    return next((held[d].name for d in dataset_ids if d in held), None)


async def refuse_loading_a_composite(dataset_id: StudioDatasetDep, datasets: DatasetsDep) -> None:
    """The same for the Studio's own routes of a dataset (ADR-140 Amendment 4): a composite is
    read, never loaded, and no pipeline loads into a drawn dataset (ADR-143 Amendment 2 decision
    5). After the dataset's own gate, which answers 404 to anyone it is not for."""
    await refuse_changing_a_composites_model(dataset_id, datasets)
    held = (await datasets.egress_of([dataset_id])).get(dataset_id)
    if held is not None and held.kind == DRAWN:
        raise DrawnNotLoaded


async def refuse_changing_a_composites_model(
    dataset_id: StudioDatasetDep, datasets: DatasetsDep
) -> None:
    """A composite's model is read, not changed, until its superset check (phase 5 item 4)."""
    if await datasets.composites_among([dataset_id]):
        # Named: past the dataset's gate, which only someone it is for reaches.
        raise CompositeReadOnlyError(await _first_name(datasets, [dataset_id]), in_a_case=False)


class DrawnNotLoaded(Exception):
    """ADR-143 Amendment 2 decision 5: no pipeline loads into a drawn dataset; what it holds is
    drawn on its board, and it reaches another dataset by merging (decision 6)."""


@app.exception_handler(DrawnNotLoaded)
async def _drawn_not_loaded_handler(request: Request, exc: DrawnNotLoaded) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": "drawn_not_loaded",
            "detail": "a drawn dataset is drawn on its board, not loaded: nothing is loaded or "
            "run into it, and it reaches another dataset by being merged into it",
        },
    )


@app.exception_handler(DrawnNotCopied)
async def _drawn_not_copied_handler(request: Request, exc: DrawnNotCopied) -> JSONResponse:
    """In words naming nothing else: the reader may hold no level on the drawing's case."""
    return JSONResponse(
        status_code=409,
        content={
            "error": "drawn_not_copied",
            "detail": "a drawn dataset is read in its own case alone, so no other case is made "
            "reading it",
        },
    )


async def refuse_copying_a_drawn_dataset(
    datasets: DatasetStore, *, case_id: str | None = None, dataset_id: str | None = None
) -> None:
    """Before any case is made: a case reading a drawn dataset is not opened from an alert into
    another case (ADR-143 Amendment 2 decision 5). `read_the_same_dataset` refuses it too, as the
    last word."""
    held = []
    if case_id is not None:
        held = await datasets.chosen_of_case(case_id)
    elif dataset_id is not None:
        found = (await datasets.egress_of([dataset_id])).get(dataset_id)
        held = [found] if found is not None else []
    if any(d.kind == DRAWN for d in held):
        raise DrawnNotCopied


NoLoadingAComposite = Depends(refuse_loading_a_composite)


@app.put(
    "/v1/datasets/{dataset_id}/gazetteers/{gazetteer_id}",
    dependencies=[Depends(require_right(Right.RUN_PIPELINES)), NoLoadingAComposite],
)
async def add_dataset_gazetteer_route(
    dataset_id: StudioDatasetDep,
    gazetteer_id: str,
    principal: PrincipalDep,
    graph: GraphDep,
    scheme: HandlingSchemeDep,
    datasets: DatasetsDep,
    store: CaseGazetteersDep,
    audit: AuditDep,
) -> CaseGazetteers:
    """Adds a gazetteer to a dataset (ADR-147 Amendment 2, the owner's ruling 6): its places copied
    into it (`case_gazetteers.copy_places`), so every case reading it reads them and stays one
    dataset that keeps its loads. **A dataset-level action** (the orchestrator's review of P5, item
    6): behind the dataset route's own gate (a person one of whose cases loads into it,
    `require_studio_dataset`) and `run_pipelines`, the right that runs a load into a dataset,
    never one case's level; a composite or a drawn dataset is refused, as for any load. A gazetteer
    of the dataset's own unit only. Again for a gazetteer already added copies its places again."""
    dataset = await _dataset_and_gazetteer(dataset_id, gazetteer_id, datasets)
    added = case_gazetteers.AddedGazetteer(
        case_dataset=dataset_id, gazetteer=gazetteer_id, added_in=dataset_id,
        added_by=principal.id, added_at=datetime.now(UTC),
    )  # fmt: skip
    # The record first and kept, whatever happens next: pages a failed copy wrote are committed, so
    # the dataset is said to hold the gazetteer, and adding it again finishes the copy, or removing
    # it stops it (the lane's review, item 4).
    await store.add(added)
    # Audited before the copy (the orchestrator's review of round 3, item 6): a copy that fails part
    # way leaves its pages committed, so it is never unaudited.
    await audit.record(
        principal=principal,
        action="add_dataset_gazetteer",
        resolved_query={"dataset_id": dataset_id, "gazetteer": gazetteer_id},
        result_cardinality=1,
    )
    await case_gazetteers.copy_places(
        graph, scheme, gazetteer=gazetteer_id, case_dataset=dataset_id, by=principal.id,
        unit=dataset.owning_unit,
    )  # fmt: skip
    return await _gazetteers_view(dataset, datasets, store)


@app.delete(
    "/v1/datasets/{dataset_id}/gazetteers/{gazetteer_id}",
    dependencies=[Depends(require_right(Right.RUN_PIPELINES)), NoLoadingAComposite],
)
async def remove_dataset_gazetteer_route(
    dataset_id: StudioDatasetDep,
    gazetteer_id: str,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    store: CaseGazetteersDep,
    audit: AuditDep,
) -> CaseGazetteers:
    """Removes a gazetteer from a dataset, so from every case reading it (ADR-147 Amendment 2, the
    orchestrator's ruling (d)): **no copy is deleted**, whatever rests on it, so no link is left to
    nothing and nothing a reader may not see changes what the asker is told (rule 3). Every copy
    keeps its gazetteer mark (3b holds); the record is kept as removed, so a re-build no longer
    refreshes them and the place search no longer offers them; adding the gazetteer again
    re-links the same copies. The answer says so in words, the same for every removal, with no
    count. Gated as adding is; audited."""
    # A record is all a removal needs: never the gazetteer's own state now (gone, or its unit
    # changed), so a removal is never made impossible (the lane's review).
    dataset = (await datasets.egress_of([dataset_id])).get(dataset_id)
    if dataset is None or gazetteer_id not in {
        a.gazetteer for a in await store.of_dataset(dataset_id)
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_SUCH_GAZETTEER)
    await store.remove(dataset_id, gazetteer_id)
    await audit.record(
        principal=principal,
        action="remove_dataset_gazetteer",
        resolved_query={"dataset_id": dataset_id, "gazetteer": gazetteer_id},
        result_cardinality=1,
    )
    return await _gazetteers_view(dataset, datasets, store, said=REMOVED_WORDS)


def _source_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")


def refresh_needs_a_key(labels: Sequence[str]) -> HTTPException:
    """ADR-110 Amendment 6 point 2 (the owner's ruling): a refresh re-reads rows, which only a
    pipeline with a deduplication key reads once. Refused in the same words at the policy and at
    Deploy."""
    names = ", ".join(sorted(labels))
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "error": "refresh_needs_a_key",
            "detail": f"This source is read again by its refresh policy, and {names} has no "
            "deduplication key, so each refresh would load its rows again. Give the pipeline a "
            "deduplication key, or set the source's refresh to by hand.",
        },
    )


async def _refuse_a_keyless_refresh(
    studio_recipes: Any, dataset_id: str, location: str, refresh: SourceRefresh
) -> None:
    """Before a refreshing policy is stored: the deployed pipelines reading the source that have no
    key. A draft is not run by a refresh, so it does not refuse; Deploy refuses it later."""
    if refresh.trigger == "manual":
        return
    keyless = [
        r.label
        for r in await studio_recipes.using_source(dataset_id, location)
        if r.status in (StudioRecipeStatus.PUBLISHED, StudioRecipeStatus.FLAGGED)
        and r.deduplicate is None
    ]
    if keyless:
        raise refresh_needs_a_key(keyless)


async def _source_of(sources: SourceStore, dataset_id: str, source_id: str) -> SourceTable:
    try:
        return await sources.get(dataset_id, source_id)
    except SourceNotFoundError as exc:
        raise _source_not_found() from exc


@app.get("/v1/ingest/connections", dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))])
async def list_ingest_connections(
    request: Request, principal: SourceAuthorDep, sources: SourcesDep
) -> list[Connection]:
    """The connections a source may be registered on (the register wizard's first step): names and
    kinds only, nothing read through them. A connection's settings (a database's host and login, an
    API's address, a secret's name) and the datasets it is bound to are for whoever administers the
    deployment (Admin › Connections), never sent here (the lane review of L1.6). A SQL, API or JSON
    connection is listed only when it is bound to a dataset one of the asker's cases loads into, by
    that dataset's own gate (`scope_to_dataset`, as every `/v1/datasets/{id}` route), so no one
    learns of a connection, or a dataset, they may not read (ADR-140 Amendment 13 decision 1's
    ruling, rule 3)."""
    reachable: dict[str, bool] = {}

    async def reaches(dataset_id: str) -> bool:
        if dataset_id not in reachable:
            scoped = await scope_to_dataset(
                principal, dataset_id, get_investigations(request), get_datasets(request)
            )
            reachable[dataset_id] = scoped is not None
        return reachable[dataset_id]

    shown: list[Connection] = []
    for c in await sources.connections():
        if c.kind != "files" and not [d for d in c.datasets if await reaches(d)]:
            continue
        shown.append(c.model_copy(update={"settings": None, "datasets": []}))
    return shown


@app.get("/v1/admin/connections", dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))])
async def list_admin_connections(sources: SourcesDep) -> list[Connection]:
    return await sources.connections()


@app.post(
    "/v1/admin/connections/{connection_id}/test",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def test_admin_connection(
    connection_id: str,
    request: Request,
    principal: PrincipalDep,
    sources: SourcesDep,
    audit: AuditDep,
) -> ConnectionTest:
    """*Test connection* (ADR-140 Amendment 13): a SQL login signed in over TLS and found read-only,
    an API's host allowed and its secret set. Nothing is read, and no secret is answered."""
    try:
        connection = await sources.connection(connection_id)
    except UnknownConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "detail": "There is no such connection."},
        ) from exc
    result = await check_connection(connection, get_connector_readers(request))
    await audit.record(principal=principal, action="test_ingest_connection",
                       resolved_query={"connection_id": connection_id, "ok": result.ok},
                       result_cardinality=1)  # fmt: skip
    return result


async def _connection_body(request: Request) -> ConnectionInput:
    """Admin › Connections' body, read here rather than by FastAPI, whose 422 carries each refused
    input back: a secret's value pasted into the field for its name, or into any other, would be
    answered to the screen (L2.7; ADR-140 Amendment 13: a secret is never answered). The refusal
    names each field and why, never what was sent, as `_model_admin_body` does for Models."""
    raw = await request.body()
    try:
        return ConnectionInput.model_validate_json(raw)
    except ValidationError as invalid:
        try:
            sent = model_admin_module.sent_values(json.loads(raw))
        except ValueError:
            sent = {raw.decode("utf-8", "replace")}
        words = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: "
            + str(e.get("msg", "")).removeprefix("Value error, ")
            for e in invalid.errors(include_input=False, include_context=False, include_url=False)
        )
        raise HTTPException(
            status_code=422,
            detail={"error": "connection_refused",
                    "detail": model_admin_module.redacted(words, sent)},
        ) from None  # fmt: skip


@app.post(
    "/v1/admin/connections",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def add_admin_connection(
    request: Request, principal: PrincipalDep, sources: SourcesDep, audit: AuditDep
) -> Connection:
    """An administrator names a connection (ADR-140 Amendments 4 and 13): files, SQL, API or JSON,
    each naming its secret, never carrying it. The body is read here (`_connection_body`), so a
    value pasted into a field the schema refuses is never answered back (L2.7)."""
    body = await _connection_body(request)
    # ADR-140 Amendment 13 (the orchestrator's review of L1.6): a host that is, or resolves to, an
    # address inside the deployment is refused before it is kept; the schema refuses written forms.
    try:
        await asyncio.to_thread(refuse_connection_hosts, body.settings)  # a lookup: off the loop
    except ConnectorRefused as refused:
        raise _connector_refused(refused, principal) from refused
    try:
        made = await sources.add_connection(body, principal)
    except SecretInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "secret_in_use",
                    "detail": "That secret is already used by another connection: a secret "
                    "belongs to one connection, so give this one its own."},
        ) from exc  # fmt: skip
    await audit.record(
        principal=principal,
        action="add_ingest_connection",
        resolved_query={"connection_id": made.id, "kind": made.kind, "name": made.name},
        result_cardinality=1,
    )
    return made


@app.get(
    "/v1/datasets/{dataset_id}/source-files",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))],
)
async def list_dataset_source_files(
    dataset_id: StudioDatasetDep, principal: SourceAuthorDep, audit: AuditDep
) -> IngestSourceListing:
    """The register wizard's file step: the dataset's own files under the ingest root, and those
    placed before ADR-099 Amendment 3 (`list_source_files`), exactly as Connect lists them."""
    listing = list_source_files(datasets=[dataset_id])
    await audit.record(
        principal=principal,
        action="list_dataset_source_files",
        resolved_query={"dataset_id": dataset_id},
        result_cardinality=len(listing.files),
    )
    return listing


# --- the screening-list connector, and a dataset's lists (ADR-140 Amendment 13) -----------------


#: The imports a list's history shows; `more` says when there are older ones.
LIST_IMPORTS_SHOWN = 20


def _subscribable(lists: Sequence[DeploymentList]) -> list[SubscribableList]:
    """The deployment's lists as a source author sees them to subscribe to: never a file's
    location, who added it, the real dataset it is, its mapping or its failure's words."""
    return [
        SubscribableList(
            id=x.id,
            name=x.name,
            template=x.template,
            version=x.version,
            entries=x.entries,
            updated_at=x.updated_at,
            failing=x.failure is not None,
            schedule_words=x.schedule_words,
        )  # fmt: skip
        for x in lists
    ]


def _list_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "not_found", "detail": "There is no deployment-wide list of that id."},
    )


@app.get(
    "/v1/studio/screening-lists",
    dependencies=[Depends(require_right(Right.LOAD_SCREENING_LISTS))],
)
async def list_deployment_lists(
    principal: PrincipalDep, lists: ListStoreDep, audit: AuditDep
) -> list[DeploymentList]:
    """The deployment-wide screening lists: template, version, entries, last import, failure and
    schedule, for whoever may load screening lists (ADR-112 L9)."""
    found = await lists.lists()
    await audit.record(principal=principal, action="list_deployment_lists", investigation_id=None,
                       resolved_query={}, result_cardinality=len(found))  # fmt: skip
    return found


@app.post(
    "/v1/studio/screening-lists",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.LOAD_SCREENING_LISTS))],
)
async def add_deployment_list(
    body: DeploymentListInput, principal: PrincipalDep, lists: ListStoreDep, audit: AuditDep
) -> DeploymentList:
    """A list named for the deployment, with its template and its file in the ingest folder.
    Nothing is read until it is imported (*Refresh now*); a location outside the folder is refused
    now, in words that do not say whether anything is there."""
    try:
        check_list_location(body.location)
        made = await lists.add(body, principal.id)
    except ListConnectorRefused as refused:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "list_refused", "detail": str(refused)},
        ) from refused
    await audit.record(principal=principal, action="add_deployment_list", investigation_id=None,
                       resolved_query={"list_id": made.id, "name": made.name,
                                       "template": made.template},
                       result_cardinality=1)  # fmt: skip
    return made


@app.post(
    "/v1/studio/screening-lists/{list_id}/refresh",
    dependencies=[Depends(require_right(Right.LOAD_SCREENING_LISTS))],
)
async def refresh_deployment_list(
    list_id: str,
    request: Request,
    principal: PrincipalDep,
    lists: ListStoreDep,
    rows_kept: ListRowsDep,
    audit: AuditDep,
) -> ListImport:
    """*Refresh now*: the list read through its template, kept as a new version if its rows
    changed, and the attempt recorded in words whatever it did."""
    try:
        done = await import_list(list_id, store=lists, rows_kept=rows_kept)
    except ListNotFound as missing:
        raise _list_not_found() from missing
    await _rules_on_list_refresh(request.app.state, done, DEPLOYMENT_WIDE)
    await audit.record(principal=principal, action="deployment_list_refreshed",
                       investigation_id=None,
                       resolved_query={"list_id": list_id, "outcome": done.outcome,
                                       "version": done.version},
                       result_cardinality=done.added + done.changed + done.delisted)  # fmt: skip
    return done


@app.get(
    "/v1/studio/screening-lists/{list_id}/imports",
    dependencies=[Depends(require_right(Right.LOAD_SCREENING_LISTS))],
)
async def list_deployment_list_imports(
    list_id: str, principal: PrincipalDep, lists: ListStoreDep, audit: AuditDep
) -> ListImports:
    """A list's latest imports, newest first: what each did, in words, and whether older ones were
    left out (rule 2: never cut short without saying so)."""
    try:
        await lists.get(list_id)
    except ListNotFound as missing:
        raise _list_not_found() from missing
    found = await lists.imports(list_id, limit=LIST_IMPORTS_SHOWN + 1)
    await audit.record(principal=principal, action="list_deployment_list_imports",
                       investigation_id=None, resolved_query={"list_id": list_id},
                       result_cardinality=len(found))  # fmt: skip
    return ListImports(imports=found[:LIST_IMPORTS_SHOWN], more=len(found) > LIST_IMPORTS_SHOWN)


@app.put(
    "/v1/studio/screening-lists/{list_id}/schedule",
    dependencies=[Depends(require_right(Right.LOAD_SCREENING_LISTS))],
)
async def set_deployment_list_schedule(
    list_id: str,
    body: ListScheduleInput,
    principal: PrincipalDep,
    lists: ListStoreDep,
    audit: AuditDep,
) -> DeploymentList:
    """The list refreshed every day or every week at an hour, as the person setting it; with no
    schedule, by hand only."""
    try:
        if body.schedule is not None:
            check_list_schedule(body.schedule)
        updated = await lists.set_schedule(list_id, body.schedule, principal.id, datetime.now(UTC))
    except ListScheduleRefused as refused:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "schedule_refused", "detail": str(refused)},
        ) from refused
    except ListNotFound as missing:
        raise _list_not_found() from missing
    await audit.record(principal=principal, action="deployment_list_schedule_set",
                       investigation_id=None,
                       resolved_query={"list_id": list_id, "schedule": (
                           body.schedule.model_dump() if body.schedule else None)},
                       result_cardinality=1)  # fmt: skip
    return updated


@app.get(
    "/v1/datasets/{dataset_id}/screening-subscriptions",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))],
)
async def dataset_list_subscriptions(
    dataset_id: StudioDatasetDep, principal: SourceAuthorDep, lists: ListStoreDep, audit: AuditDep
) -> DatasetSubscriptions:
    """The deployment-wide lists, and which this dataset subscribes to, by id."""
    found = DatasetSubscriptions(
        lists=_subscribable(await lists.lists()), subscribed=await lists.subscribed(dataset_id)
    )
    await audit.record(principal=principal, action="dataset_list_subscriptions",
                       investigation_id=None, resolved_query={"dataset_id": dataset_id},
                       result_cardinality=len(found.subscribed))  # fmt: skip
    return found


@app.put(
    "/v1/datasets/{dataset_id}/screening-subscriptions/{list_id}",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES)), NoLoadingAComposite],
)
async def subscribe_dataset_to_list(
    dataset_id: StudioDatasetDep,
    list_id: str,
    principal: SourceAuthorDep,
    lists: ListStoreDep,
    audit: AuditDep,
) -> DatasetSubscriptions:
    """The dataset subscribes to a deployment-wide list by its id: its rules and Lookups may then
    read it. A list of that id must exist; a name is never enough."""
    try:
        await lists.subscribe(dataset_id, list_id, principal.id)
    except ListNotFound as missing:
        raise _list_not_found() from missing
    await audit.record(principal=principal, action="dataset_list_subscribed",
                       investigation_id=None,
                       resolved_query={"dataset_id": dataset_id, "list_id": list_id},
                       result_cardinality=1)  # fmt: skip
    return DatasetSubscriptions(
        lists=_subscribable(await lists.lists()), subscribed=await lists.subscribed(dataset_id)
    )


@app.delete(
    "/v1/datasets/{dataset_id}/screening-subscriptions/{list_id}",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES)), NoLoadingAComposite],
)
async def unsubscribe_dataset_from_list(
    dataset_id: StudioDatasetDep,
    list_id: str,
    principal: SourceAuthorDep,
    lists: ListStoreDep,
    audit: AuditDep,
) -> DatasetSubscriptions:
    """The dataset no longer reads the list; a pipeline that looks it up is refused by the save gate
    at its next save, Test or run, in words."""
    await lists.unsubscribe(dataset_id, list_id)
    await audit.record(principal=principal, action="dataset_list_unsubscribed",
                       investigation_id=None,
                       resolved_query={"dataset_id": dataset_id, "list_id": list_id},
                       result_cardinality=1)  # fmt: skip
    return DatasetSubscriptions(
        lists=_subscribable(await lists.lists()), subscribed=await lists.subscribed(dataset_id)
    )


async def _own_lists(
    dataset_id: str, models: TargetModelStore, rows_kept: ListRows
) -> list[ReferenceList]:
    """The dataset's own lists with rows kept, whose ids its live domain model names (Amendment
    12): each at the highest version kept. One reading, shared with the rule editor's."""
    return await rule_editor.own_lists(dataset_id, models, rows_kept)


@app.get(
    "/v1/datasets/{dataset_id}/reference-lists/offered",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def offered_reference_lists(
    dataset_id: StudioDatasetDep,
    principal: PrincipalDep,
    lists: ListStoreDep,
    rows_kept: ListRowsDep,
    models: TargetModelsDep,
    audit: AuditDep,
) -> list[OfferedList]:
    """The lists this dataset's rules and Lookups are offered: its own, and the deployment-wide
    lists it subscribes to, exactly as the save gate reads them. Never another dataset's."""
    own = await _own_lists(dataset_id, models, rows_kept)
    found = await offered_lists(dataset_id, store=lists, own=own)
    await audit.record(principal=principal, action="offered_reference_lists",
                       investigation_id=None, resolved_query={"dataset_id": dataset_id},
                       result_cardinality=len(found))  # fmt: skip
    return found


@app.post(
    "/v1/datasets/{dataset_id}/reference-lists/{list_id}/import",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES)), NoLoadingAComposite],
)
async def import_dataset_own_list(
    dataset_id: StudioDatasetDep,
    list_id: str,
    body: DatasetOwnListImportInput,
    request: Request,
    principal: SourceAuthorDep,
    rows_kept: ListRowsDep,
    models: TargetModelsDep,
    audit: AuditDep,
) -> ListImport:
    """A dataset's own reference list's rows, from one of the dataset's own files: a new version
    when they differ from the version kept, none when they do not. The file must be one the
    dataset's listing offers, refused in the same words whether or not it exists."""
    offered = {f.source_location for f in list_source_files(datasets=[dataset_id]).files}
    if body.location not in offered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "source_not_offered",
                "detail": "That file is not one of this dataset's files in the ingest folder. "
                "Choose it from the dataset's files, or upload it.",
            },
        )
    live = await models.live(dataset_id)
    try:
        # Sized before it is read, so a file past the cap is never read whole (rule 2).
        if Path(body.location).stat().st_size > connector_reads_module.MAX_BYTES:
            raise ListConnectorRefused(
                f"the file is more than {connector_reads_module.MAX_BYTES} bytes, more than one "
                "import may take; nothing was kept (rule 2)"
            )
        reference, outcome = import_own_list(
            dataset_id, list_id, Path(body.location).read_bytes(), rows_kept=rows_kept,
            named=live.reference_lists if live is not None else [],
            name=body.name, key_column=body.key_column,
        )  # fmt: skip
    except ListConnectorRefused as refused:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "list_refused", "detail": str(refused)},
        ) from refused
    words = (
        f"{reference.name} is unchanged at version {reference.version}"
        if outcome == "unchanged"
        else f"{reference.name} is now version {reference.version}"
    )
    await audit.record(principal=principal, action="import_dataset_own_list",
                       investigation_id=None,
                       resolved_query={"dataset_id": dataset_id, "list_id": list_id,
                                       "outcome": outcome, "version": reference.version},
                       result_cardinality=1)  # fmt: skip
    done = ListImport(list_id=list_id, outcome=outcome, version=reference.version, words=words)
    # ADR-146 decision 3: a rule that runs when this list refreshes runs now.
    await _rules_on_list_refresh(request.app.state, done, dataset_id)
    return done


# --- a drawn dataset (ADR-143 Amendment 2 decision 5; ADR-140 Amendment 9 decision 2; L3.1b) -----


@app.post(
    "/v1/datasets/drawn",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.CREATE_CASE))],
)
async def make_drawn_dataset(
    request: Request,
    body: DrawnDatasetInput,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    datasets: DatasetsDep,
    models: TargetModelsDep,
    scheme: HandlingSchemeDep,
    ontology: OntologyDep,
    audit: AuditDep,
) -> HomeCase:
    """*New drawing board* with no case: in one step, a drawn dataset named after the drawing, its
    domain model live at version 1 (the starter pack chosen, or the POLE core alone), and its home
    case, its maker its Author. Its highest marking is the maker's choice within their own
    clearance. The board itself is L3.3's. No other case may choose it, no pipeline loads into it,
    and no rule runs on it until it is merged."""
    return await _make_drawn(
        body, principal, investigations, datasets, models, scheme, ontology, audit
    )


async def _make_drawn(
    body: DrawnDatasetInput,
    principal: Principal,
    investigations: Any,
    datasets: DatasetStore,
    models: TargetModelStore,
    scheme: HandlingScheme,
    ontology: OntologySchema,
    audit: AuditWriter,
) -> HomeCase:
    """The drawn dataset, its live model and its home case, as `POST /v1/datasets/drawn` and
    `POST /v1/drawings` both make them."""
    if body.highest_marking not in scheme.classification:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{body.highest_marking!r} is not a marking of this deployment",
        )
    if not scheme.clears(principal.clearance, body.highest_marking):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "above_your_clearance",
                "message": "a drawn dataset may hold nothing above your own clearance, "
                f"{principal.clearance}",
            },
        )
    if body.pack is not None and body.pack not in ontology.packs:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"the starter pack {body.pack!r} is not one this deployment carries",
        )
    home = await investigations.create(principal, name=body.name)
    drawn = await datasets.create_drawn(
        principal, body.name, highest_marking=body.highest_marking, home_case=home.id
    )
    # Its home case is recorded before its model goes live, as at *Make live*: a dataset with a
    # live model always has its home case.
    made = HomeCase(
        dataset_id=drawn.id, investigation_id=home.id, made_at=home.created_at,
        made_by=principal.id,
    )  # fmt: skip
    await datasets.set_home_case(made)
    await models.open_draft(drawn.id, principal)
    packs = {body.pack: ontology.packs[body.pack]} if body.pack is not None else {}
    await models.save_draft(drawn.id, TargetModelDraftInput(packs=packs), principal)
    await models.make_live(drawn.id, 1, principal)
    await audit.record(
        principal=principal,
        action="make_drawn_dataset",
        investigation_id=home.id,
        resolved_query={"dataset_id": drawn.id, "pack": body.pack,
                        "highest_marking": body.highest_marking},
        result_cardinality=1,
    )  # fmt: skip
    return made


@app.post(
    "/v1/drawings",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.CREATE_CASE)), *_DRAWS],
)
async def start_a_drawing(
    body: DrawingInput,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    datasets: DatasetsDep,
    models: TargetModelsDep,
    scheme: HandlingSchemeDep,
    ontology: OntologyDep,
    boards: BoardsDep,
    audit: AuditDep,
) -> NewDrawing:
    """*New drawing board* with no case (ADR-143 Amendment 2 decision 5): in one step, a drawn
    dataset named after the drawing, its home case with the maker as its Author, and the board.
    What is drawn on it is written to the drawn dataset itself (Amendment 3 decision 1)."""
    home = await _make_drawn(
        DrawnDatasetInput(name=body.name, pack=body.pack, highest_marking=body.highest_marking),
        principal, investigations, datasets, models, scheme, ontology, audit,
    )  # fmt: skip
    board = await boards.views.save_board(
        home.investigation_id, body.name, principal.id, node_ids=[]
    )
    await _audit_board(audit, principal, "make_board", home.investigation_id, board_id=board.id,
                       start="drawing", dataset_id=home.dataset_id)  # fmt: skip
    return NewDrawing(
        dataset_id=home.dataset_id,
        investigation_id=home.investigation_id,
        board=await boards.wire(board, principal),
    )


# --- ingest studio: a dataset's domain model (ADR-140 decisions 4 and 5, R12; L3.1b) ------------

#: Every model route: the dataset's own gate, then the right (ADR-112 Amendment 6).
_EDITS_THE_MODEL = [Depends(require_right(Right.EDIT_TARGET_MODEL))]
#: And every write of one: a composite's own model waits for its superset check over its members'
#: models (phase 5 item 4), and a composite is read-only for now (ADR-099 Amendment 14), so its
#: model is read, not changed.
_CHANGES_THE_MODEL = [*_EDITS_THE_MODEL, Depends(refuse_changing_a_composites_model)]


# --- promotion: the Studio's Analyst promotions and a removed case's layer (L3.4) -----------
# After the dataset's own gate (`StudioDatasetDep`), which a route above it would not resolve.


async def _may_review(
    promotions: Promotions, dataset_id: str, principal: Principal
) -> tuple[bool, str | None]:
    if await promotions.is_author_of(dataset_id, principal):
        return True, None
    return False, (
        "Only one of the dataset's Authors who may review promotions can decide this: you are not "
        "one of its Authors."
    )


@app.get("/v1/datasets/{dataset_id}/promotions", dependencies=_REVIEWS)
async def list_dataset_promotions(
    dataset_id: StudioDatasetDep,
    principal: PrincipalDep,
    promotions: PromotionsDep,
) -> PromotionsList:
    """The Ingest Studio's *Analyst promotions* (decision 10): every promotion into the dataset,
    as counts and words; the items themselves only through *Details*. A promotion marked above the
    reader's clearance is not listed (rule 3)."""
    author, why = await _may_review(promotions, dataset_id, principal)
    reverts = Right.REVERT_LOADS in rights_for(principal.roles)
    out = []
    # Rule 3: the reader's clearance is in the store's query, never applied after the read. Drawn
    # items carry only a permitted handling code (`Boards._handling`), so the classification is
    # the whole of their audience beyond the dataset the gate has already checked.
    held = await promotions.store.into(
        dataset_id, markings=_markings_cleared(promotions, principal)
    )
    # An Author is given the counts *Details* would show them (Amendment 5 decision 6a). Anyone
    # else reads none of the items; the recorded counts, of a promotion marked within their
    # clearance (kept current by `item_marked`), say nothing they may not know.
    shown = await promotions.shown_counts(held, principal) if author else {}
    for record in held:
        own = record.proposed_by == principal.id
        out.append(
            await promotions.view(
                record, principal, may_review=author and not own, reverts=reverts,
                why_not="You sent this promotion: a second person must review it." if own
                else why,
                # The case is named to the dataset's Authors, who answer for it, and its proposer.
                show_case=author or own, counts=shown.get(record.id),
            )
        )  # fmt: skip
    return PromotionsList(promotions=out)


def _markings_cleared(promotions: Promotions, principal: Principal) -> list[str]:
    scheme = promotions.boards.scheme
    return [m for m in scheme.classification if scheme.clears(principal.clearance, m)]


def _cleared_for(promotions: Promotions, principal: Principal, record: Any) -> bool:
    """Rule 3: a promotion marked above the reader's clearance is, to them, no promotion."""
    return promotions.boards.scheme.clears(principal.clearance, record.marking)


async def _reviewable(
    promotions: Promotions, dataset_id: str, promotion_id: str, principal: Principal
) -> Any:
    record = await promotions.of_dataset(dataset_id, promotion_id)
    if not _cleared_for(promotions, principal, record):
        raise PromotionNotFound
    if not await promotions.is_author_of(dataset_id, principal):
        raise PromotionRefused(
            "not_an_author",
            "Only one of the dataset's Authors who may review promotions can read or decide this.",
            status=403,
        )
    return record


@app.get("/v1/datasets/{dataset_id}/promotions/{promotion_id}", dependencies=_REVIEWS)
async def promotion_details(
    dataset_id: StudioDatasetDep,
    promotion_id: str,
    principal: PrincipalDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> PromotionDetails:
    """*Details*: the promotion's own items, read from its layer through the reviewer's own
    handling (Amendment 2 decision 1: a reviewer reads what they review), audited."""
    record = await _reviewable(promotions, dataset_id, promotion_id, principal)
    details = await promotions.details(record, principal)
    await _audit_promotion(
        audit, principal, "read_promotion", record.case_id, len(details.items),
        promotion_id=record.id, dataset_id=dataset_id,
    )  # fmt: skip
    return details


@app.post("/v1/datasets/{dataset_id}/promotions/{promotion_id}/decision", dependencies=_REVIEWS)
async def decide_promotion(
    dataset_id: StudioDatasetDep,
    promotion_id: str,
    body: PromotionDecision,
    principal: PrincipalDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> Promotion:
    """*Approve and commit* or *Reject with a reason* (C9, C11; ADR-133 Amendment 8)."""
    record = await _reviewable(promotions, dataset_id, promotion_id, principal)
    decided = await promotions.decide(record, principal, approve=body.approve, reason=body.reason)
    copies = await _copies_audited(promotions, decided)
    await _audit_promotion(
        audit, principal, "approve_promotion" if body.approve else "reject_promotion",
        record.case_id, len(record.node_ids) + len(record.edge_ids) + len(copies),
        promotion_id=record.id, load_id=record.load_id, dataset_id=dataset_id,
        reason=body.reason, **({"copies": copies} if copies else {}),
    )  # fmt: skip
    return await promotions.view(decided, principal, show_case=True)  # one of its Authors


# --- a drawn dataset merged into another (ADR-143 Amendment 2 decision 6; Amendment 3) -------

#: Amendment 3 decision 2 (L6 answered (a)): `merge_datasets` on every route, and an Author of the
#: target asked by the service; an administrator does not merge one by being an administrator.
_MERGES = [Depends(require_right(Right.MERGE_DATASETS))]


def get_drawn_merges(
    promotions: PromotionsDep, investigations: InvestigationsDep
) -> drawn_merge_module.DrawnMerges:
    return drawn_merge_module.DrawnMerges(promotions=promotions, cases=investigations)


DrawnMergesDep = Annotated[drawn_merge_module.DrawnMerges, Depends(get_drawn_merges)]


@app.get("/v1/datasets/{dataset_id}/merge-targets", dependencies=_MERGES)
async def drawn_merge_targets(
    dataset_id: StudioDatasetDep, principal: PrincipalDep, merges: DrawnMergesDep
) -> MergeTargets:
    """*Merge into a dataset…*: the datasets this reader may merge the drawing into (those they
    are an Author of, of the drawing's unit), or why it is merged into none."""
    drawn, _ = await merges.drawn(dataset_id)
    return await merges.target_list(drawn, principal)


_MERGE_MAPPING = TypeAdapter(Annotated[list[TypeChoice], Field(max_length=500)])


def _merge_mapping(given: str | None) -> list[TypeChoice]:
    if not given:
        return []
    try:
        return _MERGE_MAPPING.validate_json(given)
    except ValidationError:
        raise PromotionRefused(
            "not_a_mapping", "The mapping could not be read: choose from Map again.", status=422
        ) from None


@app.get("/v1/datasets/{dataset_id}/merge-sheet", dependencies=_MERGES)
async def drawn_merge_sheet(
    dataset_id: StudioDatasetDep,
    target: str,
    principal: PrincipalDep,
    merges: DrawnMergesDep,
    audit: AuditDep,
    mapping: str | None = None,
) -> DrawnMergeSheet:
    """Map and match: the drawing's items as the merger may see them, against the target's model
    and the target's loaded nodes alone; audited (it reads the drawing for a merge). `mapping`, a
    JSON list of `TypeChoice`, is the mapping chosen so far (ADR-143 Amendment 7): the matches are
    offered as each node goes in under it, as the merge will check them."""
    chosen = _merge_mapping(mapping)
    drawn, case_id = await merges.drawn(dataset_id)
    into = await merges.target(drawn, target, principal)
    sheet = await merges.sheet(drawn, case_id, into, principal, chosen)
    await _audit_promotion(
        audit, principal, "read_drawn_merge_sheet", case_id, len(sheet.items),
        dataset_id=dataset_id, target_dataset_id=into.id,
        # The mapping that chose which loaded nodes were offered (the fourth review, minor 7).
        mapping=[c.model_dump() for c in chosen],
    )  # fmt: skip
    return sheet


@app.post("/v1/datasets/{dataset_id}/merges/dry-run", dependencies=_MERGES)
async def drawn_merge_dry_run(
    dataset_id: StudioDatasetDep,
    body: DrawnMergeInput,
    principal: PrincipalDep,
    merges: DrawnMergesDep,
    audit: AuditDep,
) -> DrawnMergeDryRun:
    """The dry run: every check, nothing written but its audit entry (it reads the drawing for a
    merge, as the sheet does)."""
    drawn, case_id = await merges.drawn(dataset_id)
    into = await merges.target(drawn, body.target_dataset_id, principal)
    ran = await merges.dry_run(drawn, case_id, into, body, principal)
    await _audit_promotion(
        audit, principal, "dry_run_drawn_merge", case_id, ran.nodes + ran.links,
        dataset_id=dataset_id, target_dataset_id=into.id,
    )  # fmt: skip
    return ran


@app.post(
    "/v1/datasets/{dataset_id}/merges",
    status_code=status.HTTP_201_CREATED,
    dependencies=_MERGES,
)
async def merge_drawn_dataset(
    dataset_id: StudioDatasetDep,
    body: DrawnMergeInput,
    principal: PrincipalDep,
    merges: DrawnMergesDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> Promotion:
    """*Merge*: one load into the target (trigger `drawn_merge`), committed at once or sent for
    review under the target's policy."""
    drawn, case_id = await merges.drawn(dataset_id)
    into = await merges.target(drawn, body.target_dataset_id, principal)
    record = await merges.merge(drawn, case_id, into, body, principal)
    copies = await _copies_audited(promotions, record)
    await _audit_promotion(
        audit, principal, "merge_drawn_dataset", case_id,
        len(record.node_ids) + len(record.edge_ids) + len(copies), promotion_id=record.id,
        load_id=record.load_id, dataset_id=dataset_id, target_dataset_id=into.id,
        status=record.status, matches=len(body.matches),
        # Amendment 7: the mapping chosen, and each retyped item with the element written for it.
        mapping=[c.model_dump() for c in body.mapping], copies=copies,
    )  # fmt: skip
    return await promotions.view(record, principal, show_case=True)  # one of the target's Authors


# --- a removed case's layer (ADR-143 Amendment 2 decision 1) ---------------------------------


async def _removed_case(
    dataset_id: str,
    investigation_id: str,
    principal: Principal,
    datasets: DatasetStore,
    investigations: InvestigationStore,
    graph: GraphPort,
) -> tuple[Dataset, AdminLinkedCase, str]:
    """The dataset, the removed case reading it directly, and its layer; refused in words for a
    case that is open, not linked to this dataset, or holding no layer."""
    dataset = (await datasets.egress_of([dataset_id])).get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    row = next(
        (c for c in await _linked_cases(dataset, datasets, investigations, graph, principal,
                                        only=investigation_id)
         if c.through is None),
        None,
    )  # fmt: skip
    # Strict (rule 3; the lane review's minor 12): an open case reading the dataset answers as one
    # that reads it not at all, so the dataset's Authors cannot tell an open case's id by probing.
    if row is None or row.state != "removed":
        raise LayerActionRefused(
            404, "case_not_linked", "No removed case of that id reads this dataset."
        )
    layer = await datasets.layer_of_case(investigation_id)
    if layer is None:
        raise LayerActionRefused(404, "no_layer", "That case holds no layer.")
    return dataset, row, layer


async def _an_author(promotions: Promotions, dataset_id: str, principal: Principal) -> None:
    if not await promotions.is_author_of(dataset_id, principal):
        raise LayerActionRefused(
            403, "not_an_author",
            "Only one of the dataset's Authors may merge or delete a removed case's layer.",
        )  # fmt: skip


_COMPOSITE_NEVER_MERGED = (
    "A composite case's layer is never merged into a dataset, only deleted: its items were drawn "
    "over several datasets at once."
)


@app.get("/v1/datasets/{dataset_id}/removed-cases")
async def removed_case_layers(
    dataset_id: StudioDatasetDep,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> RemovedCaseLayers:
    """The removed cases reading this dataset, for its Authors: counts only, never contents.
    Audited, as Admin's own list of a dataset's cases is (`list_dataset_cases`): it reads across
    cases the Author is no member of."""
    await _an_author(promotions, dataset_id, principal)
    dataset = (await datasets.egress_of([dataset_id]))[dataset_id]
    rows = await _linked_cases(dataset, datasets, investigations, graph, principal)
    removed = [r for r in rows if r.state == "removed" and r.through is None]
    await _audit_promotion(
        audit, principal, "list_removed_case_layers", None, len(removed), dataset_id=dataset_id,
    )  # fmt: skip
    composite = dataset.kind == "composite"
    gazetteer = is_gazetteer(dataset)
    why_not = (
        _COMPOSITE_NEVER_MERGED
        if composite
        else GAZETTEER_TAKES_NOTHING_DRAWN
        if gazetteer
        else None
    )
    return RemovedCaseLayers(
        dataset_id=dataset_id,
        cases=[
            RemovedCaseLayer(
                investigation_id=r.investigation_id, name=r.name, items=r.items + r.links,
                mergeable=why_not is None, why_not=why_not,
            )
            for r in removed
        ],
    )  # fmt: skip


@app.post(
    "/v1/datasets/{dataset_id}/removed-cases/{case_id}/merge-sheet", dependencies=_LAYER_WRITES
)
async def open_layer_merge(
    dataset_id: StudioDatasetDep,
    case_id: str,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> LayerMergeSheet:
    """*Merge into the dataset*: opening it grants this Author read access to that one layer, for
    this merge alone, recorded in the audit before anything of it is read."""
    await _an_author(promotions, dataset_id, principal)
    dataset, row, layer = await _removed_case(
        dataset_id, case_id, principal, datasets, investigations, graph
    )
    if is_composite(dataset):
        raise LayerActionRefused(409, "composite_never_merged", _COMPOSITE_NEVER_MERGED)
    if is_gazetteer(dataset):
        raise LayerActionRefused(409, "gazetteer_never_merged", GAZETTEER_TAKES_NOTHING_DRAWN)
    await _audit_promotion(
        audit, principal, "open_layer_merge", case_id, 0, dataset_id=dataset_id,
        layer_id=layer,
    )  # fmt: skip
    return await promotions.open_merge(dataset, case_id, row.name, layer, principal)


async def _merge_grant_case(promotions: Promotions, grant_id: str) -> tuple[str, str]:
    grant = await promotions.store.grant(grant_id)
    if grant is None:
        raise PromotionRefused("no_open_grant", "This merge is closed.", status=403)
    case = await promotions._case_name(grant.case_id)
    return grant.case_id, case


@app.get("/v1/datasets/{dataset_id}/layer-merges/{grant_id}")
async def read_layer_merge(
    dataset_id: StudioDatasetDep,
    grant_id: str,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> LayerMergeSheet:
    """The merge sheet again, through its grant: refused once the merge has closed."""
    await _an_author(promotions, dataset_id, principal)
    dataset = (await datasets.egress_of([dataset_id]))[dataset_id]
    grant = await promotions.store.grant(grant_id)
    if grant is None:
        raise PromotionRefused("no_open_grant", "This merge is closed.", status=403)
    case_id, case_name = await _merge_grant_case(promotions, grant_id)
    sheet = await promotions.merge_sheet(grant, dataset, case_name, principal)
    await _audit_promotion(
        audit, principal, "read_layer_merge", case_id, len(sheet.items), dataset_id=dataset_id,
        grant_id=grant_id, layer_id=grant.layer_id,
    )  # fmt: skip
    return sheet


@app.post(
    "/v1/datasets/{dataset_id}/layer-merges/{grant_id}",
    status_code=status.HTTP_201_CREATED,
    dependencies=_LAYER_WRITES,
)
async def merge_removed_case_layer(
    dataset_id: StudioDatasetDep,
    grant_id: str,
    body: LayerMergeInput,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> Promotion:
    """*Merge*: the ticked items as one promotion (trigger `layer_merge`) under the dataset's
    policy; the grant closes with the merge."""
    await _an_author(promotions, dataset_id, principal)
    dataset = (await datasets.egress_of([dataset_id]))[dataset_id]
    grant = await promotions.store.grant(grant_id)
    if grant is not None and grant.holder == principal.id and grant.closed_at is None:
        # The case again, now: one restored since the sheet was opened is merged no more, and its
        # grant closes.
        try:
            await _removed_case(dataset_id, grant.case_id, principal, datasets, investigations,
                                graph)  # fmt: skip
        except LayerActionRefused:
            await promotions.store.close_grant(grant_id, datetime.now(UTC))
            raise
    record = await promotions.merge(grant_id, dataset, body.item_ids, principal)
    await _audit_promotion(
        audit, principal, "merge_layer", record.case_id,
        len(record.node_ids) + len(record.edge_ids), promotion_id=record.id,
        load_id=record.load_id, dataset_id=dataset_id, status=record.status,
    )  # fmt: skip
    return await promotions.view(record, principal, show_case=True)  # one of its Authors


@app.post(
    "/v1/datasets/{dataset_id}/removed-cases/{case_id}/delete/dry-run", dependencies=_LAYER_WRITES
)
async def dry_run_delete_removed_case_layer(
    dataset_id: StudioDatasetDep,
    case_id: str,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> LayerDryRun:
    """*Delete…*'s dry run for one of the dataset's Authors (Amendment 2 decision 1: each outcome
    with a dry run first that writes nothing but its audit entry): the layer's counts as this
    reader's own handling takes them, as Admin's dry run does."""
    await _an_author(promotions, dataset_id, principal)
    _, row, _ = await _removed_case(dataset_id, case_id, principal, datasets, investigations, graph)
    await _audit_promotion(
        audit, principal, "dry_run_layer_delete", case_id, row.items + row.links,
        dataset_id=dataset_id, layer_action="delete",
    )  # fmt: skip
    counts = f"{row.items} items and {row.links} links ({_size_words(row.size_bytes)})"
    return LayerDryRun(
        investigation_id=case_id, action="delete", items=row.items, links=row.links,
        size_bytes=row.size_bytes,
        # The counts are the layer's as this reader may see it, promoted items included (they
        # hold the layer too): the words say what goes, never "N deleted" (Amendment 2 decision 1).
        would=f"{row.name}'s layer holds {counts}. Deleting it withdraws those not promoted; "
        "promoted items are never touched. Nothing has been written.",
    )  # fmt: skip


@app.delete(
    "/v1/datasets/{dataset_id}/layer-merges/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_LAYER_WRITES,
)
async def cancel_layer_merge(
    dataset_id: StudioDatasetDep,
    grant_id: str,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> None:
    """*Cancel*: the grant closes and nothing is merged."""
    await _an_author(promotions, dataset_id, principal)
    dataset = (await datasets.egress_of([dataset_id]))[dataset_id]
    await promotions.cancel_merge(grant_id, dataset, principal)
    await _audit_promotion(
        audit, principal, "cancel_layer_merge", None, 0, dataset_id=dataset_id, grant_id=grant_id
    )


async def _delete_layer(
    dataset_id: str,
    investigation_id: str,
    principal: Principal,
    datasets: DatasetStore,
    investigations: InvestigationStore,
    graph: GraphPort,
    promotions: Promotions,
    audit: AuditWriter,
) -> LayerDeleted:
    _, _, layer = await _removed_case(
        dataset_id, investigation_id, principal, datasets, investigations, graph
    )
    # Audited before anything is written (ADR-127 Amendment 23's order).
    await _audit_promotion(
        audit, principal, "delete_layer", investigation_id, 0, dataset_id=dataset_id,
        layer_id=layer,
    )  # fmt: skip
    return await promotions.delete_layer(investigation_id, layer)


@app.delete("/v1/datasets/{dataset_id}/removed-cases/{case_id}/layer", dependencies=_LAYER_WRITES)
async def delete_removed_case_layer(
    dataset_id: StudioDatasetDep,
    case_id: str,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> LayerDeleted:
    """*Delete* by one of the dataset's Authors: every item wholly the layer's withdrawn; promoted
    items never touched."""
    await _an_author(promotions, dataset_id, principal)
    return await _delete_layer(dataset_id, case_id, principal, datasets, investigations,
                               graph, promotions, audit)  # fmt: skip


@app.post(
    "/v1/admin/datasets/{dataset_id}/cases/{investigation_id}/delete",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def admin_delete_removed_case_layer(
    dataset_id: str,
    investigation_id: str,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    promotions: PromotionsDep,
    audit: AuditDep,
) -> LayerDeleted:
    """*Delete* by an administrator (Admin › Datasets), after its dry run, of the dataset's own
    unit alone (the owner's ruling of 9 November 2026; ADR-143 Amendment 5): a destructive write
    with no undo. Another unit's administrator, or one with no unit, is answered as for a dataset
    that does not exist, before anything is read (fails closed)."""
    dataset = await _admin_dataset_of(datasets, dataset_id)
    if principal.org_unit is None or dataset.owning_unit != principal.org_unit:
        raise UnknownDatasetEgressError(dataset_id)
    return await _delete_layer(dataset_id, investigation_id, principal, datasets, investigations,
                               graph, promotions, audit)  # fmt: skip


@app.get("/v1/datasets/{dataset_id}/model", dependencies=_EDITS_THE_MODEL)
async def read_dataset_model(
    dataset_id: StudioDatasetDep, models: TargetModelsDep
) -> DatasetModelView:
    """The live version and the open draft; both `None` for a dataset with no model yet."""
    live, draft = await models.live(dataset_id), await models.draft(dataset_id)
    return DatasetModelView(live=live, draft=draft)


@app.post(
    "/v1/datasets/{dataset_id}/model/draft",
    status_code=status.HTTP_201_CREATED,
    dependencies=_CHANGES_THE_MODEL,
)
async def open_dataset_model_draft(
    dataset_id: StudioDatasetDep, principal: PrincipalDep, models: TargetModelsDep, audit: AuditDep
) -> TargetModel:
    """Opens the draft (N+1) as a copy of the live version; a second is refused (409)."""
    draft = await models.open_draft(dataset_id, principal)
    await _audit_model(audit, principal, "open_model_draft", dataset_id, draft.version)
    return draft


@app.put("/v1/datasets/{dataset_id}/model/draft", dependencies=_CHANGES_THE_MODEL)
async def save_dataset_model_draft(
    dataset_id: StudioDatasetDep,
    body: TargetModelDraftInput,
    principal: PrincipalDep,
    models: TargetModelsDep,
    audit: AuditDep,
) -> TargetModel:
    """Saves the draft as given; an extension removed rather than retired, or a POLE core type
    named as one, is refused (409). Nothing that runs changes."""
    draft = await models.save_draft(dataset_id, body, principal)
    await _audit_model(audit, principal, "save_model_draft", dataset_id, draft.version)
    return draft


@app.delete(
    "/v1/datasets/{dataset_id}/model/draft",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_CHANGES_THE_MODEL,
)
async def discard_dataset_model_draft(
    dataset_id: StudioDatasetDep, principal: PrincipalDep, models: TargetModelsDep, audit: AuditDep
) -> None:
    draft = await models.draft(dataset_id)
    await models.discard_draft(dataset_id)
    version = draft.version if draft is not None else 0
    await _audit_model(audit, principal, "discard_model_draft", dataset_id, version)


async def _model_impact(
    request: Request, dataset_id: str, principal: Principal, models: TargetModelStore
) -> tuple[ModelImpact, TargetModel]:
    draft = await models.draft(dataset_id)
    live = await models.live(dataset_id)
    if draft is None:
        if live is None:
            raise NoModelYet
        raise TargetModelRefused("there is no draft: open one to see what it would change")
    impact = await impact_of(
        dataset_id, live, draft,
        pack_types=pack_types_of(get_ontology(request).type_packs),
        recipes=get_studio_recipes(request), datasets=get_datasets(request),
        cases=get_investigations(request), reader=principal,
    )  # fmt: skip
    return impact, draft


@app.get("/v1/datasets/{dataset_id}/model/impact", dependencies=_EDITS_THE_MODEL)
async def dataset_model_impact(
    request: Request, dataset_id: StudioDatasetDep, principal: PrincipalDep, models: TargetModelsDep
) -> ModelImpact:
    """What making the draft live would change (R12), read before anything does."""
    impact, _draft = await _model_impact(request, dataset_id, principal, models)
    return impact


@app.post("/v1/datasets/{dataset_id}/model/make-live", dependencies=_CHANGES_THE_MODEL)
async def make_dataset_model_live(
    request: Request,
    dataset_id: StudioDatasetDep,
    body: MakeLiveInput,
    principal: PrincipalDep,
    models: TargetModelsDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
) -> MadeLive:
    """The only step that changes what runs (R12): the draft named becomes live, the old live
    version previous, and every deployed pipeline writing a changed or retired type is marked as
    needing attention, its schedule paused with the reason. Loaded data is never rewritten."""
    impact, draft = await _model_impact(request, dataset_id, principal, models)
    datasets = get_datasets(request)
    first = await datasets.home_case_of(dataset_id) is None
    owners = await _owners_answered(request, datasets, body, first=first)
    if draft.version != body.version:
        raise TargetModelRefused(
            f"the draft is version {draft.version}, not {body.version}: it changed since it was "
            "opened, so read it again before making it live"
        )
    # The home case is claimed before the model goes live, so two first *Make live*s at once make
    # one home case and one live model: the second is refused in words at the claim, before it
    # changes anything (the round-1 review's must-fix 8).
    if owners is not None:
        await _make_the_home_case(request, dataset_id, owners, principal, audit)
    live, previous = await models.make_live(dataset_id, body.version, principal)
    reasons = {p.recipe_id: flag_reason(live, p) for p in impact.pipelines}
    await studio_recipes.flag_for_model(dataset_id, list(reasons.items()))
    for recipe_id, reason in reasons.items():
        await studio_recipes.set_paused(recipe_id, paused=True, reason=reason)
    await _audit_model(
        audit, principal, "make_model_live", dataset_id, live.version,
        flagged=sorted(reasons), changed_types=impact.changed_types,
    )  # fmt: skip
    return MadeLive(live=live, previous=previous, flagged=impact.pipelines)


@app.post(
    "/v1/datasets/{dataset_id}/model/revert",
    status_code=status.HTTP_201_CREATED,
    dependencies=_CHANGES_THE_MODEL,
)
async def revert_dataset_model(
    dataset_id: StudioDatasetDep,
    body: RevertModelInput,
    principal: PrincipalDep,
    models: TargetModelsDep,
    audit: AuditDep,
) -> TargetModel:
    """A new draft copying an earlier version (N+2), never a rewrite of it."""
    if await models.live(dataset_id) is None:
        raise NoModelYet
    draft = await models.revert(dataset_id, body.version, principal)
    await _audit_model(
        audit, principal, "revert_model", dataset_id, draft.version, reverted_from=body.version
    )
    return draft


# --- the Model tab's proposed link types (ADR-143 decision 9, ADR-090 Amendment 4; L3.5) -------

#: Behind the dataset's own gate (404 to anyone it is not for) and `accept_types`; deciding writes
#: the draft model, so a composite's is refused as its model is.
_DECIDES_TYPES = [Depends(require_right(Right.ACCEPT_TYPES))]


async def _reads_proposal_words(
    dataset_id: str, principal: Principal, datasets: DatasetStore, scheme: HandlingScheme
) -> bool:
    """`may_read_proposal_words` against the dataset's highest allowed marking, or the scheme's
    highest where none is set (the strict side)."""
    held = (await datasets.egress_of([dataset_id])).get(dataset_id)
    marking = (held.highest_marking if held is not None else None) or scheme.classification[-1]
    return may_read_proposal_words(principal, marking, scheme)


@app.get("/v1/datasets/{dataset_id}/model/proposals", dependencies=_DECIDES_TYPES)
async def list_model_proposals(
    dataset_id: StudioDatasetDep,
    principal: PrincipalDep,
    link_types: LinkTypesDep,
    datasets: DatasetsDep,
    scheme: HandlingSchemeDep,
) -> ModelProposalList:
    """The link types analysts proposed for this dataset, newest first, without their cases; to a
    reader not cleared for the dataset's highest marking, without their words either."""
    words = await _reads_proposal_words(dataset_id, principal, datasets, scheme)
    return ModelProposalList(
        proposals=await link_types.dataset_proposal_views(dataset_id, may_read_words=words)
    )


async def _audit_type_decision(
    audit: AuditWriter,
    principal: Principal,
    action: str,
    dataset_id: str,
    found: Any,
    why: str,
    **more: object,
) -> None:
    await audit.record(
        principal=principal,
        action=action,
        resolved_query={
            "dataset_id": dataset_id,
            "proposal_id": found.id,
            "name": found.name,
            **more,
        },
        result_cardinality=1,
        justification=why,
    )


@app.post(
    "/v1/datasets/{dataset_id}/model/proposals/{proposal_id}/accept",
    dependencies=[*_DECIDES_TYPES, Depends(refuse_changing_a_composites_model)],
)
async def accept_model_proposal(
    dataset_id: StudioDatasetDep,
    proposal_id: str,
    body: AcceptLinkTypeRequest,
    principal: PrincipalDep,
    link_types: LinkTypesDep,
    datasets: DatasetsDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> ModelProposalView:
    """*Add it to the draft model*, Direct or Probabilistic: made live with the next model
    version; never by its proposer. The draft it was written into is named in the audit, as the
    Studio's own draft routes name theirs."""
    words = await _reads_proposal_words(dataset_id, principal, datasets, scheme)
    found, version = await link_types.accept(
        dataset_id, proposal_id, principal, basis=body.basis, reason=body.reason,
        may_read_words=words,
    )  # fmt: skip
    await _audit_type_decision(
        audit, principal, "link_type_accept", dataset_id, found, body.reason,
        basis=body.basis, model_version=version,
    )  # fmt: skip
    return ModelProposalView.of(found, in_model="draft")


@app.post(
    "/v1/datasets/{dataset_id}/model/proposals/{proposal_id}/decline",
    dependencies=[*_DECIDES_TYPES, Depends(refuse_changing_a_composites_model)],
)
async def decline_model_proposal(
    dataset_id: StudioDatasetDep,
    proposal_id: str,
    body: LinkTypeDecisionRequest,
    principal: PrincipalDep,
    link_types: LinkTypesDep,
    datasets: DatasetsDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> ModelProposalView:
    """*Decline*, with a reason: its links stay in its case's layer for good."""
    words = await _reads_proposal_words(dataset_id, principal, datasets, scheme)
    found = await link_types.decline(
        dataset_id, proposal_id, principal, reason=body.reason, may_read_words=words
    )
    await _audit_type_decision(
        audit, principal, "link_type_decline", dataset_id, found, body.reason
    )
    return ModelProposalView.of(found)


ALREADY_OWNED = (
    "this dataset already has its owners: change them in Admin › Datasets (Change owner…), not at "
    "Make live"
)


class OwnerNeeded(Exception):
    """*Make live*'s owner step refused, in words (ADR-145 Amendment 4 decision 4); nothing is made
    live and no home case is made."""


@app.exception_handler(OwnerNeeded)
async def _owner_needed_handler(request: Request, exc: OwnerNeeded) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "owner_needed", "detail": str(exc)})


async def _owners_answered(
    request: Request, datasets: DatasetStore, body: MakeLiveInput, *, first: bool
) -> list[str] | None:
    """At a dataset's first *Make live* in the deployment, who answers for it: people (a team when
    teams are built, ADR-112 Amendment 5), as Admin › System allows, never a service account, and
    never no one. `None` on a later *Make live*, which asks nothing."""
    if not first:
        if body.owners is not None:
            raise OwnerNeeded(ALREADY_OWNED)
        return None
    if body.owners is None:
        raise OwnerNeeded(
            "who answers for this dataset? Name the people who will be its home case's Authors: "
            "it cannot go live without them"
        )
    return await _owners_allowed(request, datasets, body.owners)


async def _owners_allowed(
    request: Request, datasets: DatasetStore, owners: DatasetOwners
) -> list[str]:
    """Who may answer for a dataset, as *Make live* and Admin › Datasets' *Change owner…* both ask
    it (ADR-145 Amendment 4 decisions 4, 6 and 7): as Admin › System allows, people only until
    teams are built, never a service account, and only an account the directory says is a
    person. The refusals are in words (`OwnerNeeded`)."""
    allowed = await datasets.owner_setting()
    team: list[str] = []
    if owners.team is not None:
        if allowed == "people_only":
            raise OwnerNeeded("Admin › System allows people only as a dataset's owners")
        # ADR-145 Amendment 5 point 5: a team, by its role's id or name, owns as `team:<id>`.
        store = getattr(request.app.state, "custom_roles", None)
        found = None if store is None else next(
            (t for t in await store.teams(_today())
             if owners.team in (t.role_id, t.display_name)), None)  # fmt: skip
        if found is None:
            raise OwnerNeeded(
                f"there is no team {owners.team}: make a role a team in Admin › Roles"
            )
        team = [f"{TEAM_GRANT_PREFIX}{found.role_id}"]
    if allowed == "teams_only":
        if not team or owners.people:
            raise OwnerNeeded("Admin › System allows teams only as a dataset's owners: name a team "
                              "and no people")  # fmt: skip
        return team
    named = sorted(set(owners.people))
    if not named:
        return team
    people = await get_principal_names(request).people(named)
    if people is None:
        raise OwnerNeeded(
            "who answers for a dataset cannot be checked: this deployment has no identity "
            "provider directory to say who is a person"
        )
    if refused := [p for p in named if p not in people]:
        raise OwnerNeeded(
            "only a person may answer for a dataset, never a service account: "
            + ", ".join(refused)
            + (" is not one" if len(refused) == 1 else " are not")
        )
    return named + team


async def _make_the_home_case(
    request: Request, dataset_id: str, owners: list[str], maker: Principal, audit: AuditWriter
) -> None:
    """The dataset's home case (ADR-145 Amendment 4 decision 2): named for it, of its unit, reading
    it, its Authors exactly the owners named, audited. The claim (`set_home_case`, one per dataset,
    held by the store's own key) is its first write after the case: a second *Make live* that lost
    the race removes the case it made and is refused in words, so no dataset has two."""
    datasets = get_datasets(request)
    investigations = get_investigations(request)
    dataset = (await datasets.egress_of([dataset_id]))[dataset_id]
    home = await investigations.create(maker, name=dataset.name)
    try:
        await datasets.set_home_case(
            HomeCase(dataset_id=dataset_id, investigation_id=home.id, made_at=home.created_at,
                     made_by=maker.id)
        )  # fmt: skip
    except HomeCaseHeld:
        await investigations.remove(home.id, by=maker)
        raise OwnerNeeded(ALREADY_OWNED) from None
    await datasets.set_for_case(home.id, [dataset_id], maker, case_name=home.name)
    for owner in owners:
        await investigations.set_grant(home.id, owner, AccessLevel.AUTHOR, by=maker)
    if maker.id not in owners:
        await investigations.remove_grant(home.id, maker.id, by=maker)
    await audit.record(
        principal=maker,
        action="make_home_case",
        investigation_id=home.id,
        resolved_query={"dataset_id": dataset_id, "owners": owners},
        result_cardinality=1,
    )


async def _audit_model(
    audit: AuditWriter,
    principal: Principal,
    action: str,
    dataset_id: str,
    version: int,
    **detail: object,
) -> None:
    await audit.record(
        principal=principal,
        action=action,
        resolved_query={"dataset_id": dataset_id, "version": version, **detail},
        result_cardinality=1,
    )


# --- Studio › Releases (ADR-140 Amendment 9 decision 4) -----------------------------------------

#: Export reads the live model and the published pipelines; behind the dataset's own gate.
_EXPORTS_A_RELEASE = [
    Depends(require_right(Right.EDIT_TARGET_MODEL)),
    Depends(require_right(Right.PUBLISH_PIPELINES)),
]
#: Import writes the model's draft and pipeline drafts, as the model's and the canvas's own saves.
_IMPORTS_A_RELEASE = [
    Depends(require_right(Right.EDIT_TARGET_MODEL)),
    Depends(require_right(Right.EDIT_PIPELINES)),
    Depends(refuse_loading_a_composite),
]


@app.get("/v1/datasets/{dataset_id}/release", dependencies=_EXPORTS_A_RELEASE)
async def export_dataset_release(
    dataset_id: StudioDatasetDep,
    principal: PrincipalDep,
    models: TargetModelsDep,
    studio_recipes: StudioRecipesDep,
    rows_kept: ListRowsDep,
    staging_storage: StagingStorageDep,
    list_store: ListStoreDep,
    sources: SourcesDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
    name: Annotated[str, Query(min_length=1, max_length=253)],
    version: Annotated[str, Query(min_length=1, max_length=64)],
) -> ReleaseExport:
    """*Export* (Studio › Releases) and `ospreyflow release export`: the dataset's release as its
    bundle's files (`services/api/studio_release.py` has what is read, as the exporter). Refused
    in words (422 `release_refused`) when there is no live model or a file would hold a secret."""
    try:
        result = await export_release(
            dataset_id=dataset_id,
            principal=principal,
            metadata=ReleaseMetadata.model_construct(name=name, version=version),
            models=models,
            recipes=studio_recipes,
            rows_kept=rows_kept,
            staging_storage=staging_storage,
            list_store=list_store,
            sources=sources,
            scheme=handling_scheme,
            secrets=deployment_secrets(),
        )
    except BundleRefused as refused:
        return JSONResponse(  # type: ignore[return-value]
            status_code=422, content={"error": "release_refused", "problems": refused.problems}
        )
    await audit.record(
        principal=principal,
        action="export_dataset_release",
        resolved_query={"dataset_id": dataset_id, "name": name, "version": version},
        result_cardinality=len(result.files),
    )
    return ReleaseExport(
        files={path: data.decode("utf-8") for path, data in result.files.items()},
        left_out=result.left_out,
    )


@app.post("/v1/datasets/{dataset_id}/release/import", dependencies=_IMPORTS_A_RELEASE)
async def import_dataset_release(
    dataset_id: StudioDatasetDep,
    principal: SourceAuthorDep,
    body: ReleaseBundleInput,
    models: TargetModelsDep,
    studio_recipes: StudioRecipesDep,
    rows_kept: ListRowsDep,
    staging_storage: StagingStorageDep,
    list_store: ListStoreDep,
    sources: SourcesDep,
    audit: AuditDep,
    handling_scheme: HandlingSchemeDep,
    ontology: OntologyDep,
    dry_run: bool = False,
    replace_own_draft: str | None = None,
) -> ReleaseImportPlan:
    """*Import* and `ospreyflow release import [--dry-run]`: the bundle read and checked, every
    pipeline judged by the canvas's own gates, then (unless `dry_run`) everything written as a
    draft. A bundle that cannot be read, or any refusal, writes nothing (422, the plan's words).
    Nothing goes live: *Make live* stays a person's audited step. An in-progress draft of the
    model is never replaced silently: another person's is refused, naming them, and the importer's
    own only with `replace_own_draft` (CARRIES row 90)."""
    try:
        bundle = bundle_from_text(body.files)
    except BundleRefused as refused:
        return JSONResponse(  # type: ignore[return-value]
            status_code=422,
            content=ReleaseImportPlan(dry_run=dry_run, refused=refused.problems).model_dump(
                mode="json"
            ),
        )
    # The confirmation names the version of the importer's own draft it was given for (the
    # orchestrator's review, item 5); anything else (a bare `true`, say) confirms nothing.
    confirmed = (
        int(replace_own_draft) if replace_own_draft and replace_own_draft.isdigit() else None
    )
    planned = await plan_import(
        bundle,
        dataset_id=dataset_id,
        principal=principal,
        dry_run=dry_run,
        models=models,
        rows_kept=rows_kept,
        staging_storage=staging_storage,
        list_store=list_store,
        sources=sources,
        scheme=handling_scheme,
        ontology=ontology,
        replace_own_draft=confirmed,
    )
    plan = planned.plan
    if plan.refused:
        return JSONResponse(  # type: ignore[return-value]
            status_code=422, content=plan.model_dump(mode="json")
        )
    if dry_run:
        await audit.record(
            principal=principal,
            action="plan_dataset_release_import",
            resolved_query={"dataset_id": dataset_id, "release": bundle.manifest.metadata.name},
            result_cardinality=len(plan.items),
        )
        return plan
    try:
        made, replaced = await apply_import(
            bundle,
            planned,
            dataset_id=dataset_id,
            principal=principal,
            models=models,
            recipes=studio_recipes,
            rows_kept=rows_kept,
            replace_own_draft=confirmed,
        )
    except DraftHeld as held:
        refused_now = plan.model_copy(
            update={"items": [], "refused": held.problems, "replaces_own_draft": held.own}
        )
        return JSONResponse(  # type: ignore[return-value]
            status_code=422, content=refused_now.model_dump(mode="json")
        )
    await audit.record(
        principal=principal,
        action="import_dataset_release",
        resolved_query={
            "dataset_id": dataset_id,
            "release": bundle.manifest.metadata.name,
            "version": bundle.manifest.metadata.version,
            "pipelines": made,
            # CARRIES row 90: the importer's own in-progress draft replaced, by their confirmation,
            # as the write found it (the lane review, item 3).
            "replaced_own_draft": replaced,
        },
        result_cardinality=len(plan.items),
    )
    return plan


@app.get(
    "/v1/datasets/{dataset_id}/sources",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))],
)
async def list_dataset_sources(
    dataset_id: StudioDatasetDep, principal: SourceAuthorDep, sources: SourcesDep, audit: AuditDep
) -> list[SourceTable]:
    found = await sources.list_for(dataset_id)
    await audit.record(
        principal=principal,
        action="list_dataset_sources",
        resolved_query={"dataset_id": dataset_id},
        result_cardinality=len(found),
    )
    return found


@app.post(
    "/v1/datasets/{dataset_id}/sources",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES)), NoLoadingAComposite],
)
async def register_dataset_source(
    dataset_id: StudioDatasetDep,
    body: RegisterSourceInput,
    request: Request,
    principal: SourceAuthorDep,
    sources: SourcesDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
) -> SourceTable:
    """Registers a source once (ADR-140 decision 7). A Files source must be a file the dataset's
    listing offers: the same confinement Connect has (`ingest_sources.list_source_files`), so a path
    outside the ingest root, or another dataset's folder, is refused in the same words whether or
    not it exists. A SQL, API or JSON source (Amendment 13) is read once now, into its own file in
    the dataset's folder, and registered on that file only if the read succeeds."""
    try:
        connection = await sources.connection(body.connection_id)
    except UnknownConnectionError as exc:
        raise _no_such_connection() from exc
    if connection.kind != "files":
        try:
            refuse_unbound(connection, dataset_id)
        except ConnectorRefused as refused:
            # Answered as an unknown connection is: another dataset's connection is not
            # confirmed to exist (Amendment 13 decision 1; the orchestrator's review of
            # Amendment 15, item 12).
            await _audit_refused_read(audit, principal, dataset_id, body.connection_id, refused)
            raise _no_such_connection() from refused
        made = await _register_through_connection(
            dataset_id, body, connection, request, principal, sources, studio_recipes, audit
        )
        await audit.record(
            principal=principal,
            action="register_dataset_source",
            resolved_query={"dataset_id": dataset_id, "source_id": made.id},
            result_cardinality=1,
        )
        return made
    offered = {f.source_location for f in list_source_files(datasets=[dataset_id]).files}
    if body.location not in offered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "source_not_offered",
                "detail": "That file is not one of this dataset's files in the ingest folder. "
                "Choose it from the dataset's files, or upload it.",
            },
        )
    await _refuse_a_keyless_refresh(studio_recipes, dataset_id, body.location, body.refresh)
    try:
        made = await sources.register(dataset_id, body, principal)
    except UnknownConnectionError as exc:
        raise _no_such_connection() from exc
    except SourceAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "source_already_registered",
                "detail": "This dataset already has a source reading that file.",
            },
        ) from exc
    await audit.record(
        principal=principal,
        action="register_dataset_source",
        resolved_query={"dataset_id": dataset_id, "source_id": made.id},
        result_cardinality=1,
    )
    return made


def get_connector_readers(request: Request) -> Readers:
    """What a connector read reaches (ADR-140 Amendment 13): the real database driver, the network
    through the egress allow-list; a test sets fixtures that refuse what the real ones refuse."""
    readers = getattr(request.app.state, "connector_readers", None)
    return readers if readers is not None else Readers()


async def _audit_refused_read(
    audit: AuditWriter,
    principal: Principal,
    dataset_id: str,
    connection_id: str,
    refused: ConnectorRefused,
) -> None:
    """A refused connector read is audited, by ids and words alone: no server path."""
    await audit.record(
        principal=principal,
        action="connector_read_refused",
        resolved_query={"dataset_id": dataset_id, "connection_id": connection_id,
                        "why": str(refused)},
        result_cardinality=0,
    )  # fmt: skip


#: What a source author is told when a read through a connection is refused: fixed words, never
#: the connection's host, address, schemas or anything else of its settings (Amendment 13
#: decision 7; the orchestrator's review of Amendment 15, item 1). The refusal's own words are
#: audited, and an administrator, who may see the connection's settings, is given them.
READ_REFUSED_FOR_AUTHORS = (
    "The read through this connection was refused, and nothing was read. An administrator can see "
    "why: Test connection in Admin › Connections, or the audit log."
)


READ_OVER_CAP_FOR_AUTHORS = (
    "The read was refused whole: it holds more than one read may take (500,000 rows, 256 MiB, or "
    "1,000 pages or objects). Nothing was written, and nothing was cut short."
)


def _no_such_connection() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "not_found", "detail": "There is no such connection."},
    )


def _connector_refused(refused: ConnectorRefused, principal: Principal) -> HTTPException:
    """A refused connector read: its own words for an administrator, fixed words for anyone else.
    A read past a cap has its own type, `read_over_cap` (rule 2's typed refusal; L1.9), and words
    that say so, the caps being the deployment's, not the connection's settings."""
    administrator = Right.ADMINISTER_SYSTEM in rights_for(principal.roles)
    if isinstance(refused, ReadOverCap):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "read_over_cap",
                    "detail": str(refused) if administrator else READ_OVER_CAP_FOR_AUTHORS},
        )  # fmt: skip
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": "read_refused",
                "detail": str(refused) if administrator else READ_REFUSED_FOR_AUTHORS},
    )  # fmt: skip


async def _register_through_connection(
    dataset_id: str,
    body: RegisterSourceInput,
    connection: Connection,
    request: Request,
    principal: Principal,
    sources: SourceStore,
    studio_recipes: StudioRecipeStore,
    audit: AuditWriter,
) -> SourceTable:
    """A non-file source (ADR-140 Amendment 13): every check first, then one read into its own new
    file in the dataset's folder, then the source registered on that file; if registering is
    refused, the file goes too. A name whose file is already there is refused, never overwritten
    (the lane review of L1.6)."""
    if body.read is None or body.read.kind != connection.kind:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "read_needed",
                    "detail": f"A source on a {connection.kind} connection needs its own read."},
        )  # fmt: skip
    try:
        target = source_file(dataset_id, body.location)
    except ConnectorRefused as refused:
        # The source's own name, which the author wrote: nothing of the connection's in the words.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "source_name_refused", "detail": str(refused)},
        ) from refused
    registered = {s.location for s in await sources.list_for(dataset_id)}
    if target.exists() or str(target) in registered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "source_already_registered",
                    "detail": f"The dataset already has a file named {target.name}: give the "
                    "source another name."},
        )  # fmt: skip
    refresh = body.refresh
    if refresh.trigger == "watch":
        refresh = refresh.model_copy(update={"pattern": target.name})
    body = body.model_copy(update={"location": str(target), "refresh": refresh})
    await _refuse_a_keyless_refresh(studio_recipes, dataset_id, body.location, body.refresh)
    try:
        rows, _file = await read_into_file(
            body, connection, dataset_id=dataset_id, name=target.stem, cursor=None,
            readers=get_connector_readers(request),
        )  # fmt: skip
    except ConnectorRefused as refused:
        await _audit_refused_read(audit, principal, dataset_id, connection.id, refused)
        raise _connector_refused(refused, principal) from refused
    try:
        made = await sources.register(dataset_id, body, principal)
    except SourceAlreadyRegisteredError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "source_already_registered",
                    "detail": "This dataset already has a source reading that file."},
        ) from exc  # fmt: skip
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    await sources.set_cursor(made.id, rows.cursor)
    return made


@app.post(
    "/v1/datasets/{dataset_id}/sources/{source_id}/read",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES)), NoLoadingAComposite],
)
async def read_connector_source(
    dataset_id: StudioDatasetDep,
    source_id: str,
    request: Request,
    principal: SourceAuthorDep,
    sources: SourcesDep,
    audit: AuditDep,
) -> ConnectorRead:
    """*Refresh now* for a SQL, API or JSON source (ADR-140 Amendment 13): read again through its
    connection, landing whole as its file; an incremental SQL source reads only rows past its
    cursor, so the file holds only what is new, and its watch runs the source's pipelines on it."""
    source = await _source_of(sources, dataset_id, source_id)
    try:
        connection = await sources.connection(source.connection_id)
    except UnknownConnectionError as exc:
        raise _no_such_connection() from exc
    if connection.kind != "files":
        try:
            refuse_unbound(connection, dataset_id)
        except ConnectorRefused as refused:
            await _audit_refused_read(audit, principal, dataset_id, source.connection_id, refused)
            raise _no_such_connection() from refused
    if connection.kind == "files":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "read_refused",
                    "detail": "A file source is read from its file: upload the new file instead."},
        )  # fmt: skip
    cursor = await sources.cursor(source_id)
    try:
        rows, file = await read_into_file(
            source, connection, dataset_id=dataset_id, name=Path(source.location).stem,
            cursor=cursor, readers=get_connector_readers(request),
        )  # fmt: skip
    except ConnectorRefused as refused:
        await _audit_refused_read(audit, principal, dataset_id, source.connection_id, refused)
        raise _connector_refused(refused, principal) from refused
    await sources.set_cursor(source_id, rows.cursor)
    words = (
        f"{len(rows.rows)} rows read into {file.name}"
        if rows.rows
        else f"nothing new was found; {file.name} was left as it was"
    )
    await audit.record(
        principal=principal,
        action="read_connector_source",
        resolved_query={"dataset_id": dataset_id, "source_id": source_id},
        result_cardinality=len(rows.rows),
    )
    # The file's own name: the server's folders are never in a reply (the review of L1.6).
    return ConnectorRead(source_id=source_id, file=file.name, rows=len(rows.rows),
                         cursor=rows.cursor, words=words)  # fmt: skip


@app.get(
    "/v1/datasets/{dataset_id}/sources/{source_id}",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))],
)
async def get_dataset_source(
    dataset_id: StudioDatasetDep, source_id: str, principal: SourceAuthorDep, sources: SourcesDep
) -> SourceTable:
    return await _source_of(sources, dataset_id, source_id)


def source_as_draft(source: SourceTable, owning_unit: str) -> StudioRecipeDraft:
    """The source as the profiler's bridge reads a source (`studio_profile.profile_recipe_source`
    takes a draft): its location, connector, handling and legal basis, nothing else."""
    return StudioRecipeDraft(
        recipe_id=f"source:{source.id}",
        version=source.version,
        status=StudioRecipeStatus.DRAFT,
        label=source.name,
        connector_profile=source.connector_profile,
        source_location=source.location,
        handling=source.handling,
        legal_basis=source.legal_basis,
        owning_unit=owning_unit,
        created_by=source.created_by,
        created_at=source.created_at,
        ready_for_profile=False,
        dataset_id=source.dataset_id,
    )


@app.get(
    "/v1/datasets/{dataset_id}/sources/{source_id}/profile",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))],
)
async def get_dataset_source_profile(
    dataset_id: StudioDatasetDep,
    source_id: str,
    principal: SourceAuthorDep,
    sources: SourcesDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> SourceProfile:
    """The source's profile, computed for this reader and never stored (`schemas.sources`): a sample
    value is shape-masked by its marking against this reader's clearance, as Profile is."""
    source = await _source_of(sources, dataset_id, source_id)
    draft = source_as_draft(source, principal.org_unit)
    profile = await profile_recipe_source(draft, principal, scheme)
    await audit.record(
        principal=principal,
        action="get_dataset_source_profile",
        resolved_query={"dataset_id": dataset_id, "source_id": source_id},
        result_cardinality=len(profile.columns),
    )
    return profile


@app.get(
    "/v1/datasets/{dataset_id}/sources/{source_id}/lineage",
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))],
)
async def get_dataset_source_lineage(
    dataset_id: StudioDatasetDep,
    source_id: str,
    principal: SourceAuthorDep,
    sources: SourcesDep,
    studio_recipes: StudioRecipesDep,
) -> list[SourceLineage]:
    """The pipelines of the dataset that read the source."""
    source = await _source_of(sources, dataset_id, source_id)
    return [
        SourceLineage(
            recipe_id=r.recipe_id, label=r.label, version=r.version, status=r.status.value
        )
        for r in await studio_recipes.using_source(dataset_id, source.location)
    ]


@app.patch(
    "/v1/datasets/{dataset_id}/sources/{source_id}/governance",
    dependencies=[
        Depends(require_right(Right.EDIT_PIPELINES)),
        # The answer is the whole source, its default marking included, so the edit needs what
        # reading it needs (rule 4; the orchestrator's review of the carries step, item 2).
        Depends(require_right(Right.ADD_INGEST_FILES)),
        NoLoadingAComposite,
    ],
)
async def edit_dataset_source_governance(
    dataset_id: StudioDatasetDep,
    source_id: str,
    body: SourceGovernanceInput,
    principal: SourceAuthorDep,
    sources: SourcesDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
) -> GovernanceEdited:
    """Edits a source's marking, units, legal basis or refresh: a new version of the source,
    audited with the old and the new. Every deployed pipeline reading it then needs attention, its
    scheduled and watched runs blocked until it is deployed again under the new governance
    (ADR-140 Amendment 4, the owner's ruling)."""
    before = await _source_of(sources, dataset_id, source_id)
    if body.refresh is not None:
        await _refuse_a_keyless_refresh(studio_recipes, dataset_id, before.location, body.refresh)
    edited = await sources.edit_governance(dataset_id, source_id, body, principal)
    flagged = await studio_recipes.flag_for_source(
        dataset_id, edited.location, SOURCE_GOVERNANCE_CHANGED
    )
    followed = await studio_recipes.follow_source(
        dataset_id, edited.location, edited.handling, edited.legal_basis
    )
    await audit.record(
        principal=principal,
        action="edit_dataset_source_governance",
        resolved_query={
            "dataset_id": dataset_id,
            "source_id": source_id,
            "version": edited.version,
            "handling_before": before.handling,
            "handling_after": edited.handling,
            "legal_basis_before": before.legal_basis,
            "legal_basis_after": edited.legal_basis,
            "pipelines_needing_attention": len(flagged),
            "drafts_following": len(followed),
        },
        result_cardinality=1,
    )
    return GovernanceEdited(source=edited, needs_attention=flagged)


@app.put(
    "/v1/datasets/{dataset_id}/sources/{source_id}/default-marking",
    dependencies=[
        Depends(require_right(Right.PUBLISH_PIPELINES)),
        # The answer is the whole source, so the write needs what reading it needs (rule 4; the
        # lane review, item 2): Add ingest files and the source author's Edit pipelines.
        Depends(require_right(Right.ADD_INGEST_FILES)),
        Depends(require_studio_role(StudioRole.SOURCE_AUTHOR)),
        NoLoadingAComposite,
    ],
)
async def set_dataset_source_default_marking(
    dataset_id: StudioDatasetDep,
    source_id: str,
    body: SourceDefaultMarkingInput,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_APPROVER))],
    sources: SourcesDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    handling_scheme: HandlingSchemeDep,
) -> GovernanceEdited:
    """Studio › Sources › *Default marking* (ADR-140 Amendment 19): a source approver declares,
    changes or clears the classification an unmarked table of this source carries before a join.
    Refused in words (422 `default_marking_refused`) outside the scheme, above the approver's
    clearance or the deployment's highest marking, or below the source's own marking. Audited
    with who, when, from and to; a new version of the source, so each deployed pipeline reading
    it needs attention, as after any governance edit (ADR-140 Amendment 4)."""
    before = await _source_of(sources, dataset_id, source_id)
    marking = body.default_marking.strip() if body.default_marking else None
    problems = default_marking_problems(
        before, marking, principal, handling_scheme, DeploymentCeiling.from_env(handling_scheme)
    )
    if problems:
        return JSONResponse(  # type: ignore[return-value]
            status_code=422, content={"error": "default_marking_refused", "problems": problems}
        )
    if marking == before.default_marking:
        # No change writes nothing: no version, audit, flag or draft following (the orchestrator's
        # review, item 4).
        return GovernanceEdited(source=before, needs_attention=[])
    previous, edited = await sources.set_default_marking(dataset_id, source_id, marking, principal)
    flagged = await studio_recipes.flag_for_source(
        dataset_id, edited.location, SOURCE_GOVERNANCE_CHANGED
    )
    # Each draft reading it is tested again (the lane review, item 7): its handling is unchanged,
    # so following only clears its Test, as after a governance edit.
    followed = await studio_recipes.follow_source(
        dataset_id, edited.location, edited.handling, edited.legal_basis
    )
    await audit.record(
        principal=principal,
        action="set_dataset_source_default_marking",
        resolved_query={
            "dataset_id": dataset_id,
            "source_id": source_id,
            "version": edited.version,
            # What this write replaced, as the store's update read it under the row's lock.
            "default_marking_before": previous,
            "default_marking_after": edited.default_marking,
            "set_at": edited.default_marking_set_at.isoformat()
            if edited.default_marking_set_at
            else None,
            "pipelines_needing_attention": len(flagged),
            "drafts_following": len(followed),
        },
        result_cardinality=1,
    )
    return GovernanceEdited(source=edited, needs_attention=flagged)


async def _set_source_refresh_paused(
    dataset_id: str,
    source_id: str,
    principal: Principal,
    sources: SourceStore,
    audit: AuditWriter,
    *,
    reason: str | None,
) -> SourceTable:
    source = await _source_of(sources, dataset_id, source_id)
    await sources.set_refresh_paused(source.id, paused=reason is not None, reason=reason)
    await audit.record(
        principal=principal,
        action="pause_source_refresh" if reason is not None else "resume_source_refresh",
        resolved_query={"dataset_id": dataset_id, "source_id": source.id},
        result_cardinality=1,
    )
    return await _source_of(sources, dataset_id, source_id)


@app.post(
    "/v1/datasets/{dataset_id}/sources/{source_id}/refresh/pause",
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES)), NoLoadingAComposite],
)
async def pause_source_refresh(
    dataset_id: StudioDatasetDep,
    source_id: str,
    principal: SourceAuthorDep,
    sources: SourcesDep,
    audit: AuditDep,
    body: PauseRefreshInput | None = None,
) -> SourceTable:
    """ADR-110 Amendment 13: a source's refresh paused on its page, with why in words; not an edit
    (no new version, the owner kept, no pipeline needing attention), as a schedule's pause is not.
    Its waiting files wait; *Resume* below."""
    reason = (body.reason or "").strip() if body is not None else ""
    return await _set_source_refresh_paused(
        dataset_id, source_id, principal, sources, audit,
        reason=reason or f"paused by {principal.id}",
    )  # fmt: skip


@app.post(
    "/v1/datasets/{dataset_id}/sources/{source_id}/refresh/resume",
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES)), NoLoadingAComposite],
)
async def resume_source_refresh(
    dataset_id: StudioDatasetDep,
    source_id: str,
    principal: SourceAuthorDep,
    sources: SourcesDep,
    audit: AuditDep,
) -> SourceTable:
    """Resumes a paused refresh, chapter 9's included: its next tick takes the files waiting."""
    return await _set_source_refresh_paused(
        dataset_id, source_id, principal, sources, audit, reason=None
    )


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


@app.get("/v1/grading-scheme")
async def get_grading_scheme_route(
    principal: PrincipalDep, grading: GradingSettingsDep
) -> GradingSchemeAnswer:
    """ADR-143 decision 11: the deployment's grading scheme and its parts' grades, for Admin's
    read-only display and a board's grade fields. Same treatment as `GET /v1/yardstick`: the
    deployment's own reference settings, not a disclosure of any record's content."""
    return grading.grades


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
    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES)), NoLoadingInACompositeCase],
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
    return with_default_classification(handling, scheme)


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES)), NoLoadingInACompositeCase],
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
    _refuse_a_file_not_offered(body.source_location, made_in(principal))
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


def _refuse_a_file_not_offered(location: str | None, dataset_id: str | None) -> None:
    """Connect's half of the save gate (the orchestrator's review of L1.4): a draft's file must be
    one of its dataset's files in the ingest folder (`studio_profile._confined`), refused in the
    words `register_dataset_source` refuses one in, whether or not the file exists."""
    if location and not offered_to(location, dataset_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "source_not_offered",
                "detail": "That file is not one of this dataset's files in the ingest folder. "
                "Choose it from the dataset's files, or upload it.",
            },
        )


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
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES)), NoLoadingInACompositeCase],
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
    _refuse_a_file_not_offered(body.source_location, recipe.dataset_id)
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


#: ADR-140 decision 3: an expert step changed without the right that writes one.
EXPERT_RIGHT_WORDS = (
    "This change adds, edits or removes an expert step (a SQL transform or a fuzzy match), which "
    "needs the right to write SQL transforms (write_sql_transforms), granted by an administrator. "
    "The pipeline's other steps can be edited without it."
)


async def _save_pipeline(
    recipe: StudioRecipeDraft,
    principal: Principal,
    body: PipelineGraph,
    *,
    studio_recipes: StudioRecipeStore,
    audit: AuditWriter,
    models: TargetModelStore | None,
    staging_storage: ObjectStorageConfig,
    list_store: ListStore | None,
    action: str,
) -> StudioRecipeDraft | JSONResponse:
    """The pipeline's save gate, one for the canvas's save and the YAML's (ADR-140 decision 3:
    "editable in expert mode with the same save and publish gates"): an expert step changed only by
    a holder of `write_sql_transforms` (403, in words), then the graph's rules, the sources' files
    and the staging gate (422 `pipeline_invalid`, every problem in words), and nothing stored."""
    if expert_steps_changed(pipeline_from_recipe(recipe), body) and (
        Right.WRITE_SQL_TRANSFORMS not in rights_for(principal.roles)
    ):
        return JSONResponse(
            status_code=403,
            content={
                "error": "right_required",
                "right": Right.WRITE_SQL_TRANSFORMS.value,
                "problems": [EXPERT_RIGHT_WORDS],
            },
        )
    problems = pipeline_rule_violations(body)
    problems.extend(sources_not_offered(body, recipe.dataset_id))
    problems.extend(
        p
        for p in staging_gate(
            body,
            references=await dataset_reference_lists(
                models, recipe.dataset_id, staging_storage, lists=list_store
            ),
            dataset_id=recipe.dataset_id,
            marked=draft_marked(recipe),
        )
        if p not in problems
    )
    if problems:
        return JSONResponse(
            status_code=422,
            content={"error": "pipeline_invalid", "problems": problems},
        )
    updated = await studio_recipes.update_pipeline(recipe.recipe_id, principal, pipeline=body)
    await audit.record(
        principal=principal,
        action=action,
        resolved_query={"recipe_id": recipe.recipe_id, "nodes": len(body.nodes)},
        result_cardinality=1,
    )
    return updated


@app.put(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/pipeline",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES)), NoLoadingInACompositeCase],
)
async def update_studio_recipe_pipeline(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    body: PipelineGraph,
    models: TargetModelsDep,
    staging_storage: StagingStorageDep,
    list_store: ListStoreDep,
) -> StudioRecipeDraft:
    """ADR-108 phase B: the pipeline's own save. The graph half of the save gate runs here —
    a violation answers 422 `pipeline_invalid` with every problem in words, and nothing is
    stored; the row-template half stays Map's own, unchanged. ADR-140 Amendment 12: its staging
    steps are judged here too, against its source nodes and the dataset's lists, in the words a
    drawer's Preview shows (`studio_staging.staging_gate`). ADR-140 decision 3 (phase 8): an expert
    step is added, edited or removed only by a holder of `write_sql_transforms`."""
    return await _save_pipeline(  # type: ignore[return-value]
        recipe,
        principal,
        body,
        studio_recipes=studio_recipes,
        audit=audit,
        models=models,
        staging_storage=staging_storage,
        list_store=list_store,
        action="update_studio_recipe_pipeline",
    )


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/pipeline/yaml",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def get_studio_recipe_pipeline_yaml(
    investigation: InvestigationViewerDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    audit: AuditDep,
) -> PipelineYaml:
    """*Show YAML* (ADR-140 decision 3): the pipeline as YAML, its nodes with their own settings
    (an expert step's SQL and fuzzy settings among them) and its lines. The draft's settings, never
    a row of a source."""
    await audit.record(
        principal=principal,
        action="read_studio_recipe_pipeline_yaml",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )
    return PipelineYaml(text=pipeline_yaml(pipeline_from_recipe(recipe)))


@app.put(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/pipeline/yaml",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES)), NoLoadingInACompositeCase],
)
async def update_studio_recipe_pipeline_yaml(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_AUTHOR))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    body: PipelineYaml,
    models: TargetModelsDep,
    staging_storage: StagingStorageDep,
    list_store: ListStoreDep,
) -> StudioRecipeDraft:
    """Expert mode's YAML edit (ADR-140 decision 3): the text read as a pipeline (`yaml.safe_load`,
    never run), refused in words if it is not one, then saved through the canvas's own gates
    (`_save_pipeline`)."""
    graph, problems = pipeline_from_yaml(body.text)
    if graph is None:
        return JSONResponse(  # type: ignore[return-value]
            status_code=422, content={"error": "pipeline_invalid", "problems": problems}
        )
    return await _save_pipeline(  # type: ignore[return-value]
        recipe,
        principal,
        graph,
        studio_recipes=studio_recipes,
        audit=audit,
        models=models,
        staging_storage=staging_storage,
        list_store=list_store,
        action="update_studio_recipe_pipeline_yaml",
    )


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/sql-check",
    dependencies=[Depends(require_right(Right.WRITE_SQL_TRANSFORMS))],
)
async def check_studio_recipe_sql(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    audit: AuditDep,
    body: SqlCheckInput,
) -> SqlCheck:
    """A SQL step's drawer's *Check SQL* (ADR-140 decision 12): the sandbox's gate on the step's
    SELECT, in its words, before it is saved: one SELECT, its inputs and nothing else, no file or
    network function, its `_ref` columns carried. Nothing runs over a row; the drawer's live sample
    (`…/staging-preview`) shows what it gives."""
    check = sql_check(body.pipeline, body.step, marked=draft_marked(recipe))
    await audit.record(
        principal=principal,
        action="check_studio_recipe_sql",
        resolved_query={"recipe_id": recipe.recipe_id, "step": body.step},
        result_cardinality=len(check.problems),
    )
    return check


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
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES)), NoLoadingInACompositeCase],
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
        # A Map save may hold a half-built template; Verify and publish judge it complete
        # (ADR-127 Amendment 38).
        complete=False,
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
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/staging-preview",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def preview_studio_recipe_staging(
    investigation: InvestigationViewerDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
    models: TargetModelsDep,
    staging_storage: StagingStorageDep,
    body: StagingPreviewInput,
    list_store: ListStoreDep,
    sources: SourcesDep,
) -> StagingPreview:
    """A staging step's drawer's live sample (ADR-140 Amendment 12, Q4 (a)): the steps up to one,
    over the first ten rows of each source, read as Map's sample is read (`edit_pipelines`, the
    viewer's level, the person's own principal, masked where they may not view a row), with the
    save gate's refusals for the pipeline the drawer holds, in its own words. It writes nothing:
    no staged Parquet, no raw rows, no draft. ADR-112 Amendment 8: an expert step the saved pipeline
    does not hold, or holds otherwise, is run only for a holder of `write_sql_transforms` (the lane
    review of L1.5, item 4: the sample runs the request's steps, so it would otherwise run any
    SELECT an editor wrote); the saved pipeline's own expert steps run for any editor."""
    if expert_steps_changed(pipeline_from_recipe(recipe), body.pipeline) and (
        Right.WRITE_SQL_TRANSFORMS not in rights_for(principal.roles)
    ):
        return JSONResponse(  # type: ignore[return-value]
            status_code=403,
            content={
                "error": "right_required",
                "right": Right.WRITE_SQL_TRANSFORMS.value,
                "problems": [EXPERT_RIGHT_WORDS],
            },
        )
    preview = await asyncio.to_thread(
        preview_staging,
        recipe,
        body,
        principal=principal,
        scheme=scheme,
        references=await dataset_reference_lists(
            models, recipe.dataset_id, staging_storage, lists=list_store
        ),
        storage=staging_storage,
        declared=await declared_markings(sources, recipe.dataset_id, scheme),
    )
    await audit.record(
        principal=principal,
        action="preview_studio_recipe_staging",
        resolved_query={"recipe_id": recipe.recipe_id, "step": body.step},
        result_cardinality=len(preview.rows),
    )
    return preview


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


async def _studio_dry_run(
    *,
    investigation: Investigation,
    recipe: StudioRecipeDraft,
    principal: Principal,
    scheme: HandlingScheme,
    graph: GraphPort,
    ontology: OntologySchema,
    recipe_runs: RecipeRunStore,
    typology_rules: TypologyRuleStore,
    analytics: AnalyticsPort,
    principal_resolver: PrincipalResolver,
    patterns_store: PatternStore,
    hotlists_store: HotlistStore,
    screening_lists: ScreeningListStore,
    compute: ComputePort,
    repo_root: Path,
    influencers_store: InfluencerStore | None,
    models: TargetModelStore,
    staging_storage: ObjectStorageConfig,
    list_store: ListStore | None = None,
    sources: SourceStore | None = None,
) -> tuple[VerifyReport, list[Any]]:
    """The dry run Test and Preview share (§5; ADR-140 decision 14): the report, and the files it
    read with their hashes. It writes nothing; what Test records afterwards is Test's alone."""
    # ADR-127 decision 5: the dry run counts the rows the case already kept as the run would count
    # them, by the draft's own `deduplicate`, asking the store of loaded rows (this case's keys
    # only) and writing nothing.
    # ADR-133 decision 6, stage (d): the pipeline's checks on load judge the sample as at its
    # load, each as its author, through a gate whose alert store, quarantine and signature set
    # refuse every call — Verify writes nothing.
    gate = await _rule_gate(
        investigation.id, loader=principal, graph=graph, analytics=analytics, scheme=scheme,
        typology_rules=typology_rules, principal_resolver=principal_resolver,
        screening=screening_lists, compute=compute, patterns=patterns_store,
        hotlists=hotlists_store, ontology=ontology, recipe_id=recipe.recipe_id,
        influencers=influencers_store, **READ_ONLY,  # type: ignore[arg-type]
    )  # fmt: skip

    async def judge_checks(
        written: Sequence[NodeWrite | EdgeWrite], shown: Mapping[str, Node]
    ) -> tuple[list[WouldRaise], list[CheckNotJudged], int]:
        return await would_raise(gate, written, shown)

    # Build order step 30: Verify reads the files a run of this recipe reads (a pipeline's source
    # node may name its own), and records each with the hash of its bytes, which *Run now* is held
    # to. Hashed before the read, so a file changed during Verify reads as changed at the run.
    locations = files_a_run_reads(recipe, repo_root=repo_root)
    checked = [
        await asyncio.to_thread(identify, location, recipe.dataset_id) for location in locations
    ]
    report = await run_verify(
        recipe,
        principal,
        scheme,
        graph,
        ontology,
        row_keys=recipe_runs,
        investigation_id=investigation.id,
        checks=judge_checks,
        locations=locations,
        staging=StagedTestInputs(
            references=await dataset_reference_lists(
                models, recipe.dataset_id, staging_storage, lists=list_store
            ),
            storage=staging_storage,
            # ADR-140 Amendment 19: Test reads the sources' declared default markings as the run.
            declared=await declared_markings(sources, recipe.dataset_id, scheme),
        ),
    )
    return report, checked


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
    typology_rules: TypologyRulesDep,
    analytics: AnalyticsDep,
    principal_resolver: PrincipalResolverDep,
    patterns_store: PatternsStoreDep,
    hotlists_store: HotlistsStoreDep,
    screening_lists: ScreeningListsDep,
    compute: ComputeDep,
    repo_root: RecipesRepoRootDep,
    models: TargetModelsDep,
    staging_storage: StagingStorageDep,
    influencers_store: OptionalStrengthInfluencersDep = None,
    list_store: ListStoreDep = None,  # type: ignore[assignment]
    sources: SourcesDep = None,  # type: ignore[assignment]
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
    report, checked = await _studio_dry_run(
        investigation=investigation, recipe=recipe, principal=principal, scheme=scheme, graph=graph,
        ontology=ontology, recipe_runs=recipe_runs, typology_rules=typology_rules,
        analytics=analytics, principal_resolver=principal_resolver, patterns_store=patterns_store,
        hotlists_store=hotlists_store, screening_lists=screening_lists, compute=compute,
        repo_root=repo_root, influencers_store=influencers_store, models=models,
        staging_storage=staging_storage, list_store=list_store, sources=sources,
    )  # fmt: skip
    # §5: "Verify must pass before publish" — recorded here, against a
    # *completed* run (rejections included, per §5's own "a run with
    # rejections can be published"), so `publish` below can gate on this
    # flag alone rather than re-running the dry run itself.
    await studio_recipes.mark_verified(
        recipe.recipe_id, recipe.version, now=datetime.now(UTC), sources=checked
    )
    await audit.record(
        principal=principal,
        action="verify_studio_recipe",
        resolved_query={"recipe_id": recipe.recipe_id, "would_raise": len(report.would_raise)},
        result_cardinality=len(report.nodes) + len(report.edges),
    )
    return report


@app.post(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/preview-graph",
    dependencies=[Depends(require_right(Right.VERIFY_PIPELINES))],
)
async def preview_studio_recipe_graph(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    scheme: HandlingSchemeDep,
    graph: GraphDep,
    ontology: OntologyDep,
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    recipe_runs: RecipeRunsDep,
    typology_rules: TypologyRulesDep,
    analytics: AnalyticsDep,
    principal_resolver: PrincipalResolverDep,
    patterns_store: PatternsStoreDep,
    hotlists_store: HotlistsStoreDep,
    screening_lists: ScreeningListsDep,
    compute: ComputeDep,
    repo_root: RecipesRepoRootDep,
    models: TargetModelsDep,
    staging_storage: StagingStorageDep,
    influencers_store: OptionalStrengthInfluencersDep = None,
    list_store: ListStoreDep = None,  # type: ignore[assignment]
    sources: SourcesDep = None,  # type: ignore[assignment]
) -> VerifyReport:
    """Phase 6's *Preview* of a Map or Load step (ADR-140 decision 14; ADR-140 Amendment 8 point 2):
    the same dry run Test runs, under the same right and level and the person's own principal, but
    it **marks nothing**: the draft is not marked verified, no file is recorded for *Run now* to be
    held to, and the audit row is a Preview's, never a Test's. Deploy's gate is satisfied by Test
    alone (`test_studio_preview_routes.py`, shown red against `verify`, 7 November 2026)."""
    # `studio_recipes` is taken only so the route's dependencies match Test's; nothing is written.
    report, _ = await _studio_dry_run(
        investigation=investigation, recipe=recipe, principal=principal, scheme=scheme, graph=graph,
        ontology=ontology, recipe_runs=recipe_runs, typology_rules=typology_rules,
        analytics=analytics, principal_resolver=principal_resolver, patterns_store=patterns_store,
        hotlists_store=hotlists_store, screening_lists=screening_lists, compute=compute,
        repo_root=repo_root, influencers_store=influencers_store, models=models,
        staging_storage=staging_storage, list_store=list_store, sources=sources,
    )  # fmt: skip
    await audit.record(
        principal=principal,
        action="preview_studio_recipe_graph",
        investigation_id=investigation.id,
        resolved_query={"recipe_id": recipe.recipe_id, "would_raise": len(report.would_raise)},
        result_cardinality=len(report.nodes) + len(report.edges),
    )
    return report


# --- ingest studio: checks on load (ADR-133 decision 6, stage (d)) ------------------------------


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/checks",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES))],
)
async def read_load_checks(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    ontology: OntologyDep,
    audit: AuditDep,
) -> LoadChecksView:
    """The pipeline's "Checks on load" step: the case's and the deployment's load-time rules the
    engineer may attach, read within their reach, and what has been chosen."""
    rules = await typology_rules.list_for_case(investigation.id, principal)
    record = await typology_rules.load_checks(recipe.recipe_id)
    view = checks_view(recipe.recipe_id, rules, record, ontology)
    await audit.record(principal=principal, action="read_load_checks",
                       investigation_id=investigation.id,
                       resolved_query={"recipe_id": recipe.recipe_id},
                       result_cardinality=len(view.available))  # fmt: skip
    return view


@app.put(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/checks",
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES)), NoLoadingInACompositeCase],
)
async def set_load_checks(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    ontology: OntologyDep,
    audit: AuditDep,
    body: LoadChecksInput,
) -> LoadChecksView:
    """The engineer's choice: which offered rules apply to this pipeline and what a hit does here.
    It names rules, never carries one — engineers attach rules, they do not author analyst rules
    (decision 6). A rule not offered, or a hold on a rule that runs after commit, is refused in
    words. Audited."""
    rules = await typology_rules.list_for_case(investigation.id, principal)
    try:
        checks = check_choice(body.checks, rules)
    except ChecksRefused as refused:
        raise HTTPException(
            status_code=422, detail={"error": "checks_refused", "message": str(refused)}
        ) from refused
    record = await typology_rules.set_load_checks(recipe.recipe_id, checks, principal)
    await audit.record(principal=principal, action="load_checks_set",
                       investigation_id=investigation.id,
                       resolved_query={"recipe_id": recipe.recipe_id,
                                       "checks": [c.model_dump() for c in checks]},
                       result_cardinality=len(checks))  # fmt: skip
    return checks_view(recipe.recipe_id, rules, record, ontology)


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
    dependencies=[Depends(require_right(Right.PUBLISH_PIPELINES)), NoLoadingInACompositeCase],
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
    sources: SourcesDep,
    models: TargetModelsDep,
    staging_storage: StagingStorageDep,
    list_store: ListStoreDep,
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
        # ADR-140 Amendment 12: the steps are judged by the save gate before they are built into
        # the recipe and committed, never committed unjudged.
        unjudged = staging_gate(
            recipe.pipeline,
            references=await dataset_reference_lists(
                models, recipe.dataset_id, staging_storage, lists=list_store
            ),
            dataset_id=recipe.dataset_id,
            marked=draft_marked(recipe),
        )
        if unjudged:
            return JSONResponse(  # type: ignore[return-value]
                status_code=422, content={"error": "pipeline_invalid", "problems": unjudged}
            )
        unrunnable = pipeline_run_violations(recipe.pipeline)
        if unrunnable:
            return JSONResponse(  # type: ignore[return-value]
                status_code=422,
                content={"error": "pipeline_not_runnable", "problems": unrunnable},
            )
    # ADR-110 Amendment 6 point 2 (the owner's ruling): a refresh would run this pipeline again
    # over rows it has loaded, which only a deduplication key makes harmless.
    if recipe.deduplicate is None and recipe.dataset_id and recipe.source_location:
        refreshing = [
            s
            for s in await sources.list_for(recipe.dataset_id)
            if s.location == recipe.source_location and s.refresh.trigger != "manual"
        ]
        if refreshing:
            raise refresh_needs_a_key([recipe.label])
    # A draft Map has not been done on has nothing to load: refused in words, not by an `assert`
    # (a 500, found 31 October 2026 on the Prison Intelligence demo's reports recipe, which is
    # seeded unmapped for the presenter to map live).
    if recipe.row_template is None:
        return JSONResponse(  # type: ignore[return-value]
            status_code=422,
            content={
                "error": "recipe_not_mapped",
                "detail": "Map has not been done on this pipeline yet: map its fields to the "
                "domain model, run Test, then deploy.",
            },
        )
    # ADR-120 D10, Amendment 1: the pins come from the live ontology, for the packs the recipe
    # names and the packs whose types it writes.
    check_before_publish(recipe, ontology)
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
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES)), NoLoadingInACompositeCase],
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
    if (body.schedule_cron or body.schedule_watch) and await studio_recipes.external_owner(
        recipe.recipe_id
    ):
        # ADR-141 decision 11: a pipeline owned externally has its schedule in the orchestrator.
        raise HTTPException(
            status_code=409,
            detail="the pipeline is owned externally: its orchestrator runs it; nobody sets both",
        )
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
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES)), NoLoadingInACompositeCase],
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
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES)), NoLoadingInACompositeCase],
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
    dependencies=[Depends(require_right(Right.RUN_PIPELINES))],
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
    dependencies=[Depends(require_right(Right.EDIT_PIPELINES)), NoLoadingInACompositeCase],
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
    dependencies=[Depends(require_right(Right.RUN_PIPELINES)), NoLoadingInACompositeCase],
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
    studio_recipes: StudioRecipesDep,
    watch_reach: WatchReachDep,
    board_items: BoardItemsDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    influencers: OptionalStrengthInfluencersDep = None,
    models: TargetModelsDep = None,  # type: ignore[assignment]
    staging_storage: StagingStorageDep = None,  # type: ignore[assignment]
    list_store: ListStoreDep = None,  # type: ignore[assignment]
    sources: SourcesDep = None,  # type: ignore[assignment]
    rule_lists: RuleListsDep = None,  # type: ignore[assignment]
    rule_reach: RuleReachDep = None,  # type: ignore[assignment]
    run_quotas: RunQuotasDep = None,
) -> LoadReportView | PipelineRunReportView:
    """§8: "Loader: run a published recipe against a file at or below
    their own clearance" — `body.source_location`, when given, is that
    file; omitted, this repeats against the recipe's own recorded location
    (§6: "re-runnable... the deduplication key makes a re-run idempotent").

    **Run reads exactly the file Verify checked (§5, build order step 30).** When Verify recorded
    what it read for this version, the files this run would read are hashed first and must be
    those files, byte for byte; otherwise nothing is read into a store and the answer is a 409
    `source_changed_since_verify` saying what changed and asking for Verify again. A version Verify
    recorded nothing for (published before the rule, or by a seed) runs as before. Scheduled and
    watched runs do not come here: they read each new export by design (ADR-110).
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
    verified = await studio_recipes.verified_sources(recipe.recipe_id, recipe.version)
    if verified is not None:
        now = [
            await asyncio.to_thread(identify, location, recipe.dataset_id)
            for location in files_a_run_reads(
                recipe, repo_root=repo_root, source_location=body.source_location
            )
        ]
        changed = changed_since_verify(verified, now, asked=body.source_location)
        if changed is not None:
            raise SourceChangedSinceVerifyError(changed)
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
            influencers=influencers,
            target_models=models,
            staging_storage=staging_storage,
            list_store=list_store,
            sources=sources,
            rule_lists=rule_lists,
            rule_reach=rule_reach,
            watch_reach=watch_reach,
            board_items=board_items,
            datasets=datasets,
            investigations=investigations,
            run_quotas=run_quotas,
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
        scoped = await scope_to_case(
            owner, case, state.datasets, holds_a_level=holds_a_level_in(state.investigations)
        )
        # ADR-099 Amendment 15: a run is a load, so none in a case reading a composite, before
        # `run_recipe_as` writes anything; the executor says so in words.
        await refuse_in_a_composite_case()
        return scoped

    async def run(
        owner: Principal,
        recipe: StudioRecipeDraft,
        case: str,
        slot: datetime | None,
        source_file: WatchedFile | None = None,
        trigger: RunTrigger | None = None,
        refresh: RefreshRead | None = None,
    ) -> Any:
        return await run_recipe_as(
            RecipeRunDeps.from_state(state),
            principal=owner,
            recipe=recipe,
            investigation_id=case,
            source_location=source_file.location if source_file else None,
            trigger=trigger or ("watch" if source_file else "schedule" if slot else "manual"),
            slot=slot,
            source_file=source_file.identity if source_file else None,
            refresh=refresh,
        )

    async def watch_files(recipe: StudioRecipeDraft, now: datetime) -> list[WatchedFile]:
        # A folder listing and a stat per file: off the event loop.
        return await asyncio.to_thread(waiting_files, recipe, now=now)

    async def notify(owner_id: str, recipe: StudioRecipeDraft, words: str) -> None:
        await state.alerts_store.save(schedule_notice(owner_id, recipe, words, datetime.now(UTC)))

    async def case_for_dataset(owner: Principal, dataset_id: str) -> str | None:
        """ADR-110 Amendment 6 point 6: a case the owner is an Editor of that loads into the
        dataset (its first, the same reach as `scope_to_dataset`); the executor's own checks then
        run against it as against any case."""
        for case, level in await state.investigations.list_for(owner):
            if level.rank < AccessLevel.EDITOR.rank:
                continue
            ids = await state.datasets.ids_of_case(case.id)
            if ids and ids[0] == dataset_id:
                return str(case.id)
        return None

    return ScheduleExecutor(
        recipes=state.studio_recipes,
        runs=state.recipe_runs,
        valkey=state.valkey,
        scheme=state.handling_scheme,
        resolve_owner=_owner_with_custom_roles(
            application, state.principal_resolver.resolve_for_owner_detailed
        ),
        check_case=check_case,
        run=run,
        notify=notify,
        watch_files=watch_files,
        source_watches=StoredSourceWatches(state.sources, state.studio_recipes),
        case_for_dataset=case_for_dataset,
    )


@dataclass
class _MonitoringSchedules:
    """Both of ADR-133 stage (d)'s schedules on the one minute tick."""

    rules: RuleScheduleExecutor
    lists: ListRefreshExecutor
    #: ADR-140 Amendment 13: the Studio's deployment-wide lists, on the same minute.
    deployment_lists: DeploymentListScheduler | None = None
    #: ADR-146 decision 4 (G16): saved patterns on their own schedule.
    monitors: MonitorScheduleExecutor | None = None

    async def tick(self, now: datetime) -> None:
        await self.rules.tick(now)
        await self.lists.tick(now)
        if self.deployment_lists is not None:
            await self.deployment_lists.tick(now)
        if self.monitors is not None:
            await self.monitors.tick(now)


def _rule_schedule_executor(application: FastAPI) -> RuleScheduleExecutor:
    """Scheduled rules over the running Conduit's own stores, each slot judged as the rule's author
    resolved afresh, through the same gate a load uses (ADR-133 decision 1, stage (d))."""
    state = application.state

    async def check_case(author: Principal, case: str, level: AccessLevel) -> Principal:
        await state.investigations.get_authorized(case, author, need=level)
        return await scope_to_case(
            author, case, state.datasets, holds_a_level=holds_a_level_in(state.investigations)
        )

    async def judge(rule: TypologyRule, author: Principal, slot: datetime) -> int:
        async def as_author(owner_id: str) -> Principal | None:
            return author if owner_id == author.id else None

        gate = RuleGate(
            rules=[rule], investigation_id=rule.investigation_id, graph=state.graph,
            analytics=state.analytics, scheme=state.handling_scheme, alert_store=state.alerts_store,
            audit=state.audit, valkey=state.valkey, principal_for_owner=as_author, loader=author,
            screening=state.screening_lists, compute=state.compute, patterns=state.patterns_store,
            hotlists=state.hotlists_store, ontology=state.ontology,
            influencers=state.strength_influencers, rule_lists=_rule_lists_of(state),
            rule_reach=_rule_reach_from(state),
        )  # fmt: skip
        return await run_scheduled_rule(rule, author, gate, now=slot)

    async def judge_on_refresh(rule: TypologyRule, author: Principal, now: datetime) -> int:
        # ADR-146 decision 3: the same gate as a slot's, the rule judged as its list refreshes.
        async def as_author(owner_id: str) -> Principal | None:
            return author if owner_id == author.id else None

        # The author comes narrowed to the rule's declared dataset (`RuleScheduleExecutor.reach`).
        gate = RuleGate(
            rules=[rule], investigation_id=rule.investigation_id, graph=state.graph,
            analytics=state.analytics, scheme=state.handling_scheme, alert_store=state.alerts_store,
            audit=state.audit, valkey=state.valkey, principal_for_owner=as_author, loader=author,
            screening=state.screening_lists, compute=state.compute, patterns=state.patterns_store,
            hotlists=state.hotlists_store, ontology=state.ontology,
            influencers=state.strength_influencers, rule_lists=_rule_lists_of(state),
            rule_reach=_rule_reach_from(state),
        )  # fmt: skip
        return await run_on_list_refresh(rule, author, gate, now=now)

    async def reads_list(rule: TypologyRule, list_id: str, owner: str) -> bool:
        return await rule_editor.reads_the_list(
            rule, list_id, owner, datasets=state.datasets,
            models=getattr(state, "target_models", None),
            lists=getattr(state, "list_store", None), rows_kept=getattr(state, "list_rows", None),
        )  # fmt: skip

    return RuleScheduleExecutor(
        rules=state.typology_rules,
        valkey=state.valkey,
        resolve_owner=_owner_with_custom_roles(
            application, state.principal_resolver.resolve_for_owner_detailed
        ),
        check_case=check_case,
        judge=judge,
        judge_on_refresh=judge_on_refresh,
        reads_list=reads_list,
        # Amendment 6 point 11: every slot and refresh within the rule's declared dataset alone,
        # as a load and Test read it, never the author's whole case scope, its layer with it;
        # refused in words once the case no longer reads the dataset.
        reach=lambda rule: _rule_reach_from(state)(rule),
    )


def _list_schedule_executor(application: FastAPI) -> ListRefreshExecutor:
    """Screening lists' refresh schedules (ADR-133 Amendment 3 item 4), each slot run as the person
    who set it, through the one refresh and re-screening."""
    state = application.state

    async def refresh(list_name: str, owner: Principal, slot: datetime) -> ScreeningListUpdate:
        rescreen = Rescreener(
            rules=state.typology_rules, datasets=state.datasets, graph=state.graph,
            scheme=state.handling_scheme, alert_store=state.alerts_store, audit=state.audit,
            valkey=state.valkey, principal_for_owner=state.principal_resolver.resolve_for_owner,
            runner=owner,
        )  # fmt: skip
        update = await refresh_screening_list(
            list_name, store=state.screening_lists, rescreen=rescreen, trigger="schedule"
        )
        await state.audit.record(
            principal=owner, action="screening_list_refreshed", investigation_id=None,
            resolved_query={"list_name": list_name, "outcome": update.outcome,
                            "version": update.version, "alerts": update.alerts,
                            "trigger": "schedule", "slot": slot.isoformat(),
                            **await state.screening_lists.audit_marking(list_name)},
            result_cardinality=update.alerts,
        )  # fmt: skip
        return update

    return ListRefreshExecutor(
        lists=state.screening_lists,
        valkey=state.valkey,
        resolve_owner=_owner_with_custom_roles(
            application, state.principal_resolver.resolve_for_owner_detailed
        ),
        refresh=refresh,
        scheme=state.handling_scheme,
    )


def _deployment_list_scheduler(application: FastAPI) -> DeploymentListScheduler:
    """The Studio's deployment-wide lists' schedules (ADR-140 Amendment 13): each slot once, run as
    the person who set it, who must still be able to sign in and hold `load_screening_lists`."""
    state = application.state
    resolve = _owner_with_custom_roles(
        application, state.principal_resolver.resolve_for_owner_detailed
    )

    async def claim(key: str) -> bool:
        return bool(await reply(state.valkey.set(key, "1", nx=True, ex=7 * 86400)))

    async def may_run(owner_id: str) -> str | None:
        try:
            owner = await resolve(owner_id)
        except PrincipalRevoked:
            return f"the schedule's owner, {owner_id}, can no longer sign in"
        except Exception:  # noqa: BLE001 - said, not raised
            return f"OspreyFlow could not act as the schedule's owner, {owner_id}"
        if Right.LOAD_SCREENING_LISTS not in rights_for(owner.roles):
            return f"the schedule's owner, {owner_id}, no longer holds load_screening_lists"
        return None

    async def run(list_id: str, owner_id: str) -> ListImport:
        done = await import_list(
            list_id, store=state.list_store, rows_kept=state.list_rows, trigger="schedule"
        )
        await _rules_on_list_refresh(state, done, DEPLOYMENT_WIDE)
        # Audited as the person the schedule runs as, as ADR-133's scheduled refresh is.
        owner = await resolve(owner_id)
        await state.audit.record(
            principal=owner, action="deployment_list_refreshed", investigation_id=None,
            resolved_query={"list_id": list_id, "outcome": done.outcome, "version": done.version,
                            "trigger": "schedule"},
            result_cardinality=done.added + done.changed + done.delisted,
        )  # fmt: skip
        return done

    return DeploymentListScheduler(state.list_store, claim, may_run, run)


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
    analytics: AnalyticsDep,
) -> NeighbourhoodRisk:
    """*Neighbourhood risk* (ADR-109 phase E): the case's alerts within two hops, halved per hop,
    counted for ninety days — read as the reader, never stored."""
    risk = await risk_module.neighbourhood_risk(
        graph,
        compute,
        alerts_store,
        analytics,
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
    analytics: AnalyticsPort,
) -> ReportFigures:
    level = await investigations.effective_level(investigation.id, principal)
    return await reports_module.case_report(
        alerts=alerts_store,
        graph=graph,
        analytics=analytics,
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
    analytics: AnalyticsDep,
    weeks: Annotated[int, Query(ge=1, le=52)] = 12,
) -> ReportFigures:
    """The Reports view (ADR-111): the case's figures, every one counted as the reader (rule 3);
    held rows only for Editors and above; past its bound, `limit_exceeded` (rule 2)."""
    figures = await _case_report(
        investigation, principal, investigations=investigations, graph=graph,
        alerts_store=alerts_store, held_rows=held_rows, compute=compute, explore=explore,
        ontology=ontology, period_weeks=weeks, analytics=analytics,
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
    analytics: AnalyticsDep,
    weeks: Annotated[int, Query(ge=1, le=52)] = 12,
    feed_format: Annotated[Literal["json", "csv"], Query(alias="format")] = "json",
) -> ReportFigures | Response:
    """The reporting feed a dashboard pulls (ADR-111 decisions 6 to 8): the same figures as the
    Reports view, as JSON or CSV — figures only. Every read is audited and written to the export
    ledger as metadata (who, which case, when), since the figures leave the Glass."""
    figures = await _case_report(
        investigation, principal, investigations=investigations, graph=graph,
        alerts_store=alerts_store, held_rows=held_rows, compute=compute, explore=explore,
        ontology=ontology, period_weeks=weeks, analytics=analytics,
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
        # A board pulls the feed as its dashboard identity: the team view's *mine*, the reader's own
        # claims, stays in the Glass, here as in `feed_rows` (the orchestrator's review of L2.12).
        return JSONResponse(
            figures.model_dump(mode="json", exclude={"monitoring": {"team": {"__all__": {"mine"}}}})
        )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["section", "label", "typology", "week_start", "value"])
    writer.writerows(rows)
    return Response(content=buffer.getvalue(), media_type="text/csv; charset=utf-8")


@app.exception_handler(ReportLimitExceededError)
async def _report_limit_handler(request: Request, exc: ReportLimitExceededError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=exc.detail.model_dump())


async def require_queue_rows(principal: PrincipalDep) -> Principal:
    """ADR-146 Amendment 2 point 3: the queue's rows, each alert's title, words and id, only to a
    reader Rules and Monitoring is offered to and to the Reports Viewer (ADR-145 Amendment 4
    decision 10); anyone else holding the queue's read is refused them, before anything is read,
    and reads the counts (`read_alert_queue_counts`)."""
    if not reads_queue_rows(principal.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=queue_rows_refusal())
    return principal


@app.get(
    "/v1/investigations/{investigation_id}/alert-queue/counts",
    dependencies=[Depends(require_right(Right.READ_ALERT_QUEUE))],
)
async def read_alert_queue_counts(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    analytics: AnalyticsDep,
) -> AlertQueueCounts:
    """The case's queue as counts alone (ADR-146 Amendment 2 point 3): Home's figure for a reader
    of the queue whom the place is not offered to. Counted as the queue is, by the same read, so an
    alert any of whose evidence is hidden from the reader is not counted (rule 3)."""
    rows = await alert_queue.monitoring_queue(
        alerts_store, graph, analytics, investigation.id, principal,
        statuses=["open", "claimed", "closing"],
    )  # fmt: skip
    await audit.record(
        principal=principal,
        action="read_alert_queue_counts",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=len(rows),
    )
    by = Counter(r.alert.status for r in rows)
    return AlertQueueCounts(open=by["open"], claimed=by["claimed"], closing=by["closing"])


@app.get(
    "/v1/investigations/{investigation_id}/alert-queue",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_queue_rows),
    ],
)
async def read_alert_queue(
    request: Request,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    principal_names: PrincipalNamesDep,
    audit: AuditDep,
    analytics: AnalyticsDep,
    status_filter: Annotated[
        Literal["open", "claimed", "closing", "closed", "active", "all"], Query(alias="status")
    ] = "active",
    kind: Annotated[list[AlertKind] | None, Query()] = None,
    severity: Annotated[list[AlertSeverity] | None, Query()] = None,
    show: Annotated[QueueShow | None, Query()] = None,
    older_than_days: Annotated[int | None, Query(ge=1, le=3650)] = None,
) -> list[QueuedAlert]:
    """The one alert queue (ADR-133 decision 5 and stage (a)): the case's typology alerts (the case
    team's, ADR-109 ruling 3) and the hotlist and monitor alerts the reader owns or that are shared
    with their team, each with its kind, severity and audience. `active` is open, claimed and
    closing; `kind` and `severity` may each be given more than once. Who sees which alert is decided
    in the query; an alert any of whose nodes, links or transactions the reader cannot see is then
    left out, and not counted (rule 3; ADR-146 decision 10).
    """
    statuses = {
        "active": ["open", "claimed", "closing"],
        "all": None,
    }.get(status_filter, [status_filter])
    lead_of = await _leads_today(request, principal)
    rows = await alert_queue.monitoring_queue(
        alerts_store, graph, analytics, investigation.id, principal, statuses=statuses, kinds=kind,
        severities=severity, show=show, older_than_days=older_than_days, lead_of=lead_of,
    )  # fmt: skip
    await audit.record(
        principal=principal,
        action="read_alert_queue",
        investigation_id=investigation.id,
        resolved_query={"status": status_filter, "kind": kind, "severity": severity, "show": show,
                        "older_than_days": older_than_days},  # fmt: skip
        result_cardinality=len(rows),
    )
    rows = await _with_team_names(request, rows)
    # ADR-106 Amendment 1: each claimed row's assignee by name, asked for only the assignees of
    # the rows served (step 9e: "Claimed by" named an identity-provider id).
    assignees = sorted({r.alert.assignee for r in rows if r.alert.assignee})
    if not assignees:
        return rows
    names = await principal_names.display_names(assignees)
    return [
        r.model_copy(update={"assignee_name": names.get(r.alert.assignee)})
        if r.alert.assignee
        else r
        for r in rows
    ]


@app.get(
    "/v1/investigations/{investigation_id}/alert-assignees",
    dependencies=[
        Depends(require_right(Right.TRIAGE_ALERTS)),
        Depends(require_rules_place),
    ],
)
async def read_alert_assignees(
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    principal_names: PrincipalNamesDep,
) -> list[AlertAssignee]:
    """ADR-133 stage (a): whom an alert may be given to — the case's Editors and Authors by grant,
    by name. Read at Editor, by those who triage; a Viewer is not shown the case's member list.
    People only (build order step 15): never a seed's own principal or a service account."""
    ids = await _alert_assignee_ids(investigations, investigation.id, principal, principal_names)
    names = await principal_names.display_names(sorted(ids))
    return [AlertAssignee(id=i, name=names.get(i)) for i in sorted(ids)]


async def _alert_assignee_ids(
    investigations: InvestigationStore,
    investigation_id: str,
    principal: Principal,
    principal_names: PrincipalNameDirectory,
) -> set[str]:
    """The case's Editors and Authors, and the caller, that the identity provider holds as people:
    a grant held by a seed's own principal (the account that made the case) or by a service
    account is no one to give an alert to. A deployment with no directory cannot tell, and keeps
    them all."""
    grants = await investigations.list_grants(investigation_id)
    ids = {i for i, level in grants.items() if level.rank >= AccessLevel.EDITOR.rank}
    ids |= {principal.id}
    people = await principal_names.people(sorted(ids))
    return ids if people is None else ids & people


@app.get(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_rules_place),
    ],
)
async def explain_alert(
    request: Request,
    alert_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    analytics: AnalyticsDep,
    alerts_store: AlertsStoreDep,
    principal_names: PrincipalNamesDep,
    audit: AuditDep,
    hotlists_store: HotlistsStoreDep,
) -> AlertExplanation:
    """What fired the alert: its entities and node, the links and each transaction it cites; and,
    for a close waiting for a second person, who proposed it, and for a claimed alert, who holds
    it, by name (ADR-106: resolved for those ids, once the reader has been served the alert)."""
    explanation = await alert_queue.explain(
        alerts_store, graph, analytics, investigation.id, alert_id, principal
    )
    explanation = await _named_explanation(explanation, principal_names)
    explanation = await _with_lead_tools(request, explanation, principal)
    explanation = await with_what_fired_it(explanation, principal, hotlists_store)
    await audit.record(
        principal=principal,
        action="explain_alert",
        investigation_id=investigation.id,
        resolved_query={"alert_id": alert_id},
        result_cardinality=len(explanation.nodes),
    )
    return explanation


def _home_case_author(
    investigations: InvestigationStore, principal: Principal
) -> alert_queue.CloserCheck:
    """ADR-146 decision 7: whether the closer is an Author of the alert's own case, the home case
    a dataset alert was raised into, read as them in their own unit."""

    async def check(alert: Alert) -> bool:
        if alert.investigation_id is None:
            return False
        level = await investigations.effective_level(alert.investigation_id, principal)
        return level == AccessLevel.AUTHOR

    return check


def close_refusal(refused: alert_queue.CloseRefused) -> HTTPException:
    """A refused close in words, its code by its reason: a dataset alert closed by someone not an
    Author of its home case (ADR-146 decision 7) is `not_the_home_cases_author` wherever the close
    is decided; the proposer approving their own close (ADR-133 decision 7) is `own_change`."""
    code = (
        "not_the_home_cases_author"
        if isinstance(refused, alert_queue.NotTheHomeCasesAuthor)
        else "own_change"
    )
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail={"error": code, "message": str(refused)}
    )


async def _leads_today(request: Request, principal: Principal) -> set[str]:
    """The teams the reader acts as lead of today (ADR-146 Amendment 1): none where no custom-role
    store is attached."""
    roles = getattr(request.app.state, "custom_roles", None)
    if roles is None:
        return set()
    return await leads_today(roles, principal, datetime.now(UTC).date())


async def _team_names(request: Request, team_ids: Iterable[str]) -> dict[str, str]:
    roles = getattr(request.app.state, "custom_roles", None)
    names: dict[str, str] = {}
    if roles is None:
        return names
    today = datetime.now(UTC).date()
    for team_id in sorted(set(team_ids)):
        team = await roles.team(team_id, today)
        if team is not None:
            names[team_id] = team.display_name
    return names


async def _with_team_names(request: Request, rows: list[QueuedAlert]) -> list[QueuedAlert]:
    """A routed alert's team by its display name, for the rows served alone."""
    names = await _team_names(request, [r.alert.routed_team for r in rows if r.alert.routed_team])
    if not names:
        return rows
    return [
        r.model_copy(update={"team_name": names.get(r.alert.routed_team)})
        if r.alert.routed_team
        else r
        for r in rows
    ]


async def _with_lead_tools(
    request: Request, explanation: AlertExplanation, principal: Principal
) -> AlertExplanation:
    routed = explanation.alert.routed_team
    if routed is None:
        return explanation.model_copy(
            update={"suppressed": alert_queue.suppressed_today(explanation.alert)}
        )
    names = await _team_names(request, [routed])
    return explanation.model_copy(
        update={
            "team": routed,
            "team_name": names.get(routed),
            "suppressed": alert_queue.suppressed_today(explanation.alert),
            "lead": routed in await _leads_today(request, principal),
        }
    )


async def _named_explanation(
    explanation: AlertExplanation, principal_names: PrincipalNameDirectory
) -> AlertExplanation:
    """ADR-106 Amendment 1: the proposer and the assignee by name, asked for those ids alone, once
    the reader has been served the alert."""
    proposer = explanation.alert.close_proposed_by
    assignee = explanation.alert.assignee
    people = sorted({p for p in (proposer, assignee) if p})
    if not people:
        return explanation
    names = await principal_names.display_names(people)
    return explanation.model_copy(
        update={
            "close_proposed_by_name": names.get(proposer) if proposer else None,
            "assignee_name": names.get(assignee) if assignee else None,
        }
    )


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
    dependencies=[
        Depends(require_right(Right.TRIAGE_ALERTS)),
        Depends(require_rules_place),
    ],
)
async def claim_alert(
    alert_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    analytics: AnalyticsDep,
) -> Alert:
    alert = await alert_queue.claim(
        alerts_store, graph, analytics, investigation.id, alert_id, principal
    )
    await _triage_audit(audit, principal, investigation.id, "alert_claimed", alert)
    return alert


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/release",
    dependencies=[
        Depends(require_right(Right.TRIAGE_ALERTS)),
        Depends(require_rules_place),
    ],
)
async def release_alert(
    alert_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    analytics: AnalyticsDep,
) -> Alert:
    alert = await alert_queue.release(
        alerts_store, graph, analytics, investigation.id, alert_id, principal
    )
    await _triage_audit(audit, principal, investigation.id, "alert_released", alert)
    return alert


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/disposition",
    dependencies=[
        Depends(require_right(Right.TRIAGE_ALERTS)),
        Depends(require_rules_place),
    ],
)
async def dispose_alert(
    alert_id: str,
    body: AlertDispositionInput,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    analytics: AnalyticsDep,
    working_set: WorkingSetDep,
    investigations: InvestigationsDep,
) -> Alert:
    """Closes the alert with its disposition and reason. A true positive confirms its node
    (rule 5's human confirmation); a false positive leaves it `inferred`. A dataset alert is closed
    by its home case's Authors alone (ADR-146 decision 7)."""
    try:
        alert = await alert_queue.dispose(
            alerts_store,
            graph,
            analytics,
            investigation.id,
            alert_id,
            principal,
            disposition=body.disposition,
            reason=body.reason,
            working_set=working_set,
            closer=_home_case_author(investigations, principal),
        )
    except alert_queue.CloseRefused as refused:
        raise close_refusal(refused) from refused
    action = "alert_close_proposed" if alert.status == "closing" else "alert_disposed"
    await _triage_audit(audit, principal, investigation.id, action, alert)
    return alert


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/approve-close",
    dependencies=[
        Depends(require_right(Right.TRIAGE_ALERTS)),
        Depends(require_rules_place),
    ],
)
async def approve_alert_close(
    alert_id: str,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    analytics: AnalyticsDep,
    working_set: WorkingSetDep,
    investigations: InvestigationsDep,
) -> Alert:
    """ADR-133 decision 7, stage (d): a second member approves a proposed close of a high-severity
    alert — never the member who proposed it."""
    try:
        alert = await alert_queue.approve_close(
            alerts_store,
            graph,
            analytics,
            investigation.id,
            alert_id,
            principal,
            working_set=working_set,
            closer=_home_case_author(investigations, principal),
        )
    except alert_queue.CloseRefused as refused:
        raise close_refusal(refused) from refused
    await _triage_audit(audit, principal, investigation.id, "alert_close_approved", alert)
    return alert


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/send-back",
    dependencies=[
        Depends(require_right(Right.TRIAGE_ALERTS)),
        Depends(require_rules_place),
    ],
)
async def send_back_alert_close(
    alert_id: str,
    body: RuleChangeRejection,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    analytics: AnalyticsDep,
) -> Alert:
    """A proposed close sent back to its proposer with the reason, or withdrawn by them."""
    alert = await alert_queue.send_back(
        alerts_store, graph, analytics, investigation.id, alert_id, principal
    )
    await audit.record(
        principal=principal,
        action="alert_close_sent_back",
        investigation_id=investigation.id,
        resolved_query={
            "alert_id": alert.id,
            "reason": body.reason,
            "node_ids": alert.referent_node_ids,
        },  # fmt: skip
        result_cardinality=1,
    )
    return alert


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/assign",
    dependencies=[
        Depends(require_right(Right.TRIAGE_ALERTS)),
        Depends(require_rules_place),
    ],
)
async def assign_alert(
    request: Request,
    alert_id: str,
    body: AlertAssignInput,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
    analytics: AnalyticsDep,
) -> Alert:
    """ADR-133 stage (a): give an open or claimed alert to an Editor or Author of the case who is a
    person (never a service account). Only a case (typology) alert is given to someone else; one
    shared with a team is claimed."""
    allowed = await _alert_assignee_ids(
        investigations, investigation.id, principal, principal_names
    )
    # ADR-146 Amendment 1: the lead's hand-off, to a member of a team they lead today.
    lead_of = await _leads_today(request, principal)
    members = {
        team: await _team_members_in_case(request, investigations, investigation.id, team)
        for team in lead_of
    }
    alert = await alert_queue.assign(
        alerts_store, graph, analytics, investigation.id, alert_id, principal,
        assignee=body.assignee, allowed=allowed, lead_of=lead_of, team_members=members,
    )  # fmt: skip
    handed_off = alert.routed_team is not None and alert.assignee != principal.id
    await _triage_audit(
        audit, principal, investigation.id,
        "alert_handed_off" if handed_off else "alert_assigned", alert,
    )  # fmt: skip
    return alert


async def _team_members_in_case(
    request: Request, investigations: InvestigationStore, investigation_id: str, team_id: str
) -> set[str]:
    """Whom a lead may give one of the team's alerts to: the team's enabled members (its role's
    holders, ADR-145 Amendment 5 point 5, never a service account) who hold the case at Editor or
    above, in their own name or through the team's own grant."""
    try:
        people = await get_identity_admin(request).list_people()
    except Exception:  # no directory: no one can be told apart, so no one is offered
        return set()
    role = f"{CUSTOM_ROLE_PREFIX}{team_id}"
    holders = {p.id for p in people if role in p.roles and p.enabled and not p.system_account}
    grants = await investigations.list_grants(investigation_id)
    team_level = grants.get(f"{TEAM_GRANT_PREFIX}{team_id}")
    if team_level is not None and team_level.rank >= AccessLevel.EDITOR.rank:
        return holders
    editor = AccessLevel.EDITOR.rank
    return {h for h in holders if (g := grants.get(h)) is not None and g.rank >= editor}


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/suppress",
    dependencies=[
        Depends(require_right(Right.TRIAGE_ALERTS)),
        Depends(require_rules_place),
    ],
)
async def suppress_alert(
    request: Request,
    alert_id: str,
    body: AlertSuppressInput,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    analytics: AnalyticsDep,
) -> Alert:
    """*Suppress until…* (ADR-146 Amendment 1): the team's lead, or its cover while the cover
    lasts, quiets one of the team's alerts until a day at most 90 days ahead, with a reason,
    audited. It stays open, in *All*, and counted open everywhere; it ends by itself on its day."""
    alert = await alert_queue.suppress(
        alerts_store, graph, analytics, investigation.id, alert_id, principal,
        until=body.until, reason=body.reason, lead_of=await _leads_today(request, principal),
    )  # fmt: skip
    await audit.record(
        principal=principal,
        action="alert_suppressed",
        investigation_id=investigation.id,
        resolved_query={"alert_id": alert.id, "until": body.until.isoformat(),
                        "reason": body.reason, "team": alert.routed_team},  # fmt: skip
        result_cardinality=1,
    )
    return alert


@app.exception_handler(alert_queue.SuppressRefused)
async def _suppress_refused_handler(
    request: Request, exc: alert_queue.SuppressRefused
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "suppress_refused", "detail": str(exc)})


@app.get(
    "/v1/investigations/{investigation_id}/alert-teams",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_rules_place),
    ],
)
async def read_alert_teams(
    request: Request,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    principal_names: PrincipalNamesDep,
) -> list[AlertTeam]:
    """The teams a rule's alerts may go to (ADR-146 decision 8), by name, and for each team the
    reader leads today the members of it who hold this case, whom they may give its alerts to
    (Amendment 1). Members are listed only to the team's own lead."""
    roles = getattr(request.app.state, "custom_roles", None)
    if roles is None:
        return []
    today = datetime.now(UTC).date()
    led = await leads_today(roles, principal, today)
    # Offered to whoever routes a rule's alerts (`deploy_rules`) and to a lead, for the members of
    # their own team; a reader who does neither is shown no team (the lane-reviewer's L2.10 note).
    held = rights_for(principal.roles)
    if Right.DEPLOY_RULES not in held and Right.AUTHOR_RULES not in held and not led:
        return []
    out: list[AlertTeam] = []
    for team in await roles.teams(today):
        in_case = sorted(
            await _team_members_in_case(request, investigations, investigation.id, team.role_id)
        )
        # Members are listed to the team's own lead alone; how many there are is said to anyone
        # routing a rule's alerts (ADR-146 decision 3: "seen by the 6 members of …").
        members = in_case if team.role_id in led else []
        out.append(AlertTeam(role_id=team.role_id, display_name=team.display_name,
                             lead=team.role_id in led, members=members,
                             member_count=len(in_case)))  # fmt: skip
    # ADR-106: the members served, by name, asked for those ids alone (the lane-reviewer's round on
    # the L2.10 fix: a lead's hand-off named people by their identity-provider ids).
    served = sorted({m for t in out for m in t.members})
    if served:
        names = await principal_names.display_names(served)
        out = [t.model_copy(update={"member_names": {m: names[m] for m in t.members if m in names}})
               for t in out]  # fmt: skip
    return out


@app.get(
    "/v1/investigations/{investigation_id}/alert-sources",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_rules_place),
    ],
)
async def read_alert_sources(
    request: Request,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    analytics: AnalyticsDep,
    alerts_store: AlertsStoreDep,
    typology_rules: TypologyRulesDep,
    hotlists_store: HotlistsStoreDep,
    monitors_store: MonitorsStoreDep,
    patterns_store: PatternsStoreDep,
    principal_names: PrincipalNamesDep,
    audit: AuditDep,
) -> AlertSources:
    """*What raises alerts* (ADR-146 decision 5): the case's rules and the reader's own watches in
    one list, each counted from the reader's own queue (rule 7), with the alerts suppressed today
    beside the rule or watch they quiet (Amendment 1)."""
    rules = await typology_rules.list_for_case(investigation.id, principal)
    hotlists = await hotlists_store.list_authorized(principal)
    monitors = await monitors_store.list_authorized(principal)
    patterns = {}
    for monitor in monitors:
        try:
            patterns[monitor.pattern_id] = await patterns_store.get_authorized(
                monitor.pattern_id, principal
            )
        except PatternNotFoundError:
            continue
    queue = await alert_queue.monitoring_queue(
        alerts_store, graph, analytics, investigation.id, principal
    )
    teams = await _team_names(
        request, [t for r in rules if (t := sentence_rules.routed_team_of(r)) is not None]
    )
    rows = alert_sources.inventory(rules, hotlists, monitors, patterns, queue, teams)
    # ADR-106 (and its Amendment 1's shape): the people these rows show, by name, asked only for
    # the ids of the rows served (the L2.10 review's item 3; rule 7).
    people = alert_sources.people_named(rows)
    names = await principal_names.display_names(people) if people else {}
    rows = alert_sources.named(rows, names)
    await audit.record(
        principal=principal,
        action="read_alert_sources",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=len(rows),
    )
    return AlertSources(sources=rows)


@app.post(
    "/v1/investigations/{investigation_id}/raised-alerts",
    status_code=201,
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def raise_an_alert(
    body: RaiseAlertInput,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    graph: GraphDep,
    alerts_store: AlertsStoreDep,
    datasets: DatasetsDep,
    audit: AuditDep,
) -> Alert:
    """*Raise an alert…* (ADR-146 decision 7, R4), from query results, a question's answer or the
    selection bar: to this case (its members see it) or to the case's dataset (raised into its
    home case, in the queue of every case reading it, closed by the home case's Authors). A case
    the raiser may not write is refused by the level check (Editor); a dataset the case does not
    read, a layer, or one with no home case in words; an item the raiser may not read as if it did
    not exist; and a dataset alert citing an item that is not the dataset's own (a drawn item)
    is refused at the route, not only in the form (409 `not_the_datasets_own`)."""
    home: str | None = None
    readable = True
    if body.to == "dataset" and body.dataset_id is not None:
        held = (await datasets.egress_of([body.dataset_id])).get(body.dataset_id)
        readable = held is not None and held.kind != "analyst_layer"
        found = await datasets.home_case_of(body.dataset_id) if readable else None
        home = found.investigation_id if found is not None else None
    try:
        alert = await raised_alerts.raise_alert(
            body, case_id=investigation.id, raiser=principal, graph=graph, store=alerts_store,
            home_case=home, dataset_is_readable=readable,
        )  # fmt: skip
    except raised_alerts.RaisedEvidenceNotFound:
        raise HTTPException(status_code=404, detail="not_found") from None
    except raised_alerts.RaiseRefused as refused:
        raise HTTPException(
            status_code=409, detail={"code": refused.code, "message": refused.message}
        ) from None
    await audit.record(
        principal=principal,
        action="alert_raised",
        investigation_id=investigation.id,
        resolved_query={
            "alert_id": alert.id, "to": body.to, "dataset_id": body.dataset_id,
            "severity": body.severity, "node_ids": alert.referent_node_ids,
        },  # fmt: skip
        result_cardinality=1,
    )
    return alert


@app.exception_handler(alert_queue.AssignmentRefused)
async def _assignment_refused_handler(
    request: Request, exc: alert_queue.AssignmentRefused
) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"error": "assignment_refused", "detail": str(exc)}
    )


@app.post(
    "/v1/investigations/{investigation_id}/alert-queue/{alert_id}/canvas",
    dependencies=[
        Depends(require_right(Right.TRIAGE_ALERTS)),
        Depends(require_rules_place),
    ],
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
    analytics: AnalyticsDep,
) -> StarterRunOutcome:
    """The alert's node, its entities and the links it cites onto the canvas — all, or past the
    working set's cap, none (`limit_exceeded`, rule 2). Editor, as it adds to the working set."""
    alert, nodes, edges = await alert_queue.canvas_elements(
        alerts_store, graph, analytics, investigation.id, alert_id, principal
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


# --- connection strength (ADR-139) -----------------------------------------------------------


async def _with_names(
    versions: list[InfluencerSetVersion], names: PrincipalNameDirectory
) -> list[InfluencerSetVersion]:
    """ADR-106: who proposed and who decided each version, by name, resolved for the versions
    served here and never stored."""
    ids = sorted({i for v in versions for i in (v.proposed_by, v.decided_by) if i})
    if not ids:
        return versions
    named = await names.display_names(ids)
    return [
        v.model_copy(
            update={
                "proposed_by_name": named.get(v.proposed_by),
                "decided_by_name": named.get(v.decided_by) if v.decided_by else None,
            }
        )
        for v in versions
    ]


@app.get(
    "/v1/strength-influencers",
    dependencies=[Depends(require_right(Right.MANAGE_STRENGTH_INFLUENCERS))],
)
async def list_strength_influencers_route(
    store: StrengthInfluencersDep,
    defaults: StrengthDefaultsDep,
    principal_names: PrincipalNamesDep,
) -> InfluencerSetHistory:
    """ADR-139 decision 3: every installation-wide version, newest first, with the one in force,
    and the weights file's defaults beneath them."""
    history = await store.history(defaults.influencers, defaults)
    return history.model_copy(
        update={"versions": await _with_names(history.versions, principal_names)}
    )


@app.post(
    "/v1/strength-influencers",
    status_code=201,
    dependencies=[Depends(require_right(Right.MANAGE_STRENGTH_INFLUENCERS))],
)
async def propose_strength_influencers_route(
    body: InfluencerSetInput,
    principal: PrincipalDep,
    store: StrengthInfluencersDep,
    ontology: OntologyDep,
    audit: AuditDep,
) -> InfluencerSetVersion:
    """A new installation-wide version, waiting for a second person: it changes no strength until
    approved (maker–checker, ADR-133 stage (d)'s pattern)."""
    check_influencers(body.influencers, ontology)
    version = await store.propose(
        body.influencers, body.words, principal, composition=body.composition,
        rarity_measure=body.rarity_measure,
    )  # fmt: skip
    await audit.record(
        principal=principal,
        action="strength_influencers_proposed",
        resolved_query={
            "version": version.version,
            "influencers": [i.id for i in body.influencers],
            "composition": body.composition,
            "rarity_measure": body.rarity_measure,
        },
        result_cardinality=len(body.influencers),
    )
    return version


@app.post(
    "/v1/strength-influencers/{version}/approve",
    dependencies=[Depends(require_right(Right.MANAGE_STRENGTH_INFLUENCERS))],
)
async def approve_strength_influencers_route(
    version: int,
    principal: PrincipalDep,
    store: StrengthInfluencersDep,
    audit: AuditDep,
) -> InfluencerSetVersion:
    """A second holder of the right puts the waiting version in force; its proposer cannot (403
    `own_change`)."""
    approved = await store.approve(version, principal)
    await audit.record(
        principal=principal,
        action="strength_influencers_approved",
        resolved_query={"version": version, "proposed_by": approved.proposed_by},
        result_cardinality=len(approved.influencers),
    )
    return approved


@app.post(
    "/v1/strength-influencers/{version}/send-back",
    dependencies=[Depends(require_right(Right.MANAGE_STRENGTH_INFLUENCERS))],
)
async def send_back_strength_influencers_route(
    version: int,
    body: InfluencerDecision,
    principal: PrincipalDep,
    store: StrengthInfluencersDep,
    audit: AuditDep,
) -> InfluencerSetVersion:
    """The waiting version is sent back with words (or withdrawn by its proposer); the set in force
    stays as it was."""
    sent = await store.send_back(version, body.words, principal)
    await audit.record(
        principal=principal,
        action="strength_influencers_sent_back",
        resolved_query={"version": version, "words": body.words},
        result_cardinality=0,
    )
    return sent


@app.get(
    "/v1/investigations/{investigation_id}/strength-influencers",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def case_strength_influencers_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    store: StrengthInfluencersDep,
    defaults: StrengthDefaultsDep,
    principal_names: PrincipalNamesDep,
    investigations: InvestigationsDep,
) -> CaseInfluencers:
    """ADR-139 decision 7: the case's legend (exactly the influencers in force, a case override
    marked), and its override, which its Author may change."""
    legend = await case_legend(
        investigation.id, store=store, defaults=defaults, names=principal_names,
        readable=principal.datasets,
    )  # fmt: skip
    case = await store.case_override(investigation.id)
    try:
        await investigations.get_authorized(investigation.id, principal, need=AccessLevel.AUTHOR)
        can_override = True
    except InsufficientAccessError:
        can_override = False
    override = case.override if case else None
    if override is not None and not can_override:
        # Amendment 2, ruling 3: a dataset trigger is told only by the datasets the reader reads.
        shown = as_the_reader_sees(
            [ActiveInfluencer(influencer=i, layer="case") for i in override.added],
            principal.datasets,
        )
        override = override.model_copy(update={"added": [a.influencer for a in shown]})
    return CaseInfluencers(legend=legend, override=override, can_override=can_override)


@app.put(
    "/v1/investigations/{investigation_id}/strength-influencers",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def set_case_strength_influencers_route(
    body: CaseInfluencersInput,
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    store: StrengthInfluencersDep,
    defaults: StrengthDefaultsDep,
    ontology: OntologyDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
    investigations: InvestigationsDep,
) -> CaseInfluencers:
    """ADR-139 decision 3: the case's Author adds influencers for this case or switches off
    installation-wide ones in it. No second person (it changes only this case); every version is
    kept and the change is audited."""
    check_influencers(body.added, ontology)
    saved = await store.set_case(investigation.id, body, principal)
    await audit.record(
        principal=principal,
        action="case_strength_influencers_set",
        investigation_id=investigation.id,
        resolved_query={
            "version": saved.version,
            "added": [i.id for i in body.added],
            "switched_off": body.switched_off,
            "composition": body.composition,
        },
        result_cardinality=len(body.added) + len(body.switched_off),
    )
    return await case_strength_influencers_route(
        investigation, principal, store, defaults, principal_names, investigations
    )


@app.post(
    "/v1/investigations/{investigation_id}/connection-strength",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def connection_strength_route(
    body: ConnectionStrengthRequest,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    graph: GraphDep,
    store: StrengthInfluencersDep,
    defaults: StrengthDefaultsDep,
) -> ConnectionStrengths:
    """ADR-139 decisions 5, 6 and 9: each working-set link's connection strength as the reader
    may see it, with what changed it, and the legend. Worked out in the graph adapter under the
    reader's access (rule 3); never a count from beyond the filter (rule 7)."""
    return await case_connection_strengths(
        investigation.id, body, working_set=working_set, graph=graph, principal=principal,
        store=store, defaults=defaults,
    )  # fmt: skip


@app.post(
    "/v1/investigations/{investigation_id}/rarity",
    dependencies=[Depends(require_right(Right.INVESTIGATE))],
)
async def rarity_route(
    body: RarityRequest,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    graph: GraphDep,
    defaults: StrengthDefaultsDep,
    store: OptionalStrengthInfluencersDep = None,
) -> RarityResult:
    """ADR-139 decisions 4 and 6: each working-set entity's highest shared-attribute rarity with
    another of its kind there, and each pair asked for with its shared attributes ranked. Scores
    and the reader's visible attributes only, never N or df (rule 7); past its cap,
    `limit_exceeded` (rule 2). Amendment 2: in the case's rarity measure, and under client parity
    each pair with its parity score."""
    return await case_rarity(
        investigation.id, body, working_set=working_set, graph=graph, principal=principal,
        defaults=defaults, store=store,
    )  # fmt: skip


# --- typology rules, their audit, and held rows (ADR-109 phase A) -------------


@app.get(
    "/v1/investigations/{investigation_id}/rules",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_rules_place),
    ],
)
async def list_typology_rules(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    principal_names: PrincipalNamesDep,
) -> list[TypologyRule]:
    """The case's rules, retired ones included — what watches this case's loads is the case
    team's to know (ruling 3). A change waiting for a second person names who proposed it
    (ADR-106: asked for only the proposers of the rules served here)."""
    rules = await typology_rules.list_for_case(investigation.id, principal)
    proposers = sorted({r.pending_by for r in rules if r.pending_by})
    if not proposers:
        return rules
    names = await principal_names.display_names(proposers)
    return [
        r.model_copy(update={"pending_by_name": names.get(r.pending_by)}) if r.pending_by else r
        for r in rules
    ]


@app.post(
    "/v1/investigations/{investigation_id}/rules",
    status_code=201,
    dependencies=[
        Depends(require_right(Right.DEPLOY_RULES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_author),
    ],
)
async def deploy_typology_rule(
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    patterns_store: PatternsStoreDep,
    audit: AuditDep,
    body: TypologyRuleInput,
) -> TypologyRule:
    """A case Author deploys a rule just for them, with no second approver (ADR-109 ruling 4;
    ADR-146 Amendment 6 decision 12: a rule for the case is the rule editor's, refused here as
    `use_the_rule_editor`); audited. A drawn pattern (phase D) must be one the Author saved: it is
    read as theirs at every evaluation. A sentence (ADR-133) is deployed through `…/rules/sentence`,
    which checks it against the ontology and its scope against the author's level and rights; it is
    refused here."""
    if body.params.typology == "sentence":
        raise ReleaseRefused("a rule written as a sentence is deployed from the sentence builder")
    if not body.just_me:
        # ADR-146 Amendment 6 decision 12: a case-wide rule goes live only drafted, tested and past
        # its second person, in the rule editor; this form keeps a rule just for its author.
        raise UseTheRuleEditor()
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
    dependencies=[
        Depends(require_right(Right.DEPLOY_RULES)),
        Depends(require_rules_place),
    ],
)
async def retire_typology_rule(
    rule_id: str,
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    audit: AuditDep,
) -> TypologyRule:
    """Retires a case rule at once. A whole-deployment rule's retirement waits for a second person
    with the administrator's right (ADR-133 decision 7), and needs that right to propose."""
    listed = await typology_rules.get_listed(rule_id, investigation.id, principal)
    if is_deployment_wide(listed):
        _require_administrator(principal)
    rule = await typology_rules.propose_retire(rule_id, investigation.id, principal)
    action = "rule_change_proposed" if rule.pending_action == "retire" else "rule_retired"
    await audit.record(
        principal=principal,
        action=action,
        investigation_id=investigation.id,
        resolved_query={"rule_id": rule.id, "change": "retire", "version": rule.pending_version},
        result_cardinality=1,
    )
    return rule


def _require_administrator(principal: Principal) -> None:
    """A whole-deployment rule is the administrator's (ADR-133 decision 1): deploying, changing,
    retiring, approving or rejecting one needs that right as well as the case's Author level."""
    if Right.ADMINISTER_SYSTEM not in rights_for(principal.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "right_required", "right": Right.ADMINISTER_SYSTEM.value},
        )


def _require_rule_author(principal: Principal) -> None:
    """ADR-133 decision 6: engineers attach rules; they do not author analyst rules. A rule written
    as a sentence is a saved pattern watching the case's data, so writing one needs the analyst's
    right to keep watches and saved-pattern monitors (ADR-112 L8) as well as `deploy_rules`."""
    if Right.KEEP_WATCHES not in rights_for(principal.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "right_required", "right": Right.KEEP_WATCHES.value},
        )


@app.post(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/approve",
    dependencies=[
        Depends(require_right(Right.DEPLOY_RULES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_author),
    ],
)
async def approve_rule_change(
    rule_id: str,
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    audit: AuditDep,
) -> TypologyRule:
    """ADR-133 decision 7, stage (d): a second person with the right approves the change waiting
    on a whole-deployment rule — its deployment, a new version, or its retirement. The person who
    proposed it cannot. ADR-146 decision 3: a tested draft waiting to go live under its dataset's
    second-person policy is approved by a holder of `deploy_rules` at the case's Author level,
    never by its author or whoever asked; only a whole-deployment rule's change needs the
    administrator."""
    if not await typology_rules.waits_to_go_live(rule_id, investigation.id, principal):
        _require_administrator(principal)
    try:
        rule = await typology_rules.approve(rule_id, investigation.id, principal)
    except OwnChangeRefused as refused:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "own_change",
                "message": f"{str(refused)[0].upper()}{str(refused)[1:]}.",
            },
        ) from refused
    await audit.record(
        principal=principal,
        action="rule_change_approved",
        investigation_id=investigation.id,
        resolved_query={"rule_id": rule.id, "version": rule.version, "status": rule.status},
        result_cardinality=1,
    )
    return rule


@app.post(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/reject",
    dependencies=[
        Depends(require_right(Right.DEPLOY_RULES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_author),
    ],
)
async def reject_rule_change(
    rule_id: str,
    body: RuleChangeRejection,
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    audit: AuditDep,
) -> TypologyRule:
    """The change waiting on a whole-deployment rule turned down, with the reason — or withdrawn
    by the person who proposed it. The rule stays as it was; a rejected deployment never runs. A
    tested draft waiting to go live (ADR-146 decision 3) is sent back to its draft by the same
    people who may approve it."""
    if not await typology_rules.waits_to_go_live(rule_id, investigation.id, principal):
        _require_administrator(principal)
    try:
        rule = await typology_rules.reject(rule_id, investigation.id, principal, body.reason)
    except OwnChangeRefused as refused:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "own_change",
                "message": f"{str(refused)[0].upper()}{str(refused)[1:]}.",
            },
        ) from refused
    await audit.record(
        principal=principal,
        action="rule_change_rejected",
        investigation_id=investigation.id,
        resolved_query={"rule_id": rule.id, "reason": body.reason},
        result_cardinality=1,
    )
    return rule


@app.post(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/change",
    dependencies=[
        Depends(require_right(Right.DEPLOY_RULES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_editor),
    ],
)
async def change_rule_sentence(
    rule_id: str,
    request: Request,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    typology_rules: TypologyRulesDep,
    patterns_store: PatternsStoreDep,
    ontology: OntologyDep,
    audit: AuditDep,
    body: SentenceRuleInput,
) -> TypologyRule:
    """A new version of a rule written as a sentence, checked as a deployment is. Its drawn
    pattern is saved as the person changing it, who the rule then runs as. A change to (or into) a
    whole-deployment rule waits for a second person (decision 7); any other applies at once. Every
    version is kept with who made it."""
    _require_rule_author(principal)
    current = await typology_rules.get_listed(rule_id, investigation.id, principal)
    if not isinstance(current.params, SentenceRuleParams):
        raise ReleaseRefused("only a rule written as a sentence is changed here")
    sentence = normalised(body.sentence)
    _refuse_outside_just_me(sentence, current)
    await _authorize_sentence_scope(sentence, investigation.id, principal, investigations, audit)
    await _refuse_an_unknown_team(sentence, request)
    if is_deployment_wide(current):
        _require_administrator(principal)
    spec = await _compiled_rule(body, sentence, principal, patterns_store, ontology)
    rule = await typology_rules.propose_change(rule_id, investigation.id, principal, spec)
    await audit.record(
        principal=principal,
        action="rule_change_proposed" if rule.pending_action == "change" else "rule_changed",
        investigation_id=investigation.id,
        resolved_query={"rule_id": rule.id, "rule": body.model_dump(mode="json")},
        result_cardinality=1,
    )
    return rule


@app.get(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/versions",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_rules_place),
    ],
)
async def read_rule_versions(
    rule_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    principal_names: PrincipalNamesDep,
    audit: AuditDep,
) -> list[RuleVersion]:
    """Every version of the rule, oldest first, with who proposed and who decided each, by name
    (decision 7: "rules keep their versions, and each change records who made it")."""
    versions = await typology_rules.versions(rule_id, investigation.id, principal)
    ids = {v.proposed_by for v in versions} | {v.decided_by for v in versions if v.decided_by}
    names = await principal_names.display_names(sorted(ids))
    named = [
        _only_the_testers_count(v, principal).model_copy(
            update={
                "proposed_by_name": names.get(v.proposed_by),
                "decided_by_name": names.get(v.decided_by or ""),
            }
        )  # fmt: skip
        for v in versions
    ]
    await audit.record(principal=principal, action="read_rule_versions",
                       investigation_id=investigation.id, resolved_query={"rule_id": rule_id},
                       result_cardinality=len(named))  # fmt: skip
    return named


@app.get(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/runs",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_rules_place),
    ],
)
async def read_rule_schedule(
    rule_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    audit: AuditDep,
) -> RuleScheduleView:
    """A scheduled rule's schedule in words, its next run (or why it will not run), and its latest
    runs (ADR-133 decision 1, stage (d)). A rule that runs as data loads is refused in words."""
    rule = await typology_rules.get_listed(rule_id, investigation.id, principal)
    if rule.trigger not in ("schedule", "list_refresh"):
        raise ReleaseRefused("this rule runs as data loads, not on a schedule")
    runs = await typology_rules.rule_runs(rule.id)
    runs = runs_for_reader(rule, runs, principal)
    await audit.record(principal=principal, action="read_rule_runs",
                       investigation_id=investigation.id, resolved_query={"rule_id": rule_id},
                       result_cardinality=len(runs))  # fmt: skip
    return schedule_view(rule, runs, now=datetime.now(UTC))


# --- a rule's files to the standards, BPMN 2.0 and DMN (ADR-146 decision 3, L2.11a) ------------


@app.get(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/export.{kind}",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_rules_place),
    ],
)
async def export_rule_standard_file(
    rule_id: str,
    kind: Literal["bpmn", "dmn"],
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    audit: AuditDep,
) -> Response:
    """The rule's `.bpmn` or `.dmn`, read as the rules list reads it (the reader's reach in its
    `WHERE`): a rule the reader may not see is the same 404 as a missing one. Audited."""
    rule = await typology_rules.get_listed(rule_id, investigation.id, principal)
    # ADR-146 Amendment 5: the files saved beside the version the reader reaches, byte for byte.
    kept = await typology_rules.rule_files(rule.id, rule.version)
    stored = None if kept is None else StoredRuleFiles(bpmn=kept.bpmn, dmn=kept.dmn)
    exported = export_rule_file(rule, kind, stored=stored)
    await audit.record(principal=principal, action="export_rule_file",
                       investigation_id=investigation.id,
                       resolved_query={"rule_id": rule_id, "file": kind},
                       result_cardinality=1)  # fmt: skip
    return exported


@app.post(
    "/v1/investigations/{investigation_id}/rules/import",
    dependencies=[
        Depends(require_right(Right.AUTHOR_RULES)),
        Depends(require_rules_place),
    ],
)
async def import_rule_standard_files(
    request: Request,
    investigation: InvestigationAuthorDep,
    datasets: DatasetsDep,
    ontology: OntologyDep,
) -> ImportedRule:
    """The rule a `.bpmn` and a `.dmn` hold (sent as their text, `RuleFilesUpload`) and the
    dataset it declares, for the editor to open as a draft; nothing is written. The body is capped
    as it is read. Anything OspreyFlow does not run is refused by name; a dataset that is not the
    case's own source or composite is `dataset_not_found`, whether or not it exists."""
    return await import_rule_files(
        request, investigation_id=investigation.id, datasets=datasets, ontology=ontology
    )


# --- rules written as sentences, and their preview (ADR-133 decisions 1 and 3, stage (b)) -------


@app.post(
    "/v1/investigations/{investigation_id}/rules/sentence/compile",
    dependencies=[
        Depends(require_right(Right.INVESTIGATE)),
        Depends(require_rules_place),
    ],
)
async def compile_rule_sentence(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    ontology: OntologyDep,
    body: RuleSentence,
) -> CompiledSentence:
    """The sentence checked against the ontology and compiled to its drawn pattern — its
    "advanced" view, to open in the query builder. Reads nothing from a store."""
    return compile_sentence(body, ontology)


@app.post(
    "/v1/investigations/{investigation_id}/rules/sentence/read",
    dependencies=[
        Depends(require_right(Right.INVESTIGATE)),
        Depends(require_rules_place),
    ],
)
async def read_rule_sentence(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    ontology: OntologyDep,
    body: SentenceReadRequest,
) -> RuleSentence:
    """A drawn pattern read back as the sentence, its other blanks kept; one a sentence cannot say
    is refused in words. Reads nothing from a store."""
    check_pattern_conditions(body.pattern, ontology)
    return sentence_of(body.pattern, body.sentence, ontology)


@app.post(
    "/v1/investigations/{investigation_id}/rules/preview",
    dependencies=[
        Depends(require_right(Right.INVESTIGATE)),
        Depends(require_rules_place),
    ],
)
async def preview_rule_sentence(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    analytics: AnalyticsDep,
    ontology: OntologyDep,
    hotlists_store: HotlistsStoreDep,
    screening_lists: ScreeningListsDep,
    audit: AuditDep,
    body: RulePreviewRequest,
    handling_scheme: HandlingSchemeDep,
    influencers_store: OptionalStrengthInfluencersDep = None,
) -> RulePreview:
    """Decision 3: "Preview on the last 90 days" — the rule run as the caller over the case's stored
    data, counted only over what they may see (rules 3 and 7). It raises no alert and writes no
    rule, pattern or graph element; the read is audited as every read is. Past the working-set
    limit it is refused with `limit_exceeded` (rule 2)."""
    sentence = body.sentence
    check_sentence(sentence, ontology)
    preview = await preview_sentence(
        sentence, principal,
        await _sentence_context(
            sentence, principal, investigation.id, graph=graph, analytics=analytics,
            ontology=ontology, hotlists_store=hotlists_store, screening_lists=screening_lists,
            influencers_store=influencers_store, scheme=handling_scheme,
        ),
    )  # fmt: skip
    await audit.record(
        principal=principal,
        action="rule_previewed",
        investigation_id=investigation.id,
        resolved_query={"sentence": sentence.model_dump(mode="json")},
        result_cardinality=preview.would_raise,
    )
    return preview


@app.post(
    "/v1/investigations/{investigation_id}/rules/sentence",
    status_code=201,
    dependencies=[
        Depends(require_right(Right.DEPLOY_RULES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_editor),
    ],
)
async def deploy_rule_sentence(
    request: Request,
    investigation: InvestigationEditorDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    typology_rules: TypologyRulesDep,
    patterns_store: PatternsStoreDep,
    ontology: OntologyDep,
    audit: AuditDep,
    body: SentenceRuleInput,
) -> TypologyRule:
    """A sentence deployed: checked against the ontology, its drawn pattern saved as the author's
    (the rule's "advanced" view, read afresh as them at each evaluation) and the rule deployed.
    "Just me" needs the case's Editor level; "this case" its Author level (ADR-109 ruling 4);
    "the whole deployment" its Author level and the administrator's right too, and waits for a
    second person's approval (ADR-133 decision 7). Writing one is an analyst's: it needs
    `keep_watches` (decision 6: engineers attach rules, they do not author analyst rules)."""
    _require_rule_author(principal)
    sentence = normalised(body.sentence)
    _refuse_outside_just_me(sentence)
    await _authorize_sentence_scope(sentence, investigation.id, principal, investigations, audit)
    await _refuse_an_unknown_team(sentence, request)
    spec = await _compiled_rule(body, sentence, principal, patterns_store, ontology)
    rule = await typology_rules.create(principal, investigation.id, spec)
    await audit.record(
        principal=principal,
        # ADR-133 decision 7, stage (d): a whole-deployment rule waits for a second person.
        action="rule_change_proposed" if rule.status == "pending" else "rule_deployed",
        investigation_id=investigation.id,
        resolved_query={"rule_id": rule.id, "rule": body.model_dump(mode="json")},
        result_cardinality=1,
    )
    return rule


# --- the rule editor: a declared dataset, draft, Test and Make live (ADR-146 decision 3, L2.11) ---


def _rule_files_renderer(request: Request) -> Callable[[SentenceRuleInput], RuleFiles]:
    """The rule's `.bpmn` and `.dmn` as rules-b's codec writes them (ADR-146 Amendment 5,
    `rule_standards.rule_files`), saved beside every version. A test app may set its own on
    `app.state.rule_files`."""
    set_on_app = getattr(request.app.state, "rule_files", None)
    if set_on_app is not None:
        return cast(Callable[[SentenceRuleInput], RuleFiles], set_on_app)

    def render(body: SentenceRuleInput) -> RuleFiles:
        if body.dataset_id is None:
            raise ValueError("a rule's files name its dataset; choose it first")
        files = rule_files(body, dataset_id=body.dataset_id)
        return RuleFiles(bpmn=files.bpmn, dmn=files.dmn)

    return render


async def _sentence_context(
    sentence: RuleSentence,
    principal: Principal,
    investigation_id: str,
    *,
    graph: GraphPort,
    analytics: AnalyticsPort,
    ontology: OntologySchema,
    hotlists_store: HotlistStore,
    screening_lists: ScreeningListStore,
    influencers_store: InfluencerStore | None,
    scheme: HandlingScheme,
    named_list: Callable[[str, str], Awaitable[list[Any]]] | None = None,
) -> SentenceContext:
    """What a sentence is judged with when it is previewed or tested, as `principal`; a list the
    sentence names is read through `named_list` (the rule's dataset's, ADR-146 decision 3), and a
    screening list only where `principal` is cleared for it, in the store's query (ADR-146
    Amendment 7 point 8; the orchestrator's review, item 1)."""
    relationship = sentence.relationship
    hotlisted = None
    if relationship is not None and relationship.kind == "on_hotlist":
        hotlisted = frozenset(
            h.identifier
            for h in await hotlists_store.list_authorized(principal)
            if h.status == "active"
        )
    entries: dict[str, list[Any]] = {}
    if relationship is not None and relationship.kind == "on_screening_list":
        if relationship.list_id is not None:
            if named_list is None:
                raise rule_editor.ListNotOffered(relationship.list_id)
            entries[sentence.subject] = await named_list(relationship.list_id, sentence.subject)
        else:
            entries[sentence.subject] = list(
                await screening_lists.entries(
                    sentence.subject, cleared=ListClearance.of(principal, scheme)
                )
            )
    # ADR-139 decision 8: a strength condition previews with the case's influencers in force.
    influencers, rarity_exclude, strength_settings = await strength_context(
        influencers_store, investigation_id
    )
    return SentenceContext(
        graph=graph,
        analytics=analytics,
        investigation_scope=investigation_id,
        ontology=ontology,
        hotlisted=hotlisted,
        screening_entries=entries,
        influencers=influencers,
        rarity_exclude_types=rarity_exclude,
        composition=strength_settings.composition,
        rarity_measure=strength_settings.rarity_measure,
    )


def _only_the_testers_count(version: RuleVersion, reader: Principal) -> RuleVersion:
    """Rule 7: *Test*'s count is taken as the person who tested, so only they are told it; anyone
    else reads that the version was tested, and when."""
    if version.would_raise is None or version.tested_by == reader.id:
        return version
    return version.model_copy(update={"would_raise": None})


@app.get(
    "/v1/investigations/{investigation_id}/rules/datasets",
    dependencies=[Depends(require_right(Right.AUTHOR_RULES)), Depends(require_rules_place)],
)
async def list_rule_datasets(
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    models: TargetModelsDep,
    lists: ListStoreDep,
    rows_kept: ListRowsDep,
    ontology: OntologyDep,
    audit: AuditDep,
) -> list[RuleDatasetOffer]:
    """ADR-146 decision 3: the datasets a new rule may be declared on, chosen first: the case's own
    sources and composites, each with its live model's types and links and the lists it may read,
    and whether *Make live* waits for a second person."""
    offers = await rule_editor.offered_datasets(
        investigation.id, ontology, datasets=datasets, models=models, lists=lists,
        rows_kept=rows_kept,
    )  # fmt: skip
    await audit.record(principal=principal, action="read_rule_datasets",
                       investigation_id=investigation.id, resolved_query={},
                       result_cardinality=len(offers))  # fmt: skip
    return offers


async def _save_rule_draft(
    request: Request,
    investigation_id: str,
    principal: Principal,
    body: SentenceRuleInput,
    *,
    rule_id: str | None,
    typology_rules: TypologyRuleStore,
    patterns_store: PatternStore,
    datasets: DatasetStore,
    models: TargetModelStore,
    ontology: OntologySchema,
    audit: AuditWriter,
) -> TypologyRule:
    if body.dataset_id is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "dataset_required",
                    "message": "Choose the dataset this rule watches first."},
        )  # fmt: skip
    dataset = await rule_editor.declared_dataset(investigation_id, body.dataset_id, datasets)
    if rule_id is not None:
        # Refused before anything is written, so a refused save leaves no drawn pattern behind
        # (the lane-reviewer's item 20); the store checks the same again under its lock.
        current = await typology_rules.get_listed(rule_id, investigation_id, principal)
        if current.status == "retired":
            raise RuleChangeRefused("a retired rule cannot be changed")
        if current.dataset_id != dataset.id:
            raise RuleDatasetFixed("a rule's dataset is chosen first and never changed")
        if current.pending_action is not None:
            raise RuleChangeRefused(
                "this rule is waiting for a second person's approval; send it back to change it"
            )
    sentence = normalised(body.sentence)
    if sentence.scope == "deployment":
        raise HTTPException(
            status_code=422,
            detail={"error": "sentence_refused", "message": (
                "A rule watches one dataset: a rule for the whole deployment is converted per "
                "dataset.")},
        )  # fmt: skip
    await _refuse_an_unknown_team(sentence, request)
    relationship = sentence.relationship
    if relationship is not None and relationship.kind == "on_screening_list":
        # ADR-146 decision 3: the one list it reads, chosen from those its dataset may read.
        if relationship.list_id is None:
            raise HTTPException(
                status_code=422,
                detail={"error": "list_required",
                        "message": "Choose the screening list the rule screens against."},
            )  # fmt: skip
        offered = await rule_editor.lists_of(
            dataset, datasets=datasets, models=models,
            lists=getattr(request.app.state, "list_store", None),
            rows_kept=getattr(request.app.state, "list_rows", None),
        )  # fmt: skip
        if relationship.list_id not in {o.id for o in offered if o.kind == "screening"}:
            raise rule_editor.ListNotOffered(relationship.list_id)
    model = await rule_editor.dataset_ontology(dataset, ontology, datasets=datasets, models=models)
    # The drawn pattern is saved in the rule's own dataset, which every run reads it within (the
    # lane-reviewer's item 3, at the save): never the case's first dataset.
    spec = await _compiled_rule(
        body, sentence, principal.model_copy(update={"datasets": [dataset.id]}), patterns_store,
        model,
    )  # fmt: skip
    try:
        files = _rule_files_renderer(request)(body.model_copy(update={"sentence": sentence}))
    except ValueError as refused:
        raise HTTPException(
            status_code=422,
            detail={"error": "rule_files_refused", "message": str(refused)},
        ) from refused
    rule = await typology_rules.save_draft(
        principal, investigation_id, spec, dataset_id=dataset.id, files=files, rule_id=rule_id
    )
    await audit.record(
        principal=principal, action="rule_draft_saved", investigation_id=investigation_id,
        resolved_query={"rule_id": rule.id, "dataset_id": dataset.id,
                        "rule": body.model_dump(mode="json")},
        result_cardinality=1,
    )  # fmt: skip
    return rule


@app.post(
    "/v1/investigations/{investigation_id}/rules/drafts",
    status_code=201,
    dependencies=[
        Depends(require_right(Right.AUTHOR_RULES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_author),
    ],
)
async def save_new_rule_draft(
    request: Request,
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    patterns_store: PatternsStoreDep,
    datasets: DatasetsDep,
    models: TargetModelsDep,
    ontology: OntologyDep,
    audit: AuditDep,
    body: SentenceRuleInput,
) -> TypologyRule:
    """ADR-146 decision 3: a new rule saved as a draft on its declared dataset, checked against that
    dataset's live model, its `.bpmn` and `.dmn` saved beside it. A draft never runs."""
    return await _save_rule_draft(
        request, investigation.id, principal, body, rule_id=None, typology_rules=typology_rules,
        patterns_store=patterns_store, datasets=datasets, models=models, ontology=ontology,
        audit=audit,
    )  # fmt: skip


@app.put(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/draft",
    dependencies=[
        Depends(require_right(Right.AUTHOR_RULES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_author),
    ],
)
async def save_rule_draft(
    rule_id: str,
    request: Request,
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    patterns_store: PatternsStoreDep,
    datasets: DatasetsDep,
    models: TargetModelsDep,
    ontology: OntologyDep,
    audit: AuditDep,
    body: SentenceRuleInput,
) -> TypologyRule:
    """The rule's one draft saved again; a live rule keeps running as it stands. Its dataset is
    never changed (409 `rule_dataset_fixed`)."""
    return await _save_rule_draft(
        request, investigation.id, principal, body, rule_id=rule_id,
        typology_rules=typology_rules, patterns_store=patterns_store, datasets=datasets,
        models=models, ontology=ontology, audit=audit,
    )  # fmt: skip


@app.get(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/draft",
    dependencies=[Depends(require_right(Right.READ_ALERT_QUEUE)), Depends(require_rules_place)],
)
async def read_rule_draft(
    rule_id: str,
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
) -> RuleVersion | None:
    """The rule's draft, if it has one; *Test*'s count only to the person who tested it."""
    draft = await typology_rules.draft(rule_id, investigation.id, principal)
    return None if draft is None else _only_the_testers_count(draft, principal)


@app.post(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/test",
    dependencies=[
        Depends(require_right(Right.AUTHOR_RULES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_author),
    ],
)
async def test_rule_draft(
    rule_id: str,
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    datasets: DatasetsDep,
    models: TargetModelsDep,
    graph: GraphDep,
    analytics: AnalyticsDep,
    ontology: OntologyDep,
    hotlists_store: HotlistsStoreDep,
    screening_lists: ScreeningListsDep,
    audit: AuditDep,
    handling_scheme: HandlingSchemeDep,
    influencers_store: OptionalStrengthInfluencersDep = None,
    rule_lists: RuleListsDep = None,  # type: ignore[assignment]
) -> RuleTestResult:
    """ADR-146 decision 3: *Test* runs the draft over its dataset's last 30 days, as the person
    testing, within that dataset alone, and says how many alerts it would have raised (rule 7: a
    count of what they may see). The result is kept on the draft it ran on. It raises no alert and
    writes no rule, pattern or graph element."""
    rule = await typology_rules.get_listed(rule_id, investigation.id, principal)
    draft = await typology_rules.draft(rule_id, investigation.id, principal)
    if draft is None or not isinstance(draft.params, SentenceRuleParams) or rule.dataset_id is None:
        raise RuleChangeRefused("this rule has no draft written as a sentence to test")
    dataset = await rule_editor.declared_dataset(investigation.id, rule.dataset_id, datasets)
    tester = principal.model_copy(update={"datasets": rule_editor.rule_reach(dataset)})
    model = await rule_editor.dataset_ontology(dataset, ontology, datasets=datasets, models=models)
    sentence = draft.params.sentence
    check_sentence(sentence, model)
    preview = await preview_sentence(
        sentence, tester,
        await _sentence_context(
            sentence, tester, investigation.id, graph=graph, analytics=analytics, ontology=model,
            hotlists_store=hotlists_store, screening_lists=screening_lists,
            influencers_store=influencers_store, scheme=handling_scheme,
            named_list=lambda list_id, subject: rule_lists(rule, list_id, subject),
        ),
        days=RULE_TEST_DAYS,
    )  # fmt: skip
    await typology_rules.record_test(
        rule_id, investigation.id, principal, version=draft.version, saved_at=draft.proposed_at,
        days=RULE_TEST_DAYS, would_raise=preview.would_raise,
    )  # fmt: skip
    # Rule 7: *Changes* says the draft was tested, never how many it found as the tester.
    await audit.record(
        principal=principal, action="rule_tested", investigation_id=investigation.id,
        resolved_query={"rule_id": rule_id, "version": draft.version, "days": RULE_TEST_DAYS},
        result_cardinality=0,
    )  # fmt: skip
    return RuleTestResult(
        rule_id=rule_id, version=draft.version, days=RULE_TEST_DAYS,
        would_raise=preview.would_raise, words=preview.words,
    )  # fmt: skip


@app.post(
    "/v1/investigations/{investigation_id}/rules/{rule_id}/make-live",
    dependencies=[
        Depends(require_right(Right.DEPLOY_RULES)),
        Depends(require_rules_place),
        Depends(refuse_rules_in_a_drawn_case_as_author),
    ],
)
async def make_rule_live(
    rule_id: str,
    investigation: InvestigationAuthorDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
    datasets: DatasetsDep,
    audit: AuditDep,
) -> TypologyRule:
    """ADR-146 decision 3: the tested draft goes live (409 `rule_untested` before its test), at
    once, or where the dataset's policy asks for a second person (ADR-145 A3, Amendment 6), on the
    approval of someone who neither wrote it nor asked."""
    rule = await typology_rules.get_listed(rule_id, investigation.id, principal)
    if rule.dataset_id is None:
        raise RuleChangeRefused("this rule names no dataset; it is converted before it changes")
    dataset = await rule_editor.declared_dataset(investigation.id, rule.dataset_id, datasets)
    second = await rule_editor.needs_second_person(dataset, datasets)
    made = await typology_rules.make_live(
        rule_id, investigation.id, principal, second_person=second
    )
    await audit.record(
        principal=principal,
        action="rule_make_live_proposed" if second else "rule_made_live",
        investigation_id=investigation.id,
        resolved_query={"rule_id": rule_id, "version": made.pending_version or made.version,
                        "dataset_id": dataset.id},
        result_cardinality=1,
    )  # fmt: skip
    return made


class UseTheRuleEditor(Exception):
    """ADR-146 Amendment 6: a rule for a case, or the whole deployment, is written in the rule
    editor, on its dataset, through draft, Test and Make live; the older form keeps rules just for
    their author (the lane-reviewer's L2.11 item 2: these routes passed every gate by)."""


@app.exception_handler(UseTheRuleEditor)
async def _use_the_rule_editor_handler(request: Request, exc: UseTheRuleEditor) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": "use_the_rule_editor",
            "message": "A rule for this case is written in the rule editor, on its dataset, and "
            "goes live once tested; this form keeps rules just for you.",
        },
    )


def _refuse_outside_just_me(sentence: RuleSentence, current: TypologyRule | None = None) -> None:
    if sentence.scope != "just_me":
        raise UseTheRuleEditor()
    if current is not None and isinstance(current.params, SentenceRuleParams) and (
        current.params.sentence.scope != "just_me"
    ):
        raise UseTheRuleEditor()


class UnknownTeamError(Exception):
    """A rule's *Alert goes to* names a team that does not exist (ADR-146 decision 8)."""


@app.exception_handler(UnknownTeamError)
async def _unknown_team_handler(request: Request, exc: UnknownTeamError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "code": "unknown_team",
            "message": "There is no such team: choose one of the teams listed.",
        },
    )


async def _refuse_an_unknown_team(sentence: RuleSentence, request: Request) -> None:
    """ADR-146 decision 8: a rule routed to a team names one that exists now; otherwise its
    alerts would reach nobody but the home case's Authors."""
    if sentence.team != "team" or sentence.team_id is None:
        return
    roles = getattr(request.app.state, "custom_roles", None)
    if roles is None or await roles.team(sentence.team_id, datetime.now(UTC).date()) is None:
        raise UnknownTeamError(sentence.team_id)


async def _authorize_sentence_scope(
    sentence: RuleSentence,
    investigation_id: str,
    principal: Principal,
    investigations: InvestigationStore,
    audit: AuditWriter,
) -> None:
    """ "Just me" needs the case's Editor level; "this case" its Author level (ADR-109 ruling 4);
    "the whole deployment" its Author level and the administrator's right too."""
    if sentence.scope != "just_me":
        await _authorize(investigation_id, principal, investigations, audit, AccessLevel.AUTHOR)
    if sentence.scope == "deployment":
        _require_administrator(principal)


async def _compiled_rule(
    body: SentenceRuleInput,
    sentence: RuleSentence,
    principal: Principal,
    patterns_store: PatternStore,
    ontology: OntologySchema,
) -> TypologyRuleInput:
    """The sentence checked against the ontology, its drawn pattern saved as `principal`'s (the
    rule's "advanced" view, read afresh as them at each evaluation), and the rule it deploys as."""
    pattern = compile_pattern(sentence, ontology)
    check_pattern_conditions(pattern, ontology)
    saved = await patterns_store.save(
        principal, pattern_id=None, name=f"Rule: {body.name}", definition=pattern
    )
    return TypologyRuleInput(
        name=body.name,
        params=SentenceRuleParams(
            pattern_id=saved.pattern_id, sentence=sentence, max_matches=body.max_matches
        ),
        trigger=sentence.runs,
        budget_ms=body.budget_ms,
    )


@app.get(
    "/v1/investigations/{investigation_id}/rules/audit",
    dependencies=[
        Depends(require_right(Right.READ_RULE_AUDIT)),
        Depends(require_rules_place),
    ],
)
async def read_rule_audit(
    investigation: InvestigationAccessManagerDep,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
    analytics: AnalyticsDep,
    alerts_store: AlertsStoreDep,
    screening_lists: OptionalScreeningListsDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> RuleAuditPage:
    """The rule audit inspection read (ruling 1): the case's Authors, and the deployment admin
    through ADR-052 §4's safety net. An entry naming a node, link or transaction the reader cannot
    see is withheld whole, from the page and the total (rule 3; `readable_rule_audit`)."""
    page = await readable_rule_audit(
        audit, graph, investigation.id, principal, analytics=analytics, alerts=alerts_store,
        lists=screening_lists, offset=offset, limit=limit,
    )  # fmt: skip
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
    dependencies=[
        Depends(require_right(Right.DECIDE_HELD_ROWS)),
        NoHeldRowsInACompositeCase,
    ],
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
    board_items: BoardItemsDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    influencers_store: OptionalStrengthInfluencersDep = None,
    rule_lists: RuleListsDep = None,  # type: ignore[assignment]
    rule_reach: RuleReachDep = None,  # type: ignore[assignment]
) -> LoadReportView:
    """A reviewer releases named held rows of one load: they are loaded now, under a new load
    id, with their provenance as it would have been. The case's rules judge them again, but a
    failing rule no longer holds them (ruling 1: the release is the human judgement). A load of its
    own, it runs the drawn watches as every load does (spec 01; L3.H2), and its answer says how
    many alerts they raised for the releaser alone."""
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
        recipe_id=recipe.recipe_id,
        influencers=influencers_store,
        rule_lists=rule_lists,
        rule_reach=rule_reach,
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
    report.drawn_watch_alerts = await run_drawn_watches_best_effort(
        node_ids=touched_node_ids(report), dataset_id=recipe.dataset_id, principal=principal,
        investigation_id=investigation.id, load_id=report.load_id, board_items=board_items,
        datasets=datasets, investigations=investigations, graph=graph, ontology=ontology,
        principal_resolver=principal_resolver, alerts_store=alerts_store, audit=audit,
    )  # fmt: skip
    return report_view(report, principal, handling_scheme)


@app.post(
    "/v1/investigations/{investigation_id}/held-rows/reject",
    dependencies=[
        Depends(require_right(Right.DECIDE_HELD_ROWS)),
        NoHeldRowsInACompositeCase,
    ],
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
    custom_roles: CustomRolesDep,
    audit: AuditDep,
) -> PersonAccount:
    """A person's roles, set whole — the built-in roles, `right:<name>` grants, custom roles
    (`role:<id>`) and the old role names; anything else is refused before the identity provider is
    asked (ADR-112 Amendment 1). ADR-145 Amendment 5: a custom role that does not exist is 422; a
    right newly given that the giver may not give (`giver_may_give`), a team's role given to a
    service account, or a change leaving no enabled person holding `manage_people`, is 409."""
    if refused := [r for r in body.roles if not allowed_role(r)]:
        raise UnknownRoleError(f"not a role or right this deployment grants: {', '.join(refused)}")
    current = await custom_roles.current_rights()
    if missing := [r for r in custom_role_ids(body.roles) if r not in current]:
        raise HTTPException(status_code=422, detail=f"no such custom role: {', '.join(missing)}")
    async with custom_roles.people_lock():
        people = await identity_admin.list_people()
        before = next((p for p in people if p.id == user_id), None)
        if before is None:
            raise HTTPException(status_code=404, detail={"error": "no_such_person"})
        try:
            _may_give(principal, body.roles, before.roles, current)
            all_teams = await custom_roles.teams(_today())
            teams = {t.role_id for t in all_teams}
            if before.system_account and teams & set(custom_role_ids(body.roles)):
                raise RoleRefused("service_account", "a service account is never a team member")
            # Only a member may be lead or cover (ADR-112 Amendment 5 decision 4): leaving the team
            # is refused while they are either, so a lead never outlives their membership.
            leaving = set(custom_role_ids(before.roles)) - set(custom_role_ids(body.roles))
            led = [t for t in all_teams if t.role_id in leaving and user_id in (t.lead, t.cover)]
            if led:
                raise RoleRefused(
                    "lead_leaves_team",
                    f"{before.name} is the lead or cover of {led[0].display_name}: hand the lead "
                    "over, or end the cover, before taking the team's role away",
                )
            after = [p.model_copy(update={"roles": list(body.roles)}) if p.id == user_id else p
                     for p in people]  # fmt: skip
            leaves_no_people_manager(after, current)
        except RoleRefused as error:
            raise _role_refused(error) from None
        person = await identity_admin.set_roles(user_id, body.roles)
    await audit.record(principal=principal, action="set_person_roles",
                       resolved_query={"user_id": user_id, "roles": person.roles},
                       result_cardinality=1)  # fmt: skip
    return person


# --- Roles, teams and Disable (ADR-145 decisions 6-7 and Amendment 5; ADR-112 Amendments 4-5) -----


def _role_refused(error: RoleRefused) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": error.error, "message": error.words, **error.detail},
    )


def _today() -> date:
    return datetime.now(UTC).date()


def _built_in_roles() -> list[BuiltInRole]:
    labels = BUILT_IN_ROLE_LABELS
    roles = [
        BuiltInRole(id=i, label=labels[i], rights=sorted(r, key=lambda x: x.value))
        for i, r in ROLE_RIGHTS.items()
    ]
    roles.append(
        BuiltInRole(
            id="super_user",
            label="Super user",
            rights=sorted(rights_for(SUPER_USER_PRESET), key=lambda x: x.value),
            gives=list(SUPER_USER_PRESET),
        )
    )
    return roles


async def _holders(people: Sequence[PersonAccount], role_id: str) -> list[PersonAccount]:
    return [p for p in people if f"{CUSTOM_ROLE_PREFIX}{role_id}" in p.roles]


@app.get("/v1/admin/roles", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))])
async def list_roles_route(
    custom_roles: CustomRolesDep, identity_admin: IdentityAdminDep
) -> RolesCatalogue:
    """The built-in roles and the *Super user* preset, never editable, and every custom role with
    its current version, how many hold it and its team (ADR-145 decision 7)."""
    people = await identity_admin.list_people()
    custom = await custom_roles.all(_today())
    listed = []
    for role in custom:
        holders = await _holders(people, role.id)
        team = role.team
        if team is not None:
            team = team.model_copy(
                update={"members": [TeamMember(id=p.id, name=p.name) for p in holders]}
            )
        listed.append(role.model_copy(update={"holders": len(holders), "team": team}))
    return RolesCatalogue(built_in=_built_in_roles(), custom=listed)


@app.post(
    "/v1/admin/roles",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def create_role_route(
    body: CustomRoleInput, principal: PrincipalDep, custom_roles: CustomRolesDep, audit: AuditDep
) -> CustomRole:
    """A custom role, v1: refused in words (409) for a name already used, no rights, a right that is
    not one, a forbidden pair, or a right the giver may not give (`role_refusal`)."""
    try:
        rights = role_refusal(
            body.name,
            body.rights,
            giver_rights=rights_for(principal.roles),
            names_taken=await custom_roles.names(),
        )
        role = await custom_roles.create(body.name, rights, by=principal.id)
    except RoleRefused as error:
        raise _role_refused(error) from None
    await audit.record(
        principal=principal,
        action="create_custom_role",
        result_cardinality=1,
        resolved_query={
            "role_id": role.id,
            "name": role.name,
            "version": 1,
            "rights": [r.value for r in role.rights],
        },
    )
    return role


@app.put("/v1/admin/roles/{role_id}", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))])
async def change_role_route(
    role_id: str,
    body: CustomRoleInput,
    principal: PrincipalDep,
    custom_roles: CustomRolesDep,
    identity_admin: IdentityAdminDep,
    audit: AuditDep,
) -> CustomRole:
    """A custom role's next version, with the same refusals as making one, and refused when it
    would leave no enabled person holding `manage_people` (ADR-145 Amendment 5)."""
    if await custom_roles.get(role_id, _today()) is None:
        raise HTTPException(status_code=404, detail={"error": "no_such_role"})
    async with custom_roles.people_lock():
        try:
            rights = role_refusal(
                body.name,
                body.rights,
                giver_rights=rights_for(principal.roles),
                names_taken=await custom_roles.names(except_id=role_id),
            )
            current = await custom_roles.current_rights()
            leaves_no_people_manager(
                await identity_admin.list_people(), {**current, role_id: frozenset(rights)}
            )
            before, after = await custom_roles.update(role_id, body.name, rights, by=principal.id)
        except RoleRefused as error:
            raise _role_refused(error) from None
    await audit.record(
        principal=principal,
        action="change_custom_role",
        result_cardinality=1,
        resolved_query={
            "role_id": role_id,
            "version": after.version,
            "before": {"name": before.name, "rights": [r.value for r in before.rights]},
            "after": {"name": after.name, "rights": [r.value for r in after.rights]},
        },
    )
    return after


@app.get(
    "/v1/admin/roles/{role_id}/versions",
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def role_versions_route(
    role_id: str, custom_roles: CustomRolesDep
) -> list[CustomRoleVersion]:
    versions = await custom_roles.versions(role_id)
    if not versions:
        raise HTTPException(status_code=404, detail={"error": "no_such_role"})
    return versions


@app.put(
    "/v1/admin/roles/{role_id}/team", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))]
)
async def make_team_route(
    role_id: str,
    body: TeamInput,
    principal: PrincipalDep,
    custom_roles: CustomRolesDep,
    identity_admin: IdentityAdminDep,
    audit: AuditDep,
) -> Team:
    """*Make this role a team* (ADR-112 Amendment 5 decision 3), or its name and mailbox changed.
    Refused while a service account holds the role: a service account is never a team member."""
    if await custom_roles.get(role_id, _today()) is None:
        raise HTTPException(status_code=404, detail={"error": "no_such_role"})
    holders = await _holders(await identity_admin.list_people(), role_id)
    if robots := [p.username for p in holders if p.system_account]:
        raise _role_refused(
            RoleRefused(
                "service_account",
                "a service account is never a team member, and "
                + ", ".join(robots)
                + " holds this role: take it away first",
            )
        )
    try:
        team = await custom_roles.make_team(role_id, body, _today())
    except RoleRefused as error:
        raise _role_refused(error) from None
    await audit.record(
        principal=principal,
        action="make_team",
        result_cardinality=1,
        resolved_query={
            "role_id": role_id,
            "display_name": team.display_name,
            "mailbox": team.mailbox,
        },
    )
    return team.model_copy(update={"members": [TeamMember(id=p.id, name=p.name) for p in holders]})


async def _member_of(
    identity_admin: PeopleDirectory, role_id: str, account: str
) -> PersonAccount:
    """`account` as one of the team's members, or a refusal in words: only a member, never a
    service account, may be lead or cover (ADR-112 Amendment 5 decisions 4 and 5)."""
    people = {p.id: p for p in await identity_admin.list_people()}
    person = people.get(account)
    if person is not None and person.system_account:
        raise _role_refused(
            RoleRefused(
                "service_account", "a service account owns nothing and is never a lead or cover"
            )
        )
    if person is None or f"{CUSTOM_ROLE_PREFIX}{role_id}" not in person.roles:
        raise _role_refused(
            RoleRefused("not_a_member", "only a member of the team may be its lead or cover")
        )
    if not person.enabled:
        raise _role_refused(RoleRefused("disabled", f"{person.name} is disabled"))
    return person


@app.put(
    "/v1/admin/teams/{role_id}/lead", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))]
)
async def set_team_lead_route(
    role_id: str,
    body: TeamLeadInput,
    principal: PrincipalDep,
    custom_roles: CustomRolesDep,
    identity_admin: IdentityAdminDep,
    audit: AuditDep,
) -> Team:
    """An administrator names a team's lead, or hands the role to another member (ADR-112
    Amendment 5 decision 4); a cover who becomes lead stops covering. Audited before and after."""
    if await custom_roles.team(role_id, _today()) is None:
        raise HTTPException(status_code=404, detail={"error": "no_such_team"})
    await _member_of(identity_admin, role_id, body.lead)
    before, after = await custom_roles.set_lead(role_id, body.lead, _today())
    await audit.record(
        principal=principal,
        action="set_team_lead",
        result_cardinality=1,
        resolved_query={"role_id": role_id, "before": before.lead, "after": after.lead},
    )
    return after


@app.put(
    "/v1/admin/teams/{role_id}/cover", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))]
)
async def set_team_cover_route(
    role_id: str,
    body: TeamCoverInput,
    principal: PrincipalDep,
    custom_roles: CustomRolesDep,
    identity_admin: IdentityAdminDep,
    audit: AuditDep,
) -> Team:
    """A cover until a date (inclusive), another member than the lead; after it the lead acts again
    with no action. `cover: null` ends it now. Audited before and after."""
    team = await custom_roles.team(role_id, _today())
    if team is None:
        raise HTTPException(status_code=404, detail={"error": "no_such_team"})
    if body.cover is not None:
        if body.until is None or body.until < _today():
            raise _role_refused(
                RoleRefused("cover_date", "a cover needs a last day, today or later")
            )
        if body.cover == team.lead:
            raise _role_refused(
                RoleRefused("cover_is_lead", "the lead cannot cover for themselves")
            )
        await _member_of(identity_admin, role_id, body.cover)
    before, after = await custom_roles.set_cover(role_id, body.cover, body.until, _today())
    await audit.record(
        principal=principal,
        action="set_team_cover",
        result_cardinality=1,
        resolved_query={
            "role_id": role_id,
            "before": [before.cover, str(before.cover_until or "")],
            "after": [after.cover, str(after.cover_until or "")],
        },
    )
    return after


@app.get("/v1/admin/people/rows", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))])
async def people_rows_route(
    principal: PrincipalDep,
    admin_people: AdminPeopleDep,
    identity_admin: IdentityAdminDep,
    audit: AuditDep,
) -> AdminPeopleRows:
    """Each person's case levels (R3), their own and through a team, and the cases with no Author
    (R1), of the administrator's own unit only (ADR-052): the safety net's reach, never wider."""
    people = await identity_admin.list_people()
    rows = await admin_people.rows(people, unit=principal.org_unit)
    await audit.record(
        principal=principal,
        action="read_people_rows",
        resolved_query={"unit": principal.org_unit},
        result_cardinality=len(rows.rows),
    )
    return rows


@app.put(
    "/v1/admin/cases/{case_id}/authors/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def name_an_author_route(
    case_id: str,
    account_id: str,
    request: Request,
    principal: PrincipalDep,
    principal_names: PrincipalNamesDep,
    investigations: InvestigationsDep,
    identity_admin: IdentityAdminDep,
    custom_roles: CustomRolesDep,
    audit: AuditDep,
) -> None:
    """*Name an Author* (ADR-145 decision 6, R1): a case of the administrator's own unit with no
    Author an enabled person holds, in their own name or through a team, is given one. Another
    unit's case, or one that does not exist, is 404 alike (ADR-052 §4's reach); a case that has an
    Author is 409 `has_an_author`, since naming one is then its Authors' to do; the person is held
    to who may hold a level (`_may_hold_a_level`). It reads nothing of the case. Audited as
    name_an_author."""
    try:
        case = await investigations.get_for_access_admin(case_id, principal)
    except InvestigationNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "case_not_found"}) from None
    people = {p.id: p for p in await identity_admin.list_people()}
    teams = {t.role_id for t in await custom_roles.teams(_today())}

    def answers(account: str) -> bool:
        if account.startswith(TEAM_GRANT_PREFIX):
            team = account[len(TEAM_GRANT_PREFIX) :]
            return team in teams and any(
                f"{CUSTOM_ROLE_PREFIX}{team}" in p.roles
                and p.enabled
                and not p.system_account
                and p.org_unit == case.owning_unit
                for p in people.values()
            )
        person = people.get(account)
        return (
            person is not None
            and person.enabled
            and not person.system_account
            and person.org_unit == case.owning_unit
        )

    grants = await investigations.list_grants(case.id)
    if any(answers(a) for a, level in grants.items() if level is AccessLevel.AUTHOR):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "has_an_author",
                "message": (
                    f"{case.name or case.id} has an Author already: its Authors name another"
                ),
            },
        )
    grantee = _grantee(account_id)
    await _may_hold_a_level(request, grantee, AccessLevel.AUTHOR, principal_names)
    named = people.get(grantee)
    if named is not None and not access_current(named):
        # ADR-148 Amendment 8: a unit read from Entra ID over a day ago is not trusted to place
        # them in the case's unit (the orchestrator's second review, note 13; as a transfer).
        raise HTTPException(
            status_code=409,
            detail={
                "error": "access_out_of_date",
                "message": f"{named.name}: {STALE_ACCESS_WORDS}",
            },
        )
    if named is not None and named.org_unit != case.owning_unit:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "other_unit",
                "message": f"{named.name} is of another unit: a case's level is held only within "
                "its unit",
            },
        )
    await investigations.set_grant(case.id, grantee, AccessLevel.AUTHOR, by=principal)
    await audit.record(
        principal=principal,
        action="name_an_author",
        investigation_id=case.id,
        resolved_query={"account": grantee},
        result_cardinality=1,
    )


@app.get(
    "/v1/admin/people/{user_id}/disable-plan",
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def disable_plan_route(
    user_id: str,
    principal: PrincipalDep,
    admin_people: AdminPeopleDep,
    identity_admin: IdentityAdminDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> DisablePlan:
    """*Disable…*: everything the person owns today that the administrator may see, each needing
    *Transfer to…*, L3.8's views, boards, proposed types and drawn watches among them (L2.5b), and
    the kinds not yet listed (`admin_people.L38_OWNED_KINDS`)."""
    try:
        plan = await admin_people.plan(
            user_id,
            admin=principal,
            scheme=scheme,
            people=await identity_admin.list_people(),
        )
    except DisableRefused as refused:
        raise HTTPException(
            status_code=409, detail={"error": refused.error, "message": refused.words}
        ) from None
    await audit.record(
        principal=principal,
        action="read_disable_plan",
        resolved_query={"user_id": user_id, "items": len(plan.items)},
        result_cardinality=len(plan.items),
    )
    return plan


@app.get(
    "/v1/admin/people/{user_id}/ownership",
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def person_ownership_route(
    user_id: str,
    principal: PrincipalDep,
    ownership: OwnershipDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> PersonOwnership:
    """*Disable…*'s second list (ADR-145 decision 6 and A4; L3.8): the views, boards, link-type
    proposals and drawn-item watches the person owns, read in the administrator's own unit and
    within their own clearance (`person_ownership.py`, rule 3), by kind and case name only (rule 7);
    the kinds not built yet in `not_yet_listed`. People's *Disable…* reads its `withheld`; the plan
    lists the same items by L3.8's own SQL (L2.5b)."""
    owned = await ownership.owned_by(user_id, admin=principal, scheme=scheme)
    await audit.record(
        principal=principal,
        action="read_person_ownership",
        resolved_query={"user_id": user_id, "items": len(owned.items)},
        result_cardinality=len(owned.items),
    )
    return owned


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


def _may_give(
    principal: Principal,
    roles: Sequence[str],
    before: Sequence[str],
    current: Mapping[str, Iterable[Right]],
) -> None:
    """The owner's Q3b (a) wherever a person is given roles (ADR-145 Amendment 5): each right the
    roles newly confer, through a built-in role, a single grant or a custom role's current rights,
    is one the giver may give (`giver_may_give`), or `RoleRefused` (`beyond_your_rights`). The
    roles' own names are checked first (`allowed_role`, and a custom role that exists, 422)."""
    if refused := [r for r in roles if not allowed_role(r)]:
        raise UnknownRoleError(f"not a role or right this deployment grants: {', '.join(refused)}")
    if missing := [r for r in custom_role_ids(roles) if r not in current]:
        raise HTTPException(status_code=422, detail=f"no such custom role: {', '.join(missing)}")
    given = rights_for(roles, current) - rights_for(before, current)
    held = rights_for(principal.roles)
    if beyond := sorted(r.value for r in given if not giver_may_give(r, held)):
        raise RoleRefused(
            "beyond_your_rights",
            f"you cannot give a right you do not hold: {', '.join(beyond)}",
            rights=beyond,
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
    custom_roles: CustomRolesDep,
    handling_scheme: HandlingSchemeDep,
    audit: AuditDep,
) -> SignInDelivery:
    """A new person (ADR-114 Amendment 5). The one-time code, when there is one, is in this answer
    only — never in the audit record, never stored. ADR-145 Amendment 5: no role whose rights the
    inviter may not give (`_may_give`), before the identity provider is asked."""
    _within_your_reach(principal, body, handling_scheme)
    try:
        _may_give(principal, body.roles, [], await custom_roles.current_rights())
    except RoleRefused as error:
        raise _role_refused(error) from None
    made = await identity_admin.invite(body)
    await audit.record(principal=principal, action="invite_person",
                       resolved_query={"user_id": made.person.id, "username": made.person.username,
                                       "roles": made.person.roles, "clearance": body.clearance,
                                       "org_unit": body.org_unit, "delivery": made.delivery},
                       result_cardinality=1)  # fmt: skip
    return made


@app.get("/v1/admin/sign-in", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))])
async def sign_in_kind_route(identity_admin: IdentityAdminDep) -> SignInKind:
    """ADR-148 Amendment 8: how people sign in here, so Admin › People offers invite (Keycloak) or
    add by object id (Entra ID). Behind `manage_people`, as People is."""
    return SignInKind(kind="entra" if isinstance(identity_admin, EntraPeopleAdmin) else "keycloak")


@app.get(
    "/v1/admin/dashboards/sign-in", dependencies=[Depends(require_right(Right.MANAGE_DASHBOARDS))]
)
async def dashboards_sign_in_kind_route(identity_admin: IdentityAdminDep) -> SignInKind:
    """ADR-148 Amendment 10: the same answer for Admin › Dashboards, which asks an application id on
    Entra ID and nothing on Keycloak; behind `manage_dashboards`, as Dashboards is, so an
    administrator of dashboards alone is not refused it."""
    return SignInKind(kind="entra" if isinstance(identity_admin, EntraPeopleAdmin) else "keycloak")


@app.post(
    "/v1/admin/people/by-object-id",
    status_code=201,
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def add_person_by_object_id_route(
    body: AddPersonInput,
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    audit: AuditDep,
) -> PersonAccount:
    """ADR-148 Amendment 8: on Entra ID sign-in, a person added by their Entra object id ahead of
    their first sign-in, with no roles, so roles can be given before they arrive. Elsewhere people
    are invited, and this is refused (409)."""
    if not isinstance(identity_admin, EntraPeopleAdmin):
        raise PersonActionRefused(
            "not_entra",
            "People are invited on this deployment; adding by Entra object id is for Entra ID "
            "sign-in only.",
        )
    person = await identity_admin.add_person(body.object_id, by=principal.id)
    await audit.record(principal=principal, action="add_person_by_object_id",
                       resolved_query={"user_id": person.id}, result_cardinality=1)  # fmt: skip
    return person


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
    user_id: str,
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    custom_roles: CustomRolesDep,
    admin_people: AdminPeopleDep,
    scheme: HandlingSchemeDep,
    audit: AuditDep,
    body: DisableInput | None = None,
) -> PersonAccount:
    """*Transfer and disable* (ADR-145 decision 6, A4): every item the person owns
    (`disable-plan`) given to its recipient, in one transaction with an audit entry each, then the
    account disabled and its sessions ended. Refused in words, nothing changed, while any item has
    no recipient (409 `untransferred`) or one who cannot take it (409 `recipient_refused`). Never
    one's own account — an
    administrator who did that by mistake would have no way back in."""
    if user_id == principal.id:
        raise HTTPException(status_code=409, detail={"error": "cannot_disable_yourself"})
    async with custom_roles.people_lock():
        people = await identity_admin.list_people()
        current = await custom_roles.current_rights()
        # The lock-out, read fresh under the lock (the caller's own token may be stale).
        try:
            leaves_no_people_manager(
                [p.model_copy(update={"enabled": False}) if p.id == user_id else p for p in people],
                current,
            )
        except RoleRefused as error:
            raise _role_refused(error) from None
        holders = {
            t.role_id: frozenset(
                p.id
                for p in people
                if f"{CUSTOM_ROLE_PREFIX}{t.role_id}" in p.roles
                and p.enabled
                and not p.system_account
            )
            for t in await custom_roles.teams(_today())
        }
        try:
            moved, elsewhere = await admin_people.transfer(
                user_id,
                (body or DisableInput()).transfers,
                recipients(people, current, holders),
                by=principal,
                audit=audit,
                admin_unit=principal.org_unit,
                scheme=scheme,
            )
        except DisableRefused as refused:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": refused.error,
                    "message": refused.words,
                    "items": [i.model_dump() for i in refused.items],
                },
            ) from None
        if elsewhere:
            # Each unit's administrator transfers their own share; the account is disabled once
            # nothing is left in any unit. The transfers just made stand, audited.
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "other_unit",
                    "message": f"{len(moved)} transferred, and those stand; not disabled yet: "
                    + OTHER_UNIT,
                },
            )
        try:
            # ADR-145 Amendment 8 decision 3: asked once the visible transfers have committed,
            # which stand; refused while the person owns anything this administrator may not see.
            await admin_people.refuse_if_withheld(user_id, admin=principal, scheme=scheme)
        except DisableRefused as refused:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": refused.error,
                    "message": f"{len(moved)} transferred, and those stand; not disabled yet: "
                    + refused.words,
                },
            ) from None
        try:
            person = await identity_admin.set_enabled(user_id, False)
        except IdentityAdminRefused as error:
            # Amendment 5 point 8: the transfers are committed and stand; the account is still
            # enabled.
            await audit.record(
                principal=principal,
                action="disable_person_incomplete",
                resolved_query={"user_id": user_id, "transferred": len(moved), "why": str(error)},
                result_cardinality=0,
            )
            raise HTTPException(status_code=502, detail={
                "error": "disable_incomplete",
                "message": f"every item was transferred ({len(moved)}), and those stand, but "
                f"the identity provider did not disable the account: {error}. Disable them again; "
                "there is nothing left to transfer."}) from None  # fmt: skip
    # Only now, the account disabled with nothing left elsewhere or withheld, do the person's covers
    # end; on the 502 above they stay, with the account still enabled.
    await admin_people.end_covers(user_id, by=principal, audit=audit)
    await audit.record(
        principal=principal,
        action="disable_person",
        resolved_query={"user_id": user_id, "transferred": len(moved)},
        result_cardinality=1,
    )
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


@app.delete(
    "/v1/admin/people/{user_id}", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))]
)
async def remove_person_route(
    user_id: str,
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    custom_roles: CustomRolesDep,
    audit: AuditDep,
) -> PersonAccount:
    """The person's account removed from the identity provider (ADR-112 Amendment 3). Never one's
    own; never an account OspreyFlow itself uses, nor the last person who can manage people — each
    refused in words before anything changes. The audit record keeps who the id was: what they
    made keeps their id, which ADR-106 shows in place of a name once the account is gone."""
    if user_id == principal.id:
        raise HTTPException(status_code=409, detail={"error": "cannot_remove_yourself"})
    # ADR-145 Amendment 5: a people manager through a custom role counts too; a team's lead or
    # cover is handed over or ended first, so no team points at a removed account.
    async with custom_roles.people_lock():
        current = await custom_roles.current_rights()
        try:
            leaves_no_people_manager(
                [p for p in await identity_admin.list_people() if p.id != user_id], current
            )
            teams_now = await custom_roles.teams(_today())
            if led := [t for t in teams_now if user_id in (t.lead, t.cover)]:
                raise RoleRefused(
                    "lead_leaves_team",
                    f"they are the lead or cover of {led[0].display_name}: hand the lead over, "
                    "or end the cover, before removing them",
                )
        except RoleRefused as error:
            raise _role_refused(error) from None
        person = await identity_admin.remove_person(user_id, current)
    await audit.record(principal=principal, action="remove_person",
                       resolved_query={"user_id": user_id, "username": person.username,
                                       "name": person.name, "email": person.email},
                       result_cardinality=1)  # fmt: skip
    return person


@app.get(
    "/v1/admin/organisation-arrivals", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))]
)
async def list_organisation_arrivals_route(
    principal: PrincipalDep, identity_admin: IdentityAdminDep, audit: AuditDep
) -> list[OrganisationArrival]:
    """Who the organisation's sign-in refused for a held email address and who is not yet joined
    to an account (ADR-112 Amendment 3 (b)), from the identity provider's own record; empty on a
    deployment with no sign-in through an organisation."""
    arrivals = await identity_admin.list_arrivals()
    await audit.record(principal=principal, action="list_organisation_arrivals",
                       resolved_query={}, result_cardinality=len(arrivals))  # fmt: skip
    return arrivals


@app.post(
    "/v1/admin/people/{user_id}/organisation-link",
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],
)
async def link_organisation_account_route(
    user_id: str,
    body: OrganisationLinkInput,
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    audit: AuditDep,
) -> PersonAccount:
    """A refused organisation arrival joined, deliberately, to this account (ADR-112 Amendment 3
    (b)): their next sign-in through the organisation lands here, with its roles. Refused in words:
    an account already joined, an account OspreyFlow itself uses, an id no refused arrival holds."""
    person, arrival = await identity_admin.link_organisation(user_id, body.subject)
    await audit.record(principal=principal, action="link_organisation_account",
                       resolved_query={"user_id": user_id, "username": person.username,
                                       "subject": arrival.subject,
                                       "provider_username": arrival.provider_username},
                       result_cardinality=1)  # fmt: skip
    return person


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
        body.name, clearance=body.clearance, org_unit=body.org_unit,
        application_id=body.application_id,
    )  # fmt: skip
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
    client_id: str,
    principal: PrincipalDep,
    identity_admin: IdentityAdminDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> Response:
    """Removed, and every case grant its account holds revoked with it (ADR-148 Amendment 10), so a
    dashboard registered again later finds no level waiting. The grants go first, while the
    registration still names the account: if that fails, the dashboard stays registered and removing
    it again revokes; if the removal then fails, it holds no level and is removed again. One not
    registered revokes nothing and is refused by the identity provider's own answer. The audit row
    counts the grants revoked; it never names their cases."""
    accounts = [d.account_id for d in await identity_admin.list_dashboards()
                if d.client_id == client_id]  # fmt: skip
    revoked = [
        case
        for account in accounts
        for case in await investigations.revoke_everywhere(account, by=principal)
    ]
    await identity_admin.delete_dashboard(client_id)
    await audit.record(principal=principal, action="remove_dashboard",
                       resolved_query={"client_id": client_id, "grants_revoked": len(revoked)},
                       result_cardinality=1)  # fmt: skip
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
            "metering": run.metering,
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


async def _refuse_a_composite_schedule(recipe: StudioRecipeDraft, datasets: DatasetStore) -> None:
    """ADR-099 Amendment 15, for the Admin area's schedule routes, after the schedule is found: a
    schedule whose case reads a composite, or whose recipe's dataset is one, is neither run,
    re-timed nor resumed (409 `composite_read_only`), so none starts a run that would write in
    part. The executor refuses each slot again (`check_case`), for a case switched since."""
    ids = [recipe.dataset_id] if recipe.dataset_id else []
    if recipe.schedule_case:
        ids.extend(d.id for d in await datasets.chosen_of_case(recipe.schedule_case))
    if ids and (found := await datasets.composites_among(ids)):
        # Named: an operator of schedules holds a right, so may be told dataset names (A11).
        raise CompositeReadOnlyError(await _first_name(datasets, sorted(found)), in_a_case=False)


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


# --- screening lists as managed sources (ADR-133 decision 4, stage (c)) --------------------------


@app.get(
    "/v1/screening-lists",
    dependencies=[
        Depends(require_right(Right.READ_ALERT_QUEUE)),
        Depends(require_rules_place),
    ],
)
async def list_screening_lists(
    principal: PrincipalDep,
    screening_lists: ScreeningListsDep,
    audit: AuditDep,
    handling_scheme: HandlingSchemeDep,
) -> ScreeningListsOverview:
    """The Lists screen for a reader of the alert queue: each list's version, entries, last update
    and failure, in words. Not its refreshes: their counts of customers re-screened and alerts
    raised are taken across every case in the deployment (rule 7: no unfiltered count), and the
    model has no field to hold them. Only the lists the reader is cleared for, in the store's query
    (ADR-146 Amendment 7; the orchestrator's review, item 3)."""
    cleared = ListClearance.of(principal, handling_scheme)
    # Who a list's schedule runs as is for whoever manages lists to know.
    found = [s.model_copy(update={"schedule_owner": None})
             for s in await screening_lists.subscriptions(cleared=cleared)]  # fmt: skip
    await audit.record(principal=principal, action="list_screening_lists", investigation_id=None,
                       resolved_query={}, result_cardinality=len(found))  # fmt: skip
    return ScreeningListsOverview(lists=found)


@app.get(
    "/v1/admin/screening-lists",
    dependencies=[
        Depends(require_right(Right.LOAD_SCREENING_LISTS)),
        Depends(require_rules_place),
    ],
)
async def manage_screening_lists(
    principal: PrincipalDep,
    screening_lists: ScreeningListsDep,
    audit: AuditDep,
    handling_scheme: HandlingSchemeDep,
) -> ScreeningLists:
    """The Lists screen for whoever may load screening lists: the lists and their latest
    refreshes, with what each changed, and what each re-screened and raised **in the reader's own
    unit** (the owner's answer of 1 November 2026; rule 7). The store's query joins that unit's
    counts alone; another unit's customers, alerts and rule names never reach the Conduit. Only the
    lists, and their refreshes, the reader is cleared for (ADR-146 Amendment 7; review item 3)."""
    cleared = ListClearance.of(principal, handling_scheme)
    found = await screening_lists.subscriptions(cleared=cleared)
    updates = await screening_lists.updates(
        org_unit=principal.org_unit, cleared=cleared, limit=20
    )
    await audit.record(principal=principal, action="list_screening_lists", investigation_id=None,
                       resolved_query={"manage": True}, result_cardinality=len(found))  # fmt: skip
    return ScreeningLists(lists=found, updates=updates, can_manage=True)


@app.post(
    "/v1/admin/screening-lists",
    status_code=201,
    dependencies=[
        Depends(require_right(Right.LOAD_SCREENING_LISTS)),
        Depends(require_rules_place),
    ],
)
async def subscribe_screening_list(
    principal: PrincipalDep,
    screening_lists: ScreeningListsDep,
    audit: AuditDep,
    body: ScreeningSubscriptionInput,
    handling_scheme: HandlingSchemeDep,
) -> ScreeningListStatus:
    """A list subscribed (or its subscription changed): its connector and its file in the ingest
    folder. Nothing is read until it is refreshed; a location outside the folder is refused now. A
    name held by a list the administrator is not cleared for is refused before anything is written,
    never changing or answering that list (ADR-146 Amendment 7; the orchestrator's review, item 3).
    The refusal says only that the name cannot be used, which tells them some list holds it: logged
    in Amendment 7, and accepted by the orchestrator."""
    try:
        check_location(body.location)
    except ListRefused as refused:
        raise HTTPException(
            status_code=422, detail={"error": "list_refused", "message": str(refused)}
        ) from refused
    if await screening_lists.hidden(
        body.list_name, cleared=ListClearance.of(principal, handling_scheme)
    ):
        raise HTTPException(
            status_code=422,
            detail={"error": "list_refused",
                    "message": "A list cannot be subscribed under that name; choose another."},
        )  # fmt: skip
    status_ = await screening_lists.subscribe(body, principal.id, synthetic=False)
    await audit.record(principal=principal, action="screening_list_subscribed",
                       investigation_id=None,
                       resolved_query={**body.model_dump(mode="json"),
                                       **await screening_lists.audit_marking(body.list_name)},
                       result_cardinality=1)  # fmt: skip
    return status_


@app.put(
    "/v1/admin/screening-lists/{list_name}/schedule",
    dependencies=[
        Depends(require_right(Right.LOAD_SCREENING_LISTS)),
        Depends(require_rules_place),
    ],
)
async def set_screening_list_schedule(
    list_name: str,
    principal: PrincipalDep,
    screening_lists: ScreeningListsDep,
    audit: AuditDep,
    body: ListScheduleInput,
    handling_scheme: HandlingSchemeDep,
) -> ScreeningListStatus:
    """ADR-133 Amendment 3 item 4, stage (d): the list refreshed every day or every week at an
    hour, as the person setting it — resolved afresh at each slot, and refused in words if they no
    longer hold the right. Without a schedule, the list is refreshed by hand only."""
    try:
        # A list the setter is not cleared for is answered as one never subscribed (ADR-146
        # Amendment 7; the orchestrator's review, item 3).
        if await screening_lists.hidden(
            list_name, cleared=ListClearance.of(principal, handling_scheme)
        ):
            raise LookupError(list_name)
        updated = await screening_lists.set_schedule(list_name, body.schedule, principal.id)
    except ListScheduleRefused as refused:
        raise HTTPException(
            status_code=422, detail={"error": "schedule_refused", "message": str(refused)}
        ) from refused
    except LookupError as missing:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"no list is subscribed as “{list_name}”"},
        ) from missing
    await audit.record(principal=principal, action="screening_list_schedule_set",
                       investigation_id=None,
                       resolved_query={"list_name": list_name, "schedule": (
                           body.schedule.model_dump() if body.schedule else None),
                           **await screening_lists.audit_marking(list_name)},
                       result_cardinality=1)  # fmt: skip
    return updated


@app.post(
    "/v1/admin/screening-lists/{list_name}/refresh",
    dependencies=[
        Depends(require_right(Right.LOAD_SCREENING_LISTS)),
        Depends(require_rules_place),
    ],
)
async def refresh_screening_list_route(
    list_name: str,
    request: Request,
    principal: PrincipalDep,
    screening_lists: ScreeningListsDep,
    typology_rules: TypologyRulesDep,
    graph: GraphDep,
    handling_scheme: HandlingSchemeDep,
    alerts_store: AlertsStoreDep,
    audit: AuditDep,
    valkey: ValkeyDep,
    principal_resolver: PrincipalResolverDep,
) -> ScreeningListUpdate:
    """*Refresh now*: the list read again through its connector, applied as a new version, and
    every customer of every case with a screening rule re-screened against the changed entries
    only, as each rule's deployer (rule 3). Refused or failed in words, the list left as it was.
    The answer counts the administrator's own unit alone, read back through the store's query as
    the Lists screen reads it (rule 7); the deployment's totals go to the audit only. A list the
    administrator is not cleared for is answered as one never subscribed, before it is read
    (ADR-146 Amendment 7; the orchestrator's review, item 3)."""
    cleared = ListClearance.of(principal, handling_scheme)
    if await screening_lists.hidden(list_name, cleared=cleared):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"no list is subscribed as “{list_name}”"},
        )
    rescreen = Rescreener(
        rules=typology_rules,
        datasets=get_datasets(request),
        graph=graph,
        scheme=handling_scheme,
        alert_store=alerts_store,
        audit=audit,
        valkey=valkey,
        principal_for_owner=principal_resolver.resolve_for_owner,
        runner=principal,
    )
    try:
        update = await refresh_screening_list(list_name, store=screening_lists, rescreen=rescreen)
    except ListNotSubscribed as missing:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"no list is subscribed as “{list_name}”"},
        ) from missing
    await audit.record(principal=principal, action="screening_list_refreshed",
                       investigation_id=None,
                       resolved_query={"list_name": list_name, "outcome": update.outcome,
                                       "version": update.version, "alerts": update.alerts,
                                       **await screening_lists.audit_marking(list_name)},
                       result_cardinality=update.alerts)  # fmt: skip
    own = await screening_lists.update_for(
        update.id, org_unit=principal.org_unit, cleared=cleared
    )
    if own is None:  # recorded a moment ago in the same store
        raise HTTPException(
            status_code=500,
            detail={"error": "not_recorded",
                    "message": "the refresh ran but its record could not be read back"},
        )  # fmt: skip
    return own


def get_schedule_executor(request: Request) -> ScheduleExecutor:
    return request.app.state.schedule_executor  # type: ignore[no-any-return]


ScheduleExecutorDep = Annotated[ScheduleExecutor, Depends(get_schedule_executor)]


# --- External orchestration and Operations (ADR-141; the redesign's phase 10) --------------------

#: Who may hand a pipeline's schedule to an orchestrator: who may schedule it (ADR-110 decision 3).
_HANDS_A_SCHEDULE = [Depends(require_right(Right.SCHEDULE_PIPELINES)), NoLoadingInACompositeCase]
_NO_SUCH_PIPELINE = (
    "no pipeline this service identity may trigger has that id in that dataset: a pipeline is "
    "triggered only by the client it is owned externally by"
)


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/owned-externally",
    dependencies=[Depends(require_right(Right.SCHEDULE_PIPELINES))],
)
async def read_pipeline_owned_externally(
    investigation: InvestigationViewerDep,
    recipe: AuthorizedStudioRecipeDep,
    studio_recipes: StudioRecipesDep,
) -> ExternallyOwnedInput | None:
    """Whether the pipeline is owned externally, and by which client (ADR-141 decision 11); `null`
    when it is not. The owner is not named here: the Runs tab shows the client alone."""
    owner = await studio_recipes.external_owner(recipe.recipe_id)
    return None if owner is None else ExternallyOwnedInput(client_id=owner.client_id)


@app.put(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/owned-externally",
    dependencies=_HANDS_A_SCHEDULE,
)
async def mark_pipeline_owned_externally(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_APPROVER))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
    body: ExternallyOwnedInput,
) -> ExternallyOwnedInput:
    """*Owned externally* (ADR-141 decision 11): the pipeline's schedule handed to an orchestrator,
    triggered by `body.client_id` alone; the person marking it is the owner every external run
    acts as, in this case (decision 10). Refused in words while it has a schedule of its own, so
    nobody sets both."""
    if recipe.status is not StudioRecipeStatus.PUBLISHED:
        raise HTTPException(
            status_code=409, detail="only a deployed pipeline can be owned externally"
        )
    if recipe.schedule_cron or recipe.schedule_watch:
        raise HTTPException(
            status_code=409,
            detail="the pipeline has a schedule of its own: clear it first, so nobody sets both",
        )
    if is_deployment_client(body.client_id):
        # Rule 3: the deployment's own clients have service accounts; none is an orchestrator.
        raise HTTPException(status_code=422, detail=DEPLOYMENT_CLIENT_WORDS)
    await studio_recipes.set_external_owner(
        recipe.recipe_id,
        client_id=body.client_id,
        owner=principal.id,
        case=investigation.id,
        now=datetime.now(UTC),
    )
    await audit.record(
        principal=principal,
        action="mark_pipeline_owned_externally",
        resolved_query={"recipe_id": recipe.recipe_id, "client_id": body.client_id},
        result_cardinality=1,
    )
    return body


@app.delete(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/owned-externally",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_HANDS_A_SCHEDULE,
)
async def clear_pipeline_owned_externally(
    investigation: InvestigationEditorDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_APPROVER))],
    studio_recipes: StudioRecipesDep,
    audit: AuditDep,
) -> None:
    await studio_recipes.clear_external_owner(recipe.recipe_id)
    await audit.record(
        principal=principal,
        action="clear_pipeline_owned_externally",
        resolved_query={"recipe_id": recipe.recipe_id},
        result_cardinality=1,
    )


@app.post("/v1/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_external_run_route(
    request: Request,
    client_id: ServiceIdentityDep,
    body: ExternalRunInput,
    studio_recipes: StudioRecipesDep,
    valkey: ValkeyDep,
    executor: ScheduleExecutorDep,
    principal_resolver: PrincipalResolverDep,
) -> ExternalRunStatus:
    """ADR-141 decision 9: an orchestrator starts a run of a deployed pipeline, keyed by its own
    run id (decision 12). The service identity authorises the trigger and nothing more; the run
    acts as the pipeline's owner (decision 10; `external_runs.py`). A pipeline that is not this
    client's to trigger is 404, the same answer as one that does not exist."""
    recipe = await studio_recipes.deployed(body.pipeline_id)
    owner = await studio_recipes.external_owner(body.pipeline_id) if recipe else None
    if (
        recipe is None
        or owner is None
        or owner.client_id != client_id
        or recipe.dataset_id != body.dataset_id
    ):
        raise HTTPException(status_code=404, detail=_NO_SUCH_PIPELINE)
    if body.version != "latest" and body.version != recipe.version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"the pipeline's deployed version is {recipe.version}, not {body.version}: "
                "pin the deployed version, or ask for the latest"
            ),
        )
    tasks: set[asyncio.Task[None]] = request.app.state.external_runs

    def spawn(work: Coroutine[Any, Any, None]) -> object:
        task = asyncio.create_task(work)
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return task

    return await start_external_run(
        deps=RecipeRunDeps.from_state(request.app.state),
        executor=executor,
        valkey=valkey,
        recipe=owner.applied_to(recipe),
        external=External(run_id=body.external_run_id, triggered_by=client_id),
        spawn=spawn,
        resolve_owner=_owner_or_none(principal_resolver),
    )


def _owner_or_none(resolver: PrincipalResolver) -> Callable[[str], Awaitable[Principal | None]]:
    async def resolve(owner_id: str) -> Principal | None:
        try:
            return await resolver.resolve_for_owner_detailed(owner_id)
        except Exception:  # noqa: BLE001 - an owner who cannot be resolved now sees nothing
            return None

    return resolve


@app.get("/v1/runs/{run_id}")
async def read_external_run(
    run_id: str,
    client_id: ServiceIdentityDep,
    recipe_runs: RecipeRunsDep,
    handling_scheme: HandlingSchemeDep,
    principal_resolver: PrincipalResolverDep,
) -> ExternalRunStatus:
    """A run's status, report counts and held rows (ADR-141 decision 9), only for a run this very
    client triggered, and its counts only as its owner may read them (rule 3)."""
    run = await recipe_runs.get(run_id)
    if run is None or run.trigger != "external" or run.triggered_by != client_id:
        raise HTTPException(
            status_code=404, detail="no run this service identity triggered has that id"
        )
    owner = await _owner_or_none(principal_resolver)(run.run_as)
    return await status_for(run, owner=owner, scheme=handling_scheme)


@app.get(
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/quota",
    dependencies=[Depends(require_right(Right.RUN_PIPELINES))],
)
async def read_pipeline_quota(
    investigation: InvestigationViewerDep,
    recipe: AuthorizedStudioRecipeDep,
    principal: PrincipalDep,
    recipe_runs: RecipeRunsDep,
    run_quotas: RunQuotasDep,
) -> RunQuotaUse:
    """The Runs tab's quota bar (ADR-141 decision 6): the dataset's quota of runs a day and
    whether today's runs have used it. Only a case that reads the recipe's dataset is told, as
    Test and Preview are refused (rule 4); and the day's count is every unit's runs into the
    dataset, so only `administer_system` is given the number (rules 3 and 7, the strict reading;
    ADR-141 Amendment 1)."""
    if recipe.dataset_id and recipe.dataset_id not in (principal.datasets or []):
        raise RecipeRuleError([QUOTA_WITHHELD])
    quota = (
        await run_quotas.get("dataset", recipe.dataset_id)
        if run_quotas is not None and recipe.dataset_id
        else None
    )
    today = (
        await recipe_runs.runs_since(
            since=day_start(datetime.now(UTC)), dataset_id=recipe.dataset_id
        )
        if recipe.dataset_id
        else 0
    )
    limit = quota.runs_per_day if quota is not None else None
    every_unit = Right.ADMINISTER_SYSTEM in rights_for(principal.roles)
    return RunQuotaUse(
        quota=quota,
        runs_today=today if every_unit else None,
        used=limit is not None and today >= limit,
    )


#: What the quota bar says to a case that does not read the recipe's dataset (rule 4).
QUOTA_WITHHELD = (
    "The quota is withheld: it counts this dataset's runs, which only a case that reads the "
    "dataset may read."
)


def _units_read(principal: Principal) -> list[str] | None:
    """Operations' reach (phase 10 step 7): the reader's own unit, unless they administer the
    system, who reads every unit (`None`)."""
    if Right.ADMINISTER_SYSTEM in rights_for(principal.roles):
        return None
    return [principal.org_unit]


@app.get(
    "/v1/admin/operations/runs", dependencies=[Depends(require_right(Right.OPERATE_SCHEDULES))]
)
async def operations_runs(
    principal: PrincipalDep,
    recipe_runs: RecipeRunsDep,
    studio_recipes: StudioRecipesDep,
    handling_scheme: HandlingSchemeDep,
    names: PrincipalNamesDep,
    run_quotas: RunQuotasDep,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> OperationsRollup:
    """Admin › Running › Operations (ADR-141 decisions 3, 4, 6, 7 and 14): the window's runs by
    pipeline, dataset, unit and trigger per day; scheduler health; external triggers; the quotas.
    The reader's unit's alone unless they administer the system, filtered in the ledger's own
    `WHERE` (rule 3); counts withheld where a run wrote a marking the reader may not view."""
    units = _units_read(principal)
    since = day_start(datetime.now(UTC)) - timedelta(days=days - 1)
    runs = await recipe_runs.window(since=since, units=units)
    labels: dict[str, str] = {}
    for recipe_id in {r.recipe_id for r in runs}:
        try:
            labels[recipe_id] = (await studio_recipes.get(recipe_id)).label
        except StudioRecipeNotFoundError:
            continue
    paused = [
        PausedPipeline(
            pipeline_id=r.recipe_id, pipeline_label=r.label, reason=r.schedule_paused_reason
        )
        for r in await studio_recipes.paused_of(units)
    ]
    named = await names.full_names({r.run_as for r in runs if r.run_as})
    datasets = sorted({r.dataset_id for r in runs if r.dataset_id})
    quotas = (
        [] if run_quotas is None else await run_quotas.reached_by(units=units, datasets=datasets)
    )
    since_day = since.astimezone(ZoneInfo("Europe/London")).date().isoformat()
    alerts = (
        []
        if run_quotas is None
        else await run_quotas.alerts(
            since_day=since_day,
            of=None if units is None else [(q.scope, q.key) for q in quotas],
        )
    )
    return OperationsRollup(
        days=days,
        rows=rollup_rows(runs, reader=principal, scheme=handling_scheme, labels=labels),
        scheduler=scheduler_health(runs, paused=paused, names=named),
        external=external_triggers(
            runs, reader=principal, scheme=handling_scheme, labels=labels, names=named
        ),
        quotas=quotas,
        alerts=[
            QuotaAlertView(scope=a.scope, key=a.key, day=date.fromisoformat(a.day), words=a.words)
            for a in alerts
        ],
        units=units
        if units is not None
        else sorted({r.owning_unit for r in runs if r.owning_unit}),
    )


@app.put(
    "/v1/admin/operations/quotas/{scope}/{key}",
    # Setting a quota's own right first (decision (f) of L1.7: it limits every unit's runs;
    # `test_route_rights.py` reads the first), then Operations', as each of the section's routes
    # asks (`test_admin_sections.py`).
    dependencies=[
        Depends(require_right(Right.ADMINISTER_SYSTEM)),
        Depends(require_right(Right.OPERATE_SCHEDULES)),
    ],
)
async def set_run_quota(
    scope: QuotaScope,
    key: str,
    body: RunQuotaInput,
    principal: PrincipalDep,
    run_quotas: RunQuotasDep,
    audit: AuditDep,
) -> RunQuota:
    """A dataset's or a unit's quota of runs a day (ADR-141 decision 6), set by an administrator of
    the system (the strict reach: a quota binds every unit's runs into a dataset)."""
    if run_quotas is None:
        raise HTTPException(status_code=503, detail="run quotas are not available")
    quota = RunQuota(scope=scope, key=key, **body.model_dump())
    await run_quotas.set(quota)
    await audit.record(
        principal=principal,
        action="set_run_quota",
        resolved_query={"scope": scope, "key": key, "runs_per_day": body.runs_per_day},
        result_cardinality=1,
    )
    return quota


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
    datasets: DatasetsDep,
) -> AdminSchedule:
    """*Run now* (ADR-110 Amendment 3, point 2): at once, **as the schedule's owner**, with every
    check a scheduled slot gets — refused in words (409) if the owner may not run it. The
    administrator is named in the audit as who asked; the run itself is the owner's."""
    recipe = await _scheduled_recipe(studio_recipes, recipe_id)
    await _refuse_a_composite_schedule(recipe, datasets)
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
    datasets: DatasetsDep,
) -> AdminSchedule:
    """*Change schedule* (ADR-110 Amendment 3, point 2): a new time, refused in words if it could
    not be kept; **the owner is kept**, and the administrator named in the audit."""
    await _refuse_a_composite_schedule(await _scheduled_recipe(studio_recipes, recipe_id), datasets)
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
    datasets: DatasetsDep,
) -> AdminSchedule:
    await _refuse_a_composite_schedule(await _scheduled_recipe(studio_recipes, recipe_id), datasets)
    await studio_recipes.set_paused(recipe_id, paused=False, reason=None)
    await audit.record(principal=principal, action="resume_schedule",
                       resolved_query={"recipe_id": recipe_id}, result_cardinality=1)  # fmt: skip
    recipe = await _scheduled_recipe(studio_recipes, recipe_id)
    return await _admin_schedule(recipe, recipe_runs, principal, handling_scheme)


#: ADR-114 Amendment 36: Admin -> System's words for the Conduit's own credential.
CREDENTIAL_NOTICES = {
    "refused": "The Conduit cannot act for people: run `ospreyflow repair-sign-in`",
    "unreachable": "Not known: the identity provider did not answer",
}


@app.get("/v1/admin/system", dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))])
async def system_status_route(
    request: Request,
    principal: PrincipalDep,
    graph: GraphDep,
    investigations: InvestigationsDep,
    valkey: ValkeyDep,
    identity_admin: IdentityAdminDep,
    model_routes: ModelRoutesDep,
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
    # ADR-114 Amendment 36: one client-credentials request (kept half a minute) answers both the
    # identity provider's line and whether the Conduit can act for people; a refusal is Keycloak
    # answering, so the identity provider's line stays green and the next line says what to run.
    credential = await identity_admin.credential_check()
    components = [
        await check("Graph store", lambda: graph.type_counts(nobody)),
        await check("Case and rule stores (Postgres)", lambda: investigations.list_for(principal)),
        await check("Working-set cache (Valkey)", lambda: valkey.ping()),
        await check("Model server", models),
        ComponentHealth(name="Identity provider", ok=credential.state != "unreachable",
                        millis=credential.millis,
                        detail=credential.detail if credential.state == "unreachable" else None),
        ComponentHealth(name="Acting for people", ok=credential.state == "accepted",
                        millis=credential.millis, detail=credential.detail,
                        notice=CREDENTIAL_NOTICES.get(credential.state)),
    ]  # fmt: skip
    # ADR-114 decision 11, ADR-135: each role's model and where it runs, each engine and whether
    # its key is present, from names only — never a key.
    statuses, engines, notice = model_status(model_routes)
    # ADR-144 decision 6: the migration's count, in the administrator's own unit; none when the
    # store is not reachable (the System screen still answers for every component).
    people_store = getattr(request.app.state, "admin_people", None)
    try:
        if people_store is None:
            raise RuntimeError("the people store is not connected")
        converted = await people_store.converted_views(principal.org_unit)
    except Exception as e:  # noqa: BLE001 - the count's failure is said, in words
        converted = ConvertedViews(
            problem=f"Not known: the count could not be read ({type(e).__name__})"
        )
    held_ceiling = getattr(request.app.state, "deployment_ceiling", None)
    return SystemStatus(
        # ADR-148 decision 10: the deployment's marking ceiling, as the Conduit's start read it.
        highest_marking=(held_ceiling or DeploymentCeiling.from_env()).marking,
        converted_views=converted,
        # ADR-114 Amendment 8: the version the deployment was rendered with, and the last check.
        version=deployment_version(),
        components=components,
        models=statuses,
        engines=engines,
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
    investigation: InvestigationViewerDep,
    ontology: OntologyDep,
    principal: PrincipalDep,
    typology_rules: TypologyRulesDep,
) -> TrendOptions:
    """The event types and properties a trend may use: this deployment's ontology, narrowed to
    the core types and the case's own domain packs (ADR-126 decision 6); and what an alert trend
    may split by, with the case's rules as the reader may read them (ADR-134 decision 3)."""
    rules = await typology_rules.list_for_case(investigation.id, principal)
    return trend_options(ontology, investigation.domains, rules)


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
    typology_rules: TypologyRuleStore,
) -> TrendFigures:
    """The trend counted for this reader now (rule 3): the case's own events, nothing the reader
    may not see. An alert trend (ADR-134 decision 3) is the
    analytics port's `alert_trend`, filtered in its query as the reader, its rules named after."""
    validate_definition(defn, ontology)
    now = datetime.now(UTC)
    if defn.source == "alerts":
        alert_request, start = to_alert_request(defn, case.id, now)
        result = await analytics.alert_trend(alert_request, principal)
        if defn.group_by == "rule":
            rules = await typology_rules.list_for_case(case.id, principal)
        else:
            rules = []
        result = name_alert_series(result, defn, rules)
    else:
        request, start = to_request(defn, ontology, case.id, now)
        scoped = await _case_event_filter(
            request.filter, principal, investigations, audit, working_set
        )
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
    typology_rules: TypologyRulesDep,
) -> TrendFigures:
    check_in_case_domains(body, ontology, investigation.domains)
    figures = await _trend_figures(body, investigation, principal, ontology, analytics,
                                   investigations, audit, working_set, handling_scheme,
                                   typology_rules)  # fmt: skip
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
    typology_rules: TypologyRulesDep,
) -> TrendFigures:
    saved = await trends.get(investigation.id, trend_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="no such trend in this case")
    figures = await _trend_figures(saved, investigation, principal, ontology, analytics,
                                   investigations, audit, working_set, handling_scheme,
                                   typology_rules)  # fmt: skip
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
    *,
    alerts: AlertStore,
    analytics: AnalyticsPort,
) -> tuple[list[StoredPackItem], bool]:
    """The draft's items this reader may see, in order, and whether any are withheld from them:
    filtered in the store's query as the reader, then checked again against the graph now (ADR-134
    decision 4). No item withheld from the reader reaches this function."""
    items, in_store = await packs.readable_items(pack_id, reader, scheme)
    return await readable(
        items, reader, scheme, graph, case_id, alerts=alerts, analytics=analytics,
        withheld_in_store=in_store,
    )  # fmt: skip


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
    alerts_store: AlertsStoreDep,
    analytics: AnalyticsDep,
) -> PackDraft:
    """The draft as this reader may see it: the items withheld from them are counted, not named."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    shown, withheld = await _readable_draft(
        packs,
        pack.id,
        principal,
        scheme,
        graph,
        investigation.id,
        alerts=alerts_store,
        analytics=analytics,
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
        pack=named, items=served, withheld=withheld, marking=highest_marking(served, scheme)
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
    alerts_store: AlertsStoreDep,
    typology_rules: TypologyRulesDep,
) -> PackItem:
    """The content is read and frozen here, as the adder — never taken from the request, except a
    caption and a note's own words. An alert (ADR-134 decision 1) is one of the adder's queue in
    this case, read whole as them, or not found."""
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
        alerts_store,
        typology_rules,
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
    alerts_store: AlertStore,
    typology_rules: TypologyRuleStore,
) -> StoredPackItem:
    if body.kind == "alert":
        try:
            explained, events = await alert_queue.explain_with_evidence(
                alerts_store, graph, analytics, case.id, body.alert_id or "", principal
            )
        except AlertNotFoundError as missing:
            raise HTTPException(status_code=404, detail="no such alert in this case") from missing
        # ADR-109 Amendment 12 point 10: the item never falls below what the alert's raiser read.
        floor = raiser_floor(explained.alert, await alerts_store.handlings_of(explained.alert.id))
        return alert_item(explained, events, principal, scheme, raised_over=floor)
    if body.kind == "trend":
        saved = await trends.get(case.id, body.trend_id) if body.trend_id else None
        if saved is None:
            raise HTTPException(status_code=404, detail="no such trend in this case")
        figures = await _trend_figures(
            saved, case, principal, ontology, analytics, investigations, audit, working_set, scheme,
            typology_rules,
        )  # fmt: skip
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
    alerts_store: AlertsStoreDep,
    analytics: AnalyticsDep,
) -> None:
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    shown, _ = await _readable_draft(
        packs,
        pack.id,
        principal,
        scheme,
        graph,
        investigation.id,
        alerts=alerts_store,
        analytics=analytics,
    )
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
    alerts_store: AlertsStoreDep,
    analytics: AnalyticsDep,
) -> PackDraft:
    """Only the reader's own items move; each item withheld from them keeps its place."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    shown, withheld = await _readable_draft(
        packs,
        pack.id,
        principal,
        scheme,
        graph,
        investigation.id,
        alerts=alerts_store,
        analytics=analytics,
    )
    if sorted(body.item_ids) != sorted(i.id for i in shown):
        raise PackItemRefused("the new order must name each item you can see exactly once")
    try:
        # The withheld items' places are worked out in the store, as the reader (rule 3).
        await packs.reorder_visible(pack.id, principal, scheme, body.item_ids)
    except ValueError as exc:
        raise PackItemRefused(str(exc)) from exc
    await audit.record(
        principal=principal,
        action="reorder_pack",
        investigation_id=investigation.id,
        resolved_query={"pack": pack.id},
        result_cardinality=len(body.item_ids),
    )
    by_id = {i.id: i for i in shown}
    served = [by_id[i].served() for i in body.item_ids]
    (named,) = await _named_packs(
        [await _pack_or_404(packs, investigation.id, pack_id)], principal_names
    )
    return PackDraft(
        pack=named,
        items=served,
        withheld=withheld,
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
    alerts_store: AlertsStoreDep,
    typology_rules: TypologyRulesDep,
) -> PackItem:
    """A trend snapshot counted again, or an alert read again (ADR-134 decision 1: so an alert
    added while open can say how it was closed), now, as the refresher; the earlier one stays in
    the history (decision 4)."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    shown, _ = await _readable_draft(
        packs,
        pack.id,
        principal,
        scheme,
        graph,
        investigation.id,
        alerts=alerts_store,
        analytics=analytics,
    )
    old = next((i for i in shown if i.id == item_id), None)
    if old is None:
        raise HTTPException(status_code=404, detail="no such item in this pack")
    if old.kind == "trend" and old.trend_id is not None:
        again = AddPackItem(kind="trend", trend_id=old.trend_id)
    elif old.kind == "alert" and old.alert is not None:
        again = AddPackItem(kind="alert", alert_id=old.alert.alert_id)
    else:
        raise PackItemRefused("only a trend snapshot or an alert is refreshed")
    new = await _build_pack_item(
        again,
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
        alerts_store,
        typology_rules,
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
    alerts_store: AlertsStoreDep,
    analytics: AnalyticsDep,
) -> PackHistory:
    (pack,) = await _named_packs(
        [await _pack_or_404(packs, investigation.id, pack_id)], principal_names
    )
    earlier, in_store = await packs.readable_earlier(pack.id, principal, scheme)
    shown, withheld = await readable(
        earlier,
        principal,
        scheme,
        graph,
        investigation.id,
        alerts=alerts_store,
        analytics=analytics,
        withheld_in_store=in_store,
    )
    return PackHistory(
        earlier_snapshots=[i.served() for i in shown], withheld=withheld, versions=pack.versions
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
    alerts_store: AlertsStoreDep,
    analytics: AnalyticsDep,
) -> PublishedPack:
    """A new immutable version. Refused while the draft holds an item the publisher may not see:
    nobody publishes what they cannot read (Amendment 1)."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    shown, withheld = await _readable_draft(
        packs,
        pack.id,
        principal,
        scheme,
        graph,
        investigation.id,
        alerts=alerts_store,
        analytics=analytics,
    )
    if withheld:
        raise PackHasWithheldItems()
    if not shown:
        raise PackItemRefused("an empty pack has nothing to publish")
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
    alerts_store: AlertsStoreDep,
    analytics: AnalyticsDep,
) -> PublishedPack:
    """The newest published version as this reader may see it (decision 5): every read audited."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    found = await packs.readable_version(pack.id, principal, scheme)
    if found is None:
        raise HTTPException(status_code=404, detail="this pack has no publication")
    version, items, in_store = found
    shown, withheld = await readable(
        items,
        principal,
        scheme,
        graph,
        investigation.id,
        alerts=alerts_store,
        analytics=analytics,
        withheld_in_store=in_store,
    )
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
        withheld=withheld,
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
    alerts_store: AlertsStoreDep,
    analytics: AnalyticsDep,
) -> PackExport:
    """The newest live publication through the export gate (ADR-113 decision 6, ADR-045/047): the
    approved manifest, from which the Glass renders the PDF. Editor and `export`, as every
    export."""
    pack = await _pack_or_404(packs, investigation.id, pack_id)
    found = await packs.readable_version(pack.id, principal, scheme)
    if found is None:
        raise HTTPException(status_code=404, detail="this pack has no publication to export")
    version, _, in_store = found
    result = await export_pack(
        pack=pack,
        version=version,
        withheld_in_store=in_store,
        request=body,
        exporter=principal,
        scheme=scheme,
        graph=graph,
        ledger=export_ledger,
        policy=config.export_manifest_policy,
        alerts=alerts_store,
        analytics=analytics,
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
    identity_admin: PeopleDirectory,
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


@app.exception_handler(PersonActionRefused)
async def _person_action_refused(request: Request, exc: PersonActionRefused) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": exc.error, "detail": exc.words})


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


@app.get("/v1/me")
async def me_route(principal: PrincipalDep) -> MeResponse:
    """ADR-148 Amendment 8: the signed-in person's own principal, as `principal_auth` resolved it,
    which the Glass shows and gates its places on, never a claim of the token (on Entra ID a token's
    `roles` are app roles, not ours). Their own fields only: no other person's, and no count."""
    return MeResponse(
        id=principal.id,
        clearance=principal.clearance,
        org_unit=principal.org_unit,
        roles=list(principal.roles),
        receivable_handling_codes=list(principal.receivable_handling_codes),
    )


@app.get("/v1/me/rights")
async def my_rights_route(principal: PrincipalDep) -> RightsResponse:
    """ADR-112: what the signed-in person may do, so the Glass and the Studio leave out what they
    would only refuse. Not a gate — every route still checks its own right."""
    return RightsResponse(rights=sorted(rights_for(principal.roles)))


async def require_guide_place(guide: str, principal: PrincipalDep) -> guide_files.Guide:
    """ADR-145 Amendment 10: the guide's place's gate, asked before the route touches any file. A
    name that is not one of the three guides is 404 `no_such_guide`; a principal whose rights do
    not open the guide's place (the switcher's test: one of its rights, every right it needs) is
    403 `place_required`, which names the place, its rights and its needs, in words. The place
    follows the guide's name, so it is not a static `required_place`: `test_guides.py` asks every
    role and single right of it instead (`test_place_routes.py` reads static checks only)."""
    known = guide_files.GUIDES.get(guide)
    if known is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=guide_files.unknown(guide)
        )
    if not guide_files.opens_place(known.place, principal.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=guide_files.refusal(known)
        )
    return known


@app.get("/v1/guides/{guide}", response_class=FileResponse)
async def read_guide_route(
    known: Annotated[guide_files.Guide, Depends(require_guide_place)],
) -> Response:
    """ADR-145 Amendment 10: a guide's PDF, the deployment's own, to a principal whose rights open
    the place it belongs to (`require_guide_place`): the user guide with the Glass, the developer
    guide with the Ingest Studio, the administration guide with Admin. It names no single right,
    because a place opens on any one of several. Home's link is a convenience, never the gate."""
    folder = guide_files.guides_dir()
    path = folder / known.pdf
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=guide_files.not_carried(known)
        )
    headers = {"Cache-Control": "private, no-store"}
    if (version := guide_files.version(known, folder)) is not None:
        headers["X-Guide-Version"] = version
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"ospreyflow-{known.pdf}",
        content_disposition_type="inline",
        headers=headers,
    )


@app.get("/v1/me/needs-you")
async def my_needs_you_route(
    request: Request,
    principal: PrincipalDep,
    ageing: PromotionAgeingDep,
    investigations: InvestigationsDep,
    datasets: DatasetsDep,
    link_types: LinkTypesDep,
    scheme: HandlingSchemeDep,
    alerts_store: AlertsStoreDep,
) -> NeedsYou:
    """The reader's *Needs you* (ADR-145 decision 11, A2; L2.7; `needs_you.py` says what each
    half reads). It names no right because each half is gated by what it lists, as the reader. The
    overdue promotions are served only while the reader is still a recipient (`alerts_for` asks
    `_promotion_recipients` again now). The proposed link types are counted only for a holder of
    `accept_types`, only in the datasets their own cases load into, and without any proposal they
    may not read."""
    app_ = request.app
    # Only a promotion still waiting is served (one approved, rejected or withdrawn since its alert
    # is not), with its words as they stand now; the people are read once for every alert.
    now = datetime.now(UTC)
    source = app_.state.waiting_promotions
    current = (
        {w.promotion_id: w for w in await source.all_waiting()}
        if getattr(source, "recorded", False) else {}
    )  # fmt: skip
    people: list[PersonAccount] = []
    if current:
        people = await app_.state.identity_admin.list_people()

    async def still(p: promotion_ageing_module.PendingPromotion) -> list[str]:
        if p.promotion_id not in current:
            return []
        # The promotion as the seam holds it now, with its items' marking (the contract's field).
        return await _promotion_recipients(app_, current[p.promotion_id], people)

    words_now = promotion_ageing_module.overdue_words
    overdue = [
        n.model_copy(update={"words": words_now(current[n.promotion_id], now)})
        for n in await ageing.alerts_for(principal.id, still)
    ]
    proposals: list[NeedsYouProposals] = []
    if Right.ACCEPT_TYPES in rights_for(principal.roles):
        reached = await needs_you_module.reached_datasets(
            principal, investigations.list_for, datasets.ids_of_case
        )
        held = await datasets.egress_of(reached) if reached else {}
        names = {d: held[d].name for d in reached if d in held}

        async def words(dataset_id: str) -> bool:
            return await _reads_proposal_words(dataset_id, principal, datasets, scheme)

        proposals = await needs_you_module.proposals_to_decide(
            [d for d in reached if d in held], names, link_types.open_proposal_count, words
        )
    # ADR-110 Amendment 19: the reader's own scheduled loads' notices, read by owner in the query.
    notices, notices_total = await needs_you_module.schedule_notices_for(
        principal, alerts_store, now
    )
    return NeedsYou(
        promotions_overdue=overdue, proposals=proposals,
        schedule_notices=notices, schedule_notices_total=notices_total,
    )  # fmt: skip


# --- Admin › Models (ADR-135 Amendment 2, ADR-112 Amendment 7) ----------------------------------
# Every route needs `manage_models` (rule 4). None returns, logs or audits a key: the key route
# reads its own body, so no validation error can echo it; the gateway's words are never passed on.

ModelAdminDep = Annotated[model_admin_module.ModelAdmin, Depends(get_model_admin)]
_MANAGE_MODELS = [Depends(require_right(Right.MANAGE_MODELS))]


async def _model_admin_body[Body: BaseModel](request: Request, shape: type[Body]) -> Body:
    """A Models route's body, read here rather than by FastAPI, whose 422 carries the input back:
    a field that refuses a value shaped like a key (the contract reference) would echo it. The
    refusal names each field and why, never what was sent."""
    raw = await request.body()
    try:
        return shape.model_validate_json(raw)
    except ValidationError as invalid:
        try:
            sent = model_admin_module.sent_values(json.loads(raw))
        except ValueError:
            sent = {raw.decode("utf-8", "replace")}
        words = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: "
            + str(e.get("msg", "")).removeprefix("Value error, ")
            for e in invalid.errors(include_input=False, include_context=False, include_url=False)
        )
        # A validator's message may quote what it refused (`schemas.deployment`'s do): never sent
        # back, nor the request's other values, unless shaped like a name.
        words = model_admin_module.redacted(words, sent)
        raise HTTPException(
            status_code=422, detail={"error": "model_admin_refused", "detail": words}
        ) from None


def _model_admin_refused(refused: model_admin_module.ModelAdminRefused) -> HTTPException:
    return HTTPException(
        status_code=refused.status, detail={"error": "model_admin_refused", "detail": refused.words}
    )


@app.get("/v1/admin/models", dependencies=_MANAGE_MODELS)
async def models_admin_view_route(admin: ModelAdminDep) -> ModelsAdminView:
    return admin.view()


@app.get("/v1/admin/models/history", dependencies=_MANAGE_MODELS)
async def models_admin_history_route(admin: ModelAdminDep) -> ModelAdminHistory:
    return ModelAdminHistory(entries=await admin.history())


@app.post("/v1/admin/models/engines", dependencies=_MANAGE_MODELS)
async def models_admin_add_engine_route(
    request: Request, principal: PrincipalDep, admin: ModelAdminDep
) -> ModelsAdminView:
    body = await _model_admin_body(request, EngineInput)
    try:
        await admin.add_engine(principal.id, body.provider)
    except model_admin_module.ModelAdminRefused as refused:
        raise _model_admin_refused(refused) from None
    return admin.view()


@app.put("/v1/admin/models/engines/{name}", dependencies=_MANAGE_MODELS)
async def models_admin_edit_engine_route(
    name: str, request: Request, principal: PrincipalDep, admin: ModelAdminDep
) -> ModelsAdminView:
    body = await _model_admin_body(request, EngineInput)
    try:
        await admin.edit_engine(principal.id, name, body.provider)
    except model_admin_module.ModelAdminRefused as refused:
        raise _model_admin_refused(refused) from None
    return admin.view()


@app.delete("/v1/admin/models/engines/{name}", dependencies=_MANAGE_MODELS)
async def models_admin_remove_engine_route(
    name: str, principal: PrincipalDep, admin: ModelAdminDep
) -> ModelsAdminView:
    try:
        await admin.remove_engine(principal.id, name)
    except model_admin_module.ModelAdminRefused as refused:
        raise _model_admin_refused(refused) from None
    return admin.view()


@app.put("/v1/admin/models/defaults", dependencies=_MANAGE_MODELS)
async def models_admin_defaults_route(
    request: Request, principal: PrincipalDep, admin: ModelAdminDep
) -> ModelsAdminView:
    body = await _model_admin_body(request, DefaultsInput)
    try:
        await admin.set_defaults(principal.id, body.defaults)
    except model_admin_module.ModelAdminRefused as refused:
        raise _model_admin_refused(refused) from None
    return admin.view()


_KEY_BODY_REFUSED = (
    'Send the key as JSON, {"key": "…"}, at most 4096 characters. Nothing was changed.'
)


@app.put("/v1/admin/models/engines/{name}/key", dependencies=_MANAGE_MODELS)
async def models_admin_set_key_route(
    name: str, request: Request, principal: PrincipalDep, admin: ModelAdminDep
) -> ModelsAdminView:
    """Write-only. The body is read here rather than by FastAPI, whose validation errors carry the
    input back; a body that is not `{"key": "…"}` is refused in fixed words."""
    try:
        key = KeyInput.model_validate_json(await request.body()).key
    except ValueError:
        raise HTTPException(
            status_code=422, detail={"error": "key_refused", "detail": _KEY_BODY_REFUSED}
        ) from None
    try:
        await admin.set_key(principal.id, name, key)
    except model_admin_module.ModelAdminRefused as refused:
        raise _model_admin_refused(refused) from None
    return admin.view()


@app.delete("/v1/admin/models/engines/{name}/key", dependencies=_MANAGE_MODELS)
async def models_admin_remove_key_route(
    name: str, principal: PrincipalDep, admin: ModelAdminDep
) -> ModelsAdminView:
    try:
        await admin.remove_key(principal.id, name)
    except model_admin_module.ModelAdminRefused as refused:
        raise _model_admin_refused(refused) from None
    return admin.view()


@app.put("/v1/admin/models/engines/{name}/limits", dependencies=_MANAGE_MODELS)
async def models_admin_limits_route(
    name: str, request: Request, principal: PrincipalDep, admin: ModelAdminDep
) -> ModelsAdminView:
    """ADR-135 Amendment 3: an engine's limits, applied by the gateway to the engine's own key and
    audited."""
    body = await _model_admin_body(request, LimitsInput)
    try:
        await admin.set_limits(principal.id, name, body.limits)
    except model_admin_module.ModelAdminRefused as refused:
        raise _model_admin_refused(refused) from None
    return admin.view()


@app.get("/v1/admin/models/usage", dependencies=_MANAGE_MODELS)
async def models_admin_usage_route(
    admin: ModelAdminDep, start: date | None = None, end: date | None = None
) -> ModelUsageView:
    """ADR-135 Amendment 3: calls and tokens per engine and job from the gateway's own records,
    over whole UTC days (the last 30 by default). Counts only; no figure per person."""
    last = end or datetime.now(UTC).date()
    first = start or last - timedelta(days=29)
    try:
        return await model_usage_module.usage_view(admin, first, last)
    except model_admin_module.ModelAdminRefused as refused:
        raise _model_admin_refused(refused) from None
    except UsageUnavailableError as unavailable:
        raise HTTPException(
            status_code=502, detail={"error": "model_usage_unavailable", "detail": str(unavailable)}
        ) from None


@app.post("/v1/admin/models/engines/{name}/test", dependencies=_MANAGE_MODELS)
async def models_admin_test_route(
    name: str, principal: PrincipalDep, admin: ModelAdminDep
) -> ConnectionTestResult:
    try:
        return await admin.test(principal.id, name)
    except model_admin_module.ModelAdminRefused as refused:
        raise _model_admin_refused(refused) from None


@app.get("/v1/models/engines")
async def model_engines_route(principal: PrincipalDep, routes: ModelRoutesDep) -> OfferedEngines:
    """ADR-135 decision 5: the engines an analyst may choose for Ask the case and Ask to search —
    the local engine and each enabled engine that has a key — with each one's label and the roles
    it is the default for. Any signed-in person; nothing about a key, not even whether one exists
    (an engine with none is simply not listed). The route still decides each request."""
    return OfferedEngines(engines=routes.offered())


@app.get("/v1/investigations/{investigation_id}/models/engines")
async def case_model_engines_route(
    investigation: InvestigationViewerDep,
    principal: PrincipalDep,
    routes: ModelRoutesDep,
    datasets: DatasetsDep,
) -> OfferedEngines:
    """ADR-136 decision 3: the engines offered, as for `GET /v1/models/engines`, with each one's
    contract mark, and an engine the case's data may not reach listed unavailable with the reason in
    words. The case's datasets are read from the store, as the routing reads them for Ask the case;
    a Viewer of the case may ask (anyone else is told the case is not there). Each request is still
    decided by the route, by its own handling code and datasets.

    ADR-099 Amendment 11: the datasets are those the store names to the caller, so a caller holding
    no right is given the reason for data not known — no name, and no count. For anyone else that is
    every dataset of the case (`investigation_datasets` refers only to registered datasets).

    ADR-143 decision 1, ADR-099 Amendment 12: judged over the case's read set, as the routing judges
    a request (a composite's members and its own id, and the case's layer, named as its source by
    `datasets.as_its_case`), so an engine shown available is one the routing will not refuse."""
    named = await datasets.of_case(investigation.id, principal)
    case_datasets = await datasets.ids_of_case(investigation.id) if named else []
    held = await datasets.egress_of(case_datasets)
    return OfferedEngines(engines=routes.offered(case_datasets, held))


@app.get(
    "/v1/admin/settings/dataset-owners",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def read_dataset_owner_setting(datasets: DatasetsDep) -> DatasetOwnerSetting:
    """Admin › System's *Dataset owners may be* (ADR-145 Amendment 4 decision 7): people and teams
    (the default), people only, or teams only. It governs *Make live*'s owner step."""
    return DatasetOwnerSetting(owners_may_be=await datasets.owner_setting())


@app.put(
    "/v1/admin/settings/dataset-owners",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def set_dataset_owner_setting(
    body: DatasetOwnerSetting, principal: PrincipalDep, datasets: DatasetsDep, audit: AuditDep
) -> DatasetOwnerSetting:
    before = await datasets.owner_setting()
    await datasets.set_owner_setting(body.owners_may_be)
    await audit.record(
        principal=principal,
        action="set_dataset_owner_setting",
        resolved_query={"before": before, "after": body.owners_may_be},
        result_cardinality=1,
    )
    return body


# --- Admin › Audit (ADR-145 decision 10, O2) and Operations' ageing (decision 9, O3) — L2.6 ------


class AuditFiltersRefused(Exception):
    def __init__(self, words: str) -> None:
        super().__init__(words)
        self.words = words


@app.exception_handler(AuditFiltersRefused)
async def _audit_filters_refused_handler(
    request: Request, exc: AuditFiltersRefused
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "audit_filters", "detail": exc.words})


async def _served_audit(
    principal: Principal,
    audit: AuditWriter,
    entries: list[AuditSectionEntry],
    *,
    held_in: str,
    who: str | None,
    filters: audit_section_module.StreamFilters,
    total: int,
    offset: int,
    limit: int,
    note: str | None,
    people: list[str],
) -> AuditSectionPage:
    """Audits the read and serves the page; every entry is already named (ADR-106 decision 3:
    names asked for only the accounts the page serves), so the page carries no account's id."""
    await audit.record(
        principal=principal,
        action="read_audit_section",
        investigation_id=filters.investigation_id if held_in == "rules" else None,
        resolved_query={
            "held_in": held_in,
            "kind": filters.kind,
            "who": who,
            "case": filters.investigation_id,
            "dataset": filters.dataset_id,
            "since": filters.since.isoformat() if filters.since else None,
            "until": filters.until.isoformat() if filters.until else None,
            "offset": offset,
            "limit": limit,
        },
        result_cardinality=len(entries),
    )
    return AuditSectionPage(
        entries=entries, total=total, offset=offset, limit=limit, note=note, people=people
    )


async def _people_choice(
    principal_names: PrincipalNameDirectory, writers: set[str], who: str | None
) -> tuple[list[str], tuple[str, ...] | None]:
    """The picker's names, and the accounts a chosen name stands for. Names are asked only for
    accounts whose entries this reader may already read (ADR-106 decision 3); one with no name is
    not offered, since it could be chosen only by its id."""
    names = await principal_names.full_names(writers)
    people = sorted(set(names.values()))
    if who is None:
        return people, None
    return people, audit_section_module.accounts_named(names, who, writers)


@app.get("/v1/admin/audit", dependencies=[Depends(require_right(Right.READ_AUDIT))])
async def read_audit_section(
    principal: PrincipalDep,
    reader: AuditSectionDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
    handling_scheme: HandlingSchemeDep,
    kind: Annotated[str | None, Query(max_length=40)] = None,
    who: Annotated[str | None, Query(max_length=200)] = None,
    case: Annotated[str | None, Query(max_length=200)] = None,
    dataset: Annotated[str | None, Query(max_length=200)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditSectionPage:
    """Admin › Audit's stream (`audit_section.py`): by unit in its `WHERE` clause, a case's
    entries only for the unit's administrator (ADR-052 §4), words withheld but where the reader's
    own section shows them, and no account's id anywhere (rule 7): who by name, `who` a name from
    the page's own `people`. Every filter narrows; none widens."""
    if kind and kind not in audit_section_module.STREAM_KINDS:
        raise AuditFiltersRefused(f"{kind!r} is not a kind of this record")
    rights = rights_for(principal.roles)
    cases = ADMIN_ROLE in principal.roles
    # An entry naming a screening list only for a reader cleared for it, in the read (ADR-146
    # Amendment 7; the orchestrator's re-check of lane/rules-lists at 6bfc8d6, must 3).
    lists_cleared = ListClearance.of(principal, handling_scheme)
    people, accounts = await _people_choice(
        principal_names,
        await reader.writers(principal, cases=cases, lists_cleared=lists_cleared),
        who or None,
    )
    filters = audit_section_module.StreamFilters(
        who=accounts, kind=kind or None, investigation_id=case or None,
        dataset_id=dataset or None, since=since, until=until,
    )  # fmt: skip
    rows, total = await reader.stream(
        principal, filters, offset=offset, limit=limit, rights=rights, cases=cases,
        lists_cleared=lists_cleared,
    )  # fmt: skip
    names = await principal_names.full_names(audit_section_module.ids_to_name(rows, rights))
    note = audit_section_module.stream_note(cases, await reader.units_from())
    return await _served_audit(
        principal, audit, audit_section_module.stream_entries(rows, rights, names),
        held_in="case_and_admin", who=who or None, filters=filters, total=total, offset=offset,
        limit=limit, note=note, people=people,
    )  # fmt: skip


@app.get(
    "/v1/admin/audit/rules",
    dependencies=[
        Depends(require_right(Right.READ_AUDIT)),
        Depends(require_right(Right.READ_RULE_AUDIT)),
        Depends(require_admin_role),
    ],
)
async def read_audit_section_rules(
    principal: PrincipalDep,
    audit: AuditDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    analytics: AnalyticsDep,
    alerts_store: AlertsStoreDep,
    screening_lists: OptionalScreeningListsDep,
    principal_names: PrincipalNamesDep,
    case: Annotated[str, Query(min_length=1, max_length=200)],
    who: Annotated[str | None, Query(max_length=200)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditSectionPage:
    """A case's rule audit in Admin › Audit, for the Administrator only (the orchestrator's
    settlement on rules' Q2 (a), ADR-146 Amendment 2 point 2, on the owner's list for review;
    ADR-145 Amendment 6 records the exception to ADR-146 Amendment 2 point 3). Read through
    `readable_rule_audit` behind the case rule-audit route's own gate, whole before any filter, so a
    filter narrows only what that read already withheld."""
    case_ = await _authorize(
        case, principal, investigations, audit, AccessLevel.AUTHOR, admin_safety_net=True
    )
    whole = await readable_rule_audit(
        audit, graph, case_.id, principal, analytics=analytics, alerts=alerts_store,
        lists=screening_lists, offset=0, limit=10**9,
    )  # fmt: skip
    people, accounts = await _people_choice(
        principal_names, {e.principal_id for e in whole.entries}, who or None
    )
    filters = audit_section_module.StreamFilters(
        who=accounts, investigation_id=case, since=since, until=until
    )
    kept = [
        e for e in whole.entries
        if (filters.who is None or e.principal_id in filters.who)
        and (filters.since is None or e.recorded_at >= filters.since)
        and (filters.until is None or e.recorded_at < filters.until)
    ]  # fmt: skip
    served = kept[offset : offset + limit]
    names = await principal_names.full_names({e.principal_id for e in served})
    entries = [
        AuditSectionEntry(
            recorded_at=e.recorded_at,
            who=names.get(e.principal_id, audit_section_module.NO_NAME),
            action=e.action,
            kind="rules",
            held_in="rules",
            investigation_id=case_.id,
            case_name=case_.name,
            detail=e.detail,
            result_cardinality=e.result_cardinality,
        )  # fmt: skip
        for e in served
    ]
    return await _served_audit(
        principal, audit, entries, held_in="rules", who=who or None, filters=filters,
        total=len(kept), offset=offset, limit=limit, note=None, people=people,
    )  # fmt: skip


@app.get(
    "/v1/admin/audit/models",
    dependencies=[
        Depends(require_right(Right.READ_AUDIT)),
        Depends(require_right(Right.MANAGE_MODELS)),
    ],
)
async def read_audit_section_models(
    principal: PrincipalDep,
    reader: AuditSectionDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
    who: Annotated[str | None, Query(max_length=200)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditSectionPage:
    """The engines' history in Admin › Audit, only for a holder of `manage_models` too, who reads it
    in *Models* already (the orchestrator's ruling: it names people of every unit)."""
    people, accounts = await _people_choice(
        principal_names, await reader.model_writers(), who or None
    )
    filters = audit_section_module.StreamFilters(who=accounts, since=since, until=until)
    raw, total = await reader.model_history(filters, offset=offset, limit=limit)
    names = await principal_names.full_names({e.who for e in raw})
    return await _served_audit(
        principal, audit, audit_section_module.name_entries(raw, names), held_in="models",
        who=who or None, filters=filters, total=total, offset=offset, limit=limit,
        note="Engines are the deployment's, so their history is not a unit's.", people=people,
    )  # fmt: skip


@app.get(
    "/v1/admin/operations/ageing", dependencies=[Depends(require_right(Right.OPERATE_SCHEDULES))]
)
async def read_operations_ageing(
    principal: PrincipalDep,
    ageing: PromotionAgeingDep,
    waiting: WaitingPromotionsDep,
    audit: AuditDep,
    principal_names: PrincipalNamesDep,
) -> OperationsAgeing:
    """Operations' ageing (O3): what ages and when, and the promotions waiting for review, each
    with its age and whether it is overdue. The promotions come from the seam case's L3.4 fills,
    filtered there as this reader (rule 3); until then none is recorded, and the screen says so."""
    days = await ageing.alert_after_days()
    now = datetime.now(UTC)
    served = await waiting.waiting_for_review(principal)
    # ADR-106 decision 3: names asked only for the proposers of the rows served; never an id.
    names = await principal_names.full_names({p.proposed_by for p in served}) if served else {}
    rows = [promotion_ageing_module.waiting_row(p, now, days, names) for p in served]
    await audit.record(
        principal=principal,
        action="read_operations_ageing",
        resolved_query={"alert_after_days": days},
        result_cardinality=len(rows),
    )
    return OperationsAgeing(
        alert_after_days=days,
        rules=promotion_ageing_module.ageing_rules(days),
        waiting=rows,
        promotions_recorded=bool(getattr(waiting, "recorded", False)),
    )


@app.put(
    "/v1/admin/settings/promotion-alert-days",
    dependencies=[Depends(require_right(Right.OPERATE_SCHEDULES))],
)
async def set_promotion_alert_days(
    body: PromotionAlertSetting,
    principal: PrincipalDep,
    ageing: PromotionAgeingDep,
    audit: AuditDep,
) -> PromotionAlertSetting:
    """*Alert the reviewers and administrators after N days* (decision 9), audited."""
    before = await ageing.alert_after_days()
    await ageing.set_alert_after_days(body.alert_after_days)
    await audit.record(
        principal=principal,
        action="set_promotion_alert_days",
        resolved_query={"before": before, "after": body.alert_after_days},
        result_cardinality=1,
    )
    return body


@app.get("/v1/admin/datasets", dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))])
async def admin_datasets_route(datasets: DatasetsDep) -> list[AdminDataset]:
    """ADR-136 decision 2: every dataset of the deployment, with the unit that holds it and its
    egress, for the administrator who sets where each may go. Names and settings only: nothing of
    what a dataset holds, and no count. ADR-145 Amendment 4 decision 6: its kind and, decision 8,
    its promotion policy."""
    return [_admin_dataset(d) for d in await datasets.list_all()]


def _admin_dataset(d: Dataset) -> AdminDataset:
    return AdminDataset(
        id=d.id, name=d.name, owning_unit=d.owning_unit, egress=d.egress,
        highest_marking=d.highest_marking,
        kind="composite" if d.kind == "composite" else "drawn" if d.kind == DRAWN else "source",
        promotion_policy=d.promotion_policy,
    )  # fmt: skip


@app.put(
    "/v1/admin/datasets/{dataset_id}/egress",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def set_dataset_egress_route(
    dataset_id: str,
    body: DatasetEgressInput,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    audit: AuditDep,
) -> AdminDataset:
    """ADR-136 decision 2: an administrator sets where a dataset's material may go — `none`,
    `contracted` or `any` — and each change is audited: who (the principal), when (the audit row's
    own time), and from what to what."""
    before, changed = await datasets.set_egress(dataset_id, body.egress)
    await audit.record(
        principal=principal,
        action="set_dataset_egress",
        resolved_query={"dataset_id": dataset_id, "before": before, "after": changed.egress},
        result_cardinality=1,
    )
    return _admin_dataset(changed)


@app.put(
    "/v1/admin/datasets/{dataset_id}/promotion-policy",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def set_dataset_promotion_policy_route(
    dataset_id: str,
    body: DatasetPromotionPolicyInput,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    audit: AuditDep,
) -> AdminDataset:
    """ADR-145 decision 8: *Author promotes* or *Second person reviews*, set by an administrator
    and audited (who, when, from what to what). The promotion enforces it (L3.4). A composite
    holds no drawn items of its own, so it has none: 409 `composite_read_only`."""
    if (await _admin_dataset_of(datasets, dataset_id)).kind == "composite":
        raise LayerActionRefused(
            409, "composite_read_only",
            "A composite holds none of its members' data, so nothing is promoted into it: set "
            "each member's promotion policy instead.",
        )  # fmt: skip
    before, changed = await datasets.set_promotion_policy(dataset_id, body.promotion_policy)
    await audit.record(
        principal=principal,
        action="set_dataset_promotion_policy",
        resolved_query={
            "dataset_id": dataset_id, "before": before, "after": changed.promotion_policy
        },
        result_cardinality=1,
    )  # fmt: skip
    return _admin_dataset(changed)


async def _admin_dataset_of(datasets: DatasetStore, dataset_id: str) -> Dataset:
    """A dataset Admin › Datasets lists (never a layer), or the egress route's 404."""
    found = (await datasets.egress_of([dataset_id])).get(dataset_id)
    if found is None or found.kind == "analyst_layer":
        raise UnknownDatasetEgressError(dataset_id)
    return found


async def _promotion_recipients(
    app: FastAPI,
    p: promotion_ageing_module.PendingPromotion,
    people: Sequence[PersonAccount] | None = None,
) -> list[str]:
    """Decision 11's recipients of one overdue promotion, read now (at the sweep, and again at
    each read of `alerts_for`): the dataset's home case's Authors holding `review_promotions` and
    its unit's administrators, cleared to its marking (`promotion_ageing.recipients_of`). The
    dataset's unit and marking are read as they stand now, not as the promotion recorded them, and
    a dataset no longer held has no recipients. The items' own marking is the promotion's, as the
    seam holds it now, so a dataset lowered while it waits widens nothing (CARRIES row 46). A
    team's grant is not expanded to its members."""
    current = (await app.state.datasets.egress_of([p.dataset_id])).get(p.dataset_id)
    if current is None:
        return []
    p = dataclass_replace(
        p, dataset_unit=current.owning_unit, dataset_marking=current.highest_marking
    )
    home = await app.state.datasets.home_case_of(p.dataset_id)
    authors = await _authors_of(app.state.investigations, home.investigation_id) if home else []
    if people is None:  # a read of several alerts passes the people it read once (L2.7)
        people = await app.state.identity_admin.list_people()
    store = getattr(app.state, "custom_roles", None)
    custom = await store.current_rights() if store is not None else {}
    return promotion_ageing_module.recipients_of(
        p, authors, people, custom, app.state.handling_scheme
    )


def waiting_promotions_seam(
    promotion_store: PromotionStore,
    datasets: DatasetStore,
    investigations: InvestigationStore,
    custom_roles: Any,
    scheme: HandlingScheme,
) -> WaitingFromStore:
    """Admin's seam (`promotion_ageing.WaitingPromotions`, ADR-145 Amendment 6) over L3.4's
    promotion record: a waiting promotion listed only to one who `may_review` it, asked of the
    dataset as it is now (its unit and highest marking, its home case's Authors, custom roles by
    their current rights), the reviewable datasets passed into the store's query (rule 3)."""

    async def authors_of(dataset_id: str) -> list[str]:
        home = await datasets.home_case_of(dataset_id)
        return await _authors_of(investigations, home.investigation_id) if home else []

    async def custom() -> Mapping[str, Any]:
        return await custom_roles.current_rights() if custom_roles is not None else {}

    return WaitingFromStore(
        store=promotion_store, datasets=datasets, pending=promotion_ageing_module.PendingPromotion,
        may_review=promotion_ageing_module.may_review, authors_of=authors_of, scheme=scheme,
        custom=custom,
    )  # fmt: skip


async def _authors_of(investigations: InvestigationStore, home_case_id: str) -> list[str]:
    grants = await investigations.list_grants(home_case_id)
    return sorted(a for a, level in grants.items() if level == AccessLevel.AUTHOR)


def approver_ids(
    authors: Sequence[str],
    roles_of: Mapping[str, Sequence[str]],
    custom: Mapping[str, Iterable[Right]] | None = None,
) -> list[str]:
    """ADR-145 decision 8 and ADR-112 Amendment 4: a dataset's Authors who may approve another's
    promotion under *Second person reviews*: those whose roles hold `review_promotions`, a custom
    role's by its current rights (ADR-145 Amendment 5)."""
    return [
        a for a in authors if Right.REVIEW_PROMOTIONS in rights_for(roles_of.get(a, ()), custom)
    ]


@app.get(
    "/v1/admin/datasets/{dataset_id}/authors",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def admin_dataset_authors_route(
    dataset_id: str,
    request: Request,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
) -> AdminDatasetAuthors:
    """ADR-145 Amendment 4 decision 3: a dataset's Authors, its home case's Authors, by account and
    name, each marked when they may approve a promotion. Nothing of the home case's contents."""
    await _admin_dataset_of(datasets, dataset_id)
    home = await datasets.home_case_of(dataset_id)
    if home is None:
        return AdminDatasetAuthors(dataset_id=dataset_id, has_home_case=False)
    held = await _authors_of(investigations, home.investigation_id)
    # ADR-145 Amendment 5 point 5: a team's grant is the team, named apart from the people.
    teams = [a[len(TEAM_GRANT_PREFIX) :] for a in held if a.startswith(TEAM_GRANT_PREFIX)]
    authors = [a for a in held if not a.startswith(TEAM_GRANT_PREFIX)]
    # `people` is the direct grants only, so *Change owner…* prefilled from it never turns a
    # team's ownership into personal grants; the team is `team`.
    people = await get_identity_admin(request).list_people()
    names = await get_principal_names(request).display_names(authors) if authors else {}
    roles_of = {p.id: p.roles for p in people}
    store = getattr(request.app.state, "custom_roles", None)
    custom = await store.current_rights() if store is not None else {}
    approves = set(approver_ids(authors, roles_of, custom))
    return AdminDatasetAuthors(
        dataset_id=dataset_id,
        has_home_case=True,
        people=[DatasetAuthor(id=a, name=names.get(a), approves=a in approves) for a in authors],
        team=teams[0] if teams else None,
    )


@app.put(
    "/v1/admin/datasets/{dataset_id}/owners",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def change_dataset_owners_route(
    dataset_id: str,
    body: DatasetOwners,
    request: Request,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> AdminDatasetAuthors:
    """*Change owner…* (ADR-145 Amendment 4 decision 6): the same choice *Make live* offers, under
    the same refusals (`_owners_allowed`: Admin › System's setting, a team that exists, never a
    service account), audited. The named people become the home case's Authors and
    every other Author's grant ends. A dataset not yet live has no home case, so its owners are
    named at its first *Make live*, not here."""
    await _admin_dataset_of(datasets, dataset_id)
    home = await datasets.home_case_of(dataset_id)
    if home is None:
        raise OwnerNeeded(
            "this dataset is not live yet: who answers for it is asked at its first Make live"
        )
    owners = await _owners_allowed(request, datasets, body)

    async def audited(conn: Any, before: list[str]) -> None:
        await audit.record(
            principal=principal,
            action="change_dataset_owners",
            investigation_id=home.investigation_id,
            resolved_query={"dataset_id": dataset_id, "before": before, "after": owners},
            result_cardinality=len(owners),
            conn=conn,
        )

    # One transaction: the grants, their history and the audit entry commit or fail together.
    await investigations.replace_authors(home.investigation_id, owners, by=principal, audit=audited)
    return await admin_dataset_authors_route(dataset_id, request, datasets, investigations)


async def _linked_cases(
    dataset: Dataset,
    datasets: DatasetStore,
    investigations: InvestigationStore,
    graph: GraphPort,
    reader: Principal,
    *,
    only: str | None = None,
) -> list[AdminLinkedCase]:
    """ADR-143 Amendment 2 decision 2: every case linked to `dataset` (or `only` that one), its
    state and its layer as counts, taken by the graph store under the reader's own handling (rule
    3: `dataset_footprints` counts only what `reader` may read, and returns numbers only). A
    removed case's row carries exactly an open one's fields."""
    case_ids = [c for c in await datasets.cases_reading(dataset.id) if only in (None, c)]
    states = await investigations.admin_states(case_ids)
    home = await datasets.home_case_of(dataset.id)
    layers = {c: await datasets.layer_of_case(c) for c in case_ids}
    held = await graph.dataset_footprints(
        [lay for lay in layers.values() if lay is not None], reader
    )
    rows: list[AdminLinkedCase] = []
    for case_id in case_ids:
        if case_id not in states:
            continue
        name, removed = states[case_id]
        chosen = await datasets.chosen_of_case(case_id)
        through = None if any(d.id == dataset.id for d in chosen) else (
            chosen[0].name if chosen else None
        )  # fmt: skip
        layer = layers[case_id]
        counted = held.get(layer) if layer is not None else None
        rows.append(
            AdminLinkedCase(
                investigation_id=case_id,
                name=name,
                state="removed" if removed else "open",
                home_case=home is not None and home.investigation_id == case_id,
                through=through,
                items=counted.nodes if counted else 0,
                links=counted.edges if counted else 0,
                size_bytes=counted.properties_bytes + counted.picture_bytes if counted else 0,
            )
        )
    return rows


@app.get(
    "/v1/admin/datasets/{dataset_id}/cases",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def admin_dataset_cases_route(
    dataset_id: str,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    audit: AuditDep,
) -> AdminDatasetCases:
    """Admin › Datasets' linked cases (ADR-143 Amendment 2 decision 2): an administrator sees, for
    every case, member or not, its name, state and layer's counts, and never the layer's contents:
    no item, label or property (`test_admin_dataset_cases.py`). Audited, since it reads across
    cases."""
    dataset = await _admin_dataset_of(datasets, dataset_id)
    cases = await _linked_cases(dataset, datasets, investigations, graph, principal)
    await audit.record(
        principal=principal,
        action="list_dataset_cases",
        resolved_query={"dataset_id": dataset_id},
        result_cardinality=len(cases),
    )
    return AdminDatasetCases(dataset_id=dataset_id, cases=cases)


class LayerActionRefused(Exception):
    """A removed case's *Merge into the dataset* or *Delete* refused, in words (ADR-143 Amendment
    2 decision 1)."""

    def __init__(
        self, status_code: int, error: str, words: str, right: Right | None = None
    ) -> None:
        super().__init__(words)
        self.status_code, self.error, self.words = status_code, error, words
        #: The right whose roles the Glass names (ADR-145 Amendment 4 decision 12), never a person.
        self.right = right


@app.exception_handler(LayerActionRefused)
async def _layer_action_refused_handler(request: Request, exc: LayerActionRefused) -> JSONResponse:
    content: dict[str, str] = {"error": exc.error, "detail": exc.words}
    if exc.right is not None:
        content["right"] = exc.right.value
    return JSONResponse(status_code=exc.status_code, content=content)


def _size_words(size: int) -> str:
    return f"{size} bytes" if size < 1024 else (
        f"{size / 1024:.1f} kB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"
    )  # fmt: skip


@app.post(
    "/v1/admin/datasets/{dataset_id}/cases/{investigation_id}/{action}/dry-run",
    dependencies=[Depends(require_right(Right.ADMINISTER_SYSTEM))],
)
async def layer_action_dry_run_route(
    dataset_id: str,
    investigation_id: str,
    action: str,
    request: Request,
    principal: PrincipalDep,
    datasets: DatasetsDep,
    investigations: InvestigationsDep,
    graph: GraphDep,
    audit: AuditDep,
) -> LayerDryRun:
    """A removed case's *Merge into the dataset* or *Delete*, run dry (ADR-143 Amendment 2
    decision 1): what it would touch, in counts, and nothing written but the audit entry. Refused
    for a case that is open, not linked to this dataset directly, or (to merge) when the dataset is
    a composite or the person is not one of its Authors; deleting is also an administrator's.
    Another unit's administrator is answered as for no dataset, before anything is read (the
    owner's ruling (a) of 9 November 2026). The merge and the delete themselves are done by the
    dataset's Authors in the Studio's *4 Runs* (L3.4), and Admin's own Delete is its route below.

    `action` is read as text and checked here, after the route's right: typed as `LayerAction`,
    FastAPI refused an unknown one (422) before `require_right` ran, so a caller without the right
    learnt the route's shape (case's live run, 8 November). An unknown action is 404."""
    if action not in get_args(LayerAction):
        raise HTTPException(status_code=404, detail={"error": "no_such_action"})
    action = cast(LayerAction, action)
    dataset = await _admin_dataset_of(datasets, dataset_id)
    # The owner's ruling (a) of 9 November 2026 (ADR-143 Amendment 5), as Admin's Delete: another
    # unit's administrator, or one with none, is answered as for no dataset before anything is
    # read.
    if principal.org_unit is None or dataset.owning_unit != principal.org_unit:
        raise UnknownDatasetEgressError(dataset_id)
    row = next(
        (c for c in await _linked_cases(dataset, datasets, investigations, graph, principal,
                                        only=investigation_id)
         if c.through is None),
        None,
    )  # fmt: skip
    if row is None:
        raise LayerActionRefused(404, "case_not_linked", "That case does not read this dataset.")
    if row.state != "removed":
        raise LayerActionRefused(
            409, "case_open",
            "Only a removed case's layer can be merged or deleted: this case is still open.",
        )  # fmt: skip
    if action == "merge":
        if dataset.kind == "composite":
            raise LayerActionRefused(
                409, "composite_read_only",
                "Nothing can be merged into a composite: it holds none of its members' data.",
            )  # fmt: skip
        home = await datasets.home_case_of(dataset_id)
        authors = await _authors_of(investigations, home.investigation_id) if home else []
        if principal.id not in authors:
            # ADR-145 Amendment 4 decision 12, as the owner ruled it ((c), Amendment 7; L2.5c): the
            # level and the right that may act, whose roles the Glass names, never who holds them.
            raise LayerActionRefused(
                403, "not_an_author",
                "Only one of the dataset's Authors may merge a removed case's layer into it, in "
                "the Ingest Studio's 4 Runs: an Author of its home case."
                + ("" if authors else
                   " It has no Authors yet: they are named at its first Make live."),
                right=Right.INVESTIGATE,
            )  # fmt: skip
    counts = f"{row.items} items and {row.links} links ({_size_words(row.size_bytes)})"
    policy = "the Author promotes" if dataset.promotion_policy == "author_promotes" else (
        "a second person reviews"
    )  # fmt: skip
    would = (
        f"Would merge {counts} from {row.name}'s layer into {dataset.name}, as one load under its "
        f"promotion policy ({policy}). Nothing has been written."
        if action == "merge"
        # ADR-143 Amendment 5 decision 11: the layer's counts and what deleting withdraws, never
        # "would delete N" (the counts include promoted items, which the delete never touches);
        # the Studio's dry run's words (L2.5c).
        else f"{row.name}'s layer holds {counts}. Deleting it withdraws those not promoted; "
        "promoted items are never touched. Nothing has been written."
    )
    await audit.record(
        principal=principal,
        action=f"dry_run_layer_{action}",
        investigation_id=investigation_id,
        resolved_query={"dataset_id": dataset_id, "action": action},
        result_cardinality=row.items + row.links,
    )
    return LayerDryRun(
        investigation_id=investigation_id, action=action, items=row.items, links=row.links,
        size_bytes=row.size_bytes, would=would,
    )  # fmt: skip


@app.exception_handler(UnknownDatasetEgressError)
async def _unknown_dataset_egress_handler(
    request: Request, exc: UnknownDatasetEgressError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "dataset_not_found", "detail": "There is no such dataset."},
    )


@app.post("/v1/ws-ticket", response_model=WsTicketResponse)
async def issue_ws_ticket(
    request: Request, principal: PrincipalDep, valkey: ValkeyDep
) -> WsTicketResponse:
    """`06_DECISIONS.md` ADR-050 objection 8. Authenticated the ordinary way — the same bearer
    token every other `/v1` route already requires — this mints a short-lived, single-use ticket
    bound to the calling principal and returns it; the caller opens the delta WebSocket with
    `?ticket=<this>` instead of putting its own bearer token in that URL. See
    `services.api.ws_ticket`'s own module docstring for why a ticket, why Valkey, and why 30
    seconds."""
    # ADR-145 Amendment 5: the ticket holds the token's own roles, never a custom role's rights as
    # they were at minting; the socket reads those afresh (`_authenticate_websocket`, `_admission`).
    roles = getattr(request.state, "token_roles", None)
    raw = principal if roles is None else principal.model_copy(update={"roles": list(roles)})
    ticket = await mint_ws_ticket(valkey, raw)
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
        return await resolver.resolve_principal(token)

    ticket = websocket.query_params.get("ticket", "")
    if not ticket:
        raise PrincipalResolutionError("missing bearer token or ws-ticket")
    valkey: Valkey = websocket.app.state.valkey
    principal = await redeem_ws_ticket(valkey, ticket)
    if principal is None:
        raise PrincipalResolutionError("ws-ticket is missing, expired, or already redeemed")
    return principal


async def _socket_standing(app_: Any, raw: Principal) -> int | None:
    """ADR-148 Amendment 8: on Entra ID sign-in, whether the socket's principal still stands as
    the people store has them now, since a socket (or a ticket minted before a change) outlives the
    request that resolved it. `None` when it stands (or on Keycloak, with no store); the close code
    otherwise: 1008 for a person disabled, gone or whose roles changed (they sign in again, and the
    one construction path builds their principal afresh), 1013 when the store cannot answer, never
    a socket left open on a read that failed."""
    store = getattr(app_.state, "people_store", None)
    if store is None:
        return None
    try:
        stored = await asyncio.wait_for(store.standing(raw.id), timeout=ROLE_LOOKUP_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - every failure of the read closes the socket
        return status.WS_1013_TRY_AGAIN_LATER
    if stored is None or stored.disabled:
        return status.WS_1008_POLICY_VIOLATION
    if list(dict.fromkeys(stored.roles)) != list(raw.roles):
        return status.WS_1008_POLICY_VIOLATION
    return None


def _admission(
    app_: Any, raw: Principal, investigation_id: str
) -> Callable[[], Awaitable[Principal | int]]:
    """ADR-145 Amendment 5 ("never cached"): an open socket's principal, read afresh at each
    message: its custom roles' rights as they are now (`with_custom_roles`, the bearer and the
    ticket alike), and its case level as it is now (a grant or a team's grant taken away). Once it
    no longer stands, the code the socket is closed with: 1013 when the people store cannot answer
    (try again later), 1008 otherwise (ADR-148 Amendment 8 point 1)."""

    async def admitted() -> Principal | int:
        # ADR-148 Amendment 8: a person disabled, or whose roles changed, since the socket opened;
        # or the store not answering, which is 1013, never 1008.
        if (refused := await _socket_standing(app_, raw)) is not None:
            return refused
        principal = await with_custom_roles(app_, raw)
        try:
            await app_.state.investigations.get_authorized(
                investigation_id, principal, need=AccessLevel.VIEWER
            )
        except (InvestigationNotFoundError, InsufficientAccessError):
            return status.WS_1008_POLICY_VIOLATION
        return principal

    return admitted


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
    #: ADR-145 Amendment 5: asked before each message is acted on; a close code closes the socket.
    admitted: Callable[[], Awaitable[Principal | int]] | None = None


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
        if state.admitted is not None and isinstance(refused := await state.admitted(), int):
            await websocket.close(code=refused)
            return
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
    await purge_remarked_copies(websocket.app.state.alerts_store, working_set)  # as at connect
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
        if state.admitted is not None and isinstance(refused := await state.admitted(), int):
            await websocket.close(code=refused)
            return
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
        raw = await _authenticate_websocket(websocket)
    except PrincipalResolutionError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except PrincipalLookupUnavailable:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return
    # ADR-148 Amendment 10: the socket asks no `get_principal`, so the route gate is its own here. A
    # principal admitted to named routes alone (a dashboard identity) opens no stream; nothing of
    # the case is read for it.
    if raw.routes is not None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    # ADR-148 Amendment 8: a ticket minted before a disable or a change of roles stands no longer.
    if (refused := await _socket_standing(websocket.app, raw)) is not None:
        await websocket.close(code=refused)
        return
    # One person, one principal: the bearer's and the ticket's alike have their custom roles' rights
    # read now, as `get_principal` does (ADR-145 Amendment 5).
    principal = await with_custom_roles(websocket.app, raw)

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
    principal = await scope_to_case(
        principal,
        investigation_id,
        get_datasets(websocket),  # type: ignore[arg-type]
        holds_a_level=holds_a_level_in(lambda: get_investigations(websocket)),  # type: ignore[arg-type]
    )
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
    # ADR-109 Amendment 10 (L2.8b's R2): a node a settle re-marked leaves every working set's
    # stored copy before a canvas is sent one.
    await purge_remarked_copies(websocket.app.state.alerts_store, working_set)
    initial_deltas: list[WorkingSetDeltaSent] = await working_set.sync(
        investigation_id, principal, last_acknowledged_seq=init.get("last_acknowledged_seq")
    )
    state = _SocketState(admitted=_admission(websocket.app, raw, investigation_id))
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
