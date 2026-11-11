"""Rule 5 through the real service: Laurium's findings, from Laurium's own service code with Laurium
0.6.0 and LangChain in-process, reach the review queue `pending` through `run_extraction` and the
real `ExtractionCandidateStore`'s own write (`06_DECISIONS.md` ADR-135 Amendment 6 decision 6).

The gateway is the measured stand-in served over HTTP as `litellm`, answering one finding the document
states and one it does not. `tests/adapters/extract_laurium/review_queue.py` says what stands in for
asyncpg's pool under the store and what that does not prove (Postgres's own acceptance of the row:
`tests/services/api/test_review_store.py`, live). A plant that promotes (the store writing
`accepted`) turns this red (`P12_RED_RECORD.md`). Runs in Laurium's environment; skipped elsewhere.
"""

from __future__ import annotations

import pytest

pytest.importorskip("laurium", reason="Laurium is installed only in its own service's environment")

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig  # noqa: E402
from adapters.model_litellm.stand_in import StandInGateway  # noqa: E402
from tests.adapters.extract_laurium.review_queue import (  # noqa: E402
    ANSWER,
    MODEL,
    assert_queued_pending,
    extract_into_queue,
)

from .laurium_in_process import MASTER, laurium_service  # noqa: E402


async def test_lauriums_findings_reach_the_review_queue_pending_through_the_real_service() -> None:
    gateway = StandInGateway(
        master_key=MASTER,
        salt_key="salt",
        providers={},
        config_models=frozenset({MODEL}),
        answer=ANSWER,
    )
    with laurium_service(gateway) as running:
        adapter = ExtractLauriumAdapter(
            LauriumConfig(base_url="http://laurium", gateway_key=MASTER),
            transport=running.transport,
        )
        try:
            stored, rows = await extract_into_queue(adapter)
        finally:
            await adapter.aclose()
    assert running.refused == []
    assert gateway.asked == [MODEL]  # Laurium's own service asked the gateway, once
    assert_queued_pending(stored, rows)
