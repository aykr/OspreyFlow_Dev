"""What Map writes from a fuzzy match (ADR-006 Amendment 1; ADR-140 decision 13; R13; rules 5
and 6).

A pipeline whose last step is a fuzzy match (`fuzzy_match.run_fuzzy_step`) gives Map, on each row,
the left row's columns, the matched right row's added columns and `match_score`. The engine asks
this module three things of such a recipe:

- **which elements are inferred** (`FuzzyPlan.entity_inferred`): an entity that binds, or is
  conditional on, a matched column (an added column or `match_score`), and a link that does, or
  joins such an entity. On a matched row each is written `inferred`, its `extraction_confidence` the
  match's score; nothing a fuzzy match decided is ever written as fact (R13; rule 5). A row below
  the threshold has those cells empty, so what it writes from them is absent.
- **the row's score** (`FuzzyPlan.score`), read from the row's `match_score` cell.
- **the `SAME_AS`** (`FuzzyPlan.same_as_edge`): on a matched row, a scored `SAME_AS` between the two
  elements `same_as` names, marked `inferred` with its score, its method and the version's threshold
  in its properties, and the row's refs (both sides) as its sources, exactly as Splink's post-load
  resolution writes one (`services/resolve/same_as_writer.py`). **Never a merge** (rule 6): the two
  elements stay two nodes, collapsed only at read by the Conduit's threshold. A person confirms or
  undoes it in the Glass (`confirm_inferred`); no threshold confirms it (rule 5).

`fuzzy_link_problems` is the recipe's own gate: the two elements named exist, are of one type, and
the right one is written from the matched columns and the left one from none of them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from schemas.ingest import FieldBinding, Recipe, RecipeEdge, RecipeEntity, RowTemplate
from schemas.staging import MATCH_SCORE, FuzzyMatchStep

from .fuzzy_match import MODEL_VERSION


def fuzzy_step(recipe: Recipe) -> FuzzyMatchStep | None:
    """The recipe's fuzzy match, which the save gate makes its last step; `None` if it has none."""
    if recipe.staging and isinstance(recipe.staging[-1], FuzzyMatchStep):
        return recipe.staging[-1]
    return None


def matched_columns(step: FuzzyMatchStep) -> frozenset[str]:
    return frozenset({*(a.as_ or a.column for a in step.add), MATCH_SCORE})


def _binding_columns(binding: FieldBinding) -> set[str]:
    return {c for c in (binding.field, *(binding.fields or [])) if c}


def element_columns(element: RecipeEntity | RecipeEdge) -> set[str]:
    """Every column an element reads: its bindings, its condition, its content and its time."""
    columns: set[str] = set()
    for binding in element.properties.values():
        columns |= _binding_columns(binding)
    if element.when is not None:
        columns.add(element.when.field)
    if element.content is not None:
        columns.add(element.content.field)
    if isinstance(element, RecipeEdge) and element.temporal is not None:
        columns |= _binding_columns(element.temporal.at)
        if element.temporal.valid_to is not None:
            columns |= _binding_columns(element.temporal.valid_to)
    return columns


def fuzzy_link_problems(recipe: Recipe) -> list[str]:
    """The recipe's own rules for its fuzzy match's `SAME_AS`, in words."""
    step = fuzzy_step(recipe)
    if step is None:
        return []
    template: RowTemplate = recipe.row_template
    entities = {e.ref: e for e in template.entities}
    matched = matched_columns(step)
    problems: list[str] = []
    for side in ("left", "right"):
        ref = getattr(step.same_as, side)
        if ref not in entities:
            problems.append(
                f"step {step.id!r}'s SAME_AS names {ref!r} as its {side} element, which Map's row "
                "template does not have"
            )
    if problems:
        return problems
    left, right = entities[step.same_as.left], entities[step.same_as.right]
    if left.type != right.type:
        problems.append(
            f"step {step.id!r}'s SAME_AS joins a {left.type} to a {right.type}: a SAME_AS says "
            "two records may be one thing, so both are of one type"
        )
    if element_columns(left) & matched:
        problems.append(
            f"step {step.id!r}'s left element {left.ref!r} is written from a matched column: it "
            "is the left row's own, written from the left table's columns"
        )
    if not element_columns(right) & matched:
        problems.append(
            f"step {step.id!r}'s right element {right.ref!r} is written from no matched column "
            f"({', '.join(sorted(matched - {MATCH_SCORE}))}): it is the matched row's"
        )
    return problems


@dataclass(frozen=True)
class FuzzyPlan:
    step: FuzzyMatchStep
    recipe_id: str
    recipe_version: int
    inferred_entities: frozenset[str]
    scores: Mapping[int, float]
    template_edges: tuple[RecipeEdge, ...] = ()

    def score(self, row_index: int) -> float | None:
        return self.scores.get(row_index)

    def entity_inferred(self, entity: RecipeEntity) -> bool:
        return entity.ref in self.inferred_entities

    def edge_inferred(self, edge: RecipeEdge) -> bool:
        return (
            bool(element_columns(edge) & matched_columns(self.step))
            or edge.from_ref in self.inferred_entities
            or edge.to_ref in self.inferred_entities
        )

    def edge_inferred_by(self, edge_type: str, from_ref: str, to_ref: str) -> bool:
        """`edge_inferred` for a link as the engine holds it (its type and ends): the match's own
        SAME_AS, a link joining an inferred element, or any of the template's links of that type
        and those ends that reads a matched column."""
        if edge_type == "SAME_AS" or from_ref in self.inferred_entities:
            return True
        if to_ref in self.inferred_entities:
            return True
        return any(
            self.edge_inferred(e)
            for e in self.template_edges
            if (e.type, e.from_ref, e.to_ref) == (edge_type, from_ref, to_ref)
        )

    def same_as_edge(self) -> RecipeEdge:
        """The `SAME_AS` as a link of Map's template, which the engine writes on a matched row
        through its own link path (the recipe's own rules refuse `SAME_AS` in a template)."""
        return RecipeEdge.model_validate(
            {
                "type": "SAME_AS",
                "from": self.step.same_as.left,
                "to": self.step.same_as.right,
                "provenance": {"state": "inferred"},
            }
        )

    def same_as_properties(self, score: float) -> dict[str, object]:
        return {
            "score": score,
            "model_version": MODEL_VERSION,
            "comparison_vector": json.dumps(
                {
                    "step": self.step.id,
                    "pipeline": f"{self.recipe_id}@v{self.recipe_version}",
                    "threshold": self.step.threshold,
                    "compare": [c.model_dump() for c in self.step.compare],
                    "block_on": [b.model_dump() for b in self.step.block_on],
                },
                sort_keys=True,
            ),
        }


def fuzzy_plan(recipe: Recipe, rows: Sequence[Mapping[str, str]]) -> FuzzyPlan | None:
    step = fuzzy_step(recipe)
    if step is None:
        return None
    matched = matched_columns(step)
    inferred = frozenset(
        e.ref for e in recipe.row_template.entities if element_columns(e) & matched
    )
    scores: dict[int, float] = {}
    for index, row in enumerate(rows):
        cell = (row.get(MATCH_SCORE) or "").strip()
        if cell:
            scores[index] = float(cell)
    return FuzzyPlan(
        step, recipe.id, recipe.version, inferred, scores, tuple(recipe.row_template.edges)
    )
