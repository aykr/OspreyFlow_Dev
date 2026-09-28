"""Builds a Splink settings dict from one entity type's ontology `resolution` block —
`01_DOMAIN_MODEL.md` §4: "Blocking rules and comparisons come from the ontology's `resolution`
block per entity type, so adding an entity type does not require touching the resolution
service." The closed function registry (`packages/ontology/resolution_functions.py`,
`spec/06_DECISIONS.md` ADR-021) is what makes that literally true — this module never inspects an
entity type's *name*, only its `resolution.blocking`/`comparisons` lists, already validated at
ontology-load time.

No m/u training happens here or in `resolver.py` — `06_DECISIONS.md` ADR-021's 18 September 2026
addendum is the decision record (why, the hand-labelled accuracy evidence, the honest cost of
uncalibrated probabilities, and the "revisit if" clause); this docstring only carries the
implementation-level summary, not the decision itself. Confirmed directly: Splink's
`comparison_library` helpers (`jaro_winkler_at_thresholds`, `levenshtein_at_thresholds`,
`exact_match`) ship usable default m/u priors and produce sensible `match_probability` values from
`predict()` with no `estimate_u_using_random_sampling`/EM training step at all. Real
expectation-maximisation training needs "at least a few hundred, preferably thousand" comparisons
(Splink's own guidance) — an investigation's own Person population is routinely far smaller than
that, so per-investigation EM training would silently produce statistically meaningless weights
on exactly the small cases where getting this right matters most. Deployment-wide model training
against a real historical corpus is a real, separate capability with its own persistence and
retraining story; not assumed into this stage's scope.
"""

from __future__ import annotations

from typing import Any

from splink.duckdb.comparison_library import (
    exact_match,
    jaro_winkler_at_thresholds,
    levenshtein_at_thresholds,
)

from ontology.resolution_functions import blocking_rule_sql, parse_resolution_function
from schemas.domain import EntityTypeDef

#: One Splink `comparison_library` constructor per registered comparison function name
#: (`packages/ontology/resolution_functions.py`'s `COMPARISON_FUNCTIONS`) — kept here, not there,
#: so ontology loading and validation never need `splink` importable at all.
_COMPARISON_BUILDERS = {
    "exact": exact_match,
    "jaro_winkler": jaro_winkler_at_thresholds,
    "levenshtein": levenshtein_at_thresholds,
}

#: Bumped whenever this module's config-building logic changes meaningfully — carried onto every
#: `SAME_AS` edge's `model_version` property (`same_as_writer.py`) alongside the Splink package
#: version itself, so a later change to *how* a comparison is built is distinguishable from a
#: change to *which* Splink release produced a score.
CONFIG_VERSION = "1"


def build_settings(entity_type: EntityTypeDef) -> dict[str, Any]:
    """Raises `ValueError` if `entity_type.resolution` is `None` — a caller's job to check first:
    `resolver.py` only ever calls this for entity types the ontology declares a resolution block
    for (`01_DOMAIN_MODEL.md` §4: "Only run Splink on types where identity is genuinely
    uncertain.")."""
    if entity_type.resolution is None:
        raise ValueError(f"{entity_type.name!r} has no resolution config")

    blocking_calls = [parse_resolution_function(e) for e in entity_type.resolution.blocking]
    comparison_calls = [parse_resolution_function(e) for e in entity_type.resolution.comparisons]

    return {
        "link_type": "dedupe_only",
        "blocking_rules_to_generate_predictions": [blocking_rule_sql(c) for c in blocking_calls],
        "comparisons": [_COMPARISON_BUILDERS[c.name](c.args[0]) for c in comparison_calls],
        "retain_matching_columns": True,
        "retain_intermediate_calculation_columns": True,
    }


def comparison_columns(entity_type: EntityTypeDef) -> list[str]:
    """The distinct column names every comparison in `entity_type.resolution.comparisons`
    references — what `resolver.py` needs to know which `Node.properties` keys to pull into the
    DataFrame Splink reads, without re-parsing the resolution config itself."""
    if entity_type.resolution is None:
        return []
    seen: list[str] = []
    for expr in entity_type.resolution.comparisons:
        column = parse_resolution_function(expr).args[0]
        if column not in seen:
            seen.append(column)
    return seen


def blocking_columns(entity_type: EntityTypeDef) -> list[str]:
    if entity_type.resolution is None:
        return []
    seen: list[str] = []
    for expr in entity_type.resolution.blocking:
        column = parse_resolution_function(expr).args[0]
        if column not in seen:
            seen.append(column)
    return seen
