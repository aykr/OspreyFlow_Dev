"""The deployment's marking ceiling (ADR-148 decision 10, L1.10): `osprey.yaml`'s
`deployment.highest_marking`, rendered as `OSPREY_HIGHEST_MARKING`, defaulting to the handling
scheme's highest. A load marked above it is refused before anything is written, in words that say
the deployment's limit and never the item's content.

The ingest engine reads it here (`engine.run_recipe` judges every load through it), and so does the
Conduit: an unknown value stops the Conduit's start rather than guess a limit (as an unknown grading
scheme does), since a guessed ceiling would let through what the deployment may not hold.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ontology.handling import HandlingScheme, load_uk_le_scheme

from .recipe_rules import RecipeRuleError, handling_bindings, literal_handling, template_elements

if TYPE_CHECKING:
    from schemas.domain import Handling
    from schemas.ingest import Recipe


class _Marked(Protocol):
    @property
    def handling(self) -> Handling: ...


#: The rendered `deployment.env` line the Conduit and the ingest service read.
CEILING_ENV = "OSPREY_HIGHEST_MARKING"


class CeilingUnknown(ValueError):
    """`OSPREY_HIGHEST_MARKING` names no classification of the handling scheme: the Conduit does
    not start, rather than guess the deployment's limit."""


#: The words for each kind of refusal (ADR-148 decision 10): the deployment's limit, never the
#: item's content.
_WORDS: dict[str, str] = {
    "load": (
        "This load would write rows marked above this deployment's highest marking, {c}, so "
        "nothing was loaded. Mark the source no higher than {c}, or load it into a deployment "
        "cleared to hold it."
    ),
    "unreadable": (
        "Some rows' classification cannot be read, and such a row is held at the handling "
        "scheme's highest marking, above this deployment's highest, {c}, so nothing was loaded. "
        "Correct the source's classification column, or mark it no higher than {c}."
    ),
    "import": (
        "This file is marked above this deployment's highest marking, {c}, so it was not added. "
        "Mark it no higher than {c}."
    ),
    "write": (
        "This would write something marked above this deployment's highest marking, {c}, so "
        "nothing was written."
    ),
}


class AboveTheDeploymentCeiling(RecipeRuleError):
    """A load, an import or a write is refused whole, before anything is written, because it
    would hold a marking above the deployment's highest (or one that cannot be read). A
    `RecipeRuleError`, so every caller (a run, the run ledger, the Studio's routes) already
    handles it. Its words say the limit, never the content."""

    def __init__(self, ceiling: str, kind: str = "load") -> None:
        super().__init__([_WORDS[kind].format(c=ceiling)])
        self.ceiling = ceiling
        self.kind = kind


@dataclass(frozen=True)
class DeploymentCeiling:
    """The highest classification this deployment may hold, in the scheme it is judged by."""

    marking: str
    scheme: HandlingScheme

    @classmethod
    def from_env(cls, scheme: HandlingScheme | None = None) -> DeploymentCeiling:
        """The rendered setting, in the scheme the Conduit loads (UK law enforcement,
        `services/api/run_resources.py`). Nothing set is the scheme's highest: no ceiling."""
        return cls.of((os.environ.get(CEILING_ENV) or "").strip(), scheme or load_uk_le_scheme())

    @classmethod
    def of(cls, raw: str, scheme: HandlingScheme) -> DeploymentCeiling:
        """The ceiling a rendered value names: none is the scheme's highest; an unknown one is
        refused."""
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
    element binds nothing, or an element's own literal marking), and the floor a bound element
    falls back to on an empty cell, which no cell can lower. Asked before a staged pipeline writes
    its step tables, and again by `run_recipe`."""
    if ceiling.is_the_scheme_s_highest:
        return
    defaults = recipe.defaults.handling
    elements = template_elements(recipe.row_template)
    fixed: list[str] = []
    for element in elements:
        # A bound element's literal holds no classification, so its floor is the defaults'.
        literal = literal_handling(element.handling) or {}
        fixed.append(str(literal.get("classification") or defaults.get("classification") or ""))
    if not elements:
        fixed.append(str(defaults.get("classification") or ""))
    if any(c and ceiling.above(c) for c in fixed):
        raise AboveTheDeploymentCeiling(ceiling.marking)


def _row_classifications(
    recipe: Recipe, row: Mapping[str, str], scheme: HandlingScheme
) -> tuple[set[str], bool]:
    """The classifications one row's elements would be written at, and whether any cannot be read.
    Classification alone is judged, element by element (an element whose `when` does not hold
    writes nothing): a bound cell, or the element's default where the cell is empty, both kept, so
    the stricter decides. A column the source lacks, or a value the scheme does not define, cannot
    be read. A bad originator or code beside a readable classification is the engine's to reject,
    with its cause; a conflict between units does not stop the row being judged."""
    from .engine import _condition_holds

    defaults = recipe.defaults.handling
    found: set[str] = set()
    unreadable = False
    elements = template_elements(recipe.row_template)
    for element in elements:
        if not _condition_holds(element.when, row):
            continue
        literal = literal_handling(element.handling) or {}
        default = str(literal.get("classification") or defaults.get("classification") or "")
        found.add(default)
        column = handling_bindings(element.handling).get("classification")
        if column is None:
            continue
        if column not in row:
            unreadable = True
            continue
        cell = (row[column] or "").strip()
        if not cell:
            continue
        if cell in scheme.classification:
            found.add(cell)
        else:
            unreadable = True
    if not elements:
        found.add(str(defaults.get("classification") or ""))
    return {c for c in found if c}, unreadable


def refuse_rows_above_the_ceiling(
    recipe: Recipe, rows: Iterable[Mapping[str, str]], ceiling: DeploymentCeiling
) -> None:
    """Every row's classifications (`_row_classifications`), each distinct combination of the
    columns they depend on resolved once, as the engine's own `_row_markings` keys them, not once
    per row of a million. One row above the ceiling refuses the whole load; one whose
    classification cannot be read refuses it too (the engine holds such a row's sample at the
    scheme's highest), in words that say so."""
    if ceiling.is_the_scheme_s_highest:
        return
    refuse_fixed_markings_above_the_ceiling(recipe, ceiling)
    columns: set[str] = set()
    for element in template_elements(recipe.row_template):
        bound = handling_bindings(element.handling).get("classification")
        if bound is not None:
            columns.add(bound)
        if element.when is not None:
            columns.add(element.when.field)
    ordered = sorted(columns)
    seen: set[tuple[tuple[bool, str | None], ...]] = set()
    unreadable = False
    for row in rows:
        # A column the row lacks is not the same as one it has empty (the first is unreadable).
        key = tuple((c in row, row.get(c)) for c in ordered)
        if key in seen:
            continue
        seen.add(key)
        found, cannot_read = _row_classifications(recipe, row, ceiling.scheme)
        if any(ceiling.above(c) for c in found):
            raise AboveTheDeploymentCeiling(ceiling.marking)
        unreadable = unreadable or cannot_read
    if unreadable:
        raise AboveTheDeploymentCeiling(ceiling.marking, "unreadable")


@functools.lru_cache(maxsize=8)
def _ceiling_for(raw: str) -> DeploymentCeiling:
    """The ceiling a rendered value names, read once per value (the scheme is a file)."""
    return DeploymentCeiling.of(raw, load_uk_le_scheme())


def refuse_writes_above_the_ceiling(writes: Iterable[_Marked]) -> None:
    """The backstop (L1.10, the orchestrator's (a)): node or link writes, judged by their own
    marking before the store is reached. The dataset-stamping graph asks it of every write, so a
    path the engine's own check never sees (a demo seed writing the graph directly) cannot write
    above the ceiling either. The ceiling is the rendered setting, read once per value."""
    ceiling = _ceiling_for((os.environ.get(CEILING_ENV) or "").strip())
    if ceiling.is_the_scheme_s_highest:
        return
    if any(ceiling.above(write.handling.classification) for write in writes):
        raise AboveTheDeploymentCeiling(ceiling.marking, "write")
