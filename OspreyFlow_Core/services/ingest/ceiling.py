"""The deployment's marking ceiling (ADR-148 decision 10, L1.10): `osprey.yaml`'s
`deployment.highest_marking`, rendered as `OSPREY_HIGHEST_MARKING`, defaulting to the handling
scheme's highest. A load marked above it is refused before anything is written, in words that say
the deployment's limit and never the item's content.

The ingest engine reads it here (`engine.run_recipe` judges every load through it), and so does the
Conduit: an unknown value stops the Conduit's start rather than guess a limit (as an unknown grading
scheme does), since a guessed ceiling would let through what the deployment may not hold.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ontology.handling import HandlingScheme, load_uk_le_scheme

from .recipe_rules import RecipeRuleError, handling_bindings, literal_handling, template_elements

if TYPE_CHECKING:
    from schemas.ingest import Recipe

#: The rendered `deployment.env` line the Conduit and the ingest service read.
CEILING_ENV = "OSPREY_HIGHEST_MARKING"


class CeilingUnknown(ValueError):
    """`OSPREY_HIGHEST_MARKING` names no classification of the handling scheme: the Conduit does
    not start, rather than guess the deployment's limit."""


class AboveTheDeploymentCeiling(RecipeRuleError):
    """A load is refused whole, before anything is written, because it would write a marking above
    the deployment's highest. A `RecipeRuleError`, so every caller (a run, the run ledger, the
    Studio's routes) already handles it. Its words say the limit, never the content."""

    def __init__(self, ceiling: str) -> None:
        super().__init__(
            [
                f"This load would write rows marked above this deployment's highest marking, "
                f"{ceiling}, so nothing was loaded. Mark the source no higher than {ceiling}, or "
                "load it into a deployment cleared to hold it."
            ]
        )
        self.ceiling = ceiling


@dataclass(frozen=True)
class DeploymentCeiling:
    """The highest classification this deployment may hold, in the scheme it is judged by."""

    marking: str
    scheme: HandlingScheme

    @classmethod
    def from_env(cls, scheme: HandlingScheme | None = None) -> DeploymentCeiling:
        """The rendered setting, in the scheme the Conduit loads (UK law enforcement,
        `services/api/run_resources.py`). Nothing set is the scheme's highest: no ceiling."""
        scheme = scheme or load_uk_le_scheme()
        raw = (os.environ.get(CEILING_ENV) or "").strip()
        if not raw:
            return cls(marking=scheme.classification[-1], scheme=scheme)
        if raw not in scheme.classification:
            raise CeilingUnknown(
                f"{CEILING_ENV} {raw!r} is not a classification of the {scheme.name} handling "
                f"scheme: use one of {', '.join(scheme.classification)}"
            )
        return cls(marking=raw, scheme=scheme)

    def above(self, classification: str) -> bool:
        """Whether `classification` is above the ceiling. One the scheme does not know is treated
        as above it: the ceiling fails closed."""
        if classification not in self.scheme.classification:
            return True
        return self.scheme.classification.index(classification) > self.scheme.classification.index(
            self.marking
        )

    @property
    def is_the_scheme_s_highest(self) -> bool:
        return self.marking == self.scheme.classification[-1]


def refuse_fixed_markings_above_the_ceiling(recipe: Recipe, ceiling: DeploymentCeiling) -> None:
    """What can be judged without a row: a marking no column sets (the recipe's defaults where an
    element binds nothing, or an element's own literal marking). Asked before a staged pipeline
    writes its step tables, and again by `run_recipe`."""
    if ceiling.is_the_scheme_s_highest:
        return
    defaults = recipe.defaults.handling
    elements = template_elements(recipe.row_template)
    fixed: list[str] = []
    for element in elements:
        if "classification" in handling_bindings(element.handling):
            continue
        literal = literal_handling(element.handling) or {}
        fixed.append(str(literal.get("classification") or defaults.get("classification") or ""))
    if not elements:
        fixed.append(str(defaults.get("classification") or ""))
    if any(c and ceiling.above(c) for c in fixed):
        raise AboveTheDeploymentCeiling(ceiling.marking)


def refuse_rows_above_the_ceiling(
    recipe: Recipe, rows: Iterable[Mapping[str, str]], ceiling: DeploymentCeiling
) -> None:
    """Each row's marking, as the engine marks a record of the whole row (`engine.row_marking`): a
    part that cannot be read counts as its strictest possible marking, so the check fails closed.
    A row rejected for a conflict between units is not written, so it is not judged. One row above
    the ceiling refuses the whole load."""
    if ceiling.is_the_scheme_s_highest:
        return
    from .engine import RowRejected, row_marking

    refuse_fixed_markings_above_the_ceiling(recipe, ceiling)
    for row in rows:
        try:
            marking = row_marking(recipe, row, ceiling.scheme)
        except RowRejected:
            continue
        if ceiling.above(marking.classification):
            raise AboveTheDeploymentCeiling(ceiling.marking)
