"""Adapter registry for the port conformance suites.

Empty in Phase 0 — no adapter exists yet. Each port's `test_suite.py` is
parametrised over its list here, so an empty list means zero cases collected
(expected, not a failure). `test_guard.py` asserts the list is empty and that
`test_suite.py` imports cleanly, so a broken suite module fails loudly instead
of pytest silently reporting "no tests collected".

Phase 1 appends `adapters/graph_arcadedb` to `GRAPH_PORT_ADAPTERS` and the
parametrised suite starts producing real cases with no change to this file's
shape — only its contents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ports.analytics import AnalyticsPort
    from ports.compute import ComputePort
    from ports.graph import GraphPort
    from ports.model import ModelPort

GRAPH_PORT_ADAPTERS: list[GraphPort] = []
ANALYTICS_PORT_ADAPTERS: list[AnalyticsPort] = []
COMPUTE_PORT_ADAPTERS: list[ComputePort] = []
MODEL_PORT_ADAPTERS: list[ModelPort] = []
