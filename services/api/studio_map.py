"""Map (`docs/09_INGEST_STUDIO.md` §4) — the row-template editor's own
backend surface, over the same `StudioRecipeDraft`/`RowTemplate` schemas
Connect and Profile already use.

Deliberately thin. Per §4/§5's own division of labour: Map shows the
template graph, per-element settings, the *raw* sample row a template is
"bound to" while scrubbing, and a live preview of what an element's
handling/provenance would resolve to (`services/ingest/engine.py`'s
`preview_handling_and_provenance`, extended for per-element overrides). It
does not execute a `FieldBinding`'s transform against a row or produce a
rejection — that is Verify's dry run (§5), which goes through
`GraphPort.find_node` under the author's own clearance. Building that here
would be a second, lighter resolution path that inevitably drifts from the
real one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from services.ingest.engine import preview_handling_and_provenance
from services.ingest.profiler import (
    DEFAULT_SAMPLE_SIZE,
    _free_text_summary,
    _is_free_text_column,
    _shape_mask,
    profile_source,
)

from ontology.handling import HandlingScheme, principal_may_view
from schemas.domain import Handling, Principal, Provenance
from schemas.ingest import (
    MapHandlingPreviewRequest,
    MapSampleRow,
    Recipe,
    RecipeConnector,
    RecipeDefaults,
    RowTemplate,
    StudioRecipeDraft,
)

from .studio_profile import (
    ConnectorNotAvailableError,
    RecipeNotReadyForProfileError,
    SourceHandlingIncompleteError,
)
from .studio_profile import _read_rows as _read_recipe_rows

__all__ = [
    "RowIndexOutOfRangeError",
    "HandlingLoosenedError",
    "get_sample_row",
    "preview_element_handling",
    "resolve_source_handling",
    "validate_handling_tightens",
]


class RowIndexOutOfRangeError(Exception):
    """Raised for a `row_index` past the end of the same bounded sample
    Profile reads (`services/ingest/profiler.DEFAULT_SAMPLE_SIZE` rows or
    the whole source) — the scrubber's own `is_last_row` flag is what the
    Map screen checks first, so reaching this is a defect in that check,
    not an expected path."""

    def __init__(self, row_index: int) -> None:
        self.row_index = row_index
        super().__init__(f"row {row_index} is past the end of the profiled sample")


class HandlingLoosenedError(Exception):
    """Raised when a per-element `handling` override's `classification`
    ranks below (`HandlingScheme.classification`'s dominance order) the
    draft's own source-level classification — `09_INGEST_STUDIO.md` §3's
    independent-minimums rule, restated in §4: "a per-element handling
    override in Map can tighten but never loosen the source-level masking
    baseline set at Connect." Enforced once, at save time
    (`PUT /v1/ingest/recipes/{id}/row-template`), not re-checked per row at
    run time — an element's override is static, not something that varies
    row to row."""

    def __init__(self, classification: str, baseline: str) -> None:
        self.classification = classification
        self.baseline = baseline
        super().__init__(
            f"handling override classification {classification!r} is less restrictive than "
            f"the source's own {baseline!r} — an override may tighten a source's marking, "
            "never loosen it"
        )


def validate_handling_tightens(
    baseline: Handling, override: dict[str, Any] | None, scheme: HandlingScheme
) -> None:
    """`override` is one element's own `RecipeEntity.handling`/
    `RecipeEdge.handling` (a plain dict, possibly a partial one — see
    `services/ingest/engine._merge_override`). Only `classification` is
    checked: it is the axis `HandlingScheme.classification`'s dominance
    order actually orders, and the one Profile's own masking decision
    (§3) is computed against — `handling_code`/`action_code`/
    `sanitisation_code` are real fields but have no declared ordering to
    tighten or loosen along."""
    if not override or "classification" not in override:
        return
    new_classification = override["classification"]
    if new_classification == baseline.classification:
        return
    if new_classification not in scheme.classification:
        # Not this function's job to validate a classification exists in
        # the scheme at all — `Handling.model_validate` downstream (in
        # `_write_entity`/`_write_edge`, or `preview_handling_and_provenance`
        # here) rejects an unknown one on its own terms.
        return
    baseline_rank = scheme.classification.index(baseline.classification)
    override_rank = scheme.classification.index(new_classification)
    if override_rank < baseline_rank:
        raise HandlingLoosenedError(new_classification, baseline.classification)


def resolve_source_handling(draft: StudioRecipeDraft) -> Handling:
    try:
        return Handling(**draft.handling)
    except ValidationError as exc:
        raise SourceHandlingIncompleteError(str(exc)) from exc


async def get_sample_row(
    draft: StudioRecipeDraft, principal: Principal, scheme: HandlingScheme, row_index: int
) -> MapSampleRow:
    """One raw row from the same bounded sample Profile reads — §4: "the
    template is always shown bound to a real row, and the analyst can page
    through." Masked column-by-column exactly the way `profiler._mask_profile`
    masks `ColumnProfile.sample_values`: a free-text column gets the
    character-class summary, a structured one gets the positional mask —
    the same independent-minimums rule (§3), applied to a whole row instead
    of five column samples."""
    if not draft.ready_for_profile:
        raise RecipeNotReadyForProfileError(draft.recipe_id)
    if draft.connector_profile not in {"generic-csv"}:
        raise ConnectorNotAvailableError(draft.connector_profile)
    source_handling = resolve_source_handling(draft)
    rows = _read_recipe_rows(draft)
    sampled = rows[:DEFAULT_SAMPLE_SIZE]
    if row_index >= len(sampled):
        raise RowIndexOutOfRangeError(row_index)
    row = sampled[row_index]

    masked = not principal_may_view(source_handling, principal, scheme)
    values: dict[str, str] = {}
    if masked:
        # Column classifications (free-text vs. structured) come from the
        # same profiler pass Profile itself runs — not a second
        # implementation of that judgement.
        profile = profile_source(
            sampled, source_handling=source_handling, principal=principal, scheme=scheme
        )
        free_text_columns = {c.name for c in profile.columns if _is_free_text_column(c)}
        for name, value in row.items():
            if name is None:
                continue
            raw = value or ""
            values[name] = (
                _free_text_summary([raw]) if name in free_text_columns else _shape_mask(raw)
            )
    else:
        values = {name: (value or "") for name, value in row.items() if name is not None}

    return MapSampleRow(
        row_index=row_index,
        values=values,
        values_masked=masked,
        is_last_row=row_index == len(sampled) - 1,
    )


async def preview_element_handling(
    draft: StudioRecipeDraft, request: MapHandlingPreviewRequest
) -> tuple[Handling, Provenance]:
    """What `preview_handling_and_provenance()` would compute for one
    in-progress element, before it — or the row template it lives on — is
    ever saved. `defaults` mirrors what `Recipe.defaults` will actually
    hold once Publish exists: the draft's own Connect-stage `handling`,
    `asserted` provenance unless overridden."""
    recipe_stub = Recipe(
        id=draft.recipe_id,
        version=draft.version,
        label=draft.label,
        connector=RecipeConnector(profile=draft.connector_profile or "generic-csv"),
        ontology_version=0,
        defaults=RecipeDefaults(
            handling=draft.handling, provenance={}, legal_basis=draft.legal_basis
        ),
        row_template=RowTemplate(entities=[]),
    )
    return preview_handling_and_provenance(
        recipe_stub,
        source=draft.source_location or draft.recipe_id,
        row_index=request.row_index,
        now=datetime.now(UTC),
        handling_override=request.handling_override,
        provenance_override=request.provenance_override,
    )
