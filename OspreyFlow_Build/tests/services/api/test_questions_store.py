"""`PostgresQuestionStore` against real Postgres (`make dev-up`): the half the in-memory store in
`test_questions.py` cannot prove, that a question is written and read back whole, the Documents it
was read over included, and kept per case in the order asked (ADR-098 decision 4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from services.api.config import PostgresConfig
from services.api.questions import PostgresQuestionStore, QuestionEntry

from conduit_common.identity import new_id


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
