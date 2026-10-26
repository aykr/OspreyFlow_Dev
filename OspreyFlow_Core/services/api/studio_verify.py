"""Verify (`spec/09_INGEST_STUDIO.md` §5) — the dry run over a saved
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
from collections.abc import Mapping, Sequence

from services.ingest.engine import RowKeys, dry_run_recipe
from services.ingest.profiler import DEFAULT_SAMPLE_SIZE, _shape_mask

from ontology.handling import HandlingScheme, principal_may_view
from ports.graph import GraphPort
from schemas.domain import Edge, Handling, Node, OntologySchema, Principal
from schemas.ingest import (
    Recipe,
    RecipeDefaults,
    RejectionGroup,
    RejectionRecord,
    StudioRecipeDraft,
    VerifyEdgeCount,
    VerifyEntityCount,
    VerifyReport,
)

from .studio_map import resolve_source_handling
from .studio_profile import (
    RecipeNotReadyForProfileError,
    connector_for,
    row_markings,
)
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


def _masked_sample(rows: Sequence[Mapping[str, object]], row_index: int) -> str:
    """A rejected row as its sample reads, each value shape-masked and each column name kept."""
    if not 0 <= row_index < len(rows):
        return ""
    return str({name: _mask_value(value) for name, value in rows[row_index].items()})


async def run_verify(
    draft: StudioRecipeDraft,
    principal: Principal,
    scheme: HandlingScheme,
    graph: GraphPort,
    ontology: OntologySchema,
    *,
    row_keys: RowKeys | None = None,
    investigation_id: str | None = None,
) -> VerifyReport:
    """`row_keys` and `investigation_id` (ADR-127 decision 5): given the store of loaded rows and
    the case, the dry run counts the rows the run would skip by the draft's own `deduplicate`, as
    the run counts them, and writes nothing (it only asks the store which keys the case kept)."""
    if not draft.ready_for_profile:
        raise RecipeNotReadyForProfileError(draft.recipe_id)
    if draft.row_template is None:
        raise RowTemplateMissingError(draft.recipe_id)

    source_handling = resolve_source_handling(draft)
    all_rows = _read_recipe_rows(draft)
    sampled = all_rows[:DEFAULT_SAMPLE_SIZE]
    sample_is_whole_source = len(all_rows) <= DEFAULT_SAMPLE_SIZE

    recipe = Recipe(
        id=draft.recipe_id,
        version=draft.version,
        label=draft.label,
        # Round 13bf: the profile's own settings, not just its id — `connector_for`'s own
        # docstring has the defect this replaces. It also raises
        # `ConnectorNotAvailableError` for an unavailable profile, which is the gate that
        # used to be an inline `{"generic-csv"}` set a few lines above.
        connector=connector_for(draft),
        # No publish-time staleness concept exists yet for a draft (Publish
        # is a later stage) — pinning to the live ontology's own version is
        # the same non-issue `studio_map.py`'s own recipe stub sidesteps,
        # not a claim this draft targets that version permanently.
        ontology_version=ontology.version,
        defaults=RecipeDefaults.for_source(draft.handling, draft.legal_basis),
        row_template=draft.row_template,
        deduplicate=draft.deduplicate,
    )

    result = await dry_run_recipe(
        recipe,
        sampled,
        graph=graph,
        ontology=ontology,
        principal=principal,
        source=draft.source_location or draft.recipe_id,
        scheme=scheme,
        row_keys=row_keys,
        investigation_scope=investigation_id,
    )

    # Each simulated node and link is masked by its own resolved marking (ADR-127 decision 3: the
    # source's own is only the lowest a row may carry), and a rejected row, which resolved to none,
    # by every marking a row of the source may carry (`source_markings`).
    def may_view(marking: Handling) -> bool:
        return principal_may_view(marking, principal, scheme)

    def masked_by_own_marking(element: Node | Edge) -> bool:
        return not may_view(element.handling)

    values_masked = not may_view(source_handling)
    nodes = [
        node.model_copy(
            update={"properties": {k: _mask_value(v) for k, v in node.properties.items()}}
        )
        if node.id in result.created_node_ids and (values_masked or masked_by_own_marking(node))
        else node
        for node in result.nodes
    ]
    # Every edge is this run's own creation (§5: an edge has no
    # `match_on`/`on_match` to reference by).
    edges = [
        edge.model_copy(
            update={"properties": {k: _mask_value(v) for k, v in edge.properties.items()}}
        )
        if values_masked or masked_by_own_marking(edge)
        else edge
        for edge in result.edges
    ]

    def rejected_row_unreadable(row_index: int) -> bool:
        row = sampled[row_index] if 0 <= row_index < len(sampled) else None
        return not row_markings(draft, scheme, row).readable_by(principal, scheme)

    # A rejected row resolved to no marking: it is masked unless the principal may view every
    # marking *that row's* declared and bound cells could give (an unreadable one gives them all).
    rejections = [
        rejection.model_copy(update={"sample": _masked_sample(sampled, rejection.row_index)})
        if values_masked or rejected_row_unreadable(rejection.row_index)
        else rejection
        for rejection in result.rejections
    ]
    values_masked = (
        values_masked
        or nodes != result.nodes
        or edges != result.edges
        or rejections != result.rejections
    )

    return VerifyReport(
        rows_read=result.rows_read,
        rows_deduplicated=result.rows_deduplicated,
        rows_already_loaded=result.rows_already_loaded,
        sample_is_whole_source=sample_is_whole_source,
        values_masked=values_masked,
        entities_by_type={
            name: VerifyEntityCount(created=c.created, referenced=c.referenced)
            for name, c in result.entities_by_type.items()
        },
        edges_by_type={
            name: VerifyEdgeCount(created=c.created) for name, c in result.edges_by_type.items()
        },
        rejections=_group_rejections(rejections),
        nodes=nodes,
        edges=edges,
    )
