"""P12 part 2's exit (the orchestrator's rulings of 11 November): **Laurium reads a conforming
answer from a real model** through the gateway, by the route the cloud-platform render makes,
under a lease. Its own case, beside part 1's strict xfail on the 0.5B conformance model, which
stays.

**Live, so skipped unless pointed at a gateway** (`LITELLM_HOST`, `LITELLM_PORT`, `LITELLM_API_KEY`,
as `laurium_live_adapter` reads them) **and a model** (`OSPREY_LAURIUM_LIVE_MODEL`): the pinned
LiteLLM with its own database, serving a model that could answer Laurium's prompt. The client's own
engine is not reachable from the test server; the run that stands in for it, the gateway, the model
and the lease are in `process/lanes/case-b/P12p2_RED_RECORD.md`.

The same request as `test_suite.py`'s conforming-answer case: a schema of one required string, the
answer checked against it by the adapter before it is trusted, the name never blank. Laurium's own
key on the gateway for that model alone (decision 8), made before and deleted after by the factory,
which refuses a gateway already holding Laurium's key; any host but the gateway refused at the
lookup.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

from schemas.model import ExtractionRequest

from .laurium_in_process import laurium_live_adapter

MODEL = os.environ.get("OSPREY_LAURIUM_LIVE_MODEL", "")

pytestmark = [
    # One event loop for the module, as the Conduit and Laurium's service each run one: LangChain's
    # OpenAI client caches its HTTP client across instances, so a test on a fresh loop met the last
    # test's closed one ("Event loop is closed", run 2 of the first leased run; not the model's).
    pytest.mark.asyncio(loop_scope="module"),
    pytest.mark.skipif(
        not (MODEL and os.environ.get("LITELLM_PORT") and os.environ.get("LITELLM_API_KEY")),
        reason="live: set LITELLM_HOST/PORT/API_KEY (the pinned gateway with its own database) and "
        "OSPREY_LAURIUM_LIVE_MODEL (a model it serves), under a lease",
    ),
    pytest.mark.skipif(
        importlib.util.find_spec("laurium") is None,
        reason="needs Laurium's own Python 3.13 environment (make laurium-env)",
    ),
]

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}


@pytest.mark.parametrize("attempt", [1, 2, 3])
async def test_laurium_reads_a_conforming_answer_from_a_real_model(attempt: int) -> None:
    """Three runs, each its own: a model that answers Laurium once in three is not one it reads."""
    request = ExtractionRequest(
        document_id=f"doc-live-{attempt}",
        text="Extract the person's name mentioned: Owen Wilson went to the store.",
        json_schema=SCHEMA,
        model=MODEL,
    )
    async with laurium_live_adapter(MODEL) as adapter:
        result = await adapter.extract(request)
    assert result.document_id == request.document_id
    assert result.model == MODEL
    assert set(result.data) == {"name"}
    assert isinstance(result.data["name"], str) and result.data["name"].strip()
