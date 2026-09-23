"""`ModelLiteLLMAdapter` — `ModelPort` over a LiteLLM proxy (`docs/00_ARCHITECTURE.md` §2.4).

All four `ModelPort` methods are real from Stage 2.
`transcribe()` does not support diarisation yet — `TranscribeRequest.diarize=True` raises
`NotImplementedError` rather than silently returning every segment's `speaker` as `None` as if
diarisation had run and found nothing; a disclosed Phase 6 gap, not a silent stub.

`embed()`'s own model is fixed at construction, not per call, unlike `extract()`'s
`ExtractionRequest.model`: `ports/model.py`'s `ModelPort.embed(texts)` protocol (authored in
Phase 0) takes no per-call model argument, and a deployment realistically runs one canonical
embedding model rather than choosing between several per call the way extraction reasonably might
— `osprey.yaml` is where a real deployment would configure this adapter's `embed_model`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from schemas.domain import Vector
from schemas.model import (
    ExtractionRequest,
    ExtractionResult,
    ImageAnalysis,
    TranscribeRequest,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
    VisionRequest,
)

from .client import LiteLLMClient


class ModelLiteLLMAdapter:
    def __init__(self, client: LiteLLMClient, *, embed_model: str) -> None:
        self._client = client
        self._embed_model = embed_model

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        data = await self._client.extract_json(
            model=req.model, text=req.text, response_schema=req.json_schema
        )
        return ExtractionResult(document_id=req.document_id, model=req.model, data=data)

    async def transcribe(self, req: TranscribeRequest) -> Transcript:
        if req.diarize:
            raise NotImplementedError(
                "ModelLiteLLMAdapter.transcribe: diarisation is not implemented "
                "(a disclosed gap) — call with diarize=False"
            )
        body = await self._client.transcribe(
            model=req.model, audio=req.audio, language=req.language
        )
        segments = [
            TranscriptSegment(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"].strip(),
                words=[
                    TranscriptWord(start=w["start"], end=w["end"], text=w["word"].strip())
                    for w in (seg.get("words") or [])
                ],
            )
            for seg in body["segments"]
        ]
        return Transcript(
            document_id=req.document_id,
            model=req.model,
            language=body["language"],
            segments=segments,
        )

    async def describe_image(self, req: VisionRequest) -> ImageAnalysis:
        data: dict[str, Any] = await self._client.extract_json(
            model=req.model, text=req.text, response_schema=req.json_schema, image=req.image
        )
        return ImageAnalysis(document_id=req.document_id, model=req.model, data=data)

    async def embed(self, texts: Sequence[str]) -> list[Vector]:
        return await self._client.embed(self._embed_model, texts)
