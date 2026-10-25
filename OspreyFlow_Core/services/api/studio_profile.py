"""Profile (`spec/09_INGEST_STUDIO.md` §2/§3) — bridges a Connect-stage
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
import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from services.ingest.connectors.csv_connector import read_csv
from services.ingest.engine import _merge_override, recipe_handlings
from services.ingest.profiler import DEFAULT_SAMPLE_SIZE, profile_source
from services.ingest.recipe_rules import handling_bindings, literal_handling, template_elements

from ontology.handling import HandlingScheme, principal_may_view
from schemas.connectors import ConnectorProfile, load_connector_profiles
from schemas.domain import Handling, Principal
from schemas.ingest import (
    CONNECTORS_DIR,
    Recipe,
    RecipeConnector,
    RecipeDefaults,
    RowTemplate,
    StudioRecipeDraft,
)
from schemas.profile import SourceProfile

from .ingest_sources import ingest_root, is_inside


#: **Derived from the profile files, not a literal** (round 13bf). This used to be a second,
#: hand-maintained copy of `ConnectorCatalogueEntry.available` — two truths about one fact, in
#: files that never referred to each other, and the reason `cdr-generic-csv` could be declared in
#: the catalogue and still refused here. Now both read the same `connectors/` directory
#: (`packages/schemas/connectors.py`), so a carrier layout is a file, exactly as
#: `09_INGEST_STUDIO.md` §2 has always said.
def _profiles() -> dict[str, ConnectorProfile]:
    return load_connector_profiles(CONNECTORS_DIR)


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


def _confined(location: str) -> str:
    """The source file, only if it is inside the ingest folder (`ingest_sources.ingest_root`) —
    the one place the picker, an upload and the folder watch put a file. Resolved first, so a `..`
    walk or a link inside the folder to a file outside it is judged by where it really leads.
    Refused before anything is opened or stat'd, in words that do not depend on whether the path
    exists or name it, so the refusal cannot be used to learn which files are on the server (the
    security review, 18 October 2026). Every read of a recipe's source passes through here:
    Profile, Map, Verify, a run and a publish all read with `_read_rows`."""
    root = ingest_root()
    if not is_inside(root, Path(location).resolve()):
        raise SourceUnreadableError(
            "That file is not in the ingest folder. "
            "Choose it from the folder's files, or upload it."
        )
    return location


class SourceHandlingIncompleteError(Exception):
    """Raised when the draft's `handling` dict, though non-empty (Connect's
    own `ready_for_profile` gate only checks truthiness — `schemas.ingest.
    StudioRecipeDraft._compute_ready_for_profile`), does not carry every
    field `schemas.domain.Handling` requires (`classification`,
    `handling_code`, `originator`, `owning_unit`). Profile cannot paper
    over this silently: the masking decision (§3) depends on a well-formed
    `Handling`, so an incomplete one is surfaced rather than guessed at."""


def require_available_connector(draft: StudioRecipeDraft) -> ConnectorProfile:
    """The draft's connector profile, or `ConnectorNotAvailableError` — the **single** gate.

    Round 13bf: there were four of these, written out by hand in four modules
    (`studio_profile`'s own `_AVAILABLE_CONNECTORS`, plus a literal `{"generic-csv"}` set inline
    in `studio_map.row_template` and `studio_verify.verify_recipe`, plus the catalogue's own
    `available` flag). Adding `cdr-generic-csv` to one of them left the others refusing it, which
    is exactly how round 13bc found B1-B3 unwalkable through the analyst's own door.
    """
    if draft.connector_profile is None:
        raise ConnectorNotAvailableError("<none>")
    profile = _profiles().get(draft.connector_profile)
    if profile is None or not profile.available:
        raise ConnectorNotAvailableError(draft.connector_profile)
    return profile


def connector_for(draft: StudioRecipeDraft) -> RecipeConnector:
    """The `RecipeConnector` a draft's own connector profile describes — round 13bf.

    **This is the defect that kept B1-B3 unreachable even once the profile file existed.**
    `studio_verify` and `studio_publish` both built
    `RecipeConnector(profile=draft.connector_profile or "generic-csv")` — the id and *nothing
    else*, so every connector-level setting silently fell back to the model's own defaults. A
    recipe published through the Studio for a layout declaring `date_order: dmy` reached the
    engine with `date_order=None`, and `08_ACCEPTANCE_SCENARIOS.md` B3's own `12/01/2026` would
    have been read with no declared order at all — the layout's own declaration dropped on the
    floor between the profile file and the run, with nothing anywhere reporting a problem.

    Note what the `or "generic-csv"` fallback did in the same line: substituted a *different
    layout's* settings for the one the analyst chose. That is how a carrier's `dmy` export gets
    silently read as `mdy`. There is no default connector here; an absent one is refused by name.
    """
    profile = require_available_connector(draft)
    return RecipeConnector(
        profile=profile.id,
        delimiter=profile.delimiter,
        encoding=profile.encoding,
        header_rows=profile.header_rows,
        date_order=profile.date_order,
        source_crs=profile.source_crs,
    )


def _read_rows(recipe: StudioRecipeDraft) -> list[dict[str, str]]:
    # `connector_profile` is optional on a draft — an unset one is as unavailable as an unknown
    # one, and is refused by the same named error rather than crashing on a `None` lookup.
    if recipe.connector_profile is None:
        raise ConnectorNotAvailableError("<none>")
    profile = _profiles().get(recipe.connector_profile)
    if profile is None or not profile.available:
        raise ConnectorNotAvailableError(recipe.connector_profile)
    # `ready_for_profile` (checked by the caller) already guarantees
    # `source_location` is set — `schemas.ingest.
    # StudioRecipeDraft._compute_ready_for_profile`.
    assert recipe.source_location is not None
    source = _confined(recipe.source_location)
    try:
        # The profile's own delimiter/encoding, not the reader's defaults: a layout that declares
        # a semicolon separator was being read as one column before this, and profiled as such.
        return list(
            read_csv(
                source,
                delimiter=profile.delimiter,
                encoding=profile.encoding,
            )
        )
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise SourceUnreadableError(str(exc)) from exc


def _stub(draft: StudioRecipeDraft) -> Recipe:
    return Recipe(
        id=draft.recipe_id,
        version=draft.version,
        label=draft.label,
        connector=RecipeConnector(profile=draft.connector_profile or "generic-csv"),
        ontology_version=0,
        defaults=RecipeDefaults.for_source(draft.handling, draft.legal_basis),
        row_template=draft.row_template or RowTemplate(entities=[]),
    )


@dataclass(frozen=True)
class RowMarkings:
    """What a row of the source may carry. `unviewable` says the row cannot be judged (a part with
    no value it could take, such as a unit column with no units to name): no principal may be shown
    its values, whatever the markings are and whoever asks. Every reader of this checks it first."""

    markings: list[Handling]
    unviewable: bool = False

    def readable_by(self, principal: Principal, scheme: HandlingScheme) -> bool:
        return not self.unviewable and all(
            principal_may_view(m, principal, scheme) for m in self.markings
        )


def row_markings(
    draft: StudioRecipeDraft, scheme: HandlingScheme, row: Mapping[str, str] | None
) -> RowMarkings:
    """Every marking *this row* of the source may carry (ADR-127 decision 3): the source's own and
    the recipe's fixed ones, and, for each element that binds parts of a marking to columns, the
    markings that element's cells give *over its own base* (the source's defaults and its fixed
    handling, as `row_marking` builds them): the default for an empty cell, the cell's value if
    the scheme or the units define it, every defined value if they do not (or the column is
    missing, or `row` is unknown). Columns Connect declared that no element binds yet are judged
    over the source's defaults. A part with no value it could take (a unit column with no `units`
    to name) leaves nothing to compare, so the result says `unviewable`. A read of the row's raw
    values is allowed only to a principal who may view every one of them (rule 3)."""
    stub = _stub(draft)
    markings = recipe_handlings(stub)
    units = stub.defaults.units

    groups: list[tuple[Mapping[str, Any], dict[str, list[str]]]] = []
    for element in template_elements(stub.row_template):
        bindings = handling_bindings(element.handling)
        if bindings:
            base = _merge_override(stub.defaults.handling, literal_handling(element.handling))
            groups.append((base, {part: [column] for part, column in bindings.items()}))
    bound_pairs = {
        (part, column) for _, parts in groups for part, cols in parts.items() for column in cols
    }
    declared_only = {
        part: [column]
        for part, column in stub.defaults.handling_columns.items()
        if (part, column) not in bound_pairs
    }
    if declared_only:
        groups.append((stub.defaults.handling, declared_only))
    if not groups:
        return RowMarkings(markings)

    for group_base, columns in groups:
        base = dict(group_base)
        parts = sorted(columns)
        candidates: list[list[str | None]] = []
        for part in parts:
            every = (
                list(units)
                if part in ("originator", "owning_unit")
                else _scheme_values(scheme, part)
            )
            options: list[str | None] = []
            for column in columns[part]:
                cell = ((row or {}).get(column) or "").strip() if row is not None else None
                if cell is None or column not in (row or {}):
                    options.extend(every)
                elif not cell:
                    options.append(None)
                elif cell in every:
                    options.append(cell)
                else:
                    options.extend(every)
            if not options:
                return RowMarkings(markings, unviewable=True)
            candidates.append(list(dict.fromkeys(options)))
        seen: set[tuple[tuple[str, str], ...]] = set()
        for combo in itertools.product(*candidates):
            chosen = {part: value for part, value in zip(parts, combo, strict=True) if value}
            key = tuple(sorted(chosen.items()))
            if key in seen:
                continue
            seen.add(key)
            markings.append(Handling.model_validate({**_complete(base), **chosen}))
    return RowMarkings(markings)


def _complete(handling: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(handling)
    raw.setdefault("owning_unit", raw.get("originator"))
    raw.setdefault("handling_code", "P")
    return raw


def _scheme_values(scheme: HandlingScheme, part: str) -> list[str]:
    return {
        "classification": list(scheme.classification),
        "handling_code": list(scheme.handling_codes),
        "action_code": list(scheme.action_codes),
        "sanitisation_code": list(scheme.sanitisation_codes),
    }.get(part, [])


def sample_markings(
    draft: StudioRecipeDraft, scheme: HandlingScheme, rows: Sequence[Mapping[str, str]]
) -> RowMarkings:
    """`row_markings` over every row sampled: what a profile of them, which shows column samples
    drawn from any of them, may reveal. Unviewable if any row is."""
    found: list[Handling] = []
    unviewable = False
    for row in rows:
        result = row_markings(draft, scheme, row)
        found.extend(result.markings)
        unviewable = unviewable or result.unviewable
    return RowMarkings(found, unviewable)


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
    sampled = sample_markings(recipe, scheme, rows[:DEFAULT_SAMPLE_SIZE])
    return profile_source(
        rows,
        source_handling=source_handling,
        principal=principal,
        scheme=scheme,
        source_markings=sampled.markings,
        unviewable=sampled.unviewable,
    )
