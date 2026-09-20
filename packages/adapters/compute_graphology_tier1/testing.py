"""`ComputeAdapterFactory.context()` factory for `ComputeGraphologyTier1Adapter` — stateless, no
lifecycle, the same shape `compute_rustworkx/testing.py` already establishes: every method's own
input is the request's `Subgraph`, so there is nothing to set up or tear down per test."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .adapter import ComputeGraphologyTier1Adapter


@asynccontextmanager
async def compute_graphology_tier1_adapter() -> AsyncIterator[ComputeGraphologyTier1Adapter]:
    yield ComputeGraphologyTier1Adapter()
