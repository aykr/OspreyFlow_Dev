"""`ModelPort` conformance suite (`docs/07_BUILD_PLAN.md`, `00_ARCHITECTURE.md` §2.4).

Parametrised over `MODEL_PORT_ADAPTERS` in `tests/conformance/registry.py`.
Empty in Phase 0 — zero cases collected (see `test_guard.py`). A later phase
registers `adapters/model_litellm` and the real per-method assertions land
here; the parametrisation itself does not change.
"""

from __future__ import annotations

import pytest

from tests.conformance.registry import MODEL_PORT_ADAPTERS


@pytest.mark.parametrize("adapter", MODEL_PORT_ADAPTERS)
def test_model_port_conformance(adapter: object) -> None:
    assert adapter is not None
