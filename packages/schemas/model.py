"""`ModelPort` domain types — `docs/00_ARCHITECTURE.md` §2.4.

Real types replacing `_pending_port_placeholders`'s stand-ins once each pair's own stage registers
an adapter that implements it — `ExtractionRequest`/`ExtractionResult` in Stage 1,
`TranscribeRequest`/`Transcript`/`VisionRequest`/`ImageAnalysis` in Stage 2 — see
`tests/schemas/test_placeholder_lifecycle.py`.

`ExtractionRequest.json_schema`/`VisionRequest.json_schema` are caller-supplied, not generated
here. ADR-005: the actual requirement is "send a document and a JSON Schema, get conforming
structured output" — a direct `ModelPort` call, not a framework that owns schema generation. The
Ingest Studio's extraction profile (`09_INGEST_STUDIO.md` §4, Stage 6) is what builds a schema from
the ontology's POLE-class checklist; nothing here assumes what one looks like beyond "a JSON Schema
object", so `extract()`/`describe_image()`'s results carry no per-element span/confidence shape of
their own — that shape is Stage 6's schema to design, and `.data` is simply whatever the caller's
schema said it should be.

`Transcript` is not schema-constrained the same way — a transcription's shape is fixed (segments,
word timings), not caller-chosen, so it gets concrete fields instead of a `data: dict`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from schemas.domain import DocumentId


class ExtractionRequest(BaseModel):
    document_id: DocumentId
    text: str
    #: A JSON Schema object. `extract()` uses it for constrained decoding — the model's output is
    #: guaranteed to validate against it, not merely asked to. Named `json_schema`, not `schema`,
    #: since the latter shadows `BaseModel`'s own method of that name.
    json_schema: dict[str, Any]
    #: Which model to route to, e.g. `"qwen2.5:0.5b-instruct"` — the LiteLLM proxy resolves this
    #: name to a backend (`06_DECISIONS.md` ADR-020 pins the one the conformance suite runs
    #: against; a deployment's own `osprey.yaml` may point extraction at a larger model instead).
    model: str


class ExtractionResult(BaseModel):
    document_id: DocumentId
    #: The model identifier and version that produced this result — carried onto
    #: `Provenance.extracted_by` (`01_DOMAIN_MODEL.md` §2.1) by whichever stage turns this into a
    #: graph write.
    model: str
    #: The schema-conforming structured output. Shape is whatever the request's `json_schema`
    #: declared.
    data: dict[str, Any]


class TranscribeRequest(BaseModel):
    document_id: DocumentId
    audio: bytes
    #: BCP-47-ish language hint (e.g. `"en"`) or `None` to let the model detect it.
    language: str | None = None
    #: Speaker diarisation is not implemented yet, a disclosed gap — `transcribe()` raises
    #: `NotImplementedError` if this is `True`, rather than
    #: silently returning `TranscriptSegment.speaker = None` as if diarisation had run and found
    #: nothing.
    diarize: bool = False
    model: str


class TranscriptWord(BaseModel):
    start: float
    end: float
    text: str


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    #: Always `None` until diarisation lands — never a guess.
    speaker: str | None = None
    words: list[TranscriptWord] = []


class Transcript(BaseModel):
    document_id: DocumentId
    model: str
    language: str
    segments: list[TranscriptSegment]


class VisionRequest(BaseModel):
    document_id: DocumentId
    image: bytes
    #: The instruction paired with the image — "describe the scene", "read any visible text",
    #: "list distinct objects" — `09_INGEST_STUDIO.md` §4's extraction-profile checkboxes (OCR,
    #: scene description, object detection) become this prompt plus `json_schema`'s shape; neither
    #: is generated here, same reasoning as `ExtractionRequest.json_schema` above.
    text: str
    json_schema: dict[str, Any]
    model: str


class ImageAnalysis(BaseModel):
    document_id: DocumentId
    model: str
    data: dict[str, Any]


ALL_MODELS: tuple[type[BaseModel], ...] = (
    ExtractionRequest,
    ExtractionResult,
    TranscribeRequest,
    TranscriptWord,
    TranscriptSegment,
    Transcript,
    VisionRequest,
    ImageAnalysis,
)
