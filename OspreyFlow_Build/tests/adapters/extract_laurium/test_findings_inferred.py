"""Laurium's findings arrive *inferred* (rule 5), traced to their document and span, exactly as Deep
read's do (`06_DECISIONS.md` ADR-135 Amendment 5 decision 4, Amendment 6 decision 6).

The real call site: `services/api/review.run_extraction`, the one path an extraction takes to the
review queue, given the Laurium adapter as its `ModelPort` (over `fake_service`, the stand-in gateway
behind it answering as a model would). It hands its candidates to the store's `store`, which writes
each `pending` (`ExtractionCandidateStore.store`, live-tested in `tests/services/api/test_review_store.py`);
nothing in the path writes to the graph. So the checks here: every finding reaches the store as a
candidate, not as an entity; each carries its document and a character span that is really the text
the document says; and a finding the document does not contain is dropped, not queued.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig
from adapters.model_litellm.stand_in import StandInGateway
from ontology.loader import load_default_ontology
from schemas.domain import Handling
from services.api.review import run_extraction
from services.extract.candidates import ExtractionCandidate
from services.extract.profile import ExtractionProfile
from tests.adapters.extract_laurium.fake_service import FakeLauriumService

MASTER = "sk-planted-master-0002"
MODEL = "qwen2.5:0.5b-instruct"
TEXT = "Statement taken on 3 March. Ada Lovelace met the witness outside the bank."


class _CapturingStore:
    """Stands in for `ExtractionCandidateStore`'s two writes, keeping what it was given."""

    def __init__(self) -> None:
        self.stored: list[ExtractionCandidate] = []
        self.texts: list[tuple[str, str]] = []

    async def store_document_text(self, document_id: str, text: str, principal: Any) -> None:
        self.texts.append((document_id, text))

    async def store(
        self, candidates: Sequence[ExtractionCandidate], principal: Any
    ) -> list[ExtractionCandidate]:
        self.stored.extend(candidates)
        return list(candidates)


async def test_laurium_findings_reach_the_review_queue_as_located_candidates() -> None:
    answer = {
        "Person": [
            {"family_name": "Lovelace", "given_names": "Ada", "confidence": 0.9},
            # Not in the document: no span to trace it to, so never queued.
            {"family_name": "Babbage", "given_names": "Charles", "confidence": 0.9},
        ]
    }
    gateway = StandInGateway(
        master_key=MASTER,
        salt_key="salt",
        providers={},
        config_models=frozenset({MODEL}),
        answer=json.dumps(answer),
    )
    service = FakeLauriumService(gateway)
    adapter = ExtractLauriumAdapter(
        LauriumConfig(base_url="http://laurium:8000", gateway_key=MASTER),
        transport=service.transport(),
    )
    store = _CapturingStore()
    handling = Handling(
        classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
    )
    stored = await run_extraction(
        adapter,
        load_default_ontology(),
        store,  # type: ignore[arg-type]
        document_id="doc-laurium-1",
        text=TEXT,
        profile=ExtractionProfile(["Person"]),
        handling=handling,
        principal=None,  # type: ignore[arg-type]
        extraction_model=MODEL,
    )
    await adapter.aclose()

    assert service.received, "the extraction went through Laurium's service"
    assert len(stored) == 1
    [candidate] = store.stored
    assert isinstance(candidate, ExtractionCandidate)  # a candidate, never an entity
    assert candidate.document_id == "doc-laurium-1"
    assert candidate.entity_type == "Person"
    start, end = (int(n) for n in candidate.locator.removeprefix("char span ").split("-"))
    assert TEXT[start:end] == "Lovelace"
    assert candidate.model == MODEL
    assert store.texts == [("doc-laurium-1", TEXT)]
