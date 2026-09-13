"""Phase 0 placeholder — superseded by 01_DOMAIN_MODEL.md in Phase 1.

Every name here exists only so that the four port `Protocol`s in `packages/ports`
type-check and so the Pydantic-to-TypeScript drift gate has a real model to run
against, before the real domain model exists. Nothing here is domain content.

Guarded by ``tests/schemas/test_placeholder_lifecycle.py``: this module must no
longer exist once any port's conformance registry (``tests/conformance/registry.py``)
is non-empty — see the Phase 0 plan, section 4.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Scalar identifiers. Plain str aliases: Phase 1's domain model gives these real
# (likely ULID-backed) shapes; only structural typing is needed here.
type NodeId = str
type EdgeId = str
type TxId = str
type CommunityId = str
type CliqueScore = float
type Vector = list[float]


class _Placeholder(BaseModel):
    """Common shape for every Phase 0 placeholder request/response type."""

    phase0_note: str = Field(
        default="placeholder — see 01_DOMAIN_MODEL.md",
        description="Marks this model as Phase 0 scaffolding, not domain content.",
    )


# --- GraphPort -------------------------------------------------------------


class NodeWrite(_Placeholder):
    pass


class EdgeWrite(_Placeholder):
    pass


class Node(_Placeholder):
    pass


class Principal(_Placeholder):
    pass


class ExpandRequest(_Placeholder):
    pass


class Subgraph(_Placeholder):
    pass


class PathRequest(_Placeholder):
    pass


class Path(_Placeholder):
    pass


class PatternQuery(_Placeholder):
    pass


class NeighbourhoodStats(_Placeholder):
    pass


class OntologySchema(_Placeholder):
    pass


class SchemaReport(_Placeholder):
    pass


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
    NodeWrite,
    EdgeWrite,
    Node,
    Principal,
    ExpandRequest,
    Subgraph,
    PathRequest,
    Path,
    PatternQuery,
    NeighbourhoodStats,
    OntologySchema,
    SchemaReport,
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
