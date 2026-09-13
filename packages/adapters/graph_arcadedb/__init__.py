"""`GraphPort` over ArcadeDB — `docs/04_VAULT_BACKEND.md` §1, `docs/06_DECISIONS.md` ADR-003.

`local-lite`'s graph store: one ArcadeDB container, reached over its HTTP
API. Traversal reads are Gremlin, constructed by `builders.py` from bounded
intent objects and rendered here — never free-form, and the access filter is
injected into every traversal rather than applied after retrieval.
"""

from __future__ import annotations

from .adapter import GraphArcadeDBAdapter

__all__ = ["GraphArcadeDBAdapter"]
