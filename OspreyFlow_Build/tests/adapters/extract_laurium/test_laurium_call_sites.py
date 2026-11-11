"""Only the review queue's route reaches Laurium (`06_DECISIONS.md` ADR-135 Amendment 9 point 2; the
orchestrator's round 1 on P12 part 2, its blocker): `run_extraction` is also how email extraction
(`EmailExtractionService.extract(using="model")`) and a document's content
(`DocumentContentService.extract(using="model")`) extract, so the marker is no longer set inside it;
`run_extraction(laurium_may_read=True)` is passed by the review queue's route alone.

At the email and document call sites, in their real call shape (each service's own `extract`, built
as its own tests build it, with its model composed as the Conduit composes it): **Deep read is asked
and Laurium is not.** The route's own call is read from its code: it alone passes the flag.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from adapters.extract_laurium.composed import LauriumExtracts
from schemas.model import ExtractionRequest, ExtractionResult


class _Laurium:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.asked.append(req.document_id)
        return ExtractionResult(document_id=req.document_id, model=req.model, data=json.loads("{}"))


def _composed(service: Any) -> _Laurium:
    laurium = _Laurium()
    service._model = LauriumExtracts(service._model, laurium)  # type: ignore[arg-type]  # noqa: SLF001
    return laurium


async def test_email_extraction_by_the_model_reaches_deep_read_not_laurium() -> None:
    from tests.services.api.test_email_extraction import ANALYST, TEXT, _build

    service, _, _, _, model = await _build()
    laurium = _composed(service)
    await service.extract("inv-1", "e1", "ev-1", ANALYST, using="model")
    assert [r.text for r in model.requests] == [TEXT]
    assert laurium.asked == []


async def test_a_documents_content_by_the_model_reaches_deep_read_not_laurium() -> None:
    from tests.services.api.test_document_content import ANALYST, _service

    service, _, _, _, _, _ = await _service()
    deep_read, laurium = _Laurium(), _Laurium()  # a recorder each; its media model has no extract
    service._model = LauriumExtracts(deep_read, laurium)  # type: ignore[arg-type]  # noqa: SLF001
    await service.extract("inv-1", "text-1", ANALYST, using="model")
    assert deep_read.asked == ["text-1"]
    assert laurium.asked == []


def test_the_review_queues_route_alone_passes_the_flag() -> None:
    from services.api import app as app_module
    from services.api import document_content, email_extraction

    route = inspect.getsource(app_module.run_extraction_route)
    assert "laurium_may_read=True" in route
    for module in (email_extraction, document_content):
        assert "laurium_may_read" not in inspect.getsource(module), module.__name__
