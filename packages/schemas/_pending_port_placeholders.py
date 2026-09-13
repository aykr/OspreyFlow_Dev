"""Placeholder — superseded by real design when each port's own phase lands.

Every name here exists only so `AnalyticsPort`, `ComputePort` and
`ModelPort` type-check and so the Pydantic-to-TypeScript drift gate has a
real model to run against, before those ports' own domain content exists.
Nothing here is domain content. `GraphPort`'s request/response types moved
to `schemas/domain.py` in Phase 1 — see
`tests/schemas/test_placeholder_lifecycle.py`.

Guarded by ``tests/schemas/test_placeholder_lifecycle.py``: this module must
no longer exist once *all three* of `ANALYTICS_PORT_ADAPTERS`,
`COMPUTE_PORT_ADAPTERS` and `MODEL_PORT_ADAPTERS`
(``tests/conformance/registry.py``) are non-empty.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class _Placeholder(BaseModel):
    """Common shape for every pending-port placeholder request/response type."""

    pending_port_note: str = Field(
        default="placeholder — see 00_ARCHITECTURE.md §2 for the port this belongs to",
        description="Marks this model as scaffolding, not domain content.",
    )


# --- AnalyticsPort -----------------------------------------------------------


class HistogramRequest(_Placeholder):
    pass


class Histogram(_Placeholder):
    pass


class GeoBinRequest(_Placeholder):
    pass


class GeoBin(_Placeholder):
    pass


class BaselineRequest(_Placeholder):
    pass


class BaselineResult(_Placeholder):
    pass


class CrossFilterRequest(_Placeholder):
    pass


# --- ComputePort -------------------------------------------------------------


class CentralityRequest(_Placeholder):
    pass


class CommunityRequest(_Placeholder):
    pass


class CliqueMetricRequest(_Placeholder):
    pass


class MotifRequest(_Placeholder):
    pass


class MotifMatch(_Placeholder):
    pass


# --- ModelPort ---------------------------------------------------------------


class ExtractionRequest(_Placeholder):
    pass


class ExtractionResult(_Placeholder):
    pass


class TranscribeRequest(_Placeholder):
    pass


class Transcript(_Placeholder):
    pass


class VisionRequest(_Placeholder):
    pass


class ImageAnalysis(_Placeholder):
    pass


ALL_MODELS: tuple[type[BaseModel], ...] = (
    HistogramRequest,
    Histogram,
    GeoBinRequest,
    GeoBin,
    BaselineRequest,
    BaselineResult,
    CrossFilterRequest,
    CentralityRequest,
    CommunityRequest,
    CliqueMetricRequest,
    MotifRequest,
    MotifMatch,
    ExtractionRequest,
    ExtractionResult,
    TranscribeRequest,
    Transcript,
    VisionRequest,
    ImageAnalysis,
)
