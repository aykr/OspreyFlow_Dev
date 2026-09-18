"""Verify (`docs/09_INGEST_STUDIO.md` §5) — the dry run over a saved
`RowTemplate`, bridging a `StudioRecipeDraft` to `services/ingest/engine.py`'s
`dry_run_recipe`.

The same bounded sample Profile/Map already read (`ready_for_profile`, the
`generic-csv`-only connector gate, `resolve_source_handling` — all reused
from `studio_profile.py`/`studio_map.py`, not reimplemented). §5's own
access-control mechanism — an `on_match: reference` lookup going through
the ordinary `GraphPort.find_node` under the requesting principal — lives in
`dry_run_recipe` itself, not here; this module's own job is building the
recipe stub, grouping rejections by reason, and applying §3's
independent-minimums masking to whatever this run would *create* (a
referenced node's own values are never touched here — `find_node`'s access
filter already decided this principal may see that node at all).
"""

from __future__ import annotations

from collections import defaultdict

from services.ingest.engine import dry_run_recipe
from services.ingest.profiler import DEFAULT_SAMPLE_SIZE, _shape_mask

from ontology.handling import HandlingScheme, principal_may_view
from ports.graph import GraphPort
from schemas.domain import OntologySchema, Principal
from schemas.ingest import (
    Recipe,
    RecipeConnector,
    RecipeDefaults,
    RejectionGroup,
    RejectionRecord,
    StudioRecipeDraft,
    VerifyEdgeCount,
    VerifyEntityCount,
    VerifyReport,
)

from .studio_map import resolve_source_handling
from .studio_profile import ConnectorNotAvailableError, RecipeNotReadyForProfileError
from .studio_profile import _read_rows as _read_recipe_rows

__all__ = ["RowTemplateMissingError", "run_verify"]

#: Rejection samples are capped per reason (studio_verify.py's own
#: `RejectionGroup.samples`) — `count` itself never is, so a reason with 400
#: rejections still reports 400, only the number of *samples* shown is
#: bounded. Matches `09_INGEST_STUDIO.md` §5: "grouped by cause with
#: samples", not "every rejected row listed".
_MAX_SAMPLES_PER_REASON = 5


class RowTemplateMissingError(Exception):
    """Raised when Verify is invoked before Map has ever saved a row
    template — `09_INGEST_STUDIO.md` §3: "the studio does not let you map
    until it has run", and the same discipline applies one stage further:
    there is nothing to dry-run without a template."""


def _group_rejections(rejections: list[RejectionRecord]) -> list[RejectionGroup]:
    by_reason: dict[str, list[RejectionRecord]] = defaultdict(list)
    for rejection in rejections:
        by_reason[rejection.reason].append(rejection)
    return [
        RejectionGroup(reason=reason, count=len(records), samples=records[:_MAX_SAMPLES_PER_REASON])
        for reason, records in by_reason.items()
    ]


def _mask_value(value: object) -> str:
    return _shape_mask(str(value))


async def run_verify(
    draft: StudioRecipeDraft,
    principal: Principal,
    scheme: HandlingScheme,
    graph: GraphPort,
    ontology: OntologySchema,
) -> VerifyReport:
    if not draft.ready_for_profile:
        raise RecipeNotReadyForProfileError(draft.recipe_id)
    if draft.row_template is None:
        raise RowTemplateMissingError(draft.recipe_id)
    if draft.connector_profile not in {"generic-csv"}:
        raise ConnectorNotAvailableError(draft.connector_profile)

    source_handling = resolve_source_handling(draft)
    all_rows = _read_recipe_rows(draft)
    sampled = all_rows[:DEFAULT_SAMPLE_SIZE]
    sample_is_whole_source = len(all_rows) <= DEFAULT_SAMPLE_SIZE

    recipe = Recipe(
        id=draft.recipe_id,
        version=draft.version,
        label=draft.label,
        connector=RecipeConnector(profile=draft.connector_profile or "generic-csv"),
        # No publish-time staleness concept exists yet for a draft (Publish
        # is a later stage) — pinning to the live ontology's own version is
        # the same non-issue `studio_map.py`'s own recipe stub sidesteps,
        # not a claim this draft targets that version permanently.
        ontology_version=ontology.version,
        defaults=RecipeDefaults(
            handling=draft.handling, provenance={}, legal_basis=draft.legal_basis
        ),
        row_template=draft.row_template,
    )

    result = await dry_run_recipe(
        recipe,
        sampled,
        graph=graph,
        ontology=ontology,
        principal=principal,
        source=draft.source_location or draft.recipe_id,
    )

    values_masked = not principal_may_view(source_handling, principal, scheme)
    nodes = result.nodes
    edges = result.edges
    if values_masked:
        nodes = [
            node.model_copy(
                update={"properties": {k: _mask_value(v) for k, v in node.properties.items()}}
            )
            if node.id in result.created_node_ids
            else node
            for node in nodes
        ]
        # Every edge is this run's own creation (§5: an edge has no
        # `match_on`/`on_match` to reference by) — masked unconditionally.
        edges = [
            edge.model_copy(
                update={"properties": {k: _mask_value(v) for k, v in edge.properties.items()}}
            )
            for edge in edges
        ]

    return VerifyReport(
        rows_read=result.rows_read,
        rows_deduplicated=result.rows_deduplicated,
        sample_is_whole_source=sample_is_whole_source,
        values_masked=values_masked,
        entities_by_type={
            name: VerifyEntityCount(created=c.created, referenced=c.referenced)
            for name, c in result.entities_by_type.items()
        },
        edges_by_type={
            name: VerifyEdgeCount(created=c.created) for name, c in result.edges_by_type.items()
        },
        rejections=_group_rejections(result.rejections),
        nodes=nodes,
        edges=edges,
    )
