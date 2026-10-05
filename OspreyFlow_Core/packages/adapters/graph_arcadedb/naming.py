"""Physical ArcadeDB type names for ontology entity/edge types.

ArcadeDB reserves some identifiers as SQL keywords — `Document`, a real
default-ontology entity type name (`01_DOMAIN_MODEL.md` §1), collides with
ArcadeDB's own base document type — and its DDL parser has no
identifier-quoting mechanism to escape them (backticks, double quotes and
square brackets were all tried against a live instance; none work). Every
ontology type name is namespaced with a fixed prefix before it reaches
ArcadeDB, so any such collision is avoided uniformly rather than
special-cased for the names known to collide today.
"""

from __future__ import annotations

_PREFIX = "mx_"

#: Between a proposed link type's name and its proposal id in the label its links are stored under.
#: A type name never contains it (`services/api/link_types.py` refuses one that does).
STORAGE_SEPARATOR = "__"


def physical_type_name(logical_name: str) -> str:
    return f"{_PREFIX}{logical_name}"


#: ADR-090 Amendment 1, by alias: an old link-type name -> the type it now answers to, and the
#: reverse, from the ontology last applied (`set_edge_aliases`). One ontology is in force per
#: process.
_CANONICAL: dict[str, str] = {}
_ALIASES_OF: dict[str, tuple[str, ...]] = {}


def set_edge_aliases(aliases_by_type: dict[str, list[str]]) -> None:
    """The aliases each link type declares; replaces what was set before."""
    _CANONICAL.clear()
    _ALIASES_OF.clear()
    for canonical, aliases in aliases_by_type.items():
        if aliases:
            _ALIASES_OF[canonical] = tuple(aliases)
            for alias in aliases:
                _CANONICAL[alias] = canonical


def logical_type_name(physical_name: str) -> str:
    """The ontology type a stored label is; an alias reads as the type it now answers to."""
    if not physical_name.startswith(_PREFIX):
        raise ValueError(f"not an OspreyFlow-namespaced ArcadeDB type: {physical_name!r}")
    name = physical_name[len(_PREFIX) :]
    if name in _CANONICAL:
        return _CANONICAL[name]
    # A proposal's own label, `<name>__<proposal id>` (ADR-090 Amendment 1), not yet in this
    # process's aliases (proposed through another process since this one composed): its name.
    return name.split(STORAGE_SEPARATOR, 1)[0]


def physical_edge_labels(logical_name: str) -> list[str]:
    """Every stored label a link type's filter must match: its own, then its aliases'."""
    return [physical_type_name(logical_name)] + [
        physical_type_name(alias) for alias in _ALIASES_OF.get(logical_name, ())
    ]
