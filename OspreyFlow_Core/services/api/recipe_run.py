"""One run of a published recipe, the same whichever path started it (`06_DECISIONS.md` ADR-110
decision 1, ADR-127 Amendment 23).

The Conduit's *Run now* route, the scheduler and the Prison Intelligence seed all call
`run_recipe_as`, so a scheduled or seeded load is judged, published, watched and resolved exactly
as a manual one, and every run is in the ledger (ADR-110 decision 6). It lives here, not in
`app.py`, so that the seed (a script run with the Conduit stopped) can call it without starting
the application: **this module never imports `services.api.app`**, and
`tests/services/api/test_recipe_run_module.py` imports it in a fresh interpreter to prove it.

The route's own checks stay in the route: the runnable recipe's clearance check, the `LOADER` role,
the case's Editor level, `RUN_PIPELINES`. `run_recipe_as` performs none of them, so a caller that is
not the route must make its own (the scheduler's `check_case` does; the seed deliberately does not).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.ingest.metering import CountingMedia, StagingMeter, metering_of
from services.ingest.staging import ObjectStorageConfig
from services.ingest.watermark import RefreshRead
from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from ontology.handling import HandlingScheme
from ports.analytics import AnalyticsPort
from ports.compute import ComputePort
from ports.graph import GraphPort
from ports.media import MediaStore
from schemas.domain import OntologySchema, Principal, TypologyRule
from schemas.ingest import LoadReport, PipelineRunReport, StudioRecipeDraft

from . import resolution_trigger as resolution_trigger_module
from .alerts import AlertStore
from .audit import AuditWriter
from .auth import PrincipalResolver
from .board_store import BoardItemStore
from .change_stream import ChangeStreamEntry, ChangeStreamWriter, touched_node_ids
from .config import ApiConfig
from .datasets import DatasetStore
from .drawn_watches import DrawnWatchesFailed, DrawnWatchRun, holds_a_level_in, raise_into
from .evaluation import DatasetReach, evaluate_hotlists_for_entry, evaluate_monitors_for_entry
from .held_rows import HeldRowStore
from .hotlists import HotlistStore
from .investigations import InvestigationStore
from .jobs import JobQueue
from .kyc_expiries import KycExpiryStore
from .list_connector import ListStore
from .load_records import LedgerSink
from .monitors import MonitorStore
from .pattern_store import PatternStore
from .pipeline_run import OnlineGeocode, RecogniserFor, run_published_pipeline
from .recipe_runs import Counted, External, RecipeRunStore, RunTrigger
from .review import ExtractionCandidateStore
from .rule_evaluation import RuleGate
from .run_quotas import QuotaLimit, QuotaRefused, QuotaStore
from .run_quotas import judge as judge_quota
from .screening import ScreeningListStore
from .sources import SourceStore
from .strength_influencers import InfluencerStore
from .studio_map import resolve_source_handling
from .studio_publish import LoadSink, run_published_recipe
from .target_models import TargetModelStore
from .typology_rules import TypologyRuleStore
from .watch_reach import owner_reaches_dataset_in

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecipeRunDeps:
    """What a recipe run needs, the same whichever path started it (ADR-110 decision 1)."""

    graph: GraphPort
    ontology: OntologySchema
    analytics: AnalyticsPort
    media: MediaStore
    recipe_repo_root: Path
    audit: AuditWriter
    jobs: JobQueue
    valkey: Valkey
    handling_scheme: HandlingScheme
    config: ApiConfig
    hotlists_store: HotlistStore
    monitors_store: MonitorStore
    patterns_store: PatternStore
    alerts_store: AlertStore
    principal_resolver: PrincipalResolver
    extraction_candidates: ExtractionCandidateStore
    recogniser_for: RecogniserFor
    online_geocode: OnlineGeocode | None
    typology_rules: TypologyRuleStore
    held_rows: HeldRowStore
    screening_lists: ScreeningListStore
    compute: ComputePort
    kyc_expiries: KycExpiryStore
    recipe_runs: RecipeRunStore
    #: ADR-139: the installation's and each case's link-strength influencers, which a sentence's
    #: strength condition judges by. None: the weights file's defaults alone.
    influencers: InfluencerStore | None = None
    #: ADR-140 Amendment 12: the datasets' models, whose reference lists a staged pipeline's
    #: Lookups read, and the store their rows and the staged Parquet are kept in. None: no list
    #: (a Lookup is refused in words) and the store the environment names.
    target_models: TargetModelStore | None = None
    staging_storage: ObjectStorageConfig | None = None
    #: ADR-140 Amendment 13: the deployment-wide lists and each dataset's subscriptions. None: a
    #: staged run reads the dataset's own lists alone.
    list_store: ListStore | None = None
    #: ADR-140 Amendment 19: the datasets' registered sources, whose declared default markings an
    #: unmarked table carries before a join. None: none is carried (a Join refuses it, fail closed).
    sources: SourceStore | None = None
    #: ADR-146 decision 3 (L2.11): how a sentence's named Studio list is read, within the rule's own
    #: dataset (`rule_editor.rule_list_reader`). None: a rule naming a list cannot run here, and
    #: says so as any run that cannot read what it needs.
    rule_lists: Callable[[TypologyRule, str, str], Awaitable[list[Any]]] | None = None
    #: ADR-146 decision 3: what a rule on a declared dataset reads (`rule_editor.rule_reach_of`).
    rule_reach: Callable[[TypologyRule], Awaitable[list[str] | None]] | None = None
    #: L2.10 review item 4: whether a watch's owner still reaches its dataset
    #: (`watch_reach.owner_reaches_dataset_in`). None: a watch with a dataset is not matched (fail
    #: closed). `from_state` always builds it from the state's own stores.
    watch_reach: DatasetReach | None = None
    #: L3.6 (ADR-143 Amendment 2 decision 8): the drawn watches a load is run against, and the
    #: case read sets their owners are read in, and the cases' levels their owners must still
    #: hold. None: no drawn watch is run (fail closed: no alert, nothing read). `from_state` reads
    #: each from the state (`board_items`, `datasets`, `investigations`).
    board_items: BoardItemStore | None = None
    datasets: DatasetStore | None = None
    investigations: Any | None = None
    #: ADR-141 decision 6: the run quotas, judged before every run starts. None: no quota.
    run_quotas: QuotaStore | None = None

    @classmethod
    def from_state(cls, state: Any) -> RecipeRunDeps:
        """The scheduler's way in: the application's state, read where the route's getters read
        it, so the two paths cannot be handed different stores."""
        values: dict[str, Any] = {}
        for f in dataclass_fields(cls):
            name = _RUN_DEP_STATE_NAMES.get(f.name, f.name)
            # An optional dependency (default None) the state does not hold is left None.
            optional = f.default is None
            values[f.name] = getattr(state, name, None) if optional else getattr(state, name)
        if values.get("watch_reach") is None:
            # L2.10 review round: the scheduled and folder-watched runs come this way. The check is
            # built from the state's own stores, which every running Conduit holds, never from a
            # field the state would have to be given (none is, so it would always be absent).
            values["watch_reach"] = owner_reaches_dataset_in(
                lambda: getattr(state, "datasets", None),
                lambda: getattr(state, "investigations", None),
            )
        datasets = getattr(state, "datasets", None)
        if datasets is not None:
            # ADR-146 decision 3 (L2.11): the scheduled and folder-watched runs read a rule's named
            # list and its dataset's reach (a composite's members) from the state's own stores, as
            # the route's getters do (`app._rule_lists_of`, `app._rule_reach_from`); the state holds
            # no attribute of either name, so read as fields they were always None on these runs.
            from . import rule_editor

            if values.get("rule_lists") is None:
                values["rule_lists"] = rule_editor.rule_list_reader(
                    datasets=datasets,
                    models=getattr(state, "target_models", None),
                    lists=getattr(state, "list_store", None),
                    rows_kept=getattr(state, "list_rows", None),
                )
            if values.get("rule_reach") is None:
                values["rule_reach"] = rule_editor.rule_reach_of(datasets)
        return cls(**values)


_RUN_DEP_STATE_NAMES = {
    "influencers": "strength_influencers",
    "recipe_repo_root": "recipes_repo_root",
    "recogniser_for": "pipeline_recogniser_for",
}


async def run_recipe_as(
    deps: RecipeRunDeps,
    *,
    principal: Principal,
    recipe: StudioRecipeDraft,
    investigation_id: str,
    source_location: str | None,
    trigger: RunTrigger,
    slot: datetime | None = None,
    source_file: str | None = None,
    refresh: RefreshRead | None = None,
    external: External | None = None,
) -> LoadReport | PipelineRunReport:
    """`refresh`: a source refresh's read of the file (ADR-110 Amendment 6 point 1), its mode and
    watermark column from the source's policy.

    One run of a published recipe as `principal` (ADR-110 decision 1): the route's *Run now* and
    the scheduler both come here, so a scheduled load is judged, published, watched and resolved
    exactly as a manual one, and every run is in the ledger (decision 6) — started before it
    loads, so one that dies with its Conduit shows as never finished rather than as nothing."""
    run_id, started_at = await begin_run(
        deps,
        principal=principal,
        recipe=recipe,
        investigation_id=investigation_id,
        trigger=trigger,
        slot=slot,
        source_file=source_file,
        external=external,
    )
    return await continue_run(
        deps,
        run_id=run_id,
        started_at=started_at,
        principal=principal,
        recipe=recipe,
        investigation_id=investigation_id,
        source_location=source_location,
        trigger=trigger,
        refresh=refresh,
    )


async def begin_run(
    deps: RecipeRunDeps,
    *,
    principal: Principal,
    recipe: StudioRecipeDraft,
    investigation_id: str,
    trigger: RunTrigger,
    slot: datetime | None = None,
    source_file: str | None = None,
    external: External | None = None,
) -> tuple[str, datetime]:
    """The run's start, before anything is read: its quotas judged (ADR-141 decision 6) — past
    one, it is recorded *refused* (not counted toward a schedule's pause) and `QuotaRefused` is
    raised in words — then its ledger row, which claims an external run id once
    (`ExternalRunRecorded` when it is held already, decision 12)."""
    started_at = datetime.now(UTC)
    counted = Counted(dataset_id=recipe.dataset_id, owning_unit=recipe.owning_unit)
    limits: list[QuotaLimit] = []
    if deps.run_quotas is not None:
        try:
            limits = await judge_quota(
                deps.run_quotas,
                deps.recipe_runs,
                dataset_id=recipe.dataset_id,
                owning_unit=recipe.owning_unit,
                now=started_at,
            )
        except QuotaRefused as refused:
            await deps.recipe_runs.record_not_run(
                recipe_id=recipe.recipe_id,
                recipe_version=recipe.version,
                investigation_id=investigation_id,
                trigger=trigger,
                slot=slot,
                run_as=principal.id,
                source=resolve_source_handling(recipe),
                outcome="refused",
                failure=str(refused),
                now=started_at,
                counts_toward_pause=False,
                source_file=source_file,
                counted=counted,
                external=external,
            )
            raise
    try:
        run_id = await deps.recipe_runs.start(
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.version,
            investigation_id=investigation_id,
            trigger=trigger,
            slot=slot,
            run_as=principal.id,
            source=resolve_source_handling(recipe),
            now=started_at,
            source_file=source_file,
            counted=counted,
            external=external,
            within=limits,
        )
    except QuotaRefused as refused:
        # Another run took the quota's last place between the count and the row (item 11).
        await deps.recipe_runs.record_not_run(
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.version,
            investigation_id=investigation_id,
            trigger=trigger,
            slot=slot,
            run_as=principal.id,
            source=resolve_source_handling(recipe),
            outcome="refused",
            failure=str(refused),
            now=started_at,
            counts_toward_pause=False,
            source_file=source_file,
            counted=counted,
            external=external,
        )
        raise
    return run_id, started_at


async def continue_run(
    deps: RecipeRunDeps,
    *,
    run_id: str,
    started_at: datetime,
    principal: Principal,
    recipe: StudioRecipeDraft,
    investigation_id: str,
    source_location: str | None,
    trigger: RunTrigger,
    refresh: RefreshRead | None = None,
) -> LoadReport | PipelineRunReport:
    """The run `begin_run` started: read, judged, loaded, metered and finished in the ledger."""
    # ADR-127 decision 6: each load's record is appended to this row as its graph transaction
    # commits, so a run that fails after the commit still leaves it.
    sink = LedgerSink(
        deps.recipe_runs,
        run_id,
        created_by=principal.id,
        investigation_id=investigation_id,
        started_at=started_at,
    )
    # ADR-110 Amendment 6 point 9: the run is timed, and what it puts to the object store counted.
    media = CountingMedia(deps.media)
    # ADR-140 Amendment 12: what a staged pipeline's steps staged, and their Parquet's bytes.
    staging = StagingMeter()
    clock = time.perf_counter()
    try:
        report = await _execute_recipe_run(
            deps,
            principal=principal,
            recipe=recipe,
            investigation_id=investigation_id,
            source_location=source_location,
            trigger=trigger,
            sink=sink,
            refresh=refresh,
            media=media,
            staging=staging,
        )
    except Exception as error:
        await deps.recipe_runs.fail(
            run_id,
            failure=f"{type(error).__name__}: {error}"[:1000],
            now=datetime.now(UTC),
            markings=sink.markings,
        )
        raise
    report.metering = metering_of(
        report,
        wall_seconds=time.perf_counter() - clock,
        object_store_bytes=media.bytes_written,
        staging=staging,
    )
    await deps.recipe_runs.finish(run_id, report=report, now=datetime.now(UTC))
    return report


async def _execute_recipe_run(
    deps: RecipeRunDeps,
    *,
    principal: Principal,
    recipe: StudioRecipeDraft,
    investigation_id: str,
    source_location: str | None,
    trigger: RunTrigger,
    sink: LoadSink,
    refresh: RefreshRead | None = None,
    media: MediaStore | None = None,
    staging: StagingMeter | None = None,
) -> LoadReport | PipelineRunReport:
    """`media`: the store the run puts to, counted for its metering; `deps.media` when not given.
    `staging`: told what a staged pipeline's steps wrote (ADR-140 Amendment 12).

    The load itself, `run_studio_recipe`'s docstring has what each step is for."""
    load_id = new_id()
    media = media if media is not None else deps.media
    # ADR-109 ruling 1: the case's typology rules judge this load, at the point each declares.
    rules = await _rule_gate(
        investigation_id,
        loader=principal,
        graph=deps.graph,
        analytics=deps.analytics,
        scheme=deps.handling_scheme,
        typology_rules=deps.typology_rules,
        held_rows=deps.held_rows,
        alerts_store=deps.alerts_store,
        audit=deps.audit,
        valkey=deps.valkey,
        principal_resolver=deps.principal_resolver,
        screening=deps.screening_lists,
        compute=deps.compute,
        expiries=deps.kyc_expiries,
        patterns=deps.patterns_store,
        hotlists=deps.hotlists_store,
        ontology=deps.ontology,
        recipe_id=recipe.recipe_id,
        influencers=deps.influencers,
        rule_lists=deps.rule_lists,
        rule_reach=deps.rule_reach,
    )
    report: LoadReport | PipelineRunReport
    if recipe.pipeline is not None:
        # ADR-108 phase C: a recipe holding a pipeline graph runs through the pipeline runner —
        # branches, extract stages, enrich stages — never silently as its first branch alone.
        report = await run_published_pipeline(
            recipe,
            principal,
            graph=deps.graph,
            ontology=deps.ontology,
            scheme=deps.handling_scheme,
            load_id=load_id,
            investigation_scope=investigation_id,
            repo_root=deps.recipe_repo_root,
            recogniser_for=deps.recogniser_for,
            candidates=deps.extraction_candidates,
            analytics=deps.analytics,
            media=media,
            source_location=source_location,
            online_geocode=deps.online_geocode,
            rules=rules,
            sink=sink,
            refresh=refresh,
            # ADR-109 Amendment 11: the enrich stage's supersedes go through the alerts' journal.
            alerts=deps.alerts_store,
            target_models=deps.target_models,
            staging_storage=deps.staging_storage,
            staging_meter=staging,
            list_store=deps.list_store,
            source_store=deps.sources,
        )
        for branch in report.branches:
            await resolution_trigger_module.submit_post_ingest_resolution_jobs(
                branch.report,
                recipe.row_template,
                ontology=deps.ontology,
                jobs=deps.jobs,
                enabled=deps.config.post_ingest_resolution,
            )
    else:
        report = await run_published_recipe(
            recipe,
            principal,
            graph=deps.graph,
            ontology=deps.ontology,
            load_id=load_id,
            investigation_scope=investigation_id,
            source_location=source_location,
            repo_root=deps.recipe_repo_root,
            analytics=deps.analytics,
            media=media,
            rules=rules,
            scheme=deps.handling_scheme,
            sink=sink,
            refresh=refresh,
        )
        await resolution_trigger_module.submit_post_ingest_resolution_jobs(
            report,
            recipe.row_template,
            ontology=deps.ontology,
            jobs=deps.jobs,
            enabled=deps.config.post_ingest_resolution,
        )
    entry = await ChangeStreamWriter(deps.valkey).publish(
        "ingest",
        # ADR-127 decision 7(a): the nodes the run matched by reference as well as those it created.
        node_ids=touched_node_ids(report),
        edge_ids=report.touched_edge_ids,
        investigation_id=investigation_id,
    )
    if entry is not None:
        await _evaluate_watches_best_effort(
            entry,
            principal=principal,
            graph=deps.graph,
            handling_scheme=deps.handling_scheme,
            config=deps.config,
            hotlists_store=deps.hotlists_store,
            monitors_store=deps.monitors_store,
            patterns_store=deps.patterns_store,
            alerts_store=deps.alerts_store,
            audit=deps.audit,
            valkey=deps.valkey,
            investigation_id=investigation_id,
            action_on_failure="watch_evaluation_failed",
            error_context={"load_id": load_id},
            principal_resolver=deps.principal_resolver,
            watch_reach=deps.watch_reach,
        )
        # L3.H1: the run's report says how many drawn-watch alerts it raised for its own principal.
        report.drawn_watch_alerts = await _run_drawn_watches_best_effort(
            deps, entry, dataset_id=recipe.dataset_id, principal=principal,
            investigation_id=investigation_id, load_id=load_id,
        )  # fmt: skip
    await deps.audit.record(
        principal=principal,
        action="run_studio_recipe",
        investigation_id=investigation_id,
        resolved_query={"recipe_id": recipe.recipe_id, "load_id": load_id, "trigger": trigger},
        result_cardinality=report.nodes_created + report.edges_created,
    )
    return report


def _owner_resolver(
    principal: Principal, principal_resolver: PrincipalResolver
) -> Callable[[str], Awaitable[Principal | None]]:
    """An owner's principal, resolved fresh (ADR-036, ADR-043): the requester's own at once, any
    other through Token Exchange, never cached."""

    async def resolve(owner_id: str) -> Principal | None:
        if owner_id == principal.id:
            return principal
        return await principal_resolver.resolve_for_owner(owner_id)

    return resolve


def _watch_owner_resolver(
    principal: Principal, principal_resolver: PrincipalResolver
) -> Callable[[str], Awaitable[Principal | None]]:
    """For hotlists and watches at a load (ADR-044 Amendment 1): as `_owner_resolver`, the
    requester's own at once and any other afresh, but raising each refusal, so the evaluator stops
    a watch with its reason (`evaluation._owner_or_why`) rather than an unexplained `None`."""

    async def resolve(owner_id: str) -> Principal | None:
        if owner_id == principal.id:
            return principal
        return await principal_resolver.resolve_for_owner_detailed(owner_id)

    return resolve


async def _rule_gate(
    investigation_id: str,
    *,
    loader: Principal,
    graph: GraphPort,
    analytics: AnalyticsPort,
    scheme: HandlingScheme,
    typology_rules: TypologyRuleStore,
    held_rows: HeldRowStore,
    alerts_store: AlertStore,
    audit: AuditWriter,
    valkey: Valkey,
    principal_resolver: PrincipalResolver,
    screening: ScreeningListStore,
    compute: ComputePort,
    expiries: KycExpiryStore | None,
    patterns: PatternStore,
    hotlists: HotlistStore | None = None,
    ontology: OntologySchema | None = None,
    fail_closed: bool = True,
    recipe_id: str | None = None,
    influencers: InfluencerStore | None = None,
    rule_lists: Callable[[TypologyRule, str, str], Awaitable[list[Any]]] | None = None,
    rule_reach: Callable[[TypologyRule], Awaitable[list[str] | None]] | None = None,
) -> RuleGate | None:
    """The case's active typology rules for one load (ADR-109), or `None` when it has none.
    What the KYC and pattern typologies read is required, never defaulted: a route that left it
    out once held every row it loaded, failing closed on a store the deployment had.

    ADR-133 decision 6, stage (d): when the pipeline's "Checks on load" step has been chosen, its
    case rules are the ones attached there, each doing what was chosen for a hit; a
    whole-deployment rule and a rule just for its author judge every load whatever was chosen.
    Until someone chooses, every case rule judges the load, as before the step existed."""
    rules = await typology_rules.list_active_for_case(investigation_id)
    on_hit: dict[str, str] = {}
    if recipe_id is not None:
        chosen = await typology_rules.load_checks(recipe_id)
        if chosen is not None:
            on_hit = {c.rule_id: c.on_hit for c in chosen.checks}
            rules = [r for r in rules if r.id in on_hit or always_judges(r)]
    if not rules:
        return None
    return RuleGate(
        rules=rules,
        investigation_id=investigation_id,
        graph=graph,
        analytics=analytics,
        scheme=scheme,
        alert_store=alerts_store,
        audit=audit,
        valkey=valkey,
        principal_for_owner=_owner_resolver(loader, principal_resolver),
        loader=loader,
        held_store=held_rows,
        fail_closed=fail_closed,
        screening=screening,
        compute=compute,
        expiries=expiries,
        patterns=patterns,
        hotlists=hotlists,
        ontology=ontology,
        on_hit=on_hit,
        influencers=influencers,
        rule_lists=rule_lists,
        rule_reach=rule_reach,
    )


def always_judges(rule: TypologyRule) -> bool:
    """A rule no pipeline's checks leave out: a whole-deployment rule (compliance's, the
    administrator's), and a rule just for its author (their own watch, not a check on the load)."""
    from .sentence_rules import is_deployment_wide, is_just_me

    return is_deployment_wide(rule) or is_just_me(rule)


#: What a loader's own audit entry says when a drawn watch could not run: fixed words, since the
#: failing watch may be another owner's (rule 7; L3.H2).
DRAWN_WATCH_FAILED = "a drawn watch could not run"


async def _run_drawn_watches_best_effort(
    deps: RecipeRunDeps,
    entry: ChangeStreamEntry,
    *,
    dataset_id: str | None,
    principal: Principal,
    investigation_id: str,
    load_id: str,
) -> int:
    """The run path's drawn watches (`run_drawn_watches_best_effort`), with the run's stores."""
    if deps.board_items is None or deps.datasets is None or deps.investigations is None:
        return 0
    return await run_drawn_watches_best_effort(
        node_ids=entry.node_ids, dataset_id=dataset_id, principal=principal,
        investigation_id=investigation_id, load_id=load_id, board_items=deps.board_items,
        datasets=deps.datasets, investigations=deps.investigations, graph=deps.graph,
        ontology=deps.ontology, principal_resolver=deps.principal_resolver,
        alerts_store=deps.alerts_store, audit=deps.audit,
    )  # fmt: skip


async def run_drawn_watches_best_effort(
    *,
    node_ids: Sequence[str],
    dataset_id: str | None,
    principal: Principal,
    investigation_id: str,
    load_id: str,
    board_items: BoardItemStore,
    datasets: DatasetStore,
    investigations: InvestigationStore,
    graph: GraphPort,
    ontology: OntologySchema,
    principal_resolver: PrincipalResolver,
    alerts_store: AlertStore,
    audit: AuditWriter,
) -> int:
    """L3.6 (ADR-143 Amendment 2 decision 8; ADR-146 decision 4): every live drawn watch on the
    dataset the load wrote into, run against the nodes it wrote or matched (`DrawnWatchRun`), each
    match raised into the one queue as the watch owner's alert. Each owner is resolved afresh, as
    for every watch (`_owner_resolver`), and read in their watch's case through the adapter.
    Best effort, as the other watches: a failure is audited, never the load's. Every load runs it:
    the run path (`run_recipe_as`) and a release of held rows (L3.H2), which is a load of its own.
    Returns the alerts raised for `principal` alone (rule 7)."""
    if dataset_id is None:
        return 0
    run = DrawnWatchRun(
        items=board_items,
        graph=graph,
        ontology=ontology,
        owner_of=_owner_resolver(principal, principal_resolver),
        datasets=datasets,
        holds_a_level=holds_a_level_in(investigations),
        raise_alert=raise_into(alerts_store),
    )
    try:
        return await run.after_load(
            dataset_id, list(node_ids), load_id=load_id, counted_for=principal.id
        )
    except Exception as exc:  # noqa: BLE001 - as `_evaluate_watches_best_effort`'s: audited
        # Another owner's watch failing never changes what the loader is told (rule 7), nor is its
        # error, which may name that owner or their identity provider, written under the loader:
        # fixed words under the loader, the detail under each failing watch's own owner.
        await audit.record(
            principal=principal,
            action="watch_evaluation_failed",
            investigation_id=investigation_id,
            resolved_query={"load_id": load_id, "drawn_watches": True, "error": DRAWN_WATCH_FAILED},
            result_cardinality=0,
        )
        if not isinstance(exc, DrawnWatchesFailed):
            # Not one owner's (the board store, the dataset registry): the operator's log alone.
            _log.warning("the drawn watches could not run for load %s", load_id, exc_info=exc)
            return 0
        for failure in exc.failures:
            if failure.owner is None:
                # Resolving the owner is what failed: there is no one to write it under but the
                # operator's log.
                _log.warning(
                    "drawn watch %s could not run: its owner was not resolved",
                    failure.watch.id, exc_info=failure.error,
                )  # fmt: skip
                continue
            await audit.record(
                principal=failure.owner,
                action="watch_evaluation_failed",
                investigation_id=failure.watch.case_id,
                resolved_query={"load_id": load_id, "drawn_watch_id": failure.watch.id,
                                "error": str(failure.error)},
                result_cardinality=0,
            )  # fmt: skip
        return exc.counted


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
    watch_reach: DatasetReach | None = None,
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

    # ADR-044 Amendment 1: the detailed resolver, so a watch it cannot act for is stopped with why.
    _principal_for_owner = _watch_owner_resolver(principal, principal_resolver)

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
            reaches_dataset=watch_reach,
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
            reaches_dataset=watch_reach,
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
