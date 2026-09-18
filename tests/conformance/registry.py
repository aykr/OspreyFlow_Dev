"""Adapter registry for the port conformance suites.

Each port's `test_suite.py` is parametrised over its list here. `GraphPort`
is real from Phase 1: `GRAPH_PORT_ADAPTERS` holds one `GraphAdapterFactory`
per (adapter, dialect) pair the suite must prove — a live ArcadeDB
connection can't sit in a module-level list the way an empty Phase 0 entry
could, so each factory opens a fresh adapter instance per test rather than
being the adapter itself. `AnalyticsPort` is real from Phase 2:
`ANALYTICS_PORT_ADAPTERS` holds one `AnalyticsAdapterFactory` per adapter —
its `context()` additionally takes the test's own `EventRecord` fixtures,
since (unlike the graph store) each test seeds its own event population
rather than sharing one ontology-applied schema.

`ComputePort` stays empty until Phase 7 registers its own adapter —
`test_guard.py` still asserts its list is empty, so Phase 7 populating it
flips that guard red as the expected handover, same as `graph_port/
test_guard.py` and `analytics_port/test_guard.py` did. `ModelPort` is real
from Phase 6 Stage 1: `MODEL_PORT_ADAPTERS` holds one `ModelAdapterFactory`
for `adapters/model_litellm`, calling the pinned conformance model
(`adapters.model_litellm.CONFORMANCE_MODEL`, `06_DECISIONS.md` ADR-020)
over a live LiteLLM proxy — the same "prove it against the real backend"
discipline `GraphPort`/`AnalyticsPort` already established, not a fake.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ports.analytics import AnalyticsPort
    from ports.compute import ComputePort
    from ports.graph import GraphPort
    from ports.model import ModelPort
    from schemas.analytics import EventRecord


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


@dataclass(frozen=True)
class AnalyticsAdapterFactory:
    """One conformance-testable `AnalyticsPort` adapter. `context()` takes
    the calling test's own `EventRecord` fixtures — there is no shared
    schema to apply once, the way `GraphAdapterFactory` applies an
    ontology, since every test's event population is its own fixture."""

    label: str
    context: Callable[[Sequence[EventRecord]], AbstractAsyncContextManager[AnalyticsPort]]

    def __str__(self) -> str:  # pytest parametrize id
        return self.label


def _analytics_duckdb_factories() -> list[AnalyticsAdapterFactory]:
    from adapters.analytics_duckdb.testing import duckdb_adapter
    from ontology.handling import load_uk_le_scheme

    scheme = load_uk_le_scheme()

    def _context(
        events: Sequence[EventRecord],
    ) -> AbstractAsyncContextManager[AnalyticsPort]:
        return duckdb_adapter(events, scheme)

    return [AnalyticsAdapterFactory(label="analytics_duckdb", context=_context)]


@dataclass(frozen=True)
class ModelAdapterFactory:
    """One conformance-testable `ModelPort` adapter. Unlike `GraphAdapterFactory`/
    `AnalyticsAdapterFactory`, `context()` takes no fixtures — there is no schema or event
    population to apply first; a LiteLLM proxy is called directly, stateless from the adapter's
    own point of view."""

    label: str
    context: Callable[[], AbstractAsyncContextManager[ModelPort]]

    def __str__(self) -> str:  # pytest parametrize id
        return self.label


def _model_litellm_factories() -> list[ModelAdapterFactory]:
    from adapters.model_litellm.testing import model_litellm_adapter

    return [ModelAdapterFactory(label="model_litellm", context=model_litellm_adapter)]


GRAPH_PORT_ADAPTERS: list[GraphAdapterFactory] = _graph_arcadedb_factories()
ANALYTICS_PORT_ADAPTERS: list[AnalyticsAdapterFactory] = _analytics_duckdb_factories()
COMPUTE_PORT_ADAPTERS: list[ComputePort] = []
MODEL_PORT_ADAPTERS: list[ModelAdapterFactory] = _model_litellm_factories()
