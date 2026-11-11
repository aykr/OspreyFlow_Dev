"""`ModelPort` conformance suite (`00_ARCHITECTURE.md` §2.4).

Parametrised over `MODEL_PORT_ADAPTERS` in `tests/conformance/registry.py`: the LiteLLM adapter, and
Laurium's (`extract` only, ADR-135 Amendment 6, run in Laurium's own environment; each case asks
`factory.require`, so a case an adapter does not implement is skipped saying so). `extract()`,
`embed()` and `transcribe()` are tested here — `describe_image()` has its own file
(`test_suite_vision.py`), run on a slower CI cadence than this one
(`06_DECISIONS.md` ADR-020's Stage 2 addendum) since a vision-language model is materially heavier
than any of the other three.

What this proves is the *contract* — schema in, schema-conforming structured output out, a
malformed schema rejected before any model call, one embedding vector back per text in, and a
transcription with correctly-shaped, correctly-ordered segments/words out — never extraction,
embedding or transcription *quality*. Quality (precision/recall against hand-labelled documents)
is the golden set's job (Stage 3), run less frequently: even a pinned, digest-locked small model
(`06_DECISIONS.md` ADR-020) can have minor hardware-dependent output drift, so this suite never
asserts exact output text or exact vector values — checked directly, not assumed: the
witness-statement smoke test (`tests/scenarios/test_witness_statement_extraction.py`) originally
asserted a specific extracted name and failed intermittently across repeated runs against this
exact pinned model before that assertion was weakened to shape-only.
"""

from __future__ import annotations

import pytest

from adapters.model_litellm import CONFORMANCE_MODEL, CONFORMANCE_TRANSCRIBE_MODEL
from adapters.model_litellm.errors import ExtractionFailedError, InvalidExtractionSchemaError
from schemas.model import ExtractionRequest, TranscribeRequest
from tests.conformance.model_port.fixtures import SAMPLE_SPEECH_WAV
from tests.conformance.registry import MODEL_PORT_ADAPTERS, ModelAdapterFactory

pytestmark = pytest.mark.parametrize("factory", MODEL_PORT_ADAPTERS, ids=str)

#: ADR-135 Amendment 6 (P12 part 1, round 2; the orchestrator's ruling of 11 November): Laurium
#: cannot read the pinned conformance model's answer to its prompt, 3 tries of 3 on the real
#: gateway (`process/lanes/case-b/gates/8190228d.live-*.txt`). Expected to fail for that model
#: alone, by that refusal alone, and strictly, so the case fails the day it starts passing. Every
#: other Laurium case stays a hard pass. Part 2's exit holds Laurium to a conforming answer from
#: the client's own engine.
LAURIUM_UNPARSEABLE_ON_CONFORMANCE_MODEL = pytest.mark.xfail(
    strict=True,
    raises=ExtractionFailedError,
    reason="Laurium cannot read the pinned 0.5B conformance model's answer to its prompt "
    "(unparseable, 3 of 3; process/lanes/case-b/gates/8190228d.live-stack-c.txt)",
)


async def test_extract_returns_data_conforming_to_the_requested_schema(
    factory: ModelAdapterFactory, request: pytest.FixtureRequest
) -> None:
    factory.require("extract")
    if factory.label == "extract_laurium":
        request.applymarker(LAURIUM_UNPARSEABLE_ON_CONFORMANCE_MODEL)
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    req = ExtractionRequest(
        document_id="doc-1",
        text="Extract the person's name mentioned: Owen Wilson went to the store.",
        json_schema=schema,
        model=CONFORMANCE_MODEL,
    )
    async with factory.context() as adapter:
        result = await adapter.extract(req)

    assert result.document_id == "doc-1"
    assert result.model == CONFORMANCE_MODEL
    assert set(result.data) == {"name"}
    assert isinstance(result.data["name"], str)
    assert result.data["name"]  # a small model may not extract it exactly, but never blank


async def test_extract_rejects_a_malformed_schema_before_calling_the_model(
    factory: ModelAdapterFactory,
) -> None:
    factory.require("extract")
    not_a_schema = {"type": "not-a-real-json-schema-type"}
    request = ExtractionRequest(
        document_id="doc-2", text="irrelevant", json_schema=not_a_schema, model=CONFORMANCE_MODEL
    )
    async with factory.context() as adapter:
        with pytest.raises(InvalidExtractionSchemaError):
            await adapter.extract(request)


async def test_embed_returns_one_equal_length_vector_per_text_in_order(
    factory: ModelAdapterFactory,
) -> None:
    factory.require("embed")
    texts = ["Owen Wilson", "a completely unrelated sentence about the weather"]
    async with factory.context() as adapter:
        vectors = await adapter.embed(texts)

    assert len(vectors) == len(texts)
    dims = {len(v) for v in vectors}
    assert len(dims) == 1  # every vector the same length
    assert next(iter(dims)) > 0
    assert all(isinstance(x, float) for v in vectors for x in v)
    assert any(x != 0.0 for v in vectors for x in v)  # not a degenerate all-zero response


async def test_embed_of_no_texts_returns_no_vectors(factory: ModelAdapterFactory) -> None:
    factory.require("embed")
    async with factory.context() as adapter:
        assert await adapter.embed([]) == []


async def test_transcribe_returns_correctly_shaped_segments_and_words(
    factory: ModelAdapterFactory,
) -> None:
    factory.require("transcribe")
    request = TranscribeRequest(
        document_id="audio-1",
        audio=SAMPLE_SPEECH_WAV,
        model=CONFORMANCE_TRANSCRIBE_MODEL,
    )
    async with factory.context() as adapter:
        transcript = await adapter.transcribe(request)

    assert transcript.document_id == "audio-1"
    assert transcript.model == CONFORMANCE_TRANSCRIBE_MODEL
    assert isinstance(transcript.language, str) and transcript.language
    assert transcript.segments  # the fixture is real (synthetic) speech, never silence
    for segment in transcript.segments:
        assert isinstance(segment.text, str) and segment.text
        assert isinstance(segment.start, float) and isinstance(segment.end, float)
        assert segment.end >= segment.start
        assert segment.speaker is None  # no diarisation this stage
        for word in segment.words:
            assert isinstance(word.text, str) and word.text
            assert word.end >= word.start


async def test_transcribe_with_diarize_raises_not_implemented(
    factory: ModelAdapterFactory,
) -> None:
    factory.require("transcribe")
    request = TranscribeRequest(
        document_id="audio-2",
        audio=SAMPLE_SPEECH_WAV,
        diarize=True,
        model=CONFORMANCE_TRANSCRIBE_MODEL,
    )
    async with factory.context() as adapter:
        with pytest.raises(NotImplementedError):
            await adapter.transcribe(request)
