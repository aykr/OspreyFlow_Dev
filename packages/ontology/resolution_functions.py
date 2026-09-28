"""Closed function registry for the ontology's `resolution: {blocking, comparisons}` block —
`01_DOMAIN_MODEL.md` §4, `spec/06_DECISIONS.md` ADR-021. A fixed, enumerated vocabulary mapping
function names (`soundex`, `year`, `jaro_winkler`, `levenshtein`, `exact`) to Splink blocking-rule
SQL and comparison-library constructors — the same shape as the Knowledge Adapters
(`01_DOMAIN_MODEL.md` §7) rather than a parser for an open expression language. ADR-018 refuses
scripting in the Ingest Studio for exactly this reason (an unreviewable, untestable transformation
layer); a deployment's own ontology YAML is authored by whoever configures the deployment, not an
analyst through the studio, but the same discipline applies — a string like
`jaro_winkler(family_name)` is still a tiny expression language if nothing closes the vocabulary
it draws from.

Validated at ontology-*load* time (`packages/ontology/loader.py`), not at Splink-setup time
(`services/resolve`): an unknown function name is a malformed-ontology error, the same class
`packages/ontology/validation.py` already raises for an undeclared property or an unknown entity
type, not a runtime surprise deep inside the resolution service on whatever entity type happens to
resolve first.

`soundex` needs a DuckDB scalar UDF (`services/resolve/duckdb_setup.py` registers it) since DuckDB
has no built-in `soundex()` — confirmed directly, not assumed: `SELECT soundex('MERCER')` raises
`Catalog Error: Scalar Function with name soundex does not exist!`. `year`/`levenshtein`/
`jaro_winkler_similarity` are DuckDB built-ins, confirmed the same way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import OntologyError

_CALL_PATTERN = re.compile(r"^([a-z_][a-z0-9_]*)\(([^()]*)\)$")


@dataclass(frozen=True)
class ResolutionFunctionCall:
    name: str
    args: tuple[str, ...]


def parse_resolution_function(expr: str) -> ResolutionFunctionCall:
    """`"jaro_winkler(family_name)"` -> `ResolutionFunctionCall("jaro_winkler", ("family_name",))`.
    Raises `OntologyError` for anything that isn't `name(arg[, arg...])` — no operators, no
    nesting, no literals: exactly a function call, since that is all the closed vocabulary below
    ever needs to express."""
    match = _CALL_PATTERN.match(expr.strip())
    if match is None:
        raise OntologyError(
            f"{expr!r} is not a valid resolution function call — "
            "expected `name(column[, column...])`"
        )
    name, raw_args = match.groups()
    args = tuple(a.strip() for a in raw_args.split(",")) if raw_args.strip() else ()
    if not args or any(not a for a in args):
        raise OntologyError(f"{expr!r}: every argument must be a non-empty column name")
    return ResolutionFunctionCall(name=name, args=args)


#: Every blocking function takes exactly one column and produces a SQL boolean condition over
#: `l.<col>`/`r.<col>` — Splink's own `blocking_rules_to_generate_predictions` shape.
BLOCKING_FUNCTIONS: dict[str, int] = {
    "exact": 1,
    "soundex": 1,
    "year": 1,
}

#: Every comparison function takes exactly one column and maps to a
#: `splink.duckdb.comparison_library` constructor name — resolved lazily in
#: `services/resolve/splink_config.py`, not imported here, so ontology loading and validation
#: never need `splink` importable at all.
COMPARISON_FUNCTIONS: dict[str, int] = {
    "exact": 1,
    "jaro_winkler": 1,
    "levenshtein": 1,
}


def blocking_rule_sql(call: ResolutionFunctionCall) -> str:
    """The Splink blocking-rule SQL string for one validated call. Only ever invoked on a call
    already checked against `BLOCKING_FUNCTIONS` — an unregistered name raises the same way
    `validate_resolution_config` does, so a caller that skips validation still fails loudly rather
    than emitting SQL for an unknown function."""
    (column,) = call.args
    if call.name == "exact":
        return f"l.{column} = r.{column}"
    if call.name == "soundex":
        return f"soundex(l.{column}) = soundex(r.{column})"
    if call.name == "year":
        return f"year(l.{column}) = year(r.{column})"
    raise OntologyError(f"{call.name!r} is not a registered blocking function")


def validate_resolution_config(
    entity_type_name: str, blocking: list[str], comparisons: list[str]
) -> None:
    """Raises `OntologyError` naming the entity type and the offending expression for any blocking
    or comparison string that doesn't parse, uses an unregistered function name, or passes the
    wrong number of arguments."""
    for expr in blocking:
        call = parse_resolution_function(expr)
        _check_registered(entity_type_name, "blocking", expr, call, BLOCKING_FUNCTIONS)
    for expr in comparisons:
        call = parse_resolution_function(expr)
        _check_registered(entity_type_name, "comparisons", expr, call, COMPARISON_FUNCTIONS)


def _check_registered(
    entity_type_name: str,
    block_name: str,
    expr: str,
    call: ResolutionFunctionCall,
    registry: dict[str, int],
) -> None:
    arity = registry.get(call.name)
    if arity is None:
        raise OntologyError(
            f"{entity_type_name!r}.resolution.{block_name}: {expr!r} uses unregistered function "
            f"{call.name!r} — known functions: {sorted(registry)}"
        )
    if len(call.args) != arity:
        raise OntologyError(
            f"{entity_type_name!r}.resolution.{block_name}: {expr!r} takes {arity} argument(s), "
            f"got {len(call.args)}"
        )
