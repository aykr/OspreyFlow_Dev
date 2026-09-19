"""Test-only construction for the `ComputePort` conformance suite.

No lifecycle to manage — `ComputeRustworkxAdapter` is stateless (no store connection, no schema),
the same shape `adapters/model_litellm/testing.py` already established for `ModelPort`. A plain
context manager still, matching `ComputeAdapterFactory`'s own `context()` shape in
`tests/conformance/registry.py` — consistent across every port's factory, not a special case for
the one adapter that happens not to need teardown.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .adapter import ComputeRustworkxAdapter


@asynccontextmanager
async def compute_rustworkx_adapter() -> AsyncIterator[ComputeRustworkxAdapter]:
    yield ComputeRustworkxAdapter()
