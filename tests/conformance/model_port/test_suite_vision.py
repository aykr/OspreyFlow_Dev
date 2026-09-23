"""`ModelPort.describe_image()` conformance cases — split from `test_suite.py` deliberately
(`docs/06_DECISIONS.md` ADR-020's Stage 2 addendum).

A vision-language model is materially heavier than the text/embedding/transcription pins
`test_suite.py` runs (1.8GB against 45MB–397MB), so its own CI job runs on a scheduled/
merge-to-main cadence rather than every PR — the same `02_GLASS_FRONTEND.md` §5 precedent
(a full performance-budget run is not repeated on every commit either). Splitting the file, not
just the CI job's test selection, means a contributor reading `test_suite.py` alone sees exactly
what runs on every PR without cross-referencing a CI YAML filter.

Same discipline as `test_suite.py`: shape and type only, never exact extracted content — a small
vision-language model's OCR/description output is at least as sensitive to hardware-dependent
drift as the text model's is.
"""

from __future__ import annotations

import pytest

from adapters.model_litellm import CONFORMANCE_VISION_MODEL
from schemas.model import VisionRequest
from tests.conformance.model_port.fixtures import png_bytes
from tests.conformance.registry import MODEL_PORT_ADAPTERS, ModelAdapterFactory

pytestmark = pytest.mark.parametrize("factory", MODEL_PORT_ADAPTERS, ids=str)


async def test_describe_image_returns_data_conforming_to_the_requested_schema(
    factory: ModelAdapterFactory,
) -> None:
    schema = {
        "type": "object",
        "properties": {"dominant_color": {"type": "string"}},
        "required": ["dominant_color"],
        "additionalProperties": False,
    }
    request = VisionRequest(
        document_id="image-1",
        image=png_bytes(rgb=(255, 0, 0)),
        text="What is the single dominant colour in this image?",
        json_schema=schema,
        model=CONFORMANCE_VISION_MODEL,
    )
    async with factory.context() as adapter:
        result = await adapter.describe_image(request)

    assert result.document_id == "image-1"
    assert result.model == CONFORMANCE_VISION_MODEL
    assert set(result.data) == {"dominant_color"}
    assert isinstance(result.data["dominant_color"], str)
    assert result.data["dominant_color"]  # never blank, even if the colour name is wrong
