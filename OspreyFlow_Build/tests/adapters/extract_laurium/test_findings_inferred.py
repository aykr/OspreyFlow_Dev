"""Laurium's findings arrive *inferred* (rule 5), traced to their document and span, exactly as Deep
read's do (`06_DECISIONS.md` ADR-135 Amendment 5 decision 4, Amendment 6 decision 6).

In the Conduit's environment, over the fake service (`fake_service.py`, held to the real service's
refusals) and the measured gateway stand-in behind it: `run_extraction` and the real
`ExtractionCandidateStore`'s `pending` write, down to the row its own `INSERT` sends
(`review_queue.py` says what stands in for asyncpg's pool and what that does not prove). The same
path through the **real service** in-process is
`tests/conformance/model_port/test_laurium_findings_pending.py`, in Laurium's environment. A plant
that promotes (the store writing `accepted`) turns both red (`P12_RED_RECORD.md`).
"""

from __future__ import annotations

import httpx

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig
from adapters.extract_laurium.keys import put_laurium_key
from adapters.model_litellm.stand_in import StandInGateway
from services.api.review import ExtractionCandidateStore
from tests.adapters.extract_laurium.fake_service import FakeLauriumService
from tests.adapters.extract_laurium.review_queue import (
    ANSWER,
    MODEL,
    PRINCIPAL,
    assert_queued_pending,
    extract_into_queue,
)

MASTER = "sk-planted-master-0002"


async def test_laurium_findings_reach_the_review_queue_pending() -> None:
    gateway = StandInGateway(
        master_key=MASTER,
        salt_key="salt",
        providers={},
        config_models=frozenset({MODEL}),
        answer=ANSWER,
    )
    async with httpx.AsyncClient(transport=gateway.transport(), base_url="http://litellm:4000") as c:
        await put_laurium_key(c, MASTER, [MODEL])
    service = FakeLauriumService(gateway)
    adapter = ExtractLauriumAdapter(
        LauriumConfig(base_url="http://laurium:8000", gateway_key=MASTER),
        transport=service.transport(),
    )
    try:
        stored, rows = await extract_into_queue(adapter)
    finally:
        await adapter.aclose()
    assert service.received, "the extraction went through Laurium's service"
    assert_queued_pending(stored, rows)


async def test_the_pools_stand_in_refuses_what_postgres_refuses() -> None:
    """Rule 15: the stand-in under the real store refuses a NULL where the store's own table says
    NOT NULL, values that do not match the statement, and a candidate's id twice."""
    import pytest

    from tests.adapters.extract_laurium.review_queue import REFUSALS, CandidateRows

    sql = (
        "INSERT INTO extraction_candidates (id, document_id, entity_type, properties, confidence, "
        "model, locator, excerpt_hash, handling, status, owning_unit, created_by, created_at, "
        "dataset_id, view_id) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, "
        "$14, $15)"
    )
    row = ("c1", "d", "Person", "{}", 0.9, "m", "char span 0-1", "h", "{}", "pending", "u", "a",
           "2026-11-11", None, None)  # fmt: skip
    rows = CandidateRows()
    await rows.executemany(sql, [row])
    with pytest.raises(REFUSALS["unique"]):
        await rows.executemany(sql, [row])
    with pytest.raises(REFUSALS["not_null"], match="status"):
        await rows.executemany(sql, [(*row[:9], None, *row[10:])])
    with pytest.raises(REFUSALS["arguments"]):
        await rows.executemany(sql, [row[:-1]])


async def test_the_pools_stand_in_keeps_a_transaction_whole() -> None:
    """Rule 15, the text and its search outbox row (ADR-150 decision 3): Postgres fills the outbox's
    `BIGSERIAL` key, so the same document queued twice is two rows, not a duplicate key; a NULL
    document is refused; and a transaction that raises leaves neither the text nor its outbox row."""
    import pytest

    from tests.adapters.extract_laurium.review_queue import REFUSALS, CandidateRows

    rows = CandidateRows()
    store = ExtractionCandidateStore(rows)  # type: ignore[arg-type]
    await store.store_document_text("d1", "text", PRINCIPAL)
    await store.store_document_text("d1", "text again", PRINCIPAL)
    assert [r["document_id"] for r in rows.rows["search_text_pending"]] == ["d1", "d1"]
    assert [r["text"] for r in rows.rows["document_texts"]] == ["text again"]
    with pytest.raises(REFUSALS["not_null"], match="document_id"):
        await rows.execute("INSERT INTO search_text_pending (document_id) VALUES ($1)", None)

    with pytest.raises(REFUSALS["not_null"]):
        async with rows.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO document_texts (document_id, text, owning_unit, created_at) "
                "VALUES ($1, $2, $3, $4)",
                "d2", "t", "u", "2026-11-13",
            )  # fmt: skip
            await conn.execute("INSERT INTO search_text_pending (document_id) VALUES ($1)", None)
    assert all(r["document_id"] != "d2" for r in rows.rows["document_texts"])
    assert len(rows.rows["search_text_pending"]) == 2
