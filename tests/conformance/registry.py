"""Adapter registry for the port conformance suites.

Each port's `test_suite.py` is parametrised over its list here. `GraphPort`
is real from Phase 1: `GRAPH_PORT_ADAPTERS` holds one `GraphAdapterFactory`
per (adapter, dialect) pair the suite must prove — a live ArcadeDB
connection can't sit in a module-level list the way an empty Phase 0 entry
could, so each factory opens a fresh adapter instance per test rather than
being the adapter itself.

`AnalyticsPort`/`ComputePort`/`ModelPort` stay empty until Phases 2, 6 and 7
register their own adapters — `test_guard.py` for each still asserts its
list is empty, so a later phase populating one flips that guard red as the
expected handover, same as `graph_port/test_guard.py` did this phase.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ports.analytics import AnalyticsPort
    from ports.compute import ComputePort
    from ports.graph import GraphPort
    from ports.model import ModelPort


@dataclass(frozen=True)
class GraphAdapterFactory:
    """One conformance-testable (adapter, dialect) pair."""

    label: str
    dialect: str
    context: Callable[[], AbstractAsyncContextManager[GraphPort]]

    def __str__(self) -> str:  # pytest parametrize id
        return f"{self.label}[{self.dialect}]"


def _graph_arcadedb_factories() -> list[GraphAdapterFactory]:
    from adapters.graph_arcadedb.testing import arcadedb_adapter
    from ontology.handling import load_uk_le_scheme
    from ontology.loader import load_default_ontology

    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    def _context() -> AbstractAsyncContextManager[GraphPort]:
        return arcadedb_adapter(ontology, scheme)

    return [GraphAdapterFactory(label="graph_arcadedb", dialect="gremlin", context=_context)]


GRAPH_PORT_ADAPTERS: list[GraphAdapterFactory] = _graph_arcadedb_factories()
ANALYTICS_PORT_ADAPTERS: list[AnalyticsPort] = []
COMPUTE_PORT_ADAPTERS: list[ComputePort] = []
MODEL_PORT_ADAPTERS: list[ModelPort] = []
