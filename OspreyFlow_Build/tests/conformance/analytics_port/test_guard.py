"""Guard test for the `AnalyticsPort` conformance suite — Phase 2 handover.

`ANALYTICS_PORT_ADAPTERS` was asserted empty through Phase 1; this is the
guard turning red on purpose, per the Phase 2 exit criterion
— the expected handover once `analytics_duckdb`
is registered, not a regression.
"""

from __future__ import annotations

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import ANALYTICS_PORT_ADAPTERS


def test_analytics_port_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.analytics_port.test_suite")


def test_analytics_port_registry_is_populated_from_phase_2() -> None:
    assert ANALYTICS_PORT_ADAPTERS != []
