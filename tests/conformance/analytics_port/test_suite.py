"""`AnalyticsPort` conformance suite (`docs/07_BUILD_PLAN.md`, `00_ARCHITECTURE.md` §2.2).

Parametrised over `ANALYTICS_PORT_ADAPTERS` in `tests/conformance/registry.py`.
Empty in Phase 0 — zero cases collected (see `test_guard.py`). A later phase
registers `adapters/analytics_duckdb` and the real per-method assertions land
here; the parametrisation itself does not change.
"""

from __future__ import annotations

import pytest

from tests.conformance.registry import ANALYTICS_PORT_ADAPTERS


@pytest.mark.parametrize("adapter", ANALYTICS_PORT_ADAPTERS)
def test_analytics_port_conformance(adapter: object) -> None:
    assert adapter is not None
