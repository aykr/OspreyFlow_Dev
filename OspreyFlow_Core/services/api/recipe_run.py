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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from ontology.handling import HandlingScheme
from ports.analytics import AnalyticsPort
from ports.compute import ComputePort
from ports.graph import GraphPort
from ports.media import MediaStore
from schemas.domain import OntologySchema, Principal
from schemas.ingest import LoadReport, PipelineRunReport, StudioRecipeDraft

from . import resolution_trigger as resolution_trigger_module
from .alerts import AlertStore
from .audit import AuditWriter
from .auth import PrincipalResolver
from .change_stream import ChangeStreamEntry, ChangeStreamWriter, touched_node_ids
from .config import ApiConfig
from .evaluation import evaluate_hotlists_for_entry, evaluate_monitors_for_entry
from .held_rows import HeldRowStore
from .hotlists import HotlistStore
from .jobs import JobQueue
from .kyc_expiries import KycExpiryStore
from .load_records import LedgerSink
from .monitors import MonitorStore
from .pattern_store import PatternStore
from .pipeline_run import OnlineGeocode, RecogniserFor, run_published_pipeline
from .recipe_runs import RecipeRunStore, RunTrigger
from .review import ExtractionCandidateStore
from .rule_evaluation import RuleGate
from .screening import ScreeningListStore
from .studio_map import resolve_source_handling
from .studio_publish import LoadSink, run_published_recipe
from .typology_rules import TypologyRuleStore


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

    @classmethod
    def from_state(cls, state: Any) -> RecipeRunDeps:
        """The scheduler's way in: the application's state, read where the route's getters read
        it, so the two paths cannot be handed different stores."""
        return cls(
            **{
                f.name: getattr(state, _RUN_DEP_STATE_NAMES.get(f.name, f.name))
                for f in dataclass_fields(cls)
            }
        )


_RUN_DEP_STATE_NAMES = {
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
) -> LoadReport | PipelineRunReport:
    """One run of a published recipe as `principal` (ADR-110 decision 1): the route's *Run now* and
    the scheduler both come here, so a scheduled load is judged, published, watched and resolved
    exactly as a manual one, and every run is in the ledger (decision 6) — started before it
    loads, so one that dies with its Conduit shows as never finished rather than as nothing."""
    started_at = datetime.now(UTC)
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
    )
    # ADR-127 decision 6: each load's record is appended to this row as its graph transaction
    # commits, so a run that fails after the commit still leaves it.
    sink = LedgerSink(
        deps.recipe_runs,
        run_id,
        created_by=principal.id,
        investigation_id=investigation_id,
        started_at=started_at,
    )
    try:
        report = await _execute_recipe_run(
            deps,
            principal=principal,
            recipe=recipe,
            investigation_id=investigation_id,
            source_location=source_location,
            trigger=trigger,
            sink=sink,
        )
    except Exception as error:
        await deps.recipe_runs.fail(
            run_id,
            failure=f"{type(error).__name__}: {error}"[:1000],
            now=datetime.now(UTC),
            markings=sink.markings,
        )
        raise
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
) -> LoadReport | PipelineRunReport:
    """The load itself, `run_studio_recipe`'s docstring has what each step is for."""
    load_id = new_id()
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
            media=deps.media,
            source_location=source_location,
            online_geocode=deps.online_geocode,
            rules=rules,
            sink=sink,
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
            media=deps.media,
            rules=rules,
            scheme=deps.handling_scheme,
            sink=sink,
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
        )
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
    fail_closed: bool = True,
) -> RuleGate | None:
    """The case's active typology rules for one load (ADR-109), or `None` when it has none.
    What the KYC and pattern typologies read is required, never defaulted: a route that left it
    out once held every row it loaded, failing closed on a store the deployment had."""
    rules = await typology_rules.list_active_for_case(investigation_id)
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
    )


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

    _principal_for_owner = _owner_resolver(principal, principal_resolver)

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
