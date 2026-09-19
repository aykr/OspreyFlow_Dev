"""`services/api/review.py`'s business logic (`run_extraction`/`accept_candidate`/
`reject_candidate`) — the real `ExtractionCandidateStore` (live Postgres, already proven directly
in `test_review_store.py`) plus a fake `ModelPort`/`GraphPort`, the same split
`tests/services/api/working_set/test_manual_resolution.py` uses for `WorkingSetService`.
"""

from __future__ import annotations

import pytest
from services.api.config import PostgresConfig
from services.api.review import (
    CandidateNotPendingError,
    CandidateStatus,
    ExtractionCandidateStore,
    accept_candidate,
    reject_candidate,
    run_extraction,
)
from services.extract.profile import ExtractionProfile

from conduit_common.identity import new_id
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, Handling, NodeWrite, Principal
from schemas.model import ExtractionRequest, ExtractionResult

ONTOLOGY = load_default_ontology()
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
SOURCE_TEXT = "Statement of: Dana MERCER. I received a call about Callum PRICE."


def _handling() -> Handling:
    return Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")


class _FakeModelPort:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data
        self.requests: list[ExtractionRequest] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.requests.append(req)
        return ExtractionResult(document_id=req.document_id, model=req.model, data=self.data)


class _FakeGraphPort:
    def __init__(self) -> None:
        self.upserted: list[NodeWrite] = []
        self._next_tx = 0

    async def begin_transaction(self) -> str:
        self._next_tx += 1
        return f"tx-{self._next_tx}"

    async def commit_transaction(self, tx: str) -> None:
        pass

    async def rollback_transaction(self, tx: str) -> None:
        pass

    async def upsert_nodes(self, nodes: list[NodeWrite], tx: str) -> list[str]:
        self.upserted.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: list[EdgeWrite], tx: str) -> list[str]:
        raise AssertionError("not exercised by these tests")


@pytest.fixture
async def store():
    s = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_run_extraction_persists_pending_candidates(store: ExtractionCandidateStore) -> None:
    document_id = new_id()
    model = _FakeModelPort(
        {"Person": [{"family_name": "MERCER", "given_names": "Dana", "confidence": 0.9}]}
    )
    profile = ExtractionProfile(["Person"])

    records = await run_extraction(
        model,
        ONTOLOGY,
        store,
        document_id=document_id,
        text=SOURCE_TEXT,
        profile=profile,
        handling=_handling(),
        principal=ANALYST,
        extraction_model="qwen2.5:0.5b-instruct",
    )

    assert len(records) == 1
    assert records[0].status == CandidateStatus.PENDING
    assert model.requests[0].document_id == document_id
    assert model.requests[0].model == "qwen2.5:0.5b-instruct"

    listed = await store.list_for_document(document_id, ANALYST)
    assert len(listed) == 1


async def test_run_extraction_persists_the_document_text_the_dossier_later_renders(
    store: ExtractionCandidateStore,
) -> None:
    """Phase 6a Stage 4 (B6): `run_extraction`'s own module docstring says `text` is "also
    persisted" — checked here against the real store `run_extraction` actually writes through
    (this file's own fake is `ModelPort`/`GraphPort` only), since no other test in this session
    called `run_extraction` itself and asserted the persisted text back out; every other new test
    exercises `store_document_text` directly rather than through the pipeline that is supposed to
    call it. Without this test, deleting `run_extraction`'s own `store_document_text` call left
    every existing test green — confirmed by reverting it and re-running this file."""
    document_id = new_id()
    model = _FakeModelPort(
        {"Person": [{"family_name": "MERCER", "given_names": "Dana", "confidence": 0.9}]}
    )
    profile = ExtractionProfile(["Person"])

    await run_extraction(
        model,
        ONTOLOGY,
        store,
        document_id=document_id,
        text=SOURCE_TEXT,
        profile=profile,
        handling=_handling(),
        principal=ANALYST,
        extraction_model="qwen2.5:0.5b-instruct",
    )

    assert await store.get_document_text(document_id, ANALYST) == SOURCE_TEXT


async def test_accept_candidate_writes_an_inferred_node_and_marks_accepted(
    store: ExtractionCandidateStore,
) -> None:
    model = _FakeModelPort({"Person": [{"family_name": "MERCER", "confidence": 0.9}]})
    profile = ExtractionProfile(["Person"])
    (record,) = await run_extraction(
        model,
        ONTOLOGY,
        store,
        document_id="doc-accept-1",
        text=SOURCE_TEXT,
        profile=profile,
        handling=_handling(),
        principal=ANALYST,
        extraction_model="m",
    )
    graph = _FakeGraphPort()

    node_id = await accept_candidate(store, graph, record.id, ANALYST)

    assert node_id == graph.upserted[0].id
    assert graph.upserted[0].provenance.state.value == "inferred"

    reviewed = await store.get_authorized(record.id, ANALYST)
    assert reviewed.status == CandidateStatus.ACCEPTED
    assert reviewed.node_id == node_id


async def test_accept_candidate_applies_a_properties_override() -> None:
    store = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    try:
        model = _FakeModelPort({"Person": [{"family_name": "MERCER", "confidence": 0.9}]})
        profile = ExtractionProfile(["Person"])
        (record,) = await run_extraction(
            model,
            ONTOLOGY,
            store,
            document_id="doc-edit-1",
            text=SOURCE_TEXT,
            profile=profile,
            handling=_handling(),
            principal=ANALYST,
            extraction_model="m",
        )
        graph = _FakeGraphPort()

        await accept_candidate(
            store, graph, record.id, ANALYST, properties_override={"given_names": "Danielle"}
        )

        assert graph.upserted[0].properties == {
            "family_name": "MERCER",
            "given_names": "Danielle",
        }
    finally:
        await store.close()


async def test_accept_candidate_twice_raises_not_pending(store: ExtractionCandidateStore) -> None:
    model = _FakeModelPort({"Person": [{"family_name": "MERCER", "confidence": 0.9}]})
    profile = ExtractionProfile(["Person"])
    (record,) = await run_extraction(
        model,
        ONTOLOGY,
        store,
        document_id="doc-twice-1",
        text=SOURCE_TEXT,
        profile=profile,
        handling=_handling(),
        principal=ANALYST,
        extraction_model="m",
    )
    graph = _FakeGraphPort()
    await accept_candidate(store, graph, record.id, ANALYST)

    with pytest.raises(CandidateNotPendingError):
        await accept_candidate(store, graph, record.id, ANALYST)


async def test_reject_candidate_marks_rejected_and_writes_no_node(
    store: ExtractionCandidateStore,
) -> None:
    model = _FakeModelPort({"Person": [{"family_name": "MERCER", "confidence": 0.9}]})
    profile = ExtractionProfile(["Person"])
    (record,) = await run_extraction(
        model,
        ONTOLOGY,
        store,
        document_id="doc-reject-1",
        text=SOURCE_TEXT,
        profile=profile,
        handling=_handling(),
        principal=ANALYST,
        extraction_model="m",
    )

    await reject_candidate(store, record.id, ANALYST)

    reviewed = await store.get_authorized(record.id, ANALYST)
    assert reviewed.status == CandidateStatus.REJECTED
    assert reviewed.node_id is None


async def test_reject_candidate_twice_raises_not_pending(store: ExtractionCandidateStore) -> None:
    model = _FakeModelPort({"Person": [{"family_name": "MERCER", "confidence": 0.9}]})
    profile = ExtractionProfile(["Person"])
    (record,) = await run_extraction(
        model,
        ONTOLOGY,
        store,
        document_id="doc-reject-twice-1",
        text=SOURCE_TEXT,
        profile=profile,
        handling=_handling(),
        principal=ANALYST,
        extraction_model="m",
    )
    await reject_candidate(store, record.id, ANALYST)

    with pytest.raises(CandidateNotPendingError):
        await reject_candidate(store, record.id, ANALYST)
