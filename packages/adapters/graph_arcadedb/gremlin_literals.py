"""Safe literal encoding for Gremlin/Groovy strings embedded in a traversal.

ArcadeDB executes Gremlin as Groovy. A Groovy **double**-quoted string is a
GString and interpolates `$var`/`${expr}` — embedding an untrusted value
(a property from an ingested document, say) in one is a script-injection
hole. Single-quoted Groovy strings are plain strings with no interpolation,
so every literal this adapter embeds uses single quotes, with the value's
own backslashes and single quotes escaped first.
"""

from __future__ import annotations

from collections.abc import Iterable


def groovy_string_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def groovy_args_literal(values: Iterable[str]) -> str:
    """Comma-separated literals for a Gremlin varargs step, e.g.
    `select('a','b','c')` — as opposed to a single list-typed argument."""
    return ",".join(groovy_string_literal(v) for v in values)


def groovy_string_list_literal(values: Iterable[str]) -> str:
    return "[" + groovy_args_literal(values) + "]"


_SAFE_IDENTIFIER_CACHE: set[str] = set()


def groovy_identifier(name: str) -> str:
    """A bare identifier (an edge/entity type name, a property key) embedded
    directly rather than as a string literal. Only ontology-configured names
    reach this — validated once here as defence in depth against an
    ontology file that is not what it claims to be."""
    if name not in _SAFE_IDENTIFIER_CACHE:
        if not name.replace("_", "").replace("-", "").isalnum() or not name:
            raise ValueError(f"not a safe identifier for a Gremlin/SQL literal: {name!r}")
        _SAFE_IDENTIFIER_CACHE.add(name)
    return name
