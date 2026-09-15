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


def physical_type_name(logical_name: str) -> str:
    return f"{_PREFIX}{logical_name}"


def logical_type_name(physical_name: str) -> str:
    if not physical_name.startswith(_PREFIX):
        raise ValueError(f"not an OspreyFlow-namespaced ArcadeDB type: {physical_name!r}")
    return physical_name[len(_PREFIX) :]
