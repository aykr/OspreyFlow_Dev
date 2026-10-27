"""`PostgresQuestionStore` against real Postgres (`make dev-up`): the half the in-memory store in
`test_questions.py` cannot prove, that a question is written and read back whole, the Documents it
was read over included, and kept per case in the order asked (ADR-098 decision 4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from services.api.config import PostgresConfig
from services.api.questions import GraphCitation, PostgresQuestionStore, QuestionEntry

from conduit_common.identity import new_id
from schemas.domain import Handling


@pytest.fixture
async def store():
    s = await PostgresQuestionStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


def _entry(case: str, at: datetime, question: str) -> QuestionEntry:
    return QuestionEntry(
        id=new_id(),
        investigation_id=case,
        author="analyst-1",
        question=question,
        answer="An answer [1].",
        document_ids=["doc-1"],
        read_ids=["doc-1", "doc-2"],
        candidate_ids=["c1", "c2"],
        unplaced=1,
        model="local-model",
        created_at=at,
        graph_node_ids=["node-1", "node-2"],
        graph_link_ids=["link-1"],
        graph_citations=[
            GraphCitation(
                number=1, label="[G-1]", node_ids=["node-1", "node-2"], link_ids=["link-1"]
            )
        ],
        event_handlings=[
            Handling(
                classification="SECRET",
                handling_code="P",
                originator="unit-1",
                owning_unit="unit-1",
            )
        ],
    )


async def test_a_question_round_trips_whole_and_cases_are_kept_apart(store) -> None:
    case, other = new_id(), new_id()
    now = datetime.now(UTC)
    later = _entry(case, now + timedelta(seconds=1), "second")
    first = _entry(case, now, "first")
    await store.add(later)
    await store.add(first)
    await store.add(_entry(other, now, "elsewhere"))
    listed = await store.list_for_case(case)
    assert [e.question for e in listed] == ["first", "second"]
    assert listed[0] == first


async def test_a_question_stored_before_graph_facts_reads_back_with_none(store) -> None:
    """ADR-129: the three columns were added to a table that may already hold rows. A row written
    without them (the INSERT of an earlier build) reads back whole, with no graph facts."""
    case = new_id()
    async with store._pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO case_questions (id, investigation_id, author, question, answer, "
            "document_ids, read_ids, candidate_ids, unplaced, model, created_at) "
            "VALUES ($1, $2, 'analyst-1', 'old', 'An old answer.', '[]', '[]', '[]', 0, "
            "'local-model', now())",
            new_id(),
            case,
        )
    (listed,) = await store.list_for_case(case)
    assert listed.question == "old"
    assert (listed.graph_node_ids, listed.graph_link_ids, listed.graph_citations) == ([], [], [])
