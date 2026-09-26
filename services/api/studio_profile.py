"""Profile (`docs/09_INGEST_STUDIO.md` §2/§3) — bridges a Connect-stage
`StudioRecipeDraft` to `services/ingest/profiler.py`'s headless
`profile_source`.

The profiler itself is Phase 2 scope, already implemented and already
computing shape-masking against a `Handling` block; this module is what
Phase 5a's Profile screen actually calls: it resolves which connector reads
the draft's `source_location` (only `generic-csv` has a backing reader —
`schemas.ingest.CONNECTOR_CATALOGUE`'s own `available` flag), builds the
`Handling` the profiler masks against from the draft's own gate answers,
and turns each way that can fail into a typed error the route layer maps to
a response — never a bare 500, mirroring `services/api/studio_recipes.py`'s
own `StudioRecipeNotFoundError`/`StudioRecipeNotADraftError` discipline.
"""

from __future__ import annotations

import csv

from pydantic import ValidationError
from services.ingest.connectors.csv_connector import read_csv
from services.ingest.profiler import profile_source

from ontology.handling import HandlingScheme
from schemas.domain import Handling, Principal
from schemas.ingest import StudioRecipeDraft
from schemas.profile import SourceProfile

#: `schemas.ingest.CONNECTOR_CATALOGUE`'s own `available` flag — only
#: `generic-csv` has a backing reader today (`services/ingest/connectors/
#: csv_connector.py`), so Connect's own connector `<Select>` already
#: disables every other option; this is the same restriction, checked
#: again here since Profile is the first stage to actually need it.
_AVAILABLE_CONNECTORS = frozenset({"generic-csv"})


class RecipeNotReadyForProfileError(Exception):
    """Raised when Connect's three mandatory gates (§2) are not all
    answered yet — `09_INGEST_STUDIO.md` §3: "the studio does not let you
    map [or profile] until it has run", and Profile cannot run without a
    location, a handling marking and a legal basis already on the draft."""


class ConnectorNotAvailableError(Exception):
    """Raised for a `connector_profile` with no backing reader yet."""


class SourceUnreadableError(Exception):
    """Raised when `source_location` cannot be opened as the declared
    connector expects — missing file, permissions, or a decoding failure."""


class SourceHandlingIncompleteError(Exception):
    """Raised when the draft's `handling` dict, though non-empty (Connect's
    own `ready_for_profile` gate only checks truthiness — `schemas.ingest.
    StudioRecipeDraft._compute_ready_for_profile`), does not carry every
    field `schemas.domain.Handling` requires (`classification`,
    `handling_code`, `originator`, `owning_unit`). Profile cannot paper
    over this silently: the masking decision (§3) depends on a well-formed
    `Handling`, so an incomplete one is surfaced rather than guessed at."""


def _read_rows(recipe: StudioRecipeDraft) -> list[dict[str, str]]:
    if recipe.connector_profile not in _AVAILABLE_CONNECTORS:
        raise ConnectorNotAvailableError(recipe.connector_profile)
    # `ready_for_profile` (checked by the caller) already guarantees
    # `source_location` is set — `schemas.ingest.
    # StudioRecipeDraft._compute_ready_for_profile`.
    assert recipe.source_location is not None
    try:
        return list(read_csv(recipe.source_location))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise SourceUnreadableError(str(exc)) from exc


async def profile_recipe_source(
    recipe: StudioRecipeDraft, principal: Principal, scheme: HandlingScheme
) -> SourceProfile:
    if not recipe.ready_for_profile:
        raise RecipeNotReadyForProfileError(recipe.recipe_id)
    try:
        source_handling = Handling(**recipe.handling)
    except ValidationError as exc:
        raise SourceHandlingIncompleteError(str(exc)) from exc
    rows = _read_rows(recipe)
    return profile_source(rows, source_handling=source_handling, principal=principal, scheme=scheme)
