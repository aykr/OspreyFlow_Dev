"""Laurium serves document extraction into the review queue alone (`06_DECISIONS.md` ADR-135
Amendment 9; the orchestrator's ruling of 11 November on the lane-reviewer's item 2, a rule 11 gap):
`services.api.review.run_extraction`, when the review queue's route passes `laurium_may_read`, sets
the marker (`adapters.extract_laurium.composed.laurium_reads`), and only inside it does `LauriumExtracts` send
`extract` to Laurium. Every other caller of `ModelPort.extract` (Questions, Ask to search, email
extraction, a document's content) stays with Deep read: Ask to search's schema writes an untyped
`items`, which Laurium's mapper refuses, and Questions joins every document into one call.

Through the real `run_extraction` and the real store (`review_queue.extract_into_queue`), and through
a direct call, as the other callers make it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from adapters.extract_laurium.composed import LauriumExtracts, laurium_reads
from schemas.model import ExtractionRequest, ExtractionResult
from tests.adapters.extract_laurium.review_queue import (
    ANSWER,
    MODEL,
    assert_queued_pending,
    extract_into_queue,
)


class _Engine:
    def __init__(self, name: str) -> None:
        self.name = name
        self.asked: list[str] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.asked.append(req.document_id)
        return ExtractionResult(
            document_id=req.document_id, model=req.model, data=json.loads(ANSWER)
        )

    async def transcribe(self, req: Any) -> Any:
        raise AssertionError("not asked")

    async def describe_image(self, req: Any) -> Any:
        raise AssertionError("not asked")

    async def embed(self, texts: Sequence[str]) -> Any:
        raise AssertionError("not asked")


def _model() -> tuple[LauriumExtracts, _Engine, _Engine]:
    deep_read, laurium = _Engine("deep_read"), _Engine("laurium")
    return LauriumExtracts(deep_read, laurium), deep_read, laurium  # type: ignore[arg-type]


async def test_the_review_queues_extraction_goes_to_laurium() -> None:
    model, deep_read, laurium = _model()
    # As the review queue's route calls it (`laurium_may_read=True`, its alone).
    stored, rows = await extract_into_queue(model, laurium_may_read=True)  # type: ignore[arg-type]
    assert laurium.asked and not deep_read.asked
    assert_queued_pending(stored, rows)


async def test_every_other_caller_stays_with_deep_read() -> None:
    model, deep_read, laurium = _model()
    request = ExtractionRequest(
        document_id="q-1", text="Who met whom?", json_schema={"type": "object"}, model=MODEL
    )
    await model.extract(request)
    assert deep_read.asked == ["q-1"] and not laurium.asked


async def test_the_marker_ends_with_its_block() -> None:
    model, deep_read, laurium = _model()
    request = ExtractionRequest(
        document_id="d", text="t", json_schema={"type": "object"}, model=MODEL
    )
    with laurium_reads():
        await model.extract(request)
    await model.extract(request)
    assert laurium.asked == ["d"] and deep_read.asked == ["d"]
