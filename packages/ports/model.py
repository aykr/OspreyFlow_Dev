"""`ModelPort` — `docs/00_ARCHITECTURE.md` §2.4.

Language, speech and vision inference. One OpenAI-compatible base URL, one
config file, behind a LiteLLM proxy.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from schemas._phase0_placeholders import (
    ExtractionRequest,
    ExtractionResult,
    ImageAnalysis,
    TranscribeRequest,
    Transcript,
    Vector,
    VisionRequest,
)


class ModelPort(Protocol):
    async def extract(self, req: ExtractionRequest) -> ExtractionResult: ...
    async def transcribe(self, req: TranscribeRequest) -> Transcript: ...
    async def describe_image(self, req: VisionRequest) -> ImageAnalysis: ...
    async def embed(self, texts: Sequence[str]) -> list[Vector]: ...
