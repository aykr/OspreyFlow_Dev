"""What a recipe run is built from, constructed in one place (`06_DECISIONS.md` ADR-127
Amendment 23).

The Conduit's lifespan and the Prison Intelligence seed (a script run with the Conduit stopped, so
it builds them from the environment) both call `build_run_resources`, so a seed's load is stamped,
judged and cached exactly as the route's. A copy would drift: the stamping graph's `check_against`
(ADR-099 Amendment 6: no write names a dataset the registry does not hold) and its `after_write`
hook to the explore cache (ADR-100 Amendment 3) are the two a copy forgets, and a load made without
either looks right and is wrong.

`RunResources.run_deps()` is the `RecipeRunDeps` of `services/api/recipe_run.py`, over the stores
this holds, so the route's dependencies and the seed's are the same objects as the lifespan puts on
the application's state. This module never imports `services.api.app`.

**What the lifespan keeps for itself:** the stores no run reads (sites, history, judgements, link
notes and the rest), the model clients, the services built over the stores below, the identity
admin, the sweep and the scheduler. Only what `RecipeRunDeps` names, and what builds it, is here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from services.api.list_connector import ParquetListRows, PostgresListStore
from services.api.sources import PostgresSourceStore
from services.api.target_models import PostgresTargetModelStore, core_types_of
from services.ingest.staging import ObjectStorageConfig
from valkey.asyncio import Valkey

from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.recognise_stanza import RecogniserConfig, RecogniseStanzaAdapter
from ontology.handling import HandlingScheme, load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from ports.analytics import AnalyticsPort
from ports.compute import ComputePort
from ports.graph import GraphPort
from ports.media import MediaStore
from principal_auth import ClaimMapping
from schemas.domain import OntologySchema

from . import rule_editor
from .alerts import AlertStore
from .analytics_store import Close, open_analytics
from .audit import AuditWriter
from .auth import PrincipalResolver
from .board_store import PostgresBoardItemStore
from .cache import CachedQuery
from .config import ApiConfig
from .dataset_scope import DatasetStampingGraph, stamping
from .datasets import PostgresDatasetStore
from .entra_people import EntraPeopleStore, open_people_store
from .explore import EXPLORE_TTL_SECONDS
from .held_rows import HeldRowStore
from .hotlists import HotlistStore
from .investigations import InvestigationStore
from .jobs import JobQueue
from .kyc_expiries import KycExpiryStore
from .media_store import open_media_store
from .monitors import MonitorStore
from .pattern_store import PatternStore
from .pipeline_run import (
    OnlineGeocode,
    RecogniserFor,
    online_geocode_from_env,
    recogniser_for_deployment,
)
from .recipe_run import RecipeRunDeps
from .recipe_runs import RecipeRunStore
from .review import ExtractionCandidateStore
from .run_quotas import PostgresQuotaStore
from .screening import ScreeningListStore
from .strength_influencers import InfluencerStore
from .studio_publish import _REPO_ROOT as RECIPES_REPO_ROOT
from .typology_rules import TypologyRuleStore
from .watch_reach import DatasetReach, owner_reaches_dataset_in

__all__ = ["RECIPES_REPO_ROOT", "RunResources", "build_run_resources"]


@dataclass
class RunResources:
    """The connected stores, graph, analytics and clients a recipe run reads and writes through.
    Field names are `RecipeRunDeps`' where it has the same thing."""

    config: ApiConfig
    handling_scheme: HandlingScheme
    ontology: OntologySchema
    arcadedb_client: ArcadeDBClient
    graph: GraphPort
    valkey: Valkey
    audit: AuditWriter
    patterns_store: PatternStore
    hotlists_store: HotlistStore
    monitors_store: MonitorStore
    alerts_store: AlertStore
    typology_rules: TypologyRuleStore
    held_rows: HeldRowStore
    screening_lists: ScreeningListStore
    kyc_expiries: KycExpiryStore
    recipe_runs: RecipeRunStore
    #: ADR-141 decision 6: the run quotas every run's start judges, a seed's load among them.
    run_quotas: PostgresQuotaStore
    extraction_candidates: ExtractionCandidateStore
    datasets_store: PostgresDatasetStore
    #: The cases' levels, which a watch's owner's reach is asked of (ADR-146 Amendment 4 point 7).
    investigations: InvestigationStore
    #: ADR-140 Amendment 12: a staged pipeline's lists, and where staged rows are kept.
    target_models: PostgresTargetModelStore
    staging_storage: ObjectStorageConfig
    #: ADR-140 Amendment 13: deployment-wide lists and subscriptions, which a staged run reads.
    list_store: PostgresListStore
    #: ADR-140 Amendment 19: the registered sources, whose declared default markings a staged run's
    #: unmarked tables carry before a join.
    sources: PostgresSourceStore
    explore_cache: CachedQuery
    analytics: AnalyticsPort
    close_analytics: Close
    media: MediaStore
    recogniser: RecogniseStanzaAdapter
    recogniser_for: RecogniserFor
    online_geocode: OnlineGeocode | None
    compute: ComputePort
    jobs: JobQueue
    principal_resolver: PrincipalResolver
    #: ADR-139: installation-wide and case link-strength influencers.
    influencers: InfluencerStore
    #: L3.6: the drawn watches a load is run against (ADR-143 Amendment 2 decision 8).
    board_items: PostgresBoardItemStore
    recipe_repo_root: Path = RECIPES_REPO_ROOT
    #: ADR-148 Amendment 8: on Entra ID sign-in, the people store the resolver reads roles from.
    people_store: EntraPeopleStore | None = None

    @property
    def watch_reach(self) -> DatasetReach:
        """Whether a watch's owner still reaches its dataset, over the stores held here: a
        command-line load matches watches as the Conduit's own loads do (the L2.10 gate's finding,
        `test_run_resources.py`, which first stood this path's fail-closed gap in the open)."""
        return owner_reaches_dataset_in(self.datasets_store, self.investigations)

    @property
    def datasets(self) -> PostgresDatasetStore:
        """The run's name for the datasets store (`RecipeRunDeps.datasets`)."""
        return self.datasets_store

    @property
    def rule_lists(self) -> rule_editor.RuleListReader:
        """ADR-146 decision 3 (L2.11): a command-line run reads a rule's named Studio list within
        the rule's own dataset, over the stores held here, as the Conduit's runs do."""
        return rule_editor.rule_list_reader(
            datasets=self.datasets_store,
            models=self.target_models,
            lists=self.list_store,
            rows_kept=ParquetListRows(self.staging_storage),
        )

    @property
    def rule_reach(self) -> rule_editor.RuleReach:
        """What a rule on a declared dataset reads (a composite's members), over the stores here."""
        return rule_editor.rule_reach_of(self.datasets_store)

    def run_deps(self) -> RecipeRunDeps:
        """The dependencies of `run_recipe_as`, over the objects held here."""
        return RecipeRunDeps(
            graph=self.graph,
            ontology=self.ontology,
            analytics=self.analytics,
            media=self.media,
            recipe_repo_root=self.recipe_repo_root,
            audit=self.audit,
            jobs=self.jobs,
            valkey=self.valkey,
            handling_scheme=self.handling_scheme,
            config=self.config,
            hotlists_store=self.hotlists_store,
            monitors_store=self.monitors_store,
            patterns_store=self.patterns_store,
            alerts_store=self.alerts_store,
            principal_resolver=self.principal_resolver,
            extraction_candidates=self.extraction_candidates,
            recogniser_for=self.recogniser_for,
            online_geocode=self.online_geocode,
            typology_rules=self.typology_rules,
            held_rows=self.held_rows,
            screening_lists=self.screening_lists,
            compute=self.compute,
            kyc_expiries=self.kyc_expiries,
            recipe_runs=self.recipe_runs,
            run_quotas=self.run_quotas,
            influencers=self.influencers,
            target_models=self.target_models,
            staging_storage=self.staging_storage,
            list_store=self.list_store,
            sources=self.sources,
            rule_lists=self.rule_lists,
            rule_reach=self.rule_reach,
            watch_reach=self.watch_reach,
            board_items=self.board_items,
            datasets=self.datasets_store,
            investigations=self.investigations,
        )

    async def close(self) -> None:
        """Closes everything `build_run_resources` opened."""
        await self.arcadedb_client.aclose()
        await self.valkey.aclose()
        await self.audit.close()
        await self.patterns_store.close()
        await self.hotlists_store.close()
        await self.monitors_store.close()
        await self.alerts_store.close()
        await self.typology_rules.close()
        await self.influencers.close()
        await self.held_rows.close()
        await self.screening_lists.close()
        await self.kyc_expiries.close()
        await self.recipe_runs.close()
        await self.run_quotas.close()
        await self.extraction_candidates.close()
        await self.datasets_store.close()
        await self.investigations.close()
        await self.target_models.close()
        await self.list_store.close()
        await self.sources.close()
        await self.board_items.close()
        await self.principal_resolver.aclose()
        if self.people_store is not None:
            await self.people_store.close()
        await self.close_analytics()


async def build_run_resources(config: ApiConfig) -> RunResources:
    """Opens what a run needs, from `config` and the environment, as the Conduit's lifespan does.
    The caller closes it (`RunResources.close`)."""
    arcadedb_client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await arcadedb_client.create_database_if_absent()
    handling_scheme = load_uk_le_scheme()
    ontology = load_deployment_ontology()
    # ADR-099: the services write through `DatasetStampingGraph`, so whatever the Conduit writes
    # for a case belongs to the case's dataset (`dataset_scope.py`).
    graph: GraphPort = cast(
        GraphPort, stamping(GraphArcadeDBAdapter(arcadedb_client, handling_scheme))
    )
    await graph.apply_schema(ontology)

    valkey = Valkey(**config.valkey.client_kwargs())
    audit = await AuditWriter.connect(config.postgres.dsn)
    patterns_store = await PatternStore.connect(config.postgres.dsn)
    hotlists_store = await HotlistStore.connect(config.postgres.dsn)
    monitors_store = await MonitorStore.connect(config.postgres.dsn)
    alerts_store = await AlertStore.connect(config.postgres.dsn)
    # ADR-109: each case's typology rules, and the rows a failing pre-commit rule holds.
    typology_rules = await TypologyRuleStore.connect(config.postgres.dsn)
    # ADR-139: link-strength influencers, installation-wide (maker–checker) and per case.
    influencers = await InfluencerStore.connect(config.postgres.dsn)
    held_rows = await HeldRowStore.connect(config.postgres.dsn, handling_scheme)
    screening_lists = await ScreeningListStore.connect(config.postgres.dsn)
    kyc_expiries = await KycExpiryStore.connect(config.postgres.dsn)
    # ADR-110 decision 6: the run ledger.
    recipe_runs = await RecipeRunStore.connect(config.postgres.dsn)
    run_quotas = await PostgresQuotaStore.connect(config.postgres.dsn)
    extraction_candidates = await ExtractionCandidateStore.connect(config.postgres.dsn)
    # ADR-099: the datasets of each unit and of each case.
    datasets_store = await PostgresDatasetStore.connect(config.postgres.dsn)
    investigations = await InvestigationStore.connect(config.postgres.dsn)
    # ADR-140 Amendment 12: the datasets' domain models, whose lists a staged pipeline's Lookups
    # read, and the store their rows and the staged Parquet are kept in.
    from ontology.loader import load_default_ontology

    core = load_default_ontology()
    target_models = await PostgresTargetModelStore.connect(
        config.postgres.dsn,
        core_types=core_types_of(
            [e.name for e in core.entity_types], [e.name for e in core.edge_types]
        ),
    )
    staging_storage = ObjectStorageConfig.from_env()
    list_store = await PostgresListStore.connect(config.postgres.dsn)
    sources = await PostgresSourceStore.connect(config.postgres.dsn)
    # L3.6: a command-line load runs the drawn watches on its dataset, as the Conduit's do.
    board_items = await PostgresBoardItemStore.connect(config.postgres.dsn)
    # ADR-099 Amendment 6: no write names a dataset the registry does not hold.
    cast(DatasetStampingGraph, graph).check_against(datasets_store)

    # The store `components.analytics_engine` names (ADR-114 decision 9): a DuckDB file on a
    # single machine, ClickHouse where Conduits are replicated. `analytics_store.py` refuses any
    # other name rather than falling back.
    analytics, close_analytics = await open_analytics(
        config.analytics_engine,
        duckdb_path=config.analytics_db_path,
        handling_scheme=handling_scheme,
    )
    # ADR-134 decision 3: every alert written is kept in the analytics store for alert trends.
    alerts_store.fact_sink = analytics.load_alert_facts

    # ADR-100 Amendment 3: the Explore panel's figures, kept per access class, cleared on a write.
    explore_cache = CachedQuery(valkey, prefix="explore", ttl_seconds=EXPLORE_TTL_SECONDS)
    cast(DatasetStampingGraph, graph).after_write(explore_cache.invalidate_prefix)

    # ADR-094: where a content item's file is kept; never the graph.
    media = open_media_store()
    # ADR-098 decision 2: the fast recogniser, the `ner` sidecar.
    recogniser = RecogniseStanzaAdapter(RecogniserConfig.from_env())
    # ADR-108 phase C: the pipeline runner's recogniser lookup and the online geocoding
    # allow-list (`OSPREY_ONLINE_GEOCODER`), both deployment-level wiring, not per-request.
    recogniser_for = recogniser_for_deployment(recogniser)
    online_geocode = online_geocode_from_env()
    # `06_DECISIONS.md` ADR-029/Phase 7 Stage 3: Tier 2 only, registered here — stateless, no
    # client, no lifecycle to close.
    compute: ComputePort = ComputeRustworkxAdapter()
    jobs = JobQueue(valkey)
    # ADR-148 Amendment 8: the deployment's claim mapping; on Entra ID, roles from the people store.
    claim_mapping = ClaimMapping.from_env()
    people_store = await open_people_store(config.postgres.dsn, claim_mapping, audit)
    principal_resolver = PrincipalResolver(
        config, claim_mapping=claim_mapping, role_source=people_store
    )

    return RunResources(
        config=config,
        handling_scheme=handling_scheme,
        ontology=ontology,
        arcadedb_client=arcadedb_client,
        graph=graph,
        valkey=valkey,
        audit=audit,
        patterns_store=patterns_store,
        hotlists_store=hotlists_store,
        monitors_store=monitors_store,
        alerts_store=alerts_store,
        typology_rules=typology_rules,
        influencers=influencers,
        held_rows=held_rows,
        screening_lists=screening_lists,
        kyc_expiries=kyc_expiries,
        recipe_runs=recipe_runs,
        run_quotas=run_quotas,
        extraction_candidates=extraction_candidates,
        datasets_store=datasets_store,
        investigations=investigations,
        target_models=target_models,
        staging_storage=staging_storage,
        list_store=list_store,
        sources=sources,
        explore_cache=explore_cache,
        analytics=analytics,
        close_analytics=close_analytics,
        media=media,
        recogniser=recogniser,
        recogniser_for=recogniser_for,
        online_geocode=online_geocode,
        compute=compute,
        jobs=jobs,
        principal_resolver=principal_resolver,
        people_store=people_store,
        board_items=board_items,
    )
